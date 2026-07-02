"""파라메트릭 BOQ(공내역서) 초안 엔진 — 실적 원단위 스케일링 (B2).

실무 공내역서 1건(의정부동 424 주상복합 신축공사, 연면적 238,504㎡)에서 추출한
5공종 표준항목 마스터(data/boq_master/*.json, 3,997 고유항목·414 섹션)를 기준으로,
대상 프로젝트 파라미터(연면적·세대수·조경면적)에 비례해 물량을 스케일링한
'공내역서 초안'을 생성한다. 공내역서 표준대로 단가는 비운다(빈칸).

정직성 원칙:
- 표본 n=1 — 모든 응답에 confidence '낮음(n=1)'·'전문 적산 검토 필수' 배지 부착.
- 기준값(REF) 중 추정값(세대수·조경면적)은 basis 문자열로 산출 근거를 명시.
- 가짜 단가 생성 금지 — 전기 공종의 참고 재료단가(ref_mat_price)만 원본 그대로 전달.
- 결정론: LLM 0. 드라이버 배정은 아래 규칙 기반(첫 일치 우선)으로만 수행.

드라이버 배정 규칙(항목별, 첫 일치 우선):
1) section_name/name 에 '세대' 포함('단위세대' 포함) → households
   (households 미제공 시 gfa 폴백 + warning)
2) 공종이 조경                                      → landscape_area
   (landscape_area_sqm 미제공 시 gfa 폴백 + warning)
3) unit '식' 이고 qty_sample<=2                     → fixed (횟수성 가설항목 — 수량 유지)
4) 그 외                                            → gfa

B1 boq_master_registry 의 계약(get_items 페이지네이션·get_sections·get_provenance)을
우선 사용하고, 임포트 불가 시(병렬 작업 환경) 동일 JSON을 직접 로드하는 폴백을 쓴다.
두 경로 모두 같은 data/boq_master/*.json 이 SSOT 이고 항목을 id 오름차순으로
정렬하므로 결과는 동일하다(결정론).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# ── 기준값(REF) — 실적 1건의 프로젝트 파라미터 ───────────────────────────────

REF_GFA_SQM = 238504.0
REF_HOUSEHOLDS = 1384.0
REF_LANDSCAPE_AREA_SQM = 5060.0

REF_BASIS: dict[str, str] = {
    "gfa_sqm": (
        "건축 공내역서 '임시동력+가설전기시설(연면적기준)' 수량 238,504㎡ — 확인값"
    ),
    "households": (
        "기계 공내역서 벽걸이보일러 B시리즈(B-1~B-3) 수량 합계 1,384대 기반 추정 "
        "(B-4·B-5 예비분 3대 제외 — 공식 세대수 문서 미보유)"
    ),
    "landscape_area_sqm": (
        "조경 공내역서 방근시트·배수판·부직포 공통 수량 5,060㎡ 기반 추정 "
        "(인공지반 조경면적 — 공식 조경면적 문서 미보유)"
    ),
}

_HONESTY_NOTE = "실적 1건 기반 원단위 초안 — 전문 적산 검토 필수"
_CONFIDENCE = "낮음(n=1)"

# 공종 캐논 이름(_meta.json 키) ↔ 파일/영문 별칭
_DISCIPLINE_FILES: dict[str, str] = {
    "건축": "architecture.json",
    "기계소방": "mechanical.json",
    "전기통신소방": "electrical.json",
    "조경": "landscape.json",
    "토목": "civil.json",
}
_ALIASES: dict[str, str] = {
    "architecture": "건축",
    "mechanical": "기계소방",
    "electrical": "전기통신소방",
    "landscape": "조경",
    "civil": "토목",
}

_DATA_DIR = Path(__file__).resolve().parent / "data" / "boq_master"


# ── 마스터 접근(B1 레지스트리 우선, JSON 직접 로드 폴백) ─────────────────────

def _registry() -> Any | None:
    """B1 boq_master_registry 모듈(병렬 작업) — 미존재 시 None."""
    try:
        from app.services.cost import boq_master_registry  # noqa: PLC0415
        return boq_master_registry
    except Exception:  # noqa: BLE001 — B1 미병합 환경에서도 동작(동일 JSON 폴백)
        return None


@lru_cache(maxsize=8)
def _load_json(filename: str) -> dict[str, Any]:
    with open(_DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


_PAGE_LIMIT = 500  # boq_master_registry._MAX_LIMIT 와 동일(계약값)


def _items_via_registry(reg: Any, discipline: str) -> tuple[list[dict[str, Any]], str] | None:
    """레지스트리 get_items 페이지네이션 전량 수집 — 실패/미발견 시 None."""
    items: list[dict[str, Any]] = []
    offset = 0
    canonical = discipline
    while True:
        page = reg.get_items(discipline, limit=_PAGE_LIMIT, offset=offset)
        if not isinstance(page, dict) or page.get("found") is not True:
            return None
        canonical = page.get("discipline") or discipline
        chunk = page.get("items") or []
        items.extend(chunk)
        total = int(page.get("total") or 0)
        offset += _PAGE_LIMIT
        if offset >= total or not chunk:
            break
    return items, canonical


def _get_master(discipline: str) -> dict[str, Any]:
    """공종 마스터({discipline, items, sections}) — 레지스트리 우선, 동일 JSON 폴백.

    두 경로 모두 items 를 id 오름차순 정렬해 반환(경로 무관 결정론).
    """
    reg = _registry()
    if reg is not None:
        try:
            got = _items_via_registry(reg, discipline)
            if got is not None:
                items, canonical = got
                sections: list[dict[str, Any]] = []
                sec_res = reg.get_sections(discipline)
                if isinstance(sec_res, dict) and sec_res.get("found") is True:
                    sections = [dict(s) for s in (sec_res.get("sections") or [])]
                return {"discipline": canonical, "items": items, "sections": sections}
        except Exception:  # noqa: BLE001 — 계약 불일치 시 동일 JSON 폴백(아래)
            pass
    master = _load_json(_DISCIPLINE_FILES[discipline])
    items = sorted(master.get("items") or [], key=lambda it: str(it.get("id") or ""))
    return {
        "discipline": discipline,
        "items": items,
        # 사본 반환 — lru_cache 원본 불변(호출자 변조로부터 캐시 보호)
        "sections": [dict(s) for s in (master.get("sections") or [])],
    }


def _get_provenance() -> dict[str, Any]:
    """출처(프로젝트 메타) — 레지스트리 get_provenance() 우선, _meta.json 폴백.

    두 경로 모두 동일 flat 형태({name, gfa_sqm, gfa_basis, sample_count, provenance}).
    """
    reg = _registry()
    if reg is not None:
        fn = getattr(reg, "get_provenance", None)
        if callable(fn):
            try:
                prov = fn()
                if isinstance(prov, dict) and prov:
                    return prov
            except Exception:  # noqa: BLE001
                pass
    project = _load_json("_meta.json").get("project")
    if isinstance(project, dict) and project:
        return dict(project)
    return {  # 출처 부재도 정직 표기(가짜값 금지)
        "name": None,
        "sample_count": None,
        "provenance": "출처 메타 미로드 — data/boq_master/_meta.json 확인 필요",
    }


# ── 결정론 규칙 ──────────────────────────────────────────────────────────────

def round_qty(value: float) -> float:
    """유효숫자 반올림: |v|>=100 → 정수, |v|>=1 → 1자리, 그 외 → 3자리."""
    v = abs(value)
    if v >= 100:
        return float(round(value))
    if v >= 1:
        return round(value, 1)
    return round(value, 3)


def assign_driver(item: dict[str, Any], discipline: str) -> str:
    """항목별 스케일링 드라이버 배정(첫 일치 우선) — 규칙은 모듈 docstring 참조."""
    text = f"{item.get('section_name', '')}{item.get('name', '')}"
    if "세대" in text:  # '단위세대' 역시 '세대' 포함
        return "households"
    if discipline == "조경":
        return "landscape_area"
    qty_sample = float(item.get("qty_sample") or 0.0)
    if item.get("unit") == "식" and qty_sample <= 2:
        return "fixed"
    return "gfa"


def _canonical_disciplines(disciplines: list[str] | None) -> list[str]:
    if disciplines is None:
        return list(_DISCIPLINE_FILES)
    out: list[str] = []
    for d in disciplines:
        canon = _ALIASES.get(str(d).strip().lower(), str(d).strip())
        if canon not in _DISCIPLINE_FILES:
            allowed = ", ".join(list(_DISCIPLINE_FILES) + list(_ALIASES))
            raise ValueError(f"알 수 없는 공종 '{d}' — 허용: {allowed}")
        if canon not in out:
            out.append(canon)
    return out


# ── 메인 API ─────────────────────────────────────────────────────────────────

def generate_draft(
    params: dict[str, Any],
    disciplines: list[str] | None = None,
    sample_stats: dict[Any, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """파라메트릭 공내역서 초안 생성.

    params: {gfa_sqm(필수, ㎡), households=None, site_area_sqm=None,
             landscape_area_sqm=None}
    disciplines: 공종 리스트(한글 캐논명 또는 영문 별칭) — None 이면 5공종 전체.
    sample_stats: N1 옵셔널 — (name,spec,unit)→{n,mean,cv,driver}. 항목 표본이
        n≥REF_MIN_N(3)이면 단일표본 스케일 대신 **표본평균 원단위**를 쓰고 신뢰도를
        "실적 N건 기반·CV xx%"로 전환한다. None 이거나 n<3 이면 현 동작 그대로(n=1).

    scaled_qty = qty_sample × (project_value / ref_value), 유효숫자 반올림.
    단가는 생성하지 않는다(공내역서 = 단가 빈칸). 전기 ref_mat_price 만 원본 전달.
    """
    # N1 일반화 게이트(섣부른 일반화 금지) — sample_stats 제공 시에만 지연 참조(순환 임포트 회피).
    min_n = 3
    if sample_stats:
        try:
            from app.services.cost.boq_sample_stats import REF_MIN_N  # noqa: PLC0415
            min_n = REF_MIN_N
        except Exception:  # noqa: BLE001 — 미배포 시 기본 3
            min_n = 3
    gfa = params.get("gfa_sqm")
    if not isinstance(gfa, (int, float)) or isinstance(gfa, bool) or gfa <= 0:
        raise ValueError("gfa_sqm(연면적, ㎡)은 필수 양수 파라미터입니다")
    gfa = float(gfa)

    households = params.get("households")
    households = (
        float(households)
        if isinstance(households, (int, float)) and not isinstance(households, bool) and households > 0
        else None
    )
    landscape = params.get("landscape_area_sqm")
    landscape = (
        float(landscape)
        if isinstance(landscape, (int, float)) and not isinstance(landscape, bool) and landscape > 0
        else None
    )
    site = params.get("site_area_sqm")
    site = float(site) if isinstance(site, (int, float)) and not isinstance(site, bool) and site > 0 else None

    target = _canonical_disciplines(disciplines)

    # 드라이버 → (ref_value, project_value). fixed 는 스케일링 없음.
    scale_map: dict[str, tuple[float, float]] = {"gfa": (REF_GFA_SQM, gfa)}
    if households is not None:
        scale_map["households"] = (REF_HOUSEHOLDS, households)
    if landscape is not None:
        scale_map["landscape_area"] = (REF_LANDSCAPE_AREA_SQM, landscape)

    warnings: list[str] = []
    hh_fallback_count = 0
    landscape_fallback_count = 0
    disc_out: dict[str, Any] = {}
    total_items = 0

    for disc in target:
        master = _get_master(disc)
        items_out: list[dict[str, Any]] = []
        for it in master.get("items", []):
            driver = assign_driver(it, disc)
            fallback_from: str | None = None
            if driver == "households" and "households" not in scale_map:
                fallback_from, driver = "households", "gfa"
                hh_fallback_count += 1
            elif driver == "landscape_area" and "landscape_area" not in scale_map:
                fallback_from, driver = "landscape_area", "gfa"
                landscape_fallback_count += 1

            sample = float(it.get("qty_sample") or 0.0)
            if driver == "fixed":
                ref_v: float | None = None
                proj_v: float | None = None
                qty = sample  # 횟수성 가설항목 — 수량 유지
            else:
                ref_v, proj_v = scale_map[driver]
                qty = round_qty(sample * (proj_v / ref_v))

            qty_basis: dict[str, Any] = {
                "driver": driver,
                "ref_value": ref_v,
                "project_value": proj_v,
                "sample_qty": sample,
            }
            if fallback_from:
                qty_basis["fallback_from"] = fallback_from

            # 프론트(B5) 표시용 평탄 별칭 — qty_basis와 동일 정보(additive)
            if driver == "fixed":
                basis_str = f"고정(횟수성) — 표본 수량 {sample} 유지"
            else:
                basis_str = (
                    f"표본 {sample} × ({proj_v:,.0f}/{ref_v:,.0f}) — "
                    f"{driver} 비례(의정부424 실적, n=1)"
                )
            if fallback_from:
                basis_str += f" · {fallback_from} 미제공 폴백"

            # ── N1 훅: 동일 항목 표본 n≥min_n 이면 표본평균 원단위로 전환(배지 갱신) ──
            confidence = _CONFIDENCE
            if sample_stats and driver != "fixed":
                st = sample_stats.get((it.get("name"), it.get("spec", ""), it.get("unit")))
                if st and int(st.get("n") or 0) >= min_n:
                    st_driver = st.get("driver") or driver
                    pair = scale_map.get(st_driver)
                    mean_rate = st.get("mean")
                    if pair and isinstance(mean_rate, (int, float)) and not isinstance(mean_rate, bool):
                        proj_v2 = pair[1]
                        qty = round_qty(float(mean_rate) * proj_v2)
                        n_s = int(st["n"])
                        cv_pct = float(st.get("cv") or 0.0) * 100
                        confidence = f"실적 {n_s}건 기반·CV {cv_pct:.0f}%"
                        basis_str = (
                            f"표본평균 원단위 {float(mean_rate):.4g} × {proj_v2:,.0f} "
                            f"(실적 {n_s}건, CV {cv_pct:.0f}%)"
                        )
                        qty_basis = {
                            **qty_basis, "n_samples": n_s,
                            "mean_unit_rate": float(mean_rate),
                            "cv": float(st.get("cv") or 0.0), "project_value": proj_v2,
                        }

            entry: dict[str, Any] = {
                "id": it.get("id"),
                "discipline": disc,
                "section_code": it.get("section_code"),
                "section_name": it.get("section_name"),
                "name": it.get("name"),
                "spec": it.get("spec", ""),
                "unit": it.get("unit"),
                "qty": qty,
                "qty_basis": qty_basis,
                "qty_sample": sample,
                "driver": driver,
                "basis": basis_str,
                "confidence": confidence,
            }
            if "ref_mat_price" in it:  # 전기 참고 재료단가 — 원본 그대로(가공 금지)
                entry["ref_mat_price"] = it["ref_mat_price"]
            items_out.append(entry)

        disc_out[disc] = {
            "items": items_out,
            "item_count": len(items_out),
            "sections": master.get("sections", []),
        }
        total_items += len(items_out)

    if hh_fallback_count:
        warnings.append(
            f"households 미제공 — 세대 기반 항목 {hh_fallback_count}건을 "
            "연면적(gfa) 비례로 폴백(세대수 비례 대비 부정확)"
        )
    if landscape_fallback_count:
        warnings.append(
            "조경면적 미제공 — 연면적 비례는 부정확"
            f"(조경 항목 {landscape_fallback_count}건을 gfa 비례로 폴백)"
        )

    params_used: dict[str, Any] = {
        "gfa_sqm": gfa,
        "households": households,
        "site_area_sqm": site,  # 현재 드라이버 미사용(예약)
        "landscape_area_sqm": landscape,
        "ref": {
            "gfa_sqm": {"value": REF_GFA_SQM, "basis": REF_BASIS["gfa_sqm"]},
            "households": {"value": REF_HOUSEHOLDS, "basis": REF_BASIS["households"]},
            "landscape_area_sqm": {
                "value": REF_LANDSCAPE_AREA_SQM,
                "basis": REF_BASIS["landscape_area_sqm"],
            },
        },
    }

    return {
        "disciplines": disc_out,
        "summary": {
            "total_items": total_items,
            "params_used": params_used,
            "warnings": warnings,
        },
        "provenance": _get_provenance(),
        "badges": {"note": _HONESTY_NOTE, "confidence": _CONFIDENCE},
    }


def build_xlsx(
    draft: dict[str, Any] | None = None,
    *,
    params: dict[str, Any] | None = None,
    disciplines: list[str] | None = None,
) -> bytes:
    """공내역서 xlsx — draft 직접 또는 params로 생성 후 내보내기.

    B3 라우터(boq_auto)는 본 모듈에서 generate_draft·build_xlsx를 함께 찾고
    (params=, disciplines=) 키워드로 호출하므로, 두 호출 형태를 모두 수용해
    boq_excel_export.build_xlsx(실구현)로 위임한다(additive 어댑터).
    """
    from app.services.cost.boq_excel_export import build_xlsx as _export  # noqa: PLC0415

    if draft is None:
        if params is None:
            raise ValueError("draft 또는 params 중 하나는 필요합니다")
        draft = generate_draft(params, disciplines=disciplines)
    return _export(draft)
