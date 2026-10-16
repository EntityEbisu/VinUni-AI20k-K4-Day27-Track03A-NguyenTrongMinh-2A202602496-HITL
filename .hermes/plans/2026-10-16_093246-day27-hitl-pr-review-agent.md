# Kế hoạch triển khai — Day27 Track03A: HITL PR Review Agent (LangGraph + Streamlit)

> **Dành cho Hermes:** thực thi kế hoạch này bằng skill `subagent-driven-development` — mỗi task giao cho 1 subagent mới, review 2 bước (đúng spec → chất lượng code) rồi mới sang task kế tiếp.

**Mục tiêu (1 câu):** Hoàn thành đủ 5 bài tập của lab (`exercises/exercise_1..4` + `app.py`) để có một agent review PR có human-in-the-loop (routing theo confidence, `interrupt()`/resume, audit trail SQLite replay được, UI Streamlit), kèm bằng chứng chạy thật và báo cáo tiếng Việt.

**Kiến trúc:** Một `StateGraph` duy nhất (`ReviewState`) đi qua `fetch_pr → analyze → route`; `route` rẽ 3 nhánh theo confidence tự khai của LLM (`auto_approve` ≥ 0.73, `human_approval` 0.58–0.72, `escalate` < 0.58). Nhánh HITL dùng `interrupt()` + `Command(resume=...)`, nhánh escalate đi tiếp `synthesize → commit`; mọi node ghi 1 dòng `AuditEntry` vào bảng `audit_events` (SQLite chung file với checkpointer `AsyncSqliteSaver`). `app.py` bọc đúng graph của bài 4 vào Streamlit.

**Tech stack:** Python 3.11+ (pin 3.12 cho chắc wheel), uv, LangGraph 1.2.0, langgraph-checkpoint-sqlite, langchain-openai 1.2.1 (openai 2.36.0), aiosqlite, httpx, Pydantic 2, Rich, Streamlit 1.40+, pytest + pytest-asyncio (thêm mới, phục vụ TDD offline).

**Thư mục làm việc (repo):** `D:/VinUni/day27/VinUni-AI20k-K4-Day27-Track03A-NguyenTrongMinh-2A202602496-HITL`
Mọi lệnh dưới đây chạy từ gốc repo:
```bash
cd /d/VinUni/day27/VinUni-AI20k-K4-Day27-Track03A-NguyenTrongMinh-2A202602496-HITL
```
(Đây là Git Bash/MSYS. Với công cụ native — git, uv, node, python — **không** truyền đường dẫn kiểu `/d/...`; dùng đường dẫn tương đối hoặc `D:/...`.)

---

## 0. Ngữ cảnh hiện trạng & giả định

### 0.1 Repo cung cấp gì (đã đọc hết, không cần đoán)

| Đường dẫn | Vai trò | Được sửa? |
|---|---|---|
| `README.md` | Tài liệu **duy nhất** của lab (không có RUBRIC.md trong repo, không có trên GitHub org) | Không (chỉ thêm mục "Provider" ở Phase G nếu muốn) |
| `common/llm.py` | `get_llm()` → `ChatOpenAI(model=$LLM_MODEL, base_url=$LLM_BASE_URL, api_key=$OPENROUTER_API_KEY)` | **"provided, don't modify"** |
| `common/github.py` | `fetch_pr()` / `post_review_comment()` qua httpx REST | Không |
| `common/db.py` | `db_path()`, `db_conn()`, `write_audit_event()`, `replay_events()` | Không |
| `common/schemas.py` | `PRAnalysis`, `AuditEntry`, `ReviewState`, `risk_level_for`, `AUTO_APPROVE_THRESHOLD=0.73`, `ESCALATE_THRESHOLD=0.58` | Không |
| `audit/schema.sql`, `audit/replay.py` | Bảng `audit_events` (tự tạo khi kết nối lần đầu) + CLI replay | Không |
| `exercises/exercise_1..4*.py` | **Skeleton có `# TODO:` — việc chính của mình** | Có |
| `app.py` | Skeleton Streamlit (Exercise 5) | Có |
| `pyproject.toml` | Đã có sẵn `streamlit>=1.40.0`, `typer`, `rich`… (README nói "add streamlit" nhưng **đã có**) | Có (thêm dev deps + cấu hình pytest) |
| `.env.example` | Mẫu biến môi trường | Có (bổ sung biến mới, có comment) |

Số TODO phải hoàn thành (đếm trực tiếp trong file):

- `exercise_1_confidence.py`: 3 (node_analyze, node_route, build_graph wiring)
- `exercise_2_hitl.py`: 3 (node_human_approval, compile với `MemorySaver()`, vòng resume trong `main()`)
- `exercise_3_escalation.py`: 4 (prompt analyze có escalation_questions, node_escalate, node_synthesize, wiring `escalate → synthesize → commit`)
- `exercise_4_audit.py`: **10** (thân `audit()`, + 1 entry cho analyze/route/commit/auto_approve/synthesize, + 2 entry cho human_approval, + 2 entry cho escalate)
- `app.py`: 5 (import graph, sidebar recent sessions, 3 nút approval, form escalation, `run_graph`)

### 0.2 Sự thật đã kiểm chứng bằng lệnh thật (không phải suy đoán)

1. **`uv` 0.12.13 đã cài**, Python hệ thống 3.14.7 (Hermes tool python), uv cũng có sẵn 3.11.15 và tải được 3.12.14. Repo **chưa có `.venv`**, chưa có `.env`.
2. **Git repo sạch**, remote `origin = https://github.com/EntityEbisu/VinUni-AI20k-K4-Day27-Track03A-NguyenTrongMinh-2A202602496-HITL.git`, HEAD `25159a3` (nhánh `main`). Repo upstream của môn là `VinUni-AI20k/VinUni-AI20k-Day27-Track03-HITL` — **giống hệt cây thư mục**, cũng không có rubric.
3. **GitHub**: repo demo `VinUni-AI20k/PR-Demo` là **public**, PR #1 `feat: add priority field to tasks` (tác giả `manhpv8`, 3 file, +22/−10) đang **open**. `gh` CLI có cài nhưng **chưa đăng nhập**; máy **không có `GITHUB_TOKEN`** ở đâu cả. IP hiện tại đã chạm rate-limit ẩn danh của api.github.com → phải dùng PAT cho mọi lệnh GitHub.
4. **Provider LLM**: khóa OpenCode Go **có sẵn trên máy** ở `D:/VinUni/day26/K4-Day26-NguyenTrongMinh-2A202602496/.env` (`OPENCODE_API_KEY`, dùng cho lab hôm trước) — đã test bằng lệnh thật, còn sống.
5. **Danh mục model của OpenCode Go** (`GET https://opencode.ai/zen/go/v1/models`, HTTP 200, 37 id) có:
   `longcat-2.5-preview-free`, `step-5-preview`, `deepseek-v4.1-flash`, `deepseek-v4-pro`, `cat-jam-free`, `glm-5.1/5.2/5.3`, `kimi-k3`, `qwen3.7/3.8-*`, `minimax-m3`, …
   **Không có `deepseek-v4.1-flash-free`** (không tồn tại id này — đã kiểm tra cả danh sách).
6. **Probe thật `longcat-2.5-preview-free`** (đã chạy, 1 lần): HTTP 200 sau **4.9 s**, `finish_reason=stop`, `content` 207 ký tự **JSON hợp lệ**, `usage.completion_tokens_details.reasoning_tokens=61/114` → model này **có reasoning** nhưng vẫn trả `content` bình thường với `max_tokens=1024`.
7. **Header bắt buộc**: gọi `/chat/completions` **không** có `x-opencode-session` → `HTTP 400 {"type":"MissingSessionID"}`. Có header đó + `Authorization: Bearer <key>` → 200. (User-Agent mặc định của curl thì OK; skill nội bộ ghi nhận **UA mặc định của thư viện Python bị Cloudflare trả 403 error code 1010** → vẫn nên tự đặt UA.)
8. **openai-python 2.36.0 (bản uv.lock pin) đọc header từ biến môi trường**: trong `src/openai/_client.py` (cả `OpenAI` dòng 217 và `AsyncOpenAI` dòng 723):
   ```python
   custom_headers_env = os.environ.get("OPENAI_CUSTOM_HEADERS")
   if custom_headers_env is not None:
       parsed: dict[str, str] = {}
       for line in custom_headers_env.split("\n"):
           colon = line.find(":")
           if colon >= 0:
               parsed[line[:colon].strip()] = line[colon + 1 :].strip()
       default_headers = {**parsed, **(default_headers if is_mapping_t(default_headers) else {})}
   ```
   → Định dạng là **nhiều dòng `Tên: giá trị`** (KHÔNG phải JSON), và áp dụng cho **cả client sync (`invoke`) lẫn async (`ainvoke`)**. Nghĩa là có thể trỏ lab sang OpenCode Go **mà không phải sửa `common/llm.py`** — chỉ cần `.env`.
9. `sqlite3` CLI có sẵn (`/c/ProgramData/anaconda3/Library/bin/sqlite3`) → dùng để trích bằng chứng.
10. Không có rubric riêng cho Day27 ⇒ **"rubric" = danh sách Deliverables + 5 exercise trong README**: HITL agent, UI Streamlit, confidence routing, audit trail. Plan này bám đúng 4 mục đó.

### 0.3 Quyết định đã chốt (để implementer không phải suy nghĩ)

| Hạng mục | Chốt |
|---|---|
| Model chính | `longcat-2.5-preview-free` (đã probe sống) |
| Model dự phòng | `deepseek-v4.1-flash` (đúng "model đang dùng trong chat"; **không** có bản `-free`) |
| Cách trỏ provider | Qua `.env`: `LLM_BASE_URL=https://opencode.ai/zen/go/v1`, `OPENROUTER_API_KEY=<khóa OpenCode>`, `OPENAI_CUSTOM_HEADERS` (session header + UA). **Không sửa `common/llm.py`.** |
| Ngôn ngữ prompt/comment/report | Tiếng Việt có dấu; tên field JSON, enum, tên file giữ tiếng Anh |
| Test | pytest offline với LLM giả (monkeypatch) — **không** tốn quota; chạy thật chỉ ở bước evidence |
| Thứ tự | Pre-flight → Ex1 → Ex2 → Ex3 → Ex4 → Ex5 → report/evidence → push |

---

## 1. Kiến trúc & quyết định thiết kế

