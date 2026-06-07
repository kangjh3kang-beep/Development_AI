# 71. 프론트엔드 부지분석 고도화 표시 — 실효용적률 계층·종상향 잠재시나리오·대장(표제부/멸실/미준공/분묘)

## 1. 대상 컴포넌트
- **주 렌더**: `apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx`
  - `L3EnhancedCards` 함수형 컴포넌트가 `/zoning/comprehensive`(=`LandInfoService.collect_comprehensive`, auto_zoning.py:118) 응답을 렌더.
  - 기존 카드 3종(실거래가/건축물대장/인프라) + 신규 3섹션 추가.
- **부 렌더(미수정)**: `components/pipeline/SiteAnalysisDetail.tsx` — 파이프라인 진입 경로의 카테고리 카드. 이미 용도지역/AI해석 카드 보유. 본 작업은 site-analysis 페이지(직접 분석 진입)만 강화(스크린샷 화면). SiteAnalysisDetail은 무변경(무파괴).

## 2. 변경 파일
- `apps/web/.../site-analysis/page.tsx` (1파일, +393/-7). 커밋 `cf6dfda`.

## 3. 백엔드 응답 경로 정합(중요)
- 프론트는 `/zoning/comprehensive` 호출 → **`LandInfoService.collect_comprehensive`** 반환.
  - ✅ 보유: `building_detail`(표제부 세대/가구/호/동·멸실·미준공·data_source, land_info_service.py:739~768), `grave_registry`(available:false 정직), `zone_limits`(max_far_pct·ordinance_far_pct·ordinance_source·ordinance_legal_basis).
  - ❌ 미보유(현재): `effective_far`/`far_basis_detail`/`upzoning`/`upzoning_scenarios`/`potential_far_range`/`upzoning_interpretation` — 이들은 **`ComprehensiveAnalysisService.analyze`**(`/api/v1/analysis/comprehensive`, comprehensive_analysis_service.py:180·249·1005)에만 존재.
- **설계 결정(표시만·호출 무변경 제약 준수)**: 프론트 타입·setL3Data에 위 필드를 **옵셔널로 캡처**하고, 카드는 **데이터 존재 시에만 렌더(없으면 정직 미표시)**. 실효용적률 카드는 `zone_limits`(현 응답 보유)로도 법정·조례 계층을 표시 가능하게 폴백 추출. → 종상향/far_basis_detail이 종합응답에 합류(백엔드 69/70 종합엔드포인트로 통합되거나 collect_comprehensive 확장)하면 코드 무변경 자동 노출.
- ※ 백엔드 워크스페이스 67(실효용적률 계층화)·69·70 명세 기준. 69/70 md 파일은 디스크 미존재(커밋 763afa6·bb1df41로 백엔드 반영됨). 필드명은 소스 확인: 시나리오는 `expected_far_pct_low/high`(프롬프트의 expected_far_low/high 아님), `feasibility`(상/중/하)·`feasibility_reason`·`expected_far_source`·`legal_basis`·`timeline_est`·`caveats`·`is_estimate`.

## 4. 표시 방식
### ① 실효용적률 계층 카드 (indigo)
- 가로 흐름: **① 법정범위(min~max) → ② 조례 적용 → [③ 계획상한] → [④ 인센티브 완화율]**(③④는 데이터 있을 때만).
- 조례 미확인 시 ② 칸 점선·"확인 필요" + 헤더에 "조례 확인 필요" 앰버 배지.
- 하단 강조 박스: **최종 실효 용적률** + `far_basis_detail.최종근거`(폴백 zone_limits.ordinance_source) + `데이터출처` 표기.
- 추출 폴백: far_basis_detail 없으면 effFar.legal_*  → 없으면 zone_limits.max_far_pct/ordinance_far_pct/ordinance_legal_basis.

