# Knowledge Item — 성장루프·플랫폼 감사·아이콘 리팩토링 세션 (2026-06-19 ~ 06-23)

> 대상: PropAI 부동산개발 플랫폼(FastAPI `apps/api` + Next.js `apps/web` 모노레포, 멀티세션 개발).
> 범위: ①분양관리앱 ERP 성장루프 10/10 ②플랫폼 전체 배선·병목 감사 ③이모지→lucide SVG 전수교체.
> 목적: 재사용 가능한 아키텍처 결정·트러블슈팅·모범사례 압축. 세션 일기가 아니라 다음 작업에 바로 적용할 규칙.

---

## 1. 아키텍처 결정사항 (Architecture Decisions)

### AD-1. 성장루프 = 구현 → 완결게이트 → 다층 적대리뷰 → min 하한게이트 판정
- 1 iteration = **구현(executor)** → **완결게이트**(py_compile/ruff/pytest) → **3관점 적대리뷰**(정확성·완성도 / 보안·은폐 / 아키텍처·UX, 별도 리뷰 레인) → **판정**.
- ★종합점수 = 5차원 **각각의 최소값(min 하한게이트)**, 가중평균 아님. 가장 약한 차원 하나가 전체를 끌어내림 → 약점이 가려지지 않는다.
- 판정: PASS(≥9.5) / IMPROVED(>baseline·<9.5) / NOPROGRESS(≤baseline).
- **차원 점수 = 3리뷰의 최소값**(보수적). 9.0+는 "해당 차원 미배선/dead-wire/silent-fail/병목 0"일 때만.

### AD-2. 수렴정책: critical/high 0 + IMPROVED → 커밋, MED/LOW는 backlog
- 서브시스템당 **critical/high 0 + IMPROVED** 도달 시 누적 커밋. MEDIUM/LOW는 backlog·deploy-pending으로 정직 이연.
- ★커밋 기준선 = "직전 iter 점수"가 아니라 **마지막 커밋(미착수면 원본 baseline)**. iter-간 점수 정체는 *더 깊은 리뷰가 선재결함을 계속 발굴*한 측정 아티팩트이지 코드 퇴행이 아님(이 함정에 여러 번 빠질 뻔).
- 금융·상태머신·WS 서브시스템은 6~7 iter 소요(깊은 리뷰가 선재결함 연쇄발굴 = 루프의 가치).

### AD-3. 멀티세션 워크트리 격리 + origin/main 기준 작업
- 브랜치 = 워크트리 1:1. **공유 main 워크트리에서 feature 브랜치 checkout·편집 금지**, main 직접 푸시 금지, 머지/배포 = 통합자 세션.
- ★작업 베이스는 **항상 origin/main**(stale 로컬 main 아님). 신규 작업 전 `git worktree add <DEST> -b <branch> origin/main`.
- 신규 워크트리는 `.venv`/`node_modules` 없음 → 1회 설치 필요(`pnpm install`은 글로벌 스토어 하드링크라 빠름).

### AD-4. 안티패턴 3종 + 1 — 모든 리뷰의 공통 렌즈
- **미배선(반쪽출하)**: 정의됐으나 미연결. 특히 *백엔드만 있고 프론트 소비처 0* (응답키 계산·반환하나 렌더 안 함 = dead-wire).
- **silent-fail**: 예외→0/빈값/패널숨김 은폐. SQLSTATE 분류(`42P01`/`42703`만 정상0, 그외 전파)로 차단.
- **런타임 DDL race**: 매요청 `CREATE TABLE IF NOT EXISTS` → Alembic 정본 + 부팅 1회 게이트 + advisory-lock.
- (+) **dead-channel**: 헤더/필드를 부착·반환하나 소비처 0 (예: `X-PropAI-Stale` 헤더를 sw.js가 붙이는데 프론트가 안 읽음).

### AD-5. 공용화·표준계약(국소패치 금지) — 전역 전파방지
- 버그 수정 시 ①기록 ②**동일패턴 전역 스윕**(공용 헬퍼/표준계약으로 추출, 한 곳 고치면 전역이 따라옴).
- 예: WS 하드닝을 `_ws_hardening.py` 공용모듈로 추출 → channel_ws·social_ws 동시 적용. pricing 3개 자매경로(generate/solve_base/resolve)를 `_load_group_map`·`_clamp_price` 공용헬퍼로 by-construction 패리티.

### AD-6. 아이콘 = lucide-react (인라인 SVG / 무라이브러리 대비)
- 플랫폼에 아이콘 라이브러리 부재(인라인 SVG 관례만) → **lucide-react 도입**(트리셰이킹·표준·구신 별칭 모두 export).
- config 객체의 이모지 `icon: string`은 **`string | LucideIcon` 하위호환 위젯닝**(렌더 `typeof === 'string'` 분기) → 기존 string 소비처 무회귀 + 신규 컴포넌트 아이콘 가능. 모든 렌더 사이트에 가드 적용 필수(놓치면 빌드 타입에러).

