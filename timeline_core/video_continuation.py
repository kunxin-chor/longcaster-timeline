"""VPipe-style learned REF2VA continuation from a decoded AV reference tail."""
import re
from .store import FIELDS, atomic_json, digest, fingerprint

FRAMES = 90


def validate(profile, source, settings, plan=None):
    if profile != 'ref2va':
        raise ValueError('Video-reference continuation requires REF2VA.')
    if not source:
        raise ValueError('Video-reference continuation requires a finalized source take.')
    bounds = source['plan']['delivery']
    if bounds['end'] - bounds['start'] < FRAMES:
        raise ValueError('Video-reference continuation needs at least 90 delivered source frames (3.75s).')
    if settings.get('image_motion_frames', 0):
        raise ValueError('Disable image motion context for video-reference continuation.')
    protection = settings.get('continuation_protection', 'off')
    if isinstance(protection, dict): protection = protection.get('mode', 'off')
    edge = settings.get('decode_edge_frames', (settings.get('decode_edge') or {}).get('frames', 0))
    if edge or (settings.get('refine') or {}).get('enabled') or protection not in (None, 'off'):
        raise ValueError('Disable seam correction, refinement and continuation protection for video-reference continuation.')
    if plan is not None and (plan['context_frames'] != 0 or plan['sampled_frames'] < FRAMES):
        raise ValueError('Video-reference continuation needs at least 90 target frames (3.75s) and no latent overlap.')


def compile_with_video(fields, references, source):
    from .compiler import compile_prompt, qualified_name
    if not source: raise ValueError('Select a finalized source take for video-reference continuation.')
    bounds = source['plan']['delivery']
    if bounds['end'] - bounds['start'] < FRAMES:
        raise ValueError('Video-reference continuation needs at least 90 delivered source frames (3.75s).')
    if any(r.get('enabled', True) and r['kind'] != 'image' for r in references):
        raise ValueError('Only the generated continuation video/audio is supported; disable other video/audio assets.')
    names = {qualified_name(r).casefold() for r in references}
    virtual = []
    for kind, role in (('video', 'continuation_video'), ('audio', 'continuation_audio')):
        name = '_continuation_tail'
        while kind + '.' + name in names: name = '_' + name
        virtual.append(dict(id=role+'-'+source['id'], kind=kind, token_name=name,
            display_name='Previous segment AV tail', scope='segment', owner_id=None,
            enabled=True, asset_path=None, asset_sha256=None, generated_role=role,
            source_take_id=source['id'], source_archive_sha256=source['latent_sha256'],
            source_frame_start=bounds['end']-FRAMES, source_frame_end=bounds['end']))
    compiled = compile_prompt(fields, [*references, *virtual], allow_generated_video=True)
    additions = {
        'subject_definitions': '<Video 1> is the final 3.75 seconds of the preceding segment and provides the continuation starting point, ongoing motion, camera and environment.\n<Audio 1> is the synchronized soundtrack of <Video 1>, used as an audio reference.',
        'retention_analysis': '<Video 1> (continuation starting point): fully_preserved - Continue from its final frame, retaining the ongoing action, subject appearance, camera framing, environment and lighting.\n<Audio 1>: reference - Follow the preceding ambience and sound character; generate new sound without copying the reference signal.',
        'detailed_description': 'Continue immediately from the end of <Video 1>, carrying the ongoing action and camera motion forward without replaying the reference or introducing an opening hold. Use <Audio 1> as a reference for continuing sound texture and ambience, without copying the signal.'}
    resolved = compiled['resolved_fields']
    summary = resolved['summary'].strip()
    prefix = re.match(r'^\[([^\]]+)\]\s*', summary)
    tasks = [s.strip().lower() for s in prefix.group(1).split('+')] if prefix else (['reference generation'] if compiled['images'] else [])
    tasks = list(dict.fromkeys(['video continuation', 'audio reference', *tasks]))
    additions['summary'] = '['+' + '.join(tasks)+'] The target video continues from the end of <Video 1>, with <Audio 1> as its soundtrack reference.'
    resolved['summary'] = (additions['summary']+' '+(summary[prefix.end():] if prefix else summary)).strip()
    for field in ('subject_definitions', 'retention_analysis'):
        resolved[field] = (resolved[field].rstrip()+'\n'+additions[field]).strip()
    text = resolved['detailed_description']
    shot = re.compile(r'\[Shot\s+1\]', re.I)
    if len(shot.findall(text)) > 1: raise ValueError('Video continuation requires a single [Shot 1] opening.')
    if shot.search(text): text = shot.sub(lambda m: m.group(0)+' '+additions['detailed_description'], text, count=1)
    elif re.search(r'\[Shot\s+\d+\]', text, re.I): raise ValueError('Start the continuation prompt with [Shot 1].')
    else: text = '[Shot 1] '+additions['detailed_description']+' '+text
    resolved['detailed_description'] = text.strip()
    compiled['automatic_additions'] = additions
    compiled['continuation_video'] = {**virtual[0], 'native_label':'<Video 1>', 'audio_label':'<Audio 1>', 'frames':FRAMES}
    compiled['prompt'] = '\n\n'.join(f'{f}:\n{resolved[f]}' for f in FIELDS)
    compiled['sha256'] = fingerprint({'prompt':compiled['prompt'], 'assets':compiled['assets']})
    return compiled


