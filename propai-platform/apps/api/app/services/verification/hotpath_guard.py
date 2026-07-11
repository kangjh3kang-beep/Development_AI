"""법정초과 경량 핫패스 가드 — check_against_legal 공용 래퍼(★A-3/G8, additive).

배경: legal_zone_limits.check_against_legal(법정/조례/계획 3단 근거기반 초과판정)이
comprehensive_analysis_service.analyze()의 P0-3에서만 핫패스로 배선되어 있었다(다른
분석 라우터·엔진은 실효 건폐율/용적률을 응답에 실으면서도 무가드). 이 모듈은 그 P0-3
패턴을 그대로 추출한 공용 헬퍼다 — 새 판정 로직 없음(산식복제 0), check_against_legal을
그대로 호출하고 결과를 표준 계약(additive integrity_warnings)으로 부착만 한다.

무날조 원칙: 값 자체를 클램프(강제로 법정상한에 맞춰 깎기)하지 않는다. 초과가 검출되면
"정직 경고"만 additive로 얹고, high(위반 근거 미확인) 등급이면 표시블록의 confidence를
"degraded"로 강등해 신뢰도만 낮춘다. 가드 실패는 무해 no-op(그레이스풀 — 기존 분석 무손상).
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


def apply_legal_hotpath_guard(
    result: dict[str, Any],
    *,
    zone_type: str | None,
    bcr_pct: float | None,
    far_pct: float | None,
    regulation_payload: Any = None,
    plan_payload: Any = None,
    confidence_target: dict[str, Any] | None = None,
    legal_far_pct: float | None = None,
    legal_bcr_pct: float | None = None,
    tolerance_pct: float = 0.5,
) -> list[dict[str, Any]]:
    """실효 건폐율/용적률을 법정초과 경량 가드(check_against_legal)로 검증해 additive 부착.

    comprehensive_analysis_service의 P0-3(RC6) 패턴을 표준화한 공용 헬퍼 — 분석 표면마다
    같은 3줄(호출 → integrity_warnings 부착 → high면 confidence 강등)을 복제하지 않도록 한다.

    Args:
        result: 가드 결과(integrity_warnings)를 additive로 부착할 대상 dict(응답 본체 등).
            기존 키는 절대 변경/삭제하지 않는다 — "integrity_warnings" 키만 추가한다.
        zone_type: 용도지역명(정규화 전). 블렌디드 표면에선 dominant_zone(대표/우세 용도) —
            legal_*_pct override가 주어지면 임계값 산정엔 쓰이지 않고 라벨(근거 문구)에만 쓰인다.
        bcr_pct: 검증 대상 건폐율(%) — 블렌디드 표면에선 면적가중 blended_bcr_eff_pct.
        far_pct: 검증 대상 용적률(%) — 블렌디드 표면에선 면적가중 blended_far_eff_pct.
        regulation_payload: 조례/규제분석 페이로드(applicable_limits_for 적용값 산정용).
        plan_payload: 도시·군관리계획/지구단위계획 페이로드(상한용적률 최우선 근거).
        confidence_target: high 등급 검출 시 confidence="degraded"+confidence_note를 부착할
            표시블록(dict). None이면 신뢰도 강등은 생략(경고만 부착).
        legal_far_pct / legal_bcr_pct: ★블렌디드(면적가중) 표면 전용 override(additive) — 지정
            시 zone_type의 단일 법정상한(check_against_legal 내부 legal_limits_for 조회) 대신
            이 값(예: blended_far_legal_pct — 같은 면적가중 법정 블렌드)과 비교한다.
            근거(QA MEDIUM 수정): 정당한 혼합용도(예: 2종일반 250%+준주거 400% 블렌드 290%)는
            각 필지 eff≤legal(자기 zone 기준)이 성립하므로 그 면적가중 평균인 eff블렌드≤legal
            블렌드가 구조적으로 보장된다. 단일 zone(dominant)의 법정상한과 비교하면 정당한
            블렌드도 초과로 오탐(false "high")해 정직 경고가 늑대소년이 된다. legal_*_pct
            override로 비교 기준을 같은 블렌드 계층으로 맞추면 오탐은 사라지고, 진짜 오염
            (eff블렌드>legal블렌드 — 예: P0-1 이전 zone 미매칭 하드코딩 폴백 재발)은 여전히
            검출된다(법정 블렌드 자체가 이미 zone 미매칭 필지를 배제·가중하므로 오염은
            legal_*_pct에 희석되지 않는다). 둘 다 None(기본)이면 기존 동작(zone_type 단일
            법정상한 비교) 무회귀 — comprehensive·precheck·단일필지 /zoning/analyze 등
            단일 zone 표면은 이 파라미터를 전달하지 않는다.
        tolerance_pct: 반올림 오차 허용폭(%p). check_against_legal 기본값(0.5)과 동일 기본.

    Returns:
        검출된 issues 리스트(severity: high|warn|info). 없음·가드 실패 시 빈 리스트.
        호출부가 별도 판단(예: 자체 로깅)에 재사용할 수 있도록 그대로 반환한다.
    """
    try:
        if legal_far_pct is not None or legal_bcr_pct is not None:
            issues = _check_against_blended_legal(
                zone_type, bcr_pct=bcr_pct, far_pct=far_pct,
                legal_bcr_pct=legal_bcr_pct, legal_far_pct=legal_far_pct,
                tolerance_pct=tolerance_pct,
                regulation_payload=regulation_payload, plan_payload=plan_payload,
            )
        else:
            from app.services.zoning.legal_zone_limits import check_against_legal

            issues = check_against_legal(
                zone_type,
                bcr_pct=bcr_pct, far_pct=far_pct, tolerance_pct=tolerance_pct,
                regulation_payload=regulation_payload, plan_payload=plan_payload,
            )
        if issues:
            result["integrity_warnings"] = issues
            # 값은 그대로 두고 신뢰 강등 라벨만 부착(정직 표기 — 클램프 금지).
            if confidence_target is not None and any(i.get("severity") == "high" for i in issues):
                confidence_target["confidence"] = "degraded"
                confidence_target["confidence_note"] = (
                    "법정상한 초과 + 완화근거 미확인 — integrity_warnings 참조."
                )
        return issues
    except Exception as e:  # noqa: BLE001 — 가드 실패는 무손상(기존 분석 유지)
        logger.warning("법정초과 가드 스킵(graceful)", err=str(e)[:160])
        return []


def _check_against_blended_legal(
    zone_type: str | None,
    *,
    bcr_pct: float | None,
    far_pct: float | None,
    legal_bcr_pct: float | None,
    legal_far_pct: float | None,
    tolerance_pct: float,
    regulation_payload: Any,
    plan_payload: Any,
) -> list[dict[str, Any]]:
    """블렌디드(면적가중) 표면 전용 판정 — check_against_legal의 근거판정(_judge_excess)을
    그대로 재사용하되(산식복제 0), 비교 기준(threshold)만 zone_type 단일 법정상한 대신
    legal_far_pct/legal_bcr_pct(면적가중 법정 블렌드)로 교체한다.

    check_against_legal 자체는 손대지 않는다(직접 테스트 계약 보호 — 단일 zone 표면은
    그 함수를 그대로 계속 호출한다). has_basis·plan_ceiling 산정 로직은 check_against_legal
    본문과 동일(복제 아님 — 같은 판정 재료를 여기서도 그대로 조립).
    """
    from app.services.zoning.legal_zone_limits import (
        _has_relaxation_basis,  # noqa: SLF001 — check_against_legal과 동일 판정 재사용(복제 방지)
        _is_non_incentive_zone,  # noqa: SLF001
        _judge_excess,  # noqa: SLF001
        applicable_limits_for,
        normalize_zone_name,
    )

    zone = normalize_zone_name(zone_type) or (zone_type or "혼합 용도지역(면적가중 블렌드)")
    non_incentive = _is_non_incentive_zone(zone)

    has_basis = (
        (_has_relaxation_basis(regulation_payload) if regulation_payload is not None else False)
        or (_has_relaxation_basis(plan_payload) if plan_payload is not None else False)
    )
    plan_far_ceiling: float | None = None
    plan_bcr_ceiling: float | None = None
    if regulation_payload is not None or plan_payload is not None:
        applied = applicable_limits_for(
            zone_type, regulation_payload=regulation_payload, plan_payload=plan_payload)
        if applied:
            plan_far_ceiling = applied.get("plan_far_pct")
            plan_bcr_ceiling = applied.get("plan_bcr_pct")
            if applied.get("ordinance_confirmed") or plan_far_ceiling is not None or plan_bcr_ceiling is not None:
                has_basis = True

    issues: list[dict[str, Any]] = []
    if bcr_pct is not None and legal_bcr_pct is not None and bcr_pct > legal_bcr_pct + tolerance_pct:
        issues.append(_judge_excess(
            "건폐율(면적가중 블렌드)", bcr_pct, legal_bcr_pct, zone, has_basis, non_incentive,
            plan_ceiling=plan_bcr_ceiling))
    if far_pct is not None and legal_far_pct is not None and far_pct > legal_far_pct + tolerance_pct:
        issues.append(_judge_excess(
            "용적률(면적가중 블렌드)", far_pct, legal_far_pct, zone, has_basis, non_incentive,
            plan_ceiling=plan_far_ceiling))
    return issues
