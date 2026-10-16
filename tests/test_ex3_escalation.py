import exercises.exercise_3_escalation as mod
from common.schemas import PRAnalysis
from tests.fakes import FakeLLM, make_analysis


def test_escalate_interrupt_payload_contains_questions(monkeypatch):
    captured: dict = {}

    def fake_interrupt(payload):
        captured.update(payload)
        return {q: f"trả lời cho {q}" for q in payload["questions"]}

    monkeypatch.setattr(mod, "interrupt", fake_interrupt)

    questions = ["Vì sao dùng MD5 ở auth.py?", "SYNC_URL có phải HTTPS ở production không?"]
    state = {
        "analysis": make_analysis(0.35, questions=questions),
        "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/2",
    }

    out = mod.node_escalate(state)

    assert captured["kind"] == "escalation"
    assert captured["questions"] == questions
    assert captured["risk_factors"], "phải gửi risk_factors cho người duyệt"
    assert out["escalation_answers"] == {q: f"trả lời cho {q}" for q in questions}


def test_escalate_falls_back_when_llm_sends_no_questions(monkeypatch):
    monkeypatch.setattr(mod, "interrupt", lambda payload: {q: "x" for q in payload["questions"]})
    out = mod.node_escalate({"analysis": make_analysis(0.3, questions=[]), "pr_url": "u"})
    assert len(out["escalation_answers"]) == 2


def test_synthesize_uses_answers_and_returns_refined(monkeypatch):
    fake = FakeLLM(make_analysis(0.88))
    monkeypatch.setattr(mod, "get_llm", lambda *a, **kw: fake)
    state = {
        "pr_diff": "+ md5(pw)",
        "escalation_answers": {"Vì sao dùng MD5?": "chỉ là demo nội bộ"},
    }
    out = mod.node_synthesize(state)
    assert isinstance(out["analysis"], PRAnalysis)
    assert out["analysis"].confidence == 0.88
    sent = "\n".join(m["content"] for m in fake.structured.messages)
    assert "chỉ là demo nội bộ" in sent


def test_ex3_graph_wires_escalate_through_synthesize_to_commit():
    graph = mod.build_graph().get_graph()
    edges = {(e.source, e.target) for e in graph.edges}
    assert ("escalate", "synthesize") in edges
    assert ("synthesize", "commit") in edges


def test_analyze_prompt_asks_for_escalation_questions(monkeypatch):
    fake = FakeLLM(make_analysis(0.3, questions=["Vì sao MD5?"]))
    monkeypatch.setattr(mod, "get_llm", lambda *a, **kw: fake)
    out = mod.node_analyze({"pr_title": "t", "pr_diff": "+ md5"})
    sent = "\n".join(m["content"] for m in fake.structured.messages)
    assert "escalation_questions" in sent
    assert out["analysis"].escalation_questions == ["Vì sao MD5?"]
