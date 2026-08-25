# 계획 — 폴백 사유가 화면까지 닿게 한다 (2026-08-25)

브랜치 `fix/insight-metrics-key-coverage` · 베이스 `origin/main`

## ① 옵시디언 조회 결과

조회함(`obsidian-brain` query · Vault `나의-모든-기록-최적화본`).

| 문서 | 무엇을 줬나 |
|---|---|
| `AI-Sessions/conversations/2026-08-25_PropAI_등기분석품질_인계.md` | 정본 인계서. **값이 아니라 재측정 명령**을 쓰라는 지시. `RegistryService.get_one` 이 래퍼라는 계약 변경 · `mutate_changed.py` 를 `python3` 로 부르지 말 것 · 스쿼시 머지 브랜치 재사용 금지 |
| `AI-Sessions/wiki/decisions/2026-08-24_완성도_100퍼센트_한계분석과_목표_재정의.md` | 로드맵 정본. **④ 최저항 개선은 ③ 사유 분포가 쌓인 뒤**. "원인을 모르고 고치면 그 수정이 다음 조사의 잡음이 된다" |
| `AI-Sessions/wiki/concepts/유료·비가역_산출물_규율.md` | 유료 호출은 재사용 래퍼 경유 · 실패도 사유를 버리지 않는다 |

**없었던 것**: 이 결함(인터프리터 자체 계측에 `reason` 부재)을 다룬 기록은 **없음**.
가장 가까운 것은 *"관측 사각 6건 → 면제 0건"* 인데, 그 스윕의 축이
**"`llm.ainvoke` 를 직접 부르는 21개 서비스"** 였고 **BaseInterpreter 자신은 축 밖**이었다.

## ② 전제 표 — 확인 *방법* 과 **실제 측정값**

| # | 전제 | 확인 방법 | 실제 측정값 | 판정 |
|---|---|---|---|---|
| P1 | #816 이 라이브에 없다 | `curl -s https://4t8t.net/sw.js \| grep -m1 '^const CACHE_NAME'` → sha 를 `git cat-file -e` 로 대조 | `propai-v002763-f15288bf`, main 은 `b8396e58`. 미배포 3커밋 | **관측** — 미배포 |
| P2 | 라이브 폴백률과 그 서비스 | admin 로그인 후 `/api/v1/growth/insights?limit=500` | `fallback_rate` **26건 / 3서비스**: `site_analysis` 100%(13/13) · `feasibility` 100%(21/21) · `market` 40%(4/10) | **관측** |
| P3 | 그 인사이트에 `reasons` 가 있나 | 같은 응답에서 키 존재 계수 | **0건** (음성 대조군 = 미배포 확증) | **관측** |
| P4 | 세 서비스가 BaseInterpreter 인가 | `grep -rn '^\s*name = "' app/services/ai/*.py` (파생형) | `site_analysis_interpreter.py:138` · `feasibility_interpreter.py:106` · `market_interpreter.py:117` — **셋 다** | **관측** |
| P5 | 그 실패 경로가 `reason` 을 싣나 | `base_interpreter.py` 의 `ok=False` 쓰기 자리 전수 | `:851` `payload: {"ok": False, "error": ...}` — **없음** | **관측** |
| P6 | analyzer 가 `error` 에서 사후 분류하나 | 사유 SQL 을 끝까지 읽음 | `COALESCE(NULLIF(payload->>'reason',''),'unlabeled')` — **문자열 파싱 없음** | **관측** |
| P7 | 다른 경로로 `reason` 이 실리나 | `record_llm_failure` 호출부 전수(대조군으로 조회기 생존 확인) | 비테스트 호출부 2곳(`llm_provider.py:230` `registry_analysis_service.py:629`) — **세 서비스 아님** | **관측** |
| P8 | `_ObservedChat` 이 감싸나 | `_get_llm()` 이 `service=` 를 넘기는지 | **안 넘긴다**(`llm_provider.py` 주석이 그렇게 선언) | **관측** |
| P9 | 화면이 사유를 그리나 | admin 로그인 후 성장 분석 탭 실측 | `서비스 / 폴백률 / 호출 수` **3줄뿐**, `최다 사유`·`사유 분포` **0건** | **관측** |
| P10 | narrative 가 이미 말하는 키 | 라이브 카드 본문 + `_rule_narrative` 대조 | *"(폴백 32/42콜)"* 등 — `fallback`·`signature`·`per_hour`·`high_count` 는 **이미 보인다** | **관측** |
| P11 | 대시보드 실사용 빈도 | — | **미측정** | 미측정 |

## ③ 회귀가 아닌 근거

- 쓰기층은 **인라인 복제를 같은 파일의 기존 공용 헬퍼로 합류**시킨 것이다. 새 이벤트가 아니라
  **같은 한 줄**에 키 두 개가 늘어난다 → 분자·분모 불변(락 `test_이중계상이_아니다` 가 강제).
- 합류가 `latency_ms` 를 떨어뜨릴 뻔했다 → 헬퍼에 파라미터를 추가하고 **락으로 잠갔다**.
- 표시층은 `metrics_json` 에 키가 **없으면 행을 안 낸다**(특이도 케이스로 잠금) → 배포 전에도 무해.

## ④ ★검증하지 못한 것

- **키 전수 커버리지 축은 미잠금**이다. `it.todo` 로 초록 안에 남겼다.
  정규식 파서를 시도했다가 **접었다** — 그 파서가 `insight_type_for_latency(sev)`(함수 호출)로
  만들어지는 latency 2종을 놓치고 `quality_drop` 의 `**metrics` 스프레드 키 3개도 못 봐,
  **"미참조 12건"이라는 위음성 목록**을 만들었다. 그 목록을 보드에 이미 적었다가 정정했다.
- **배포 후 실제 분포는 아직 모른다.** 이 PR 이 배포돼야 `unlabeled` 이 아닌 값이 쌓이기 시작한다.
  즉 로드맵 ④는 **이 PR 배포 + 관측 창(24h) 이후**에 착수 가능하다.
- `growth/` 밖에 `INSERT INTO platform_insights` 가 더 있는지는 **스윕 범위 밖**(§26 — 한 층만
  보고 "없다"고 하지 않기 위해 범위를 명시한다).
- P11(대시보드 실사용 빈도) 미측정.

## ⑤ 되돌리기

파일 4개 · 순수 가산. `git revert` 로 원복 가능하고 마이그레이션·스키마 변경 **없음**.
표시층만 되돌려도 백엔드는 정상 동작한다(키가 늘 뿐 소비를 강제하지 않는다).

## ⑥ 잠금

| 축 | 어디서 | 변이 |
|---|---|---|
| 탐지(쓰기) | `test_interpreter_failure_reason_wiring.py` | `reason=` 삭제 → CAUGHT |
| 특이도(쓰기) | 〃 | 사유를 상수 고정 → CAUGHT |
| 합류 회귀 | 〃 | `latency_ms` 삭제 → CAUGHT |
| 이중계상 | 〃 | (락만 · 변이 미생성 — 계약 선언) |
| 탐지(표시) | `GrowthDashboard.metrics-rows.test.tsx` | `최다 사유` 행 삭제 → CAUGHT |
| payload 결속 | 〃 | `m.confidence` 파손 → CAUGHT(**처음엔 SURVIVED** — 상수 행이 가렸다) |
| 라벨표 | 〃 | `REASON_LABELS` 무력화 → CAUGHT |
