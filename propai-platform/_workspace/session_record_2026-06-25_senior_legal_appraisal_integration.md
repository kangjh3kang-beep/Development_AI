# 세션 기록 — 시니어 법무사·감정평가사 통합 + 전문데이터 수동입력 surface (2026-06-25)

- **브랜치:** `feat/senior-agents-foundation` (워크트리 `Development_AI_senior`)
- **세션 커밋:** `9ea5158e` → `b401f8c8` → `27a64ad8` → `9894e9ce` → `e412ddc8` (5커밋·전부 푸시됨)
- **머지/배포:** ★통합자 경계(main 직접 푸시 금지) — 브랜치만 푸시. 미머지.
- **상위 맥락:** 시니어 전문가 AI 에이전트 시스템(기존 7종 → **9종**으로 확장). 메모리 `project_senior_agents_foundation.md` 참조.

---

## 1. 목표 (사용자 요청)

1. **정비사업 종전평가(감정) 분석 엔진 신규 구축 + 시니어 법무사 spec 완벽 보강** → 구현계획 수립 후 OMC·성장루프로 진행.
2. (작업 중 정련) **"시니어 법무사 + 시니어 감정평가사를 통합해 권리분석을 더 정밀하게"** — 감정가가 권리분석으로 흘러들게.
3. (후속) **무목업 정밀 적용**: store 부재 데이터를 숨기지 말고 "미입력"으로 표시 + 입력 시 즉시 활성.

표준 게이트(매 증분): ruff 0 · pytest · 프론트 tsc/eslint/next build · **독립 코드리뷰(별도 레인 ≥ACCEPT)** · 무목업 · 근거(verified 법조문) · 라이브검증 · 보드 claim/release.

---

## 2. 결과 (무엇을 만들었나)

### 증분 A — 시니어 법무사(8)·감정평가사(9) 통합 권리분석 (`9ea5158e`)
- **신규 spec 2종**(additive·공유서비스 미접촉):
  - `specs/appraiser.py` `senior_appraiser`(시니어 감정평가사) — 4룰: 공시지가기준법(감칙14조)·원가법(감칙15조·잔가율 하한20%)·다방법 결합·**종전자산평가**(토지+건물·★법무사/비례율 전파·도시정비법).
  - `specs/legal_scrivener.py` `senior_legal_scrivener`(시니어 법무사) — 말소기준 권리분석(민사집행법·주임법·부등법)·조합 동의율(도시정비법35조)·소유/신탁 등기·개발신탁(차입형/관리형/담보).
- **★핵심 통합**: `evaluators/legal.py`의 `rights_takeover`가 감정평가사 산출 **감정가(appraised_value)**를 소비 → **실효가치 = 감정가 − 인수권리(선순위·대항보증금)**, **인수율 = 인수권리/감정가** 정량 판정(BLOCK 인수율≥100% / WARN 선순위>0 / PASS clean).
- `evaluators/appraisal.py` 종전평가=토지+건물(건물 결측→WARN 과소평가).
- registry **9에이전트** · `HIGH_RISK` **5** · `DOMAIN_ROUTES`(법무/권리분석/등기→법무사, 감정평가/종전평가→감정평가사).
- 프론트 `build-inputs.ts`: store `estimatedValue` → 감정가(감정평가사 `land_appraised_total`·법무사 `appraised_value`로 전파·기존 store 필드 재사용).

### 증분 B — 코드리뷰 수정 (`b401f8c8`·`27a64ad8`)
- 코드리뷰 8.7 ACCEPT-WITH-NITS의 MED 3건 반영:
  - 재건축 **각 동별 과반(35조③)** 누락 → `building_consent_majority` 게이트. 미입력 시 소유자·면적 충족이어도 **PASS 단정 금지**(동별 미검증 WARN·정직 고지) = 거짓 PASS 구조적 차단.
  - `rights_takeover` threshold "초과"→"이상(실효가치 ≤ 0)"로 코드(≥1.0)와 정합 + 실효가치 음수 `max(0)` 표기.
  - spec에 `legal.rights_takeover` DecisionRule 추가 → 평가기 rule_id와 1:1 citation 추적 완결.

