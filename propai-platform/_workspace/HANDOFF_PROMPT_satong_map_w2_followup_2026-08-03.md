# 인계 프롬프트 — 사통맵 W2 후속(PR #536 머지) + 계측 판독 → W3~W5

> 이 파일 경로를 그대로 새 세션에 붙여넣으면 됩니다.
> 작성: 2026-08-03 · 선행 정본: 옵시디언 `AI-Sessions/conversations/2026-08-03_PropAI_사통맵_W2_지오코딩_인수인계`

---

## 0. 착수 전 (건너뛰지 말 것)

1. **옵시디언 먼저 참조** — `obsidian-brain` 스킬 query 로 아래 두 문서를 읽는다.
   SessionStart 훅이 주입하는 요약은 **출발점일 뿐 충분하지 않다.**
   - `AI-Sessions/conversations/2026-08-03_PropAI_사통맵_W2_지오코딩_인수인계` ← **이 프롬프트의 정본**
   - `AI-Sessions/wiki/dev-tasks/2026-08-03_PropAI_지오코딩_시군구근원_W2` ← 기술 상세·교훈
2. **보드 확인** — `scripts/coord.sh status`. 재개 시 **새 claim 필요**(W2 claim 은 모두 RELEASE 됨).
3. **전용 워크트리에서만 작업.** 기존 워크트리 `/home/kangjh3kang/My_Projects/Development_AI_geocode_root`
   (브랜치 `fix/geocode-observability-followups`). **`git stash` 금지.**
   공유 메인 워크트리는 stale(HEAD 5582bb30) — 코드 확인은 `git show origin/main:` 로.
4. `scripts/coord.sh note` 에 **백틱 금지**(명령 치환으로 내용이 소실된다).

---

## 1. 지금 상태 (실측 확인됨)

