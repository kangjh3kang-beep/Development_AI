import hre from "hardhat";

async function main() {
  const { ethers } = hre;
  const [deployer] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("PropAIEscrow");
  const feeData = await ethers.provider.getFeeData();
  const txRequest = await factory.getDeployTransaction();
  const gasEstimate = await deployer.estimateGas(txRequest);
  const balance = await ethers.provider.getBalance(deployer.address);
  const gasPrice = feeData.gasPrice ?? 0n;
  const maxFeePerGas = feeData.maxFeePerGas ?? gasPrice;
  const maxPriorityFeePerGas = feeData.maxPriorityFeePerGas ?? 0n;

  console.log(`deployer=${deployer.address}`);
  console.log(`balance=${balance.toString()}`);
  console.log(`gasEstimate=${gasEstimate.toString()}`);
  console.log(`gasPrice=${gasPrice.toString()}`);
  console.log(`maxFeePerGas=${maxFeePerGas.toString()}`);
  console.log(`maxPriorityFeePerGas=${maxPriorityFeePerGas.toString()}`);
  console.log(`gasPriceCost=${(gasEstimate * gasPrice).toString()}`);
  console.log(`maxFeeCost=${(gasEstimate * maxFeePerGas).toString()}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
