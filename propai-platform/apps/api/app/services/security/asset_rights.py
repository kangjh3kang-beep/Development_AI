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
from typing import Any

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


def keep_train_allowed(
    rows: list, rights: dict[str, AssetRight | None], *, key_index: int
) -> tuple[list, int]:
    """P16 학습게이트(순수) — 학습 데이터셋 행 중 **train_allowed 자산만** 통과시킨다.

    "권리 불명 = 학습 0"(default-deny)의 핵심 필터다. WP-J(성장루프) 데이터셋 빌더가 이 함수로
    한 번 걸러 권리 미확인·미등록 자산을 학습에서 제외한다(공용 게이트 — 한 곳을 고치면 전 학습
    경로가 따른다).

    Args:
        rows: 학습예시 행 리스트(각 행은 튜플/시퀀스). key_index 위치에 자산키(content_hash)가 있다.
        rights: {자산키 → AssetRight | None} 사전. 미등록 키는 None(=불명=금지)으로 취급.
        key_index: 각 행에서 자산키(content_hash)의 인덱스.

    Returns: (통과 행 리스트, 제외 건수). ★0-falsy·불명 모두 is_train_allowed 로 판정(None→False).
    """
    kept: list = []
    excluded = 0
    for r in rows:
        key = r[key_index] if len(r) > key_index else None
        if key and is_train_allowed(rights.get(key)):
            kept.append(r)
        else:
            excluded += 1
    return kept, excluded


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


# upsert SQL·파라미터는 단건/배치가 공유(한 곳만 고치면 전 upsert 경로가 따른다).
_UPSERT_SQL = (
    "INSERT INTO asset_rights "
    "(asset_key, tenant_id, scope, train_allowed, export_allowed, source, note, meta) "
    "VALUES (:k, :t, :sc, :tr, :ex, :src, :note, CAST(:meta AS jsonb)) "
    "ON CONFLICT (asset_key, tenant_id) DO UPDATE SET "
    "  scope=EXCLUDED.scope, train_allowed=EXCLUDED.train_allowed, "
    "  export_allowed=EXCLUDED.export_allowed, source=EXCLUDED.source, "
    "  note=EXCLUDED.note, meta=EXCLUDED.meta, updated_at=now()"
)


def _upsert_params(right: AssetRight) -> dict[str, Any]:
    """AssetRight → upsert 바인드 파라미터. ★전역 권리는 tenant_id 를 ''(빈문자)로 정규화해
    멱등 upsert 가 되게 한다(NULL 다중행 방지 — UNIQUE 에서 NULL 은 서로 충돌 안 함)."""
    return {
        "k": right.asset_key, "t": right.tenant_id or "", "sc": right.scope,
        "tr": bool(right.train_allowed), "ex": bool(right.export_allowed),
        "src": right.source, "note": right.note,
        "meta": json.dumps(right.meta or {}, ensure_ascii=False, default=str),
    }


