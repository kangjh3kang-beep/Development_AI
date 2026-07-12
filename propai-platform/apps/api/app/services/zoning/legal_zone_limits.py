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

# ── 법령 원문링크 근거키 매핑(법령 레퍼런스 레지스트리 키와 일치) ──
# 용도지역 한도(건폐율/용적률/용도지역제한)의 근거 조문을 가리키는 키.
# 값은 legal_reference_registry(LEGAL_REFERENCES) 키 명명과 정확히 일치해야 하며
# (불일치 시 법령 딥링크가 깨짐), law.go.kr 한글주소 딥링크는 레지스트리가 보유한다.
#   bcr → 국토계획법 시행령 제84조(용도지역 안에서의 건폐율)
#   far → 국토계획법 시행령 제85조(용도지역 안에서의 용적률)
#   use → 국토계획법 제76조(용도지역에서의 건축물 제한)
# (이 모듈은 키만 노출하고 URL 생성/매핑은 하지 않는다 — 데이터 매핑은 레지스트리 책임.)
LEGAL_REF_KEYS: dict[str, str] = {
    "bcr": "bcr_limit",
    "far": "far_limit",
    "use": "zone_use",
}

# ── 법정 '범위'(국토계획법 시행령 제85조) ──
# 시행령은 용적률을 단일값이 아닌 범위(min~max)로 두고, 구체 적용값은 지자체 도시계획조례로
# 정한다. ZONE_LIMITS(auto_zoning)의 max_far는 이 범위의 '상한'이다. 본 표는 그 '하한'을
# 보유하여 검증·그라운딩이 "법정 범위(예: 자연녹지 50~100%)"를 정확히 제시하게 한다.
# 건폐율(제84조)도 용도지역별 상한이며, 통상 하한은 0(조례로 강화)이므로 min_bcr는 0으로 둔다.
# ── 법정 층수상한 근거문구(★자연/생산녹지 4층 이하 — legal_limits_for.max_floors와 짝) ──
# 근거: 국토의 계획 및 이용에 관한 법률 시행령 별표15~17(보전·생산·자연녹지지역 안에서
# 건축할 수 있는 건축물)의 두문(head note) — "다음 각 호의 어느 하나에 해당하는 건축물로서
# 4층 이하의 건축물에 한한다." (별표 번호는 development_type_analyzer.ZONE_ALLOWED_BUILDINGS의
# legal_basis와 교차확인 — 보전=별표15·생산=별표16·자연=별표17). 조례로 이보다 더 낮게(예:
# 3층) 강화할 수 있다(본 표는 법정 상한만 SSOT — 조례 강화값은 별도 데이터). ★근거 확인이
# 안 되는 용도지역은 절대 수록하지 않는다(임의 층수제한 날조 금지) — ZONE_LIMITS(auto_zoning_
# service)에서 max_floors가 None인 용도지역은 이 표에도 없다(구조적으로 정합 보장).
FLOOR_CAP_BASIS: dict[str, str] = {
    "보전녹지지역": "국토계획법 시행령 별표15(보전녹지지역) 두문 — 4층 이하(조례로 더 낮게 강화 가능)",
    "생산녹지지역": "국토계획법 시행령 별표16(생산녹지지역) 두문 — 4층 이하(조례로 더 낮게 강화 가능)",
    "자연녹지지역": "국토계획법 시행령 별표17(자연녹지지역) 두문 — 4층 이하(조례로 더 낮게 강화 가능)",
}

