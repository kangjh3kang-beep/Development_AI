"""coverage 불변식 — 분석에 등장한 용도지역이 BCR/FAR 룩업에 미등재되어 '조용한 판정불가'로
끝나는 커버리지 갭을 표면화한다.

W1-3 [P1 G3]: "분석에 등장한 용도지역이 국토계획법 별표(시행령 §84·85조)에 BCR/FAR 법정한도가
명확한 표준 용도지역인데, 산출된 법정 건폐율/용적률이 '판정불가'(null)면 → 커버리지 갭
AuditFinding을 낸다." G1/G2와 동형으로 값을 생산하지 않고 이미 계산된 result의 BCR/FAR를
'별표 한도가 있는 표준 용도지역' 독립 오라클(_STATUTORY_LIMIT_ZONES)과 대조만 한다
(neuro proposes / symbolic disposes).

★M3 교정(핵심 — 가짜 정밀 제조 금지): '판정불가'에는 두 종류가 있고 반드시 구분한다.
  (a) 커버리지 갭 — 별표에 법정 한도가 명확한데(계획관리 40/100·생산관리 20/80·보전관리 20/80)
      룩업 누락으로 못 낸 것. 등재하면 낼 수 있다 → 갭 finding으로 표면화(이 불변식 소관).
  (b) 본질적 조례의존 판정불가 — 정답이 '지자체 도시계획조례·개별심의 확인 필요'인 것
      (관리지역 허용행위/용도는 별표18~20이 다수를 조례에 위임). → 정직 판정불가 유지,
      갭 아님. 이 불변식은 **BCR/FAR만** 대조하고 허용용도(permit)는 건드리지 않으므로
      (b)를 갭으로 오플래그하지 않는다(구조적 격리 — 조용한 판정불가와 정직한 조례의존
      판정불가를 구분).

★근본봉합(별표 등재)은 이 불변식의 소관이 아니다 — 별표 BCR/FAR 한도는 이미
auto_zoning_service.ZONE_LIMITS(보전/생산관리 20/80·계획관리 40/100)에 등재돼
legal_limits_for가 산출한다(2026-06 리뷰 M-7). 이 불변식은 그 등재가 회귀하거나 표준
용도지역이 룩업에서 누락되면 '조용한 판정불가'를 감지하는 **안전망**이다
(변이-kill: 관리지역을 룩업에서 제거→legal_limits_for가 None(판정불가) 복귀→이 finding 재발).

★독립 오라클(변이-kill 성립의 핵심): _STATUTORY_LIMIT_ZONES는 auto_zoning_service.ZONE_LIMITS를
임포트하지 않는다. 룩업(ZONE_LIMITS)에서 zone을 제거해도 오라클은 그 zone이 '별표 한도가
법정으로 존재하는 표준 용도지역'임을 계속 알아야, 룩업 누락을 갭으로 적발할 수 있다.
오라클이 ZONE_LIMITS에서 파생되면 룩업과 함께 사라져 갭을 못 잡는다(가드가 죽음).

경로 비의존: 실 analyze() 결과(effective_far.national_far_pct)와 골든 fixture(legal_limits.
far_pct) 두 shape 모두에서 법정 BCR/FAR를 추출한다(runner가 다중 삽입점에 재사용되므로).
"""

from __future__ import annotations

from typing import Any

from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import register_audit_rule

# 안정 식별자 — rule_id는 rules_registry 등록·per-rule 롤백 키, code는 finding 안정 식별자.
_G3_RULE_ID = "G3_ZONE_COVERAGE_GAP"
_G3_FINDING_CODE = "G3_ZONE_COVERAGE_GAP"

# finding의 expected 마커(계획 §4 W1-3: expected=별표 한도존재). 특정 수치가 아니라 '별표에
# 법정 한도가 존재한다'는 사실을 기술한다 — 수치 대조(값 correctness)는 이 갭 불변식의 소관이
# 아니고, 룩업 누락(커버리지)만 판정한다. 테스트가 참조하도록 상수로 노출.
_EXPECTED_MARK = "별표 한도존재(국토계획법 시행령 §84·85)"

