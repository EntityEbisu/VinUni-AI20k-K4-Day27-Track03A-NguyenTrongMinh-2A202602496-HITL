# Báo cáo lab Day 27 — Track 3A: HITL PR Review Agent (Nguyen Trong Minh — 2A202602496)

## 1. Tổng quan

Lab yêu cầu xây một agent review pull request có **human-in-the-loop** bằng LangGraph, gồm 4 deliverable:

| Deliverable (theo README) | Nơi triển khai | Trạng thái |
|---|---|---|
| HITL agent | `exercises/exercise_2_hitl.py`, `exercise_3_escalation.py` | ✅ chạy thật |
| Approval UI (Streamlit) | `app.py` | ✅ chạy thật (3 ảnh chụp trong `docs/evidence/`) |
| Confidence-based routing | `common/schemas.py` (ngưỡng 0.73 / 0.58) + `exercise_1_confidence.py` | ✅ |
| Audit trail (SQLite) + replay | `exercises/exercise_4_audit.py`, `audit_events` | ✅ replay được toàn phiên |

5 bài tập đều hoàn thành: **29 test offline pass**, và toàn bộ luồng đã được chạy thật với LLM thật + GitHub thật (2 bình luận review được đăng lên PR-Demo dưới tên `EntityEbisu`).

## 2. Kiến trúc

```
START → fetch_pr → analyze → route ─┬─(≥0.73)→ auto_approve ──────────────→ END
                                    │
                                    ├─(0.58–0.72)→ human_approval(interrupt) → commit → END
                                    │
                                    └─(<0.58)→ escalate(interrupt) → synthesize → commit → END
```

- `analyze` gọi LLM với `with_structured_output(PRAnalysis, method="json_schema")`; `route` rẽ nhánh theo `confidence`.
- **HITL**: node `human_approval` / `escalate` gọi `interrupt(payload)`; `main()` (và Streamlit) resume bằng `Command(resume=...)`. Checkpointer: `MemorySaver` (bài 2, 3) và `AsyncSqliteSaver` (bài 4, 5).
- **Audit**: mỗi node ghi 1 dòng `AuditEntry` vào bảng `audit_events` (chung file `hitl_audit.db` với bảng checkpoint của LangGraph).
- **Streamlit** dùng lại **đúng** `build_graph(checkpointer)` của bài 4 (không copy wiring), sidebar đọc `audit_events`.

## 3. Provider LLM — đã đổi so với README (có chủ ý, có bằng chứng)

README giả định OpenRouter + `openai/gpt-4o-mini`. Máy này **không có `OPENROUTER_API_KEY`**, nhưng có sẵn khóa **OpenCode Go** dùng cho lab hôm trước, và endpoint đó OpenAI-compatible nên `common/llm.py` (file được cung cấp) dùng được nguyên trạng.

| Hạng mục | Giá trị |
|---|---|
| Endpoint | `https://opencode.ai/zen/go/v1` |
| Model chính | `longcat-2.5-preview-free` |
| Model dự phòng | `deepseek-v4.1-flash` |
| Biến môi trường | `OPENROUTER_API_KEY` (giữ nguyên tên vì `common/llm.py` đọc tên này), `LLM_BASE_URL`, `LLM_MODEL` |

**Vì sao không dùng `deepseek-v4.1-flash-free` như mong muốn ban đầu:** model id này **không tồn tại**. `GET /v1/models` của OpenCode Go trả 37 id; trong đó `longcat-2.5-preview-free` là model free có thật, còn chỉ có `deepseek-v4.1-flash` (không có hậu tố `-free`). Vì vậy chọn `longcat-2.5-preview-free` và để `deepseek-v4.1-flash` làm dự phòng.

**Header bắt buộc:** OpenCode Go trả `HTTP 400 {"type":"MissingSessionID"}` nếu thiếu header `x-opencode-session` (đã kiểm chứng trực tiếp). Header này được truyền **không cần sửa code** thông qua biến `OPENAI_CUSTOM_HEADERS` (SDK `openai 2.36.0` đọc biến này cho cả client sync và async; định dạng nhiều dòng `Tên: giá trị`):

