"""Pinned noEmbryo refiner arithmetic; sampler donor supplied by Timeline. See NOTICE.md."""

import torch
import logging
log_=logging.getLogger("longcaster_noembryo")
_H3_FRAME_PER_TOKEN=(1,4,4,4,4)

def _band_gauss1d(sigma, device, dtype):
    r = max(1, int(round(3.0 * float(sigma))))
    x = torch.arange(-r, r + 1, dtype=torch.float32, device=device)
    k = torch.exp(-(x * x) / (2.0 * float(sigma) ** 2))
    return (k / k.sum()).to(dtype)

def _band_split(t, sigma=2.0):
    """Separable Gaussian low/high split over the last two dims. -> (lo, hi).

    Returns None when the tensor has no spatial extent to speak of.
    Replicate padding, not reflect: a latent's spatial dims are small and
    reflect needs the pad to be smaller than the dimension.
    """
    if t.dim() < 2 or t.shape[-1] < 8 or t.shape[-2] < 8:
        return None
    # noinspection PyUnresolvedReferences
    import torch.nn.functional as f
    h, w = int(t.shape[-2]), int(t.shape[-1])
    flat = t.reshape(-1, 1, h, w)
    k = _band_gauss1d(sigma, t.device, t.dtype)
    pad = k.numel() // 2
    lo = f.conv2d(f.pad(flat, (pad, pad, 0, 0), mode="replicate"),
                  k.view(1, 1, 1, -1))
    lo = f.conv2d(f.pad(lo, (0, 0, pad, pad), mode="replicate"),
                  k.view(1, 1, -1, 1))
    lo = lo.reshape(t.shape)
    return lo, t - lo

def _high_band_sd(t, sigma=2.0):
    """Absolute high-band standard deviation. -> float, or None.

    The band *ratio* only drifts ~1.6% across a chain (0.3643 -> 0.3702),
    so a gain match on the ratio moves a tiny delta that strength cannot
    amplify visibly. The absolute high-band sigma can drift much more when
    the total sigma also grows, so matching the absolute value gives a
    correction delta that is large enough for strength to move.
    """
    got = _band_split(t, sigma)
    if got is None:
        return None
    _, hi = got
    hi_sd = float(hi.float().std())
    if not hi_sd or hi_sd != hi_sd:
        return None
    return hi_sd

class _AVStreamPair:
    """Minimal stand-in for a NestedTensor: wraps (video, audio) tensors and
    exposes the unbind() interface that comfy-core's LTXVSeparateAVLatent
    (and the H3 sampler code) expects. The wrapped tensors are always dense,
    detached, contiguous copies, so they are safe to feed to the VAE kernels.
    """

    def __init__(self, video, audio):
        self._parts = [video, audio]

    def unbind(self):
        # noinspection PyTypeChecker
        return tuple(self._parts)

    def __iter__(self):
        return iter(self._parts)

    def __len__(self):
        return len(self._parts)

def _steps_for_frames(n):
    """ Latent steps covering exactly n pixel frames from cycle position 0.

    Mirrors H3-Motion-Context's own _steps_for_frames: 5/22/39/56 -> 2/7/12/17.
    Returns None when n does not land on a whole token boundary (e.g. 3).
    """
    n = int(n)
    if n <= 0:
        return None
    covered = 0
    k = 0
    while covered < n:
        covered += _H3_FRAME_PER_TOKEN[k % len(_H3_FRAME_PER_TOKEN)]
        k += 1
    return k if covered == n else None

