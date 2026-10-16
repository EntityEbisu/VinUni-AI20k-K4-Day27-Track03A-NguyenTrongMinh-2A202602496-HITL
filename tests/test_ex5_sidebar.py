import app_helpers
from common.schemas import AuditEntry


async def test_recent_threads_and_events(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "ui.db"))
    for i, risk in enumerate(("med", "high")):
        await mod.audit(
            {"thread_id": f"t-{i}", "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/1"},
            AuditEntry(agent_id="pr-review-agent@v0.1", action="route", confidence=0.5,
                       risk_level=risk, decision="escalate", reason="r",
                       reviewer_id=None, execution_time_ms=5),
        )

    threads = await app_helpers.fetch_recent_threads()
    assert {t["thread_id"] for t in threads} == {"t-0", "t-1"}
    assert {t["worst_risk"] for t in threads} == {"med", "high"}

    events = await app_helpers.fetch_thread_events("t-1")
    assert len(events) == 1 and events[0]["risk_level"] == "high"


async def test_worst_risk_is_not_lexicographic(monkeypatch, tmp_path):
    """HIGH phải thắng MED — MAX(risk_level) kiểu chuỗi sẽ trả sai 'med'."""
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "ui2.db"))
    for risk in ("med", "high", "low"):
        await mod.audit(
            {"thread_id": "t-x", "pr_url": "u"},
            AuditEntry(agent_id="a", action="route", confidence=0.5, risk_level=risk,
                       decision="escalate", reason="r", reviewer_id=None, execution_time_ms=1),
        )
    threads = await app_helpers.fetch_recent_threads()
    assert threads[0]["worst_risk"] == "high"
