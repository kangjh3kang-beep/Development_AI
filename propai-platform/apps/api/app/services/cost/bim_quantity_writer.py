"""bim_quantities 공용 쓰기 헬퍼 — PR#315 H1(비멱등 이중적재)·H2(ORM 이중정의) 봉합.

analyze_ifc·generate_ifc_from_design(apps/api/services/bim_ifc_service.py)와
upload_ifc(app/routers/cost.py) — bim_quantities 를 쓰는 3개 경로 전부 이 헬퍼 하나만
경유한다(전역 스윕). 한 곳을 고치면 세 경로가 함께 따라온다.

## H1 — 비멱등 이중적재
기존에는 각 쓰기 경로가 add_all 만 하고 기존 행을 지우지 않아, 같은 프로젝트를 2회 이상
분석/업로드하면 bim_quantities 물량이 배가되고 origin-cost 원가도 정확히 배수로 부풀었다.
이 헬퍼는 INSERT 전에 같은 project_id·extraction_method 조합의 기존 행을 DELETE 하여
"현재 스냅샷으로 교체"하는 의미론을 갖는다 — 몇 번을 호출해도 결과가 같다(멱등).
extraction_method 스코프로만 지우므로, 적산사가 verified=True 로 수기 검증/수정한 행
(다른 extraction_method 값을 쓰거나 이 헬퍼가 건드리지 않는 행)은 자동 재분석에 휩쓸려
삭제되지 않는다.

## H2 — ORM 이중정의(tenant_id 유/무 split-brain)
`database/models/v61_cost.py::BimQuantity`(TenantMixin, tenant_id 有)와
`app/models/v61_cost.py::BimQuantity`(tenant_id 無) 두 클래스가 같은 테이블을 가리켰다.
정본은 전자(TenantMixin)로 확정 — cost_tables_bootstrap 의 물리 스키마에도 nullable
tenant_id 컬럼을 추가해 정합을 맞췄다(PR#315 H2). app/models 쪽은 이 테이블의 쓰기에
더 이상 쓰이지 않는다(해당 파일에 폐기 주석 추가·클래스 자체는 하위호환을 위해 유지).

무목업: DB/부트스트랩 실패 시 여기서 예외를 삼키지 않는다 — 호출측(3개 쓰기 경로)이 각자의
graceful 정책(응답 무영향·경고 로그)으로 처리한다(기존 계약 유지).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


async def replace_bim_quantities(
    db: Any,
    project_id: str | UUID,
    tenant_id: str | UUID | None,
    rows_in: list[dict[str, Any]],
    extraction_method: str = "AI_AUTO",
) -> int:
    """공종매핑된 요소(rows_in)를 project_id 스코프로 교체 영속한다.

    Args:
        db: AsyncSession(호출측이 commit/rollback 트랜잭션 경계를 관리 — 여기서 commit 안 함).
        project_id: 대상 프로젝트(문자열/UUID 모두 허용).
        tenant_id: 소유 테넌트(없으면 None 정직 — 억지로 지어내지 않는다).
        rows_in: 요소 dict 목록. 키는 analyze_ifc(_parse_ifc.elements)와
            upload_ifc(extract_quantities_with_work_codes) 양쪽 출력 형식을 모두 수용
            (element_type/ifc_object_type, global_id/ifc_global_id, name/ifc_object_name).
        extraction_method: 교체 스코프 판별 키(기본 AI_AUTO — 자동 매핑만 교체).

    Returns:
        영속된 행 수. rows_in 이 비어있으면 DB 를 건드리지 않고 0 반환(기존 행 보존 —
        "이번엔 요소가 없었다"가 "기존 물량을 전부 지운다"를 뜻하지 않는다).
    """
    if not rows_in:
        return 0

    from sqlalchemy import text

    from app.services.cost.cost_tables_bootstrap import _ensure_cost_tables
    from apps.api.database.models.v61_cost import BimQuantity

    # bim_quantities(+tenant_id 컬럼) 존재 보장 — 신규 DB 조용한 단절 방지.
    await _ensure_cost_tables(db)

    # H1: 같은 project_id·extraction_method 기존 행을 지우고 재삽입(REPLACE) — 이중적재 방지.
    await db.execute(
        text(
            "DELETE FROM bim_quantities WHERE project_id = :pid AND extraction_method = :method"
        ),
        {"pid": str(project_id), "method": extraction_method},
    )

    rows = [
        BimQuantity(
            tenant_id=tenant_id,
            project_id=project_id,
            ifc_global_id=r.get("ifc_global_id") or r.get("global_id") or None,
            ifc_object_type=r.get("ifc_object_type") or r.get("element_type") or None,
            ifc_object_name=r.get("ifc_object_name") or r.get("name") or None,
            work_code=r.get("work_code") or None,
            floor_level=r.get("floor_level") or None,
            quantity=r.get("quantity", 0) or 0,
            unit=r.get("unit") or None,
            extraction_method=r.get("extraction_method") or extraction_method,
        )
        for r in rows_in
    ]
    db.add_all(rows)
    return len(rows)
