from __future__ import annotations

from scripts.run_profile_matchups import (
    _compute_history_ci_out,
    _compute_pipeline_ci_failed,
    _resolve_failure_exit_code,
)


def test_history_ci_compute_returns_unknown_when_summary_missing_and_unknown_mode_fail() -> None:
    out = _compute_history_ci_out(
        history_summary_payload=None,
        history_ci_status_threshold="warning",
        history_ci_readiness_mode="required",
        history_ci_blockers_mode="required",
        history_ci_unknown_mode="fail",
        history_ci_readiness_score_threshold=None,
    )
    assert out["status"] == "unknown"
    assert out["source"] == "unavailable"
    assert "history_summary_unavailable" in out["reasons"]


def test_history_ci_compute_returns_pass_when_summary_missing_and_unknown_mode_pass() -> None:
    out = _compute_history_ci_out(
        history_summary_payload=None,
        history_ci_status_threshold="warning",
        history_ci_readiness_mode="required",
        history_ci_blockers_mode="required",
        history_ci_unknown_mode="pass",
        history_ci_readiness_score_threshold=None,
    )
    assert out["status"] == "pass"
    assert out["source"] == "unavailable"
    assert out["reasons"] == []


def test_history_ci_compute_fails_when_summary_breaks_policy() -> None:
    out = _compute_history_ci_out(
        history_summary_payload={
            "overall_status": "warning",
            "is_ready_for_next_phase": False,
            "readiness_score": 0.6,
            "readiness_blocker_count": 1,
        },
        history_ci_status_threshold="warning",
        history_ci_readiness_mode="required",
        history_ci_blockers_mode="required",
        history_ci_unknown_mode="fail",
        history_ci_readiness_score_threshold=0.8,
    )
    assert out["status"] == "fail"
    assert out["source"] == "history_summary"
    reasons = set(out["reasons"])
    assert "status_threshold_failed" in reasons
    assert "not_ready_failed" in reasons
    assert "blockers_failed" in reasons
    assert "readiness_score_failed" in reasons


def test_pipeline_ci_failed_uses_core_only_when_history_not_included() -> None:
    assert _compute_pipeline_ci_failed(core_ci_failed=False, include_history_ci=False, history_ci_status="fail") is False
    assert _compute_pipeline_ci_failed(core_ci_failed=True, include_history_ci=False, history_ci_status="pass") is True


def test_pipeline_ci_failed_includes_history_when_enabled() -> None:
    assert _compute_pipeline_ci_failed(core_ci_failed=False, include_history_ci=True, history_ci_status="fail") is True
    assert _compute_pipeline_ci_failed(core_ci_failed=False, include_history_ci=True, history_ci_status="unknown") is True
    assert _compute_pipeline_ci_failed(core_ci_failed=False, include_history_ci=True, history_ci_status="pass") is False


def test_resolve_failure_exit_code_prefers_ci_status_only_mode() -> None:
    code, msg = _resolve_failure_exit_code(
        fail_on_ci_status_only=True,
        fail_on_ci_status=False,
        ci_status="fail",
        fail_on_alerts=True,
        low_decisive_rate_alert=True,
        seat_bias_alert=False,
        fail_on_unreliable_recommendation=True,
        recommendation_reliable=False,
        fail_on_history_ci=True,
        history_ci_status="fail",
    )
    assert code == 5
    assert msg == "run_failed_on_ci_status: fail"


def test_resolve_failure_exit_code_uses_legacy_order_when_not_ci_only() -> None:
    code, msg = _resolve_failure_exit_code(
        fail_on_ci_status_only=False,
        fail_on_ci_status=False,
        ci_status="pass",
        fail_on_alerts=True,
        low_decisive_rate_alert=True,
        seat_bias_alert=False,
        fail_on_unreliable_recommendation=True,
        recommendation_reliable=False,
        fail_on_history_ci=True,
        history_ci_status="fail",
    )
    assert code == 2
    assert msg == "run_failed_on_alerts: True"


def test_resolve_failure_exit_code_allows_success() -> None:
    code, msg = _resolve_failure_exit_code(
        fail_on_ci_status_only=False,
        fail_on_ci_status=True,
        ci_status="pass",
        fail_on_alerts=True,
        low_decisive_rate_alert=False,
        seat_bias_alert=False,
        fail_on_unreliable_recommendation=True,
        recommendation_reliable=True,
        fail_on_history_ci=True,
        history_ci_status="pass",
    )
    assert code is None
    assert msg is None