### ② 종상향 잠재 시나리오 카드 (purple, 현행/잠재 2계층 분리)
- 상단 **앰버 고지박스**: "예상치 — 도시·군관리계획 결정 및 인허가를 전제로 한 잠재 시나리오이며, 실현을 보장하지 않습니다."
- **현행(확정, 회색)** vs **잠재(예상치·미확정, 점선 purple)** 2칼럼 시각분리. 잠재에 `potential_far_range`(min~max) 요약.
- 시나리오 리스트: 경로(path)·목표지역(target_zone)·예상용적률(low~high+source)·가능성 배지(상=emerald/중=amber/하=muted)·사유·조건칩·근거법령·예상기간·전제(caveats).
- `upzoning_interpretation` LLM 해석 카드(accent) 연결. 시나리오 0건이면 `summary` 안내.

### ③ 대장(건축물대장 표제부) 강화 — 기존 카드 확장
- 추가 필드(`_display` 우선): 동수·세대수·호수·가구수. 사용승인일·표제부상태(비정상 시).
- **멸실**(is_demolished) → 빨강 "멸실 건축물(확인 필요)" + 멸실일 배지.
- **미준공**(is_uncompleted) → 앰버 "미준공/공사중 추정" 배지.
- **data_source** 배지: molit_live="실시간 조회"(emerald) / 그 외="조회 불가"(muted).

### 분묘
- `grave_registry.available===false`면 묘비 아이콘 안내카드: "분묘 정보: 데이터 없음 — {reason} — {suggestion}". **가짜 표시 금지**(available 외 케이스는 미표시).

## 5. 정직성(예상라벨·무자료처리)
- 종상향은 카드 헤더("현행과 분리된 예상치")+앰버 고지박스+잠재 칼럼 "예상치·미확정"+각 시나리오 `is_estimate` 전제로 **현행과 명확 분리**, 단정 금지.
- 조례 미확인 시 "확인 필요"·점선, 가짜 조례값 미표시.
- 대장 무자료(필드 0/없음)는 해당 칸 미렌더. 분묘는 available:false에서만 "데이터 없음(사유)" 표기.

## 6. 디자인/제약 준수
- 전부 토큰색(var(--surface-strong/-muted/-soft), --line(-strong), --accent-strong/-soft, --text-*) + 의미색(emerald/amber/red/blue/purple/indigo). 다크 기본. 모바일 sm: 브레이크.
- 데이터·호출 로직 무변경(옵셔널 캡처만 추가). 새 의존성 0(기존 framer-motion/Icons 재사용).

## 7. 검증
- **tsc**: `npx tsc --noEmit --incremental false` → **EXIT 0**(전체).
- **eslint**: 대상파일 잔존 4건(useEffect 미사용 warning·hero 인용부호 `"` error 2건·apt items map `i` warning)은 **전부 사전존재**(git stash 베이스라인 동일, 라인만 시프트). 본 변경 신규 0건.
- **import 보존**: apiClient import·/zoning/analyze·/zoning/comprehensive 호출 git diff로 확인(삭제 0). 건축물대장 카드 중복 없음(제목 1회).

## 8. 커밋
- `cf6dfda` feat(site-analysis): 부지분석 고도화 표시 — 실효용적률 계층·종상향 잠재시나리오(현행/잠재 분리)·대장(표제부/멸실/미준공/분묘 정직)
- 명시경로(page.tsx)만 add. push·배포 안 함.

## 9. 미진점 / 후속 권고
1. **종상향·far_basis_detail 실표시는 백엔드 종합응답 합류 필요**: 현재 `/zoning/comprehensive`(collect_comprehensive)에 미포함. 권고 — (a) collect_comprehensive에 `_calc_effective_far`/UpzoningPotentialAnalyzer 결과 동봉, 또는 (b) 프론트가 `/analysis/comprehensive`도 병렬 호출. 본 작업은 (a)/(b) 합류 시 무변경 자동노출 되도록 옵셔널 렌더로 선반영.
2. 사전존재 eslint 2 error(hero 인용부호)는 범위 외라 미수정(무파괴 원칙). 필요 시 별도 정리 권장.
3. SiteAnalysisDetail.tsx(파이프라인 경로)에도 동일 3섹션 이식 시 일관성↑(이번엔 스크린샷 화면=site-analysis 페이지만).
