// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title PropAIToken
 * @notice STO (Security Token Offering) 부동산 토큰화 컨트랙트
 * @dev ERC-1400 간소화 — KYC/AML 화이트리스트 + 배당 분배 + 잠금(lockup)
 *
 * 기능:
 * - 토큰 발행 (프로젝트별 부동산 증권)
 * - KYC 화이트리스트 관리
 * - 잠금 기간(lockup) 제어
 * - 배당 분배 (임대 수익 + 매각 차익)
 * - 투자자 간 P2P 양도 (화이트리스트 조건)
 */
contract PropAIToken is Ownable, Pausable, ReentrancyGuard {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public totalSupply;

    uint64 public lockupEndTime;
    uint256 public totalDividendsDistributed;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => bool) public whitelisted;
    mapping(address => uint256) public dividendCredit; // 미수령 배당
    mapping(address => uint256) public dividendDebit;  // 이미 반영된 배당
    uint256 public dividendPerToken; // 누적 배당/토큰 (1e18 정밀도)

    error NotWhitelisted(address account);
    error LockupActive();
    error InsufficientBalance(address account, uint256 requested, uint256 available);
    error InsufficientAllowance(address owner, address spender, uint256 requested, uint256 available);
    error InvalidAddress();
    error InvalidAmount();
    error TransferFailed();
    error NoDividend();

    event Transfer(address indexed from, address indexed to, uint256 amount);
    event Approval(address indexed owner, address indexed spender, uint256 amount);
    event WhitelistUpdated(address indexed account, bool status);
    event TokensMinted(address indexed to, uint256 amount);
    event TokensBurned(address indexed from, uint256 amount);
    event DividendDistributed(uint256 totalAmount, uint256 perToken);
    event DividendClaimed(address indexed account, uint256 amount);
    event LockupSet(uint64 endTime);

    modifier onlyWhitelisted(address _account) {
        if (!whitelisted[_account]) revert NotWhitelisted(_account);
        _;
    }

    modifier lockupExpired() {
        if (block.timestamp < lockupEndTime) revert LockupActive();
        _;
    }

    constructor(
        string memory _name,
        string memory _symbol,
        uint64 _lockupEndTime
    ) Ownable(msg.sender) {
        name = _name;
        symbol = _symbol;
        lockupEndTime = _lockupEndTime;
    }

    // ──────────────────────────────────────────────
    // KYC 화이트리스트
    // ──────────────────────────────────────────────

    function setWhitelist(address _account, bool _status) external onlyOwner {
        if (_account == address(0)) revert InvalidAddress();
        whitelisted[_account] = _status;
        emit WhitelistUpdated(_account, _status);
    }

    function batchSetWhitelist(address[] calldata _accounts, bool _status) external onlyOwner {
        for (uint256 i = 0; i < _accounts.length; i++) {
            if (_accounts[i] == address(0)) revert InvalidAddress();
            whitelisted[_accounts[i]] = _status;
            emit WhitelistUpdated(_accounts[i], _status);
        }
    }

    // ──────────────────────────────────────────────
    // 토큰 발행/소각
    // ──────────────────────────────────────────────

    function mint(address _to, uint256 _amount) external onlyOwner onlyWhitelisted(_to) whenNotPaused {
        if (_amount == 0) revert InvalidAmount();

        _settleDividend(_to);
        totalSupply += _amount;
        balanceOf[_to] += _amount;
        _syncDividendDebit(_to);

        emit TokensMinted(_to, _amount);
        emit Transfer(address(0), _to, _amount);
    }

    function burn(uint256 _amount) external {
        if (_amount == 0) revert InvalidAmount();
        if (balanceOf[msg.sender] < _amount) revert InsufficientBalance(msg.sender, _amount, balanceOf[msg.sender]);

        _settleDividend(msg.sender);
        totalSupply -= _amount;
        balanceOf[msg.sender] -= _amount;
        _syncDividendDebit(msg.sender);

        emit TokensBurned(msg.sender, _amount);
        emit Transfer(msg.sender, address(0), _amount);
    }

    // ──────────────────────────────────────────────
    // 양도 (잠금 기간 이후, 화이트리스트 양자)
    // ──────────────────────────────────────────────

    function transfer(address _to, uint256 _amount)
        external
        lockupExpired
        onlyWhitelisted(msg.sender)
        onlyWhitelisted(_to)
        whenNotPaused
        returns (bool)
    {
        _transfer(msg.sender, _to, _amount);
        return true;
    }

    function approve(address _spender, uint256 _amount) external returns (bool) {
        allowance[msg.sender][_spender] = _amount;
        emit Approval(msg.sender, _spender, _amount);
        return true;
    }

    function transferFrom(address _from, address _to, uint256 _amount)
        external
        lockupExpired
        onlyWhitelisted(_from)
        onlyWhitelisted(_to)
        whenNotPaused
        returns (bool)
    {
        uint256 currentAllowance = allowance[_from][msg.sender];
        if (currentAllowance < _amount) revert InsufficientAllowance(_from, msg.sender, _amount, currentAllowance);
        allowance[_from][msg.sender] = currentAllowance - _amount;
        _transfer(_from, _to, _amount);
        return true;
    }

    function _transfer(address _from, address _to, uint256 _amount) internal {
        if (_to == address(0)) revert InvalidAddress();
        if (_amount == 0) revert InvalidAmount();
        if (balanceOf[_from] < _amount) revert InsufficientBalance(_from, _amount, balanceOf[_from]);

        _settleDividend(_from);
        _settleDividend(_to);

        balanceOf[_from] -= _amount;
        balanceOf[_to] += _amount;

        _syncDividendDebit(_from);
        _syncDividendDebit(_to);

        emit Transfer(_from, _to, _amount);
    }

    // ──────────────────────────────────────────────
    // 배당 분배
    // ──────────────────────────────────────────────

    function distributeDividend() external payable onlyOwner nonReentrant {
        if (msg.value == 0) revert InvalidAmount();
        if (totalSupply == 0) revert InvalidAmount();

        dividendPerToken += (msg.value * 1e18) / totalSupply;
        totalDividendsDistributed += msg.value;

        emit DividendDistributed(msg.value, dividendPerToken);
    }

    function claimDividend() external nonReentrant {
        _settleDividend(msg.sender);
        uint256 amount = dividendCredit[msg.sender];
        if (amount == 0) revert NoDividend();

        dividendCredit[msg.sender] = 0;

        (bool success, ) = payable(msg.sender).call{value: amount}("");
        if (!success) revert TransferFailed();

        emit DividendClaimed(msg.sender, amount);
    }

    function pendingDividend(address _account) external view returns (uint256) {
        uint256 owed = (balanceOf[_account] * dividendPerToken) / 1e18;
        return dividendCredit[_account] + owed - dividendDebit[_account];
    }

    /**
     * @dev 현재 잔액 기준 미정산 배당을 credit으로 정산.
     *      잔액 변경 전에 호출해야 한다 (MasterChef 정산 패턴 1단계).
     *      불변식: dividendDebit는 항상 직전 sync 시점의 balance×dpt이고
     *      dividendPerToken은 단조증가하므로 owed >= debit (언더플로 불가).
     */
    function _settleDividend(address _account) internal {
        uint256 owed = (balanceOf[_account] * dividendPerToken) / 1e18;
        dividendCredit[_account] += owed - dividendDebit[_account];
        dividendDebit[_account] = owed;
    }

    /**
     * @dev 잔액 변경 직후 debit를 새 잔액 기준으로 재동기화 (패턴 2단계).
     *      이를 누락하면 mint 후 과다적립, burn/transfer 후 언더플로 DoS 발생.
     */
    function _syncDividendDebit(address _account) internal {
        dividendDebit[_account] = (balanceOf[_account] * dividendPerToken) / 1e18;
    }

    // ──────────────────────────────────────────────
    // 관리
    // ──────────────────────────────────────────────

    function setLockupEndTime(uint64 _endTime) external onlyOwner {
        lockupEndTime = _endTime;
        emit LockupSet(_endTime);
    }

    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }
}
