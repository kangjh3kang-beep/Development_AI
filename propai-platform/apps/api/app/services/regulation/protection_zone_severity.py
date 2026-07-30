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
from typing import Any

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

# ── 규제 designation → 실무 메타(조치 한 줄·발목 이유·높이제약 여부). ★키워드를 여기서 다시
#   적지 않는다 — 위 _ZONE_SEVERITY(+_FLIGHT_SAFETY_KW)의 키워드를 **키로 재사용**하고 값만
#   붙인다. 키워드 목록을 두 벌 두는 것(SSOT 이중화)이 이 저장소의 반복 결함이라, 두 표의
#   키 집합 일치는 테스트(test_protection_zone_severity)가 구조적으로 고정한다.
#     action  — 칩/배지용 짧은 실무 조치(예: "군부대 협의")
#     reason  — "무엇이 발목인가" 한 줄(지배 제약 headline 후반부에 그대로 붙는다)
#     height  — 이 지정이 **건축물 높이를 제한**하는가. True인데 플랫폼이 수치를 못 가진 항목은
#               소비처(dominant_constraint)가 "지정됨 — 수치 미보유"로 정직 표기한다.
#               ★수치를 추정해 채우지 않는다(고도지구 조례 수치 룩업 부재 — 별건 티켓).
_ZONE_META: dict[str, dict[str, Any]] = {
    # ── 군사 ──
    "통제보호구역": {"action": "군부대 협의", "reason": "군부대 협의 없이는 건축 불가", "height": False},
    "제한보호구역": {"action": "군부대 협의", "reason": "군부대 협의 후 개발 가능(인허가 기간 증가)", "height": False},
    "방공유도탄기지": {"action": "군부대 협의", "reason": "방공유도탄기지 인접 — 군 협의 없이는 건축 불가", "height": True},
    "방공기지": {"action": "군부대 협의", "reason": "방공기지 인접 — 군 협의 없이는 건축 불가", "height": True},
    "대공방어협조구역": {"action": "고도 협의", "reason": "대공방어 협조 대상 — 건축물 높이 협의 필요", "height": True},
    "군사시설보호": {"action": "군부대 협의", "reason": "군사시설보호구역 — 군부대 협의 없이는 건축 불가", "height": False},
    _FLIGHT_SAFETY_KW: {"action": "고도 협의", "reason": "비행안전구역 — 건축물 높이가 제한됨", "height": True},
    # ── 개발제한·상수원 ──
    "개발제한구역": {"action": "해제·예외 검토", "reason": "개발제한구역(그린벨트) — 신축이 원칙적으로 불가", "height": False},
    "그린벨트": {"action": "해제·예외 검토", "reason": "개발제한구역(그린벨트) — 신축이 원칙적으로 불가", "height": False},
    "상수원보호구역": {"action": "행위제한 확인", "reason": "상수원보호구역 — 개발행위가 원칙적으로 금지됨", "height": False},
    # ── 기타 규제지구·시설 ──
    "폐기물매립시설": {"action": "이격·영향 검토", "reason": "폐기물매립시설 영향권 — 용도·분양성 제약", "height": False},
    "고도지구": {"action": "조례 높이 확인", "reason": "고도지구 — 건축물 높이가 제한되어 용적률 소진이 어려움", "height": True},
    "경관지구": {"action": "경관 심의", "reason": "경관지구 — 높이·형태·색채 심의 대상", "height": False},
    "방화지구": {"action": "내화구조 반영", "reason": "방화지구 — 내화구조 의무로 공사비 상승", "height": False},
}


def zone_keywords() -> tuple[str, ...]:
    """SSOT가 인지하는 규제 키워드 전체(비행안전 특수키 포함) — 표 정합 테스트가 소비."""
    return (*(kw for kw, _sev in _ZONE_SEVERITY), _FLIGHT_SAFETY_KW)


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


def classify(regulation_name: str | None) -> dict[str, Any] | None:
    """규제 designation 이름 → severity + 실무메타 1건. 보호구역/규제지구가 아니면 None.

    반환: {"keyword", "severity", "action", "reason", "height_constraining"}

    부분일치(키워드 in 이름)로 스캔하고, 복수 키워드가 걸리면 **최댓값** severity를 취한다
    (보수적). 동순위면 먼저 매치된 키워드가 이긴다(severity_for의 종전 누적 규칙과 동일 —
    max_severity가 동순위에서 좌항(기존 best)을 보존하므로 첫 매치 우선). 비행안전구역은
    구역번호 granular로 특수처리(_flight_safety_severity)하고 표보다 먼저 스캔한다.

    ★severity_for는 이 함수의 severity만 꺼내 쓴다(스캔 로직 이중화 금지 — 값이 갈리면
    리스크 등급과 조치문구가 서로 다른 규제를 가리키는 거짓 조합이 된다).
    """
    if not regulation_name:
        return None
    n = str(regulation_name).replace(" ", "")
    best_sev: str | None = None
    best_kw: str | None = None
    matched: list[str] = []
    # 비행안전구역 — 구역번호 granular(표보다 먼저 특수처리)
    if _FLIGHT_SAFETY_KW in n:
        best_sev, best_kw = _flight_safety_severity(n), _FLIGHT_SAFETY_KW
        matched.append(_FLIGHT_SAFETY_KW)
    # 손큐레이션 권위표 스캔(최댓값 누적 — 동순위는 기존 best 유지)
    for keyword, sev in _ZONE_SEVERITY:
        if keyword in n:
            matched.append(keyword)
            higher = max_severity(best_sev, sev)
            if higher != best_sev:
                best_sev, best_kw = higher, keyword
    if best_sev is None or best_kw is None:
        return None
    meta = _ZONE_META.get(best_kw) or {}
    return {
        "keyword": best_kw,
        # ★R1 HIGH-1: 매치된 키워드 **전체**를 보존한다. 실제 designation은 개별법 명칭이
        #   합쳐진 한 문자열로 온다("군사기지 및 군사시설 보호구역(비행안전제6구역)"). 최댓값
        #   키워드 하나만 남기면 낮은 쪽이 갖고 있던 정보가 조용히 사라진다 — 실측: 위 문자열은
        #   '군사시설보호'(높음)가 이겨 '비행안전'(height=True)이 버려지고 **높이 상한 블록 자체가
        #   소실**됐다(이 모듈의 핵심 산출물인 "수치 미보유 정직 고지"가 무음 누락).
        "matched": tuple(matched),
        "severity": best_sev,
        "action": meta.get("action"),
        "reason": meta.get("reason"),
        # 높이제약은 **합집합** — 하나라도 높이를 제한하면 높이 제약이다(severity와 달리
        #   "대표 하나"로 접을 수 없는 성질). action/reason은 최댓값 키워드 유지(대표 조치).
        "height_constraining": any(
            bool((_ZONE_META.get(kw) or {}).get("height")) for kw in matched
        ),
        # 높이를 제한한 키워드들 — 소비처가 "무엇 때문에 높이가 걸렸는지" 표기할 수 있게.
        "height_keywords": tuple(
            kw for kw in matched if bool((_ZONE_META.get(kw) or {}).get("height"))
        ),
    }


def severity_for(regulation_name: str | None) -> str | None:
    """규제 designation 이름 → 개발 리스크 severity. 보호구역/규제지구가 아니면 None.

    스캔은 classify()가 단일 소유(부분일치·최댓값·비행안전 granular) — 여기선 severity만 꺼낸다.
    """
    hit = classify(regulation_name)
    return hit["severity"] if hit else None


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
