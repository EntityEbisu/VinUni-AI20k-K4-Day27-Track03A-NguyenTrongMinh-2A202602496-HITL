"""Tìm method chạy được cho with_structured_output trên model free.

Chạy: uv run python scripts/probe_structured.py
"""

from __future__ import annotations

from dotenv import load_dotenv

from common.llm import get_llm
from common.schemas import PRAnalysis

load_dotenv()

DIFF = """diff --git a/tasktrack/models.py b/tasktrack/models.py
+    priority: str | None = None
"""

MSGS = [
    {"role": "system", "content": "Bạn là reviewer cấp cao. Trả về đánh giá có cấu trúc."},
    {"role": "user", "content": f"Tiêu đề PR: add priority field\n\nDiff:\n{DIFF}"},
]


def main() -> int:
    for method in ("json_schema", "function_calling", None):
        try:
            llm = get_llm()
            structured = (
                llm.with_structured_output(PRAnalysis)
                if method is None
                else llm.with_structured_output(PRAnalysis, method=method)
            )
            res = structured.invoke(MSGS)
            print(
                f"OK   method={method or 'default'} -> {type(res).__name__} "
                f"confidence={res.confidence:.2f} comments={len(res.comments)}"
            )
            print(f"RESULT: dùng method={method!r}")
            return 0
        except Exception as exc:  # noqa: BLE001 - probe cần bắt mọi lỗi
            print(f"FAIL method={method or 'default'}: {type(exc).__name__}: {str(exc)[:200]}")
    print("RESULT: không method nào chạy được -> Task A7-fallback")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
