"""Assemble the demo video: a screen recording (MP4/GIF from the Chrome extension) or a set of screenshots,
plus per-segment narration (macOS TTS or Carson's audio). Output docs/scripty-demo.mp4 at 1280x720.
Usage: python scripts/make_video.py <screenshots_dir_or_recording> [voice]"""
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "video"; OUT.mkdir(parents=True, exist_ok=True)
src = Path(sys.argv[1]); voice = sys.argv[2] if len(sys.argv) > 2 else "Daniel"
paras = [re.sub(r"^\d+\.\s*", "", p.strip()) for p in re.split(r"\n(?=\d+\.\s)", (ROOT / "docs" / "NARRATION.md").read_text().split("\n", 2)[2]) if p.strip()]
frames = sorted(src.glob("*.jpg")) + sorted(src.glob("*.png")) if src.is_dir() else [src]
assert frames, "no frames"
if src.is_dir():
    assert len(frames) >= len(paras), f"need {len(paras)} images, have {len(frames)}"
concat = []
for i, text in enumerate(paras):
    aiff, wav = OUT / f"n{i+1}.aiff", OUT / f"n{i+1}.wav"
    subprocess.run(["say", "-v", voice, "-r", "178", "-o", str(aiff), text], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "48000", "-ac", "2", str(wav)], check=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)], capture_output=True, text=True).stdout.strip()) + 0.5
    seg = OUT / f"seg{i+1}.mp4"
    img = frames[i] if src.is_dir() else frames[0]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", str(img), "-i", str(wav), "-t", f"{dur:.2f}", "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-shortest", str(seg)], check=True)
    concat.append(f"file '{seg}'")
(OUT / "concat.txt").write_text("\n".join(concat) + "\n")
final = ROOT / "docs" / "scripty-demo.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(OUT / "concat.txt"), "-c", "copy", str(final)], check=True)
d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(final)], capture_output=True, text=True).stdout.strip()
print(f"wrote {final} ({final.stat().st_size//1024} KB), {float(d):.0f}s, {len(paras)} segments")