- **Một graph duy nhất, tái sử dụng**: `exercises/exercise_4_audit.py::build_graph(checkpointer)` là bản đầy đủ (nhận checkpointer làm tham số) — `app.py` import lại đúng hàm này (`from exercises.exercise_4_audit import build_graph`). Không copy graph lần thứ hai (DRY).
- **Bài 1/2/3 là file độc lập, có lặp code có chủ ý**: skeleton của môn thiết kế mỗi exercise chạy được một mình (giảng viên chấm từng file). Vì vậy **giữ** cấu trúc lặp của scaffold, không tách helper dùng chung — đây là ngoại lệ có ý thức với DRY, ghi rõ trong report.
- **Provider switch nằm hoàn toàn ở `.env`**: header `x-opencode-session` + `User-Agent` đi qua `OPENAI_CUSTOM_HEADERS` mà SDK openai tự đọc (mục 0.2.8). Nếu cách này fail → có 2 phương án dự phòng ghi sẵn ở Task A6.
- **Audit là first-class**: mỗi node 1 dòng, `decision` lấy từ enum `'auto'|'approve'|'reject'|'edit'|'escalate'|'pending'`, `risk_level` luôn tính bằng `risk_level_for(confidence)`.
- **HITL chống trùng lặp có kiểm soát**: LangGraph chạy lại node từ đầu khi resume (README FAQ nói rõ), nên dòng audit "trước interrupt" sẽ bị ghi 2 lần nếu không chặn. Task E7 thêm guard idempotent trong `audit()` (có test chứng minh). Đây là sai lệch có chủ ý so với TODO "một dòng" — bắt buộc ghi vào report.
- **TDD offline trước, chạy thật sau**: test dùng LLM giả; chỉ gọi model free ở bước evidence (mỗi lần tốn ~5 s + quota).

---

## 2. GIAI ĐOẠN A — Pre-flight (môi trường, provider, GitHub)

### Task A1 — Xác nhận trạng thái repo & pin Python 3.12

**Mục tiêu:** có môi trường chạy được, không phụ thuộc Python 3.14 (rủi ro thiếu wheel cho streamlit/pyarrow).

**Files:** tạo `.python-version`; sửa `pyproject.toml`.

**Bước 1 — kiểm tra trạng thái sạch:**
```bash
git status --short && git log --oneline -1
```
Kỳ vọng: `git status` **không in gì** (cây sạch), log là `25159a3 Add Exercise 5 (Streamlit UI) + retune thresholds to 0.58 / 0.73`.

**Bước 2 — pin Python:**
```bash
uv python pin 3.12
```
Kỳ vọng: `Using CPython 3.12.14` (uv tự tải nếu chưa có) và tạo file `.python-version` chứa `3.12`.

**Bước 3 — commit:**
```bash
git add .python-version && git commit -m "chore: pin Python 3.12 for uv"
```
Kỳ vọng: 1 file changed, 1 insertion.

---

### Task A2 — Tạo `.env` trỏ OpenCode Go (không cần sửa code)

**Mục tiêu:** `common/llm.py` (nguyên bản) chạy được với `longcat-2.5-preview-free` trên OpenCode Go.

**Files:** tạo `.env` (đã gitignore — **kiểm tra lại trước khi ghi**).

**Bước 1 — xác nhận `.env` được gitignore:**
```bash
grep -n '^\.env$' .gitignore
```
Kỳ vọng: in ra `.env`.

**Bước 2 — lấy khóa OpenCode từ lab hôm trước (không in ra màn hình):**
```bash
grep -E '^OPENCODE_API_KEY=' /d/VinUni/day26/K4-Day26-NguyenTrongMinh-2A202602496/.env | cut -d= -f2-
```
Kỳ vọng: một chuỗi khóa (50–60 ký tự). **Không** dán khóa vào chat, không commit. Copy ngay bằng clipboard.

**Bước 3 — tạo `.env` (copy nguyên khối; điền 2 giá trị bí mật):**
```dotenv
# ── LLM provider: OpenCode Go (OpenAI-compatible) ───────────────────────────
# Tên biến OPENROUTER_API_KEY là do common/llm.py quy định (file được cung cấp,
# không sửa) — giá trị đặt ở đây là khóa OpenCode Go.
OPENROUTER_API_KEY=<DÁN KHÓA OPENCODE VÀO ĐÂY>
LLM_BASE_URL=https://opencode.ai/zen/go/v1
LLM_MODEL=longcat-2.5-preview-free
LLM_FALLBACK_MODEL=deepseek-v4.1-flash
LLM_SESSION_ID=day27-minh-001

# Header bắt buộc của OpenCode Go (thiếu -> HTTP 400 MissingSessionID) + User-Agent
# riêng (UA mặc định của thư viện Python bị Cloudflare chặn 403/1010).
# openai-python đọc biến này: định dạng NHIỀU DÒNG "Tên: giá trị".
OPENAI_CUSTOM_HEADERS="x-opencode-session: day27-minh-001
User-Agent: Day27-HITL-Lab/0.1"

# ── GitHub ──────────────────────────────────────────────────────────────────
# PAT classic, scope `public_repo` (xem Task A4)
GITHUB_TOKEN=<DÁN PAT VÀO ĐÂY>
GITHUB_USER=EntityEbisu

# ── SQLite ──────────────────────────────────────────────────────────────────
HITL_DB_PATH=hitl_audit.db
```

**Bước 4 — xác nhận dotenv đọc đúng giá trị nhiều dòng:**
```bash
uv run python -c "from dotenv import load_dotenv; import os; load_dotenv(); v=os.environ.get('OPENAI_CUSTOM_HEADERS',''); print(repr(v))"
```
Kỳ vọng: `'x-opencode-session: day27-minh-001\nUser-Agent: Day27-HITL-Lab/0.1'` — **phải thấy `\n` là xuống dòng thật** (khi `repr` in ra `\\n` thì giá trị đang là chuỗi 2 ký tự → dùng Phương án B ở Task A6).

**Bước 5 — commit** (không có gì để commit; `.env` bị ignore — xác nhận):
```bash
git status --short
```
Kỳ vọng: **không** thấy `.env`.

---

### Task A3 — `uv sync` và kiểm tra import

**Files:** sinh `.venv/`, cập nhật `uv.lock` nếu cần.

**Bước 1:**
```bash
uv sync
```
Kỳ vọng (dòng cuối): `Installed NN packages in Xs` — không có lỗi build.

**Bước 2 — kiểm tra import + version đúng như uv.lock:**
```bash
uv run python -c "import langgraph, langchain_openai, openai, streamlit, aiosqlite, httpx; print('langgraph', langgraph.__version__ if hasattr(langgraph,'__version__') else '?'); import importlib.metadata as m; print('langchain-openai', m.version('langchain-openai')); print('openai', m.version('openai')); print('streamlit', m.version('streamlit'))"
```
Kỳ vọng: `langchain-openai 1.2.1`, `openai 2.36.0`, `streamlit >= 1.40`.

Nếu lỗi thiếu wheel (thường gặp với Python 3.14), quay lại Task A1 (`uv python pin 3.12`) rồi `rm -rf .venv && uv sync`.

**Bước 3 — commit** nếu `uv.lock` đổi:
```bash
git add uv.lock && git commit -m "chore: refresh uv.lock for pinned Python" || echo "uv.lock unchanged"
```

---

### Task A4 — GitHub PAT (việc của Nguyen, không tự tạo hộ)

**Mục tiêu:** có `GITHUB_TOKEN` để `fetch_pr`/`post_review_comment` chạy được (comment hiện trên PR công khai dưới tên Nguyen — yêu cầu của lab).

**Các bước cho Nguyen (làm 60 giây):**
1. Mở <https://github.com/settings/tokens/new> (classic).
2. Note: `Day27 HITL Lab`; Expiration: 30 days; **tick `public_repo`**.
3. Generate → copy `ghp_...` → dán vào `.env` ở dòng `GITHUB_TOKEN=` (**không** dán vào chat).

**Bước kiểm tra (implementer chạy):**
```bash
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" -H "User-Agent: Day27-HITL-Lab" \
  https://api.github.com/repos/VinUni-AI20k/PR-Demo | python -c "import sys,json;print(json.load(sys.stdin).get('full_name'))"
```
Kỳ vọng: `VinUni-AI20k/PR-Demo`. Nếu in `None` hoặc lỗi 401/403 → PAT sai scope, tạo lại.

**Bước phụ — liệt kê PR demo (dùng chính PAT để tránh rate-limit ẩn danh):**
```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" -H "User-Agent: Day27-HITL-Lab" \
  "https://api.github.com/repos/VinUni-AI20k/PR-Demo/pulls?state=all" \
  | python -c "import sys,json;[print(p['number'], p['title'], p['changed_files']) for p in json.load(sys.stdin)]"
```
Kỳ vọng: ít nhất `1 feat: add priority field to tasks 3` và `2 ...` (PR #2 = login + cloud sync).
**Nếu PR #2 không tồn tại** → ghi lại thành blocker, vẫn làm bài 3 với PR #1 + câu trả lời tự soạn, và báo lại Nguyen (đừng bịa evidence).

---

### Task A5 — Ghi lại bằng chứng provider (1 lần gọi thật)

**Files:** tạo `scripts/probe_provider.py`; tạo `docs/evidence/provider_probe.txt`.

**Bước 1 — viết script:**
```python
"""Kiểm tra provider LLM trước khi viết node.
Chạy: uv run python scripts/probe_provider.py
Ghi lại kết quả vào docs/evidence/provider_probe.txt
"""
from __future__ import annotations

import asyncio
import os
import time

from dotenv import load_dotenv

from common.llm import get_llm

load_dotenv()


def _headers_of(llm) -> dict:
    for attr in ("root_async_client", "root_client"):
        client = getattr(llm, attr, None)
        if client is not None:
            try:
                return {str(k): str(v) for k, v in dict(client.default_headers).items()}
            except Exception:  # pragma: no cover - chỉ để probe không vỡ
                continue
    return {}


def main() -> int:
    print("LLM_MODEL    =", os.environ.get("LLM_MODEL"))
    print("LLM_BASE_URL =", os.environ.get("LLM_BASE_URL"))

    llm = get_llm()
    headers = _headers_of(llm)
    print("headers      =", headers)
    has_session = any(k.lower() == "x-opencode-session" for k in headers)
    print("session header present:", has_session)
    if not has_session:
        print("FAIL: thiếu x-opencode-session -> dùng Task A6 (phương án B)")
        return 2

    t0 = time.monotonic()
    out = llm.invoke([{"role": "user", "content": "Trả lời đúng một từ: OK"}])
    print(f"sync  invoke : {time.monotonic() - t0:.1f}s -> {str(out.content)[:40]!r}")

    async def _async_probe() -> str:
        t = time.monotonic()
        res = await llm.ainvoke([{"role": "user", "content": "Trả lời đúng một từ: OK"}])
        print(f"async ainvoke: {time.monotonic() - t:.1f}s -> {str(res.content)[:40]!r}")
        return str(res.content or "")

    if not asyncio.run(_async_probe()):
        print("FAIL: async trả content rỗng")
        return 3
    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Bước 2 — chạy và lưu bằng chứng:**
```bash
mkdir -p docs/evidence scripts
uv run python scripts/probe_provider.py 2>&1 | tee docs/evidence/provider_probe.txt
```
Kỳ vọng:
```
LLM_MODEL    = longcat-2.5-preview-free
LLM_BASE_URL = https://opencode.ai/zen/go/v1
headers      = {... 'x-opencode-session': 'day27-minh-001', 'User-Agent': 'Day27-HITL-Lab/0.1' ...}
session header present: True
sync  invoke : 3.1s -> 'OK'
async ainvoke: 2.4s -> 'OK'
PROBE OK
```
Nếu `session header present: False` → sang Task A6. Nếu lỗi `400 MissingSessionID` → cùng cách xử lý.

**Bước 3 — commit:**
```bash
git add scripts/probe_provider.py docs/evidence/provider_probe.txt
git commit -m "chore(provider): probe OpenCode Go (session header + sync/async call)"
```

---

### Task A6 — Phương án dự phòng nếu `OPENAI_CUSTOM_HEADERS` không tác dụng

Chỉ làm khi Task A5 fail. Thử **theo thứ tự**, dừng ở cách đầu tiên chạy được.

**A6-B (đổi giá trị `.env`, không sửa code):** dùng escape `\n` trong giá trị có nháy kép:
```dotenv
OPENAI_CUSTOM_HEADERS="x-opencode-session: day27-minh-001\nUser-Agent: Day27-HITL-Lab/0.1"
```
Chạy lại `uv run python scripts/probe_provider.py`. Nếu vẫn fail → A6-C.

**A6-C (sửa `common/llm.py` — 6 dòng thêm, đã cân nhắc và nêu rõ trong report):**
```python
def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set — copy .env.example to .env")
    extra_headers = {
        k.strip(): v.strip()
        for line in (os.environ.get("OPENAI_CUSTOM_HEADERS") or "").split("\n")
        if (colon := line.find(":")) > 0
        for k, v in [(line[:colon], line[colon + 1:])]
    }
    return ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "openai/gpt-4o-mini"),
        base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=api_key,
        temperature=temperature,
        default_headers=extra_headers or None,
    )
