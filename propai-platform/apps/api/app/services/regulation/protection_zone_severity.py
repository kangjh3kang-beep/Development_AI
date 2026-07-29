"""보호구역·규제지구 → 개발 리스크 severity 손큐레이션 권위표(SSOT).

이 모듈은 "규제 designation 이름 → 종합개발 리스크 severity"의 **단일 진실원천**이다.
그간 comprehensive_analysis_service.risk_keywords·regulation_analysis_service._HIGH/_MID·
land_info_service.regulation_map에 **흩어져 서로 다른 값으로 하드코딩**되던 매핑을 여기로
수렴시켜, 한 곳을 고치면 3소비처가 함께 따라오게 한다(전역 전파방지 — CLAUDE.md 버그정책).

★근본원인(라이브 실증): 종합분석이 군사 통제/제한보호·방공기지를 리스크에 저평가했다
(호미곶 통제보호구역+방공기지인데 리스크 "낮음"). risk_keywords 사전에 '통제보호구역·
제한보호구역·방공기지·방공유도탄' 키워드가 **부재**해 규제목록에 있어도 미반영됐다.

★M4 교정(과잉교정 회피 — 계획 §12.3): 리스크를 일괄 "높음"으로 평탄화하지 않는다.
구역별·행위별 **granular**:
  - 통제보호구역 → 높음(개발 극히 제한)
  - 제한보호구역 → 중간(협의개발 가능 — 정상사업을 죽이지 않도록 높음이 아님)
  - 방공기지·방공유도탄기지 → 높음
  - 비행안전구역 → 구역번호별(제1구역/활주로 → 높음, 그 외/외곽 → 보통)
  - 개발제한구역(그린벨트)·상수원보호구역 → 극히 높음(기존 유지, M4 '높음' 하한 이상)
  - 군사시설보호(일반)·대공방어협조구역 → 기존 유지
평탄화는 §3.5가 경고한 과잉교정으로, 협의가능한 제한보호구역의 정상사업을 죽인다.

하이브리드 오라클(계획 §9): 손큐레이션 권위표로 **즉시 착수**(authoritative SSOT로 취급).
이 표는 legal_reference_registry를 **import·재사용하지 않는다**(코드 통합 아님). 값은 여기서
독립 손큐레이션하되, 그 법령키(water_source_protection·military_protection_zone·greenbelt)의
취지와 severity가 어긋나지 않도록 정합만 유지한다(실제 legal_ref 연동은 후속 Wave로 유예).
계산 로직 0 — 순수 문자열 매핑 + 순서비교만(import 부작용 없음).

# TODO(F1c·후속): 이 손큐레이션 권위표에 TTL/owner/review-by 메타와 법제처 MOLEG·
#   국토계획법 별표 API 주기 differential(이탈 행 자동 플래그)이 아직 없다. 법 개정 시
#   양방향 확신오류를 막기 위해 오라클 버전화·상류 변경감지를 후속 Wave에서 배선한다(계획 §11.2).
"""

from __future__ import annotations

from collections.abc import Iterable

# ── severity 정규 사다리(낮음→높음). 소비처의 리스크 등급·불변식 하한비교가 공유하는 단일 순서.
#   '중간'은 '보통'(비행안전 외곽·대공방어)과 '높음'(통제보호·방공) 사이 — 제한보호(협의개발
#   가능)의 자리다. 기존 comprehensive 4등급(낮음/보통/높음/극히 높음)에 '중간'만 additive 삽입.
SEVERITY_ORDER: tuple[str, ...] = ("낮음", "보통", "중간", "높음", "극히 높음")

# ── 손큐레이션 권위표: 규제 키워드 → severity. 부분일치(키워드 in 이름). 한 이름이 복수
#   키워드에 걸리면 severity_for가 **최댓값**을 취한다(보수적·순서 무관). 비행안전구역은
#   구역번호 granular이라 표가 아니라 _flight_safety_severity로 특수처리한다.
_ZONE_SEVERITY: tuple[tuple[str, str], ...] = (
    # ── 군사(군사기지 및 군사시설 보호법) — M4 granular ──
    ("통제보호구역", "높음"),        # 개발 극히 제한(사실상 곤란)
    ("제한보호구역", "중간"),        # 협의개발 가능 — 과잉교정 회피(높음 아님)
    ("방공유도탄기지", "높음"),
    ("방공기지", "높음"),
    ("대공방어협조구역", "보통"),    # 기존 유지(고도 협의 위주)
    ("군사시설보호", "높음"),        # 일반 군사시설보호구역 — 기존 유지
    # ── 개발제한·상수원 — 기존 극히 높음 유지(M4 '높음' 하한 이상, 무회귀) ──
    ("개발제한구역", "극히 높음"),
    ("그린벨트", "극히 높음"),
    ("상수원보호구역", "극히 높음"),
    # ── 기타 규제지구·시설(기존 comprehensive risk_keywords 값 보존 — 무회귀) ──
    ("폐기물매립시설", "보통"),
    ("고도지구", "보통"),
    ("경관지구", "낮음"),
    ("방화지구", "낮음"),
)

