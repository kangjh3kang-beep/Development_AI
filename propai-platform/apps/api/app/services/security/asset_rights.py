"""자산 권리 레지스트리 — 최소형 (P0 자산권리).

무엇을 푸는가: 업로드·수집된 자산(도면·데이터셋 항목 등)이 **학습에 써도 되는지**
(train_allowed)·**내보내도 되는지**(export_allowed)를 명시 권리로 관리한다. 핵심 원칙은
"권리 불명 = 금지"(default-deny): 출처·라이선스가 확인되지 않은 자산은 학습 0·내보내기 0 이
기본값이다. 이는 WP-J(P16 성장루프)에서 "권리 불명 학습 0" 게이트의 데이터 기반이 된다.

이번 세션(WP-H 1/2)은 **계약(모델+해석기+영속 헬퍼)만 준비**한다. 실제 P16 데이터셋 빌드/
학습 경로 결선은 WP-J 몫이다(여기서 boot·엔드포인트에 배선하지 않는다).

영속 판단(★): alembic 헤드 추가는 금지다(WP-M 이 모든 마이그레이션 WP 완료 후 5→1 병합을
최후단 격리 실행 — 그 전 헤드 분기 금지). 따라서 기존 전례(growth/secret_store/memory_hub
schema_guard)와 동일하게 **CREATE TABLE IF NOT EXISTS 기반 schema_guard** 로 `asset_rights`
테이블을 멱등 보장한다. provenance JSON additive 대신 테이블을 택한 이유: 권리는 키(자산
지문·테넌트)로 조회·집계되는 레지스트리라 JSON 산재보다 질의 가능한 테이블이 P16 게이트에
적합하다. 헬퍼는 전부 best-effort(실패해도 호출경로 불변)·지연 초기화(첫 호출 시 보장)라
부팅 배선이 필요 없다.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 권리 범위(scope) 어휘 — 자산을 어디까지 쓸 수 있는지의 대분류.
#   internal_only : 내부 분석/표시만(학습·외부내보내기 불가)
#   train_ok      : 모델 학습 허용
#   export_ok     : 외부 내보내기 허용
#   public        : 공개 자산(학습·내보내기 모두 허용 가정 — 출처 명시 필요)
#   unknown       : 권리 불명(기본값 — 학습·내보내기 모두 금지)
VALID_SCOPES = frozenset({"internal_only", "train_ok", "export_ok", "public", "unknown"})
DEFAULT_SCOPE = "unknown"


@dataclass
class AssetRight:
    """자산 1건의 권리. 권리 불명이면 train/export 모두 False(default-deny)."""

    asset_key: str  # 자산 지문(content_hash 등) — 레지스트리 조회 키
    scope: str = DEFAULT_SCOPE
    train_allowed: bool = False  # 학습 허용 여부(★기본 False)
    export_allowed: bool = False  # 내보내기 허용 여부(★기본 False)
    source: str | None = None  # 출처/라이선스 근거(예: 'aihub-license', 'user-upload')
    tenant_id: str | None = None
    note: str | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "asset_key": self.asset_key,
            "scope": self.scope,
            "train_allowed": bool(self.train_allowed),
            "export_allowed": bool(self.export_allowed),
            "source": self.source,
            "tenant_id": self.tenant_id,
            "note": self.note,
            "meta": self.meta,
        }


def resolve_asset_right(
    asset_key: str,
    *,
    scope: str | None = None,
    train_allowed: bool | None = None,
    export_allowed: bool | None = None,
    source: str | None = None,
    tenant_id: str | None = None,
    note: str | None = None,
) -> AssetRight:
    """입력(부분 정보)에서 AssetRight 를 만든다. **불명은 항상 금지(False)로 수렴**한다.

    핵심 계약: train_allowed/export_allowed 가 None(불명)이면 False 다. scope 로부터의
    유추도 '명시 허용'일 때만 True 를 준다(train_ok→train, export_ok→export, public→둘 다).
    이렇게 해서 "권리 불명 train 0" 이 데이터 계층에서 보장된다.
    """
    sc = (scope or DEFAULT_SCOPE).strip().lower()
    if sc not in VALID_SCOPES:
        sc = DEFAULT_SCOPE

    # scope 기반 명시 허용(불명/내부전용은 False 유지).
    scope_train = sc in ("train_ok", "public")
    scope_export = sc in ("export_ok", "public")

    # 명시 인자(True/False)가 있으면 그것이 우선. None(불명)이면 scope 유추, 그마저 없으면 False.
    # ★0-falsy 주의: train_allowed=False 는 "명시 거부"이므로 유효값이다. `train_allowed or ...`
    #   같은 단축평가는 False 를 불명으로 오인하므로 반드시 `is None` 으로 구분한다.
    resolved_train = scope_train if train_allowed is None else bool(train_allowed)
    resolved_export = scope_export if export_allowed is None else bool(export_allowed)

    return AssetRight(
        asset_key=(asset_key or "").strip(),
        scope=sc,
        train_allowed=resolved_train,
        export_allowed=resolved_export,
        source=source,
        tenant_id=tenant_id,
        note=note,
    )


def is_train_allowed(right: AssetRight | None) -> bool:
    """학습 허용 게이트 — right 가 없으면(불명) False(default-deny)."""
    return bool(right and right.train_allowed)


def is_export_allowed(right: AssetRight | None) -> bool:
    """내보내기 허용 게이트 — right 가 없으면(불명) False(default-deny)."""
    return bool(right and right.export_allowed)


# ── 영속(schema_guard — CREATE TABLE IF NOT EXISTS, alembic 헤드 없음) ─────────
# growth/secret_store 선례와 동일. 지연 초기화(첫 호출 보장) + best-effort.
_SCHEMA_READY = False

_ASSET_RIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS asset_rights (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_key text NOT NULL,
    tenant_id text,
    scope text NOT NULL DEFAULT 'unknown',
    train_allowed boolean NOT NULL DEFAULT false,
    export_allowed boolean NOT NULL DEFAULT false,
    source text,
    note text,
    meta jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""

_INDEXES = [
    # (asset_key, tenant_id) 멱등 upsert 키 — 테넌트 격리 조회.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_rights_key_tenant "
    "ON asset_rights (asset_key, tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_asset_rights_scope ON asset_rights (scope)",
    "CREATE INDEX IF NOT EXISTS idx_asset_rights_train ON asset_rights (train_allowed)",
]


async def ensure_schema(db: AsyncSession, force: bool = False) -> bool:
    """asset_rights 테이블·인덱스를 멱등 보장. 실패는 graceful(rollback 후 False)."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return True
    try:
        await db.execute(text(_ASSET_RIGHTS_DDL))
        for ddl in _INDEXES:
            await db.execute(text(ddl))
        await db.commit()
        _SCHEMA_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("asset_rights schema_guard 실패: %s", str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def upsert_asset_right(db: AsyncSession, right: AssetRight) -> bool:
    """권리 1건 upsert((asset_key, tenant_id) 기준). best-effort — 실패해도 예외 안 냄.

    ★NULL tenant_id 는 UNIQUE 에서 서로 충돌하지 않으므로, 전역 권리는 tenant_id 를
      빈 문자열('') 로 정규화해 멱등 upsert 가 되게 한다(NULL 다중행 방지).
    """
    if not right.asset_key:
        return False
    if not await ensure_schema(db):
        return False
    tid = right.tenant_id or ""
    try:
        await db.execute(
            text(
                "INSERT INTO asset_rights "
                "(asset_key, tenant_id, scope, train_allowed, export_allowed, source, note, meta) "
                "VALUES (:k, :t, :sc, :tr, :ex, :src, :note, CAST(:meta AS jsonb)) "
                "ON CONFLICT (asset_key, tenant_id) DO UPDATE SET "
                "  scope=EXCLUDED.scope, train_allowed=EXCLUDED.train_allowed, "
                "  export_allowed=EXCLUDED.export_allowed, source=EXCLUDED.source, "
                "  note=EXCLUDED.note, meta=EXCLUDED.meta, updated_at=now()"
            ),
            {
                "k": right.asset_key, "t": tid, "sc": right.scope,
                "tr": bool(right.train_allowed), "ex": bool(right.export_allowed),
                "src": right.source, "note": right.note,
                "meta": json.dumps(right.meta or {}, ensure_ascii=False, default=str),
            },
        )
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("upsert_asset_right 실패(%s): %s", right.asset_key[:32], str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def get_asset_right(
    db: AsyncSession, asset_key: str, tenant_id: str | None = None
) -> AssetRight:
    """레지스트리에서 권리를 조회한다. **없으면 unknown(default-deny) AssetRight 반환**.

    호출부는 언제나 AssetRight 를 받으며(None 아님), 미등록 자산은 자동으로 train/export 0 이다
    → "권리 불명 train 0" 이 조회 계층에서 보장된다.
    """
    key = (asset_key or "").strip()
    tid = tenant_id or ""
    if not key:
        return resolve_asset_right(key, tenant_id=tenant_id)
    if not await ensure_schema(db):
        return resolve_asset_right(key, tenant_id=tenant_id)
    try:
        row = (
            await db.execute(
                text(
                    "SELECT scope, train_allowed, export_allowed, source, note, meta "
                    "FROM asset_rights WHERE asset_key=:k AND tenant_id=:t"
                ),
                {"k": key, "t": tid},
            )
        ).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("get_asset_right 조회 실패(%s): %s", key[:32], str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return resolve_asset_right(key, tenant_id=tenant_id)
    if row is None:
        return resolve_asset_right(key, tenant_id=tenant_id)  # 미등록 = 불명 = 금지
    scope, train, export, source, note, meta = row
    ar = AssetRight(
        asset_key=key, scope=scope or DEFAULT_SCOPE,
        train_allowed=bool(train), export_allowed=bool(export),
        source=source, tenant_id=tenant_id, note=note,
        meta=(meta if isinstance(meta, dict) else {}),
    )
    return ar
