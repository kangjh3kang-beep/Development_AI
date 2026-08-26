# 계획 — 성장 인사이트 정리(승계분 닫기)

> 기준 커밋 `efc19a9b` · 전제 측정 **2026-08-26 16:0x~16:4xZ · 활성 컨테이너** · 브랜치 `fix/growth-insight-retention`

## 0. 옵시디언·보드 조회 결과 (계획 게이트 §0)

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **없음** |
| **확정된 처방 순서** | 보드 2026-08-26 16:42: `0.페이지 계약(#854)` → `1.하한 withheld(#861) + content_hash 무변화 단락` → … **이 PR 은 1단계 뒤 절반 자리인데, 그 처방이 실측으로 틀렸다**(§1 P1) |
| **같은 클래스의 앞선 결함** | `latency_baseline` 이 **2,059건 쌓여 조치 대상을 가린 전례**(`insight_types.py` 주석 · 2026-08-23). 같은 병이 재발했다 |
| **저장소가 이미 가진 것** | 카탈로그 SSOT `insight_types.py`(스윕 락 있음) · `row_number() PARTITION BY` 선례(`analysis_ledger_service:194-213`) · growth 의 **celery beat 관행**(잡 7개) |

## 1. 전제 표 — 측정 방법과 **실제 값**

| # | 전제 | 확인 방법 | 결과(관측) |
|---|---|---|---|
| **P1** | ★보드: *"`content_hash` 무변화 단락이 소음 본체를 유입에서 끊는다"* | 24h 창에서 타입별 `count(*)` vs `count(DISTINCT 내용)` | **거짓.** `latency_regression` 유입 **24건** · **중복 0건(0%)**. **대조군**: 다른 타입도 전부 중복 0. **끊을 것이 없다** |
| P2 | 그럼 본체는 무엇인가 | `status` 분포 · 나이 분포 | **닫히지 않는 재고.** `open` **3,127** / `acknowledged` **16** / `expired`·`superseded` **0**. `latency_regression` 2,298 중 **30일 초과 1,212** |
| P3 | 승계분의 크기 | `row_number() PARTITION BY (type, 정체필드)` | **전 타입 승계 2,678** → 정리 시 `open` **3,127 → 449 (86% 감소)** |
| P4 | 타입별 **정체 필드** | 라이브 `metrics_json` 키 분포 + 유일성 | `latency_regression/baseline`=`key` · `error_cluster`=**`signature`** · `fallback_rate`/`quality_drop`/`recurring_verify_error`=`service` · `selection_contamination`=`verdict` |
| P5 | `status` 에 제약이 있나 | `schema_guard` DDL | `varchar(20)` **무제약** → `superseded` 저장 가능 |
| P6 | 사람 전이와 충돌하나 | `ack_insight` 직독 | 허용 전이는 `open|acknowledged → acknowledged|dismissed`. `superseded` 는 그 밖이라 **사람이 재처리 불가** — **의도한 동작**(승계된 행은 더 새 행이 대신 말한다) |
| P7 | celery 신규 도입인가 | `celery_app.py` beat 직독 | **아니다.** growth 는 이미 celery beat 로 돈다(잡 7개). 기존 관행 사용 |
| P8 | 파이썬 기준선 | CI 동일 명령 | 68 failed / 10,418 passed / 14 errors |

### ★P1 이 이 PR 의 방향을 바꿨다

보드의 처방(`content_hash`)을 그대로 구현했으면 **아무것도 줄지 않았을 것**이다.
인계된 진단은 **작성 시점의 사실**이고, 유입 양상은 그 뒤 바뀌었다.

### ★내 프로브가 한 번 과소계상했다

`error_cluster` 를 `key` 로 물었는데 실제 정체는 `signature` 였다 — 112행(고유 12)이
**승계 0** 으로 나왔다. **손으로 고른 키가 상한이 된 것**이고 내가 저질렀다.
그래서 정체 필드를 **코드 SSOT 에 선언**하고 카탈로그 전수 대조로 잠갔다.

## 2. 변경 내용

1. `insight_types.IDENTITY_FIELD` — 타입 → 정체 필드. **`None` 은 "정리하지 않는다"는 명시 선언**이다(누락과 구별).
2. `growth/insight_retention.supersede_stale_insights` — 키별 최신 1건을 남기고 나머지 `open` 을 `superseded` 로 **전이**(삭제 아님).
3. `growth_tasks.cleanup_insights` + beat `03:10`(분석 `02:30` **이후**).

**회귀가 아닌 근거**: 신규 상태값은 `status` 필터를 쓰는 화면에서 자동으로 빠진다.
`actionable_counts`·`total` 모두 `status` 술어를 타므로 정리 즉시 반영된다.

## 3. ★검증하지 못한 것

1. **실제 Postgres 문법·성능** — 락은 SQL 을 해석하는 **가짜 DB** 다. `row_number()` 는 파이썬으로 흉내 냈다.
2. **beat 가 실제로 발화하는지** — 스케줄 **등록**만 소스로 잠갔다. 배포 후 로그로 확인해야 한다(§5).
3. **`superseded` 를 읽는 화면이 없다** — 사용자는 사라진 것으로만 본다. *"승계돼 닫혔다"* 를 보여 주는 표면은 **미구현**.
4. **정체 필드의 정확성은 라이브 표본 기반**이다. 필드가 없는 행(`metrics_json ? :field` 불충족)은 **손대지 않는다**(안전 기본값)이지만, 그런 행이 얼마나 되는지는 타입별로 **미측정**.
5. **되돌리기 경로가 UI 에 없다** — 잘못 닫으면 SQL 로 되돌려야 한다.

## 4. 되돌리기 경로

```sql
UPDATE platform_insights SET status='open' WHERE status='superseded';
```
행을 지우지 않으므로 **완전 가역**이다. beat 항목 1줄을 빼면 수집도 멈춘다.

## 5. 잠금

`tests/test_growth_insight_retention.py` — **두 모집단**(승계 있음/없음이 **다른 결과**) ·
`acknowledged` 불가침 · `None` 선언 타입 무접촉 · **멱등**(2회차 0건) · `limit` 상한 ·
`dry_run` 무쓰기 · **빈 카탈로그는 시끄럽게 실패** · **카탈로그 전수 대조**(새 타입이 빠지면 실패) ·
beat 등록을 **ast 로**(양성 대조군 포함).

★배포 후 라이브 프로브:
```sql
SELECT status, count(*) FROM platform_insights GROUP BY 1;   -- superseded 가 생겼는가
```
```
docker logs propai-celery-worker | grep 'growth 정리'         -- 0건일 때도 나와야 한다
```
