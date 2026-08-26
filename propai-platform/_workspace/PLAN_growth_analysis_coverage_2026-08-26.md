# 계획 — 성장루프 분석 커버리지 (확정 순서 1단계)

> 기준 커밋 `ccba93b1` · 전제 측정 **2026-08-26 09:00~09:20Z** · 브랜치 `fix/growth-analyzer-withheld`

## 0. 옵시디언·보드 조회 결과 (계획 게이트 §0)

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **없음.** 다만 ★**"A(FALLBACK_MIN_CALLS 완화)를 먼저 하지 마라"** 는 명시적 경고가 있다(보드 · 통합자 진단: n=3 표본이 `threshold_relax` 를 발화시키고 그것이 **실제 프로덕션 HTTP 타임아웃에 곱해진다**). **이 PR 은 하한을 완화하지 않는다 — 하한은 그대로 두고 보류를 말하게만 한다.** |
| **확정된 처방 순서** | 보드 2026-08-26 16:42 통합자 NOTE: `0.페이지 계약(=#854)` → **`1.analyzer 3개 하한을 withheld() 로 배선 + content_hash 무변화 단락`** → `2.C 독립 baseline` → `3.D 절반·A 마지막`. **이 PR 은 1단계의 앞 절반**(content_hash 는 별건으로 분리 — §2-4) |
| **같은 클래스의 앞선 결함** | `site_score_service.GRADE_COVERAGE_FLOOR` — 값 `None` + 사유 문구 + ★**발행했을 때도 `covered/total` 을 싣는다**. 이 PR 은 그 관용을 그대로 옮긴다 |
| **미결·부채** | `metrics_json.analysis_coverage` 소비처 0 (§3-2 · `xfail` 로 표시) |

## 1. 전제 표 — 측정 방법과 **실제 값**

| # | 전제 | 확인 방법 | 결과(관측) |
|---|---|---|---|
| P1 | 하한 3개가 실재한다 | 소스 직독 | **참.** `FALLBACK_MIN_CALLS=10`(:52) · `QUALITY_MIN_SAMPLES=5`(:57) · `LATENCY_MIN_SAMPLES=20`(:68) |
| P2 | 그 보류가 **아무 흔적도 안 남긴다** | 소비처 3곳 직독 | **참.** `:253 return None, 0.0` → 호출부가 `continue` · `:281 return None, metrics` → `continue` · `:702 continue`(행 자체 없음) |
| P3 | ★**"거짓 0%가 발행된다"** | 호출부 직독 | **거짓 — 내 첫 서술이 틀렸다.** `sev is None` 이면 호출부가 `continue` 해 `0.0` 은 **발행되지 않는다.** 진짜 결함은 *"커버리지가 안 보인다"* 다 |
| P4 | latency 보류 규모 | 라이브 SQL(24h · 활성 컨테이너) | **키 825개 중 802개(97%) 보류** · 이벤트 1,243/3,893. **대조군**: 통과 키 3개(tiles 290·260 · store/projects 197) → 조회기 생존 |
| P5 | fallback 보류 규모 | 같은 방법 | **서비스 5개 전부 미달**(permit 3·regulation 1·scenario 1·site_analysis 1·verifier 1) → 인사이트 **0건** |
| P6 | 소음 재고 | 같은 방법 | insights **3,127** · open **3,111** · `latency_regression` **2,308(74%)** |
| P7 | growth 가 `withheld()` 를 쓰는가 | 파생형 grep + 대조군 | **0건.** 대조군: 저장소 전체 소비 파일 **12개** → 조회기 생존 |
| P8 | 0건 실행이 로그를 남기는가 | 소스 직독 | **거짓(결함).** `if insights:` 라 **0건이면 아무 로그도 없다** — 배치 미실행과 구별 불가 |
| P9 | 파이썬 기준선 | CI 동일 명령 | 68 failed / 10,439 passed / 14 errors (`ccba93b1`) |

★**부수 관측(별건)**: `/.env` 가 19건으로 지연 키에 잡힌다 — **스캐너 트래픽이 모집단에 섞여 있다.**

## 2. 변경 내용

1. `note_coverage()` — 축별 `{judged, withheld, total, floor}`. `total` 은 **파생**(인자로 받지 않는다).
2. 세 분석기가 **표본으로** 판정가능 여부를 센다. ★`sev is None` 으로 세지 않는다 —
   그러면 *"표본 충분·정상"* 이 보류로 오분류된다(락으로 잠갔다).
3. `analyze_window` 가 **생산자 표식과 같은 자리**에서 **모든 인사이트**에 `analysis_coverage` 를 박는다.
   ★그 자리의 기존 주석이 *"타입별 손수 분기는 새 타입을 자동으로 누락시킨다"* 고 이미 지시한다.
4. **0건일 때도 로그**(P8 봉합).

**행을 새로 만들지 않는 이유**: 802개를 보류 행으로 발행하면 **소음이 늘 뿐**이다(P6).

**회귀가 아닌 근거**: `coverage` 는 **뒤에 붙인 기본값 인자**라 기존 호출부(위치인자 3개)가 밀리지 않는다.
`note_coverage(None, ...)` 는 무해한 no-op 이라 분석기를 단독 호출하는 기존 테스트가 안 깨진다.

## 3. ★검증하지 못한 것

1. **DB INSERT 를 태우지 않았다.** 락은 판정 로직만 본다 — `analysis_coverage` 가 실제 행에
   들어가는지는 배포 후 라이브 조회로만 확증된다(§5 프로브).
2. **소비처 0** — `analysis_coverage` 를 읽는 화면이 **없다**. `xfail(strict)` 로 초록 안에 남겼다.
   **값을 실어 보내는 것과 사용자가 보는 것은 다르다.**
3. **`content_hash` 무변화 단락**(1단계의 뒤 절반 · 소음 본체)은 **이 PR 에 없다** — 별건.
4. 로그 문구는 단언하지 않았다(산문 락은 다듬을 때마다 깨진다). 잠근 것은 **분기와 인자**다.

## 4. 되돌리기 경로

기본값 인자·no-op 헬퍼·스탬프 한 줄. 되돌려도 계약·스키마 변경 0.

## 5. 잠금

`tests/test_growth_analysis_coverage.py` — **두 모집단을 가른다**(미달만 vs 충족만 → `judged` 가 **실제로 달라야** 한다).
표본 충분·정상 케이스가 `judged` 로 세어지는지(= `sev is None` 로 세면 실패) · 스탬프가 **타입 분기 없이** 붙는지 ·
0건 로그 분기를 **ast 로**(주석에 걸리지 않게) 판정.

★배포 후 라이브 프로브:
```sql
SELECT metrics_json->'analysis_coverage' FROM platform_insights
 WHERE created_at > now() - interval '1 hour' LIMIT 3;   -- 값이 실려 있는가
```
그리고 `docker logs propai-celery-worker | grep '커버리지'` — **0건 실행에서도** 나와야 한다.
