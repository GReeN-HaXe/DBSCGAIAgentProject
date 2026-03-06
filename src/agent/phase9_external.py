from __future__ import annotations

from pathlib import Path
from typing import Any


PHASE9_EXTERNAL_MATCH_SCHEMA_VERSION = "phase9.external_match.v1"
PHASE9_VIDEO_FRAMES_SCHEMA_VERSION = "phase9.video_frames.v1"


def _coerce_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_external_match(
    payload: dict[str, Any],
    *,
    match_id: str,
    source_name: str,
    source_type: str = "manual_annotation",
    video_path: str | None = None,
) -> dict[str, Any]:
    raw_events = payload.get("events", payload.get("annotations", []))
    if not isinstance(raw_events, list):
        raw_events = []
    participants = payload.get("participants", {})
    if not isinstance(participants, dict):
        participants = {}

    annotations: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_events):
        if not isinstance(row, dict):
            continue
        annotations.append(
            {
                "sequence_index": idx + 1,
                "timestamp_seconds": _coerce_float(row.get("timestamp_seconds", row.get("timestamp"))),
                "turn_number": _coerce_int(row.get("turn_number")),
                "phase": str(row.get("phase", "")),
                "actor": {
                    "seat": _coerce_int(row.get("actor_seat")),
                    "name": str(row.get("actor_name", "")),
                },
                "action_type": str(row.get("action_type", "")),
                "action_text": str(row.get("action_text", row.get("action", ""))),
                "confidence": _coerce_float(row.get("confidence")),
                "review_status": str(row.get("review_status", "unreviewed")),
                "zone_snapshot": dict(row.get("zone_snapshot", {})) if isinstance(row.get("zone_snapshot"), dict) else {},
                "notes": str(row.get("notes", "")),
            }
        )

    return {
        "schema_version": PHASE9_EXTERNAL_MATCH_SCHEMA_VERSION,
        "match_id": str(match_id),
        "source_name": str(source_name),
        "source_type": str(source_type),
        "media": {
            "video_path": str(video_path) if video_path else str(payload.get("video_path", "")),
        },
        "participants": {
            "player_1": dict(participants.get("player_1", {})) if isinstance(participants.get("player_1"), dict) else {},
            "player_2": dict(participants.get("player_2", {})) if isinstance(participants.get("player_2"), dict) else {},
        },
        "result": {
            "winner_seat": _coerce_int(payload.get("winner_seat")),
            "winner_name": str(payload.get("winner_name", "")),
        },
        "annotations": annotations,
        "review": {
            "review_status": str(payload.get("review_status", "unreviewed")),
            "reviewer": str(payload.get("reviewer", "")),
            "notes": str(payload.get("notes", "")),
        },
    }


def build_video_frame_manifest(
    *,
    video_path: Path,
    output_dir: Path,
    every_n_seconds: float,
    frame_count: int,
    extracted: bool,
    ffmpeg_path: str,
) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []
    for idx in range(max(0, int(frame_count))):
        timestamp = float(idx) * float(every_n_seconds)
        frames.append(
            {
                "frame_index": idx,
                "timestamp_seconds": timestamp,
                "relative_path": str(Path("frames") / f"frame_{idx:05d}.jpg"),
            }
        )
    return {
        "schema_version": PHASE9_VIDEO_FRAMES_SCHEMA_VERSION,
        "video_path": str(video_path),
        "output_dir": str(output_dir),
        "every_n_seconds": float(every_n_seconds),
        "frame_count": int(frame_count),
        "extracted": bool(extracted),
        "ffmpeg_path": str(ffmpeg_path),
        "frames": frames,
    }


