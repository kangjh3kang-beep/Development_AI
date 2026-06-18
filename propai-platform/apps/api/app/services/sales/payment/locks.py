"""수납(#4) Postgres advisory-lock 키 단일 상수(SSOT).

여러 모듈(lifecycle_p5 라우터, main.py 일배치 루프)이 '같은' 키로 상호배제해야 동시진입이
직렬화된다. 키를 각 파일에 따로 정의하면 한쪽만 바꿨을 때 값이 어긋나 상호배제가 깨지므로,
이 모듈 한 곳에서만 정의하고 모두가 import 한다(매직넘버 중복 제거).

- _OVERDUE_LOCK_KEY: 연체이자 산정(일배치 + 수동 트리거)의 상호배제 키.
- _ADJ_LOCK_KEY: sales_payment_adjustments 테이블 런타임 보장(CREATE) race 제거 키.
다른 잡과 충돌하지 않는 고유 상수다(_GROWTH_LOCK_KEYS 와 동일 컨벤션).
"""

OVERDUE_LOCK_KEY = 911_004_002
ADJ_LOCK_KEY = 911_004_001
