"""운영자에게 보이는 라벨이 **코드가 실제로 받는 항목**을 말하는가 — 파생 잠금.

## 왜 이 파일이 생겼나 (2026-09-13)

`#1037` 이 상업용 자본환원율에 **항목 가드**(`_CAP_RATE_ITM`)를 넣어 «투자수익률» 표를
거부하게 했다. 그런데 **운영자가 보는 표면 셋**은 여전히 「투자수익률」이라 말하고 있었다:

    secrets/secret_store.py   label: "R-ONE 상업용 **투자수익률** 통계표ID"
                              desc : "상업용부동산 **소득수익률** … 투자수익률 표를 넣으면 **가드가 거부**한다"
    routers/land_price.py     표시명: "상업용 **투자수익률**"
    reb_statistics_service    독스트링: "상업용 **투자수익률**(cap rate)"  ↔ 같은 파일 :51 «cap rate 가 아니다»

★***한 레코드 안에서 label 과 desc 가 반대를 말했다.*** 운영자는 **label 을 본다** —
그 지시를 따르면 가드가 거부하고, 이유는 화면 어디에도 없다.

## ★이 락이 잠그지 **않는** 것 (정직 표기)

이 변경은 **`cap_rate` 를 고치지 않는다.** 같은 저장소의 strict xfail
(`test_sido_resolution_fail_open.py::test_commercial_yield_table_publishes_a_cap_rate_item`)이
선언한 부채 — *설정된 통계표가 소득수익률 항목을 아예 안 담는다(라이브 `distinct_ITM_NM=['투자수익률']`,
2002~2012 폐지 시계열)* — 는 **그대로 남는다.** 이 PR 이 하는 일은
***운영자에게 틀린 것을 넣으라고 말하던 것을 멈추는 것***뿐이다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.services.land_intelligence import reb_statistics_service as S

_REJECTED = "투자수익률"          # 가드가 거부하는 항목(= cap rate 가 아닌 것)


def _accepted_items() -> tuple[str, ...]:
    """코드가 실제로 받는 항목을 **모듈 상수에서** 가져온다(문자열 복사 금지)."""
    return tuple(S._CAP_RATE_ITM)


def _secret_record() -> dict[str, str]:
    """`RONE_COMMYIELD_STATBL_ID` 레코드를 **AST 로** 뽑는다(주석·독스트링 무관)."""
    from app.services.secrets import secret_store as SS
    src = Path(inspect.getfile(SS)).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Dict):
            continue
        rec = {
            k.value: v.value
            for k, v in zip(node.keys, node.values, strict=False)
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
            and isinstance(k.value, str) and isinstance(v.value, str)
        }
        if rec.get("name") == "RONE_COMMYIELD_STATBL_ID":
            return rec
    return {}


def test_operator_label_names_the_item_the_guard_accepts() -> None:
    """★운영자 라벨은 **가드가 받는 항목**을 말해야 한다(가드가 거부하는 것이 아니라)."""
    accepted = _accepted_items()
    assert accepted, "_CAP_RATE_ITM 이 비었다 — 수집기 사망(공허한 참 방지)"

    rec = _secret_record()
    assert rec, "RONE_COMMYIELD_STATBL_ID 레코드를 못 찾았다(조회기 사망)"
    label = rec.get("label", "")
    assert label, f"label 이 비었다: {rec}"

    assert any(item in label for item in accepted), (
        f"★운영자 라벨이 **가드가 받는 항목**을 말하지 않는다. "
        f"label={label!r} · 받는 항목={list(accepted)} — "
        f"운영자가 이 라벨을 따르면 가드가 거부하고 이유는 화면에 없다."
    )


def test_the_two_surfaces_of_one_record_do_not_contradict() -> None:
    """★두 모집단 — `label` 은 **받는 것만**, `desc` 는 거부 경고를 **담아도 된다**.

    한쪽만 보면 «둘 다 같은 말」과 «한쪽이 반대」를 구별하지 못한다.
    """
    rec = _secret_record()
    label, desc = rec.get("label", ""), rec.get("desc", "")
    accepted = _accepted_items()

    # ㉮ label: 받는 항목을 담고, 거부 항목을 **단독으로** 내세우지 않는다
    assert not (
        _REJECTED in label and not any(i in label for i in accepted)
    ), f"★label 이 거부 항목만 말한다: {label!r}"

    # ㉯ desc: 거부 경고를 담는 것이 **정상**이다(이게 대조군 — 여기까지 지우면 과잉)
    assert _REJECTED in desc, (
        f"desc 에서 거부 경고가 사라졌다 — 운영자가 **왜 거부되는지** 알 길이 없어진다: {desc!r}"
    )


def test_the_discovery_screen_names_the_accepted_item_too() -> None:
    """★형제 표면 — 통계표 탐색 화면의 **표시명**도 같은 축이다.

    ★단 **검색어는 기능값**이라 이 락의 축이 아니다(R-ONE 표 이름으로 찾는다).
      재보지 않고 바꾸면 탐색이 조용히 0건이 된다 — 그래서 표시명만 본다.
    """
    from app.routers import land_price as LP
    src = Path(inspect.getfile(LP)).read_text(encoding="utf-8")
    keys = [
        k.value
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Dict)
        for k, v in zip(node.keys, node.values, strict=False)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
        and "RONE_COMMYIELD_STATBL_ID" in ast.unparse(v)
    ]
    assert keys, "탐색 화면에서 상업용 항목 표시명을 못 찾았다(조회기 사망)"
    accepted = _accepted_items()
    for k in keys:
        assert any(i in k for i in accepted), (
            f"★탐색 화면 표시명이 받는 항목을 말하지 않는다: {k!r} · 받는 항목={list(accepted)}"
        )


def test_the_module_docstring_does_not_contradict_its_own_constant() -> None:
    """★같은 파일 안에서 독스트링과 상수가 반대를 말하지 않는다.

    실측(종전): 독스트링 `:3` 「상업용 **투자수익률**(cap rate)」 ↔ 같은 파일 `:51`
    「투자수익률은 **cap rate 가 아니다**」. **한 파일이 자기와 모순**했다.
    """
    doc = ast.get_docstring(ast.parse(Path(inspect.getfile(S)).read_text(encoding="utf-8"))) or ""
    assert doc, "모듈 독스트링이 비었다(조회기 사망)"
    accepted = _accepted_items()
    # cap rate 를 말하는 줄에 거부 항목이 붙어 있으면 모순이다
    for line in doc.splitlines():
        if "cap rate" not in line:
            continue
        assert not (
            _REJECTED in line and not any(i in line for i in accepted)
        ), f"★독스트링이 거부 항목을 cap rate 라 부른다: {line.strip()!r}"
