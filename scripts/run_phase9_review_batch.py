from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch reconstruct/review Phase 9 external matches and build a queue manifest.")
    parser.add_argument("--input", type=Path, nargs="+", required=True, help="Imported Phase 9 external match JSON files.")
    parser.add_argument("--reviewer", type=str, default="batch_reviewer", help="Reviewer label.")
    parser.add_argument("--review-status", type=str, default="reviewed", help="Review status to stamp.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase9_review_batch"), help="Output directory.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    reviewed_paths: list[Path] = []
    for idx, path in enumerate(args.input):
        out = args.artifacts_dir / f"reviewed_{idx + 1}.json"
        _run(
            [
                sys.executable,
                "scripts/reconstruct_phase9_external_match.py",
                "--input",
                str(path),
                "--reviewer",
                str(args.reviewer),
                "--review-status",
                str(args.review_status),
                "--output",
                str(out),
            ]
        )
        reviewed_paths.append(out)
    queue_path = args.artifacts_dir / "phase9_review_queue.json"
    _run(
        [
            sys.executable,
            "scripts/build_phase9_review_queue.py",
            "--input",
            *[str(path) for path in reviewed_paths],
            "--output",
            str(queue_path),
        ]
    )
    summary = {
        "reviewed_count": len(reviewed_paths),
        "reviewed_paths": [str(path) for path in reviewed_paths],
        "queue_path": str(queue_path),
        "queue_summary": _load_json(queue_path),
    }
    out = args.artifacts_dir / "phase9_review_batch_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
