from tests.fakes import FakeLLM, make_analysis


def test_fake_llm_returns_configured_analysis():
    fake = FakeLLM(make_analysis(0.65))
    out = fake.with_structured_output(object).invoke([{"role": "user", "content": "x"}])
    assert out.confidence == 0.65
    assert out.comments[0].file == "tasktrack/models.py"
