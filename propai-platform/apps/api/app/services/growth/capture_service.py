"""자가성장 엔진 — 이벤트 수집 코어(논블로킹 큐 + 배치 적재).

설계서 §3.2/§4. 요청경로 지연을 최소화하기 위해 미들웨어/인터프리터는
record_event() 로 in-memory 큐에 push 만 하고(동기 INSERT 금지), 실제 적재는
Celery 태스크(또는 인프로세스 폴백)가 flush_batch() 로 배치 INSERT 한다.

프라이버시:
- user_id → HMAC-SHA256(GROWTH_HMAC_KEY) → user_hash. 원본 user_id 미저장.
  GROWTH_HMAC_KEY 미설정 시 APP_SECRET_KEY 파생 폴백(둘 다 없으면 익명 처리).
- payload 는 저장 전 PII 마스킹 — 이메일/전화/주민번호 **값 패턴** + 민감 **키**(이름·주소 등). ★주소는 **값 안에서 지워지지 않는다**(2026-08-27 실측 — `_mask_str` 에 주소 정규식 없음). 부채는 `tests/test_pii_mask_diagnostic_keys.py` 의 xfail 로 초록 안에 보인다.

멱등: event_id(uuid) 가 있으면 INSERT ... ON CONFLICT(event_id) DO NOTHING.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from collections import deque
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

# ── in-memory 큐(프로세스 로컬, 논블로킹). maxlen 으로 폭주 시 오래된 것부터 drop. ──
_MAX_QUEUE = 10_000
_QUEUE: deque[dict[str, Any]] = deque(maxlen=_MAX_QUEUE)

#: ★**유실을 센다.** 종전에는 세는 것이 하나도 없었다(전수 확인 — 이 파일에 계수기 0건).
#:
#:   그래서 *"성장루프 데이터가 얼마나 사라졌나"* 에 **아무도 답할 수 없었다.**
#:   하류 전체(인사이트·자가치유·효과기 발화 표면)가 `platform_events` 의 **완전성을 가정**하는데,
#:   그 가정이 참인지 거짓인지 판별할 관측이 없었다.
#:
#:   ★침묵은 성공이 아니다 — 유실이 0인 것과 유실을 **안 세는 것**은 다른 사실이다.
_STATS: dict[str, int] = {
    # 큐가 가득 차 **가장 오래된 것이 밀려난** 수(deque maxlen 동작).
    "dropped_overflow": 0,
    # flush 가 반복 실패해 **포기하고 버린** 수(아래 _MAX_FLUSH_RETRY 참조).
    "dropped_after_retry": 0,
    # flush 실패 후 **큐로 되돌린** 수(유실이 아니다 — 구별해서 센다).
    "requeued": 0,
    # flush 시도가 실패한 횟수.
    "flush_failures": 0,
    # 정상 적재된 누계(분모 — 이게 없으면 유실률을 말할 수 없다).
    "flushed": 0,
    # ★취소(`CancelledError`)로 중단됐다가 되돌린 수 — 종료 경로가 잃지 않았음을 보이는 값.
    "cancelled_requeued": 0,
}

#: 같은 배치가 이 횟수를 넘게 실패하면 **포기하고 버린다**(계수와 함께).
#:
#:   ★왜 무한 재시도가 아닌가: 행 자체가 잘못돼(스키마 위반 등) 영원히 실패하면
#:   그 배치가 큐 앞을 막아 **새 이벤트가 영영 못 들어간다**. 한 배치를 지키려다
#:   전체를 잃는다. 그래서 상한을 두되 **버린 사실을 센다**.
#:   ★반대로 상한을 1 로 두면 종전과 같아진다(일시적 DB 장애에 즉시 유실).
_MAX_FLUSH_RETRY = 12

#: 연속 실패 횟수(프로세스 로컬). 성공하면 0 으로.
_consecutive_failures = 0

# 1회 배치 INSERT 상한(과도한 단일 트랜잭션 방지).
_FLUSH_LIMIT = 500

#: 인프로세스 flush 루프의 주기(초) — `main.py` 의 `_growth_flush_loop` 와 **짝이다**.
#:   ★이 둘이 갈리면 `max_sustained_per_sec` 이 거짓이 된다. 락이 두 값을 대조한다.
_FLUSH_INTERVAL_S = 5

# user_hash 캐시(같은 user_id 반복 해시 비용 절감, 프로세스 로컬).
_HASH_CACHE: dict[str, str] = {}

# ★**진단 전용 안전 키(정확일치)** — `_PII_KEYS` 부분일치보다 **먼저** 본다.
#
# 왜 필요한가(2026-08-27 실측 · 원본 함수를 그대로 실행해 확인): `_PII_KEYS` 에 `"name"` 이 있고
# 판정이 **부분일치**(`p in key_l`)라 **`"name" in "filename"` 이 참**이다. 그래서 조기 오류 포착이
# 애써 싣는 `filename` 이 **적재 시점에 `[redacted]`** 되어 왔다 — 진단 불가는 그 자체로 장애다.
# 프론트가 보내는 payload 키를 파생형으로 전수(**15개** — `trackEvent(` 호출 인자 + `TrackEventProps`
# 반환 함수 두 축) 태운 결과 위양성은 **이 하나**였다.
# ★초판 주석은 **23** 이라고 적었는데 그것은 **폐기된 수집 축**(파일 전체의 `payload:`)의 값이라
#   재현되지 않았다 — 독립 리뷰가 적발했다. **주석에 박힌 거짓은 후임이 재검증하지 않고 신뢰한다.**
#
# ★**부분일치를 「토큰경계 일치」로 바꾸는 것이 가장 먼저 떠오르는 처방인데, 실측으로 기각했다.**
#   위양성은 12/16 → 8/16 로만 줄고 **PII 누출을 5건 새로 만든다** —
#   `username`·`firstname`·`lastname`·`nickname`·`realname` 이 전부 통과로 바뀐다(단일 토큰이라
#   `"name"` 과 토큰 일치하지 않는다). **매처를 약화시키지 않는다.** 미지의 키는 계속 fail-safe 로
#   redact 하고, **실측으로 확인된 진단 키만** 정확일치로 면제한다.
#   → 이 결정은 `tests/test_pii_mask_diagnostic_keys.py` 가 잠근다(그 5개 키의 redact 를 못 박아,
#     누가 나중에 매처를 "개선"하면 즉시 빨개진다).
#
# ★한계(정직): 이 목록은 **프론트 이벤트 모집단**에서 파생했다. `learning_loop._summarize_payload`
#   가 태우는 `analysis_ledger` payload 키 모집단은 **미측정**이므로 거기엔 아직 위양성이 남아 있을 수 있다.
_DIAGNOSTIC_SAFE_KEYS = frozenset({"filename"})

# payload 에서 마스킹할 민감 키(부분일치, 소문자 비교).
_PII_KEYS = (
    "email", "phone", "tel", "mobile", "name", "addr", "address", "jumin",
    "ssn", "resident", "rrn", "owner", "contact", "birth", "passport",
)

# 값 내부 PII 패턴(문자열 값에 적용).
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RE_PHONE = re.compile(r"\b01[0-9][-\s]?\d{3,4}[-\s]?\d{4}\b")
_RE_RRN = re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")  # 주민등록번호
_REDACTED = "[redacted]"

# 이벤트가 허용하는 화이트리스트 컬럼(그 외 키는 payload 로 흡수하지 않고 버림).
_EVENT_COLS = (
    "event_id", "tenant_id", "user_hash", "session_id", "event_type", "surface",
    "route", "status_code", "latency_ms", "severity", "service", "payload",
    "app_version", "created_at",
)


def _hmac_key() -> bytes | None:
    """HMAC 키 바이트. GROWTH_HMAC_KEY → APP_SECRET_KEY 파생 폴백 순."""
    raw = os.getenv("GROWTH_HMAC_KEY") or ""
    if not raw:
        app_secret = os.getenv("APP_SECRET_KEY") or ""
        if app_secret:
            # APP_SECRET_KEY 에서 도메인 분리 파생(전용 키와 충돌 방지).
            raw = hashlib.sha256(("growth:" + app_secret).encode("utf-8")).hexdigest()
    return raw.encode("utf-8") if raw else None


def hash_user_id(user_id: str | None) -> str | None:
    """user_id 를 HMAC-SHA256 으로 익명화. 키/입력 없으면 None(익명)."""
    if not user_id:
        return None
    cached = _HASH_CACHE.get(user_id)
    if cached is not None:
        return cached
    key = _hmac_key()
    if key is None:
        return None
    digest = hmac.new(key, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if len(_HASH_CACHE) < 50_000:
        _HASH_CACHE[user_id] = digest
    return digest


def _mask_str(value: str) -> str:
    """문자열 값 내부의 이메일/전화/주민번호 패턴을 치환."""
    if not value:
        return value
    out = _RE_EMAIL.sub(_REDACTED, value)
    out = _RE_PHONE.sub(_REDACTED, out)
    out = _RE_RRN.sub(_REDACTED, out)
    return out


def _mask_diagnostic(value: Any, _depth: int) -> Any:
    """면제된 **진단 키의 값**을 그래도 한 번 더 거른다 — 면제는 「무검사」가 아니다.

    ★왜(2026-08-27 독립 적대 리뷰 실측): `filename` 은 **인라인 스크립트 오류에서 문서 URL 전체**가
    된다(`ErrorEvent.filename` 실측 — 헤드리스 브라우저로 확인). 그리고 이 앱은 **지번을 쿼리에**
    싣는다(`LandScheduleClient.tsx:460` — `registry-analysis?addr=${encodeURIComponent(jibun)}`).
    즉 면제를 그냥 통과시키면 **지번·이메일·전화가 평문으로 적재**된다.

    ★더 나쁜 것: **퍼센트 인코딩이 `_mask_str` 의 정규식을 전부 비켜 간다**
    (`hong%40corp.co.kr` 는 이메일 정규식에 안 걸린다). 그래서 두 겹으로 막는다 —

      ① URL 이면 **쿼리·프래그먼트를 통째로 버린다.** 진단 목적(어느 파일에서 났나)에는
         **경로만으로 충분**하므로 이 절단은 목적을 훼손하지 않는다.
      ② 남은 문자열을 **퍼센트 디코드해서** 검사한다. 디코드본에 PII 패턴이 있으면 통째로 버린다
         (원본에서 지우려 하면 인코딩 경계가 어긋나 부분 노출이 남는다).
    """
    if not isinstance(value, str):
        return mask_pii(value, _depth)
    out = value
    if "://" in out or out.startswith("/"):
        parts = urlsplit(out)
        out = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    decoded = unquote(out)
    if _mask_str(decoded) != decoded:
        return _REDACTED
    return _mask_str(out)


def mask_pii(obj: Any, _depth: int = 0) -> Any:
    """payload 의 PII 를 재귀 마스킹한다.

    - `_DIAGNOSTIC_SAFE_KEYS`(정확일치)는 면제 — 진단 전용 키가 부분일치에 걸리는 위양성을 막는다.
    - 민감 키(_PII_KEYS 부분일치)의 값은 통째로 [redacted].
    - 그 외 문자열 값은 내부 패턴(이메일/전화/주민번호)만 치환.
    - dict/list 재귀(과도한 깊이는 방어적으로 중단).
    """
    if _depth > 8:
        return _REDACTED
    if isinstance(obj, dict):
        masked: dict[str, Any] = {}
        for k, v in obj.items():
            key_l = str(k).lower()
            # ★정확일치 안전 키가 부분일치보다 **먼저**다(위 `_DIAGNOSTIC_SAFE_KEYS` 주석 참조).
            if key_l in _DIAGNOSTIC_SAFE_KEYS:
                masked[k] = _mask_diagnostic(v, _depth + 1)
            elif any(p in key_l for p in _PII_KEYS):
                masked[k] = _REDACTED
            else:
                masked[k] = mask_pii(v, _depth + 1)
        return masked
    if isinstance(obj, (list, tuple)):
        return [mask_pii(v, _depth + 1) for v in obj]
    if isinstance(obj, str):
        return _mask_str(obj)
    return obj


def record_event(event_type: str, props: dict[str, Any] | None = None) -> None:
    """이벤트를 in-memory 큐에 논블로킹 push 한다(동기 INSERT 없음).

    props 에 user_id 가 있으면 즉시 user_hash 로 익명화하고 user_id 는 버린다.
    payload 는 PII 마스킹 후 저장. 어떤 예외도 호출경로로 전파하지 않는다.
    """
    try:
        props = dict(props or {})
        # user_id → user_hash 익명화(원본 미저장).
        uid = props.pop("user_id", None)
        if uid is not None and not props.get("user_hash"):
            props["user_hash"] = hash_user_id(str(uid))
        # payload PII 마스킹.
        if props.get("payload") is not None:
            props["payload"] = mask_pii(props["payload"])
        # 화이트리스트 컬럼만 보존.
        row = {k: props.get(k) for k in _EVENT_COLS}
        row["event_type"] = event_type
        if row.get("created_at") is None:
            row["created_at"] = datetime.now(UTC)
        # ★밀려나는 것을 **센다** — `deque(maxlen=)` 은 조용히 버린다.
        if len(_QUEUE) == _MAX_QUEUE:
            _STATS["dropped_overflow"] += 1
        _QUEUE.append(row)
    except Exception as e:  # noqa: BLE001 — 수집은 절대 호출경로를 깨뜨리면 안 됨.
        logger.debug("growth record_event 무시: %s", str(e)[:120])


def record_fallback(service: str, kind: str, *, severity: str = "warn", **meta: Any) -> None:
    """폴백/장애 이벤트 기록(C3) — 자가치유 루프(healing_rules.py)가 구독하는 공용 계약.

    healing_rules._collect_candidates가 구독하는 계약: event_type='fallback', service 컬럼,
    payload.kind. kind='ledger_broken' + severity='critical'는 원장 변조탐지(재분석 제안) 브랜치를
    발동시키고, 그 외 kind는 severity 무관하게 서비스별 10분 윈도 circuit-observe 집계에 잡힌다
    (healing_rules.py:198~224 실측). severity 기본값은 'warn'(단순 관측), 원장 변조 등 중대 신호는
    호출측이 severity='critical'로 명시해야 한다.

    record_event와 동일하게 best-effort — 어떤 예외도 호출경로로 전파하지 않는다(치유루프 관측
    실패가 주경로(엔진 호출·원장 검증 등)를 방해해서는 안 된다).
    """
    try:
        record_event("fallback", {"service": service, "severity": severity,
                                  "payload": {"kind": kind, **meta}})
    except Exception as e:  # noqa: BLE001 — 이중 방어(record_event 자체도 이미 삼킴)
        logger.debug("growth record_fallback 무시: %s", str(e)[:120])


def flush_interval_s() -> int:
    """배수 루프의 대기 주기(초). ★소비처가 리터럴을 쓰지 않게 **파생시킨다**.

    `apps/api/main.py` 는 역사적으로 `sleep(5)` 리터럴을 쓰고 그 짝을
    `test_flush_interval_matches_the_actual_loop` 이 소스 대조로 잠근다(그대로 둔다).
    **새로 배선하는 소비처는 이 접근자를 쓴다** — 리터럴을 하나 더 만들지 않는다.
    """
    return _FLUSH_INTERVAL_S


def queue_size() -> int:
    """현재 큐 적재 건수(관측·테스트용)."""
    return len(_QUEUE)


def _drain(limit: int) -> list[dict[str, Any]]:
    """큐에서 최대 limit 건을 꺼낸다(FIFO)."""
    out: list[dict[str, Any]] = []
    while _QUEUE and len(out) < limit:
        out.append(_QUEUE.popleft())
    return out


_INSERT_SQL = """
INSERT INTO platform_events
    (event_id, tenant_id, user_hash, session_id, event_type, surface, route,
     status_code, latency_ms, severity, service, payload, app_version, created_at)
