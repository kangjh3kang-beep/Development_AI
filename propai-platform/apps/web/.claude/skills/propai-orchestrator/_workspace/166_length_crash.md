# 166. site-analysis 페이지 `undefined.length` 크래시 추적·수정

## 증상
- URL `/ko/projects/8f07026a-2ac2-4489-94e2-b11a4c5faaba/site-analysis` 진입 시 에러바운더리:
  **"Cannot read properties of undefined (reading 'length')"**
- 해당 프로젝트는 현재 계정(test@4t8t.net)에 존재하지 않음.

## 라이브 재현 (agent-browser, session lencrash)
1. `https://www.4t8t.net/ko/login` → test@4t8t.net/test1234 로그인 성공 → `/ko`.
2. 대상 URL 진입 후 네트워크 확인:
   - `GET https://api.4t8t.net/api/v1/projects/8f07026a-...` → **404** (프로젝트 미존재 확정).
3. 현재 컨텍스트 스토어(`propai-project-context`)는 **다른 프로젝트**(`a3c7746e...` "E2E검증_역삼동736", address="서울 강남구 역삼동 1")에 바인딩되어 있음.
4. 운영 응답 셰이프 직접 검증:
   - `POST /api/v1/zoning/analyze` (유효 주소) → 200, `special_districts:[]`, `warnings:[]` 정상.
   - `POST /api/v2/feasibility/auto-recommend` (유효 주소) → 200, `recommendations` 배열 정상.
   - → 유효 주소 경로는 안전. **부분응답/스테일 컨텍스트(404 프로젝트로 SPA 전환 시 이전 프로젝트 주소 잔류)** 경로에서 배열 필드 누락 가능.
5. 크래시 로직 직접 증명(브라우저 eval): `special_districts`/`warnings`가 없는 부분 zoning 페이로드에서
   - 기존(무가드): `CRASH: Cannot read properties of undefined (reading 'length')`
   - 수정(가드): `no-crash`
   → 보고된 에러 메시지와 **정확히 일치**.

## 근본원인 (정확한 파일:라인)
백엔드 응답을 받아 그대로 state에 저장한 뒤(`setZoningData(res)`),
TypeScript 타입은 배열을 **필수**로 선언했지만 부분응답/404 컨텍스트에서 런타임에 `undefined`가 되어 무가드 `.length`/`.map` 호출:

- `components/projects/LandIntelligencePanel.tsx:404` — `zoningData.special_districts.length` (★주 용의자, `zoningCharacteristics` useMemo가 result 렌더 시 즉시 실행)
- `components/projects/LandIntelligencePanel.tsx:407` — `zoningData.special_districts.map(...)`
- `components/projects/LandIntelligencePanel.tsx:412` — `zoningData.warnings.length`
- `components/projects/LandIntelligencePanel.tsx:415` — `zoningData.warnings[0].slice(...)`
- `components/projects/LandIntelligencePanel.tsx:315~317` — `raw.recommendations.map/.length` (auto-recommend 부분응답, try/catch 내부지만 하드닝)
- `components/projects/LandIntelligencePanel.tsx:360~362` — 동일 패턴(deep analysis)
- `app/.../site-analysis/page.tsx:456` — `tx.apt.items.length` (comprehensive 부분응답에서 items 누락 가능)
- `app/.../site-analysis/page.tsx:573,601` — `infra.schools.length` (동일)

타입 정의: `LandIntelligencePanel.tsx:45-46` (`special_districts`, `warnings` 필수 선언) ↔ 런타임 undefined 불일치.

## 수정 (무목업 · `?? []` / 옵셔널체이닝 가드)
- `LandIntelligencePanel.tsx:404-412` → `const specialDistricts = zoningData.special_districts ?? []; const zoningWarnings = zoningData.warnings ?? [];` 후 가드.
- `LandIntelligencePanel.tsx:315`, `360` → `const recs = raw.recommendations ?? [];` 후 `recs.map/.length`.
- `page.tsx:456` → `(tx.apt.items?.length ?? 0) > 0` + `(tx.apt.items ?? []).slice`.
- `page.tsx:573,601` → `(infra.schools?.length ?? 0) > 0` + `(infra.schools ?? []).slice`.
- 가짜 배열 주입 없음(빈상태는 카드 미표시로 정직 처리). import 보존(diff상 import 라인 0건 변경).

## 404 graceful 처리 (확인 결과 — 별도 미해결 UX 이슈)
- 404 프로젝트 **하드 로드** 시 크래시는 아니지만 **무한 바인딩 스피너**(`stage==="init" && !isBound`, page.tsx:841-849)에 멈춤.
  스피너 컨테이너 클래스 `flex items-center justify-center py-32`로 라이브 확인.
- `.length` 크래시(에러바운더리)는 **SPA 전환** 경로(이전 프로젝트 주소 잔류 → 자동 result 진입 → 부분 zoning 응답)에서 발생.
- 무한 스피너는 바인딩(ProjectContextBinder/SSOT) 로직 영역이며 본 작업(렌더 트리 무가드 .length)과 분리 — 바인딩 아키텍처 변경 리스크가 있어 본 패치에 포함하지 않음. 별도 후속 권장(예: 바인딩 타임아웃 폴백 → SiteInitiator/“프로젝트를 찾을 수 없음” 안내).

## 검증
- `npx tsc --noEmit` → **EXIT 0**.
- `git diff` import 라인 0건 변경(보존), 2개 파일만 수정(page.tsx 10줄·LandIntelligencePanel.tsx 27줄 diff).
- 브라우저 eval로 기존=크래시 / 수정=무크래시 대조 확인(보고 메시지 정확 일치).
- 무목업 준수(빈상태 정직 미표시).

## 잔여 (다른 작업 영역 — 미수정)
- DigitalTwinScene/permit/v2_feasibility는 범위 외(지시대로 미변경).
- 404 하드로드 무한 스피너(바인딩 graceful) 후속 권장.
