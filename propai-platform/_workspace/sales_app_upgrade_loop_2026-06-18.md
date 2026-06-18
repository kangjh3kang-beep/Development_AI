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