def slice_tail(frames, sound, source, width, height):
    """Keep exact decoded values and sample-aligned source bounds; no preview I/O."""
    import torch
    end = source['plan']['delivery']['end']; start = end-FRAMES
    if frames.ndim == 5: frames = frames.reshape(-1, *frames.shape[-3:])
    if frames.ndim != 4 or len(frames) != source['plan']['sampled_frames']:
        raise ValueError('Decoded reference video frame count differs from frozen source.')
    if not source['plan']['delivery']['start'] <= start < end <= len(frames):
        raise ValueError('Video reference tail exceeds source delivered bounds.')
    video = frames[start:end, ..., :3].detach().float().cpu().contiguous()
    if tuple(video.shape) != (FRAMES,height,width,3) or not torch.isfinite(video).all() or video.min()<0 or video.max()>1:
        raise ValueError('Decoded reference video has invalid geometry or pixel values.')
    rate = sound['sample_rate']
    if isinstance(rate,bool) or not isinstance(rate,int) or rate <= 0: raise ValueError('Invalid reference audio sample rate.')
    first,last = (start*rate+12)//24, (end*rate+12)//24
    wave = sound['waveform']
    if wave.ndim!=3 or wave.shape[0]!=1 or wave.shape[1] not in (1,2) or wave.shape[-1]<last:
        raise ValueError('Decoded reference audio does not cover the frozen video tail.')
    wave = wave[...,first:last].detach().float().cpu().contiguous()
    if not torch.isfinite(wave).all(): raise ValueError('Decoded reference audio is not finite.')
    return video, {'waveform':wave,'sample_rate':rate}, {'start':start,'end':end,'audio_start_sample':first,'audio_end_sample':last}


def load_reference(api, store, snapshot, video_vae, audio_vae, job_id, cancelled=lambda:False):
    import hashlib
    from comfy_extras.nodes_audio import vae_decode_audio
    from .engine import primary
    validate(snapshot['profile'],snapshot['source'],snapshot,snapshot['plan'])
    source=snapshot['source']; path=store.asset(source['latent_path'])
    if not path.is_file() or digest(path)!=source['latent_sha256']: raise ValueError('Video reference source archive is missing or changed.')
    if cancelled(): raise RuntimeError('Generation cancelled before video-reference decoding.')
    latent, descriptor, contract=primary(api,api.load_archive(str(path),verify='full'))
    if descriptor['id']!=source['latent_resource_id']: raise ValueError('Video reference source resource changed.')
    video,audio=latent['samples'].unbind()
    frames=video_vae.decode(video.detach().to('cpu',copy=True).contiguous())
    if cancelled(): raise RuntimeError('Generation cancelled during video-reference decoding.')
    sound=vae_decode_audio(audio_vae,{'samples':audio})
    frames,sound,bounds=slice_tail(frames,sound,source,snapshot['width'],snapshot['height'])
    binding=snapshot['compiled'].get('continuation_video') or {}
    if (binding.get('source_take_id'),binding.get('source_archive_sha256'),binding.get('source_frame_start'),binding.get('source_frame_end')) != (source['id'],source['latent_sha256'],bounds['start'],bounds['end']):
        raise ValueError('Video reference differs from frozen prompt binding.')
    if cancelled(): raise RuntimeError('Generation cancelled after video-reference decoding.')
    if digest(path)!=source['latent_sha256']: raise ValueError('Video reference archive changed during decoding.')
    receipt=dict(version=1,method='video_reference',conditioning_strategy='ref2va_video_audio_reference',
        source_take_id=source['id'],source_sha256=source['latent_sha256'],source_resource_id=descriptor['id'],source_contract=contract,
        native_label='<Video 1>',audio_label='<Audio 1>',video_frames=FRAMES,fps=24,**bounds,
        video_float32_sha256=hashlib.sha256(frames.numpy().tobytes()).hexdigest(),
        audio_float32_sha256=hashlib.sha256(sound['waveform'].numpy().tobytes()).hexdigest(),audio_sample_rate=sound['sample_rate'],
        conditioning_input='decoded_archive_float32_not_preview',hard_latent_pin=False,latent_overlap_frames=0,
        motion_reference=True,audio_reference=True,audio_history=False,quality_validation='requires_native_test',
        automatic_additions=snapshot['compiled']['automatic_additions'])
    atomic_json(store.asset(f'diagnostics/{job_id}/video-continuation.json'),receipt)
    return frames,sound,receipt


def condition(native, args, images, audio_vae, frames, sound, image_size):
    """Preflight the native API, then preserve the paired video/audio index."""
    from .engine import compatible_signature
    kwargs=dict(**args,audio_vae=audio_vae,ref_image_size=image_size,ref_images=images,
                ref_videos={'ref_video_1':frames},ref_video_audios={'ref_video_audio_1':sound})
    compatible_signature('MiniMaxH3ReferenceToVideo.execute video/audio references',native,(),kwargs)
    return native(**kwargs)