# 미수록 용도지역은 max를 min으로 간주(범위정보 없음 → 단일상한).
ZONE_FAR_MIN: dict[str, int] = {
    "제1종전용주거지역": 50,
    "제2종전용주거지역": 100,
    "제1종일반주거지역": 100,
    "제2종일반주거지역": 150,
    "제3종일반주거지역": 200,
    "준주거지역": 200,
    "중심상업지역": 400,
    "일반상업지역": 300,
    "근린상업지역": 200,
    "유통상업지역": 200,
    "전용공업지역": 150,
    "일반공업지역": 200,
    "준공업지역": 200,
    "보전녹지지역": 50,
    "생산녹지지역": 50,
    "자연녹지지역": 50,
    "보전관리지역": 50,
    "생산관리지역": 50,
    "계획관리지역": 50,
    "농림지역": 50,
    "자연환경보전지역": 50,
}

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
    # 도시계획조례·도시군관리계획·도시군계획·종세분(계층 적용값 신호)
    "도시계획조례", "도시·군관리계획", "도시군관리계획", "관리계획",
    "도시·군계획", "도시군계획", "종세분", "특별계획구역", "특별구역",
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
        return any(_has_relaxation_basis(v) for v in payload.values())
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
    max_far = limits.get("max_far")
    min_far = ZONE_FAR_MIN.get(key, max_far)
    return {
        "zone_type": key,
        "max_bcr_pct": limits.get("max_bcr"),
        "min_bcr_pct": 0,  # 건폐율 하한은 0(조례로 강화 가능), 상한이 법정 제약.
        "max_far_pct": max_far,
        "min_far_pct": min_far,
        "max_height_m": limits.get("max_height_m"),
        # 층수 제한(★녹지지역 4층 등). SSOT(ZONE_LIMITS)에서 위임. 녹지 외 지역은 None.
        "max_floors": limits.get("max_floors"),
        # 층수상한 법령 근거문구(구조상한=건폐율×층수 계산 시 출처 표기용). max_floors가
        # None인 용도지역은 이 값도 None(짝 불변식 — 근거 없는 층수제한 날조 금지).
        "floor_cap_basis": FLOOR_CAP_BASIS.get(key),
        "legal_basis": LEGAL_BASIS,
        # 옵셔널: 건폐율/용적률 한도의 법령 원문링크 근거키(레지스트리 키와 일치).
        # 기존 키는 전부 유지하며, 소비자는 이 키를 옵셔널로 읽는다(없어도 무해).
        "legal_ref_keys": {"bcr": LEGAL_REF_KEYS["bcr"], "far": LEGAL_REF_KEYS["far"]},
    }


# ★조례 '확정' 출처로 인정하는 키워드(법제처/ELIS/지자체 조례). '법정상한'은 조례 미보유
#   폴백을 뜻하므로 여기 포함하지 않는다(effective_far가 법정값과 같아도 조례값이 아님).
_CONFIRMED_ORDINANCE_SOURCE_HINTS: tuple[str, ...] = ("조례", "법제처", "ELIS", "elis")


def _is_confirmed_ordinance_source(source: Any) -> bool:
    """source 문자열이 '실제 조례 취득' 출처인지 판정.

    '법정상한'(류)이면 조례 미보유 폴백이므로 False. '조례'/'법제처'/'ELIS'가 포함되면 True.
    None/빈 문자열은 판정 불가로 False(호출부가 명시적 ordinance_far 유무로 별도 인정).
    """
    if not source or not isinstance(source, str):
        return False
    if "법정상한" in source:
        return False
    return any(h in source for h in _CONFIRMED_ORDINANCE_SOURCE_HINTS)


