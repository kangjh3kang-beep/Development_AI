// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title SubcontractPayment
 * @notice 하도급 대금 직불 컨트랙트
 * @dev 건설산업기본법 제35조 기반 — 발주자가 하도급업체에 직접 지급
 *
 * 흐름:
 * 1. 원청(generalContractor)이 하도급 등록 → registerSubcontract()
 * 2. 발주자(owner)가 승인 → approveSubcontract()
 * 3. 하도급업체가 기성청구 → claimPayment()
 * 4. 발주자가 검수 후 직불 → releaseDirectPayment()
 */
contract SubcontractPayment is Ownable, Pausable, ReentrancyGuard {
    enum SubcontractStatus {
        Registered,
        Approved,
        Active,
        Completed,
        Disputed,
        Cancelled
    }

    enum ClaimStatus {
        Pending,
        Approved,
        Rejected,
        Paid
    }

    struct Subcontract {
        address generalContractor;
        address subcontractor;
        uint256 totalAmount;
        uint256 paidAmount;
        uint256 retentionRate; // BPS (예: 1000 = 10%)
        uint64 startDate;
        uint64 endDate;
        SubcontractStatus status;
    }

    struct PaymentClaim {
        uint256 subcontractId;
        uint256 amount;
        string workDescription;
        uint64 claimDate;
        ClaimStatus status;
    }

    uint16 public constant BPS_DENOMINATOR = 10_000;
    uint16 public constant MAX_RETENTION_RATE = 2_000; // 최대 20%

    uint256 public nextSubcontractId;
    uint256 public nextClaimId;

    mapping(uint256 => Subcontract) public subcontracts;
    mapping(uint256 => PaymentClaim) public claims;
    mapping(uint256 => uint256) public retentionBalance; // subcontractId → 유보금

    error InvalidAddress();
    error InvalidAmount();
    error InvalidDates();
    error RetentionTooHigh();
    error Unauthorized();
    error SubcontractNotFound(uint256 id);
    error ClaimNotFound(uint256 id);
    error InvalidStatus(uint256 id);
    error InsufficientFunds();
    error TransferFailed();
    error AmountExceedRemaining(uint256 id, uint256 requested, uint256 remaining);

    event SubcontractRegistered(uint256 indexed id, address indexed generalContractor, address indexed subcontractor, uint256 totalAmount);
    event SubcontractApproved(uint256 indexed id);
    event PaymentClaimed(uint256 indexed claimId, uint256 indexed subcontractId, uint256 amount);
    event DirectPaymentReleased(uint256 indexed claimId, uint256 indexed subcontractId, address indexed subcontractor, uint256 netAmount, uint256 retention);
    event RetentionReleased(uint256 indexed subcontractId, address indexed subcontractor, uint256 amount);
    event SubcontractCompleted(uint256 indexed id);
    event SubcontractDisputed(uint256 indexed id);

    constructor() Ownable(msg.sender) {}

    // ──────────────────────────────────────────────
    // 하도급 등록/승인
    // ──────────────────────────────────────────────

    function registerSubcontract(
        address _subcontractor,
        uint256 _totalAmount,
        uint256 _retentionRate,
        uint64 _startDate,
        uint64 _endDate
    ) external whenNotPaused returns (uint256 subcontractId) {
        if (_subcontractor == address(0)) revert InvalidAddress();
        if (_totalAmount == 0) revert InvalidAmount();
        if (_endDate <= _startDate) revert InvalidDates();
        if (_retentionRate > MAX_RETENTION_RATE) revert RetentionTooHigh();

        subcontractId = nextSubcontractId++;
        subcontracts[subcontractId] = Subcontract({
            generalContractor: msg.sender,
            subcontractor: _subcontractor,
            totalAmount: _totalAmount,
            paidAmount: 0,
            retentionRate: _retentionRate,
            startDate: _startDate,
            endDate: _endDate,
            status: SubcontractStatus.Registered
        });

        emit SubcontractRegistered(subcontractId, msg.sender, _subcontractor, _totalAmount);
    }

    function approveSubcontract(uint256 _id) external onlyOwner {
        Subcontract storage sc = _getSubcontract(_id);
        if (sc.status != SubcontractStatus.Registered) revert InvalidStatus(_id);

        sc.status = SubcontractStatus.Approved;
        emit SubcontractApproved(_id);
    }

    // ──────────────────────────────────────────────
    // 기성 청구 + 직불
    // ──────────────────────────────────────────────

    function claimPayment(
        uint256 _subcontractId,
        uint256 _amount,
        string calldata _workDescription
    ) external whenNotPaused returns (uint256 claimId) {
        Subcontract storage sc = _getSubcontract(_subcontractId);
        if (msg.sender != sc.subcontractor) revert Unauthorized();
        if (sc.status != SubcontractStatus.Approved && sc.status != SubcontractStatus.Active) revert InvalidStatus(_subcontractId);

        uint256 remaining = sc.totalAmount - sc.paidAmount;
        if (_amount > remaining) revert AmountExceedRemaining(_subcontractId, _amount, remaining);

        claimId = nextClaimId++;
        claims[claimId] = PaymentClaim({
            subcontractId: _subcontractId,
            amount: _amount,
            workDescription: _workDescription,
            claimDate: uint64(block.timestamp),
            status: ClaimStatus.Pending
        });

        if (sc.status == SubcontractStatus.Approved) {
            sc.status = SubcontractStatus.Active;
        }

        emit PaymentClaimed(claimId, _subcontractId, _amount);
    }

    function releaseDirectPayment(uint256 _claimId) external payable onlyOwner nonReentrant whenNotPaused {
        PaymentClaim storage claim = _getClaim(_claimId);
        if (claim.status != ClaimStatus.Pending) revert InvalidStatus(_claimId);

        Subcontract storage sc = _getSubcontract(claim.subcontractId);
        uint256 retention = (claim.amount * sc.retentionRate) / BPS_DENOMINATOR;
        uint256 netPayment = claim.amount - retention;

        if (msg.value < netPayment) revert InsufficientFunds();

        claim.status = ClaimStatus.Paid;
        sc.paidAmount += claim.amount;
        retentionBalance[claim.subcontractId] += retention;

        (bool success, ) = payable(sc.subcontractor).call{value: netPayment}("");
        if (!success) revert TransferFailed();

        // 초과 입금분 반환
        if (msg.value > netPayment) {
            (bool refundSuccess, ) = payable(msg.sender).call{value: msg.value - netPayment}("");
            if (!refundSuccess) revert TransferFailed();
        }

        emit DirectPaymentReleased(_claimId, claim.subcontractId, sc.subcontractor, netPayment, retention);
    }

    function rejectClaim(uint256 _claimId) external onlyOwner {
        PaymentClaim storage claim = _getClaim(_claimId);
        if (claim.status != ClaimStatus.Pending) revert InvalidStatus(_claimId);
        claim.status = ClaimStatus.Rejected;
    }

    // ──────────────────────────────────────────────
    // 유보금 해제 + 완료
    // ──────────────────────────────────────────────

    function releaseRetention(uint256 _subcontractId) external payable onlyOwner nonReentrant {
        Subcontract storage sc = _getSubcontract(_subcontractId);
        uint256 retention = retentionBalance[_subcontractId];
        if (retention == 0) revert InvalidAmount();

        retentionBalance[_subcontractId] = 0;

        if (msg.value < retention) revert InsufficientFunds();

        (bool success, ) = payable(sc.subcontractor).call{value: retention}("");
        if (!success) revert TransferFailed();

        if (msg.value > retention) {
            (bool refundSuccess, ) = payable(msg.sender).call{value: msg.value - retention}("");
            if (!refundSuccess) revert TransferFailed();
        }

        emit RetentionReleased(_subcontractId, sc.subcontractor, retention);
    }

    function completeSubcontract(uint256 _id) external onlyOwner {
        Subcontract storage sc = _getSubcontract(_id);
        if (sc.status != SubcontractStatus.Active) revert InvalidStatus(_id);
        sc.status = SubcontractStatus.Completed;
        emit SubcontractCompleted(_id);
    }

    function disputeSubcontract(uint256 _id) external {
        Subcontract storage sc = _getSubcontract(_id);
        if (msg.sender != sc.generalContractor && msg.sender != sc.subcontractor && msg.sender != owner()) revert Unauthorized();
        sc.status = SubcontractStatus.Disputed;
        emit SubcontractDisputed(_id);
    }

    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    // ──────────────────────────────────────────────
    // Internal helpers
    // ──────────────────────────────────────────────

    function _getSubcontract(uint256 _id) internal view returns (Subcontract storage) {
        if (_id >= nextSubcontractId) revert SubcontractNotFound(_id);
        return subcontracts[_id];
    }

    function _getClaim(uint256 _id) internal view returns (PaymentClaim storage) {
        if (_id >= nextClaimId) revert ClaimNotFound(_id);
        return claims[_id];
    }
}
