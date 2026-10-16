import types

from common.db import replay_events
from common.schemas import AuditEntry, risk_level_for
from tests.fakes import FakeLLM, make_analysis


async def test_audit_writes_one_row(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "audit_test.db"))
    state = {"thread_id": "t-1", "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/1"}
    await mod.audit(state, AuditEntry(
        agent_id=mod.AGENT_ID, action="analyze", confidence=0.65,
        risk_level=risk_level_for(0.65), decision="pending",
        reason="vì diff nhỏ nhưng đổi schema", reviewer_id=None, execution_time_ms=12,
    ))

    rows = await replay_events("t-1")
    assert len(rows) == 1
    assert rows[0]["action"] == "analyze"
    assert rows[0]["risk_level"] == "med"
    assert rows[0]["decision"] == "pending"
    assert rows[0]["execution_time_ms"] == 12


async def test_route_writes_row_with_real_decision(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "a.db"))
    state = {"thread_id": "t-2", "pr_url": "u", "analysis": make_analysis(0.90)}
    await mod.node_route(state)

    rows = await replay_events("t-2")
    assert rows[-1]["action"] == "route"
    assert rows[-1]["decision"] == "auto"
    assert rows[-1]["risk_level"] == "low"


async def test_human_approval_writes_pending_then_decision(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(mod, "interrupt", lambda payload: {"choice": "approve", "feedback": "ổn"})

    state = {"thread_id": "t-3", "pr_url": "u", "analysis": make_analysis(0.65), "pr_diff": "x"}
    out = await mod.node_human_approval(state)

    rows = await replay_events("t-3")
    assert [r["decision"] for r in rows] == ["pending", "approve"]
    assert rows[-1]["reviewer_id"] == "EntityEbisu"
    assert "ổn" in rows[-1]["reason"]
    assert out["human_choice"] == "approve"


async def test_escalate_writes_two_rows_with_reviewer(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(
        mod, "interrupt", lambda payload: {q: "demo nội bộ" for q in payload["questions"]}
    )

    state = {"thread_id": "t-4", "pr_url": "u",
             "analysis": make_analysis(0.3, questions=["Vì sao MD5?"]), "pr_diff": "x"}
    out = await mod.node_escalate(state)

    rows = await replay_events("t-4")
    assert [r["action"] for r in rows] == ["escalate", "escalate"]
    assert [r["decision"] for r in rows] == ["pending", "escalate"]
    assert rows[0]["reviewer_id"] is None and rows[1]["reviewer_id"] == "EntityEbisu"
    assert out["escalation_answers"] == {"Vì sao MD5?": "demo nội bộ"}


async def test_real_interrupt_resume_writes_single_pending_row(monkeypatch, tmp_path):
    """interrupt() THẬT + Command(resume=...) THẬT: guard phải chặn bản ghi pending thứ hai.

    Đây là kịch bản thật (không monkeypatch interrupt): LangGraph chạy lại node từ đầu khi
    resume, nên code trước interrupt() thực thi hai lần.
    """
    import exercises.exercise_4_audit as mod
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "g.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(mod, "get_llm", lambda *a, **kw:
                        FakeLLM(make_analysis(0.4, questions=["Vì sao MD5?"])))
    monkeypatch.setattr(mod, "post_review_comment", lambda url, body: None)
    monkeypatch.setattr(mod, "fetch_pr", lambda url: types.SimpleNamespace(
        title="demo", diff="+ md5(pw)", files_changed=["auth.py"], head_sha="deadbeef1234"))

    graph = mod.build_graph(MemorySaver())
    cfg = {"configurable": {"thread_id": "t-resume"}}

    paused = await graph.ainvoke({"pr_url": "u", "thread_id": "t-resume"}, cfg)
    assert "__interrupt__" in paused, "graph phải pause ở node escalate"
    await graph.ainvoke(Command(resume={"Vì sao MD5?": "demo nội bộ"}), cfg)

    rows = await replay_events("t-resume")
    pending_escalate = [r for r in rows if r["action"] == "escalate" and r["decision"] == "pending"]
    assert len(pending_escalate) == 1, f"dòng escalate 'pending' bị ghi trùng: {len(pending_escalate)}"
    assert [r["action"] for r in rows] == [
        "fetch_pr", "analyze", "route", "escalate", "escalate", "synthesize", "commit",
    ]


async def test_commit_and_auto_approve_rows(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "d.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(mod, "post_review_comment", lambda url, body: None)

    s1 = {"thread_id": "t-5", "pr_url": "u", "analysis": make_analysis(0.65),
          "human_choice": "approve", "human_feedback": None}
    await mod.node_commit(s1)
    s2 = {"thread_id": "t-6", "pr_url": "u", "analysis": make_analysis(0.95)}
    await mod.node_auto_approve(s2)

    rows1, rows2 = await replay_events("t-5"), await replay_events("t-6")
    assert rows1[-1]["action"] == "commit" and rows1[-1]["decision"] == "approve"
    assert rows2[-1]["action"] == "auto_approve" and rows2[-1]["risk_level"] == "low"


async def test_synthesize_row_uses_refined_confidence(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "f.db"))
    monkeypatch.setattr(mod, "get_llm", lambda *a, **kw: FakeLLM(make_analysis(0.88)))
    state = {"thread_id": "t-8", "pr_url": "u", "pr_diff": "d",
             "escalation_answers": {"q": "a"}}
    await mod.node_synthesize(state)

    rows = await replay_events("t-8")
    assert rows[-1]["action"] == "synthesize"
    assert rows[-1]["confidence"] == 0.88
    assert rows[-1]["risk_level"] == "low"


async def test_pending_row_is_not_duplicated_on_resume(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "e.db"))
    state = {"thread_id": "t-7", "pr_url": "u"}
    entry = AuditEntry(agent_id=mod.AGENT_ID, action="human_approval", confidence=0.65,
                       risk_level="med", decision="pending", reason="chờ duyệt",
                       reviewer_id=None, execution_time_ms=1)
    await mod.audit(state, entry)   # lần chạy đầu
    await mod.audit(state, entry)   # lần chạy lại sau resume
    rows = await replay_events("t-7")
    assert len(rows) == 1, "dòng 'pending' của cùng action không được ghi 2 lần"


async def test_full_dry_run_writes_expected_action_sequence(monkeypatch, tmp_path):
    """Chạy cả graph (LLM + GitHub + interrupt đều giả) và kiểm tra chuỗi action."""
    import exercises.exercise_4_audit as mod
    from langgraph.checkpoint.memory import MemorySaver

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "full.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(mod, "get_llm", lambda *a, **kw:
                        FakeLLM(make_analysis(0.4, questions=["Vì sao MD5?"])))
    monkeypatch.setattr(mod, "interrupt", lambda payload: {"Vì sao MD5?": "demo nội bộ"})
    monkeypatch.setattr(mod, "post_review_comment", lambda url, body: None)
    monkeypatch.setattr(mod, "fetch_pr", lambda url: types.SimpleNamespace(
        title="demo", diff="+ md5(pw)", files_changed=["auth.py"], head_sha="deadbeef1234"))

    graph = mod.build_graph(MemorySaver())
    cfg = {"configurable": {"thread_id": "t-full"}}
    await graph.ainvoke({"pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/2",
                         "thread_id": "t-full"}, cfg)

    rows = await replay_events("t-full")
    actions = [r["action"] for r in rows]
    assert actions == [
        "fetch_pr", "analyze", "route", "escalate", "escalate", "synthesize", "commit",
    ], actions
    assert rows[-1]["decision"] == "approve"
