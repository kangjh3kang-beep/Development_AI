"""terrain_coverage 불변식(계층 A) — 임야/산지 후보 필지인데 '수집가능한' 경사도(DEM/SRTM
결정값)가 미획득(None)이면 correctness 완전성 갭으로 표면화한다(Phase0 W3-3 / G6).

성격(★오라클 독립성 — G3 zone coverage와 동형·값 재계산 없음):
- 이 규칙은 경사도 '값을 재계산하지 않는다'. 이미 계산된 result에서 '수집가능 경사도가 있어야
  할 자리에 None인가'라는 **데이터 완전성**만 판정한다(neuro proposes / symbolic disposes).
  경사도 산출(terrain_service SRTM 30m DEM)과 완전 독립이라 값-재구현 위험이 없다
  (G3 coverage가 BCR/FAR '값'이 아니라 '판정불가 여부'만 본 것과 동일 원리).

★수집가능(경사도) vs 실측필요(임목축적) 구분 — 이 규칙의 핵심 격리(재확증 확정):
  - 수집가능(SRTM/DEM 결정값): _fetch_terrain_facts → terrain_service.analyze_terrain 이
    산출하는 평균경사도(%)다. 미획득이면 '재수집으로 채울 수 있는' 갭 → finding 대상.
    result 노출 위치(재확증 — comprehensive_analysis_service.py 라이브 코드 대조 2026-07-29):
      · special_parcel.factors[].forest_facts["평균경사도_pct"]
        (special_parcel.py:221 기본 None → _inject_forest_observations:1063-1068에서
         terrain_facts.평균경사도_pct 획득 시에만 float 주입) — 수집가능 경사도의 정본 위치.
      · dev_act_permit_gate.criteria["slope"]["value"]
        (dev_act_permit_gate.py:257-261 _eval_slope — dem_pct None이면 value=None·status UNKNOWN)
         — 산지 district 후보(임야 지목 아님)의 수집가능 경사도 위치.
  - 실측필요(산림청 현장조사): _fetch_forest_data → get_forest_facts 의 입목축적(입목축적_per_ha)
    등이다. **실측 전엔 알 수 없는** 정직 미획득이라 None이어도 finding이 아니다.
    result 위치: forest_facts["입목축적_per_ha"]·preliminary_assessment["stocking"]/["stocking_skip_reason"].
    → 이 규칙은 **경사도 키만** 읽고 stocking 계열 키를 **일절 읽지 않는다**(구조적 격리 —
      실측필요 None을 갭으로 오플래그하지 않는다).

★근본봉합(경사도 실수집)은 이 불변식의 소관이 아니다 — DEM 경사도 배선은 이미
  comprehensive_analysis_service._fetch_terrain_facts(:265)가 후보 필지에 대해 조회한다.
  이 불변식은 그 수집이 실패/회귀해 임야/산지 후보의 수집가능 경사도가 None으로 남으면
  '개발행위 판단 근거 불완전'을 감지하는 **안전망**이다(변이-kill: 규칙 fn을 return []로 변이하면
  임야+경사None 골든이 finding 0으로 떨어져 FAIL — 가드가 죽음).

경로 비의존: 실 analyze() 결과(special_parcel.factors[].forest_facts) shape와, 산지 district만으로
  후보인 경우의 dev_act_permit_gate.criteria.slope shape 두 곳 모두에서 수집가능 경사도를 추출한다
  (runner가 다중 삽입점에 재사용되므로).
"""

from __future__ import annotations

from typing import Any

from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import register_audit_rule

# 안정 식별자 — rule_id=rules_registry 등록·per-rule 롤백 키, code=finding 안정 식별자.
_RULE_ID = "TERRAIN_SLOPE_COLLECTION_GAP"
_FINDING_CODE = "TERRAIN_SLOPE_COLLECTION_GAP"

