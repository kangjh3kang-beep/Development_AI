"""판정률 100% 의 **정의**를 잠근다 — 하한을 낮춰서 달성하는 길을 막는다.

★왜 이 파일이 있는가 (2026-08-27 라이브 실측):
    fallback_rate       judged 0/2   =  0.0%   (하한 10)
    latency_regression  judged 7/23  = 30.4%   (하한 20)
    quality_drop        judged 0/0            (축 자체가 0)

`judged_pct` 는 *"임계로 분류할 수 있었던 비율"* 이라 **트래픽이 적으면 영원히 100% 가 못 된다.**
트래픽이 적은 것은 결함이 아니다(라이브: LLM 호출 자체가 적다).

★그래서 "100%" 를 **하한을 내려서** 달성하려는 시도가 나온다. 그 길은 **기각됐다**:
`threshold_relax` 가 `integrations/base_client.py` 에서 **실제 프로덕션 HTTP 타임아웃을 곱하고**,
`effector_reach.py` 기준 **PRODUCT 에 닿는 유일한 이펙터**다.
표본 n=3 으로 그것을 발화시키면 사용자에게 닿는다.

→ 올바른 정의: **「모든 축이 *무언가를* 말한다」** — 판정이든, 왜 판정 못 하는지든.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_A = (Path(__file__).resolve().parents[1]
      / "app" / "services" / "growth" / "analyzer.py")


def _mod():
    """analyzer 를 **파일 경로로** 불러온다 — DB·앱 임포트 없이 순수 함수만 태운다."""
    assert _A.exists(), f"analyzer 가 없다: {_A}"
    # ★py3.10 에는 `datetime.UTC`(3.11+)가 없다. 런타임(컨테이너·CI)은 3.12 이므로
    #   **코드 결함이 아니라 환경 차이**다. 그 한 가지만 얇게 메워 **락이 실제로 돌게** 한다
    #   — 조용한 skip 은 "잠갔다"와 "안 돌았다"를 구별해 주지 않는다.
    import datetime as _dt
    if not hasattr(_dt, "UTC"):
        # ★`noqa: UP017` — **이 줄이 그 폴리필 자체다.** ruff 는 target-version=py312 라
        #   `_dt.timezone.utc` 를 `_dt.UTC` 로 바꾸라고 하는데, 그 자동수정은
        #   `_dt.UTC = _dt.UTC` **자기참조**가 되어 3.10 에서 AttributeError 로 폴리필을 깬다
        #   (ruff 0.16.3 이 실제로 그 수정을 제안한다 — 도구 출력이 원문보다 옳지 않은 사례).
        _dt.UTC = _dt.timezone.utc  # type: ignore[attr-defined]  # noqa: UP017

    spec = importlib.util.spec_from_file_location("growth_analyzer", _A)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except ImportError as e:
        # ★**환경 차이만** 건너뛴다. 로컬 py3.10 에는 `datetime.UTC`(3.11+)가 없고
        #   컨테이너·CI 는 3.12 다. 그 한 가지 외의 ImportError 는 **진짜 결함**이므로
        #   삼키지 않는다 — 종전엔 `except Exception` 이라 **8건 전부 조용히 skip** 됐고
        #   그것이 "통과"로 읽혔다(#857 에서 내가 잡은 바로 그 함정을 내가 저질렀다).
        if "UTC" not in str(e):
            raise
        pytest.skip(f"py{sys.version_info.major}.{sys.version_info.minor} 에 datetime.UTC 없음 "
                    f"— CI(3.12)에서는 실행된다: {e}")
    return m


def test_락이_이_환경에서_실제로_실행된다():
    """★skip 을 통과로 세지 않기 위한 표지 — **실행 가능성 자체**를 단언한다.

    ★2026-08-27 독립 리뷰가 이 자리의 **거짓 보고**를 잡았다: 종전 표지는
    `py<3.11` 이면 *"이 파일의 락이 하나도 실행되지 않습니다"* 라고 skip 했는데,
    `_mod()` 안의 폴리필 덕에 **8건이 실제로 돌아 통과하고 있었다.** 표지가
    사실의 반대를 말했다 — `#857` 함정을 피하려고 넣은 장치가 같은 함정의 새 서식지가 됐다.

    이제는 **버전과 무관하게** `_mod()` 가 되는지만 본다. 안 되면 `_mod()` 가
    시끄럽게 skip 하거나 raise 한다.
    """
    m = _mod()
    assert hasattr(m, "note_coverage"), "analyzer 를 불러왔는데 note_coverage 가 없다"


class Test판정률정의:
    def test_표본_충분하면_judged_100(self):
        m = _mod(); cov: dict = {}
        m.note_coverage(cov, "ax", judged=5, withheld=0, floor=10)
        assert cov["ax"]["judged_pct"] == 100.0
        assert cov["ax"]["state"] == "judged"

    def test_표본_부족은_judged_0_이되_축이_안_도는_것과_구별된다(self):
        """★핵심 — 표본 부족(`partial`)과 축 정지(`axis_idle`)는 **다른 사실**이다."""
        m = _mod(); cov: dict = {}
        m.note_coverage(cov, "ax", judged=0, withheld=2, floor=10)
        assert cov["ax"]["judged_pct"] == 0.0, "판정 못 했는데 judged_pct 가 0 이 아니다"
        assert cov["ax"]["state"] == "partial"

    def test_judged_pct_가_실제_비율이다(self):
        """★비율이 **값**이어야 한다 — 상수를 싣지 않는다(공허한 지표 방지)."""
        m = _mod(); cov: dict = {}
        m.note_coverage(cov, "ax", judged=1, withheld=9, floor=10)
        assert cov["ax"]["judged_pct"] == 10.0
        cov2: dict = {}
        m.note_coverage(cov2, "ax", judged=9, withheld=1, floor=10)
        assert cov2["ax"]["judged_pct"] == 90.0
        assert cov["ax"]["judged_pct"] != cov2["ax"]["judged_pct"], "입력이 달라도 같은 값 = 상수"

    def test_축이_안_돌면_judged_pct_는_None_이다(self):
        """★★`0.0` 으로 두면 *"판정률 0%"* 가 되어 **축 정지를 결함으로 오독**시킨다 —
        이 PR 이 고치겠다고 선언한 바로 그 혼동이다(독립 리뷰 지적)."""
        m = _mod(); cov: dict = {}
        m.note_coverage(cov, "idle", judged=0, withheld=0, floor=5)
        assert cov["idle"]["judged_pct"] is None, "축 정지인데 0.0 이면 결함으로 읽힌다"
        cov2: dict = {}
        m.note_coverage(cov2, "short", judged=0, withheld=3, floor=5)
        assert cov2["short"]["judged_pct"] == 0.0, "표본 부족은 0.0 이어야 한다"
        assert cov["idle"]["judged_pct"] != cov2["short"]["judged_pct"], "두 모집단이 같은 값"

    def test_소수점_한_자리로_반올림한다(self):
        """★`round(..., 1)` 이 장식이 되지 않게 — 자릿수를 바꾸면 빨개진다."""
        m = _mod(); cov: dict = {}
        m.note_coverage(cov, "ax", judged=1, withheld=2, floor=10)
        assert cov["ax"]["judged_pct"] == 33.3, "한 자리 반올림이 아니다"

    def test_축이_안_도는_것과_표본_부족은_다른_표기(self):
        """★종전엔 둘 다 judged=0 이라 뭉개졌다."""
        m = _mod(); cov: dict = {}
        m.note_coverage(cov, "idle", judged=0, withheld=0, floor=5)
        m.note_coverage(cov, "short", judged=0, withheld=3, floor=5)
        assert cov["idle"]["state"] == "axis_idle"
        assert cov["short"]["state"] == "partial"
        assert cov["idle"]["state"] != cov["short"]["state"], "두 모집단이 같은 값을 낸다"

    def test_기존_키가_사라지지_않는다(self):
        """★소비처가 읽던 키를 지우면 화면이 조용히 빈다(회귀 방지)."""
        m = _mod(); cov: dict = {}
        m.note_coverage(cov, "ax", judged=3, withheld=1, floor=10)
        for k in ("judged", "withheld", "total", "floor"):
            assert k in cov["ax"], f"기존 키 {k} 가 사라졌다"

    def test_coverage_None_이면_아무것도_안_한다(self):
        m = _mod()
        m.note_coverage(None, "ax", judged=1, withheld=0, floor=10)  # 예외 없이 통과


class Test하한불변:
    """★★이 계획이 **하지 않기로 한 것**을 잠근다 — 다음 사람이 100% 를 쉽게 만들려고
    하한을 내리는 것을 기계가 막는다(§계획서 §5 마지막 항목).
    """

    def test_표본_하한이_내려가지_않았다(self):
        m = _mod()
        assert m.FALLBACK_MIN_CALLS == 10, "폴백 하한이 바뀌었다 — n 이 작으면 threshold_relax 가 프로덕션 타임아웃을 곱한다"
        assert m.LATENCY_MIN_SAMPLES == 20, "지연 하한이 바뀌었다"
        assert m.QUALITY_MIN_SAMPLES == 5, "품질 하한이 바뀌었다"

    def test_하한이_실제로_보류를_만든다(self):
        """★상수만 단언하면 **장식**이 된다 — 그 값이 판정에 쓰이는지까지 본다."""
        m = _mod()
        sev_low, _ = m._classify_fallback(fallback=9, total_calls=m.FALLBACK_MIN_CALLS - 1)
        sev_ok, _ = m._classify_fallback(fallback=9, total_calls=m.FALLBACK_MIN_CALLS + 10)
        assert sev_low is None, "하한 미달인데 판정했다"
        assert sev_ok is not None, "하한을 넘겼는데 판정 못 했다 — 대조군 실패"
