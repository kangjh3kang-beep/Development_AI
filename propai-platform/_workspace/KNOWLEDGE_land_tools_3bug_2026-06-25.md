# 토지·자금 3대 라이브버그 수정 — 지식기록 + 다음 세션 인수인계서

> 작성 2026-06-25 · 브랜치 `fix/land-tools-multiparcel-responsive`(origin/main `eb0efa44` 기준) · 커밋 `9f1d5246`(83파일, 푸시 완료) · 워크트리 `~/My_Projects/Development_AI_landtools`
> 검증: type-check exit0(0 errors) · eslint 0 errors · py_compile OK · 3관점 적대적 코드리뷰 critical/high 0(종합 7.5)
> ★머지/배포 = 통합자. main 직접 푸시 금지.

---

## PART A — 과정·결과·노하우 (기록)

### 0. 한 줄 요약
라이브(4t8t.net) 토지·자금 메뉴의 3대 사용자보고 버그(① AVM시세추정 대표번지만 분석 ② 등기권리분석 안 됨 ③ 토지조서 프레임 오버플로우)를 **코드 그라운드트루스 진단 → 공용패턴 수정 → 전역스윕 → 완결게이트 → 커밋·푸시·기록** 절차로 근본수정.

### 1. 진단 방법론 (재사용 가능)
"안 됨/부정합" 사용자 신고는 **추측 금지, 코드 그라운드트루스로 3단 추적**:
1. **정답 기준선 확보**: 정상 동작하는 형제 경로를 먼저 찾는다(다필지는 registry-analysis·land-schedule이 `siteAnalysis.parcels` 소비 = 정답). 버그 경로와의 **격차**가 곧 근본원인.
2. **체인 추적**: 데이터 흐름(스토어→컴포넌트→fetch→백엔드 서비스→provider)과 렌더 체인(layout→page→component→table)을 끝까지 따라가 **끊긴 고리**를 특정.
3. **전역 규모 측정**: 같은 패턴이 몇 곳에 있는지 `grep -rn`으로 센 뒤(국소가 아니라 패턴) 전역 스윕.

### 2. 버그별 상세

#### ① AI시세추정 대표번지만 분석 (다필지 부정합)
- **증상**: 토지조서·등기부열람은 33필지 일괄인데 AVM은 대표번지(상도동 210-453) 1건만.
- **근본원인**: `apps/web/components/operations/DeskAppraisalReportClient.tsx`가 `siteAnalysis.address`(대표) 단일만 `addr` state로 소비. 형제 페이지는 `siteAnalysis.parcels` 전필지 소비 → **이 페이지만 미배선(반쪽출하)**.
- **수정**: `parcels`(useMemo) 소비 + `fetchAppraisal(targetAddr, {addressOnly?})` 공통헬퍼 + `analyzeAll`(순차 일괄·진행중 점진표시·첫성공 상세고정) + 다필지 요약표(필지·면적·채택가·단가·신뢰도 + **통합 합계행**, 행클릭→상세). ★일괄경로 `addressOnly:true`로 주소만 전송 → 필지별 공시지가·면적 자동조회(대표 수동입력이 타 필지 오염 방지).

#### ② 등기권리분석 기능부재 + 법무사
- **페르소나 사실확인**: `registry_analysis_service.py:_SYSTEM`은 이미 "법무사20년+부동산변호사" — **경매 페르소나 오염 없음**(화면 "압류·가압류·경매"는 권리표기). 사용자 인식 오해 정정.
- **근본원인A(프론트)**: `RegistryAnalysisWorkspaceClient.analyzeAll`이 `run()`의 `setResult`를 **매번 덮어써** 다필지 시 마지막 1건만 표시.
  - 수정: `run`이 `Result|null` 반환 → `batchResults` 누적 + 필지별 요약(안전성등급·요약·'상세'버튼) 렌더 + 종료 후 첫 성공건 고정.
- **근본원인B(백엔드)**: apick은 **xlsx→텍스트(openpyxl)**가 주 소스. xlsx 추출이 비고 **PDF만 확보**되면 `source` 공백 → `analyze()`가 `{status:"empty", ai:None}` 반환 → 권리분석 통째 누락.
  - 수정: `_pdf_to_text`(PyMuPDF·**기존 의존성** `pymupdf==1.24.10`, `import pymupdf`→`except ImportError: import fitz` 폴백) 추가. source 공백 시 PDF 본문 텍스트추출해 분석소스 보강(이미지 PDF는 빈문자열 graceful — OCR 미적용, 무리한 추측 금지).
