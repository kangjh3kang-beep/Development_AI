"""v62 — users.social_consent_pending (소셜 가입 동의 미완 표시).

Revision ID: v62_9_social_consent_pending
Revises: v62_8_run_execution
Create Date: 2026-09-06

★왜 컬럼 하나인가 — 소급 차단을 피하기 위해서다.
  이메일 가입은 `UserConsent` 3종을 버전과 함께 기록하는데(routers/auth.py),
  소셜 가입 경로(auth/oauth_common.py)는 **동의를 받지도 남기지도 않았다**(실측 0건).
  그런데 «동의 이력이 없으면 차단» 으로 구현하면 **이미 가입한 소셜 사용자가 전원 차단**된다.
  그래서 상태(이력 부재)가 아니라 **명시 플래그**로 판정하고, 기본값을 False 로 둔다:
  기존 행은 전부 False → **자동 유예**. 앞으로 만들어지는 소셜 계정만 True 로 켠다.

★NOT NULL + server_default 라 기존 행 재작성 없이 안전하다.
"""
from alembic import op
import sqlalchemy as sa

revision = "v62_9_social_consent_pending"
down_revision = "v62_8_run_execution"
branch_labels = None
depends_on = None

_COL = "social_consent_pending"


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    # 멱등 — ensure_schema 경로로 이미 생겼을 수 있다(이 저장소 관례)
    if _has_column(bind, "users", _COL):
        return
    op.add_column(
        "users",
        sa.Column(
            _COL,
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "소셜 가입으로 만들어졌으나 약관·개인정보 동의를 아직 받지 않은 상태. "
                "기본값 False 라 기존 사용자는 자동 유예된다."
            ),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "users", _COL):
        op.drop_column("users", _COL)
