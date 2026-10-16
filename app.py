"""Exercise 5 — Streamlit approval UI for the HITL PR review agent.

Run with:
    uv run streamlit run app.py

Goal: wrap the LangGraph built in exercises 1–4 in a web UI that adapts to
the confidence bucket of each PR.

Routing thresholds (common/schemas.py):
    > 72%        auto_approve     UI shows a success card; reviewer does nothing
    58 – 72%     human_approval   UI shows Approve / Reject / Edit buttons
    <  58%       escalate         UI shows a question form for the reviewer
"""

from __future__ import annotations

import asyncio
import uuid

import streamlit as st
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

import app_helpers
from common.db import db_path
# Dùng lại đúng graph của bài 4 (build_graph nhận checkpointer) — không copy wiring.
from exercises.exercise_4_audit import build_graph


load_dotenv()


# ─── Session state ─────────────────────────────────────────────────────────
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "pr_url" not in st.session_state:
    st.session_state.pr_url = ""
if "interrupt_payload" not in st.session_state:
    st.session_state.interrupt_payload = None
if "final" not in st.session_state:
    st.session_state.final = None
if "selected_thread" not in st.session_state:
    st.session_state.selected_thread = None


# ─── Page setup ────────────────────────────────────────────────────────────
st.set_page_config(page_title="HITL PR Review", layout="wide")
st.title("HITL PR Review Agent")


# ─── Sidebar — recent sessions ─────────────────────────────────────────────
with st.sidebar:
    st.header("Recent sessions")
    # Dữ liệu lấy từ bảng audit_events qua app_helpers (KHÔNG sửa audit/replay.py).
    try:
        threads = asyncio.run(app_helpers.fetch_recent_threads())
    except Exception as exc:  # chưa có DB / chưa có bảng -> coi như chưa có phiên nào
        threads = []
        st.caption(f"(chưa đọc được audit_events: {exc})")

    if threads:
        st.dataframe(
            [
                {
                    "thread": t["thread_id"][:8],
                    "pr": t["pr_url"].rsplit("/", 1)[-1],
                    "risk": t["worst_risk"],
                    "events": t["events"],
                    "last": str(t["last_event"])[:19],
                }
                for t in threads
            ],
            use_container_width=True,
            hide_index=True,
        )
        pick = st.selectbox(
            "Xem chi tiết phiên",
            options=[t["thread_id"] for t in threads],
            index=None,
            placeholder="chọn thread_id",
        )
        if pick:
            st.session_state.selected_thread = pick
    else:
        st.caption("(chưa có phiên nào trong audit_events)")

    if st.session_state.selected_thread:
        st.subheader("Sự kiện của phiên")
        events = asyncio.run(app_helpers.fetch_thread_events(st.session_state.selected_thread))
        st.dataframe(
            [
                {
                    "action": e["action"],
                    "conf": round(e["confidence"], 2),
                    "risk": e["risk_level"],
                    "decision": e["decision"],
                    "reviewer": e["reviewer_id"] or "-",
                    "ms": e["execution_time_ms"],
                }
                for e in events
            ],
            use_container_width=True,
            hide_index=True,
        )


# ─── Top form — start a new review ─────────────────────────────────────────
with st.form("start"):
    pr_url = st.text_input(
        "PR URL", value=st.session_state.pr_url,
        placeholder="https://github.com/VinUni-AI20k/PR-Demo/pull/1",
    )
    submitted = st.form_submit_button("Run review")