# finding expected 마커(값이 아니라 '기대 상태'를 기술 — 특정 경사도 수치가 아님). 테스트가 참조하도록 상수로 노출.
_EXPECTED_MARK = "수집가능 경사도(SRTM/DEM) 획득"

# 배지 패널명 — 경사도 미획득은 개발행위허가 경사도 기준 판정을 막는다(developability 불완전).
_PANEL = "개발행위"

# finding note(사용자 표면 문구) — 재수집 권장·실측필요 항목과의 구분 명시(과제 지정 문구).
_NOTE = (
    "임야/산지 필지의 수집가능 경사도(DEM) 미획득 — 개발행위 판단 근거 불완전, 재수집 권장"
    "(임목축적 등 실측필요 항목과 구분)"
)

# ★수집가능 경사도의 정본 키 — 이 규칙은 이 키만 읽는다(실측필요 입목축적_per_ha 등은 일절 안 봄).
_SLOPE_KEY = "평균경사도_pct"


def _is_missing_slope(v: Any) -> bool:
    """수집가능 경사도가 '미획득'인가. None·bool·비수치를 미획득으로 본다.

    ★0.0(평지)은 '유효 수집값'이다 — 0을 미획득으로 보면 안 된다(G3의 _is_null_limit이 0을
    판정불가로 본 것과 반대: 슬로프 0%는 정상 수집값이라 갭 아님). bool은 슬로프값일 수 없어 미획득
    취급. 수치(0·음수 포함)는 '수집됨'으로 본다 — 음수 등 값-정합성은 이 완전성 갭의 소관 아님.
    """
    if v is None:
        return True
    if isinstance(v, bool):
        return True
    if isinstance(v, (int, float)):
        return False  # 수치(0 포함) = 수집됨 → 갭 아님
    return True  # 문자열 등 비수치 = 유효 수집값 아님 → 미획득 취급


def _forest_factor_facts(special_parcel: Any) -> dict[str, Any] | None:
    """result-노출 임야 요인의 forest_facts를 반환(수집가능 경사도 정본 위치). 없으면 None.

    special_parcel.factors[]에서 forest_facts(dict)를 가진 요인(=detect_special_parcel의
    임야(산지) 요인 — special_parcel.py:214-256)을 찾는다. 이게 '임야/산지 후보'의 result-노출
    판정이자 수집가능 경사도(평균경사도_pct)의 위치다.
    """
    if not isinstance(special_parcel, dict):
        return None
    factors = special_parcel.get("factors")
    if isinstance(factors, list):
        for f in factors:
            if isinstance(f, dict) and isinstance(f.get("forest_facts"), dict):
                return f["forest_facts"]
    return None


def _raw_forest_candidate(payload: dict[str, Any], special_parcel: Any) -> bool:
    """지목/산지구분 기반 임야/산지 후보 판정(폴백 — forest_facts 부재 시).

    _is_forest_slope_candidate(comprehensive_analysis_service.py:226) 로직을 result 판정으로
    참조(재구현 아님): 지목(land_category)에 '임야' 또는 특별구역(special_districts)에 '산지'.
    추가로 factor category에 '임야'/'산지'가 있으면 후보(요인 노출값). 무엇도 아니면 비후보.
    """
    lc = str(payload.get("land_category") or "")
    if "임야" in lc:
        return True
    districts = payload.get("special_districts") or []
    if isinstance(districts, (list, tuple)) and any("산지" in str(d) for d in districts):
        return True
    if isinstance(special_parcel, dict):
        factors = special_parcel.get("factors")
        if isinstance(factors, list):
            for f in factors:
                if isinstance(f, dict):
                    cat = str(f.get("category") or "")
                    if "임야" in cat or "산지" in cat:
                        return True
    return False