def _extract_ordinance_far(regulation_payload: Any) -> dict[str, Any]:
    """규제분석/조례 페이로드에서 해당 용도지역의 조례 적용 건폐율/용적률을 추출.

    OrdinanceService(land_info_service의 local_ordinance)·RegulationAnalysisService(limits.far/bcr)
    가 산출한 구체값을 '적용 법정값'으로 인식한다. 다양한 키 형태를 관대하게 수용하며,
    중첩 dict/list에서도 조례 컨테이너(local_ordinance/zone_limits/limits)를 깊이탐색한다.

    ★provenance 정직성: effective_far가 법정상한과 같더라도 '실제 조례를 취득한 경우'에만
    조례값으로 채택한다. 판정 기준(둘 중 하나):
      (a) source가 확정 조례 출처('조례'/'법제처'/'ELIS', 단 '법정상한' 제외), 또는
      (b) 명시적 ordinance_far/ordinance_bcr 키 존재(effective_far는 조례 신호가 아님).
    이를 만족하지 못하면(예: 용인 자연녹지 법정상한 폴백) ord_far=None을 반환해 하류에서
    ordinance_confirmed=False(조례 확인 필요)로 정직하게 마감되게 한다.

    Returns: {"ord_far": float|None, "ord_bcr": float|None, "source": str|None}.
    """
    out: dict[str, Any] = {"ord_far": None, "ord_bcr": None, "source": None}

    if isinstance(regulation_payload, list):
        for item in regulation_payload:
            r = _extract_ordinance_far(item)
            if r["ord_far"] is not None or r["ord_bcr"] is not None:
                return r
        return out

    if not isinstance(regulation_payload, dict):
        return out

    # 1) land_info 형태: local_ordinance.{effective_far, ordinance_far}
    #    ★가드: effective_far는 법정상한 폴백에서도 실려오므로(용인 자연녹지=None조례+100),
    #    '실제 조례 취득 신호'가 있을 때만 조례값으로 채택한다.
    lo = regulation_payload.get("local_ordinance")
    if isinstance(lo, dict):
        explicit_far = lo.get("ordinance_far")
        explicit_bcr = lo.get("ordinance_bcr")
        confirmed_src = _is_confirmed_ordinance_source(lo.get("source"))
        # 조례 신호: 명시적 ordinance_* 또는 확정 조례 출처. 없으면 effective_*는 무시.
        if explicit_far or explicit_bcr or confirmed_src:
            far = explicit_far or lo.get("effective_far")
            bcr = explicit_bcr or lo.get("effective_bcr")
            if far or bcr:
                out["ord_far"] = float(far) if far else None
                out["ord_bcr"] = float(bcr) if bcr else None
                out["source"] = lo.get("source") or "지자체 조례"
                return out

    # 2) zone_limits 형태: ordinance_far_pct / effective_far_pct
    #    ★가드: 명시적 ordinance_*_pct가 있을 때만 confirmed. effective_*_pct만으론 조례 아님.
    zl = regulation_payload.get("zone_limits")
    if isinstance(zl, dict):
        explicit_far = zl.get("ordinance_far_pct")
        explicit_bcr = zl.get("ordinance_bcr_pct")
        if explicit_far or explicit_bcr:
            out["ord_far"] = float(explicit_far) if explicit_far else None
            out["ord_bcr"] = float(explicit_bcr) if explicit_bcr else None
            out["source"] = "지자체 조례"
            return out

    # 3) RegulationAnalysisService.limits 형태: {"far": {"legal": ..., "ordinance": ..., "effective": ...}}
    #    ★가드(step1과 동일 계약): trio 생산자(_limits.trio)가 ordinance 미보유 시
    #    effective = ordinance or legal 로 법정값을 effective에 채워넣으므로(용인과 동일 버그
    #    클래스), 명시적 ordinance 키가 있을 때만 조례값으로 채택한다. effective 단독 금지.
    limits = regulation_payload.get("limits")
    if isinstance(limits, dict):
        f = limits.get("far") or {}
        b = limits.get("bcr") or {}
        far = f.get("ordinance") if isinstance(f, dict) else None
        bcr = b.get("ordinance") if isinstance(b, dict) else None
        if far or bcr:
            out["ord_far"] = float(far) if far else None
            out["ord_bcr"] = float(bcr) if bcr else None
            out["source"] = "지자체 조례"
            return out

    # 4) 평탄 형태: regulation_payload.{ordinance_far, ordinance_bcr} 직접(테스트/단순 호출).
    #    주의: 일반 far/bcr는 '검증 대상값'일 수 있어 조례값으로 오인하지 않는다(명시 키만 인정).
    far = regulation_payload.get("ordinance_far") or regulation_payload.get("ordinance_far_pct")
    bcr = regulation_payload.get("ordinance_bcr") or regulation_payload.get("ordinance_bcr_pct")
    if far or bcr:
        try:
            out["ord_far"] = float(far) if far else None
            out["ord_bcr"] = float(bcr) if bcr else None
            out["source"] = regulation_payload.get("source") or "지자체 조례"
            return out
        except (TypeError, ValueError):
            pass

    # 5) 컨테이너가 없으면 자식으로 깊이탐색(중첩 source/output 수용).
    for v in regulation_payload.values():
        if isinstance(v, (dict, list)):
            r = _extract_ordinance_far(v)
            if r["ord_far"] is not None or r["ord_bcr"] is not None:
                return r
    return out


