"""다필지 parcels 요청 계약 공용 정규화(SSOT).

■ 왜(문제 = 무음 no-op 은폐)
  `parcels` 요청 필드의 shape 이 두 갈래로 발산해 왔다.
    · list[str]  … 주소 문자열 배열(지도 다중선택 등)
    · list[dict] … 필지 객체 배열(면적·용도지역 등 보유)
  dict 를 기대하는 엔드포인트에 str[] 을 보내면, 핸들러의 `isinstance(p, dict)` 필터와
  `area_sqm > 0` 필터가 문자열 요소를 '전량' 걸러낸다. 그 결과 에러 하나 없이 필지 목록이
  비어 단일필지 경로로 조용히 폴백(silent no-op)돼, 프론트/배선 실수가 '첫 필지만 분석'되는
  회귀로 은폐된다(디버깅 난이도 ↑, 사용자에겐 조용한 오답).

■ 무엇(해결 = 한 canonical dict[] 로 수렴)
  요청 검증 단계에서 두 shape 를 canonical dict[] 로 수렴시킨다.
    · str  요소 → {"address": s} 로 승격(주소만 채운 필지 객체) → 파이프라인에 '진입'한다
                (더 이상 무음 드롭되지 않는다).
    · dict 요소 → 원본 키를 보존한 채(merge) 정본 snake_case 키맵을 오버레이한다.

■ 무회귀(왜 기존 dict 동작이 안 깨지나)
  · 정본 통합집계 `_aggregate_integrated_zoning` 는 snake 키(area_sqm/zone_type/_far_eff…)
    '만' 읽는다. merge 로 원본 키가 남아 있어도 통합집계 산출값은 바이트 동일하다.
  · 정본 키맵에 없는 원본 키(예: auto_zoning `enrich_parcel_list` 가 필지 식별에 쓰는
    jibun·bcode, 설계생성이 쓰는 zone_code·zone_name·ordinance_*)는 merge 로 '보존'되어
    각 소비처가 그대로 읽는다. (원본을 통째로 치환[pure]했다면 이 키들이 소실 = 회귀였다.)
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator


def _to_float(v: Any) -> float | None:
    """숫자 변환(build_integrated_context 내부 `_f` 와 동일 계약) — None/변환실패는 None."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def canonicalize_parcel_row(p: dict) -> dict:
    """필지 dict → 정본 snake_case 키맵(12키)만 추출한 dict.

    ★comprehensive_analysis_service.build_integrated_context 의 인라인 정규화
      (프론트 camelCase(AddressEntry) ↔ 집계 입력키(_far_eff 등))를 byte-동일하게
      '이관'한 것 — 재작성이 아니다. 반환 dict 의 키·값은 인라인 q 와 동일하다.
      (프론트 farPct/bcrPct 는 이미 조례반영 실효치이므로 _far_eff/_bcr_eff 로 매핑한다.)
    """
    return {
        "pnu": p.get("pnu"),
        "address": p.get("address") or p.get("jibunAddress") or p.get("fullAddress"),
        "zone_type": p.get("zone_type") or p.get("zoneCode") or p.get("zoneType"),
        "land_category": p.get("land_category") or p.get("landCategory") or p.get("jimok"),
        "area_sqm": _to_float(
            p.get("area_sqm") if p.get("area_sqm") is not None else p.get("areaSqm")
        ),
        "_far_eff": _to_float(
            p.get("_far_eff") if p.get("_far_eff") is not None else p.get("farPct")
        ),
        "_bcr_eff": _to_float(
            p.get("_bcr_eff") if p.get("_bcr_eff") is not None else p.get("bcrPct")
        ),
        "_far_legal": _to_float(
            p.get("_far_legal") if p.get("_far_legal") is not None else p.get("farLegalPct")
        ),
        "_bcr_legal": _to_float(
            p.get("_bcr_legal") if p.get("_bcr_legal") is not None else p.get("bcrLegalPct")
        ),
        # 필지 경계(geometry) 통과 — 없으면 인접성(contiguous) 판정이 영구 미확정.
        "geometry": p.get("geometry"),
        # 다필지 접도 완화 입력 — 프론트/업로드가 이미 실어 보내는 경우만 통과(신규 조회 없음).
        "road_side": p.get("road_side") or p.get("roadSide"),
        "road_contact": (
            p.get("road_contact") if p.get("road_contact") is not None else p.get("roadContact")
        ),
    }


def normalize_parcels(raw: Any) -> list[dict]:
    """parcels 요청값(list[str] | list[dict] | None) → canonical dict[] 로 수렴.

    - str  요소 → {"address": s.strip()} 로 승격(공백 트림·빈 문자열 제외).
             ★무음 no-op 은폐 제거: str[] 이 dict 필터에 전량 걸러지지 않고 주소 필지로 진입한다.
    - dict 요소 → {**원본, **canonicalize_parcel_row(원본)} (merge=무손실).
             원본 키(jibun/bcode/zone_code 등)를 보존한 채 정본 snake 키를 오버레이한다.
    - 그 외 타입(int/None 등) 요소 → 드롭(정직 축소 — 가짜 필지 생성 금지).
    - address(정본) 기준 중복 제거(순서 보존·첫 항목 우선). address 가 없는 행은 dedup 대상이
      아니다(식별 키가 없어 임의 병합 시 필지 소실 위험 → 전부 보존).
    - None/빈 입력 → [].
    """
    if not raw:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            s = item.strip()
            if not s:
                continue
            row = canonicalize_parcel_row({"address": s})
        elif isinstance(item, dict):
            # merge: 원본 키 보존 + 정본 snake 키 오버레이(무손실).
            row = {**item, **canonicalize_parcel_row(item)}
        else:
            continue
        addr = row.get("address")
        if addr:
            if addr in seen:
                continue
            seen.add(addr)
        out.append(row)
    return out


# ── Pydantic v2 공용 타입 ──
# 요청모델의 `parcels` 필드를 이 타입으로 교체하면, str[]/dict[] 양 shape 가 검증 단계
# (BeforeValidator)에서 canonical dict[] 로 수렴한다. 라우터의 기존 `isinstance(p, dict)`
# 사전 필터는 normalize 가 선행되어 실질 no-op 이 되지만 방어층으로 남겨둔다(제거 금지).
ParcelsIn = Annotated[list[dict], BeforeValidator(normalize_parcels)]
