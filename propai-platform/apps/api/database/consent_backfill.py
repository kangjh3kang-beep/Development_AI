"""동의 미완 소급 표시 SQL — **alembic 에 의존하지 않는 단일 원천**.

★왜 마이그레이션 밖으로 뺐나: 락이 이 SQL 을 태우려면 모듈을 import 해야 하는데,
  마이그레이션 파일은 최상단에서 `from alembic import op` 를 하므로 테스트 환경
  (alembic 미설치)에서 ModuleNotFoundError 가 난다. 실측 2026-09-06 —
  그래서 «실제 문자열을 태운다» 는 락이 **원리적으로 실행 불가**였다.

★그리고 소스 모양으로 검사하면 f-string 보간 전 `{_COL}` 을 보게 된다.
  값을 태우려면 값이 만들어지는 자리를 import 가능한 곳에 둬야 한다.
"""
from __future__ import annotations

#: users 테이블의 동의 미완 플래그 컬럼명(모델·마이그레이션·락이 공유하는 단일 원천)
CONSENT_PENDING_COLUMN = "consent_pending"

#: 동의 이력이 **한 행도 없는 생존 사용자**를 미완으로 표시한다.
#:
#: ★멱등: 이미 True 인 행은 대상에서 빠지고(= false 조건), 동의가 생긴 행은
#:   NOT EXISTS 에서 빠진다. 재실행이 동의자를 미완으로 되돌리지 않는다.
#: ★탈퇴(deleted_at) 사용자는 제외 — 다시 동의를 요구할 대상이 아니다.
BACKFILL_SQL = f"""
    UPDATE users u
       SET {CONSENT_PENDING_COLUMN} = true
     WHERE u.deleted_at IS NULL
       AND u.{CONSENT_PENDING_COLUMN} = false
       AND NOT EXISTS (SELECT 1 FROM user_consents c WHERE c.user_id = u.id)
"""
