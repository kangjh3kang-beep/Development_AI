# 분양관리앱(ERP) 혁신 업그레이드 — 성장루프 SSOT

> 브랜치 `feature/sales-app-erp-upgrade` · 오케스트레이터-기획자 /loop · 게이트 ★종합 9.5(5차원 하한)
> iter-1 워크플로우(wf_364401c8-d81, 15에이전트) 산출. 검증 통과분만 feature 브랜치 커밋·푸시(main 직푸시X, 머지=통합자).

## 베이스라인 점수표 (avg 6.81 / ≥9.5: 0개)

| # | 서브시스템 | 종합 | 정확 | UX | 아키 | 보안 | 완성 | 핵심 갭 |
|---|-----------|:--:|:--:|:--:|:--:|:--:|:--:|------|
| 1 | 현장 인증·보안·RLS | 6.8 | 7.2 | 6.5 | 7.0 | 6.8 | 6.2 | RLS FORCE 미적용·세션변수 풀러전파 미검증 |
| 2 | 워크스페이스·내비·PWA | 7.8 | 8.2 | 7.5 | 7.8 | 8.1 | 7.2 | WS라우팅 극소·22탭 인지부하·역할별홈 부재 |
| 3 | 수수료·더치페이·원천징수 | 6.2 | 7.0 | 6.5 | 6.0 | 5.5 | 5.5 | 런타임 DDL race·settle_summary silent-fail·해시체인 best-effort |
| 4 | 수납·대출·보증 | 6.5 | 7.0 | 5.0 | 7.0 | 8.0 | 5.0 | overdue_calc 미배선·대출상환 미구현·런타임 DDL |
| 5 | 조직도·직원 | 5.8 | 5.5 | 6.2 | 5.5 | 6.8 | 5.2 | team/staff_overview 응답계약 불일치·ltree label 숫자시작 |
| 6 | 세대 라이프사이클·추첨 | 8.1 | 8.5 | 7.2 | 8.8 | 8.0 | 7.5 | DRAWING_UPLOAD 파서 빈구현·추첨 while-True 무한위험 |
| 7 | 계약·CRM·광고·청약 | 6.8 | 7.5 | 6.0 | 7.0 | 6.5 | 6.5 | 메시지 example URL·야간차단 UTC/KST 오류·FK 미지정 |
| 8 | 적정분양가·매출역산·원가 | 7.1 | 8.0 | 6.5 | 7.0 | 6.5 | 7.0 | verdict 기준 모호·공사비엔진 silent·Pydantic 부재 |
| 9 | 해촉·전매·MH·옵션·추천·소셜·구인 | 7.2 | 7.5 | 6.8 | 7.0 | 7.0 | 7.2 | 소셜WS 단일워커·야간 UTC·채용연계 silent-fail |
| 10 | 관리자 통합콘솔·연결회계 | 5.8 | 5.5 | 5.0 | 6.5 | 6.0 | 6.5 | _scalar 예외흡수(0원 오판)·손익=계약매출(수납/선수금 미반영)·소득세 추정 |

## 9.5 게이트 정의 (가중평균 아님 = 하한)
종합 9.5 = **5차원 모두 ≥9.0 AND 미배선/목업/silent-fail 0건**. 한 차원이라도 9.0 미만이면 9.5 불가.
- 정확: 핵심계산 라이브 교차검증·할루시네이션가드·회귀0 / UX: 역할별홈·오프라인입력·마찰최소·터치≥48px / 아키: 런타임DDL 0(Alembic)·멱등키표준·응답계약 SSOT / 보안: RLS FORCE·세션변수누수0·silent-fail0·권한중앙화 / 완성: 미배선0·목업0
- ★샌드박스 제약: 라이브 DB/배포/공공API 불가 → 라이브검증 차원은 **배포후 검증(deploy-pending)** 으로 표기, 코드평가 가능 차원으로 채점.

