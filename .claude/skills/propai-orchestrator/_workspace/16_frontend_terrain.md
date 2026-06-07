# Flagship C-1 — 지형분석 프론트엔드 구현 보고

계약: `15_flagshipC1_contract.md` (POST /api/v1/terrain/analyze)
작업 루트: `propai-platform/apps/web`
커밋: `61f1bb1` feat(terrain): 지형분석 패널(경사도·토공량·지형단면 프로파일)

## 1. 신규/변경 파일 · 배치 위치

| 파일 | 종류 | 비고 |
|------|------|------|
| `components/terrain/types.ts` | 신규 | 계약 응답 스키마 1:1 타입 (TerrainRequest/Result/Slope/Earthwork/CrossSection 등) |
| `components/terrain/TerrainAnalysisPanel.tsx` | 신규 | "use client" 패널. 입력 + 3섹션 결과 렌더 |
| `app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` | 변경(+4줄) | import 1줄 + `stage==="result"` 블록 L3EnhancedCards 직후 `<TerrainAnalysisPanel address={siteData.address} pnu={siteData.pnu} />` 1줄 |

배치 결정: 신규 라우트 대신 **부지분석 결과 화면에 섹션 결합**(계약 권장). 상위에서 확보한 `address`·`pnu`를 props로 전달, 패널 내부에서도 주소 재입력 가능(독립 실행 지원).

## 2. 응답타입 계약 일치 · 재사용
- 계약 스키마 전 필드 매핑: `ok/message, elevation_source, resolution_m, sample_count, area_sqm, slope{mean_pct,max_pct,aspect_deg,class,detail}, earthwork{base_level_m,cut_volume_m3,fill_volume_m3,net_m3,balance,detail}, cross_section{bearing_deg,length_m,points[{dist_m,elev_m}],min_elev_m,max_elev_m,relief_m}, confidence, note, sources`.
- `SlopeClass`=평지|완경사|경사|급경사, `EarthworkBalance`=절토우세|성토우세|균형 — 계약 enum 그대로 union 타입화.
- **차트 재사용**: recharts ^3.8.0(package.json 확인). 지형단면 = `AreaChart`(x=dist_m, y=elev_m, 토큰색 그라데이션). 기존 `MonteCarloPanel.tsx`의 ResponsiveContainer/XAxis/YAxis/Tooltip 패턴 답습.
- 패널 구조·스타일: `components/avm-vision/AvmVisionPanel.tsx` 답습(Card/CardContent @propai/ui, EXPERIMENTAL 배지, FeatureBar→VolumeBar, apiClient.post v1, null-graceful).
- API: `apiClient.post<TerrainResult>("/terrain/analyze", { body })`.

### 렌더 3섹션
- 경사도: class 의미색 배지(녹/황/적)+desc, mean/max %, **SVG 나침반**(aspect 16방위 바늘), aspect 한글방위 라벨.
- 토공량: 절토/성토 정규화 비교 바(volMax 기준), balance 배지, net·base_level.
- 지형단면: points→AreaChart 프로파일, min/max/relief 3칸.
- 메타칩: elevation_source·resolution_m·sample_count·area_sqm·신뢰도(% 의미색). note(ℹ)·sources 명시. EXPERIMENTAL/참고용 표기.
- 상태: 로딩("지형 분석 중…")/에러(amber)/`ok:false`(message 표시) 전부 처리. 표본 부족 시 차트 자리 폴백 문구.

## 3. 로컬 검증
- `npx tsc --noEmit` → **EXIT 0** (초기 recharts3 Tooltip formatter 타입오류 1건 → `(v) => [...]`로 수정 후 통과).
- `npx eslint components/terrain/*` → **EXIT 0, 0 problems**.
- page.tsx의 eslint error 2 + warning 2(line 3 useEffect, 326 unescaped quote, 392 unused i)는 **기존 코드 이슈**로 본 변경(+4줄: import·패널 배치)과 무관. apiClient import **보존 확인**(린터 삭제 회귀 없음).

## 4. 백엔드/QA 정합사항
- 프론트는 계약 200 스키마에 **정확히** 의존. 백엔드는 다음 보장 필요:
  - `slope.class` ∈ {평지,완경사,경사,급경사}, `earthwork.balance` ∈ {절토우세,성토우세,균형} — 정확 일치(다르면 의미색/배지 미표시).
  - `cross_section.points` 2개 이상이어야 단면 차트 렌더(1개 이하 → "단면 표본 부족" 폴백).
  - `confidence`는 0~1 실수(프론트 ×100 표기). `aspect_deg` null 허용(나침반 N/A).
  - 실패 시 `{ok:false, message}` 반환(프론트가 message 노출). 422(주소·pnu 둘 다 없음)는 catch로 일반 에러 표시.
- QA: 부지분석 결과 단계 진입 → 패널 자동 노출, 주소 사전주입 확인. 다크/토큰색·CTA nowrap 준수.
- 데이터흐름: useProjectContextStore.terrain 저장은 계약 "가능시/과설계 금지" 단서라 **미구현**(공사비 토공 연계는 백엔드 응답 안정화 후 후속).
