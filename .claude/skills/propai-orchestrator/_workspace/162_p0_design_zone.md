# P0 설계 용도지역 SSOT 상속 (DesignStudio)

## 근본원인 (확정)
부지분석에서 일반상업지역 확정·영속(`siteAnalysis.zoneCode`)인데 설계 화면이
용적률 250%(제2종일반주거 기본값) 환각 → 수지 ROI/등급/보고서 하류 전파.

두 결함:
1. **정규화 부재**: `getZoningSpec`/`calcMaxGrossArea`가 `ZONING_DB[zoning]` 정확매칭만 수행.
   `zoneCode`가 변형 표기("일반상업", 공백/괄호 포함 등)면 조회 실패 → `calcMaxGrossArea`
   기본 250% 폴백(= 환각의 직접 원인) 또는 `getZoningSpec`=null로 calc 미산출.
2. **사용자 편집 미추적**: DesignStudio 시드 effect가 `siteAnalysis` 변경마다
   `zoning`을 덮어써 사용자 수정 유실 가능.

## zone 시드 경로
`siteAnalysis.zoneCode` (부지분석 SSOT)
→ DesignStudio useEffect(73행 부근): `normalizeZoning(zoneCode)` 정규화 후 `form.zoning` 시드
→ `localCalc` → `getZoningSpec(form.zoning)` / `calcMaxGrossArea(area, form.zoning)` (둘 다 내부 정규화)
→ 건폐/용적/높이/연면적/주차 산출.

## 정규화 매핑 (`lib/kr-building-regulations.ts` 신규 export `normalizeZoning`)
- 공백 제거 후 ZONING_DB 정식 키 직매칭/포함검사("...일반상업지역..." → "일반상업지역").
- "지역" 접미사 누락 변형 보정("일반상업" → "일반상업지역").
- 단축코드 보정(1R/2R/3R/QR/GC/NC/QI → 정식 키, AutoDesignPanel 계열 정합).
- 실패 시 null 반환 → calc는 honest null(허위 수치 미표시), 시드는 원문 보존(드롭다운/SolarEnvelope 폴백).
- `getZoningSpec`·`calcMaxGrossArea`에 내부 적용 → DesignStudio 외 CostEstimationClient,
  CadCompliancePanel, CostAndQuantityDashboard 등 모든 소비자 SSOT-wide 동시 교정.

## 일반상업 800/1300 정합
- 일반상업지역 ZONING_DB: 건폐율 80%, 용적률 1300%, 높이제한 없음.
- 정규화 후 calc가 1300% 산출 → SolarEnvelopeCard(envelope) zone과도 동일 출처(`siteAnalysis.zoneCode || form.zoning`)로 정합.
- (근린상업 900%, 준주거 500% 등 기존 테이블 값 그대로.)

## 무한루프 가드
- 시드 effect 의존성 `[siteAnalysis, zoneEdited]`. `zoneEdited`는 select onChange에서만 true 전환.
- `zoneEdited=true`면 `prev.zoning` 유지(시드 미적용) → 사용자값 우선, 재시드 루프 없음.
- designData 기록 effect(기존)는 그대로 unchanged 가드 유지.

## SSOT·무목업
- 용도지역 단일출처 = 부지분석. 설계는 정규화하여 상속만. 하드코딩/목업 수치 없음.
- 정규화 불가 시 calc 미산출(거짓 250% 금지).

## 검증
- `npx tsc --noEmit` → EXIT 0.
- git diff: import `normalizeZoning` 추가, 기존 import 보존(린터 트랩 없음).
- 변경 파일: `components/design/DesignStudio.tsx`, `lib/kr-building-regulations.ts`.

## 미진
- 라이브 E2E(일반상업 주소 재진입 → 1300% 표시 → ROI 정상) 미실행(push/배포 금지 범위).
- `siteAnalysis.zoneCode`가 정규화 불가한 신규 변형일 경우 `normalizeZoning` 패턴 추가 필요(현재 NED prposArea1Nm 정식명 기준 커버).
