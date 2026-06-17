"""플랫폼 관리자 시크릿 커넥터 — platform_secrets(Fernet 암호화) → os.environ 오버레이(읽기 전용).

플랫폼 관리자 화면에서 입력한 키(ANTHROPIC/VWORLD/OPENAI 등)는 propai_db의 platform_secrets에
Fernet 암호화 저장된다. 같은 DB를 공유하는 본 엔진이 같은 마스터키로 복호화해 os.environ에 덮어쓰면,
어댑터(VLLM/VWORLD)가 그 키를 즉시 사용한다(재입력 불필요).

마스터키: SECRET_STORE_KEY(우선) 또는 APP_SECRET_KEY — **플랫폼과 동일**해야 복호화 성공.
위험 인프라 키(DATABASE_URL/SECRET 등)는 DENYLIST로 오버레이 차단. 평문은 절대 로그/응답에 노출 안 함.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_DENYLIST = {
    "DATABASE_URL", "SYNC_DATABASE_URL", "APP_SECRET_KEY", "JWT_SECRET_KEY",
    "SECRET_STORE_KEY", "REDIS_URL", "PATH", "PYTHONPATH", "HOME",
}


def is_allowed(name: str) -> bool:
    name = (name or "").strip()
    return bool(_NAME_RE.match(name)) and name.upper() not in _DENYLIST


def _fernet_key_from_material(material: str) -> bytes:
    from cryptography.fernet import Fernet

    b = material.encode()
    try:
        Fernet(b)  # 이미 정식 Fernet 키면 그대로(플랫폼과 동일 규칙)
        return b
    except Exception:  # noqa: BLE001
        return base64.urlsafe_b64encode(hashlib.sha256(b).digest())


_MASTER_NAMES = ("SECRET_STORE_KEY", "APP_SECRET_KEY", "JWT_SECRET_KEY")


def _read_env_kv(path: str) -> dict[str, str]:
    """플랫폼 .env 파일을 key=value 딕트로 파싱. 값은 런타임 복호화에만 사용(로그/응답 노출 금지)."""
    kv: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        return {}
    return kv


def _platform_kvs() -> list[dict[str, str]]:
    from app.settings import env_or_setting

    kvs: list[dict[str, str]] = []
    for path in (env_or_setting("PLATFORM_ENV_FILE") or "").split(","):
        path = path.strip()
        if path:
            kv = _read_env_kv(path)
            if kv:
                kvs.append(kv)
    return kvs


def master_key_candidates() -> list[str]:
    """복호화 후보 마스터키(중복 제거). 순서=로컬(env/.env) 먼저, 그다음 플랫폼 .env들.

    각 출처 내에서 플랫폼 _fernet 우선순위(SECRET_STORE_KEY→APP_SECRET_KEY→JWT_SECRET_KEY)를 따른다.
    플랫폼이 어느 키로 암호화했는지 불확실하므로 단일 가정 대신 후보 목록을 순차 시도한다(무음 오판 0).
    """
    from app.settings import env_or_setting

    cands: list[str] = []
    for n in _MASTER_NAMES:  # 로컬: 이름 우선순위
        v = env_or_setting(n)
        if v:
            cands.append(v)
    kvs = _platform_kvs()
    for n in _MASTER_NAMES:  # 플랫폼 파일: 모든 파일의 SECRET_STORE→APP→JWT 순
        for kv in kvs:
            v = kv.get(n)
            if v:
                cands.append(v)
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def master_key_material() -> str:
    """대표 마스터키(후보 1순위) — 폴백 포함. 단일 복호화 경로(_fernet)·표시용."""
    cands = master_key_candidates()
    return cands[0] if cands else "propai-secret-store-fallback"


def has_master_key() -> bool:
    """전용 마스터키(폴백 제외) 가용 여부 — 로컬 또는 플랫폼 .env 참조. 가드/doctor용."""
    return bool(master_key_candidates())


def _fernet_from_material(material: str):
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key_from_material(material))


def _fernet():
    return _fernet_from_material(master_key_material())


def overlay_secrets(rows: list[tuple[str, str]], fernet=None) -> dict:
    """(name, value_enc) 목록을 복호화해 os.environ에 오버레이. 적용/실패/차단 카운트 반환.

    fernet 미지정 시 환경 마스터키로 생성. 복호화 실패(마스터키 불일치)는 skip(무음 단정 금지 — failed 카운트).
    """
    fernet = fernet or _fernet()
    applied: list[str] = []
    failed = 0
    denied = 0
    for name, enc in rows:
        if not is_allowed(name):
            denied += 1
            continue
        try:
            val = fernet.decrypt(enc.encode()).decode()
        except Exception:  # noqa: BLE001 — 마스터키 불일치/손상
            failed += 1
            continue
        os.environ[name] = val
        applied.append(name)
    return {"applied": applied, "applied_count": len(applied), "failed": failed, "denied": denied}


def _count_decryptable(pairs: list[tuple[str, str]], material: str) -> int:
    """주어진 마스터키로 복호화 성공하는(허용된) 행 수 — env 미설정(순수 판정용)."""
    f = _fernet_from_material(material)
    n = 0
    for name, enc in pairs:
        if not is_allowed(name):
            continue
        try:
            f.decrypt(enc.encode())
            n += 1
        except Exception:  # noqa: BLE001 — 마스터키 불일치/손상
            continue
    return n


async def load_platform_secrets(session: AsyncSession) -> dict:
    """platform_secrets 전체를 읽어, 복호화되는 후보 마스터키를 선택해 os.environ에 1회 오버레이.

    후보가 여럿이면 복호화 성공 건수가 최대인 키를 선택(가정 대신 검증). 0건이면 무음 단정 금지(note).
    테이블 없음/빈 테이블/마스터키 없음은 graceful(0)으로 보고.
    """
    try:
        rows = (await session.execute(text("SELECT name, value_enc FROM platform_secrets"))).all()
    except Exception:  # noqa: BLE001 — 테이블 없음/권한
        return {"applied": [], "applied_count": 0, "failed": 0, "denied": 0,
                "key_index": -1, "note": "platform_secrets 미존재"}
    pairs = [(r[0], r[1]) for r in rows]
    if not pairs:
        return {"applied": [], "applied_count": 0, "failed": 0, "denied": 0,
                "key_index": -1, "note": "platform_secrets 비어있음"}
    cands = master_key_candidates()
    if not cands:
        return {"applied": [], "applied_count": 0, "failed": 0, "denied": 0,
                "key_index": -1, "note": "마스터키 없음"}
    best_material, best_n, best_i = "", -1, -1
    for i, material in enumerate(cands):
        n = _count_decryptable(pairs, material)
        if n > best_n:
            best_material, best_n, best_i = material, n, i
    if best_n <= 0:
        return {"applied": [], "applied_count": 0, "failed": len(pairs), "denied": 0,
                "key_index": -1, "candidates": len(cands),
                "note": "모든 후보 마스터키로 복호화 실패(플랫폼 암호화 키 불일치)"}
    res = overlay_secrets(pairs, _fernet_from_material(best_material))
    res["key_index"] = best_i
    res["candidates"] = len(cands)
    return res
