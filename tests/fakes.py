"""LLM giả để test node mà không gọi mạng (không tốn quota)."""

from __future__ import annotations

from typing import Any

from common.schemas import PRAnalysis, ReviewComment


class FakeStructured:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.messages: list[dict] = []

    def invoke(self, messages, config=None, **kwargs):  # noqa: ANN001
        self.messages = list(messages)
        return self._result

    async def ainvoke(self, messages, config=None, **kwargs):  # noqa: ANN001
        self.messages = list(messages)
        return self._result


class FakeLLM:
    """with_structured_output(...) luôn trả về cùng một PRAnalysis đã cấu hình."""

    def __init__(self, result: PRAnalysis) -> None:
        self.result = result
        self.structured = FakeStructured(result)
        self.schemas: list[Any] = []

    def with_structured_output(self, schema, **kwargs):  # noqa: ANN001
        self.schemas.append(schema)
        return self.structured

    def invoke(self, messages, **kwargs):  # noqa: ANN001
        self.structured.messages = list(messages)
        return self.result


def make_analysis(confidence: float = 0.65, questions: list[str] | None = None) -> PRAnalysis:
    return PRAnalysis(
        summary="Thêm trường priority cho model Task, có migration schema.",
        risk_factors=["migration schema"] if confidence < 0.73 else [],
        comments=[
            ReviewComment(
                file="tasktrack/models.py",
                line=12,
                severity="suggestion",
                body="Nên có migration tương ứng.",
            )
        ],
        confidence=confidence,
        confidence_reasoning="Diff nhỏ nhưng có thay đổi schema.",
        escalation_questions=questions or [],
    )
