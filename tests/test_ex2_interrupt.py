import exercises.exercise_2_hitl as mod
from tests.fakes import make_analysis


def test_human_approval_interrupt_payload_and_resume(monkeypatch):
    captured: dict = {}

    def fake_interrupt(payload):
        captured.update(payload)
        return {"choice": "approve", "feedback": "ok"}

    monkeypatch.setattr(mod, "interrupt", fake_interrupt)

    state = {
        "analysis": make_analysis(0.65),
        "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/1",
        "pr_diff": "+ priority = None\n" * 200,
    }
    out = mod.node_human_approval(state)

    assert captured["kind"] == "approval_request"
    assert captured["confidence"] == 0.65
    assert captured["summary"]
    assert captured["comments"] and captured["comments"][0]["file"] == "tasktrack/models.py"
    assert len(captured["diff_preview"]) <= 2000
    assert out == {"human_choice": "approve", "human_feedback": "ok"}


def test_graph_is_compiled_with_checkpointer():
    graph = mod.build_graph()
    assert graph.checkpointer is not None, "interrupt() cần checkpointer trong .compile()"
