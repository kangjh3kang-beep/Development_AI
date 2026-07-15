"""성장루프 표면(사용자 대면 분석 표시 엔드포인트) SSOT 매니페스트 + 배선 검증.

왜 필요한가: 프론트 피드백(👍/👎)은 응답 최상위 `ledger_hash`(원장 sha256)를 조인키로 서버에
보낸다. 표시 엔드포인트가 자신의 분석 결과를 원장에 적재(record_user_analysis/append)하고 그
해시를 응답에 노출해야, few-shot 큐레이션의 등가조인(learning_loop.curate_few_shot)이 성립한다.
과거 적대리뷰가 "emit(적재) / read(조인) 양단 disjoint"를 HIGH 로 적발했고(PR#199 폐합), 그 뒤
표면이 늘 때마다 배선이 누락될 위험이 재발한다.

이 매니페스트는 "성장루프 표면 11개"(PR#199 폐합 정본)를 **체크인 SSOT** 로 고정하고,
`verify_surface_wiring` 이 각 표면 소스에 (a)원장 write 경로 + (b)`ledger_hash` 노출이 실제로
존재함을 정적 증거로 확인한다. 신규 표시 엔드포인트를 만들면 이 목록에 추가하라 → 배선 누락 시
게이트 테스트(tests/test_wpj_growth_surfaces.py)가 즉시 실패해 전역 disjoint 재발을 구조적으로
막는다(전역 전파방지·기존 규약 "표시엔드포인트=record_user_analysis").

정적 검증인 이유: 라우터 모듈을 import 하면 무거운 앱 의존(FastAPI·DB·LLM)이 끌려와 CI 가
불안정해진다. 표면 배선은 소스에 존재하는 **불변 계약**(analysis_type 문자열·헬퍼 호출)이라
소스 텍스트 증거로 확인하는 편이 결정적이고 인프라 무관하다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 이 파일: apps/api/app/services/growth/growth_surfaces.py → parents[3] = apps/api 루트.
API_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class GrowthSurface:
    """성장루프 표면 1건의 배선 계약(정적 검증 대상)."""

    key: str  # 표면 식별자(대개 원장 analysis_type)
    source: str  # 배선 소스 파일(apps/api 기준 상대경로)
    endpoint: str  # 사용자 대면 엔드포인트(문서·추적용)
    analysis_type: str | None  # 원장 적재 analysis_type(파이프라인은 cost/feasibility 복합 → None)
    # 원장 write 경로 증거(any 매칭) — 기본은 공용 기록기 record_user_analysis.
    write_markers: tuple[str, ...] = ("record_user_analysis",)
    # ledger_hash 노출 증거(any 매칭) — attach/extract 헬퍼나 직접 필드 세팅 모두 이 문자열을 포함.
    hash_markers: tuple[str, ...] = ("ledger_hash",)


# ★성장루프 표면 11개 — PR#199 폐합 정본(cost_overview·avm·pricing_suggest·permit_ai·regulation·
#   desk_appraisal·pipeline/run·market_report·esg_lca·digital_twin·investor_report). 각 표면은
#   원장 적재 + ledger_hash 노출로 성장루프(생성→피드백→큐레이션)에 편입된다.
GROWTH_LOOP_SURFACES: tuple[GrowthSurface, ...] = (
    GrowthSurface("cost_overview", "app/routers/cost.py",
                  "POST /api/v1/cost/overview", "cost_overview"),
    GrowthSurface("avm", "routers/avm.py",
                  "POST /api/v1/avm/estimate", "avm"),
    GrowthSurface("pricing_suggest", "app/api/endpoints/sales/actions.py",
                  "POST /api/v1/sales/.../pricing-suggest", "pricing_suggest"),
    GrowthSurface("permit_ai", "routers/permits.py",
                  "POST /api/v1/permits/ai-analysis", "permit_ai"),
    GrowthSurface("regulation", "routers/regulation.py",
                  "POST /api/v1/regulation/analyze", "regulation"),
    GrowthSurface("desk_appraisal", "app/routers/land_price.py",
                  "POST /land-price/desk-appraisal", "desk_appraisal"),
    # 파이프라인은 cost/feasibility 를 각각 원장에 적재하고 대표 해시를 ledger_hash 로 노출한다
    # (단일 analysis_type 이 아니므로 analysis_type=None + write 마커를 파이프라인 기록기로 지정).
    GrowthSurface("pipeline_run", "app/routers/pipeline.py",
                  "POST /api/v2/pipeline/run", None,
                  write_markers=("_record_pipeline_ledger", "append_analysis"),
                  hash_markers=("ledger_hash",)),
    GrowthSurface("market_report", "routers/market_report.py",
                  "POST /api/v1/market/report", "market_report"),
    GrowthSurface("esg_lca", "app/routers/esg.py",
                  "POST /api/v1/esg/lca", "esg_lca"),
    GrowthSurface("digital_twin", "routers/digital_twin.py",
                  "POST /api/v1/digital-twin/interpret", "digital_twin"),
    GrowthSurface("investor_report", "routers/reports.py",
                  "POST /api/v1/reports/investor/generate", "investor_report"),
)


def _read_source(surface: GrowthSurface, *, base: Path | None = None) -> str:
    """표면 소스 파일 텍스트(없으면 빈 문자열 — check 에서 exists=False 로 드러남)."""
    path = (base or API_ROOT) / surface.source
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 — 파일 부재/읽기실패는 미배선(exists=False)로 수렴.
        return ""


def check_surface(surface: GrowthSurface, *, base: Path | None = None) -> dict:
    """단일 표면의 배선 증거를 정적 확인한다.

    반환: {wired, exists, has_write, has_hash, has_type}.
      wired = 소스존재 AND 원장 write 증거 AND ledger_hash 노출 증거 AND (analysis_type 일치 or None).
    """
    src = _read_source(surface, base=base)
    exists = bool(src)
    has_write = any(m in src for m in surface.write_markers)
    has_hash = any(m in src for m in surface.hash_markers)
    has_type = surface.analysis_type is None or f'analysis_type="{surface.analysis_type}"' in src
    return {
        "wired": exists and has_write and has_hash and has_type,
        "exists": exists,
        "has_write": has_write,
        "has_hash": has_hash,
        "has_type": has_type,
    }


def verify_surface_wiring(*, base: Path | None = None) -> dict[str, dict]:
    """전 성장루프 표면의 배선 상태를 반환한다(게이트 테스트·헬스 표기용). {key: check dict}."""
    return {s.key: check_surface(s, base=base) for s in GROWTH_LOOP_SURFACES}


def unwired_surfaces(*, base: Path | None = None) -> list[str]:
    """배선 누락 표면 키 목록. 게이트: 이 목록이 비어야 11/11 배선(성장루프 폐합)."""
    return [k for k, v in verify_surface_wiring(base=base).items() if not v["wired"]]


__all__ = [
    "GrowthSurface",
    "GROWTH_LOOP_SURFACES",
    "check_surface",
    "verify_surface_wiring",
    "unwired_surfaces",
    "API_ROOT",
]
