"""과금 경로용 멱등 가드 — 라우터가 **한 줄로** 재전송 안전을 얻는다.

## 왜 컨텍스트 매니저인가 (규율을 형태로 강제한다)

계획서는 순서를 **문장**으로 적었다: *"save 는 과금 뒤여야 한다"*. 문장으로 적힌 규율은
호출부가 늘어나는 순간 갈라진다 — 이 저장소가 반복해서 데인 형태다(같은 판정이 두 통로).

그래서 순서를 **형태로** 강제한다:

    async with charge_once(request, endpoint="registry.bulk", payload=..., user=u) as guard:
        result = await 무거운_작업()
        if guard.billable:
            await 과금(...)
        return result

- 선점은 `with` **진입 시** 일어난다(= 실행보다 앞). 늦출 방법이 없다.
- 정산은 블록이 **정상 종료할 때** 일어난다(= 과금보다 뒤). 앞당길 방법이 없다.
- 블록이 예외로 끝나면 선점을 **푼다** — 실패한 요청이 자기 키를 잠그지 않는다.

## 호출부가 지켜야 할 단 하나

`guard.billable` 이 False 면 **과금 호출을 건너뛴다.** 그 외에는 종전과 완전히 같게 동작한다
(결과는 항상 새로 계산해 돌려준다 — 이 가드는 응답을 재생하지 않는다).

## 키가 없으면?

`Idempotency-Key` 헤더가 없으면 종전 동작 그대로다(`billable=True`, 선점 없음). 하위호환이며,
★그 말은 **프론트가 헤더를 보내기 전까지 커버리지가 0** 이라는 뜻이다 — 백엔드만 배선하고
"멱등성 있음"이라고 적으면 거짓이 된다. 그래서 이 가드를 넣는 PR 은 프론트 키 생성을 같이 넣는다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import HTTPException, Request

from app.core import charge_idempotency as ci

logger = structlog.get_logger(__name__)


class ChargeGuard:
    """`charge_once()` 가 넘겨주는 핸들 — 호출부는 `billable` 하나만 보면 된다."""

    __slots__ = ("endpoint", "key", "state")

    def __init__(self, *, state: str, key: str | None, endpoint: str) -> None:
        self.state = state
        self.key = key
        self.endpoint = endpoint

    @property
    def billable(self) -> bool:
        """이번 호출에서 과금해도 되는가. 같은 키로 이미 청구됐으면 False."""
        return self.state != ci.STATE_SETTLED


def _as_plain(payload: Any) -> Any:
    """요청 페이로드를 지문 계산용 평범한 값으로 만든다.

    ★라우터마다 요청 타입이 다르다 — `/get-one` 은 **plain dict**, 나머지는 pydantic 모델이다.
      계획서는 4곳 공통으로 `req.model_dump()` 를 적었는데, 그러면 `/get-one` 이 첫날부터
      전량 500 이 난다(dict 에 `model_dump` 가 없다). 호출부마다 분기시키면 또 갈라지므로
      **한 곳에서** 흡수한다. 테스트 스텁처럼 둘 다 아닌 객체도 그대로 넘겨
      `compute_request_hash` 의 정규화에 맡긴다.
    """
    dump = getattr(payload, "model_dump", None)
    if callable(dump):
        return dump()
    return payload


@asynccontextmanager
async def charge_once(
    request: Request,
    *,
    endpoint: str,
    payload: Any,
    tenant_id: Any,
    user_id: Any,
) -> AsyncIterator[ChargeGuard]:
    """과금 경로를 재전송 안전하게 감싼다.

    - 같은 키 + 같은 요청, **동시** → 두 번째는 409(선점 중)
    - 같은 키 + 같은 요청, 순차 → 두 번째는 실행하되 **과금 안 함**
    - 같은 키 + **다른** 요청 → 422(키 오사용)
    - 키 없음 / 저장소 장애 → 종전 동작(과금함)

    ★`endpoint` 는 경로마다 **서로 달라야** 한다. 같으면 `/bulk` 키가 `/analyze` 응답을
      정산 처리해 한쪽이 무료가 된다.
    """
    key = ci.normalize_key(request.headers.get("Idempotency-Key"))
    if not key:
        yield ChargeGuard(state=ci.STATE_UNAVAILABLE, key=None, endpoint=endpoint)
        return

    scope = ci.scope_id(tenant_id, user_id)
    request_hash = ci.compute_request_hash(_as_plain(payload))

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        res = await ci.reserve(
            db=db, key=key, scope=scope, endpoint=endpoint, request_hash=request_hash
        )

        if res.state == ci.STATE_CONFLICT:
            raise HTTPException(
                status_code=422,
                detail="같은 Idempotency-Key 가 다른 요청 내용으로 재사용되었습니다. "
                       "요청마다 새 키를 쓰세요.",
            )
        if res.state == ci.STATE_IN_FLIGHT:
            raise HTTPException(
                status_code=409,
                detail="같은 요청이 처리 중입니다. 완료를 기다린 뒤 결과를 확인하세요. "
                       "(중복 청구를 막기 위해 두 번째 요청을 받지 않았습니다.)",
            )
        if res.state == ci.STATE_UNAVAILABLE:
            # ★무음으로 두지 않는다 — 보호가 꺼진 채 "배선했다"고 남는 것이 이 저장소의 반복 결함이다.
            logger.warning("멱등 보호 미작동(저장소 사용 불가) — 종전대로 실행·과금", endpoint=endpoint)

        guard = ChargeGuard(state=res.state, key=key, endpoint=endpoint)
        try:
            yield guard
        except Exception:
            if res.owns_reservation:
                await ci.release(db=db, key=key, scope=scope, endpoint=endpoint)
            raise
        if res.owns_reservation:
            # ★여기가 '과금 뒤'다 — 블록이 끝났다는 것은 과금 호출이 끝났다는 뜻이다.
            await ci.settle(db=db, key=key, scope=scope, endpoint=endpoint)
