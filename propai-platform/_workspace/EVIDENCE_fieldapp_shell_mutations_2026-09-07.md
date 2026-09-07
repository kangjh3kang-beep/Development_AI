# 변이 검증 증거 — 분양 현장앱 셸 리팩토링 (PR #1015)

적대 리뷰가 *「11/11 인지 8/8 인지 알 수 없고 `::VERDICT=` 산출물이 없어 **재현 불가**」* 라고
지적했다. 그래서 **판정 줄을 그대로** 남긴다(손으로 고른 변이만 · 기계 변이는 별도).
각 실행은 도구가 **기준선 초록 · 주입 성공 · 원복 바이트 동일**을 강제한다.

## ① 도구가 찍은 판정 (로그에서 그대로 옮김)

```
mut1   CAUGHT    기준선 15건
mut2   CAUGHT    기준선 15건
mut3   CAUGHT    기준선 15건
mut4   CAUGHT    기준선 27건
mut5   CAUGHT    기준선 27건
mut6   CAUGHT    기준선 27건
mut7   CAUGHT    기준선 27건
mut8   CAUGHT    기준선 27건
mut9   CAUGHT    기준선 33건
mut10  CAUGHT    기준선 33건
mut11  CAUGHT    기준선 33건
r1     CAUGHT    기준선 41건
r2     CAUGHT    기준선 41건
r3     CAUGHT    기준선 41건
r4     CAUGHT    기준선 41건
r5     CAUGHT    기준선 41건
r6     SURVIVED  기준선 41건
r7     CAUGHT    기준선 41건
r8     CAUGHT    기준선 41건
```

★기준선 수열(15 → 27 → 33 → 41)이 커밋 타임라인과 일치한다:
`c4412fda2`=15 · `476a1abe9`=27 · `641ddf76d`=33 · 그 뒤=41.

## ② 무엇을 변이시켰는가 — ★**작성자 기재**(로그 파생 아님)

★정직하게 구분한다: **`mutate_manual.sh` 는 대상 파일과 sed 표현을 로그에 찍지 않는다**(실측).
아래는 내가 실행한 명령을 **기억이 아니라 셸 이력 기준**으로 옮긴 것이고, 위 ①과 달리
**도구 산출물이 아니다.** 재현하려면 아래를 그대로 돌려라.

| 라벨 | 대상 | 변이(sed) | 무엇을 죽이려 했나 |
|---|---|---|---|
| `mut1` | `FieldNav.tsx` | `const pinned = tabs.filter(...)` → `const pinned: SalesTabDef[] = []` | 고정 슬롯 파생 |
| `mut2` | `FieldNav.tsx` | `{open.items.map(` → `{tabs.map(` | 전 탭 나열 회귀(리터럴) |
| `mut3` | `FieldNav.tsx` | `g.items.length > 0` → `>= 0` | 빈 그룹 숨김 |
| `mut4` | `FieldAppAffordance.tsx` | `if (inAppShell) return null;` → `if (false)` | 앱 안 가드 |
| `mut5` | `FieldAppAffordance.tsx` | `별도 창으로 열기` → `앱으로 열기` | 거짓 라벨 |
| `mut6` | `FieldAppAffordance.tsx` | `menubar=no,toolbar=no,status=no` → `…,location=no,…` | 지키지 못할 약속 |
| `mut7` | `FieldAppAffordance.tsx` | `window.location.href, FIELD_APP_WINDOW_NAME, feat` → 리터럴 `"propai-field"` | 여는 이름 ↔ 판별 이름 |
| `mut8` | `field-app-shell.ts` | `standalone \|\| inSeparateWindow` → `standalone` | 별도 창 축 |
| `mut9` | `FieldAppAffordance.tsx` | `onClick={() => void requestInstall()}` → `onClick={() => {}}` | 설치 버튼 무동작 |
| `mut10` | `FieldAppAffordance.tsx` | 팝업 차단 폴백 제거 | 새 탭 폴백 |
| `mut11` | `SiteWorkspaceClient.tsx` | `<FieldDesktopNav … />` → `<div />` | 셸 배선 |
| `r1` | `FieldNav.tsx` | `{open.items.map(` → `{groups.flatMap((g) => g.items).map(` | ★**적대 리뷰가 SURVIVED 로 실증한 변이** |
| `r2` | `FieldNav.tsx` | `backdrop-blur sm:block` → `sm:hidden` | ★같음(반응형 축) |
| `r3` | `FieldAppAffordance.tsx` | `noopener,noreferrer` → `__MUT__` | ★같음(역탭내빙) |
| `r4` | `FieldAppAffordance.tsx` | `if (standalone)` → `if (standalone \|\| inSeparateWindow)` | 되돌린 BLOCKER 복원 |
| `r5` | `SiteWorkspaceClient.tsx` | `onNavigate={setTab} />` → `onNavigate={() => {}} />` | 셸 배선(핸들러) |
| `r6` | `FieldNav.tsx` | `groups.find(g => g.title === activeGroupTitle) ??` → `null ??` | 폴백 사슬 |
| `r7` | `FieldNav.tsx` | `aria-current={holdsActive ? "true" : undefined}` → `undefined` | 활성 그룹 표기 |
| `r8` | `FieldNav.tsx` | `r6` 과 **동일** | 락 강화 후 재확인 |

## ③ 판독

- **19회 · 최종 전부 CAUGHT.**
- ★**중간의 SURVIVED 1건(`r6`)을 지우지 않는다** — M2 락이 `activeGroupTitle` 폴백이 아니라
  `groups[0]` 폴백으로도 만족됐다(활성 탭을 첫 그룹에 뒀기 때문). 활성 탭을 첫 그룹 **밖**으로
  옮겨 고친 뒤 `r8` 에서 CAUGHT 를 받았다.
  **락을 추가한 것만으로는 그것이 무엇을 보는지 모른다** — 이 줄이 그 증거다.
- `r1`·`r2`·`r3` 은 **적대 리뷰가 `::VERDICT=SURVIVED` 로 실증한 바로 그 변이**이고,
  봉합 후 CAUGHT 로 뒤집혔다(리뷰어가 자기 변이로 독립 재확인했다).

## ④ 재현

```bash
cd propai-platform/apps/web
../../../scripts/mutate_manual.sh <위 표의 대상> '<위 표의 sed>' \
  ./node_modules/.bin/vitest run components/sales-app/
```

★기계적 변이는 별도다: `python3 scripts/mutate_changed.py --tests <테스트 파일들>`
(수치는 커밋마다 바뀌므로 **값으로 적지 않는다** — 돌려서 봐라).
