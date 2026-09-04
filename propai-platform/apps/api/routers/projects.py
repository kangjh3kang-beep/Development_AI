"""프로젝트 라우터.

CRUD + 상태 전환 + 소프트 삭제.
"""

from datetime import UTC, datetime  # noqa: F401 (UTC는 하위호환 re-export)
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from packages.schemas.enums import ProjectStatus
from packages.schemas.models import (
    PaginatedResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectStatusUpdateRequest,
    ProjectUpdateRequest,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.auth.rbac import RequirePermission  # noqa: F401 (다른 자원에서 사용 가능)
from apps.api.database.models.project import Project
from apps.api.database.session import get_db
from apps.api.metrics import PROJECT_CREATED
from apps.api.services.audit_service import record_audit

# UTC 하위호환 re-export(기존 `from ...projects import UTC` 호출자 보호) — import 블록 뒤로 이동.
UTC = UTC

router = APIRouter()

# 멱등 저장소의 엔드포인트 네임스페이스 — 키 공간을 다른 엔드포인트와 섞지 않는다.
_EP_CREATE_PROJECT = "POST /projects"


def create_request_fingerprint(body: ProjectCreateRequest) -> dict[str, str]:
    """생성 요청의 **논리 지문** — 같은 프로젝트의 재전송이면 같아야 한다.

    ★왜 주소만 보는가(순수 함수로 꺼내 둔 이유):
      전체 본문을 지문에 넣으면, **나중에 도착한 면적이 실린 재전송**이 "다른 요청"으로 판정돼
      422 가 된다. 그 재전송은 실재한다 — `syncFromBackend` 의 고아 마이그레이션은 로컬 레코드의
      `area` 문자열에서 면적을 만들고, 최초 생성은 `effectiveLandAreaSqm` 을 쓴다(값이 갈린다).
      같은 프로젝트를 다시 보낸 것인데 거부하면, 그 레코드는 **영원히 서버에 도달하지 못한다.**

      이름도 보지 않는다 — 고아 마이그레이션은 `name || address` 로 이름을 만들기 때문에
      최초 생성의 이름과 갈릴 수 있다.

      키 오사용 방어는 남는다: **키가 클라이언트 생성 고유 id** 라, 같은 키에 다른 주소가 오면
      그것은 진짜로 다른 프로젝트다.

    ★이 판단을 함수로 꺼낸 이유: 핸들러 안 한 줄로 두면 어떤 테스트도 이것을 직접 태우지 못한다.
    """
    return {"address": body.address or ""}


def is_idempotency_conflict(look) -> bool:
    """같은 키인데 다른 요청인가 — 422 로 거부할 상황."""
    return look.state == idempotency.STATE_CONFLICT


def resolve_idempotent_replay(look):
    """★재생 **판단** — 저장된 응답이 있으면 그것을 돌려주고(재실행 0), 없으면 `None`(정상 실행).

    왜 함수로 꺼내는가: 이 판단을 핸들러 안 `if` 두 줄로 두었더니 **변이가 살아남았다** —
    `if replay is not None:` 을 `if False:` 로 바꿔도 테스트가 전부 초록이었다(소스 검사가
    `.to_response()` 라는 **문자열만** 봤기 때문). 중복 생성을 막는 바로 그 분기가 무잠금이었다.

    본문이 없는 저장(대형이라 미저장)은 `None` 을 돌려 **정상 실행으로 떨어뜨린다** —
    빈 응답을 재생하면 클라이언트가 프로젝트 id 를 못 받는다.
    """
    if look.state != idempotency.STATE_REPLAY or look.stored is None:
        return None
    return look.stored.to_response()

# 유효한 상태 전환 맵
_VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["planning", "archived"],
    "planning": ["design", "archived"],
    "design": ["permit", "archived"],
    "permit": ["construction", "archived"],
    "construction": ["completed", "archived"],
    "completed": ["archived"],
    "archived": [],
}


def _to_response(project: Project, *, include_snapshot: bool = False) -> ProjectResponse:
    """Project ORM 인스턴스를 ProjectResponse로 변환한다.

    include_snapshot=True일 때만 analysis_snapshot을 포함한다(상세/수정 응답).
    목록 응답은 페이로드 절약 위해 제외(None 유지).
    """
    return ProjectResponse(
        id=project.id,
        tenant_id=project.tenant_id,
        name=project.name,
        status=ProjectStatus(project.status),
        address=project.address,
        latitude=project.latitude,
        longitude=project.longitude,
        total_area_sqm=project.total_area_sqm,
        building_type=getattr(project, "building_type", None) or "공동주택",
        created_at=project.created_at,
        updated_at=project.updated_at,
        analysis_snapshot=(
            getattr(project, "analysis_snapshot", None) if include_snapshot else None
        ),
    )