async def upsert_asset_right(db: AsyncSession, right: AssetRight) -> bool:
    """권리 1건 upsert((asset_key, tenant_id) 기준). best-effort — 실패해도 예외 안 냄."""
    if not right.asset_key:
        return False
    if not await ensure_schema(db):
        return False
    try:
        await db.execute(text(_UPSERT_SQL), _upsert_params(right))
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("upsert_asset_right 실패(%s): %s", right.asset_key[:32], str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def upsert_asset_rights_batch(db: AsyncSession, rights: list[AssetRight]) -> int:
    """권리 여러 건을 **1 트랜잭션**으로 멱등 upsert 한다(레지스트리 시딩용).

    ingest 소스(예: AI Hub 라이선스)가 한 배치의 자산 권리를 채울 때 단건 upsert(=행마다 commit)의
    왕복 비용을 없앤다. 빈 asset_key 는 건너뛴다. 반환: 커밋 성공 건수(0=미영속/전무).
    best-effort — 실패 시 rollback 후 0(호출경로 불변).
    """
    valid = [r for r in rights if r.asset_key]
    if not valid:
        return 0
    if not await ensure_schema(db):
        return 0
    try:
        for r in valid:
            await db.execute(text(_UPSERT_SQL), _upsert_params(r))
        await db.commit()
        return len(valid)
    except Exception as e:  # noqa: BLE001
        logger.warning("upsert_asset_rights_batch 실패(%d건): %s", len(valid), str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return 0


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


# Postgres 바인드 파라미터 상한(32767)을 피하려고 고유키(쌍당 2바인드)를 이 크기로 청크한다
# (통합자 리뷰 LOW: ~16k 조합에서 상한 초과→예외→전건 default-deny 되던 under-scale 결함).
# 1000키/청크 = 2000바인드/질의로 상한에 크게 여유(응답 payload 크기도 청크 단위로 완만).
_BATCH_CHUNK_SIZE = 1000


async def get_asset_rights_batch(
    db: AsyncSession, keys: list[tuple[str, str | None]]
) -> dict[tuple[str, str | None], AssetRight]:
    """여러 자산 권리를 **청크 단위 배치 질의**로 조회한다(N+1 제거 — WP-I 리뷰 LOW).

    학습셋 수천~수만 행의 권리를 확인할 때 행마다 get_asset_right 를 부르면 왕복이 N배다. 이 함수는
    고유 (asset_key, tenant_id) 조합을 모아 `WHERE (asset_key, tenant_id) IN (...)` 로 읽되,
    고유키 수가 `_BATCH_CHUNK_SIZE` 를 넘으면 **여러 청크 질의로 분할**한다(단일 질의 바인드 상한
    32767 초과 방지 — 통합자 리뷰 LOW: 청크 없이는 ~16k 고유조합에서 예외→전건 default-deny로
    번지는 under-scale 결함이었다). 결과는 청크 전체를 병합한 뒤 반환한다.

    계약은 get_asset_right 와 동일: **미등록 키는 unknown(default-deny) AssetRight** 로 채워
    반환한다(호출부는 언제나 값을 받는다). 반환 dict 키는 **입력한 원본 (asset_key, tenant_id) 튜플**
    이다(정규화 전 — 호출부 조회 일치). best-effort: 청크 조회 실패는 **그 청크의 키만**
    default-deny(fail-safe·보수적)로 남기고, 이미 성공한 다른 청크의 실제 조회결과는 보존한다.
    """
    out: dict[tuple[str, str | None], AssetRight] = {}
    # 고유·유효 키만 추림(빈 asset_key 는 즉시 default-deny). norm 키=(정규 asset_key, 정규 tenant '').
    uniq: dict[tuple[str, str], list[tuple[str, str | None]]] = {}
    for asset_key, tenant_id in keys:
        k = (asset_key or "").strip()
        if not k:
            out[(asset_key, tenant_id)] = resolve_asset_right(k, tenant_id=tenant_id)
            continue
        uniq.setdefault((k, tenant_id or ""), []).append((asset_key, tenant_id))

    if not uniq:
        return out

    norms = list(uniq.keys())
    found: dict[tuple[str, str], Any] = {}
    if await ensure_schema(db):
        for start in range(0, len(norms), _BATCH_CHUNK_SIZE):
            chunk = norms[start:start + _BATCH_CHUNK_SIZE]
            pairs_sql = ", ".join(f"(:k{i}, :t{i})" for i in range(len(chunk)))
            params: dict[str, Any] = {}
            for i, (nk, nt) in enumerate(chunk):
                params[f"k{i}"] = nk
                params[f"t{i}"] = nt
            try:
                rows = (await db.execute(
                    text(
                        "SELECT asset_key, tenant_id, scope, train_allowed, export_allowed, "
                        "source, note, meta "
                        f"FROM asset_rights WHERE (asset_key, tenant_id) IN ({pairs_sql})"
                    ),
                    params,
                )).all()
                for r in rows:
                    found[(r[0], r[1] or "")] = r
            except Exception as e:  # noqa: BLE001 — 청크 실패는 그 청크만 default-deny(아래서 자동)
                logger.warning(
                    "get_asset_rights_batch 청크 조회 실패(%d keys, chunk_start=%d): %s",
                    len(chunk), start, str(e)[:160],
                )
                with contextlib.suppress(Exception):
                    await db.rollback()
    # ensure_schema 실패(스키마 미가용)여도 아래 루프가 found 를 빈 채로 두어 전건 default-deny 로
    # 자연 수렴한다(별도 분기 불요 — get_asset_right 의 단건 폴백과 동일 계약).

    for norm, originals in uniq.items():
        r = found.get(norm)
        for orig in originals:
            if r is None:
                out[orig] = resolve_asset_right(norm[0], tenant_id=orig[1])  # 미등록/실패=불명=금지
            else:
                _ak, _t, scope, train, export, source, note, meta = r
                out[orig] = AssetRight(
                    asset_key=norm[0], scope=scope or DEFAULT_SCOPE,
                    train_allowed=bool(train), export_allowed=bool(export),
                    source=source, tenant_id=orig[1], note=note,
                    meta=(meta if isinstance(meta, dict) else {}),
                )
    return out
