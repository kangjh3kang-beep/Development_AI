# 인계 프롬프트 — 본문 팝오버 조상 트랩 (2026-08-08 → 다음 세션)

아래를 그대로 다음 세션 첫 지시로 쓰면 된다.

---

## 0. 착수 전 필수 (순서대로)

1. **`CLAUDE.md` 의 "회귀망·검증 규율" 을 읽어라.**
2. **★`gh pr list` 를 보되 *제목까지* 읽어라.** 이 세션이 여기서 중복 직전까지 갔다 —
   목록에 있던 PR 번호만 보고 제목을 안 읽어서, **이미 머지된 것을 다시 만들 뻔했다**
   (렌즈 2개·라이브 측정 ≈20분 낭비). `git log origin/main --oneline -15` 도 함께 본다.
3. `scripts/coord.sh status` — 여러 세션이 동시에 돈다. 이번에도 같은 린트 수정을 **35초 차이**로
   중복 생성했다(내 쪽을 닫았다).
4. **옵시디언 인계 문서**:
   `AI-Sessions/conversations/2026-08-08_PropAI_본문팝오버_조상트랩_인수인계.md`
   교훈 정본: `AI-Sessions/wiki/errors/2026-08-08_계약값은_조상이_깨끗할_때만_의미가_있다.md`
5. `git fetch` 후 **origin/main 기준 전용 워크트리**. 공유 메인에서 feature checkout 금지. `git stash` 금지.

## 1. 지금 상태

