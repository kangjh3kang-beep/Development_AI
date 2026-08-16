"""과금 요율 **값 위생** 락 — 관리자 오타 하나가 과금 장애가 되지 않게.

## 왜 이 파일이 있나

`apply_config` 안에서 요율 세 뭉치가 **서로 다르게** 처리되고 있었다:

| 대상 | 이전 동작 |
|---|---|
| `service_fees` 단일 키 | 변환 실패 시 **원본을 그대로 저장** — "음수 차단" 주석이 약속한 위생을 우회 |
| `service_fees.stages` | **검증이 아예 없음**(float 도, 음수 clamp 도 없음) |
| `service_fees.analysis_modules` | **올바름** — 변환 실패 시 건너뜀 |

옳은 패턴이 **바로 옆에** 있었는데 나머지 둘이 그것을 안 쓰고 있었다.

## 무엇이 실제로 터지나

소비처(`service_fee_project_create()` · `service_fee_stage()`)는 `float(...)` 를 **무방비로**
호출한다. 숫자가 아닌 값이 설정에 들어가면 그 순간이 아니라 **나중에 과금하는 요청 경로에서**
ValueError 가 난다. 게다가 `save_config` 가 그것을 DB 에 영속시키므로 **재기동해도 되살아난다.**

그래서 이 파일의 핵심 단언은 "저장이 거부됐다"가 아니라 **"거부한 뒤에도 과금 조회가
살아 있다"** 이다 — 진짜 피해 경로를 태운다.

## 두 모집단

**유효한 값**(적용됨)과 **무효한 값**(거부·이전 값 보존)이 **다른 결과**를 내야 한다.
둘이 같으면 위생 코드를 통째로 지워도 통과한다.
"""

from __future__ import annotations

import copy

import pytest

from app.core import billing as billing_core

# ★대상을 코드에서 파생시키지 않고 손으로 적되, **세 뭉치가 모두 들어 있는지**를 아래
#   test_all_fee_groups_are_covered 가 검사한다(새 뭉치가 생기면 실패해서 알린다).
_GROUPS = ("plain", "stages", "analysis_modules")


def _override(group: str, value: object) -> dict:
    """세 뭉치 각각에 같은 값을 넣는 override 를 만든다."""
    if group == "plain":
        return {"service_fees": {"project_create": value}}
    if group == "stages":
        return {"service_fees": {"stages": {"design": value}}}
    return {"service_fees": {"analysis_modules": {"persona_sales_agent": value}}}


def _read(group: str) -> float:
    if group == "plain":
        return billing_core.service_fee_project_create()
    if group == "stages":
        return billing_core.service_fee_stage("design")
    return billing_core.service_fee_analysis_module("persona_sales_agent")


@pytest.fixture(autouse=True)
def _restore_config():
    snapshot = copy.deepcopy(billing_core.get_config())
    yield
    live = billing_core.get_config()
    live.clear()
    live.update(snapshot)


def test_all_fee_groups_are_covered() -> None:
    """공허 진리 가드 — 검사 대상이 실제로 셋 다 존재하는가.

    `_GROUPS` 가 비거나 경로가 어긋나면 아래 파라미터화 테스트가 **아무것도 안 태우고**
    통과한다. 여기서 각 그룹이 실제로 읽히는지 먼저 확인한다.
    """
    assert len(_GROUPS) == 3
    for group in _GROUPS:
        assert isinstance(_read(group), float), f"{group} 읽기 경로가 끊겼다"


@pytest.mark.parametrize("group", _GROUPS)
def test_valid_value_is_applied(group: str) -> None:
    """★모집단 A — 숫자는 그대로 적용된다."""
    billing_core.apply_config(_override(group, 4321))
    assert _read(group) == 4321.0