def _gate_slope_criterion(payload: dict[str, Any]) -> dict[str, Any] | None:
    """dev_act_permit_gate.criteria["slope"]를 안전 추출(폴백 경사도 위치). 없으면 None.

    산지 district만으로 후보인 필지는 임야 요인(forest_facts)이 없고 경사도가 개발행위허가
    게이트의 slope 기준(_eval_slope)에만 실린다. value=None(status UNKNOWN)이 미획득 신호다.
    """
    gate = payload.get("dev_act_permit_gate")
    if not isinstance(gate, dict):
        return None
    criteria = gate.get("criteria")
    if not isinstance(criteria, dict):
        return None
    slope = criteria.get("slope")
    return slope if isinstance(slope, dict) else None


def _finding(field: str) -> AuditFinding:
    """수집가능 경사도 미획득 finding 조립(Tier A·P1 비차단 — is_valid 불변)."""
    return AuditFinding(
        code=_FINDING_CODE,
        severity="P1",
        panel=_PANEL,
        field=field,
        expected=_EXPECTED_MARK,
        observed="미획득(None)",
        rule_id=_RULE_ID,
        tier="A",
        note=_NOTE,
    )


def _terrain_slope_collection_gap(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """TERRAIN_SLOPE_COLLECTION_GAP(계층 A): 임야/산지 후보인데 수집가능 경사도가 None이면 P1 갭.

    발동 조건(전부 충족 시에만 — 오탐 0):
      ① 임야/산지 후보 — result 노출값 우선(special_parcel.factors[].forest_facts), 없으면
         지목/산지구분(land_category='임야'·special_districts='산지'·factor category).
      ② 수집가능 경사도(DEM/SRTM)가 미획득(None/비수치) — forest_facts["평균경사도_pct"] 우선,
         (임야 요인이 없는 산지 district 후보는) dev_act_permit_gate.criteria.slope.value.
      ③ (구조적 격리) 실측필요(입목축적 등)의 None은 **판정 대상 아님** — 이 규칙은 경사도 키만 읽는다.
    경사도 구조 자체가 부재(임야 요인·게이트 경사도 모두 없음)면 무발동(오탐 없음 — '부재'와 '미획득'
    구분). P1 = 비차단(is_valid 불변 — is_valid=not has_p0). ★값 재계산·오라클 의존 없음(완전성만 판정).
    """
    if not isinstance(payload, dict):
        return []
    special_parcel = payload.get("special_parcel")

    # ── 1) 우선: result-노출 임야 요인(forest_facts)의 수집가능 경사도 판정 ──
    ff = _forest_factor_facts(special_parcel)
    if ff is not None:
        slope = ff.get(_SLOPE_KEY)  # 수집가능(DEM) — 실측필요(입목축적_per_ha)는 일절 안 봄(③ 격리)
        if _is_missing_slope(slope):
            return [_finding(f"special_parcel.forest_facts.{_SLOPE_KEY}")]
        return []  # 경사도 수집됨(수치) → 갭 없음

    # ── 2) 폴백: forest_facts 부재 + 지목/산지구분 후보 + 게이트 경사도 미획득 ──
    if not _raw_forest_candidate(payload, special_parcel):
        return []  # ① 비후보(비임야·비산지) → 무발동
    slope_cr = _gate_slope_criterion(payload)
    if slope_cr is None:
        return []  # 경사도 구조 부재('부재'는 미획득 아님) → 무발동(오탐 없음)
    if _is_missing_slope(slope_cr.get("value")):
        return [_finding("dev_act_permit_gate.criteria.slope.value")]
    return []


def register_rules() -> None:
    """terrain_coverage 불변식을 rules_registry에 등록(멱등 — _SEEN_IDS가 중복 무시).

    프로덕션은 모듈 임포트 시 하단에서 자동 호출한다. clear_registry()로 레지스트리를 비우는
    격리 테스트는 이 함수를 다시 호출해 프로덕션 규칙을 재등록한다.
    """
    register_audit_rule(rule_id=_RULE_ID, tier="A")(_terrain_slope_collection_gap)


# 프로덕션 임포트 시 자동 등록(field_audit 패키지 __init__가 이 모듈을 임포트한다).
register_rules()
