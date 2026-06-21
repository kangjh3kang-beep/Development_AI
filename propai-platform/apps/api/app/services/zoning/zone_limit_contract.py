"""용도지역 한도 — 공용 fail-closed 폴백계약(품질감사 '근본 A' 공용해결).

★문제(플랫폼 품질감사 2026-06-21): `solar_envelope._zone_limits`·`comprehensive`·
`far_tier_service`·`permit_validator`·`design_review` 등 6+ 함수가 용도지역(zone)이
미확정/미인식일 때 **무경고로 기본값(250%/100% 등)을 반환**한다. 특히 서브스트링 매칭
`'' in k`가 모든 키에 True가 되어 빈 zone에 엉뚱한 한도를 붙이는 버그가 있다. 결과적으로
근거 없는 한도가 신뢰도 표기 없이 분석 전반에 흘러간다(연면적·층수 과대 등).

★공용 해결(근본 A): 용도지역 한도 조회를 이 단일 계약으로 일원화한다.
  - 권위 출처 = `legal_zone_limits`(ZONE_LIMITS SSOT)·정규화 매칭.
  - ★위임 출처 `normalize_zone_name`이 양방향 부분문자열 매칭이라 '역'·'주거' 같은 짧은
    조각이 임의 용도지역으로 confirmed될 수 있다(자신있게 틀린 답). 이 계약은 매칭 후
    `_is_spurious_match`로 '짧은 진부분문자열 오매칭'을 걸러 fail-closed로 강등한다.
  - zone 미확정/미인식/모호오매칭은 **fail-closed** — 확정 한도(max_*_pct)는 None으로 두고
    `matched=False`·`confidence='fallback'`·`fallback_reason`을 동반한다. 추정 한도가
    필요한 소비자는 `estimated_*_pct`를 '명시적으로' 읽고 추정임을 표기·경고해야 한다.
    즉 '무근거 무경고 폴백'을 구조적으로 차단한다.

소유 세션(site_score/solar_envelope·comprehensive 등)은 자기 함수의 `_zone_limits`/
`ZONE_DEFAULTS` 직접조회를 이 계약 호출로 점진 교체하면 근본 A가 일괄 해소된다.
본 파일은 신규(additive)이며 legal_zone_limits를 read-only로 사용한다(타 파일 무접촉).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.zoning.legal_zone_limits import legal_limits_for

# 표준 용도지역 키의 최소 의미길이. 정제입력이 표준키의 '진부분문자열'인데 이보다 짧으면
# (예: '역'·'주거'·'지역') 모호 오매칭으로 보고 confirmed를 거부한다(서브스트링 false-confirm 차단).
_MIN_ZONE_TOKEN_LEN = 5


def _is_spurious_match(raw_zone: str | None, matched_key: str | None) -> bool:
    """normalize_zone_name의 양방향 부분문자열 매칭이 만든 '짧은 조각 오매칭'인지 판정.

    정확 매칭(정제입력 == 표준키)은 항상 신뢰. 정제입력이 표준키의 '진부분문자열'이고
    길이가 _MIN_ZONE_TOKEN_LEN 미만이면 모호 오매칭으로 간주(예: '주거'→'제1종전용주거지역').
    """
    cleaned = (raw_zone or "").replace(" ", "").strip()
    mk = (matched_key or "").replace(" ", "").strip()
    if not cleaned or not mk:
        return False
    if cleaned == mk:
        return False  # 정확 매칭은 신뢰
    return cleaned in mk and len(cleaned) < _MIN_ZONE_TOKEN_LEN

# 추정(fallback) 한도 — '확정값'이 아니라 소비자가 추정으로 표기할 때만 쓰는 보수적 기본값.
# ★이 값은 max_*_pct(확정)로 절대 새지 않는다. estimated_*_pct로만 노출된다.
_ESTIMATED_BCR_PCT = 60.0
_ESTIMATED_FAR_PCT = 200.0  # 일반주거 통상값(법정 250% 아님 — 보수적 추정).

# 한도 근거 법령키(legal_reference_registry 키와 일치). 확정 매칭 시만 부착.
_CONFIRMED_LEGAL_REF_KEYS = ["bcr_limit", "far_limit", "zone_use"]


@dataclass(frozen=True)
class ZoneLimitResolution:
    """용도지역 한도 조회 결과 — '확정'과 '추정'을 구조적으로 분리한 fail-closed 계약.

    소비자 규칙:
      - matched=True  → max_bcr_pct/max_far_pct(확정값) 사용. legal_ref_keys로 근거 표시.
      - matched=False → max_*_pct는 None(확정값 없음). 추정이 필요하면 estimated_*_pct를
                        '명시적으로' 읽고, fallback_reason과 함께 '추정값(신뢰도 낮음)' 경고.
    """

    zone_type: str | None       # 정규화된 표준 용도지역키(미확정 시 None)
    matched: bool               # 권위 출처(법정표)에서 확정 매칭됐는가
    confidence: Literal["confirmed", "fallback"]
    max_bcr_pct: float | None   # 법정 건폐율 상한(%) — 확정 시만(미매칭 시 None)
    max_far_pct: float | None   # 법정 용적률 상한(%) — 확정 시만(미매칭 시 None)
    fallback_reason: str | None  # 추정(fallback)일 때 사유(미입력/미인식)
    legal_ref_keys: list[str]   # 한도 근거 법령키 — 확정 시만 채움
    estimated_bcr_pct: float | None = None  # 추정 한도(opt-in) — 소비자가 추정으로 표기 시만
    estimated_far_pct: float | None = None
    legal_basis: str | None = None

    @property
    def is_fallback(self) -> bool:
        """추정 폴백 여부 — 소비자가 '추정값' 경고를 띄울지 판단하는 단일 신호."""
        return not self.matched


def resolve_zone_limits(
    zone_type: str | None,
    *,
    far_override_pct: float | None = None,
    bcr_override_pct: float | None = None,
) -> ZoneLimitResolution:
    """용도지역 한도를 fail-closed로 조회한다(공용계약).

    Args:
        zone_type: 용도지역명(표기변형 허용 — 내부에서 normalize_zone_name으로 정규화).
        far_override_pct/bcr_override_pct: 실효 용적률/건폐율 등 '권위 입력값'이 있으면
            그것을 확정값으로 우선한다(예: 조례 실효값). None이면 SSOT 법정표로 조회.

    Returns:
        ZoneLimitResolution — 확정(matched=True)이면 max_*_pct 채움, 미확정(matched=False)이면
        max_*_pct=None + estimated_*_pct(추정) + fallback_reason. 무근거 무경고 폴백 없음.
    """
    legal = legal_limits_for(zone_type)  # SSOT 정규화 매칭(미매칭 시 None — fail-closed)
    # ★서브스트링 false-confirm 차단: 짧은 조각('역'·'주거') 오매칭이면 매칭 무효화(fail-closed).
    if legal and _is_spurious_match(zone_type, legal.get("zone_type")):
        legal = None

    # 1) 권위 입력(실효값)이 있으면 확정으로 채택(법정표 매칭 여부와 무관하게 입력이 우선).
    if far_override_pct is not None or bcr_override_pct is not None:
        lz = legal or {}
        # 부분 입력 시 빠진 한도는 법정표로 보완(둘 다 없으면 None — 소비자 null-check).
        bcr = bcr_override_pct if bcr_override_pct is not None else lz.get("max_bcr_pct")
        far = far_override_pct if far_override_pct is not None else lz.get("max_far_pct")
        # 근거키는 '실제 값이 있는 한도'에만 부착(값 없는 한도에 근거 붙는 모순 방지).
        keys: list[str] = []
        if bcr is not None:
            keys.append("bcr_limit")
        if far is not None:
            keys.append("far_limit")
        if legal:
            keys.append("zone_use")
        return ZoneLimitResolution(
            zone_type=lz.get("zone_type") or (zone_type.strip() if (zone_type and zone_type.strip()) else None),
            matched=True,
            confidence="confirmed",
            max_bcr_pct=bcr,
            max_far_pct=far,
            fallback_reason=None,
            legal_ref_keys=keys,
            legal_basis=lz.get("legal_basis"),
        )

    # 2) SSOT 법정표 확정 매칭.
    if legal:
        return ZoneLimitResolution(
            zone_type=legal.get("zone_type"),
            matched=True,
            confidence="confirmed",
            max_bcr_pct=legal.get("max_bcr_pct"),
            max_far_pct=legal.get("max_far_pct"),
            fallback_reason=None,
            legal_ref_keys=list(_CONFIRMED_LEGAL_REF_KEYS),
            legal_basis=legal.get("legal_basis"),
        )

    # 3) ★fail-closed: zone 미확정/미인식 — 확정 한도 없음(None). 추정값은 opt-in으로만.
    reason = (
        "용도지역 미입력"
        if not (zone_type and zone_type.strip())
        else f"용도지역 미인식('{zone_type.strip()}')"
    )
    return ZoneLimitResolution(
        zone_type=None,
        matched=False,
        confidence="fallback",
        max_bcr_pct=None,
        max_far_pct=None,
        fallback_reason=reason,
        legal_ref_keys=[],
        estimated_bcr_pct=_ESTIMATED_BCR_PCT,
        estimated_far_pct=_ESTIMATED_FAR_PCT,
        legal_basis=None,
    )
