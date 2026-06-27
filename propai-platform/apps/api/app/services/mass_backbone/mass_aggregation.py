"""건축물대장 실측 → 건축물종류별 매스 템플릿 집계(순수·결정론·라이브 API 무관).

mass_backbone 데이터 레이어 D1 — building_registry_service가 정규화한 대장 record list를 받아
건축물종류별로 중앙값 통계(건폐/용적/층수/연면적)를 산출한다. 동일 입력 동일 출력(median·정렬 결정론).

★무목업: 실측치 보유 표본이 있는 종류만 산출하고, 지표가 없으면 그 지표는 None(가짜 표준 금지).
★출처(provenance): 표본 건수(sample_count)와 지표별 표본수(metadata)를 동반해 신뢰도를 정직 표기.
입력 record(정규화) = building_registry_service 출력: main_purpose·bcr_pct·far_pct·ground_floors·total_area_sqm.
"""

from __future__ import annotations

from statistics import median
from typing import Any

# 주용도(mainPurpsCdNm) → 정규화 건축물종류. 공부상 명칭 변형 대비 키워드 매칭.
# ★우선순위 순(첫 매칭 채택) — 개발상품으로 구분 가치가 큰 '세부 유형'을 상위에 둬, 포괄 유형(공장/업무/
#   숙박/판매)에 흡수되지 않게 한다. 예: 지식산업센터는 공장보다, 오피스텔/생활숙박은 업무/숙박보다 먼저.
# ★키워드는 건축법 별표1 주용도 명칭 변형을 포괄(데이터에 없으면 매칭 안 돼도 무해 — 가짜 분류 금지).
_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    # ── 개발상품 세부 유형(포괄 유형보다 먼저) ──
    ("지식산업센터", ("지식산업센터", "아파트형공장")),               # 공장보다 먼저
    ("오피스텔", ("오피스텔",)),                                      # 업무시설보다 먼저
    ("생활숙박시설", ("생활숙박", "생활형숙박", "레지던스")),         # 숙박시설보다 먼저
    ("상가주택", ("상가주택", "점포겸용")),                          # 단독/판매보다 먼저(점포겸용 단독)
    # ── 주거 ──
    ("공동주택", ("공동주택", "아파트", "연립주택", "다세대", "기숙사", "도시형생활주택")),
    ("단독주택", ("단독주택", "다가구", "전원주택")),
    # ── 숙박·판매·업무 ──
    ("숙박시설", ("숙박", "호텔", "모텔", "여관", "펜션", "콘도", "리조트")),
    # "시장"→"전통시장": 일반 "시장"은 "전시장"(문화)을 부분매칭으로 가로채므로 좁힘.
    ("판매시설", ("판매시설", "상가", "쇼핑", "백화점", "마트", "전통시장", "점포")),
    ("업무시설", ("업무시설", "사무소", "사무실", "오피스")),
    ("근린생활시설", ("근린생활", "근생", "소매점")),
    # ── 산업·물류 ──
    ("창고시설", ("창고", "물류")),
    ("공장", ("공장", "제조", "공업")),
    # ── 공공·생활 ──
    # ★의료를 교육보다 먼저: "대학병원"이 "대학"(교육)에 흡수되지 않고 "병원"(의료)으로 잡히게.
    ("의료시설", ("의료", "병원", "요양", "의원")),
    ("교육연구시설", ("교육", "학교", "연구소", "대학", "학원")),
    # ★"전시"→"전시장"으로 좁힘: "발전시설"·"충전시설"이 "전시" 부분매칭으로 오분류되던 것 방지.
    ("문화집회시설", ("문화", "집회", "종교", "전시장", "공연", "예식")),
    ("운동시설", ("운동", "체육", "스포츠", "경기")),
    ("운수시설", ("운수", "터미널", "여객", "주차장")),
    ("위락시설", ("위락",)),
]


def classify_building_type(main_purpose: str | None) -> str:
    """주용도 명칭 → 정규화 건축물종류. 빈값/미매칭은 '기타'(가짜 분류 금지)."""
    s = (main_purpose or "").strip()
    if not s:
        return "기타"
    for label, keywords in _TYPE_RULES:
        if any(k in s for k in keywords):
            return label
    return "기타"