# 도시·군관리계획/지구단위계획 상한용적률 추출 키.
_PLAN_FAR_KEYS: tuple[str, ...] = (
    "plan_far_pct", "상한용적률", "ceiling_far_pct", "max_plan_far_pct",
    "district_plan_far_pct", "urban_plan_far_pct",
)
_PLAN_BCR_KEYS: tuple[str, ...] = ("plan_bcr_pct", "district_plan_bcr_pct")


def _extract_plan_limit(plan_payload: Any) -> dict[str, Any]:
    """도시·군관리계획/지구단위계획 페이로드에서 상한용적률·건폐율을 추출(최우선 적용 후보)."""
    out: dict[str, Any] = {"plan_far": None, "plan_bcr": None, "source": None}

    def _scan(obj: Any) -> None:
        if out["plan_far"] is not None and out["plan_bcr"] is not None:
            return
        if isinstance(obj, dict):
            for k in _PLAN_FAR_KEYS:
                v = obj.get(k)
                if v and out["plan_far"] is None:
                    try:
                        out["plan_far"] = float(v)
                        out["source"] = "도시·군관리계획/지구단위계획"
                    except (TypeError, ValueError):
                        pass
            for k in _PLAN_BCR_KEYS:
                v = obj.get(k)
                if v and out["plan_bcr"] is None:
                    try:
                        out["plan_bcr"] = float(v)
                        out["source"] = out["source"] or "도시·군관리계획/지구단위계획"
                    except (TypeError, ValueError):
                        pass
            for v in obj.values():
                _scan(v)
        elif isinstance(obj, list):
            for v in obj:
                _scan(v)

    _scan(plan_payload)
    return out


def applicable_limits_for(
    zone_type: str | None,
    sigungu: str | None = None,
    regulation_payload: Any = None,
    plan_payload: Any = None,
) -> dict[str, Any] | None:
    """용도지역의 '적용 한도'를 계층 산정해 반환.

    계층(낮은 순서가 더 구체·우선):
      1. 법정 범위(국토계획법 시행령) — min_far~max_far / max_bcr.
      2. 지자체 도시계획조례 구체값(regulation_payload에 있으면) → '적용 법정값'.
      3. 도시·군관리계획/지구단위계획 상한용적률(plan_payload에 있으면) → 최우선.

    조례·계획 데이터가 없으면 법정 범위를 반환하며 ordinance_confirmed=False(확인필요)로
    정직하게 표시한다(허위 조례값 생성 금지).

    Returns(주요 키):
      zone_type, legal_min_far_pct, legal_max_far_pct, legal_max_bcr_pct,
      ordinance_far_pct?, ordinance_bcr_pct?, plan_far_pct?, plan_bcr_pct?,
      applied_far_pct(적용 상한 기준값), applied_bcr_pct, far_source, ordinance_confirmed,
      sources(list), legal_basis.
    """
    legal = legal_limits_for(zone_type)
    if legal is None:
        return None

    legal_max_far = legal["max_far_pct"]
    legal_min_far = legal["min_far_pct"]
    legal_max_bcr = legal["max_bcr_pct"]

    ord_info = _extract_ordinance_far(regulation_payload)
    plan_info = _extract_plan_limit(plan_payload)

    sources: list[str] = ["법정범위"]
    result: dict[str, Any] = {
        "zone_type": legal["zone_type"],
        "legal_min_far_pct": legal_min_far,
        "legal_max_far_pct": legal_max_far,
        "legal_max_bcr_pct": legal_max_bcr,
        "sigungu": sigungu,
        "legal_basis": LEGAL_BASIS,
        "ordinance_confirmed": False,
    }

    # 기준값(적용 상한): 기본은 법정범위 max. ★조례·계획 미확인이면 정직하게 '법정상한 적용
    #   (조례 확인 필요)'로 표기(false-confirmed 방지).
    applied_far = float(legal_max_far) if legal_max_far is not None else None
    applied_bcr = float(legal_max_bcr) if legal_max_bcr is not None else None
    far_source = "법정상한 적용(조례 확인 필요)"

    # 2) 조례 적용값. ★source 존중: _extract_ordinance_far가 조례 신호가 있을 때만 ord_far를
    #    채우지만, 방어적으로 '법정상한' 출처는 confirmed로 승격하지 않는다(중복 게이트).
    ord_src = ord_info["source"]
    ord_source_is_fallback = isinstance(ord_src, str) and "법정상한" in ord_src
    if ord_info["ord_far"] is not None and not ord_source_is_fallback:
        result["ordinance_far_pct"] = ord_info["ord_far"]
        # 조례는 법정범위 내로 클램프(조례가 법정상한을 넘어설 수 없음).
        if legal_max_far is not None:
            applied_far = min(ord_info["ord_far"], float(legal_max_far))
        else:
            applied_far = ord_info["ord_far"]
        result["ordinance_confirmed"] = True
        far_source = f"지자체 도시계획조례 적용값({ord_info['source'] or '조례'})"
        sources.append(ord_info["source"] or "지자체 조례")
    if ord_info["ord_bcr"] is not None and not ord_source_is_fallback:
        result["ordinance_bcr_pct"] = ord_info["ord_bcr"]
        if legal_max_bcr is not None:
            applied_bcr = min(ord_info["ord_bcr"], float(legal_max_bcr))
        else:
            applied_bcr = ord_info["ord_bcr"]

    # 3) 도시·군관리계획/지구단위계획 상한 — 최우선(조례보다 구체).
    if plan_info["plan_far"] is not None:
        result["plan_far_pct"] = plan_info["plan_far"]
        applied_far = plan_info["plan_far"]
        far_source = "도시·군관리계획/지구단위계획 상한용적률(최우선 적용)"
        sources.append(plan_info["source"] or "도시·군관리계획")
    if plan_info["plan_bcr"] is not None:
        result["plan_bcr_pct"] = plan_info["plan_bcr"]
        applied_bcr = plan_info["plan_bcr"]

    result["applied_far_pct"] = applied_far
    result["applied_bcr_pct"] = applied_bcr
    result["far_source"] = far_source
    result["sources"] = sources
    return result


