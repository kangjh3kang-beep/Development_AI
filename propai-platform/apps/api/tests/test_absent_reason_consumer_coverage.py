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

#: 필드 → 그 필드의 **소비자**(코드를 받아 화면·문서 문구를 내는 함수). 여기 있는 것만 태운다.
#: ★값은 「사유를 말하지 못하면 무엇을 돌려주나」다 — 그 침묵값을 알아야 침묵을 검출한다.
_CONSUMERS: dict[str, tuple] = {
    _FIELD: (_fmt_per_pyeong, "—"),
}

#: ★**미배선 부채 — 사유와 좌표를 적어 초록 안에 드러낸다**(커밋 메시지에만 적으면 안 드러난다).
#:   아래는 `withheld()` 로 사유를 **생산은 하는데** 그 사유를 사람 문구로 바꾸는 소비자를
#:   이 락이 태울 수 없는 필드다. 이유는 두 갈래이고 **다르게 취급해야 한다**:
#:     (a) 소비처가 **아예 없다** — 사유가 사용자에게 도달하지 않는다(진짜 부채)
#:     (b) 소비처가 **문구(`_basis`)를 렌더**한다 — 계약이 지시하는 정상 형태다(부채 아님)
_KNOWN_UNWIRED: dict[str, str] = {
    # (a) ★진짜 부채 — 유료 등기부 권리분석 경로. 세 사유를 코드로 갈라서 내는데
    #     (parcel_rights_survey_service.py:262·275·288) 프론트 소비처가 **0건**이다
    #     (역조회 실측 2026-09-04: `sell_claim_judgment_absent` 0 / 대조군 `매도청구` 18건).
    #     ★저장소의 「유료 산출물 규율 §4 — 사유를 버렸다」 그 자리다. 별건으로 남긴다.
    "sell_claim_judgment": "(a) 프론트 소비처 0건 — 유료 경로. 별건(#974 본문에 좌표)",
    "transactions": "(a) 프론트 소비처 0건",
    "suggested_price": "(a) 프론트 소비처 0건",
    # (b) 정상 — 화면이 `_basis` **문구**를 렌더한다(코드는 기계축으로 선언만).
    "balanced": "(b) DeveloperProjection.tsx:314 이 balanced_basis 문구를 렌더 — 계약대로",
    "ok": "(b) ApiKeyManagementPanel.tsx 가 r.message 를 렌더 — 계약대로",
    "parcel_level_match": "(b) RealtxReportPanel.tsx 가 _basis 문구를 렌더 — 계약대로",
    # (b') 성장루프 내부 지표 — 사용자 화면이 아니라 기계가 읽는다(is_withheld 로 소비).
    "down_pct": "(b') growth/analyzer.py 가 is_withheld 로 기계 소비 — 사람 문구 불필요",
    "fail_pct": "(b') 〃",
    "warn_pct": "(b') 〃",
}


# ── 1. 어휘 SSOT — 양방향 ────────────────────────────────────────────────────
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


# ── 2. 소비자 행위 — ★`app/` 전수에서 (필드 → 코드) 를 파생한다 ──────────────
def _produced() -> dict[str, set[str]]:
    """`withheld(<코드>, …, field=<필드>)` 호출부를 **app/ 전수**에서 파생한다(목록형 금지).

    ★`**withheld(...)` · `row.update(withheld(...))` 등 어느 형태로 불려도 `ast.walk` 가
      `Call` 노드로 만난다 — 호출 **모양**이 아니라 **함수 이름**으로 고른다.
    """
    from app.utils import withheld as _w
    out: dict[str, set[str]] = {}
    for path in sorted(_APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 있으면 아래 하한 교차검증이 잡는다
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "withheld"):
                continue
            field = next(
                (kw.value.value for kw in node.keywords
                 if kw.arg == "field" and isinstance(kw.value, ast.Constant)),
                None,
            )
            if not field or not node.args:
                continue
            first = node.args[0]
            # 계약 상수는 **이름**으로 넘긴다(기존 락이 리터럴 변수 사용을 이미 금지한다).
            val = (getattr(_w, first.id, None) if isinstance(first, ast.Name)
                   else first.value if isinstance(first, ast.Constant) else None)
            if isinstance(val, str):
                out.setdefault(field, set()).add(val)
    return out


