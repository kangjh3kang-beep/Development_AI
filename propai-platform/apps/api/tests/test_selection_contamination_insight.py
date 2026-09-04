"""선택 오염 관측이 **적재만 되고 아무도 안 보던** 것을 인사이트로 잇는다 (2026-08-24).

배경: `#797` 이 프론트→백엔드 계측 통로를 만들어 `selection_contamination_observation`
이 `platform_events` 에 쌓이기 시작했다. 그런데 `analyzer` 는 **이벤트 타입마다 손으로 쓴
스캐너**만 돌린다(`js_error/api_error` · `verify_issue` · `fallback/llm_call` · latency · quality).
새 타입은 어느 스캐너에도 안 걸려 **수집되지만 영원히 조회되지 않는다** —
이 저장소가 반복해서 데인 *"정의만 하고 소비처 0"* 그대로다. 그 마지막 홉을 잇는다.

★이 파일이 잠그는 것 중 가장 중요한 것은 **정책**이다:
  `multi_region`(원거리 혼합)은 **결함이 아닐 수 있다**. 캠페인이 라이브 실측으로 내린
  결정이 *"막지 말고 고지한다"* 였다(290km 건은 후보지 비교로 보였다).
  severity 를 올리거나 자동조치를 붙이는 순간 **정상 사용이 '고칠 대상'이 된다.**
  그 결정은 주석에만 있으면 다음 사람이 지운다 — 여기서 실행으로 잠근다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.growth import analyzer as az  # noqa: E402


# ── 판정 층 ────────────────────────────────────────────────────────────────
def test_A_깨진_데이터는_1건도_사람이_본다():
    assert az._classify_contamination("malformed", 1) == "warn"


def test_B_원거리_혼합은_저빈도면_알리지_않는다():
    """★위양성 방지 — 후보지 비교 한두 건까지 신고하면 지표가 소음이 된다."""
    assert az._classify_contamination("multi_region", 1) is None
    assert az._classify_contamination("multi_region", 2) is None


def test_C_원거리_혼합은_쌓이면_info_로만_알린다():
    assert az._classify_contamination("multi_region", 3) == "info"


@pytest.mark.parametrize("n", [3, 10, 100, 10_000])
def test_D_정책잠금_multi_region_은_아무리_많아도_info_를_넘지_않는다(n):
    """★캠페인 결정(*"막지 말고 고지한다"*)의 실행 잠금.

    두 모집단이 **다른 값**을 내야 잠금이다 — 같은 입력수에서 malformed 는 warn,
    multi_region 은 info 다. 차가 0이면 배선을 끊어도 결과가 같다.
    """
    assert az._classify_contamination("multi_region", n) == "info"
    assert az._classify_contamination("malformed", n) == "warn"  # 대조 모집단


def test_E_모르는_verdict_는_판정하지_않는다():
    """수집 엔드포인트는 **익명 허용**이라 임의 값이 올 수 있다."""
    assert az._classify_contamination("single_site", 999) is None
    assert az._classify_contamination("<script>", 999) is None
    assert az._classify_contamination("", 999) is None


# ── 배선 층 — 스캐너가 배치에 실제로 등록됐는가 ────────────────────────────
def test_F_스캐너가_analyze_window_에_배선돼_있다():
    """판정이 맞아도 배치가 안 부르면 사용자에게는 아무 일도 일어나지 않는다.

    ★소스 검사이므로 **주석·문자열을 배제하고** 실행되는 줄만 본다
      (주석 처리 변이에 뚫린 전례가 이 저장소에 2회 있다).
    """
    import inspect

    src = inspect.getsource(az.analyze_window)
    live = [
        ln for ln in src.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    calls = [ln for ln in live if "_analyze_selection_contamination(" in ln]
    assert calls, "analyze_window 가 선택 오염 스캐너를 부르지 않는다(배선 끊김)"
    assert any("insights.extend" in ln for ln in calls), (
        "호출은 있는데 결과를 insights 에 넣지 않는다 — 값이 버려진다"
    )


def test_G_narrative_가_verdict_별로_다르게_쓰인다():
    """빈 문자열·기본 폴백(`[sev] type`)으로 새면 사람이 읽을 게 없다."""
    mal = az._rule_narrative({
        "insight_type": "selection_contamination", "severity": "warn",
        "metrics_json": {"verdict": "malformed", "count": 2, "malformed_rows": 7},
    })
    multi = az._rule_narrative({
        "insight_type": "selection_contamination", "severity": "info",
        "metrics_json": {"verdict": "multi_region", "count": 5, "max_spread_km": 15.94},
    })
    assert mal != multi                      # 두 모집단이 다른 글을 낸다
    assert "주소가 아닌 값" in mal
    assert "7행" in mal                       # 실제 수치가 실린다
    assert "15.94km" in multi
    assert "후보지 비교라면 정상" in multi     # ★결정이 사람에게도 전달된다
    for text_ in (mal, multi):
        assert text_ != "[warn] selection_contamination"   # 기본 폴백으로 새지 않음


def test_H_좌표가_없으면_거리_미상으로_쓴다_0이_아니라():
    """★`spread_km=None` 을 0 으로 쓰면 **'붙어 있다'는 거짓**이 된다.

    무좌표 프로젝트가 실재한다(라이브 `ad66982a` 는 13필지 전부 좌표 없음).
    """
    narr = az._rule_narrative({
        "insight_type": "selection_contamination", "severity": "info",
        "metrics_json": {"verdict": "multi_region", "count": 4, "max_spread_km": None},
    })
    assert "미상" in narr
    assert "0km" not in narr


# ── 정책 층 — 자동조치가 붙지 않는다 ───────────────────────────────────────
@pytest.mark.asyncio
async def test_I_자가치유가_이_인사이트에_손대지_않는다():
    """★가장 중요한 잠금.

    `healing_rules._candidate_actions` 는 `recommended_action IN ('heal','none','correct')`
    인 **모든** open 인사이트를 끌어온 뒤 `insight_type` 으로 분기한다. 즉 우리 타입도
    **후보 조회에는 들어온다** — 분기에 걸리지 않아 조치가 안 될 뿐이다.
    누군가 그 if/elif 에 우리 타입을 추가하면 **정상 사용(후보지 비교)을 자동으로
    '고치기' 시작한다.** 그 문을 여기서 잠근다.
    """
    from datetime import UTC, datetime, timedelta

    from app.services.growth import healing_rules as hr

    now = datetime.now(UTC)

    class _Row(tuple):
        pass

    class _Res:
        def __init__(self, rows): self._rows = rows
        def fetchall(self): return self._rows

    calls = {"n": 0}

    class _DB:
        async def execute(self, stmt, params=None):
            calls["n"] += 1
            if calls["n"] == 1:
                # open 인사이트 조회 — 우리 타입 1건만 돌려준다.
                return _Res([_Row((
                    "11111111-1111-1111-1111-111111111111",
                    "selection_contamination", "info",
                    {"verdict": "multi_region", "count": 50, "max_spread_km": 290.33},
                ))])
            return _Res([])   # 이후 이벤트 기반 조회는 전부 비움

    cands = await hr._candidate_actions(_DB(), now)
    assert cands == [], (
        f"선택 오염 인사이트가 자동조치 후보를 만들었다 — 정상 사용(후보지 비교)을 "
        f"기계가 '고치려' 한다: {cands}"
    )
    del timedelta  # noqa: F821 — 임포트 사용 표시용(린트 조용히)


# ── 상수 층 — 만든 상수가 실효 경로에 결속돼 있는가 ────────────────────────
def test_J_임계상수가_L1_자동보정_경로에_등록돼_있다():
    """★상수를 만들고 `_TUNABLE_THRESHOLDS` 에 안 넣으면 그 상수는 **장식**이다.

    이 저장소가 반복한 실수: 값은 정의했는데 소비처가 없어, 되돌려도 테스트가 통과한다.
    """
    assert "contam_malformed_warn_count" in az._TUNABLE_THRESHOLDS
    assert "contam_multi_region_info_count" in az._TUNABLE_THRESHOLDS
    # 프라임 키에도 자동으로 따라 들어가야 한다(파생 — 손으로 센 목록이 아니다).
    assert "threshold.contam_multi_region_info_count" in az._DYNAMIC_PRIME_KEYS


# ── SQL 층 — 방어적 캐스팅이 **런타임 문자열**에서 살아 있는가 ──────────────
def test_K_숫자꼴_정규식이_런타임에_올바르다():
    """★파이썬 이스케이프가 한 번 더 먹으면 정규식이 **조용히** 안 맞는다.

    그러면 `spread_km` 이 숫자여도 캐스팅 분기에 안 들어가 `max_spread_km` 이
    **항상 None** 이 된다 — 지표는 비었는데 테스트는 초록인 형태다.
    소스 텍스트가 아니라 **런타임 문자열**을 본다.
    """
    import re

    pats = re.findall(r"~ '([^']+)'", az._CONTAM_SQL)
    assert pats, "정규식 가드가 SQL 에서 사라졌다 — 임의 문자열이 캐스팅으로 들어간다"
    assert r"^[0-9]+(\.[0-9]+)?$" in pats      # spread_km(소수 허용)
    assert r"^[0-9]+$" in pats                  # malformed_rows(정수)
    # 실제로 그 정규식이 의도대로 동작하는지 파이썬으로 재현(포스트그레와 같은 POSIX 문법 범위).
    dec = re.compile(pats[pats.index(r"^[0-9]+(\.[0-9]+)?$")])
    assert dec.match("15.94") and dec.match("0")
    assert not dec.match("abc") and not dec.match("15.94; DROP TABLE")


def test_L_알려진_verdict_로만_집계한다():
    """익명 수집이라 임의 verdict 가 카디널리티를 늘릴 수 있다."""
    assert "IN ('multi_region','malformed')" in az._CONTAM_SQL


def test_M_윈도우_경계와_이벤트타입이_SQL에_묶여_있다():
    """★대상이 틀리면 위 판정 전부가 공허하다."""
    assert "event_type='selection_contamination_observation'" in az._CONTAM_SQL
    assert ":w0" in az._CONTAM_SQL and ":w1" in az._CONTAM_SQL


# ── 튜너블 결속 층 — 등록한 **그 키**를 판정이 실제로 읽는가 ────────────────
def test_N_판정이_등록된_키를_실제로_읽는다_이름이_갈리면_잡는다():
    """★변이 생존 2건을 메우는 락.

    `_effective_threshold("<이름>", 기본값)` 의 **이름 문자열**을 바꿔도 판정 결과는
    안 바뀐다 — 캐시에 그 키가 없으면 모듈상수 기본값으로 조용히 폴백하기 때문이다.
    그래서 문자열 변이가 **생존**했다. 그런데 이름이 `_TUNABLE_THRESHOLDS` 의 키와
    갈리면 실제 피해가 있다: L1 자동보정은 `threshold.contam_*` 로 **쓰는데**
    판정은 `threshold.<오타>` 를 **읽어** — 보정값이 영원히 소비되지 않는다
    (이 저장소가 반복한 *"정의만 하고 소비처 0"*).

    여기서는 **등록된 키로 캐시를 채우고** 판정이 그 값을 따라 움직이는지 본다.
    이름이 갈리는 순간 이 테스트가 죽는다.
    """
    from app.services.growth import dynamic_config

    dynamic_config.reset_cache()
    try:
        # 기준선 — 기본 임계에서는 2건이면 아직 알리지 않는다.
        assert az._classify_contamination("multi_region", 2) is None

        # ★손으로 문자열을 적지 않는다 — `_TUNABLE_THRESHOLDS` 에서 **파생**시킨다.
        #   그래야 판정과 등록표가 같은 이름을 쓰는지 진짜로 대조된다.
        key = "contam_multi_region_info_count"
        assert key in az._TUNABLE_THRESHOLDS          # 전제(공허 진리 방지)
        dynamic_config._put(f"threshold.{key}", "global", 2)

        assert az._classify_contamination("multi_region", 2) == "info", (
            "L1 자동보정 값이 판정에 반영되지 않았다 — 판정이 읽는 이름과 "
            "_TUNABLE_THRESHOLDS 의 키가 갈렸다(보정값 소비처 0)"
        )

        # malformed 쪽도 같은 방식으로 결속돼 있는지 확인(두 이름 모두 변이 생존이었다).
        mkey = "contam_malformed_warn_count"
        assert mkey in az._TUNABLE_THRESHOLDS
        dynamic_config._put(f"threshold.{mkey}", "global", 99)
        assert az._classify_contamination("malformed", 1) is None, (
            "malformed 임계가 자동보정을 따라가지 않는다 — 이름이 갈렸다"
        )
    finally:
        dynamic_config.reset_cache()
