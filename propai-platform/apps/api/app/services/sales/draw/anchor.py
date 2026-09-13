"""추첨 **체인 앵커링** — 공약·결과를 체인에 남겨 사후 변조를 막는다.

## 이 모듈의 경계 (먼저 적는다)

  한다      `DrawRegistry` 에 **해시만** 올린다(공약·명부해시·nonce·결과 머클루트).
  하지 않는다 **공정성을 만들지 않는다.** 그건 오프체인 commit–reveal 이 한다.
            체인은 「바뀌지 않았다」를 증명하지 **「처음부터 옳았다」를 증명하지 않는다.**

★★**개인정보는 한 바이트도 올리지 않는다.** 이름·연락처·동호는 전부 오프체인이고 체인에는
  **해시와 머클루트**만 간다. 체인은 **삭제가 불가능**해서 파기 요구를 구조적으로 못 지킨다 —
  「나중에 지우면 된다」가 성립하지 않는 층이다.

★**앵커링 실패가 추첨을 막지 않는다.** 체인은 **부가 증거**다. RPC 가 죽었다고 추첨이 멈추면
  가용성을 인질로 잡는 것이고, 그건 이 기능이 주는 값보다 크다.
  ⇒ 모든 진입점이 `AnchorResult` 를 돌려주고 **예외를 밖으로 던지지 않는다.**
    대신 **왜 못 올렸는지**를 `reason` 에 적는다(무성 실패 금지).

★**아직 배포되지 않았다**(2026-09-13). `DRAW_REGISTRY_ADDRESS` 가 없으면 `skipped` 를 돌려준다 —
  ***「주소가 없다」와 「올리다 실패했다」는 다른 사실이라 다른 값으로 말한다.***
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any


#: 체인 식별자. `keccak` 이 아니라 **sha256** 을 쓴다 — 오프체인 검증기·컨트랙트와 **같은 함수**여야
#: 세 층이 갈리지 않는다(컨트랙트도 `sha256(abi.encodePacked(nonce))` 로 검산한다).
def draw_id(scope: str, ref_id: str) -> str:
    """`scope`·`ref_id` → 32바이트 식별자(hex)."""
    return "0x" + hashlib.sha256(f"{scope}:{ref_id}".encode()).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    """결과 머클루트 — 개별 항목은 **오프체인**에 두고 루트만 올린다.

    ★잎은 **정렬**해서 넣는다(입력 순서가 루트를 바꾸면 같은 결과가 다른 루트를 낸다).
    ★홀수면 마지막을 **복제**한다(표준 관행). 빈 목록은 0 루트.
    """
    if not leaves:
        return "0x" + "00" * 32
    level = [hashlib.sha256(x.encode()).digest() for x in sorted(leaves)]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest()
                 for i in range(0, len(level), 2)]
    return "0x" + level[0].hex()


@dataclass(frozen=True)
class AnchorResult:
    """앵커링 결과. ★`ok=False` 여도 **추첨은 성립한다** — 이건 부가 증거다."""

    ok: bool
    state: str          # "anchored" | "skipped" | "failed"
    reason: str = ""
    tx_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "state": self.state, "reason": self.reason,
                "tx_hash": self.tx_hash}


def _config() -> tuple[str, str, str] | None:
    """(rpc_url, address, private_key) — 하나라도 없으면 `None`."""
    rpc = os.getenv("POLYGON_RPC_URL", "").strip()
    addr = os.getenv("DRAW_REGISTRY_ADDRESS", "").strip()
    key = os.getenv("DRAW_ANCHOR_PRIVATE_KEY", "").strip()
    if not (rpc and addr and key):
        return None
    return rpc, addr, key


def anchor_enabled() -> bool:
    """설정이 갖춰졌는가. ★이 값이 `False` 인 것은 **실패가 아니라 미설정**이다."""
    return _config() is not None


def _missing() -> str:
    names = [n for n in ("POLYGON_RPC_URL", "DRAW_REGISTRY_ADDRESS", "DRAW_ANCHOR_PRIVATE_KEY")
             if not os.getenv(n, "").strip()]
    return "미설정: " + ", ".join(names)


def commit_onchain(scope: str, ref_id: str, commit_hash: str,
                   participants_hash: str, *, wait_s: int | None = None) -> AnchorResult:
    """공약을 체인에 올린다. **실패해도 예외를 던지지 않는다.**"""
    cfg = _config()
    if cfg is None:
        return AnchorResult(False, "skipped", _missing())
    try:
        # ★`draw_id` 는 **hex 문자열**이다 — `_b32` 로 32바이트로 만든다. 종전에는 web3 가
        #   이 변환을 대신해 주고 있었고, 그것을 걷어내자 **첫 인자에서 터졌다**(fail-soft 설계
        #   덕에 추첨은 멈추지 않고 `failed` 사유로 드러났다).
        return _send(cfg, "commitDraw",
                     [_b32(draw_id(scope, ref_id)), _b32(commit_hash), _b32(participants_hash)],
                     wait_s=wait_s)
    except Exception as exc:                      # noqa: BLE001 — 사유를 남기고 삼키지 않는다
        return AnchorResult(False, "failed", f"{type(exc).__name__}: {exc}"[:300])


def reveal_onchain(scope: str, ref_id: str, nonce: str, result_root: str,
                   *, wait_s: int | None = None) -> AnchorResult:
    """추첨 후 nonce·결과 루트를 올린다. 컨트랙트가 **공약을 스스로 검산**한다."""
    cfg = _config()
    if cfg is None:
        return AnchorResult(False, "skipped", _missing())
    try:
        return _send(cfg, "revealDraw",
                     [_b32(draw_id(scope, ref_id)), _b32(nonce), _b32(result_root)],
                     wait_s=wait_s)
    except Exception as exc:                      # noqa: BLE001
        return AnchorResult(False, "failed", f"{type(exc).__name__}: {exc}"[:300])


def _b32(hex_str: str) -> bytes:
    """32바이트로 정규화. ★길이가 다르면 **조용히 패딩하지 않고** 예외 — 잘린 해시는 거짓이다."""
    s = (hex_str or "").removeprefix("0x")
    raw = bytes.fromhex(s)
    if len(raw) != 32:
        raise ValueError(f"32바이트가 아니다({len(raw)}바이트) — 해시를 자르거나 늘리지 않는다")
    return raw


#: 함수 시그니처 — ★**셀렉터를 손으로 적지 않는다**(keccak 로 파생한다).
#:   세 인자가 전부 `bytes32` 라 인코딩은 **32바이트 3개를 이어 붙이는 것**이 전부다
#:   (동적 타입이 없으므로 ABI 인코더가 필요 없다 — 그래서 `web3` 를 안 쓴다).
_SIGS = {
    "commitDraw": "commitDraw(bytes32,bytes32,bytes32)",
    "revealDraw": "revealDraw(bytes32,bytes32,bytes32)",
}

#: 영수증을 기다리는 기본 상한(초). ★기다리지 않으면 **되돌려진 트랜잭션도 「성공」으로 보고**된다.
#:   ★다만 **HTTP 요청 안에서 90초를 기다릴 수는 없다** — 그래서 요청 경로는 짧게 기다리고
#:   못 받으면 `pending` 으로 **정직하게** 말한 뒤, 읽을 때 `reconcile` 로 맞춘다.
_RECEIPT_TIMEOUT_S = 15
_RECEIPT_POLL_S = 3


def _rpc(url: str, method: str, params: list[Any]) -> Any:
    import httpx

    r = httpx.post(url, json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                   timeout=20.0)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"RPC {method}: {body['error'].get('message', body['error'])}")
    return body["result"]


def _calldata(fn: str, args: list[bytes]) -> str:
    from eth_utils import keccak

    sel = keccak(text=_SIGS[fn])[:4]
    return "0x" + (sel + b"".join(args)).hex()


def _send(cfg: tuple[str, str, str], fn: str, args: list[Any],
          *, wait_s: int | None = None) -> AnchorResult:
    """실제 전송. ★**영수증의 `status` 까지 확인**해야 「올렸다」고 말할 수 있다.

    ★★종전 구현은 `send_raw_transaction` 직후 `anchored` 를 반환했다. 그런데 이 컨트랙트는
      `revealDraw` 에서 **공약을 스스로 검산**하고 어긋나면 `revert` 한다 — 즉 ***되돌려진
      트랜잭션을 「체인에 올렸다」고 보고***하게 된다. 그것이 이 모듈이 존재하는 이유와 정면으로
      어긋난다(앵커는 **증거**인데, 거짓 증거는 증거보다 나쁘다).

    ★상태 어휘를 넷으로 가른다 — ***하나의 신호가 여러 사건을 덮지 않게.***
      `anchored`(영수증 status=1) · `pending`(보냈으나 상한 내 미채굴) ·
      `failed`(되돌려짐·전송 실패) · `skipped`(설정·의존성 부재)
    """
    rpc, addr, key = cfg
    try:
        from eth_account import Account
    except ImportError:
        return AnchorResult(False, "skipped",
                            "eth-account 미설치 — 앵커링 없이 추첨은 정상 진행된다")
    acct = Account.from_key(key)                  # ★키는 이 프로세스 밖으로 나가지 않는다
    data = _calldata(fn, args)
    chain_id = int(_rpc(rpc, "eth_chainId", []), 16)
    nonce = int(_rpc(rpc, "eth_getTransactionCount", [acct.address, "pending"]), 16)
    call = {"from": acct.address, "to": addr, "data": data}
    # ★가스 추정이 실패하면 그 자체가 **컨트랙트가 거부한다는 신호**다 — 임의값으로 덮지 않는다.
    gas = int(_rpc(rpc, "eth_estimateGas", [call]), 16)
    gas_price = int(_rpc(rpc, "eth_gasPrice", []), 16)
    tx = {"to": addr, "data": data, "nonce": nonce, "chainId": chain_id,
          "gas": int(gas * 1.2), "gasPrice": int(gas_price * 1.25), "value": 0}
    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = _rpc(rpc, "eth_sendRawTransaction", ["0x" + bytes(raw).hex()])

    limit = _RECEIPT_TIMEOUT_S if wait_s is None else max(0, int(wait_s))
    waited = 0.0
    while waited < limit:
        rcpt = _rpc(rpc, "eth_getTransactionReceipt", [tx_hash])
        if rcpt:
            ok = int(rcpt.get("status", "0x0"), 16) == 1
            if ok:
                return AnchorResult(True, "anchored", "", tx_hash)
            return AnchorResult(False, "failed",
                                "트랜잭션이 되돌려졌다(revert) — 컨트랙트가 거부했다", tx_hash)
        time.sleep(_RECEIPT_POLL_S)
        waited += _RECEIPT_POLL_S
    # ★**「모른다」를 「성공」으로 말하지 않는다.**
    return AnchorResult(False, "pending",
                        f"{limit}초 안에 채굴되지 않았다 — 나중에 영수증을 확인하라", tx_hash)


def reconcile(tx_hash: str) -> AnchorResult:
    """`pending` 으로 남은 트랜잭션의 **현재 상태를 다시 잰다.**

    ★`pending` 은 *"모른다"* 이지 *"실패"* 도 *"성공"* 도 아니다. 그 상태를 영원히 두면
      **원장이 「모른다」로 굳는다** — 읽을 때마다 이 함수로 맞춘다(게으른 정합).
    """
    cfg = _config()
    if cfg is None:
        return AnchorResult(False, "skipped", _missing(), tx_hash)
    try:
        rcpt = _rpc(cfg[0], "eth_getTransactionReceipt", [tx_hash])
    except Exception as exc:                      # noqa: BLE001
        return AnchorResult(False, "pending", f"조회 실패: {type(exc).__name__}", tx_hash)
    if not rcpt:
        return AnchorResult(False, "pending", "아직 채굴되지 않았다", tx_hash)
    if int(rcpt.get("status", "0x0"), 16) == 1:
        return AnchorResult(True, "anchored", "", tx_hash)
    return AnchorResult(False, "failed", "트랜잭션이 되돌려졌다(revert)", tx_hash)


def commit_preceded_reveal(scope: str, ref_id: str) -> bool | None:
    """★**체인에게 직접 묻는다** — 「공약이 공개보다 앞섰는가」.

    이 PR 은 그동안 *"그건 추첨 전에 commit_hash 를 받아 둔 사람만 말할 수 있다"* 고 적어 왔다.
    ***앵커가 붙으면 그 명제를 체인이 증언한다*** — 시각이 블록에 박히기 때문이다.
    설정이 없으면 `None`(모름) — **`False`(아니다)와 구별한다.**
    """
    cfg = _config()
    if cfg is None:
        return None
    try:
        from eth_utils import keccak

        sel = keccak(text="commitPrecededReveal(bytes32)")[:4]
        data = "0x" + (sel + _b32(draw_id(scope, ref_id))).hex()
        got = _rpc(cfg[0], "eth_call", [{"to": cfg[1], "data": data}, "latest"])
        return int(got, 16) == 1
    except Exception:                             # noqa: BLE001 — 모르면 모른다고 한다
        return None