def reconstruct_external_match(match_payload: dict[str, Any]) -> dict[str, Any]:
    annotations = match_payload.get("annotations", [])
    if not isinstance(annotations, list):
        annotations = []
    reconstructed: list[dict[str, Any]] = []
    inferred_turn = 1
    last_phase = ""
    phase_transitions: list[dict[str, Any]] = []
    for idx, row in enumerate(annotations):
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase", "") or "")
        turn_number = _coerce_int(row.get("turn_number"))
        if turn_number is None:
            if idx > 0 and phase == "charge" and last_phase not in {"", "charge"}:
                inferred_turn += 1
            turn_number = inferred_turn
        else:
            inferred_turn = turn_number
        if phase and phase != last_phase:
            phase_transitions.append(
                {
                    "sequence_index": int(row.get("sequence_index", idx + 1) or (idx + 1)),
                    "turn_number": turn_number,
                    "phase": phase,
                }
            )
            last_phase = phase
        reconstructed.append({**row, "turn_number": turn_number, "phase": phase})
    return {
        **match_payload,
        "annotations": reconstructed,
        "reconstruction": {
            "phase_transitions": phase_transitions,
            "annotation_count": len(reconstructed),
            "inferred_turns": max((int(row.get("turn_number", 0) or 0) for row in reconstructed), default=0),
        },
    }


def score_external_match_confidence(match_payload: dict[str, Any]) -> dict[str, Any]:
    annotations = match_payload.get("annotations", [])
    if not isinstance(annotations, list):
        annotations = []
    confidences = []
    reviewed = 0
    for row in annotations:
        if not isinstance(row, dict):
            continue
        confidence = _coerce_float(row.get("confidence"))
        if confidence is not None:
            confidences.append(confidence)
        if str(row.get("review_status", "")).strip().lower() == "reviewed":
            reviewed += 1
    avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
    review_coverage = (reviewed / len(annotations)) if annotations else 0.0
    overall = (avg_conf * 0.7) + (review_coverage * 0.3)
    status = "high" if overall >= 0.85 else ("medium" if overall >= 0.60 else "low")
    return {
        "avg_annotation_confidence": avg_conf,
        "review_coverage": review_coverage,
        "overall_confidence": overall,
        "status": status,
        "annotation_count": len(annotations),
    }


def apply_external_review(
    match_payload: dict[str, Any],
    *,
    reviewer: str,
    review_status: str,
    notes: str = "",
) -> dict[str, Any]:
    confidence = score_external_match_confidence(match_payload)
    review = dict(match_payload.get("review", {})) if isinstance(match_payload.get("review"), dict) else {}
    review.update(
        {
            "review_status": str(review_status),
            "reviewer": str(reviewer),
            "notes": str(notes),
            "confidence_summary": confidence,
        }
    )
    return {**match_payload, "review": review}


def external_match_to_phase7_trace_artifact(match_payload: dict[str, Any]) -> dict[str, Any]:
    annotations = match_payload.get("annotations", [])
    if not isinstance(annotations, list):
        annotations = []
    winner_seat = _coerce_int(match_payload.get("result", {}).get("winner_seat")) if isinstance(match_payload.get("result"), dict) else None
    setup = {
        "mode": "external_import",
        "source_name": str(match_payload.get("source_name", "")),
        "source_type": str(match_payload.get("source_type", "")),
        "match_id": str(match_payload.get("match_id", "")),
        "review_status": str(match_payload.get("review", {}).get("review_status", "")) if isinstance(match_payload.get("review"), dict) else "",
        "external_confidence_status": str(match_payload.get("review", {}).get("confidence_summary", {}).get("status", "")) if isinstance(match_payload.get("review"), dict) else "",
    }
    actions: list[dict[str, Any]] = []
    for row in annotations:
        if not isinstance(row, dict):
            continue
        actor = row.get("actor", {})
        actor_seat = _coerce_int(actor.get("seat")) if isinstance(actor, dict) else None
        zone_snapshot = row.get("zone_snapshot", {})
        actions.append(
            {
                "actor_kind": "external",
                "player_id": actor_seat,
                "turn_number": _coerce_int(row.get("turn_number")),
                "phase": str(row.get("phase", "")),
                "action": str(row.get("action_text", "")),
                "action_type": str(row.get("action_type", "")),
                "state_snapshot": {
                    "active_player": actor_seat,
                    "turn_number": _coerce_int(row.get("turn_number")),
                    "phase": str(row.get("phase", "")),
                    "battle_step": None,
                    "counter_window_kind": None,
                    "players": dict(zone_snapshot) if isinstance(zone_snapshot, dict) else {},
                },
            }
        )
    final_turn = max((_coerce_int(item.get("turn_number")) or 0 for item in annotations if isinstance(item, dict)), default=0)
    final_phase = ""
    if annotations:
        last = annotations[-1]
        if isinstance(last, dict):
            final_phase = str(last.get("phase", ""))
    return {
        "trace": {
            "total_actions": len(actions),
            "winner_id": winner_seat,
            "final_turn_number": final_turn,
            "final_phase": final_phase,
            "human_player_id": None,
            "setup": setup,
            "actions": actions,
        }
    }


