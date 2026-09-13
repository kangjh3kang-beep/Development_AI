"""공개 난수 비콘(drand) — ***서버도 테넌트도 예측할 수 없는 값***을 추첨에 섞는다.

## 왜 이것이 필요한가

Phase 0 는 정직하게 적었다: *"DB 를 직접 읽는 사람은 여전히 nonce 를 본다 —
이 모듈은 「운영자 무신뢰」가 아니다."* 이 모듈이 **그 자리**를 겨눈다.

## ★왜 「테넌트 기여값」보다 이것이 먼저인가

2자 commit–reveal(테넌트가 공약→공개)은 ***테넌트가 명부를 보고 공개를 거부하면 멈춘다.***
타임아웃 후 서버 단독으로 진행하면 그 순간 보장이 사라진다 — **중단 공격이 프로토콜에 내재**한다.

공개 비콘은 그 문제가 없다:
  · 공약 시점에 **미래 라운드 번호**를 못 박는다 — **그 값은 아직 세상에 없다**
  · 라운드가 오면 **누구도 보류할 수 없다**(전 세계에 공개된다)
  · 검증자가 **같은 라운드를 직접 조회**해 재현한다

## ★이 모듈이 하지 않는 것 (정직하게)

**BLS 서명을 검증하지 않는다.** drand 는 라운드마다 서명을 주고 그것을 체인 공개키로 검증하는 것이
정석인데, 여기서는 **두 독립 엔드포인트의 값을 대조**하는 것으로 갈음한다.
***이것은 암호학적 검증이 아니라 「두 곳이 동시에 거짓말하지는 않았다」는 가용성 기반 대조다.***
한 운영자가 두 엔드포인트를 모두 통제하면 뚫린다 — 그 한계를 알고 쓴다.
(서명 검증을 넣으려면 BLS12-381 라이브러리가 필요하고, 그건 별도 의존성 판단이다.)
"""
from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

#: ★**독립성과 가용성은 다른 축**이다(2026-09-13 실측).
#:   · `api.drand.sh` 와 `drand.cloudflare.com` 은 **서로 다른 운영자** — 여기서 값이 갈리면 신호다.
#:   · `api2/api3.drand.sh` 는 **같은 운영자의 예비** — 가용성은 올리지만 **독립 대조가 아니다**.
#:     (그래서 아래 `fetch_round` 는 「2곳 이상」이 아니라 «**서로 다른 운영자 2곳 이상**»을 요구한다.)
#:   실측: 넷 다 라운드 6461120 에 대해 같은 값(`8095e332…`)을 돌려줬다.
#:   ★한때 cloudflare 가 실패해 「일시적 장애」로 적었는데 **오진이었다** — 기본 urllib
#:     User-Agent 를 **403 으로 막는 것**이었다(아래 `_UA` 참조). 예비 엔드포인트는
#:     여전히 필요하지만, 그 사유는 「간헐 장애」가 아니다.
DEFAULT_ENDPOINTS = (
    "https://api.drand.sh",
    "https://drand.cloudflare.com",
    "https://api2.drand.sh",
    "https://api3.drand.sh",
)

#: 엔드포인트 → 운영자. **대조는 운영자 단위**로 센다.
def operator_of(base: str) -> str:
    if "cloudflare" in base:
        return "cloudflare"
    return "drand.sh"

#: ★**체인 해시를 못 박는다**(2026-09-13 실측). 이것을 URL 경로에 넣지 않으면 엔드포인트가
#:   *"자기 기본 체인"* 을 준다 — 그게 서로 다르면 값이 갈리고, **같은 운영자가 기본 체인을
#:   바꾸면 두 곳이 함께 갈아탄다**(그때 교차 대조는 눈이 먼다).
#:   실측: 두 운영자 `/info` 가 같은 해시·주기 30초·genesis 1595431050 을 줬고,
#:   **없는 해시를 넣으면 500 으로 거부**된다(대조군 — 조용히 기본 체인으로 떨어지지 않는다).
CHAIN_HASH = "8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce"


