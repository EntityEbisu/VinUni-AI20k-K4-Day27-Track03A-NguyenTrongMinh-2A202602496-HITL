"""Truy vấn audit_events phục vụ sidebar Streamlit.

Không sửa `audit/replay.py` (thư mục được cung cấp). Lưu ý: truy vấn trong file đó dùng
`MAX(risk_level)` — đó là so sánh CHUỖI (lexicographic) nên cho kết quả sai thứ tự rủi ro
('med' > 'low' > 'high'). Ở đây tính hạng rủi ro bằng CASE rồi map lại nhãn.
"""

from __future__ import annotations

from typing import Any

from common.db import db_conn

_RANK_TO_LABEL = {3: "high", 2: "med", 1: "low"}


async def fetch_recent_threads(limit: int = 25) -> list[dict[str, Any]]:
    """Trả về các phiên review gần đây (mới nhất trước) kèm mức rủi ro cao nhất."""
    async with db_conn() as conn:
        async with conn.execute(
            """
            SELECT thread_id,
                   pr_url,
                   MIN(timestamp) AS started,
                   MAX(timestamp) AS last_event,
                   MAX(CASE risk_level WHEN 'high' THEN 3 WHEN 'med' THEN 2 ELSE 1 END) AS worst_rank,
                   COUNT(*) AS events
              FROM audit_events
             GROUP BY thread_id, pr_url
             ORDER BY MAX(timestamp) DESC
             LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        row["worst_risk"] = _RANK_TO_LABEL.get(row.pop("worst_rank"), "low")
        out.append(row)
    return out


async def fetch_thread_events(thread_id: str) -> list[dict[str, Any]]:
    """Toàn bộ sự kiện của một phiên, theo thứ tự thời gian."""
    async with db_conn() as conn:
        async with conn.execute(
            """
            SELECT timestamp, action, confidence, risk_level, reviewer_id, decision,
                   reason, execution_time_ms
              FROM audit_events
             WHERE thread_id = ?
             ORDER BY id
            """,
            (thread_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