- 층위 파생 감시 캠페인(#587) **종결** · 라이브 검증 3항 **전부 통과** · registry 결함 2건 봉합(#596·#599)
- 본문 팝오버 칸 `contentPopover: 650` 은 **다른 세션이 #597 로 봉합·sw v498 배포 완료**
- ★**그런데 그 값이 먹지 않는 마운트가 남아 있다.** 실코드 수정은 **미착수**다.

## 2. 즉시 할 일

### ① 가드가 Tailwind v3 토큰을 찾는다 — 저장소는 v4다 (최우선)

`components/common/__tests__/GlobalAddressSearch.popoverRung.test.tsx:71`

```js
const ISOLATE = /(?:^|\s)(?:[a-z0-9-]+:)*(?:isolate|transform|filter|backdrop-filter)(?=\s|$)/;
```

| 가드가 찾는 것 | 저장소 실재 |
|---|---|
| `isolate`·`transform`·`filter`·`backdrop-filter` | 3 · 14 · **0** · **0** |
| v4 에서 실제로 SC 를 만드는 유틸 — `backdrop-blur-*` **105** · `opacity-N` **160** · `blur-*` 27 | **전부 미탐** |

즉 **"조상이 깨끗한지 검사한다"는 가드가 실제 SC 생성자의 대부분을 못 본다.**
정규식을 v4 유틸로 갱신하면 `SiteInitiator.tsx:140`(`backdrop-blur-3xl`) 등이 **빨갛게 드러난다.**
★갱신 후 **변이로 CAUGHT 를 확인**하고 넘어갈 것(추가만으로는 증명이 아니다).

### ② 계약 값이 안 먹는 마운트 5곳

`z-[650]` 은 값일 뿐이고 **조상이 SC 를 만들면 갇히고 `overflow-hidden` 이면 잘린다.**
라이브 실측(`/ko/projects/new`): 팝오버 z=650 인데 조상이 `overflow-hidden` ×2 + `relative z-10` ×2
→ **`scrollHeight 341px` vs `height 256px` = 85px(후보 약 2행) 잘림.**

| 마운트 | 무력화 요인 |
|---|---|
| `components/projects/ProjectAnalysisFlow.tsx:72` | `relative overflow-hidden` + `relative z-10` (잘림+갇힘) |
| `components/projects/SiteInitiator.tsx:151` | `backdrop-blur-3xl` (갇힘) |
| `app/[locale]/(dashboard)/projects/new/page.tsx:201` | `relative z-10` ×2 (갇힘) — **라이브 실측한 그것** |
| `components/precheck/PreCheckWorkspace.tsx:264` | `overflow-hidden` (잘림) |
| `components/sales/ProjectPipelinePanel.tsx:1147` | `overflow-hidden` (잘림·위험 낮음) |

**처방 미결정** — 포털(`createPortal` + 앵커 좌표)인지 클리핑 해제인지. 포털은 리사이즈·줌·스크롤
동기화라는 **새 버그 클래스**를 산다. 다만 조상이 **실제로** 클리핑하므로 이번엔 포털이 유리할 수
있다. **결정 전에 두 안의 실패 모드를 적고 시작할 것.**

### ③ 계약에 **전제 조건**을 적어라

`lib/satong-map-z.ts` 에 `contentPopover: 650` 은 있는데, **그 값이 유효할 조건**이 없다:

> 이 칸을 쓰는 요소의 **조상에 스태킹 컨텍스트(`relative`+`z-*`·`backdrop-blur-*`·`opacity-N`·
> `transform` 계열)나 `overflow-hidden|auto|scroll` 이 있으면 이 값은 효력이 없다.**

★이 저장소는 **같은 함정을 이미 겪었다** — CAD 전체화면이 `relative z-10` 에 갇혀 z-9990 이
실효 10 이었다. 그 사이 계약에 조건이 추가되지 않아 **다른 자리에서 반복됐다.**

## 3. 부채 (사용자 결정으로 이번에 안 함)

**감시망이 실제 대상을 안 태운다** — `GlobalAddressSearch.popoverRung.test.tsx` 는 그 컴포넌트를
**단독 렌더**하므로 조상 체인에 소비처 래퍼가 없다. 위 5건을 **구조적으로 볼 수 없다.**
처방은 소비처 13곳의 조상 체인을 **소스에서 파생**해 검사하는 것. `it.todo` 로 초록 안에 드러낼 것.

## 4. 재생성 금지 — 이미 반증한 것

1. "리스트박스가 **지도 오버레이**(380/420/430)에 가린다" → **거짓**.
   1280 은 컬럼 분리(가로 안 겹침)·780 은 세로 162px 간격. 진짜 상대는 **sticky ContextHeader(600)**
2. "본문 팝오버 칸을 신설해야 한다" → **이미 있다**(`contentPopover: 650`, #597·sw v498 배포 완료)
3. "601~698 대역에 뭔가 있어 승격이 위험하다" → **전 저장소 실측 0건**(650·699 만 존재)
4. "심각도는 목록이 통째로 사라지는 수준" → **아니다**. 실측 85px 잘림 = 하단 2행 접근 불가
5. "포털이 항상 정답" → 조상에 SC·overflow 가 **없는** 마운트 8곳에서는 비용만 지불

## 5. 작업 방식

실측 → `/insight-loop` 으로 **독립 렌즈를 병렬**로 돌려 문제를 생성 → 구현 →
**커밋 먼저 → 변이 → 원복** → 게이트 → 독립 적대검증(자기승인 금지) → 봉합 → 머지 →
sw 범프(**보드 claim 확인** — 통합자가 선점했을 수 있다) → 배포 → **라이브 검증** → 옵시디언 기록.

★**추정을 그대로 옮기지 마라.** 이번에 정적 판독 "~40px 만 남는다"가 실측 "85px 잘림"과 방향이
반대였다(과장). 심각도·수치는 **재보고 쓴다**.
★**"가드가 있다"와 "그 가드가 현재 스택에서 성립한다"는 다르다.** v3→v4 전환에서 SC 유틸 표기가
바뀌었는데 가드는 그대로였다.
★**라이브 판정은 경쟁 상대가 실제로 보이는 상태**에서 하라. 이번에 레일을 안 연 채 재서 공허한
통과가 나왔고, 겹치는 좌표를 계산해 다시 쟀다.
