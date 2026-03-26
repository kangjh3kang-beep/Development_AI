#!/usr/bin/env bash
set -euo pipefail

repo_root="/home/kangjh3kang/My_Projects/Development_AI/propai-platform"

cd "${repo_root}"

docker run --rm \
  --entrypoint bash \
  -v "${repo_root}:/repo" \
  -w /repo/contracts \
  trailofbits/eth-security-toolbox \
  -lc "slither . --filter-paths 'test|mocks|typechain-types|artifacts|cache|deployments' --exclude-dependencies --exclude 'arbitrary-send-eth,timestamp,low-level-calls'"
