// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title PropAIGovernance
 * @notice 부동산 개발 사업 DAO 거버넌스 컨트랙트
 * @dev 조합원/투자자 투표 기반 의사결정
 *
 * 기능:
 * - 제안 생성 (시공사 선정, 분양가 결정, 설계 변경 등)
 * - 투표 (찬성/반대/기권, 지분 비례 가중)
 * - 실행 (쿼럼 충족 + 과반 찬성 시)
 */
contract PropAIGovernance is Ownable, ReentrancyGuard {
    enum ProposalStatus {
        Pending,
        Active,
        Defeated,
        Succeeded,
        Executed,
        Cancelled
    }

    enum VoteType {
        Against,
        For,
        Abstain
    }

    struct Proposal {
        uint256 id;
        address proposer;
        string title;
        string description;
        bytes32 documentHash; // IPFS CID 해시 (증빙 문서)
        uint64 startTime;
        uint64 endTime;
        uint256 forVotes;
        uint256 againstVotes;
        uint256 abstainVotes;
        ProposalStatus status;
        bool executed;
    }

    struct MemberInfo {
        uint256 votingPower; // 지분 비례 투표권
        bool isActive;
    }

    uint256 public constant MIN_VOTING_PERIOD = 3 days;
    uint256 public constant MAX_VOTING_PERIOD = 30 days;
    uint256 public quorumBps = 5_000; // 50% 쿼럼
    uint256 public constant BPS_DENOMINATOR = 10_000;

    uint256 public nextProposalId;
    uint256 public totalVotingPower;
    uint256 public memberCount;

    mapping(uint256 => Proposal) public proposals;
    mapping(address => MemberInfo) public members;
    mapping(uint256 => mapping(address => bool)) public hasVoted;
    mapping(uint256 => mapping(address => VoteType)) public voteCast;

    error NotMember();
    error InsufficientVotingPower();
    error ProposalNotFound(uint256 id);
    error ProposalNotActive(uint256 id);
    error AlreadyVoted(uint256 id, address voter);
    error VotingPeriodInvalid();
    error QuorumNotReached(uint256 id);
    error ProposalNotSucceeded(uint256 id);
    error AlreadyExecuted(uint256 id);
    error InvalidQuorum();
    error MemberAlreadyExists(address member);

    event MemberAdded(address indexed member, uint256 votingPower);
    event MemberRemoved(address indexed member);
    event MemberVotingPowerUpdated(address indexed member, uint256 newPower);
    event ProposalCreated(uint256 indexed id, address indexed proposer, string title);
    event VoteCasted(uint256 indexed proposalId, address indexed voter, VoteType voteType, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCancelled(uint256 indexed id);
    event QuorumUpdated(uint256 oldQuorum, uint256 newQuorum);

    modifier onlyMember() {
        if (!members[msg.sender].isActive) revert NotMember();
        _;
    }

    constructor() Ownable(msg.sender) {}

    // ──────────────────────────────────────────────
    // 멤버 관리
    // ──────────────────────────────────────────────

    function addMember(address _member, uint256 _votingPower) external onlyOwner {
        if (_member == address(0) || _votingPower == 0) revert InsufficientVotingPower();
        if (members[_member].isActive) revert MemberAlreadyExists(_member);

        members[_member] = MemberInfo({votingPower: _votingPower, isActive: true});
        totalVotingPower += _votingPower;
        memberCount++;

        emit MemberAdded(_member, _votingPower);
    }

    function removeMember(address _member) external onlyOwner {
        if (!members[_member].isActive) revert NotMember();

        totalVotingPower -= members[_member].votingPower;
        members[_member].isActive = false;
        members[_member].votingPower = 0;
        memberCount--;

        emit MemberRemoved(_member);
    }

    function updateVotingPower(address _member, uint256 _newPower) external onlyOwner {
        if (!members[_member].isActive) revert NotMember();
        if (_newPower == 0) revert InsufficientVotingPower();

        totalVotingPower = totalVotingPower - members[_member].votingPower + _newPower;
        members[_member].votingPower = _newPower;

        emit MemberVotingPowerUpdated(_member, _newPower);
    }

    // ──────────────────────────────────────────────
    // 제안 생성 + 투표
    // ──────────────────────────────────────────────

    function createProposal(
        string calldata _title,
        string calldata _description,
        bytes32 _documentHash,
        uint64 _votingPeriod
    ) external onlyMember returns (uint256 proposalId) {
        if (_votingPeriod < MIN_VOTING_PERIOD || _votingPeriod > MAX_VOTING_PERIOD) revert VotingPeriodInvalid();

        proposalId = nextProposalId++;
        proposals[proposalId] = Proposal({
            id: proposalId,
            proposer: msg.sender,
            title: _title,
            description: _description,
            documentHash: _documentHash,
            startTime: uint64(block.timestamp),
            endTime: uint64(block.timestamp) + _votingPeriod,
            forVotes: 0,
            againstVotes: 0,
            abstainVotes: 0,
            status: ProposalStatus.Active,
            executed: false
        });

        emit ProposalCreated(proposalId, msg.sender, _title);
    }

    function castVote(uint256 _proposalId, VoteType _voteType) external onlyMember {
        Proposal storage p = _getProposal(_proposalId);
        if (p.status != ProposalStatus.Active) revert ProposalNotActive(_proposalId);
        if (block.timestamp > p.endTime) revert ProposalNotActive(_proposalId);
        if (hasVoted[_proposalId][msg.sender]) revert AlreadyVoted(_proposalId, msg.sender);

        uint256 weight = members[msg.sender].votingPower;
        hasVoted[_proposalId][msg.sender] = true;
        voteCast[_proposalId][msg.sender] = _voteType;

        if (_voteType == VoteType.For) {
            p.forVotes += weight;
        } else if (_voteType == VoteType.Against) {
            p.againstVotes += weight;
        } else {
            p.abstainVotes += weight;
        }

        emit VoteCasted(_proposalId, msg.sender, _voteType, weight);
    }

    // ──────────────────────────────────────────────
    // 제안 확정 + 실행
    // ──────────────────────────────────────────────

    function finalizeProposal(uint256 _proposalId) external {
        Proposal storage p = _getProposal(_proposalId);
        if (p.status != ProposalStatus.Active) revert ProposalNotActive(_proposalId);
        if (block.timestamp <= p.endTime) revert ProposalNotActive(_proposalId);

        uint256 totalVoted = p.forVotes + p.againstVotes + p.abstainVotes;
        uint256 quorumRequired = (totalVotingPower * quorumBps) / BPS_DENOMINATOR;

        if (totalVoted < quorumRequired) {
            p.status = ProposalStatus.Defeated;
        } else if (p.forVotes > p.againstVotes) {
            p.status = ProposalStatus.Succeeded;
        } else {
            p.status = ProposalStatus.Defeated;
        }
    }

    function executeProposal(uint256 _proposalId) external onlyOwner {
        Proposal storage p = _getProposal(_proposalId);
        if (p.status != ProposalStatus.Succeeded) revert ProposalNotSucceeded(_proposalId);
        if (p.executed) revert AlreadyExecuted(_proposalId);

        p.executed = true;
        p.status = ProposalStatus.Executed;

        emit ProposalExecuted(_proposalId);
    }

    function cancelProposal(uint256 _proposalId) external {
        Proposal storage p = _getProposal(_proposalId);
        if (msg.sender != p.proposer && msg.sender != owner()) revert NotMember();
        if (p.status != ProposalStatus.Active && p.status != ProposalStatus.Pending) revert ProposalNotActive(_proposalId);

        p.status = ProposalStatus.Cancelled;
        emit ProposalCancelled(_proposalId);
    }

    // ──────────────────────────────────────────────
    // 설정 + 조회
    // ──────────────────────────────────────────────

    function setQuorum(uint256 _newQuorumBps) external onlyOwner {
        if (_newQuorumBps == 0 || _newQuorumBps > BPS_DENOMINATOR) revert InvalidQuorum();
        uint256 old = quorumBps;
        quorumBps = _newQuorumBps;
        emit QuorumUpdated(old, _newQuorumBps);
    }

    function getProposalVotes(uint256 _proposalId) external view returns (uint256 forVotes, uint256 againstVotes, uint256 abstainVotes) {
        Proposal storage p = _getProposal(_proposalId);
        return (p.forVotes, p.againstVotes, p.abstainVotes);
    }

    function _getProposal(uint256 _id) internal view returns (Proposal storage) {
        if (_id >= nextProposalId) revert ProposalNotFound(_id);
        return proposals[_id];
    }
}
