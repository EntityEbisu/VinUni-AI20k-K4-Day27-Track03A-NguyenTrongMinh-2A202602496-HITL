"""Đo confidence của model trên 2 PR demo (dùng để hiệu chỉnh prompt).

Chạy: uv run python scripts/calibrate.py
"""

from __future__ import annotations

from dotenv import load_dotenv

from common.github import fetch_pr
from common.llm import get_llm
from common.schemas import PRAnalysis
from common_prompts import ANALYZE_SYSTEM_PROMPT, STRUCTURED_METHOD

load_dotenv(dotenv_path=".env")


def main() -> int:
    for n, expected in ((1, "58-72% (human_approval)"), (2, "<58% (escalate)")):
        pr = fetch_pr(f"https://github.com/VinUni-AI20k/PR-Demo/pull/{n}")
        a = get_llm().with_structured_output(PRAnalysis, method=STRUCTURED_METHOD).invoke([
            {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Tiêu đề PR: {pr.title}\n\nDiff:\n{pr.diff}"},
        ])
        print(f"--- PR#{n} ({pr.title}) — kỳ vọng {expected}")
        print(f"    confidence = {a.confidence:.2f}  risk_level = "
              f"{__import__('common.schemas', fromlist=['risk_level_for']).risk_level_for(a.confidence)}")
        print(f"    reasoning  = {a.confidence_reasoning[:400]}")
        print(f"    risks      = {a.risk_factors}")
        print(f"    questions  = {a.escalation_questions}")
        print(f"    comments   = {[(c.severity, c.file) for c in a.comments]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