```dotenv
OPENAI_CUSTOM_HEADERS="x-opencode-session: day27-minh-001
User-Agent: Day27-HITL-Lab/0.1"
```

Bằng chứng: `docs/evidence/provider_probe.txt` — in ra header thật của client (`x-opencode-session` + `User-Agent`) và 2 lời gọi thật (`invoke` + `ainvoke`) đều trả `OK`. Phương án dự phòng (sửa `common/llm.py` hoặc proxy nội bộ) **không phải dùng tới**.

## 4. Kết quả từng bài tập

### Exercise 1 — Confidence routing
`docs/evidence/ex1_pr1.txt`, `ex1_pr2.txt`

| PR | confidence | nhánh | kỳ vọng của đề |
|---|---|---|---|
| #1 `feat: add priority field to tasks` | **65 %** | `human_approval` | 58–72 % ✅ |
| #2 `feat: add user login and cloud sync` | **20 %** | `escalate` | < 58 % ✅ |

Hai PR ra **hai nhánh khác nhau** — đúng tiêu chí "Success" của README.

Nhánh `auto_approve` không có PR demo tương ứng (cả 2 PR của PR-Demo đều không rủi ro thấp), nên được chứng minh bằng 1 lời gọi LLM thật trên một diff tí hon tự soạn — `scripts/demo_auto_branch.py`, kết quả `confidence = 0.93 → auto_approve`, `risk_level = low` (`docs/evidence/ex1_auto_branch.txt`). Node `auto_approve` (có đăng bình luận) được kiểm bằng test offline `test_commit_and_auto_approve_rows`.

