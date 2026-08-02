"""F4a 격리 — **소비자측** 회귀락(발행측이 아니라 읽는 쪽을 잠근다).

## 왜 이 테스트가 따로 필요한가

기존 `test_runner_noop.py`는 field_audit이 어떤 event_type으로 **발행**하는지만 확인한다.
그런데 격리가 실제로 성립하려면 성장엔진의 **소비 쿼리**가 그 event_type을 읽지 않아야 한다.
발행측만 잠그면 `analyzer._analyze_quality_drop`의 WHERE 절에 field_audit event_type을 끼워
넣는 변이가 **모든 테스트를 통과한 채 살아남는다**(실측 확인함).

격리가 깨지면 무슨 일이 벌어지나: field_audit은 분석의 correctness(값이 규칙에 맞나)를 본다.
그 신호가 quality_drop으로 흘러가면 → down_pct 상승 → feature_flags가 `llm_narrative`를
자동 비활성 → 성장엔진이 스스로 서술을 멈춘다. **틀린 값을 찾아낼수록 그걸 설명할 기능이
먼저 꺼지는** 카테고리 오류다. 그래서 이건 스타일이 아니라 안전 계약이다.

## 오라클 설계 (동어반복 금지)

리터럴끼리 비교하지 않는다. **field_audit 관측만 들어 있는 가짜 DB**를 만들고 분석기를
실제로 호출한다. 분석기가 그 이벤트를 고르는 쿼리를 던지면 행이 나오고 → 인사이트가 생기고
→ 테스트가 깨진다. 지금처럼 안 고르면 행이 0이라 인사이트도 0이다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services.growth.analyzer import _analyze_quality_drop
from app.services.verification.field_audit.runner import _OBSERVATION_EVENT_TYPE


def _mentions(value: Any, needle: str) -> bool:
    """바인드 파라미터 어딘가에 needle이 들어 있는가(중첩 리스트·딕트 포함)."""
    if value is None:
        return False
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(_mentions(v, needle) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_mentions(v, needle) for v in value)
    return False


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows


class _FieldAuditOnlyDb:
    """field_audit 관측 이벤트만 저장된 DB를 흉내낸다.

    쿼리 문자열이 field_audit event_type을 고를 때에만 행을 돌려준다 — 즉 '분석기가 이 데이터를
    읽으려 했는가'를 행 개수로 드러낸다. ai_feedback 테이블은 비어 있다(그 축은 별도 관심사).
    """

    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(stmt)
        self.executed_sql.append(sql)
        # ★SQL 문자열만 보면 안 된다: 같은 누출을 **바인드 파라미터**로 넣는 변이
        #   (WHERE event_type = ANY(:types), params={"types": [..., "field_audit_observation"]})가
        #   그대로 살아남는다. 파라미터 바인딩은 SQL 리팩터링의 가장 흔한 형태다.
        if "platform_events" in sql and (
            _OBSERVATION_EVENT_TYPE in sql or _mentions(params, _OBSERVATION_EVENT_TYPE)
        ):
            # 품질저하 판정을 확실히 넘길 만큼(전건 fail) 돌려준다 — 격리가 깨지면 반드시 터지게.
            return _FakeResult([("field_audit", "fail", {"verdict": "fail"}) for _ in range(50)])
        return _FakeResult([])


@pytest.mark.asyncio
async def test_quality_drop_does_not_consume_field_audit_observations() -> None:
    """field_audit 관측만 있는 DB에서 품질저하 인사이트가 0건이어야 한다.

    ★변이 kill: `_analyze_quality_drop`의 platform_events WHERE 절에 field_audit event_type을
      추가하면 가짜 DB가 50건을 돌려주고 인사이트가 생겨 이 단언이 깨진다.
    """
    db = _FieldAuditOnlyDb()
    now = datetime.now(UTC)
    out = await _analyze_quality_drop(db, now - timedelta(days=1), now)

    assert out == [], (
        "field_audit 관측이 quality_drop 인사이트로 전환됐다 — correctness 신호가 서술기능 "
        f"자동토글 루프에 유입되는 F4a 위반. 생성된 인사이트: {out}"
    )


@pytest.mark.asyncio
async def test_quality_drop_actually_queried_platform_events() -> None:
    """위 테스트가 '아무 쿼리도 안 날려서' 통과하는 공허한 참이 아님을 확인한다.

    ★이 테스트가 없으면, 분석기가 platform_events를 아예 조회하지 않도록 망가져도 위 단언이
      그대로 통과한다(0건이니까). 오라클이 실제로 대상 경로를 탔는지 먼저 확인한다.
    """
    db = _FieldAuditOnlyDb()
    now = datetime.now(UTC)
    await _analyze_quality_drop(db, now - timedelta(days=1), now)

    assert any("platform_events" in s for s in db.executed_sql), (
        "품질저하 분석기가 platform_events를 조회하지 않았다 — 격리 단언이 공허한 참이 된다."
    )