### 증분 C — 전문데이터 수동입력 surface (`9894e9ce`·`e412ddc8`)
- **무목업 정밀 적용**: store 자동산출 불가한 *사용자 제공 사실*(인수 선순위 권리·조합 동의율·건물 감정가)을 숨기지 않고 **"미입력" 투명표시 + 수동입력 → 입력 시 즉시 활성**.
- 신규 `lib/senior/manual-inputs.ts`:
  - `MANUAL_INPUTS`(법무사 7필드·감정평가사 1필드) — **백엔드 evaluator input 키와 1:1**.
  - `coerceManualInputs`(빈값=미입력 생략·number 유한수·boolean·select·명시 0 보존).
  - `mergeSeniorInputs`(**store 우선 SSOT** → 향후 store 보유 시 코드변경 없이 자동매핑 우선).
- `SeniorConsultPanel.tsx`: 선택 에이전트에 수동필드 있으면 '추가 입력' 폼(placeholder "미입력"·전문용어 hint·"입력값으로 자문"). consult/stale/캐시키가 병합 inputs 사용. 헤더 7→9.
- **★백엔드 무변경**: 평가기가 이미 키 소비·라우터 `context: dict[str,Any]`라 mixed-type 수용.

---

## 3. 검증 (게이트 통과 증거)

| 게이트 | 결과 |
|---|---|
| senior 백엔드 테스트 | **104 PASS** (test_senior_{agents,evaluators,router,reasoner,llm_runner}) |
| 백엔드 전체 회귀 | **921 PASS** · 신규 실패 **0** (선재 9건=stage4 latency·무관) |
| ruff (senior 패키지) | All checks passed |
| 프론트 vitest (lib/senior) | **24 PASS** (build-inputs 13 + manual-inputs 11 신규) |
| tsc --noEmit / eslint | 클린 (exit 0) |
| next build | **EXIT 0** (136 static pages) |
| 라이브(orchestrator) | 종전평가 10억 · 동의율 80%/60% PASS · 인수율 30% WARN · 재건축 동별 미입력 WARN |

성장루프 수렴: A/B **8.7 → 9.5 ACCEPT** · C **9.4 → 9.5 ACCEPT** (둘 다 fresh code-reviewer 독립 재리뷰로 수렴 확인).

---

## 4. 노하우 (재사용 패턴·교훈)

1. **"신규 엔진" 요청 ≈ 기존 capability 배선**: "종전평가 엔진 신규구축"을 조사하니 `desk_appraisal_service`(원가법 건물감정)·토지감정이 이미 존재 → 신규가 아니라 **평가기로 배선**. 매번 신규 빌드 전에 기존 자산 grep 먼저(CLAUDE.md 버그정책·전역화 원칙과 동일).
2. **★무목업의 정확한 의미 = 미입력 투명표시 + 입력 시 즉시 활성** (숨김/생략 ❌, 가정 0 ❌). 자동수집 불가한 사용자 제공 사실은 수동입력 surface로. 병합은 store 우선(SSOT)이라 미래에 store가 그 값을 보유하면 코드변경 없이 활성. → `feedback_no_mockup_verify` 메모리에 반영함.
3. **통합은 단일 입력키로 결합**: 감정가→권리분석을 `appraised_value` 한 키로 묶어 결합도↓·추적성↑. consult_multi(["감정평가","법무사"])로 동시 자문.
4. **거짓 PASS 구조적 차단**: 강행 추가요건(재건축 동별 과반)이 데이터 부재로 미검증이면 PASS 단정 금지 → WARN+정직 고지. `is True` 엄격비교로 truthy 우회 차단.
5. **citation 추적성**: 평가기 `rule_id`마다 대응 DecisionRule(spec)을 1:1로 둬야 근거가 형식이 아닌 실효(register() 판단자격 게이트 통과).
6. **성장루프 운영**: 구현→독립 코드리뷰(fresh code-reviewer 스폰·SendMessage 재개는 파일권한 거부)→MED+ 수정→재리뷰로 ≥9.5 수렴. 표기상 LOW/NIT도 한 줄이면 마저 정리해 완전 정합.
7. **프론트↔백엔드 키 정합 grep 검증**: manual-inputs 필드 key 8개를 evaluator가 읽는 키와 grep 대조(8/8) — 계약 드리프트 방지.

