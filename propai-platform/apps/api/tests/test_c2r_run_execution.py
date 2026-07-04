"""C2R P0 추적 인프라 단위 테스트 — RunStateEnum·RunExecution 스키마·마이그레이션(DB 불요).

실제 DB 왕복(insert/select)은 배포 후 `POST /api/v1/c2r/ping` 라이브검증으로 커버한다.
여기서는 스키마 계약(컬럼·제약·enum·마이그레이션 head 병합)을 import/파싱만으로 고정해
회귀를 막는다. alembic 미설치 환경에서도 통과하도록 마이그레이션은 ast 파싱으로 검증한다.
"""

import ast
import pathlib

from packages.schemas.run_state import RunStateEnum

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "database/migrations/versions/v62_8_run_execution.py"
)


def test_run_state_enum_values() -> None:
    """RunStateEnum 은 계획서 7상태를 이 순서/값으로 고정한다(SSOT)."""
    assert [s.value for s in RunStateEnum] == [
        "draft",
        "pass",
        "pass_with_warnings",
        "fail",
        "manual_review_required",
        "human_approved",
        "locked",
    ]
    # StrEnum: 값이 문자열과 동일 비교(DB 저장·비교 편의)
    assert RunStateEnum.DRAFT == "draft"


def test_run_state_exported_from_schemas_package() -> None:
    """packages.schemas.__init__ 이 RunStateEnum 을 재export 한다(공유 SSOT 진입점)."""
    import packages.schemas as ps

    assert hasattr(ps, "RunStateEnum")


def test_run_execution_table_contract() -> None:
    """run_execution 테이블 계약: PK·필수 컬럼·멱등키 UNIQUE."""
    from apps.api.database.models.run_execution import RunExecution

    t = RunExecution.__table__
    assert t.name == "run_execution"
    assert [c.name for c in t.primary_key.columns] == ["run_id"]
    expected = {
        "run_id",
        "parent_run_id",
        "project_id",
        "tenant_id",
        "track",
        "s_phase",
        "state",
        "input_hash",
        "artifact_uri",
        "approval_gate_json",
        "idempotency_key",
        "created_at",
        "updated_at",
    }
    assert expected <= {c.name for c in t.columns}
    # 멱등키 UNIQUE 필수(같은 입력 재요청이 run 을 중복 생성하지 않도록)
    assert t.columns["idempotency_key"].unique is True


def test_run_execution_default_state_is_draft() -> None:
    """신규 run 의 기본 상태는 DRAFT(미검증)."""
    from apps.api.database.models.run_execution import RunExecution

    default = RunExecution.__table__.columns["state"].default
    assert default is not None
    assert default.arg == RunStateEnum.DRAFT.value


def _migration_assignments() -> dict:
    """마이그레이션 파일의 top-level 상수(revision/down_revision)를 alembic 없이 파싱."""
    tree = ast.parse(_MIGRATION.read_text())
    out: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in ("revision", "down_revision"):
                    out[tgt.id] = ast.literal_eval(node.value)
    return out


def test_migration_merges_both_heads() -> None:
    """v62_8 이 현재 2개 head(034·041)를 튜플 down_revision 으로 병합해 단일 head 로 정상화.

    한쪽 head 만 체이닝하면 다른 head 가 미병합으로 남아 3-head 로 악화된다.
    """
    a = _migration_assignments()
    assert a["revision"] == "v62_8_run_execution"
    assert set(a["down_revision"]) == {
        "034_ledger_unique_version",
        "041_sales_unit_events_ledger",
    }


def test_migration_targets_only_run_execution() -> None:
    """마이그레이션 _tables() 가 run_execution 만 생성 대상으로 필터(alembic 있으면 실행)."""
    import importlib.util

    import pytest

    pytest.importorskip("alembic")
    spec = importlib.util.spec_from_file_location("v62_8_run_execution", _MIGRATION)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert [t.name for t in m._tables()] == ["run_execution"]