# ── 독립 오라클: 국토계획법 별표(§84·85)에 BCR/FAR 법정한도가 명확한 표준 용도지역 21종 ──
# 국토계획법 제36조가 정하는 용도지역(주거6·상업4·공업3·녹지3·관리3·농림1·자연환경보전1).
# 전부 시행령 §84(건폐율)·§85(용적률)에 법정 상한/범위가 있어 '룩업 등재 시 산출 가능'하다.
# ★ZONE_LIMITS 비의존(위 docstring 참조) — 이 frozenset은 룩업이 무너져도 불변이어야
#   변이-kill이 성립한다. 관리지역 허용'행위'는 조례의존(별표18~20 위임)이라 여기서 다루지
#   않는다 — 이 오라클은 BCR/FAR 법정한도 존재 여부만 판정한다(M3 (a)/(b) 구분).
_STATUTORY_LIMIT_ZONES: frozenset[str] = frozenset({
    # 주거지역(6)
    "제1종전용주거지역", "제2종전용주거지역",
    "제1종일반주거지역", "제2종일반주거지역", "제3종일반주거지역", "준주거지역",
    # 상업지역(4)
    "중심상업지역", "일반상업지역", "근린상업지역", "유통상업지역",
    # 공업지역(3)
    "전용공업지역", "일반공업지역", "준공업지역",
    # 녹지지역(3)
    "보전녹지지역", "생산녹지지역", "자연녹지지역",
    # 관리지역(3) — BCR/FAR는 별표 한도 명확(계획관리 40/100·생산/보전관리 20/80).
    "보전관리지역", "생산관리지역", "계획관리지역",
    # 농림·자연환경보전(2)
    "농림지역", "자연환경보전지역",
})

# 법정 BCR/FAR 한도를 담는 컨테이너(경로 비의존). 실 analyze()는 effective_far,
# 정산/그라운딩 경로는 legal_limits/zone_limits/zoning shape를 쓴다.
_LIMIT_CONTAINERS: tuple[str, ...] = ("effective_far", "legal_limits", "zone_limits", "zoning")
# 각 컨테이너/평면에서 '법정 용적률/건폐율'로 인정하는 키(national_*=법정 표시값 우선).
_FAR_KEYS: tuple[str, ...] = ("national_far_pct", "legal_max_far_pct", "far_pct", "max_far_pct")
_BCR_KEYS: tuple[str, ...] = ("national_bcr_pct", "legal_max_bcr_pct", "bcr_pct", "max_bcr_pct")
# 용도지역명을 담을 수 있는 payload 경로(ctx 우선).
_ZONE_CONTAINERS: tuple[str, ...] = (
    "effective_far", "legal_limits", "zoning", "development_plans",
)

_MISSING = object()  # '키 부재'와 'None 값'을 구분하는 센티널.


def _zone_has_statutory_limit(zone: str | None) -> str | None:
    """zone이 국토계획법 별표(§84·85)에 BCR/FAR 법정한도가 명확한 표준 용도지역인지 판정.

    독립 오라클(_STATUTORY_LIMIT_ZONES) 대조 — ★ZONE_LIMITS 비의존(변이-kill 성립). 공백 정규화
    후 정확 일치 → 부분 일치(긴 키 우선, 광의 오탐 최소화). 매칭 실패 시 None(비표준/미지
    용도지역 — 개발제한구역 등은 별표 한도가 없어 갭 대상 아님 → 오탐 방지).
    """
    if not zone:
        return None
    key = str(zone).replace(" ", "").strip()
    if not key:
        return None
    if key in _STATUTORY_LIMIT_ZONES:
        return key
    for z in sorted(_STATUTORY_LIMIT_ZONES, key=len, reverse=True):
        if z in key or key in z:
            return z
    return None


def _extract_zone_type(payload: dict[str, Any], ctx: dict[str, Any]) -> str | None:
    """분석에 등장한 용도지역명을 추출(ctx 우선 — seam이 zone_type을 넘김, 그다음 payload)."""
    if isinstance(ctx, dict) and ctx.get("zone_type"):
        return ctx["zone_type"]
    if not isinstance(payload, dict):
        return None
    if payload.get("zone_type"):
        return payload["zone_type"]
    for c in _ZONE_CONTAINERS:
        cont = payload.get(c)
        if isinstance(cont, dict) and cont.get("zone_type"):
            return cont["zone_type"]
    return None


