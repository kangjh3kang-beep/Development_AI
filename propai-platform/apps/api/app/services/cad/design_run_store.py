"""design_run_store — 설계 실행(design_run)을 DB에 영속화하는 얇은 저장소(WP-E · P10).

이 파일이 푸는 문제(쉬운 설명):
- 지금까지 설계 매스 산출 결과는 design_run_cache(프로세스 메모리 LRU)에만 남았다 — 배포하면
  사라지는 '휘발' 캐시라, "어떤 입력으로 이 설계를 만들었나(재현·출처추적)"를 나중에 확인할 수 없다.
- 그래서 설계 실행의 정체(입력해시·기하해시·seed·컴파일러버전·지표)와 승인차원 상태(DRAFT/APPROVED)를
  DB `design_runs` 테이블에 '영속'으로 승격한다 → 배포 후에도 남아 재현·감사·승인 흐름이 가능하다.

★provenance 앵커 통일(PR#290 리뷰 MEDIUM 봉합) ───────────────────────────────
같은 설계인데 소비 표면마다 design_input_hash가 3벌로 갈렸다(실측):
  A) save_drawing 스탬프 = bare 4스칼라 매스 해시
  B) glb/generate = enriched 매스(코어·복도·게이트 등 부착) 해시
  C) generate 캐시열쇠 = resolved 계약(req 필드) 해시
→ 이들을 하나로 묶는 '정본 앵커(canonical anchor)'를 정의한다: **사용자가 실제로 부여한 최소
  기하(폭·깊이·층수·층고)를 정규화한 입력**. 세 표면 모두 이 4개 기하를 공유하므로, 이 앵커의
  input_hash는 표면과 무관하게 동일하다(같은 건물 = 같은 input_hash). 표면별 고유 해시는 버리지
  않고 surface_hashes(jsonb)에 '별도 필드'로 보존한다(발산은 통일하되 표면 정체는 추적 가능).
  근거: 앵커를 enriched 매스로 잡으면 부착물(캐시상태·게이트)이 해시를 흔들어 재현이 깨지고,
  resolved 계약으로 잡으면 zone/use 등 비-기하 입력이 섞여 '같은 기하 다른 해시'가 된다. bare
  기하가 세 표면의 유일한 교집합이자 '기하 정체'의 최소 SSOT다.

★영속 스키마 계약(WP-G site_basis_service 선례 재사용 — 절대 제약)
- alembic 신규 헤드 없음. CREATE TABLE IF NOT EXISTS(멱등·lazy·부팅안전)로만 생성한다.
- 승인차원 status(DRAFT/APPROVED)만 이 테이블이 소유한다. 실행상태(job QUEUED/RUNNING 등)는
  '다른 차원'이라 혼용 금지 — job_status 컬럼은 WP-L 몫으로 예약만 하고 이 WP에서는 미사용.
- 원장(analysis_ledger)은 이 파일에서 단 한 줄도 건드리지 않는다(append-only 무접촉).

★테넌트 격리(WP-G IDOR 교훈 — 심층방어 2중화)
  ①run_id 해시 입력에 tenant_id를 편입(테넌트별로 run_id 분할).
  ②조회·승인 쿼리는 항상 `tenant_id IS NOT DISTINCT FROM :tid`로 스코프(교차테넌트 접근 차단).

★결정성: 앵커·input_hash·geometry_hash·run_id 모두 입력에서 파생한다(uuid4/now/random 0).
  created_at 등 DB 시각만 DB 함수(now())로 채운다.

신규 의존성 0: json은 표준 라이브러리, provenance 헬퍼는 기존 ⑦ 재사용.
"""
from __future__ import annotations

import contextlib
import json
from typing import Any

import structlog

from app.services.cad.provenance import (
    ENGINE_SOURCE_VERSION,
    compute_geometry_hash,
    compute_input_hash,
    normalize_fingerprint,
)

logger = structlog.get_logger(__name__)

# ── 승인차원 상태(이 테이블이 소유) — 실행상태(job)와 다른 차원 ──
STATUS_DRAFT = "DRAFT"
STATUS_APPROVED = "APPROVED"
_VALID_STATUSES = (STATUS_DRAFT, STATUS_APPROVED)

