"""부지분석 AI 해석 서비스.

수집된 7개 섹션 분석 데이터를 LLM(Claude)이 해석하여
전문가 수준의 분석 설명을 생성한다.

핵심 원칙:
- LLM 호출 실패 시에도 기존 분석 결과는 정상 반환 (폴백)
- 토큰 절약을 위해 핵심 데이터만 추출하여 프롬프트에 포함
- timeout 10초
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """\
당신은 대한민국 부동산개발 부지 타당성(Site Feasibility)을 총괄하는 수석 심의역입니다. 아래 자격·직능을 겸비한 전문가의 관점으로, 수집·검증된 실데이터에만 근거해 분석합니다(자격은 분석 권위의 기준이며, 사칭 문구를 출력하지 않습니다).

[전문가 자격·직능 페르소나]
- 감정평가사(국가전문자격, 감정평가 및 감정평가사에 관한 법률): 토지·건물 가치 평가 15년, 개발부지 감정 3,000건 이상. 감정평가 3방식(원가법·거래사례비교법·수익환원법)과 공시지가 기준법을 적용해 지가·시세를 판단.
- 도시계획기술사(국가기술자격, 국가기술자격법): 용도지역·지구단위계획·도시관리계획 수립 검토 다수. 용도지역별 행위제한·밀도규제·기반시설 정합성을 판정.
- 건축사(건축사법) 겸 인허가 실무: 배치·규모검토(연면적/용적률/건폐율/층수) 및 사전결정·건축허가·심의 실무 다수. 대지안의 공지·정북방향 일조 이격 등 실무 규제를 반영.
- 도시계획·건축 심의위원 경험: 경관·교통·환경·건축심의 관점에서 리스크와 조건부 인가 가능성을 평가.
- PF(프로젝트파이낸싱) 자문 실무: 사업성·분양성·개발규모의 금융 실현성을 개발자 관점으로 조언.

[반드시 적용·인용하는 도메인 산식(확실한 것만 — 데이터 있는 항목에만 적용)]
- 건폐율 = (건축면적 ÷ 대지면적) × 100, 용적률 = (지상층 연면적 ÷ 대지면적) × 100 (연면적은 용적률 산정 시 지하층·주차장 등 제외). 근거: 건축법 제55·56조, 국토의 계획 및 이용에 관한 법률 제77·78조.
- 대지면적×용적률 = 확보 가능 지상 연면적(GFA) → 개발규모·세대수 추정의 기준값. 세대수 추정은 (전용/공용) 계획에 따른 근사치이므로 '추정'으로 표기.
- 지가·시세 판단: 공시지가는 부동산 가격공시에 관한 법률상 개별공시지가이며 '시장가'가 아니다. 시장가는 거래사례비교법(주변 실거래)·수익환원법으로 별도 산정하되 데이터가 있을 때만 제시. 단가(원/평)=단가(원/㎡)×3.3058, 면적(평)=면적(㎡)÷3.3058(반드시 곱셈/나눗셈 방향 준수).
- 정북방향 일조 이격(전용주거·일반주거): 높이 9m 이하는 인접대지경계선에서 1.5m 이상, 9m 초과는 해당 높이의 1/2 이상 이격(건축법 제61조, 시행령 제86조). 배치·층수 판단 시 반영.

[반드시 확인·인용하는 핵심 조문·출처 계층(용적률/행위제한 산정 순서)]
①국토계획법 시행령 제84조(건폐율)·제85조(용적률) 법정 범위 → ②해당 지자체 도시계획조례의 범위 내 구체값 → ③도시·군관리계획/지구단위계획(상한용적률·종세분·특별구역) → ④인센티브(기부채납·친환경·역세권 시프트·공공임대). 이 계층은 USER 프롬프트의 그라운딩 규칙·법정한도 블록과 정확히 일치하게 지켜라. 출처 없는 상한 초과 수치는 할루시네이션이다.

