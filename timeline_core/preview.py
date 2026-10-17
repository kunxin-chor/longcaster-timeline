import shutil
import subprocess
import wave
from .store import atomic_json, digest


def ffmpeg():
    executable = shutil.which("ffmpeg")
    if executable: return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("FFmpeg is required for saved previews. Install FFmpeg or imageio-ffmpeg, then rebuild this preview; no resampling is needed.") from exc


def build_preview(store, take, video_vae, audio_vae, api, on_stage=None):
    if on_stage:on_stage("decoding")
    import numpy as np
    from comfy_extras.nodes_audio import vae_decode_audio
    from .engine import primary
    source = store.asset(take["latent_path"])
    if digest(source) != take["latent_sha256"]: raise ValueError("Saved take changed before preview.")
    latent, _, _ = primary(api, api.load_archive(str(source), verify="full"))
    video, audio = latent["samples"].unbind()
    images = video_vae.decode(video)
    if images.ndim == 5: images = images.reshape(-1, *images.shape[-3:])
    if len(images) != take["plan"]["sampled_frames"]: raise ValueError("Decoded video frame count differs from the frozen plan.")
    sound = vae_decode_audio(audio_vae, {"samples": audio})
    waveform = sound["waveform"].detach().float().cpu().numpy()
    waveform = waveform[0] if waveform.ndim == 3 else waveform
    rate = int(sound["sample_rate"])
    if on_stage:on_stage("saving_media")
    path = store.asset(f"takes/{take['id']}/original.wav")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(waveform.shape[0]); handle.setsampwidth(2); handle.setframerate(rate)
        handle.writeframes((np.clip(waveform.T, -1, 1) * 32767).astype("<i2").tobytes())
    pixels = (images[..., :3].detach().float().cpu().clamp(0, 1).numpy() * 255).round().astype(np.uint8)
    height, width = pixels.shape[1:3]
    executable = ffmpeg()
    for name, start in (("original.mp4", 0), ("preview.mp4", take["plan"]["context_frames"])):
        if on_stage:on_stage("building_preview" if name=="preview.mp4" else "saving_media")
        destination = store.asset(f"takes/{take['id']}/{name}")
        temp = destination.with_name("." + name)
        start_sample = (start * rate + 12) // 24
        frames = len(pixels) - start
        args = [executable, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", "24", "-i", "pipe:0", "-i", str(path),
            "-map", "0:v:0", "-map", "1:a:0", "-af", f"atrim=start_sample={start_sample},asetpts=PTS-STARTPTS,apad",
            "-frames:v", str(frames), "-t", str(frames / 24), "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(temp)]
        try:
            result = subprocess.run(args, input=pixels[start:].tobytes(), capture_output=True, timeout=240)
            if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace")[-3000:])
            import os
            os.replace(temp, destination)
        finally: temp.unlink(missing_ok=True)
    atomic_json(store.asset(f"takes/{take['id']}/preview.json"), {"status": "ready", "source_sha256": take["latent_sha256"],
        "path": f"takes/{take['id']}/preview.mp4", "raw_path": f"takes/{take['id']}/original.mp4", "context_trimmed": True,
        "delivery": take["plan"]["delivery"], "fps": 24, "audio_sample_rate": rate,
        "audio_start_sample": (take["plan"]["context_frames"] * rate + 12) // 24})