---

## 5. 잔여 / 인계 (다음 세션)

### 차단 없음 — 통합자 작업
- **머지**: `feat/senior-agents-foundation` → main. origin/main과 충돌은 `public/sw.js` CACHE_NAME 버전라인 trivial 단일 충돌만 예상(senior=v332·상위본 택일). senior 코드는 클린머지. 머지 후 A1 재빌드(프론트)·`deploy.sh`(백엔드, origin/main 기준).

### ✅ 증분 D — 정비사업 비례율 활성 완료 (`bc560787`, 2026-06-25 추가 세션)
- **순수 프론트 배선**(백엔드 `evaluate_urban` 무변경) — 도시계획전문가 비례율 평가기에 입력을 흘려 UI 정량판정 활성.
  - `build-inputs.ts` `buildUrbanInputs`: 수지(`feasibilityData`) 종후자산 `totalRevenueWon`→`post_appraisal_total`, 총사업비 `totalCostWon`→`total_project_cost` 자동매핑(SSOT).
  - `manual-inputs.ts` `senior_urban_planner` 5필드: `prior_appraisal_total`(종전자산총평가=비례율 분모·활성 전제)·`post`/`total_project_cost`(수지 미실행 폴백·store 우선)·`prior_appraisal_individual`·`member_sale_price`(권리가액·분담금).
  - **★분모(종전평가=토지+건물 감정)는 자동매핑 안 함**: `estimatedValue`는 토지만·탁상 → 분모 과소 → 비례율 과대(오도) → 수동입력으로(무목업, 테스트로 잠금).
  - 키 5종 백엔드 `evaluate_urban`과 **1:1 grep 정합**. 라이브: 종전100억·종후120억·사업비90억 → **비례율 30% WARN**(권리가액 1.5억·분담금 4.5억)·종후200억 → **110% PASS**·종전평가 미입력 시 **생략(무목업)**.
- 게이트: **vitest 29 PASS(+5)**·tsc 0·eslint 0·**next build EXIT 0**·독립 코드리뷰 **9.4 ACCEPT**(critical/high/med 0; LOW 2건=coerce 0가드 비대칭[법무사 0보존 계약 충돌로 의도 유지]·"필수" 미강제[백엔드 게이트가 차단]=백로그). `sw v332→v333`.
- 보드 갱신·메모리 `project_senior_agents_foundation.md` 본문 반영 완료. 머지/배포는 **통합자 경계**(senior 전용 additive·무충돌).

### 후속 기능 (비차단·데이터/배선)
1. ~~**정비사업 비례율 활성**~~ → ✅ **증분 D 완료**(위). 잔여 데이터 정련(선택): `prior_appraisal_individual`을 조합원 단위 일괄(세대별 분담금 표)로 확장하면 관리처분 시뮬레이션 가능. 종후자산을 관리처분 추산액(조합원분양분+일반분양분 분리)으로 정밀화하면 `totalRevenueWon` 근사 대비 오차 축소.
2. **수동입력 영속화(선택)**: 현재 수동입력은 로컬 컴포넌트 state(읽기소비 경계 유지). 프로젝트별 저장이 필요하면 store/백엔드 영속 검토(과금·계정격리 준수).
3. **분석코어 모세혈관 배선**: 별도 세션이 `analysis-core wiring`(SpecialistAgent→decision_brief/comprehensive) 진행 중(보드 line 376). senior_agents와 충돌 없음(additive).

### 멀티세션 주의
- 같은 파일군(`legal_reference_registry` 등 법률 SSOT)은 6세션 동시편집 이력 — senior_agents는 `app/services/senior_agents/`(전용·additive)라 무충돌. 공유파일 편집 시 보드 claim 필수.
- 진행 중 인접 작업: `feat-tmp`의 desk-appraisal 다필지배선·registry 법무사그라운딩(보드 line 370·374 RELEASE). 종전평가 관련이라 비례율 배선 시 참고.
