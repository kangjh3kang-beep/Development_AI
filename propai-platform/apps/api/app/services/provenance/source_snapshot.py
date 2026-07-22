"""SourceSnapshot — 외부 API 원본 응답 불변 수집 스냅샷 + dead-letter (v4.0 Wave2 W2-1).

SPEC v4 Zero-Trust ACQUIRE 단계 계약의 실용 부분집합을 구현한다
(SPEC_v4_master_execution_prompt §[Zero-Trust Data 원칙] 1.ACQUIRE·§P1):
  "원본을 읽기 전용으로 확보하고 출처·취득시각·기준시점·라이선스·checksum을 기록한다."
  "raw payload를 checksum과 함께 불변 object store에 저장한다."
  "API 호출시각과 데이터 기준시각을 분리한다(fetched_at ≠ observed_at)."
  "retry/backoff/rate limit/circuit breaker/cache/dead-letter를 구현한다."

스파이크 결론(★근거— 그린필드 금지):
- integrations/base_client.BaseAPIClient._request 는 캐시(Redis)+Circuit Breaker+재시도(tenacity)만
  갖추고 있고 원본(raw) 불변저장·dead-letter는 없었다(이번 W2-1이 메우는 공백).
- 저장 방식은 analysis_ledger_service._ensure 선례를 그대로 따른다: alembic 신규 헤드 없이 런타임
  CREATE TABLE IF NOT EXISTS + advisory lock 이중검사(double-checked locking)로 동시 최초생성
  경합을 직렬화한다. Supabase Storage(propai-uploads)는 이미지 등 대용량 바이너리 자산용이라
  API 원문(대개 수십KB급 JSON/XML) 저장에는 과함 — DB append-only 테이블이 이 저장소의 기존
  관례(analysis_ledger·platform_events)와 정합적이다.
- 실제 프로덕션 VWorld 호출은 대부분 app/services/external_api/vworld_service.py(자체 httpx +
  자체 재시도)를 거치고, BaseAPIClient 계열(apps/api/integrations/vworld_client.VWorldClient)은
  일부(avm_service·propai_orchestrator)만 사용한다. G2B 실사용 커넥터(app/integrations/g2b_client.
  G2BClient)는 BaseAPIClient를 아예 상속하지 않는 별도 httpx 클래스다. 이번 1차는 두 실사용
  진입점(VWorldClient·G2BClient)에 opt-in 플래그로 직접 배선한다 — vworld_service.py의 자체
  httpx 경로까지 통합하는 것은 더 큰 리팩토링이라 후속(W2-2 이후) 과제로 남긴다(한계 참고).

★기록 실패 무영향(계약 핵심): safe_record_success/safe_record_dead_letter는 어떤 예외(DB
  미가용·직렬화 실패·마스킹 버그 등)도 호출경로로 전파하지 않는다 — 스냅샷 기록이 실패해도
  외부 API 수집 자체는 항상 그대로 진행된다(best-effort, capture_service.record_event 패턴과 동형).

★용량 방어: payload_bytes는 상한(기본 512KB) 초과 시 절단 저장 + payload_truncated=True 플래그를
  남긴다(정직 — 잘렸다는 사실을 숨기지 않는다). checksum은 항상 절단 전 원문 전체 기준으로 계산해
  무결성 검증 의미를 유지한다. 보존기간(retention)·정리(prune) 정책은 이번 1차에서 컬럼/함수 없이
  구현하지 않고 주석으로만 후속 명시한다 — #415(적산 QTO 보존기간) 교훈: 실제 소비처가 참조하는
  최대 조회 윈도우가 정해진 뒤 analysis_ledger_quota류 패턴(테넌트/소스별 max_entries + prune_old)
  으로 한 번에 정하는 편이, 임의로 먼저 정한 보존기간을 나중에 다시 넓히는 것보다 안전하다.

★커넥터 opt-in(기본 OFF): 전 커넥터 일괄 ON은 용량 위험이 커서, 호출부가 명시적으로 켠 커넥터만
  기록한다. 1차 ON 대상은 VWorld(BaseAPIClient.snapshot_enabled)·G2B(g2b_client._SNAPSHOT_ENABLED)
  2종 — 스파이크에서 실제 사용 경로를 확인한 결과다.

★"불변" 명칭의 실제 수준 — 정직화(R1 MEDIUM): 이 테이블은 analysis_ledger처럼 content_hash
  체인(prev_hash 연결)으로 변조를 재계산·탐지하거나, DB 권한 수준에서 UPDATE/DELETE를
  REVOKE해 강제하는 진짜 "불변 저장소"가 아니다. 이 모듈의 코드 경로가 INSERT만 발행한다는
  의미의 "관례적(conventional) append-only"일 뿐이며, 이 테이블에 직접 접근하는 다른 경로
  (운영자 SQL·다른 서비스의 실수 등)의 수정·삭제를 막지 않는다. analysis_ledger 수준의 진짜
  불변성(해시체인+변조탐지)이 필요해지면 checksum을 prev_checksum으로 체이닝하는 승격은
  후속 과제다(보존기간 정책과 마찬가지로 이번 1차 범위 밖).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

STATUS_OK = "OK"
STATUS_DEAD_LETTER = "DEAD_LETTER"

# payload 저장 상한(바이트) — 초과분은 절단하고 payload_truncated=True로 정직 표기.
PAYLOAD_LIMIT_BYTES = 512 * 1024  # 512KB

# request_fingerprint 계산 전 마스킹 대상 파라미터 키 판정 토큰(대소문자 무관 부분일치).
# logging_config.py의 로그 마스킹 선례(_PII_PATTERNS: serviceKey/apiKey/authKey= 정규식)를
# "요청 파라미터 dict 직접 마스킹"으로 확장한다 — VWorld는 서비스 접두 없는 평문 'key'
# 파라미터를 쓰므로, 로그 정규식보다 넓게 "키 이름에 이 토큰이 포함되면 비밀로 간주"한다.
_SECRET_PARAM_TOKENS: tuple[str, ...] = ("key", "token", "secret", "password", "credential")
_MASK = "***MASKED***"


def mask_secret_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """비밀로 추정되는 파라미터 값을 마스킹한 새 dict를 반환한다(원본은 변경하지 않음).

    키 이름에 key/token/secret/password/credential 토큰이 포함되면(대소문자 무관) 값을
    고정 마커로 치환한다. VWorld(평문 'key')·G2B('serviceKey') 등 실사용 키 이름 변형을
    모두 포괄한다.
    """
    if not params:
        return {}
    masked: dict[str, Any] = {}
    for k, v in params.items():
        key_lower = str(k).lower()
        if any(tok in key_lower for tok in _SECRET_PARAM_TOKENS):
            masked[k] = _MASK
        else:
            masked[k] = v
    return masked


def _canonical_params(params: dict[str, Any] | None) -> str:
    """마스킹 후 결정적 직렬화(키 정렬) — 동일 요청 = 동일 지문."""
    masked = mask_secret_params(params)
    return json.dumps(masked, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def build_request_fingerprint(method: str, url: str, params: dict[str, Any] | None) -> str:
    """URL+파라미터(비밀 마스킹 후)로 sha256 요청지문을 만든다(감사·중복조회 조인키).

    ★비밀은 해시 전에 마스킹한다 — 해시값 자체는 안전해도 원문 파라미터를 그대로 저장/해시하면
    다른 경로(로그·DB 덤프)로 키가 유출될 위험이 있어, 저장되는 어떤 형태에도 비밀 원문이
    남지 않게 한다.
    """
    basis = f"{(method or 'GET').upper()}|{url}|{_canonical_params(params)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def compute_checksum(payload_bytes: bytes | None) -> str:
    """원문 바이트의 sha256 checksum(불변성 검증용). 빈 응답도 결정적으로 해시한다."""
    return hashlib.sha256(payload_bytes or b"").hexdigest()


def truncate_payload(
    payload_bytes: bytes | None, limit: int = PAYLOAD_LIMIT_BYTES,
) -> tuple[bytes | None, bool]:
    """상한 초과 시 절단하고 (저장할 payload, truncated 여부)를 반환한다."""
    if payload_bytes is None:
        return None, False
    if len(payload_bytes) <= limit:
        return payload_bytes, False
    return payload_bytes[:limit], True


# URL 뒤에 붙은 쿼리스트링을 통째로 "?***"로 절단한다(리뷰어 지정 1차 방어) — 어떤
# 파라미터 이름이든(예: VWorld 평문 'key') 무조건 제거되므로 키 이름을 일일이 나열할
# 필요가 없다. httpx.HTTPStatusError.__str__()가 "...for url '<원본URL+쿼리스트링>'"
# 형태로 요청 URL을 그대로 문자열화하는 것이 실제 유출 경로(★R1 HIGH 근거).
_URL_QUERY_STRIP = re.compile(r"(https?://[^\s'\"?]+)\?[^\s'\"]*")


def scrub_error_message(message: str | None) -> str | None:
    """error_message를 저장 직전에 스크러빙한다 — 비밀이 평문으로 append-only 테이블에
    영구 저장되는 것을 막는 마지막 방어선(★R1 HIGH 회귀 수정).

    근본원인: mask_secret_params()는 request_fingerprint 계산 "입력"만 마스킹했고,
    error_message는 그 경로를 거치지 않는 별도 필드였다. 그런데 httpx.HTTPStatusError를
    str()하면 "Client error '...' for url 'https://.../data?service=data&key=SECRET&...'"
    처럼 원본 요청 URL(쿼리스트링 포함)이 그대로 들어있다 — VWorld/G2B는 인증키를
    쿼리파라미터로 보내므로, 이 문자열을 그대로 저장하면 비밀 마스킹 계약(★비밀 마스킹
    후 해시) 자체가 error_message 필드 하나 때문에 무의미해진다.

    1차 방어(리뷰어 지정): URL의 "?" 뒤 전체를 통째로 "?***"로 절단 — 파라미터 이름을
    몰라도(모든 커넥터에 공용) 항상 안전하다.
    2차 방어(계약 정합): logging_config._PII_PATTERNS(serviceKey=/apiKey=/authKey= 등)를
    재사용해, 쿼리스트링 형태가 아닌 위치(헤더 로그 등)에 실린 키도 함께 잡는다. 로그와
    저장소가 "같은 비밀 판정 규칙"을 공유하게 되어 계약이 갈라지지 않는다.
    """
    if not message:
        return message
    scrubbed = _URL_QUERY_STRIP.sub(r"\1?***", message)
    try:
        from apps.api.logging_config import _PII_PATTERNS

        for pattern, replacement in _PII_PATTERNS:
            scrubbed = pattern.sub(replacement, scrubbed)
    except Exception:  # noqa: BLE001 — 로그마스킹 모듈 부재/구조변경 시에도 1차 방어는 이미 적용됨.
        pass
    return scrubbed


# ══════════════════════════════════════════════════════════════════════════
# 영속 — 런타임 스키마 보강(analysis_ledger_service._ensure 동형·그린필드 금지)
# ══════════════════════════════════════════════════════════════════════════
_DDL = (
    "CREATE TABLE IF NOT EXISTS source_snapshots ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  source_id text NOT NULL,"
    "  source_name text,"
    "  authority_grade text,"
    "  fetched_at timestamptz NOT NULL DEFAULT now(),"
    "  observed_at timestamptz,"
    "  request_fingerprint text NOT NULL,"
    "  checksum text NOT NULL,"
    "  payload_bytes bytea,"
    "  payload_truncated boolean NOT NULL DEFAULT false,"
    "  status text NOT NULL,"
    "  http_status int,"
    "  error_message text,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
# 보존기간(retention_policy)·정리(prune) 정책은 이번 1차에서 컬럼/함수 없이 보류한다
# (위 모듈독스트링 ★용량 방어 참고 — #415 교훈: 소비처 최대 조회 윈도우가 정해진 뒤
# analysis_ledger_quota류 패턴으로 한 번에 추가).
_IDX: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_source_snapshots_checksum "
    "ON source_snapshots(checksum)",
    "CREATE INDEX IF NOT EXISTS idx_source_snapshots_fingerprint "
    "ON source_snapshots(request_fingerprint, fetched_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_source_snapshots_source_status "
    "ON source_snapshots(source_id, status, fetched_at DESC)",
)


# 프로세스-로컬 1회화 플래그(design_run_job._JOB_SCHEMA_READY 동형) — 첫 확인 이후에는
# to_regclass DB 왕복 자체를 생략한다.
_SCHEMA_READY = False


async def _ensure(db: Any) -> None:
    """테이블 보장(멱등) — 프로세스-로컬 플래그로 1회화 + 최초생성 advisory lock.

    ★정정(R1 MEDIUM): 이전 주석은 "advisory lock 이중검사(double-checked locking)"라 적었지만
    실제로는 매 호출마다 to_regclass DB 왕복을 했다(이중검사가 아니라 매번 확인). 이제는
    모듈 전역 _SCHEMA_READY를 1차 방어로 둬 최초 확인 이후엔 DB 왕복 자체를 생략한다.
    advisory lock은 "테이블이 아직 없어 최초 생성해야 하는" 드문 경로에서만(동시 최초생성
    경합 직렬화) 쓰인다 — analysis_ledger_service._ensure의 advisory lock과 동일 역할.

    ★1회화가 새로 만든 위험과 그 봉합: get_by_checksum/get_by_request_fingerprint 같은
    읽기전용 호출부는 이후 db.commit()을 하지 않는다. 만약 여기서 DDL만 실행하고 커밋하지
    않으면, 세션 종료 시 암묵적 롤백으로 방금 만든 테이블이 사라지는데 _SCHEMA_READY만
    True로 남아 "존재한다고 착각"하는 상태가 된다(이후 모든 호출이 DB 왕복 없이 스킵되며
    실패). 그래서 생성 분기에서는 반드시 여기서 즉시 commit한다(design_run_job.
    _ensure_job_schema 동형 — 그 함수도 자기 안에서 commit 후 READY 플래그를 세운다).
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    from sqlalchemy import text

    exists = (await db.execute(text(
        "SELECT to_regclass('source_snapshots') IS NOT NULL"))).scalar()
    if exists:
        _SCHEMA_READY = True
        return
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('source_snapshots_ddl')::bigint)"))
    await db.execute(text(_DDL))
    for ix in _IDX:
        await db.execute(text(ix))
    await db.commit()  # ★생성 직후 즉시 커밋(위 독스트링 참고) — 읽기전용 호출부에서도 안전.
    _SCHEMA_READY = True


