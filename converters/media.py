"""Audio and video with FFmpeg."""
from pathlib import Path

from .tools import ConversionError, require, run

AUDIO_CODEC = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-c:a", "pcm_s16le"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "flac": ["-c:a", "flac"],
    "aac": ["-c:a", "aac", "-b:a", "192k"],
    "opus": ["-c:a", "libopus", "-b:a", "128k"],
    "wma": ["-c:a", "wmav2", "-b:a", "192k"],
}
H264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k"]


def _start(src, opts):
    """ffmpeg + input, cut to the optional start/end times (seconds or mm:ss)."""
    # local files only: a playlist disguised as a video can't make FFmpeg fetch URLs
    args = [require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-protocol_whitelist", "file"]
    for key, flag in (("start", "-ss"), ("end", "-to")):
        if opts.get(key):
            args += [flag, _time(opts[key])]
    return args + ["-i", src]


def _time(value):
    """'90', '1:30' or '0:01:30' -> seconds, so a typo fails here with a clear message."""
    try:
        seconds = 0.0
        for part in str(value).strip().split(":"):
            seconds = seconds * 60 + float(part)
    except ValueError:
        raise ConversionError(f"'{value}' isn't a time. Use seconds (90) or minutes:seconds (1:30).")
    return f"{seconds:g}"


def convert(src, out_dir, fmt, opts):
    out = Path(out_dir) / f"{Path(src).stem}.{fmt}"
    height = int(opts.get("resolution") or 0)
    scale = [f"scale=-2:{height}"] if height else []
    args = _start(src, opts)
    if fmt in ("mp4", "mov"):
        args += [*H264, "-movflags", "+faststart"]
    elif fmt == "mkv":
        args += H264
    elif fmt == "webm":
        args += ["-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0", "-deadline", "realtime", "-cpu-used", "8",
                 "-c:a", "libopus"]
    elif fmt == "gif":
        size = f"scale=-2:{height or 360}:flags=lanczos"
        args += ["-an", "-vf", f"fps=12,{size},split[a][b];[a]palettegen[p];[b][p]paletteuse"]
        scale = []
    else:  # audio output, also "extract audio" from a video
        args += ["-vn", *AUDIO_CODEC[fmt]]
    if scale:
        args += ["-vf", ",".join(scale)]
    run(args + [out], opts["_timeout"])
    return [out]


def compress(src, out_dir, fmt, opts):
    """Smaller MP4: stronger compression, and at most 720p tall."""
    out = Path(out_dir) / f"{Path(src).stem}_small.mp4"
    height = int(opts.get("resolution") or 720)
    args = _start(src, opts) + ["-c:v", "libx264", "-preset", "medium", "-crf", "28", "-pix_fmt", "yuv420p",
                                "-vf", f"scale=-2:'min({height},ih)'", "-c:a", "aac", "-b:a", "96k",
                                "-movflags", "+faststart"]
    run(args + [out], opts["_timeout"])
    return [out]


def thumbnail(src, out_dir, fmt, opts):
    out = Path(out_dir) / f"{Path(src).stem}_thumbnail.jpg"
    run(_start(src, opts) + ["-vf", "thumbnail", "-frames:v", "1", "-q:v", "2", out], opts["_timeout"])
    return [out]


def mute(src, out_dir, fmt, opts):
    out = Path(out_dir) / f"{Path(src).stem}_muted.{fmt}"
    copy = [] if opts.get("start") or opts.get("end") else ["-c:v", "copy"]  # copying can't cut precisely
    run(_start(src, opts) + [*copy, "-an", out], opts["_timeout"])
    return [out]


def normalize(src, out_dir, fmt, opts):
    out = Path(out_dir) / f"{Path(src).stem}_normalized.{fmt}"
    # loudnorm outputs 192 kHz, which FLAC and WMA refuse
    run(_start(src, opts) + ["-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", *AUDIO_CODEC[fmt], out],
        opts["_timeout"])
    return [out]