def public_url(base: str, tail: str) -> str:
    """`.../<체인해시>/public/<라운드|latest>` — ★체인을 URL 에 박아 **조용한 체인 교체**를 막는다."""
    return f"{base}/{CHAIN_HASH}/public/{tail}"


#: 체인의 라운드 주기(초) — ★`/info` 로 **실측**했다(period=30). ★값을 여기 적는 이유: `LEAD_ROUNDS` 가 몇 초를 뜻하는지
#:   호출부가 계산할 수 있어야 하기 때문이다(「10라운드」만으로는 대기 시간을 모른다).
ROUND_PERIOD_S = 30

#: 공약 시점보다 **몇 라운드 뒤**를 잡을 것인가. ★이 값이 곧 **공약→추첨 최소 대기**다
#:   (기본 10라운드 ≈ 5분). 너무 작으면 공약 직후 값이 나와 「미래」가 아니게 되고,
#:   너무 크면 운영이 못 기다린다.
LEAD_ROUNDS = 10


@dataclass(frozen=True)
class BeaconValue:
    round: int
    randomness: str
    sources: tuple[str, ...]


class BeaconError(RuntimeError):
    """비콘을 **믿을 수 있게** 가져오지 못했다. ★조용히 진행하지 않기 위한 예외다."""


class BeaconNotReadyError(BeaconError):
    """공약된 라운드가 **아직 공개되지 않았다** — 장애가 아니라 **설계된 대기**다.

    ★별도 예외로 가르는 이유: 상위 층이 하나로 받으면 *"비콘 장애"* 와 *"아직 시각이 안 됐다"* 가
      **같은 화면**을 내게 된다. 그러면 운영자는 기다리면 되는 상황에서 장애 대응을 시작한다.
      ***한 신호가 두 사건을 덮는 것 — 이 저장소가 반복해 데인 클래스다.***
    """

    def __init__(self, message: str, *, seconds_remaining: int) -> None:
        super().__init__(message)
        self.seconds_remaining = int(seconds_remaining)


#: ★**User-Agent 를 반드시 준다.** `drand.cloudflare.com` 은 기본 `Python-urllib/3.x` 를
#:   **403 으로 막는다**(실측 2026-09-13: UA 없음 → 403 · UA 아무거나 → 200 · curl → 200).
#:   ★이걸 몰라서 「cloudflare 가 일시적으로 죽는다」고 **오진**할 뻔했다 —
#:   ***도구가 다르면 답이 다르다. curl 이 되는데 코드가 안 되면 헤더를 먼저 의심하라.***
_UA = "propai-draw-verifier/1.0 (+fairness-audit)"


def _http_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 — 고정 https 목록
        return json.loads(r.read().decode())


def latest_round(endpoints=DEFAULT_ENDPOINTS, fetch: Callable[[str], dict] | None = None) -> int:
    """지금 나와 있는 가장 최근 라운드 번호."""
    f = fetch or _http_json
    for base in endpoints:
        try:
            return int(f(public_url(base, "latest"))["round"])
        except Exception:                                      # noqa: BLE001 — 다음 곳을 시도
            continue
    raise BeaconError("어느 비콘 엔드포인트에서도 최신 라운드를 못 가져왔다")


def target_round(endpoints=DEFAULT_ENDPOINTS, fetch=None, lead: int = LEAD_ROUNDS) -> int:
    """공약 시점에 못 박을 **미래** 라운드. ★`lead <= 0` 은 거부한다 — 과거·현재 라운드는
    **이미 알려진 값**이라 「예측 불가」가 거짓이 된다."""
    if lead <= 0:
        raise BeaconError(f"lead 는 양수여야 한다(lead={lead}) — 과거 라운드는 이미 공개된 값이다")
    return latest_round(endpoints, fetch) + lead