## 우선순위 로드맵 (레버리지 순)
**Wave1 정합성·보안**: #10(5.8→8.0 P0-1) → #1(6.8→8.5 P0-2) → #3(6.2→8.3 P0-3) → 횡단 멱등키표준(P0-4)
**Wave2 미배선완성**: #4(6.5→8.2) → #5(5.8→8.0) → #7(6.8→8.3)
**Wave3 UX혁신**: #2 역할홈+오프라인(7.8→8.8) → #8 신뢰투명화(7.1→8.5)
**Wave4 차별화·마감**: #9(7.2→8.5) → #6(8.1→9.0) → 횡단 법규룰엔진(P2-4)

## 사용자친화 혁신 Top7 (리서치 근거)
1. 오프라인-우선 현장입력(IndexedDB outbox+Background Sync, 멱등키) ★ 2. 역할별 홈 대시보드+하단탭바+FAB 3. AI 영업비서(상담음성→CRM·리드스코어, 토큰과금) 4. 온라인 리드퍼널 자동화(OSC, Lasso/Sell.do) 5. 계약자 셀프포털(납부캘린더·알림톡) 6. 실시간 리더보드+예상수수료(게이미피케이션) 7. 신뢰 가시화(적정분양가 신뢰%·법규 자동판정·3-뷰 회계 — 무경쟁 차별점)

## 반복 루프 규칙
iteration(subsystem): 기획확정→구현(미배선/목업/silent-fail 0)→완결게이트(리뷰+린트+빌드)→[배포후 라이브]→다층 리뷰채점(별도lane·자기승인금지)→min(5차원) 하한게이트→통과시 커밋·푸시·다음 / 미달시 갭귀인(3대 안티패턴 분류)·최소변경 재기획·재구현·재리뷰. 2회연속 미달=서브시스템 분해. 차원 트레이드오프(UX↑위해 보안↓) reject.

---
## ITERATION LOG
| iter | 대상 | 전 | 작업요약 | 후 | 판정 | 커밋 |
|--|--|:--:|--|:--:|--|--|
| 1 | (분석·리서치·기획) | — | 10모듈 베이스라인 채점+4리서치+종합기획 | — | 완료 | c94eef60 (plan doc) |
| 2a | #10 회계 | 5.8 | (오케스트레이션 버그: args 미주입→docs-only) | 5.5 | NOPROGRESS | 미반영(스크립트 args 방어파싱 수정) |
| 2b | #10 회계 | 5.8 | _scalar silent-fail제거·손익2뷰(현금흐름/발생/선수금)·Alembic032·멱등(site,ym,type)·소득세면책 | 5.5 | NOPROGRESS | 미반영(워크트리 유지). 결함:①2뷰 프론트미배선 dead ②032 docstring 허위(5head 잔존) |
| 3 | #10 회계 | 5.8 | +2뷰 프론트배선(ProfitTriView)·롤업/summary 2뷰·부분내결함·ym검증·deferred정밀·ruff·Alembic AST교차검증(리뷰어 오진 반증) | 6.5 | IMPROVED | ★반영 c17dad89·push |
| 4 | #10 회계 | 6.5 | 읽기경로DDL강등·GET ym가드·reconcile독립대사·오류마스킹(보안8.5)·K-IFRS경고 | 6.5 | NOPROGRESS | 미반영(워크트리유지). 회귀:①reconcile 엄격!=→반올림잔차 거짓경보64.9% ②_YM_RE $앵커→개행 우회 |
| 5 | #10 회계 | 6.5 | ym fullmatch·reconcile 허용오차밴드·SIGNED범위·완전성플래그·DDL완전강등·단위테스트22 | 7.0 | IMPROVED | ★반영 82245632·push |
| 6 | #10 회계 | 7.0 | paid_exceeds tol·dead-output 단일출처화·stage확장·I001·tol타이트화·테스트24 | 6.0 | NOPROGRESS | 미반영(워크트리유지). correctness 8.5↑이나 신규 HIGH 보안적발: rollup/summary require_role 미배선(권한상승)+reconciliation dead-output |
| 7 | #10 회계 | 7.0 | require_tenant_finance 권한상승차단(테스트5)·reconciliation 배선·SSOT stage정정·문서드리프트·pytest29 | 7.5 | IMPROVED | ★반영 3cadfed2·push. **#10 종료(critical/high0 코드실링)** |

