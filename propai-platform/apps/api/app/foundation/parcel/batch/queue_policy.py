"""큐 정책 — 단일 동기 경로 우선, 배치는 별도 저우선 큐(INV-M1).

실제 큐 라우팅은 Celery 큐 이름(parcel_batch)으로만 표현한다.
여기서는 단일 SLA 우선·배치 동시성·청크 크기 등의 정책 상수와 헬퍼만 둔다.
배치 작업이 단일 필지 동기 경로(빠른 사용자 응답)를 절대 막지 않도록 하는 것이 목적이다.
"""

from __future__ import annotations

# 단일 필지 동기 응답의 목표 SLA(초). 배치는 이 SLA보다 항상 낮은 우선순위.
SINGLE_SLA_SECONDS: float = 2.0

# 배치 전용 Celery 큐 이름(단일 경로와 물리적으로 분리).
BATCH_QUEUE_NAME: str = "parcel_batch"

# 한 청크에 묶는 필지 수(기본 50).
DEFAULT_CHUNK_SIZE: int = 50

# 청크 내 동시 호출 상한(asyncio.Semaphore, 기본 5). 외부 API 폭주 방지.
DEFAULT_CHUNK_CONCURRENCY: int = 5

# FIFO 기반이되, 단일 경로가 대기 중이면 배치에 부여하는 가중치(낮을수록 후순위).
BATCH_PRIORITY_WEIGHT: int = 9   # 0(최우선)~9(최후순위) 중 최후순위


def is_single_path_priority() -> bool:
    """단일 동기 경로가 배치보다 항상 우선임을 알리는 정책 신호.

    배치 스케줄러/큐 라우팅이 이 값을 보고 단일 경로를 먼저 처리하도록 한다.
    구조적으로 단일 경로와 배치 store/락이 분리되어 있으므로 항상 True.
    """
    return True


def batch_concurrency() -> int:
    """배치 청크 내 동시 호출 상한을 반환한다."""
    return DEFAULT_CHUNK_CONCURRENCY


def chunk_size() -> int:
    """배치 청크 크기를 반환한다."""
    return DEFAULT_CHUNK_SIZE