def _judge_excess(
    label: str,
    value: float,
    max_legal: float,
    zone: str,
    has_basis: bool,
    non_incentive_zone: bool,
    plan_ceiling: float | None = None,
) -> dict[str, Any]:
    """법정 상한 초과값 1건에 대한 근거기반 3단 판정.

    수치(초과량)가 아니라 '근거(basis)'로 severity를 정한다.
    - 근거 없음 → high(할루시네이션 의심).
    - 근거 있음 → info(정당한 완화 가능성). 단 sanity(법정×배수) 초과면 warn.
    - 인센티브 비대상 용도지역에서 sanity 초과는 근거가 있어도 warn,
      근거가 없으면 high(원 사고 재현 방지)로 격상.
    - plan_ceiling(도시·군관리계획/지구단위계획 상한용적률) 근거가 있고 value가 그 이내면
      정당한 계획상한 적용으로 info(인센티브 비대상 용도지역이어도 info 유지).
    """
    over_sanity = value > max_legal * SANITY_MULTIPLIER + 0.5
    within_plan = plan_ceiling is not None and value <= plan_ceiling + 0.5

    # 도시·군관리계획/지구단위계획 상한용적률 근거 + 그 이내 → 정당(할루시네이션 아님).
    if within_plan:
        return {
            "type": "법정한도초과",
            "claim": f"{label} {value:g}%",
            "severity": "info",
            "note": (
                f"{zone} 법정 {label} 범위(상한 {max_legal:g}%)를 초과하나 "
                f"도시·군관리계획/지구단위계획 상한({plan_ceiling:g}%) 이내 — "
                "계획상한 적용으로 정당(할루시네이션 아님)."
            ),
        }

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


# 높이/층수 '제한없음'으로 잘못 표기됐는지 탐지하는 문자열 신호.
# 녹지 등 층수 제한이 있는 용도지역에서 이런 표기가 나오면 할루시네이션(검증 누락)이다.
_NO_LIMIT_TOKENS: tuple[str, ...] = (
    "제한없음", "제한 없음", "무제한", "없음", "unlimited", "no limit", "n/a",
)
# 층고(층당 높이) 가정 — 4층×3m≈12m. 높이(m) 환산·표기에 사용.
_FLOOR_HEIGHT_M: float = 3.0