- **법무사 그라운딩**: `_SYSTEM/_TMPL`에 결정규칙(말소기준권리·인수/소멸·대항력·개발리스크 연결) + JSON에 `baseline_right`·`acquired_extinguished` 신규필드(백엔드 생성 + 프론트 타입·렌더 — 구버전 응답 graceful 가드).
- ★**시니어 법무사 `senior_agents/specs` spec은 담당 세션(`feat/senior-agents-foundation`)에 위임 — 디렉토리 미접촉**(사용자 지시).

#### ③ 토지조서 비반응형 프레임 오버플로우 (전역 패턴)
- **증상**: 토지조서 테이블 우측 열("자동채움 분석")이 프레임 밖으로 잘림("분석"→"분"), 가로 스크롤 안 됨.
- **근본원인(확정)**: 레이아웃 체인의 **min-width:auto 블로우아웃**.
  - `(dashboard)/layout.tsx:88` `<main className="min-w-0 ...">` ✅
  - → `land-schedule/page.tsx` `<div className="grid gap-6">` ❌ **열정의·min-w-0 둘 다 없는 맨 grid** → 암시적 단일 트랙이 `auto`(NOT `minmax(0,1fr)`) → 넓은 테이블(`min-w-[980px]`)의 max-content로 **팽창**.
  - → `LandScheduleClient`(내부는 `grid min-w-0 grid-cols-1` 정상) → `CardContent overflow-x-auto` → `table min-w-[980px]`.
  - 상위 `auto` 트랙이 이미 콘텐츠 너비로 팽창 → **안쪽 `overflow-x-auto`가 스크롤바를 못 만들고** 뷰포트 넘어 클립. "필지별 2줄"은 행 높이만 키울 뿐, 가로 오버플로우는 1줄도 발생.
- **수정(공용 SSOT 전역스윕)**: bare `className="grid gap-6"`/`"grid gap-8"` → `grid grid-cols-1 gap-N min-w-0` **apps/web 전역 약 82곳**(app 26 + components 44 + features 등). Tailwind `grid-cols-1`=`repeat(1,minmax(0,1fr))`로 트랙 최소 0 → `overflow-x-auto` 정상 활성.

### 3. 노하우 / 모범사례 (전역 일반화)
1. **CSS Grid min-width:auto 블로우아웃**: 페이지/섹션 래퍼에 **bare `grid` 금지**. 항상 `grid-cols-1`(=`minmax(0,1fr)`)+`min-w-0`. 증상=안쪽 `overflow-x-auto`가 스크롤 안 되고 콘텐츠가 뷰포트 밖 클립. 원인=`auto` 트랙이 max-content로 팽창. **bare `grid`는 단일열 세로스택이 의도였으므로 `grid-cols-1` 추가는 의미동일·무손상**.
2. **미배선/반쪽출하 안티패턴**: 같은 데이터 SSOT(`siteAnalysis.parcels`)를 소비하는 형제 페이지가 있는데 한 페이지만 단일값 소비 → **형제 페이지 패리티 체크**가 진단의 지름길.
3. **silent-fail**: provider가 PDF만 주고 텍스트가 비면 분석이 통째 누락. 폴백 소스(PDF추출)를 두되, 추출 실패 시 **정직하게 empty 처리**(무리한 추측 금지).
4. **다필지 결과 덮어쓰기**: 루프에서 단일 `setResult`를 반복하면 마지막 1건만 남음 → **로컬 `acc` 배열 누적 후 `set([...acc])`** + 첫 성공건 고정(형제 페이지 UX 대칭).
5. **전역 전파방지**: 국소패치 금지. `grep -rn`으로 전 범위 측정 → 공용 패턴 일괄 치환. ★주의: 스윕 디렉토리 누락 함정(최초 `app`+`components`만 → `features` 누락 → 리뷰서 적발 → 전역 재스윕).
6. **계약 경계 양측 검증**: 신규 필드는 백엔드 생성 + 프론트 렌더를 **동시**에(반쪽출하 방지), 구버전 응답엔 graceful 가드.
7. **성장루프 게이트**: 구현 → 완결게이트(type-check/eslint/py_compile) → 3관점 적대적 코드리뷰 → 지적 MEDIUM 반영 → 커밋. critical/high 0 + IMPROVED만 커밋.
8. **멀티세션 안전**: 전용 워크트리(origin/main 기준)·공유보드 claim/release·**타 세션 소유 디렉토리 미접촉**(senior_agents는 담당세션 위임).