| 항목 | 값 |
|---|---|
| `main` | `976797d9` (#535 W2 근원 봉합) |
| 168 백엔드 | `976797d9` — **배포 종결** |
| 158 프론트 | `79f621f3` · sw `propai-v481-ratio-matrix` |
| 배포 대기 | 0 (#536 머지 전) |
| **PR #536** | `fix/geocode-observability-followups` head **`cc21fbb0`** · **OPEN · MERGEABLE** |

**PR #536 CI**: Backend(pytest) / Frontend(type-check+lint+test) / Frontend(next build) / Detect changes
= **전건 SUCCESS**. Cloudflare Pages · Workers Builds 2건 FAILURE = **백엔드 전용 변경과 무관한 공통 선재 부채**.

**게이트 실측**: 백엔드 **8,933 passed / 7 failed** — 7건은 선재 목록과 **정확히 일치**(증가 0):
`test_growth_loop_e2e` · ledger 2건 · `test_cost_backtest` · `test_disbursement_ledger` ·
`test_parcel_boundary_export` 2건(matplotlib ModuleNotFound). ruff clean.

---

## 2. ★W2 는 끝났다 — 효과가 수치로 확인됐다

통합자 배포 전/후 대조(호미곶 대보리 산1-1 · PNU `4711135022200010001`):

| 지표 | 배포 전 | 배포 후 |
|---|---|---|
| `coords_unresolved_count` | 30 | **8 (−73%)** |
| `apt_trade` count | 32 | **0** |
| `radius_filtered_out_count` | 315 | 337 |
| `lawd_cd` | — | 47111(포항시 남구·정상) |

사라진 apt_trade **32건이 1억 1,144만원 가짜 시세를 만들던 그 표본**이다. 반경제외가 315→337 로 는 것은
좌표가 풀린 건들이 이제 **제대로 반경 판정을 받아** 정상 제외된 것이라 방향이 맞다.
→ **#516(AVM)·#527(요약통계)·#535(시군구)가 한 결함의 하류·하류·상류였음이 수치로 확인됐다.**

---

## 3. 할 일 (순서대로)

### ① PR #536 머지 → 통합자 배포 요청 (즉시)

- CI 그린 · MERGEABLE · **백엔드 전용**(프론트 변경 0 · **sw 범프 불요**).
- 머지 후 `scripts/coord.sh note` 로 **168 단독 배포** 요청.

### ② 계측 판독 → 다음 처방을 데이터로 결정 (#536 배포 후)

**★판독 규칙 (N-1 이 만든 계약 — 반드시 지킬 것)**
`geocode_failure_breakdown` 에서 **`cached:` 접두가 붙은 항목은 라이브 사건이 아니다.**
캐시분을 뺀 뒤에야 429/5xx 비중을 말할 수 있다. 이걸 안 지키면 **단일 429 사건이 30개 질의로 증폭된
숫자**를 실제 실패율로 오독하고, transient-first 편향과 같은 방향으로 중첩돼 판정이 틀린다.

또한 **캐시 워밍 이후**에 판독한다(#535 로 질의 문자열이 바뀌어 `geo:vworld` 7일 캐시가 전량 무효화됨).

판독 대상:
- `geocode_failure_breakdown` (캐시분 분리 후)
- `geocode_attempt_breakdown` — 시도 단위(질의 1건 = PARCEL·ROAD 2시도)
- `sigungu_source` 의 `row_fallback` 비율 — 힌트 도출 실패율
- `apt_trade` located 비율 — **기준선: 역삼동 736 아파트 매매 `located=10 · approximate=8 · unlocated=87` (17%)**

### ③ M-4 — 사전컷 예산 분할 + 역방향 회귀 테스트 (이월분 최우선)

**이월 항목 중 유일하게 사용자 수율에 직접 영향.** 손실 분해가 우선순위를 말해준다:

> 사전컷 **73.8%** · 반경밖 18.8% · **지오코딩 실패 2.6%**

즉 재시도(2.6%)보다 사전컷(73.8%)이 압도적으로 크다.
주의: 마스킹 지번(`4**`) 스킵 · `_BUILD_CACHE` 실패율 임계 · 그룹 키에 법정동 추가는
**사전컷·캡 상향과 한 PR 로 묶어야** 순효과가 음수가 되지 않는다(그룹이 쪼개져 캡에 밀린다).

### ④ 나머지 이월 (경미)

F-4(로그 위치) · F-5(군 차단 근거 비대칭) · R-4 잔여(분자⊄분모 · `geocode_attempted_count` →
`geocode_queries_count` 개명) · M-6 · L-1 · L-2 · M-9(`as never` 캐스트) ·
H-2 후반(`deriveResults`/`buildResult` 행위 테스트) · `presale_service` 무음 드롭(별건).

### ⑤ W3~W5 — 원 캠페인 잔여 (미착수)

- **W3** 자가진단 거짓음성
- **W4** 반경 SSOT / 적응형 반경(최근접이 1.35km 라 1km 고정은 0건이 보장되는 지점이 있다)
- **W5** Next API 라우트 프로덕션 404(AVM 항공 썸네일 미표시)

---

## 4. ★재생성 금지 — 이미 반증된 가설

**"`_geocode_one` 에 재시도가 없다"** 는 인계문서에 1년 가까이 살아 있었으나 **반증됐다.**

- 그룹 손실의 **2.6%** 만 겨냥한다.
- 게다가 **발화조차 하지 않는다** — VWorld 는 매칭 실패도 **HTTP 200 + `status=NOT_FOUND`** 로 주는데
  재시도 헬퍼 `_vworld_get_json` 은 429/5xx/타임아웃만 본다.
- 착수하더라도 **`_vworld_get_json` 위임은 금지** — 위임하면 `geocode_address` 가 `refined.text` 를 버려
  W1-b 의 `_refined_mismatch` 가드가 **무성 파괴**된다.

계측(②)이 캐시분을 뺀 뒤에도 429/5xx 비중이 유의미하다고 말할 때만 재검토한다.

---

## 5. 작업 규율 (이 캠페인의 표준 — 매 웨이브 반복)

**실측 → 구현 → 3층 변이(로직·배선·표면) → 게이트 → 독립 적대검증 → 봉합 → 머지 → 배포요청**

- **자기승인 금지.** 승인 패스는 반드시 `code-reviewer` 서브에이전트(작성한 컨텍스트와 분리).
- 계획·분석을 사용자에게 제시하기 **전에** `/insight-loop` 로 자기반증을 먼저 돌린다.
- **★채택 규칙(이번 세션에서 새로 확립): 새 분기를 만들면 그 분기를 태우는 테스트를 같은 커밋에 넣는다.**
  근거 — "로직은 고치고 그 로직의 잠금은 빠지는" 패턴이 이 캠페인에서만 **세 번** 반복됐다
  (H-1 공허 배선단언 · R-2 `_dong_tail` 무잠금 · N-2/N-3 라이브 HTTP 분기 무테스트).
- **변이는 로직뿐 아니라 배선·표면에도 넣는다.** 배선 미변이로 이미 다섯 번 뚫렸다.
- **"생존" 보고 전에 주입이 실제로 됐는지 확인**(부분 치환·이스케이프 위양성).
- sw 범프가 필요하면 **PR 생성 전에 보드에 번호를 claim**(v463·v481 두 번 충돌했다).

---

## 6. 검증 명령 모음

```bash
# 워크트리
cd /home/kangjh3kang/My_Projects/Development_AI_geocode_root

# PR 상태
gh pr view 536 --json state,mergeable,statusCheckRollup

# 백엔드 게이트 (선재 7건 목록과 대조할 것)
cd propai-platform/apps/api && ruff check . && python -m pytest -q

# 라이브 계측 (배포 후 · 로그인 필요)
# GET https://api.4t8t.net/api/v1/zoning/nearby-map?... → 응답의
#   geocode_failure_breakdown / geocode_attempt_breakdown / sigungu_source / coords_unresolved_count
```
