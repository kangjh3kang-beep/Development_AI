"""과금 요율 변경 **감사** 락 — "그때 얼마였나"에 답할 수 있어야 한다.

## 왜 이 파일이 있나

`billing_config` 저장은 `ON CONFLICT (id) DO UPDATE` 로 **단일 행을 덮어쓴다.** 이전 요율은
그 순간 사라지고 스키마에는 `updated_at` 만 남는다(누가·무엇을→무엇으로 바꿨는지 없음).

그 결과 실제로 이런 일이 있었다 — `project_create` 원장 **50,000원** vs 요율 SSOT **2,000원**
(25배)이 발견됐는데, *"관리자 요율 변경 이력을 봐야 판정 가능"* 으로 미확정 처리됐다.
**볼 이력이 없었다.** 코인원장은 청구 *금액*을 남기지만 그 근거 *요율*은 소멸하므로,
어떤 과금 분쟁도 사후 판정이 불가능했다.

`save_config` 가 변경 전/후 diff 를 감사 원장(append-only 해시체인)에 남기도록 고쳤고,
이 파일이 그 배선을 잠근다.

## 두 모집단을 가른다

값이 **바뀌는** 저장과 **안 바뀌는** 저장이 서로 **다른 결과**를 내야 한다. 둘이 같은 값을
내면 배선을 끊어도 테스트가 통과한다(픽스처가 모집단을 안 가르면 잠금이 아니다).

## 이 파일이 특히 노리는 변이

`get_config()` 는 `_CONFIG` 를 **그대로** 돌려주고 `apply_config()` 는 그것을 **in-place** 로
고친다. 그래서 `before = get_config()` 처럼 사본을 안 뜨면 before 와 after 가 **같은 객체**가
되어 diff 가 **항상 비고**, 감사는 "변경 없음"만 영원히 기록한다 — 초록인 채로 무용해진다.
`test_rate_change_is_audited` 가 그 변이에서 죽는다.
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core import billing as billing_core
from app.services.billing import billing_service


class _FakeSession:
    """DB 없이 save_config 를 태우는 최소 세션(실행된 SQL 만 기록)."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: Any, params: Any = None) -> Any:
        self.statements.append(str(statement))
        return None

    async def commit(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _restore_config():
    """전역 `_CONFIG` 를 테스트마다 원복(테스트 간 오염 차단)."""
    snapshot = copy.deepcopy(billing_core.get_config())
    yield
    live = billing_core.get_config()
    live.clear()
    live.update(snapshot)


async def _save(
    override: dict[str, Any],
    actor_id: str | None = "admin-1",
    actor_role: str | None = "super_admin",
):
    """save_config 를 태우고 감사 호출을 가로챈다.

    ★가로채는 대상은 `app.core.audit.audit_admin_action` 이다 — 같은 라우터의 형제
    엔드포인트(`billing.set_tier`)가 쓰는 **표준 통로**이고, `admin_audit_log` 테이블과
    감사 원장(해시체인) 양쪽에 흡수한다. 원장에 직접 넣는 것은 그 부분집합이다.
    """
    with patch(
        "app.core.audit.audit_admin_action", new_callable=AsyncMock
    ) as spy:
        await billing_service.save_config(
            _FakeSession(), override, actor_id=actor_id, actor_role=actor_role
        )
        return spy


def test_config_write_is_destructive_premise() -> None:
    """이 락의 **전제**를 못박는다 — 저장이 단일 행을 덮어쓴다는 사실.

    전제가 바뀌면(예: 이력 테이블이 생기면) 이 파일의 존재 이유가 달라지므로 여기서 알린다.
    """
    ddl = billing_service._CONFIG_DDL
    assert "billing_config" in ddl
    assert "updated_by" not in ddl, (
        "스키마에 변경 주체 컬럼이 생겼다 — 감사를 원장이 아니라 테이블로 옮길 시점인지 재검토하라"
    )


@pytest.mark.asyncio
async def test_rate_change_is_audited() -> None:
    """★모집단 A — 요율이 **바뀌면** 감사가 남고, 거기에 **옛 값**이 들어 있어야 한다.

    `old` 가 핵심이다. `new` 만 남기면 원장에 요율이 늘어설 뿐, 어떤 청구가 어떤 요율에서
    나왔는지 복원되지 않는다 — 애초에 이 락이 생긴 이유(25배 괴리)를 여전히 못 푼다.
    """
    before_fee = billing_core.service_fee_project_create()
    assert before_fee != 50000, "픽스처 전제 붕괴 — 바꾸기 전 값이 이미 목표값이면 차이가 0이다"

    spy = await _save({"service_fees": {"project_create": 50000}})

    assert spy.await_count == 1, "요율이 바뀌었는데 감사가 남지 않았다"
    kwargs = spy.await_args.kwargs
    # ★형제 관례와 같은 이름공간을 쓴다. 같은 라우터의 `billing.set_tier` 가 그 형태다 —
    #   조회할 때 `action LIKE 'billing.%'` 하나로 등급 변경과 요율 변경이 같이 잡혀야 한다.
    assert kwargs["action"] == "billing.update_config"
    assert kwargs["action"].startswith("billing."), "형제(billing.set_tier)와 이름공간이 갈라졌다"
    # ★target 도 단언한다. 빠지면 감사 행에 대상이 비는데, audit_admin_action 은 계약상
    #   내부에서 예외를 삼키므로 **조용히** 반쪽 기록이 남는다. 모킹 테스트는 kwarg 누락을
    #   그냥 통과시키므로 여기서 명시하지 않으면 그 변이가 살아남는다 — 실제로 살아남았다.
    assert kwargs["target"] == "billing_config"
    assert kwargs["actor_id"] == "admin-1", "변경 주체가 감사에 안 실렸다"
    assert kwargs["actor_role"] == "super_admin", "**무슨 권한으로** 바꿨는지가 안 남았다"

    changes = kwargs["detail"]["changes"]
    assert changes, (
        "변경 diff 가 비었다 — before 스냅샷이 _CONFIG 의 **별칭**일 때 나타나는 증상이다"
        "(get_config() 는 라이브 dict 를 돌려주고 apply_config() 는 in-place 다). deepcopy 를 확인하라."
    )
    key = "service_fees.project_create"
    assert key in changes, f"바뀐 키가 diff 에 없다: {sorted(changes)}"
    assert changes[key]["old"] == before_fee, "**옛 요율**이 기록되지 않았다 — 분쟁 판정이 여전히 불가하다"
    assert changes[key]["new"] == 50000


@pytest.mark.asyncio
async def test_noop_save_is_not_audited() -> None:
    """★모집단 B — 값이 **안 바뀌면** 감사가 남지 않는다.

    A 와 B 가 **다른 결과**를 내야 배선 변이가 죽는다. 둘 다 남기거나 둘 다 안 남기면,
    감사 호출을 통째로 지워도(또는 무조건 호출해도) 테스트가 통과한다.
    """
    current = billing_core.service_fee_project_create()

    spy = await _save({"service_fees": {"project_create": current}})

    assert spy.await_count == 0, (
        "값이 그대로인데 감사가 남았다 — 무변경 저장까지 적으면 원장이 소음으로 덮여 "
        "진짜 요율 변경을 찾을 수 없게 된다"
    )


@pytest.mark.asyncio
async def test_actor_absence_is_recorded_as_null_not_dropped() -> None:
    """주체를 모르면 **빈 채로 남긴다** — 감사를 통째로 건너뛰지 않는다.

    주체 미상이라고 기록을 생략하면, 가장 수상한 변경이 가장 조용해진다.
    """
    spy = await _save(
        {"service_fees": {"project_create": 4321}}, actor_id=None, actor_role=None
    )

    assert spy.await_count == 1
    assert spy.await_args.kwargs["actor_id"] is None


def test_diff_records_removed_keys() -> None:
    """키 **삭제**도 금액을 바꾸는 변경이다(접근자가 기본값으로 되돌아간다)."""
    changes = billing_service.diff_config(
        {"service_fees": {"project_create": 2000, "land_analysis": 2000}},
        {"service_fees": {"land_analysis": 2000}},
    )
    assert changes == {"service_fees.project_create": {"old": 2000, "new": None}}


def test_diff_is_empty_when_nothing_changed() -> None:
    """공허 진리 가드 — 같은 입력이면 비어야 한다.

    이게 없으면 diff 가 **항상** 무언가를 반환하는 구현(예: 전체 스냅샷)도 위 테스트를 통과한다.
    """
    same = {"service_fees": {"project_create": 2000}, "tiers": {"power": {"fee_krw": 24500}}}
    assert billing_service.diff_config(same, copy.deepcopy(same)) == {}
