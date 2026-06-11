import { expect } from "chai";
import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-network-helpers";

async function deployFixture() {
  const [owner, investor1, investor2, outsider] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("PropAIToken");
  const lockupEnd = (await time.latest()) + 30 * 86400; // 30일 후 잠금 해제
  const token = await factory.deploy("PropAI Gangnam Tower", "PAGT", lockupEnd);
  await token.waitForDeployment();
  return { token, owner, investor1, investor2, outsider, lockupEnd };
}

describe("PropAIToken (STO)", function () {
  describe("화이트리스트", function () {
    it("관리자가 투자자를 화이트리스트에 추가할 수 있다", async function () {
      const { token, owner, investor1 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      expect(await token.whitelisted(investor1.address)).to.be.true;
    });

    it("배치 화이트리스트 설정이 가능하다", async function () {
      const { token, owner, investor1, investor2 } = await deployFixture();
      await token.connect(owner).batchSetWhitelist([investor1.address, investor2.address], true);
      expect(await token.whitelisted(investor1.address)).to.be.true;
      expect(await token.whitelisted(investor2.address)).to.be.true;
    });
  });

  describe("토큰 발행/소각", function () {
    it("화이트리스트 투자자에게 토큰을 발행할 수 있다", async function () {
      const { token, owner, investor1 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      const amount = ethers.parseEther("1000");

      await token.connect(owner).mint(investor1.address, amount);
      expect(await token.balanceOf(investor1.address)).to.equal(amount);
      expect(await token.totalSupply()).to.equal(amount);
    });

    it("비화이트리스트 주소에는 발행할 수 없다", async function () {
      const { token, owner, outsider } = await deployFixture();
      await expect(
        token.connect(owner).mint(outsider.address, ethers.parseEther("100"))
      ).to.be.revertedWithCustomError(token, "NotWhitelisted");
    });

    it("투자자가 토큰을 소각할 수 있다", async function () {
      const { token, owner, investor1 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));

      await token.connect(investor1).burn(ethers.parseEther("200"));
      expect(await token.balanceOf(investor1.address)).to.equal(ethers.parseEther("800"));
    });
  });

  describe("양도 (잠금 기간)", function () {
    it("잠금 기간 내 양도 시 실패한다", async function () {
      const { token, owner, investor1, investor2 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).setWhitelist(investor2.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));

      await expect(
        token.connect(investor1).transfer(investor2.address, ethers.parseEther("100"))
      ).to.be.revertedWithCustomError(token, "LockupActive");
    });

    it("잠금 해제 후 화이트리스트 간 양도가 가능하다", async function () {
      const { token, owner, investor1, investor2, lockupEnd } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).setWhitelist(investor2.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));

      // 잠금 기간 경과
      await time.increaseTo(lockupEnd + 1);

      await token.connect(investor1).transfer(investor2.address, ethers.parseEther("300"));
      expect(await token.balanceOf(investor1.address)).to.equal(ethers.parseEther("700"));
      expect(await token.balanceOf(investor2.address)).to.equal(ethers.parseEther("300"));
    });

    it("비화이트리스트 주소로 양도 시 실패한다", async function () {
      const { token, owner, investor1, outsider, lockupEnd } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));
      await time.increaseTo(lockupEnd + 1);

      await expect(
        token.connect(investor1).transfer(outsider.address, ethers.parseEther("100"))
      ).to.be.revertedWithCustomError(token, "NotWhitelisted");
    });
  });

  describe("배당 분배", function () {
    it("관리자가 배당을 분배할 수 있다", async function () {
      const { token, owner, investor1, investor2 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).setWhitelist(investor2.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("700"));
      await token.connect(owner).mint(investor2.address, ethers.parseEther("300"));

      const dividend = ethers.parseEther("10");
      await token.connect(owner).distributeDividend({ value: dividend });

      // investor1: 700/1000 * 10 = 7 ETH
      const pending1 = await token.pendingDividend(investor1.address);
      expect(pending1).to.equal(ethers.parseEther("7"));

      // investor2: 300/1000 * 10 = 3 ETH
      const pending2 = await token.pendingDividend(investor2.address);
      expect(pending2).to.equal(ethers.parseEther("3"));
    });

    it("투자자가 배당을 수령할 수 있다", async function () {
      const { token, owner, investor1 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));

      await token.connect(owner).distributeDividend({ value: ethers.parseEther("5") });

      const balBefore = await ethers.provider.getBalance(investor1.address);
      const tx = await token.connect(investor1).claimDividend();
      const receipt = await tx.wait();
      const gasUsed = receipt!.gasUsed * receipt!.gasPrice;
      const balAfter = await ethers.provider.getBalance(investor1.address);

      expect(balAfter - balBefore + gasUsed).to.equal(ethers.parseEther("5"));
    });

    it("배당이 없으면 수령 시 실패한다", async function () {
      const { token, owner, investor1 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));

      await expect(
        token.connect(investor1).claimDividend()
      ).to.be.revertedWithCustomError(token, "NoDividend");
    });
  });

  describe("배당 회계 회귀 (2026-06 감사 H-1 수정)", function () {
    it("burn 후에도 기존 배당을 정상 수령할 수 있다 (언더플로 DoS 회귀)", async function () {
      const { token, owner, investor1 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));

      await token.connect(owner).distributeDividend({ value: ethers.parseEther("10") });

      // 수정 전: burn 후 debit가 옛 잔액 기준으로 남아 claim/transfer/burn 영구 revert
      await token.connect(investor1).burn(ethers.parseEther("200"));

      const balBefore = await ethers.provider.getBalance(investor1.address);
      const tx = await token.connect(investor1).claimDividend();
      const receipt = await tx.wait();
      const gasUsed = receipt!.gasUsed * receipt!.gasPrice;
      const balAfter = await ethers.provider.getBalance(investor1.address);

      // burn 전 분배된 10 ETH 전액 (당시 단독 보유자)
      expect(balAfter - balBefore + gasUsed).to.equal(ethers.parseEther("10"));
    });

    it("transfer 후 양도인·양수인 모두 배당 회계가 정확하다", async function () {
      const { token, owner, investor1, investor2, lockupEnd } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).setWhitelist(investor2.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));
      await time.increaseTo(lockupEnd + 1);

      // 1차 배당: investor1 단독 보유 → 10 ETH 전액
      await token.connect(owner).distributeDividend({ value: ethers.parseEther("10") });

      // 400 양도 후 2차 배당: 600/400 비율
      await token.connect(investor1).transfer(investor2.address, ethers.parseEther("400"));
      await token.connect(owner).distributeDividend({ value: ethers.parseEther("10") });

      expect(await token.pendingDividend(investor1.address)).to.equal(ethers.parseEther("16")); // 10 + 6
      expect(await token.pendingDividend(investor2.address)).to.equal(ethers.parseEther("4"));  // 0 + 4

      // 양쪽 모두 실제 수령 가능 (revert 없음)
      await token.connect(investor1).claimDividend();
      await token.connect(investor2).claimDividend();
    });

    it("mint가 과거 배당을 소급 적립하지 않는다 (지급불능 회귀)", async function () {
      const { token, owner, investor1, investor2 } = await deployFixture();
      await token.connect(owner).setWhitelist(investor1.address, true);
      await token.connect(owner).setWhitelist(investor2.address, true);
      await token.connect(owner).mint(investor1.address, ethers.parseEther("1000"));

      // investor2가 없던 시점의 배당
      await token.connect(owner).distributeDividend({ value: ethers.parseEther("10") });

      // 이후 investor2에게 mint — 과거 배당에 대한 권리가 생기면 안 됨
      await token.connect(owner).mint(investor2.address, ethers.parseEther("1000"));
      expect(await token.pendingDividend(investor2.address)).to.equal(0n);

      // 추가 mint 후에도 적립 합계 = 분배 총액 (컨트랙트 지급여력 보존)
      await token.connect(owner).distributeDividend({ value: ethers.parseEther("10") });
      const p1 = await token.pendingDividend(investor1.address); // 10 + 5
      const p2 = await token.pendingDividend(investor2.address); // 0 + 5
      expect(p1 + p2).to.equal(ethers.parseEther("20"));

      // 전원 수령해도 잔액 부족 revert가 없어야 함
      await token.connect(investor1).claimDividend();
      await token.connect(investor2).claimDividend();
    });
  });

  describe("관리 기능", function () {
    it("잠금 기간을 변경할 수 있다", async function () {
      const { token, owner } = await deployFixture();
      const newLockup = (await time.latest()) + 60 * 86400;
      await token.connect(owner).setLockupEndTime(newLockup);
      expect(await token.lockupEndTime()).to.equal(newLockup);
    });

    it("일시정지/해제가 가능하다", async function () {
      const { token, owner } = await deployFixture();
      await token.connect(owner).pause();
      // 일시정지 중 발행 실패
      await token.connect(owner).setWhitelist(owner.address, true);
      await expect(
        token.connect(owner).mint(owner.address, ethers.parseEther("100"))
      ).to.be.reverted; // EnforcedPause
      await token.connect(owner).unpause();
    });
  });
});
