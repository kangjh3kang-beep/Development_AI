"""스코프 시크릿 내보내기 — 플랫폼 관리자 키 중 '허용목록'만 외부 서비스 .env로 내보낸다.

배경/보안 경계:
- 심의분석엔진(propai-review)은 별도 서비스다. 그 서비스가 플랫폼 마스터키로 금고 전체를
  복호화하면 '한 서비스가 다른 서비스 자격증명 보관소에 접근'하는 신뢰 경계를 넘는다.
- 대신 **플랫폼(=금고의 정당한 소유자)** 이 자기 마스터키로 자기 금고를 복호화하고,
  외부 서비스가 실제로 필요한 **허용목록 키만** 스코프해서 그 서비스의 .env로 내보낸다.
  → 외부 서비스는 자기 .env만 읽는다(마스터키·금고 접근 0).

기존 키 재입력 불필요: 관리자 화면에서 입력한 값(platform_secrets, 암호화)과 플랫폼 .env에
이미 등록된 값을 **그대로** 읽어 연결한다. 손으로 다시 넣는 입력은 없다.

동작:
1) 플랫폼 .env 파일(들)을 베이스라인으로 os.environ에 적재(평문 .env에 이미 있는 키 + 마스터키).
   ⚠️ .env는 worktree마다 별도(gitignored)다. 키가 채워진 .env가 다른 worktree에 있어도
   찾을 수 있도록 기본 후보에 형제 worktree 경로를 포함한다(존재하는 것만 읽음).
2) --with-db 시 secret_store.load_into_env()로 관리자 입력(DB 암호화) 키를 오버레이(플랫폼과 동일 복호화).
3) ALLOWLIST(+ --allow 추가) 키만 대상 .env로 0600 권한으로 원자적 기록.

출력 요약은 키명·설정여부·출처·마스킹값만 — 평문은 절대 노출/로그하지 않는다.
실행 위치: 플랫폼 apps/api(venv 활성). 예)
    python scripts/export_scoped_secrets.py \
        --target /home/<you>/My_Projects/propai-review/.env.secrets --with-db
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# sys.path: 리포루트(→ `apps.api.*`) + apps/api(→ `app.*`) — main.py와 동일 임포트 경로.
_HERE = Path(__file__).resolve()
_API_DIR = _HERE.parents[1]          # apps/api
_REPO_ROOT = _HERE.parents[3]        # propai-platform(이 worktree)
for p in (str(_API_DIR), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# 심의분석엔진이 실제 쓰는 키만(과다노출 금지). 필요 시 --allow 로 확장.
DEFAULT_ALLOWLIST = [
    "ANTHROPIC_API_KEY",   # VLLM 시트 분류(멀티모달 해석)
    "OPENAI_API_KEY",      # LLM 대체 공급자(선택)
    "VWORLD_API_KEY",      # 관할/용도지역 해석
    "MOLIT_API_KEY",       # 규제/실거래 등 공공데이터(선택)
]
# 인프라/마스터 키는 절대 내보내지 않음(스코프 export의 핵심).
_HARD_DENY = {
    "DATABASE_URL", "SYNC_DATABASE_URL", "APP_SECRET_KEY", "JWT_SECRET_KEY",
    "SECRET_STORE_KEY", "ENCRYPTION_KEY", "REDIS_URL", "PATH", "PYTHONPATH", "HOME",
    "AWS_SECRET_ACCESS_KEY", "DEPLOYER_PRIVATE_KEY", "PRIVATE_KEY",
}

# 기본 베이스라인 .env 후보(나중 항목이 우선). worktree마다 .env가 별도라
# 자기 worktree에 .env가 없어도 키가 채워진 메인 worktree에서 읽을 수 있게 한다.
# _HERE.parents[5] = My_Projects (…/My_Projects/<worktree>/propai-platform/apps/api/scripts/이파일)
_MYP = _HERE.parents[5] if len(_HERE.parents) > 5 else _REPO_ROOT.parent
_DEFAULT_ENV_FILES = [
    str(_MYP / "Development_AI" / ".env"),                      # 마스터키(SECRET_STORE_KEY) 등 공통
    str(_MYP / "Development_AI" / "propai-platform" / ".env"),  # 키가 채워진 .env(현재 위치)
    str(_REPO_ROOT / ".env"),                                   # 이 worktree(있으면 최우선)
    str(_REPO_ROOT / "apps" / "api" / ".env"),
]


def _parse_env_file(path: str) -> dict[str, str]:
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


def _mask(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "•" * len(v)
    return f"{v[:3]}{'•' * 6}{v[-3:]}"


def _load_baseline(env_files: list[str]) -> list[str]:
    """플랫폼 .env(들)을 os.environ 베이스라인으로 적재(나중 파일이 우선). 실제 읽은 파일 목록 반환."""
    seen: list[str] = []
    for path in env_files:
        kv = _parse_env_file(path)
        if not kv:
            continue
        seen.append(path)
        for k, v in kv.items():
            if v:
                os.environ[k] = v
    return seen


async def _overlay_db() -> int:
    """관리자 입력(DB 암호화) 키를 플랫폼과 동일 로직으로 os.environ에 오버레이. best-effort."""
    from app.services.secrets import secret_store
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await secret_store.load_into_env(session)


def _atomic_write(target: str, lines: list[str]) -> None:
    tmp = target + ".tmp"
    data = "".join(lines)
    # 0600 권한으로 생성(소유자만 읽기/쓰기) — 시크릿 파일 보호.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="플랫폼 관리자 키 중 허용목록만 외부 서비스 .env로 내보내기")
    ap.add_argument("--target", required=True, help="내보낼 대상 파일(예: propai-review/.env.secrets)")
    ap.add_argument("--with-db", action="store_true", help="platform_secrets(DB) 관리자 키도 복호화 오버레이")
    ap.add_argument("--allow", default="", help="추가 허용 키(쉼표구분)")
    ap.add_argument("--env-file", action="append", default=None,
                    help="베이스라인 .env 경로(반복 지정 가능). 기본=플랫폼 .env들(형제 worktree 포함)")
    args = ap.parse_args()

    env_files = args.env_file if args.env_file else _DEFAULT_ENV_FILES
    allow = list(DEFAULT_ALLOWLIST)
    allow += [a.strip().upper() for a in args.allow.split(",") if a.strip()]
    allow = [a for a in dict.fromkeys(allow) if a not in _HARD_DENY]  # 중복 제거 + 하드 디나이 제외

    read_files = _load_baseline(env_files)
    db_applied = 0
    if args.with_db:
        try:
            db_applied = asyncio.run(_overlay_db())
        except Exception as exc:  # noqa: BLE001 — DB 미가용은 .env 베이스라인으로 graceful
            print(f"[warn] DB 오버레이 실패(베이스라인 .env만 사용): {str(exc)[:120]}", file=sys.stderr)

    lines = ["# 자동 생성 — 플랫폼 export_scoped_secrets.py (편집 금지, 재실행으로 갱신)\n",
             "# 허용목록 키만 포함. 마스터키/인프라 키 없음.\n"]
    summary: list[tuple[str, str, str]] = []
    written = 0
    for name in allow:
        val = (os.environ.get(name) or "").strip()
        if not val:
            summary.append((name, "unset", ""))
            continue
        lines.append(f"{name}={val}\n")
        written += 1
        summary.append((name, "set", _mask(val)))

    _atomic_write(args.target, lines)

    print(f"내보내기 완료 → {args.target}")
    print(f"  베이스라인 .env: {len(read_files)}개 읽음 | DB 오버레이: {db_applied}개 | 기록된 키: {written}/{len(allow)}")
    for path in read_files:
        print(f"    · {path}")
    for name, state, masked in summary:
        print(f"  - {name}: {state}{(' ' + masked) if masked else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
