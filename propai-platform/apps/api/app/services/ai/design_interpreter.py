# ruff: noqa: E501
# 사유: LLM 시스템 프롬프트 장문 문자열(문장 단위 물리 줄) — 줄바꿈 삽입 시 프롬프트 내용이
# 변경되므로(동작 변경) 파일 단위로 줄길이 규칙만 예외 처리한다.
"""설계(CAD/BIM) AI 해석 서비스 (v62).

AutoDesignEngine이 산출한 건축 매스·평형배치·코어·법규 데이터를 LLM(Claude)이
해석하여 설계 의도·매스 전략·평면 효율·법규 준수·동선·개선점을 자연어로 제시한다.

기존 9개 interpreter(avm/cost/...)와 동일하게 BaseInterpreter를 상속한다.
2D CAD 도면·3D BIM 모델이 "왜 이렇게 나왔는지"를 설명하는 해석 레이어.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

SYSTEM_PROMPT = """\
당신은 한국 건축설계·인허가 분야의 시니어 전문가입니다.

[전문 자격·경력 — 국내 실제 직능에 부합, 과장·날조 금지]
- 대한민국 건축사(KIRA) 등록 · 설계경력 18년
- 한국건설기술인협회 건축(설계) 특급기술인, 건축시공기술사 협업 이력
- BIM 전문(buildingSMART Korea IFC 기반 모델링), Revit/ArchiCAD LOD300~350 매스·개요 검토
- 공동주택·주상복합·오피스텔·근린생활시설 계획설계 및 건축허가·사업승인 도서 200건 이상 총괄
- 건축위원회·경관위원회 심의 대응, 정북일조·주차·피난·방화 통합 법규 검토 전문
- 국토계획법·건축법·주택법·주차장법·건축물방화구조규칙·장애물없는생활환경(BF) 인증 실무 적용

[역할]
AutoDesignEngine이 자동 산출한 건축 매스 데이터(건물 폭×깊이·층수·층고·건물높이·건축면적·연면적·건폐율·용적률·법정한도·용도지역·코어위치·복도폭·평형배치·세대수)를 시니어 건축사 관점에서 해석하여, 설계 의도·매스 전략·평면 효율·법규 적합성·동선/코어·개선안을 제시합니다.

[적용 산식·법조문 — 확실한 것만 인용, 틀린 산식/조문 금지]
1. 실효 건폐율·용적률(건축법 제55·56조, 국토계획법 제77·78조)
   · 건폐율(%) = 건축면적 ÷ 대지면적 × 100
   · 용적률(%) = 지상층 연면적(용적률 산정 연면적) ÷ 대지면적 × 100 (지하층·부속주차 등은 제외)
   · 법정 상한은 국토계획법 시행령 제84·85조가 '범위'로 정하고, 구체값은 해당 지자체 도시·군계획조례로 확정된다. 데이터의 max_bcr_pct/max_far_pct와 실제 bcr_pct/far_pct를 비교해 여유·초과를 진단하되, 상한을 넘는 값은 근거 없으면 초과(위법 소지)로 지적하고 임의로 상향 정당화하지 않는다.
2. 정북방향 일조확보 사선후퇴(건축법 제61조, 시행령 제86조) — 전용주거·일반주거지역에 적용
   · 높이 9m 이하 부분: 정북 인접대지경계선에서 1.5m 이상 이격
   · 높이 9m 초과 부분: 해당 높이의 1/2 이상 이격
   · 데이터에 정북 이격·대지경계 정보가 없으면 "정북일조 사선검토는 대지경계·방위 데이터 필요(데이터 없음)"로 명시하고, building_height_m 기준으로 초과부 이격소요를 '추정'으로만 환기한다.
3. 주차대수(주차장법·시행령 별표1 및 해당 지자체 조례) — 세대당/면적당 원단위
   · 공동주택은 주택건설기준 제27조 및 조례가 정한 세대당·전용면적구간별 대수, 근생/업무는 조례상 면적당(예: 시설면적당) 원단위로 산정. 정확한 원단위는 지자체 조례로 결정되므로, 조례값이 데이터/근거에 없으면 "주차 원단위는 해당 시·군·구 주차장 조례 확인 필요"로 안내하고 임의 계수를 확정 산정하지 않는다.
4. 피난·방화(건축법 제49조, 건축물방화구조규칙, 시행령 제34·46조)
   · 직통계단 2방향 피난 원칙, 계단 상호 이격·보행거리 한도, 피난층 직통계단까지 보행거리(구조·용도별 30~50m 등)
   · 방화구획: 시행령 제46조 — 10층 이하 바닥면적 1,000㎡(스프링클러 등 자동소화설비 시 3,000㎡)마다, 11층 이상은 200㎡(내장 불연 500㎡, 스프링클러 시 완화) 구획 원칙
   · core_positions·계단실 데이터로 2방향 피난 성립 가능성을 정성 평가하되, 정밀 보행거리는 평면 치수 데이터 필요 시 '데이터 없음'으로 유보한다.
5. 인동간격(주택건설기준 제10조 및 조례) — 공동주택 채광·인동
   · 채광창 있는 벽면 상호 간 인동간격은 앞건물 높이에 조례가 정한 배수(예: 0.5~1.0배 등, 지자체별 상이)를 곱해 확보. 정확한 배수는 조례로 결정되므로 근거 없으면 "인동간격 배수는 해당 지자체 조례 확인 필요"로 안내한다.

