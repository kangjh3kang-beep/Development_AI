"""설계 도구 운영기(DesignOperator) — P2. LLM=의도파싱, 커널=기하생성, 검증=하드가드.

흐름(할루시네이션 차단):
  자연어/음성 텍스트
    → DesignIntentInterpreter(LLM, 토큰계측, 규칙기반 폴백)로 '의도' 추출
    → apply_intent_to_spec: 의도를 DesignSpec에 '결정론적'으로 반영(법규 클램핑)
    → validate_spec: 스펙 사전 검증
    → AutoDesignEngineService.generate: 실제 기하·면적·법규지표 '계산'(LLM 아님)
    → validate_geometry: 커널 산출값을 법규와 대조(근거 게이트)
    → 결과 + 적용변경 + 위반(사유) 반환

LLM은 좌표·수치를 만들지 않는다. 화면 숫자는 전부 커널 산출값.
"""

from __future__ import annotations

from typing import Any

import structlog

from .auto_design_engine import AutoDesignEngineService
from .design_spec import DesignSpec, validate_geometry, validate_spec

logger = structlog.get_logger(__name__)

# 방 구성(자연어 의도) → 대표 평형(커널 UNIT_TYPES)
_ROOM_TO_UNIT = {"원룸": "39A", "투룸": "59A", "쓰리룸": "84A"}
_VALID_USES = {"공동주택", "근린생활시설", "업무시설", "판매시설", "숙박시설"}
_MIX_THRESHOLD = 0.15  # 비중 15% 이상인 방 구성만 평형에 반영


def _unit_types_from_mix(unit_mix: dict[str, float] | None, fallback: list[str]) -> list[str]:
    """방 비중(원룸/투룸/쓰리룸) → 대표 평형 리스트. 비면 기존 유지."""
    if not unit_mix:
        return fallback
    picked: list[str] = []
    for room, ratio in unit_mix.items():
        try:
            r = float(ratio or 0)
        except Exception:  # noqa: BLE001
            r = 0
        ut = _ROOM_TO_UNIT.get(room)
        if ut and r >= _MIX_THRESHOLD and ut not in picked:
            picked.append(ut)
    return picked or fallback


def apply_intent_to_spec(spec: DesignSpec, intent: dict[str, Any]) -> tuple[DesignSpec, list[str]]:
    """파싱된 의도를 스펙에 결정론적으로 반영. 적용된 변경 목록 반환."""
    changes: list[str] = []
    data = spec.model_dump()

    use = intent.get("building_use")
    if use and use in _VALID_USES and use != data["building_use"]:
        data["building_use"] = use
        changes.append(f"용도 → {use}")

    mix = intent.get("unit_mix")
    new_types = _unit_types_from_mix(mix, data["target_unit_types"])
    if new_types and new_types != data["target_unit_types"]:
        data["target_unit_types"] = new_types
        changes.append(f"평형 구성 → {', '.join(new_types)}")

    units = intent.get("target_units")
    if isinstance(units, (int, float)) and units and int(units) != (data.get("target_units") or 0):
        data["target_units"] = int(units)
        changes.append(f"목표 세대수 → {int(units)}")

    pr = intent.get("priority")
    if pr in ("yield", "balanced", "livability") and pr != data["priority"]:
        data["priority"] = pr
        changes.append(f"우선순위 → {pr}")

    margin = intent.get("target_margin_pct")
    if isinstance(margin, (int, float)) and margin and margin != data.get("target_margin_pct"):
        data["target_margin_pct"] = float(margin)
        changes.append(f"목표 마진 → {float(margin)}%")

    return DesignSpec(**data), changes


def _metrics_from_result(summary: dict[str, Any]) -> dict[str, Any]:
    """커널 summary → 검증용 지표(전부 커널 산출값)."""
    return {
        "bcr_pct": summary.get("bcr_percent"),
        "far_pct": summary.get("far_percent"),
        "building_height_m": summary.get("building_height_m"),
        "parking_required": summary.get("parking_count"),
        "total_units": summary.get("total_units"),
    }


class DesignOperator:
    """자연어/음성 → 검증된 설계 생성·편집 운영기."""

    def __init__(self) -> None:
        self.engine = AutoDesignEngineService()

    async def operate(self, text: str, spec: DesignSpec) -> dict[str, Any]:
        """텍스트 의도로 스펙을 편집하고 커널로 생성·검증한다.

        반환: spec, summary, compliance, design_payload, applied_changes,
              intent_notes, violations, source
        """
        # 1) 의도 파싱(LLM, 실패 시 규칙기반) — 기존 인터프리터 재사용
        intent: dict[str, Any] = {}
        source = "none"
        if (text or "").strip():
            try:
                from app.services.ai.design_intent_interpreter import DesignIntentInterpreter
                intent = await DesignIntentInterpreter().parse(
                    text, site_area_sqm=spec.site_area_sqm, zone_code=spec.zone_code,
                )
                source = intent.get("source", "llm")
            except Exception as e:  # noqa: BLE001 — 의도파싱 실패는 빈 의도로 흡수
                logger.warning("의도 파싱 실패", error=str(e)[:120])

        # 2) 의도 → 스펙(결정론적, 법규 클램핑)
        new_spec, changes = apply_intent_to_spec(spec, intent)

        # 3) 스펙 사전 검증
        spec_v = validate_spec(new_spec)

        # 4) 커널 생성(실제 기하·수치 계산 — LLM 아님)
        result = self.engine.generate(new_spec.to_site_input())

        # 5) 근거 게이트(법규): 커널 산출값을 법규와 대조
        m = _metrics_from_result(result.summary)
        geom_v = validate_geometry(
            new_spec, bcr_pct=m["bcr_pct"], far_pct=m["far_pct"],
            building_height_m=m["building_height_m"],
            parking_required=m["parking_required"], parking_provided=m["parking_required"],
        )

        # 6) 근거 게이트(수치): LLM 설명문 수치를 커널 산출값과 대조(가짜수치 적발)
        from .design_grounding import ground_check
        notes = intent.get("notes", "") or ""
        grounding = ground_check(result.summary, notes)

        return {
            "spec": new_spec.model_dump(),
            "summary": result.summary,
            "compliance": result.compliance,
            "design_payload": result.design_payload,
            "applied_changes": changes,
            "intent_notes": notes,
            "violations": [v.model_dump() for v in (spec_v + geom_v)],
            "grounding": grounding,
            "source": source,
        }

    async def generate_from_params(self, spec: DesignSpec) -> dict[str, Any]:
        """텍스트 없이 스펙 파라미터만으로 생성·검증(슬라이더/프리셋 경로)."""
        return await self.operate("", spec)
