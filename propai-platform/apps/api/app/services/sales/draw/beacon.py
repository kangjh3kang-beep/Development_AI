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

#: ★**cloudflare 가 실제로 403 으로 막는 모양**(실측: `UA='Python-urllib/3.13'` → 403).
#:   UA 를 「비어 있지 않은가」로만 잠그면 **이 문자열로 바꿔도 초록**이고, 그러면 운영자 두 곳 중
#:   하나가 죽어 **모든 공약·모든 추첨이 503** 이 된다(대조가 성립하지 않으므로).
#:   ⇒ 값 자체를 **모양으로** 거부한다 — 락이 아니라 **코드가** 막는다.
_BLOCKED_UA_PREFIXES = ("python-urllib", "python-requests", "curl/")


def _assert_ua_is_not_blocked(ua: str) -> None:
    low = ua.strip().lower()
    if not low:
        raise BeaconError("User-Agent 가 비었다 — cloudflare 가 403 으로 막는다")
    for bad in _BLOCKED_UA_PREFIXES:
        if low.startswith(bad):
            raise BeaconError(
                f"User-Agent 가 **차단되는 모양**이다({ua!r}) — 실측으로 403 을 받는 접두 {bad!r}. "
                "이 값을 쓰면 운영자 한 곳이 통째로 죽어 교차 대조가 불가능해진다"
            )


def _http_json(url: str, timeout: int = 12) -> dict:
    _assert_ua_is_not_blocked(_UA)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 — 고정 https 목록
        return json.loads(r.read().decode())


#: 두 운영자가 보고하는 `latest` 가 이만큼까지 어긋나는 것은 **정상**이다(라운드가 30초마다
#:   오르므로 전파 지연으로 1~2 라운드 차가 난다). 이보다 벌어지면 **대조 실패**로 본다.
LATEST_SKEW_TOLERANCE = 2


def latest_round(endpoints=DEFAULT_ENDPOINTS, fetch: Callable[[str], dict] | None = None) -> int:
    """지금 나와 있는 가장 최근 라운드 — ★**서로 다른 운영자 2곳**에서 받아 대조한다.

    ★★**종전에는 첫 번째로 응답한 곳을 그대로 썼다. 그것이 구멍이었다**(독립 적대 리뷰 2026-09-13
      · 두 리뷰어가 각각 발견). `fetch_round` 는 「운영자 2곳」을 요구하는데 `latest_round` 는 안
      해서 **경계를 한쪽만 잠근** 꼴이었고, 「미래 라운드인가」 판정이 전부 이 값에 걸려 있다:

        · `target_round` — 공약에 못 박을 라운드
        · `commit_draw` 의 과거 라운드 거부
        · `randomness_for` 의 「아직 안 나왔다」 판정
        · `seconds_until` 의 남은 시간

      실측(리뷰어): 첫 엔드포인트만 **1000 라운드(≈8.3시간) 뒤처지게** 하면 공약이
      **이미 8시간 전에 공개된 라운드**를 못 박는다 ⇒ nonce 를 아는 사람이 **공약 시점에**
      당첨자를 계산한다. ***보장이 통째로 사라지는데 모든 신호는 「비콘 사용」이라고 말한다.***
      거짓말은 **한 곳으로 충분했다** — 그래서 「두 곳을 다 통제해야 뚫린다」는 내 문서는
      **과소 진술**이었다.

    ★**최댓값을 쓴다**(허용 오차 안에서). 뒤처진 곳을 따라가면 「과거를 미래라 부르는」 쪽으로
      틀리는데, 그 방향이 **보장을 깨는 방향**이다. 앞선 곳을 따라가면 대기가 길어질 뿐이다.
      ***틀릴 수밖에 없다면 안전한 쪽으로 틀려라.***
    """
    f = fetch or _http_json
    got: dict[str, int] = {}
    errors: list[str] = []
    for base in endpoints:
        try:
            got[base] = int(f(public_url(base, "latest"))["round"])
        except Exception as exc:                               # noqa: BLE001 — 다음 곳을 시도
            errors.append(f"{base}: {type(exc).__name__}")
    by_op: dict[str, int] = {}
    for base, rnd in got.items():
        op = operator_of(base)
        by_op[op] = max(by_op.get(op, 0), rnd)
    if len(by_op) < 2:
        raise BeaconError(
            f"최신 라운드를 **서로 다른 운영자 2곳 이상**에서 못 가져왔다"
            f"(성공 {len(got)}곳 · 운영자 {sorted(by_op)}) — 한 곳의 말만 믿고 "
            f"「미래 라운드」를 정하지 않는다. 사유: {errors}"
        )
    spread = max(by_op.values()) - min(by_op.values())
    if spread > LATEST_SKEW_TOLERANCE:
        raise BeaconError(
            f"운영자들이 보고한 최신 라운드가 **{spread}라운드나 어긋난다**({by_op}) — "
            f"허용 오차 {LATEST_SKEW_TOLERANCE}. 한 곳이 뒤처졌거나 거짓말하고 있다. "
            "★뒤처진 값을 쓰면 **이미 공개된 라운드를 「미래」로 못 박게** 된다"
        )
    return max(by_op.values())


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
    """추첨 seed 에 섞을 **비콘 기여값**과 **사람이 읽는 라벨**.

    ★두 추첨 경로(청약·동호)가 **같은 함수**를 통과하게 하는 것이 이 함수의 존재 이유다.

    ★★**`beacon_round is None` 은 거부한다**(2026-09-13 적대 리뷰 · 두 리뷰어 공통 지적).
      종전에는 *"Phase 0 이전 공약"* 이라며 `([], "비콘 미사용")` 을 돌려줬는데, 그것이 곧
      **`UPDATE sales_draw_commitments SET beacon_round=NULL` 한 줄로 비콘을 통째로 끄는 통로**
      였다. 그 UPDATE 를 할 수 있는 사람은 **nonce 도 읽을 수 있는 사람**이므로,
      ***이 모듈이 막으려던 바로 그 상대에게 탈출구를 열어 준 셈이다.***
      ⇒ 라벨로 「말하는 것」은 침묵보다 낫지만 **거부보다는 나쁘다.**
      ***지금 장식인 예외는 나중 서식지가 된다.***
    """
    if beacon_round is None:
        raise BeaconError(
            "공약에 비콘 라운드가 없습니다 — 비콘 없이는 추첨하지 않습니다(fail-closed). "
            "라운드 없이 만들어진 옛 공약이라면 그 추첨은 **다시 공약해야** 합니다"
        )
    value = randomness_for(int(beacon_round), endpoints, fetch)
    return [f"drand:{int(beacon_round)}:{value}"], f"drand round {int(beacon_round)}"
