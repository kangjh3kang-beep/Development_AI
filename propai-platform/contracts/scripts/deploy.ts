import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import hre from "hardhat";

async function main() {
  const { ethers, artifacts, network } = hre;
  const factory = await ethers.getContractFactory("PropAIEscrow");
  const feeData = await ethers.provider.getFeeData();
  const deployRequest = await factory.getDeployTransaction();
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

  const contract = await factory.deploy(deployOverrides);

  await contract.waitForDeployment();

  const contractAddress = await contract.getAddress();
  const deploymentTx = contract.deploymentTransaction();
  const chainId = Number((await ethers.provider.getNetwork()).chainId);
  const artifact = await artifacts.readArtifact("PropAIEscrow");
  const deploymentDir = path.join(__dirname, "..", "deployments", network.name);
  const abiDir = path.join(__dirname, "..", "artifacts", "abi");

  await mkdir(deploymentDir, { recursive: true });
  await mkdir(abiDir, { recursive: true });

  const deploymentFile = path.join(deploymentDir, "PropAIEscrow.json");
  const abiFile = path.join(abiDir, "PropAIEscrow.abi.json");
  const payload = {
    contractName: "PropAIEscrow",
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
  console.log(`artifact=${path.join("artifacts", "src", "PropAIEscrow.sol", "PropAIEscrow.json")}`);
  console.log(`abi=${abiFile}`);
  console.log(`deployment=${deploymentFile}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