def _pos_float(v: Any) -> float | None:
    """양수 유한 수치만(bool·None·0·음수·비수치 제외) — 실측치만 집계(가짜 0 평균 방지)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v > 0 else None


def aggregate_mass_templates(
    records: list[dict[str, Any]],
    *,
    region: str,
    zone_code: str | None = None,
    source: str = "building_registry",
    min_samples: int = 1,
) -> list[dict[str, Any]]:
    """대장 record list → 건축물종류별 매스 템플릿(중앙값 통계 + provenance).

    유효 표본(핵심지표 하나 이상 보유 record)이 min_samples 이상인 종류만 반환한다(무목업).
    반환 = MassTemplate 컬럼과 정합한 dict 목록(표본수 내림차순·종류명 결정론 정렬).

    ★zone 경계(caller 책임): 그룹화는 building_type만으로 하고 zone_code는 출력행에 라벨로 찍는다.
      용도지역(2종/3종 등)이 섞인 records를 한 번에 넣으면 용적률 등 중앙값이 이질 zone을 혼합한다.
      → caller는 단일 zone으로 사전 필터해 zone별로 호출하라(혼합 시 median 왜곡·라벨 오인).
    ★median_floors는 통계 중앙값(짝수 표본 시 22.5처럼 분수 가능) — 표시용은 caller가 반올림.
    """
    min_samples = max(1, min_samples)  # 0 이하면 전지표 None 행이 생겨 무목업 위배 → 하한 1 강제.
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if not isinstance(r, dict):
            continue
        groups.setdefault(classify_building_type(r.get("main_purpose")), []).append(r)

    out: list[dict[str, Any]] = []
    for building_type, rows in groups.items():
        bcrs = [x for x in (_pos_float(r.get("bcr_pct")) for r in rows) if x is not None]
        fars = [x for x in (_pos_float(r.get("far_pct")) for r in rows) if x is not None]
        floors = [x for x in (_pos_float(r.get("ground_floors")) for r in rows) if x is not None]
        areas = [x for x in (_pos_float(r.get("total_area_sqm")) for r in rows) if x is not None]
        # 표본 = 핵심지표(건폐/용적/층수/연면적) 중 하나라도 실측치 보유한 record 수.
        sample = sum(
            1 for r in rows
            if any(_pos_float(r.get(k)) is not None for k in ("bcr_pct", "far_pct", "ground_floors", "total_area_sqm"))
        )
        if sample < min_samples:
            continue
        out.append({
            "region": region,
            "zone_code": zone_code,
            "building_type": building_type,
            "sample_count": sample,
            "source": source,
            "median_bcr_pct": round(median(bcrs), 1) if bcrs else None,
            "median_far_pct": round(median(fars), 1) if fars else None,
            "median_floors": round(median(floors), 1) if floors else None,
            "median_total_area_sqm": round(median(areas), 1) if areas else None,
            # 지표별 표본수(신뢰도 정직 표기) — 일부 지표만 있을 수 있음.
            "metadata": {"bcr_n": len(bcrs), "far_n": len(fars), "floors_n": len(floors), "area_n": len(areas)},
        })
    # 대표 종류 우선(표본 많은 순)·동수는 종류명 사전순(결정론).
    out.sort(key=lambda t: (-t["sample_count"], t["building_type"]))
    return out


def fill_bcr_far_from_recap(
    templates: list[dict[str, Any]], recap_templates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """표제부 집계(templates)의 결측 건폐/용적을 총괄표제부 집계(recap_templates)의 같은 종류 값으로 보강.

    ★공동주택(아파트)은 동별 표제부에 bcRat/vlRat이 비어 median_bcr/far가 None이 되는데, 총괄표제부
      (단지 기준)엔 충실하다 → 같은 building_type의 총괄 median으로 채운다(in-place 갱신·반환).
    ★면적(median_total_area_sqm)·층수·표본수는 표제부 기준 유지 — 총괄 면적은 '단지 총연면적'이라
      동별 면적과 섞으면 왜곡되므로 보강하지 않는다(건폐/용적만).
    ★보강 시 provenance(metadata.bcr_far_source='recap_title')로 출처를 정직 표기. 무목업: 총괄에도
      값이 없으면 그대로 None 유지(가짜 생성 금지).
    """
    by_type = {t["building_type"]: t for t in recap_templates}
    for t in templates:
        rc = by_type.get(t["building_type"])
        if not rc:
            continue
        filled = False
        if not t.get("median_bcr_pct") and (rc.get("median_bcr_pct") or 0) > 0:
            t["median_bcr_pct"] = rc["median_bcr_pct"]
            filled = True
        if not t.get("median_far_pct") and (rc.get("median_far_pct") or 0) > 0:
            t["median_far_pct"] = rc["median_far_pct"]
            filled = True
        if filled:
            meta = t.setdefault("metadata", {})
            meta["bcr_far_source"] = "recap_title"  # 건폐/용적은 총괄표제부(단지 기준)에서 보강
            meta["recap_sample"] = rc.get("sample_count")
    return templates