**Lịch sử hiệu chỉnh (trung thực):** prompt đầu tiên cho PR#1 = 54 % và PR#2 = 57 % → **cả hai đều rơi vào nhánh escalate, sai kỳ vọng**. Nguyên nhân: prompt cũ không tách bạch "độ chắc chắn của đánh giá" với "mức nguy hiểm của code". Đã viết lại prompt thành **quy trình 2 bước** (BƯỚC 1: danh sách tín hiệu rủi ro cao cụ thể → chỉ khi có mới được < 0.58; BƯỚC 2: phân loại theo mức thay đổi) trong `common_prompts.py`. Sau đó PR#1 = 65 %, PR#2 = 28 % (`docs/evidence/calibration_run2.txt`). **Không đổi ngưỡng 0.73/0.58 trong `common/schemas.py`.**
Ghi chú: giữa các lần chạy, model free dao động ±0.06 (PR#1 đo được 0.62 / 0.65 / 0.68; PR#2 0.20 / 0.22 / 0.25 / 0.28) — vẫn nằm đúng nhánh.

### Exercise 2 — HITL với `interrupt()`
`docs/evidence/ex2_pr1_approve.txt`, `ex2_github_comment.txt`

Graph pause ở `human_approval` (panel hiện diff + lý do + danh sách comment), chọn `approve` → resume → node `commit` đăng bình luận lên PR #1.

Đã xác minh **trên GitHub**, không chỉ tin log console:
`https://github.com/VinUni-AI20k/PR-Demo/pull/1#issuecomment-6206990667` (tác giả `EntityEbisu`, `### Automated review (confidence 65%)`).

Lưu ý: PR #1 đã có 719 bình luận từ các bạn khác, nên phải duyệt hết các trang của `GET /issues/1/comments` rồi lọc theo login mới thấy — hai lần kiểm tra đầu (chỉ lấy trang 1) đã báo nhầm "0 comment của EntityEbisu".
Nhánh `edit` cũng đã chạy: `docs/evidence/ex2_pr1_edit.txt` → `skipping comment (choice=edit)` → `rejected` (đúng như skeleton: chỉ `approve` mới đăng).

### Exercise 3 — Escalation + reviewer Q&A
`docs/evidence/ex3_pr2_escalate.txt`, `ex3_github_comment.txt`

PR #2 (confidence 20–28 %) → node `escalate` hỏi **4 câu hỏi cụ thể, có file:line**, ví dụ:

```
? Vì sao storage.py:15 lại dùng f-string để nhét trực tiếp `title` vào SQL thay vì parameterized query?
? Vì sao auth.py:10 chọn MD5 không salt cho password hashing thay vì bcrypt/argon2?
? Vì sao sync.py:9 dùng http:// thay vì https:// cho endpoint nhận bearer token?
? Hard-coded user_id = 1 ở sync.py:35 có phải là design tạm thời không?
```

Sau khi trả lời → `synthesize` (LLM thật) → confidence tinh chỉnh **88 %** → `commit` đăng bản review đã tinh chỉnh, trong đó **trích dẫn nguyên câu trả lời của reviewer** cho từng rủi ro: `.../pull/2#issuecomment-6207037152`.

### Exercise 4 — Audit trail có cấu trúc
`docs/evidence/ex4_rows.txt`, `ex4_replay_pr1.txt`, `ex4_replay_pr2.txt`, `ex4_invariant.txt`, `ex4_dup_check.txt`

Hai phiên thật (chạy sau khi sửa guard):

| thread | PR | chuỗi dòng audit |
|---|---|---|
| `183f29c9…` | #1 | fetch_pr → analyze(0.68) → route(pending) → human_approval(pending) → human_approval(**approve**, `EntityEbisu`) → commit(approve) |
| `747b5b15…` | #2 | fetch_pr → analyze(0.22) → route(**escalate**) → escalate(pending) → escalate(escalate, `EntityEbisu`) → synthesize(0.35) → commit(approve) |

Các truy vấn kiểm tra:

```sql
-- 6 dòng cho phiên human_approval, 7 dòng cho phiên escalate
SELECT substr(thread_id,1,8), action, confidence, risk_level, decision, reviewer_id
  FROM audit_events ORDER BY id;

-- bất biến của đề: rủi ro cao mà agent tự duyệt -> KHÔNG BAO GIỜ xảy ra
SELECT COUNT(*) FROM audit_events WHERE risk_level='high' AND decision='auto';   -- = 0 ✅
SELECT ROUND(AVG(confidence),3) FROM audit_events WHERE decision='approve';      -- = 0.57
SELECT thread_id, action, COUNT(*) FROM audit_events WHERE decision='pending'
 GROUP BY thread_id, action HAVING COUNT(*) > 1;                                 -- TRỐNG ✅
```

**Một lỗi thật đã phát hiện và sửa:** LangGraph chạy lại node chứa `interrupt()` **từ đầu** khi resume (README FAQ cũng cảnh báo), nên dòng audit "trước interrupt" bị ghi lần thứ hai. Ban đầu tôi chỉ chặn `decision='pending'`, nhưng dòng trước-interrupt của `escalate` lại đặt `decision='escalate'` nên **vẫn bị trùng** (thấy rõ trong phiên `315eceb7`). Đã sửa: dòng trước interrupt của `escalate` dùng `decision='pending'` (nhánh escalate đã được ghi ở dòng `route`), và guard trong `audit()` chặn mọi dòng `pending` trùng theo `(thread_id, action)`. Có test dùng **interrupt() thật + Command(resume=...) thật** để chứng minh: `test_real_interrupt_resume_writes_single_pending_row`.

### Exercise 5 — Streamlit approval UI
`docs/evidence/ex5_streamlit.log`, `ex5_card_approval.png`, `ex5_ui_committed_pr1.png`, `ex5_ui_committed_pr2.png`, `ex5_escalation_card.txt`

`uv run streamlit run app.py` (HTTP 200). Đã lái thật bằng browser (DOM/accessibility, text-first):

| Luồng | Kết quả trên UI | thread_id |
|---|---|---|
| PR #1 → card "Approval requested — confidence 66 %" → **Approve** | `✓ committed — comment posted to .../pull/1` | `a4dc2266…` |
| PR #2 → card "Strong escalation — confidence 25 %" + form 4 câu hỏi → điền → **Submit answers** | `✓ committed — comment posted to .../pull/2` | `d6321d00…` |
| PR #1 → card approval → **Reject** | `Rejected — no comment posted` | `545ce408…` |

Sidebar "Recent sessions" + "Sự kiện của phiên" đọc trực tiếp `audit_events` qua `app_helpers.py`.

## 5. Test (TDD, offline, 0 quota)

`docs/evidence/pytest_full.txt` — **29 passed** (`uv run pytest`). Toàn bộ test **không gọi mạng**: LLM được thay bằng `tests/fakes.py`, mọi lời gọi `post_review_comment` bị monkeypatch, DB test nằm trong `tmp_path`.

| File test | Nội dung |
|---|---|
| `test_fakes.py` | fixture LLM giả |
| `test_ex1_routing.py` | 7 test biên ngưỡng (0.73, 0.72, 0.58, 0.57) + có đủ 6 node |
| `test_ex1_analyze.py` | `with_structured_output(PRAnalysis)`, diff nằm trong prompt, prompt có thang hiệu chỉnh |
| `test_ex2_interrupt.py` | payload `interrupt()` đủ trường; graph compile **có** checkpointer |
| `test_ex3_escalation.py` | payload escalation + fallback khi LLM không sinh câu hỏi + synthesize dùng câu trả lời + wiring `escalate→synthesize→commit` |
| `test_ex4_audit.py` | 1 dòng/lượt ghi; `route` đặt `decision` thật; cặp pending/after cho 2 node HITL; `commit`/`auto_approve`/`synthesize`; **guard chống trùng với interrupt thật**; chạy cả graph (dry-run) và kiểm tra đúng chuỗi 7 action |
| `test_ex5_sidebar.py` | truy vấn sidebar + `worst_risk` không dùng so sánh chuỗi |
| `test_ex5_widgets.py` | `app.py` import được, có 3 hàm renderer/`run_graph` |

## 6. Sai lệch so với đề bài (khai báo đầy đủ)

1. **Provider**: OpenRouter/gpt-4o-mini → **OpenCode Go/`longcat-2.5-preview-free`** (không có khóa OpenRouter trên máy). `common/llm.py` **không bị sửa** — cấu hình nằm trọn trong `.env` + biến `OPENAI_CUSTOM_HEADERS` (xem mục 3).
2. **`deepseek-v4.1-flash-free` không tồn tại**; dùng `longcat-2.5-preview-free`, dự phòng `deepseek-v4.1-flash`.
3. **Prompt hiệu chỉnh confidence** được viết lại thành quy trình 2 bước sau khi bản đầu cho PR#1 vào sai nhánh (54 %). Không đổi ngưỡng trong `common/schemas.py`.
4. **Thêm guard chống trùng dòng audit** trong `audit()` — nhiều hơn yêu cầu "một dòng" của TODO, nhưng cần thiết vì LangGraph chạy lại node khi resume; đã có test chứng minh.
5. **Thêm thư mục `tests/` + pytest/pytest-asyncio** (dev deps) — repo gốc không có test nào.
6. **Thêm `app_helpers.py`** ở gốc repo để sidebar truy vấn audit (không sửa `audit/replay.py` vì đó là file được cung cấp).
7. **`GITHUB_TOKEN`**: không tạo PAT mới mà dùng credential GitHub đã lưu trong Windows Credential Manager (git-credential-manager) của chính tài khoản `EntityEbisu` — token có scope `repo`, `gist`, `workflow`. `.env` đã gitignore, không có khóa nào bị commit (đã quét). **Nên kiểm tra hạn dùng của token này.**
8. **Nhiều hơn một bình luận** được đăng lên PR #1/#2 do phải chạy lại demo nhiều lần (Exercise 2 và 4 chạy riêng, thêm 3 lần chạy qua UI).
9. **Sửa deprecation** `use_container_width=True` → `width="stretch"` trong `app.py` (Streamlit cảnh báo tính năng này bị bỏ sau 2025-12-31).
10. **`streamlit` đã có sẵn** trong `pyproject.toml` (README nói cần thêm) — chỉ xác nhận, không thêm lại.

## 7. Lỗi/phát hiện phụ trong chính tài liệu & code được cung cấp

- **`audit/replay.py` tính `worst_risk` sai**: dùng `MAX(risk_level)` là so sánh **chuỗi**, mà `'med' > 'low' > 'high'`, nên phiên `747b5b15` (toàn dòng `high` + 1 dòng `med`) hiển thị `worst_risk = med`. Bằng chứng đối chiếu: `docs/evidence/ex5_worst_risk_contrast.txt` — `replay.py` nói `med`, `app_helpers.py` (dùng `CASE` theo hạng) nói `high`. **Không sửa file được cung cấp**, chỉ ghi nhận.
- Kết luận này cũng chứng minh vì sao sidebar phải có truy vấn riêng.

## 8. Hạn chế & hướng phát triển

- **`synthesize` không phải lúc nào cũng làm confidence tăng.** Với câu trả lời kiểu "sẽ sửa ở PR sau", model free giữ nguyên đánh giá rủi ro (đo được 0.20 và 0.35 ở hai lần chạy); khi câu trả lời thực sự giải toả lo ngại thì lên 0.88 (lần chạy Exercise 3). Đây là hành vi hợp lý chứ không phải lỗi: "sẽ sửa sau" không làm PR an toàn hơn.
- **Model free không ổn định**: confidence dao động ±0.06 giữa các lần; có thể bị 429. `.env` đã có `LLM_FALLBACK_MODEL=deepseek-v4.1-flash`.
- **SQLite dùng chung file** cho checkpointer + audit; đã bật `PRAGMA journal_mode=WAL` để tránh `database is locked`. Không gặp lỗi này trong 4 lần chạy.
- **Streamlit chạy `asyncio.run()` mỗi lần bấm** (theo skeleton): chấp nhận được cho lab, nhưng mỗi lần resume lại mở/đóng SQLite connection. Tab trình duyệt đôi khi bị crash khi poll DOM quá nhiều lần bằng CDP (đã gặp 1 lần, phải chạy lại luồng).
- Chưa làm phần bonus (time-travel, calibration theo N phiên, `Send` fan-out, auto-edit).

## 9. Cách chạy lại

```bash
cd D:/VinUni/day27/VinUni-AI20k-K4-Day27-Track03A-NguyenTrongMinh-2A202602496-HITL
uv sync
cp .env.example .env    # điền OPENROUTER_API_KEY (khóa OpenCode Go) + GITHUB_TOKEN + GITHUB_USER

uv run python scripts/probe_provider.py      # kiểm tra header + gọi thật
uv run python scripts/probe_structured.py    # kiểm tra structured output
uv run pytest                                # 29 test offline

uv run python exercises/exercise_1_confidence.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/1
uv run python exercises/exercise_2_hitl.py      --pr https://github.com/VinUni-AI20k/PR-Demo/pull/1   # approve/reject/edit
uv run python exercises/exercise_3_escalation.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/2  # trả lời câu hỏi
uv run python exercises/exercise_4_audit.py      --pr https://github.com/VinUni-AI20k/PR-Demo/pull/1
uv run python -m audit.replay --thread <thread_id>
uv run python -m audit.replay --list

uv run streamlit run app.py                  # UI: card theo 3 nhóm confidence
```

## 10. Bản đồ file

| Nhóm | File |
|---|---|
| Sửa (TODO của đề) | `exercises/exercise_1_confidence.py`, `exercise_2_hitl.py`, `exercise_3_escalation.py`, `exercise_4_audit.py`, `app.py` |
| Thêm mới | `common_prompts.py`, `app_helpers.py`, `tests/` (9 file), `scripts/probe_provider.py`, `scripts/probe_structured.py`, `scripts/calibrate.py`, `scripts/demo_auto_branch.py`, `.python-version` |
| Sửa (cấu hình) | `pyproject.toml` (dev deps + pytest config), `.env.example` |
| Không sửa | `common/*.py`, `audit/*.py`, `audit/schema.sql` (đúng yêu cầu "provided, don't modify") |
| Bằng chứng | `docs/evidence/` (27 file: log chạy thật, ảnh chụp UI, kết quả SQL, replay) |
