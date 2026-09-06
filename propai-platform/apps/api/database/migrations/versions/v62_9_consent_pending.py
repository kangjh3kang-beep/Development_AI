"""v62 — users.consent_pending 컬럼만 만든다(★소급은 다음 리비전).

Revision ID: v62_9_consent_pending
Revises: 043_mypage_coin_orders_ledger
Create Date: 2026-09-06

★모집단을 라이브에서 재고 이름을 바꿨다.
  처음엔 `social_consent_pending` 으로 두고 «기존 사용자는 기본값 False 로 유예» 하려 했다.
  그런데 프로덕션을 조회하니 **소셜만의 문제가 아니었다**(2026-09-06 실측, 탈퇴 제외):

      경로      동의  인원   생성일
      email      ✘     6    2026-05-27 ~ 2026-08-27
      email      ✔     5    2026-08-27 (전원 같은 날 — 동의 기능 도입일)
      kakao      ✘     1    2026-06-09
      naver      ✘     1    2026-09-06  ← 동의 기능이 있는데도 소셜이라 안 받았다

  즉 ①**동의 기능 도입(2026-08-27) 이전 계정 8명**이 동의 없이 남아 있고
     ②그중 네이버 1건은 **기능 도입 이후에 만들어졌는데도** 소셜 경로라 비어 있다.
  ①은 소급 대상, ②는 이 브랜치가 고친 결함의 실증이다.
  → 이름에서 `social` 을 빼고, **동의 이력이 없는 모든 생존 사용자**를 True 로 채운다.

★소급은 되돌릴 수 있어야 한다 — downgrade 는 컬럼째 지운다(플래그만 지우면 되므로
  사용자 데이터는 손실되지 않는다. 동의 이력 user_consents 는 이 리비전이 건드리지 않는다).
"""
import sqlalchemy as sa
from alembic import op

revision = "v62_9_consent_pending"
# ★부모는 **실제 head** 여야 한다. v62_8 은 이미 자식(042_member_account_system)이 있어
#   거기 매달면 042 와 형제가 되어 **가지를 친다** → head 2개 → `alembic upgrade head` 가 거부.
#   2026-09-06 실측: 이 PR 전 head 1개(043) · 후 2개. 배포가 그 지점에서 안전 중단됐다.
#   ★그리고 라이브 DB 스탬프가 043 이므로, 043 을 부모로 두면 `upgrade head` 가
#     **이 리비전 하나만** 실행한다(v62_5~v62_8 재적용 위험 없음).
down_revision = "043_mypage_coin_orders_ledger"
branch_labels = None
depends_on = None

from apps.api.database.consent_backfill import (  # noqa: E402
    CONSENT_PENDING_COLUMN as _COL,
)


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "users", _COL):
        op.add_column(
            "users",
            sa.Column(
                _COL,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
                comment="약관·개인정보 동의 미완. 동의 이력이 없는 사용자를 소급 표시한다.",
            ),
        )

    # ★★소급 UPDATE 는 **이 리비전에 없다.** 여기서 돌리면
    #   머지 → api 배포(deploy-zero-downtime.sh:234 `alembic upgrade head`, 트래픽 전환 前)
    #   → 소급이 **한 덩어리로** 적용된다. 즉 «배포를 확증한 뒤 소급» 이 원리적으로 불가능해진다.
    #   2026-09-06 실측: 소급 대상 8명에 **사용자 본인 계정과 super_admin 이 포함**되고,
    #   복구에 **본인의 동의 행동**이 필요하다 — 배포 부수효과로 일어날 일이 아니다.
    #   → 소급은 별도 리비전(v62_10)에서, **사용자 승인 뒤에** 적용한다.
    #     SQL 자체는 database/consent_backfill.py 에 단일 원천으로 있다.


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "users", _COL):
        op.drop_column("users", _COL)


