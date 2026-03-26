import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import hre from "hardhat";

async function main() {
  const { artifacts } = hre;
  const artifact = await artifacts.readArtifact("PropAIEscrow");
  const abiDir = path.join(__dirname, "..", "artifacts", "abi");
  const abiFile = path.join(abiDir, "PropAIEscrow.abi.json");

  await mkdir(abiDir, { recursive: true });
  await writeFile(abiFile, `${JSON.stringify(artifact.abi, null, 2)}\n`, "utf8");

  console.log(`abi=${abiFile}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
