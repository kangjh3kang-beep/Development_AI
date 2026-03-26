export type EthereumRequestArguments = {
  method: string;
  params?: unknown[] | Record<string, unknown>;
};

export type EthereumProvider = {
  request(args: EthereumRequestArguments): Promise<unknown>;
};

type BrowserWindowWithEthereum = Window &
  typeof globalThis & {
    ethereum?: EthereumProvider;
  };

export function getProvider(): EthereumProvider {
  const ethereum = (window as BrowserWindowWithEthereum).ethereum;

  if (typeof window === "undefined" || !ethereum) {
    throw new Error("MetaMask provider is not available in this browser.");
  }

  return ethereum;
}

export async function deployContract(
  abi: ReadonlyArray<unknown>,
  bytecode: string,
  constructorArgs: unknown[],
): Promise<string> {
  getProvider();
  void abi;
  void bytecode;
  void constructorArgs;

  throw new Error(
    "Client-side contract deployment is not enabled in this build. Use the live blockchain API routes instead.",
  );
}
