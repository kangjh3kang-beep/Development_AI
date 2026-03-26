# PropAI v30.0 구축안 — 전체 실행 순서 요약

> **목적**: Codex, Claude Code, Gemini 담당 문서를 한 장에서 연결해 보는 공통 실행 순서 문서
> **상세 문서**:
> - `build-plan-claude-code.md`
> - `build-plan-codex.md`
> - `build-plan-gemini.md`
> - `propai-platform/docs/lock-files-guide.md`

---

## 기준 원칙

1. 상위 명세 `부동산개발 전주기 AI 자동화 플랫폼.md`의 `Part IX`를 최종 기준으로 삼는다.
2. 단계 번호는 상위 명세 `STEP 1`부터 `STEP 12`까지의 흐름을 우선한다.
3. 에이전트 문서는 역할 분리 문서이고, 이 문서는 전체 순서와 handoff 기준 문서다.
4. `packages/types/`, ABI, OpenAPI는 교차 에이전트 산출물의 단일 소스로 관리한다.
5. 파일 잠금 운영은 `propai-platform/docs/lock-files-guide.md`를 따른다.

---

## STEP 소유권 맵

| STEP | 주 담당 | 보조 | 핵심 산출물 |
|------|---------|------|-------------|
| **BOOT** | Gemini | 없음 | 모노레포 골격, 루트 설정, `.build-journal/` |
| **1** | Claude Code | Gemini 리뷰 | `apps/api` 앱 뼈대 |
| **2** | Claude Code | Gemini 리뷰 | DB 스키마, Alembic, `packages/types/` |
| **3** | Claude Code | Codex 일부 연동, Gemini 리뷰 | 핵심 AI 서비스 |
| **4** | Claude Code | Gemini 리뷰 | 외부 API 통합 레이어 |
| **5** | Codex | Claude API 계약 제공, Gemini 리뷰 | `apps/web`, `packages/ui`, 접근성 구현 |
| **6** | Codex | Claude Python 연동, Gemini 리뷰 | `contracts`, ABI, 배포 메타데이터 |
| **7** | Gemini | Claude/Codex 소비 | Docker Compose 개발 환경 |
| **8** | Gemini | Claude/Codex 소비 | 환경 변수 템플릿 |
| **9** | Claude Code | Codex 소비, Gemini 리뷰 | OpenAPI, API 응답 계약 |
| **10** | Claude Code | Codex Playwright 보조, Gemini CI 지원 | 테스트 구조와 통합 테스트 |
| **11** | Gemini | Codex 접근성 연계, Claude API mock 지원 | CI/CD, 접근성 자동 검증 |
| **12** | Gemini | Claude/Codex 보안 피드백 반영 | 보안/컨테이너 강화 |

---

## 권장 실행 순서

### Phase A. 저장소/인프라 기반

1. `BOOT` 완료
2. `STEP 7` Docker Compose 완료
3. `STEP 8` 환경 변수 템플릿 완료

### Phase B. 백엔드 뼈대와 데이터 계약

1. `STEP 1` FastAPI 앱 뼈대
2. `STEP 2` DB 스키마 + `packages/types/`

이 시점 handoff:
- Claude Code → Codex: `packages/types/`
- Claude Code → Gemini: DB 스키마/Alembic 요구사항

### Phase C. 병렬 개발 구간

1. Claude Code: `STEP 4` 외부 API 통합 레이어
2. Claude Code: `STEP 3-1`, `STEP 3-2` 핵심 AI 서비스
3. Codex: `STEP 5-1`, `STEP 5-2`, `STEP 5-3`를 Mock-first로 진행
4. Codex: `STEP 6` 스마트컨트랙트 패키지 진행 가능

병렬 개발 원칙:
- Codex는 API 완성 전에도 `Mock-first`로 웹 앱을 진행한다.
- Claude Code는 API 응답 계약이 바뀌면 `packages/types/`와 문서를 같이 갱신한다.