# run_id 접두 — design_run 계열 식별자.
_RUN_ID_PREFIX = "dr_"
_RUN_ID_HASH_LEN = 16


# ══════════════════════════════════════════════════════════════════════════
# 순수 헬퍼 — 앵커 통일·해시·run_id·상태전이(DB 불요·결정적·단위테스트 대상)
# ══════════════════════════════════════════════════════════════════════════

def _num(value: Any) -> float | None:
    """숫자 후보를 float로 정규화(0/음수는 그대로 보존 — 0-falsy 금지). 변환 불가·None은 None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_design_anchor(
    *,
    building_width_m: Any,
    building_depth_m: Any,
    num_floors: Any,
    floor_height_m: Any,
) -> dict[str, Any]:
    """정본 앵커 — 사용자 최소 기하(폭·깊이·층수·층고)만 담은 결정적 dict(표면 통일의 SSOT).

    ★부착물(compliance·special_parcel·_cache_hit 등)·비-기하 입력(zone/use)은 절대 넣지 않는다 —
      그것들이 섞이면 표면마다 해시가 갈려 재현이 깨진다(앵커 발산의 근본원인). 숫자는 compute_input_hash가
      다시 정규화하지만, 여기서도 float로 통일해 int/float 혼입에 둔감하게 만든다.
    """
    nf = _num(num_floors)
    return {
        "building_width_m": _num(building_width_m),
        "building_depth_m": _num(building_depth_m),
        # 층수는 정수 정체가 자연스러우나(30층 vs 30.0층 동일), None 보존을 위해 조건 분기.
        "num_floors": int(nf) if nf is not None else None,
        "floor_height_m": _num(floor_height_m),
    }


def anchor_from_mass(mass: dict[str, Any]) -> dict[str, Any]:
    """매스/요청 dict에서 정본 앵커를 추출한다 — num_floors/floor_count 키 관용(둘 다 지원).

    왜 관용인가: 매스 SSOT는 'num_floors', BimGenerateRequest는 'floor_count'로 같은 값을 부른다
    (zone/zone_type 관용 교훈과 동형). 두 표면이 같은 앵커를 내도록 두 키를 모두 받아준다.
    """
    nf = mass.get("num_floors")
    if nf is None:
        nf = mass.get("floor_count")
    return canonical_design_anchor(
        building_width_m=mass.get("building_width_m"),
        building_depth_m=mass.get("building_depth_m"),
        num_floors=nf,
        floor_height_m=mass.get("floor_height_m"),
    )


def compute_anchor_input_hash(anchor: dict[str, Any]) -> str:
    """정본 앵커 → 통일 input_hash(⑦ compute_input_hash 재사용 — 표면 무관 동일 계약)."""
    return compute_input_hash(anchor)


def compute_anchor_geometry_hash(anchor: dict[str, Any]) -> str:
    """정본 앵커 → 파생 기하해시(높이·바닥면적 포함). input_hash와 1:1 결정적 대응.

    geometry_hash는 '앵커(폭·깊이·층수·층고)에서 결정적으로 파생한 박스 치수의 지문'이다.
    앵커에서 파생되므로 "동일 seed+input_hash → 동일 geometry_hash" 재현 게이트가 구조적으로 성립한다.

    ★주의(리뷰 권고①): geometry_hash는 이 최소 박스 치수의 지문일 뿐, '실제로 렌더링되는 enriched
      기하의 정체'가 아니다 — 코어·복도·창호·게이트 등 부착물이 반영된 산출 기하는 여기에 안 들어간다.
      따라서 렌더 산출물의 중복제거(dedup)·위조탐지에는 이 해시가 아니라 표면별 해시(surface_hashes:
      save_stamp/glb/generate…)를 써야 한다. 이 해시를 렌더 dedup 열쇠로 오용하면 '다른 렌더가 같은
      박스면 같은 해시'가 되어 서로 다른 산출물을 하나로 착각한다.
    ★결정성 방어(리뷰 권고④): compute_geometry_hash는 정규화 없이 canonical_json만 하므로, 여기서
      normalize_fingerprint로 숫자를 미리 통일한다(int/float·미세 부동소수 차이에 둔감) — input_hash
      (compute_input_hash가 이미 정규화)와 동일한 정규화 계약을 geometry_hash에도 적용해 발산을 막는다.
    """
    bw = anchor.get("building_width_m")
    bd = anchor.get("building_depth_m")
    nf = anchor.get("num_floors")
    fh = anchor.get("floor_height_m")
    geometry: dict[str, Any] = dict(anchor)
    # 파생 기하(존재 값만 계산 — None이면 생략, 무날조).
    if nf is not None and fh is not None:
        geometry["building_height_m"] = round(float(nf) * float(fh), 6)
    if bw is not None and bd is not None:
        geometry["footprint_sqm"] = round(float(bw) * float(bd), 6)
    # ★권고④: 해시 직전 수치 정규화(int/float 혼입 방어) — compute_input_hash와 동일 계약.
    return compute_geometry_hash(normalize_fingerprint(geometry))


def make_design_run_id(
    *, tenant_id: str | None, project_id: str | None, seed: str, input_hash: str
) -> str:
    """스코프된 run_id — 'dr_' + hash({tenant,project,seed,input_hash})[:16].

    ★input_hash(기하 정체)는 테넌트/프로젝트 무관 동일하지만(=같은 건물), run_id는 그 식별자를
      테넌트·프로젝트·seed로 분할한다 — 교차테넌트 충돌 차단(IDOR 교훈)이자 프로젝트별 독립 실행 식별.
    """
    scoped = compute_input_hash({
        "tenant_id": tenant_id,
        "project_id": project_id,
        "seed": seed,
        "input_hash": input_hash,
    })
    return f"{_RUN_ID_PREFIX}{scoped[:_RUN_ID_HASH_LEN]}"


def can_approve_design_run(current_status: str, approved_by: str | None) -> tuple[bool, str]:
    """DRAFT→APPROVED 전이 가능 여부(순수 규칙) — 명시적 인간승인 액션에서만 True.

    ★타임아웃·부분해는 DRAFT로 남는다: persist는 항상 DRAFT로 기록하고, APPROVED 승격은 오직
      approve_design_run(=이 규칙 통과)만 한다. 승인자(approved_by)가 비면 거부(무인 승인 0).
    """
    if not (approved_by and str(approved_by).strip()):
        return False, "승인자(approved_by)가 비어 있어 APPROVED로 전이할 수 없습니다."
    if current_status == STATUS_APPROVED:
        return False, "이미 APPROVED 상태입니다(재승인 불필요)."
    if current_status != STATUS_DRAFT:
        return False, f"DRAFT 상태에서만 승인 가능합니다(현재: {current_status})."
    return True, "ok"


# ── schema_guard 패턴(site_basis_service 선례) — 신규 alembic 헤드 없이 멱등 보장 ──
_DESIGN_RUNS_DDL = (
    "CREATE TABLE IF NOT EXISTS design_runs ("
    "  run_id text PRIMARY KEY,"
    "  tenant_id text,"
    "  project_id text,"
    "  seed text NOT NULL DEFAULT 'default',"
    "  compiler_version text,"
    "  input_hash text NOT NULL,"           # 통일 앵커 해시(표면 무관 동일)
    "  surface_hashes jsonb NOT NULL DEFAULT '{}'::jsonb,"  # 표면별 해시 보존(save_stamp/glb/generate…)
    "  geometry_hash text,"
    "  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,"
    "  status text NOT NULL DEFAULT 'DRAFT',"   # 승인차원(DRAFT/APPROVED)만
    "  job_status text,"                        # ★WP-L 예약(실행상태 QUEUED/RUNNING 등) — 이 WP 미사용·미접촉
    "  approved_by text,"
    "  approved_at timestamptz,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_design_runs_scope ON design_runs (tenant_id, project_id, input_hash)",
    "CREATE INDEX IF NOT EXISTS idx_design_runs_status ON design_runs (status)",
)

_SCHEMA_READY = False


async def _ensure_schema(db: Any, force: bool = False) -> None:
    """design_runs 테이블 멱등 보장(부팅 대기 없이 최초 호출 시 lazy 생성).

    ★권고②(공용 패턴 교정 — growth/schema_guard.py 선례 정합): _SCHEMA_READY는 DDL '커밋 성공
      후'에만 세팅한다. 커밋 전에 세팅하면, 이후 데이터 트랜잭션이 롤백될 때 DDL도 함께 되돌려지는데
      플래그는 ready로 남아 다음 호출이 생성을 건너뛴다 — '유령 ready'(테이블 부재인데 생성 스킵)
      버그가 된다. DDL을 즉시 확정(commit)하면 이후 INSERT가 실패해도 스키마는 남는다.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    from sqlalchemy import text

    await db.execute(text(_DESIGN_RUNS_DDL))
    for ix in _INDEXES:
        await db.execute(text(ix))
    await db.commit()  # ★DDL 즉시 확정 — 커밋 성공 후에만 ready 세팅(유령 ready 방지·schema_guard 동형).
    _SCHEMA_READY = True


