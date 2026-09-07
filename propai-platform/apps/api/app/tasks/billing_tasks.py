"""결제 정합성 회복 배치 — ★**사람의 클릭에 의존하지 않는 복구**.

## 왜 이 파일이 생겼나 (2026-09-06 실측)

`reconcile_order` 의 소비처는 **두 곳뿐**이었다: 토스 웹훅과 관리자 버튼.
스케줄러는 **0건**(대조군: 같은 billing 패키지의 `purge_expired_buyer_pii` 는
celery beat `purge-order-pii-daily` 에 배선돼 있다 → 조회기 생존).

그 결과 두 가지가 **영원히 방치**될 수 있었다:

  · 승인 요청이 타임아웃되면 주문 `pending` · 영수증 `unknown` 으로 남고 아무도 안 건드린다
    → **돈은 나갔는데 코인이 없다**
  · 가상계좌는 지급으로 가는 **유일한 경로가 웹훅**이었다. 토스 콘솔 URL 등록은
    배포 후 소유자 작업이므로 **미등록이 기본 상태**다 → 그 경로가 통째로 0

★celery 는 이 저장소에서 한 번 데인 층이다 — 배포가 API 컨테이너만 교체하고
  **celery 는 3주간 2026-07-22 이미지로 돌았다**(볼트
  `2026-08-12_PropAI_배포가_celery에_3주간_닿지_않았다`). PR #605 가 워커 정렬을
  넣어 봉합했고, 2026-09-06 배포 로그에 `✅ 워커 정렬 완료 (arq · celery)` 를 실측했다.
  **그 전제가 깨지면 이 배치도 안 돈다** — 배포 로그의 그 줄이 이 파일의 생존 조건이다.
"""

from __future__ import annotations

import logging
from typing import Any

from app.tasks._async_batch import run_async_batch

logger = logging.getLogger(__name__)

try:  # pragma: no cover - celery 미설치 환경(테스트)에서도 임포트되어야 한다
    from app.tasks.celery_app import app as _celery_app
except Exception:  # noqa: BLE001
    _celery_app = None


async def _reconcile_stale_async() -> dict[str, Any]:
    from app.services.billing.toss_orders_service import reconcile_stale_payments

    return await reconcile_stale_payments()


def _run() -> dict[str, Any]:
    """★얇은 진입점 — 로직은 서비스에 있다(celery 없이 태울 수 있게)."""
    result = run_async_batch(_reconcile_stale_async)
    logger.info("결제 정합성 회복 배치 완료: %s", result)
    return result


if _celery_app is not None:  # pragma: no cover - 워커 런타임에서만 등록된다
    reconcile_stale_payments_task = _celery_app.task(
        name="app.tasks.billing_tasks.reconcile_stale_payments",
        queue="celery",
    )(_run)
else:  # 테스트 환경 — 이름만 맞춰 둔다(호출 가능해야 한다).
    reconcile_stale_payments_task = _run