---

## PART B — 다음 세션 인수인계서

### B-1. 현재 상태 (DONE)
- 3대 버그 수정 완료·커밋 `9f1d5246`·**브랜치 푸시 완료**(`origin/fix/land-tools-multiparcel-responsive`).
- 게이트 전부 PASS. 코드리뷰 critical/high 0.
- 메모리 `project_land_tools_multiparcel_responsive.md` + MEMORY.md 인덱스 기록.
- 공유보드 note + claim release 완료.

### B-2. 통합자가 할 일 (머지/배포)
1. `fix/land-tools-multiparcel-responsive` → main 머지(PR 또는 직접). origin/main 최신과 충돌 가능성 낮음(대부분 additive·className 치환).
2. 백엔드/프론트 둘 다 Oracle Cloud 배포(프론트=A1 재빌드·sw 버전 올림 / 백엔드=`deploy.sh` origin/main 기준). 상세 [[project_oracle_deploy]].

### B-3. deploy-pending 라이브 검증 체크리스트 (배포 후)
- **버그①**: 다필지 프로젝트(예: 상도동 33필지)에서 AVM `/desk-appraisal` → "전체 필지 분석" → 요약표 N행 + 통합 합계 정상? 단일 '서칭·분석'은 상세 입력 적용되나?
- **버그②**: `/registry-analysis` → "전체 분석" → 필지별 요약 누적 표시(마지막 1건만 X)? 말소기준권리·인수/소멸 카드 렌더? ★**등기권리분석이 여전히 "안 됨"이면 1순위 = apick 인증키(`APICK_CL_AUTH_KEY`) 활성 여부**(코드 정상·키 미설정 시 정직 안내문). [[project_registry_providers]] 참조.
- **버그③**: `/land-schedule` 33필지 → 우측 "자동채움/분석" 열 안 잘리고 카드 내부 가로 스크롤 활성? 모바일/좁은 화면도.

### B-4. 다음 세션 backlog (이어받을 작업)
- **(LOW) grid 일반화 룰**: `gap-2~4` bare grid는 내부 소형 레이아웃이라 이번 스윕 제외. 재발 원천차단 위해 **ESLint 커스텀 룰**(bare `grid` 금지) 또는 공용 `<StackGrid>` 래퍼 도입 검토.
- **(조율) 시니어 법무사**: `senior_agents/specs/legal_scrivener.py`는 `feat/senior-agents-foundation` 담당 세션이 추가. 이번 registry 경로의 결정규칙(말소기준권리·인수/소멸·대항력)을 그 spec의 골든사례·decision_rule로 승격하면 일원화. 담당세션과 `mcp__ccd_session_mgmt__send_message`로 조율.
- **(개선) 일괄분석 취소(abort)**: 수십 필지 순차호출 시 누적 지연(등기 ~31s/건). AbortController로 중간 취소 UX 추가 검토(리뷰 open question).
- **(진단) PDF/업로드 로깅 분리**: `registry_analysis_service` PDF 추출/업로드가 동일 try/except — 운영 디버깅 위해 분리 로깅(LOW).

### B-5. 충돌 주의 (멀티세션)
- **`Development_AI_senior`(feat/senior-agents-foundation)**: senior_agents 디렉토리 소유 — 이번 작업은 미접촉. 법무사 spec 추가 시 그 세션과 조율.
- 다른 활성 워크트리 다수(`git worktree list` 확인). 공유보드 `scripts/coord.sh status` 먼저 읽기.

### B-6. 빠른 재개 (다음 세션)
```
cd ~/My_Projects/Development_AI_landtools/propai-platform   # 이 작업 워크트리
git log --oneline -3                                        # 9f1d5246 확인
bash ~/My_Projects/Development_AI/scripts/coord.sh status   # 공유보드
# 라이브 검증: 배포 후 4t8t.net/ko/{desk-appraisal,registry-analysis,land-schedule}
```

---

연관 메모리: [[project_land_tools_multiparcel_responsive]] [[project_multiparcel_integrated_analysis_gap]] [[project_registry_providers]] [[project_registry_landschedule]] [[project_oracle_deploy]] [[feedback_bug_fix_record_and_propagate]] [[feedback_record_and_share]].
