"""mirror_snapshot (jurisdiction, snapshot_id) 유니크 — INC-13 멱등·동시writer 원자 upsert 근거.

Revision ID: 0014_mirror_snapshot_uniq
Revises: 0013_external_source_cache
"""
from alembic import op

revision = "0014_mirror_snapshot_uniq"
down_revision = "0013_external_source_cache"
branch_labels = None
depends_on = None

SCHEMA = "review"


def upgrade() -> None:
    # 유니크 제약 생성 전 기존 중복 정리 — (created_at, id) 최댓값 1건만 보존(동률 안전한 전순서).
    op.execute(f"""
        DELETE FROM {SCHEMA}.mirror_snapshot a
        USING {SCHEMA}.mirror_snapshot b
        WHERE a.jurisdiction = b.jurisdiction
          AND a.snapshot_id = b.snapshot_id
          AND (a.created_at, a.id) < (b.created_at, b.id)
    """)
    op.create_unique_constraint(
        "uq_mirror_snapshot_jur_sid", "mirror_snapshot",
        ["jurisdiction", "snapshot_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint("uq_mirror_snapshot_jur_sid", "mirror_snapshot",
                       schema=SCHEMA, type_="unique")
