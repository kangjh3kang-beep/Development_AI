import { expect } from "chai";
import { ethers } from "hardhat";
import { createHash } from "node:crypto";

/**
 * DrawRegistry — 추첨 공약·결과 앵커링 계약 락.
 *
 * ★이 파일의 중심 단언은 「저장된다」가 아니라 **「막는다」**이다:
 *   재공약 불가 · 공약 불일치 거부 · 이중 공개 거부 · 권한 없는 호출 거부.
 *   ***저장만 잠그면 「아무 값이나 받는 창고」도 통과한다.***
 */
describe("DrawRegistry", () => {
  const drawId = ethers.keccak256(ethers.toUtf8Bytes("dongho:group-1"));
  // ★오프체인 검증기와 **같은 해시 함수**(SHA-256)로 공약을 만든다.
  //   keccak 으로 만들면 체인이 거부한다 — 그 사실 자체를 아래에서 태운다.
  const nonce = "0x" + "a7".repeat(32);
  const commitHash = "0x" + createHash("sha256")
    .update(Buffer.from(nonce.slice(2), "hex")).digest("hex");
  const participants = ethers.keccak256(ethers.toUtf8Bytes("roster-v1"));
  const resultRoot = ethers.keccak256(ethers.toUtf8Bytes("merkle-root"));

  async function deploy() {
    const [owner, operator, outsider] = await ethers.getSigners();
    const F = await ethers.getContractFactory("DrawRegistry");
    const c = await F.deploy(owner.address);
    await c.waitForDeployment();
    return { c, owner, operator, outsider };
  }

  it("공약→공개 정상 경로가 돌고, 체인이 선후를 판정한다", async () => {
    const { c } = await deploy();
    await expect(c.commitDraw(drawId, commitHash, participants))
      .to.emit(c, "DrawCommitted");
    // ★공개 전에는 「선후」가 성립하지 않는다(공허 방지 — 항상 true 를 돌려주는 구현 차단)
    expect(await c.commitPrecededReveal(drawId)).to.equal(false);

    await ethers.provider.send("evm_increaseTime", [5]);
    await expect(c.revealDraw(drawId, nonce, resultRoot)).to.emit(c, "DrawRevealed");

    // ★★오프체인에서 **기계가 판정하지 못하던** 명제가 여기서 판정된다
    expect(await c.commitPrecededReveal(drawId)).to.equal(true);
    const d = await c.getDraw(drawId);
    expect(d.nonce).to.equal(nonce);
    expect(d.resultRoot).to.equal(resultRoot);
    expect(d.committedAt).to.be.lessThan(d.revealedAt);
  });

  it("★재공약을 거부한다 — 오프체인 UNIQUE 와 같은 불변식", async () => {
    const { c } = await deploy();
    await c.commitDraw(drawId, commitHash, participants);
    await expect(c.commitDraw(drawId, commitHash, participants))
      .to.be.revertedWithCustomError(c, "AlreadyCommitted");
    // 다른 공약값으로도 안 된다(값만 바꿔 덮어쓰는 경로 차단)
    const other = "0x" + "bb".repeat(32);
    await expect(c.commitDraw(drawId, other, participants))
      .to.be.revertedWithCustomError(c, "AlreadyCommitted");
  });

  it("★★체인이 스스로 공약을 검산한다 — 다른 nonce 는 거부", async () => {
    const { c } = await deploy();
    await c.commitDraw(drawId, commitHash, participants);
    const wrong = "0x" + "ff".repeat(32);
    await expect(c.revealDraw(drawId, wrong, resultRoot))
      .to.be.revertedWithCustomError(c, "CommitMismatch");
    // ★두 모집단 — 옳은 nonce 는 통과한다(거부만 보면 「항상 거부」도 통과한다)
    await expect(c.revealDraw(drawId, nonce, resultRoot)).to.emit(c, "DrawRevealed");
  });

  it("★해시 함수가 오프체인과 같아야 한다 — keccak 공약은 거부된다", async () => {
    const { c } = await deploy();
    const keccakCommit = ethers.keccak256(nonce);   // ← 일부러 다른 함수
    await c.commitDraw(drawId, keccakCommit, participants);
    await expect(c.revealDraw(drawId, nonce, resultRoot))
      .to.be.revertedWithCustomError(c, "CommitMismatch");
  });

  it("공개는 한 번만 — 결과를 갈아치울 수 없다", async () => {
    const { c } = await deploy();
    await c.commitDraw(drawId, commitHash, participants);
    await c.revealDraw(drawId, nonce, resultRoot);
    const other = ethers.keccak256(ethers.toUtf8Bytes("다른-결과"));
    await expect(c.revealDraw(drawId, nonce, other))
      .to.be.revertedWithCustomError(c, "AlreadyRevealed");
  });

  it("공약 없이 공개할 수 없다(fail-closed)", async () => {
    const { c } = await deploy();
    await expect(c.revealDraw(drawId, nonce, resultRoot))
      .to.be.revertedWithCustomError(c, "NotCommitted");
  });

  it("빈 공약값을 거부한다 — 0 을 「공약했다」로 읽지 않는다", async () => {
    const { c } = await deploy();
    await expect(c.commitDraw(drawId, ethers.ZeroHash, participants))
      .to.be.revertedWithCustomError(c, "EmptyValue");
  });

  it("★권한 — 외부인은 공약도 공개도 못 한다. 운영자 지정은 owner 만", async () => {
    const { c, operator, outsider } = await deploy();
    await expect(c.connect(outsider).commitDraw(drawId, commitHash, participants))
      .to.be.revertedWithCustomError(c, "NotOperator");
    await expect(c.connect(outsider).setOperator(outsider.address, true))
      .to.be.revertedWithCustomError(c, "OwnableUnauthorizedAccount");
    // ★두 모집단 — 지정된 운영자는 **할 수 있다**(거부만 보면 「아무도 못 함」도 통과한다)
    await c.setOperator(operator.address, true);
    await expect(c.connect(operator).commitDraw(drawId, commitHash, participants))
      .to.emit(c, "DrawCommitted");
  });

  it("★개인정보를 담을 자리가 없다 — 저장 구조가 전부 bytes32/uint64", async () => {
    const { c } = await deploy();
    const d = await c.getDraw(drawId);
    // 구조체 필드가 고정폭이면 이름·연락처 같은 가변 문자열이 **들어갈 수 없다**
    expect(d.commitHash).to.equal(ethers.ZeroHash);
    expect(typeof d.committedAt).to.equal("bigint");
    const abi = (c.interface.fragments as any[]).filter(f => f.type === "function");
    const hasString = abi.some(f => (f.inputs ?? []).some((i: any) => i.type === "string"));
    expect(hasString, "string 인자가 있다 — 개인정보가 올라갈 통로가 생긴다").to.equal(false);
  });
});
