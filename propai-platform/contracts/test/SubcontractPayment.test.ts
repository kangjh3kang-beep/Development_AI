import { expect } from "chai";
import { ethers } from "hardhat";

const STATUS_REGISTERED = 0n;
const STATUS_APPROVED = 1n;
const STATUS_ACTIVE = 2n;
const STATUS_COMPLETED = 3n;
const STATUS_DISPUTED = 4n;

const CLAIM_PENDING = 0n;
const CLAIM_APPROVED = 1n;
const CLAIM_REJECTED = 2n;
const CLAIM_PAID = 3n;

async function deployFixture() {
  const [owner, generalContractor, subcontractor, outsider] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("SubcontractPayment");
  const contract = await factory.deploy();
  await contract.waitForDeployment();
  return { contract, owner, generalContractor, subcontractor, outsider };
}

function futureTimestamp(offsetDays: number) {
  return Math.floor(Date.now() / 1000) + offsetDays * 86400;
}

describe("SubcontractPayment", function () {
  describe("하도급 등록", function () {
    it("원청이 하도급 계약을 등록할 수 있다", async function () {
      const { contract, generalContractor, subcontractor } = await deployFixture();
      const startDate = futureTimestamp(1);
      const endDate = futureTimestamp(180);
      const totalAmount = ethers.parseEther("100");
      const retentionRate = 1000n; // 10%

      const tx = await contract.connect(generalContractor).registerSubcontract(
        subcontractor.address, totalAmount, retentionRate, startDate, endDate
      );
      await tx.wait();

      const sc = await contract.subcontracts(0n);
      expect(sc.generalContractor).to.equal(generalContractor.address);
      expect(sc.subcontractor).to.equal(subcontractor.address);
      expect(sc.totalAmount).to.equal(totalAmount);
      expect(sc.status).to.equal(STATUS_REGISTERED);
    });

    it("잘못된 주소로 등록 시 실패한다", async function () {
      const { contract, generalContractor } = await deployFixture();
      await expect(
        contract.connect(generalContractor).registerSubcontract(
          ethers.ZeroAddress, ethers.parseEther("100"), 1000, futureTimestamp(1), futureTimestamp(180)
        )
      ).to.be.revertedWithCustomError(contract, "InvalidAddress");
    });

    it("유보율이 20% 초과 시 실패한다", async function () {
      const { contract, generalContractor, subcontractor } = await deployFixture();
      await expect(
        contract.connect(generalContractor).registerSubcontract(
          subcontractor.address, ethers.parseEther("100"), 2500, futureTimestamp(1), futureTimestamp(180)
        )
      ).to.be.revertedWithCustomError(contract, "RetentionTooHigh");
    });
  });

  describe("승인 + 기성 청구", function () {
    it("발주자가 하도급을 승인할 수 있다", async function () {
      const { contract, owner, generalContractor, subcontractor } = await deployFixture();
      await contract.connect(generalContractor).registerSubcontract(
        subcontractor.address, ethers.parseEther("100"), 1000, futureTimestamp(1), futureTimestamp(180)
      );
      await contract.connect(owner).approveSubcontract(0n);

      const sc = await contract.subcontracts(0n);
      expect(sc.status).to.equal(STATUS_APPROVED);
    });

    it("하도급업체가 기성을 청구할 수 있다", async function () {
      const { contract, owner, generalContractor, subcontractor } = await deployFixture();
      await contract.connect(generalContractor).registerSubcontract(
        subcontractor.address, ethers.parseEther("100"), 1000, futureTimestamp(1), futureTimestamp(180)
      );
      await contract.connect(owner).approveSubcontract(0n);

      const tx = await contract.connect(subcontractor).claimPayment(0n, ethers.parseEther("30"), "1차 기성");
      await tx.wait();

      const claim = await contract.claims(0n);
      expect(claim.amount).to.equal(ethers.parseEther("30"));
      expect(claim.status).to.equal(CLAIM_PENDING);
    });

    it("비승인 상태에서 기성 청구 시 실패한다", async function () {
      const { contract, generalContractor, subcontractor } = await deployFixture();
      await contract.connect(generalContractor).registerSubcontract(
        subcontractor.address, ethers.parseEther("100"), 1000, futureTimestamp(1), futureTimestamp(180)
      );
      await expect(
        contract.connect(subcontractor).claimPayment(0n, ethers.parseEther("30"), "1차 기성")
      ).to.be.revertedWithCustomError(contract, "InvalidStatus");
    });
  });

  describe("직불 + 유보금", function () {
    it("발주자가 하도급업체에 직불할 수 있다", async function () {
      const { contract, owner, generalContractor, subcontractor } = await deployFixture();
      const amount = ethers.parseEther("100");
      await contract.connect(generalContractor).registerSubcontract(
        subcontractor.address, amount, 1000, futureTimestamp(1), futureTimestamp(180)
      );
      await contract.connect(owner).approveSubcontract(0n);
      await contract.connect(subcontractor).claimPayment(0n, ethers.parseEther("30"), "1차 기성");

      // 유보율 10% → 30 ETH 중 3 ETH 유보, 27 ETH 직불
      const netPayment = ethers.parseEther("27");
      const balanceBefore = await ethers.provider.getBalance(subcontractor.address);

      await contract.connect(owner).releaseDirectPayment(0n, { value: netPayment });

      const balanceAfter = await ethers.provider.getBalance(subcontractor.address);
      expect(balanceAfter - balanceBefore).to.equal(netPayment);

      const retention = await contract.retentionBalance(0n);
      expect(retention).to.equal(ethers.parseEther("3"));
    });
  });

  describe("분쟁 + 완료", function () {
    it("계약을 분쟁 상태로 전환할 수 있다", async function () {
      const { contract, owner, generalContractor, subcontractor } = await deployFixture();
      await contract.connect(generalContractor).registerSubcontract(
        subcontractor.address, ethers.parseEther("100"), 1000, futureTimestamp(1), futureTimestamp(180)
      );
      await contract.connect(owner).approveSubcontract(0n);
      await contract.connect(subcontractor).claimPayment(0n, ethers.parseEther("10"), "1차");
      await contract.connect(owner).releaseDirectPayment(0n, { value: ethers.parseEther("9") });

      await contract.connect(subcontractor).disputeSubcontract(0n);
      const sc = await contract.subcontracts(0n);
      expect(sc.status).to.equal(STATUS_DISPUTED);
    });

    it("외부인은 분쟁을 제기할 수 없다", async function () {
      const { contract, owner, generalContractor, subcontractor, outsider } = await deployFixture();
      await contract.connect(generalContractor).registerSubcontract(
        subcontractor.address, ethers.parseEther("100"), 1000, futureTimestamp(1), futureTimestamp(180)
      );
      await expect(
        contract.connect(outsider).disputeSubcontract(0n)
      ).to.be.revertedWithCustomError(contract, "Unauthorized");
    });
  });
});