[근거·링크 부착(evidence 그라운딩)]
- 모든 수치·판단은 프롬프트에 제공된 수집·검증 데이터(analysis_json, 추가 근거 자료, few-shot이 아닌 실데이터)에서만 인용한다. 출처 없는 단정 금지.
- 법령·조례 근거를 서술할 때는 조문명과 함께 확인 링크를 병기하라: 법령은 국가법령정보센터(https://www.law.go.kr), 자치법규(도시계획조례 등)는 자치법규정보시스템(https://www.elis.go.kr). 예: "국토계획법 시행령 제84조(https://www.law.go.kr)". 링크는 근거 표기 목적이며 데이터에 없는 수치를 링크로 정당화하지 않는다.
- 데이터가 없으면 "데이터 없음"으로 정직히 표기한다(분양가·실거래·시장가·벤치마크 등 없으면 만들어내지 말 것).

[출력 정밀도 — 각 해석 값(문자열)의 서술 구조]
각 섹션 해석은 2~4문장으로, 가능한 한 [분석 → 근거수치(제공 데이터의 실값) → 시사점 → 리스크 → 권고]의 논리 흐름을 담아 서술하라. 수치를 인용할 때는 원본 값을 정확히 옮기고, 계산·추정값에는 "추정/약"을 붙여 사실값과 구분하라. 단, 이는 문자열 값 '내부'의 서술 방식일 뿐이며 — ★요구 출력 JSON의 키 이름·개수·구조·값 타입(문자열)은 절대 변경하지 말라(파서 계약 보존). risk_factors·opportunity_factors는 각 2~3개 핵심 항목을 문자열로 기술한다.

[특이부지·불확실·종상향 강등 규율(정직 강등 계승)]
- special_parcel(학교용지·GB·농지·산지·맹지·문화재 등)이 감지되면 developability/honest_disclosure/development_caveat를 그대로 반영하고, 선행절차(도시계획시설 폐지·용도변경·전용·GB해제) 통과를 '전제'로만 잠재 규모를 언급하라. 해결불가면 '현 상태 일반 분양개발 불가'를 명시하고 무리한 개발규모를 제시하지 말라.
- upzoning(종상향)은 현행 실효 용적률과 분리된 '예상치'다. 목표 용도지역 기준 예상치임을 명시하고 가능성 등급·근거법령·전제(도시계획 결정·인허가)를 동반해 비단정 표현("~가능성/~예상/전제 충족 시")으로 서술하라. 확정처럼 단정 금지.
- buildable_options는 인허가가능성×가용용적률 랭킹이며, is_current=true는 현행 실효값, false는 종상향 전제(예상 far)임을 구분하라. 사업성 정량은 별도 분석임을 명시하라.

[출력 형식(불변)]
- 각 섹션 해석에는 "왜 이 값인지", "이것이 의미하는 바", "개발자에게 주는 시사점"을 반드시 포함한다.
- 숫자는 원본 데이터의 값을 정확히 사용하고, 추측·가정은 명확히 표시한다.
- ★반드시 요구된 JSON 키만 가진 JSON 객체 하나로만 응답한다(마크다운·코드펜스·설명문·서론/결론 문장 금지). 각 값은 문자열이다.
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 부지분석 데이터를 해석하여 각 섹션별 전문가 의견을 JSON으로 작성하세요.

## 분석 대상
- 주소: {address}
- 용도지역: {zone_type}
- 대지면적: {land_area_sqm}m² ({land_area_pyeong}평)

## 법정 한도(국토계획법 시행령 제84·85조 — 기본값)
{legal_limits_block}

## 그라운딩 규칙(위반 금지)
실효 건폐율/용적률은 다음 **계층 순서**로 분석해 산정한다:
**①국토계획법 시행령의 법정 범위(예: 자연녹지 용적률 50~100%) → ②해당 지자체 도시계획조례의
구체값(범위 내 적용 법정값, 예: 용인시 조례 80%/100%) → ③도시·군관리계획/지구단위계획
(상한용적률·종세분·특별구역) → ④인센티브(기부채납·친환경·시프트·공공임대).**
페이로드(far_basis_detail·local_ordinance·special_districts)에 **조례·계획·완화근거가 있으면
그 출처를 명시해 수치를 제시**하라. 없으면 **법정 범위를 제시하며 '구체 용적률은 OO시 도시계획
조례·도시·군관리계획 확인 필요'**로 안내하라. **출처 없는 단일수치 단정 금지** — 근거가 없는데
법정 범위 상한을 초과하는 수치는 할루시네이션이다. 페이로드(analysis_json)에 없는 수치를
지어내지 말라.

## 종상향/종변경 잠재력(★현행과 별도 — 예상치)
페이로드의 `upzoning`(scenarios·potential_far_range)은 **현행 실효 용적률과 분리된 잠재 시나리오
(예상치)**다. 도시개발사업·지구단위계획·정비사업·역세권 활성화/시프트·공공주택지구·가로주택/
모아주택 등으로 현재 용도지역보다 용적률을 상향할 수 있는 **경로·조건·가능성·전제**다.
해석 시 **반드시**: ①현행 실효 용적률과 혼동하지 말 것(별도 항목으로 안내), ②각 경로의 예상
용적률은 '목표 용도지역 기준 예상치'임을 명시, ③가능성 등급(상/중/하)·근거법령·전제(도시계획
결정·인허가 필요)를 동반, ④"~가능성", "~예상", "전제 충족 시" 등 비단정 표현 사용. **종상향이
확정/보장된 것처럼 단정 금지.** scenarios가 비어있으면 "정형 종상향 경로 미매핑 — 지자체 확인 필요"로 안내.

## 건축가능항목 선정·랭킹(★무엇을 지을 수 있는가)
페이로드의 `buildable_options`(top_recommendation·options_top5)는 **별표 허용용도 + 종상향 시나리오**를
결합해 '이 부지에서 지을 수 있는 사업유형'을 **인허가가능성×가용용적률**로 랭킹한 결과다. 해석 시:
①최우선 사업유형(top_recommendation)과 상위 후보를 안내하되, ②`is_current=true`는 현행 용도지역 내
'바로 가능'(far=실효 사실값), `is_current=false`는 종상향 전제(far=예상치)임을 구분, ③`permit_feasibility`
(현행/상/중/하)와 `via`(달성 경로)를 동반, ④사업성(수익) 비교는 별도 정량분석임을 명시(랭킹은 인허가×용적률
기준). `buildable_options`가 없으면 이 항목은 생략한다.

## 특이부지 게이트(★최우선 — 위반 시 할루시네이션)
페이로드에 `special_parcel`이 있으면 이 부지는 학교용지·개발제한구역(GB)·농지·산지·맹지·문화재·
공공기반시설 등 **비일상 토지특성**이 감지된 것이다. 이 경우 **반드시**:
①`developability`(BLOCKED/PRECONDITION/CONDITIONAL/POSSIBLE)와 `honest_disclosure`를 그대로 반영하라.
②BLOCKED/PRECONDITION이면 "법정 최대 용적률/연면적이 그대로 실현됨"을 **단정 금지** — 선행절차
(도시계획시설 폐지·용도변경·농지/산지전용·GB해제 등) 통과를 **전제**로만 잠재 규모를 언급하고,
미충족 시 개발 불가/제한을 명시하라. ③`development_caveat`를 supply_area_interpretation과
overall_summary에 반드시 포함하라. ④해결불가(resolvable=NO) 요인이 있으면 "현 상태 일반 분양개발
불가"를 분명히 고지하고 무리한 개발규모(예: 'OO평 가능')를 제시하지 말라. `special_parcel`이 없으면 일상 개발부지로 본다.

## 분석 데이터
{analysis_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "effective_far_interpretation": "실효 용적률/건폐율에 대한 해석 (법적 근거, 조례 영향, 개발 가능 규모)",
  "supply_area_interpretation": "개발방식별 공급면적 분석 (최적 개발유형, 세대수, 수익성 시사점)",
  "land_price_interpretation": "토지 시세 해석 (제공된 공시지가만 인용. ★'공시지가는 시장가의 70~80%' 등 비율을 데이터 근거 없이 단정 금지. 시장가 데이터 없으면 '시장가 데이터 없음')",
  "transaction_interpretation": "주변 실거래가 해석 (제공된 실거래 데이터 있을 때만. 없으면 '실거래 데이터 없음')",
  "sale_price_interpretation": "분양가 해석 (★sale_prices_top3 등 분양가 데이터가 제공된 경우에만 해석. 제공 안 됐으면 평균·벤치마크 분양가를 절대 만들어내지 말고 '분양가 데이터 없음'으로만 기술)",
  "location_interpretation": "입지 분석 해석 (교통, 교육, 생활 인프라, 입지 등급)",
  "development_plan_interpretation": "개발계획 해석 (토지이용규제, 특수구역, 규제 리스크)",
  "upzoning_interpretation": "종상향/종변경 잠재력 해석 (★예상치 — 현행 실효 용적률과 분리. 유력 경로·목표 용도지역·예상 용적률 범위·가능성 등급·전제(도시계획 결정·인허가)를 비단정 표현으로 안내. scenarios 없으면 미매핑 안내)",
  "buildable_options_interpretation": "건축가능항목 해석 (★buildable_options 제공 시에만. 최우선 사업유형·상위 후보를 인허가가능성×가용용적률 기준으로 안내. 현행 가능(실효 far) vs 종상향 전제(예상 far) 구분, 인허가 난이도·달성경로 동반. 사업성은 별도 정량분석임을 명시. 미제공 시 빈 문자열)",
  "overall_summary": "종합 평가 (이 부지의 개발 가치를 3~4문장으로 종합 판단)",
  "risk_factors": "주요 리스크 요인 (2~3개 핵심 리스크와 대응 방안)",
  "opportunity_factors": "개발 기회 요인 (2~3개 핵심 기회 요인)"
}}
"""


class SiteAnalysisInterpreter(BaseInterpreter):
    """수집된 부지분석 데이터를 AI가 해석하여 전문가 수준의 분석 설명을 생성."""

    name = "site_analysis"
    expected_keys = [
        "effective_far_interpretation",
        "supply_area_interpretation",
        "land_price_interpretation",
        "transaction_interpretation",
        "sale_price_interpretation",
        "location_interpretation",
        "development_plan_interpretation",
        "upzoning_interpretation",
        "buildable_options_interpretation",
        "overall_summary",
        "risk_factors",
        "opportunity_factors",
    ]
    fallback_key = "overall_summary"
    max_tokens = 6000
    system_prompt = SYSTEM_PROMPT


    async def generate_interpretation(
        self,
        analysis_data: dict,
        *,
        evidence_text: str | None = None,
        prior_context: str | None = None,
    ) -> dict[str, str]:
        """7개 섹션 각각에 대한 해석 텍스트를 생성.

        Args:
            analysis_data: ComprehensiveAnalysisService.analyze()의 반환값(또는 동일 스키마).
            evidence_text: 호출처(서비스/라우터)가 async로 조립한 사람이 읽는 근거 문자열
                (MOLIT 실거래·법규 RAG·공시지가·조례 출처 등). BaseInterpreter._invoke가
                프롬프트 '추가 근거 자료' 섹션에 부착하고 캐시키에 반영한다(CR-3). 없으면 None.
            prior_context: 원장 직전심사 근거블록(있으면). 없으면 None(graceful).

        Returns:
            12개 키를 가진 dict — 각 값은 전문가 해석 문자열.
            LLM 호출 실패 시 빈 dict가 아니라 None을 반환하여
            호출자가 폴백 처리할 수 있게 한다.
        """
        # 토큰 절약: 핵심 데이터만 추출
        compact = self._extract_compact_data(analysis_data)

        address = analysis_data.get("address", "주소 미상")
        zone_type = analysis_data.get("zone_type", "미상")
        land_area_sqm = analysis_data.get("land_area_sqm", 0)
        land_area_pyeong = round(land_area_sqm / 3.305785, 1)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            address=address,
            zone_type=zone_type,
            land_area_sqm=land_area_sqm,
            land_area_pyeong=land_area_pyeong,
            legal_limits_block=self._legal_limits_block(zone_type),
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        return await self._invoke_or_empty(
            user_prompt, cache_data=compact, evidence_data=analysis_data,
            evidence_text=evidence_text, prior_context=prior_context,
        )

    @staticmethod
    def _legal_limits_block(zone_type: str) -> str:
        """탐지된 용도지역의 법정 건폐율/용적률 상한을 프롬프트용 텍스트로 변환.

        법정 한도를 명시 주입하여 LLM이 상한을 초과하는 수치를 지어내지 못하게 그라운딩한다.
        """
        from app.services.zoning.legal_zone_limits import legal_limits_for

        legal = legal_limits_for(zone_type)
        if not legal:
            return (
                f"- 용도지역('{zone_type}')의 법정 한도를 표에서 확정할 수 없습니다. "
                "건폐율/용적률을 임의로 단정하지 말고 페이로드의 명시값만 인용하십시오."
            )
        min_far = legal.get("min_far_pct", legal["max_far_pct"])
        return (
            f"- 용도지역: {legal['zone_type']}\n"
            f"- 법정 건폐율 상한: {legal['max_bcr_pct']}%\n"
            f"- 법정 용적률 범위: {min_far}~{legal['max_far_pct']}% "
            "(국토계획법 시행령은 용적률을 범위로 두고, 구체값은 지자체 도시계획조례로 정함)\n"
            f"- 근거: {legal['legal_basis']}\n"
            "- 산정 계층: 법정범위 → ②지자체 도시계획조례 적용값 → ③도시·군관리계획/지구단위계획"
            "(상한용적률) → ④인센티브(기부채납·친환경·역세권 시프트·공공임대). "
            "구체 수치는 페이로드(far_basis_detail/조례/계획/완화근거)가 있을 때만 출처와 함께 제시하고, "
            "없으면 '구체 용적률은 해당 시·군·구 도시계획조례·도시·군관리계획 확인 필요'로 안내."
        )

    def _evidence(self, data: dict) -> str | None:
        """P3: 대상지 주소 기반 지역 시세 벤치마크 주입."""
        return self._regional_benchmark(address=str(data.get("address", "")))

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """전체 분석 결과에서 LLM에 필요한 핵심 데이터만 추출.

        토큰 절약을 위해 불필요한 상세 데이터(items 배열, 시뮬레이션 테이블 등)를 제거.
        """
        compact: dict[str, Any] = {}

        # Section 1: 실효 용적률
        far = data.get("effective_far", {})
        if far:
            compact["effective_far"] = {
                "national_bcr_pct": far.get("national_bcr_pct"),
                "national_far_pct": far.get("national_far_pct"),
                # ★정직가드(2026-07-22, live-fix① R2 — R1 봉합): ordinance_*_pct는 SSOT
                #   (far_tier_service.calc_effective_far)가 이미 미확정 시 None을 반환하지만,
                #   ordinance_confirmed를 함께 동봉해 LLM이 "확인 안 됨"을 명시 근거로 인지하게
                #   한다(필드 부재만으론 LLM이 누락으로 오인할 수 있음 — 명시 신호가 더 안전).
                "ordinance_bcr_pct": far.get("ordinance_bcr_pct"),
                "ordinance_far_pct": far.get("ordinance_far_pct"),
                "ordinance_confirmed": bool(far.get("ordinance_confirmed")),
                "effective_bcr_pct": far.get("effective_bcr_pct"),
                "effective_far_pct": far.get("effective_far_pct"),
                "source": far.get("source"),
                "annotations": far.get("annotations", []),
            }

        # Section 2: 공급면적 — 상위 3개만
        supply = data.get("supply_areas", [])
        if supply:
            top_items = supply[:3]
            compact["supply_areas_top3"] = [
                {
                    "type_name": s.get("type_name"),
                    "applied_far_pct": s.get("applied_far_pct"),
                    "total_gfa_sqm": s.get("total_gfa_sqm"),
                    "unit_count": s.get("unit_count"),
                    "floor_count": s.get("floor_count"),
                    "estimated_construction_cost_won": s.get("estimated_construction_cost_won"),
                    "permit_complexity": s.get("permit_complexity"),
                    "feasibility_status": s.get("feasibility_status"),
                }
                for s in top_items
            ]
            compact["supply_areas_total_count"] = len(supply)

        # Section 3: 토지 시세
        lp = data.get("land_prices", {})
        if lp:
            compact["land_prices"] = {
                "official_price_per_sqm": lp.get("official_price_per_sqm"),
                "official_price_per_pyeong": lp.get("official_price_per_pyeong"),
                "total_official_value_won": lp.get("total_official_value_won"),
                "estimated_market_per_sqm": lp.get("estimated_market_per_sqm"),
                "total_estimated_value_won": lp.get("total_estimated_value_won"),
            }

        # Section 4: 실거래가 — 통계만
        txn = data.get("transaction_prices", {})
        if txn and not txn.get("error"):
            compact_txn: dict[str, Any] = {}
            for prop_type, detail in txn.items():
                if isinstance(detail, dict) and "count" in detail:
                    compact_txn[prop_type] = {
                        "count": detail.get("count"),
                        "avg_price_10k": detail.get("avg_price_10k"),
                        "max_price_10k": detail.get("max_price_10k"),
                        "min_price_10k": detail.get("min_price_10k"),
                    }
            if compact_txn:
                compact["transaction_prices"] = compact_txn

        # Section 5: 분양가 — 상위 3개
        sale = data.get("sale_prices", [])
        if sale:
            compact["sale_prices_top3"] = [
                {
                    "type_name": s.get("type_name"),
                    "sale_price_per_pyeong_man": s.get("sale_price_per_pyeong_man"),
                    "sale_price_per_sqm_man": s.get("sale_price_per_sqm_man"),
                }
                for s in sale[:3]
            ]

        # Section 6: 입지
        loc = data.get("location", {})
        if loc:
            compact["location"] = {
                "nearest_subway": loc.get("transportation", {}).get("nearest_subway"),
                "subway_accessible": loc.get("transportation", {}).get("subway_accessible"),
                "school_count": loc.get("education", {}).get("school_count"),
                "location_score": loc.get("location_score"),
                "grade": loc.get("grade"),
            }

        # Section 7: 개발계획
        dev = data.get("development_plans", {})
        if dev:
            compact["development_plans"] = {
                "special_districts": dev.get("special_districts", []),
                "land_use_regulations": dev.get("land_use_regulations", []),
            }

        # Section 7-2: 특이부지 감지(학교·GB·농지·산지·맹지·문화재 등) — ★LLM 그라운딩 필수.
        #   이 블록을 프롬프트에 넣지 않으면 LLM이 '최대 연면적 가능'류를 독자 서술하는
        #   할루시네이션이 발생한다(감사 적발: 의정부동224 학교용지 오분석 회귀 위험).
        # ★다필지 통합: 대표번지가 아니라 통합 N필지 기준임을 LLM에 명시(통합분석 반영).
        ig = data.get("integrated")
        if isinstance(ig, dict) and ig.get("is_multi_parcel"):
            compact["integrated_multi_parcel"] = {
                "parcel_count": ig.get("parcel_count"),
                "total_area_sqm": ig.get("total_area_sqm"),
                "blended_far_pct": ig.get("blended_far_pct"),
                "blended_bcr_pct": ig.get("blended_bcr_pct"),
                "note": ig.get("note"),
            }

        sp = data.get("special_parcel")
        if isinstance(sp, dict) and sp.get("is_special"):
            compact["special_parcel"] = {
                "developability": sp.get("developability"),
                "severity_label": sp.get("severity_label"),
                "resolvable": sp.get("resolvable"),
                "development_caveat": sp.get("development_caveat"),
                "honest_disclosure": sp.get("honest_disclosure"),
                "factors": [
                    {
                        "category": f.get("category"),
                        "developability": f.get("developability"),
                        "resolvable": f.get("resolvable"),
                    }
                    for f in (sp.get("factors") or [])[:5]
                ],
            }

        # Section 8: 종상향/종변경 잠재력(★예상치 — 현행과 분리)
        up = data.get("upzoning", {})
        if up and up.get("scenarios"):
            compact["upzoning"] = {
                "current_zone": up.get("current_zone"),
                "potential_far_range": up.get("potential_far_range"),
                "scenarios_top3": [
                    {
                        "path": s.get("path"),
                        "target_zone": s.get("target_zone"),
                        "expected_far_pct_low": s.get("expected_far_pct_low"),
                        "expected_far_pct_high": s.get("expected_far_pct_high"),
                        "feasibility": s.get("feasibility"),
                        "feasibility_reason": s.get("feasibility_reason"),
                        "legal_basis": s.get("legal_basis"),
                    }
                    for s in up.get("scenarios", [])[:3]
                ],
                "is_estimate": True,
                "note": "현행 실효 용적률과 분리된 종상향 예상 시나리오(도시계획 결정·인허가 전제).",
            }

        # Stage 1: 건축가능항목 선정·랭킹(인허가가능성×가용용적률) — ★LLM 그라운딩.
        #   result에만 붙고 compact에 빠지면 인터프리터가 못 봐서 그라운딩 효과 0(orphan handoff).
        #   상위 5건 + 최우선 추천을 compact에 실어 LLM이 '무엇을 지을 수 있는가'를 인지하게 한다.
        bo = data.get("buildable_options")
        if isinstance(bo, dict) and bo.get("options"):
            compact["buildable_options"] = {
                "top_recommendation": bo.get("top_recommendation"),
                "options_top5": [
                    {
                        "product": o.get("product"),
                        "zone": o.get("zone"),
                        "achievable_far_pct": o.get("achievable_far_pct"),
                        "permit_feasibility": o.get("permit_feasibility"),
                        "is_current": o.get("is_current"),
                        "via": o.get("via"),
                    }
                    for o in (bo.get("options") or [])[:5]
                ],
                "summary": bo.get("summary"),
                "note": "랭킹=인허가가능성×가용용적률. 종상향 항목 far는 예상치(사업성 정량은 Stage 3 별도).",
            }

        return compact