async def _safe_rollback(db: Any) -> None:
    """오염된 세션이 get_db 티어다운 commit을 깨지 않도록 best-effort rollback(site_basis 선례)."""
    with contextlib.suppress(Exception):
        await db.rollback()


# ══════════════════════════════════════════════════════════════════════════
# 영속 — persist(항상 DRAFT로 기록·기존 승인 보존)
# ══════════════════════════════════════════════════════════════════════════

async def persist_design_run(
    *,
    db: Any,
    tenant_id: str | None,
    project_id: str | None = None,
    building_width_m: Any,
    building_depth_m: Any,
    num_floors: Any,
    floor_height_m: Any = None,
    seed: str = "default",
    compiler_version: str | None = None,
    surface: str | None = None,
    surface_hash: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """설계 실행을 design_runs에 영속(upsert) — 통일 앵커 기준. 항상 status는 DRAFT로 시작한다.

    ★기존 승인 보존(site_basis MEDIUM-2 교훈): 같은 run_id가 이미 APPROVED면 재저장이 그 승인을
      무음으로 DRAFT로 되돌리면 안 된다. 그래서 ON CONFLICT는 내용 컬럼·surface_hashes(병합)·
      updated_at만 갱신하고 status/approved_by/approved_at은 절대 건드리지 않는다.
    ★surface_hashes 병합: 표면별 해시를 덮어쓰지 않고 jsonb concat(||)으로 누적한다 — save_stamp가
      먼저 쓰고 나중에 glb가 써도 두 표면 해시가 모두 남는다.
    반환: run_id·input_hash·geometry_hash·status(항상 DRAFT 또는 보존된 기존 상태).
    """
    anchor = canonical_design_anchor(
        building_width_m=building_width_m,
        building_depth_m=building_depth_m,
        num_floors=num_floors,
        floor_height_m=floor_height_m,
    )
    input_hash = compute_anchor_input_hash(anchor)
    geometry_hash = compute_anchor_geometry_hash(anchor)
    run_id = make_design_run_id(
        tenant_id=tenant_id, project_id=project_id, seed=seed, input_hash=input_hash
    )
    surface_map: dict[str, Any] = {}
    if surface and surface_hash:
        surface_map[surface] = surface_hash
    surface_json = json.dumps(surface_map, ensure_ascii=False)
    metrics_json = json.dumps(metrics or {}, ensure_ascii=False, default=str)
    resolved_compiler = compiler_version or ENGINE_SOURCE_VERSION

    status = STATUS_DRAFT
    try:
        await _ensure_schema(db)
        from sqlalchemy import text

        await db.execute(text(
            "INSERT INTO design_runs"
            "(run_id, tenant_id, project_id, seed, compiler_version, input_hash, "
            " surface_hashes, geometry_hash, metrics, status, updated_at) "
            "VALUES (:rid, :tid, :pid, :seed, :cv, :ih, CAST(:sh AS jsonb), :gh, "
            " CAST(:mj AS jsonb), 'DRAFT', now()) "
            "ON CONFLICT (run_id) DO UPDATE SET "
            "  compiler_version = EXCLUDED.compiler_version, "
            "  input_hash = EXCLUDED.input_hash, "
            "  geometry_hash = EXCLUDED.geometry_hash, "
            "  metrics = EXCLUDED.metrics, "
            "  surface_hashes = design_runs.surface_hashes || EXCLUDED.surface_hashes, "
            "  updated_at = now()"
            # ★status/approved_by/approved_at은 의도적으로 미갱신 — 기존 인간승인 무음취소 방지.
        ), {"rid": run_id, "tid": tenant_id, "pid": project_id, "seed": seed,
            "cv": resolved_compiler, "ih": input_hash, "sh": surface_json,
            "gh": geometry_hash, "mj": metrics_json})
        # 기존 행이 APPROVED였는지 확인해 반환 status를 정직하게 보고(테넌트 스코프).
        row = (await db.execute(text(
            "SELECT status FROM design_runs WHERE run_id = :rid "
            "AND tenant_id IS NOT DISTINCT FROM :tid"
        ), {"rid": run_id, "tid": tenant_id})).first()
        if row is not None:
            status = row[0]
        await db.commit()
    except Exception as e:  # noqa: BLE001 — 영속 실패해도 정체(해시·run_id)는 정직 반환(best-effort).
        logger.warning("design_run 영속 실패", err=str(e)[:160])
        await _safe_rollback(db)

    return {
        "run_id": run_id,
        "input_hash": input_hash,
        "geometry_hash": geometry_hash,
        "surface_hashes": surface_map,
        "status": status,
    }


# ══════════════════════════════════════════════════════════════════════════
# 조회 — get(테넌트 스코프)
# ══════════════════════════════════════════════════════════════════════════

async def get_design_run(
    *, db: Any, run_id: str, tenant_id: str | None = None
) -> dict[str, Any] | None:
    """design_run 단건 조회 — HIGH-1: tenant_id 스코프(교차테넌트 조회 차단·존재 비노출)."""
    from sqlalchemy import text

    await _ensure_schema(db)
    row = (await db.execute(text(
        "SELECT run_id, tenant_id, project_id, seed, compiler_version, input_hash, "
        " surface_hashes, geometry_hash, metrics, status, approved_by "
        "FROM design_runs WHERE run_id = :rid AND tenant_id IS NOT DISTINCT FROM :tid"
    ), {"rid": run_id, "tid": tenant_id})).first()
    if row is None:
        return None
    return {
        "run_id": row[0], "tenant_id": row[1], "project_id": row[2], "seed": row[3],
        "compiler_version": row[4], "input_hash": row[5], "surface_hashes": row[6] or {},
        "geometry_hash": row[7], "metrics": row[8] or {}, "status": row[9], "approved_by": row[10],
    }


# ══════════════════════════════════════════════════════════════════════════
# 인간승인 — approve(DRAFT→APPROVED, 명시 액션만)
# ══════════════════════════════════════════════════════════════════════════

async def approve_design_run(
    *, db: Any, run_id: str, approved_by: str, tenant_id: str | None = None
) -> dict[str, Any]:
    """설계 실행을 APPROVED로 승격 — DRAFT 상태 + 승인자 존재일 때만(명시 인간승인 액션).

    ★HIGH-1(테넌트 격리): run_id 조회를 tenant_id로 스코프한다 — 다른 테넌트의 run_id는 '없음'과
      동일 취급(존재 비노출 — IDOR 오라클 방지).
    ★자동경로(persist)는 절대 APPROVED를 만들지 않는다 — 이 함수만이 유일한 승격 경로(WP-G 계약 정합).
    """
    from sqlalchemy import text

    await _ensure_schema(db)
    row = (await db.execute(text(
        "SELECT status FROM design_runs WHERE run_id = :rid "
        "AND tenant_id IS NOT DISTINCT FROM :tid"
    ), {"rid": run_id, "tid": tenant_id})).first()
    if row is None:
        return {"ok": False, "message": f"run_id={run_id} 없음(먼저 persist 필요).", "run_id": run_id}

    current = row[0]
    ok, reason = can_approve_design_run(current, approved_by)
    if not ok:
        return {"ok": False, "message": reason, "run_id": run_id, "status": current}

    try:
        await db.execute(text(
            "UPDATE design_runs SET status = 'APPROVED', approved_by = :by, "
            "approved_at = now(), updated_at = now() WHERE run_id = :rid"
        ), {"by": approved_by, "rid": run_id})
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("design_run 승인 영속 실패", err=str(e)[:160])
        await _safe_rollback(db)
        return {"ok": False, "message": f"승인 저장 실패: {str(e)[:120]}", "run_id": run_id}

    return {"ok": True, "run_id": run_id, "status": STATUS_APPROVED, "approved_by": approved_by}
