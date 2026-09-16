from __future__ import annotations
import shutil, subprocess
from pathlib import Path

def generate_replay_video(artifact_dir: Path, output: Path, fps: int = 2) -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    images = sorted(artifact_dir.glob("step-*.png"))
    if not ffmpeg or not images:
        return None
    concat = artifact_dir / "frames.txt"
    concat.write_text("".join(f"file '{p.name}'\nduration {1/max(fps,1):.3f}\n" for p in images) + f"file '{images[-1].name}'\n", encoding="utf-8")
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat.name, "-vf", "scale=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", str(output)]
    p = subprocess.run(cmd, cwd=artifact_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=60)
    return str(output) if p.returncode == 0 and output.exists() else None