@pytest.mark.parametrize("group", _GROUPS)
def test_invalid_value_is_rejected_and_previous_kept(group: str) -> None:
    """★모집단 B — 숫자가 아니면 **거부**하고 이전 값을 지킨다.

    A 와 B 가 다른 결과를 내야 위생 코드를 지웠을 때 죽는다.
    """
    billing_core.apply_config(_override(group, 1234))  # 기준값을 세운다
    assert _read(group) == 1234.0

    billing_core.apply_config(_override(group, "무료"))  # 숫자가 아님

    assert _read(group) == 1234.0, (
        "숫자가 아닌 값이 설정에 들어갔다 — 이전 값이 덮였다. "
        "그 값은 DB 에 영속되어 재기동해도 되살아난다."
    )


@pytest.mark.parametrize("group", _GROUPS)
def test_charge_lookup_survives_invalid_override(group: str) -> None:
    """★진짜 피해 경로 — 무효값을 넣은 **뒤에도 과금 조회가 살아 있어야** 한다.

    이 단언이 이 파일의 존재 이유다. 소비처는 `float(...)` 를 무방비로 부르므로,
    설정에 문자열이 들어가면 **과금하는 요청에서** ValueError 가 난다.
    "저장을 거부했다"가 아니라 **"거부한 결과 장애가 안 난다"** 를 태운다.
    """
    billing_core.apply_config(_override(group, {"이건": "dict 다"}))

    fee = _read(group)  # 여기서 ValueError 가 나면 실패한다
    assert isinstance(fee, float)
    assert fee >= 0


@pytest.mark.parametrize("group", _GROUPS)
def test_negative_is_clamped_to_zero(group: str) -> None:
    """음수는 0으로 막는다(허위 마이너스 차감 차단) — 세 뭉치 모두 동일하게."""
    billing_core.apply_config(_override(group, -5000))
    assert _read(group) == 0.0


@pytest.mark.parametrize(
    ("group", "expected_path"),
    [
        ("plain", "service_fees.project_create"),
        ("stages", "service_fees.stages.design"),
        ("analysis_modules", "service_fees.analysis_modules.persona_sales_agent"),
    ],
)
def test_rejection_warning_names_the_key(group: str, expected_path: str) -> None:
    """★거부는 **조용하면 안 된다** — 경고가 *어느 키* 였는지 말해야 한다.

    이 단언이 없으면, 경고에서 `where=` 를 지워도(=관리자가 "무언가 거부됐다"만 보고 무엇인지
    모르게 돼도) 테스트가 통과한다. 실제로 변이 검증에서 그 줄이 **살아남았다** —
    "어느 키가 왜 거부됐는지 남긴다"고 커밋에 써 놓고 아무것도 그것을 지키지 않았다.

    거부 자체는 이전 값을 지키므로 시스템은 멀쩡하다. 그래서 **경고만이 유일한 단서**다.
    """
    calls: list[dict] = []
    original = billing_core.logger.warning

    def _capture(*args: object, **kwargs: object) -> None:
        calls.append(kwargs)
        original(*args, **kwargs)

    billing_core.logger.warning = _capture  # type: ignore[assignment]
    try:
        billing_core.apply_config(_override(group, "숫자아님"))
    finally:
        billing_core.logger.warning = original  # type: ignore[assignment]

    assert calls, "거부했는데 경고가 없다 — 관리자는 설정이 반영된 줄 안다(무언 실패)"
    wheres = [c.get("where") for c in calls]
    assert expected_path in wheres, (
        f"경고가 **어느 키**인지 말하지 않는다. 기대={expected_path} 실제={wheres}"
    )


def test_coerce_fee_contract() -> None:
    """공용 헬퍼 계약 — 숫자는 float(0 이상), 그 외는 None(적용 거부)."""
    assert billing_core.coerce_fee(1500, where="t") == 1500.0
    assert billing_core.coerce_fee("2500", where="t") == 2500.0  # 숫자 문자열은 유효
    assert billing_core.coerce_fee(-1, where="t") == 0.0
    assert billing_core.coerce_fee("무료", where="t") is None
    assert billing_core.coerce_fee(None, where="t") is None
    assert billing_core.coerce_fee({"a": 1}, where="t") is None