### Phase D. 연동 구간

1. Claude Code: `STEP 3-3` 드론/에이전트/블록체인 Python 연동
2. Claude Code: `STEP 9` OpenAPI/응답 계약 고정
3. Codex: `STEP 5-4`, `STEP 5-5` API 연동 UI와 접근성 마감

이 시점 handoff:
- Codex → Claude Code: ABI, 배포 주소, 컨트랙트 상태 모델
- Claude Code → Codex: OpenAPI, SSE 이벤트 포맷, API 예제 응답
- Gemini → Codex/Claude: Hasura/CI/실행 환경 정리

### Phase E. 검증과 운영

1. Claude Code: `STEP 10` 테스트 구조
2. Codex: Playwright, 접근성 대상 페이지, 프론트 smoke flow 보조
3. Gemini: `STEP 11` CI/CD + 접근성 자동 검증
4. Gemini: `STEP 12` 보안 + 컨테이너 강화

---

## 에이전트별 착수 조건

### Claude Code

- `STEP 7`, `STEP 8`이 최소 수준으로 준비되어야 한다.
- `packages/types/`는 가능한 한 이른 시점에 정의한다.
- `STEP 9` 전까지는 응답 계약을 자주 바꿀 수 있으므로 변경 기록을 남긴다.

### Codex

- `packages/types/` 초안 확보 후 `STEP 5-1`부터 착수 가능하다.
- API 미완성 상태에서는 `Mock-first`를 유지한다.
- `STEP 5-4`, `STEP 5-5`는 `STEP 9` 이후 본격 연동한다.
- `STEP 10`, `STEP 11` 보조는 `STEP 5` 완료 이후다.

### Gemini

- `BOOT`, `STEP 7`, `STEP 8`은 가장 먼저 진행한다.
- `STEP 11`, `STEP 12`는 앱 기능이 어느 정도 완료된 뒤 강하게 잠근다.
- GraphQL/Hasura는 `STEP 2` DB 스키마가 안정된 이후 진행한다.

---

## 교차 산출물 규칙

### `packages/types/`

- 소유: Claude Code
- 소비: Codex, Gemini
- 규칙: breaking change 시 `.build-journal/type-changes.md` 기록

### ABI / 배포 메타데이터

- 소유: Codex
- 경로: `contracts/artifacts/**`, `contracts/deployments/**`
- 소비: Claude Code
- 규칙: breaking change 시 `.build-journal/abi-changes.md` 기록

### OpenAPI / 응답 계약

- 소유: Claude Code
- 소비: Codex, Gemini
- 규칙: `STEP 9`에서 고정, 이후 변경은 문서와 테스트 동시 갱신

### CI / 보안 정책

- 소유: Gemini
- 소비: Codex, Claude Code
- 규칙: 워크플로와 문서가 항상 같이 변경되어야 함

---

## 현재 상태 파일 해석 규칙

`.build-journal/current-stage.json`은 작업 중간 상태일 수 있으므로 다음처럼 해석한다.

- `current_stage`: 전체 프로젝트의 기준 진행 단계
- `agents.{name}.stage`: 각 에이전트가 현재 손대는 단계
- `status=active`: 실제 작업 중
- `status=waiting`: 선행 조건 대기 또는 리뷰 대기

주의:
- 에이전트별 `stage` 값은 병렬 작업 때문에 반드시 전체 권장 실행 순서와 같지 않을 수 있다.
- 다만 `Codex STEP 10/11`처럼 후행 보조 단계가 먼저 활성화되면, 실제 선행 구현이 완료되었는지 별도 확인이 필요하다.

---

## 문서 사용법

1. 전체 우선순위를 볼 때는 이 문서를 먼저 본다.
2. 세부 구현 파일과 품질 게이트는 각 에이전트 문서를 본다.
3. 실제 작업 착수 전에는 `.build-journal/current-stage.json`과 문서 선행 조건을 함께 확인한다.
