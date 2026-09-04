---
type: design
project: PropAI
date: 2026-07-22
status: active
tags: [분양앱, 화면스펙, 페이지구성, 패널, 필드, 워크스페이스, sales, fieldapp]
source: "코드 실측 — SiteWorkspaceClient/roleConfig 직접 read + 25개 패널 병렬 필드추출(4 Explore)"
verified: true
confidentiality: internal
---

# 분양앱 화면 스펙 보강 — 페이지·패널·필드·배치·워크스페이스

> 앞선 [[PLAN_sales_app_sitemap_storyboard_2026-07-22]]의 사이트맵/스토리보드를 **화면 단위 설계 스펙**으로
> 내린 문서. 전 내용은 코드 그라운드트루스(실제 컴포넌트 필드) 기준. 범례: ✅ 구현 · 🔶 부분 · ⬜ 계획

---

## A. 워크스페이스 셸 (S3 현장앱 — 공통 골격)

`SiteWorkspaceClient.tsx` (462줄). 모든 현장 메뉴가 이 셸 안에서 탭 전환된다.

### A-1. 레이아웃 영역 (상→하 스택, `space-y-5`)

```
┌─ 헤더 (커맨드센터 패널) ─────────────────────────────────┐
│  [← 내 현장]   FIELD APP · WORKSPACE                       │
│               분양 현장  [역할칩: 본부장]                   │
│                     ↳우측 액션: [＋동·호표 생성]*(세대탭만) │
│                                 [🔧 현장 비밀번호]*(관리자) │
│                                 [⊞ 앱으로 열기]            │
├─ 에러 배너 (조건부·status-error)                           │
├─ 오프라인 배너 (navigator.onLine=false·status-warning)     │
├─ 스티키 탭바 ── MENU · N개 메뉴 · 내 권한 기준 ───────────┤
│  [세대배치도][고객·상담][업무일지][분양가]…가로스크롤·아이콘 │
├─ 메뉴 헤더 (활성 탭 아이콘 + 제목 + 목적 1줄 desc)          │
├─ 패널 영역 (활성 탭의 컴포넌트)                            │
└──────────────────────────────────────────────────────────┘
```

- **격리·진입**: `site_token` 없으면 `SiteEnterModal`(2차 비밀번호). 401/403 → 토큰 클리어 후 재진입. 502/503/504/0 → 지수백오프 3회 자동재시도.
- **자가치유**: `online` 이벤트 시 `loadRole()` 재호출(오프라인 중 실패 로딩 회복 — WS 재연결과 동일 패턴).
- **역할 게이팅(SSOT)**: `visibleTabs(features[])` — `alwaysOn` 탭은 항상, 나머지는 `features[]` 포함 시만. `staff` 탭은 `STAFF_OVERVIEW_ROLES`만.
- **'앱으로 열기'**: 크롬 없는 팝업 윈도우(menubar/toolbar/location=no)로 독립 앱처럼. 차단 시 새 탭 폴백.

### A-2. 탭 정의 (21탭, `roleConfig.SALES_TABS`)

| 탭키 | 라벨 | feature | alwaysOn | 아이콘 | 상태 |
|------|------|---------|:--:|--------|:--:|
| units | 세대 배치도 | units | | Building2 | ✅ |
| customers | 고객·상담 | customers | | Users | ✅ |
| worklog | 업무일지 | worklog | ● | NotebookPen | ✅ |
| pricing | 분양가 | pricing | | Wallet | ✅ |
| subscription | 청약·당첨 | contracts | | Ticket | ✅ |
| payments | 수납·납부 | contracts | | Receipt | 🔶 |
| loan | 중도금 대출 | contracts | | Landmark | 🔶 |
| resale | 전매·실거래 | contracts | | RefreshCw | ✅ |
| tax | 세금·보증 | contracts | | BarChart3 | ✅ |
| org | 조직도 | org | | FolderTree | ✅ |
| commission | 수수료 | commission | | Banknote | ✅ |
| desk | 방문 데스크 | customers | | ConciergeBell | ✅ |
| integrity | 무결성 가드 | settings | | ShieldCheck | ✅ |
| projection | 시행사 통합 | reports | | TrendingUp | 🔶 |
| cert | 해촉증명서 | cert | ● | FileText | ✅ |
| market | 구인구직 | market | ● | Briefcase | ✅ |
| profile | 내 프로필 | profile | ● | User | ✅ |
| social | 소셜·채팅 | social | ● | MessageCircle | 🔶 |
| referral | 공유·홍보 | referral | ● | Share2 | ✅ |
| staff | 직원관리 | staff | | Users | ✅ |