# 비행안전구역 트리거(형태: '비행안전구역', '비행안전 제N구역', '비행안전제5구역' 등 공백변형 포함).
_FLIGHT_SAFETY_KW = "비행안전"


def severity_rank(severity: str | None) -> int:
    """severity의 사다리 순위(index). 미상/None/사다리 밖 문자열은 -1(어떤 실하한에도 미달)."""
    if not severity:
        return -1
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return -1


def max_severity(a: str | None, b: str | None) -> str | None:
    """두 severity 중 사다리상 더 높은 쪽. 둘 다 None/미상이면 None."""
    ra, rb = severity_rank(a), severity_rank(b)
    if ra < 0 and rb < 0:
        return None
    return a if ra >= rb else b


def meets_floor(observed: str | None, floor: str | None) -> bool:
    """observed severity가 floor(하한) 이상인가. floor가 None이면 항상 True(제약 없음).

    observed가 None/미상(rank -1)이면 실하한(rank ≥ 0)에 미달로 판정(False) — 보호구역이
    있는데 리스크가 미산출/미상이면 불변식 위반으로 잡는다.
    """
    if floor is None:
        return True
    return severity_rank(observed) >= severity_rank(floor)


def _flight_safety_severity(name_nospace: str) -> str:
    """비행안전구역 severity — 구역번호 granular(M4).

    제1구역(활주로 인접) → 높음. 그 외(제6구역 외곽·번호 미상) → 보통(기존 baseline 유지).
    비행안전구역은 제1~제6구역만 존재하므로 '제1구역'/'활주로' 리터럴로 안전 판별(오탐 없음).
    """
    if "제1구역" in name_nospace or "활주로" in name_nospace:
        return "높음"
    return "보통"


def severity_for(regulation_name: str | None) -> str | None:
    """규제 designation 이름 → 개발 리스크 severity. 보호구역/규제지구가 아니면 None.

    부분일치(키워드 in 이름)로 스캔하고, 복수 키워드가 걸리면 **최댓값** severity를 돌려준다
    (보수적). 비행안전구역은 구역번호 granular로 특수처리(_flight_safety_severity).
    """
    if not regulation_name:
        return None
    n = str(regulation_name).replace(" ", "")
    best: str | None = None
    # 비행안전구역 — 구역번호 granular(표보다 먼저 특수처리)
    if _FLIGHT_SAFETY_KW in n:
        best = max_severity(best, _flight_safety_severity(n))
    # 손큐레이션 권위표 스캔(최댓값 누적)
    for keyword, sev in _ZONE_SEVERITY:
        if keyword in n:
            best = max_severity(best, sev)
    return best


def is_protection_zone(regulation_name: str | None) -> bool:
    """이름이 (개발 리스크를 유발하는) 보호구역/규제지구로 SSOT에 인지되는가."""
    return severity_for(regulation_name) is not None


def risk_floor_for_regulations(
    regulations: Iterable[str] | None,
) -> tuple[str | None, str | None]:
    """규제 이름 목록 → (종합 리스크 하한 severity, 그 하한을 만든 대표 규제명).

    목록 중 보호구역/규제지구로 인지되는 것들의 severity **최댓값**을 하한으로 돌려준다.
    보호구역이 하나도 없으면 (None, None). 불변식(cross_field)이 이 하한과 산출 리스크를
    대조해 미달 시 finding을 낸다.
    """
    floor: str | None = None
    driver: str | None = None
    for raw in regulations or []:
        sev = severity_for(raw)
        if sev is None:
            continue
        higher = max_severity(floor, sev)
        if higher != floor:
            floor = higher
            driver = str(raw)
    return floor, driver
