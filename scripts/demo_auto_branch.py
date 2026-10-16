"""Minh hoạ nhánh auto_approve (> 72%) bằng 1 lời gọi LLM THẬT.

Vì sao cần script này: PR-Demo chỉ có 2 PR demo, cả hai đều KHÔNG rủi ro thấp
(PR#1 ~0.65, PR#2 ~0.25), nên không có PR thật nào rơi vào nhánh > 0.73.
Script dùng một diff tí hon tự soạn (thêm field optional, không đổi hành vi) và
CHỈ gọi analyze + route để chứng minh nhánh auto_approve thực sự bật — KHÔNG đăng
bình luận lên GitHub (node auto_approve không được gọi).

Chạy: uv run python scripts/demo_auto_branch.py
"""

from __future__ import annotations

from dotenv import load_dotenv

from common.llm import get_llm
from common.schemas import AUTO_APPROVE_THRESHOLD, PRAnalysis, risk_level_for
from common_prompts import ANALYZE_SYSTEM_PROMPT, STRUCTURED_METHOD

load_dotenv(dotenv_path=".env")

TINY_DIFF = """diff --git a/tasktrack/models.py b/tasktrack/models.py
index 9fb4701..cce0f4e 100644
--- a/tasktrack/models.py
+++ b/tasktrack/models.py
@@ -6,3 +6,4 @@ class Task:
     id: int | None
     title: str
     done: bool = False
+    note: str | None = None   # ghi chú tuỳ chọn, không đổi hành vi hiện có
"""


def main() -> int:
    a = get_llm().with_structured_output(PRAnalysis, method=STRUCTURED_METHOD).invoke([
        {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Tiêu đề PR: add optional note field\n\nDiff:\n{TINY_DIFF}"},
    ])
    threshold = AUTO_APPROVE_THRESHOLD
    decision = "auto_approve" if a.confidence >= threshold else "human_approval/escalate"
    print(f"confidence        = {a.confidence:.2f}")
    print(f"risk_level        = {risk_level_for(a.confidence)}")
    print(f"ngưỡng auto       = {threshold}")
    print(f"reasoning         = {a.confidence_reasoning[:200]}")
    print(f"NHÁNH ĐƯỢC CHỌN   = {decision}")
    return 0 if decision == "auto_approve" else 1


if __name__ == "__main__":
    raise SystemExit(main())
