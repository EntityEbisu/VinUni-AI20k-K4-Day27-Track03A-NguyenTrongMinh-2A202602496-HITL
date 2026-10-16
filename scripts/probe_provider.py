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
