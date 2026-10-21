"""Descriptive seam measurements; these are not perceptual acceptance scores."""
import subprocess
import wave


def measure_seam(store, take, pixels, waveform, rate, executable):
    import numpy as np
    source = take.get("snapshot", {}).get("source")
    if not source:
        return {"status": "independent_start"}
    c = take["plan"]["context_frames"]
    d = take["snapshot"].get("decode_edge", {}).get("frames", 0)
    result = {"version": 1, "status": "measured", "units": "RGB normalized to 0..1; audio PCM normalized to -1..1",
        "comparison": "encoded source original versus uncompressed child decode; codec error is included",
        "quality_verdict": "requires_human_review", "decode_edge_frames": d}
    previous = store.asset(f"takes/{source['id']}/original.mp4")
    h, w = pixels.shape[1:3]
    n = source["plan"]["sampled_frames"]
    start = max(0, n - max(d + 1, 2))
    args = [executable, "-v", "error", "-nostdin", "-i", str(previous), "-vf",
            f"trim=start_frame={start}:end_frame={n}", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    decoded = subprocess.run(args, capture_output=True, timeout=120)
    expected_bytes = (n - start) * h * w * 3
    if decoded.returncode or len(decoded.stdout) != expected_bytes:
        raise ValueError("Source decode unavailable or incompatible for seam measurements.")
    parent = np.frombuffer(decoded.stdout, dtype=np.uint8).reshape(n - start, h, w, 3).astype(np.float32) / 255
    child = pixels[max(0, c - max(d, 1)):c + 1].astype(np.float32) / 255
    first = child[-1]; context_end = child[-2] if c else None
    mae = lambda a, b: float(np.abs(a - b).mean())
    result.update(source_context_decode_mae=mae(parent[-1], context_end) if c else None,
        baseline_join_mae=mae(parent[-1], first), child_internal_join_mae=mae(context_end, first) if c else None,
        parent_motion_mae=mae(parent[-2], parent[-1]),
        mean_rgb_change=(first.mean(axis=(0, 1)) - parent[-1].mean(axis=(0, 1))).tolist())
    result["continuation_method"] = take.get("snapshot", {}).get("continuation_method", "latent")
    if d:
        result["corrected_ownership_join_mae"] = mae(parent[-d-1], child[0])
    # Compare delivered source end to delivered child start in decoded PCM.
    with wave.open(str(store.asset(f"takes/{source['id']}/original.wav")), "rb") as audio:
        if audio.getsampwidth() != 2 or audio.getframerate() != rate or audio.getnchannels() != waveform.shape[0]:
            raise ValueError("Source PCM format differs; no audio seam score is inferred.")
        source_end = (n * rate + 12) // 24
        if audio.getnframes() < source_end:
            raise ValueError("Source PCM ends before its delivery boundary; padded audio requires separate review.")
        audio.setpos(source_end - 1)
        last = np.frombuffer(audio.readframes(1), dtype="<i2").astype(np.float32) / 32767
    child_start = (c * rate + 12) // 24
    if not np.isfinite(waveform[:, child_start]).all():
        raise ValueError("Non-finite PCM at the child boundary.")
    result["audio_boundary_sample_jump"] = float(np.abs(last - waveform[:, child_start]).mean())
    result["audio_child_start_sample"] = child_start
    result["audio_sample_rate"] = rate
    return result
