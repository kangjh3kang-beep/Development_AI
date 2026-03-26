#!/usr/bin/env bash
set -euo pipefail

repo_root="/home/kangjh3kang/My_Projects/Development_AI/propai-platform"

docker run --rm \
  --entrypoint bash \
  -v "${repo_root}:/repo" \
  trailofbits/eth-security-toolbox \
  -lc "rm -rf /repo/contracts/artifacts /repo/contracts/cache /repo/contracts/typechain-types"
