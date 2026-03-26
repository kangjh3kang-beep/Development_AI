import { expect } from "chai";
import { ethers } from "hardhat";

const STATUS_PENDING_FUNDING = 0n;
const STATUS_FUNDED = 1n;
const STATUS_DISPUTED = 2n;
const STATUS_RELEASED = 3n;
const STATUS_REFUNDED = 4n;

async function deployEscrowFixture() {
  const [owner, payer, payee, subcontractor, outsider] = await ethers.getSigners();
  const escrowFactory = await ethers.getContractFactory("PropAIEscrow");
  const escrow = await escrowFactory.deploy();

  await escrow.waitForDeployment();

  return { escrow, owner, payer, payee, subcontractor, outsider };
}

async function getFutureExpiry(offsetSeconds = 3600) {
  const latestBlock = await ethers.provider.getBlock("latest");

  if (!latestBlock) {
    throw new Error("최신 블록을 읽지 못했습니다.");
  }

  return latestBlock.timestamp + offsetSeconds;
}

async function createFundedEscrow(amount = ethers.parseEther("10")) {
  const { escrow, owner, payer, payee, subcontractor, outsider } = await deployEscrowFixture();
  const expiresAt = await getFutureExpiry();
  const conditionHash = ethers.id("release-conditions");
  const createReceipt = await escrow
    .connect(payer)
    .createEscrow(payee.address, subcontractor.address, expiresAt, conditionHash);

  await createReceipt.wait();

  const escrowId = 1n;

  await escrow.connect(payer).fundEscrow(escrowId, { value: amount });

  return {
    escrow,
    owner,
    payer,
    payee,
    subcontractor,
    outsider,
    escrowId,
    amount,
    expiresAt,
    conditionHash,
  };
}

