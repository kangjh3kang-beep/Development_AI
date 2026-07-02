"""SGIS/KOSIS 공공데이터 연동 라이브 시뮬레이션 테스트.

검증 범위(절대 결과 위장 금지 — 실제 실행 출력만 신뢰):
  1) import 스모크: 두 클라이언트가 ImportError 없이 로딩되는가
  2) mock 경로: use_mock=True 시 모델 스키마에 맞는 dict를 반환하는가
  3) 더미키 실API 폴백: use_mock=False + 더미키 시 예외 없이 mock으로 폴백하는가
  4) Pydantic 표준화: 반환 dict가 market_models 모델 검증을 통과하는가

실행: propai-platform 디렉토리에서
  apps/api/.venv/bin/python apps/api/test_integration_sim.py
"""

import asyncio
import os
import sys

# apps 패키지를 import 할 수 있도록 프로젝트 루트(propai-platform)를 경로에 추가.
# __file__ = .../propai-platform/apps/api/test_integration_sim.py 이므로 3단계 상위가 루트.
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from apps.api.app.core.config import settings  # noqa: E402 — sys.path 설정 후 의도적 임포트
from apps.api.app.services.market.market_models import (  # noqa: E402 — sys.path 설정 후 의도적 임포트
    MacroIncomeData,
    MigrationData,
    PopulationData,
)
from apps.api.integrations.kosis_client import KosisClient  # noqa: E402 — sys.path 설정 후 의도적 임포트
from apps.api.integrations.sgis_client import SgisClient  # noqa: E402 — sys.path 설정 후 의도적 임포트

_results: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    """검증 항목 결과를 기록한다."""
    _results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


async def run_simulation() -> bool:
    print("--- Live Simulation Started ---")

    # ── 1. KOSIS ──
    print("\n[KOSIS] 거시 소득 데이터")
    kosis = KosisClient()

    # 1-a. mock 경로
    res_mock = await kosis.get_macro_income_stats("11680", "2022", use_mock=True)
    print("  [KOSIS mock]:", res_mock)
    try:
        MacroIncomeData(**res_mock)
        _check("KOSIS mock → MacroIncomeData 검증", True,
               f"avg_income_10k={res_mock.get('avg_income_10k')}")
    except Exception as e:
        _check("KOSIS mock → MacroIncomeData 검증", False, str(e))

    # 1-b. 더미키 실API 폴백
    old_k_key = getattr(settings, "KOSIS_API_KEY", None)
    settings.KOSIS_API_KEY = "DUMMY_INVALID_KEY"
    try:
        res = await kosis.get_macro_income_stats("11680", "2022", use_mock=False)
        print("  [KOSIS live-fallback]:", res)
        MacroIncomeData(**res)
        _check("KOSIS 더미키 폴백(예외 없이 mock 복귀)", True)
    except Exception as e:
        _check("KOSIS 더미키 폴백(예외 없이 mock 복귀)", False, str(e))
    finally:
        settings.KOSIS_API_KEY = old_k_key

    # ── 2. SGIS ──
    print("\n[SGIS] 인구 이동 / 인구 통계")
    sgis = SgisClient()

    # 2-a. mock 경로(인구 이동)
    mig_mock = await sgis.get_migration_stats("11680", "2022", use_mock=True)
    print("  [SGIS migration mock]:", mig_mock)
    try:
        MigrationData(**mig_mock)
        _check("SGIS migration mock → MigrationData 검증", True,
               f"net_migration={mig_mock.get('net_migration')}")
    except Exception as e:
        _check("SGIS migration mock → MigrationData 검증", False, str(e))

    # 2-b. mock 경로(인구 통계) — age_distribution/household_types 스키마 일치 확인
    pop_mock = await sgis.get_population_stats("11680", "2022", use_mock=True)
    print("  [SGIS population mock]:", pop_mock)
    try:
        PopulationData(**pop_mock)
        _check("SGIS population mock → PopulationData 검증", True,
               f"keys={sorted(pop_mock.get('age_distribution', {}).keys())}")
    except Exception as e:
        _check("SGIS population mock → PopulationData 검증", False, str(e))

    # 2-c. 더미키 실API 폴백
    old_s_key = getattr(settings, "SGIS_CONSUMER_KEY", None)
    old_s_sec = getattr(settings, "SGIS_CONSUMER_SECRET", None)
    settings.SGIS_CONSUMER_KEY = "DUMMY_KEY"
    settings.SGIS_CONSUMER_SECRET = "DUMMY_SEC"
    try:
        res2 = await sgis.get_migration_stats("11680", "2022", use_mock=False)
        print("  [SGIS migration live-fallback]:", res2)
        MigrationData(**res2)
        # 정상 인구통계 경로(스키마 교정분)도 더미키로 호출 → 폴백 검증
        res3 = await sgis.get_population_stats("11680", "2022", use_mock=False)
        print("  [SGIS population live-fallback]:", res3)
        PopulationData(**res3)
        _check("SGIS 더미키 폴백(예외 없이 mock 복귀)", True)
    except Exception as e:
        _check("SGIS 더미키 폴백(예외 없이 mock 복귀)", False, str(e))
    finally:
        settings.SGIS_CONSUMER_KEY = old_s_key
        settings.SGIS_CONSUMER_SECRET = old_s_sec

    # HTTP 클라이언트 정리
    await asyncio.gather(kosis.close(), sgis.close(), return_exceptions=True)

    # ── 최종 판정 ──
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n--- Result: {passed}/{total} PASS ---")
    if passed != total:
        for name, ok, detail in _results:
            if not ok:
                print(f"  FAILED: {name} — {detail}")
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_simulation())
    sys.exit(0 if success else 1)
