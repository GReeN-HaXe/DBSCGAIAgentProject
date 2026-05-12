from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run(script_name: str) -> None:
    script_path = ROOT / "scripts" / script_name
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=ROOT,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    for script_name in (
        "build_effect_catalog.py",
        "run_effect_support_audit.py",
        "build_effect_family_mapping_report.py",
        "build_effect_family_report.py",
        "build_effect_family_shortlist.py",
    ):
        print(f"running: {script_name}")
        _run(script_name)
    print("effect artifact rebuild complete")


if __name__ == "__main__":
    main()
