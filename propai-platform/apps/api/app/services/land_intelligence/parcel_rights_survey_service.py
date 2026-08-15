"""토지필지 종합분석 **P1 — 선택 필지 병렬 발급·권리분석**.

## 왜 이 단계인가

P0(`parcel_survey_quote_service`)가 "얼마인가·무엇을 아는가"를 보여준 뒤, 사용자가
비용을 쓸 필지를 **직접 선택**한다. 이 서비스는 그 선택된 필지들을 **병렬로 발급→
권리분석**해 필지별 카드 + 세트 요약을 돌려준다.

★새 분석엔진을 만들지 않는다. 발급·권리분석 본체는 그대로
`app.services.registry.registry_analysis_service.RegistryAnalysisService.analyze()` 를
호출한다(말소기준권리·인수/소멸 판정, 소유자 구조화, 캐시, PDF 그라운딩이 이미 거기 있다).
이 서비스가 얹는 것은 **딱 하나** — 그 결과 위에 "소유자별 매도청구 가능여부(보유기간
기준)" 판정 계층이다. 과금(`issued_count`/`analysis_charged`)도 기존 라우터 헬퍼가
그대로 소비할 수 있게 원본 분석 결과를 `analysis` 로 카드에 그대로 실어 보낸다
(이 서비스 자체는 과금하지 않는다 — 배선은 호출부의 몫).

## 법령 원문 대조로 확정된 제약(구현 근거)

1. **판정 단위 = (필지 × 소유자)**. "매도청구 불가"는 소유자 속성이다 → 카드마다
   `owners: [...]` 배열로 소유자별 판정을 낸다(공유필지는 소유자 수만큼 갈린다).
2. **보유기간 기준일 = 「지구단위계획구역 결정고시일」**(주택법 §22①2호) — **오늘이
   아니다**. 미입력이면 판정하지 않는다(`_judge_owner`가 `district_plan_decision_date is
   None`이면 즉시 "판정 보류"를 반환하고 오늘 날짜로 임의 계산하지 않는다).
3. **상속은 피상속인 보유기간을 합산**한다. 이 서비스는 등기 분석이 낸 취득원인
   문자열로 상속 여부를 1차 판별하되(`_classify_inheritance`), **피상속인의 원취득일은
   현재 등기분석 스키마가 구조화하지 않아 실제로 합산할 수 없다** — 그래서 상속으로
   판별되든 판별 불가이든 항상 `inheritance_aggregation_note`로 "합산 여부 미확인"을
   명시하고, 산출한 보유기간을 확정치가 아닌 자기 보유분만의 값으로 표기한다(합산
   안 한 값을 확정처럼 내지 않는다).
4. **원문 근거 스니펫**: 각 소유자 판정에는 등기 분석이 구조화한 취득일·취득원인·
   지분 문자열을 그대로 담은 `evidence`를 동반한다(재파싱 LLM 콜을 추가하지 않는다 —
   그린필드 금지. `_SYSTEM`/`_TMPL` 프롬프트가 "등기 내용에 있는 사실만 사용, 없으면
   '기재 없음'"을 강제하므로 이 필드들 자체가 원문 그라운딩된 근거다).
5. **부분 실패 허용**: 필지 하나의 발급·분석이 예외를 던지거나 등기부를 확보하지
   못해도(`status != "ok"`) 전체 응답이 죽지 않는다. 그 필지의 카드에 `status`와
   `message`(사유)를 남기고 나머지 필지는 계속 처리한다.
6. **동시성 상한**: 아래 `_MAX_CONCURRENT_ISSUES` 참조.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ★동시성 상한 — 외부 등기 발급 API(CODEF/틸코)는 건당 30~50초가 걸리고 **건당 과금**된다.
#   무제한 병렬 발급은 (1) 프로바이더 rate limit을 넘겨 동시다발 실패를 유발하고,
#   (2) 실패 시 재시도 로직과 얽히면 같은 필지에 중복 발급·중복 과금 위험을 키운다.
#   P0(견적) 화면에서 필지 수·예상 비용을 이미 보여준 뒤 진입하는 단계라, 여기서는
#   처리량보다 프로바이더 안정성·과금 정확성을 우선한다.
_MAX_CONCURRENT_ISSUES = 4

# 지구단위계획구역 결정고시일(주택법 §22①2호) 기준 이 연수 이상 "계속 보유"하면
# 매도청구 대상에서 제외되는 것으로 1차 판정한다(장기보유 예외).
_LONG_TERM_HOLDING_YEARS = 10

# 등기 취득원인 문자열에서 상속 여부를 판별하는 키워드. 목록에 없는 표현은
# "판별 불가"로 정직하게 처리한다(추측 금지).
_INHERIT_KEYWORDS = ("상속",)
_NON_INHERIT_KEYWORDS = (
    "매매", "증여", "교환", "신탁", "신축", "보존", "경매", "공매", "분할", "판결",
    "수용", "협의분할", "재산분할", "환매",
)

# "2015년 3월 2일" / "2015.03.02" / "2015-3-2" / "2015/03/02" 등 등기부 관용 표기 흡수.
_KDATE_RE = re.compile(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")

_EMPTY_MARKERS = ("", "기재 없음", "데이터 없음", "없음")


def _parse_kdate(s: str | None) -> date | None:
    """등기부·사용자 입력에 흔한 한국식 날짜 표기를 `date`로 변환. 실패 시 None(추측 금지)."""
    if not s or s.strip() in _EMPTY_MARKERS:
        return None
    m = _KDATE_RE.search(s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _classify_inheritance(cause_raw: str | None) -> dict[str, Any]:
    """취득원인 문자열에서 상속 여부를 판별. 모호하면 '판별 불가'(추측하지 않는다)."""
    c = (cause_raw or "").strip()
    # ★이중 가드 — 아래로 흘러도(키워드 매칭 전부 실패) 마지막 fallback이 동일하게
    #   "판별 불가"를 반환하므로, 이 조기 반환을 지워도 빈 문자열 입력의 결과는 같다.
    #   그래도 남기는 이유: 의도(비어있으면 즉시 판별 불가)를 코드로 명시하기 위함.
    if not c or c in _EMPTY_MARKERS:
        return {"status": "판별 불가", "cause_raw": cause_raw}
    if any(k in c for k in _INHERIT_KEYWORDS):
        return {"status": "상속", "cause_raw": cause_raw}
    if any(k in c for k in _NON_INHERIT_KEYWORDS):
        return {"status": "비상속", "cause_raw": cause_raw}
    return {"status": "판별 불가", "cause_raw": cause_raw}


def _owner_evidence(owner: dict[str, Any]) -> str:
    """★제약4 — 원문 근거 스니펫. 등기 분석이 구조화한 필드를 그대로 담는다(재파싱 없음)."""
    name = owner.get("name") or "성명 미상"
    share = owner.get("share") or "기재 없음"
    acq_date = owner.get("acquisition_date") or "기재 없음"
    acq_cause = owner.get("acquisition_cause") or "기재 없음"
    return f"[등기분석 추출] 소유자: {name} · 지분: {share} · 취득일: {acq_date} · 취득원인: {acq_cause}"


def _predecessor_acquisition(
    owner: dict[str, Any], history: list[dict[str, Any]] | None
) -> tuple[date | None, dict[str, Any] | None]:
    """상속 합산용 — **피상속인의 취득일**을 소유권 이전 이력에서 찾는다.

    ★주택법 §22①2호는 상속 취득 시 **피상속인의 소유기간을 합산**하도록 정한다.
      합산을 못 하면 상속 필지가 "보유 3년"으로 보여 **매도청구 가능으로 오분류**된다.
    ★찾는 법: 이력을 오래된 순으로 보며 이 소유자의 취득 항목 **직전** 항목의 취득일을 쓴다.
      이력이 없거나 직전 항목이 없으면 **None** — 그때는 합산하지 않고 '미확인'으로 남긴다
      (없는 것을 추정으로 채우지 않는다).
    """
    rows = [h for h in (history or []) if isinstance(h, dict)]
    if not rows:
        return None, None
    name = str(owner.get("name") or "").strip()
    own_acq = _parse_kdate(owner.get("acquisition_date"))
    parsed = [(h, _parse_kdate(h.get("date"))) for h in rows]
    parsed = [(h, d) for h, d in parsed if d is not None]
    parsed.sort(key=lambda x: x[1])
    for idx, (h, d) in enumerate(parsed):
        same_owner = name and name in str(h.get("owner") or "")
        same_date = own_acq is not None and d == own_acq
        if not (same_owner or same_date):
            continue
        if idx == 0:
            return None, None  # 최초 등기 = 피상속인 기록이 이력에 없다
        prev_row, prev_date = parsed[idx - 1]
        return prev_date, prev_row
    return None, None


def _judge_owner(
    owner: dict[str, Any],
    decision_date: date | None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """소유자 1인의 매도청구 가능여부(보유기간 기준) 판정. 항상 `evidence`를 동반한다."""
    name = owner.get("name") or "성명 미상"
    share = owner.get("share")
    evidence = _owner_evidence(owner)
    inheritance = _classify_inheritance(owner.get("acquisition_cause"))

    base = {
        "owner": name,
        "share": share,
        "inheritance": inheritance,
        "evidence": evidence,
    }

    # ★제약2 — 기준일 미입력이면 판정하지 않는다(오늘 날짜로 임의 계산 금지).
    if decision_date is None:
        return {
            **base,
            "holding_period_basis": None,
            "holding_period_years": None,
            "sell_claim_judgment": "판정 보류",
            "sell_claim_reason": (
                "기준일(지구단위계획구역 결정고시일) 미입력으로 보유기간 판정 불가"
                "(주택법 §22①2호 — 오늘 날짜로 임의 계산하지 않습니다)."
            ),
        }

    acq_date = _parse_kdate(owner.get("acquisition_date"))
    if acq_date is None:
        return {
            **base,
            "holding_period_basis": decision_date.isoformat(),
            "holding_period_years": None,
            "sell_claim_judgment": "판정 보류",
            "sell_claim_reason": "등기부상 취득일을 인식하지 못해 보유기간을 계산할 수 없습니다.",
        }

    holding_years = round((decision_date - acq_date).days / 365.25, 1)
    long_term = holding_years >= _LONG_TERM_HOLDING_YEARS

    # ★제약3 — 상속이든 판별 불가든, 피상속인 보유기간을 실제로 합산할 근거(원취득일)가
    #   없으므로 항상 "합산 여부 미확인"으로 정직하게 낸다. 계산된 보유기간은 자기
    #   보유분만의 값(확정치 아님)임을 함께 표시한다.
    aggregated = False
    predecessor_evidence: dict[str, Any] | None = None
    if inheritance["status"] == "상속":
        # ★P1.5 — 이력에서 **피상속인 취득일**을 찾으면 실제로 합산한다(법령 요건).
        pred_date, predecessor_evidence = _predecessor_acquisition(owner, history)
        if pred_date is not None:
            holding_years = round((decision_date - pred_date).days / 365.25, 1)
            long_term = holding_years >= _LONG_TERM_HOLDING_YEARS
            aggregated = True
            agg_note = (
                f"상속 취득 — 피상속인 취득일({pred_date.isoformat()})을 **합산**한 값입니다"
                "(주택법 §22①2호)."
            )
        else:
            agg_note = (
                "취득원인이 상속으로 판별되었으나 등기 이력에서 피상속인 취득일을 찾지 못해 "
                "**합산 여부 미확인** — 아래 보유기간은 상속 개시일부터의 값으로, 합산 시 더 "
                "길어질 수 있습니다(확정치 아님)."
            )
    elif inheritance["status"] == "판별 불가":
        agg_note = (
            "취득원인을 등기분석 결과에서 판별할 수 없어 상속 여부·합산 여부 모두 "
            "미확인 — 아래 보유기간은 확정치가 아닙니다."
        )
    else:
        agg_note = "상속에 의한 취득으로 보이지 않아 피상속인 보유기간 합산 대상이 아닙니다."

    # ★합산에 성공했으면 더는 "미확인"이 아니다 — 성공했는데도 미확인이라 하면
    #   사용자가 확정된 판정을 신뢰하지 못한다(정직 표기의 반대 방향 오류).
    unconfirmed = (not aggregated) and inheritance["status"] in ("상속", "판별 불가")
    judgment = "불가(장기보유 추정)" if long_term else "가능(원칙)"
    reason = (
        f"지구단위계획구역 결정고시일({decision_date.isoformat()}) 기준 보유기간 약 "
        f"{holding_years}년"
        + (" — 합산 미반영, 실제는 더 길 수 있음" if unconfirmed else "")
        + f". 주택법 §22①2호(결정고시일 기준 {_LONG_TERM_HOLDING_YEARS}년 이상 계속보유 시 "
          "매도청구 제외) 기준 1차 판정이며, 사용권원 확보율 등 사업방식별 요건은 별도 확인 "
          "필요(법률자문 아님, 참고용)."
    )

    return {
        **base,
        "holding_period_basis": decision_date.isoformat(),
        "acquisition_date": acq_date.isoformat(),
        "holding_period_years": holding_years,
        "inheritance_aggregated": aggregated,
        "predecessor_evidence": predecessor_evidence,
        "inheritance_aggregation_note": agg_note,
        "sell_claim_judgment": judgment,
        "sell_claim_reason": reason,
    }


def _parcel_label(parcel: dict[str, Any], idx: int) -> str:
    return str(parcel.get("address") or parcel.get("pnu") or f"필지#{idx + 1}")


def _build_card(
    parcel: dict[str, Any], idx: int, analysis: dict[str, Any], decision_date: date | None
) -> dict[str, Any]:
    """RegistryAnalysisService.analyze() 결과 위에 소유자별 매도청구 판정 계층을 얹는다."""
    label = _parcel_label(parcel, idx)
    status = str((analysis or {}).get("status") or "error")
    ai = (analysis or {}).get("ai")

    if status != "ok" or not isinstance(ai, dict) or not ai.get("generated"):
        # ★제약5 — 조용히 비우지 않는다. 이 필지가 왜 권리분석까지 못 갔는지 사유를 남긴다.
        return {
            "parcel": label,
            "pnu": parcel.get("pnu"),
            "address": parcel.get("address"),
            "status": status,
            "message": (analysis or {}).get("message") or "권리분석 결과가 없습니다.",
            "registry": None,
            "owners": [],
            "analysis": analysis,
        }

    from app.services.registry.registry_analysis_service import _derive_ownership

    deriv = _derive_ownership(ai)
    owners_raw = deriv.get("owners") or []
    # ★P1.5 — 소유권 이전 이력을 넘겨 **상속 시 피상속인 보유기간을 합산**한다(주택법 §22①2호).
    #   이력이 없으면 `_judge_owner` 가 합산하지 않고 '미확인'으로 남긴다(추정 금지).
    history = ((ai or {}).get("ownership") or {}).get("ownership_history")
    history = history if isinstance(history, list) else None
    owner_judgments = [_judge_owner(o, decision_date, history) for o in owners_raw]

    return {
        "parcel": label,
        "pnu": parcel.get("pnu"),
        "address": parcel.get("address"),
        "status": "ok",
        "message": None,
        "registry": {
            "baseline_right": ai.get("baseline_right"),
            "acquired_extinguished": ai.get("acquired_extinguished"),
            "right_to_demand_sale": ai.get("right_to_demand_sale"),
            "safety_grade": ai.get("safety_grade"),
            "summary": ai.get("summary"),
        },
        "ownership_form": deriv.get("ownership_form"),
        "owners": owner_judgments,
        "analysis": analysis,
    }


async def _survey_one(
    parcel: dict[str, Any],
    idx: int,
    decision_date: date | None,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    async with sem:
        from app.services.registry.registry_analysis_service import RegistryAnalysisService

        try:
            analysis = await RegistryAnalysisService().analyze(
                address=parcel.get("address"),
                pnu=parcel.get("pnu"),
                registry_text=parcel.get("registry_text"),
                realty_type=parcel.get("realty_type"),
                dong=parcel.get("dong"),
                ho=parcel.get("ho"),
                land_hint=parcel.get("land_hint"),
            )
        except Exception as e:  # noqa: BLE001 — ★제약5: 한 필지 실패가 전체를 죽이지 않는다.
            label = _parcel_label(parcel, idx)
            logger.warning("필지 발급·권리분석 실패: %s (%s)", label, str(e)[:160])
            return {
                "parcel": label,
                "pnu": parcel.get("pnu"),
                "address": parcel.get("address"),
                "status": "error",
                "message": f"발급·권리분석 중 오류: {str(e)[:200]}",
                "registry": None,
                "owners": [],
                "analysis": None,
            }
        return _build_card(parcel, idx, analysis, decision_date)


def _summarize(cards: list[dict[str, Any]], decision_date_provided: bool) -> dict[str, Any]:
    owners_total = 0
    owners_undetermined = 0
    owners_long_term = 0
    owners_inheritance_unconfirmed = 0
    parcels_ok = 0
    parcels_failed = 0

    for c in cards:
        if c.get("status") == "ok":
            parcels_ok += 1
        else:
            parcels_failed += 1
        for o in c.get("owners") or []:
            owners_total += 1
            if o.get("sell_claim_judgment") == "판정 보류":
                owners_undetermined += 1
            if o.get("holding_period_years") is not None and o["holding_period_years"] >= _LONG_TERM_HOLDING_YEARS:
                owners_long_term += 1
            if (o.get("inheritance") or {}).get("status") in ("상속", "판별 불가"):
                owners_inheritance_unconfirmed += 1

    return {
        "parcels_ok": parcels_ok,
        "parcels_failed": parcels_failed,
        "owners_total": owners_total,
        "owners_holding_period_undetermined": owners_undetermined,
        "owners_long_term_holders": owners_long_term,
        "owners_inheritance_aggregation_unconfirmed": owners_inheritance_unconfirmed,
        "decision_date_provided": decision_date_provided,
        "note": (
            "매도청구 판정은 보유기간(지구단위계획구역 결정고시일 기준) 1차 판정이며, "
            "상속 취득분은 피상속인 보유기간 합산이 확인되지 않았습니다. 법률자문이 아닌 "
            "참고용 분석입니다."
        ),
    }


async def survey_selected_parcels(
    parcels: list[dict[str, Any]],
    district_plan_decision_date: str | None = None,
) -> dict[str, Any]:
    """선택 필지를 병렬 발급→권리분석하고, 필지별 카드 + 세트 요약을 돌려준다.

    `district_plan_decision_date`: 지구단위계획구역 결정고시일(주택법 §22①2호 보유기간
    기준일). 미입력이면 모든 소유자 판정이 "판정 보류"로 나온다(제약2 — 오늘 날짜로
    임의 계산하지 않는다).
    """
    rows = [p for p in (parcels or []) if isinstance(p, dict)]
    decision_date = _parse_kdate(district_plan_decision_date)
    decision_date_provided = decision_date is not None

    sem = asyncio.Semaphore(_MAX_CONCURRENT_ISSUES)
    cards = list(
        await asyncio.gather(
            *[_survey_one(p, idx, decision_date, sem) for idx, p in enumerate(rows)]
        )
    )

    return {
        "parcel_count": len(rows),
        "district_plan_decision_date": decision_date.isoformat() if decision_date else None,
        "cards": cards,
        "summary": _summarize(cards, decision_date_provided),
    }
