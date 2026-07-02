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
import contextlib
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
    {"name": "ONBID_SERVICE_KEY", "label": "온비드(KAMCO 공매) OpenAPI 인증키", "group": "공공데이터·지도",
     "secret": True, "kind": "text", "guide_url": "https://www.data.go.kr",
     "desc": "한국자산관리공사 온비드 공매물건 API. 미설정 시 G2B/MOLIT 공용키 폴백→그래도 없으면 mock."},
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
    {"name": "REPLICATE_API_TOKEN", "label": "Replicate API 토큰(AI 포토리얼 렌더)", "group": "AI(LLM)",
     "secret": True, "kind": "text", "guide_url": "https://replicate.com/account/api-tokens",
     "desc": "3D 뷰포트→포토리얼 렌더(ControlNet) 생성에 사용. "
             "미설정 시 렌더 메뉴는 정직하게 '키 미설정' 안내(가짜 이미지 없음)."},
    # 인증·소셜 로그인(카카오 등) — 변경 시 백엔드 재시작 후 반영(pydantic Settings 캐시).
    {"name": "KAKAO_REST_API_KEY", "label": "카카오 REST API 키(로그인 client_id)", "group": "인증·소셜",
     "secret": True, "kind": "text", "guide_url": "https://developers.kakao.com"},
    {"name": "KAKAO_REDIRECT_URI", "label": "카카오 로그인 Redirect URI", "group": "인증·소셜",
     "secret": False, "kind": "text", "guide_url": "https://developers.kakao.com"},
    {"name": "KAKAO_CLIENT_SECRET", "label": "카카오 Client Secret(보안 사용 시)", "group": "인증·소셜",
     "secret": True, "kind": "text", "guide_url": "https://developers.kakao.com"},
    {"name": "KAKAO_DEFAULT_ADMIN_KEY", "label": "카카오 어드민 키(회원관리 등)", "group": "인증·소셜",
     "secret": True, "kind": "text", "guide_url": "https://developers.kakao.com"},
    {"name": "KAKAO_JS_KEY", "label": "카카오 JavaScript 키(지도/SDK, 공개)", "group": "인증·소셜",
     "secret": False, "kind": "text", "guide_url": "https://developers.kakao.com"},
    {"name": "GOOGLE_CLIENT_ID", "label": "구글 OAuth Client ID(로그인)", "group": "인증·소셜",
     "secret": True, "kind": "text", "guide_url": "https://console.cloud.google.com/apis/credentials",
     "desc": "구글 소셜 로그인 client_id. Google Cloud Console > 사용자 인증 정보에서 OAuth 클라이언트 발급."},
    {"name": "GOOGLE_CLIENT_SECRET", "label": "구글 OAuth Client Secret", "group": "인증·소셜",
     "secret": True, "kind": "text", "guide_url": "https://console.cloud.google.com/apis/credentials"},
    {"name": "GOOGLE_REDIRECT_URI", "label": "구글 로그인 Redirect URI", "group": "인증·소셜",
     "secret": False, "kind": "text", "guide_url": "https://console.cloud.google.com/apis/credentials"},
    {"name": "NAVER_CLIENT_ID", "label": "네이버 OAuth Client ID(로그인)", "group": "인증·소셜",
     "secret": True, "kind": "text", "guide_url": "https://developers.naver.com/apps",
     "desc": "네이버 소셜 로그인 client_id. 네이버 개발자센터 > 애플리케이션 등록에서 발급."},
    {"name": "NAVER_CLIENT_SECRET", "label": "네이버 OAuth Client Secret", "group": "인증·소셜",
     "secret": True, "kind": "text", "guide_url": "https://developers.naver.com/apps"},
    {"name": "NAVER_REDIRECT_URI", "label": "네이버 로그인 Redirect URI", "group": "인증·소셜",
     "secret": False, "kind": "text", "guide_url": "https://developers.naver.com/apps"},
    # 스토리지·기타 통합(서비스롤/DB비번은 DENYLIST로 차단 — 공개·URL 키만 관리)
    {"name": "SUPABASE_URL", "label": "Supabase 프로젝트 URL", "group": "스토리지·기타",
     "secret": False, "kind": "text", "guide_url": "https://supabase.com/dashboard"},
    {"name": "SUPABASE_ANON_KEY", "label": "Supabase anon 키(공개)", "group": "스토리지·기타",
     "secret": False, "kind": "text", "guide_url": "https://supabase.com/dashboard"},
    {"name": "SUPABASE_BUCKET", "label": "Supabase 업로드 버킷명", "group": "스토리지·기타",
     "secret": False, "kind": "text"},
    # service_role(=신규 대시보드의 'Secret key', sb_secret_…) — 서버측 업로드/버킷생성에 필수.
    # 모든 RLS를 우회하는 god-key라 기본은 DENYLIST 였으나, 운영 편의를 위해 관리자 등록을 허용한다
    # (암호화 시크릿DB 저장·관리자 게이팅). DB비번/연결URL 등 더 위험한 키는 계속 DENYLIST 유지.
    {"name": "SUPABASE_SERVICE_SECRET_KEY", "label": "Supabase Secret 키(service_role)", "group": "스토리지·기타",
     "secret": True, "kind": "text", "guide_url": "https://supabase.com/dashboard",
     "desc": "Supabase 대시보드 > Project Settings > API > 'Secret key'(=구 service_role) 값. "
             "서버 업로드 전용·비공개. (구 이름 SUPABASE_SERVICE_ROLE_KEY 로 등록해도 동작)"},
    {"name": "PUBLIC_API_BASE", "label": "공개 API 베이스 URL(프록시 절대화)", "group": "스토리지·기타",
     "secret": False, "kind": "text"},
]