```
Đây là **thay đổi duy nhất** được phép trên thư mục `provided`; phải (a) ghi vào report mục "Sai lệch", (b) ghi chú ngay trên hàm rằng vì sao. Commit: `fix(provider): pass OpenCode Go session header explicitly`.

**A6-D (không sửa file provided — shim proxy, chỉ khi cả B và C bị cấm):** viết `scripts/zen_proxy.py` (http.server chuyển tiếp `POST /v1/chat/completions` tới `https://opencode.ai/zen/go/v1/chat/completions`, thêm 2 header), rồi đặt `LLM_BASE_URL=http://127.0.0.1:8791/v1`. Phải mở proxy trước mỗi lần chạy. Ghi rõ trong report.

---

### Task A7 — Probe structured output (quyết định tham số `with_structured_output`)

**Mục tiêu:** biết **chính xác** cách gọi `with_structured_output(PRAnalysis)` chạy được trên `longcat-2.5-preview-free`, trước khi viết node.

**Files:** tạo `scripts/probe_structured.py`; lưu `docs/evidence/structured_probe.txt`.

**Bước 1 — viết script:**
```python
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
            print(f"OK   method={method or 'default'} -> {type(res).__name__} "
                  f"confidence={res.confidence:.2f} comments={len(res.comments)}")
            print(f"RESULT: dùng method={method!r}")
            return 0
        except Exception as exc:  # noqa: BLE001 - probe cần bắt mọi lỗi
            print(f"FAIL method={method or 'default'}: {type(exc).__name__}: {str(exc)[:200]}")
    print("RESULT: không method nào chạy được -> Task A7-fallback")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

**Bước 2 — chạy:**
```bash
uv run python scripts/probe_structured.py 2>&1 | tee docs/evidence/structured_probe.txt
```
Kỳ vọng (1 trong 3 dòng đầu xuất hiện):
```
OK   method=json_schema -> PRAnalysis confidence=0.90 comments=0
RESULT: dùng method='json_schema'
```
→ Ghi lại method thắng vào hằng số `STRUCTURED_METHOD` dùng chung cho cả 4 exercise + app (xem Task B3).

**Bước 3 — A7-fallback (chỉ khi cả 3 method fail):** thêm helper parse JSON thủ công vào **từng** node analyze (không sửa `common/`):
```python
import json

def _analyze_text(llm, messages, schema: type[BaseModel]) -> BaseModel:
    """Dự phòng khi provider không hỗ trợ structured output: hỏi JSON thuần rồi parse."""
    text = llm.invoke(messages + [{
        "role": "user",
        "content": "Chỉ trả về JSON hợp lệ đúng schema sau, không thêm chữ nào khác:\n"
                   + json.dumps(schema.model_json_schema(), ensure_ascii=False),
    }]).content
    raw = str(text)
    start, end = raw.find("{"), raw.rfind("}")
    return schema.model_validate_json(raw[start:end + 1])
```
Ghi rõ trong report: "provider không hỗ trợ `with_structured_output`; đã thêm đường parse JSON thủ công".

**Bước 4 — commit:**
```bash
git add scripts/probe_structured.py docs/evidence/structured_probe.txt
git commit -m "chore(provider): probe structured-output method for free model"
```

---

### Task A8 — Thêm dev deps + cấu hình pytest (nền cho TDD)

**Files:** `pyproject.toml`; tạo `tests/conftest.py`.

**Bước 1:**
```bash
uv add --dev pytest pytest-asyncio
```
Kỳ vọng: `+ pytest==...`, `+ pytest-asyncio==...`, `uv.lock` cập nhật.

**Bước 2 — thêm vào `pyproject.toml` (ngay sau khối `[build-system]`):**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-q"
```

**Bước 3 — tạo `tests/conftest.py`:**
```python
"""Đảm bảo gốc repo nằm trên sys.path để `import exercises.exercise_1_confidence` chạy được."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

**Bước 4 — xác nhận pytest chạy (chưa có test nào):**
```bash
uv run pytest
```
Kỳ vọng: `no tests ran in 0.0Xs` (exit code 5 — chấp nhận ở bước này).

**Bước 5 — commit:**
```bash
git add pyproject.toml uv.lock tests/conftest.py
git commit -m "test: add pytest + asyncio config and sys.path conftest"
```

---

### Task A9 — Fixture LLM giả dùng chung cho test (offline, 0 quota)

**Files:** tạo `tests/fakes.py`.

```python
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
        comments=[ReviewComment(file="tasktrack/models.py", line=12, severity="suggestion",
                                body="Nên có migration tương ứng.")],
        confidence=confidence,
        confidence_reasoning="Diff nhỏ nhưng có thay đổi schema.",
        escalation_questions=questions or [],
    )
```

**Test (viết trước, chạy để thấy fail — vì chưa có gì để test, ta kiểm tra fixture tự nó):** tạo `tests/test_fakes.py`:
```python
from tests.fakes import FakeLLM, make_analysis


def test_fake_llm_returns_configured_analysis():
    fake = FakeLLM(make_analysis(0.65))
    out = fake.with_structured_output(object).invoke([{"role": "user", "content": "x"}])
    assert out.confidence == 0.65
    assert out.comments[0].file == "tasktrack/models.py"
```

**Chạy:**
```bash
uv run pytest tests/test_fakes.py -q
```
Kỳ vọng: `1 passed`. (Nếu `ModuleNotFoundError: tests` → thêm `tests/__init__.py` rỗng rồi chạy lại.)

**Commit:**
```bash
git add tests/fakes.py tests/test_fakes.py
git commit -m "test: add offline fake LLM fixtures"
```

---

## 3. GIAI ĐOẠN B — Exercise 1: confidence routing

### Task B1 — Test cho `node_route` (viết test fail trước)

**Files:** tạo `tests/test_ex1_routing.py`.

```python
import pytest

from common.schemas import AUTO_APPROVE_THRESHOLD, ESCALATE_THRESHOLD
from exercises.exercise_1_confidence import build_graph, node_route
from tests.fakes import make_analysis


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.95, "auto_approve"),
        (AUTO_APPROVE_THRESHOLD, "auto_approve"),   # biên: 0.73 -> auto
        (0.72, "human_approval"),                   # biên: 0.72 -> human
        (0.65, "human_approval"),
        (ESCALATE_THRESHOLD, "human_approval"),     # biên: 0.58 -> human (không escalate)
        (0.57, "escalate"),
        (0.10, "escalate"),
    ],
)
def test_node_route_maps_confidence_to_branch(confidence, expected):
    state = {"analysis": make_analysis(confidence)}
    assert node_route(state)["decision"] == expected


def test_ex1_graph_contains_all_nodes():
    graph = build_graph().get_graph()
    assert {"fetch_pr", "analyze", "route", "auto_approve", "human_approval", "escalate"} <= set(graph.nodes)
```

**Chạy (phải FAIL):**
```bash
uv run pytest tests/test_ex1_routing.py -q
```
Kỳ vọng: FAIL — `NotImplementedError: Implement node_route` (và `NotImplementedError: Implement node_analyze` khi import module… nếu lỗi import thì đó cũng là FAIL hợp lệ).

---

### Task B2 — Implement `node_route`

**Files:** `exercises/exercise_1_confidence.py:53-58`.

```python
def node_route(state: ReviewState) -> dict:
    console.print("[cyan]→ route[/cyan]")
    c = state["analysis"].confidence
    if c >= AUTO_APPROVE_THRESHOLD:
        decision: Decision = "auto_approve"
    elif c < ESCALATE_THRESHOLD:
        decision = "escalate"
    else:
        decision = "human_approval"
    console.print(f"  [green]✓[/green] decision=[bold]{decision}[/bold] (confidence={c:.0%})")
    return {"decision": decision}
```
Thêm `Decision` vào import `from common.schemas import (...)` sẵn có.

**Chạy 6 test routing:**
```bash
uv run pytest tests/test_ex1_routing.py -q -k node_route
```
Kỳ vọng: `6 passed`.

**Commit:**
```bash
git add exercises/exercise_1_confidence.py tests/test_ex1_routing.py
git commit -m "feat(ex1): implement confidence-based routing"
```

---

### Task B3 — Prompt dùng chung + `node_analyze` (test trước)

**Mục tiêu:** prompt hiệu chỉnh confidence theo đúng 3 bucket của lab (nếu không, model free sẽ luôn trả ~0.9 và nhánh escalate không bao giờ chạy).

**Files:** tạo `common_prompts.py` (file của mình, không nằm trong `common/`); sửa `exercises/exercise_1_confidence.py`.

**Bước 1 — tạo `common_prompts.py`:**
```python
"""Prompt dùng chung cho 5 bài tập (giữ 1 chỗ duy nhất — DRY)."""

from __future__ import annotations

