"""EnvelopeResult — 매스/엔벨로프 산출물의 단일 타입계약(C2R envelope_result ADAPT, INC2-a).

이 파일이 푸는 문제(쉬운 설명):
- 지금 우리 플랫폼은 '건물 매스(층수·면적·치수)' 결과를 여러 경로가 제각각의 dict로 만든다
  (DesignResult의 summary/compliance, compute_buildable_envelope의 납작한 dict, c2r build_foundation 등).
  같은 값을 부르는 이름·구조가 경로마다 달라서 '층수/면적이 어디선 다르게 나오는' SSOT 불일치의 토양이 된다.
- 그래서 이 파일은 매스 결과를 담는 '한 가지 표준 그릇'(Pydantic 모델 EnvelopeResult)을 정의한다.
  앞으로 모든 경로가 같은 그릇에 담으면 이름·구조가 한 곳에서 강제돼 불일치가 구조적으로 사라진다.

이번 증분(INC2-a)의 범위는 '계약 정의 + 순수 어댑터 + additive 부착'까지다.
- 어댑터 mass_to_envelope_result(): compute_optimal_mass가 내놓는 매스 dict를 이 표준 그릇으로 '변환만' 한다.
- 기존 반환 구조·수치는 손대지 않는다(소비처 마이그레이션은 후속 증분 = 리스크 격리).

★무날조 원칙: 매스 dict에 없는 값은 절대 가짜로 채우지 않고 None으로 둔다(가짜 0 금지).
  숫자는 None/NaN/inf를 흡수하고, 매스가 dict가 아니면 예외 없이 '빈 결과'를 돌려준다.

신규 의존성 0: Pydantic은 이미 전역 표준이고, GeoStatus enum은 geometry_invariants(INC1)를 재사용한다.
"""

from __future__ import annotations

import math
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.services.cad.geometry_invariants import GeoStatus  # PASS/PASS_WITH_WARNINGS/FAIL 재사용
from app.services.cad.provenance import (  # INC3: run_id+해시(재현·출처추적·변조탐지·멱등)
    ENGINE_SOURCE_VERSION,
    compute_geometry_hash,
    compute_input_hash,
    make_run_id,
)

logger = structlog.get_logger(__name__)


# ── 작은 수치 가드(무날조) ──