**#10 결산: 5.8→7.5(critical/high 0). 7 iterations(2 IMPROVED커밋·5차단). 잔여 deferred(MEDIUM/LOW): rollup sites[] 완전소비·_TENANT_FINANCE_ROLES import SSOT·integrity_check stage·403화면표기. 9.5갭=K-IFRS 1115 진행기준(deploy-pending 스키마).**

---
### iter→ #1 현장 인증·보안·RLS (baseline 6.8) — Wave1 P0-2
대상: services/sales/sales_rls_bootstrap.py, database/migrations/versions/v62_2_sales_rls.py, app/api/deps_sales.py, app/core/sales_crypto.py, app/api/endpoints/sales/site_auth.py, web SitePasswordModal/SiteEnterModal/SiteListClient.

| iter | 대상 | 전 | 작업요약 | 후 | 판정 | 커밋 |
|--|--|:--:|--|:--:|--|--|
| 1 | #1 RLS | 6.8 | FORCE적용·nullif fail-closed·SET LOCAL헬퍼·sales_crypto·RLS pytest19 | 5.0 | NOPROGRESS | 미반영(워크트리유지·위험). 리뷰 HIGH: ①마이그레이션 정책없는테이블 FORCE무차별→non-bypassrls시 앱전체브릭 ②p_org 광역분기 현장격리붕괴 ③org수직격리 미실현 ④중간commit SET LOCAL소멸 ⑤deleted_at누락 ⑥토큰revocation부재 |
| 2 | #1 RLS | 6.8 | ★FORCE 정책테이블만(브릭 landmine제거)·p_org RESTRICTIVE 현장스코프·after_begin 재주입·deleted_at일원화·pytest27 | 7.0 | IMPROVED | ★반영 68cfe785·push |
| 3 | #1 RLS | 7.0 | X-Site-Token 매요청 DB재검증(8h지연제거)·rls_status bypassrls·downgrade DROP·crypto fail-fast·verify제거·pytest39 | 7.5 | IMPROVED | ★반영 6c5e1028·push |
| 4 | #1 RLS | 7.5 | rolsuper·fail-open보수·docstring·resolve_site_membership 헬퍼·키길이·pytest52 | 7.5 | NOPROGRESS | 미반영(워크트리유지). 잔존 false-assurance 2: ①crypto denylist 미복제(유출키 통과)·os.getenv 우회 ②isolation_effective forced==0서 True오보 |

### #1 iter-5 재기획(9.5 도전): (a)sales_crypto._key() config 검증 재사용(settings.APP_SECRET_KEY 우선+_KNOWN_WEAK_SECRETS denylist 공용화·유출키 거부) (b)isolation_effective=(forced>0 AND not unknown AND not bypasses), forced==0→경고 (c)resolve_site_membership node= 실사용(중복쿼리 제거) 또는 YAGNI제거 (d)_site_token_ctx sentinel로 해촉토큰 2회쿼리 제거 (e)_SUPERADMIN/_DEVELOPER_ROLES 공용모듈 SSOT·my_sites 헬퍼경유·site_auth dead 제거 (f)scalar_one_or_none→first()+우선순위(복수역할 500 방지) (g)forced_policyless 다중사유 경고.

### #1 iter-3 재기획(코드-실링): (a)★X-Site-Token 경로 멤버십 1회 재검증 또는 jti revocation(해촉 즉시무효, 8h 권한지연 제거) (b)rls_status에 connecting role rolbypassrls 플래그(forced=true+bypassrls=true=격리미실효 경고, false assurance 제거) (c)마이그 downgrade에 DROP POLICY IF EXISTS(런타임 disable과 정합) (d)sales_crypto 폴백키 prod fail-fast (e)verify() dead code 배선 또는 제거. Defer P2: org subtree DB정책. 이후 #1 종료(잔여=FORCE실효/풀러=deploy-pending)→#3.