def check_floors_against_legal(
    zone_type: str | None,
    floors: Any = None,
    height_m: Any = None,
    height_text: Any = None,
    has_basis: bool = False,
) -> list[dict[str, Any]]:
    """층수/높이가 용도지역 법정 제한(녹지 4층 등)을 위반하는지 근거기반 판정.

    far/bcr와 달리 층수 제한은 녹지(자연·생산·보전)에서 핵심이다(건폐율·용적률만으론
    '4층 제한'을 못 잡아 8~13층 같은 비현실 산정·'높이 제한없음' 오표기가 검증을 통과했다).

    적발 3종:
      ① 층수 초과: 제시 층수 > 법정 max_floors(예: 자연녹지 8층 > 4층).
      ② '제한없음' 모순: 층수 제한이 있는 용도지역에 높이/층수가 '제한없음'으로 표기됨.
      ③ 높이(m) 초과: 제시 높이 > 법정 층수×층고(예: 자연녹지 30m > 4층≈12m).

    severity: 근거 없으면 high(할루시네이션 의심), 근거 있어도 녹지는 인센티브 비대상이라 warn.
    층수 제한이 없는 용도지역(주거·상업 등 max_floors=None)은 빈 리스트(검증 대상 아님).
    """
    limits = legal_limits_for(zone_type)
    if limits is None:
        return []
    max_floors = limits.get("max_floors")
    if not max_floors:
        return []  # 층수 제한이 없는 용도지역 — 층수/높이는 다른 규칙(일조·가로구역)에 위임.

    zone = limits["zone_type"]
    non_incentive = _is_non_incentive_zone(zone)
    legal_height = round(max_floors * _FLOOR_HEIGHT_M)  # 약 12m(4층)
    # 근거가 있어도 녹지(인센티브 비대상)는 warn, 그 외 근거없음은 high.
    sev = "warn" if (has_basis or non_incentive) else "high"

    issues: list[dict[str, Any]] = []

    # ① 층수 초과 ──────────────────────────────────────────────
    try:
        if floors is not None and float(floors) > max_floors + 0.5:
            issues.append({
                "type": "층수제한초과",
                "claim": f"{float(floors):g}층",
                "severity": sev,
                "note": (
                    f"{zone}은 {max_floors}층(약 {legal_height}m) 이하 제한이 있으나 "
                    f"{float(floors):g}층이 제시됨 — "
                    + ("완화근거 검토 필요(녹지는 인센티브 비대상, 재확인)."
                       if sev == "warn" else
                       f"근거 미제시(할루시네이션 의심). 건폐율·용적률만으론 층수 제한이 "
                       f"드러나지 않으니 {max_floors}층 상한을 반드시 적용.")
                ),
            })
    except (TypeError, ValueError):
        pass

    # ② '제한없음' 모순 ────────────────────────────────────────
    if height_text:
        t = str(height_text).replace(" ", "").lower()
        if any(tok.replace(" ", "").lower() in t for tok in _NO_LIMIT_TOKENS):
            issues.append({
                "type": "높이제한오표기",
                "claim": f"높이 {height_text}",
                "severity": "medium",
                "note": (
                    f"{zone}은 {max_floors}층(약 {legal_height}m) 이하 제한이 있으나 "
                    f"높이가 '{height_text}'(제한없음)으로 표기됨 — 오표기. "
                    f"{max_floors}층 제한을 명시할 것."
                ),
            })

    # ③ 높이(m) 초과 ──────────────────────────────────────────
    try:
        if height_m is not None and float(height_m) > legal_height + 1.0:
            issues.append({
                "type": "높이제한초과",
                "claim": f"높이 {float(height_m):g}m",
                "severity": sev,
                "note": (
                    f"{zone}은 {max_floors}층(약 {legal_height}m) 이하 제한이 있으나 "
                    f"{float(height_m):g}m가 제시됨 — "
                    + ("완화근거 검토 필요(재확인)." if sev == "warn"
                       else f"근거 미제시(할루시네이션 의심). 약 {legal_height}m 상한 적용 권고.")
                ),
            })
    except (TypeError, ValueError):
        pass

    return issues


