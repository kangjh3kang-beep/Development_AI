"""토지필지 종합분석 **P2 — 매입전략 분류**(순수함수, 외부콜 0).

P1(`parcel_rights_survey_service`)이 (필지 × 소유자)별 매도청구 판정을 냈다. 이 서비스는 그
판정 위에 **실행 가능한 매입전략**을 얹는다 — 협의매수/매도청구/수용/제척검토/판정보류.

## 이 파일이 반증(counterexample)으로 확정한 네 가지

1. **확보율은 분모를 받아야 한다.** `parcel_graph._area_sqm` 는 면적 미상에 0 이 아니라
   **None** 을 돌려준다. 이걸 무시하고 "아는 면적만" 합하면, 실제 64% 부지가 **100% 로
   보고되어 95% 게이트를 통과**한다(실증). 게다가 사용자는 보통 **미확보 필지만** 등록하므로
   행 합계를 분모로 쓰면 0% 아니면 100% 라는 무의미한 값이 나온다.
   → `housing_site_area_sqm`(주택건설대지면적)은 **필수 입력**이고, 면적·지분이 하나라도
     미상이면 **숫자를 내지 않고 거부**한다(`status="판정 불가"`).

2. **제척은 집합(SET) 판정이지 필지별 소속 판정이 아니다.** 안마당을 둘러싼 4필지 고리
   (BOTTOM–RIGHT–TOP–LEFT)에서 `articulation_points` 는 **빈 배열**이다. 그런데 각자
   "안전"해 보이는 LEFT + RIGHT 를 **함께** 빼면 부지가 **2조각으로 분단**된다(실행 확인).
   4-사이클은 절단점이 0개지만 크기 2의 **절단 집합**을 갖는다.
   → 그래서 `severability()` 는 개별 필지가 articulation 인지 묻지 않고, **제외 집합을 실제로
     제거한 뒤 연결성분 수를 다시 센다**(`parcel_graph._components` 재사용 — BFS 재구현 금지).

3. **"최소 비용"과 "최소 건수"는 서로 다른 최적해를 갖는다.** 워크드 예제: 면적 그리디는
   1필지 30억을 고르고, 최소비용은 2필지 7억을 고른다(4.3배 차이). 단가 데이터는 이
   저장소 어디에도 없다 → **최소 건수 하나만** 낸다. 최소 건수는 그리디로 **정확히** 풀린다
   (임의의 k 에 대해 면적 상위 k 개가 달성 가능 면적을 최대화하므로, 임계를 넘기는 최소 k 가
   최적이다). 그 증명 사실을 `optimality` 필드로 매 결과에 싣는다.
   ★단가(매입 예상가) 입력이 생기면 **최소비용 탐색은 별도 함수로** 추가한다 —
     같은 함수에 목적함수 두 개를 섞으면 어느 쪽 최적해인지 호출부가 알 수 없다.

4. **위상은 구역 지정요건을 증명하지 못한다.** 그래서 이 파일은 "제척 가능"이라고 **말하지
   않는다**. `topology_severable`(위상상 분단 없음)까지만 말하고, 면적·접도율·노후도 등
   구역 지정요건은 여전히 `procedure_required`(구역계 변경 — 주민공람·도시계획위원회 심의)
   절차에서 판단된다는 사실을 **모든 결과에** 붙인다.

## 정직 계약
- **시가·보상액 숫자를 내지 않는다**(`_PRICE_BASIS` — "시가 = 감정평가 필요").
- 모든 판정 객체는 **구조화된 면책 형제필드**(`disclaimer` 오브젝트)를 갖는다. 산문 사유
  문자열에 파묻으면 UI 가 배지로 못 그리고, 렌더링 과정에서 조용히 사라진다.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, NamedTuple

from apps.api.app.utils.withheld import SOURCE_UNAVAILABLE

# 보유기간(10년) 요건이 존재하는 유일한 법령 계열 — 정책표(MAGDO_RULES) SSOT 를 그대로 쓴다.
# ★여기서 "주택법" 문자열을 다시 적으면 정책표와 갈라진다(전역 값은 한 곳에서만 산다).
try:  # pragma: no cover — 정책표 임포트 실패 시에도 모듈이 살아 있어야 한다
    from app.services.development.scenario_simulator import HOLDING_PERIOD_ACT
except Exception:  # noqa: BLE001
    HOLDING_PERIOD_ACT = "주택법"

# ── 계약 상수(테스트는 대역이 아니라 이 상수에 `==` 로 결속한다) ──────────────
# 주택법 §22①1호 — 주택건설대지면적의 95% 이상 사용권원 확보 시 잔여 전부 매도청구 가능.
SECURED_RATIO_THRESHOLD_PCT = 95.0

# 위상 판정이 증명하지 못하는 것 — 구역 지정요건(면적·접도율·노후도)은 절차에서 본다.
PROCEDURE_REQUIRED = "구역계 변경 — 주민공람·도시계획위원회 심의"

# 시가는 숫자로 내지 않는다(감정평가 영역).
PRICE_BASIS = "시가 = 감정평가 필요"

# 최소 건수 조합의 최적성 근거 — 매 결과에 싣는다.
OPTIMALITY_MIN_COUNT = "exact(k-largest 증명)"

# 액션 열거 — **다섯**이다. 셋(협의매수/매도청구/제척)으로는 도시개발법 **수용**도,
# 판정할 수 없는 행(자료·기준 부재)도 표현하지 못한다.
ACTION_NEGOTIATE = "협의매수"
ACTION_SELL_CLAIM = "매도청구"
ACTION_EXPROPRIATION = "수용"
ACTION_EXCLUSION_REVIEW = "제척검토"
ACTION_UNDECIDED = "판정보류"
ACTIONS: tuple[str, ...] = (
    ACTION_NEGOTIATE,
    ACTION_SELL_CLAIM,
    ACTION_EXPROPRIATION,
    ACTION_EXCLUSION_REVIEW,
    ACTION_UNDECIDED,
)

# 1순위(핵심관리필지) 라벨 — §2-A. 확보율을 모르면 이 라벨도 낼 수 없다.
PRIORITY_A_LABEL = "A(1순위 핵심관리필지)"
PRIORITY_UNDECIDED_LABEL = "판정보류"

STATUS_OK = "산정"
STATUS_UNDECIDABLE = "판정 불가"
STATUS_UNREACHABLE = "달성 불가"
STATUS_ALREADY_MET = "이미 충족"

# 구조화 면책 — 산문에 파묻지 않는다(배지로 렌더돼도 살아남아야 한다).
_DISCLAIMER_TEXT = (
    "본 분류는 공부·등기 자료 기반 **참고용 1차 판정**이며 법률자문이 아닙니다. "
    "매도청구·수용의 실제 성립은 동의현황·시행자 유형·인가 시점에 따라 갈리므로 "
    "집행 전 반드시 전문가 검토를 받으십시오."
)
_REQUIRES_PROFESSIONAL = ("법무사", "변호사")


def disclaimer() -> dict[str, Any]:
    """구조화 면책 오브젝트(매 판정의 **형제 필드**). 호출마다 새 dict — 공유 변형 금지."""
    return {
        "advisory": False,  # ★자문 아님 — False 가 "자문이 아니다"를 뜻한다
        "disclaimer": _DISCLAIMER_TEXT,
        "requires_professional": list(_REQUIRES_PROFESSIONAL),
    }


# ── 지분 문자열 파싱 ───────────────────────────────────────────────────────
# 등기부 지분 표기는 형태가 다양하다. **인식 못 한 표기를 1.0 으로 접으면** 미확보 지분이
# 확보로 둔갑해 확보율이 부풀고 95% 게이트를 잘못 통과한다 → 인식 실패는 항상 None.
_SHARE_EMPTY_MARKERS = ("", "기재 없음", "데이터 없음", "없음", "미상", "-", "미기재")
_SHARE_FULL_MARKERS = ("전부", "단독", "전체")
# "1388분의 1387.08" = 1387.08/1388 — **A분의B 는 B/A** 다(순서 주의).
_BUNUI_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*분의\s*([\d,]+(?:\.\d+)?)")
_SLASH_RE = re.compile(r"^([\d,]+(?:\.\d+)?)\s*/\s*([\d,]+(?:\.\d+)?)$")
_PCT_RE = re.compile(r"^([\d,]+(?:\.\d+)?)\s*%$")


def _frac(num: str, den: str) -> float | None:
    """문자열 분수를 Fraction 으로 **정확히** 계산 후 float 변환. 0~1 밖이면 None(무날조)."""
    try:
        f = Fraction(num.replace(",", "")) / Fraction(den.replace(",", ""))
    except (ZeroDivisionError, ValueError, ArithmeticError):
        return None
    if f <= 0 or f > 1:
        return None
    return float(f)


def _share_ratio(s: str | None) -> float | None:
    """지분 문자열 → 0<r<=1 비율. **인식 실패는 None**(절대 1.0 으로 접지 않는다).

    지원: `"1/2"` · `"1388분의 1387.08"`(= 1387.08/1388) · `"99.934%"` ·
    `"전부"`/`"단독"` → 1.0 · `"기재 없음"`/None → None.
    """
    # ★이중 가드(변이 감사 2026-08-15 — 이 두 조기 반환은 지워도 결과가 같다):
    #   None·"기재 없음"·"-" 는 아래 어느 정규식에도, 어느 전부-마커에도 걸리지 않아
    #   마지막 `return None` 으로 떨어진다. 그래도 남기는 이유는 **의도를 코드로 밝히기**
    #   위해서다(빈 표기는 파싱 대상이 아니라 '미상'이다).
    if s is None:
        return None
    t = str(s).strip()
    if t in _SHARE_EMPTY_MARKERS:
        return None
    m = _BUNUI_RE.search(t)
    if m:
        return _frac(m.group(2), m.group(1))  # A분의B → B/A
    m = _SLASH_RE.match(t)
    if m:
        return _frac(m.group(1), m.group(2))  # A/B → A/B
    m = _PCT_RE.match(t)
    if m:
        return _frac(m.group(1), "100")
    if any(k in t for k in _SHARE_FULL_MARKERS):
        return 1.0
    # ★맨숫자("0.5")는 지분인지 면적인지 알 수 없다 — 추측하지 않는다.
    return None


def _parcel_area(parcel: dict[str, Any]) -> float | None:
    """면적 추출은 `parcel_graph._area_sqm`(SSOT) 를 그대로 쓴다 — 키 후보가 갈라지면 안 된다."""
    from app.services.zoning.parcel_graph import _area_sqm

    return _area_sqm(parcel)


def _pnu_of(parcel: dict[str, Any], idx: int) -> str:
    from app.services.zoning.parcel_graph import _parcel_id

    return _parcel_id(parcel, idx)


def _owner_secured(owner: dict[str, Any], parcel_flag: bool | None) -> bool | None:
    """소유자 단위 사용권원 확보 여부. 소유자에 값이 없으면 **필지 단위 값**을 승계한다."""
    v = owner.get("use_right_secured")
    if isinstance(v, bool):
        return v
    return parcel_flag


class _SecuredArea(NamedTuple):
    """`_parcel_secured_area()` 의 반환 — 필지 하나의 면적·**이미 확보된 면적**·미상 사유."""

    area_sqm: float | None          # 면적 미상이면 None
    secured_sqm: float | None       # ★None = "확보 면적을 알 수 없다"(0 이 아니다)
    unparsed_share: bool            # 확보 소유자의 지분 표기를 못 읽었다
    undetermined_secured: bool      # 확보 여부(True/False) 자체가 미상이다


def _parcel_secured_area(parcel: dict[str, Any]) -> _SecuredArea:
    """필지 하나의 **이미 확보된 면적**(= 면적 × 확보 지분합). 확보 판정의 **단일 출처**다.

    ★★이 함수가 존재하는 이유는 실제로 갈라졌기 때문이다(2026-08-15 실증). `secured_ratio` 의
      분자는 **소유자 지분 단위**로 확보분을 셌는데, 최소건수 조합의 후보 필터는 **필지 단위
      플래그**(`use_right_secured is not True`)만 봤다. 그래서 소유자 단위로만 확보된(또는
      부분 확보된) 필지가 **전체 면적 그대로** 후보에 들어가, 이미 분자에 들어간 확보분을
      **두 번** 셌다:

          이미확보8000(소유자 지분 전부 확보) + 진짜필요2000 · 대지 10,000㎡
          → 확보율 80%(확보면적 8000) 인데 **추천 매입 = 이미확보8000**(이미 100% 보유한 필지!)
          → `resulting_ratio_pct` = **160.0%** (불가능한 숫자)

      같은 판정이 두 곳에 살면 반드시 갈라진다 — 그래서 `secured_ratio` 와
      `min_count_combination` 이 **둘 다 이 함수만** 호출한다(로직 복제 금지).

    ★미상은 0 으로 접지 않는다: 확보 여부·지분을 못 읽으면 `secured_sqm=None` 을 돌려주고,
      그 사실을 두 불리언으로 함께 실어 보낸다(호출부가 사유별로 다르게 처리해야 한다).
    """
    area = _parcel_area(parcel)

    parcel_flag = parcel.get("use_right_secured")
    parcel_flag = parcel_flag if isinstance(parcel_flag, bool) else None
    owners = [o for o in (parcel.get("owners") or []) if isinstance(o, dict)]

    if not owners:
        # 소유자 구조가 없으면 필지 단위 플래그가 곧 전 지분(1.0)이다. 미상이면 미상이다.
        if parcel_flag is None:
            return _SecuredArea(area, None, False, True)
        share = 1.0 if parcel_flag else 0.0
        return _SecuredArea(area, None if area is None else area * share, False, False)

    share_sum = 0.0
    unparsed = False
    undetermined = False
    for o in owners:
        sec = _owner_secured(o, parcel_flag)
        if sec is None:
            undetermined = True
            continue
        if not sec:
            continue  # 미확보 지분은 확보면적에 안 들어간다 — 지분 파싱도 불필요
        r = _share_ratio(o.get("share"))
        if r is None:
            unparsed = True
            continue
        share_sum += r

    if area is None or unparsed or undetermined:
        return _SecuredArea(area, None, unparsed, undetermined)
    return _SecuredArea(area, area * min(share_sum, 1.0), unparsed, undetermined)


def secured_ratio(
    parcels: list[dict[str, Any]] | None,
    housing_site_area_sqm: float | None,
) -> dict[str, Any]:
    """사용권원 확보율(%) — **분모를 받아야** 산정한다. 모르면 숫자를 내지 않고 거부한다.

    분자 = Σ(필지면적 × 확보 소유자 지분합) · 분모 = `housing_site_area_sqm`(주택건설대지면적).

    ★분모를 행 합계로 유도하지 않는 이유: 사용자는 보통 **미확보 필지만** 등록한다. 그 집합의
      면적 합을 분모로 쓰면 0% 아니면 100% 라는 무의미한 값이 나온다.
    ★거부 조건(하나라도 걸리면 숫자 없음): 분모 미입력·비양수 / 면적 미상 필지 존재 /
      확보 소유자의 지분 문자열 인식 실패 / 확보 여부(True·False) 미상.
    ★입력 행이 주택건설대지 전체를 덮지 않으면 분자가 **과소**가 된다 — 거부하지는 않되
      `coverage` 로 그 사실을 드러낸다(조용히 낮은 확보율을 내면 오독한다).
    """
    rows = [p for p in (parcels or []) if isinstance(p, dict)]
    missing_area: list[str] = []
    unparsed_share: list[str] = []
    undetermined_secured: list[str] = []

    try:
        denom = float(housing_site_area_sqm) if housing_site_area_sqm is not None else 0.0
    except (TypeError, ValueError):
        denom = 0.0

    secured_area = 0.0
    row_area_sum = 0.0

    for idx, p in enumerate(rows):
        pid = _pnu_of(p, idx)
        # ★확보면적 계산은 **공용 헬퍼 하나**만 쓴다 — 최소건수 조합의 후보 기여분도 같은
        #   함수를 쓴다(두 곳에서 따로 세다가 이중계상이 났다. `_parcel_secured_area` 참조).
        got = _parcel_secured_area(p)
        if got.area_sqm is None:
            missing_area.append(pid)
            continue
        row_area_sum += got.area_sqm
        if got.unparsed_share:
            unparsed_share.append(pid)
        if got.undetermined_secured:
            undetermined_secured.append(pid)
        if got.secured_sqm is not None:
            secured_area += got.secured_sqm

    if denom <= 0:
        return {
            "status": STATUS_UNDECIDABLE,
            "reason": (
                "주택건설대지면적(housing_site_area_sqm)이 입력되지 않아 확보율을 산정할 수 "
                "없습니다. 등록 필지 면적 합을 분모로 대신 쓰면(사용자는 보통 미확보 필지만 "
                "등록하므로) 0% 또는 100% 라는 무의미한 값이 나옵니다 — 추정하지 않습니다."
            ),
            "threshold_pct": SECURED_RATIO_THRESHOLD_PCT,
            "missing_area_pnus": sorted(set(missing_area)),
            "unparsed_share_pnus": sorted(set(unparsed_share)),
            "undetermined_secured_pnus": sorted(set(undetermined_secured)),
            "disclaimer": disclaimer(),
        }

    if missing_area or unparsed_share or undetermined_secured:
        return {
            "status": STATUS_UNDECIDABLE,
            "reason": (
                "면적 미상 필지 "
                f"{len(set(missing_area))}건 · 지분 표기 인식 실패 {len(set(unparsed_share))}건 · "
                f"확보 여부 미상 {len(set(undetermined_secured))}건이 있어 확보율을 산정하지 "
                "않습니다. 아는 값만 합하면 실제보다 높은 확보율이 나와 95% 게이트를 잘못 "
                "통과합니다(미상을 0 으로 접지 않습니다)."
            ),
            "threshold_pct": SECURED_RATIO_THRESHOLD_PCT,
            "missing_area_pnus": sorted(set(missing_area)),
            "unparsed_share_pnus": sorted(set(unparsed_share)),
            "undetermined_secured_pnus": sorted(set(undetermined_secured)),
            "disclaimer": disclaimer(),
        }

    if secured_area > denom * 1.0001:
        return {
            "status": STATUS_UNDECIDABLE,
            "reason": (
                f"확보 면적({round(secured_area, 2)}㎡)이 주택건설대지면적({round(denom, 2)}㎡)을 "
                "넘습니다 — 입력이 서로 모순되어 확보율을 내지 않습니다."
            ),
            "threshold_pct": SECURED_RATIO_THRESHOLD_PCT,
            "missing_area_pnus": [], "unparsed_share_pnus": [], "undetermined_secured_pnus": [],
            "disclaimer": disclaimer(),
        }

    ratio_pct = secured_area / denom * 100.0
    covers_site = row_area_sum >= denom * 0.9999
    return {
        "status": STATUS_OK,
        "secured_ratio_pct": round(ratio_pct, 4),
        "secured_area_sqm": round(secured_area, 2),
        "housing_site_area_sqm": round(denom, 2),
        "threshold_pct": SECURED_RATIO_THRESHOLD_PCT,
        "meets_threshold": ratio_pct >= SECURED_RATIO_THRESHOLD_PCT,
        "missing_area_pnus": [], "unparsed_share_pnus": [], "undetermined_secured_pnus": [],
        "coverage": {
            "row_area_sum_sqm": round(row_area_sum, 2),
            "covers_site": covers_site,
            "note": (
                "입력 필지 면적 합이 주택건설대지면적에 못 미칩니다 — 등록되지 않은 확보분이 "
                "있으면 위 확보율은 **과소**입니다."
                if not covers_site
                else "입력 필지가 주택건설대지면적을 덮습니다."
            ),
        },
        "basis": (
            "분자=Σ(필지면적×확보 소유자 지분합), 분모=주택건설대지면적(입력). "
            f"임계={SECURED_RATIO_THRESHOLD_PCT}%(주택법 §22①1호)."
        ),
        "disclaimer": disclaimer(),
    }


# ── 제척(구역계 변경) 위상 판정 ─────────────────────────────────────────────

def severability(
    graph: dict[str, Any] | None,
    exclusion_pnus: list[str] | None,
) -> dict[str, Any]:
    """제외 **집합**을 실제로 빼 보고 부지가 분단되는지 판정한다(개별 절단점 판정 아님).

    ★반증(실행 확인): 안마당을 둘러싼 4필지 고리에서 `articulation_points` 는 **빈 배열**이다.
      그런데 각자 "안전"한 LEFT + RIGHT 를 **함께** 빼면 부지가 2조각이 된다 — 4-사이클은
      절단점 0개지만 크기 2의 절단 집합을 갖는다. 따라서 "articulation 목록에 없으니 빼도
      된다"는 판정은 **원리적으로 틀렸다**.
    ★`parcel_graph._components`(BFS)를 그대로 호출한다 — 같은 판정이 두 곳에 생기면 갈라진다.
    ★geometry 미확보 필지는 `n_minus_1[pid]["remains_connected"]` 가 이미 True|False|**None**
      3값이다. None 은 **절대 "가능"이 아니다** — 판정 불가로 낸다.
    ★위상은 구역 지정요건(면적·접도율·노후도)을 증명하지 못한다 → "제척 가능"이라 말하지 않고
      `topology_severable`(위상상 분단 없음)까지만 말하며 `procedure_required` 를 항상 붙인다.
    """
    from app.services.zoning.parcel_graph import _components

    base: dict[str, Any] = {
        "severable": None,
        "topology_severable": None,
        "component_count_before": None,
        "component_count_after": None,
        "undecidable_pnus": [],
        "excluded_pnus": [],
        "procedure_required": PROCEDURE_REQUIRED,
        "basis": (
            "제외 집합을 제거한 뒤 연결성분 수를 재계산해 기준(제거 전) 성분 수와 비교한다. "
            "개별 필지의 articulation 소속 여부로 판정하지 않는다(4-사이클 반증)."
        ),
        "disclaimer": disclaimer(),
    }

    # ★전제 가드가 **가장 먼저**다 — `skipped_large_set` 응답에는 `articulation_points` 키가
    #   **아예 없다**. 다른 키를 먼저 읽으면 KeyError 로 죽거나 None 을 "없음"으로 오독한다.
    if not isinstance(graph, dict):
        return {**base, "reason": "인접 그래프가 없어 제척 위상 판정을 할 수 없습니다."}
    status = graph.get("status")
    if status != "ok":
        return {
            **base,
            "reason": (
                f"인접 그래프 status={status!r} — 위상 판정 전제가 성립하지 않습니다"
                "(필지 수 상한 초과·입력 없음·필지 식별자 중복 등)."
            ),
        }

    exclusions = [str(x) for x in (exclusion_pnus or []) if str(x).strip()]
    exclusion_set = set(exclusions)
    base["excluded_pnus"] = sorted(exclusion_set)
    if not exclusion_set:
        return {**base, "reason": "제외 대상 필지가 지정되지 않아 판정할 것이 없습니다."}

    adjacency_raw = graph.get("adjacency") or {}
    known_ids = list(adjacency_raw)
    before = graph.get("component_count")
    base["component_count_before"] = before

    # ★이중 가드(변이 감사) — 이 분기를 지워도 단일 필지는 아래 geometry 게이트에서
    #   `n_minus_1[pid].remains_connected is None`(제거 후 남는 필지 없음)으로 걸려
    #   같은 '판정 불가'가 나온다. 사유 문구가 달라질 뿐이라 의도를 명시하려 남긴다.
    if len(known_ids) < 2:
        return {
            **base,
            "reason": (
                f"형상 확보 필지가 {len(known_ids)}개뿐이라 '빼도 이어지는가'를 물을 수 없습니다"
                "(유일 필지 제외를 '가능'이라 하지 않습니다)."
            ),
        }
    if before != 1:
        return {
            **base,
            "reason": (
                f"제거 전 연결성분이 {before}개입니다 — 이미 분리된 집합에는 제척 위상 판정이 "
                "성립하지 않습니다(먼저 구역 자체를 정리해야 합니다)."
            ),
        }

    # geometry 미확보·그래프 미포함 필지가 섞이면 집합 판정 자체가 불가하다.
    n_minus_1 = graph.get("n_minus_1") or {}
    undecidable = []
    for pid in sorted(exclusion_set):
        entry = n_minus_1.get(pid)
        if not isinstance(entry, dict) or entry.get("remains_connected") is None:
            undecidable.append(pid)
    if undecidable:
        return {
            **base,
            "undecidable_pnus": undecidable,
            "reason": (
                f"형상(geometry) 미확보 필지 {len(undecidable)}건이 제외 집합에 포함돼 있어 "
                "분단 여부를 계산할 수 없습니다 — '판정 불가'이며 '가능'이 아닙니다."
            ),
        }

    remaining = [i for i in known_ids if i not in exclusion_set]
    if not remaining:
        return {
            **base,
            "reason": "제외 후 남는 필지가 없습니다 — 전량 제척은 사업 자체가 성립하지 않습니다.",
        }

    restricted = {
        i: {nb for nb in (adjacency_raw.get(i) or ()) if nb not in exclusion_set}
        for i in remaining
    }
    after = len(_components(remaining, restricted))
    ok = after <= before

    return {
        **base,
        "severable": ok,
        "topology_severable": ok,
        "component_count_after": after,
        "reason": (
            (
                f"제외 집합({', '.join(sorted(exclusion_set))})을 빼도 잔여 {len(remaining)}필지가 "
                f"연결성분 {after}개로 유지됩니다 — **위상상** 분단은 없습니다. 다만 구역 지정요건"
                "(면적·접도율·노후도)은 위상이 증명하지 못하므로 아래 절차에서 확인해야 합니다."
            )
            if ok
            else (
                f"제외 집합({', '.join(sorted(exclusion_set))})을 빼면 잔여 부지가 연결성분 "
                f"{after}개로 **분단**됩니다(제거 전 {before}개). 개별 필지는 각각 절단점이 "
                "아니어도 집합으로는 절단이 될 수 있습니다."
            )
        ),
    }


# ── 95% 도달 최소 **건수** 조합 ────────────────────────────────────────────

def min_count_combination(
    candidate_parcels: list[dict[str, Any]] | None,
    housing_site_area_sqm: float | None,
    current_secured_sqm: float | None,
) -> dict[str, Any]:
    """95% 확보에 필요한 **최소 건수** 조합. 목적함수는 **하나**다.

    ★★후보의 기여분은 **면적 − 이미 확보된 면적**이다(원면적이 아니다). 원면적을 쓰면
      `current_secured_sqm` 에 이미 들어간 확보분을 **두 번** 세게 되어, 사용자가 이미 100%
      보유한 필지를 "사라"고 권고하고 확보율 160% 라는 불가능한 숫자를 낸다(실증 2026-08-15).
      기여분이 0 인 필지(전량 확보)는 후보 목록에서 **아예 뺀다** — 살 것이 없는 필지다.

    ★"최소 비용/최소 건수"를 한 함수에 섞지 않는다 — 두 목적은 최적해가 다르다(워크드 예제:
      면적 그리디 1필지 30억 vs 최소비용 2필지 7억, 4.3배). 이 저장소에는 **단가 필드가 어디에도
      없다**. 없는 데이터로 비용 최적화를 흉내 내면 그 숫자가 매입 결정에 쓰인다.
      → 단가 입력이 생기면 **최소비용 탐색은 별도 함수로** 추가한다(이 함수를 확장하지 않는다).

    ★최소 건수는 그리디로 **정확히** 풀린다: 임의의 k 에 대해 면적 상위 k 개가 달성 가능 면적을
      최대화하므로, 임계를 넘기는 최소 k 가 곧 최적해다. 그 근거를 `optimality` 로 항상 싣는다.

    ★면적 미상 후보가 하나라도 있으면 조합을 내지 않는다(§2a 와 같은 규칙 — 아는 값만 합하면
      "이 2필지면 된다"는 **틀린 실행 지시**가 나간다).
    ★전부 확보해도 95% 에 못 미치면 빈 배열이 아니라 `"달성 불가"` 를 명시한다 —
      빈 배열은 "쉽다"로 오독된다.
    """
    rows = [p for p in (candidate_parcels or []) if isinstance(p, dict)]
    common: dict[str, Any] = {
        "optimality": OPTIMALITY_MIN_COUNT,
        "threshold_pct": SECURED_RATIO_THRESHOLD_PCT,
        # ★기여분 0(=이미 전량 확보)으로 후보에서 빠진 필지를 **표면에 드러낸다**.
        #   조용히 빼면 "왜 이 필지가 추천에 없지?"를 사용자가 알 수 없다.
        "already_secured_pnus": [],
        "cost_note": (
            "최소 **비용** 조합은 산출하지 않습니다 — 이 플랫폼에 필지 단가 데이터가 없습니다. "
            "단가 입력이 생기면 별도 탐색으로 추가합니다(면적 최소건수와 최적해가 다릅니다)."
        ),
        "price_basis": PRICE_BASIS,
        "disclaimer": disclaimer(),
    }

    try:
        denom = float(housing_site_area_sqm) if housing_site_area_sqm is not None else 0.0
    except (TypeError, ValueError):
        denom = 0.0
    try:
        secured = float(current_secured_sqm) if current_secured_sqm is not None else -1.0
    except (TypeError, ValueError):
        secured = -1.0

    if denom <= 0 or secured < 0:
        return {
            **common,
            "status": STATUS_UNDECIDABLE,
            "reason": (
                "주택건설대지면적 또는 현재 확보면적이 없어 목표 부족분을 계산할 수 없습니다."
            ),
            "combination_pnus": None,
            "missing_area_pnus": [],
        }

    missing: list[str] = []
    already_secured: list[str] = []
    candidates: list[tuple[str, float]] = []
    for idx, p in enumerate(rows):
        pid = _pnu_of(p, idx)
        got = _parcel_secured_area(p)   # ★확보면적 판정의 단일 출처(분자와 같은 함수)
        if got.area_sqm is None:
            missing.append(pid)
            continue
        # ★확보 정보가 아예 없는 행은 확보분 0 으로 본다 — 이 인자는 '매입 후보'이고,
        #   조립 경로(`build_strategy`)는 **확보율이 산정된 경우에만** 기준선을 넘긴다.
        #   확보율 산정 = 모든 행의 확보 여부·지분이 확정됐다는 뜻이라, 그 경로에서
        #   `secured_sqm is None` 은 나오지 않는다(미상은 확보율 단계에서 이미 거부된다).
        already = 0.0 if got.secured_sqm is None else got.secured_sqm
        remaining = got.area_sqm - already
        if remaining <= 0:
            already_secured.append(pid)   # 이미 전량 확보 — 살 것이 없다(후보가 아니다)
            continue
        candidates.append((pid, remaining))

    common["already_secured_pnus"] = sorted(set(already_secured))

    if missing:
        return {
            **common,
            "status": STATUS_UNDECIDABLE,
            "reason": (
                f"면적 미상 후보 {len(set(missing))}건이 있어 최소 건수 조합을 내지 않습니다 — "
                "아는 면적만으로 조합을 내면 실제로는 95% 에 못 미치는 실행 지시가 나갑니다."
            ),
            "combination_pnus": None,
            "missing_area_pnus": sorted(set(missing)),
        }

    target_area = denom * (SECURED_RATIO_THRESHOLD_PCT / 100.0)
    needed = target_area - secured
    if needed <= 0:
        return {
            **common,
            "status": STATUS_ALREADY_MET,
            "reason": (
                f"현재 확보면적({round(secured, 2)}㎡)이 이미 임계"
                f"({round(target_area, 2)}㎡ = {SECURED_RATIO_THRESHOLD_PCT}%)를 충족합니다."
            ),
            "combination_pnus": [],
            "count": 0,
            "needed_area_sqm": 0.0,
            "missing_area_pnus": [],
        }

    total_available = sum(a for _, a in candidates)
    if total_available < needed:
        return {
            **common,
            "status": STATUS_UNREACHABLE,
            "reason": (
                f"미확보 필지 {len(candidates)}건을 **전부** 확보해도 "
                f"{round(total_available, 2)}㎡ 로 부족분 {round(needed, 2)}㎡ 에 미달합니다 — "
                f"{SECURED_RATIO_THRESHOLD_PCT}% 도달이 불가능합니다(구역 재설정·제척 검토 필요)."
            ),
            "combination_pnus": None,
            "needed_area_sqm": round(needed, 2),
            "available_area_sqm": round(total_available, 2),
            "missing_area_pnus": [],
        }

    ordered = sorted(candidates, key=lambda x: (-x[1], x[0]))
    picked: list[str] = []
    acc = 0.0
    for pid, remaining in ordered:
        picked.append(pid)
        acc += remaining
        if acc >= needed:
            break

    # ★★확보율 100% 초과는 **결과가 아니라 버그다** — 숫자로 내지 않는다.
    #   `secured_ratio` 가 `secured_area > denom` 을 '모순'으로 거부하는 것과 같은 규율이다
    #   (분자가 분모를 넘을 수 없다). 이중계상이 살아 있던 동안 이 자리에서 실제로 160% 가
    #   찍혔다 — 그때 이 가드가 있었다면 틀린 실행 지시가 조용히 나가지 않았을 것이다.
    if secured + acc > denom * 1.0001:
        return {
            **common,
            "status": STATUS_UNDECIDABLE,
            "reason": (
                f"확보면적({round(secured, 2)}㎡) + 추가 확보면적({round(acc, 2)}㎡)이 "
                f"주택건설대지면적({round(denom, 2)}㎡)을 넘습니다 — 입력이 서로 모순되어 "
                "조합을 내지 않습니다(확보율은 100% 를 넘을 수 없습니다)."
            ),
            "combination_pnus": None,
            "needed_area_sqm": round(needed, 2),
            "available_area_sqm": round(total_available, 2),
            "missing_area_pnus": [],
        }

    return {
        **common,
        "status": STATUS_OK,
        "combination_pnus": picked,
        "count": len(picked),
        "added_area_sqm": round(acc, 2),
        "needed_area_sqm": round(needed, 2),
        "resulting_ratio_pct": round((secured + acc) / denom * 100.0, 4),
        "missing_area_pnus": [],
        "reason": (
            f"미확보 기여분 상위 {len(picked)}필지({round(acc, 2)}㎡)를 먼저 확보하면 부족분"
            f"({round(needed, 2)}㎡)을 넘겨 {SECURED_RATIO_THRESHOLD_PCT}% 에 도달합니다. "
            "그 시점부터 잔여 전부에 매도청구가 가능해집니다(주택법 §22①1호)."
        ),
    }


# ── 조립 표면 — (필지 × 소유자) 행 ─────────────────────────────────────────

def _row_action(
    *,
    owner_judgment: str | None,
    governing_act: str | None,
    instrument: str | None,
    requires_track_input: bool,
    ratio_known: bool,
    meets_threshold: bool,
    in_exclusion_set: bool,
    exclusion_ok: bool | None,
) -> tuple[str, str]:
    """행 하나의 권고 액션 + 사유. 우선순위를 **코드로 명시**한다(암묵 순서 금지)."""
    housing_act = governing_act == HOLDING_PERIOD_ACT

    # ① 근거법령 자체가 확정되지 않으면 어떤 액션도 말할 수 없다.
    if governing_act is None:
        return ACTION_UNDECIDED, (
            "사업방식의 근거법령이 확정되지 않아(미지정 또는 트랙 입력 필요) 강제취득 수단을 "
            "말할 수 없습니다."
        )
    # ①-b 근거법령은 확정이어도 **강제취득 수단**이 트랙에 따라 갈리면 액션을 단정할 수 없다.
    #     소규모정비특례법 §35 **본문 단서**: 「§35의2 에 따라 수용·사용할 수 있는 경우는 제외」
    #     → 소규모재개발·관리지역 가로주택(공공시행)은 **수용**이라 매도청구 대상이 아니다.
    #     `scheme` 만으로 갈리지 않는다 — 시행자 유형·관리지역 여부가 분류를 뒤집는다.
    #     ★역세권 활성화(근거법령 자체가 모호)와 **같은 기제**를 쓴다(정책표 하나로 관리).
    if requires_track_input:
        return ACTION_UNDECIDED, (
            f"근거법령은 {governing_act}이나 강제취득 수단이 사업 트랙(시행자 유형·관리지역 "
            "여부)에 따라 매도청구/수용으로 갈립니다 — 트랙이 입력되기 전에는 액션을 확정하지 "
            "않습니다(소규모정비특례법 §35 본문 단서: §35의2 수용 대상 제외)."
        )
    # ② 주택법 계열인데 보유기간 판정이 보류면(기준일·취득일 부재) 행을 확정하지 않는다.
    if housing_act and owner_judgment not in ("가능(원칙)", "불가(장기보유 추정)"):
        return ACTION_UNDECIDED, (
            f"보유기간 판정이 '{owner_judgment}'라 매도청구 가부를 확정할 수 없습니다"
            "(기준일·취득일 자료 보완 필요)."
        )
    # ③ 제척은 **집합 판정이 통과했을 때만** 제안한다(개별 절단점 판정 아님).
    if in_exclusion_set and exclusion_ok is True:
        return ACTION_EXCLUSION_REVIEW, (
            "제외 집합을 빼도 잔여 부지의 연결성분이 늘지 않습니다(위상상 분단 없음) — "
            f"{PROCEDURE_REQUIRED} 절차로 제척 가능성을 검토합니다."
        )
    if in_exclusion_set and exclusion_ok is None:
        return ACTION_UNDECIDED, (
            "제외 집합의 위상 판정이 불가(형상 미확보·전제 미충족)해 제척 여부를 말할 수 없습니다."
        )
    # ④ 도시개발법 = 수용(토지보상법 준용). 매도청구가 아니다.
    if instrument == "수용":
        return ACTION_EXPROPRIATION, (
            "도시개발법 §22 수용방식 — 매도청구가 아니라 토지보상법 준용 수용 절차"
            "(협의→재결→보상)입니다. 동의요건(면적 2/3 + 소유자 총수 1/2) 충족 여부는 별도 확인."
        )
    # ⑤ 주택법 계열 — 확보율이 액션을 가른다.
    if housing_act:
        if not ratio_known:
            return ACTION_UNDECIDED, (
                "사용권원 확보율을 산정할 수 없어(면적·지분·분모 미상) 매도청구 성립 여부를 "
                "말할 수 없습니다."
            )
        if meets_threshold:
            return ACTION_SELL_CLAIM, (
                f"확보율이 {SECURED_RATIO_THRESHOLD_PCT}% 이상이라 미확보 대지의 **모든** "
                "소유자에게 매도청구가 가능합니다(주택법 §22①1호, 보유기간 무관)."
            )
        if owner_judgment == "불가(장기보유 추정)":
            return ACTION_NEGOTIATE, (
                f"확보율 {SECURED_RATIO_THRESHOLD_PCT}% 미만 + 결정고시일 기준 10년 이상 계속보유 "
                "→ 매도청구 대상에서 제외됩니다(주택법 §22①2호). 강제수단이 없어 협의매수가 "
                "유일한 경로입니다."
            )
        return ACTION_SELL_CLAIM, (
            f"확보율 {SECURED_RATIO_THRESHOLD_PCT}% 미만이나 결정고시일 기준 10년 미만 보유라 "
            "매도청구 대상입니다(주택법 §22①2호)."
        )
    # ⑥ 동의율 기반(도정법 §64 · 소규모정비특례법 §35) — 보유기간 요건이 **없다**.
    #    (그래서 여기서는 owner_judgment 를 보지 않는다 — 보면 없는 요건을 씌우는 셈이다.)
    return ACTION_SELL_CLAIM, (
        f"{governing_act}은(는) 동의율 기준이라 보유기간 요건이 없습니다 — 동의요건 충족 후 "
        "미동의자에게 매도청구가 가능합니다(동의현황·시행자 유형은 별도 확인 필요)."
    )


def build_strategy(
    survey: dict[str, Any] | None,
    parcels: list[dict[str, Any]] | None = None,
    *,
    scheme: str | None = None,
    housing_site_area_sqm: float | None = None,
    current_secured_sqm: float | None = None,
    graph: dict[str, Any] | None = None,
    exclusion_candidates: list[str] | None = None,
) -> dict[str, Any]:
    """P1 조사결과(`survey_selected_parcels()`) + 필지 제원 → **매입전략 판정표**.

    `survey`: P1 응답 그대로(cards→owners 판정 포함). 이 서비스는 **P1 을 우회하지 않는다**.
    `parcels`: 면적·확보 여부·지분 등 제원(등기 발급 결과와 별개 입력).
    `exclusion_candidates`: 사용자가 제안한 제척 **집합**(집합 단위로 위상 판정한다).
    """
    survey = survey if isinstance(survey, dict) else {}
    cards = [c for c in (survey.get("cards") or []) if isinstance(c, dict)]
    rows_in = [p for p in (parcels or []) if isinstance(p, dict)]
    scheme = scheme if scheme is not None else survey.get("scheme")

    from app.services.development.scenario_simulator import scheme_legal_profile

    profile = scheme_legal_profile(scheme) or {}
    governing_act = profile.get("governing_act")
    instrument = profile.get("instrument")
    # ★`instrument` 는 트랙이 확정된 뒤에만 단정할 수 있다 — 정책표가 그 사실을 이 플래그로
    #   실어 나른다(값만 보고 "매도청구"라 단정하면 §35의2 수용 대상을 오분류한다).
    requires_track_input = bool(profile.get("requires_track_input"))

    ratio = secured_ratio(rows_in, housing_site_area_sqm)
    ratio_known = ratio.get("status") == STATUS_OK
    meets = bool(ratio.get("meets_threshold")) if ratio_known else False

    sev = severability(graph, exclusion_candidates) if exclusion_candidates else None
    exclusion_set = set(str(x) for x in (exclusion_candidates or []))
    exclusion_ok = sev.get("severable") if isinstance(sev, dict) else None

    # ★★후보는 **전 행**을 그대로 넘긴다. 종전에는 여기서 `use_right_secured is not True` 로
    #   걸렀는데, 그 필터는 **필지 단위 플래그**만 보고 `secured_ratio` 의 분자는 **소유자 지분
    #   단위**로 셌다 — 두 판정이 갈라져, 소유자 단위로만 확보된(또는 부분 확보된) 필지가
    #   확보분과 후보에 **동시에** 잡히는 이중계상이 났다(확보율 160%·이미 가진 필지를 매입 추천).
    #   기여분(면적 − 이미 확보면적)과 전량 확보 제외는 `min_count_combination` 이 같은 공용
    #   헬퍼(`_parcel_secured_area`)로 판정한다 — 필터를 두 곳에 두지 않는다.
    combo = min_count_combination(
        rows_in,
        housing_site_area_sqm,
        ratio.get("secured_area_sqm") if ratio_known else current_secured_sqm,
    )

    by_pnu = {_pnu_of(p, i): p for i, p in enumerate(rows_in)}
    by_address = {str(p.get("address")): p for p in rows_in if p.get("address")}

    rows: list[dict[str, Any]] = []
    for card in cards:
        pnu = card.get("pnu")
        pid = str(pnu) if pnu not in (None, "") else None
        parcel = by_pnu.get(pid or "") or by_address.get(str(card.get("address") or ""))
        in_excl = bool(pid and pid in exclusion_set)
        area = _parcel_area(parcel) if parcel else None

        owners = card.get("owners") or []
        if not owners:
            # ★조용히 빈 행으로 만들지 않는다 — 왜 판정이 없는지 사유를 남긴다(P1 계약 승계).
            rows.append({
                "pnu": pnu,
                "address": card.get("address"),
                "parcel": card.get("parcel"),
                "owner": None,
                "share": None,
                "area_sqm": area,
                "card_status": card.get("status"),
                "action": ACTION_UNDECIDED,
                "action_reason": card.get("message") or "권리분석 결과가 없어 판정할 수 없습니다.",
                "priority_label": PRIORITY_UNDECIDED_LABEL,
                "sell_claim_judgment": None,
                # 권리분석 카드 자체가 없는 갈래 — 값도 사유도 상류에 없다.
                "sell_claim_judgment_absent": SOURCE_UNAVAILABLE,
                "governing_act": governing_act,
                "instrument": instrument,
                "in_exclusion_set": in_excl,
                "price_basis": PRICE_BASIS,
                "procedure_required": PROCEDURE_REQUIRED,
                "disclaimer": disclaimer(),
            })
            continue

        for owner in owners:
            judgment = owner.get("sell_claim_judgment")
            action, reason = _row_action(
                owner_judgment=judgment,
                governing_act=governing_act,
                instrument=instrument,
                requires_track_input=requires_track_input,
                ratio_known=ratio_known,
                meets_threshold=meets,
                in_exclusion_set=in_excl,
                exclusion_ok=exclusion_ok,
            )
            # ★A 라벨(§2-A)은 **주택법 계열 + 확보율 산정 가능**일 때만 붙는다.
            #   확보율을 모르면 "지금 1순위인가"를 물을 수 없다 → 라벨도 판정보류다.
            if governing_act != HOLDING_PERIOD_ACT:
                priority = None
            elif not ratio_known:
                priority = PRIORITY_UNDECIDED_LABEL
            elif (not meets) and judgment == "불가(장기보유 추정)":
                priority = PRIORITY_A_LABEL
            else:
                priority = None

            row: dict[str, Any] = {
                "pnu": pnu,
                "address": card.get("address"),
                "parcel": card.get("parcel"),
                "owner": owner.get("owner"),
                "share": owner.get("share"),
                "area_sqm": area,
                "card_status": card.get("status"),
                "holding_period_years": owner.get("holding_period_years"),
                "inheritance": owner.get("inheritance"),
                "inheritance_aggregated": owner.get("inheritance_aggregated"),
                "sell_claim_judgment": judgment,
                # ★사유 **코드**도 함께 나른다 — 상류가 붙여도 중간이 안 옮기면
                #   최종 표면에서 사라진다(이 저장소가 반복해 겪은 orphan handoff).
                "sell_claim_judgment_absent": owner.get("sell_claim_judgment_absent"),
                "sell_claim_reason": owner.get("sell_claim_reason"),
                "evidence": owner.get("evidence"),
                "governing_act": governing_act,
                "instrument": instrument,
                "action": action,
                "action_reason": reason,
                "priority_label": priority,
                "in_exclusion_set": in_excl,
                "price_basis": PRICE_BASIS,   # ★시가 숫자를 내지 않는다
                "procedure_required": PROCEDURE_REQUIRED,
                "disclaimer": disclaimer(),   # ★구조화 면책(형제 필드) — 배지로 살아남는다
            }
            if action == ACTION_SELL_CLAIM and governing_act == HOLDING_PERIOD_ACT:
                row["prerequisite"] = (
                    "매도청구 전 **3개월 이상 협의**가 법정 선행요건입니다(주택법 §22①)."
                )
            rows.append(row)

    by_action = {a: sum(1 for r in rows if r["action"] == a) for a in ACTIONS}
    return {
        "scheme": scheme,
        "governing_act": governing_act,
        "instrument": instrument,
        # ★동의율 기반 방식(도정법 §64·특례법 §35)은 **동의요건이 곧 판정 근거**다 —
        #   근거 없이 "매도청구 가능"만 내면 사용자가 무엇을 충족해야 하는지 모른다.
        "legal": {
            "basis": profile.get("basis"),
            "consent_required": profile.get("consent_required"),
            "consent_threshold_pct": profile.get("consent_threshold_pct"),
            "requires_track_input": profile.get("requires_track_input"),
        },
        "action_enum": list(ACTIONS),
        "secured_ratio": ratio,
        "severability": sev,
        "min_count_combination": combo,
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "by_action": by_action,
            "priority_a_count": sum(1 for r in rows if r.get("priority_label") == PRIORITY_A_LABEL),
            "priority_undecided_count": sum(
                1 for r in rows if r.get("priority_label") == PRIORITY_UNDECIDED_LABEL
            ),
            "secured_ratio_available": ratio_known,
            "geometry_unknown_count": len((graph or {}).get("geometry_unknown_pnus") or []),
        },
        "price_basis": PRICE_BASIS,
        "procedure_required": PROCEDURE_REQUIRED,
        "disclaimer": disclaimer(),
    }