def test_derivation_is_alive_and_not_silently_shrinking() -> None:
    """★**하한을 다른 방법으로 교차검증**한다 — 손으로 적은 `>= 3` 은 느슨한 하한이었다.

    첫 판은 `assert len(produced) >= 3` 이었는데 실측이 정확히 3이라 **파서가 하나를 놓쳐도
    통과**할 수 있었다(적대 리뷰 MINOR-2). 이제 **텍스트 계수**라는 독립 축과 대조한다 —
    두 방법이 어긋나면 그 자체가 신호다.
    """
    produced = _produced()
    assert produced, "생산자 파생이 **비었다** — 파서가 죽었거나 app/ 이 옮겨졌다. 판정 거부."
    text_calls = 0
    for path in _APP.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            t = line.lstrip()
            if "withheld(" not in t or t.startswith("#"):
                continue
            if "def withheld(" in t or "is_withheld(" in t or "validate_withheld_pair(" in t:
                continue
            text_calls += 1
    assert text_calls > 0, "텍스트 축도 0 — 조회기 사망(판정 거부)"
    ast_calls = sum(len(v) for v in produced.values())
    # ★같기를 요구하지 않는다(한 호출이 코드 1개고, 주석·문자열이 텍스트 축에 섞인다).
    #   요구하는 것은 **두 축이 같은 규모**라는 것 — 한쪽이 붕괴하면 잡힌다.
    assert ast_calls >= text_calls // 3, (
        f"ast 파생({ast_calls})이 텍스트 계수({text_calls})에 비해 붕괴했다 — 파서 누락. 판정 거부."
    )
    assert produced.keys() >= _CONSUMERS.keys(), (
        f"소비자를 등록해 둔 필드가 생산자에서 사라졌다: {sorted(_CONSUMERS.keys() - produced.keys())}"
        " — 필드명이 바뀌었다면 이 락도 함께 옮겨라(죽은 등록을 조용히 통과시키지 않는다)."
    )


def test_every_producing_field_is_either_burned_or_declared_debt() -> None:
    """★**양방향 명단** — 새 미배선이 생겨도, 배선이 생겼는데 명단에 남아도 실패한다.

    면제는 **초록으로 보이기 때문에** 특히 썩기 쉽다(§36 「죽은 면제도 실패시켜라」).
    """
    produced = set(_produced())
    covered, declared = set(_CONSUMERS), set(_KNOWN_UNWIRED)
    assert not (covered & declared), (
        f"소비자가 등록됐는데 부채 명단에도 남아 있다(죽은 면제): {sorted(covered & declared)}"
    )
    assert produced == covered | declared, (
        "생산 필드와 (소비자 ∪ 부채명단)이 어긋난다.\n"
        f"  ★소비자도 부채선언도 없는 새 필드: {sorted(produced - covered - declared)}\n"
        f"  ★생산자에서 사라진 선언: {sorted((covered | declared) - produced)}"
    )
    for field, why in _KNOWN_UNWIRED.items():
        assert why.strip(), f"{field}: 부채 사유가 비었다 — 사유 없는 면제는 판단할 수 없다"


def test_registered_consumers_can_name_every_code_the_producer_emits() -> None:
    """★이 락이 종전 결함을 **직접** 잡는다 — 봉합 전에는 `insufficient_coverage` 가 `"—"` 였다."""
    produced = _produced()
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
    assert burned >= 3, f"태운 코드가 {burned}건뿐 — 판정 거부(등록된 소비자가 사라졌는가?)"


#: ★`withheld()` 를 **우회**해 `X_absent` 키를 직접 쓰는 생산자. 위 ast 파생이 **구조적으로
#:   못 보는** 형태라, 늘어나는 것만이라도 알아채게 못 박는다(비성장 래칫).
#:   ★이것을 「0건」이라 부르지 않는다 — **못 읽는 형태를 「없음」으로 세지 않는다.**
_KNOWN_BYPASS = {
    "app/services/feasibility/legacy_ledger.py",
    "app/services/zoning/ordinance_conditional.py",
    "app/services/land_intelligence/parcel_purchase_strategy_service.py",
    "app/services/land_intelligence/parcel_rights_survey_service.py",
    "app/services/report/render/realtx_adapter.py",
    "app/services/legal/gosi_coverage_service.py",
}


def test_bypass_producers_do_not_grow_silently() -> None:
    """`withheld()` 를 안 거치고 `X_absent` 를 직접 쓰는 파일이 **늘지 않는다**."""
    found: set[str] = set()
    for path in _APP.rglob("*.py"):
        if path.name == "withheld.py":
            continue  # 계약 구현 자신은 당연히 그 키를 만든다
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # ★`ast` 로 **문자열 상수**만 본다 — 주석·독스트링에 뚫리지 않는다.
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                if v.endswith("_absent") and len(v) > len("_absent"):
                    found.add(str(path.relative_to(_API)))
    # ★대조군 — 조회기가 살아 있는가(하나도 못 찾으면 파서가 죽은 것이다).
    assert found, "우회 생산자를 하나도 못 찾았다 — ast 조회기 사망(판정 거부)"
    new = found - _KNOWN_BYPASS
    assert not new, (
        f"`withheld()` 를 우회해 `_absent` 를 직접 쓰는 **새 파일**: {sorted(new)}. "
        "계약 헬퍼를 쓰거나, 못 쓸 이유를 여기 사유와 함께 등재하라."
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
