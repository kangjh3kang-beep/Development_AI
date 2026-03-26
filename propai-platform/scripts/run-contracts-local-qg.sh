#!/usr/bin/env bash
set -euo pipefail

repo_root="/home/kangjh3kang/My_Projects/Development_AI/propai-platform"
contracts_dir="${repo_root}/contracts"
log_file="/tmp/propai-hardhat-node.log"
node_pid=""

cleanup() {
  if [[ -n "${node_pid}" ]]; then
    kill "${node_pid}" >/dev/null 2>&1 || true
    wait "${node_pid}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

cd "${contracts_dir}"

npx hardhat node >"${log_file}" 2>&1 &
node_pid=$!

ready="false"
for _ in $(seq 1 30); do
  if curl -s \
    -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
    http://127.0.0.1:8545 | grep -Fq '"result"'; then
    ready="true"
    break
  fi

  sleep 1
done

if [[ "${ready}" != "true" ]]; then
  cat "${log_file}"
  exit 1
fi

npx hardhat run scripts/deploy.ts --network localhost
