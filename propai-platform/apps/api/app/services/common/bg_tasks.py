"""백그라운드 태스크 참조 보관 공용 헬퍼.

왜 필요한가(쉬운 설명):
`asyncio.create_task(...)` 의 반환 Task 를 아무 데도 보관하지 않으면, CPython 이벤트 루프는
실행 중 태스크를 약참조로만 쥐고 있어 I/O 대기 중 GC 가 태스크를 수거할 수 있다 — 잡이
"조용히 사라지고" 프론트는 타임아웃까지 무익 폴링한다(R1 리뷰 적발). 이 헬퍼는 모듈 전역
set 에 강참조를 보관하고 완료 시 자동 제거한다(shadow_integration._bg_tasks 정답 패턴의
공용 추출 — design_audit·registry 등 fire-and-forget 잡 제출부가 공유).
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_TRACKED: set[asyncio.Task] = set()


def create_tracked_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """create_task + 강참조 보관(+완료 시 자동 discard) — GC 유실 방지."""
    task = asyncio.create_task(coro)
    _TRACKED.add(task)
    task.add_done_callback(_TRACKED.discard)
    return task
