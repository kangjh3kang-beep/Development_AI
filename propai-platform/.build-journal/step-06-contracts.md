# STEP 6 진행 보고: 스마트컨트랙트 구현
> 완료일: 2026-03-19
> 담당: Codex
> 상태: STEP 7 Hardhat 환경 검증 종료 + STEP 6 배포본 유지

---

## 구현 범위

- `contracts` 워크스페이스 패키지 생성
- Hardhat + TypeScript + OpenZeppelin 기반 개발 환경 구성
- `PropAIEscrow.sol` 구현
- 배포 스크립트와 배포 메타데이터 산출 규칙 구성
- 수수료, 분쟁, 환불, 하도급 직불, pause, 재진입 방어 테스트 작성

## 생성 및 수정 파일

- `contracts/package.json`
- `contracts/tsconfig.json`
- `contracts/hardhat.config.ts`
- `contracts/src/PropAIEscrow.sol`
- `contracts/src/mocks/ReentrantRefundAttacker.sol`
- `contracts/scripts/deploy.ts`
- `contracts/scripts/estimate-deploy.ts`
- `contracts/scripts/extract-abi.ts`
- `contracts/test/PropAIEscrow.test.ts`
- `contracts/deployments/amoy/PropAIEscrow.json`
- `contracts/deployments/localhost/PropAIEscrow.json`
- `contracts/deployments/polygon/.gitkeep`
- `contracts/deployments/hardhat/PropAIEscrow.json`
- `contracts/artifacts/abi/PropAIEscrow.abi.json`
- `contracts/slither-accepted-findings.md`
- `package.json`
- `scripts/run-contracts-local-qg.sh`
- `scripts/run-contracts-slither-qg.sh`
- `scripts/reset-contracts-artifacts.sh`

## 구현 요약

- `PropAIEscrow`는 `Ownable`, `Pausable`, `ReentrancyGuard`를 사용한다.
- 수수료는 `30 bps`로 계산하며 `calculateFee()`로 검증 가능하게 열어두었다.
- 상태는 `PendingFunding`, `Funded`, `Disputed`, `Released`, `Refunded` enum으로 관리한다.
- 핵심 함수는 `createEscrow`, `fundEscrow`, `releaseEscrow`, `directPaymentToSubcontractor`, `autoRefundOnExpiry`, `initiateDispute`, `resolveDispute`로 구성했다.
- 배포 스크립트는 ABI와 배포 메타데이터를 `contracts/deployments/{network}/PropAIEscrow.json`에 기록한다.
- `viaIR` 최적화와 수동 `gasLimit` 설정으로 `amoy` 계정 잔액 범위 안에서 실배포가 가능하도록 조정했다.
- ABI 전용 산출물은 `contracts/artifacts/abi/PropAIEscrow.abi.json`에 별도 추출한다.

## 검증 결과

- `corepack pnpm --filter @propai/contracts build` 통과
- `corepack pnpm --filter @propai/contracts test` 통과
  - 총 10개 테스트 통과
  - 생성, 예치, 정상 지급, 만료 환불, 분쟁, 하도급 직불, 수수료 계산, 재진입 방어, pause, 권한 거부 확인
- `corepack pnpm --filter @propai/contracts deploy:local` 통과
  - 로컬 배포 주소: `0x5FbDB2315678afecb367f032d93F642f64180aa3`
  - 배포 메타데이터: `contracts/deployments/hardhat/PropAIEscrow.json`
- `bash scripts/run-contracts-local-qg.sh` 통과
  - Hardhat `localhost` 노드 기동 후 배포 확인
  - 배포 메타데이터: `contracts/deployments/localhost/PropAIEscrow.json`
- `corepack pnpm --filter @propai/contracts exec hardhat verify --help` 확인
  - Polygonscan 검증 명령 사용 가능
- `corepack pnpm --filter @propai/contracts exec hardhat verify --list-networks` 확인
  - `polygonAmoy (80002)` 지원 확인
- `bash scripts/run-contracts-slither-qg.sh` 통과
  - Docker 기반 Slither 실행 결과 `0 result(s) found`
  - 허용 항목은 `contracts/slither-accepted-findings.md`에 문서화
- `corepack pnpm --filter @propai/contracts deploy:amoy` 통과
  - 실배포 주소: `0x961cba4A27D3080d8450789c91D4f30ff72E82E6`
  - 트랜잭션 해시: `0xee032f5e6cadfbb282b5ca09ce0b2b416e43439c72db58a018bea377ec48f01e`
  - 배포 메타데이터: `contracts/deployments/amoy/PropAIEscrow.json`
  - ABI 파일: `contracts/artifacts/abi/PropAIEscrow.abi.json`
- `corepack pnpm --filter @propai/contracts exec hardhat verify --network amoy 0x961cba4A27D3080d8450789c91D4f30ff72E82E6` 통과
  - Polygonscan 코드 검증 완료
  - Explorer: `https://amoy.polygonscan.com/address/0x961cba4A27D3080d8450789c91D4f30ff72E82E6#code`
- 2026-03-19 재실행
  - `corepack pnpm --filter @propai/contracts build` 통과
  - `corepack pnpm --filter @propai/contracts test` 통과
  - `bash scripts/run-contracts-local-qg.sh` 통과
  - `bash scripts/run-contracts-slither-qg.sh` 통과
  - `corepack pnpm --filter @propai/contracts extract:abi` 통과
  - 동일 주소 `0x961cba4A27D3080d8450789c91D4f30ff72E82E6`에 대해 `hardhat verify --network amoy` 재확인 결과 `already verified`
  - 새 redeploy는 지갑 잔액 부족으로 중단됨. 현재 배포/검증 산출물은 기존 `amoy` 배포본을 기준으로 유지
- 2026-03-20 종료 검증
  - `corepack pnpm --filter @propai/contracts build` 통과
  - `corepack pnpm --filter @propai/contracts test` 통과
  - `bash scripts/run-contracts-local-qg.sh` 통과
  - `bash scripts/run-contracts-slither-qg.sh` 통과
  - `corepack pnpm --filter @propai/contracts extract:abi` 통과
  - 기존 `amoy` 배포 주소 `0x961cba4A27D3080d8450789c91D4f30ff72E82E6` Verify 재확인 결과 `already verified`
  - Hardhat 환경 검증 기준 `build/test/local deploy/slither/verify-ready/abi` 종료
- `corepack pnpm test` 통과
  - 루트 `turbo run test`가 `@propai/contracts` 테스트를 정상 실행함
  - WSL 환경에서 `turbo`가 패키지 매니저 바이너리를 찾을 수 있도록 루트에 `pnpm`을 개발 의존성으로 고정

## 종료 상태

- Hardhat 환경 검증 종료
- `amoy` 실배포본 유지
- ABI 산출물 유지
- 추가 redeploy는 테스트 MATIC 재충전 이후 별도 요청 시 진행
