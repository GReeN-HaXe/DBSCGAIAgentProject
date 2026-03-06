from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_video_frame_manifest


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract video frames for Phase 9 external-match processing.")
    parser.add_argument("--video", type=Path, required=True, help="Video input path.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase9_video_frames"), help="Output directory.")
    parser.add_argument("--every-n-seconds", type=float, default=1.0, help="Frame interval in seconds.")
    parser.add_argument("--frame-count", type=int, default=10, help="Planned frame count used for manifest scaffolding.")
    parser.add_argument("--plan-only", action="store_true", help="Write extraction manifest without invoking ffmpeg.")
    parser.add_argument("--ffmpeg-path", type=str, default="ffmpeg", help="ffmpeg executable name/path.")
    parser.add_argument("--manifest-output", type=Path, default=None, help="Optional explicit manifest path.")
    args = parser.parse_args()

    frames_dir = args.output_dir / "frames"
    manifest_path = args.manifest_output or (args.output_dir / "phase9_video_frames_manifest.json")
    extracted = False
    if not args.plan_only:
        if not args.video.exists():
            raise ValueError(f"--video not found: {args.video}")
        ffmpeg = shutil.which(str(args.ffmpeg_path))
        if ffmpeg is None:
            raise ValueError(f"ffmpeg not found: {args.ffmpeg_path}")
        frames_dir.mkdir(parents=True, exist_ok=True)
        fps = 1.0 / max(0.001, float(args.every_n_seconds))
        _run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(args.video),
                "-vf",
                f"fps={fps}",
                str(frames_dir / "frame_%05d.jpg"),
            ]
        )
        actual_count = len(list(frames_dir.glob("frame_*.jpg")))
        args.frame_count = actual_count
        extracted = True
    manifest = build_video_frame_manifest(
        video_path=args.video,
        output_dir=args.output_dir,
        every_n_seconds=float(args.every_n_seconds),
        frame_count=int(args.frame_count),
        extracted=bool(extracted),
        ffmpeg_path=str(args.ffmpeg_path),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