_CATALOG_BY_NAME = {c["name"]: c for c in CATALOG}
_CUSTOM_GROUP = "사용자 추가"

# 환경변수명 규칙 + 위험 인프라 키 차단(잠금사고·DB유출 방지)
_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_DENYLIST = {
    "DATABASE_URL", "DATABASE_URL_ASYNC", "APP_SECRET_KEY", "JWT_SECRET_KEY",
    "SECRET_STORE_KEY", "SUPABASE_DB_PASSWORD",
    # ★SUPABASE_SERVICE_ROLE_KEY 는 운영 편의를 위해 관리자 등록 허용(위 CATALOG 참조). DB비번/
    #   연결URL/마스터키 등 더 위험한 키는 차단 유지 — 관리자 패널 침해가 DB 전체 탈취로 번지는 것 방지.
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
# 백업/버전 이력 테이블 — 키가 덮어써지거나 삭제되기 직전의 (암호)값을 스냅샷 보관.
# 평문은 저장하지 않음(value_enc 그대로 복사). 복구 시 이 행을 골라 되돌린다.
_DDL_BACKUP = (
    "CREATE TABLE IF NOT EXISTS platform_secret_backups ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  name text NOT NULL, value_enc text NOT NULL,"
    "  label text, group_name text, is_secret boolean DEFAULT true,"
    "  action text NOT NULL,"  # 'overwrite'(수정 직전) 또는 'delete'(삭제 직전)
    "  backed_up_at timestamptz DEFAULT now(), updated_by text)"
)
# 키 이름으로 이력 조회를 빠르게(많이 안 쌓여도 안전).
_DDL_BACKUP_IDX = (
    "CREATE INDEX IF NOT EXISTS ix_secret_backups_name "
    "ON platform_secret_backups(name)"
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
        with contextlib.suppress(Exception):  # 권한/구버전 PG 폴백
            await db.execute(text(a))
    # 백업 이력 테이블도 같은 흐름에서 멱등 생성(앱 부팅·최초 호출 시).
    try:
        await db.execute(text(_DDL_BACKUP))
        await db.execute(text(_DDL_BACKUP_IDX))
    except Exception:  # noqa: BLE001 — 권한/구버전 PG 폴백
        pass
    await db.commit()


def _fernet_key_from_material(material: str) -> bytes:
    """임의 문자열 → 유효한 Fernet 키(bytes). 이미 유효한 Fernet 키면 그대로, 아니면 SHA256 파생.

    SECRET_STORE_KEY 로 아무 문자열(또는 정식 Fernet 키)을 줘도 생성 단계 예외 없이 동작하게 한다.
    (과거: raw.encode() 가 정식 포맷이 아니면 Fernet() 생성 시 예외)
    """
    from cryptography.fernet import Fernet

    b = material.encode()
    try:
        Fernet(b)  # 이미 정식 Fernet 키(32B urlsafe base64)면 그대로 사용(하위호환)
        return b
    except Exception:  # noqa: BLE001 — 정식 키가 아니면 결정적 파생
        return base64.urlsafe_b64encode(hashlib.sha256(b).digest())


def master_key_status() -> dict[str, Any]:
    """현재 시크릿 마스터키의 출처와 안정성을 보고한다(평문 미노출).

    안정(stable)=True 는 전용 SECRET_STORE_KEY 사용 시에만. APP_SECRET_KEY/JWT_SECRET_KEY/
    하드코딩 폴백은 로테이션·재배포·블루그린 인스턴스에 따라 바뀔 수 있어 unstable.
    """
    if os.getenv("SECRET_STORE_KEY"):
        return {"source": "SECRET_STORE_KEY", "stable": True}
    for src in ("APP_SECRET_KEY", "JWT_SECRET_KEY"):
        if os.getenv(src):
            return {"source": src, "stable": False,
                    "warning": (f"마스터키가 {src}에서 파생됨 — 이 값은 로테이션/재배포 시 바뀌어 "
                                "기존 시크릿 복호화가 깨질 수 있음. 전용 SECRET_STORE_KEY 고정 권장.")}
    return {"source": "hardcoded-fallback", "stable": False,
            "warning": "SECRET_STORE_KEY·APP_SECRET_KEY 미설정 — 하드코딩 폴백 사용(운영 부적합)."}


def _fernet():
    from cryptography.fernet import Fernet

    raw = os.getenv("SECRET_STORE_KEY")
    if raw:
        return Fernet(_fernet_key_from_material(raw))
    base = os.getenv("APP_SECRET_KEY") or os.getenv("JWT_SECRET_KEY") or "propai-secret-store-fallback"
    return Fernet(_fernet_key_from_material(base))


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


async def _snapshot_existing(db: AsyncSession, name: str, action: str) -> bool:
    """덮어쓰기/삭제 직전, platform_secrets 의 현재 행을 백업 테이블로 복사.

    값은 암호문(value_enc) 그대로 복사 — 평문은 절대 다루지 않는다.
    기존 행이 없으면(처음 등록) 백업할 게 없으므로 False.
    """
    row = (await db.execute(
        text("SELECT value_enc, label, group_name, is_secret, updated_by "
             "FROM platform_secrets WHERE name=:n"),
        {"n": name},
    )).first()
    if not row:
        return False
    # 직전에 누가 마지막으로 바꿨는지(updated_by)도 같이 보존.
    enc, label, grp, is_sec, by = row[0], row[1], row[2], row[3], row[4]
    await db.execute(
        text("INSERT INTO platform_secret_backups"
             "(name, value_enc, label, group_name, is_secret, action, updated_by) "
             "VALUES (:n, :v, :l, :g, :s, :a, :by)"),
        {"n": name, "v": enc, "l": label, "g": grp, "s": is_sec, "a": action, "by": by},
    )
    return True


async def load_into_env(db: AsyncSession) -> int:
    """DB의 시크릿을 복호화해 os.environ 에 오버레이(앱 시작 시 1회). 적용 개수 반환.

    복호화 실패(마스터키 불일치) 건수와 마스터키 안정성을 함께 진단·경고한다.
    """
    _capture_baseline()
    n = 0
    failed = 0
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
            else:
                failed += 1
    except Exception as e:  # noqa: BLE001
        logger.warning("시크릿 env 로드 실패", err=str(e)[:120])
    if n:
        logger.info("플랫폼 시크릿 env 오버레이 적용", count=n)
    # 마스터키 불일치 진단: 복호화 실패가 있으면 근본원인(마스터키 변경) 경고.
    if failed:
        st = master_key_status()
        logger.error(
            "시크릿 복호화 실패 — 마스터키 불일치(저장 시점 키 ≠ 현재 키)",
            failed=failed, applied=n, key_source=st.get("source"), key_stable=st.get("stable"),
            hint="전용 SECRET_STORE_KEY 고정 후 실패분 재입력 필요(또는 옛 키로 reencrypt_all 마이그레이션).",
        )
    # 운영에서 전용 마스터키 미고정 시 경고(APP_SECRET_KEY 로테이션에 얹히는 위험 구조).
    if not master_key_status().get("stable"):
        logger.warning("시크릿 마스터키 미고정", **master_key_status())
    return n


async def reencrypt_all(db: AsyncSession, old_key_material: str) -> dict[str, int]:
    """키 회전 마이그레이션 — 옛 마스터키로 복호화 후 현재 마스터키로 재암호화한다.

    old_key_material: 과거 SECRET_STORE_KEY 또는 옛 APP_SECRET_KEY 값(파생 동일 규칙 적용).
    현재 _fernet()(가급적 새 SECRET_STORE_KEY 고정 상태)로 재암호화해 DB를 갱신한다.
    반환: {total, recovered, skipped}. recovered=옛 키로 복호화 성공해 재암호화한 건수.
    """
    from cryptography.fernet import Fernet

    old = Fernet(_fernet_key_from_material(old_key_material))
    await _ensure_table(db)
    rows = (await db.execute(text("SELECT name, value_enc FROM platform_secrets"))).all()
    total = len(rows)
    recovered = 0
    for name, enc in rows:
        try:
            plain = old.decrypt(enc.encode()).decode()
        except Exception:  # noqa: BLE001 — 옛 키로도 안 풀리면 건너뜀(다른 키로 암호화됨)
            continue
        await db.execute(
            text("UPDATE platform_secrets SET value_enc=:v WHERE name=:n"),
            {"v": _encrypt(plain), "n": name},
        )
        recovered += 1
    await db.commit()
    logger.info("시크릿 재암호화 마이그레이션 완료", total=total, recovered=recovered)
    return {"total": total, "recovered": recovered, "skipped": total - recovered}


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
    # 덮어쓰기 직전: 기존 값이 있으면 백업 스냅샷(실수 수정 시 되돌릴 수 있게).
    try:
        await _snapshot_existing(db, name, action="overwrite")
    except Exception as e:  # noqa: BLE001 — 백업 실패가 본 저장을 막지 않음(best-effort)
        logger.warning("시크릿 백업 스냅샷 실패", name=name, err=str(e)[:120])
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
    # 삭제 직전: 현재 값을 백업 스냅샷(실수 삭제 시 복구할 수 있게).
    try:
        await _snapshot_existing(db, name, action="delete")
    except Exception as e:  # noqa: BLE001 — 백업 실패가 삭제를 막지 않음(best-effort)
        logger.warning("시크릿 삭제 백업 스냅샷 실패", name=name, err=str(e)[:120])
    await db.execute(text("DELETE FROM platform_secrets WHERE name=:n"), {"n": name})
    await db.commit()
    base = _ENV_BASELINE.get(name)
    if base is not None and base != "":
        os.environ[name] = base
    else:
        os.environ.pop(name, None)


async def list_backups(db: AsyncSession, name: str | None = None) -> list[dict[str, Any]]:
    """백업(버전) 이력 — 키명·동작·시점·작업자·마스킹값(평문 절대 미노출).

    name 을 주면 그 키의 이력만, 없으면 전체. 최신 백업이 위로 오게 정렬.
    """
    await _ensure_table(db)
    sql = ("SELECT id, name, value_enc, label, group_name, is_secret, "
           "action, backed_up_at, updated_by FROM platform_secret_backups")
    params: dict[str, Any] = {}
    if name:
        sql += " WHERE name=:n"
        params["n"] = (name or "").strip()
    sql += " ORDER BY backed_up_at DESC"
    out: list[dict[str, Any]] = []
    try:
        rows = (await db.execute(text(sql), params)).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("시크릿 백업 이력 조회 실패", err=str(e)[:120])
        return out
    for r in rows:
        bid, nm, enc, label, grp, is_sec, action, at, by = r
        # 마스킹 미리보기 — secret 키는 복호화 후 마스킹, 평문은 절대 반환 안 함.
        plain = _decrypt(enc)
        if plain is None:
            masked = "(복호화 불가 — 마스터키 변경 가능성)"
        elif is_sec:
            masked = _mask(plain)
        else:
            masked = plain  # 공개 키(secret=False)는 원래 평문 노출 정책과 동일
        out.append({
            "id": str(bid),
            "name": nm,
            "label": label,
            "group": grp,
            "secret": bool(is_sec),
            "action": action,
            "backed_up_at": at.isoformat() if at else None,
            "updated_by": by,
            "masked": masked,
        })
    return out


async def restore_secret(db: AsyncSession, backup_id: str, updated_by: str | None) -> None:
    """백업 한 건을 골라 현재 값으로 복구 — 그 시점의 value_enc 를 복호화→set_secret 재설정.

    복구 전 현재 값은 set_secret 안에서 다시 백업되므로 안전(되돌리기의 되돌리기 가능).
    복호화 실패(마스터키 변경 등)면 명확한 에러를 던진다.
    """
    backup_id = (backup_id or "").strip()
    if not backup_id:
        raise ValueError("backup_id 가 비어 있습니다.")
    await _ensure_table(db)
    row = (await db.execute(
        text("SELECT name, value_enc FROM platform_secret_backups WHERE id=CAST(:i AS uuid)"),
        {"i": backup_id},
    )).first()
    if not row:
        raise ValueError(f"해당 백업을 찾을 수 없습니다: {backup_id}")
    name, enc = row[0], row[1]
    if not is_allowed(name):
        raise ValueError(f"복구할 수 없는 보호 키입니다: {name}")
    plain = _decrypt(enc)
    if plain is None:
        raise ValueError(
            "백업 값을 복호화할 수 없습니다(마스터키가 변경되었을 수 있습니다). 복구를 진행할 수 없습니다."
        )
    # set_secret 이 현재 값을 다시 백업한 뒤 이 값으로 재설정(env 즉시 반영 포함).
    await set_secret(db, name, plain, updated_by)
