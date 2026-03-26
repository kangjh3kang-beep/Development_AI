import { expect } from "chai";
import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-network-helpers";

const VOTE_AGAINST = 0n;
const VOTE_FOR = 1n;
const VOTE_ABSTAIN = 2n;

const STATUS_PENDING = 0n;
const STATUS_ACTIVE = 1n;
const STATUS_DEFEATED = 2n;
const STATUS_SUCCEEDED = 3n;
const STATUS_EXECUTED = 4n;

async function deployFixture() {
  const [owner, member1, member2, member3, outsider] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("PropAIGovernance");
  const contract = await factory.deploy();
  await contract.waitForDeployment();
  return { contract, owner, member1, member2, member3, outsider };
}

const THREE_DAYS = 3 * 24 * 60 * 60;

describe("PropAIGovernance", function () {
  describe("멤버 관리", function () {
    it("관리자가 멤버를 추가할 수 있다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      const info = await contract.members(member1.address);
      expect(info.votingPower).to.equal(100n);
      expect(info.isActive).to.be.true;
    });

    it("관리자가 멤버를 제거할 수 있다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      await contract.connect(owner).removeMember(member1.address);
      const info = await contract.members(member1.address);
      expect(info.isActive).to.be.false;
    });

    it("투표권을 업데이트할 수 있다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      await contract.connect(owner).updateVotingPower(member1.address, 200);
      const info = await contract.members(member1.address);
      expect(info.votingPower).to.equal(200n);
    });

    it("중복 멤버 추가 시 실패한다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      await expect(
        contract.connect(owner).addMember(member1.address, 200)
      ).to.be.revertedWithCustomError(contract, "MemberAlreadyExists");
    });
  });

  describe("제안 생성", function () {
    it("멤버가 제안을 생성할 수 있다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      const docHash = ethers.id("proposal-doc-v1");

      await contract.connect(member1).createProposal(
        "시공사 선정", "A건설 vs B건설 비교 검토", docHash, THREE_DAYS
      );

      const proposal = await contract.proposals(0n);
      expect(proposal.proposer).to.equal(member1.address);
      expect(proposal.title).to.equal("시공사 선정");
      expect(proposal.status).to.equal(STATUS_ACTIVE);
    });

    it("비멤버는 제안을 생성할 수 없다", async function () {
      const { contract, outsider } = await deployFixture();
      await expect(
        contract.connect(outsider).createProposal("테스트", "내용", ethers.ZeroHash, THREE_DAYS)
      ).to.be.revertedWithCustomError(contract, "NotMember");
    });

    it("투표 기간이 너무 짧으면 실패한다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      await expect(
        contract.connect(member1).createProposal("테스트", "내용", ethers.ZeroHash, 60) // 1분
      ).to.be.revertedWithCustomError(contract, "VotingPeriodInvalid");
    });
  });

  describe("투표", function () {
    it("멤버가 찬성/반대/기권 투표할 수 있다", async function () {
      const { contract, owner, member1, member2, member3 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      await contract.connect(owner).addMember(member2.address, 200);
      await contract.connect(owner).addMember(member3.address, 50);

      const docHash = ethers.id("proposal-doc");
      await contract.connect(member1).createProposal("분양가 결정", "3.3㎡당 2,800만원", docHash, THREE_DAYS);

      await contract.connect(member1).castVote(0n, VOTE_FOR);
      await contract.connect(member2).castVote(0n, VOTE_FOR);
      await contract.connect(member3).castVote(0n, VOTE_AGAINST);

      const [forVotes, againstVotes, abstainVotes] = await contract.getProposalVotes(0n);
      expect(forVotes).to.equal(300n);
      expect(againstVotes).to.equal(50n);
      expect(abstainVotes).to.equal(0n);
    });

    it("이중 투표를 방지한다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      await contract.connect(member1).createProposal("테스트", "내용", ethers.ZeroHash, THREE_DAYS);
      await contract.connect(member1).castVote(0n, VOTE_FOR);

      await expect(
        contract.connect(member1).castVote(0n, VOTE_AGAINST)
      ).to.be.revertedWithCustomError(contract, "AlreadyVoted");
    });
  });

  describe("확정 + 실행", function () {
    it("투표 종료 후 쿼럼 충족 + 과반 찬성 시 Succeeded", async function () {
      const { contract, owner, member1, member2 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 300);
      await contract.connect(owner).addMember(member2.address, 200);

      await contract.connect(member1).createProposal("설계 변경", "평면도 B안", ethers.ZeroHash, THREE_DAYS);
      await contract.connect(member1).castVote(0n, VOTE_FOR);
      await contract.connect(member2).castVote(0n, VOTE_FOR);

      // 투표 기간 경과
      await time.increase(THREE_DAYS + 1);
      await contract.finalizeProposal(0n);

      const proposal = await contract.proposals(0n);
      expect(proposal.status).to.equal(STATUS_SUCCEEDED);
    });

    it("관리자가 성공한 제안을 실행할 수 있다", async function () {
      const { contract, owner, member1 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 500);
      await contract.connect(member1).createProposal("테스트", "내용", ethers.ZeroHash, THREE_DAYS);
      await contract.connect(member1).castVote(0n, VOTE_FOR);
      await time.increase(THREE_DAYS + 1);
      await contract.finalizeProposal(0n);

      await contract.connect(owner).executeProposal(0n);
      const proposal = await contract.proposals(0n);
      expect(proposal.status).to.equal(STATUS_EXECUTED);
      expect(proposal.executed).to.be.true;
    });

    it("쿼럼 미달 시 Defeated", async function () {
      const { contract, owner, member1, member2, member3 } = await deployFixture();
      await contract.connect(owner).addMember(member1.address, 100);
      await contract.connect(owner).addMember(member2.address, 100);
      await contract.connect(owner).addMember(member3.address, 100);

      await contract.connect(member1).createProposal("테스트", "내용", ethers.ZeroHash, THREE_DAYS);
      await contract.connect(member1).castVote(0n, VOTE_FOR); // 100/300 = 33% < 50% quorum

      await time.increase(THREE_DAYS + 1);
      await contract.finalizeProposal(0n);

      const proposal = await contract.proposals(0n);
      expect(proposal.status).to.equal(STATUS_DEFEATED);
    });
  });

  describe("쿼럼 설정", function () {
    it("관리자가 쿼럼을 변경할 수 있다", async function () {
      const { contract, owner } = await deployFixture();
      await contract.connect(owner).setQuorum(3000); // 30%
      expect(await contract.quorumBps()).to.equal(3000n);
    });
  });
});