### A-3. 공통 UI 계약 (전 패널 일관)

- **입력**: `.IN` 스타일 · **버튼**: `.BTN` · **로딩**: `SkeletonLoader` h-24 ×3 · **금액**: `won()` 포맷터.
- **상태 색 인코딩(SSOT)**: 완납/성공/상환완료 = emerald · 미납/원천징수/미상환/주의 = amber · 연체/차단/실패/심각 = rose · 진행중 = sky · 취소 = zinc.
- **터치타깃** ≥44px, 탭바 스냅·페이드.

### A-4. ⬜ 셸 보강 계획 (P0 — Top7 ①②)

1. **역할별 홈 탭**(신규 `home`, 첫 진입 기본): 오늘 할 일·미납/연체 알림·내 실적·바로가기 FAB. 21탭 인지부하 해소.
2. **하단 탭바(모바일)**: 상위 5개(홈·세대·고객·업무일지·+더보기) 고정, 나머지는 '더보기' 시트.
3. **FAB(플로팅)**: 활성 탭 문맥 액션(세대=＋동·호표, 고객=＋고객, 업무일지=＋일지).
4. **오프라인-우선 입력**: 업무일지·고객·상담 기록에 IndexedDB outbox + Background Sync·멱등키(현재는 no-store 503 정직표기만).

---

## B. 메뉴별 페이지 구성 · 패널 · 필드 · 배치

각 메뉴 = 페이지 목적 → 구성 패널 → 필드(입력/컬럼/지표) → 배치. 필드는 실제 컴포넌트 추출.

### B-1. 세대 배치도 `units` ✅
**배치**: 세그먼트 3모드 토글(한 번에 하나) → 모드별 패널.

- **🟢 실시간 선점** `UnitLiveBoard`: 스탯바(총세대·분양률%·분양가능·선점중·계약) · Sticky 툴바(WS연결칩·새로고침·범례) · 동별 그리드(TTL `MM:SS` 카운트다운·60초 긴급강조·잠금) · 내 선점 액션바 · 계약확정 고객선택 모달.
  - 액션: hold(낙관+WS·기본 5분) · release · reserve(고객선택/없이) · 새로고침 · WS복구(다시로그인/재진입).
  - 상태(3): AVAILABLE·HOLD(타인)·HOLD_ME(내선점 ring)·CONTRACTED.
- **🗺️ 동·호지정** `UnitGrid` + `Unit360Panel`:
  - UnitGrid: 스탯바(총세대·분양률%·분양가능·보류·청약·계약) · 뷰컨트롤(2D/3D·확대축소 0.5~1.5·범례) · 동별 배치도(동→층 내림차순) · `Grid3D`(Three.js 큐브).
  - Unit360Panel(우측 드로어): 기본(층/라인/향·상태·분양가) · 세대액션(상태전이 컨텍스트) · 특이사항 등록(text·Enter) · 분양가 구성 · 계약(단계·계약금액·회차) · 이벤트 타임라인(원장·content_hash 12자).
  - 상태전이 버튼(동적): HOLD_REQUEST·CONTRACT_WAIT·HOLD_CANCEL·CONTRACT_SIGN·CONTRACT_CANCEL·CONTRACT_TERMINATE·NOTE.
  - 상태(5): AVAILABLE·HOLD·APPLIED·CONTRACTED·CANCELLED.