async def _persist(
    *,
    source_id: str,
    method: str,
    url: str,
    params: dict[str, Any] | None,
    status: str,
    payload_bytes: bytes | None,
    http_status: int | None,
    source_name: str | None,
    authority_grade: str | None,
    observed_at: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    """실제 INSERT — 예외를 호출부로 그대로 전파한다(흡수 책임은 safe_record_* 가 진다)."""
    from sqlalchemy import text

    from app.core.database import async_session_factory

    fingerprint = build_request_fingerprint(method, url, params)
    # ★무결성 계약: checksum은 절단 "전" 원문 전체 기준으로 계산한다 — 저장 상한 때문에
    #   실제 저장된 payload_bytes와 checksum 재계산 결과가 달라질 수 있음을 payload_truncated로
    #   구분해서 알린다(정직 표기, checksum 자체를 편법으로 재계산해 맞추지 않는다).
    checksum = compute_checksum(payload_bytes)
    stored_payload, was_truncated = truncate_payload(payload_bytes)

    async with async_session_factory() as db:
        await _ensure(db)
        res = await db.execute(text(
            "INSERT INTO source_snapshots"
            "(source_id, source_name, authority_grade, observed_at, request_fingerprint,"
            " checksum, payload_bytes, payload_truncated, status, http_status, error_message)"
            " VALUES (:sid,:sname,:agrade,:obs,:fp,:ch,:pb,:trunc,:st,:hs,:err)"
            " RETURNING id, fetched_at"
        ), {
            "sid": source_id, "sname": source_name, "agrade": authority_grade,
            "obs": observed_at, "fp": fingerprint, "ch": checksum,
            "pb": stored_payload, "trunc": was_truncated, "st": status,
            # ★R1 HIGH: error_message는 저장 직전 이 한 곳에서만 스크러빙한다(공용화) —
            #   호출부(base_client·g2b_client)가 str(exc)를 그대로 넘겨도 여기서 안전해진다.
            "hs": http_status, "err": (scrub_error_message(error_message) or "")[:2000] or None,
        })
        row = res.first()
        await db.commit()
        return {
            "ok": True,
            "id": str(row[0]) if row else None,
            "fetched_at": str(row[1]) if row else None,
            "checksum": checksum,
            "request_fingerprint": fingerprint,
            "payload_truncated": was_truncated,
            "status": status,
        }


async def safe_record_success(
    *,
    source_id: str,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    payload_bytes: bytes | None = None,
    http_status: int | None = None,
    source_name: str | None = None,
    authority_grade: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any] | None:
    """성공 응답 스냅샷을 status=OK로 기록한다(best-effort).

    ★계약 핵심: 어떤 예외가 나도 호출경로로 전파하지 않고 None만 반환한다 — 이 함수의
    실패가 외부 API 수집 자체를 막아서는 절대 안 된다.
    """
    try:
        return await _persist(
            source_id=source_id, method=method, url=url, params=params,
            status=STATUS_OK, payload_bytes=payload_bytes, http_status=http_status,
            source_name=source_name, authority_grade=authority_grade,
            observed_at=observed_at, error_message=None,
        )
    except Exception as e:  # noqa: BLE001 — 기록 실패가 수집 호출경로를 절대 막으면 안 됨.
        # ★R1 MEDIUM: debug→warning — 조회 실패(get_by_*)는 이미 warning인데 "쓰기" 실패가
        #   더 낮은 debug였던 역전을 해소한다(무음 skip 금지 원칙 — 감사기록 유실은 조용히
        #   넘어갈 사안이 아니다).
        logger.warning("SourceSnapshot 기록 실패(성공응답)", source_id=source_id, err=str(e)[:160])
        return None


async def safe_record_dead_letter(
    *,
    source_id: str,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    payload_bytes: bytes | None = None,
    http_status: int | None = None,
    source_name: str | None = None,
    authority_grade: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    """실패 응답(재시도 소진)을 status=DEAD_LETTER로 기록한다(best-effort, 예외 흡수)."""
    try:
        return await _persist(
            source_id=source_id, method=method, url=url, params=params,
            status=STATUS_DEAD_LETTER, payload_bytes=payload_bytes, http_status=http_status,
            source_name=source_name, authority_grade=authority_grade,
            observed_at=None, error_message=error_message,
        )
    except Exception as e:  # noqa: BLE001 — R1 MEDIUM: debug→warning(위 safe_record_success 동일 사유).
        logger.warning("SourceSnapshot 기록 실패(dead-letter)", source_id=source_id, err=str(e)[:160])
        return None


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "source_id": row[1],
        "status": row[2],
        "http_status": row[3],
        "fetched_at": str(row[4]) if row[4] else None,
        "observed_at": str(row[5]) if row[5] else None,
        "payload_truncated": bool(row[6]),
        "checksum": row[7],
        "request_fingerprint": row[8],
    }


_SELECT_COLS = (
    "id, source_id, status, http_status, fetched_at, observed_at,"
    " payload_truncated, checksum, request_fingerprint"
)


async def get_by_checksum(checksum: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """checksum으로 스냅샷을 조회한다(감사용). 실패 시 빈 리스트(무날조)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(
                f"SELECT {_SELECT_COLS} FROM source_snapshots"
                " WHERE checksum = :ch ORDER BY fetched_at DESC LIMIT :lim"
            ), {"ch": checksum, "lim": limit})).all()
            return [_row_to_dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("SourceSnapshot checksum 조회 실패", err=str(e)[:160])
        return []


async def get_by_request_fingerprint(fingerprint: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """request_fingerprint로 스냅샷을 조회한다(감사용 — 같은 요청 반복 이력 추적)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(
                f"SELECT {_SELECT_COLS} FROM source_snapshots"
                " WHERE request_fingerprint = :fp ORDER BY fetched_at DESC LIMIT :lim"
            ), {"fp": fingerprint, "lim": limit})).all()
            return [_row_to_dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("SourceSnapshot fingerprint 조회 실패", err=str(e)[:160])
        return []
