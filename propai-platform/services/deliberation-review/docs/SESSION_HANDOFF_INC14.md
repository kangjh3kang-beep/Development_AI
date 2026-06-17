# 세션 인수인계 — INC-14 (reconcile_mirror 완결)

> 작성: 2026-06-18 세션 종료 시점. INC-10·11·12·13·15 완료 후 **INC-14만 잔여**(P-데이터 마지막 무거운 항목).
> 무거운 작업(LiveNetwork 실구현·broker·async)이라 깨끗한 컨텍스트에서 시작하려 인수인계함.

## 0. 먼저 읽을 것
- 메모리 `[[simui-review-engine]]`(엔진 전체 상태), `[[bash-tool-vs-wsl-filesystem]]`(⚠️도구/경로), `[[respond-in-korean]]`.
- `docs/MULTIMODAL_UPGRADE_ROADMAP.md`(INC 시리즈 — INC-14 섹션), `docs/EXECUTION_LOG.md`(INC-10~15 기록).

## 1. 현재 상태(검증된 사실)
- **정본 워크트리(WSL)**: `~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review`
  (브랜치 `feature/deliberation-review`). UNC=`\\wsl.localhost\Ubuntu\home\kangjh3kang\My_Projects\Development_AI_deliberation\propai-platform\services\deliberation-review`.
- **HEAD `af0bb77f`**(INC-15). 직전: 02df218c(13)·cc377cc1(12)·2433711f(11)·2bac55e4(10).
- **alembic head `0014_mirror_snapshot_uniq`**. **테스트 396 passed**, ruff clean, static_scan 0.
- ⚠️ 정본 워크트리엔 `.venv` 없음 → 파이썬/pytest = `~/My_Projects/propai-review/.venv/bin/python`.

## 2. 환경/도구(⚠️ 이 세션에서 PowerShell 도구가 다운됐었음)
- WSL 명령/테스트: **Bash 도구 → `wsl.exe -e bash -lc '...'`** (PowerShell 도구 죽어도 동작, 진짜 WSL FS 도달).
  - 예: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest -q'`
- 파일 R/W: **Read/Edit/Write + UNC 경로**(위 §1).
- 전체 테스트: 위 venv로 `python -m pytest -q`(cwd=정본). 마이그레이션: `~/My_Projects/propai-review/.venv/bin/alembic -c apps/api/alembic.ini upgrade head`(cwd=정본).
- 커밋: `cat > /tmp/msg.txt <<"EOF" … EOF` (한 wsl 호출 내 heredoc) → `git -C <repo> commit -F /tmp/msg.txt`. repo 루트=`Development_AI_deliberation`(propai-platform은 하위), 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **푸시 경로**: repo 루트 `~/My_Projects/Development_AI_deliberation`, **origin = `git@github.com:kangjh3kang-beep/Development_AI.git`(SSH)**, 추적 브랜치 `origin/feature/deliberation-review`. 명령=`git -C ~/My_Projects/Development_AI_deliberation push origin feature/deliberation-review`.
  - ⚠️ **SSH로만 push**(gh 인증계정=kangjh3kang-beep; gh 토큰에 workflow scope 없어 **https push는 `.github/workflows/ci.yml` 거부**됨 — origin이 이미 SSH라 그대로 push). 
  - **푸시는 사용자 확인 후**(이 시리즈는 로컬 커밋 우선 정책).
  - 🔴 **현재 미푸시(로컬 전용) 6커밋**: `2bac55e4`(INC-10)·`2433711f`(INC-11)·`cc377cc1`(INC-12)·`02df218c`(INC-13)·`af0bb77f`(INC-15)·`078cdcd9`(핸드오프) — origin보다 6 ahead. 새 세션/사용자가 승인 시 push 필요.

## 3. INC-14 스펙 [high/L]
**reconcile_mirror 완결(라이브 diff→미러 갱신→영향 finding 재분석).**

현재 코드 상태:
- `apps/api/app/tasks/reconcile_tasks.py` — `reconcile_mirror(citation_ref)`가 **bool 스텁**: `LiveNetwork().get(...)`로 live_ok만 반환(실 diff/갱신/재분석 미배선).
- `apps/api/app/adapters/network.py` — `LiveNetwork.get(url)`이 **항상 NetworkError**(mock). 공급측 전용 choke point(소비경로는 import 금지 — `test_consume_static`가 강제).
- 미러 영속·조회는 **INC-13 완료분 재사용**: `app/supply/mirror/mirror_store.py`의 `write_snapshot_to_db`(원자 on_conflict, 0014 유니크)·`load_active_snapshot_from_db`. 분석 재실행 트리거는 `app/tasks/analysis_tasks.py:analyze_task.delay`.

