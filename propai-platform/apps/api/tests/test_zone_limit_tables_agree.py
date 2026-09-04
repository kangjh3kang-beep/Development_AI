"""용도지역 **법정 한도 표 5벌**이 서로 갈리지 않는다 — 교차 대조 락 (2026-08-24 · R0-e).

## 왜 이 락인가 — 리팩토링이 아니라 락이다

같은 "용도지역 → 법정 건폐율/용적률" 표가 저장소에 **다섯 벌** 있다:

    app/services/zoning/auto_zoning_service.py          ZONE_LIMITS          (23종)
    app/services/permit/building_code_rules.py          ZONE_DEFAULTS        (12종·부분집합)
    app/services/zoning/far_incentive_calculator.py     NATIONAL_FAR_LIMITS  (23종·용적률만)
    app/services/land_intelligence/ordinance_service.py NATIONAL_LIMITS      (21종)
    apps/web/lib/kr-building-regulations.ts             ZONING_DB            (21종)

**오늘은 값이 전부 일치한다**(이 테스트가 그것을 확인한다). 위험은 지금이 아니라
**하나만 고칠 때** 온다 — 이 저장소는 이미 그 형태로 여러 번 데었다
(`#748` 근거 없는 `or 200` · `#760` 틀린 `MAX_FLOORS` · `#763` 법정·조례 혼재).

`legal_zone_limits`(SSOT)로의 이관은 이미 진행 중이고 소비처가 12곳을 넘는다.
그 이관이 끝날 때까지 **남은 사본들이 조용히 갈라지는 것**을 막는 것이 이 파일의 일이다.
표를 지우는 일(리팩토링)은 소비처가 많아 위험이 크고 소유 세션이 여럿이다 —
**락은 싸고 안전하며, 이관이 끝나면 이 파일도 함께 사라진다.**

## ★파서 규율 (실수 #42 의 처방을 코드로)

처음 이 검사를 손으로 돌렸을 때 **"불일치 11종"** 이라는 없는 결함을 만들었다.
표 시작점에서 **고정 길이 창**을 잘랐더니 **바로 아래 지자체 조례 캐시 표**까지 읽어
같은 키가 덮어써졌고, **조례값을 국가 법정값으로** 읽었다.

그래서 이 파일의 파서는:
  1. 경계를 **문법으로** 잡는다 — 중괄호 균형이 0 이 되는 지점까지만.
  2. **자기검사**를 한다 — 표마다 기대 최소 종수와 필수 키를 확인하고, 못 미치면
     **시끄럽게 실패**한다(조용히 적게 읽는 파서가 가장 위험하다).
  3. **판별력을 증명**한다 — 일부러 갈라진 입력을 만들어 비교기가 그것을 **잡는지** 본다.
     대조군이 없으면 "아무것도 안 잡는 비교기"도 초록이 된다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1]
WEB = API.parent / "web"   # apps/api → apps/web

Limits = dict[str, tuple[float | None, float | None]]  # zone -> (bcr, far)


def _balanced_block(text: str, marker: str) -> str:
    """`marker` 이후 **첫 `{` 부터 중괄호 균형이 0 이 되는 `}` 까지**만 돌려준다.

    ★고정 길이 창을 쓰지 않는 이유: 소스에는 같은 모양의 표가 여러 개 붙어 있다
      (`NATIONAL_LIMITS` 바로 아래에 지자체 조례 캐시 표들이 있다). 창이 넘치면
      뒤쪽 표의 같은 키가 앞쪽 값을 **덮어써** 없는 불일치를 만든다(실수 #42).
    """
    i = text.index(marker)
    j = text.index("{", i)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[j : k + 1]
    raise AssertionError(f"{marker}: 중괄호 균형이 닫히지 않는다 — 파서가 파일 끝까지 읽었다")


def _parse_py(block: str) -> Limits:
    out: Limits = {}
    for m in re.finditer(r'"([가-힣0-9]+(?:지역|구역))"\s*:\s*(\{[^}]*\}|[0-9.]+)', block):
        zone, val = m.group(1), m.group(2)
        if val.startswith("{"):
            bcr = re.search(r'"(?:max_bcr|bcr)"\s*:\s*([0-9.]+)', val)
            far = re.search(r'"(?:max_far|far)"\s*:\s*([0-9.]+)', val)
            out[zone] = (float(bcr.group(1)) if bcr else None, float(far.group(1)) if far else None)
        else:  # 용적률만 담는 표(NATIONAL_FAR_LIMITS)
            out[zone] = (None, float(val))
    return out


def _load_py(rel: str, marker: str) -> Limits:
    return _parse_py(_balanced_block((API / rel).read_text(encoding="utf-8"), marker))


def _load_web() -> Limits:
    """프론트 `ZONING_DB` — ★언어가 달라도 같은 법을 말해야 한다.

    FE/BE 가 갈리는 지점이 이 저장소가 반복해 데인 자리라, 이 락은 **언어를 건너뛴다**.
    """
    src = (WEB / "lib/kr-building-regulations.ts").read_text(encoding="utf-8")
    out: Limits = {}
    for m in re.finditer(
        r'name:\s*"([^"]+)"[\s\S]{0,400}?buildingCoverageMax:\s*([0-9.]+)'
        r"[\s\S]{0,200}?floorAreaRatioMax:\s*([0-9.]+)",
        src,
    ):
        out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return out


# (표 이름, 로더, 기대 최소 종수, 반드시 있어야 하는 키)
TABLES: list[tuple[str, object, int, str]] = [
    ("auto_zoning.ZONE_LIMITS", lambda: _load_py("app/services/zoning/auto_zoning_service.py", "ZONE_LIMITS"), 20, "일반상업지역"),
    ("building_code.ZONE_DEFAULTS", lambda: _load_py("app/services/permit/building_code_rules.py", "ZONE_DEFAULTS: dict"), 10, "일반상업지역"),
    ("far_incentive.NATIONAL_FAR_LIMITS", lambda: _load_py("app/services/zoning/far_incentive_calculator.py", "NATIONAL_FAR_LIMITS"), 20, "일반상업지역"),
    ("ordinance.NATIONAL_LIMITS", lambda: _load_py("app/services/land_intelligence/ordinance_service.py", "NATIONAL_LIMITS: dict"), 18, "일반상업지역"),
    ("web.ZONING_DB", _load_web, 18, "일반상업지역"),
]


def _all() -> dict[str, Limits]:
    return {name: loader() for name, loader, _n, _k in TABLES}


# ── ① 파서 자기검사 — 조용히 적게 읽는 파서가 가장 위험하다 ──────────────
@pytest.mark.parametrize(("name", "loader", "min_zones", "must_have"), TABLES)
def test_파서가_표를_실제로_읽었다(name, loader, min_zones, must_have) -> None:
    """★이 단언이 없으면 **0종을 읽고도** 아래 비교가 초록이 된다(공허한 진리)."""
    t = loader()
    assert len(t) >= min_zones, f"{name}: {len(t)}종만 읽었다 — 파서가 표를 놓쳤다"
    assert must_have in t, f"{name}: 대표 키 '{must_have}' 가 없다 — 엉뚱한 블록을 읽었다"
    bcr, far = t[must_have]
    assert far is not None and far > 0, f"{name}: {must_have} 용적률을 못 읽었다"


def test_파서가_인접_조례표를_침범하지_않는다() -> None:
    """★실수 #42 회귀 락 — 조례 캐시 표가 붙어 있는 파일에서 **국가 법정값**만 읽는가.

    `ordinance_service.py` 는 `NATIONAL_LIMITS` **바로 아래**에 지자체 조례 캐시 표들을
    두고 있고, 거기엔 같은 키가 **다른 값**으로 들어 있다(예: 일반상업 800·900).
    창이 넘치면 그 값들이 국가 법정값을 덮어쓴다.
    """
    nat = _load_py("app/services/land_intelligence/ordinance_service.py", "NATIONAL_LIMITS: dict")
    # 국계법 시행령 §85 — 일반상업지역 용적률 상한 1300%. 조례 캐시(800·900 등)를 읽었으면 죽는다.
    assert nat["일반상업지역"] == (80.0, 1300.0), f"조례표를 침범했다: {nat['일반상업지역']}"


# ── ② 본 계약 — 같은 용도지역이면 같은 한도를 말한다 ──────────────────────
def test_다섯_표가_같은_용도지역에_같은_한도를_말한다() -> None:
    """표마다 **담는 범위는 달라도**(부분집합 허용) **담은 값은 같아야 한다**.

    ★값을 고칠 일이 생기면 이 테스트가 **다섯 곳 전부 고치라고** 알려 준다.
      한 곳만 고치는 것이 이 저장소가 반복해 데인 형태다.
    """
    tables = _all()
    zones = sorted({z for t in tables.values() for z in t})
    # 공허한 진리 방지 — 비교 대상이 실제로 있어야 한다.
    assert len(zones) >= 18, f"용도지역이 {len(zones)}종뿐 — 표를 못 읽었다"

    conflicts: list[str] = []
    compared = 0
    for z in zones:
        present = {k: t[z] for k, t in tables.items() if z in t}
        if len(present) < 2:
            continue  # 한 표에만 있는 항목은 대조 대상이 아니다(범위 차이는 허용).
        compared += 1
        for idx in (0, 1):  # 0=건폐율, 1=용적률
            vals = {v[idx] for v in present.values() if v[idx] is not None}
            if len(vals) > 1:
                conflicts.append(
                    f"{z} {'건폐율' if idx == 0 else '용적률'}: "
                    + json.dumps({k: v[idx] for k, v in present.items()}, ensure_ascii=False)
                )
    # ★두 표 이상에 걸친 항목이 충분히 많아야 이 락이 의미를 갖는다.
    assert compared >= 18, f"두 표 이상에 등장한 용도지역이 {compared}종뿐 — 락이 공허하다"
    assert not conflicts, (
        "법정 한도 표가 갈렸습니다. 값을 바꿨다면 **다섯 곳 전부** 고쳐야 합니다"
        " (근거 조문도 함께 적으십시오 — 국계법 시행령 §84 건폐율 / §85 용적률).\n  "
        + "\n  ".join(conflicts)
    )


# ── ③ 대조군 — 이 비교기가 **갈린 것을 실제로 잡는가** ────────────────────
def test_대조군_비교기가_갈린_값을_잡는다() -> None:
    """★"아무것도 안 잡는 비교기"도 초록이 된다 — 판별력을 직접 증명한다.

    실제 표를 하나 복제해 **한 값만** 바꾼 뒤, 같은 비교 규칙이 그것을 집어내는지 본다.
    """
    tables = _all()
    poisoned = {k: dict(v) for k, v in tables.items()}
    # 프론트 표의 일반상업 용적률만 1300 → 999 로 오염시킨다.
    bcr, _far = poisoned["web.ZONING_DB"]["일반상업지역"]
    poisoned["web.ZONING_DB"]["일반상업지역"] = (bcr, 999.0)

    def conflicts_of(ts: dict[str, Limits]) -> list[str]:
        out = []
        for z in {z for t in ts.values() for z in t}:
            present = {k: t[z] for k, t in ts.items() if z in t}
            if len(present) < 2:
                continue
            for idx in (0, 1):
                vals = {v[idx] for v in present.values() if v[idx] is not None}
                if len(vals) > 1:
                    out.append(f"{z}:{idx}")
        return out

    assert conflicts_of(tables) == [], "기준선이 이미 갈려 있다 — 대조군이 성립하지 않는다"
    assert "일반상업지역:1" in conflicts_of(poisoned), "오염시켰는데 비교기가 못 잡는다 — 락이 공허하다"
