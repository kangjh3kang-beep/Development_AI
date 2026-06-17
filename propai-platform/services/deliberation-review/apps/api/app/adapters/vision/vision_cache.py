"""비전 추출/분류 응답 캐시 — 결정론(INV-1) 복원·비용절감.

비전 LLM 호출은 비결정적이라 동일 도면을 두 번 분석하면 다른 결과가 나올 수 있어 INV-1(동일입력→
동일출력)을 깬다. temperature=0(샘플링 제거)과 함께, 동일 (model, image_ref, prompt) 호출 응답을
캐시해 재현성을 보장한다. 키에 model·prompt 포함(설명가능성). None(실패)은 캐시하지 않음(재시도 허용).

프로세스 로컬 인메모리(분산/영속 캐시는 INC-11 external_source_cache로 확장 예정).
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from threading import Lock
from typing import TypeVar

_store: dict[str, object] = {}
_lock = Lock()

T = TypeVar("T")


def cache_key(model: str | None, image_ref: str | None, prompt: str | None) -> str:
    """동일 모델·이미지참조·프롬프트 → 동일 키(sha256). 설명가능성 위해 입력 3요소 결합."""
    h = hashlib.sha256()
    for part in (model or "", image_ref or "", prompt or ""):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def get_or_call(key: str, fn: Callable[[], T]) -> T:
    """캐시 적중 시 저장값 반환, 아니면 fn() 호출 후 저장. None(실패)은 저장 안 함(재시도 허용)."""
    with _lock:
        if key in _store:
            return _store[key]  # type: ignore[return-value]
    result = fn()
    if result is not None:
        with _lock:
            _store[key] = result
    return result


def clear() -> None:
    """캐시 비우기(테스트/스냅샷 경계용)."""
    with _lock:
        _store.clear()