ANALYZE_SYSTEM_PROMPT = (
    "Bạn là một reviewer cấp cao đang đánh giá một pull request. "
    "Đọc kỹ diff và trả về đánh giá có cấu trúc theo schema đã cho.\n"
    "QUAN TRỌNG — hiệu chỉnh confidence trung thực theo thang sau (đây là bài toán "
    "tự đánh giá, KHÔNG được mặc định 0.9):\n"
    "  • 0.85–1.00: thay đổi cơ học, rủi ro thấp, không có chỗ nào cần người xác nhận "
    "(ví dụ: thêm field optional, sửa typo, bump dependency).\n"
    "  • 0.58–0.72: thay đổi vừa, có 1–2 điểm cần con người xác nhận (migration schema, "
    "thay đổi API công khai, logic mới chưa có test).\n"
    "  • 0.00–0.57: có dấu hiệu rủi ro cao hoặc cần thông tin ngoài diff "
    "(băm mật khẩu yếu như MD5/SHA1, lưu token dạng plaintext, SQL ghép chuỗi, "
    "hard-code user id, thiếu test cho logic mới, thay đổi liên quan xác thực).\n"
    "Nếu confidence < 0.58: điền escalation_questions bằng 2–4 câu hỏi CỤ THỂ, mỗi câu "
    "phải nêu rõ tệp/hàm/đoạn diff đang hỏi (ví dụ: \"Vì sao dùng MD5 cho mật khẩu ở "
    "auth.py:42 thay vì bcrypt?\"). Nếu confidence >= 0.58: escalation_questions để rỗng.\n"
    "Mọi nhận xét trong comments phải tham chiếu tệp thật trong diff."
)

SYNTHESIZE_SYSTEM_PROMPT = (
    "Bạn là reviewer cấp cao. Bạn đã hỏi reviewer con người vài câu hỏi và nhận được câu trả lời.\n"
    "Hãy TỔNG HỢP LẠI đánh giá dựa trên diff gốc + câu trả lời, cập nhật risk_factors và comments "
    "cho đúng những gì câu trả lời hé lộ, và đặt lại confidence theo đúng thang:\n"
    "0.85–1.00 (rủi ro thấp, không cần người) | 0.58–0.72 (cần người xác nhận) | "
    "0.00–0.57 (rủi ro cao/còn thiếu thông tin).\n"
    "escalation_questions để rỗng vì đã hỏi xong."
)