VALUES
    (:event_id, :tenant_id, :user_hash, :session_id, :event_type, :surface, :route,
     :status_code, :latency_ms, :severity, :service, CAST(:payload AS jsonb),
     :app_version, :created_at)
ON CONFLICT (event_id) DO NOTHING
"""


def _requeue(rows: list[dict[str, Any]], *, cancelled: bool) -> None:
    """빼낸 행을 큐 앞으로 **되돌리고 센다** — ★되돌림 경로는 **하나뿐이어야 한다**.

    `flush_batch` 에는 되돌려야 하는 출구가 **셋**이다(취소 · 정리 중 취소 · 평범한 실패).
    셋이 각자 되돌림 루프를 갖고 있으면 **반드시 하나를 빠뜨리고, 그 하나가 곧 무성 유실 경로**다
    — 실제로 그렇게 뚫렸다(정리용 `rollback()` 이 `except Exception` 이라 취소를 안 잡았다).

    FIFO 를 지켜 역순으로 `appendleft` 하고, 큐가 가득이면 밀려나는 것**도 센다**.
    """
    for r in reversed(rows):
        if len(_QUEUE) == _MAX_QUEUE:
            _STATS["dropped_overflow"] += 1
        _QUEUE.appendleft(r)
    _STATS["requeued"] += len(rows)
    if cancelled:
        _STATS["cancelled_requeued"] += len(rows)


async def flush_batch(db, limit: int = _FLUSH_LIMIT) -> int:
    """큐의 이벤트를 platform_events 로 배치 INSERT 한다. 적재 건수 반환.

    event_id 멱등(ON CONFLICT DO NOTHING). best-effort: 실패 시 rollback 후 0.
    """
    import json

    from sqlalchemy import text

    global _consecutive_failures

    rows = _drain(limit)
    if not rows:
        return 0
    params: list[dict[str, Any]] = []
    for r in rows:
        payload = r.get("payload")
        params.append({
            "event_id": str(r["event_id"]) if r.get("event_id") else None,
            "tenant_id": str(r["tenant_id"]) if r.get("tenant_id") else None,
            "user_hash": r.get("user_hash"),
            "session_id": r.get("session_id"),
            "event_type": r.get("event_type"),
            "surface": r.get("surface"),
            "route": r.get("route"),
            "status_code": r.get("status_code"),
            "latency_ms": r.get("latency_ms"),
            "severity": r.get("severity"),
            "service": r.get("service"),
            "payload": json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None,
            "app_version": r.get("app_version"),
            "created_at": r.get("created_at"),
        })
    try:
        await db.execute(text(_INSERT_SQL), params)
        await db.commit()
        _consecutive_failures = 0
        _STATS["flushed"] += len(params)
        return len(params)
    except BaseException as e:
        # ★★**`Exception` 이 아니라 `BaseException` 이다**(독립 적대 리뷰 실측 2026-08-27).
        #
        #   `asyncio.CancelledError` 는 **`BaseException` 전용**이다(3.8+ · 실측 확인).
        #   `main.py:712` 는 종료 시 `_gt.cancel()` 을 **await 없이** 부르고 바로 마지막 flush 를
        #   시도하는데, 그 취소가 `await db.execute(...)` 안에서 배달되면
        #   **`_drain` 이 이미 빼낸 배치가 그대로 사라진다** — 어떤 계수기에도 안 잡힌 채.
        #
        #   ★이 PR 의 논지("조용히 사라지던 것")가 **수리 안에서 그대로 재현**된 자리다.
        #     노출 창은 (INSERT 소요 / 5초)이고 **DB 가 느릴수록 넓어진다** —
        #     즉 큐가 가장 깊을 때 가장 잘 터진다.
        #
        #   → 취소도 **되돌리고 센다.** 다만 취소는 **삼키면 안 되므로** 되돌린 뒤 re-raise 한다.
        if not isinstance(e, Exception):
            _requeue(rows, cancelled=True)
            logger.warning("growth flush_batch 취소 — %d건 되돌림(재전파)", len(rows))
            raise
        # ★★종전에는 여기서 **그대로 잃었다** — `_drain` 이 `popleft()` 로 큐에서 빼낸 뒤라
        #   실패하면 되돌아갈 곳이 없었다. 로그 문구가 그 사실을 그대로 적고 있었다:
        #   *"flush_batch 실패(%d건 유실)"*.
        #
        #   flush 는 5초마다 최대 500건이므로 **10분 DB 장애 = 120회 × 최대 500건**이다.
        #   이 저장소는 그런 길이의 DB 버스트를 실제로 기록했다.
        #
        #   → **되돌린다.** ★단 **무조건 무손실이 아니다**: 재시도 상한(`_MAX_FLUSH_RETRY`)
        #     × flush 주기(`_FLUSH_INTERVAL_S`) = **약 65초** 이내의 장애에서만 무손실이고,
        #     그보다 길면 상한에서 **포기하며 그 사실을 센다**(`dropped_after_retry`).
        #     ★리뷰 실측: 연속 13회(=65초)째에 500건 유실. 위 「10분 장애」 시나리오는
        #     **이 코드로도 잃는다** — 다만 **조용하지 않다**(계수 + logger.error + 화면).
        _consecutive_failures += 1
        _STATS["flush_failures"] += 1
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        except BaseException:
            # ★★**같은 구멍이 정리 경로에 하나 더 있었다**(독립 적대 렌즈 실측 2026-08-28).
            #
            #   위에서 `db.execute()`/`commit()` 의 취소는 `BaseException` 으로 막았는데,
            #   **바로 아래 정리용 `rollback()` 은 `except Exception`** 이라
            #   `CancelledError` 를 **안 잡는다**. 그러면 취소가 여기서 그대로 전파돼
            #   **아래 되돌림을 건너뛴다** — `_drain` 이 이미 빼낸 행이
            #   **어떤 계수기에도 안 잡힌 채** 사라진다.
            #
            #   ★실측(두 모집단 대조 · 큐 300행 중 200행 배치):
            #     rollback 정상 → 사라진 행 **0** · `requeued` 200 · `lost_total` 0
            #     rollback 취소 → 사라진 행 **200** · `requeued` **0** · `lost_total` **0**
            #   ★즉 **계수기끼리는 서로 일치하는데 둘 다 틀렸다.** 화면에는 아무 이상이
            #     안 보인다 — 계수기가 없는 것보다 나쁘다.
            #
            #   ★이 PR 의 논지("조용히 사라지던 것")가 **수리 안에서 두 번째로** 재현된 자리다.
            _requeue(rows, cancelled=True)
            logger.warning("growth flush_batch 정리 중 취소 — %d건 되돌림(재전파)", len(rows))
            raise

        if _consecutive_failures > _MAX_FLUSH_RETRY:
            # ★한 배치가 영원히 실패하면 큐 앞을 막아 **새 이벤트가 영영 못 들어간다**.
            #   한 배치를 지키려다 전체를 잃지 않는다 — 버리되 **센다**.
            _STATS["dropped_after_retry"] += len(rows)
            logger.error(
                "growth flush_batch %d회 연속 실패 — %d건 포기(누계 유실 %d): %s",
                _consecutive_failures, len(rows),
                _STATS["dropped_after_retry"], str(e)[:160],
            )
            _consecutive_failures = 0
            return 0

        # ★FIFO 순서를 지켜 되돌린다(역순 appendleft). 큐가 가득이면 `maxlen` 이
        #   가장 오래된 것을 밀어내는데 **그것도 센다**.
        _requeue(rows, cancelled=False)
        logger.warning(
            "growth flush_batch 실패(%d건 되돌림 · 연속 %d회): %s",
            len(rows), _consecutive_failures, str(e)[:160],
        )
        return 0


async def drain_until_empty(session_factory: Any, *, max_rounds: int = 20) -> int:
    """큐가 빌 때까지 배치 flush 한다. 적재된 총 건수 반환.

    ## ★왜 함수로 빼는가 — **배수 경로가 여럿이면 하나가 빠진다**

    이 루프는 종전에 `apps/api/main.py` **두 곳에 복제**돼 있었고(주기 루프 · 종료 flush),
    상한 `500` 이 **리터럴로 하드코딩**돼 `_FLUSH_LIMIT` 과 따로 놀았다.
    거기에 워커용으로 **세 번째 사본**을 만들면 셋이 갈라진다.

    ★그리고 실제로 **배수구가 아예 없는 프로세스**가 있었다 — `apps/worker`(arq).
      진입점 임포트 폐포(79파일)가 `record_event` 에 **닿는데**(`base_client._emit_growth_fallback`
      → 외부 API 회로차단기 폴백마다 발화) 그 폐포 안에 `flush_batch` 호출은 **0건**이었다.
      즉 워커가 담은 이벤트는 **컨테이너 재시작마다 통째로 사라졌다.**

    ## 계약

    - 큐가 비어 있으면 **세션을 열지 않는다**(빈 커넥션 낭비 방지).
    - 한 회차가 `_FLUSH_LIMIT` **미만**을 적재하면 큐가 마른 것이므로 멈춘다.
    - `max_rounds` 는 **폭주 상한**이다 — 계속 차오르는 큐에 갇히지 않는다.
    - ★상한은 **리터럴이 아니라 `_FLUSH_LIMIT` 에서 파생**된다. 상수를 바꾸면 여기가 따라온다.
    """
    if queue_size() == 0:
        return 0
    total = 0
    async with session_factory() as session:
        for _ in range(max_rounds):
            n = await flush_batch(session)
            total += n
            if n < _FLUSH_LIMIT:
                break
    return total


def capture_status() -> dict[str, Any]:
    """수집 파이프라인의 **건강 상태** — 세기만 하고 아무도 못 보면 같은 결함이다.

    ## 왜 이 함수가 필요한가

    성장루프의 모든 결론(인사이트·자가치유·효과기 발화)은 `platform_events` 의
    **완전성을 가정**한다. 그런데 그 가정이 참인지 거짓인지 판별할 관측이 **하나도 없었다**.

    ★**유실이 0인 것과 유실을 안 세는 것은 다른 사실이다.** 종전에는 둘을 구별할 수 없었다.

    ## 이 값을 어떻게 읽나

    - `queue_depth` 가 `max_queue` 에 가까우면 flush 가 못 따라가고 있다.
      지속 처리량 천장은 **`flush_limit / flush_interval`** 이다(현재 500/5초 = 100건/초).
    - `dropped_overflow` > 0 이면 **이미 잃었다**. ★단 **어느 쪽이 밀려나는지는 경로마다 다르다**:
      · `record_event`(정상 유입) — 오른쪽에 붙이므로 **가장 오래된 것**이 밀려난다
      · 되돌리기(`appendleft`) — 왼쪽에 넣으므로 **가장 새것**이 밀려난다
      같은 계수기로 세지만 **뜻이 다르다**. 종전 문서가 전자만 적어 후자를 가렸다.
    - `dropped_after_retry` > 0 이면 **한 배치를 포기했다** — 그 사유가 로그에 있다.
    - `requeued` 는 **유실이 아니다**(일시 장애에서 되돌린 것). 유실과 뭉치지 않는다.
    - ★`loss_rate_pct` 는 분모가 0 이면 `None` 이다 — **0.0 이 아니다.**
      "잃은 게 없다"와 "아직 아무것도 안 실었다"는 다른 말이다.

    ## ★★이 수치는 **하한**이다 — 과대해석 금지

    `_STATS` 는 **프로세스 로컬**이다:
      · 재시작하면 **0 으로 돌아간다**(누적 이력이 아니다)
      · 워커가 여럿이면 **워커마다 다른 값**을 본다

    → 따라서 **실제 유실 ≥ 여기 보이는 값**이다. `lost_total == 0` 은
      *"이 프로세스가 시작한 뒤로는 못 봤다"* 이지 *"유실이 없었다"* 가 아니다.
      ★이 구분을 놓치면 화면의 「유실 없음」이 **거짓 안심**이 된다.

    (누적을 보려면 `platform_events` 에 유실 이벤트를 적재하는 별도 설계가 필요하다 —
     이 PR 범위 밖이고, 그 사실을 여기 적어 다음 사람이 오해하지 않게 한다.)
    """
    lost = _STATS["dropped_overflow"] + _STATS["dropped_after_retry"]
    denom = _STATS["flushed"] + lost
    return {
        "queue_depth": len(_QUEUE),
        "max_queue": _MAX_QUEUE,
        "flush_limit": _FLUSH_LIMIT,
        # ★지속 처리량 천장 — 이 수를 넘는 유입이 이어지면 큐가 찬다.
        "max_sustained_per_sec": _FLUSH_LIMIT // _FLUSH_INTERVAL_S,
        **{k: v for k, v in _STATS.items()},
        "consecutive_failures": _consecutive_failures,
        "max_flush_retry": _MAX_FLUSH_RETRY,
        # 유실 = 밀려난 것 + 포기한 것. **되돌린 것은 유실이 아니다.**
        "lost_total": lost,
        # ★이 수치가 **프로세스 로컬**이라는 사실을 응답에 싣는다 —
        #   화면이 「유실 없음」을 **어떤 범위에서** 말하는지 밝힐 수 있게.
        "scope": "process_local",
        "loss_rate_pct": round(100.0 * lost / denom, 3) if denom else None,
    }


def _reset_stats_for_test() -> None:
    """테스트 전용 — 프로세스 로컬 카운터를 초기화한다."""
    global _consecutive_failures
    for k in _STATS:
        _STATS[k] = 0
    _consecutive_failures = 0
    _QUEUE.clear()