해야 할 일(roadmap):
1. **LiveNetwork.get에 공급측 한정 실 httpx 주입** — mock 기본 유지, 설정(env/flag, 예: `LIVE_NETWORK=on`) 시 실 httpx GET. 소비경로 미사용 불변(INV-13) 유지(test_consume_static·INC-15 live_call_scan 그린 유지).
2. **라이브 본문 vs mirror content_hash diff** — ⚠️ `MirrorSnapshotModel`엔 현재 **content_hash 컬럼 없음**(rules/active_candidate_ids만). 설계 결정 필요: (a) mirror_snapshot에 content_hash 컬럼 추가(신규 alembic 0015) 또는 (b) rules에서 결정론 해시 파생. (a) 권장(명시적·재현성).
3. **불일치 시 새 snapshot append**(write_snapshot_to_db, 새 snapshot_id — 기존 불변·재현성 보존, INC-13 멱등 활용).
4. **영향 finding 재분석 트리거** — `analyze_task.delay(payload)`. 영향 분석 조회(어느 analysis_run이 이 citation/jurisdiction을 썼나)는 analysis_run 테이블 조회 필요(설계).
5. **broker** — 실 Celery redis(주기 잡). dev eager 폴백 유지.

## 4. 불변식(반드시 보존)
- **INV-13**: 라이브는 reconcile(공급측)에서만. 소비경로(run_analysis·warm)는 라이브 0 — INC-15 `tools/live_call_scan.py` + `test_consume_static`로 강제됨(깨지면 AT 실패).
- 미러 갱신=새 snapshot **append**(기존 snapshot 불변, MirrorSnapshot frozen). content_hash 전후 보존(설명가능성).
- 재분석=동일입력 재실행(결정론, run_analysis 순수).
- **무음0**: reconcile 실패/비활성은 표면화(결손 은폐 금지). emit(INV-23) 등 기존 강제 유지.

## 5. 이 시리즈에서 확립된 패턴(재사용)
- **sync/async 경계**: 소비측 sync(run_analysis) ↔ async DB는 **warm-at-route**로 해소(INC-11/13). Celery sync 태스크에서 async DB 필요 시 **일회용 NullPool 엔진**(`create_async_engine(url, poolclass=NullPool)` + `await eng.dispose()` in finally) — ⚠️ 글로벌 엔진을 새 asyncio.run 루프서 재사용하면 'Event loop is closed' 무음 실패(INC-13 리뷰 HIGH 결함). `tasks/supply_tasks.py:_persist_documents_best_effort` 참고.
- **DB upsert 멱등**: postgres `insert(M).on_conflict_do_nothing/do_update`(유니크 제약 위). best-effort 영속 실패는 **로깅**(무음0).
- **검증 게이트(완결 필수)**: 구현→**전체 pytest green + ruff + static_scan 0**→**적대적 다관점 리뷰(Workflow, gate ≥4.5)**→확인 결함 해소→커밋→docs(roadmap ✅/EXECUTION_LOG)·memory 갱신. 무거운 증분은 3-lens 워크플로(determinism/persist/quality + verify), 가벼운 건 단일 집중 리뷰(비례).
- 테스트 격리: conftest autouse가 source_cache/vision_cache clear, 키 없음 격리. DB 테스트는 `db` 픽스처(`await engine.dispose()`로 교차루프 풀 초기화) + 고유 식별자 + cleanup.

## 6. 착수 순서(권장)
1. 메모리·로드맵 INC-14·본 문서 읽기 → 현 상태 git/test로 재확인(396 passed).
2. reconcile_tasks.py·network.py·mirror_store.py(INC-13)·analysis_tasks.py·기존 reconcile/verify 테스트 정독.
3. content_hash 저장 방식 결정(2-(a) 권장 → alembic 0015) → LiveNetwork 실 주입(설정 게이트) → diff→append→재분석 배선.
4. 테스트(diff 감지·새 snapshot append·재분석 트리거·소비경로 라이브0 유지·mock 폴백) → 게이트(§5) → 커밋 → docs/memory.
