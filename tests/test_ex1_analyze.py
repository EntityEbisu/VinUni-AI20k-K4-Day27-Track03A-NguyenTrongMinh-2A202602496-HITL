from common.schemas import PRAnalysis
from exercises.exercise_1_confidence import node_analyze
from tests.fakes import FakeLLM, make_analysis


def test_node_analyze_returns_analysis_and_sends_diff(monkeypatch):
    import exercises.exercise_1_confidence as mod

    fake = FakeLLM(make_analysis(0.65))
    monkeypatch.setattr(mod, "get_llm", lambda *a, **kw: fake)

    out = node_analyze({"pr_title": "add priority", "pr_diff": "+ priority = None"})

    assert isinstance(out["analysis"], PRAnalysis)
    assert out["analysis"].confidence == 0.65
    assert fake.schemas == [PRAnalysis], "phải gọi with_structured_output(PRAnalysis)"
    sent = "\n".join(m["content"] for m in fake.structured.messages)
    assert "+ priority = None" in sent, "diff phải nằm trong prompt"
    assert "0.58" in sent, "prompt phải có thang hiệu chỉnh confidence"
