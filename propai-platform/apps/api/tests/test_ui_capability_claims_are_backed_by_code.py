"""화면이 주장하는 **숫자**가 코드에서 파생되는지 잠근다.

## 왜 (2026-08-27 실측)

사용자 화면(`projects/[id]/feasibility` — 개략수지가 도는 바로 그 페이지)이 3개 언어로
이렇게 주장하고 있었다:

    "15개 개발유형, 38종 세무 알고리즘, **전국 229개 시군구 조례를 실시간 통합 분석**"

실측하니 **셋 중 둘이 근거가 없었다**:

| 주장 | 실제 |
|---|---|
| **229개 시군구** | 조례 정적 캐시 **26** · 상하수도 단가표 **20** · `regions` 테이블 **부재** |
| **38종 세금** | 엔진이 실제로 내는 코드 **32종**(A01–A10·B01–B08·C01–C08·D01–D06) |
| 15개 개발유형 | **15** ✓ (M01–M15) |

★`229` 는 `app/models/tax_regional.py` **독스트링**에만 있고 — 그 파일이 정의하는
`regions` 테이블은 **생성된 적이 없다**(라이브 확인: `relation "regions" does not exist`,
대조군으로 `public` 테이블 **290개**가 조회돼 조회기 생존 증명). 즉 **열거도 파생도 0건**인
숫자가 마케팅 문구로 흘러 3개 언어에 박혀 있었다.

## 이 락이 하는 일 — **언어 무관**

주장 문자열에 등장하는 **모든 정수**가 **코드에서 파생된 값**이어야 한다.
한국어 `개/종`, 영어 `types/codes`, 중국어 `种` 를 각각 정규식으로 상대하지 않는다
(그렇게 하면 언어가 늘 때마다 뚫린다).

★그리고 **코드가 바뀌면 문구가 깨진다** — 개발유형이 16개가 되면 파생값이 `{16, 32}` 가 되어
문구의 `15` 가 여기서 빨개진다. 문구를 **코드에 결속**시키는 것이 이 락의 요점이다.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

#: 사용자에게 **역량(capability)을 수치로 주장**하는 i18n 키.
#: ★새 주장 키가 생기면 여기 등록해야 한다 — 등록을 강제하는 것은 리뷰다(이 락의 한계, 명시).
CLAIM_KEYS: tuple[str, ...] = (
    "modulePlaceholders.feasibility.description",
    "deepIntegration.feasibilityV2.subtitle",
)
LOCALES: tuple[str, ...] = ("ko", "en", "zh-CN")
_WEB = pathlib.Path(__file__).resolve().parents[2] / "web" / "public" / "locales"


def _derived_counts() -> dict[str, int]:
    """코드에서 **파생**한다 — 손으로 적으면 그 숫자가 곧 상한이 된다."""
    api = pathlib.Path(__file__).resolve().parents[1]
    dev = set(re.findall(
        r'"(M\d\d)"',
        (api / "app/services/feasibility/feasibility_service_v2.py").read_text(encoding="utf-8"),
    ))
    codes: set[str] = set()
    for f in (api / "app/services/tax").rglob("*.py"):
        codes |= set(re.findall(r'"code":\s*"([A-D]\d\d)"', f.read_text(encoding="utf-8")))
    return {"development_types": len(dev), "tax_codes": len(codes)}


def _get(dic: dict, dotted: str):
    cur = dic
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _claim_strings() -> list[tuple[str, str, str]]:
    out = []
    for loc in LOCALES:
        data = json.loads((_WEB / loc / "common.json").read_text(encoding="utf-8"))
        for key in CLAIM_KEYS:
            val = _get(data, key)
            if isinstance(val, str):
                out.append((loc, key, val))
    return out


class TestDerivationIsAlive:
    """★대조군 — 파생값·수집기가 죽으면 아래 「위반 0」이 공허해진다."""

    def test_derived_counts_are_plausible(self):
        d = _derived_counts()
        assert d["development_types"] >= 10, f"개발유형 파생 실패: {d}"
        assert d["tax_codes"] >= 20, f"세금코드 파생 실패: {d}"

    def test_claim_strings_were_actually_found(self):
        found = _claim_strings()
        assert len(found) == len(LOCALES) * len(CLAIM_KEYS), (
            f"★수집기 사망 — 주장 문자열 {len(LOCALES) * len(CLAIM_KEYS)}개를 기대했는데 {len(found)}개"
        )


class TestEveryClaimedNumberIsDerived:
    @pytest.mark.parametrize(("locale", "key", "text"), _claim_strings())
    def test_numbers_in_claim_are_code_derived(self, locale, key, text):
        allowed = set(_derived_counts().values())
        numbers = {int(n) for n in re.findall(r"\d+", text)}
        unbacked = numbers - allowed
        assert not unbacked, (
            f"[{locale}] {key} 가 코드에 없는 수치를 주장한다: {sorted(unbacked)} "
            f"(파생 가능한 값: {sorted(allowed)}) — 문구: {text[:70]}"
        )

    def test_the_check_can_actually_fail(self):
        """★음성 대조군 — 위반을 심어 **잡히는지** 본다(공허한 초록 방지)."""
        allowed = set(_derived_counts().values())
        planted = "15개 개발유형, 38종 세무, 전국 229개 시군구 실시간"
        unbacked = {int(n) for n in re.findall(r"\d+", planted)} - allowed
        assert unbacked, "★검사기 사망 — 옛 문구(38·229)를 심었는데 위반으로 안 잡힌다"
        assert 229 in unbacked and 38 in unbacked


class TestRetiredClaimsDoNotReturn:
    """근거 없던 특정 수치가 **어느 로케일에도** 되살아나지 않게."""

    @pytest.mark.parametrize("locale", LOCALES)
    def test_229_is_gone(self, locale):
        raw = (_WEB / locale / "common.json").read_text(encoding="utf-8")
        assert "229" not in raw, f"[{locale}] 근거 없는 '229개 시군구' 주장이 되살아났다"

    def test_positive_control_scanner_reads_the_file(self):
        """★대조군 — 파일을 실제로 읽고 있는지(빈 문자열을 훑고 「없음」이라 하지 않게)."""
        raw = (_WEB / "ko" / "common.json").read_text(encoding="utf-8")
        assert len(raw) > 1000 and "개발유형" in raw, "★스캐너가 파일을 못 읽는다"
