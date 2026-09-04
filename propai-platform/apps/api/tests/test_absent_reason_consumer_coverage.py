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
_PRODUCER = _API / "app" / "services" / "land_intelligence" / "realtx_report_service.py"
_FIELD = "price_per_pyeong_10k"


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


# ── 2. 소비자 행위 — ★생산자 코드 집합을 파생시켜 전수로 태운다 ──────────────
def _codes_produced_for(field: str) -> set[str]:
    """`withheld(<상수>, ..., field=<field>)` 호출부에서 코드를 **파생**한다(목록형 금지)."""
    tree = ast.parse(_PRODUCER.read_text(encoding="utf-8"))
    codes: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "withheld"):
            continue
        if not any(
            kw.arg == "field" and isinstance(kw.value, ast.Constant) and kw.value.value == field
            for kw in node.keywords
        ):
            continue
        if not node.args:
            continue
        first = node.args[0]
        # 계약 상수는 **이름**으로 넘긴다(그 락이 리터럴 변수 사용을 이미 금지한다).
        if isinstance(first, ast.Name):
            from app.utils import withheld as _w
            val = getattr(_w, first.id, None)
            if isinstance(val, str):
                codes.add(val)
        elif isinstance(first, ast.Constant) and isinstance(first.value, str):
            codes.add(first.value)
    return codes


def test_pdf_consumer_can_name_every_code_the_producer_emits() -> None:
    """★이 락이 종전 결함을 **직접** 잡는다 — 봉합 전에는 `insufficient_coverage` 가 `"—"` 였다."""
    produced = _codes_produced_for(_FIELD)
    # ★공허 진리 방지 — 파생이 비면 «위반 0» 이 아니라 **판정 거부**다.
    assert len(produced) >= 3, (
        f"{_PRODUCER.name} 에서 {_FIELD} 생산 코드를 {len(produced)}건만 파생했다 "
        f"({sorted(produced)}) — 파서가 죽었거나 파일이 옮겨졌다. 판정 거부."
    )
    assert produced <= set(ABSENT_REASONS), f"생산자가 어휘 밖 코드를 낸다: {sorted(produced - set(ABSENT_REASONS))}"

    silent = sorted(c for c in produced if _fmt_per_pyeong({f"{_FIELD}_absent": c}) == "—")
    assert not silent, (
        f"생산자가 내는 코드인데 PDF 가 사유를 말하지 못한다(«—» 로 침묵): {silent}. "
        "소비자 맵이 부분 목록이면 공용 어휘로 떨어지게 하라 — 목록은 곧 상한이 된다."
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


def test_column_specific_wording_is_still_honored() -> None:
    """★열 고유 문구는 **덮어쓰기로 살아 있다** — 공용화가 국소 판단을 지우지 않는다.

    `not_applicable` 은 이 열에서 «해당없음» 이다(공용 짧은 라벨과 우연히 같아도,
    **덮어쓰기 경로가 살아 있다는 것**은 아래 `masked_by_source` 가 증명한다).
    """
    assert _fmt_per_pyeong({f"{_FIELD}_absent": "not_applicable"}) == "해당없음"
    assert _fmt_per_pyeong({f"{_FIELD}_absent": "masked_by_source"}) == "원천미제공"
