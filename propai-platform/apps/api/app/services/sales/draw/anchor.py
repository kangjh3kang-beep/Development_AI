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
                   participants_hash: str) -> AnchorResult:
    """공약을 체인에 올린다. **실패해도 예외를 던지지 않는다.**"""
    cfg = _config()
    if cfg is None:
        return AnchorResult(False, "skipped", _missing())
    try:
        return _send(cfg, "commitDraw",
                     [draw_id(scope, ref_id), _b32(commit_hash), _b32(participants_hash)])
    except Exception as exc:                      # noqa: BLE001 — 사유를 남기고 삼키지 않는다
        return AnchorResult(False, "failed", f"{type(exc).__name__}: {exc}"[:300])


def reveal_onchain(scope: str, ref_id: str, nonce: str, result_root: str) -> AnchorResult:
    """추첨 후 nonce·결과 루트를 올린다. 컨트랙트가 **공약을 스스로 검산**한다."""
    cfg = _config()
    if cfg is None:
        return AnchorResult(False, "skipped", _missing())
    try:
        return _send(cfg, "revealDraw",
                     [draw_id(scope, ref_id), _b32(nonce), _b32(result_root)])
    except Exception as exc:                      # noqa: BLE001
        return AnchorResult(False, "failed", f"{type(exc).__name__}: {exc}"[:300])


def _b32(hex_str: str) -> bytes:
    """32바이트로 정규화. ★길이가 다르면 **조용히 패딩하지 않고** 예외 — 잘린 해시는 거짓이다."""
    s = (hex_str or "").removeprefix("0x")
    raw = bytes.fromhex(s)
    if len(raw) != 32:
        raise ValueError(f"32바이트가 아니다({len(raw)}바이트) — 해시를 자르거나 늘리지 않는다")
    return raw


_ABI = [
    {"type": "function", "name": "commitDraw", "stateMutability": "nonpayable",
     "inputs": [{"name": "drawId", "type": "bytes32"}, {"name": "commitHash", "type": "bytes32"},
                {"name": "participantsHash", "type": "bytes32"}], "outputs": []},
    {"type": "function", "name": "revealDraw", "stateMutability": "nonpayable",
     "inputs": [{"name": "drawId", "type": "bytes32"}, {"name": "nonce", "type": "bytes32"},
                {"name": "resultRoot", "type": "bytes32"}], "outputs": []},
]


def _send(cfg: tuple[str, str, str], fn: str, args: list[Any]) -> AnchorResult:
    """실제 전송. ★`web3` 미설치도 **실패가 아니라 사유가 있는 skipped** 로 말한다."""
    rpc, addr, key = cfg
    try:
        from web3 import Web3
    except ImportError:
        return AnchorResult(False, "skipped", "web3 미설치 — 앵커링 없이 추첨은 정상 진행된다")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    acct = w3.eth.account.from_key(key)
    c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_ABI)
    tx = getattr(c.functions, fn)(*args).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "chainId": w3.eth.chain_id,
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return AnchorResult(True, "anchored", "", tx_hash.hex())
