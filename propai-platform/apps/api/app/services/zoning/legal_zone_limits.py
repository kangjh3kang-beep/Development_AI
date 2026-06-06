"""용도지역별 법정 건폐율/용적률 상한 SSOT(Single Source of Truth).

근거: 국토의 계획 및 이용에 관한 법률 시행령
- 제84조(용도지역 안에서의 건폐율)
- 제85조(용도지역 안에서의 용적률)
※ 시행령은 용적률에 범위(예: 자연녹지 50~100%)를 두며, 구체 수치는 지자체 조례로 정한다.
  본 표는 '법정 상한(국토계획법 시행령 최대치)'을 SSOT로 보유한다. 조례 가감은 별도 데이터
  (local_ordinance)로 처리하며, 이 표의 값을 초과하는 임의 수치는 할루시네이션으로 간주한다.

실제 데이터 원본(ZONE_LIMITS)은 auto_zoning_service에 있고, 본 모듈은 그 표를 SSOT로
재노출하며 '용도지역명 → 법정 상한' 결정론 조회 헬퍼를 제공한다(검증기·그라운딩 공용).
"""

from __future__ import annotations

from typing import Any

# 데이터 원본(SSOT). auto_zoning_service.ZONE_LIMITS를 단일 출처로 사용.
from app.services.zoning.auto_zoning_service import ZONE_LIMITS

# 법정 출처 주석(그라운딩/배지 표기에 사용)
LEGAL_BASIS = "국토계획법 시행령 제84·85조(용도지역별 건폐율·용적률 상한)"

# ── 인센티브(완화) 근거 신호 ──
# 법정 상한은 '기본값'이며 아래 합법적 인센티브로 상향될 수 있다. 페이로드(source/output)에
# 이 키워드 또는 구조화 필드가 존재하면 '근거 있음'으로 보고 법정초과를 무조건 fail 하지 않는다.
RELAXATION_KEYWORDS: tuple[str, ...] = (
    "기부채납", "기부체납", "공공기여",
    "친환경", "녹색건축", "제로에너지", "신재생",
    "역세권", "시프트", "장기전세", "청년주택", "활성화",
    "공공임대", "임대주택",
    "지구단위계획", "상한용적률", "허용용적률",
    "종상향", "완화", "인센티브",
)
# 구조화 필드명(완화근거/완화율). 값이 truthy면 근거로 인정.
RELAXATION_FIELDS: tuple[str, ...] = (
    "relaxation", "incentive", "incentives",
    "완화근거", "완화율", "relaxation_ratio_pct", "relaxation_basis",
    "donation_ratio_pct", "far_incentive",
)
# 합리성 절대 상한 배수: 근거가 있어도 법정×이 배수를 초과하면 '완화 상한 초과 가능성' warn.
# 거짓양성 최소화를 위해 관대하게(보수적으로 너그럽게) 2.0배.
SANITY_MULTIPLIER: float = 2.0
# 인센티브 적용대상이 사실상 아닌 용도지역(녹지·관리·농림·자연환경보전 등).
# 이 지역에서 법정×2 같은 극단 초과는 근거가 있어도 sanity warn, 근거가 없으면 high 유지.
_NON_INCENTIVE_ZONE_TOKENS: tuple[str, ...] = (
    "녹지", "관리지역", "농림", "자연환경보전",
)


def _has_relaxation_basis(payload: Any) -> bool:
    """페이로드(중첩 dict/list)에서 완화근거 신호(키워드/구조화 필드)를 탐색."""
    if isinstance(payload, dict):
        for f in RELAXATION_FIELDS:
            v = payload.get(f)
            if v:  # truthy(비어있지 않은 dict/list/숫자>0/비공백 문자열)
                if isinstance(v, str) and not v.strip():
                    continue
                return True
        for v in payload.values():
            if _has_relaxation_basis(v):
                return True
        return False
    if isinstance(payload, list):
        return any(_has_relaxation_basis(v) for v in payload)
    if isinstance(payload, str):
        return any(kw in payload for kw in RELAXATION_KEYWORDS)
    return False


def _is_non_incentive_zone(zone: str) -> bool:
    """인센티브 적용대상이 사실상 아닌 용도지역(자연녹지 등)인지 판정."""
    return any(tok in zone for tok in _NON_INCENTIVE_ZONE_TOKENS)


def normalize_zone_name(raw_zone: str | None) -> str | None:
    """용도지역명(공백/표기변형 포함)을 ZONE_LIMITS 표준 키로 정규화.

    정확 일치 → 부분 일치 순으로 매칭한다. 매칭 실패 시 None.
    """
    if not raw_zone:
        return None
    key = str(raw_zone).replace(" ", "").strip()
    if not key:
        return None
    if key in ZONE_LIMITS:
        return key
    # 부분 일치: 가장 구체적(긴) 키 우선으로 매칭하여 '주거지역' 같은 광의 매칭을 줄인다.
    for zone in sorted(ZONE_LIMITS, key=len, reverse=True):
        if zone in key or key in zone:
            return zone
    return None


def legal_limits_for(zone_type: str | None) -> dict[str, Any] | None:
    """용도지역명에 대한 법정 건폐율/용적률 상한을 반환.

    Returns:
        {"zone_type": 표준키, "max_bcr_pct": int, "max_far_pct": int,
         "max_height_m": int|None, "legal_basis": str} 또는 미매칭 시 None.
    """
    key = normalize_zone_name(zone_type)
    if key is None:
        return None
    limits = ZONE_LIMITS.get(key)
    if not limits:
        return None
    return {
        "zone_type": key,
        "max_bcr_pct": limits.get("max_bcr"),
        "max_far_pct": limits.get("max_far"),
        "max_height_m": limits.get("max_height_m"),
        "legal_basis": LEGAL_BASIS,
    }


