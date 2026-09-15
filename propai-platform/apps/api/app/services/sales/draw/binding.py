"""공약이 **무엇을 묶는가** — 명부(participants)와 대상 세대(pool)의 지문.

## 왜 이 모듈이 생겼나 (독립 적대 리뷰 2026-09-13 · MAJOR-1/2 실측)

Phase 1 까지 공약은 **nonce 하나만** 묶고 있었다. 키를 정하는 자유변수는 이랬다:

    key = seed_key(nonce, group_id, candidate_id, drand:round:value)
                                    ~~~~~~~~~~~~  ← **이것만 공격자가 고른다**

`sales_draw_candidates` 에는 이름·고객 유일성이 없고, `POST …/candidates` 는 **공약 이후에도**
제한 없이 불린다. 그래서:

  1. 공약을 게시한다(공개: `commit_hash`·`beacon_round`)
  2. 비콘 라운드가 공개될 때까지 기다린다 — 이제 그 값은 **공개값**이다
  3. DB 에서 nonce 를 **한 번** 읽는다 ⇒ 키를 오프라인에서 완전히 재현할 수 있다
  4. 밀어 줄 사람을 **여러 번** 등록하고, 각 `candidate_id` 의 결과를 미리 계산한다
  5. **원하는 동·호가 나오는 행으로만** 추첨을 누른다

***원장·공약·비콘은 한 글자도 바뀌지 않는다. 검증기는 ✔ 를 찍는다.***
실측(리뷰어): 30세대 중 **지정한 1세대**를 얻는 데 등록 75회. 비용 0, 흔적 0.

그리고 pool 도 같은 상태였다 — 추첨이 `status='AVAILABLE'` 을 **실시간 조회**해서,
세대 3건을 HOLD 로 빼는 것만으로 **30세대 중 10세대**에 도달할 수 있었다.

★***「공약이 무엇을 묶는지」를 안 적으면, grinding 은 없어지는 게 아니라 자리를 옮긴다.***
  nonce 를 서버가 만들게 해서 nonce grinding 을 막았더니 **식별자 grinding** 으로 옮겨 갔다.

## 이 모듈이 하는 것

공약 시점에 **명부와 pool 을 통째로 기록**하고 그 **지문**을 공개한다. 추첨 시점에
다시 계산해 **다르면 거부**한다. 그리고 그 지문을 **seed 에도 섞는다**(이중 방어) —
게이트만 두면 게이트를 우회하는 경로가 생기지만, seed 에 들어가면 **바꾸는 순간 결과가 바뀌어**
공약된 `commit_hash` 와 대조하는 제3자가 알아챌 수 있다.

★**도메인 분리**: 같은 id 목록이라도 「명부」와 「pool」은 다른 지문을 낸다.
  안 그러면 한쪽 지문을 다른 쪽 자리에 넣는 혼동이 성립한다.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable

_ROSTER_DOMAIN = "propai.draw.participants.v1"
_POOL_DOMAIN = "propai.draw.pool.v1"


def _digest(domain: str, ids: Iterable[str]) -> str:
    """정렬·중복 제거한 id 목록의 지문. ★입력 순서에 의존하지 않는다 — DB 가 돌려주는 순서는
    계약이 아니다. 줄바꿈으로 잇는다(콤마는 id 안에 나타날 수 있다)."""
    items = sorted({str(x) for x in ids if str(x)})
    payload = domain + "\n" + "\n".join(items)
    return hashlib.sha256(payload.encode()).hexdigest()


def roster_hash(ids: Iterable[str]) -> str:
    """추첨 **명부**(대상자 id 또는 신청 id)의 지문."""
    return _digest(_ROSTER_DOMAIN, ids)


def pool_hash(ids: Iterable[str]) -> str:
    """추첨 **대상 세대**의 지문."""
    return _digest(_POOL_DOMAIN, ids)


def normalize(ids: Iterable[str]) -> list[str]:
    """저장용 정규형 — 지문과 **같은 정렬·중복 제거**를 쓴다.

    ★지문과 저장형이 다른 규칙을 쓰면 *"저장한 걸로 다시 계산했는데 지문이 다르다"* 가 난다.
    """
    return sorted({str(x) for x in ids if str(x)})
