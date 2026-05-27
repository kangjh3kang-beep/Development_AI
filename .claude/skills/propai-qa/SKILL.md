---
name: propai-qa
description: "PropAI 부동산개발 플랫폼 품질 검증 스킬. API↔프론트엔드 인터페이스 정합성, Pydantic↔TypeScript 타입 교차 비교, 파일경로↔라우트경로 매핑 검증, DB↔ORM 스키마 정합성, 상태 전이 완전성 검증. QA 검증, 통합 테스트, 정합성 검사, 인터페이스 검증, 타입 일치 확인 요청 시 이 스킬을 사용. 점검, 감사, 재검증, 회귀 테스트 요청에도 사용."
---

# PropAI QA Validation Skill

PropAI 부동산개발 플랫폼의 인터페이스 정합성과 통합 품질을 검증하는 가이드.

## 검증 원칙

> 단순 "존재 확인"이 아닌 **경계면 교차 비교**가 핵심이다.

빌드 통과 ≠ 정상 동작. TypeScript 제네릭, `any`, Pydantic `model_config` 변환으로 인해 컴파일은 성공하지만 런타임에 실패하는 결함을 잡는다.

## 검증 체크리스트

### 1. API 응답 ↔ 프론트 훅 타입 교차 검증

```
단계:
1. apps/api/app/routers/ 또는 apps/web/app/api/ 에서 응답 shape 추출
   - FastAPI: response_model 또는 return 문의 딕셔너리 구조
   - Next.js API Route: NextResponse.json()에 전달하는 객체
2. 대응하는 프론트 훅에서 fetch 타입 파라미터 확인
   - useQuery<T>의 T, fetchJson<T>의 T
3. shape과 T가 일치하는지 비교:
   - 필드명 일치 (snake_case → camelCase 변환 포함)
   - 필드 타입 일치 (string vs number, optional vs required)
   - 래핑 구조 일치 ({ data: [...] } vs 배열 직접)
   - 페이지네이션 구조 ({ items, total, page } vs 배열)
```

**자주 발견되는 패턴:**
- API가 `{ projects: [...] }` 반환, 훅이 `Project[]` 기대 → 래핑 불일치
- API가 `thumbnail_url` 반환, 타입이 `thumbnailUrl` 기대 → 케이스 불일치
- API가 202 + `{ status }` 반환, 훅이 `{ data, failedIndices }` 기대 → 동기/비동기 혼동

### 2. 파일 경로 ↔ 라우트 경로 매핑

```
단계:
1. apps/web/app/[locale]/ 하위 page.tsx 파일 목록 수집
2. 파일 경로에서 URL 패턴 추출:
   - (group) → URL에서 제거
   - [param] → 동적 세그먼트 (:param)
3. 코드 내 모든 href=, router.push(, redirect( 값 수집
4. 각 링크가 실제 page 파일과 매칭되는지 확인
```

### 3. Pydantic ↔ TypeScript 타입 정합성

```
단계:
1. apps/api/app/schemas/ 에서 Pydantic 모델 필드 추출
2. packages/types/api.ts 에서 TypeScript 인터페이스 필드 추출
3. 1:1 대응 확인:
   - 필드명 (snake_case Python ↔ camelCase TS)
   - 타입 매핑 (str→string, int→number, Optional→?)
   - 중첩 타입 재귀 확인
```

### 4. DB 스키마 ↔ ORM 모델 정합성

```
단계:
1. Alembic 마이그레이션 최종 상태에서 테이블/컬럼 추출
2. apps/api/app/models/ SQLAlchemy 모델 정의와 비교
3. 확인: 컬럼명, 타입, nullable, 인덱스, 외래키
```

### 5. 상태 전이 완전성

```
단계:
1. 코드에서 status 관련 enum/상수 정의 찾기
2. 모든 status 업데이트 코드 수집 (UPDATE, .status =)
3. 정의된 상태 전이 맵과 대조
4. 도달 불가능한 상태, 누락된 전이 식별
```

### 6. 의존성 정합성

```
단계:
1. Python: requirements.txt vs pyproject.toml vs import 문
2. Node.js: package.json vs 실제 import 문
3. 미설치 의존성, 미사용 의존성 식별
```

## 보고서 형식

```markdown
# QA 검증 보고서: {모듈명}

**검증일**: {날짜}
**검증 범위**: {대상 파일/모듈 목록}

## 요약
- 총 검증 항목: {N}개
- PASS: {N}개 | FAIL: {N}개 | SKIP: {N}개
- 심각도: Critical {N} / Major {N} / Minor {N}

## 상세 결과

### [FAIL] {검증 항목명}
- **심각도**: Critical / Major / Minor
- **위치**: `{파일A}:{라인}` ↔ `{파일B}:{라인}`
- **기대값**: `{expected}`
- **실제값**: `{actual}`
- **수정 제안**: {어느 쪽을 어떻게 수정}

### [PASS] {검증 항목명}
- **위치**: `{파일A}` ↔ `{파일B}`
- **확인 내용**: {간단 설명}
```

## 점진적 QA 실행

전체 완성 후 1회가 아니라, 각 모듈 완성 직후 해당 경계면을 검증한다:

| 완성된 모듈 | 검증 대상 경계면 |
|-----------|----------------|
| 백엔드 API | DB↔ORM, Pydantic 스키마 내부 일관성 |
| 프론트 페이지 | 라우트 경로 매핑, 훅 타입 정의 |
| API + 프론트 연동 | API 응답↔훅 타입, 인증 흐름 |
| AI 서비스 | AI 입출력↔API 스키마, 폴백 동작 |
| 전체 통합 | 상태 전이, 의존성, E2E 흐름 |
