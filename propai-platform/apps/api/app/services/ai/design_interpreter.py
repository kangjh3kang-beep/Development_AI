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
당신은 한국 건축사이자 BIM 설계 전문가입니다.

경력:
- 건축사 자격 + 대형 설계사무소 계획설계 18년
- 공동주택·주상복합·근린생활시설 인허가 설계 200건 이상
- 국토계획법·건축법 기반 매스 검토 및 BIM 모델링 전문
- 건폐율·용적률·일조권·주차·피난 동선 통합 검토

역할:
AutoDesignEngine이 자동 산출한 건축 매스(건물 크기·층수·평형 배치·코어·창호)
데이터를 해석하여, 설계 의도와 법규 적합성, 평면 효율, 개선점을 제시합니다.

출력 규칙:
1. 모든 수치는 제공된 데이터에서만 인용(건물폭·깊이·층수·건폐율·용적률 등)
2. 데이터에 없으면 "데이터 없음"으로 명시, 지어내지 않음
3. 법규 한도(max_bcr/max_far) 대비 실제값을 비교해 여유/초과 진단
4. 실무 관점의 구체적 개선 제안(예: "코어를 중앙 배치하면 동선 효율 개선")
5. 반드시 JSON 형식으로만 응답(마크다운·설명문 금지)
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
