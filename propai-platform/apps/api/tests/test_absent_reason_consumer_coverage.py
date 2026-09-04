"""보류 사유의 **소비자 축** 락 — 생산자가 내는 코드를 소비자가 **이름 붙일 수 있는가**.

## 왜 새 파일인가 (§5 「이미 막고 있는 것이 있나」를 먼저 쟀다)

`tests/test_withheld_value_contract.py` 가 이미 있고 **파생형**이다. 그런데 그 락의 축은
**생산자**다 — *"`withheld()` 에 넘긴 코드가 닫힌 어휘 안인가"*. 소비자가 그 코드를
**해석할 수 있는가**는 보지 않는다. **한쪽만 건 단언**이고(§D19), 그래서 아래가 통과했다:

    생산자 realtx_report_service.py  → not_applicable · insufficient_coverage · masked_by_source
    소비자 realtx_adapter.py(PDF)    → not_applicable · masked_by_source · source_unavailable
    소비자 RealtxReportPanel.tsx(화면) → (같은 3종)

`insufficient_coverage` 가 **양쪽에서 `"—"`** 로 떨어져 **사유가 소실**됐다. 코드는 어휘 안이라
기존 락은 초록이었다. **셀 수 있는 것을 셌는데, 세야 할 것이 다른 쪽이었다.**

## 이 파일이 잠그는 것

1. **어휘 SSOT 일치**(양방향) — 파이썬 `ABSENT_REASONS` ≡ `ABSENT_SHORT` ≡ 프론트 거울.
   ★한쪽에만 코드를 더하면 실패한다. 그래야 «목록이 상한» 이 되지 않는다.
2. **소비자 행위**(파생형) — 생산자가 그 필드에 내는 코드 집합을 `ast` 로 **파생**해
   소비자 함수를 **전수로 태운다**. 하나라도 `"—"` 를 내면 실패.
   ★목록을 손으로 적지 않는다 — 생산자에 코드가 늘면 이 테스트가 **자동으로** 그것을 태운다.

★**공허 진리 방지**: 파생이 비면(파일 이동·이름 변경·파서 실패) **판정을 거부**한다.
  「0건이라 위반 0」은 이 저장소가 반복해서 데인 형태다 — 그래서 하한을 **먼저** 단언한다.

## ★★적대 리뷰(2026-09-04)가 이 파일에서 잡은 것 — 「목록이 한 층 위로 옮겨갔다」

첫 판은 코드 집합만 `ast` 로 파생하고 **필드와 생산자 파일은 손으로 적었다**(각 길이 1).
*"목록을 늘리지 않는다"* 고 선언해 놓고 **상한이 한 층 위로 이동했을 뿐**이었다:

    withheld() 로 _absent 를 다는 필드 **10개** — 락이 덮던 것은 **1개**
    balanced · down_pct · fail_pct · ok · parcel_level_match · price_per_pyeong_10k ·
    sell_claim_judgment · suggested_price · transactions · warn_pct

→ 이제 **`app/` 전수에서 `(필드 → 코드)` 를 파생**하고, 소비자가 **등록된 필드만** 태운다.
  미등록 필드는 **사유와 함께 초록 안에 드러낸다**(`_KNOWN_UNWIRED`). 그 명단은 **양방향**이라
  ①새 필드가 소비자 없이 생기면 실패하고 ②소비자가 생겼는데 명단에 남아 있어도 실패한다
  (§36 「죽은 면제도 실패시켜라」 — 면제는 초록으로 보이므로 특히 썩기 쉽다).

## ★★★2차 적대 리뷰(2026-09-04)가 **1차 봉합이 새로 판 자리**에서 잡은 것

결함은 매번 **내가 방금 만든 구조의 이음매**로 이동했다. 세 가지가 다 같은 형태였다 —
*"파생형으로 바꿨는데 축이 한 층 위"*. 1차가 그것을 지적했고, 나는 **그 지적을 반영하면서
같은 오류를 두 곳에 새로 만들었다.**

1. **`_produced()` 가 「이름」으로 골랐다** — `node.func.id == "withheld"`. 별칭 임포트
   (`from … import withheld as _wh`)나 속성 호출(`wh.withheld(...)`)은 **안 보인다.**
   그리고 「독립 축」이라 적은 텍스트 계수도 **같은 철자에 의존**해 독립이 아니었다.
   ★변이 실측: 별칭으로 **소비자도 부채선언도 없는 새 필드**를 만들었는데 **SURVIVED**.
   즉 *"새 필드가 소비자 없이 생기면 실패한다"* 는 **이 파일 자신의 주장이 거짓**이었다.
   → **임포트 표를 읽어 `withheld` 에 묶인 지역 이름 집합**으로 판정한다(철자 아님).
   → 독립 축도 임포트 표에서 파생한다: **`withheld` 를 임포트한 모듈은 반드시 필드를
     내야 한다.** 못 읽으면 「없음」이 아니라 **판정 거부**다.

2. **`_KNOWN_BYPASS` 가 「파일」 단위였다** — 이미 등재된 파일 **안에서** 새 우회 필드가
   생기면 무잠금(변이 SURVIVED). 그리고 **단방향**이라 죽은 면제가 안 죽었다(변이 SURVIVED)
   — **같은 커밋에서 `_KNOWN_UNWIRED` 에는 양방향을 적용해 놓고** 30줄 아래에서 빠뜨렸다.
   → **`(파일, 필드)` 쌍**으로 바꾸고 **양방향**으로 만든다. 그리고 **읽기와 쓰기를 가른다**
     (`.get("x_absent")` 는 **소비**지 생산이 아니다 — 종전 명단 6개 중 **3개가 위양성**이었다).

3. ★**분류표가 틀렸다 — 그리고 틀린 방법이 내가 방금 진단한 그 방법이었다.**
   `_KNOWN_UNWIRED` 의 *"(a) 프론트 소비처 0건"* 3건 중 **2건이 거짓**이었다:
   `transactions` → **`RealtxReportPanel.tsx:366` 이 `transactions_basis` 를 렌더**한다 ·
   `suggested_price` → **`FairPriceSuggestCard.tsx:66·143` 이 `note` 를 렌더**한다
   (`text_field="note"`). 진짜 (a) 는 **`sell_claim_judgment` 하나뿐**이다(대조군:
   `매도청구` 18건 ↔ `sell_claim` **0건**으로 조회기 생존 확인).
   ★**왜 틀렸나**: 분류를 `<field>_absent` **역grep** 으로 했다. 그건 내가 바로 그 커밋에서
     *"위음성 축"* 이라고 **진단한 조회 방식**이다 — `_basis`/`_reason`/custom `text_field`
     소비자를 **원리적으로 못 본다.** ***진단한 결함을 그 진단의 다음 단계에서 다시 썼다.***
   → 분류를 **산문이 아니라 구조**로 만든다: 접두는 **닫힌 토큰**이고, `(b)`/`(b′)` 는
     **좌표를 대야 하며 그 파일을 실제로 열어 문구 키를 확인**한다. 못 열면 판정 거부.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.services.report.render.realtx_adapter import _fmt_per_pyeong
from app.utils.withheld import ABSENT_REASONS, ABSENT_SHORT

_API = Path(__file__).resolve().parents[1]
_WEB = _API.parents[1] / "apps" / "web"
_TS_VOCAB = _WEB / "lib" / "withheld" / "absent-reasons.ts"
_APP = _API / "app"
_FIELD = "price_per_pyeong_10k"

#: 필드 → **소비자**(코드를 받아 화면·문서 문구를 내는 함수)와 **침묵값**.
#: ★침묵값을 알아야 침묵을 검출한다 — 「사유를 말하지 못하면 무엇을 돌려주나」다.
_CONSUMERS: dict[str, tuple] = {
    _FIELD: (_fmt_per_pyeong, "—"),
}

#: ★**미배선·정상 분류표.** 접두는 **닫힌 토큰**이고(`_TAXONOMY`), `(b)`/`(b')` 는
#:   **좌표를 대야 하며 락이 그 파일을 실제로 열어 문구 키가 있는지 확인**한다.
#:   ★2차 리뷰 전에는 이 칸이 **산문**이었고, 그래서 3건 중 2건이 **틀린 채로 초록**이었다.
_KNOWN_UNWIRED: dict[str, str] = {
    # (a) ★진짜 부채 — 유료 등기부 권리분석. 세 사유를 코드로 갈라 내는데
    #     (parcel_rights_survey_service.py:262·275·288) **어떤 형태로도** 프론트에 도달하지
    #     않는다. 실측 2026-09-04: `sell_claim` 0건 / 대조군 `매도청구` 18건(조회기 생존).
    #     ★저장소의 「유료 산출물 규율 §4 — 사유를 버렸다」 그 자리다. 별건으로 남긴다.
    "sell_claim_judgment": "(a) 프론트가 어떤 형태로도 사유를 렌더하지 않는다",
    # (b) 정상 — 화면이 **문구**(`_basis`/`_reason`/`text_field`)를 렌더한다.
    #     코드는 기계축으로 선언만 하는 것이 계약이 지시하는 형태다.
    "transactions": "(b) apps/web/components/dashboard/RealtxReportPanel.tsx transactions_basis",
    "suggested_price": "(b) apps/web/components/sales/FairPriceSuggestCard.tsx note",
    "balanced": "(b) apps/web/components/sales/DeveloperProjection.tsx balanced_basis",
    "ok": "(b) apps/web/components/settings/ApiKeyManagementPanel.tsx message",
    "parcel_level_match": "(b) apps/web/components/dashboard/RealtxReportPanel.tsx parcel_level_match_basis",
    # (b') 성장루프 내부 지표 — 사용자 화면이 아니라 **기계가** 읽는다.
    #      ★경로는 **저장소(propai-platform) 기준**으로 통일한다 — 첫 판은 (b) 를 repo 기준,
    #        (b') 를 apps/api 기준으로 섞어 적었고 **이 락이 첫 실행에서 그것을 잡았다.**
    "down_pct": "(b') apps/api/app/services/growth/analyzer.py is_withheld",
    "fail_pct": "(b') apps/api/app/services/growth/analyzer.py is_withheld",
    "warn_pct": "(b') apps/api/app/services/growth/analyzer.py is_withheld",
}

#: 분류 접두 — **닫힌 토큰 집합**. 산문이면 무엇을 써도 통과한다.
_TAXONOMY = ("(a)", "(b)", "(b')")


def _withheld_local_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """이 모듈에서 `withheld` **함수에 묶인 지역 이름**과 **모듈 별칭**을 임포트 표에서 뽑는다.

    ★철자로 고르지 않는다 — `from … import withheld as _wh` · `import app.utils.withheld as wh`
      가 전부 **다른 철자**로 같은 함수를 부른다. 2차 리뷰가 별칭 변이로 **SURVIVED** 를 냈다.
    """
    fn_names: set[str] = set()
    mod_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("utils.withheld"):
            for alias in node.names:
                if alias.name == "withheld":
                    fn_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("utils.withheld"):
                    # `import a.b.withheld` → 참조는 `a.b.withheld.withheld`, 별칭이면 `X.withheld`
                    mod_aliases.add(alias.asname or alias.name.split(".")[-1])
    return fn_names, mod_aliases


def _produced() -> tuple[dict[str, set[str]], set[str]]:
    """`app/` 전수에서 `(필드 → 코드)` 를 파생한다. 두 번째 값은 **판정 불가 모듈**이다.

    ★`**withheld(...)` · `row.update(withheld(...))` 등 어느 **모양**으로 불려도 `ast.walk` 가
      `Call` 로 만난다. 고르는 기준은 **임포트 표가 그 이름에 무엇을 묶었나**다.
    ★`withheld` 를 임포트했는데 필드를 하나도 못 뽑은 모듈은 **「없음」이 아니라 「못 읽음」**
      이다 — 두 번째 값으로 돌려주고 호출부가 **판정을 거부**한다.
    """
    from app.utils import withheld as _w
    out: dict[str, set[str]] = {}
    unreadable: set[str] = set()
    for path in sorted(_APP.rglob("*.py")):
        if path.name == "withheld.py":
            continue  # 계약 구현 자신
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            unreadable.add(str(path.relative_to(_API)))
            continue
        fn_names, mod_aliases = _withheld_local_names(tree)
        if not fn_names and not mod_aliases:
            continue
        found_here = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            is_withheld_call = (
                (isinstance(f, ast.Name) and f.id in fn_names)
                or (isinstance(f, ast.Attribute) and f.attr == "withheld"
                    and isinstance(f.value, ast.Name) and f.value.id in mod_aliases)
            )
            if not is_withheld_call or not node.args:
                continue
            field = next(
                (kw.value.value for kw in node.keywords
                 if kw.arg == "field" and isinstance(kw.value, ast.Constant)),
                None,
            )
            if not field:
                continue
            first = node.args[0]
            # 계약 상수는 **이름**으로 넘긴다(기존 락이 리터럴 변수 사용을 이미 금지한다).
            val = (getattr(_w, first.id, None) if isinstance(first, ast.Name)
                   else first.value if isinstance(first, ast.Constant) else None)
            if isinstance(val, str):
                out.setdefault(field, set()).add(val)
                found_here += 1
        # ★임포트는 했는데 한 건도 못 뽑았다 = 내가 못 읽는 형태다. 「없음」으로 세지 않는다.
        #   (단 `withheld` 를 임포트만 하고 안 쓰는 경우는 린터가 F401 로 이미 막는다.)
        if fn_names and found_here == 0:
            unreadable.add(str(path.relative_to(_API)))
    return out, unreadable


def test_derivation_is_alive_and_refuses_when_it_cannot_read() -> None:
    """★**「못 읽음」을 「없음」으로 세지 않는다** — 독립 축을 **임포트 표**에서 파생한다.

    첫 판의 「독립 축」은 `"withheld(" in line` 텍스트 계수였는데, `_produced()` 와 **같은
    철자에 의존**해 독립이 아니었다(2차 리뷰). 이제 축은 *"`withheld` 를 임포트한 모듈은
    반드시 필드를 낸다"* 이고, 이것은 **호출부 철자와 무관**하다.
    """
    produced, unreadable = _produced()
    assert produced, "생산자 파생이 **비었다** — 파서가 죽었거나 app/ 이 옮겨졌다. 판정 거부."
    assert not unreadable, (
        f"`withheld` 를 임포트했는데 필드를 하나도 못 뽑은 모듈: {sorted(unreadable)} — "
        "내가 **못 읽는 호출 형태**다. 「없음」으로 세지 않고 판정을 거부한다."
    )
    assert produced.keys() >= _CONSUMERS.keys(), (
        f"소비자를 등록해 둔 필드가 생산자에서 사라졌다: {sorted(_CONSUMERS.keys() - produced.keys())}"
        " — 필드명이 바뀌었다면 이 락도 함께 옮겨라(죽은 등록을 조용히 통과시키지 않는다)."
    )


def test_every_producing_field_is_either_burned_or_declared_debt() -> None:
    """★**양방향 명단** — 새 미배선이 생겨도, 배선이 생겼는데 명단에 남아도 실패한다."""
    produced, _ = _produced()
    fields = set(produced)
    covered, declared = set(_CONSUMERS), set(_KNOWN_UNWIRED)
    assert not (covered & declared), (
        f"소비자가 등록됐는데 부채 명단에도 남아 있다(죽은 면제): {sorted(covered & declared)}"
    )
    assert fields == covered | declared, (
        "생산 필드와 (소비자 ∪ 부채명단)이 어긋난다.\n"
        f"  ★소비자도 부채선언도 없는 새 필드: {sorted(fields - covered - declared)}\n"
        f"  ★생산자에서 사라진 선언: {sorted((covered | declared) - fields)}"
    )


def test_debt_classification_is_structured_not_prose() -> None:
    """★분류를 **구조**로 강제한다 — 산문이면 무엇을 써도 통과하고, 실제로 **틀린 채 초록**이었다.

    2차 리뷰 실측: `(a) 프론트 소비처 0건` 3건 중 **2건이 거짓**이었다(`transactions` 는
    `RealtxReportPanel.tsx` 가, `suggested_price` 는 `FairPriceSuggestCard.tsx` 가 문구를
    렌더한다). 종전 단언은 `assert why.strip()` 뿐이라 **원리적으로 못 잡았다.**

    이제 `(b)`/`(b')` 는 **좌표를 대야 하고, 락이 그 파일을 열어 문구 키를 실제로 확인**한다.
    ★못 열면 「없음」이 아니라 **판정 거부**다.
    """
    repo = _API.parents[1]
    for field, why in sorted(_KNOWN_UNWIRED.items()):
        assert why.startswith(_TAXONOMY), (
            f"{field}: 분류 접두가 닫힌 토큰이 아니다 ({why!r}). 허용: {_TAXONOMY}"
        )
        if why.startswith("(a)"):
            continue
        parts = why.split(None, 2)
        assert len(parts) == 3, f"{field}: (b)/(b') 는 «접두 경로 문구키» 세 토큰이어야 한다 — {why!r}"
        _, rel, text_key = parts
        target = repo / rel
        assert target.is_file(), (
            f"{field}: 분류가 가리키는 소비처를 찾지 못했다: {rel} — 파일이 옮겨졌다면 분류도 "
            "함께 옮겨라. **찾지 못한 것을 «맞다» 로 세지 않는다.**"
        )
        body = target.read_text(encoding="utf-8")
        assert text_key in body, (
            f"{field}: {rel} 안에 문구 키 {text_key!r} 가 없다 — 분류가 거짓이거나 소비처가 "
            "바뀌었다. (a) 인지 다시 재라."
        )


def test_registered_consumers_can_name_every_code_the_producer_emits() -> None:
    """★이 락이 종전 결함을 **직접** 잡는다 — 봉합 전에는 `insufficient_coverage` 가 `"—"` 였다."""
    produced, _ = _produced()
    expected = sum(len(produced.get(f, set())) for f in _CONSUMERS)
    burned = 0
    for field, (consumer, silent_value) in _CONSUMERS.items():
        codes = produced.get(field, set())
        # ★공허 진리 방지 — 코드가 비면 아래 루프가 0회 돌고 「위반 0」으로 통과한다.
        assert codes, f"{field}: 생산 코드를 하나도 파생하지 못했다 — 판정 거부"
        assert codes <= set(ABSENT_REASONS), (
            f"{field}: 생산자가 어휘 밖 코드를 낸다 {sorted(codes - set(ABSENT_REASONS))}"
        )
        silent = sorted(c for c in codes if consumer({f"{field}_absent": c}) == silent_value)
        assert not silent, (
            f"{field}: 생산자가 내는 코드인데 소비자가 사유를 말하지 못한다"
            f"(«{silent_value}» 로 침묵): {silent}. 소비자가 부분 목록이면 공용 어휘로 "
            "떨어지게 하라 — 목록은 곧 상한이 된다."
        )
        burned += len(codes)
    # ★하한을 **손으로 적지 않는다** — 종전 `>= 3` 은 오늘 값과 정확히 같아 슬랙이 0이었고,
    #   소비자가 하나만 늘어도 즉시 장식이 됐다(2차 리뷰 MINOR-2). 파생값과 결속시킨다.
    assert burned == expected and burned > 0, f"태운 코드 {burned} ≠ 파생 {expected} — 판정 거부"


#: ★`withheld()` 를 **우회**해 `X_absent` 키를 **직접 쓰는**(생산하는) 자리. **`(파일, 필드)` 쌍**이다.
#:   ★2차 리뷰 전에는 **파일 단위**라 이미 등재된 파일 안의 새 우회 필드가 무잠금이었고
#:     (변이 SURVIVED), **단방향**이라 죽은 면제가 안 죽었다(변이 SURVIVED).
#:     그리고 **읽기를 생산으로 오분류**해 6개 중 3개가 위양성이었다(`.get("x_absent")` 는 소비다).
_KNOWN_BYPASS: set[tuple[str, str]] = {
    ("app/services/feasibility/legacy_ledger.py", "qty"),
    ("app/services/feasibility/legacy_ledger.py", "unit_price"),
    ("app/services/zoning/ordinance_conditional.py", "decision"),
    ("app/services/land_intelligence/parcel_purchase_strategy_service.py", "sell_claim_judgment"),
}


def _bypass_writes() -> set[tuple[str, str]]:
    """`X_absent` 를 **딕셔너리 키로 쓰는**(=생산하는) 자리만 모은다.

    ★**읽기와 쓰기를 가른다** — `t.get("x_absent")` 는 **소비**지 생산이 아니다.
      종전 명단은 그것을 섞어 `realtx_adapter.py`(소비) · `parcel_rights_survey_service.py`(소비)
      · `gosi_coverage_service.py`(그냥 **값 문자열** `"pdf_attachment_absent"`)를 **위양성**으로
      담고 있었다. **위양성도 결함이다** — 가드가 정상 코드를 우회 생산자로 신고한다.
    """
    out: set[tuple[str, str]] = set()
    for path in _APP.rglob("*.py"):
        if path.name == "withheld.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(path.relative_to(_API))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key in node.keys:
                if (isinstance(key, ast.Constant) and isinstance(key.value, str)
                        and key.value.endswith("_absent") and len(key.value) > len("_absent")):
                    out.add((rel, key.value[: -len("_absent")]))
    return out


def test_bypass_producers_are_pinned_both_directions() -> None:
    """`withheld()` 를 안 거치고 `X_absent` 를 **생산**하는 (파일, 필드) 가 **양방향**으로 고정된다."""
    found = _bypass_writes()
    # ★대조군 — 조회기가 살아 있는가(하나도 못 찾으면 파서가 죽은 것이다).
    assert found, "우회 생산자를 하나도 못 찾았다 — ast 조회기 사망(판정 거부)"
    new = found - _KNOWN_BYPASS
    assert not new, (
        f"`withheld()` 를 우회해 `X_absent` 를 직접 생산하는 **새 (파일, 필드)**: {sorted(new)}. "
        "계약 헬퍼를 쓰거나, 못 쓸 이유를 여기 사유와 함께 등재하라."
    )
    # ★**죽은 면제도 실패시킨다**(§36) — 같은 커밋에서 `_KNOWN_UNWIRED` 에는 적용해 놓고
    #   여기서 빠뜨렸던 축이다. 면제는 **초록으로 보이기 때문에** 특히 썩는다.
    dead = _KNOWN_BYPASS - found
    assert not dead, (
        f"이미 사라진 우회 생산자가 명단에 남아 있다(죽은 면제): {sorted(dead)}. "
        "고쳤으면 명단에서도 지워라 — 안 지우면 다음 사람이 «아직 부채가 있다» 로 읽는다."
    )



# ── 1. 어휘 SSOT ────────────────────────────────────────────────────────────
def test_short_labels_cover_exactly_the_closed_vocabulary() -> None:
    """★**양방향**이다 — 어느 쪽에 더해도 실패한다(한쪽만 걸면 반대쪽이 무제한)."""
    assert len(ABSENT_REASONS) >= 7, "어휘가 비었다 — 판정 거부(공허 진리 방지)"
    assert set(ABSENT_SHORT) == set(ABSENT_REASONS), (
        "ABSENT_SHORT 와 ABSENT_REASONS 의 키가 다르다. "
        f"짧은 라벨에만: {sorted(set(ABSENT_SHORT) - set(ABSENT_REASONS))} · "
        f"긴 문구에만: {sorted(set(ABSENT_REASONS) - set(ABSENT_SHORT))}"
    )
    # ★라벨이 **비어 있지 않은지**까지 본다 — 키만 맞추고 값을 비우면 화면이 빈칸이 된다.
    assert all(v.strip() for v in ABSENT_SHORT.values())


def _parse_ts_record(name: str) -> dict[str, str]:
    """프론트 거울에서 `Record` 리터럴을 뽑는다. ★못 읽으면 **판정 거부**."""
    assert _TS_VOCAB.is_file(), (
        f"프론트 어휘 거울을 찾지 못했다: {_TS_VOCAB} — 파일이 옮겨졌다면 이 락도 함께 옮겨라. "
        "찾지 못한 것을 «위반 0» 으로 세지 않는다."
    )
    src = _TS_VOCAB.read_text(encoding="utf-8")
    m = re.search(rf"^export const {name}[^=]*= \{{(.*?)^\}};", src, re.S | re.M)
    assert m, f"{name} 리터럴을 파싱하지 못했다 — 판정 거부(조회기 사망을 «깨끗함» 으로 읽지 않는다)"
    body = m.group(1)
    out = {k: v for k, v in re.findall(r'^\s*(\w+):\s*"([^"]*)",\s*$', body, re.M)}
    assert out, f"{name} 에서 항목을 하나도 못 뽑았다 — 판정 거부"
    return out


@pytest.mark.parametrize(
    ("ts_name", "py_map"),
    [("ABSENT_REASONS", ABSENT_REASONS), ("ABSENT_SHORT", ABSENT_SHORT)],
)
def test_frontend_mirror_matches_backend_ssot(ts_name: str, py_map: dict[str, str]) -> None:
    """프론트 거울이 백엔드 SSOT 와 **키·문구까지** 같다.

    ★문구까지 대조하는 이유: 같은 코드가 **화면과 PDF 에서 다른 뜻**이 되면 그건 «한 화면이
      두 기준으로 말한다» 는 이 저장소의 기록된 사고 형태다. 코드는 기계가 세는 축이고,
      **문구는 사용자가 읽는 계약**이다.
    """
    ts = _parse_ts_record(ts_name)
    assert ts == py_map, (
        f"{ts_name} 거울이 백엔드와 어긋난다.\n"
        f"  프론트에만: { {k: ts[k] for k in set(ts) - set(py_map)} }\n"
        f"  백엔드에만: { {k: py_map[k] for k in set(py_map) - set(ts)} }\n"
        f"  문구 불일치: { {k: (py_map[k], ts[k]) for k in set(ts) & set(py_map) if ts[k] != py_map[k]} }"
    )


def test_dash_still_means_no_reason_at_all() -> None:
    """★**음성 대조군** — 전부를 말하게 만들면 «—» 가 사라져 **위양성 락**이 된다.

    사유 코드가 **아예 없을 때**와 **어휘 밖일 때**는 여전히 `"—"` 여야 한다.
    이것이 없으면 «항상 뭔가 말한다» 는 구현도 만점을 받는다(§37 위양성도 결함).
    """
    assert _fmt_per_pyeong({}) == "—"
    assert _fmt_per_pyeong({f"{_FIELD}_absent": "zzz_not_in_vocabulary"}) == "—"
    # ★값이 있으면 사유가 아니라 **값**이 나온다(두 모집단이 실제로 갈린다).
    assert _fmt_per_pyeong({_FIELD: 1234}) == "1,234"


def test_not_applicable_does_not_repeat_the_status_column() -> None:
    """★이 열의 **설계 판단**을 렌더 결과로 고정한다 — 문구를 못 박지 않는다.

    ★첫 판은 이 자리에 `test_column_specific_wording_is_still_honored` 를 두고 독스트링에
      *"덮어쓰기 경로가 살아 있다는 것은 `masked_by_source` 가 증명한다"* 고 적었다.
      **거짓이었다** — 그 항목도 공용 어휘와 **글자까지 같아서**(차집합 공집합) 아무것도
      증명하지 않았다. 오버라이드 맵을 통째로 지워도 **테스트가 전부 초록**이었다.
      (§C10 「주석에 쓴 근거도 검증 대상」 · 「자기 상수를 단언하는 락」)
      → 오버라이드를 없앴고, 여기서는 **진짜 계약**만 잠근다.

    진짜 계약: `not_applicable` 을 **"해제"라고 쓰지 않는다.** 이 표에는 상태 열이 따로
    있어 이미 "해제"를 말하므로, 두 열이 같은 말을 하면 사용자가 얻는 정보가 0이 된다.
    ★**닫힌 토큰 집합**으로 본다 — 특정 문구를 못 박으면 다듬을 때마다 깨지는 취약한 락이 된다.
    """
    label = _fmt_per_pyeong({f"{_FIELD}_absent": "not_applicable"})
    assert label and label != "—", "사유를 말하지 못한다"
    for forbidden in ("해제", "취소", "무효"):
        assert forbidden not in label, (
            f"단가 열이 상태 열과 같은 말을 한다({label!r} 안에 {forbidden!r}) — "
            "두 열이 같은 말을 하면 사용자가 얻는 정보가 0이다."
        )
    # ★음성 대조군 — 이 단언이 «무엇을 넣어도 참» 이 아님을 보인다(공허하지 않다).
    assert "해제" in "계약이 해제된 신고 건"