def _judge_excess(
    label: str,
    value: float,
    max_legal: float,
    zone: str,
    has_basis: bool,
    non_incentive_zone: bool,
) -> dict[str, Any]:
    """법정 상한 초과값 1건에 대한 근거기반 3단 판정.

    수치(초과량)가 아니라 '근거(basis)'로 severity를 정한다.
    - 근거 없음 → high(할루시네이션 의심).
    - 근거 있음 → info(정당한 완화 가능성). 단 sanity(법정×배수) 초과면 warn.
    - 인센티브 비대상 용도지역에서 sanity 초과는 근거가 있어도 warn,
      근거가 없으면 high(원 사고 재현 방지)로 격상.
    """
    over_sanity = value > max_legal * SANITY_MULTIPLIER + 0.5

    if not has_basis:
        # 근거 없음: 법정초과는 할루시네이션 의심으로 적발.
        return {
            "type": "법정한도초과",
            "claim": f"{label} {value:g}%",
            "severity": "high",
            "note": (
                f"{zone} 법정 {label} 상한은 {max_legal:g}%({LEGAL_BASIS}). "
                f"제시값 {value:g}%는 상한 초과 + 완화근거(기부채납/친환경/역세권/공공임대/"
                f"지구단위계획 등) 미제시 — 할루시네이션 의심, 근거 확인 필요. "
                f"법정값 {max_legal:g}% 적용 권고."
            ),
        }

    # 근거 있음.
    # 인센티브 비대상 용도지역(자연녹지 등)은 완화근거가 있어도 적용대상이 아닐 개연성이
    # 높으므로 info로 통과시키지 않고 warn(재확인)으로 둔다(과도한 상향 거짓음성 방지).
    if over_sanity or non_incentive_zone:
        # 합리성 절대 상한(법정×배수) 초과 또는 인센티브 비대상 용도지역
        # — 근거가 있어도 재확인 필요(관대하게 warn).
        sev = "warn"
        extra = ""
        if over_sanity:
            extra += (
                f" 다만 법정의 {SANITY_MULTIPLIER:g}배({max_legal * SANITY_MULTIPLIER:g}%)를 초과 — "
                "완화 상한 초과 가능성, 완화율·근거 재확인 필요."
            )
        if non_incentive_zone:
            extra += " (인센티브 적용대상이 사실상 아닌 용도지역으로 과도한 상향 주의 — 재확인 필요.)"
        return {
            "type": "법정한도초과",
            "claim": f"{label} {value:g}%",
            "severity": sev,
            "note": (
                f"{zone} 법정 {label} 상한 {max_legal:g}% 초과 — 완화근거 명시됨,"
                f" 적용여부·완화율 검토 필요.{extra}"
            ),
        }

    # 근거 있음 + sanity 内 → info(정당한 인센티브 상향 가능성, fail 아님).
    return {
        "type": "법정한도초과",
        "claim": f"{label} {value:g}%",
        "severity": "info",
        "note": (
            f"{zone} 법정 {label} 상한 {max_legal:g}% 초과 — 완화근거(기부채납/친환경/역세권/"
            f"공공임대/지구단위계획 등) 명시됨, 적용여부·완화율 검토 필요(할루시네이션 아님)."
        ),
    }


def check_against_legal(
    zone_type: str | None,
    bcr_pct: float | None = None,
    far_pct: float | None = None,
    tolerance_pct: float = 0.5,
    payload: Any = None,
    has_basis: bool | None = None,
) -> list[dict[str, Any]]:
    """건폐율/용적률이 법정 상한을 초과하는지 '근거기반' 3단 판정.

    법정 상한은 기본값일 뿐, 기부채납·친환경·역세권·공공임대·지구단위계획(상한용적률) 등
    합법적 인센티브로 상향될 수 있다. 따라서 초과 수치 자체로 fail 하지 않고, 페이로드에
    완화근거가 있는지로 severity를 결정한다.

    Args:
        zone_type: 용도지역명(정규화 전).
        bcr_pct: 검증 대상 건폐율(%).
        far_pct: 검증 대상 용적률(%).
        tolerance_pct: 반올림 오차 허용폭(%p). 기본 0.5%p.
        payload: 완화근거 탐색 대상(source/output 등). has_basis 미지정 시 여기서 탐색.
        has_basis: 완화근거 존재 여부를 외부에서 직접 주입(테스트/명시 호출용).

    Returns:
        위반/주의 이슈 목록(severity: high|warn|info). 위반 없으면 빈 리스트.
        용도지역 미매칭 시에도 빈 리스트(일반 범위 규칙에 위임).
    """
    limits = legal_limits_for(zone_type)
    if limits is None:
        return []

    if has_basis is None:
        has_basis = _has_relaxation_basis(payload) if payload is not None else False

    max_bcr = limits["max_bcr_pct"]
    max_far = limits["max_far_pct"]
    zone = limits["zone_type"]
    non_incentive = _is_non_incentive_zone(zone)

    issues: list[dict[str, Any]] = []
    if bcr_pct is not None and max_bcr is not None and bcr_pct > max_bcr + tolerance_pct:
        issues.append(
            _judge_excess("건폐율", bcr_pct, max_bcr, zone, has_basis, non_incentive)
        )
    if far_pct is not None and max_far is not None and far_pct > max_far + tolerance_pct:
        issues.append(
            _judge_excess("용적률", far_pct, max_far, zone, has_basis, non_incentive)
        )
    return issues
