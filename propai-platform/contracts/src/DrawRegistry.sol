// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title DrawRegistry — 동·호 추첨의 **공약·결과를 체인에 앵커링**한다.
/// @notice 이 컨트랙트가 하는 일은 하나다: ***오프체인 추첨이 사후에 바뀌지 않았음을
///         제3자가 확인할 수 있게 만드는 것.*** 공정성 자체는 오프체인 commit–reveal 이 만든다.
///
/// ★★**개인정보는 한 바이트도 올리지 않는다.** 이름·연락처·동호·신청 내역은 전부 오프체인이고,
///   체인에는 **해시와 머클루트**만 남는다. 체인은 **삭제가 불가능**해서 파기 요구(개인정보보호법)를
///   구조적으로 지킬 수 없다 — 그래서 「나중에 지우면 된다」가 성립하지 않는다.
///
/// ★**왜 이것만으로 공정해지지 않는가**
///   체인은 「바뀌지 않았다」를 증명하지 「처음부터 옳았다」를 증명하지 않는다.
///   공약이 추첨보다 앞섰다는 것은 **commit 트랜잭션이 reveal 보다 앞선 블록에 있다**는 사실로
///   비로소 기계가 판정할 수 있게 된다 — 그것이 이 컨트랙트가 오프체인 저장소에 더하는 값이다.
contract DrawRegistry is Ownable {
    struct Draw {
        bytes32 commitHash;      // sha256(nonce) — 추첨 전에 올린다
        bytes32 participantsHash; // 명부 확정 해시(공약 시점에 고정)
        bytes32 nonce;           // 추첨 후에만 채워진다
        bytes32 resultRoot;      // 결과 머클루트(개별 항목은 오프체인)
        uint64 committedAt;      // block.timestamp
        uint64 revealedAt;
    }

    /// @dev drawId = keccak256(abi.encodePacked(scope, refId)) — 오프체인에서 만들어 넘긴다.
    mapping(bytes32 => Draw) private _draws;

    /// @notice 공약을 올릴 수 있는 주소(서버 서명자). owner 가 관리한다.
    mapping(address => bool) public operators;

    event DrawCommitted(bytes32 indexed drawId, bytes32 commitHash, bytes32 participantsHash, uint64 at);
    event DrawRevealed(bytes32 indexed drawId, bytes32 nonce, bytes32 resultRoot, uint64 at);
    event OperatorSet(address indexed who, bool allowed);

    error NotOperator();
    error AlreadyCommitted();
    error NotCommitted();
    error AlreadyRevealed();
    error CommitMismatch();
    error EmptyValue();

    constructor(address initialOwner) Ownable(initialOwner) {
        operators[initialOwner] = true;
        emit OperatorSet(initialOwner, true);
    }

    modifier onlyOperator() {
        if (!operators[msg.sender]) revert NotOperator();
        _;
    }

    function setOperator(address who, bool allowed) external onlyOwner {
        operators[who] = allowed;
        emit OperatorSet(who, allowed);
    }

    /// @notice 추첨 **전에** 공약을 올린다. ★**한 번만** — 재공약은 되돌릴 수 없다.
    /// @dev 오프체인 `sales_draw_commitments` 의 `UNIQUE(scope, ref_id)` 와 **같은 불변식**을
    ///      체인에도 둔다. 한쪽만 두면 다른 쪽에서 새어 나간다.
    function commitDraw(bytes32 drawId, bytes32 commitHash, bytes32 participantsHash)
        external
        onlyOperator
    {
        if (commitHash == bytes32(0)) revert EmptyValue();
        Draw storage d = _draws[drawId];
        if (d.committedAt != 0) revert AlreadyCommitted();
        d.commitHash = commitHash;
        d.participantsHash = participantsHash;
        d.committedAt = uint64(block.timestamp);
        emit DrawCommitted(drawId, commitHash, participantsHash, d.committedAt);
    }

    /// @notice 추첨 **후에** nonce 와 결과 머클루트를 공개한다.
    /// @dev ★`sha256(nonce) != commitHash` 면 **거부**한다 — 체인이 스스로 공약을 검산한다.
    ///      오프체인 검증기와 **같은 해시 함수**(SHA-256)를 쓴다. keccak 으로 바꾸면
    ///      두 층이 갈려 «검증했다」가 거짓이 된다.
    function revealDraw(bytes32 drawId, bytes32 nonce, bytes32 resultRoot) external onlyOperator {
        Draw storage d = _draws[drawId];
        if (d.committedAt == 0) revert NotCommitted();
        if (d.revealedAt != 0) revert AlreadyRevealed();
        if (sha256(abi.encodePacked(nonce)) != d.commitHash) revert CommitMismatch();
        d.nonce = nonce;
        d.resultRoot = resultRoot;
        d.revealedAt = uint64(block.timestamp);
        emit DrawRevealed(drawId, nonce, resultRoot, d.revealedAt);
    }

    /// @notice 공개 조회 — 누구나 읽는다(그것이 목적이다).
    function getDraw(bytes32 drawId) external view returns (Draw memory) {
        return _draws[drawId];
    }

    /// @notice ★**공약이 추첨보다 앞섰는가** — 오프체인에서 기계가 판정하지 못하던 그 명제.
    /// @dev 두 시각이 모두 있고 `committedAt < revealedAt` 이어야 참이다.
    ///      (같은 블록이면 순서를 보장하지 못하므로 **엄격 부등호**를 쓴다.)
    function commitPrecededReveal(bytes32 drawId) external view returns (bool) {
        Draw storage d = _draws[drawId];
        return d.committedAt != 0 && d.revealedAt != 0 && d.committedAt < d.revealedAt;
    }
}