def merge_frame_events_into_external_match(
    match_payload: dict[str, Any],
    frame_payload: dict[str, Any],
) -> dict[str, Any]:
    annotations = list(match_payload.get("annotations", [])) if isinstance(match_payload.get("annotations"), list) else []
    frame_events = frame_payload.get("events", [])
    if not isinstance(frame_events, list):
        frame_events = []
    next_index = max((int(item.get("sequence_index", 0) or 0) for item in annotations if isinstance(item, dict)), default=0)
    merged_events = list(annotations)
    for raw in frame_events:
        if not isinstance(raw, dict):
            continue
        next_index += 1
        merged_events.append(
            {
                "sequence_index": next_index,
                "timestamp_seconds": _coerce_float(raw.get("timestamp_seconds")),
                "turn_number": _coerce_int(raw.get("turn_number")),
                "phase": str(raw.get("phase", "")),
                "actor": {
                    "seat": _coerce_int(raw.get("actor_seat")),
                    "name": str(raw.get("actor_name", "")),
                },
                "action_type": str(raw.get("action_type", "")),
                "action_text": str(raw.get("action_text", "")),
                "confidence": _coerce_float(raw.get("confidence")),
                "review_status": str(raw.get("review_status", "unreviewed")),
                "zone_snapshot": dict(raw.get("zone_snapshot", {})) if isinstance(raw.get("zone_snapshot"), dict) else {},
                "notes": str(raw.get("notes", "")),
                "source": "frame_event",
            }
        )
    merged_events.sort(key=lambda item: ((item.get("timestamp_seconds") is None), item.get("timestamp_seconds"), item.get("sequence_index", 0)))
    return {
        **match_payload,
        "annotations": merged_events,
        "frame_merge": {
            "merged_event_count": len(frame_events),
            "frame_manifest_path": str(frame_payload.get("manifest_path", "")),
        },
    }


def summarize_phase7_dataset_by_mode(dataset: dict[str, Any]) -> dict[str, Any]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    grouped: dict[str, dict[str, Any]] = {}
    for row in examples:
        if not isinstance(row, dict):
            continue
        setup = row.get("setup", {})
        mode = str(setup.get("mode", "unknown")) if isinstance(setup, dict) else "unknown"
        bucket = grouped.setdefault(mode, {"example_count": 0, "wins": 0, "known_outcomes": 0})
        bucket["example_count"] = int(bucket["example_count"]) + 1
        if row.get("did_player_win") is True:
            bucket["wins"] = int(bucket["wins"]) + 1
        if row.get("did_player_win") is not None:
            bucket["known_outcomes"] = int(bucket["known_outcomes"]) + 1
    for mode, bucket in grouped.items():
        known = int(bucket["known_outcomes"])
        bucket["win_rate"] = 0.0 if known == 0 else float(bucket["wins"]) / float(known)
        bucket["mode"] = mode
    return {
        "mode_count": len(grouped),
        "by_mode": [grouped[key] for key in sorted(grouped.keys())],
    }


def build_phase9_review_queue(matches: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for payload in matches:
        if not isinstance(payload, dict):
            continue
        review = payload.get("review", {})
        confidence = review.get("confidence_summary", {}) if isinstance(review, dict) else {}
        annotations = payload.get("annotations", [])
        items.append(
            {
                "match_id": str(payload.get("match_id", "")),
                "source_name": str(payload.get("source_name", "")),
                "review_status": str(review.get("review_status", "")) if isinstance(review, dict) else "",
                "confidence_status": str(confidence.get("status", "")) if isinstance(confidence, dict) else "",
                "annotation_count": len(annotations) if isinstance(annotations, list) else 0,
            }
        )
    return {
        "match_count": len(items),
        "needs_review_count": sum(1 for item in items if item.get("review_status") != "reviewed"),
        "low_confidence_count": sum(1 for item in items if item.get("confidence_status") == "low"),
        "matches": items,
    }
