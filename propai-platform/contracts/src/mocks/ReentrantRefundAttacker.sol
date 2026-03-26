// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {PropAIEscrow} from "../PropAIEscrow.sol";

contract ReentrantRefundAttacker {
    PropAIEscrow public immutable escrow;
    uint256 public escrowId;
    bool public attackOnReceive;
    bool public reentrancyBlocked;

    constructor(address escrowAddress) {
        escrow = PropAIEscrow(escrowAddress);
    }

    function createEscrowAndFund(
        address payee,
        uint64 expiresAt,
        bytes32 conditionHash
    ) external payable {
        escrowId = escrow.createEscrow(payee, address(0), expiresAt, conditionHash);
        escrow.fundEscrow{value: msg.value}(escrowId);
    }

    function setAttackOnReceive(bool nextValue) external {
        attackOnReceive = nextValue;
    }

    function triggerRefund() external {
        escrow.autoRefundOnExpiry(escrowId);
    }

    receive() external payable {
        if (!attackOnReceive) {
            return;
        }

        attackOnReceive = false;

        try escrow.autoRefundOnExpiry(escrowId) {
            reentrancyBlocked = false;
        } catch {
            reentrancyBlocked = true;
        }
    }
}