def _first_present(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """keys 중 처음으로 **존재**하는 키의 값을 반환(None 값도 반환). 전부 부재면 _MISSING."""
    for k in keys:
        if k in d:
            return d[k]
    return _MISSING


def _extract_legal_far_bcr(payload: dict[str, Any]) -> tuple[bool, Any, Any]:
    """법정 BCR/FAR를 추출. 반환 (container_present, far, bcr).

    container_present = 분석이 법정 BCR/FAR 컨테이너/필드를 실제로 산출했는가(키 존재). 이
    게이트가 핵심이다 — BCR/FAR를 아예 다루지 않는 payload(G1 규제·G2 학교 등)에는 무발동해
    오탐을 원천 차단한다. far/bcr는 None일 수 있고(=판정불가 신호), 값이 있으면 산출된 것.
    """
    if not isinstance(payload, dict):
        return (False, None, None)
    for c in _LIMIT_CONTAINERS:
        cont = payload.get(c)
        if isinstance(cont, dict):
            far = _first_present(cont, _FAR_KEYS)
            bcr = _first_present(cont, _BCR_KEYS)
            if far is not _MISSING or bcr is not _MISSING:
                return (
                    True,
                    None if far is _MISSING else far,
                    None if bcr is _MISSING else bcr,
                )
    far = _first_present(payload, _FAR_KEYS)
    bcr = _first_present(payload, _BCR_KEYS)
    if far is not _MISSING or bcr is not _MISSING:
        return (True, None if far is _MISSING else far, None if bcr is _MISSING else bcr)
    return (False, None, None)


def _is_null_limit(v: Any) -> bool:
    """법정 한도값이 '판정불가/미산출'인가. None·비양수(0/음수)를 판정불가로 본다.

    bool은 숫자로 오인하지 않는다(True/False가 한도값일 수 없음 → 판정불가 취급).
    """
    if v is None:
        return True
    if isinstance(v, bool):
        return True
    if isinstance(v, (int, float)):
        return v <= 0
    return False  # 문자열 등 비수치는 '무언가 산출됨'으로 보아 갭 아님(보수적 무발동).


def _g3_zone_coverage_gap(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """G3 불변식: 별표 한도가 명확한 표준 용도지역인데 법정 BCR/FAR가 '판정불가'면 P1 갭 finding.

    발동 조건(전부 충족 시에만):
      ① 등장 zone이 별표 한도 표준 용도지역(독립 오라클) — 비표준/미지 zone은 무발동(오탐 방지).
      ② 분석이 BCR/FAR 컨테이너를 실제 산출(키 존재) — BCR/FAR 무관 payload는 무발동.
      ③ 그 법정 BCR/FAR가 둘 다 판정불가(null/비양수) — 하나라도 산출됐으면 무발동(정상 경로).
    P1 = 제자리 표면화+배지(비차단 — is_valid 미변경). ★M3: 허용용도(permit) 판정불가는
    조례의존이라 여기서 다루지 않는다(BCR/FAR만 대조 — 갭 아닌 것을 갭으로 오플래그 안 함).
    """
    zone = _extract_zone_type(payload, ctx)
    std = _zone_has_statutory_limit(zone)
    if std is None:
        return []  # ① 비표준/미지 용도지역 — 별표 한도 없음, 갭 대상 아님
    present, far, bcr = _extract_legal_far_bcr(payload)
    if not present:
        return []  # ② 분석이 BCR/FAR를 다루지 않음 — 이 불변식 소관 아님(무발동)
    if not (_is_null_limit(far) and _is_null_limit(bcr)):
        return []  # ③ 하나라도 산출됨(별표 한도 반영) — 정상(근본봉합 후 경로)
    return [
        AuditFinding(
            code=_G3_FINDING_CODE,
            severity="P1",
            panel="법규/공급",
            field="legal_bcr_far_pct",
            expected=_EXPECTED_MARK,
            observed="판정불가",
            rule_id=_G3_RULE_ID,
            tier="A",
            note=(
                f"용도지역 '{std}'은 국토계획법 별표(시행령 §84·85)에 BCR/FAR 법정한도가 명확한 "
                "표준 용도지역인데 산출이 '판정불가'(BCR/FAR 룩업 미등재/회귀) — 커버리지 갭. "
                "ZONE_LIMITS 등재 시 산출 가능(예: 계획관리 40/100·생산/보전관리 20/80). "
                "※ 관리지역 허용용도의 판정불가는 조례의존(별표18~20 위임)으로 이 갭과 별개 — "
                "정직 판정불가 유지가 정답(억지 산출 금지)."
            ),
        )
    ]


def register_rules() -> None:
    """coverage 불변식을 rules_registry에 등록(멱등 — _SEEN_IDS가 중복 무시).

    프로덕션은 모듈 임포트 시 하단에서 자동 호출한다. clear_registry()로 레지스트리를
    비우는 격리 테스트는 이 함수를 다시 호출해 프로덕션 규칙을 재등록한다.
    """
    register_audit_rule(rule_id=_G3_RULE_ID, tier="A")(_g3_zone_coverage_gap)


# 프로덕션 임포트 시 자동 등록(field_audit 패키지 __init__가 이 모듈을 임포트한다).
register_rules()
