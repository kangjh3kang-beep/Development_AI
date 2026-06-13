"""시크릿 스토어 마스터키 회전 마이그레이션 — 옛 키로 복호화 → 현재 키로 재암호화.

근본문제(마스터키 불일치) 복구용. 사용 절차:
  1) 운영 .env·compose·블루그린 양쪽에 전용 SECRET_STORE_KEY(고정 Fernet 키)를 먼저 설정한다.
  2) 옛 APP_SECRET_KEY(또는 옛 SECRET_STORE_KEY) 값을 알면 아래로 일괄 복구:
       cd propai-platform && PYTHONPATH=.:apps/api \
         OLD_SECRET_MATERIAL='옛APP_SECRET_KEY값' \
         apps/api/.venv/bin/python apps/api/scripts/reencrypt_secret_store.py
  3) 옛 값을 모르면(분실) → 관리자 화면에서 실패한 시크릿을 1회 재입력(이 스크립트 불필요).

OLD_SECRET_MATERIAL 로 복호화된 건만 현재 SECRET_STORE_KEY 로 재암호화한다(나머지는 skip).
"""
from __future__ import annotations

import asyncio
import os
import sys


async def _main() -> int:
    old_material = os.getenv("OLD_SECRET_MATERIAL")
    if not old_material:
        print("OLD_SECRET_MATERIAL 환경변수(옛 마스터키 재질)가 필요합니다.", file=sys.stderr)
        return 2
    if not os.getenv("SECRET_STORE_KEY"):
        print("경고: 현재 SECRET_STORE_KEY 미설정 — 먼저 전용 고정키를 설정하세요(재발 방지).",
              file=sys.stderr)

    from app.core.database import AsyncSessionLocal
    from app.services.secrets import secret_store

    async with AsyncSessionLocal() as db:
        result = await secret_store.reencrypt_all(db, old_material)
    print(f"재암호화 완료: total={result['total']} recovered={result['recovered']} "
          f"skipped={result['skipped']}")
    print("recovered>0 이면 해당 건이 현재 마스터키로 복구됨. skipped 는 옛 키로도 안 풀린 건(다른 키).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
