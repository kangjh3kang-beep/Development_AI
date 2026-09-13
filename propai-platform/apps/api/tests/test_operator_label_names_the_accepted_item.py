"""운영자에게 보이는 라벨이 **코드가 실제로 받는 항목**을 말하는가 — 파생 잠금.

## 왜 이 파일이 생겼나 (2026-09-13)

`#1037` 이 상업용 자본환원율에 **항목 가드**(`_CAP_RATE_ITM`)를 넣어 «투자수익률» 표를
거부하게 했다. 그런데 **운영자가 보는 표면 셋**은 여전히 「투자수익률」이라 말하고 있었다:

    secrets/secret_store.py   label: "R-ONE 상업용 **투자수익률** 통계표ID"
                              desc : "상업용부동산 **소득수익률** … 투자수익률 표를 넣으면 **가드가 거부**한다"
    routers/land_price.py     표시명: "상업용 **투자수익률**"
    reb_statistics_service    독스트링: "상업용 **투자수익률**(cap rate)"  ↔ 같은 파일 :51 «cap rate 가 아니다»

★***한 레코드 안에서 label 과 desc 가 반대를 말했다.*** 운영자는 **제목(`label`)을 먼저 읽는다**
(`ApiKeyManagementPanel.tsx:152` `<h4>{item.label}</h4>`) — 그 지시를 따르면 가드가 거부한다.
★**정정(독립 리뷰 MINOR-3)**: 종전엔 *"이유는 화면 어디에도 없다"* 라고 적었는데 **거짓**이다 —
  `desc` 는 **바로 아래 렌더된다**(`:180-181`). 결함은 «제목이 본문과 반대» 이지 «이유가 없다» 가 아니다.

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

import pytest

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


def test_the_record_explains_why_the_rejected_table_is_rejected() -> None:
    """★`desc` 가 **거부 사유를 속성으로** 담는가 — 어휘가 아니라.

    ★**정정 이력**: 종전 판은 두 가지가 틀렸다(독립 리뷰).
      ㉮ *"label 이 거부 항목만 말하지 않는다"* 는 **락 ①에 함의**돼 원리적으로 위반 불가였다
        (실측: 그 절반을 무력화해도 `::VERDICT=SURVIVED`). **판별력 0이라 지웠다.**
      ㉯ `assert "투자수익률" in desc` 는 **어휘를 잠갔다.** 거부 경고를 온전히 유지한 채
        낱말만 바꾼 정당한 문구(「종합수익률(소득수익률+자본수익률) … 가드가 거부한다」)를
        **위양성으로 막았다**(실측 CAUGHT). ⇒ **속성**으로 바꾼다.
    """
    rec = _secret_record()
    assert rec, "RONE_COMMYIELD_STATBL_ID 레코드를 못 찾았다(조회기 사망)"   # MINOR-4
    desc = rec.get("desc", "")
    assert desc, f"desc 가 비었다: {rec}"

    accepted = _accepted_items()
    # 속성 ①: 거부가 **일어난다**는 사실을 말한다(어떤 낱말로든)
    rejects = any(w in desc for w in ("거부", "가드", "차단"))
    # 속성 ②: **받는 항목**이 무엇인지 말한다
    names_accepted = any(i in desc for i in accepted)
    assert rejects and names_accepted, (
        f"★desc 가 «무엇을 받고 왜 거부되는지»를 말하지 않는다 — 운영자가 거부당해도 이유를 못 찾는다. "
        f"거부 언급={rejects} · 받는항목 언급={names_accepted} · desc={desc!r}"
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


def test_the_ingestion_list_names_the_accepted_item() -> None:
    """★축 ㉠ — **모듈 독스트링의 인제스션 목록**이 받는 항목을 말하는가.

    그 목록은 *"이 모듈이 무엇을 넣는가"* 라는 **사실 주장**이다. 거기서 거부 항목을 이름으로 쓰면
    파일 `:51`(「투자수익률은 cap rate 가 **아니다**」)과 정면으로 모순한다.
    ★어휘(`cap rate`)에 매달리지 않는다 — **「상업용」 항목이 받는 것을 말하는가**만 본다
      (독립 리뷰 MEDIUM-1: 종전 판은 괄호만 떼면 눈이 멀었다 · 실측 SURVIVED).
    """
    doc = ast.get_docstring(ast.parse(Path(inspect.getfile(S)).read_text(encoding="utf-8"))) or ""
    assert doc, "모듈 독스트링이 비었다(조회기 사망)"
    accepted = _accepted_items()
    lines = [ln for ln in doc.splitlines() if "상업용" in ln]
    assert lines, f"독스트링에서 「상업용」 항목을 못 찾았다(조회기 사망): {doc[:120]!r}"
    for ln in lines:
        assert any(a in ln for a in accepted), (
            f"★인제스션 목록이 받는 항목을 말하지 않는다: {ln.strip()!r} · 받는 항목={list(accepted)}"
        )


def test_no_inline_comment_calls_the_rejected_item_the_cap_rate() -> None:
    """★축 ㉡ — **인라인 주석**이 거부 항목을 자본환원율이라 부르지 않는가.

    ★실측으로 잡힌 자리(독립 리뷰 MAJOR-3): `"cap_rate": cap,  # 상업용 **투자수익률**(자본환원율)`
      — 같은 파일 `:51` 이 명문으로 부정하는 등식이 **독스트링 축 밖**에 살아 있었다.

    ★★**이 락이 닫지 못하는 것**(정직 표기): 「거부 항목이 산문에 단독으로 나오면 위반」은
      **성립하지 않는다** — 정당한 단독 출현이 실재한다(실측 2건: 옛 문자열 **인용**과
      **라이브 관측 기록** `distinct_ITM_NM=['투자수익률']`). 즉 이 축은 **의미 판정**이라
      줄 단위 규칙으로 닫히지 않는다. 여기서는 **자본환원율 어휘와 같은 줄**인 경우만 잡는다.
    """
    src = Path(inspect.getfile(S)).read_text(encoding="utf-8")
    accepted = _accepted_items()
    CAPRATE = ("cap rate", "caprate", "자본환원율")
    offenders = [
        f"{i}: {ln.strip()[:100]}"
        for i, raw in enumerate(src.splitlines(), 1)
        for ln in [raw]
        # ★꼬리주석도 본다 — `startswith("#")` 만 보면 `code  # 주석` 을 놓친다
        #   (이 저장소에서 이미 한 번 밟은 사각이다). `#` 뒷부분만 판정한다.
        if "#" in ln
        and _REJECTED in ln.split("#", 1)[1]
        and any(w in ln.split("#", 1)[1].lower() for w in CAPRATE)
        and not any(a in ln.split("#", 1)[1] for a in accepted)
    ]
    assert not offenders, (
        "★인라인 주석이 거부 항목을 자본환원율이라 부른다(같은 파일 :51 이 부정한다):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.xfail(strict=True, reason=(
    "★부채(미잠금) — 이 락의 **모집단이 1**이다. `secret_store` 에는 `name`+`label` 레코드가 "
    "**48개**(desc 보유 25개) 있는데, 같은 클래스의 label↔desc 모순이 나머지에 생겨도 "
    "아무것도 울지 않는다(독립 리뷰 MEDIUM-4). 파생형으로 넓히려면 «가드가 이름을 아는 "
    "레코드» 를 코드에서 뽑는 축이 필요하고, 그 축이 아직 없다."
))
def test_every_secret_record_is_checked_not_just_this_one() -> None:
    raise AssertionError("모집단이 1이다 — 파생형 축이 없다")