### #1 iter-2 재기획(★FORCE 범위 안전화 우선)
P0: (a)마이그레이션·부트스트랩 FORCE를 **정책 보유 테이블에만**(site_id보유+sales_org_nodes), 정책0 테이블은 FORCE 미적용→앱 브릭 landmine 제거. 부트스트랩↔마이그레이션 적용범위 1:1 + 정합 회귀테스트 (b)sales_org_nodes p_org를 RESTRICTIVE 또는 USING에 site_id 스코프 추가(광역분기 현장격리). P1: (c)중간 commit sales 엔드포인트에 _apply_session_ctx 재주입 일원화(after_commit/SalesCtx.reapply) (d)sales_ctx에 deleted_at.is_(None) 추가(멤버십 일원화). Defer(backlog): org subtree 정책(업무테이블 path<@ RESTRICTIVE)·현장토큰 revocation(버전클레임)=P2.

### iter-7 재기획(#10 최종, 보안+배선 마감 → 코드실링)
1. ★[보안HIGH] views.py projection_summary(:258)·projection_accounting_rollup(:284)에 require_role('GM_DIRECTOR','SUBAGENCY','AGENCY','DEVELOPER','SUPERADMIN') 배선(형제 actions.py 일치)+영업직/viewer 403 회귀테스트(권한상승 차단) 2. [완성도HIGH] reconciliation(balanced/discrepancies/schedule_missing_for_signed/paid_exceeds) 프론트 배선: Detail/Rollup 타입+드릴다운/배너 렌더, consolidated에 reconcile_failed_count 전파 3. [완성도] docstring/note tol·None/False 동작 갱신(드리프트) 4. [아키] stage IN 확장이 투기적(contract.stage는 RESERVED/SIGNED/CANCELLED만, MIDDLE/BALANCE는 installment kind 혼동)→SIGNED 복원 또는 SSOT 상수공유. 개선시 반영 후 #10 종료(잔여=K-IFRS deploy-pending)→#1.

### iter-5 재기획(#10, 회귀수정+갭마감 — correctness 게이트 돌파)
1. _YM_RE `$`→`\Z`(또는 re.fullmatch): 개행 우회 차단, POST varchar(7) 22001 누출도 진입전 400 2. reconcile 허용오차 밴드(abs(delta)≤max(회차수,eps) 반올림잔차 흡수)+약정ratio합≠1 별도규칙(schedule_ratio_invalid)으로 '계약결함'vs'반올림' 구분 3. 독립대사 SIGNED 범위 한정(revenue/scheduled/paid 정렬, 미서명ACTIVE 거짓불일치 제거) 4. 롤업 consolidated complete/failed_count/partial 플래그+프론트 RollupSite에 status=ERROR/error_code/correlation_id/site_status 소비(dead output 해소) 5. compute_payroll graceful 폴백(읽기경로 DDL 완전강등) 또는 쓰기게이트 실패 rollback+400매핑 6. 순수로직 단위테스트(_validate_ym 개행·_classify_error·discrepancies 반올림/범위·_month_bounds, 게이트플래그 fixture reset). 개선시 반영 후 #10 코드실링→#1.

### iter-4 재기획(#10, 코드-실링 ~8.0 목표 — 코드수정 가능분만)
1. 읽기경로 _ensure_acct/_ensure_wage DDL 강등(쓰기경로+startup 1회로 한정, 매 읽기 advisory-lock+commit 제거) 2. GET /payroll(payroll_compute) ym 비정규→500 누출을 400 가드(POST와 통일) 3. reconcile_ok 항상-참(max정의 항등식) → '대수항등식(불일치미탐)' 명시 또는 독립대사 4. 롤업 errors 원문 str(e)→분류코드+상관ID 마스킹 5. K-IFRS 발생주의 계약총액즉시인식=과대계상 note 강화(진행기준 정밀화는 deploy-pending). 이후 #10은 correctness 게이트(K-IFRS·독립대사)가 deploy-pending 지배 → 코드실링 도달 시 #1로 이동.