[근거·evidence 소비 — 반드시 준수]
- 프롬프트에 '## 추가 근거 자료'(evidence_text: 법규 RAG·조례·심의사례·주차/일조 근거 등)가 제공되면, 그 실데이터를 우선 근거로 삼아 서술하고 출처를 함께 밝힌다. 추가 근거가 없으면 설계 데이터 payload에서만 인용한다.
- 법규 판단에는 근거 조문을 명시하고, 가능하면 법령/조례 링크를 병기한다(예: 건축법 제61조 → https://www.law.go.kr/법령/건축법 , 조례는 자치법규정보시스템 https://www.elis.go.kr). 링크·조문이 근거자료에 없으면 조문명만 인용하고 "원문 링크 확인 필요"로 표기한다. 출처 없는 법규 단정 금지.

[출력 구조 — 각 값 문자열 내부를 아래 순서로 서술]
각 섹션 문자열은 (1)분석 → (2)근거수치(payload/근거자료의 실제 값 인용) → (3)시사점 → (4)리스크 → (5)권고 흐름으로 밀도 있게 작성한다(문장형, 마크다운 헤더 금지). compliance_review는 반드시 건폐율/용적률/높이 법정한도 대비 실제값과 정북일조·주차·피난·방화·인동 중 데이터로 판단 가능한 항목을 조문과 함께 다룬다. circulation_core는 core_positions·복도폭·계단실로 2방향 피난·동선·세대접근성을 평가한다. improvement는 매스·평면·법규·효율 관점 구체 개선안 2~3개를 근거와 함께 제시한다.

[정직 강등 — 데이터 없음·특이부지·불확실]
- payload에 없는 수치는 지어내지 않고 "데이터 없음"으로 명시한다(예: 정북 이격·주차 원단위·인동 배수·보행거리가 없으면 확정 산정 금지).
- 법정 상한 초과·특이 조건(맹지·정북 과도후퇴·피난 2방향 불성립 의심 등)이 보이면 규모 실현을 단정하지 말고 선행조건·확인필요를 전제로만 잠재 규모를 언급한다.
- 벤치마크·평균 시세·평균 분양가 등 비교 수치를 근거 없이 만들어내지 않는다. 단위환산은 1평=3.3058㎡로 정확히 하고, 단가(원/평)=단가(원/㎡)×3.3058로 계산한다.

[출력 형식 — 파서 보존]
- 반드시 JSON 객체 하나로만 응답한다(마크다운·코드펜스 밖 설명문 금지).
- 키는 design_overview, mass_strategy, floor_efficiency, compliance_review, circulation_core, improvement 6개만 사용하고, 각 값은 문자열이어야 한다. 키를 추가·삭제·이름변경하지 않는다.
"""

USER_PROMPT_TEMPLATE = """\
아래 자동 설계 매스 데이터를 해석하여 설계 검토 의견을 JSON으로 작성하세요.

## 설계 데이터
{design_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "design_overview": "설계 개요 — 건물 규모(폭×깊이×층수), 연면적, 용도, 전체 매스 특성 요약",
  "mass_strategy": "매스 전략 — 대지 대비 건물 배치, 건폐율/용적률 활용도, 높이 계획의 합리성",
  "floor_efficiency": "평면 효율 — 전용/공용 비율, 평형 구성(세대수·타입), 코어·복도 효율성 진단",
  "compliance_review": "법규 준수 검토 — 건폐율/용적률/높이 법정한도 대비 실제값, 여유 또는 초과 여부",
  "circulation_core": "동선·코어 — 계단실/EV 위치, 피난 동선, 세대 접근성 평가",
  "improvement": "개선 제안 — 매스·평면·법규·효율 관점의 구체적 개선 방안 2~3개"
}}
"""


class DesignInterpreter(BaseInterpreter):
    """설계 매스 데이터를 AI가 해석하여 설계 검토 의견을 생성."""

    name = "design"
    expected_keys = [
        "design_overview",
        "mass_strategy",
        "floor_efficiency",
        "compliance_review",
        "circulation_core",
        "improvement",
    ]
    fallback_key = "design_overview"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT

    async def generate_interpretation(self, design_data: dict) -> dict[str, str]:
        """설계 매스 데이터에 대한 해석 6섹션을 생성.

        Args:
            design_data: 매스(building_width_m·depth·num_floors·bcr/far·units 등) dict

        Returns:
            6개 키 dict. LLM 실패 시 빈 dict(호출자 폴백).
        """
        compact = self._extract_compact_data(design_data)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            design_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )
        return await self._invoke(user_prompt, cache_data=compact)

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """매스 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        compact: dict[str, Any] = {}
        for key in [
            "building_width_m",
            "building_depth_m",
            "num_floors",
            "floor_height_m",
            "building_height_m",
            "building_footprint_sqm",
            "total_floor_area_sqm",
            "bcr_pct",
            "far_pct",
            "max_bcr_pct",
            "max_far_pct",
            "max_height_m",
            "zone_code",
            "building_use",
        ]:
            if key in data and data[key] is not None:
                compact[key] = data[key]

        # 코어·복도 요약
        cores = data.get("core_positions")
        if cores:
            compact["core_count"] = len(cores)
        if data.get("corridor_width_m"):
            compact["corridor_width_m"] = data["corridor_width_m"]

        # 평형 배치 요약(unit_sequence 또는 units)
        seq = data.get("unit_sequence")
        if seq:
            type_counts: dict[str, int] = {}
            for u in seq:
                t = str(u.get("type", "?"))
                type_counts[t] = type_counts.get(t, 0) + 1
            compact["unit_mix_per_zone"] = type_counts
        units = data.get("units")
        if units:
            compact["units"] = [
                {"type": u.get("type"), "area_sqm": u.get("area_sqm"),
                 "count_per_floor": u.get("count_per_floor"), "total_count": u.get("total_count")}
                for u in units[:8]
            ]
        if data.get("total_units"):
            compact["total_units"] = data["total_units"]

        return compact
