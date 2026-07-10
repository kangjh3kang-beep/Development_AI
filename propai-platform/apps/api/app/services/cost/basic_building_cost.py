"""분양가상한제 기본형건축비 고시 — 층수×전용면적 매트릭스(확정구간만 시드) + 개정 감지.

2026-03 정기고시(16~25층·전용 60㎡초과~85㎡이하 지상층 ㎡당 2,220,000원, 직전 2025-09
고시 2,174,000원 대비 +2.12%)만 확정 반영한다(2026-02-27 보도 — 뉴스1·아주경제·게트뉴스 등
복수 언론 교차확인). 그 외 층수·전용면적 구간은 law.go.kr 고시 원문(법제처 행정규칙 본문)을
확보하기 전까지 수치를 발명하지 않고 value=None + "고시 원문 확인 필요"로 정직 표기한다
(★무날조 — 대표 구간 1건만 확정 시드, 나머지는 미확보).

개정 감지(detect_gosi_update)는 gosi_search_service.GosiSearchService(법제처 DRF admrul)로
"분양가상한제 적용주택의 기본형건축비" 최신 고시 발령일자를 조회해 이 모듈의 시드 발령일자와
다르면 변경으로 판단하고 regulation_change_log에 이벤트를 기록한다(기존 계약 재사용).
수치 자동 갱신은 하지 않는다 — 감지만 하고, 실제 시드 갱신은 원문 대조 후 수동으로 반영한다.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_GOSI_QUERY = "분양가상한제 적용주택의 기본형건축비"
# law.go.kr 행정규칙 목록 페이지(정확한 고시번호·회차는 원문 미확보 — 대표 링크로만 사용).
_SOURCE_URL = (
    "https://www.law.go.kr/%ED%96%89%EC%A0%95%EA%B7%9C%EC%B9%99/"
    "%EB%B6%84%EC%96%91%EA%B0%80%EC%83%81%ED%95%9C%EC%A0%9C%20%EC%A0%81%EC%9A%A9%EC%A3%BC%ED%83%9D%EC%9D%98%20"
    "%EA%B8%B0%EB%B3%B8%ED%98%95%EA%B1%B4%EC%B6%95%EB%B9%84%20%EB%B0%8F%20%EA%B0%80%EC%82%B0%EB%B9%84%EC%9A%A9"
)

# ── 확정 시드(대표 구간 1건만) ──
# 수치 출처: 국토교통부 2026-03 정기고시 보도(2026-02-27, 복수 언론 교차확인).
# 고시번호(gosi_no)는 law.go.kr 원문 미확보로 None(정직) — detect_gosi_update가 법제처 DRF로
# 최신 발령정보를 별도 조회한다(이 시드 값을 자동으로 덮어쓰지 않음).
_BASELINE_MATRIX: list[dict[str, Any]] = [
    {
        "floor_band_label": "16~25층",
        "floor_min": 16, "floor_max": 25,
        "unit_area_band_label": "전용 60㎡초과~85㎡이하",
        "unit_area_min": 60.0, "unit_area_max": 85.0,
        "above_ground_won_per_sqm": 2_220_000,
        "prev_above_ground_won_per_sqm": 2_174_000,  # 2025-09 직전 고시
        "change_pct": 2.12,
        "gosi_no": None,  # 고시 원문 미확보(law.go.kr 원문 확인 필요)
        "gosi_date": "2026-03-01",  # 정기고시 시행일(연 2회: 3/1, 9/15) — 언론보도 기준, 원문 대조 요망
        "source_url": _SOURCE_URL,
        "confidence": "verified_press",  # 언론보도 교차확인(원문 미대조)
    },
]


def _match_cell(floors: int, avg_unit_sqm: float) -> dict[str, Any] | None:
    for cell in _BASELINE_MATRIX:
        if (
            cell["floor_min"] <= floors <= cell["floor_max"]
            and cell["unit_area_min"] < avg_unit_sqm <= cell["unit_area_max"]
        ):
            return cell
    return None


def get_baseline(floors: int, avg_unit_sqm: float) -> dict[str, Any]:
    """층수·평균전용면적 → 기본형건축비 지상층 ㎡당 기준선.

    확정 구간(현재 16~25층·전용 60~85㎡)만 값을 반환하고, 그 외 구간은 value=None +
    "고시 원문 확인 필요"로 정직 표기한다(★무날조 — 미확보 수치 발명 금지).

    반환: {value, basis, legal_link, confidence, floor_band, unit_area_band, prev_value?, change_pct?}.
    """
    cell = _match_cell(floors, avg_unit_sqm)
    if not cell:
        return {
            "value": None,
            "basis": f"고시 원문 확인 필요 — {floors}층·전용{avg_unit_sqm:.0f}㎡ 구간 미시드",
            "legal_link": _SOURCE_URL,
            "confidence": "unavailable",
            "floor_band": None, "unit_area_band": None,
        }
    return {
        "value": cell["above_ground_won_per_sqm"],
        "basis": (
            f"국토교통부 기본형건축비 고시({cell['gosi_date']} 시행 추정) "
            f"{cell['floor_band_label']}·{cell['unit_area_band_label']} 지상층 기준"
        ),
        "legal_link": cell["source_url"],
        "confidence": cell["confidence"],
        "floor_band": cell["floor_band_label"], "unit_area_band": cell["unit_area_band_label"],
        "prev_value": cell.get("prev_above_ground_won_per_sqm"),
        "change_pct": cell.get("change_pct"),
    }


_DDL_REGULATION_CHANGE_LOG = (
    "CREATE TABLE IF NOT EXISTS regulation_change_log ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  law_name varchar(200) NOT NULL,"
    "  article_number varchar(100),"
    "  change_type varchar(50) NOT NULL,"
    "  change_summary text,"
    "  impact_analysis jsonb DEFAULT '{}'::jsonb,"
    "  affected_projects jsonb DEFAULT '[]'::jsonb,"
    "  notification_sent boolean DEFAULT false,"
    "  effective_date timestamptz,"
    "  detected_at timestamptz DEFAULT now()"
    ")"
)


async def _record_regulation_change(latest: dict[str, Any], seed_date: str | None) -> None:
    """regulation_change_log 이벤트 기록(기존 계약 재사용 — 감지만, 수치 자동갱신 금지).

    best-effort — 기록 실패해도 detect_gosi_update 결과 자체는 정상 반환(무차단).
    """
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await db.execute(text(_DDL_REGULATION_CHANGE_LOG))
            await db.execute(
                text(
                    "INSERT INTO regulation_change_log"
                    "(law_name, change_type, change_summary, impact_analysis)"
                    " VALUES (:law_name, :change_type, :change_summary, CAST(:impact_analysis AS jsonb))"
                ),
                {
                    "law_name": _GOSI_QUERY,
                    "change_type": "고시개정감지",
                    "change_summary": (
                        f"기본형건축비 고시 변경 감지 — 시드({seed_date}) ≠ 최신({latest.get('date')}). "
                        "수치 자동 갱신 안 함(수동 검증 후 시드 갱신 필요)."
                    ),
                    "impact_analysis": json.dumps(
                        {
                            "latest_name": latest.get("name"), "latest_id": latest.get("id"),
                            "latest_dept": latest.get("dept"), "latest_date": latest.get("date"),
                        },
                        ensure_ascii=False, default=str,
                    ),
                },
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 — 감지 결과는 손상 없이 반환(로그만)
        logger.warning("regulation_change_log 기록 실패(best-effort)", err=str(e)[:150])


async def detect_gosi_update() -> dict[str, Any]:
    """법제처 DRF(admrul)로 최신 기본형건축비 고시 발령일자를 조회해 시드와 다르면 변경 보고.

    감지만 수행 — 수치 자동 갱신은 하지 않는다(원문 대조 후 수동 시드 갱신).
    법제처 키 미설정/조회 실패 시 checked=False로 정직 표기.
    """
    from app.services.legal.gosi_search_service import GosiSearchService

    seed_date = _BASELINE_MATRIX[0]["gosi_date"]
    result = await GosiSearchService().search_admrule(_GOSI_QUERY, max_results=3)
    if not result.get("available"):
        return {
            "checked": False, "reason": result.get("reason", "법제처 API 미가용"),
            "seed_gosi_date": seed_date,
        }
    hits = result.get("results") or []
    if not hits:
        return {"checked": True, "changed": False, "reason": "검색결과 0건", "seed_gosi_date": seed_date}

    latest = hits[0]
    latest_date = latest.get("date")
    changed = bool(latest_date) and str(latest_date).replace("-", "") != str(seed_date).replace("-", "")
    if changed:
        await _record_regulation_change(latest, seed_date)
    return {
        "checked": True, "changed": changed,
        "seed_gosi_date": seed_date, "latest_gosi_date": latest_date,
        "latest_name": latest.get("name"), "latest_dept": latest.get("dept"),
    }
