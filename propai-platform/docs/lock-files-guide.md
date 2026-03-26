# Lock Files 운영 규칙

> **대상 파일**: `.build-journal/lock-files.json`
> **목적**: 에이전트 간 파일 충돌 방지와 작업 범위 가시화

---

## 기본 원칙

1. 파일을 수정하기 전에 먼저 잠근다.
2. 읽기만 할 파일은 잠그지 않는다.
3. 디렉토리 전체보다 가능한 한 구체적인 파일 단위로 잠근다.
4. 작업이 끝나면 즉시 잠금을 해제한다.
5. 잠금 정보와 실제 작업 상태가 다르면 `current-stage.json`도 함께 확인한다.

---

## 권장 잠금 단위

### 파일 단위 잠금

가장 권장되는 방식이다.

예시:
- `apps/api/main.py`
- `apps/web/app/[locale]/layout.tsx`
- `contracts/src/PropAIEscrow.sol`

### 디렉토리 단위 잠금

여러 파일을 한 번에 생성하거나 구조를 크게 바꿀 때만 사용한다.

예시:
- `apps/api/auth/`
- `packages/ui/src/components/`

주의:
- 루트 `apps/`, `packages/`, `contracts/` 같은 광범위 잠금은 지양한다.

---

## lock-files.json 형식

```json
{
  "locks": [
    {
      "agent": "claude_code",
      "path": "apps/api/main.py",
      "reason": "STEP 1 FastAPI 앱 초기화",
      "locked_at": "2026-03-18T06:50:00+09:00"
    },
    {
      "agent": "codex",
      "path": "apps/web/app/[locale]/layout.tsx",
      "reason": "STEP 5 i18n 레이아웃 구현",
      "locked_at": "2026-03-18T06:50:30+09:00"
    }
  ]
}
```

필드 규칙:
- `agent`: `gemini`, `claude_code`, `codex` 중 하나
- `path`: 리포 루트 기준 상대 경로
- `reason`: 단계와 작업 목적을 짧게 설명
- `locked_at`: ISO 8601 형식 타임스탬프

---

## 잠금 절차

### 1. 작업 시작 전

- `lock-files.json`에 항목 추가
- `current-stage.json`에서 자기 상태를 `active`로 확인

### 2. 작업 중

- 잠근 파일 범위 밖 수정이 필요하면 잠금부터 갱신
- 같은 파일을 다른 에이전트가 이미 잠갔으면 먼저 조정

### 3. 작업 완료 후

- 완료한 파일 잠금 제거
- 필요하면 `current-stage.json` 상태 갱신
- 산출물 handoff가 있으면 관련 문서도 같이 갱신

---

## 충돌 처리 규칙

### 이미 잠긴 파일을 수정해야 할 때

1. 잠금 주체 확인
2. 실제로 충돌하는지 확인
3. 충돌이면 해당 에이전트 산출물 완료 후 이어서 작업
4. 급한 수정이면 파일 분리나 책임 재조정부터 한다

### 같은 디렉토리의 다른 파일을 수정할 때

- 파일별 잠금이 다르면 병렬 작업 가능
- 디렉토리 잠금이 걸려 있으면 먼저 범위가 과도한지 검토

---

## 에이전트별 권장 패턴

### Claude Code

- `apps/api/**`
- `apps/worker/**`
- `packages/types/**`

### Codex

- `apps/web/**`
- `packages/ui/**`
- `contracts/**`

### Gemini

- `infra/**`
- `.github/**`
- `.build-journal/**`
- `docs/**`

주의:
- 교차 산출물 파일은 소유권 기준을 따른다.
- `packages/types/**`는 Claude Code 소유, ABI 산출물은 Codex 소유, CI/보안 설정은 Gemini 소유다.

---

## 지금 리포에서의 권장 운영

현재처럼 초기 단계에서는 다음 순서를 권장한다.

1. Claude Code가 `apps/api/**`, `packages/types/**`를 잠그고 `STEP 1`, `STEP 2`를 진행
2. Gemini는 `infra/**`, `.github/**`, `.build-journal/**`만 잠금
3. Codex는 `packages/types/**` 초안이 나온 뒤 `apps/web/**`, `packages/ui/**`, `contracts/**` 잠금 시작

---

## 최소 운영 원칙

1. 잠금 없이 수정하지 않는다.
2. 광범위 디렉토리 잠금은 최소화한다.
3. 잠금은 짧게 유지한다.
4. handoff 산출물은 잠금 해제 전에 기록한다.