### iter-3 재기획(#10, replan — 워크트리 누적 변경 위에 보강)
1. 손익 2뷰 **프론트 배선**: DeveloperProjection.tsx(RollupSite/Rollup/Detail 타입+렌더)에 cash_flow/accrual/deferred_revenue 3지표+발생주의 과대계상 경고배지, views.py projection_accounting_rollup·accounting/summary 2뷰 확장
2. **Alembic 단일 head 실수렴**: 잔존 5head(015/019/021/022/032) merge 리비전(033) 또는 down_revision 확장 + 누락3건(010_v49/018_v53/018_v57) 트리복구 + 032 docstring 허위 정정
3. projection_accounting_rollup 현장별 try/except 부분내결함(한 현장 오류가 전사 롤업 500 방지, 은폐금지 유지)
4. ym 형식검증(YYYY-MM 정규식, 2026-13/2026-6 reject→400, 멱등키 우회 차단)
5. deferred_revenue 정밀화(실수납−인식매출/recognition_pending)
6. ruff 정리(미사용 timezone·E501·I001)

### iter-3 구현결과(#10, executor)
변경: console.py / views.py(projection_accounting_rollup) / actions.py(payroll_post·accounting/summary) / DeveloperProjection.tsx / 032 docstring. 신규: 없음(033 불필요 판정).
1. **2뷰 프론트 배선 완료**: DeveloperProjection.tsx에 CashFlow/Accrual/RollupConsolidated/RollupError 인터페이스+`ProfitTriView`(현금흐름/발생주의/선수금/미수금 4지표+발생주의>현금흐름&미수금>0 시 과대계상 경고배지) 신규. 통합회계 섹션·현장 드릴다운 양쪽 렌더. views.py 롤업이 cash_collected/cash_profit/deferred_revenue/receivable 합산. accounting/summary가 cash_flow/accrual/deferred_revenue 반환. profit_estimate 키 유지(무회귀).
2. **Alembic 정정(★허위→사실)**: 정적 그래프분석(ast 파싱) 결과 — 032 포함 시 **head=1(032), 누락참조 0, 사이클 0**. 032 제외 시 head=2(031_analysis_ledger·v62_7_learning_examples). 즉 기존 보고 "5head·누락3건"은 stale 오진단이고 032 docstring "단일 head 정상화"는 **사실**이었다. 누락처럼 보인 010_v49_phase2·018_v53_contract_generation·018_v57_completion은 모두 실존 revision id(파일명접두어≠revision id). → **033 신설 안 함**(만들면 헤드 재분기). 032 docstring에 검증사실·033불필요 명시.
3. **부분내결함 완료**: 롤업 루프 현장별 try/except — 실패 현장은 rollback 후 errors[]+sites[].error 표기·로깅, 나머지 정상 합산(500 방지·은폐금지). 프론트 errors 배너.
4. **ym 검증 완료**: console `_validate_ym`(정규식 ^\d{4}-(0[1-9]|1[0-2])$) 신규 — `_month_bounds`·`add_accounting_entry`(ym경로)·actions `payroll_post`에서 호출. 2026-13/2026/06/2026-6/공백 → ValueError→400. 멱등키 우회 차단.
5. **deferred_revenue 정밀화 완료**: 단순 등치(=cash_collected) 제거 → 미수금=max(인식매출−실수납,0)·선수금=max(실수납−인식매출,0). accrual.receivable+reconciliation(검산 항등식 revenue==cash−deferred+receivable, balanced 플래그) 추가. 출처상이 note 보강.
6. **ruff 완료**: console.py·032 **All checks passed**(timezone F401 제거·UTC정렬 I001·E501 6건 래핑·SIM105 contextlib.suppress). actions.py 클린. views.py 신규 0(잔존 13건=전부 pre-existing E702/I001/F401, 미수정 영역).

