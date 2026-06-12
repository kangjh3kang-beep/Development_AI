"""표준 BOQ(공내역서) 마스터 레지스트리 — 실적 5공종 표준항목 사전 조회.

data/boq_master/{architecture,mechanical,electrical,landscape,civil}.json
(의정부동 424 주상복합 신축공사 실적 공내역서에서 추출한 표준항목 마스터,
3,997 고유항목 · 414 섹션)을 lazy-load + 모듈 캐시로 제공한다.

원칙:
- 순수 결정론(LLM 0) · 읽기 전용 — 동일 입력은 항상 동일 출력(정렬 고정).
- 정직성: 표본 1건(n=1) 실적 기반 — get_provenance() dict를 모든 응답에 동봉.
  공내역서 특성상 단가는 빈칸(전기통신소방만 ref_mat_price 참고가 보유).
- 미존재 discipline/파일은 예외 없이 빈 결과 + reason(정직 표기).
- additive — 기존 적산 자산(boq_builder 등) 무수정 재사용 전제, 본 모듈은 조회 전용.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DATA_DIR = Path(__file__).resolve().parent / "data" / "boq_master"
_META_FILE = "_meta.json"

# 공종(한글 canonical) ↔ 파일명 매핑(내장). 순서 = 응답 고정 순서(결정론).
_DISCIPLINE_FILES: dict[str, str] = {
    "건축": "architecture.json",
    "기계소방": "mechanical.json",
    "전기통신소방": "electrical.json",
    "조경": "landscape.json",
    "토목": "civil.json",
}

# 영문 별칭(파일명 stem) → 한글 canonical (additive 편의 — 한글 키가 표준).
_ALIASES: dict[str, str] = {
    "architecture": "건축",
    "mechanical": "기계소방",
    "electrical": "전기통신소방",
    "landscape": "조경",
    "civil": "토목",
}

# 페이지 크기 상한(방어적 클램프 — 결정론 유지).
_MAX_LIMIT = 500
_DEFAULT_LIMIT = 100

# ── 모듈 캐시(lazy-load: 공종 파일 5개 + _meta 각 1회) ──
_CACHE: dict[str, dict[str, Any] | None] = {}
_META_CACHE: dict[str, Any] | None = None
_META_LOADED = False

_PROVENANCE_UNAVAILABLE: dict[str, Any] = {
    "name": None,
    "gfa_sqm": None,
    "gfa_basis": None,
    "sample_count": 0,
    "provenance": "boq_master/_meta.json 미로드 — 출처 정보 없음(정직 표기)",
}


def clear_cache() -> None:
    """모듈 캐시 초기화(테스트/리로드용) — 동작 결과에는 영향 없음(결정론)."""
    global _META_CACHE, _META_LOADED
    _CACHE.clear()
    _META_CACHE = None
    _META_LOADED = False


def normalize_discipline(discipline: Any) -> str | None:
    """입력 공종명 → 한글 canonical 키. 미등록은 None(예외 없음).

    허용: 한글 canonical('건축' 등), 영문 stem('architecture' 등), 파일명('civil.json').
    """
    if not isinstance(discipline, str):
        return None
    key = discipline.strip()
    if key in _DISCIPLINE_FILES:
        return key
    low = key.lower()
    if low.endswith(".json"):
        low = low[: -len(".json")]
    return _ALIASES.get(low)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("boq_master_load_failed", path=str(path), error=str(exc))
        return None
    return data if isinstance(data, dict) else None


def _load_meta() -> dict[str, Any]:
    """_meta.json lazy-load(모듈 캐시). 실패 시 {} — 예외 금지."""
    global _META_CACHE, _META_LOADED
    if not _META_LOADED:
        _META_CACHE = _load_json(_DATA_DIR / _META_FILE)
        _META_LOADED = True
    return _META_CACHE or {}


def _load_discipline(canonical: str) -> dict[str, Any] | None:
    """공종 마스터 파일 lazy-load(모듈 캐시). 실패 시 None 캐시 — 예외 금지."""
    if canonical not in _CACHE:
        _CACHE[canonical] = _load_json(_DATA_DIR / _DISCIPLINE_FILES[canonical])
    return _CACHE[canonical]


def get_provenance() -> dict[str, Any]:
    """프로젝트 출처 dict — 모든 응답에 항상 동봉(정직성 SSOT).

    의정부동 424 주상복합 · 표본 1건(n=1) · 연면적 238,504㎡ 근거.
    _meta 미로드 시에도 dict 반환(출처 없음을 정직 표기). 항상 사본 반환.
    """
    project = _load_meta().get("project")
    if not isinstance(project, dict) or not project:
        return dict(_PROVENANCE_UNAVAILABLE)
    return copy.deepcopy(project)


def list_disciplines() -> list[dict[str, Any]]:
    """5공종 요약 목록 — _meta 기반(고정 순서 = 결정론).

    각 항목: {discipline, file, sections, unique_items, rows_aggregated, provenance}.
    _meta 미로드 시 빈 리스트(정직 — 가짜값 금지).
    """
    disciplines = _load_meta().get("disciplines")
    if not isinstance(disciplines, dict):
        return []
    provenance = get_provenance()
    rows: list[dict[str, Any]] = []
    for name, default_file in _DISCIPLINE_FILES.items():
        info = disciplines.get(name)
        if not isinstance(info, dict):
            continue
        rows.append(
            {
                "discipline": name,
                "file": info.get("file", default_file),
                "sections": info.get("sections"),
                "unique_items": info.get("unique_items"),
                "rows_aggregated": info.get("rows_aggregated"),
                "provenance": provenance,
            }
        )
    return rows


def _not_found(discipline: Any, reason: str) -> dict[str, Any]:
    return {
        "discipline": discipline,
        "found": False,
        "reason": reason,
        "total": 0,
        "provenance": get_provenance(),
    }


def _unknown_reason(discipline: Any) -> str:
    supported = ", ".join(_DISCIPLINE_FILES)
    return f"미등록 공종 '{discipline}' — 지원 공종: {supported}"


def _build_tree(flat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """섹션 코드 prefix 기반 트리 구성(문서 순서 보존 — 결정론).

    부모 = 앞서 등장한 섹션 중 코드가 가장 긴 proper prefix. 없으면 루트.
    (예: 전기 '01020101' → '01' 전기공사 하위, 조경 'L01' → 루트)
    """
    roots: list[dict[str, Any]] = []
    by_code: dict[str, dict[str, Any]] = {}
    for s in flat:
        node: dict[str, Any] = {**s, "children": []}
        code = str(s.get("code") or "")
        parent: dict[str, Any] | None = None
        for cut in range(len(code) - 1, 0, -1):
            candidate = by_code.get(code[:cut])
            if candidate is not None:
                parent = candidate
                break
        (parent["children"] if parent is not None else roots).append(node)
        if code:
            by_code[code] = node
    return roots


def get_sections(discipline: str) -> dict[str, Any]:
    """공종 섹션 트리(level 포함) — 미존재 공종은 빈 결과 + reason(예외 금지).

    반환: {discipline, found, total, sections(평탄 목록 — code/name/level/item_count),
           tree(코드 prefix 중첩), provenance, reason}.
    """
    canonical = normalize_discipline(discipline)
    if canonical is None:
        return {**_not_found(discipline, _unknown_reason(discipline)), "sections": [], "tree": []}
    data = _load_discipline(canonical)
    if data is None:
        reason = f"마스터 파일 미로드: {_DISCIPLINE_FILES[canonical]}"
        return {**_not_found(canonical, reason), "sections": [], "tree": []}

    items = data.get("items") or []
    counts: dict[str, int] = {}
    for it in items:
        sc = it.get("section_code")
        if sc:
            counts[sc] = counts.get(sc, 0) + 1

    flat = [
        {
            "code": s.get("code"),
            "name": s.get("name"),
            "level": s.get("level"),
            "item_count": counts.get(s.get("code"), 0),
        }
        for s in data.get("sections") or []
    ]
    return {
        "discipline": canonical,
        "found": True,
        "reason": None,
        "total": len(flat),
        "sections": flat,
        "tree": _build_tree(flat),
        "provenance": get_provenance(),
    }


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_items(
    discipline: str,
    section_code: str | None = None,
    query: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """공종 표준항목 조회(섹션 필터 + name/spec 부분일치 검색 + 페이지네이션).

    - 정렬: item id 오름차순 고정(결정론). query는 casefold 부분일치(name/spec).
    - total = 필터 적용 후 전체 건수(페이지와 무관). items 는 사본(캐시 불변).
    - 미존재 공종은 {total:0, items:[], found:False, reason}(예외 금지).
    """
    limit = max(0, min(_safe_int(limit, _DEFAULT_LIMIT), _MAX_LIMIT))
    offset = max(0, _safe_int(offset, 0))
    base = {"section_code": section_code, "query": query, "limit": limit, "offset": offset}

    canonical = normalize_discipline(discipline)
    if canonical is None:
        return {**_not_found(discipline, _unknown_reason(discipline)), **base, "items": []}
    data = _load_discipline(canonical)
    if data is None:
        reason = f"마스터 파일 미로드: {_DISCIPLINE_FILES[canonical]}"
        return {**_not_found(canonical, reason), **base, "items": []}

    items: list[dict[str, Any]] = list(data.get("items") or [])
    if section_code is not None and str(section_code).strip():
        sc = str(section_code).strip()
        items = [it for it in items if it.get("section_code") == sc]
    if query is not None and str(query).strip():
        q = str(query).strip().casefold()
        items = [
            it
            for it in items
            if q in str(it.get("name") or "").casefold()
            or q in str(it.get("spec") or "").casefold()
        ]

    items.sort(key=lambda it: str(it.get("id") or ""))  # 결정론 정렬
    total = len(items)
    page = copy.deepcopy(items[offset : offset + limit])
    return {
        "discipline": canonical,
        "found": True,
        "reason": None,
        **base,
        "total": total,
        "items": page,
        "provenance": get_provenance(),
    }