- **🎲 동·호추첨** `DrawMode`: 그룹 선택/생성 · 대상자 등록(수기 textarea "이름,연락처" / Excel .xlsx / 계약자명부 / 청약당첨자 연계) · 진행률바 · 순번 추첨패널(현재차례 강조·로스터: 순번#·이름·배정결과·seed 8자·계약상태) · 룰렛 공개모달(당첨자·동호·seed·pool·remaining).
- **모달**: `UnitOutlineBuilder`(＋동·호표 생성): 건축개요(대지면적·용도지역·건폐율·용적률 자동로드) · 동 빌더 반복(동명·모드[공동주택 uniform / 상가 retail]·층수·층당호수·향·평형) · "설계(BIM)에서 자동" / "동·호표 생성".

> ★설계 노트: 상태 모델 불일치(LiveBoard 3상태 vs Grid/360/3D 5상태) — 통일 스펙 필요(APPLIED·CANCELLED를 LiveBoard가 어떻게 표시할지).

### B-2. 고객·상담 `customers` ✅
**배치**: 상단 추가폼 → 필터바 → 카드 리스트(→상세 드로어) → AI 예측 리스트.

- `CrmPanel`: 고객추가(고객명·연락처) · 필터(범위 세그먼트[현장별/통합]·단계 select 8종·이름/연락처 검색) · 고객카드(등급칩·이름·연락처[통합뷰 마스킹]·단계칩·현장명칩) · AI 가망고객(등급·이름·연락처·점수·사유→다음액션).
  - 액션: ＋추가·조회·재예측·등급 일괄반영·(카드)상세·(예측)상담기록.
  - 등급: A핫(rose)·B웜(amber)·C콜드(sky). 단계 8종: 리드/상담/방문/예약/계약/중도금/잔금/이탈.
- `CustomerCardDrawer`(상세): 문자/알림톡 발송(채널토글·템플릿코드[알림톡]·본문 textarea) · ＋기록 추가(종류토글[상담/방문/메모/단계변경]·단계 select·내용) · 활동 타임라인(종류칩·from→to·시각·작성자).
  - 발송결과: SENT/BLOCKED/SKIPPED/FAILED. 차단사유: 수신동의없음·야간(21~08)·발신번호미등록·채널미설정·발송오류(정보통신망법 §50).

### B-3. 업무일지 `worklog` ✅ (alwaysOn)
`WorkLogPanel`: 실적요약(기간토글 오늘/주/월/분기/연·지표 상담·방문·계약·메시지·일지 count) · 작성(일자·요약·활동행 반복[종류 select·내용·고객ID]) · 목록(기간필터 from~to·일자·작성자·요약·활동).

### B-4. 분양가 `pricing` ✅
**배치**: 차수(round) select → 3패널 수직 스택.

- `PricingConfigPanel`(접이식): ⓪적정분양가 추천(`FairPriceSuggestCard` 임베드) · ①기준가(타입별 basis[호당/㎡당]·기준단가) · ②가중치(dimension[층/라인/향]·값·basis[비율%/정액]·value) · ③가격구성(component[토지비/건축비/기타]·표시명·basis·value·VAT).
  - 액션: 기준가 저장(onBlur) · ＋가중치/＋구성 · AI 분양가 제안(LLM) · 설정적용→재생성 · 적정가 채택(전타입 일괄).
- `FairPriceSuggestCard`: 시장요약(주변실거래 만원/평·신뢰도%·verdict·건수) · 3안 티어(보수/기준/공격: premium%·만원/평·84총액·원가비율·마진) · 원가검증 · 직접입력 · 근거패널 · AI검증 배지.
  - 신뢰도 색: ≥0.7 emerald·≥0.45 amber·else rose. 티어: 원가회수 가능(emerald)/미회수(rose).
- `PriceGroupingPanel`: 헤더(총매출·선택수) · 원가구성 칩 · 목표총매출 역산 · 빠른선택(라인/향/해제) · 세대 그리드(범위선택) · 적용(mode[＋%/＋원/평당단가절대]·value).
- `PriceTableEditor`: 컬럼(동/호·모드[가중치/확정금액]·분양가·확정금액 입력) · 가중치 일괄 재생성.

### B-5. 청약·당첨 `subscription` ✅
`SubscriptionPanel`: 입주자모집공고 등록(공고번호·회차) · 공고 목록표(공고번호·상태·추첨) · 당첨/예비 현황 칩.
- 액션: 공고 등록 · 가점·추첨 실행("추첨 완료: N세대"). 상태: OPEN→DRAWN.

### B-6. 수납·납부 `payments` 🔶
`PaymentsPanel`(가장 복잡): 계약자별 통합수납(지표 6칩[분양가·청구·납부·미납·연체·할인/환급] + 회차 스케줄표[회차·구분·약정일·금액·납부·미납·상태·연체일·이자] + 할인/환급 등록) · 가상계좌 발급(계약·은행·계좌번호·예금주) · 입금 수납(계좌번호·입금액) · 연체현황표(+즉시재계산) · 미대사 입금큐 · 매칭완료 리스트 · 취소/반려·수동매칭 모달.
- 상태(회차): PAID완납(emerald)·PARTIAL부분(sky)·UNPAID예정(회색)·OVERDUE연체(rose볼드). 입금: MATCHED/UNMATCHED/REVERSED.
- 🔶 이체=기록만(실 PG 미수행)·savepoint flush 실DB 검증 대기.

### B-7. 중도금 대출 `loan` 🔶
`LoanPanel`: 대출협약(은행·보증유형 HUG/HF/NONE) · 차주약정(계약·협약·승인액) · 중도금 실행(약정·회차·금액) · 대출상환(약정·상환액·상환일 + 결과 지표 4칩[실행총액·상환누적·미상환잔액·상태]).
- 상태: 협약 ACTIVE · 약정 APPROVED→REPAID. 🔶 자금이체=기록만.

### B-8. 전매·실거래 `resale` ✅
`ResalePanel`: 실거래신고(계약·목록[상태·기한]) · 전매/명의변경 요청(계약·양수인ID·유형[RESALE/NAME_CHANGE]) · 심사표(유형·판정·사유·처리).
- 판정: 허용(emerald)/차단(rose)+사유. 계약당 단일 PENDING.

### B-9. 세금·보증 `tax` ✅
`TaxPanel`: 선분양 보증요건(충족/미충족·HUG·신탁) · 세금계산서 발행(사업자번호·공급가액·VAT·품목 + 목록) · 지급명세서(기간 YYYY-MM + 결과[지급총액·원천징수]).
- 보증: 충족(emerald)/미충족(rose). direction: ISSUE(정발행)/역발행.

### B-10. 조직도 `org` ✅
`OrgTree`: 팀현황(지표[관리대상N명·전체계약·고객·업무일지] + 로스터표[직급·이름·인원배정·계약·고객·업무일지·수수료세금·정산]) · 노드추가(상위·직급·이름) · 조직트리(ltree) · 정산 명세모달(계약기여·수수료·정산액·VAT/원천 3.3%·실수령).
- 액션: 배정/해제·세금유형 변경·정산·＋추가·이동·기본조직 생성. 세금: WITHHOLDING 3.3%/VAT 10%.
- ★라벨 정합주의: OrgTree DIRECTOR=이사 vs CommissionBoard/DutchPay DIRECTOR=본부장(SSOT 통일 필요).

### B-11. 수수료 `commission` ✅
**배치**: `CommissionBoard` → 구분선 → `CommissionDutchPay`.
- `CommissionBoard`: 1단 시행사총액(기준[건당고정/분양가요율%/총액풀]·요율·확정 자물쇠) · 2단 대행사배분(직급·기준[총액%/정액]·값 + 배분표 + Σ≤총액 검증[샘플분양가]).
- `CommissionDutchPay`: 계약선택 + 합의생성 · 작성폼(총수수료·기준[비율/금액]·참여자카드[아바타·라벨·비율/금액]·합계바·1/N 균등) · 합의 목록(상태칩·동의진행바·해시체인 봉인 content_hash 24자).
  - 합의: pending(amber)/confirmed(emerald)/rejected(rose). 변경 시 전원 재동의.

### B-12. 방문 데스크 `desk` ✅
**배치**: `lg:grid-cols-2` — 좌 체크인 / 우 통계.
- `DeskCheckin`: 방문등록(성함·연락처·서명 canvas) · 개인정보 동의모달 · 지명매칭(타입토글[전화/이름/명함OCR]·입력/파일 + 결과[matched 호출/candidates]).
- `VisitorStats`: 시간대별(24h) 막대차트(X=시·Y=방문자·인디고 #6366f1).

### B-13. 무결성 가드 `integrity` ✅
`IntegrityGuard`: 재점검 · 정상배너(위반없음 emerald) · 위반 findings(심각도칩·제목·건수·상세).
- 점검: 중복 동·호/1호1계약 · 수수료초과 · 서명계약 미보증 · 미가격세대. 심각도: critical(rose)/high(amber)/medium(sky).

### B-14. 시행사 통합 `projection` 🔶
`DeveloperProjection`: 포트폴리오 계기판(현장수·방문·계약·계약액·평균분양률·수수료) · 통합회계 연결결산(매출·비용·수수료배분·실수납 + 손익 3뷰[현금흐름·발생주의·선수금·미수금]) · 현장별표(→드릴다운 SiteManagePanel: 담당자·근태·회계·급여·광고 ROI) · 회계등록(항목·금액·메모) · 급여 자동산정(근태×단가·세무).
- 상태: 준비중/분양중/분양종료. 🔶 과대계상 경고배지(발생>현금흐름 & 미수금)·K-IFRS 진행기준 대기·독립대사 불일치칩.

### B-15. 해촉증명서 `cert` ✅ (alwaysOn·역할분기 2뷰)
`TerminationCertPanel`: 뷰 전환(내 증명서/발급 관리).
- **발급주체뷰**(시행/대행 관리자): 발급주체 등록(법인명·사업자번호·대표·구분·직인) · 증명서 발급(발급주체·대상행[사용자ID·기간]).
- **프리랜서뷰**(전원): 근무이력→발급신청(현장·기간 체크) · 신청현황 · 발급 증명서(연도·현장 필터·PDF/PNG/JPEG·일괄 ZIP).
- 상태: 신청중(amber)/발급완료(emerald)/반려(rose). ★정직 고지(법정양식 아님·3.3% 참고).

### B-16~19. PUBLIC (현장 무관·alwaysOn)
- **구인구직 `market`** `JobMarketPanel`: kind탭(구인/구직/현장홍보/대행모집) · 공고작성 · 필터(지역/분야/키워드) · 목록 · 상세(신청폼/신청자목록). 프로필 첨부·수락/거절.
- **내 프로필 `profile`** `MarketProfilePanel`: 개인/회사 서브탭 · 개인(사진·이름·연락처·지역·경력·분야·자격증·실적·희망조건) · 회사(로고·회사명·유형·규모·지역·소개·현장·실적) · 공개설정(전체/연결/비공개·연락처 마스킹).
- **소셜·채팅 `social`** 🔶 `SocialPanel`: 뷰탭(단톡/친구/다중톡)+WS상태 · 단톡목록·방생성 · 친구(검색→요청/받은/보낸/목록) · 채팅방(타임라인·미디어·입력바·초대) · 다중톡(다중선택·consent·야간가드). WS: 연결됨(emerald)/연결중(amber)/끊김(rose). 🔶 멀티워커 Redis 백플레인 필요.
- **공유·홍보 `referral`** `ReferralSharePanel` + `InstallGuide`: 추천코드(개인/현장전용) · 공유(링크·Web Share·QR canvas) · 퍼널통계(클릭→방문→리드→계약 전환%). PWA 설치안내(Android 버튼/iOS 3단계).

### B-20. 직원관리 `staff` ✅ (관리역할만)
`StaffOverviewPanel`: 범위 세그먼트(현장별/종합) · 합계 StatCard(멤버·계약·출근·수수료) · 현장별 집계표.

---

## C. S1 분양정보 (플랫폼측·`(dashboard)/sales-info`) ✅
`ProjectPresaleMap`: 상태필터 칩바(상태별 건수) · 카카오맵(중심마커+반경원+유형별 마커) · 마커 InfoWindow(단지명·상태·유형·접수기간·세대수·거리·시행사·입주월→상세) · 풀스크린 토글.
- 상태색: 분양중(emerald)/분양예정(blue)/분양완료(slate 0.6)/미정(amber). ★분양가·주택형은 상세조회에서만(가짜표시 방지).

---

## D. 배치 원칙 (배치계획 SSOT)

1. **수직 스택 기본**(`space-y`): 설정→실행→결과 순. 분양가·수수료가 대표(설정 상단, 표 하단).
2. **2열 그리드**는 좌=입력/우=조회일 때만(데스크 체크인|통계).
3. **드로어(우측)**: 세대 상세·고객 상세 — 리스트 유지한 채 상세 오픈.
4. **모달(중앙)**: 생성 플로우(동·호표 빌더·추첨 공개·취소/수동매칭).
5. **세그먼트 토글**: 상호배타 뷰(세대 3모드·범위 현장별/종합·소셜 3뷰) — 동시 렌더 금지(중복 방지).
6. **지표는 항상 상단**(스탯바/StatCard) → 상세는 하단(정보설계: summary before detail).
7. **상태는 형태로 인코딩**(색+칩+아이콘) — A-3 색 SSOT 준수.

## E. 보강 우선순위 (기획 확정 시)
1. **P0 셸(A-4)**: 역할별 홈 + 하단탭바 + FAB + 오프라인 입력.
2. **라벨 SSOT 통일**: 직급 라벨(DIRECTOR)·상태 모델(세대 3/5상태) 정합.
3. **🔶 배포대기 3종**(수납·회계·소셜) 라이브 확증 후 완성표기.

## Links
- [[PLAN_sales_app_sitemap_storyboard_2026-07-22]] — 상위 사이트맵·스토리보드
- [[sales_app_upgrade_loop_2026-06-18]] — 성장루프 SSOT