검증: 4 .py py_compile OK. console ruff clean. _validate_ym/_month_bounds 라이브 스모크(정상3통과·비정규8차단). reconciliation 항등식 6케이스 정합. views/actions 모듈 import OK. TSX는 main워크트리 tsconfig로 단일파일 tsc → 오류0(복원검증). **deploy-pending**: 라이브 DB E2E(롤업 errors 실발생·2뷰 실수치·032 upgrade head 실행)·프론트 빌드/배포는 샌드박스 제약으로 미수행.
제거한 안티패턴: silent-fail 0(신규)·미배선 0(2뷰 화면연결 완료)·DDL race(advisory-lock 기존유지)·docstring 허위(2번 사실확인·정정).

---
## 진행 현황 요약 (2026-06-19 갱신)
| # | 서브시스템 | 전 | 후 | critical/high | 커밋 | 비고 |
|--|--|:--:|:--:|:--:|--|--|
| 10 | 회계 통합콘솔 | 5.8 | 7.5 | 0 | 3cadfed2 등 3 | 7 iter. 잔여 9.5갭=K-IFRS 진행기준(deploy-pending) |
| 1 | RLS 보안 | 6.8 | 8.5 | 0 | 9a84254a 등 4 | 6 iter. security·correctness 9.0. 잔여=ux진단화면·라이브RLS(deploy-pending) |
| 3 | 수수료·원천징수 | 6.2 | 8.0 | 0 | 22092bd8 등 3 | 8 iter. 머니패스 다중버그 마감. backlog=build 가드·income_type collapse·TOTAL_POOL |
| 4 | 수납·대출·보증 | 6.5 | (진행) | | | overdue_calc/대출상환 미배선 |

**큐**: #4 → #5(조직도 5.8) → #7(계약CRM 6.8) → #2(워크스페이스 7.8) → #8(분양가 7.1) → #9(해촉외 7.2) → #6(세대 8.1)
**효율정책**: 각 서브시스템 critical/high 0까지 2-3 iter 수렴 후 IMPROVED 커밋·이동, medium/low는 backlog 정직표기, 라이브검증은 deploy-pending. **검증 통과(IMPROVED↑)분만 커밋·푸시**(main 직푸시X·머지=통합자).
**누적**: 커밋 10건, 위험/무진전 22회 차단(앱브릭·권한상승·false assurance·머니패스 누수·반쪽출하 등).

| 4 | 수납·대출·보증 | 6.5 | 7.0 | 0(잔여 deploy-pending) | 472bea55 | 5 iter(스파이럴→교정탈출). overdue/repay/allocations/프론트 배선. backlog=savepoint flush 의미론(실DB) |
**4개 완료**: #10(7.5)·#1(8.5)·#3(8.0)·#4(7.0). 다음 #5(조직 5.8)→#7→#2→#8→#9→#6. 커밋 11건.

| 5 | 조직도·직원 | 5.8 | 8.0 | 0 | (커밋대기) | 7 iter. IDOR전수봉합(create_node·move_subtree·descendants·ancestors_path site_id+deleted_at)·사이클가드·fail-closed authz(DIRECTOR키+키셋패리티)·잠복500수정(sum(e.amount)→base_amount)·DDL SSOT(sales_market_ddl+036)·라벨SSOT(DIRECTOR 트리=로스터 정합)·프론트 silent-fail제거·advisory-lock TOCTOU. 49백+9프론트 테스트 |

**#5 종료 backlog(MEDIUM/LOW 이연)**: ①commission_gross status필터(market.py:845 REVERSED 환수분 gross 과대표시 — settle_summary status='SPLIT' 규약과 미배선, WHERE status IN('PENDING','SPLIT') 추가) ②move_subtree 직급위계검증(TEAM_LEADER→AGENCY 단계건너뛰기 이동 가능, 위계단조성+422) ③move_subtree node.path stale refresh ④no-op 이동 early-return ⑤StaffOverviewPanel .catch status분류(OrgTree와 정직성 비대칭) ⑥advisory-lock 키 중앙레지스트리 ⑦라벨 codegen SSOT ⑧staff_overview N+1 동일엔진 세마포어 병렬화. ★전부 deploy-pending(라이브 PG·ltree UPDATE·036마이그·vitest·tsc·동시성).
**5개 완료**: #10(7.5)·#1(8.5)·#3(8.0)·#4(7.0)·#5(8.0). 다음 #7(6.8)→#2(7.8)→#8(7.1)→#9(7.2)→#6(8.1).