### AD-7. 다중 에이전트 오케스트레이션(Workflow) = map → verify → synthesize
- 대규모 감사/리뷰: 차원별 병렬 매핑 → **critical/high 적대검증**(코드 직접확인, 오탐·과장 강등) → min 하한게이트 종합.
- 대량 기계적 리팩토링(이모지 100파일): 디렉토리별 분할 병렬 executor(파일 겹침 0 → 충돌 0) + loop-until-dry 잔여 소진.

---

## 2. 트러블슈팅 내역 (Troubleshooting)

| 증상 | 근본원인 | 해결 |
|---|---|---|
| **반복되는 "스파이럴"**: 수정이 인접버그 유발(strict zip이 미달청약 깸·역할집합 단일상수 과확장·세션스코프 락·decompose 음수전파) | 한 iter의 수선이 인접 로직 회귀 유발 + **내 replan 지시의 과한 일반화**("strict"·"단일상수 통일") | **회귀유발 단일변경만 정밀 revert**(corrective iter), 양질변경 보존. replan은 최소·구체로(일반화 금지) |
| pytest 전체 중단(0 실행) | `test_auction_demock_court`·`test_molit_client` **수집에러**(`parse_detail_html`/`_BASE_PATH` 선재 import 실패)가 collection 단계서 전체 인터럽트 | `--ignore=<broken>` 로 격리 실행(선재 결함, 내 변경 무관) |
| ruff "1916 errors" | CI 미강제로 누적된 **스타일 부채**(UP045 Optional·E501·I001·F401) + **B008(186)=FastAPI `Depends()` 관용구 오탐** | 기능오류 사실상 0. `ruff --fix`(autofix) + B008 per-file-ignore. "에러 수"에 겁먹지 말 것 |
| 빌드 실패(Type error) | 계약 위젯닝(`string|LucideIcon`) 후 **두 번째 렌더 사이트 미가드** | 같은 파일 모든 렌더 사이트에 `typeof` 가드 적용. ★`next build`는 컴파일 성공 후 type-check서 막힘 — "Compiled successfully" ≠ 빌드성공 |
| WS 인증 UX 전부 무동작(브라우저) | **close-before-accept**: `ws.close(4401)`을 `accept()` 전 호출 → uvicorn이 HTTP 403 업그레이드 거부로 변환(Close 프레임 미전달) → 브라우저 `CloseEvent.code=1006`(커스텀코드 손실). 단위테스트는 `_FakeWS`에 코드 직접주입해 **거짓통과** | **accept-then-close**(throttle만 pre-accept). **starlette TestClient 통합테스트**로 전송계층 계약 검증(fake 우회 제거) |
| 라이브 잠복 500 | `staleness`/silent-fail 제거가 **선재 잠복버그를 노출**(예 `sum(e.amount)` — 컬럼은 `base_amount`. 과거 42703이 0으로 은폐) | 은폐 제거 + 노출된 결함 동시수정. ORM 컬럼계약 회귀테스트로 드리프트 차단 |
| 멱등 race 미보호(500 누출) | docstring은 "FOR UPDATE 직렬화" 약속하나 코드는 평문 select → 동시 INSERT가 부분유니크 23505 → 미가공 500 | SAVEPOINT(`begin_nested`)+`IntegrityError` graceful 재조회. **세션스코프 `pg_advisory_lock`은 pgbouncer transaction-pooling서 락누수**(commit이 backend 풀반환→finally unlock이 다른 backend) → **트랜잭션스코프 `pg_advisory_xact_lock`**(자동해제) 표준 |
| 멱등키 상수붕괴(복리) | `idem = f"{mode}:그룹"`(상수) → distinct 그룹핑이 묵음병합·값 덮어쓰기 | **콘텐츠해시**(`mode+sorted(unit_ids)`) 멱등키 — 더블클릭만 dedup, distinct 보존 |
| Workflow `args` undefined | args가 JSON 문자열로 주입될 수 있음 | `const S = (typeof args === 'string' ? JSON.parse(args) : args) || {}`. ★resume 시 args 재전달 필수 |
| Workflow Review/Verdict 실패 | 세션 한도(시각 리셋)·`529 Overloaded`·stream idle timeout | ScheduleWakeup backoff(270s 캐시창/1800s) 후 `resumeFromRunId`로 재개(캐시된 Implement 재사용) |
| 화면에 수정 미반영("아직 🤖") | 변경이 **미머지 feature 브랜치**에만 존재. 라이브·dev는 main 기반 | "코드는 고쳐졌으나 머지·배포 미반영" — origin/main에 grep해 확정. 머지/배포 게이트 안내 |
| 리베이스 충돌(54커밋 전진) | 다른 세션이 같은 프론트 파일 동시편집(이모지파일 인기) | 리베이스 후 충돌 **양쪽 보존 병합**(다른세션 변경 + 내 아이콘). 병합으로 **새로 딸려온 이모지**도 재스캔·변환 |