def fetch_round(rnd: int, endpoints=DEFAULT_ENDPOINTS, fetch=None) -> BeaconValue:
    """특정 라운드를 **두 곳 이상에서** 가져와 대조한다.

    ★한 곳만 성공하면 **거부**한다 — 대조가 없으면 그 값이 옳다고 말할 근거가 없다.
    ★값이 **갈리면** 거부한다. 조용히 하나를 고르면 그 선택이 곧 조작 통로다.
    """
    f = fetch or _http_json
    got: dict[str, str] = {}
    errors: list[str] = []
    for base in endpoints:
        try:
            d = f(public_url(base, str(rnd)))
            if int(d["round"]) != rnd:
                errors.append(f"{base}: 다른 라운드({d.get('round')})를 돌려줬다")
                continue
            got[base] = str(d["randomness"]).lower()
        except Exception as exc:                               # noqa: BLE001
            errors.append(f"{base}: {type(exc).__name__}")
    operators = {operator_of(b) for b in got}
    if len(operators) < 2:
        raise BeaconError(
            f"라운드 {rnd} 를 **서로 다른 운영자 2곳 이상**에서 못 가져왔다"
            f"(성공 {len(got)}곳 · 운영자 {sorted(operators)}) — 대조 없이 진행하지 않는다. "
            f"★같은 운영자의 예비 여러 곳은 대조가 아니다. 사유: {errors}"
        )
    values = set(got.values())
    if len(values) != 1:
        raise BeaconError(
            f"라운드 {rnd} 의 값이 엔드포인트마다 **다르다** — 조작이거나 체인이 다르다: {got}"
        )
    return BeaconValue(rnd, next(iter(values)), tuple(sorted(got)))


def seconds_until(rnd: int, endpoints=DEFAULT_ENDPOINTS, fetch=None) -> int:
    """그 라운드까지 **몇 초** 남았는가. ★「아직 안 나왔다」만 말하면 운영자가 언제 다시 올지 모른다."""
    now = latest_round(endpoints, fetch)
    return max(0, (rnd - now) * ROUND_PERIOD_S)


def randomness_for(rnd: int, endpoints=DEFAULT_ENDPOINTS, fetch=None) -> str:
    """공약된 라운드의 값을 가져온다 — **아직 안 나왔으면 몇 초 남았는지 말하며 거부**한다.

    ★*"아직입니다"* 만 말하면 운영자는 **언제 다시 올지 모른다.** 그러면 사람은 새로고침을
      반복하고, 그 반복이 곧 grinding 처럼 보인다. **대기 시간을 말하는 것이 거부의 일부다.**
    """
    latest = latest_round(endpoints, fetch)
    if rnd > latest:
        wait = (rnd - latest) * ROUND_PERIOD_S
        raise BeaconNotReadyError(
            f"공약된 비콘 라운드 {rnd} 가 **아직 공개되지 않았습니다**(현재 {latest}) — "
            f"약 {wait}초 뒤에 추첨할 수 있습니다. "
            "★이 대기는 결함이 아니라 설계입니다: 공약 시점에 **아직 세상에 없는 값**을 못 박았기 "
            "때문에 서버도 결과를 미리 알 수 없습니다",
            seconds_remaining=wait,
        )
    return fetch_round(rnd, endpoints, fetch).randomness


def seed_contributions(beacon_round: int | None, endpoints=DEFAULT_ENDPOINTS,
                       fetch=None) -> tuple[list[str], str]:
    """추첨 seed 에 섞을 **비콘 기여값**과 **사람이 읽는 라벨**을 함께 돌려준다.

    ★두 추첨 경로(청약·동호)가 **같은 함수**를 통과하게 하는 것이 이 함수의 존재 이유다 —
      각자 `if beacon_round:` 를 쓰면 **한쪽만 조용히 비콘을 빼는** 경로가 생긴다.

    ★`beacon_round is None` 은 **Phase 0 시기에 공약된 옛 행**이다(그때는 컬럼이 없었다).
      그 경우 **조용히 진행하지 않고 라벨이 「비콘 미사용」이라고 말한다** — 침묵이 아니라 표기다.
      ***지금 새로 하는 공약은 라운드 없이 만들어질 수 없다*** (`commit_draw` 가 거부한다).
    """
    if beacon_round is None:
        return [], "비콘 미사용(공약에 라운드 없음 — Phase 0 이전 공약)"
    value = randomness_for(int(beacon_round), endpoints, fetch)
    return [f"drand:{int(beacon_round)}:{value}"], f"drand round {int(beacon_round)}"