def refine(latent, strength, context_length, reference_latent=None, model=None, positive=None, negative=None, refine_denoise=0.4, refine_steps=3, refine_cfg=1.0, sampler_name='euler', scheduler='normal', seed=0, detail_strength=1.0, detail_donor=None):
    if not isinstance(latent, dict) or 'samples' not in latent:
        raise ValueError("H3ClipRefiner: expected a latent dict with 'samples' key")
    samples = latent['samples']
    if hasattr(samples, 'unbind'):
        parts = list(samples.unbind())
    elif isinstance(samples, (tuple, list)):
        parts = list(samples)
    else:
        raise ValueError('H3ClipRefiner: expected AV latent with video+audio')
    if len(parts) < 2:
        raise ValueError('H3ClipRefiner: latent has no audio stream')
    video_latent = parts[0].detach().to('cpu', copy=True).contiguous()
    audio_latent = parts[1].detach().to('cpu', copy=True).contiguous()
    had_batch = False
    if video_latent.dim() == 5:
        if video_latent.shape[0] != 1:
            raise ValueError('H3ClipRefiner: only batch size 1 is supported, got video shape %s.' % (tuple(video_latent.shape),))
        had_batch = True
        video_latent = video_latent.squeeze(0)
    c, t, h, w = video_latent.shape
    overlap = _steps_for_frames(context_length) or 0
    if overlap > 0 and t >= 2 * overlap:
        head = video_latent[:, :overlap]
        body = video_latent[:, overlap:t - overlap]
        tail = video_latent[:, t - overlap:]
        has_overlap = True
    else:
        head = None
        body = video_latent
        tail = None
        has_overlap = False
    refined_body = None
    if detail_donor is not None and detail_strength > 0.0:
        refined_video=detail_donor.detach().to('cpu',copy=True).to(video_latent.dtype)
        if refined_video.dim()==5:refined_video=refined_video[0]
        if refined_video.shape!=video_latent.shape:raise ValueError('Refine donor geometry differs')
        if has_overlap:
            refined_head=refined_video[:,:overlap]
            refined_body=refined_video[:,overlap:t-overlap]
            refined_tail=refined_video[:,t-overlap:]
        else:
            refined_head=None;refined_body=refined_video;refined_tail=None

    body_flat = body.reshape(c * body.shape[1], h, w)
    flat_latent = video_latent.reshape(c * t, h, w)
    current_mean = float(body_flat.mean())
    current_std = float(body_flat.std())
    current_channel_means = body.mean(dim=(1, 2, 3))
    current_channel_stds = body.std(dim=(1, 2, 3))
    hi_sds = []
    for s in [1.0, 2.0, 3.0]:
        hs = _high_band_sd(body_flat, sigma=s)
        if hs is not None:
            hi_sds.append(hs)
    current_hi_sd = sum(hi_sds) / len(hi_sds) if hi_sds else None
    target_mean = current_mean
    target_std_val = current_std
    target_channel_means = current_channel_means.clone()
    target_channel_stds = current_channel_stds.clone()
    target_hi_sd = current_hi_sd
    if reference_latent is not None:
        if not isinstance(reference_latent, dict) or 'samples' not in reference_latent:
            raise ValueError('H3ClipRefiner: reference_latent must be an AV latent dict')
        ref_samples = reference_latent['samples']
        if hasattr(ref_samples, 'unbind'):
            ref_parts = list(ref_samples.unbind())
        elif isinstance(ref_samples, (tuple, list)):
            ref_parts = list(ref_samples)
        else:
            raise ValueError('H3ClipRefiner: reference_latent must be AV latent')
        if len(ref_parts) < 2:
            raise ValueError('H3ClipRefiner: reference_latent has no audio stream')
        ref_video = ref_parts[0].detach().to('cpu', copy=True).contiguous()
        if ref_video.dim() == 5:
            ref_video = ref_video.squeeze(0)
        ref_overlap = overlap
        if ref_overlap > 0 and ref_video.shape[1] >= 2 * ref_overlap:
            ref_body = ref_video[:, ref_overlap:ref_video.shape[1] - ref_overlap]
        else:
            ref_body = ref_video
        ref_flat = ref_body.reshape(-1, ref_body.shape[-2], ref_body.shape[-1])
        target_mean = float(ref_flat.mean())
        target_std_val = float(ref_flat.std())
        target_channel_means = ref_body.mean(dim=(1, 2, 3))
        target_channel_stds = ref_body.std(dim=(1, 2, 3))
        ref_hi_sds = []
        for s in [1.0, 2.0, 3.0]:
            hs = _high_band_sd(ref_flat, sigma=s)
            if hs is not None:
                ref_hi_sds.append(hs)
        if ref_hi_sds:
            target_hi_sd = sum(ref_hi_sds) / len(ref_hi_sds)
        log_.info('H3ClipRefiner: measured targets from reference_latent: mean=%.4f, std=%.4f, hi_sd=%.4f', target_mean, target_std_val, target_hi_sd)
    report_parts = ['H3ClipRefiner: mean=%.4f->%.4f' % (current_mean, target_mean), 'std=%.4f->%.4f' % (current_std, target_std_val)]
    if current_hi_sd is not None:
        report_parts.append('hi_sd=%.4f->%.4f' % (current_hi_sd, target_hi_sd))
    else:
        report_parts.append('hi_sd=N/A')
    needs_correction = False
    if abs(target_mean - current_mean) > 1e-06:
        needs_correction = True
    if abs(target_std_val - current_std) > 1e-06:
        needs_correction = True
    if (target_channel_means - current_channel_means).abs().max() > 1e-06:
        needs_correction = True
    if current_hi_sd is not None and target_hi_sd is not None:
        if abs(target_hi_sd - current_hi_sd) > 1e-06:
            needs_correction = True
    if refined_body is None and (strength <= 0 or not needs_correction):
        report = ', '.join(report_parts)
        report += ' [MEASURE ONLY - latent passed through]'
        return (latent, report)
    band_gain = None
    corrected_body = body
    if strength > 0 and needs_correction:
        a = torch.ones(c, device=video_latent.device, dtype=video_latent.dtype)
        b = torch.zeros(c, device=video_latent.device, dtype=video_latent.dtype)
        for ch in range(c):
            ch_data = body[ch]
            ch_mean = float(ch_data.mean())
            ch_std = float(ch_data.std())
            if ch_std < 1e-06:
                ch_std = 1e-06
            tgt_ch_mean = float(target_channel_means[ch])
            tgt_ch_std = float(target_channel_stds[ch])
            scale = tgt_ch_std / ch_std
            shift = tgt_ch_mean - scale * ch_mean
            a[ch] = scale
            b[ch] = shift
        corrected_body = body * a.view(c, 1, 1, 1) + b.view(c, 1, 1, 1)
        log_.info('H3ClipRefiner: per-channel affine: a=%s, b=%s', a.tolist(), b.tolist())
        if refined_body is None and current_hi_sd is not None and (target_hi_sd is not None):
            if abs(target_hi_sd - current_hi_sd) > 1e-06:
                corr_body_flat = corrected_body.reshape(c * body.shape[1], h, w)
                corr_split = _band_split(corr_body_flat, sigma=2.0)
                if corr_split is not None:
                    corr_lo, corr_hi = corr_split
                    cur_hi = float(corr_hi.float().std())
                    if cur_hi > 1e-06:
                        k_1to1 = target_hi_sd / cur_hi
                        k_1to1 = min(max(k_1to1, 0.05), 5.0)
                        corrected_body = (corr_lo + corr_hi * k_1to1).reshape(c, body.shape[1], h, w)
                        band_gain = k_1to1
                        report_parts.append('band_gain=%.4f' % band_gain)
                    else:
                        report_parts.append('band_correction_failed')
                else:
                    report_parts.append('band_correction_failed')
        corrected_body = body + (corrected_body - body) * strength
    if has_overlap:
        corrected_head = head
        corrected_tail = tail
    if refined_body is not None:
        log_.info('H3ClipRefiner: performing detail transfer (strength=%.2f)...', detail_strength)
        d = float(min(max(detail_strength, 0.0), 1.0))

        def _detail_transfer(corrected_reg, refined_reg, region_name):
            if corrected_reg is None or refined_reg is None:
                return corrected_reg
            corr_flat = corrected_reg.reshape(c * corrected_reg.shape[1], h, w)
            ref_flat = refined_reg.reshape(c * refined_reg.shape[1], h, w)
            corr_split = _band_split(corr_flat, sigma=2.0)
            ref_split = _band_split(ref_flat, sigma=2.0)
            if corr_split is not None and ref_split is not None:
                corr_lo, corr_hi = corr_split
                _, ref_hi = ref_split
                mixed_hi = corr_hi * (1.0 - d) + ref_hi.to(corr_hi.dtype) * d
                result = (corr_lo + mixed_hi).reshape(c, corrected_reg.shape[1], h, w)
                log_.info('H3ClipRefiner: detail transfer applied to %s', region_name)
                return result
            else:
                log_.warning('H3ClipRefiner: detail transfer failed for %s - band split returned None', region_name)
                return corrected_reg
        corrected_body = _detail_transfer(corrected_body, refined_body, 'body')
        if has_overlap:
            corrected_head = _detail_transfer(corrected_head, refined_head, 'head')
            corrected_tail = _detail_transfer(corrected_tail, refined_tail, 'tail')
        report_parts.append('detail_transfer=%.2f' % d)
        log_.info('H3ClipRefiner: detail transfer applied successfully')
    body_changed = not torch.allclose(corrected_body, body, rtol=0.0001, atol=1e-05)
    if has_overlap and (body_changed or refined_body is not None):
        target_ch_means = corrected_body.mean(dim=(1, 2, 3))
        target_ch_stds = corrected_body.std(dim=(1, 2, 3))

        def _correct_region(region, region_name):
            if region is None:
                return None
            reg_ch_means = region.mean(dim=(1, 2, 3))
            reg_ch_stds = region.std(dim=(1, 2, 3)).clamp(min=1e-06)
            a_reg = target_ch_stds / reg_ch_stds
            b_reg = target_ch_means - a_reg * reg_ch_means
            corrected_reg = region * a_reg.view(c, 1, 1, 1) + b_reg.view(c, 1, 1, 1)
            corrected_reg = region + (corrected_reg - region) * strength
            if band_gain is not None:
                reg_flat = corrected_reg.reshape(c * region.shape[1], h, w)
                reg_split = _band_split(reg_flat, sigma=2.0)
                if reg_split is not None:
                    reg_lo, reg_hi = reg_split
                    corrected_reg = (reg_lo + reg_hi * band_gain).reshape(c, region.shape[1], h, w)
            log_.info('H3ClipRefiner: %s corrected to match body (a=%s, b=%s)', region_name, a_reg.tolist(), b_reg.tolist())
            return corrected_reg
        corrected_head = _correct_region(corrected_head, 'head')
        corrected_tail = _correct_region(corrected_tail, 'tail')
    elif has_overlap:
        pass
    if has_overlap:
        corrected = torch.cat([corrected_head, corrected_body, corrected_tail], dim=1)
    else:
        corrected = corrected_body
    report = ', '.join(report_parts)
    tags = []
    if refined_body is not None:
        tags.append('refine+detail')
    if band_gain is not None:
        tags.append('gain=%.4f' % band_gain)
    tags.append('strength=%.2f' % strength)
    tags.append('ctx=%df/%dt' % (int(context_length), overlap))
    report += ' [CORRECTED - ' + ', '.join(tags) + ']'
    if has_overlap:
        report += ' [overlap-corrected]'
    log_.info('H3ClipRefiner: applied correction, strength=%.2f, ctx=%d frames/%d tokens', strength, int(context_length), overlap)
    if had_batch:
        corrected = corrected.unsqueeze(0)
    out = dict(latent)
    out['samples'] = _AVStreamPair(corrected, audio_latent)
    return (out, report)
