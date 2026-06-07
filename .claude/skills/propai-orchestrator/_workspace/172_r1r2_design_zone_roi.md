# 172. R1/R2 근본수정 — 설계탭 용도지역 상속 · 수지 ROI 정상화

## 결론 요약
- **R1(설계탭 용도지역 미상속/GFA 과소)**: DesignStudio가 부지분석 SSOT(`siteAnalysis.zoneCode`)를
  비동기 form 시드(effect)에만 의존 → 초기 1프레임 동안 기본값(제2종/250%)으로 `localCalc`가
  돌아 250% 기본 GFA(629.8×2.5=**1,574㎡**)가 `designData`에 영속화되던 회귀. GFA 계산을 SSOT에서
  **동기 파생**(`effectiveZoning`)하도록 변경해 차단.
- **R2(설계 다운스트림 ROI -100%)**: 설계 GFA 정정 → 수지 staleness 트리거 → 자동
  `/feasibility/calculate`가 **매출입력 비어있는 DEFAULT_INPUT**(분양단가·세대수=0)으로 실행되어
  **revenue=0 / ROI -100%**를 `feasibilityData`에 영속화(건전한 baseline -0.8%를 덮어씀).
  매출 파라미터 부재 시 자동재계산을 **calculate→baseline(zone역산)** 으로 폴백하도록 가드.

## 라이브 재현(증거, www.4t8t.net, test@4t8t.net)
프로젝트 `a3c7746e-...`(서울 강남구 역삼동 1, **일반상업지역**, 629.8㎡):

| 위치 | 관찰값 | 판정 |
|------|--------|------|
| store `siteAnalysis.zoneCode` | `"일반상업지역"` | 정상(SSOT 보유) |
| 설계탭 진입 직전 `designData` | far **250**, totalGfaSqm **1,574.5** | R1 과소(250% 기본) |
| 설계탭 DesignStudio 마운트 후 | select=**일반상업지역**, far **1300**, totalGfaSqm **8,187.4**, 17층 | v88 기본동작 OK |
| 수지탭 `feasibilityData` | revenue **0**, cost **52,663,753,650**, **roiPct -100**, grade E | R2 오염 |
| `/api/v2/feasibility/baseline`(직접호출) | roi **1705%**, profit **74.58%**, revenue **23.7B**, cost **6.0B**, is_baseline=true | 건전 baseline 존재 |

→ R1은 "용도지역 미상속"이 아니라 **비동기 시드 타이밍**으로 인한 stale 250% GFA 영속화.
  R2는 stale 자동재계산이 **매출0 calculate**로 건전 baseline을 덮어쓴 오염.

## 렌더 컴포넌트 식별
- 설계 탭 `app/[locale]/(dashboard)/projects/[id]/design/page.tsx:52` → `DesignStudio` 렌더(맞음).
- 프로젝트 인덱스 파이프라인 `components/projects/LifecycleStageViews.tsx`는 designData를
  **읽기전용 표시**만 하고 재계산 안 함 → stale designData가 그대로 노출되는 표시 경로.

## 수정 내역(최소 diff, 2파일 35+/7−)

### R1 — `components/design/DesignStudio.tsx`
1. `effectiveZoning` useMemo 신설: `zoneEdited`면 form값, 아니면
   `normalizeZoning(siteAnalysis.zoneCode) || form.zoning`(SSOT 동기 파생).
2. `localCalc`의 `getZoningSpec`/`calcMaxGrossArea` 인자를 `form.zoning`→`effectiveZoning`,
   deps도 `effectiveZoning`으로 교체 → 첫 렌더부터 정확한 GFA(과소 250% 영속화 차단).
3. select `value`, SolarEnvelope `zone` 폴백, 연동 배지 표기를 `effectiveZoning` 기준으로 정합.
   (`zoneEdited` 가드 보존: 사용자 수동변경은 SSOT를 덮지 않음.)

### R2 — `components/feasibility/FeasibilityEditorV2.tsx`
- stale 자동재계산 effect에 매출입력 가드 추가:
  `hasRevenueInputs = avg_sale_price_per_pyeong>0 && (total_households>0 || avg_area_pyeong>0)`.
  - true → 기존대로 `/feasibility/calculate`(공사비 override) 정밀 재계산.
  - false → `baselineTriedSigRef` self-reset 후 `runBaseline`(zone역산: 실제 매출 추정) 재실행
    → revenue=0/ROI-100% 위양성 방지, 정직 추정값 유지(무목업).
- `result` 변경 시 `updateFeasibilityData`가 baseline의 실매출을 반영 → 기존 오염
  feasibilityData(revenue0/roi-100)는 다음 stale에서 **자동 자가복구**.

## 무목업·SSOT
- 용도지역 단일출처 = 부지분석(`siteAnalysis.zoneCode`), 설계는 정규화만 수행(임의 기본값 주입 안 함).
- 매출 결측 시 0 매출 강제 대신 zone역산 baseline으로 정직 폴백(가짜값 생성 아님).

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- 라이브 baseline 직접호출로 일반상업지역 건전 ROI(양수) 확인 — R2 폴백 타깃 검증.
- 설계탭 라이브: select=일반상업지역·GFA 8,187㎡ 상속 확인(R1 기본동작 + 하드닝).
- git diff: import(`normalizeZoning`/`runBaseline` 등) 보존 확인.
- 배포(Cloudflare 자동, main push) 후 stale 트리거 시 오염 feasibilityData 자가복구 예상.

## 잔여/주의
- 이미 영속된 오염 `feasibilityData`(revenue0)는 배포 후 수지탭 재진입 시 stale 경로로 1회 자가복구.
  즉시 강제정정이 필요하면 수지탭에서 부지/공사비 갱신을 트리거하면 baseline 재산출.
- 사용자가 실제 분양단가·세대수를 입력한 경우는 정밀 calculate 유지(의도된 동작).
