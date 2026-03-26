// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract PropAIEscrow is Ownable, Pausable, ReentrancyGuard {
    uint16 public constant FEE_BPS = 30;
    uint16 public constant BPS_DENOMINATOR = 10_000;

    enum EscrowStatus {
        PendingFunding,
        Funded,
        Disputed,
        Released,
        Refunded
    }

    struct Escrow {
        address payer;
        address payee;
        address subcontractor;
        uint256 totalAmount;
        uint256 remainingAmount;
        uint64 expiresAt;
        bytes32 conditionHash;
        EscrowStatus status;
    }

    error InvalidAddress();
    error InvalidAmount();
    error InvalidExpiry();
    error InvalidConditionHash();
    error Unauthorized();
    error EscrowNotFound(uint256 escrowId);
    error InvalidEscrowState(uint256 escrowId, EscrowStatus currentStatus);
    error EscrowExpired(uint256 escrowId);
    error EscrowNotExpired(uint256 escrowId);
    error AmountExceedsBalance(uint256 escrowId, uint256 requested, uint256 available);
    error TransferFailed();
    error InvalidSubcontractor(uint256 escrowId, address subcontractor);

    event EscrowCreated(
        uint256 indexed escrowId,
        address indexed payer,
        address indexed payee,
        address subcontractor,
        uint64 expiresAt,
        bytes32 conditionHash
    );
    event EscrowFunded(uint256 indexed escrowId, uint256 amount);
    event EscrowReleased(
        uint256 indexed escrowId,
        address indexed recipient,
        uint256 grossAmount,
        uint256 feeAmount
    );
    event EscrowDisputed(uint256 indexed escrowId, address indexed initiator, bytes32 reasonHash);
    event EscrowRefunded(uint256 indexed escrowId, uint256 amount);

    mapping(uint256 escrowId => Escrow escrowRecord) private escrows;
    uint256 private nextEscrowId = 1;

    constructor() Ownable(msg.sender) {}

    function createEscrow(
        address payee,
        address subcontractor,
        uint64 expiresAt,
        bytes32 conditionHash
    ) external whenNotPaused returns (uint256 escrowId) {
        if (payee == address(0)) revert InvalidAddress();
        if (expiresAt <= block.timestamp) revert InvalidExpiry();
        if (conditionHash == bytes32(0)) revert InvalidConditionHash();

        escrowId = nextEscrowId;
        nextEscrowId += 1;

        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            subcontractor: subcontractor,
            totalAmount: 0,
            remainingAmount: 0,
            expiresAt: expiresAt,
            conditionHash: conditionHash,
            status: EscrowStatus.PendingFunding
        });

        emit EscrowCreated(escrowId, msg.sender, payee, subcontractor, expiresAt, conditionHash);
    }

    function fundEscrow(uint256 escrowId) external payable whenNotPaused {
        Escrow storage escrowRecord = _getEscrow(escrowId);

        if (msg.sender != escrowRecord.payer) revert Unauthorized();
        if (escrowRecord.status != EscrowStatus.PendingFunding) {
            revert InvalidEscrowState(escrowId, escrowRecord.status);
        }
        if (block.timestamp > escrowRecord.expiresAt) revert EscrowExpired(escrowId);
        if (msg.value == 0) revert InvalidAmount();

        escrowRecord.totalAmount = msg.value;
        escrowRecord.remainingAmount = msg.value;
        escrowRecord.status = EscrowStatus.Funded;

        emit EscrowFunded(escrowId, msg.value);
    }

    function releaseEscrow(uint256 escrowId) external nonReentrant whenNotPaused {
        Escrow storage escrowRecord = _getEscrow(escrowId);

        if (msg.sender != escrowRecord.payer && msg.sender != owner()) revert Unauthorized();
        if (escrowRecord.status != EscrowStatus.Funded) {
            revert InvalidEscrowState(escrowId, escrowRecord.status);
        }
        if (block.timestamp > escrowRecord.expiresAt) revert EscrowExpired(escrowId);

        uint256 grossAmount = escrowRecord.remainingAmount;
        if (grossAmount == 0) revert InvalidAmount();

        escrowRecord.remainingAmount = 0;
        escrowRecord.status = EscrowStatus.Released;

        (uint256 payoutAmount, uint256 feeAmount) = _distribute(escrowRecord.payee, grossAmount);
        emit EscrowReleased(escrowId, escrowRecord.payee, payoutAmount + feeAmount, feeAmount);
    }

    function directPaymentToSubcontractor(
        uint256 escrowId,
        address subcontractor,
        uint256 grossAmount
    ) external nonReentrant whenNotPaused {
        Escrow storage escrowRecord = _getEscrow(escrowId);

        if (msg.sender != escrowRecord.payer && msg.sender != owner()) revert Unauthorized();
        if (escrowRecord.status != EscrowStatus.Funded) {
            revert InvalidEscrowState(escrowId, escrowRecord.status);
        }
        if (block.timestamp > escrowRecord.expiresAt) revert EscrowExpired(escrowId);
        if (subcontractor == address(0)) revert InvalidAddress();
        if (grossAmount == 0) revert InvalidAmount();
        if (grossAmount > escrowRecord.remainingAmount) {
            revert AmountExceedsBalance(escrowId, grossAmount, escrowRecord.remainingAmount);
        }
        if (
            escrowRecord.subcontractor != address(0) &&
            escrowRecord.subcontractor != subcontractor
        ) {
            revert InvalidSubcontractor(escrowId, subcontractor);
        }

        if (escrowRecord.subcontractor == address(0)) {
            escrowRecord.subcontractor = subcontractor;
        }

        escrowRecord.remainingAmount -= grossAmount;
        if (escrowRecord.remainingAmount == 0) {
            escrowRecord.status = EscrowStatus.Released;
        }

        (uint256 payoutAmount, uint256 feeAmount) = _distribute(subcontractor, grossAmount);
        emit EscrowReleased(escrowId, subcontractor, payoutAmount + feeAmount, feeAmount);
    }

    function autoRefundOnExpiry(uint256 escrowId) external nonReentrant whenNotPaused {
        Escrow storage escrowRecord = _getEscrow(escrowId);

        if (
            escrowRecord.status != EscrowStatus.Funded &&
            escrowRecord.status != EscrowStatus.Disputed
        ) {
            revert InvalidEscrowState(escrowId, escrowRecord.status);
        }
        if (block.timestamp <= escrowRecord.expiresAt) revert EscrowNotExpired(escrowId);

        uint256 refundAmount = escrowRecord.remainingAmount;
        escrowRecord.remainingAmount = 0;
        escrowRecord.status = EscrowStatus.Refunded;

        _safeTransferETH(escrowRecord.payer, refundAmount);
        emit EscrowRefunded(escrowId, refundAmount);
    }

    function initiateDispute(uint256 escrowId, bytes32 reasonHash) external whenNotPaused {
        Escrow storage escrowRecord = _getEscrow(escrowId);

        bool isParticipant =
            msg.sender == escrowRecord.payer ||
            msg.sender == escrowRecord.payee ||
            msg.sender == owner();

        if (!isParticipant) revert Unauthorized();
        if (escrowRecord.status != EscrowStatus.Funded) {
            revert InvalidEscrowState(escrowId, escrowRecord.status);
        }

        escrowRecord.status = EscrowStatus.Disputed;
        emit EscrowDisputed(escrowId, msg.sender, reasonHash);
    }

    function resolveDispute(uint256 escrowId, bool releaseToPayee) external onlyOwner nonReentrant {
        Escrow storage escrowRecord = _getEscrow(escrowId);

        if (escrowRecord.status != EscrowStatus.Disputed) {
            revert InvalidEscrowState(escrowId, escrowRecord.status);
        }

        uint256 amount = escrowRecord.remainingAmount;
        escrowRecord.remainingAmount = 0;

        if (releaseToPayee) {
            escrowRecord.status = EscrowStatus.Released;
            (uint256 payoutAmount, uint256 feeAmount) = _distribute(escrowRecord.payee, amount);
            emit EscrowReleased(escrowId, escrowRecord.payee, payoutAmount + feeAmount, feeAmount);
            return;
        }

        escrowRecord.status = EscrowStatus.Refunded;
        _safeTransferETH(escrowRecord.payer, amount);
        emit EscrowRefunded(escrowId, amount);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function calculateFee(uint256 grossAmount) public pure returns (uint256) {
        return (grossAmount * FEE_BPS) / BPS_DENOMINATOR;
    }

    function getEscrow(uint256 escrowId) external view returns (Escrow memory) {
        return _getEscrow(escrowId);
    }

    function getNextEscrowId() external view returns (uint256) {
        return nextEscrowId;
    }

    function _getEscrow(uint256 escrowId) internal view returns (Escrow storage escrowRecord) {
        escrowRecord = escrows[escrowId];

        if (escrowRecord.payer == address(0)) {
            revert EscrowNotFound(escrowId);
        }
    }

    function _distribute(
        address recipient,
        uint256 grossAmount
    ) internal returns (uint256 payoutAmount, uint256 feeAmount) {
        feeAmount = calculateFee(grossAmount);
        payoutAmount = grossAmount - feeAmount;

        if (feeAmount > 0) {
            _safeTransferETH(owner(), feeAmount);
        }
        _safeTransferETH(recipient, payoutAmount);
    }

    function _safeTransferETH(address recipient, uint256 amount) internal {
        (bool success, ) = recipient.call{value: amount}("");

        if (!success) {
            revert TransferFailed();
        }
    }
}
