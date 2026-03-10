from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


PHASE22_PRODUCTION_SUMMARY_SCHEMA_VERSION = "phase22.production_summary.v1"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def build_phase22_production_summary(
    *,
    best_config_path: Path,
    production_dir: Path,
) -> dict[str, Any]:
    best_config = _load_json(best_config_path)
    best = best_config.get("best", {})
    if not isinstance(best, dict) or not best:
        raise ValueError("phase22 best config is missing the best run payload")
    manifest_path = Path(str(best.get("manifest_path", ""))).resolve()
    manifest = _load_json(manifest_path)
    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise ValueError("phase22 manifest is missing artifact paths")

    production_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for key, filename in {
        "manifest": "phase22_manifest.json",
        "model": "phase22_state_model.json",
        "evaluation": "phase22_state_eval.json",
        "baseline_model": "phase22_baseline_model.json",
        "baseline_eval": "phase22_baseline_eval.json",
        "compare": "phase22_compare.json",
    }.items():
        source_key = {
            "manifest": None,
            "model": "phase22_model",
            "evaluation": "phase22_eval",
            "baseline_model": "baseline_model",
            "baseline_eval": "baseline_eval",
            "compare": "compare",
        }[key]
        source = manifest_path if source_key is None else Path(str(artifacts.get(source_key, ""))).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        destination = (production_dir / filename).resolve()
        if source != destination:
            shutil.copy2(source, destination)
        copied[key] = str(destination)

    summary = {
        "schema_version": PHASE22_PRODUCTION_SUMMARY_SCHEMA_VERSION,
        "best_config_path": str(best_config_path.resolve()),
        "source_manifest_path": str(manifest_path),
        "target_field": str(best_config.get("target_field", manifest.get("target_field", ""))),
        "metrics": manifest.get("metrics", {}),
        "production_paths": copied,
    }
    return summary
