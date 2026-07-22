"""주차구획·차로 치수 SSOT (스펙 P — W3-5).

주차장법 시행규칙 §3(주차장의 주차구획)·§11(주차장의 구조·설비기준 — 차로 너비)를
근거로 구획 유형별 치수와 주차각도별 차로 폭을 상수로 고정한다. 법정 주차 "대수" 산정
(주차장법 시행령 §6 별표1)은 이 모듈의 범위가 아니다 — 그 SSOT는
``app.services.permit.building_code_rules.PARKING_REQUIREMENTS``이며, 본 패키지는
이를 재사용한다(이중화 금지, verify.py 참조).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class StallType(StrEnum):
    """주차구획 유형(주차장법 시행규칙 §3)."""

    GENERAL = "general"       # 일반형
    EXPANDED = "expanded"     # 확장형
    PARALLEL = "parallel"     # 평행주차형
    DISABLED = "disabled"     # 장애인전용


class StallSpec(BaseModel):
    """구획 유형 1건의 치수·근거·가정·한계."""

    stall_type: StallType
    name_kr: str
    width_m: float
    length_m: float
    area_sqm: float
    basis: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verified: bool = True


# ── 구획 유형별 치수 SSOT(주차장법 시행규칙 §3) ────────────────────────────
STALL_SPECS: dict[StallType, StallSpec] = {
    StallType.GENERAL: StallSpec(
        stall_type=StallType.GENERAL,
        name_kr="일반형",
        width_m=2.5,
        length_m=5.0,
        area_sqm=12.5,
        basis="주차장법 시행규칙 제3조(주차장의 주차구획) — 일반형 너비 2.5m×길이 5.0m",
        assumptions=["직각(90°) 배치 기준 표준 치수 — 지자체 조례로 강화될 수 있음"],
        limitations=["평지·직선 구획 기준(경사·곡선 구획은 별도 여유 필요)"],
        verified=True,
    ),
    StallType.EXPANDED: StallSpec(
        stall_type=StallType.EXPANDED,
        name_kr="확장형",
        width_m=2.6,
        length_m=5.2,
        area_sqm=13.52,
        basis="주차장법 시행규칙 제3조(주차장의 주차구획) — 확장형 너비 2.6m×길이 5.2m",
        assumptions=["부설주차장 등 확장형 적용 대상 기준(경형·일반형 혼합 배치 시 별도 비율 규정 확인 필요)"],
        limitations=["평지·직선 구획 기준(경사·곡선 구획은 별도 여유 필요)"],
        verified=True,
    ),
    StallType.PARALLEL: StallSpec(
        stall_type=StallType.PARALLEL,
        name_kr="평행주차형",
        width_m=2.0,
        length_m=6.0,
        area_sqm=12.0,
        basis="주차장법 시행규칙 제3조(주차장의 주차구획) — 평행주차형 너비 2.0m×길이 6.0m",
        assumptions=["도로·통로변 1열 평행배치 기준"],
        limitations=["진출입 동선(전진/후진) 여유공간은 본 치수에 포함되지 않음"],
        verified=True,
    ),
    StallType.DISABLED: StallSpec(
        stall_type=StallType.DISABLED,
        name_kr="장애인전용",
        width_m=3.3,
        length_m=5.0,
        area_sqm=16.5,
        basis="주차장법 시행규칙 제3조(주차장의 주차구획) — 장애인전용 너비 3.3m×길이 5.0m",
        assumptions=["장애인·노인·임산부 등의 편의증진 보장에 관한 법률 관련 설치기준과 병행 확인 필요"],
        limitations=["설치 의무 대수(전체 주차대수 대비 비율)는 본 모듈 범위 밖"],
        verified=True,
    ),
}


class AisleSpec(BaseModel):
    """주차각도 1건의 차로 폭·근거·가정·한계."""

    parking_angle_deg: int
    name_kr: str
    aisle_width_m: float
    basis: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verified: bool = True


# ── 주차각도별 차로 폭 SSOT(주차장법 시행규칙 §11) ─────────────────────────
# ★키 0은 각도 0°가 아니라 "평행주차" 배치를 가리키는 관례적 키.
AISLE_SPECS: dict[int, AisleSpec] = {
    90: AisleSpec(
        parking_angle_deg=90,
        name_kr="직각주차",
        aisle_width_m=6.0,
        basis="주차장법 시행규칙 제11조(주차장의 구조·설비기준) — 직각주차 차로 너비 6.0m 이상",
        assumptions=["양방향 통행 기준(일방통행 시 조례로 완화될 수 있음)"],
        limitations=["직선 구간 기준 — 곡선부 확폭은 별도(swept_path 참조)"],
        verified=True,
    ),
    60: AisleSpec(
        parking_angle_deg=60,
        name_kr="60도 주차",
        aisle_width_m=4.5,
        basis="주차장법 시행규칙 제11조(주차장의 구조·설비기준) — 60도 주차 차로 너비 4.5m 이상",
        assumptions=[],
        limitations=["직선 구간 기준 — 곡선부 확폭은 별도(swept_path 참조)"],
        verified=True,
    ),
    45: AisleSpec(
        parking_angle_deg=45,
        name_kr="45도 주차",
        aisle_width_m=3.5,
        basis="주차장법 시행규칙 제11조(주차장의 구조·설비기준) — 45도 주차 차로 너비 3.5m 이상",
        assumptions=[],
        limitations=["직선 구간 기준 — 곡선부 확폭은 별도(swept_path 참조)"],
        verified=True,
    ),
    0: AisleSpec(
        parking_angle_deg=0,
        name_kr="평행주차",
        aisle_width_m=3.0,
        basis="주차장법 시행규칙 제11조(주차장의 구조·설비기준) — 평행주차 차로 너비 3.0m 이상",
        assumptions=["편도 통행 기준"],
        limitations=["직선 구간 기준 — 곡선부 확폭은 별도(swept_path 참조)"],
        verified=True,
    ),
}


# ── 설계기준차량 최소회전반경(swept path 1차 검증용) ───────────────────────
# ★출처 조항번호 미확인 — 값 자체(승용차 6.0m)는 실무·설계기준 관례이나 정확한
# 조문 대조는 이번 스파이크 범위 밖. verified=False로 정직 표기(날조 금지).
DESIGN_VEHICLE_MIN_TURN_RADIUS_M: float = 6.0
DESIGN_VEHICLE_MIN_TURN_RADIUS_BASIS: str = (
    "도로의 구조·시설 기준에 관한 규칙/KDS(한국설계기준) — 승용차 설계기준차량 "
    "최소회전반경 통상 6.0m(구체 조항번호 미확인 — verified=False, 상세설계 단계에서 "
    "실제 설계기준차량 제원으로 재확인 필요)"
)
