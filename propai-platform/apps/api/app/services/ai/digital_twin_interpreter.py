"""가상준공 3D 디지털트윈 AI 해설 인터프리터.

build_scene 씬 요약 + (선택) ROI/ESG/인허가/용도지역/설계요약 컨텍스트를 LLM(Claude)이
해석해 5개 섹션의 한국어 서술을 생성한다.

핵심 원칙(비협상):
- 데이터 그라운딩: 제공된 씬·컨텍스트 수치만 근거. 없는 값은 "데이터 부족"으로 명시(추측 금지).
- 가짜 시각콘텐츠 생성 금지 — 텍스트 해석만.
- LLM 호출 실패 시 빈 dict 반환(호출자 폴백). base_interpreter 공통기반 재사용.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """\
당신은 한국 부동산개발 설계·도시계획·분양 전문가입니다.

경력:
- 건축사·도시계획기술사 협업으로 가상준공(디지털트윈) 매스·배치 검토 다수
- 지형·일조·조망·주변 맥락을 고려한 배치/매스 디자인 자문
- 개발사업 타당성(용도지역 한도·ROI·ESG)과 분양 마케팅 포인트 도출

역할:
사용자가 제공하는 가상준공 3D 씬 요약(필지·지형·주변·건물 매스)과 개발 컨텍스트
(ROI·ESG·인허가·용도지역·설계요약)를 전문적이지만 이해하기 쉬운 한국어로 해석합니다.

출력 규칙:
1. 각 섹션은 2~4문장의 한국어 서술
2. 구체적 수치(경사도·기복·필지면적·주변동수·평균높이·층수/GFA 등)는 제공된 데이터만 인용
3. 데이터가 없는 항목은 해당 섹션에 "데이터 부족"이라고 명시하고 추측하지 않음
4. 가상준공 매스는 AI 절차생성(인허가도면 아님), 표고는 SRTM 30m(실측 아님)임을 전제로 신중히 서술
5. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 가상준공 3D 디지털트윈 씬 요약과 개발 컨텍스트를 해석해 JSON으로 작성하세요.

## 씬·컨텍스트 데이터
{analysis_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 한국어 문자열입니다:

{{
  "design_rationale": "건물 매스·배치의 설계 의도와 근거 (층수/GFA·필지면적·매스 유무 기반. \
매스 없으면 데이터 부족 명시)",
  "context_fit": "주변 맥락 적합성 (주변 동수·평균 높이 대비 스케일·정합성. 데이터 없으면 데이터 부족 명시)",
  "view_sunlight": "조망·일조 관점 해석 (지형 경사도·기복·향 추정. 정밀 일조 시뮬레이션 아님을 명시)",
  "development_implication": "개발 시사점 (용도지역 한도·ROI·인허가 관점. 컨텍스트 없으면 데이터 부족 명시)",
  "marketing_highlight": "분양·마케팅 강조 포인트 (입지·조망·ESG 등 검증된 사실 기반. 과장 금지)"
}}
"""


class DigitalTwinInterpreter(BaseInterpreter):
    """가상준공 디지털트윈 씬·컨텍스트를 AI가 해석해 5개 섹션 서술을 생성."""

    name = "digital_twin"
    expected_keys = [
        "design_rationale",
        "context_fit",
        "view_sunlight",
        "development_implication",
        "marketing_highlight",
    ]
    fallback_key = "design_rationale"
    max_tokens = 3072
    system_prompt = SYSTEM_PROMPT

    async def generate_interpretation(self, data: dict) -> dict[str, str]:
        """씬 요약+컨텍스트에 대한 5개 섹션 해석을 생성.

        Args:
            data: build_scene 요약 + context(roi/esg/permit/zone_type/design_summary).

        Returns:
            5개 키를 가진 dict — 각 값은 한국어 해석 문자열.
            LLM 호출 실패 시 빈 dict(호출자 폴백).
        """
        compact = self._extract_compact_data(data)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )
        return await self._invoke(user_prompt, cache_data=compact, evidence_data=data)

    def _evidence(self, data: dict) -> str | None:
        """P3: 대상지 주소 기반 지역 시세 벤치마크 주입(가용 시)."""
        return self._regional_benchmark(address=str(data.get("address", "")))

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """씬·컨텍스트에서 LLM에 필요한 핵심 그라운딩 데이터만 추출."""
        compact: dict[str, Any] = {}
        for key in ("address", "pnu", "zone_type", "land_area_sqm"):
            val = data.get(key)
            if val is not None:
                compact[key] = val

        terrain = data.get("terrain") or {}
        if terrain:
            compact["terrain"] = {
                "slope_deg": terrain.get("slope_deg") or terrain.get("avg_slope_deg"),
                "relief_m": terrain.get("relief_m"),
                "terrain_class": terrain.get("terrain_class") or terrain.get("class"),
                "elev0_m": terrain.get("elev0"),
                "resolution_m": terrain.get("resolution_m"),
            }

        if "neighbor_count" in data:
            compact["neighbor_count"] = data.get("neighbor_count")
        if "neighbor_avg_height_m" in data:
            compact["neighbor_avg_height_m"] = data.get("neighbor_avg_height_m")
        if "has_building_mass" in data:
            compact["has_building_mass"] = data.get("has_building_mass")
        for key in ("floors", "gross_floor_area_sqm"):
            if data.get(key) is not None:
                compact[key] = data.get(key)

        context = data.get("context") or {}
        if isinstance(context, dict):
            ctx: dict[str, Any] = {}
            for key in ("roi", "esg", "permit", "zone_type", "design_summary"):
                if context.get(key) is not None:
                    ctx[key] = context.get(key)
            if ctx:
                compact["context"] = ctx
        return compact