async def _get_project_or_404(
    project_id: UUID, tenant_id: UUID, db: AsyncSession,
) -> Project:
    """프로젝트를 조회하고, 없으면 404를 반환한다."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.tenant_id == tenant_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다",
        )
    return project


@router.get("/{project_id}/operations/status")
async def get_operations_status(project_id: UUID) -> dict:
    """프로젝트 운영 현황 — **수집원이 아직 없다는 사실을 정직하게 알린다.**

    ★2026-08-16 — 종전 구현은 `project_id` 를 **에코만 하고 DB 조회 0** 인 채
      입주율 92.5·유지보수 87·에너지 "1+"·만족도 4.2·IoT 센서 45/48 을 **리터럴로** 돌려줬다.
      `current_user`·`db` 의존성조차 없었다.

    ★대조 실험(프로덕션 실측): 성격이 전혀 다른 두 프로젝트가 **바이트 단위로 같은 값**을 냈다.
        458d7c86…(역삼동 736 · 강남 상업지)   → 입주율 92.5 · 센서 45/48
        49b59c62…(산 1-1 외 1필지 · 147,074㎡ 임야) → 입주율 92.5 · 센서 45/48
      개발되지 않은 임야에 "입주율 92.5%" 와 "IoT 센서 45개 온라인" 이 붙는다.

    ★그런데 이 화면은 **지금 뜨지 않는다**(프론트가 `kpis` 를 배열로 가정 →
      `TypeError: kpis.map is not a function`). 즉 **고장이 거짓말을 가리고 있었다** —
      크래시만 고치면 그때부터 거짓 지표가 사용자에게 보인다. 그래서 **함께** 고친다.

    센서·입주·만족도의 **수집원이 아직 연동되지 않았다**. 없는 것을 지어내지 않고
    `available=False` + 사유로 알린다. 배열 3종은 프론트 계약에 맞춘 **빈 배열**이다
    (형태 불일치로 인한 크래시를 구조적으로 없앤다).
    """
    return {
        "project_id": str(project_id),
        "available": False,
        "reason": "운영 지표(입주·유지보수·센서) 수집원이 아직 연동되지 않았습니다",
        "kpis": [],
        "maintenance": [],
        "sensors": [],
    }


@router.get("", response_model=PaginatedResponse)
async def list_projects(
    page: int = 1,
    page_size: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """프로젝트 목록을 조회한다."""
    offset = (page - 1) * page_size
    base_where = (
        Project.tenant_id == current_user.tenant_id,
        Project.is_deleted == False,  # noqa: E712
    )
    total = (
        await db.execute(
            select(func.count()).select_from(Project).where(*base_where)
        )
    ).scalar_one()

    query = (
        select(Project)
        .where(*base_where)
        .offset(offset)
        .limit(page_size)
        .order_by(Project.created_at.desc())
    )
    result = await db.execute(query)
    projects = list(result.scalars().all())

    has_next = offset + len(projects) < total

    items = [_to_response(p).model_dump() for p in projects]
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, has_next=has_next
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """프로젝트를 생성한다 — `Idempotency-Key` 로 재전송 안전.

    ## 왜 필요한가(실물)

    프로덕션에 이름·주소·필지집합이 **완전히 같은 중복 프로젝트가 2쌍** 있다. 그리고 클라이언트에는
    같은 프로젝트를 두 번 POST 할 수 있는 경로가 실측으로 둘 있었다:

    - `#815` — 생성 `await` 창에 동기화가 끼어들어 "고아"로 오판(같은 탭 안에서만 막았다)
    - `#822` — 목록이 20건에서 잘려 **이미 있는 프로젝트를 "백엔드에 없다"고 오판**

    둘 다 **클라이언트 쪽 처방**이라 다른 탭·다른 기기·재설치에는 닿지 않는다.
    서버가 같은 키를 기억하면 그 경로가 **전부** 닫힌다.

    ## 계약

    같은 `(테넌트·엔드포인트·키)` + 같은 요청지문이면 **처음 응답을 그대로 재생**한다(재실행 0).
    같은 키인데 지문이 다르면 422(키 오사용). 키가 없으면 종전과 **완전히 동일**하게 동작한다.

    ★요청지문은 **주소만** 본다. 전체 본문을 지문에 넣으면, 나중에 도착한 면적이 실린
      재전송(`syncFromBackend` 의 고아 마이그레이션)이 **다른 요청**으로 판정돼 422 가 된다 —
      같은 프로젝트를 재전송한 것인데 거부하게 된다. 그 경로는 실제로 본문이 다르다(실측:
      최초 생성은 `effectiveLandAreaSqm`, 재전송은 로컬 레코드의 `area` 문자열).
    """
    tenant_id = str(current_user.tenant_id) if current_user.tenant_id else None
    key = idempotency.normalize_key(idempotency_key)
    request_hash = idempotency.compute_request_hash(create_request_fingerprint(body))

    if key:
        look = await idempotency.lookup(
            db=db,
            key=key,
            tenant_id=tenant_id,
            endpoint=_EP_CREATE_PROJECT,
            request_hash=request_hash,
        )
        if is_idempotency_conflict(look):
            raise HTTPException(
                status_code=422,
                detail="같은 Idempotency-Key 가 다른 요청에 재사용되었습니다.",
            )
        replay = resolve_idempotent_replay(look)
        if replay is not None:
            return replay  # 처음 응답 그대로 재생 — 두 번째 프로젝트를 만들지 않는다

    project = Project(
        tenant_id=current_user.tenant_id,
        name=body.name,
        address=body.address,
        latitude=body.latitude,
        longitude=body.longitude,
        total_area_sqm=body.total_area_sqm,
    )
    db.add(project)
    await db.flush()

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="create",
        actor_id=current_user.user_id,
        after_state={"name": project.name, "status": project.status},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(project)
    PROJECT_CREATED.inc()

    response = _to_response(project)
    if key:
        # 성공 응답을 키로 기억한다 — 다음 재전송이 이 바이트를 그대로 재생한다.
        # ★실패는 저장하지 않는다: 실패한 생성은 **다시 시도돼야** 한다.
        await idempotency.save(
            db=db,
            key=key,
            tenant_id=tenant_id,
            endpoint=_EP_CREATE_PROJECT,
            request_hash=request_hash,
            response_status=status.HTTP_201_CREATED,
            body=response.model_dump_json().encode("utf-8"),
            media_type="application/json",
            run_id=str(project.id),
        )
    return response


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트 상세 정보를 조회한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)
    return _to_response(project, include_snapshot=True)


class DecisionBriefRequest(BaseModel):
    """Stage1 통합 의사결정 브리프 요청.

    address/parcels 미지정 시 프로젝트에 저장된 주소·필지를 사용한다(SSOT 일관).
    use_llm 기본 false(무과금·무LLM). force_refresh로만 캐시 무시 재분석.
    """

    address: str | None = Field(default=None, description="대표 분석 주소(미지정 시 프로젝트 주소 사용)")
    parcels: list[str] | None = Field(default=None, description="다필지 주소 목록(미지정 시 프로젝트 필지 사용)")
    # ★다필지 통합면적 종단배선: 프론트(effectiveLandAreaSqm SSOT)가 보낸 유효면적을 수용해
    #   부지 part의 대지면적·계획 GFA 메트릭을 이 면적 기준으로 재계산한다(통합면적이 KPI에 실반영).
    #   미전송(None)이면 공유 엔진(ComprehensiveAnalysisService)이 산출한 대표면적을 그대로 쓴다(무회귀).
    # ★보안 상한 검증(gt=0, le=1e7): 면적은 양수여야 하고(0/음수=가짜면적 차단), 1천만㎡(=10㎢,
    #   대규모 신도시 단위)를 절대 상한으로 둔다. 악의/버그 입력(예 999999999㎡)이 검증 없이
    #   권위 KPI(대지면적·GFA·사업성)로 흘러드는 것을 422로 차단한다(무검증 override 방지).
    land_area_sqm: float | None = Field(
        default=None,
        gt=0,
        le=1e7,
        description=(
            "유효 대지면적(㎡) — 다필지 통합면적 우선(미지정 시 엔진 산출 대표면적). "
            "양수·1e7㎡ 이하만 허용(가짜/과대 면적 차단)."
        ),
    )
    equity_won: int | None = Field(default=None, description="자기자본(원) — Go/No-Go ROE 경로")
    use_llm: bool = Field(default=False, description="LLM 내러티브 포함 여부(기본 false=무과금)")
    force_refresh: bool = Field(default=False, description="True면 캐시 무시 재분석(기본 false=캐시 재사용)")


@router.post("/{project_id}/decision-brief", summary="Stage1 통합 의사결정 브리프")
async def build_decision_brief(
    project_id: UUID,
    body: DecisionBriefRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """주소 1회 입력으로 부지·시장·법규·인허가/Top3를 모아 단일 종합판정(GO/CONDITIONAL/HOLD)을 낸다.

    기존 엔진(ComprehensiveAnalysisService·RegulationAnalysisService·FeasibilityServiceV2·
    디벨로퍼 페르소나 Go/No-Go)을 병렬 조립하는 오케스트레이션이다(신규 분석엔진 없음).
    프로젝트는 테넌트 격리(_get_project_or_404)로 조회하고, 주소/필지 미지정 시 프로젝트 SSOT를 쓴다.
    """
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)
    return await _build_decision_brief(project, project_id, body, current_user, db)


def _resolve_brief_inputs(
    project: Project, body: "DecisionBriefRequest",
) -> tuple[str | None, list[str] | None]:
    """주소·필지 SSOT 해석 — 요청이 비면 프로젝트 저장값으로 채운다(일관·무목업).

    JSON 브리프 엔드포인트와 PDF 엔드포인트가 동일 입력을 쓰도록 공용화(드리프트 방지).
    """
    address = body.address or project.address
    parcels = body.parcels
    if not parcels:
        try:
            parcels = [p.address for p in (project.parcels or []) if getattr(p, "address", None)]
        except Exception:  # noqa: BLE001 — 필지 관계 로딩 실패는 단일주소로 진행
            parcels = None
    return address, parcels or None


async def _build_decision_brief(
    project: Project,
    project_id: UUID,
    body: "DecisionBriefRequest",
    current_user: CurrentUser,
    db: AsyncSession,
) -> dict:
    """통합 의사결정 브리프 dict 산출 — JSON·PDF 엔드포인트 공용(과금 게이트 포함).

    과금 게이트(MED) — use_llm=True면 다중 LLM 경로(부지/시장·법규·인허가 인터프리터)를
    트리거하므로 personas.py 패턴(enforce_llm_quota)을 재사용해 한도 초과 시 402 차단한다.
    use_llm=False(기본)는 무LLM·무과금이라 게이트를 건너뛴다.
    """
    if body.use_llm:
        from app.core.billing_deps import enforce_llm_quota
        await enforce_llm_quota(db)

    address, parcels = _resolve_brief_inputs(project, body)

    from app.services.land_intelligence.decision_brief_service import DecisionBriefService

    return await DecisionBriefService().build(
        address=address,
        project_id=str(project_id),
        parcels=parcels,
        tenant_id=str(current_user.tenant_id),
        # 프론트가 보낸 유효면적(다필지 통합면적 우선)을 종단까지 전달 — 부지 KPI 재계산용.
        land_area_sqm=body.land_area_sqm,
        equity_won=body.equity_won,
        use_llm=body.use_llm,
        force_refresh=body.force_refresh,
        db=db,
    )


@router.post("/{project_id}/decision-brief/pdf", summary="Stage1 통합 의사결정 브리프 PDF")
async def build_decision_brief_pdf(
    project_id: UUID,
    body: DecisionBriefRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """통합 의사결정 브리프를 산출(build)해 PDF(application/pdf)로 스트리밍 다운로드한다.

    JSON 엔드포인트(/decision-brief)와 동일한 build()·입력 SSOT·과금 게이트·테넌트 격리를 쓰고,
    결과 dict 만 decision_brief_pdf.to_pdf 로 렌더한다(persona PDF 패턴 재사용·신규 엔진 없음).
    """
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)
    brief = await _build_decision_brief(project, project_id, body, current_user, db)

    from app.services.land_intelligence import decision_brief_pdf

    pdf = decision_brief_pdf.to_pdf(brief)
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="decision_brief_{project_id}.pdf"'},
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: ProjectUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트를 수정한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    before = {"name": project.name, "address": project.address}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    # 감사 로그 after_state에는 분석 스냅샷 blob(대용량)을 싣지 않고 변경 여부만 기록.
    audit_after = {k: v for k, v in update_data.items() if k != "analysis_snapshot"}
    if "analysis_snapshot" in update_data:
        audit_after["analysis_snapshot_updated"] = True

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="update",
        actor_id=current_user.user_id,
        before_state=before,
        after_state=audit_after,
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(project)
    return _to_response(project, include_snapshot=True)


@router.patch("/{project_id}/status", response_model=ProjectResponse)
async def update_project_status(
    project_id: UUID,
    body: ProjectStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트 상태를 전환한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    current_status = project.status
    new_status = body.status.value

    allowed = _VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{current_status}'에서 '{new_status}'로의 상태 전환은 허용되지 않습니다",
        )

    project.status = new_status

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="status_change",
        actor_id=current_user.user_id,
        before_state={"status": current_status},
        after_state={"status": new_status},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """프로젝트를 소프트 삭제한다(테넌트 스코프 — 본인 테넌트 프로젝트만)."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    project.is_deleted = True
    project.deleted_at = datetime.now(UTC)

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="delete",
        actor_id=current_user.user_id,
        before_state={"name": project.name, "status": project.status},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
