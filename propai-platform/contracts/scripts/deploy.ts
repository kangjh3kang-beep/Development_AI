import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import hre from "hardhat";

/**
 * 배포할 컨트랙트 이름. ★기본값은 종전 그대로 `PropAIEscrow` 다 — 이 스크립트를
 * 일반화하면서 **기존 배포 명령의 동작을 바꾸지 않는다**(회귀가 아닌 근거).
 *
 *   DEPLOY_CONTRACT=DrawRegistry npm run deploy:amoy
 *
 * ★`DrawRegistry` 는 생성자에 **owner 주소**를 받는다. 주지 않으면 **배포자 주소**를 쓴다 —
 *   배포자가 곧 owner 라는 뜻이고, 그 키를 잃으면 운영자 목록을 못 바꾼다(스크립트가 그렇게 알린다).
 */
const CONTRACT = process.env.DEPLOY_CONTRACT || "PropAIEscrow";

/** 생성자 인자 — 컨트랙트마다 다르다. 목록형이 아니라 **이름으로 분기**한다. */
async function constructorArgs(ethers: typeof hre.ethers): Promise<unknown[]> {
  if (CONTRACT === "DrawRegistry") {
    const owner = process.env.DRAW_REGISTRY_OWNER
      || (await ethers.getSigners())[0].address;
    return [owner];
  }
  return [];
}

async function main() {
  const { ethers, artifacts, network } = hre;
  const factory = await ethers.getContractFactory(CONTRACT);
  const ctorArgs = await constructorArgs(ethers);
  const feeData = await ethers.provider.getFeeData();
  const deployRequest = await factory.getDeployTransaction(...ctorArgs);
  const gasEstimate = await ethers.provider.estimateGas(deployRequest);
  const gasLimit = (gasEstimate * 110n) / 100n;
  const deployOverrides: {
    gasLimit: bigint;
    gasPrice?: bigint;
    maxFeePerGas?: bigint;
    maxPriorityFeePerGas?: bigint;
  } = {
    gasLimit,
  };

  if (feeData.gasPrice) {
    deployOverrides.gasPrice = feeData.gasPrice;
  } else {
    if (feeData.maxFeePerGas) {
      deployOverrides.maxFeePerGas = feeData.maxFeePerGas;
    }

    if (feeData.maxPriorityFeePerGas) {
      deployOverrides.maxPriorityFeePerGas = feeData.maxPriorityFeePerGas;
    }
  }

  const contract = await factory.deploy(...ctorArgs, deployOverrides);

  await contract.waitForDeployment();

  const contractAddress = await contract.getAddress();
  const deploymentTx = contract.deploymentTransaction();
  const chainId = Number((await ethers.provider.getNetwork()).chainId);
  const artifact = await artifacts.readArtifact(CONTRACT);
  const deploymentDir = path.join(__dirname, "..", "deployments", network.name);
  const abiDir = path.join(__dirname, "..", "artifacts", "abi");

  await mkdir(deploymentDir, { recursive: true });
  await mkdir(abiDir, { recursive: true });

  const deploymentFile = path.join(deploymentDir, `${CONTRACT}.json`);
  const abiFile = path.join(abiDir, `${CONTRACT}.abi.json`);
  const payload = {
    contractName: CONTRACT,
    network: network.name,
    chainId,
    address: contractAddress,
    deploymentTransactionHash: deploymentTx?.hash ?? null,
    deployedAt: new Date().toISOString(),
    abi: artifact.abi,
    bytecode: artifact.bytecode,
    deployedBytecode: artifact.deployedBytecode,
  };

  await writeFile(deploymentFile, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  await writeFile(abiFile, `${JSON.stringify(artifact.abi, null, 2)}\n`, "utf8");

  console.log(`network=${network.name}`);
  console.log(`address=${contractAddress}`);
  console.log(`gasEstimate=${gasEstimate.toString()}`);
  console.log(`gasLimit=${gasLimit.toString()}`);
  // ★종전엔 이 줄이 `PropAIEscrow` 를 **하드코딩**해서, DrawRegistry 를 배포하고도
  //   「artifact=…/PropAIEscrow.json」이라고 **거짓으로** 찍었다(실측). 배포 보고가 틀리면
  //   다음 사람이 **없는 파일을 찾으러 간다.**
  console.log(`artifact=${path.join("artifacts", "src", `${CONTRACT}.sol`, `${CONTRACT}.json`)}`);
  console.log(`abi=${abiFile}`);
  console.log(`deployment=${deploymentFile}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