describe("PropAIEscrow", function () {
  it("에스크로를 생성하고 핵심 메타데이터를 저장한다", async function () {
    const { escrow, payer, payee, subcontractor } = await deployEscrowFixture();
    const expiresAt = await getFutureExpiry();
    const conditionHash = ethers.id("project-conditions");

    await expect(
      escrow.connect(payer).createEscrow(payee.address, subcontractor.address, expiresAt, conditionHash),
    )
      .to.emit(escrow, "EscrowCreated")
      .withArgs(1n, payer.address, payee.address, subcontractor.address, expiresAt, conditionHash);

    const savedEscrow = await escrow.getEscrow(1n);

    expect(savedEscrow.payer).to.equal(payer.address);
    expect(savedEscrow.payee).to.equal(payee.address);
    expect(savedEscrow.subcontractor).to.equal(subcontractor.address);
    expect(savedEscrow.conditionHash).to.equal(conditionHash);
    expect(savedEscrow.status).to.equal(STATUS_PENDING_FUNDING);
  });

  it("자금 예치 시 총액과 잔액을 기록한다", async function () {
    const { escrow, payer, payee, subcontractor } = await deployEscrowFixture();
    const expiresAt = await getFutureExpiry();
    const amount = ethers.parseEther("12");

    await escrow
      .connect(payer)
      .createEscrow(payee.address, subcontractor.address, expiresAt, ethers.id("funding"));

    await expect(escrow.connect(payer).fundEscrow(1n, { value: amount }))
      .to.emit(escrow, "EscrowFunded")
      .withArgs(1n, amount);

    const savedEscrow = await escrow.getEscrow(1n);

    expect(savedEscrow.totalAmount).to.equal(amount);
    expect(savedEscrow.remainingAmount).to.equal(amount);
    expect(savedEscrow.status).to.equal(STATUS_FUNDED);
  });

  it("정상 지급 시 수수료를 차감하고 수급자와 플랫폼 소유자에게 분배한다", async function () {
    const { escrow, owner, payer, payee, escrowId, amount } = await createFundedEscrow();
    const fee = await escrow.calculateFee(amount);
    const payout = amount - fee;

    await expect(escrow.connect(payer).releaseEscrow(escrowId)).to.changeEtherBalances(
      [escrow, payee, owner],
      [-amount, payout, fee],
    );

    const savedEscrow = await escrow.getEscrow(escrowId);

    expect(savedEscrow.remainingAmount).to.equal(0n);
    expect(savedEscrow.status).to.equal(STATUS_RELEASED);
  });

  it("만료 후에는 잔액을 환불한다", async function () {
    const { escrow, payer, outsider, escrowId, amount } = await createFundedEscrow();

    await ethers.provider.send("evm_increaseTime", [3700]);
    await ethers.provider.send("evm_mine", []);

    await expect(escrow.connect(outsider).autoRefundOnExpiry(escrowId)).to.changeEtherBalances(
      [escrow, payer],
      [-amount, amount],
    );

    const savedEscrow = await escrow.getEscrow(escrowId);

    expect(savedEscrow.status).to.equal(STATUS_REFUNDED);
    expect(savedEscrow.remainingAmount).to.equal(0n);
  });

  it("참여자는 분쟁 상태로 전환할 수 있다", async function () {
    const { escrow, payee, escrowId } = await createFundedEscrow();
    const reasonHash = ethers.id("quality-issue");

    await expect(escrow.connect(payee).initiateDispute(escrowId, reasonHash))
      .to.emit(escrow, "EscrowDisputed")
      .withArgs(escrowId, payee.address, reasonHash);

    const savedEscrow = await escrow.getEscrow(escrowId);

    expect(savedEscrow.status).to.equal(STATUS_DISPUTED);
  });

  it("하도급 직불은 잔액 범위 안에서 부분 지급된다", async function () {
    const { escrow, owner, payer, subcontractor, escrowId, amount } = await createFundedEscrow();
    const grossAmount = ethers.parseEther("4");
    const fee = await escrow.calculateFee(grossAmount);
    const payout = grossAmount - fee;

    await expect(
      escrow.connect(payer).directPaymentToSubcontractor(escrowId, subcontractor.address, grossAmount),
    ).to.changeEtherBalances([escrow, subcontractor, owner], [-grossAmount, payout, fee]);

    const savedEscrow = await escrow.getEscrow(escrowId);

    expect(savedEscrow.remainingAmount).to.equal(amount - grossAmount);
    expect(savedEscrow.status).to.equal(STATUS_FUNDED);
  });

  it("수수료는 basis points 기준으로 계산된다", async function () {
    const { escrow } = await deployEscrowFixture();
    const amount = ethers.parseEther("1");

    expect(await escrow.calculateFee(amount)).to.equal(ethers.parseEther("0.003"));
  });

  it("환불 경로에서 재진입 공격을 막는다", async function () {
    const { escrow, payee } = await deployEscrowFixture();
    const attackerFactory = await ethers.getContractFactory("ReentrantRefundAttacker");
    const attacker = await attackerFactory.deploy(await escrow.getAddress());
    const expiresAt = await getFutureExpiry(1800);
    const fundedAmount = ethers.parseEther("3");

    await attacker.createEscrowAndFund(payee.address, expiresAt, ethers.id("reentrancy"), {
      value: fundedAmount,
    });

    await ethers.provider.send("evm_increaseTime", [1900]);
    await ethers.provider.send("evm_mine", []);

    await attacker.setAttackOnReceive(true);
    await attacker.triggerRefund();

    expect(await attacker.reentrancyBlocked()).to.equal(true);

    const savedEscrow = await escrow.getEscrow(await attacker.escrowId());
    expect(savedEscrow.status).to.equal(STATUS_REFUNDED);
    expect(savedEscrow.remainingAmount).to.equal(0n);
  });

  it("일시정지 상태에서는 핵심 기능 호출이 차단된다", async function () {
    const { escrow, owner, payer, payee, subcontractor } = await deployEscrowFixture();
    const expiresAt = await getFutureExpiry();

    await escrow.connect(owner).pause();

    await expect(
      escrow.connect(payer).createEscrow(payee.address, subcontractor.address, expiresAt, ethers.id("paused")),
    ).to.be.revertedWithCustomError(escrow, "EnforcedPause");
  });

  it("권한 없는 호출자는 자금 예치와 지급을 수행할 수 없다", async function () {
    const { escrow, payer, payee, subcontractor, outsider, escrowId } = await createFundedEscrow();

    await expect(escrow.connect(outsider).releaseEscrow(escrowId)).to.be.revertedWithCustomError(
      escrow,
      "Unauthorized",
    );

    const secondExpiry = await getFutureExpiry();

    await escrow
      .connect(payer)
      .createEscrow(payee.address, subcontractor.address, secondExpiry, ethers.id("second-funding"));

    await expect(escrow.connect(outsider).fundEscrow(2n, { value: ethers.parseEther("1") }))
      .to.be.revertedWithCustomError(escrow, "Unauthorized");
  });
});
