# 심의 CI 를 **필수로 등록 가능한 구조**로 전환한다 (2026-09-04)

> **작성: `development-ai-8f` · 2026-09-04**

## 0. 옵시디언 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **없음**(기각 기록 없음) |
| ★같은 클래스의 앞선 작업 | ★**있다. 대부분 이미 했다.** `#423 path-aware CI(a1989bc9)` 가 **주 CI** 를 `pull_request paths → changes 잡 + 잡레벨 if` 로 이관했다(*"스킵=required 충족·문서PR Expected 함정 해소"*). 그때 심의는 **self-trigger 만** 받았고 **이 전환에서 빠졌다** |
| ★미결 | ★**있다. 그리고 같은 종류다.** 같은 기록: *"**브랜치보호 등록 = 분류기 차단 · 사용자 실행 대기**"* — 이전 세션도 **설정 변경에서 막혀 사용자에게 넘겼다** |
| ★실해 증거 | ★**있다.** 같은 기록: *"필요성 실증: 타 세션에서 **`#425` 가 CI FAIL 채로 머지된 실사고** 발생 — 보호 있었으면 구조적 불가"* |

★**내 초기 판단 「실해 0건」은 범위가 좁았다** — 심의 워크플로 안에서만 셌다.
저장소 차원에서는 **CI FAIL 머지 사고가 실재했고**, 그래서 지금 필수 4종이 등록돼 있다.
**심의만 그 전환에서 빠진 상태**다.

## 1. 전제 표 (전부 **실측** · 2026-09-04)

| 전제 | 확인 방법 | 결과 |
|---|---|---|
| 심의 CI 가 main 에서 도는가 | `#962` 머지 직후 run 조회 | ★**돈다.** `33825884559` · `01:28:16Z` success (머지 `01:28:14Z`) — **초기 「3주 기준선 부재」 판단은 틀렸다**(경로가 안 바뀌었을 뿐) |
| 필수 체크 목록 | `gh api .../branches/main/protection` 파생 | `Backend (pytest)` · `Detect changes` · `Frontend (next build)` · `Frontend (type-check + lint + test)` — ★**심의는 없다** |
| 심의가 빨간 채 머지된 적 | 그 워크플로 PR run 전수 시계열 | **없다.** `fix/deliberation-honesty` 가 실패 4회였으나 **머지 직전 마지막 run 은 success**(21:34 · 머지 21:52) |
| 왜 그냥 required 에 못 넣나 | `ci.yml:8~12` 주석 원문 | 워크플로 레벨 `pull_request: paths` + required = **문서 전용 PR 이 `Expected` 영구대기**로 차단 |
| 심의가 그 형태인가 | `deliberation-ci.yml:11~12` 원문 | ★**그렇다.** `pull_request:` 아래 `paths:` 가 있다 |
| 복사할 정본 패턴 | `ci.yml:16~50` | `changes` 잡(`Detect changes`) + 잡 레벨 `if` · **fail-safe**(판별 실패 → 전체 실행) · `here-string`(SIGPIPE 회피) |

## 2. 변경 내용

`deliberation-ci.yml` 을 `#423` 이 주 CI 에 쓴 구조로 옮긴다:

1. `pull_request:` 의 `paths:` **제거**(bare trigger).
2. `changes` 잡 신설 — PR 이면 파일 목록으로 판별, **아니면 전체 실행**.
   ★**fail-safe**: 판별 실패는 반드시 `engine=true`(전체 실행)로 귀결한다.
   반대로 하면 이 잡의 실패가 하위 잡 skip → **required 충족 → 무검증 머지**가 된다
   (`#423` R1 이 실제로 그 결함을 냈다).
3. `engine-tests` 에 `if: needs.changes.outputs.engine == 'true'`.
4. `push` 트리거의 `paths` 는 **유지**한다 — push 에는 required-check 함정이 없고,
   main 에서 불필요한 실행을 늘리지 않는다.

**회귀가 아닌 근거**: 심의 트리를 건드리는 PR 은 지금과 동일하게 전체를 태운다.
안 건드리는 PR 은 **지금은 잡이 아예 안 나타나고**, 바뀐 뒤에는 **skip 으로 나타난다** —
GitHub 이 skip 을 required 충족으로 계수하므로 그 PR 이 막히지 않는다.

## 3. ★검증하지 못한 것 — **이 PR 만으로는 잠기지 않는다**

★★**`Deliberation Engine (pytest)` 를 `required_status_checks` 에 추가하는 것은
저장소 설정 변경이고 내 권한 밖이다.** 동료에게 대신 부탁하지 않는다(권한 세탁).

> **이 PR 은 「필수로 만들 수 있는 구조」를 만들 뿐, 「필수」로 만들지 않는다.**
> 설정 추가 전까지 그 검사는 **여전히 머지를 막지 않는다.**

`#423` 도 같은 자리에서 멈춰 **사용자 실행 대기**로 남겼고, 그 뒤 필수 4종은 등록됐다 —
즉 이 경로는 **작동한 전례가 있다.** 아래 명령을 소유자에게 남긴다:

```bash
gh api -X PUT repos/kangjh3kang-beep/Development_AI/branches/main/protection/required_status_checks \
  -f strict=true \
  -f 'contexts[]=Backend (pytest)' \
  -f 'contexts[]=Detect changes' \
  -f 'contexts[]=Frontend (next build)' \
  -f 'contexts[]=Frontend (type-check + lint + test)' \
  -f 'contexts[]=Deliberation Engine (pytest)'
```
★**기존 4종을 함께 적는다** — 이 API 는 **치환**이라 빠뜨리면 그 보호가 사라진다.

- **`skip` 이 required 를 충족한다**는 것은 `ci.yml` 주석의 **선례**로만 안다.
  이 저장소에서 그렇게 동작해 왔다는 것이 근거이고, **내가 직접 재지는 않았다.**

## 4. 되돌리기 경로

단일 커밋 revert. 런타임 코드 변경 없음.

## 5. 잠금 — 락 **7건**(6 pass + **1 xfail**) · 변이 **4/4 CAUGHT**

| 변이 | 결과 |
|---|---|
| `pull_request` 에 `paths` 복원 | CAUGHT |
| 잡 레벨 `if` 제거 | CAUGHT |
| **fail-safe 를 fail-open 으로** | CAUGHT |
| `push` 의 `paths` 도 제거(**음성 대조군**) | CAUGHT |

★**공허 방지 대조군을 단언 앞에** 뒀다 — 워크플로가 안 읽히면 아래가 전부 공허하다.
★**양성 대조군**: 내가 복사한 패턴이 주 CI 에 **실제로 있는지**도 단언한다.
주 CI 가 바뀌면 *"내가 인용한 근거가 낡았다"* 로 빨개진다.
★★**부채를 `xfail(strict=True)` 로 초록 안에 드러냈다** — 브랜치보호에 등록되면
그 테스트가 **XPASS 로 실패**해서 다음 사람이 `xfail` 을 지우게 된다.
**부채가 조용히 남지 않는다.**

## 6. 회귀 대조 (실측 · 세 축)

    origin/main   5 failed · 1,135 passed · 3 xfailed · 1,173 collected
    이 브랜치      5 failed · 1,141 passed · 4 xfailed · 1,180 collected
    실패 집합 comm 회귀 0 · 통과 +6 · xfail +1 · 수집 +7 = 신규 7건과 일치 ✔

★**수집 노드까지 잰다** — 실패 개수가 같아도 테스트가 소실된 사례가 이 저장소에 있다.