| 7 | 계약·CRM·광고·청약 | 6.8 | 8.0 | 0 | (커밋대기) | 7 iter. 계약 상태머신 멱등·FOR UPDATE·split_commission 멱등가드+DB백스톱(수수료2배 차단)·청약 추첨결정론·FCFS race·promote_reserve FORFEITED 라이프사이클·IDOR 전수스윕 9경로(run_draw·inventory_txn 교차테넌트write·claim·create·sign·cancel·promote)·HOLD 토큰 소유권(점유탈취 차단)·NotFoundError 예외클래스·CRM silent-fail/reason_code 배선·역할 3집합·54테스트 |

**#7 종료 backlog(MEDIUM/LOW 이연)**: ①create_contract 만료 owner-HOLD 분기 순서(만료-우선 재배치=타직원 재선점 허용, 현재 fail-closed 오차단 — 즉시·무배포 수정) ②expire_holds dead-code(미스케줄+SalesUnitHold만 보고 inventory.held_by 미정리) 실배선 또는 lazy-expire 런타임보장+주석교정 ③claim_offer 서비스계층 customer IDOR 검증 대칭화(현재 엔드포인트만) ④draw 계약경로 ValueError→404 SSOT ⑤NotFoundError 공용 중립모듈 승격(청약→계약 방향결합 해소) ⑥desk_inv 역할게이트 ⑦member_node_id 현장검증 ⑧cancel_contract VOID필터·_set_unit_status DRY·sales_message_log 마이그·MhInventoryTxn site_id·VOID writer. ★전부 deploy-pending(라이브 PG 동시성·037 인덱스 23505강제·실발송 kakaoapi.example치환·tsc).
**6개 완료**: #10(7.5)·#1(8.5)·#3(8.0)·#4(7.0)·#5(8.0)·#7(8.0). 다음 #2(7.8)→#8(7.1)→#9(7.2)→#6(8.1).

| 2 | 워크스페이스·내비·PWA | 7.8 | 8.3 | 0 | (커밋대기) | 7 iter. WS 현장격리(4401/4403/4429 인증/인가)·★accept-then-close 전송계층 버그수정(pre-accept close→uvicorn 1006변환→프론트 분기 미발화, starlette TestClient 통합테스트로 검증)·연결단 throttle+슬라이딩윈도 rate-limit·RLS ctx 주입(silent-DoS)·유령소켓 finally·메모리누수·공용 _ws_hardening 추출 전역스윕(channel+social)·onAuthError 종단배선·self-heal·sw.js no-store. 41 백+vitest6 |

**#2 종료 backlog(MEDIUM/LOW 이연)**: ①social room_users write-only vestigial(broadcast는 DB _member_ids fan-out이라 도청불가하나 disconnect 미prune 느린 증식)→subscribe/room_users 제거+SUBSCRIBE 화이트리스트서 제외(채널과 일치) ②sw.js X-PropAI-Stale 헤더 소비처 0(dead-wire)→network-first 화면 배지 배선 또는 헤더 제거 ③_authorize_site_channel 광범위 except가 DB일시장애와 비멤버를 동일 4403→인프라장애는 4429(백오프)/비멤버만 4403 분기 ④멀티워커 Redis 전역 throttle ⑤units_live held_by WS 마스킹 ⑥_conn_log LRU캡 ⑦siteCode prop 명명·socialWs onAuthError. ★deploy-pending(라이브 DB 인가·실브라우저 CloseEvent·tsc·sw런타임·멀티워커).
**7개 완료**: #10(7.5)·#1(8.5)·#3(8.0)·#4(7.0)·#5(8.0)·#7(8.0)·#2(8.3). 다음 #8(7.1)→#9(7.2)→#6(8.1).

