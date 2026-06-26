"""mass_templates 영속·조회 — 수집된 종류별 매스 템플릿을 표준 테이블에 저장/조회.

mass_backbone 데이터 레이어 D1.5(영속). collect_templates 결과를 region(+zone) 스냅샷으로 교체 저장하고,
BuildableMassPreview·유사건축물 추천(D2)이 lookup_templates로 실측 median을 직접 소비한다.

★멱등 교체(replace): region(+source[, zone]) 기존 행 DELETE 후 INSERT — 재수집 시 중복 누적 방지
  (mass_templates엔 UNIQUE 제약이 없어 'delete-then-insert'로 스냅샷 정합 보장 — g2b rebuild_award_stats 선례).
★무목업: lookup 무자료 시 빈 목록(가짜 생성 금지). text() SQL은 schema_guard DDL과 동일 스타일 유지.
⚠️ 라이브 DB 쓰기 검증은 배포 단계(deploy-pending) — 본 모듈은 순수 SQL/파라미터 구성까지 단위검증.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.mass_backbone.schema_guard import ensure_mass_schema

logger = logging.getLogger(__name__)

_INSERT = text(
    "INSERT INTO mass_templates "
    "(region, zone_code, building_type, sample_count, median_bcr_pct, median_far_pct, "
    " median_floors, median_total_area_sqm, source, metadata) VALUES "
    "(:region, :zone_code, :building_type, :sample_count, :median_bcr_pct, :median_far_pct, "
    " :median_floors, :median_total_area_sqm, :source, CAST(:metadata AS jsonb))"
)


def template_to_params(t: dict[str, Any]) -> dict[str, Any]:
    """집계 템플릿 dict → INSERT 바운드 파라미터(결정론·metadata는 JSON 직렬화).

    median_* 결측(None)은 그대로 NULL로 저장(가짜 0 금지). sample_count는 정수 강제.
    """
    return {
        "region": t["region"],
        "zone_code": t.get("zone_code"),
        "building_type": t["building_type"],
        "sample_count": int(t.get("sample_count") or 0),
        "median_bcr_pct": t.get("median_bcr_pct"),
        "median_far_pct": t.get("median_far_pct"),
        "median_floors": t.get("median_floors"),
        "median_total_area_sqm": t.get("median_total_area_sqm"),
        "source": t.get("source") or "building_registry",
        "metadata": json.dumps(t.get("metadata") or {}, ensure_ascii=False),
    }


async def replace_templates(
    db: AsyncSession,
    templates: list[dict[str, Any]],
    *,
    region: str,
    source: str = "building_registry",
    zone_code: str | None = None,
) -> int:
    """region(+source[, zone]) 스냅샷 교체 저장: 기존 행 DELETE 후 새 템플릿 INSERT(멱등). 저장 건수 반환.

    ★zone_code=None이면 (region, source) 전체 스냅샷 교체, 값 지정 시 해당 zone만 부분 교체.
      caller가 zone별로 수집했다면 반드시 동일 zone_code를 넘겨 다른 zone 데이터를 지우지 않게 한다.
    ★footgun 가드: zone 지정 시 templates에 다른 zone 행이 섞였으면 즉시 ValueError(타 zone 삭제 사고 차단).
    """
    # zone 지정 부분교체인데 다른 zone 템플릿이 섞이면, 그 zone DELETE는 안 하면서 잘못된 위치에 저장돼
    # 데이터 정합이 깨진다 → DDL/DELETE 이전에 조기 실패(zone_code=None 템플릿은 허용=zone 미상).
    if zone_code is not None:
        mismatched = sorted({
            str(t.get("zone_code")) for t in templates if t.get("zone_code") not in (None, zone_code)
        })
        if mismatched:
            raise ValueError(
                f"replace_templates: zone_code={zone_code!r} 인데 다른 zone 템플릿 포함 {mismatched} "
                "— 동일 zone만 넘기세요(부분 교체가 타 zone 데이터를 삭제/오염할 위험)"
            )
    await ensure_mass_schema(db)  # 테이블 멱등 보장(첫 저장 시 생성)
    if zone_code is None:
        del_sql = text("DELETE FROM mass_templates WHERE region = :region AND source = :source")
        del_params: dict[str, Any] = {"region": region, "source": source}
    else:
        del_sql = text(
            "DELETE FROM mass_templates WHERE region = :region AND source = :source AND zone_code = :zone_code"
        )
        del_params = {"region": region, "source": source, "zone_code": zone_code}
    # DELETE+INSERT는 한 트랜잭션 — 중간 실패 시 rollback해 세션을 깨끗이(공용 세션 연쇄 실패 방지).
    try:
        await db.execute(del_sql, del_params)
        for t in templates:
            await db.execute(_INSERT, template_to_params(t))
        await db.commit()
        return len(templates)
    except Exception:  # noqa: BLE001 — 호출자에게 전파하되 세션은 정리
        with contextlib.suppress(Exception):
            await db.rollback()
        raise


async def lookup_templates(
    db: AsyncSession,
    *,
    region: str,
    building_type: str | None = None,
    zone_code: str | None = None,
) -> list[dict[str, Any]]:
    """저장된 매스 템플릿 조회(region 필수·종류/zone 선택). 표본수 내림차순·종류명 사전순(결정론).

    반환 = dict 목록(BuildableMassPreview·추천이 median_* 직접 소비). 무자료/오류 시 빈 목록(가짜 생성 금지).
    """
    clauses = ["region = :region"]
    params: dict[str, Any] = {"region": region}
    if building_type:
        clauses.append("building_type = :building_type")
        params["building_type"] = building_type
    if zone_code:
        clauses.append("zone_code = :zone_code")
        params["zone_code"] = zone_code
    sql = text(
        "SELECT region, zone_code, building_type, sample_count, median_bcr_pct, median_far_pct, "
        "median_floors, median_total_area_sqm, source, metadata FROM mass_templates "
        "WHERE " + " AND ".join(clauses) + " ORDER BY sample_count DESC, building_type ASC"
    )
    try:
        result = await db.execute(sql, params)
        return [dict(row) for row in result.mappings().all()]
    except Exception as e:  # noqa: BLE001 — 테이블 부재/오류는 빈 결과(가짜 생성 금지)
        logger.warning("매스 템플릿 조회 실패: %s", str(e)[:120])
        with contextlib.suppress(Exception):
            await db.rollback()
        return []
