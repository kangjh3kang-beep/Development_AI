"""화면이 주장하는 **숫자**가 코드에서 파생되는지 잠근다.

## 왜 (2026-08-27 실측)

사용자 화면(`projects/[id]/feasibility` — 개략수지가 도는 바로 그 페이지)이 3개 언어로
이렇게 주장하고 있었다:

    "15개 개발유형, 38종 세무 알고리즘, **전국 229개 시군구 조례를 실시간 통합 분석**"

실측하니 **셋 중 둘이 근거가 없었다**:

| 주장 | 실제 |
|---|---|
| **229개 시군구** | 조례 정적 캐시 **26** · 상하수도 단가표 **20** · `regions` 테이블 **부재** |
| **38종 세금** | 엔진이 실제로 내는 코드 **32종**(A01–A10·B01–B08·C01–C08·D01–D06) — *2026-08-27 시점* |

★**그 32 도 이미 낡았다(2026-08-27 → 08-28)**. `#913` 이 인입 4종(B05 전기·B06 가스·
B07 통신·B08 소방)을 **부담금에서 공사비로 재분류**하면서 `app/services/tax/` 를 떠나
파생값이 **28** 이 됐다. 실측(같은 방법·다른 커밋으로 조회기 생존 확인):

    0cb731ac~1 (재분류 전) → 32종      df81fc85 (#913) → 28종      origin/main → 28종

**이 락이 그것을 잡았다** — 문구는 「32종」인 채였고 CI 가 6건을 빨갛게 냈다.
★그러니 아래 표의 수치를 **현재 값으로 읽지 마라.** 현재 값은 `_derived_counts()` 가 말한다.
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

#: 주장 문자열이 사는 **구조적 축**(손 목록이 아니라 파생형).
#:
#: ★2026-08-28 — 종전에는 손으로 적은 `CLAIM_KEYS` 2개였고, 이 파일이 스스로
#: *"등록을 강제하는 것은 리뷰다"* 라고 한계를 적어 두었다. **그 한계가 실재 결함을 이미
#: 놓치고 있었다** — `deepIntegration.taxV2.subtitle` 이 3개 언어로 「38종 세금」을
#: 주장하는데 등록이 안 돼 감시 밖이었다(엔진 파생값은 28). 목록은 곧 상한이 된다.
#:
#: 그래서 **축을 선언하고 키는 파생**시킨다. 새 주장 키가 이 축에 생기면 자동으로 감시망에 든다.
CLAIM_SECTIONS: tuple[tuple[str, str], ...] = (
    ("deepIntegration", "subtitle"),
    ("modulePlaceholders", "description"),
)

#: 차원 표기(`2D`·`3D`·`4D`)는 **개수가 아니다** — 숫자 검사 전에 걷어낸다.
#: ★이 면제가 죽으면(대상이 사라지면) `test_dimension_exemption_is_live` 가 실패한다.
#: ★`\b` 를 쓰지 않는다 — `3D建模` 처럼 **한자가 바로 붙으면 경계가 성립하지 않아** 면제가
#:   조용히 죽는다(zh-CN 번역자가 공백을 빼는 순간). 앞뒤로 **숫자·라틴문자만** 배제한다.
_DIMENSION = re.compile(r"(?<![0-9A-Za-z])\d+\s?[Dd](?![A-Za-z0-9])")

#: ★CJK 수사 — `re.findall(r"\d+")` 는 **한자 숫자를 보지 못한다.** 독립 리뷰가 이 통로로
#:   폐기된 「229개 시군구 조례 실시간」 주장을 zh-CN 에 되살렸는데 **19건 전부 초록**이었다.
#:   락 독스트링이 *"언어 무관"* 이라 단언하고 있었으므로 그 단언 자체가 거짓이었다.
#:   판정할 수 없는 표기는 **통과시키지 않고 거부**한다(모르는 것을 초록으로 두지 않는다).
#:   ★단순히 「수사 한 글자라도 있으면 거부」는 **위양성**이다 — `一键计算`(원클릭)·`一体化`·
#:     `下一阶段`(다음 단계)처럼 수사가 **낱말의 일부**인 경우가 흔하다(실측: 전체 1,478
#:     문자열 중 10건). 그래서 **수사 2자 이상 연속** 또는 **수사 + 계수 단위**만 본다.
#:     양성 대조군: `三十八`·`二二九`·`十种` 은 잡히고 `一键`·`一体` 는 안 잡힌다.
#:     ★한계: `十` 단독처럼 계수 단위 없는 한 글자 주장은 여전히 안 보인다(축 안 실측 0건).
_CJK_NUM_CHARS = "〇零一二三四五六七八九十百千万億两"
_CJK_COUNTERS = "种個个項项개종가지단계階阶級级"
_CJK_NUMERAL = re.compile(
    rf"[{_CJK_NUM_CHARS}]{{2,}}|[{_CJK_NUM_CHARS}][{_CJK_COUNTERS}]"
)


def _unbacked_numbers(text: str) -> set[int]:
    """문구가 주장하는 정수 중 **코드에서 파생되지 않은 것**.

    ★`_derived_counts()` 를 **여기 한 자리에서만** 부른다. 종전에는 판정이 테스트 본문에
      인라인돼 있어서, `allowed` 를 리터럴 `{15, 28, 4}` 로 바꾸는 변이가 **19건 전부 초록**으로
      **생존**했다(독립 리뷰 실측). 이 락의 요점이 *"문구를 코드에 결속시키는 것"* 인데
      **결속을 끊어도 아무것도 죽지 않았다** — 변이를 함수 안에만 넣으면 배선은 무잠금이다.
      단일 호출부로 모아야 `test_판정이_파생값에_실제로_실린다` 가 그것을 태울 수 있다.
    """
    allowed = set(_derived_counts().values())
    return {int(n) for n in re.findall(r"\d+", _judgeable(text))} - allowed


def _judgeable(text: str) -> str:
    """숫자 판정에 쓸 문자열 — 차원 표기를 **판정 단계에서도** 걷어낸다.

    ★종전에는 **키를 고를 때만** 걷어내고 판정에서는 안 걷어냈다. 그래서 `3D` 를 품은
      문자열에 **정당한** 개수를 넣으면 락이 **거짓 위반**을 냈다(가드의 위양성도 결함이다).
      면제는 **한 자리**에서만 정의한다.
    """
    return _DIMENSION.sub("", text)
_WEB = pathlib.Path(__file__).resolve().parents[2] / "web" / "public" / "locales"

#: ★로케일도 **파생**한다. 종전에는 손으로 적은 3개였고, 독립 리뷰가 그것을 깼다:
#:   `LOCALES` 를 `("ko",)` 로 줄이면 **빨개지지 않고 단언 8개가 조용히 사라진다**
#:   (수집기 생존 락의 기대값이 `len(LOCALES) * ...` 라 **변이와 함께 줄어든다**).
#:   *"빨강 개수가 아니라 통과 수를 대조하라 — 수집 실패는 조용하다"* 의 정확한 사례.
LOCALES: tuple[str, ...] = tuple(
    sorted(d.name for d in _WEB.iterdir() if d.is_dir() and (d / "common.json").exists())
)


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
    return {
        "development_types": len(dev),
        "tax_codes": len(codes),
        "stage_groups": _stage_groups(codes),
    }


def _stage_groups(codes: set[str]) -> int:
    """「4단계」 = 코드군 머리글자 수(A 취득 · B 부담금 · C 분양 · D 처분).

    ★손으로 4 를 적지 않는다 — 군이 늘면 파생값이 따라 늘어 문구가 여기서 깨진다.
    ★순수 함수로 꺼낸 이유: 리터럴 `4` 로 바꾸는 변이는 **오늘의 코드에서는 A~D 가 마침
      넷이라 잡히지 않는다.** 두 모집단(3군·5군)을 먹여야 그 변이가 죽는다.
    """
    return len({c[0] for c in codes})


def _get(dic: dict, dotted: str):
    cur = dic
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _claim_keys(locale: str = "ko") -> list[str]:
    """축에서 **파생**한다 — 숫자를 주장하는 문자열만 고른다(차원 표기는 개수가 아니다)."""
    data = json.loads((_WEB / locale / "common.json").read_text(encoding="utf-8"))
    keys: list[str] = []
    for section, leaf in CLAIM_SECTIONS:
        for name, node in (data.get(section) or {}).items():
            if not isinstance(node, dict):
                continue
            val = node.get(leaf)
            if isinstance(val, str) and re.search(r"\d", _judgeable(val)):
                keys.append(f"{section}.{name}.{leaf}")
    return sorted(keys)


def _claim_strings() -> list[tuple[str, str, str]]:
    out = []
    for loc in LOCALES:
        data = json.loads((_WEB / loc / "common.json").read_text(encoding="utf-8"))
        for key in _claim_keys():
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
        # 코드군은 A·B·C·D 넷이다. 0/1 이면 파생 정규식이 죽은 것이고,
        # 그때 「4단계」가 조용히 허용되지 않게 하한을 건다.
        assert d["stage_groups"] >= 4, f"코드군 파생 실패: {d}"

    def test_stage_groups_is_derived_not_a_literal(self):
        """★두 모집단 — 리터럴 4 로 바꾸면 여기서 죽는다(상수 단언은 락이 아니다)."""
        assert _stage_groups({"A01", "B01", "C01"}) == 3
        assert _stage_groups({"A01", "B01", "C01", "D01", "E01"}) == 5
        # 같은 군의 코드가 늘어도 군 수는 안 변한다(개수를 세는 게 아니라 군을 센다).
        assert _stage_groups({"A01", "A02", "A03"}) == 1

    def test_claim_keys_are_derived_not_a_hand_list(self):
        """★축에서 파생됐는지 — 손 목록으로 되돌리면 여기서 걸린다."""
        keys = _claim_keys()
        # 하한: 셋은 지금 실재한다(줄면 축이 좁아졌거나 문구가 사라진 것).
        assert len(keys) >= 3, f"★주장 키 파생 실패: {keys}"
        # ★2026-08-28 에 손 목록이 놓쳤던 바로 그 키가 축에 들어오는지.
        assert "deepIntegration.taxV2.subtitle" in keys, (
            f"★손 목록이 놓쳤던 키가 축에서 빠졌다 — 축이 좁아졌다: {keys}"
        )
        for section, leaf in CLAIM_SECTIONS:
            assert any(k.startswith(f"{section}.") and k.endswith(f".{leaf}") for k in keys), (
                f"★축 {section}.*.{leaf} 이 한 건도 안 잡힌다(수집기 사망): {keys}"
            )

    def test_claim_strings_were_actually_found(self):
        found = _claim_strings()
        expected = len(LOCALES) * len(_claim_keys())
        assert len(found) == expected, (
            f"★수집기 사망 — 주장 문자열 {expected}개를 기대했는데 {len(found)}개"
        )
        assert found, "★수집기가 아무것도 못 찾았다"

    def test_dimension_exemption_is_live(self):
        """★죽은 면제를 초록으로 두지 않는다 — 2D/3D/4D 가 실제로 걸러지고 있는가."""
        raw = (_WEB / "ko" / "common.json").read_text(encoding="utf-8")
        hits = _DIMENSION.findall(raw)
        assert hits, (
            "★차원 표기 면제가 죽었다 — 대상이 사라졌으면 면제를 지워라"
            "(면제가 남으면 다음 사람이 '걸러지고 있다'고 오독한다)"
        )
        # 면제가 **과잉**이 아닌지: 개수 주장(28/15)까지 먹으면 락이 무력해진다.
        assert _DIMENSION.sub("", "28종 세금") == "28종 세금"


class TestEveryClaimedNumberIsDerived:
    @pytest.mark.parametrize(("locale", "key", "text"), _claim_strings())
    def test_numbers_in_claim_are_code_derived(self, locale, key, text):
        judgeable = _judgeable(text)
        assert not _CJK_NUMERAL.search(judgeable), (
            f"[{locale}] {key} 에 **한자 수사**가 있다 — 이 락은 아라비아 숫자만 판정할 수 있어 "
            f"그 주장을 **볼 수 없다**(판정 불가를 초록으로 두지 않는다). 문구: {text[:70]}"
        )
        unbacked = _unbacked_numbers(text)
        assert not unbacked, (
            f"[{locale}] {key} 가 코드에 없는 수치를 주장한다: {sorted(unbacked)} "
            f"(파생 가능한 값: {sorted(_derived_counts().values())}) — 문구: {text[:70]}"
        )

    def test_the_check_can_actually_fail(self):
        """★음성 대조군 — 위반을 심어 **잡히는지** 본다(공허한 초록 방지).

        ★리뷰 지적으로 **판정 로직을 인라인 재구현하지 않고** 실제 함수를 태운다 —
          종전에는 재구현이라 본문을 무력화해도 이 대조군이 초록이었다.
        """
        planted = "15개 개발유형, 38종 세무, 전국 229개 시군구 실시간"
        unbacked = _unbacked_numbers(planted)
        assert unbacked, "★검사기 사망 — 옛 문구(38·229)를 심었는데 위반으로 안 잡힌다"
        assert 229 in unbacked and 38 in unbacked

    def test_판정이_파생값에_실제로_실린다(self, monkeypatch):
        """★배선 락 — 파생값을 흔들면 **같은 문구의 판정이 따라 바뀌어야** 한다.

        독립 리뷰가 `allowed` 리터럴 변이로 **19건 전부 초록**을 만들었다. 이름(파생값을
        «부른다»)이 아니라 **값이 실리는지**를 두 모집단으로 본다.
        """
        문구 = "15개 개발유형 x 28종"
        # 모집단 A — 실제 파생값에서는 위반 없음
        assert _unbacked_numbers(문구) == set()
        # 모집단 B — 파생값을 흔들면 **같은 문구가 위반이 된다**
        monkeypatch.setitem(
            __import__("sys").modules[__name__].__dict__,
            "_derived_counts", lambda: {"흔든값": 7},
        )
        assert _unbacked_numbers(문구) == {15, 28}, (
            "★파생값을 바꿨는데 판정이 안 바뀐다 — 판정이 코드에 결속돼 있지 않다"
        )
        # 흔든 값이 **실제로 실리는지**(허용 방향도 함께 — 한쪽만 보면 반쪽이다)
        assert _unbacked_numbers("7개") == set()


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


# ──────────────────────────────────────────────────────────────────────────────
# ★랜딩 페이지 스탯 — **선언은 스스로를 검증하지 않는다**
#
# `WhySection.tsx` 헤더가 *"스탯 수치는 전부 코드베이스에서 실측 검증한 값만 사용
# (무근거 수치 0)"* 이라고 **선언**하고 있었는데, 락이 없어서 재보니 **셋 중 둘이 틀렸다**:
#   · `11` 종 지도 레이어  → 실제 `LAYERS` **12**
#   · `6`  종 AI 리포트    → 실제 `creationProducts` **9**(생성 허브 9번째 카드)
# 게다가 주석이 가리킨 경로마저 틀렸다(`page.tsx` ↔ 실제 `DashboardHome.tsx`).
#
# ★i18n 축과 **다른 매체**다(하드코딩 .tsx). 그래서 축을 넓히지 않고 **여기에 따로** 잠근다.
# ──────────────────────────────────────────────────────────────────────────────
_WEBROOT = pathlib.Path(__file__).resolve().parents[2] / "web"


def _bracketed_array(source: str, anchor: str) -> str:
    """`anchor` 뒤의 `[` 부터 **괄호 균형**으로 배열 본문을 떼어 낸다.

    ★고정 길이 창으로 자르지 않는다 — 이 저장소는 고정 창이 **옆 표를 읽어** 「없는 결함」을
      만든 전례가 있다. 경계는 **문법**으로 정한다.
    """
    m = re.search(anchor, source)
    assert m, f"앵커를 못 찾았다(수집기 사망): {anchor}"
    # ★`index("[", m.start())` 로 찾으면 **타입 표기의 `[]`** 를 집는다
    #   (`const LAYERS: SatongLayer[] = [` → 빈 배열을 떼어 내 개수가 0 이 된다).
    #   실제로 이 락을 처음 쓸 때 그렇게 0 을 얻었고, **대조군(«파생값 > 0»)이 잡았다.**
    #   그래서 앵커가 `= [` 까지 포함하도록 요구하고 그 끝에서 시작한다.
    start = source.index("[", m.end() - 1)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "[":
            depth += 1
        elif source[i] == "]":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"괄호가 닫히지 않았다: {anchor}")


def _landing_stats() -> dict[str, int]:
    """랜딩 스탯이 주장하는 값을 **원천에서 파생**한다."""
    layers = _bracketed_array(
        (_WEBROOT / "components/precheck/SatongMapShell.tsx").read_text(encoding="utf-8"),
        r"\bLAYERS\s*(?::[^=]*)?=\s*\[",
    )
    products = _bracketed_array(
        (_WEBROOT / "components/dashboard/DashboardHome.tsx").read_text(encoding="utf-8"),
        r"const creationProducts\s*(?::[^=]*)?=\s*\[",
    )
    renderers = sorted(
        p.name
        for p in (
            pathlib.Path(__file__).resolve().parents[1] / "app/services/report/render"
        ).glob("*_renderer.py")
    )
    return {
        "map_layers": len(re.findall(r'^\s*id:\s*"', layers, re.M)),
        "creation_products": len(re.findall(r'^\s*routeId:\s*"', products, re.M)),
        "report_formats": len(renderers),
    }


class TestLandingStatsAreDerived:
    def test_수집기가_살아있다(self) -> None:
        """★대조군 — 파생이 죽으면 아래 일치 단언이 «0 == 0» 으로 공허해진다."""
        d = _landing_stats()
        for k, v in d.items():
            assert v > 0, f"★{k} 파생 실패(수집기 사망): {d}"
        # 괄호 균형 파서가 실제로 자르고 있는지(전체 파일을 통째로 반환하지 않는지)
        src = (_WEBROOT / "components/precheck/SatongMapShell.tsx").read_text(encoding="utf-8")
        arr = _bracketed_array(src, r"\bLAYERS\s*[:=]")
        assert 0 < len(arr) < len(src), "★파서가 파일 전체를 반환한다 — 경계가 안 잡혔다"

    def test_랜딩_스탯이_코드와_일치한다(self) -> None:
        why = (_WEBROOT / "components/marketing/WhySection.tsx").read_text(encoding="utf-8")
        주장 = [int(v) for v in re.findall(r'^\s*value:\s*"(\d+)"', why, re.M)]
        assert len(주장) == 3, f"★스탯 카드 3장을 기대했는데 {len(주장)}개 — 수집기 사망"
        d = _landing_stats()
        기대 = [d["map_layers"], d["creation_products"], d["report_formats"]]
        assert 주장 == 기대, (
            f"랜딩 스탯이 코드와 어긋난다 — 화면 {주장} vs 코드 {기대}. "
            "배열이 늘었으면 문구를 함께 고쳐라(수치는 선언이 아니라 파생이다)"
        )