def _num(value: Any) -> float | None:
    """값이 유한한 숫자면 float로, 아니면 None(=미상 → 가짜값 금지)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _int_or_none(value: Any) -> int | None:
    """값이 유한한 숫자면 정수로, 아니면 None(층수·세대수 같은 정수 필드용)."""
    f = _num(value)
    return int(f) if f is not None else None


def _dict_or_none(value: Any) -> dict | None:
    """값이 dict면 그대로, 아니면 None(podium/tower 같은 중첩 박스용)."""
    return value if isinstance(value, dict) else None


# ── 표준 그릇(Pydantic 모델) ──

class EnvelopeGeometry(BaseModel):
    """기하(매스 치수) — 건물의 '모양·크기'를 담는 칸. 미상은 None."""

    building_width_m: float | None = None        # 건물 폭(m)
    building_depth_m: float | None = None        # 건물 깊이(m)
    footprint_sqm: float | None = None           # 건축면적(지상 한 층 바닥판, ㎡)
    num_floors: int | None = None                # 전체 층수(podium+tower 합산 등 headline)
    floor_height_m: float | None = None          # 층고(m)
    building_height_m: float | None = None        # 건물 높이(m)
    massing_profile: str | None = None           # 매스 형상(예: "podium_tower")
    podium: dict | None = None                   # {width_m,depth_m,floors,footprint_sqm}
    tower: dict | None = None                    # {width_m,depth_m,floors,footprint_sqm}
    floors_for_units: int | None = None          # ★정본 주거층수(세대수 산정 기준·podium 제외)
    residential_gfa_sqm: float | None = None     # 주거 연면적(세대분해 풀·podium 제외, ㎡)


class EnvelopeMetrics(BaseModel):
    """핵심 수치 — 보고·검증에 바로 쓰는 '숫자' 칸. 미상은 None(가짜값 금지)."""

    bcr_pct: float | None = None                 # 건폐율(%)
    far_pct: float | None = None                 # 용적률(%)
    # 총 연면적(total_floor_area_sqm·podium 포함) — geometry.residential_gfa_sqm(주거풀·podium 제외)과 구별.
    gfa_sqm: float | None = None
    canonical_floors: int | None = None          # ★정본 층수(floors_for_units가 있으면 그것, 없으면 num_floors)
    total_units: int | None = None               # 총 세대수
    applied_max_bcr_pct: float | None = None     # 적용 건폐율 한도(목표 반영)
    applied_max_far_pct: float | None = None     # 적용 용적률 한도(목표 반영)


class EnvelopeResult(BaseModel):
    """매스/엔벨로프 산출물의 단일 표준 그릇(SSOT 계약).

    기존 dict 산출물을 대체하지 않고(이번 증분은 additive 부착만), 앞으로 모든 경로가
    같은 구조로 모이게 하는 '표준'이다. status는 기하불변식(INC1)의 최악 등급을 반영한다.
    """

    schema_version: str = "propai.envelope_result.v0.1"
    status: GeoStatus = GeoStatus.PASS                       # 기하불변식 최악등급(없으면 PASS)
    geometry: EnvelopeGeometry
    metrics: EnvelopeMetrics
    # 근거계약{value,basis,source,legal_link,confidence} 리스트. 없으면 빈 리스트.
    evidence: list[dict] = Field(default_factory=list)
    geometry_invariants: dict | None = None                  # INC1 결과 to_dict()(있으면)
    warnings: list[str] = Field(default_factory=list)
    # ★hash/run_id는 다음 증분(INC3)에서 부착할 자리 — 지금은 옵셔널로만 둔다(미리 깨지지 않게).
    run_id: str | None = None
    input_hash: str | None = None
    geometry_hash: str | None = None
    source_version: str | None = None
    # ★rule_trace/rule_set_hash(INC5-a·additive) — '어떤 법규가 어떤 값으로 적용됐는지' 추적.
    #   rule_set_hash는 §4 provenance triad(input_hash·geometry_hash·rule_set_hash)의 마지막 한 칸.
    #   둘 다 옵셔널이라 미부착(None/빈 리스트)이어도 기존 직렬화·소비처는 깨지지 않는다.
    # rule_set_hash = '적용된 규칙 묶음'의 지문(산출 결과값이 아님 — 결과는 geometry_hash가 담당, triad 역할분담).
    rule_set_hash: str | None = None
    # rule_trace 항목 {rule_code,rule_name,applied,basis,source,legal_link} — evidence와 별개 구조(kernel-trace).
    rule_trace: list[dict] = Field(default_factory=list)


# ── 순수 어댑터 ──

def mass_to_envelope_result(
    mass: dict,
    *,
    total_units: int | None = None,
    evidence: list[dict] | None = None,
    geo_invariants: dict | None = None,
    input_fingerprint: dict | None = None,
) -> EnvelopeResult:
    """compute_optimal_mass 출력(매스 dict)을 표준 EnvelopeResult로 변환하는 순수 함수.

    무날조: 매스에 없는 키는 None으로 둔다(가짜값 금지). 매스가 dict가 아니면 예외 없이
    빈 geometry/metrics의 EnvelopeResult를 돌려준다(소비처가 깨지지 않게).

    provenance(INC3): 재현·출처추적·변조탐지·멱등을 위해 run_id+해시를 부착한다.
      - input_fingerprint가 주어지면 input_hash=sha256(정규화 JSON)·run_id="c2r_"+input_hash[:16]를
        채운다(★결정론 — 같은 입력이면 항상 같은 값). 없으면 둘 다 None(가짜 해시 금지·무날조).
      - geometry_hash는 산출 기하(EnvelopeGeometry)에서 항상 계산한다(기하가 비면 빈 dict 해시).
      - source_version은 코드 상수라 항상 채운다(어느 엔진·법규 기준 산출물인지 표기).

    매핑(매스 dict 키 → 표준 그릇):
      building_width_m/building_depth_m/building_footprint_sqm/num_floors/floor_height_m/
      building_height_m/total_floor_area_sqm/bcr_pct/far_pct/applied_max_bcr_pct/
      applied_max_far_pct/podium/tower/floors_for_units/residential_gfa_sqm/massing_profile.
      canonical_floors = floors_for_units(있으면) else num_floors.
      status = geo_invariants["status"](있으면) else PASS.
    """
    # 매스가 dict가 아니면 '빈 결과'를 정직하게 돌려준다(예외 금지·소비처 보호).
    # 단, source_version·geometry_hash(빈 기하)는 항상 채워 provenance 일관성을 유지한다.
    if not isinstance(mass, dict):
        logger.debug("mass_to_envelope_result: 비-dict 입력 — 빈 EnvelopeResult 반환")
        empty_geometry = EnvelopeGeometry()
        return _attach_provenance(
            EnvelopeResult(geometry=empty_geometry, metrics=EnvelopeMetrics()),
            geometry=empty_geometry,
            input_fingerprint=input_fingerprint,
        )

    floors_for_units = _int_or_none(mass.get("floors_for_units"))
    num_floors = _int_or_none(mass.get("num_floors"))

    geometry = EnvelopeGeometry(
        building_width_m=_num(mass.get("building_width_m")),
        building_depth_m=_num(mass.get("building_depth_m")),
        footprint_sqm=_num(mass.get("building_footprint_sqm")),
        num_floors=num_floors,
        floor_height_m=_num(mass.get("floor_height_m")),
        building_height_m=_num(mass.get("building_height_m")),
        massing_profile=mass.get("massing_profile"),
        podium=_dict_or_none(mass.get("podium")),
        tower=_dict_or_none(mass.get("tower")),
        floors_for_units=floors_for_units,
        residential_gfa_sqm=_num(mass.get("residential_gfa_sqm")),
    )

    # ★정본 층수: 주거층수(floors_for_units)가 있으면 그것, 없으면(단일박스) 전체 층수.
    canonical_floors = floors_for_units if floors_for_units is not None else num_floors

    metrics = EnvelopeMetrics(
        bcr_pct=_num(mass.get("bcr_pct")),
        far_pct=_num(mass.get("far_pct")),
        gfa_sqm=_num(mass.get("total_floor_area_sqm")),
        canonical_floors=canonical_floors,
        total_units=_int_or_none(total_units),
        applied_max_bcr_pct=_num(mass.get("applied_max_bcr_pct")),
        applied_max_far_pct=_num(mass.get("applied_max_far_pct")),
    )

    # status는 기하불변식(INC1) 최악등급을 따른다 — 없거나 알 수 없는 값이면 PASS(가짜 FAIL 금지).
    status = GeoStatus.PASS
    if isinstance(geo_invariants, dict):
        raw_status = geo_invariants.get("status")
        try:
            status = GeoStatus(raw_status)
        except ValueError:
            status = GeoStatus.PASS

    # 경고는 기하불변식 결과의 warnings를 그대로 싣는다(있으면).
    warnings: list[str] = []
    if isinstance(geo_invariants, dict):
        raw_warnings = geo_invariants.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [str(w) for w in raw_warnings]

    result = EnvelopeResult(
        status=status,
        geometry=geometry,
        metrics=metrics,
        evidence=list(evidence) if evidence else [],
        geometry_invariants=geo_invariants if isinstance(geo_invariants, dict) else None,
        warnings=warnings,
    )
    # provenance(INC3): run_id+해시 부착 — 산출 기하에서 geometry_hash를 계산하고,
    #   input_fingerprint가 있으면 input_hash·run_id까지 채운다(없으면 None·무날조).
    return _attach_provenance(
        result, geometry=geometry, input_fingerprint=input_fingerprint
    )


def _attach_provenance(
    result: EnvelopeResult,
    *,
    geometry: EnvelopeGeometry,
    input_fingerprint: dict | None,
) -> EnvelopeResult:
    """EnvelopeResult에 provenance(run_id·input_hash·geometry_hash·source_version)를 채워 돌려준다.

    무날조: input_fingerprint가 없으면 input_hash/run_id는 None으로 둔다(가짜 해시 금지).
    geometry_hash는 산출 기하에서 항상 계산한다(기하가 비면 빈 dict 해시).
    source_version은 코드 상수라 항상 채운다.
    """
    # 입력 핑거프린트가 있으면 결정론적 input_hash·run_id를 만든다(없으면 None — 정직).
    input_hash = compute_input_hash(input_fingerprint) if isinstance(input_fingerprint, dict) else None
    run_id = make_run_id(input_hash) if input_hash is not None else None

    # 산출 기하의 해시는 항상 계산한다(빈 기하면 빈 dict 해시 → 안정적·변조탐지 가능).
    geometry_hash = compute_geometry_hash(geometry.model_dump(mode="json"))

    # Pydantic 모델은 model_copy(update=...)로 불변 갱신 — 원본 손대지 않고 새 필드만 채운다.
    return result.model_copy(
        update={
            "run_id": run_id,
            "input_hash": input_hash,
            "geometry_hash": geometry_hash,
            "source_version": ENGINE_SOURCE_VERSION,
        }
    )