def check_against_legal(
    zone_type: str | None,
    bcr_pct: float | None = None,
    far_pct: float | None = None,
    tolerance_pct: float = 0.5,
    payload: Any = None,
    has_basis: bool | None = None,
    regulation_payload: Any = None,
    plan_payload: Any = None,
) -> list[dict[str, Any]]:
    """건폐율/용적률이 '적용 한도'를 초과하는지 '근거기반' 3단 판정.

    비교 기준은 법정 단일상한이 아니라 계층 적용 한도다:
      법정범위 max → (조례 적용값) → (도시·군관리계획/지구단위계획 상한).
    법정 상한은 기본값일 뿐, 기부채납·친환경·역세권·공공임대·지구단위계획(상한용적률)·
    도시계획조례 등 합법적 근거로 상향될 수 있다. 따라서 초과 수치 자체로 fail 하지 않고,
    페이로드에 근거(조례/계획/인센티브)가 있는지로 severity를 결정한다.

    Args:
        zone_type: 용도지역명(정규화 전).
        bcr_pct: 검증 대상 건폐율(%).
        far_pct: 검증 대상 용적률(%).
        tolerance_pct: 반올림 오차 허용폭(%p). 기본 0.5%p.
        payload: 완화근거 탐색 대상(source/output 등). has_basis 미지정 시 여기서 탐색.
        has_basis: 완화근거 존재 여부를 외부에서 직접 주입(테스트/명시 호출용).
        regulation_payload: 조례/규제분석 페이로드(applicable_limits_for로 적용값 산정).
        plan_payload: 도시·군관리계획/지구단위계획 페이로드(상한용적률 최우선).

    Returns:
        위반/주의 이슈 목록(severity: high|warn|info). 위반 없으면 빈 리스트.
        용도지역 미매칭 시에도 빈 리스트(일반 범위 규칙에 위임).
    """
    limits = legal_limits_for(zone_type)
    if limits is None:
        return []

    # regulation/plan 페이로드는 그 자체로 완화근거(조례·계획 적용값)다.
    if has_basis is None:
        has_basis = (
            (_has_relaxation_basis(payload) if payload is not None else False)
            or (_has_relaxation_basis(regulation_payload) if regulation_payload is not None else False)
            or (_has_relaxation_basis(plan_payload) if plan_payload is not None else False)
        )

    max_bcr = limits["max_bcr_pct"]
    max_far = limits["max_far_pct"]
    zone = limits["zone_type"]
    non_incentive = _is_non_incentive_zone(zone)

    # 계층 적용 한도 산정(조례/계획 근거가 있으면 그 상한을 plan_ceiling으로 사용).
    plan_far_ceiling: float | None = None
    plan_bcr_ceiling: float | None = None
    if regulation_payload is not None or plan_payload is not None:
        applied = applicable_limits_for(
            zone_type, regulation_payload=regulation_payload, plan_payload=plan_payload
        )
        if applied:
            # 도시·군관리계획/지구단위계획 상한(plan_far_pct)은 법정상한 초과를 정당화한다.
            plan_far_ceiling = applied.get("plan_far_pct")
            plan_bcr_ceiling = applied.get("plan_bcr_pct")
            # 조례 적용값 또는 계획 상한이 실제로 발견된 경우에만 근거로 인정한다.
            # (페이로드를 넘겼다는 사실만으로 무근거 초과를 면죄하지 않는다.)
            if (
                applied.get("ordinance_confirmed")
                or plan_far_ceiling is not None
                or plan_bcr_ceiling is not None
            ):
                has_basis = True

    issues: list[dict[str, Any]] = []
    if bcr_pct is not None and max_bcr is not None and bcr_pct > max_bcr + tolerance_pct:
        issues.append(
            _judge_excess(
                "건폐율", bcr_pct, max_bcr, zone, has_basis, non_incentive,
                plan_ceiling=plan_bcr_ceiling,
            )
        )
    if far_pct is not None and max_far is not None and far_pct > max_far + tolerance_pct:
        issues.append(
            _judge_excess(
                "용적률", far_pct, max_far, zone, has_basis, non_incentive,
                plan_ceiling=plan_far_ceiling,
            )
        )
    return issues


