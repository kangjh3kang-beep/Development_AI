"""플랫폼 연동 API 키 시크릿 스토어 — DB 암호화 저장 + os.environ 오버레이.

설계:
- 관리자가 화면에서 입력한 키를 `platform_secrets`(DB)에 **Fernet 암호화** 저장.
- 앱 시작 시(lifespan) DB의 키를 복호화해 `os.environ`에 덮어씀(오버레이) → 기존
  공급자 코드(`os.getenv("APICK_CL_AUTH_KEY")` 등)를 **그대로** 두고 즉시 사용.
- 단일 워커(uvicorn --workers 1)라 set/delete 시 같은 프로세스 env를 갱신하면
  **재배포 없이 즉시 반영**된다(billing_config 패턴과 동일 철학).

확장(분류별·항목별 + 사용자 임의추가):
- CATALOG = 자주 쓰는 키(라벨·발급가이드·분류 내장).
- 카탈로그에 없는 키도 **네임+값(+분류/라벨)** 으로 자유 추가 → 향후 코드수정 불필요.
- 위험 인프라 키(DATABASE_URL/시크릿키 등)는 DENYLIST로 차단(잠금사고·DB유출 방지).

보안:
- 평문 키는 DB에 저장하지 않음(Fernet). 마스터키는 `SECRET_STORE_KEY`(우선) 또는
  `APP_SECRET_KEY`에서 결정적 파생(SHA256). 서버 .env의 APP_SECRET_KEY는 고정값이라
  재시작 후에도 복호화 가능.
- 응답에는 절대 평문 노출 안 함 — 설정여부·마스킹 미리보기·출처만 반환.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# ── 자주 쓰는 키 카탈로그(분류·라벨·가이드 내장) ─────────────────────
# secret=True 면 값 마스킹·평문 미노출. select 는 옵션 중 선택(키 아님).
CATALOG: list[dict[str, Any]] = [
    # 등기/부동산 연동
    {"name": "REGISTRY_PROVIDER", "label": "등기 공급자 선택", "group": "등기(부동산등기부)",
     "secret": False, "kind": "select", "options": ["codef", "apick", "tilko"],
     "desc": "등기부등본 조회에 사용할 공급자. apick=건당과금·간편, codef=구조화JSON, tilko=IROS ID로그인·PDF/XML."},
    {"name": "APICK_CL_AUTH_KEY", "label": "apick 인증키(CL_AUTH_KEY)", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "guide_url": "https://apick.app",
     "desc": "apick 등기부 열람/다운로드 API 인증키. 마이페이지에서 발급."},
    {"name": "CODEF_CLIENT_ID", "label": "CODEF Client ID", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "guide_url": "https://codef.io"},
    {"name": "CODEF_CLIENT_SECRET", "label": "CODEF Client Secret", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "guide_url": "https://codef.io"},
    {"name": "CODEF_PUBLIC_KEY", "label": "CODEF Public Key", "group": "등기(부동산등기부)",
     "secret": True, "kind": "textarea", "guide_url": "https://codef.io"},
    {"name": "TILKO_API_KEY", "label": "틸코(Tilko) API Key", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "guide_url": "https://tilko.net"},
    {"name": "IROS_USER_ID", "label": "인터넷등기소 ID", "group": "등기(부동산등기부)",
     "secret": False, "kind": "text"},
    {"name": "IROS_USER_PW", "label": "인터넷등기소 비밀번호", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text"},
    {"name": "IROS_EMONEY_NO1", "label": "인터넷등기소 전자지급 번호1(틸코)", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "desc": "틸코 등기 발급 수수료 결제용 선불전자지급수단 번호1."},
    {"name": "IROS_EMONEY_NO2", "label": "인터넷등기소 전자지급 번호2(틸코)", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "desc": "선불전자지급수단 번호2(있을 경우)."},
    {"name": "IROS_EMONEY_PWD", "label": "인터넷등기소 전자지급 비밀번호(틸코)", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "desc": "선불전자지급수단 비밀번호."},
    {"name": "IROS_PIN", "label": "인터넷등기소 PIN(틸코, 선택)", "group": "등기(부동산등기부)",
     "secret": True, "kind": "text", "desc": "필요 시 PIN(평문 전송 필드)."},
    # 공공데이터/지도
    {"name": "VWORLD_API_KEY", "label": "V-World 인증키", "group": "공공데이터·지도",
     "secret": True, "kind": "text", "guide_url": "https://www.vworld.kr",
     "desc": "부지분석·용도지역·필지·공시지가 핵심 데이터."},
    {"name": "MOLIT_API_KEY", "label": "공공데이터포털 인증키(국토부 실거래/G2B)", "group": "공공데이터·지도",
     "secret": True, "kind": "text", "guide_url": "https://www.data.go.kr",
     "desc": "실거래가·나라장터(G2B) 등 data.go.kr 공통 키."},
    {"name": "KAKAO_REST_API_KEY", "label": "카카오 REST API 키", "group": "공공데이터·지도",
     "secret": True, "kind": "text", "guide_url": "https://developers.kakao.com",
     "desc": "지도/주소 지오코딩(선택)."},
    {"name": "RONE_API_KEY", "label": "한국부동산원 R-ONE 인증키", "group": "공공데이터·지도",
     "secret": True, "kind": "text", "guide_url": "https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do",
     "desc": "지가변동률 등 부동산통계 OpenAPI. 시점수정 실데이터에 사용."},
    {"name": "RONE_LANDPRICE_STATBL_ID", "label": "R-ONE 지가변동률 통계표ID(STATBL_ID)", "group": "공공데이터·지도",
     "secret": False, "kind": "text",
     "desc": "R-ONE 통계표 목록에서 '지가변동률' 통계표 ID. 설정 시 시점수정에 실데이터 적용."},
    {"name": "RONE_HOUSING_STATBL_ID", "label": "R-ONE 주택매매가격지수 통계표ID", "group": "공공데이터·지도",
     "secret": False, "kind": "text",
     "desc": "주택종합 매매가격지수(월 변동률) 통계표 ID. 건물/주택 시점수정 실데이터에 사용."},
    {"name": "RONE_COMMYIELD_STATBL_ID", "label": "R-ONE 상업용 투자수익률 통계표ID", "group": "공공데이터·지도",
     "secret": False, "kind": "text",
     "desc": "상업용부동산 투자수익률(분기) 통계표 ID. 수익환원법 자본환원율(cap rate) 실데이터에 사용."},
    {"name": "RONE_JEONSE_CONV_STATBL_ID", "label": "R-ONE 전월세전환율 통계표ID", "group": "공공데이터·지도",
     "secret": False, "kind": "text",
     "desc": "전월세전환율(월) 통계표 ID. 보증금↔월세 환산(NOI) 실데이터에 사용."},
    # LLM
    {"name": "ANTHROPIC_API_KEY", "label": "Anthropic(Claude) API Key", "group": "AI(LLM)",
     "secret": True, "kind": "text", "guide_url": "https://console.anthropic.com"},
    {"name": "OPENAI_API_KEY", "label": "OpenAI API Key", "group": "AI(LLM)",
     "secret": True, "kind": "text", "guide_url": "https://platform.openai.com"},
]

_CATALOG_BY_NAME = {c["name"]: c for c in CATALOG}
_CUSTOM_GROUP = "사용자 추가"

# 환경변수명 규칙 + 위험 인프라 키 차단(잠금사고·DB유출 방지)
_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_DENYLIST = {
    "DATABASE_URL", "DATABASE_URL_ASYNC", "APP_SECRET_KEY", "JWT_SECRET_KEY",
    "SECRET_STORE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_PASSWORD",
    "POSTGRES_PASSWORD", "REDIS_URL", "PATH", "PYTHONPATH", "HOME",
}


def is_allowed(name: str) -> bool:
    """관리 허용 키인지 — env명 규칙 충족 + 위험 인프라 키 아님."""
    name = (name or "").strip()
    return bool(_NAME_RE.match(name)) and name.upper() not in _DENYLIST

_DDL = (
    "CREATE TABLE IF NOT EXISTS platform_secrets ("
    "name text PRIMARY KEY, value_enc text NOT NULL, "
    "label text, group_name text, is_secret boolean DEFAULT true, "
    "updated_at timestamptz DEFAULT now(), updated_by text)"
)
# 기존 테이블(구버전) 보강 — 신규 메타 컬럼 멱등 추가
_ALTERS = [
    "ALTER TABLE platform_secrets ADD COLUMN IF NOT EXISTS label text",
    "ALTER TABLE platform_secrets ADD COLUMN IF NOT EXISTS group_name text",
    "ALTER TABLE platform_secrets ADD COLUMN IF NOT EXISTS is_secret boolean DEFAULT true",
]

# 시작 시 .env 원본값 스냅샷(삭제 시 baseline 복원용)
_ENV_BASELINE: dict[str, str | None] = {}
_BASELINE_CAPTURED = False


async def _ensure_table(db: AsyncSession) -> None:
    await db.execute(text(_DDL))
    for a in _ALTERS:
        try:
            await db.execute(text(a))
        except Exception:  # noqa: BLE001 — 권한/구버전 PG 폴백
            pass
    await db.commit()


def _fernet():
    from cryptography.fernet import Fernet

    raw = os.getenv("SECRET_STORE_KEY")
    if raw:
        key = raw.encode()
    else:
        base = (os.getenv("APP_SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
                or "propai-secret-store-fallback").encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(base).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception as e:  # noqa: BLE001
        logger.warning("시크릿 복호화 실패(마스터키 변경 가능성)", err=str(e)[:80])
        return None


def _capture_baseline() -> None:
    global _BASELINE_CAPTURED
    if _BASELINE_CAPTURED:
        return
    for n in _CATALOG_BY_NAME:
        _ENV_BASELINE[n] = os.environ.get(n)
    _BASELINE_CAPTURED = True


def _mask(value: str) -> str:
    v = value.strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "•" * len(v)
    return f"{v[:3]}{'•' * 6}{v[-3:]}"


async def load_into_env(db: AsyncSession) -> int:
    """DB의 시크릿을 복호화해 os.environ 에 오버레이(앱 시작 시 1회). 적용 개수 반환."""
    _capture_baseline()
    n = 0
    try:
        await _ensure_table(db)
        rows = (await db.execute(text("SELECT name, value_enc FROM platform_secrets"))).all()
        for name, enc in rows:
            if not is_allowed(name):
                continue
            val = _decrypt(enc)
            if val is not None:
                os.environ[name] = val
                n += 1
    except Exception as e:  # noqa: BLE001
        logger.warning("시크릿 env 로드 실패", err=str(e)[:120])
    if n:
        logger.info("플랫폼 시크릿 env 오버레이 적용", count=n)
    return n


async def list_status(db: AsyncSession) -> list[dict[str, Any]]:
    """카탈로그 + 사용자추가 키를 분류별로 — 설정여부·마스킹·출처(평문 미노출)."""
    _capture_baseline()
    db_rows: dict[str, Any] = {}
    try:
        await _ensure_table(db)
        for name, enc, label, grp, is_sec, upd, by in (
            await db.execute(text(
                "SELECT name, value_enc, label, group_name, is_secret, updated_at, updated_by "
                "FROM platform_secrets"))
        ).all():
            db_rows[name] = {"enc": enc, "label": label, "group": grp,
                             "is_secret": is_sec, "updated_at": upd, "updated_by": by}
    except Exception as e:  # noqa: BLE001
        logger.warning("시크릿 목록 조회 실패", err=str(e)[:120])

    def _entry(name: str, cat: dict[str, Any] | None) -> dict[str, Any]:
        cur = os.environ.get(name) or ""
        in_db = name in db_rows
        dbr = db_rows.get(name, {})
        secret = bool(cat["secret"]) if cat else bool(dbr.get("is_secret", True))
        source = "db" if in_db else ("env" if cur else "none")
        masked = (cur if not secret else _mask(cur)) if cur else ""
        item = {
            "name": name,
            "label": (cat["label"] if cat else (dbr.get("label") or name)),
            "group": (cat["group"] if cat else (dbr.get("group") or _CUSTOM_GROUP)),
            "secret": secret,
            "kind": (cat.get("kind", "text") if cat else "text"),
            "options": (cat.get("options") if cat else None),
            "desc": (cat.get("desc") if cat else None),
            "guide_url": (cat.get("guide_url") if cat else None),
            "custom": cat is None,
            "is_set": bool(cur) or in_db,
            "source": source, "masked": masked,
        }
        if in_db:
            item["updated_at"] = dbr["updated_at"].isoformat() if dbr.get("updated_at") else None
            item["updated_by"] = dbr.get("updated_by")
        return item

    out = [_entry(c["name"], c) for c in CATALOG]
    # 카탈로그에 없는 사용자추가 키
    for name in db_rows:
        if name not in _CATALOG_BY_NAME and is_allowed(name):
            out.append(_entry(name, None))
    return out


async def set_secret(
    db: AsyncSession, name: str, value: str, updated_by: str | None,
    *, label: str | None = None, group: str | None = None, secret: bool | None = None,
) -> None:
    """키 입력/수정 — DB 암호화 저장 + 현재 프로세스 env 갱신(즉시 반영).

    카탈로그 키는 라벨/분류/비밀여부를 카탈로그값으로 강제, 사용자추가 키는 인자 사용.
    """
    name = (name or "").strip()
    if not is_allowed(name):
        raise ValueError(f"허용되지 않는 키 이름입니다: {name} (영대문자/숫자/_ 만, 보호키 제외)")
    value = (value or "").strip()
    if not value:
        raise ValueError("값이 비어 있습니다.")

    cat = _CATALOG_BY_NAME.get(name)
    if cat:
        f_label, f_group, f_secret = cat["label"], cat["group"], bool(cat["secret"])
    else:
        f_label = (label or name).strip()
        f_group = (group or _CUSTOM_GROUP).strip()
        f_secret = True if secret is None else bool(secret)

    await _ensure_table(db)
    enc = _encrypt(value)
    await db.execute(
        text("INSERT INTO platform_secrets(name, value_enc, label, group_name, is_secret, updated_at, updated_by) "
             "VALUES (:n, :v, :l, :g, :s, now(), :by) "
             "ON CONFLICT (name) DO UPDATE SET value_enc=:v, label=:l, group_name=:g, "
             "is_secret=:s, updated_at=now(), updated_by=:by"),
        {"n": name, "v": enc, "l": f_label, "g": f_group, "s": f_secret, "by": updated_by},
    )
    await db.commit()
    os.environ[name] = value  # 즉시 반영


async def delete_secret(db: AsyncSession, name: str) -> None:
    """키 삭제 — DB 삭제 + env 를 .env 원본(baseline)으로 복원(없으면 제거)."""
    name = (name or "").strip()
    if not is_allowed(name):
        raise ValueError(f"허용되지 않는 키 이름입니다: {name}")
    _capture_baseline()
    await _ensure_table(db)
    await db.execute(text("DELETE FROM platform_secrets WHERE name=:n"), {"n": name})
    await db.commit()
    base = _ENV_BASELINE.get(name)
    if base is not None and base != "":
        os.environ[name] = base
    else:
        os.environ.pop(name, None)
