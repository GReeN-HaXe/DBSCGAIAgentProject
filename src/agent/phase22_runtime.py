from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.phase14_torch import _load_state_dict, _select_device
from src.agent.phase22_state_encoder import _prepare_examples, _require_torch


PHASE22_PRODUCTION_QUERY_SCHEMA_VERSION = "phase22.production_query.v1"

DEFAULT_PHASE22_PRODUCTION_DIR = Path("artifacts/phase22_production")
DEFAULT_PHASE22_PRODUCTION_MODEL = DEFAULT_PHASE22_PRODUCTION_DIR / "phase22_state_model.json"
DEFAULT_PHASE22_PRODUCTION_SUMMARY = DEFAULT_PHASE22_PRODUCTION_DIR / "phase22_production_summary.json"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def resolve_phase22_production_paths(
    *,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    dataset_path: Path | None = None,
) -> dict[str, Path]:
    production_root = (production_dir or DEFAULT_PHASE22_PRODUCTION_DIR).resolve()
    resolved_summary = (summary_path or (production_root / DEFAULT_PHASE22_PRODUCTION_SUMMARY.name)).resolve()
    resolved_model = (model_path or (production_root / DEFAULT_PHASE22_PRODUCTION_MODEL.name)).resolve()
    if dataset_path is not None:
        resolved_dataset = dataset_path.resolve()
    else:
        summary = _load_json(resolved_summary)
        manifest_path = Path(str(summary.get("source_manifest_path", ""))).resolve()
        if not manifest_path.exists():
            manifest_path = Path(str(summary.get("production_paths", {}).get("manifest", ""))).resolve()
        manifest = _load_json(manifest_path)
        resolved_dataset = Path(str(manifest.get("dataset_path", ""))).resolve()
    return {
        "production_dir": production_root,
        "summary": resolved_summary,
        "model": resolved_model,
        "dataset": resolved_dataset,
    }


def _build_phase22_model(torch_mods: dict[str, Any], model_payload: dict[str, Any], *, device: str) -> Any:
    torch = torch_mods["torch"]
    nn = torch_mods["nn"]
    categorical_fields = tuple(str(item) for item in model_payload.get("categorical_fields", []))
    category_vocabs = {str(key): [str(v) for v in value] for key, value in dict(model_payload.get("category_vocabs", {})).items()}
    numeric_fields = tuple(str(item) for item in model_payload.get("numeric_fields", []))
    label_vocab = [str(item) for item in model_payload.get("label_vocab", [])]
    hidden_dim = int(model_payload.get("hidden_dim", 128) or 128)
    embedding_dim = int(model_payload.get("embedding_dim", 16) or 16)

    class StateEncoder(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embeddings = nn.ModuleList(
                [
                    nn.Embedding(
                        num_embeddings=max(2, len(category_vocabs[field])),
                        embedding_dim=min(int(embedding_dim), max(4, len(category_vocabs[field]))),
                    )
                    for field in categorical_fields
                ]
            )
            cat_width = sum(int(emb.embedding_dim) for emb in self.embeddings)
            self.net = nn.Sequential(
                nn.Linear(len(numeric_fields) + cat_width, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, len(label_vocab)),
            )

        def forward(self, numeric_x: Any, categorical_x: Any) -> Any:
            embedded = []
            for index, emb in enumerate(self.embeddings):
                embedded.append(emb(categorical_x[:, index]))
            x = torch.cat([numeric_x, *embedded], dim=1) if embedded else numeric_x
            return self.net(x)

    model = StateEncoder().to(device)
    model.load_state_dict(_load_state_dict(torch, dict(model_payload.get("state_dict", {}))))
    model.eval()
    return model


def evaluate_phase22_production(
    *,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    dataset_path: Path | None = None,
    split: str = "validation",
    batch_size: int = 64,
    top_k_values: tuple[int, ...] = (1, 3, 5),
) -> dict[str, Any]:
    from src.agent.phase22_state_encoder import evaluate_phase22_state_encoder

    paths = resolve_phase22_production_paths(
        production_dir=production_dir,
        model_path=model_path,
        summary_path=summary_path,
        dataset_path=dataset_path,
    )
    return evaluate_phase22_state_encoder(
        _load_json(paths["model"]),
        _load_json(paths["dataset"]),
        split=str(split),
        batch_size=int(batch_size),
        top_k_values=tuple(int(value) for value in top_k_values),
    )


def query_phase22_production(
    *,
    query_index: int,
    top_k: int = 5,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    dataset_path: Path | None = None,
    split: str = "validation",
) -> dict[str, Any]:
    paths = resolve_phase22_production_paths(
        production_dir=production_dir,
        model_path=model_path,
        summary_path=summary_path,
        dataset_path=dataset_path,
    )
    model_payload = _load_json(paths["model"])
    dataset = _load_json(paths["dataset"])
    numeric_fields = tuple(str(item) for item in model_payload.get("numeric_fields", []))
    categorical_fields = tuple(str(item) for item in model_payload.get("categorical_fields", []))
    category_vocabs = {str(key): [str(v) for v in value] for key, value in dict(model_payload.get("category_vocabs", {})).items()}
    label_vocab = [str(item) for item in model_payload.get("label_vocab", [])]
    prepared = _prepare_examples(
        dataset,
        split=str(split),
        target_field=str(model_payload.get("target_field", "decision_class")),
        numeric_fields=numeric_fields,
        categorical_fields=categorical_fields,
        category_vocabs=category_vocabs,
        label_vocab=label_vocab,
    )
    index = int(query_index)
    if index < 0 or index >= len(prepared.raw_rows):
        raise IndexError(f"query_index out of range: {index}")

    torch_mods = _require_torch()
    torch = torch_mods["torch"]
    selected_device = _select_device(torch, str(model_payload.get("device", "cpu")))
    model = _build_phase22_model(torch_mods, model_payload, device=selected_device)

    with torch.no_grad():
        numeric_x = torch.tensor([prepared.numeric_rows[index]], dtype=torch.float32).to(selected_device)
        categorical_x = torch.tensor([prepared.categorical_rows[index]], dtype=torch.long).to(selected_device)
        logits = model(numeric_x, categorical_x).cpu()
        top_scores, top_indices = torch.topk(logits, k=min(max(1, int(top_k)), logits.shape[1]), dim=1)

    row = prepared.raw_rows[index]
    predictions = [
        {
            "rank": rank + 1,
            "label": label_vocab[int(label_id)],
            "score": float(top_scores[0][rank].item()),
        }
        for rank, label_id in enumerate([int(value) for value in top_indices[0].tolist()])
    ]
    expected_label = str(row.get(str(model_payload.get("target_field", "decision_class")), "")).strip()
    found_rank = next((item["rank"] for item in predictions if item["label"] == expected_label), None)
    return {
        "schema_version": PHASE22_PRODUCTION_QUERY_SCHEMA_VERSION,
        "query_index": index,
        "split": str(split),
        "expected_label": expected_label,
        "found_rank": found_rank,
        "predictions": predictions,
        "row": {
            "example_index": int(row.get("example_index", index) or index),
            "action_type": str(row.get("action_type", "")),
            "action_signature": str(row.get("action_signature", "")),
            "decision_class": str(row.get("decision_class", "")),
        },
    }