# ─── Renderers per interrupt kind ──────────────────────────────────────────
def render_approval_card(payload: dict) -> dict | None:
    """58–72% bucket: show the LLM review + 3 buttons. Return resume dict or None."""
    conf = payload["confidence"]
    st.subheader(f"Approval requested — confidence {conf:.0%}")
    st.caption(payload["confidence_reasoning"])
    st.markdown(payload["summary"])

    for c in payload.get("comments", []):
        st.markdown(f"- **[{c['severity']}]** `{c['file']}:{c.get('line') or '?'}` — {c['body']}")

    with st.expander("Diff"):
        st.code(payload.get("diff_preview", ""), language="diff")

    feedback = st.text_input("Feedback (optional)", key="approval_feedback")
    col1, col2, col3 = st.columns(3)
    choice = None
    if col1.button("Approve", type="primary"):
        choice = "approve"
    if col2.button("Reject"):
        choice = "reject"
    if col3.button("Edit"):
        choice = "edit"
    if choice is None:
        return None
    return {"choice": choice, "feedback": feedback}


def render_escalation_card(payload: dict) -> dict | None:
    """< 58% bucket: show risk factors + question form. Return {question: answer} or None."""
    conf = payload["confidence"]
    st.subheader(f"Strong escalation — confidence {conf:.0%}")
    st.caption(payload["confidence_reasoning"])
    if payload.get("risk_factors"):
        st.error("Risks: " + ", ".join(payload["risk_factors"]))
    st.markdown(payload["summary"])

    with st.form("escalation"):
        answers: dict[str, str] = {}
        for i, q in enumerate(payload["questions"]):
            answers[q] = st.text_input(q, key=f"escalation_answer_{i}")
        submitted_answers = st.form_submit_button("Submit answers")

    if not submitted_answers:
        return None
    if not any(v.strip() for v in answers.values()):
        st.warning("Cần trả lời ít nhất một câu hỏi trước khi gửi.")
        return None
    return {q: v for q, v in answers.items() if v.strip()}


# ─── Drive the graph ───────────────────────────────────────────────────────
async def run_graph(pr_url: str, thread_id: str, resume_value=None):
    """Invoke the graph once. Returns the final result or {'__interrupt__': ...}."""
    async with AsyncSqliteSaver.from_conn_string(db_path()) as cp:
        await cp.setup()
        # build_graph của bài 4 nhận checkpointer -> dùng chính checkpointer SQLite này,
        # nên phiên có thể resume được kể cả sau khi tắt Streamlit.
        graph = build_graph(cp)
        cfg = {"configurable": {"thread_id": thread_id}}
        if resume_value is None:
            return await graph.ainvoke({"pr_url": pr_url, "thread_id": thread_id}, cfg)
        return await graph.ainvoke(Command(resume=resume_value), cfg)


# ─── Main flow ─────────────────────────────────────────────────────────────
if submitted and pr_url:
    st.session_state.pr_url = pr_url
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.interrupt_payload = None
    st.session_state.final = None

    with st.spinner("Fetching PR + asking the LLM..."):
        result = asyncio.run(run_graph(pr_url, st.session_state.thread_id))

    if "__interrupt__" in result:
        st.session_state.interrupt_payload = result["__interrupt__"][0].value
    else:
        st.session_state.final = result

# Render the current interrupt card, if any
payload = st.session_state.interrupt_payload
if payload is not None:
    kind = payload["kind"]
    answer = render_approval_card(payload) if kind == "approval_request" else render_escalation_card(payload)
    if answer is not None:
        with st.spinner("Resuming..."):
            result = asyncio.run(run_graph(
                st.session_state.pr_url, st.session_state.thread_id, resume_value=answer,
            ))
        if "__interrupt__" in result:
            st.session_state.interrupt_payload = result["__interrupt__"][0].value
        else:
            st.session_state.interrupt_payload = None
            st.session_state.final = result
        st.rerun()

# Render final state, if reached
if st.session_state.final is not None:
    final = st.session_state.final
    action = final.get("final_action", "?")
    if action.startswith("auto") or action.startswith("committed"):
        st.success(f"✓ {action} — comment posted to {st.session_state.pr_url}")
    elif action == "rejected":
        st.warning("Rejected — no comment posted")
    else:
        st.info(f"final_action = {action}")
    st.caption(f"thread_id = {st.session_state.thread_id}  ·  replay: "
               f"`uv run python -m audit.replay --thread {st.session_state.thread_id}`")