---

## 3. 모범 사례 (Best Practices)

### BP-1. 검증은 리뷰어 주장을 코드로 재확인
- 적대리뷰가 과대진단할 수 있음 → verdict 단계가 **코드 직접추적으로 주장 검증**(예 "head=1 실제로 맞음", "_fix_supabase_url은 no-op", "unit_mix SLSQP는 라이브 소비됨"). 거짓신고·과장 강등.

### BP-2. 신규 엔드포인트는 같은 iter에 프론트 배선 필수
- 백엔드만 출하 = 반쪽출하 게이트. GET→POST 분리, 응답키 신설, 계약변경 시 **소비처 동시수정**.

### BP-3. min-gate를 의식한 작업 — 한 번에 게이트 차원 전부
- 두 결함이 서로 다른 차원을 막으면 **둘 다** 고쳐야 IMPROVED(하나만 고치면 다른 차원이 막아 NOPROGRESS 반복).

### BP-4. deploy-pending / backlog 정직표기
- 샌드박스 불가(라이브 DB·동시성·MOLIT·공공API·tsc 일부)는 **deploy-pending**으로 분리. 가짜 통과 위장 금지. 코드평가 가능 부분만 채점.

### BP-5. 2겹 방어(앱+DB)
- 멱등/격리는 ①앱레벨 가드(즉시·코드평가 가능·샌드박스 검증) + ②DB 제약(부분유니크/UNIQUE, 정본·deploy-pending) 병행.

### BP-6. 마이그레이션 헤드 단일성·체이닝
- 신규 Alembic은 **현재 head 확인 후 단일 부모 체이닝**(orphan/멀티헤드 금지). `from alembic import op`를 함수 내부 지연 import하면 alembic 미설치 샌드박스서도 모듈 import 가능(SSOT 단위테스트 가능).

### BP-7. 보존 판단(이모지·기호)
- 교체: UI 아이콘(버튼/탭/제목/배지/배너 leading). 보존: 코드주석·LLM프롬프트·로그·산문 속 이모지·**색범례 사각형(🟩🟫 lucide 등가 없음)**·`<option>` 내부(SVG 자식 불가)·타이포 단색기호(✕✓★). 매핑부재 emoji는 의미상 최근접 lucide 또는 보존+보고.

### BP-8. config 라벨의 이모지는 위젯닝 또는 문자열 스트립
- `icon: "🤖"` config는 (a)타입 `string|LucideIcon` 위젯닝+소비처 렌더 분기, 또는 (b)외부 string prop이면 이모지만 제거(크로스파일 plumbing 회피).

### BP-9. 메모리·SSOT 문서로 진척 영속
- 장기 루프는 SSOT 진행문서(`_workspace/*.md`) + 메모리에 *수렴정책·스파이럴 교훈·진척*을 기록(컨텍스트 압축 생존).

---

## 4. 이번 세션 산출물 요약
- **분양관리앱 ERP 성장루프 10/10 완료**(`feature/sales-app-erp-upgrade`): 평균 6.81→7.9, 전부 critical/high 0. 실버그 발굴 — 수수료 2배배분·교차테넌트 IDOR(전매/FCFS/조직/재고/원장)·fail-open authz(DIRECTOR)·잠복500(sum(e.amount))·해시체인 fork·WS close-before-accept·SSRF(직인fetch)·decompose 음수 회계전파·멱등 상수붕괴 복리.
- **플랫폼 배선·병목 감사**(NEEDS_WORK 5.0, 52발견/25 high): ★로컬 main 143커밋 stale=베이스라인오염, market_ai 가짜데이터 위장, rates 라우터 orphan, NEXT_PUBLIC_API_URL 404, DB풀 이원화, Monte Carlo sync-in-async DoS, 심의/설계엔진 모세혈관 미배선. 권고=재베이스라인 선행→P0 머니패스→인메모리상태 Redis공유(인프라트랙).
- **이모지→lucide SVG 전수교체**(`feat/emoji-to-svg-icons`, origin/main 리베이스 완료·클린 머지가능): ~138건/~100파일, 컬러 UI아이콘 잔여 0. tsc 0·build 136/136. 머지/배포는 통합자.

### 주의(이 세션의 한계)
- 모든 머지/배포는 통합자 세션 몫(main 직접조작 안 함). 위 브랜치들은 푸시까지만.
- 라이브 검증(동시성·실DB·실발송·MOLIT)은 deploy-pending — 정적/순수로직/TestClient로만 검증.