def mixed_zone_limits(zones: list[dict[str, Any]]) -> dict[str, Any]:
    """둘 이상 용도지역에 걸치는 대지의 건폐율/용적률(국토계획법 제84조·시행령 제94조).

    토지이음 '인허가 사례1'(두 개 이상 용도지역 → 건폐율·용적률 면적가중) 등가물.
    규칙: 가장 작은 용도지역 부분이 330㎡ 이하면 가장 넓은 용도지역에 포함(흡수) 적용,
          초과면 각 용도지역별 한도를 면적가중 평균해 대지 전체에 적용.

    Args:
        zones: [{"zone_type": 용도지역명, "area_sqm": 면적}] — 부지 내 각 용도지역.
    Returns:
        {is_mixed, per_zone[...], blended_bcr_pct, blended_far_pct, dominant_zone?, absorbed?,
         rule, total_area_sqm?, legal_ref_keys, note}. 면적 미확보 시 가중치 None(정직).
    """
    parts = [z for z in (zones or []) if z.get("zone_type")]
    # 중복 용도지역명 병합(같은 용도지역이 여러 조각이면 면적 합산).
    merged: dict[str, float | None] = {}
    for z in parts:
        zt = str(z["zone_type"]).strip()
        a = z.get("area_sqm")
        if zt not in merged:
            merged[zt] = (float(a) if a else None)
        elif a and merged[zt] is not None:
            merged[zt] += float(a)
    uniq = list(merged.items())
    if len(uniq) < 2:
        return {"is_mixed": False}

    legal_keys = ["mixed_zone_rule", "mixed_zone_rule_dec", "bcr_law", "far_law"]
    per_zone = []
    for zt, a in uniq:
        L = legal_limits_for(zt) or {}
        per_zone.append({"zone_type": zt, "area_sqm": a,
                         "max_bcr_pct": L.get("max_bcr_pct"), "max_far_pct": L.get("max_far_pct")})

    has_area = all(a for _, a in uniq)
    if not has_area:
        return {
            "is_mixed": True, "per_zone": per_zone,
            "blended_bcr_pct": None, "blended_far_pct": None,
            "rule": "면적가중(미산정)", "legal_ref_keys": legal_keys,
            "note": ("둘 이상 용도지역에 걸치는 대지 — 면적가중 건폐율/용적률 적용(국토계획법 제84조). "
                     "용도지역별 면적분할 미확보로 가중치 미산정(정직). 각 용도지역 면적 확보 시 자동 산정."),
        }

    total = sum(float(a) for _, a in uniq)
    smallest_zt, smallest_a = min(uniq, key=lambda kv: kv[1])
    largest_zt, _ = max(uniq, key=lambda kv: kv[1])

    # 330㎡ 이하 작은 부분 흡수(시행령 제94조) — 2개 용도지역에서만 단순 적용.
    if len(uniq) == 2 and float(smallest_a) <= 330.0:
        L = legal_limits_for(largest_zt) or {}
        return {
            "is_mixed": True, "per_zone": per_zone, "total_area_sqm": round(total, 1),
            "absorbed": smallest_zt, "dominant_zone": largest_zt,
            "blended_bcr_pct": L.get("max_bcr_pct"), "blended_far_pct": L.get("max_far_pct"),
            "rule": "330㎡이하 흡수", "legal_ref_keys": legal_keys,
            "note": (f"작은 부분({smallest_zt} {round(float(smallest_a))}㎡ ≤ 330㎡)은 {largest_zt}에 "
                     "포함 적용(국토계획법 시행령 제94조). 건폐율/용적률은 큰 용도지역 기준."),
        }

    # 면적가중 평균.
    bw = sum(float(a) * ((legal_limits_for(zt) or {}).get("max_bcr_pct") or 0) for zt, a in uniq)
    fw = sum(float(a) * ((legal_limits_for(zt) or {}).get("max_far_pct") or 0) for zt, a in uniq)
    return {
        "is_mixed": True, "per_zone": per_zone, "total_area_sqm": round(total, 1),
        "dominant_zone": largest_zt,
        "blended_bcr_pct": round(bw / total, 1) if total else None,
        "blended_far_pct": round(fw / total, 1) if total else None,
        "rule": "면적가중", "legal_ref_keys": legal_keys,
        "note": ("둘 이상 용도지역 면적가중 건폐율/용적률(국토계획법 제84조·시행령 제94조). "
                 "각 용도지역별 한도를 면적비로 가중평균."),
    }