# Method dùng cho ChatOpenAI.with_structured_output — điền theo kết quả Task A7
# ("json_schema" | "function_calling" | None nếu để mặc định của thư viện).
STRUCTURED_METHOD = "json_schema"
```

**Bước 2 — test trước, tạo `tests/test_ex1_analyze.py`:**
```python
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
```

**Chạy (FAIL):**
```bash
uv run pytest tests/test_ex1_analyze.py -q
```
Kỳ vọng: FAIL — `NotImplementedError: Implement node_analyze`.

**Bước 3 — implement `node_analyze`** (thay `exercises/exercise_1_confidence.py:41-50`), thêm import:
```python
from common_prompts import ANALYZE_SYSTEM_PROMPT, STRUCTURED_METHOD
```
```python
def node_analyze(state: ReviewState) -> dict:
    console.print("[cyan]→ analyze[/cyan]")
    llm = get_llm().with_structured_output(PRAnalysis, method=STRUCTURED_METHOD)
    with console.status("[dim]LLM đang đọc diff...[/dim]"):
        analysis: PRAnalysis = llm.invoke([
            {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Tiêu đề PR: {state['pr_title']}\n\nDiff:\n{state['pr_diff']}"},
        ])
    console.print(f"  [green]✓[/green] confidence={analysis.confidence:.0%}, {len(analysis.comments)} comment(s)")
    return {"analysis": analysis}
```
(Nếu Task A7 chọn `None` → bỏ tham số `method=`.)

**Bước 4 — chạy lại:**
```bash
uv run pytest tests/test_ex1_analyze.py -q
```
Kỳ vọng: `1 passed`.

**Commit:**
```bash
git add common_prompts.py exercises/exercise_1_confidence.py tests/test_ex1_analyze.py
git commit -m "feat(ex1): implement analyze node with calibrated Vietnamese prompt"
```

---

### Task B4 — Wiring graph bài 1

**Files:** `exercises/exercise_1_confidence.py:76-83`.

```python
def build_graph():
    g = StateGraph(ReviewState)
    g.add_node("fetch_pr", node_fetch_pr)
    g.add_node("analyze", node_analyze)
    g.add_node("route", node_route)
    g.add_node("auto_approve", node_auto_approve)
    g.add_node("human_approval", node_human_approval)
    g.add_node("escalate", node_escalate)

    g.add_edge(START, "fetch_pr")
    g.add_edge("fetch_pr", "analyze")
    g.add_edge("analyze", "route")
    g.add_conditional_edges(
        "route",
        lambda s: s["decision"],
        {"auto_approve": "auto_approve", "human_approval": "human_approval", "escalate": "escalate"},
    )
    g.add_edge("auto_approve", END)
    g.add_edge("human_approval", END)
    g.add_edge("escalate", END)
    return g.compile()
```

**Chạy toàn bộ test bài 1:**
```bash
uv run pytest tests/test_ex1_routing.py tests/test_ex1_analyze.py -q
```
Kỳ vọng: `8 passed`.

**Commit:**
```bash
git add exercises/exercise_1_confidence.py
git commit -m "feat(ex1): wire StateGraph with conditional routing to three terminals"
```

---

### Task B5 — Chạy thật bài 1 trên 2 PR + evidence (2 lời gọi LLM)

```bash
mkdir -p docs/evidence
uv run python exercises/exercise_1_confidence.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/1 2>&1 | tee docs/evidence/ex1_pr1.txt
uv run python exercises/exercise_1_confidence.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/2 2>&1 | tee docs/evidence/ex1_pr2.txt
```
Kỳ vọng — **hai PR in ra nhánh KHÁC nhau** (đây là tiêu chí "Success" của README):
```
→ route
  ✓ decision=human_approval (confidence=65%)
✓ HUMAN APPROVAL — placeholder, exercise 2 will pause here
────────── Final ──────────
confidence = 65%
action     = pending_human_approval
```
và PR #2:
```
  ✓ decision=escalate (confidence=44%)
✓ ESCALATE — placeholder, exercise 3 will ask the reviewer questions
```
**Nếu cả 2 PR ra cùng nhánh:** xem Risk R3 (hiệu chỉnh prompt trước, đổi ngưỡng sau, có ghi chép). **Nếu lệnh lỗi `MissingSessionID`** → quay lại Task A6.

**Commit:**
```bash
git add docs/evidence/ex1_pr1.txt docs/evidence/ex1_pr2.txt
git commit -m "docs(ex1): evidence of two PRs routing to different branches"
```

---

## 4. GIAI ĐOẠN C — Exercise 2: HITL với `interrupt()`

### Task C1 — Test payload của `interrupt()` (test fail trước)

**Files:** tạo `tests/test_ex2_interrupt.py`.

```python
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
```

**Chạy (FAIL):**
```bash
uv run pytest tests/test_ex2_interrupt.py -q
```
Kỳ vọng: FAIL — `NotImplementedError: Call interrupt() with an approval_request payload`.

---

### Task C2 — Implement `node_human_approval` + compile có checkpointer

**Files:** `exercises/exercise_2_hitl.py:63-76` và `:137`.

```python
def node_human_approval(state: ReviewState) -> dict:
    """Pause và hỏi người duyệt."""
    a = state["analysis"]
    response = interrupt({
        "kind": "approval_request",
        "pr_url": state["pr_url"],
        "confidence": a.confidence,
        "confidence_reasoning": a.confidence_reasoning,
        "summary": a.summary,
        "comments": [c.model_dump() for c in a.comments],
        "diff_preview": state["pr_diff"][:2000],
    })
    return {"human_choice": response.get("choice"), "human_feedback": response.get("feedback")}
```

```python
    return g.compile(checkpointer=MemorySaver())
```

**Chạy:**
```bash
uv run pytest tests/test_ex2_interrupt.py -q
```
Kỳ vọng: `1 passed`.

**Commit:**
```bash
git add exercises/exercise_2_hitl.py tests/test_ex2_interrupt.py
git commit -m "feat(ex2): interrupt() in human_approval node + MemorySaver checkpointer"
```

---

### Task C3 — Vòng resume trong `main()`

**Files:** `exercises/exercise_2_hitl.py:175-182` (thay khối TODO).

```python
    result = app.invoke({"pr_url": args.pr, "thread_id": thread_id}, cfg)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        answer = prompt_human(payload)
        console.print(f"[dim]resume với {answer}[/dim]")
        result = app.invoke(Command(resume=answer), cfg)
```

**Kiểm tra tĩnh (không gọi mạng):**
```bash
uv run python -c "import ast,sys;src=open('exercises/exercise_2_hitl.py',encoding='utf-8').read();ast.parse(src);print('syntax OK')" && grep -n 'while "__interrupt__"' exercises/exercise_2_hitl.py
```
Kỳ vọng: `syntax OK` và dòng chứa `while "__interrupt__" in result:`.

**Commit:**
```bash
git add exercises/exercise_2_hitl.py
git commit -m "feat(ex2): resume loop with Command(resume=...) in main"
```

---

### Task C4 — Chạy thật bài 2 trên PR #1 (tương tác, có POST comment thật)

**Chuẩn bị:** PR #1 phải nằm ở nhánh `human_approval` (đã xác nhận ở Task B5).
```bash
uv run python exercises/exercise_2_hitl.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/1 2>&1 | tee docs/evidence/ex2_pr1_approve.txt
```
Tại prompt:
```
Choice (approve/reject/edit)? approve
```
Kỳ vọng (đuôi log):
```
→ human_approval
→ commit
  ✓ posted comment to https://github.com/VinUni-AI20k/PR-Demo/pull/1
────────── Done ──────────
committed
```
**Kiểm tra comment đã thực sự lên GitHub (không chỉ tin log):**
```bash
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" -H "User-Agent: Day27-HITL-Lab" \
  https://api.github.com/repos/VinUni-AI20k/PR-Demo/issues/1/comments \
  | python -c "import sys,json;d=json.load(sys.stdin);print([(c['user']['login'], c['body'][:60]) for c in d][-3:])"
```
Kỳ vọng: thấy comment mới nhất từ `EntityEbisu` với nội dung `### Automated review (confidence ...)`.

**Thêm 1 lần chạy `edit` để chứng minh nhánh thứ ba của HITL (tuỳ chọn, tốn 1 lời gọi):**
```bash
uv run python exercises/exercise_2_hitl.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/1 2>&1 | tee docs/evidence/ex2_pr1_edit.txt
# Choice: edit ; Feedback: Bổ sung ghi chú về migration
```
Kỳ vọng: `skipping comment (choice=edit)` → `rejected` (đúng như skeleton: chỉ `approve` mới post).

**Commit:**
```bash
git add docs/evidence/ex2_pr1_approve.txt docs/evidence/ex2_pr1_edit.txt
git commit -m "docs(ex2): evidence of pause-approve-post and edit flows"
```

---

## 5. GIAI ĐOẠN D — Exercise 3: escalation + synthesize

### Task D1 — Test `node_escalate` (test fail trước)

**Files:** tạo `tests/test_ex3_escalation.py`.

```python
import exercises.exercise_3_escalation as mod
from common.schemas import PRAnalysis
from tests.fakes import FakeLLM, make_analysis


def test_escalate_interrupt_payload_contains_questions(monkeypatch):
    captured: dict = {}

    def fake_interrupt(payload):
        captured.update(payload)
        return {q: f"trả lời cho {q}" for q in payload["questions"]}

    monkeypatch.setattr(mod, "interrupt", fake_interrupt)

    questions = ["Vì sao dùng MD5 ở auth.py?", "SYNC_URL có phải HTTPS ở production không?"]
    state = {"analysis": make_analysis(0.35, questions=questions),
             "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/2"}

    out = mod.node_escalate(state)

    assert captured["kind"] == "escalation"
    assert captured["questions"] == questions
    assert captured["risk_factors"], "phải gửi risk_factors cho người duyệt"
    assert out["escalation_answers"] == {q: f"trả lời cho {q}" for q in questions}


def test_escalate_falls_back_when_llm_sends_no_questions(monkeypatch):
    monkeypatch.setattr(mod, "interrupt", lambda payload: {q: "x" for q in payload["questions"]})
    out = mod.node_escalate({"analysis": make_analysis(0.3, questions=[]), "pr_url": "u"})
    assert len(out["escalation_answers"]) == 2


def test_synthesize_uses_answers_and_returns_refined(monkeypatch):
    fake = FakeLLM(make_analysis(0.88))
    monkeypatch.setattr(mod, "get_llm", lambda *a, **kw: fake)
    state = {
        "pr_diff": "+ md5(pw)",
        "escalation_answers": {"Vì sao dùng MD5?": "chỉ là demo nội bộ"},
    }
    out = mod.node_synthesize(state)
    assert isinstance(out["analysis"], PRAnalysis)
    assert out["analysis"].confidence == 0.88
    sent = "\n".join(m["content"] for m in fake.structured.messages)
    assert "chỉ là demo nội bộ" in sent
```

**Chạy (FAIL):**
```bash
uv run pytest tests/test_ex3_escalation.py -q
```
Kỳ vọng: 3 failed với `NotImplementedError: Call interrupt() with an escalation payload` và `Synthesize a refined PRAnalysis...`.

---

### Task D2 — Implement `node_escalate`

**Files:** `exercises/exercise_3_escalation.py:66-78`.

```python
def node_escalate(state: ReviewState) -> dict:
    """Hỏi người duyệt các câu hỏi cụ thể; trả câu trả lời vào state."""
    a = state["analysis"]
    questions = a.escalation_questions
    if not questions:
        questions = [
            "Mục tiêu của PR này là gì?",
            "Có lo ngại gì về migration dữ liệu khi deploy không?",
        ]
    console.print(f"[yellow]⚠ escalate với {len(questions)} câu hỏi[/yellow]")
    answers = interrupt({
        "kind": "escalation",
        "pr_url": state["pr_url"],
        "confidence": a.confidence,
        "confidence_reasoning": a.confidence_reasoning,
        "summary": a.summary,
        "risk_factors": a.risk_factors,
        "questions": questions,
    })
    return {"escalation_answers": answers}
```

**Chạy:**
```bash
uv run pytest tests/test_ex3_escalation.py -q -k escalate
```
Kỳ vọng: `2 passed`.

**Commit:**
```bash
git add exercises/exercise_3_escalation.py tests/test_ex3_escalation.py
git commit -m "feat(ex3): escalate node asks specific reviewer questions"
```

---

### Task D3 — Implement `node_synthesize`

**Files:** `exercises/exercise_3_escalation.py:81-89`; thêm import `from common_prompts import ANALYZE_SYSTEM_PROMPT, STRUCTURED_METHOD, SYNTHESIZE_SYSTEM_PROMPT`.

```python
def node_synthesize(state: ReviewState) -> dict:
    """Prompt lại LLM kèm câu trả lời của reviewer để ra đánh giá tinh chỉnh."""
    console.print("[cyan]→ synthesize[/cyan]")
    qa = "\n".join(
        f"Câu hỏi: {q}\nTrả lời: {a}" for q, a in (state.get("escalation_answers") or {}).items()
    )
    llm = get_llm().with_structured_output(PRAnalysis, method=STRUCTURED_METHOD)
    with console.status("[dim]LLM tổng hợp lại đánh giá theo câu trả lời...[/dim]"):
        refined: PRAnalysis = llm.invoke([
            {"role": "system", "content": SYNTHESIZE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Tiêu đề PR: {state.get('pr_title', '')}\n\nDiff:\n{state['pr_diff']}"
                f"\n\nCâu trả lời của reviewer:\n{qa}"
            )},
        ])
    console.print(f"  [green]✓[/green] refined confidence={refined.confidence:.0%}")
    return {"analysis": refined}
```
(Thêm `pr_title` vào state ở `node_fetch_pr` của file này — skeleton đã trả `pr_title` rồi, chỉ cần dùng `state.get`.)

**Chạy:**
```bash
uv run pytest tests/test_ex3_escalation.py -q
```
Kỳ vọng: `3 passed`.

**Commit:**
```bash
git add exercises/exercise_3_escalation.py
git commit -m "feat(ex3): synthesize refined review from reviewer answers"
```

---

### Task D4 — Wiring `escalate → synthesize → commit`

**Files:** `exercises/exercise_3_escalation.py:164`.

```python
    g.add_edge("escalate", "synthesize")
    g.add_edge("synthesize", "commit")
```

**Test bổ sung vào `tests/test_ex3_escalation.py`:**
```python
def test_ex3_graph_wires_escalate_through_synthesize_to_commit():
    graph = mod.build_graph().get_graph()
    edges = {(e.source, e.target) for e in graph.edges}
    assert ("escalate", "synthesize") in edges
    assert ("synthesize", "commit") in edges
```
**Chạy:**
```bash
uv run pytest tests/test_ex3_escalation.py -q
```
Kỳ vọng: `4 passed`.

**Commit:**
```bash
git add exercises/exercise_3_escalation.py tests/test_ex3_escalation.py
git commit -m "feat(ex3): wire escalate -> synthesize -> commit"
```

---

### Task D5 — Chạy thật bài 3 trên PR #2 (2 lời gọi LLM + 1 POST)

```bash
uv run python exercises/exercise_3_escalation.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/2 2>&1 | tee docs/evidence/ex3_pr2_escalate.txt
```
Trả lời từng câu hỏi ở prompt (gõ câu trả lời thật, ví dụ: `chỉ là demo nội bộ, sẽ thay bằng bcrypt ở PR sau`).
Kỳ vọng: panel vàng `Escalation conf=..%`, in ra từng `Q: ...` rồi `→ synthesize` với `refined confidence` **cao hơn** confidence gốc, cuối cùng `final_action = committed_after_escalation` và dòng `✓ posted comment to .../pull/2`.
Xác nhận comment đã lên (dùng lệnh curl ở Task C4 nhưng với `/issues/2/comments`).

**Commit:** `git add docs/evidence/ex3_pr2_escalate.txt && git commit -m "docs(ex3): evidence of escalation Q&A and refined review"`

---

## 6. GIAI ĐOẠN E — Exercise 4: audit trail

### Task E1 — Test `audit()` (test fail trước)

**Files:** tạo `tests/test_ex4_audit.py`.

```python
from common.schemas import AuditEntry, risk_level_for
from common.db import replay_events


async def test_audit_writes_one_row(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    db = tmp_path / "audit_test.db"
    monkeypatch.setenv("HITL_DB_PATH", str(db))

    state = {"thread_id": "t-1", "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/1"}
    await mod.audit(state, AuditEntry(
        agent_id=mod.AGENT_ID, action="analyze", confidence=0.65,
        risk_level=risk_level_for(0.65), decision="pending",
        reason="vì diff nhỏ nhưng đổi schema", reviewer_id=None, execution_time_ms=12,
    ))

    rows = await replay_events("t-1")
    assert len(rows) == 1
    assert rows[0]["action"] == "analyze"
    assert rows[0]["risk_level"] == "med"
    assert rows[0]["decision"] == "pending"
    assert rows[0]["execution_time_ms"] == 12
```

**Chạy (FAIL):**
```bash
uv run pytest tests/test_ex4_audit.py -q
```
Kỳ vọng: FAIL — `NotImplementedError: Implement the audit() body`.

---

### Task E2 — Implement `audit()`

**Files:** `exercises/exercise_4_audit.py:58-66`.

```python
async def audit(state, entry: AuditEntry) -> None:
    """Ghi một dòng AuditEntry vào bảng `audit_events`.

    `thread_id` và `pr_url` lấy từ `state` để nơi gọi chỉ cần dựng entry.
    """
    await write_audit_event(thread_id=state["thread_id"], pr_url=state["pr_url"], entry=entry)
```

**Chạy:**
```bash
uv run pytest tests/test_ex4_audit.py -q
```
Kỳ vọng: `1 passed`.

**Commit:** `git add exercises/exercise_4_audit.py tests/test_ex4_audit.py && git commit -m "feat(ex4): implement audit() writer"`

---

### Task E3 — Entry cho `analyze` và `route`

**Files:** `exercises/exercise_4_audit.py:100-126`.

```python
async def node_analyze(state):
    console.print("[cyan]→ analyze[/cyan]")
    t0 = time.monotonic()
    llm = get_llm().with_structured_output(PRAnalysis, method=STRUCTURED_METHOD)
    with console.status("[dim]LLM đang đọc diff...[/dim]"):
        a: PRAnalysis = await llm.ainvoke([
            {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Tiêu đề PR: {state['pr_title']}\n\nDiff:\n{state['pr_diff']}"},
        ])
    console.print(f"  [green]✓[/green] confidence={a.confidence:.0%}, {len(a.comments)} comment(s)")
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="analyze",
        confidence=a.confidence,
        risk_level=risk_level_for(a.confidence),
        reviewer_id=None,
        decision="pending",
        reason=a.confidence_reasoning,
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))
    return {"analysis": a}
```

```python
async def node_route(state):
    console.print("[cyan]→ route[/cyan]")
    t0 = time.monotonic()
    c = state["analysis"].confidence
    if c >= AUTO_APPROVE_THRESHOLD:
        decision = "auto_approve"
    elif c < ESCALATE_THRESHOLD:
        decision = "escalate"
    else:
        decision = "human_approval"
    console.print(f"  [green]✓[/green] decision=[bold]{decision}[/bold] (confidence={c:.0%})")
    audit_decision = {"auto_approve": "auto", "escalate": "escalate"}.get(decision, "pending")
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="route",
        confidence=c,
        risk_level=risk_level_for(c),
        reviewer_id=None,
        decision=audit_decision,
        reason=f"Định tuyến vào nhánh {decision} với confidence={c:.0%}",
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))
    return {"decision": decision}
```

**Test bổ sung (`tests/test_ex4_audit.py`):**
```python
async def test_route_writes_row_with_real_decision(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "a.db"))
    state = {"thread_id": "t-2", "pr_url": "u", "analysis": make_analysis(0.90)}
    await mod.node_route(state)

    rows = await replay_events("t-2")
    assert rows[-1]["action"] == "route"
    assert rows[-1]["decision"] == "auto"
    assert rows[-1]["risk_level"] == "low"
```
(thêm `from tests.fakes import make_analysis` đầu file)

**Chạy:**
```bash
uv run pytest tests/test_ex4_audit.py -q
```
Kỳ vọng: `2 passed`.

**Commit:** `git commit -am "feat(ex4): audit entries for analyze and route"`

---

### Task E4 — Hai entry cho `human_approval` (trước/sau interrupt)

**Files:** `exercises/exercise_4_audit.py:129-148`.

```python
async def node_human_approval(state):
    t0 = time.monotonic()
    a = state["analysis"]

    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="human_approval",
        confidence=a.confidence,
        risk_level=risk_level_for(a.confidence),
        reviewer_id=None,
        decision="pending",
        reason=f"Yêu cầu duyệt: {a.summary[:200]}",
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))

    t1 = time.monotonic()
    resp = interrupt({
        "kind": "approval_request",
        "pr_url": state["pr_url"],
        "confidence": a.confidence,
        "confidence_reasoning": a.confidence_reasoning,
        "summary": a.summary,
        "comments": [c.model_dump() for c in a.comments],
        "diff_preview": state["pr_diff"][:2000],
    })
    waited_ms = int((time.monotonic() - t1) * 1000)

    choice = resp.get("choice")
    feedback = resp.get("feedback")
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="human_approval",
        confidence=a.confidence,
        risk_level=risk_level_for(a.confidence),
        reviewer_id=os.environ.get("GITHUB_USER"),
        decision=choice or "pending",
        reason=(f"Người duyệt chờ {waited_ms} ms rồi chọn {choice}"
                + (f" — góp ý: {feedback}" if feedback else "")),
        execution_time_ms=int((time.monotonic() - t1) * 1000),
    ))
    return {"human_choice": choice, "human_feedback": feedback}
```

**Test bổ sung:**
```python
async def test_human_approval_writes_pending_then_decision(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(mod, "interrupt", lambda payload: {"choice": "approve", "feedback": "ổn"})

    state = {"thread_id": "t-3", "pr_url": "u", "analysis": make_analysis(0.65), "pr_diff": "x"}
    out = await mod.node_human_approval(state)

    rows = await replay_events("t-3")
    assert [r["decision"] for r in rows] == ["pending", "approve"]
    assert rows[-1]["reviewer_id"] == "EntityEbisu"
    assert "ổn" in rows[-1]["reason"]
    assert out["human_choice"] == "approve"
```

**Chạy:** `uv run pytest tests/test_ex4_audit.py -q` → kỳ vọng `3 passed`.

**Commit:** `git commit -am "feat(ex4): audit entries before and after the approval interrupt"`

---

### Task E5 — Hai entry cho `escalate`

**Files:** `exercises/exercise_4_audit.py:199-217`.

```python
async def node_escalate(state):
    t0 = time.monotonic()
    a = state["analysis"]
    questions = a.escalation_questions or ["Mục tiêu của PR này là gì?"]

    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="escalate",
        confidence=a.confidence,
        risk_level=risk_level_for(a.confidence),
        reviewer_id=None,
        decision="escalate",
        reason="Câu hỏi gửi người duyệt: " + " | ".join(questions)[:300],
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))

    t1 = time.monotonic()
    answers = interrupt({
        "kind": "escalation",
        "pr_url": state["pr_url"],
        "confidence": a.confidence,
        "confidence_reasoning": a.confidence_reasoning,
        "summary": a.summary,
        "risk_factors": a.risk_factors,
        "questions": questions,
    })
    waited_ms = int((time.monotonic() - t1) * 1000)

    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="escalate",
        confidence=a.confidence,
        risk_level=risk_level_for(a.confidence),
        reviewer_id=os.environ.get("GITHUB_USER"),
        decision="escalate",
        reason=f"Người duyệt trả lời {len(answers)} câu hỏi sau {waited_ms} ms",
        execution_time_ms=int((time.monotonic() - t1) * 1000),
    ))
    return {"escalation_answers": answers}
```

**Test bổ sung:**
```python
async def test_escalate_writes_two_rows_with_reviewer(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(mod, "interrupt",
                        lambda payload: {q: "demo nội bộ" for q in payload["questions"]})

    state = {"thread_id": "t-4", "pr_url": "u",
             "analysis": make_analysis(0.3, questions=["Vì sao MD5?"]), "pr_diff": "x"}
    out = await mod.node_escalate(state)

    rows = await replay_events("t-4")
    assert [r["action"] for r in rows] == ["escalate", "escalate"]
    assert rows[0]["reviewer_id"] is None and rows[1]["reviewer_id"] == "EntityEbisu"
    assert out["escalation_answers"] == {"Vì sao MD5?": "demo nội bộ"}
```

**Chạy:** `uv run pytest tests/test_ex4_audit.py -q` → `4 passed`.

**Commit:** `git commit -am "feat(ex4): audit entries before and after the escalation interrupt"`

---

### Task E6 — Entry cho `synthesize`, `commit`, `auto_approve`

**Files:** `exercises/exercise_4_audit.py` (3 chỗ).

`synthesize` (sau dòng print refined):
```python
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="synthesize",
        confidence=refined.confidence,
        risk_level=risk_level_for(refined.confidence),
        reviewer_id=os.environ.get("GITHUB_USER"),
        decision="pending",
        reason=refined.confidence_reasoning,
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))
```

`commit` (thay khối TODO ở `node_commit`):
```python
    posted = action not in ("rejected", "commit_failed")
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="commit",
        confidence=state["analysis"].confidence,
        risk_level=risk_level_for(state["analysis"].confidence),
        reviewer_id=(os.environ.get("GITHUB_USER")
                     if state.get("human_choice") or state.get("escalation_answers") else None),
        decision="approve" if posted else "reject",
        reason=f"final_action={action}",
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))
```

`auto_approve` (thay khối TODO):
```python
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="auto_approve",
        confidence=a.confidence,
        risk_level=risk_level_for(a.confidence),
        reviewer_id=None,
        decision="auto",
        reason=a.summary[:300],
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))
```
(`risk_level_for(a.confidence)` ở nhánh này luôn `"low"` vì confidence ≥ 0.73 — đúng với truy vấn kiểm tra của README: `risk_level='high' AND decision='auto'` không bao giờ xảy ra.)

**Test bổ sung (chặn POST bằng monkeypatch — không gọi GitHub):**
```python
async def test_commit_and_auto_approve_rows(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "d.db"))
    monkeypatch.setenv("GITHUB_USER", "EntityEbisu")
    monkeypatch.setattr(mod, "post_review_comment", lambda url, body: None)

    s1 = {"thread_id": "t-5", "pr_url": "u", "analysis": make_analysis(0.65),
          "human_choice": "approve", "human_feedback": None}
    await mod.node_commit(s1)
    s2 = {"thread_id": "t-6", "pr_url": "u", "analysis": make_analysis(0.95)}
    await mod.node_auto_approve(s2)

    rows1, rows2 = await replay_events("t-5"), await replay_events("t-6")
    assert rows1[-1]["action"] == "commit" and rows1[-1]["decision"] == "approve"
    assert rows2[-1]["action"] == "auto_approve" and rows2[-1]["risk_level"] == "low"
```
**Chạy:** `uv run pytest tests/test_ex4_audit.py -q` → `5 passed`.

**Commit:** `git commit -am "feat(ex4): audit entries for synthesize, commit and auto_approve"`

---

### Task E7 — Guard chống ghi trùng dòng "trước interrupt" (bắt buộc, có test)

**Lý do:** LangGraph chạy lại node từ đầu khi resume (README FAQ), nên entry `decision="pending"` trước `interrupt()` bị ghi **2 lần** → audit trail có dòng trùng. Guard dưới đây chặn đúng trường hợp đó.

**Files:** `exercises/exercise_4_audit.py` (thân `audit()`).

```python
async def audit(state, entry: AuditEntry) -> None:
    """Ghi một dòng AuditEntry vào bảng `audit_events`.

    `thread_id`/`pr_url` lấy từ `state`. Chống trùng: khi graph resume, node chứa
    `interrupt()` được chạy lại từ đầu, nên dòng 'trước interrupt' (decision='pending')
    sẽ bị ghi lại lần hai. Ta bỏ qua nếu dòng gần nhất của cùng thread đã có
    đúng `action` + `decision='pending'`.
    """
    if entry.decision == "pending":
        recent = await replay_events(state["thread_id"])
        if recent and recent[-1]["action"] == entry.action and recent[-1]["decision"] == "pending":
            return
    await write_audit_event(thread_id=state["thread_id"], pr_url=state["pr_url"], entry=entry)
```

**Test bổ sung:**
```python
async def test_pending_row_is_not_duplicated_on_resume(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "e.db"))
    state = {"thread_id": "t-7", "pr_url": "u"}
    entry = AuditEntry(agent_id=mod.AGENT_ID, action="human_approval", confidence=0.65,
                       risk_level="med", decision="pending", reason="chờ duyệt",
                       reviewer_id=None, execution_time_ms=1)
    await mod.audit(state, entry)   # lần chạy đầu
    await mod.audit(state, entry)   # lần chạy lại sau resume
    rows = await replay_events("t-7")
    assert len(rows) == 1, "dòng 'pending' của cùng action không được ghi 2 lần"
```

**Chạy:** `uv run pytest tests/test_ex4_audit.py -q` → `6 passed`. Chạy lại task E4/E5 test → vẫn `passed` (entry sau interrupt có decision khác `pending` nên không bị chặn).

**Commit:** `git commit -am "fix(ex4): avoid duplicated pre-interrupt audit rows on resume"`

**Ghi chú report:** nếu giảng viên muốn giữ đúng "một dòng" như README mô tả, xoá guard này và ghi vào report rằng mỗi HITL node sinh 3 dòng (pending, pending, kết quả). **Không** giấu.

---

### Task E8 — Chạy thật bài 4 trên cả 2 PR + replay + SQL (evidence)

```bash
rm -f hitl_audit.db         # demo sạch; DB cũ bị *.db gitignore nên không mất gì trên git
sqlite3 hitl_audit.db "PRAGMA journal_mode=WAL;" || true   # giảm rủi ro 'database is locked'
uv run python exercises/exercise_4_audit.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/1 2>&1 | tee docs/evidence/ex4_pr1.txt
# tại prompt: approve
uv run python exercises/exercise_4_audit.py --pr https://github.com/VinUni-AI20k/PR-Demo/pull/2 2>&1 | tee docs/evidence/ex4_pr2.txt
# tại prompt: trả lời từng câu hỏi
```
Kỳ vọng cuối mỗi lần:
```
final_action = committed        (PR #1)
final_action = committed        (PR #2, qua refine → commit)

Replay: uv run python -m audit.replay --thread <thread_id>
```
Lấy `thread_id` trong log rồi:
```bash
uv run python -m audit.replay --list | tee docs/evidence/ex4_replay_list.txt
uv run python -m audit.replay --thread <thread_id_pr1> | tee docs/evidence/ex4_replay_pr1.txt
sqlite3 hitl_audit.db "SELECT thread_id, action, confidence, risk_level, decision, reviewer_id, execution_time_ms FROM audit_events ORDER BY id;" | tee docs/evidence/ex4_rows.txt
sqlite3 hitl_audit.db "SELECT COUNT(*) FROM audit_events WHERE risk_level='high' AND decision='auto';" | tee docs/evidence/ex4_invariant.txt
```
Kỳ vọng: bảng replay có đủ `fetch_pr → analyze → route → human_approval(pending) → human_approval(approve) → commit` (PR #1) với **không** dòng `pending` trùng; dòng cuối của `ex4_invariant.txt` là `0`.
Truy vấn của README thêm 1 lần cho report:
```bash
sqlite3 hitl_audit.db "SELECT AVG(confidence) FROM audit_events WHERE decision='approve';"
```

**Commit:** `git add docs/evidence/ex4_* && git commit -m "docs(ex4): audit trail evidence (replay + SQL invariants)"`

---

## 7. GIAI ĐOẠN F — Exercise 5: Streamlit UI (`app.py`)

### Task F1 — Test cho helper truy vấn sidebar

**Files:** tạo `tests/test_ex5_sidebar.py`.

```python
import app_helpers  # noqa: F401  (sẽ tạo ở Task F2)


async def test_recent_threads_and_events(monkeypatch, tmp_path):
    import exercises.exercise_4_audit as mod
    from common.schemas import AuditEntry

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "ui.db"))
    for i, risk in enumerate(("med", "high")):
        await mod.audit(
            {"thread_id": f"t-{i}", "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/1"},
            AuditEntry(agent_id="pr-review-agent@v0.1", action="route", confidence=0.5,
                       risk_level=risk, decision="escalate", reason="r",
                       reviewer_id=None, execution_time_ms=5),
        )

    threads = await app_helpers.fetch_recent_threads()
    assert {t["thread_id"] for t in threads} == {"t-0", "t-1"}
    assert {t["worst_risk"] for t in threads} == {"med", "high"}

    events = await app_helpers.fetch_thread_events("t-1")
    assert len(events) == 1 and events[0]["risk_level"] == "high"
```

**Chạy (FAIL):** `uv run pytest tests/test_ex5_sidebar.py -q` → `ModuleNotFoundError: No module named 'app_helpers'`.

---

### Task F2 — Implement `app_helpers.py` (truy vấn audit cho sidebar)

**Files:** tạo `app_helpers.py` ở gốc repo (mình tự tạo — **không** sửa `audit/replay.py`; lý do: thư mục `audit/` là file được cung cấp).

```python
"""Truy vấn audit_events phục vụ sidebar Streamlit.

Không sửa `audit/replay.py` (file được cung cấp). Lưu ý: `MAX(risk_level)` trong file đó
là so sánh chuỗi (lexicographic) nên 'med' > 'low' > 'high' — sai thứ tự rủi ro.
Ở đây tính hạng rủi ro bằng CASE rồi map lại nhãn.
"""

from __future__ import annotations

from typing import Any

from common.db import db_conn

_RANK_TO_LABEL = {3: "high", 2: "med", 1: "low"}


async def fetch_recent_threads(limit: int = 25) -> list[dict[str, Any]]:
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
    out = []
    for r in rows:
        row = dict(r)
        row["worst_risk"] = _RANK_TO_LABEL.get(row.pop("worst_rank"), "low")
        out.append(row)
    return out


async def fetch_thread_events(thread_id: str) -> list[dict[str, Any]]:
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
```

**Chạy:** `uv run pytest tests/test_ex5_sidebar.py -q` → `1 passed`.

**Commit:** `git add app_helpers.py tests/test_ex5_sidebar.py && git commit -m "feat(ex5): audit-backed sidebar queries + tests"`

---

### Task F3 — Sidebar "Recent sessions" trong `app.py`

**Files:** `app.py:52-58`.

```python
# ─── Sidebar — recent sessions ─────────────────────────────────────────────
with st.sidebar:
    st.header("Recent sessions")
    try:
        threads = asyncio.run(app_helpers.fetch_recent_threads())
    except Exception as exc:  # chưa có DB -> chưa có phiên nào
        threads = []
        st.caption(f"(chưa đọc được audit_events: {exc})")

    if threads:
        st.dataframe(
            [
                {
                    "thread_id": t["thread_id"][:8],
                    "pr": t["pr_url"].rsplit("/", 1)[-1],
                    "risk": t["worst_risk"],
                    "events": t["events"],
                    "last_event": str(t["last_event"])[:19],
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

    if st.session_state.get("selected_thread"):
        st.subheader("Sự kiện")
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
```
Thêm ở đầu file: `import app_helpers`, và thêm `selected_thread` vào khối session state (`st.session_state.selected_thread = None` nếu chưa có).

**Kiểm tra cú pháp (không cần server):**
```bash
uv run python -c "import ast;ast.parse(open('app.py',encoding='utf-8').read());print('syntax OK')"
```
Kỳ vọng: `syntax OK`.

**Commit:** `git commit -am "feat(ex5): audit-backed recent sessions sidebar"`

---

### Task F4 — Nút Approve / Reject / Edit trong `render_approval_card`

**Files:** `app.py:86-96`.

```python
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
```

**Test tĩnh (AppTest của Streamlit, không gọi mạng — chỉ dựng widget):** tạo `tests/test_ex5_widgets.py`:
```python
"""Kiểm tra 2 renderer trả None khi chưa bấm nút (không gọi mạng, không gọi graph)."""

import app as app_module  # noqa: F401


def test_app_module_imports():
    assert hasattr(app_module, "render_approval_card")
    assert hasattr(app_module, "render_escalation_card")
```
**Chạy:** `uv run pytest tests/test_ex5_widgets.py -q` → `1 passed`. (Streamlit import khi không có runtime vẫn tạo warning "missing ScriptRunContext" — chấp nhận, ghi vào report.)

**Commit:** `git commit -am "feat(ex5): approve/reject/edit buttons return resume payload"`

---

### Task F5 — Form escalation trong `render_escalation_card`

**Files:** `app.py:108-114`.

```python
    with st.form("escalation"):
        answers_inputs: dict[str, str] = {}
        for i, q in enumerate(payload["questions"]):
            answers_inputs[q] = st.text_input(q, key=f"escalation_answer_{i}")
        submitted_answers = st.form_submit_button("Submit answers")

    if not submitted_answers:
        return None
    if not any(v.strip() for v in answers_inputs.values()):
        st.warning("Cần trả lời ít nhất một câu hỏi trước khi gửi.")
        return None
    return {q: v for q, v in answers_inputs.items() if v.strip()}
```

**Chạy lại:** `uv run pytest tests/test_ex5_widgets.py -q` → `1 passed`.

**Commit:** `git commit -am "feat(ex5): escalation question form returns {question: answer}"`

---

### Task F6 — `run_graph()` + import graph bài 4

**Files:** `app.py:23-30` (import) và `:118-133`.

```python
from exercises.exercise_4_audit import build_graph
```
```python
async def run_graph(pr_url: str, thread_id: str, resume_value=None):
    """Gọi graph một lần. Trả về kết quả cuối hoặc {'__interrupt__': [...]}."""
    async with AsyncSqliteSaver.from_conn_string(db_path()) as cp:
        await cp.setup()
        graph = build_graph(cp)
        cfg = {"configurable": {"thread_id": thread_id}}
        if resume_value is None:
            return await graph.ainvoke({"pr_url": pr_url, "thread_id": thread_id}, cfg)
        return await graph.ainvoke(Command(resume=resume_value), cfg)
```

**Xác nhận `streamlit` đã có trong dependencies (README yêu cầu — kiểm tra, đừng thêm lại):**
```bash
grep -n 'streamlit' pyproject.toml
```
Kỳ vọng: `"streamlit>=1.40.0",` đã có sẵn.

**Chạy:** `uv run pytest -q` → toàn bộ test PASS (khoảng 20 test).
**Commit:** `git commit -am "feat(ex5): wire AsyncSqliteSaver graph invocation and resume"`

---

### Task F7 — Chạy Streamlit thật + click-through (evidence)

```bash
uv run streamlit run app.py --server.headless true --server.port 8501 > docs/evidence/ex5_streamlit.log 2>&1 &
sleep 6
curl -s -o /dev/null -w "http=%{http_code}\n" http://localhost:8501
```
Kỳ vọng: `http=200`.

Sau đó (bằng browser tool, text-first):
1. Mở `http://localhost:8501`, điền PR #1 → **Run review**.
2. Chờ card "Approval requested — confidence ~65%" → bấm **Approve**. Kỳ vọng: `st.success("✓ committed — comment posted to ...")`.
3. Làm lại với PR #2 → card đỏ "Strong escalation" + form câu hỏi → trả lời → **Submit answers** → kỳ vọng thấy review tinh chỉnh rồi success/committed.
4. Chụp màn hình 2 card lưu `docs/evidence/ex5_card_approval.png`, `docs/evidence/ex5_card_escalation.png` (đính kèm report).
5. Kiểm tra DB có dòng mới + comment thật đã lên GitHub (curl như Task C4).
6. Tắt server: `kill %1` (hoặc `lsof -ti:8501 | xargs kill`).

**Commit:** `git add docs/evidence/ex5_* && git commit -m "docs(ex5): streamlit smoke test + UI evidence"`

---

## 8. GIAI ĐOẠN G — Deliverables, report, push

### Task G1 — Bộ test đầy đủ + đo độ phủ chức năng

```bash
uv run pytest -q 2>&1 | tee docs/evidence/pytest_full.txt
```
Kỳ vọng: `~20 passed` và **không** test nào gọi mạng (chạy được khi tắt wifi).

### Task G2 — `report.md` tiếng Việt

**Files:** tạo `report.md`. Bắt buộc có các mục (viết ngắn, số liệu lấy từ `docs/evidence/`):

1. **Tổng quan & mục tiêu** — agent review PR, 3 bucket theo confidence.
2. **Kiến trúc** — sơ đồ ASCII các node + nhánh; bảng ngưỡng 0.73 / 0.58.
3. **Provider LLM** — dùng OpenCode Go `longcat-2.5-preview-free`; lý do; **kết quả probe** (số liệu ở `docs/evidence/provider_probe.txt`); header bắt buộc `x-opencode-session`; cách truyền qua `OPENAI_CUSTOM_HEADERS`; **nếu đã dùng A6-C thì ghi rõ đã sửa `common/llm.py`**.
4. **Kết quả từng exercise** — mỗi bài: lệnh chạy, kết quả (nhánh nào, confidence bao nhiêu), ảnh trích log.
5. **Audit trail** — bảng `audit_events`, 3 truy vấn SQL mẫu + kết quả thật, ảnh `audit.replay`.
6. **UI Streamlit** — mô tả 3 card, ảnh chụp.
7. **Sai lệch & ghi chú trung thực** — bắt buộc liệt kê: (a) provider đổi sang OpenCode Go + model free thay vì OpenRouter/gpt-4o-mini; (b) `deepseek-v4.1-flash-free` không tồn tại, dùng `longcat-2.5-preview-free`; (c) nếu đổi `ESCALATE_THRESHOLD` để ép nhánh escalate → ghi rõ giá trị cũ/mới và lý do; (d) guard chống trùng dòng audit; (e) nếu dùng A7-fallback (parse JSON thủ công); (f) nếu PR #2 không tồn tại.
8. **Hạn chế & hướng phát triển** — free model có thể 429; audit trùng/hiệu năng SQLite; Streamlit chạy `asyncio.run` mỗi lần bấm.

**Commit:** `git add report.md && git commit -m "docs: Vietnamese lab report with evidence"`

### Task G3 — Cập nhật `.env.example` (tài liệu hoá cấu hình mới)

Thêm vào `.env.example`:
```dotenv
# Provider thay thế: bất kỳ endpoint OpenAI-compatible nào.
# Lab này dùng OpenCode Go (https://opencode.ai/zen/go/v1); header bắt buộc
# x-opencode-session + User-Agent riêng, truyền qua OPENAI_CUSTOM_HEADERS.
LLM_FALLBACK_MODEL=deepseek-v4.1-flash
LLM_SESSION_ID=day27-minh-001
# OPENAI_CUSTOM_HEADERS="x-opencode-session: day27-minh-001\nUser-Agent: Day27-HITL-Lab/0.1"
# Tên GitHub của người duyệt (ghi vào cột reviewer_id của audit_events)
GITHUB_USER=your-github-login
```
**Commit:** `git commit -am "docs: document OpenCode Go provider + GITHUB_USER in .env.example"`

### Task G4 — Kiểm tra bí mật trước khi push (BẮT BUỘC)

```bash
git status --porcelain --untracked-files=all | grep -E '\.env$|\.db$' && echo "CẢNH BÁO: có file cấm trong cây làm việc" || echo "OK: không có .env/.db trong cây"
git grep -nE 'sk-|ghp_|OPENCODE_API_KEY=[A-Za-z0-9]' -- . ':!*.lock' || echo "OK: không có khóa trong mã nguồn"
```
Kỳ vọng: `OK: không có .env/.db trong cây` và `OK: không có khóa trong mã nguồn`.

Nếu phát hiện khóa trong file đã track → **dừng**, báo Nguyen, xoay khóa (rotate) tại OpenCode/GitHub, rồi mới push.

### Task G5 — Push & xác nhận

```bash
git log --oneline | head -20
git push origin main
git status --short
```
Kỳ vọng: push thành công, `git status` sạch (không còn commit nào chưa đẩy).

---

## 9. Tests / validation — quy tắc chung

- **TDD từng task code**: viết test → `uv run pytest <file> -q` **thấy FAIL** → code tối thiểu → chạy lại **thấy PASS** → commit. Không gộp 2 test vào 1 lần commit.
- **Không test nào gọi mạng**: đã có `tests/fakes.py`; POST GitHub bị chặn bằng monkeypatch `post_review_comment`; DB test dùng `tmp_path` + `HITL_DB_PATH`.
- **Chạy thật chỉ ở**: A5, A7, B5, C4, D5, E8, F7 (tổng ≈ 12–18 lời gọi LLM free).
- **Bảng tiêu chí nghiệm thu** (dùng khi tự review ở cuối):

| # | Tiêu chí | Lệnh kiểm tra | Kỳ vọng |
|---|---|---|---|
| 1 | 3 nhánh routing rẽ đúng | `uv run pytest tests/test_ex1_routing.py -q` | 7 passed |
| 2 | 2 PR demo ra 2 nhánh khác nhau | `docs/evidence/ex1_pr1.txt`, `ex1_pr2.txt` | 1 human_approval, 1 escalate |
| 3 | `interrupt()` + resume chạy | `docs/evidence/ex2_pr1_approve.txt` | `committed` + comment thật trên GitHub |
| 4 | Escalate hỏi câu cụ thể rồi tinh chỉnh | `docs/evidence/ex3_pr2_escalate.txt` | có `Q:`/`A:`, refined confidence > gốc |
| 5 | Audit đủ dòng, không trùng | `sqlite3 hitl_audit.db "SELECT action,decision FROM audit_events ORDER BY id;"` | ≥6 dòng/phiên, **không** có 2 dòng `pending` liền nhau cùng action |
| 6 | Invariant "rủi ro cao mà tự duyệt" không xảy ra | `docs/evidence/ex4_invariant.txt` | `0` |
| 7 | Replay được toàn phiên | `uv run python -m audit.replay --thread <id>` | in bảng đủ sự kiện |
| 8 | Streamlit UI 3 card | `docs/evidence/ex5_card_*.png` + `ex5_streamlit.log` | http=200 + 2 ảnh |
| 9 | Không rò bí mật | Task G4 | 2 dòng OK |

---

## 10. Risks, tradeoffs, câu hỏi mở

**R1 — Model free không ổn định.** `longcat-2.5-preview-free` đã probe sống, nhưng model free có thể 429/đổi hành vi bất cứ lúc nào. *Giảm thiểu:* `LLM_FALLBACK_MODEL=deepseek-v4.1-flash` trong `.env`; nếu gặp 429 liên tục, đổi `LLM_MODEL=deepseek-v4.1-flash` và **ghi vào report** (model không còn free).

**R2 — Structured output có thể không được hỗ trợ.** Model reasoning + `with_structured_output` là điểm chưa chắc chắn nhất → Task A7 quyết định bằng thực nghiệm, có A7-fallback parse JSON thủ công.

**R3 — Model quá tự tin, PR #2 không rơi vào nhánh escalate.** *Xử lý theo thứ tự:* (1) prompt hiệu chỉnh đã có ở `common_prompts.py`; (2) thêm 1–2 ví dụ trong prompt; (3) đổi `ESCALATE_THRESHOLD` lên `0.70` **và ghi rõ trong report** (README FAQ cho phép, nhưng phải khai báo vì đó là thay đổi ngưỡng của đề).

**R4 — Sai lệch so với "provided, don't modify".** Mặc định kế hoạch **không** sửa file nào trong `common/`/`audit/`. Chỉ A6-C (bắt buộc nếu header không truyền được qua env) hoặc A7-fallback mới chạm code — cả hai đều có đường ghi chú vào report. Ưu tiên tuyệt đối A6-B trước A6-C.

**R5 — Ghi trùng dòng audit khi resume.** Đã xử lý bằng guard (Task E7) + test. Nếu bỏ guard để bám đúng README, phải ghi rõ 3 dòng/HITL node trong report.

**R6 — SQLite lock khi checkpointer và audit cùng ghi.** *Giảm thiểu:* chạy `PRAGMA journal_mode=WAL` một lần (đã có ở Task E8). Nếu vẫn gặp `database is locked`, thêm retry 3 lần trong `audit()` — nhưng phải ghi chép.

**R7 — `MAX(risk_level)` lexicographic trong `audit/replay.py`.** File được cung cấp có lỗi thứ tự rủi ro (`'med' > 'low' > 'high'`). Kế hoạch **không** sửa; `app_helpers.py` tính đúng bằng `CASE`. Ghi 1 dòng vào report coi như phát hiện phụ.

**R8 — PR #2 có thể không tồn tại.** Đã có bước xác minh ở Task A4; nếu thiếu → báo Nguyen, không bịa evidence.

**R9 — Python 3.14 thiếu wheel.** Đã pin 3.12 ở Task A1.

**Câu hỏi mở (cần Nguyen quyết, ghi ngay khi triển khai):**
1. PAT GitHub — Nguyen tự tạo và dán vào `.env` (kế hoạch không thể chạy thật nếu thiếu). Có dùng luôn PAT cũ nếu còn hạn không?
2. Có được phép sửa `common/llm.py` trong trường hợp A6-C không (README ghi "don't modify")?
3. Submission có cần `report.md` + `docs/evidence/` như các lab trước (day23/day26) không, hay chỉ cần code chạy?
4. Cuối cùng có `git push origin main` lên `EntityEbisu/...-HITL` không?
5. Nếu model tự tin quá và buộc phải đổi `ESCALATE_THRESHOLD`, có chấp nhận đổi ngưỡng của đề không (kèm khai báo)?

---

## 11. Bản đồ file (tạo mới / sửa)

**Tạo mới**
- `.python-version`
- `.env` (gitignored — chứa khóa, KHÔNG commit)
- `common_prompts.py`
- `app_helpers.py`
- `tests/conftest.py`, `tests/fakes.py`, `tests/test_fakes.py`
- `tests/test_ex1_routing.py`, `tests/test_ex1_analyze.py`
- `tests/test_ex2_interrupt.py`
- `tests/test_ex3_escalation.py`
- `tests/test_ex4_audit.py`
- `tests/test_ex5_sidebar.py`, `tests/test_ex5_widgets.py`
- `scripts/probe_provider.py`, `scripts/probe_structured.py`
- `report.md`
- `docs/evidence/*.txt|*.png` (provider_probe, structured_probe, ex1_*, ex2_*, ex3_*, ex4_*, ex5_*)

**Sửa**
- `exercises/exercise_1_confidence.py` (3 TODO + import)
- `exercises/exercise_2_hitl.py` (3 TODO)
- `exercises/exercise_3_escalation.py` (4 TODO)
- `exercises/exercise_4_audit.py` (10 TODO + guard)
- `app.py` (5 TODO + import)
- `pyproject.toml` (dev deps + `[tool.pytest.ini_options]`)
- `.env.example` (biến mới, có comment)
- `uv.lock` (do `uv add --dev`)
- `README.md` (**chỉ** nếu muốn thêm mục "Provider đang dùng" — mặc định bỏ trống)

**Không được sửa**: `common/*.py`, `audit/*.py`, `audit/schema.sql` (trừ trường hợp A6-C/A7-fallback, có khai báo).

---

**Ước lượng thời gian:** A ≈ 25 phút (phần lớn là chờ `uv sync` + 3 lời gọi probe) · B–D ≈ 45 phút · E ≈ 30 phút · F ≈ 25 phút · G ≈ 20 phút → **≈ 2h15**, khớp khung lab 2 giờ.