| 8 | 적정분양가·매출역산·원가 | 7.1 | 8.3 | 0 | (커밋대기) | 7 iter. Decimal 머니패스 정합·decompose 잔차흡수 4중가드(음수/과배분/팽창/상대편차, 회계전파차단)·매출역산 gap 원기반(floor편향 제거)·멱등 콘텐츠해시(상수붕괴·값정정 복리 차단)·멤버레벨 복리 3겹봉합(_load_group_map dedup+039 UNIQUE+SAVEPOINT graceful)·3경로 공용헬퍼 패리티(_load_group_map/_clamp_price)·warning 종단배선·OVERRIDE value<=0 가드·정직강등(unavailable)·라우터400·engine ruff청소. 88 백+19 인접 |

**#8 종료 backlog(MEDIUM/LOW 이연)**: ①CAP 모드 CUSTOM 제외→ΣRATE<1 왜곡가드 영구 false-positive 잠복(provision.py GENERAL 하드코딩이라 현재 unreachable, CAP 활성시 분기 필요) ②멱등키 클라키(cli:)/자동(auto:) 혼용시 별도그룹 복리(규약주석 의존→by-construction화: 콘텐츠해시 꼬리 1차조회 dedup) ③멤버/그룹 UNIQUE가 마이그038/039만·ORM __table_args__ 미선언(create_all 부트스트랩 SSOT 이원화) ④흡수취소 합계 원장 종단전파 게이트 ⑤reconciles_won 구성정의(전부FIXED) 한정 ⑥gap banker's→HALF_UP ⑦PricingWarningBanner 공용컴포넌트 ⑧PricingConfigPanel regenerate try/catch. ★deploy-pending(라이브 MOLIT 실거래·DB round-trip·038/039 인덱스 alembic·동시성 23505·tsc).
**8개 완료**: #10(7.5)·#1(8.5)·#3(8.0)·#4(7.0)·#5(8.0)·#7(8.0)·#2(8.3)·#8(8.3). 다음 #9(7.2)→#6(8.1).

| 9 | 해촉·전매·MH·옵션·추천·소셜·구인 | 7.2 | 7.5 | 0 | (커밋대기) | 2 iter. 전매 IDOR 봉합(_load_contract_scoped)·decide with_for_update 이중명의변경 차단·TOCTOU 2겹(040 부분유니크 WHERE decided_at IS NULL/status=PENDING + SAVEPOINT IntegrityError 재조회)·submit_realtx 종결가드(report_no 소실차단)·transfer_type 노출(과대매칭 해소)·resale_decide 응답계약 배선·해촉증명서 RRN 마스킹·SSRF allowlist(is_global, CGNAT/예약/링크로컬 차단)·발송 silent-fail 분류로깅·notify 로더 graceful. 33테스트 |

**#9 종료 backlog(MEDIUM/LOW 이연)**: ①realtx_report/submit_realtx 엔드포인트 {ok:True} 절반배선→resale_decide처럼 응답 SSOT 대칭+ResalePanel.report() 분기(중복/제출됨 표기, 현재 항상 성공토스트) ②submit_realtx status!=PENDING 무조건멱등→상태전이 매트릭스(PENDING→SUBMITTED→ACCEPTED/CORRECTED 허용·report_no None 재제출만 차단) ③SSRF DNS-rebinding IP pin(검사IP를 connect 대상 고정) ④알림톡 kakaoapi.example 플레이스홀더 ⑤resale_request 권한(sales_ctx→require_role 정책결정) ⑥is_blocked_ip 멀티캐스트 주석정정. ★deploy-pending(040 인덱스 alembic·라이브 23505·decide 동시승인·실 FCM/알림톡·tsc).
**9개 완료**: #10(7.5)·#1(8.5)·#3(8.0)·#4(7.0)·#5(8.0)·#7(8.0)·#2(8.3)·#8(8.3)·#9(7.5). 마지막 #6(8.1).
