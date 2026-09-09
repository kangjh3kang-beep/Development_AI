# 배선의 **동일성 축**을 잠근다 — 모든 마커가 「아파트」라고 말해도 초록이었다

> #1018 적대 리뷰 MAJOR-6 이 남긴 미해결. 그때는 *"Leaflet 목이 없어 못 잠근다"* 로 부채였는데,
> #1024 가 **목이 필요 없다**는 것을 실증했다(진짜 Leaflet 이 jsdom 에서 돈다). 이제 닫는다.

작성 세션 sid=`dcb7a4f2` · base `696b532a8`(#1024 배포본)

---

## 0. 옵시디언 조회 결과

히트 **2건** — 둘 다 이 작업에 직접 해당한다.

| 문서 | 이 작업에 주는 것 |
|---|---|
| `2026-09-09_하네스는_있었고_원문확인은_범위때문에_거짓이었다` | **내 어제 기록.** 하네스 실증 + *"`SatongMultiMap` effect 를 새 하네스로 태운다"* 를 **Next Action 으로 적어 둔 그 항목**이 이 PR 이다 |
| `2026-09-03_락이_리팩토링에_깨지면_그건_락의_결함이다` | ★**이 PR 이 정확히 그 위험을 만든다** — effect 를 함수로 꺼내면 **위치·모양에 의존하는 기존 락**이 깨질 수 있다. 깨지면 «코드를 되돌린다」가 아니라 **락의 경계를 구조에서 파생**시킨다 |

★**조회 신뢰도 낮음**: 같은 스캔에서 **읽기 실패 5건**(볼트가 808→26 으로 훼손됐다).
「없음」이 아니라 **「조회 결과」**다.

---

## 1. 전제 표 — 확인 방법과 **실측값**

| # | 전제 | 확인 방법 | **실측값** |
|---|---|---|---|
| P1 | 동일성 축이 정말 무잠금인가 | #1018 리뷰 변이 | ★**그렇다.** 호출부 `const { type, … } = entry` → `const type = "apt"` 로 바꿔치기하면 **모든 마커가 「아파트」**라고 말하는데 **2412건 초록**(SURVIVED) |
| P2 | 왜 못 잠갔나 | — | 그 배선이 **Leaflet effect 안**이라 목이 없으면 행위로 못 태운다고 판단했다 |
| P3 | ★그 판단이 옳았나 | #1024 실증 | ★**아니다.** `leaflet` 이 선언돼 있고 **jsdom 에서 그대로 돈다**. 목은 필요 없었다 |
| P4 | 마커 생성부가 분리 가능한가 | 원문 | **가능하다** — `groups.forEach` 안이 ①반지름 ②`circleMarker` ③`bindPopup` ④가격표기 ⑤`bindSatongLabel` ⑥`addTo(group)` ⑦`bounds.extend` 로 순차적이다. ★**정정(적대 리뷰 MINOR-5)**: 초판은 외부 상태를 *「`bounds`·`group` 뿐」* 이라 적었는데 **틀렸다** — 실제로는 `kind`·`pricePerPyeongOn`·**라벨 버짓**(`ordinal`·`typeLabelLimit`)도 effect 스코프에서 온다. 그 넷은 **인자로 넘긴다**. 남는 외부 상태는 `bounds` 뿐이다 |
| P5 | 유형·색이 어디서 오나 | 원문 | **같은 `entry` 객체**에서 온다(`entry.type` · `entry.color`) — 그래서 **함수가 `entry` 를 받으면** 동일성이 함수 안으로 들어온다 |
| P6 | 기존 락이 이 자리를 어떻게 보나 | 파생 | `satong-map-honesty-wiring.test.ts` 가 **소스 문자열**로 본다 — §0 의 두 번째 문서가 경고한 그 형태다 |

### ★P1·P5 가 이 PR 의 근거다

동일성이 **effect 안의 지역변수**라 잠글 수 없었다. `entry` 를 통째로 받는 함수로 옮기면
**바꿔치기할 지역변수가 사라지고**, 그 함수는 진짜 Leaflet 으로 **행위 검증**된다.

---

## 2. 변경 내용과 **회귀가 아닌 근거**

### 2-a. 마커 생성을 `buildMarketMarker(L, item, entry, opts)` 로 꺼낸다

- `entry` 를 **통째로** 받는다(`type` 문자열이 아니라). ⇒ 호출부에 «바꿔치기할 지역변수»가 없다.
- 팝업 유형·마커 색이 **같은 인자에서** 나오므로 둘의 **일치**가 함수 안에서 잠긴다.
- 반환은 마커. `bounds.extend` 는 **effect 에 남긴다**(경계는 여러 마커의 누적이라 effect 관심사).
- ★★**정정(적대 리뷰 MAJOR-1)**: 초판은 `addTo(group)` 도 *「레이어는 effect 관심사」* 라며 밖에 뒀다.
  **그것이 정확히 이 PR 이 고치려던 결함의 재발**이었다 — 그 한 줄을 `void marker;` 로 지우면
  **실거래 마커가 하나도 안 뜨는데 초록**이다(실측 SURVIVED). 지금은 `opts.group` 으로 받아
  **함수 안에서** 붙이고, `group.getLayers().length` 로 잠근다(실측 CAUGHT · 4건이 잡는다).
  ***태울 수 없는 자리에 배선을 남기고 「관심사 분리」로 부르지 않는다.***
- ★라벨 버짓(`ordinal < typeLabelLimit`)도 함수 안에서 판정한다 — 계약이 선언돼 있었는데 단언이 0건이었다.

회귀가 아닌 근거: 옮기는 것은 **순차 코드 묶음**이고, effect 에서 오던 값(`kind`·`pyeongFirst`·
`ordinal`·`typeLabelLimit`·`group`)은 **전부 인자로 넘겨 같은 값이 그대로 흐른다**. 호출 순서도
★**정정(R2 MAJOR-5)**: 초판은 *"호출 순서도 동일하다(`addTo` 는 종전에도 `bindSatongLabel`
뒤였다)"* 라고 적었는데 **정확히 반대였다** — `origin/main` 실측: `.bindPopup(...).addTo(group)`
이 **먼저**고 `bindSatongLabel(marker, …)` 이 **나중**이었다. 지금은 그 반대다. **순서는 바뀌었다.**

★**그런데 동작 회귀는 없다**(관측): `node_modules/leaflet/dist/leaflet-src.js:10876`(바인드 시
이미 맵 위면 즉시 open) · `:10910`(`events.add = this._openTooltip`) 때문에 **두 순서 모두
permanent 툴팁이 열린다**. `group: map` 을 주는 테스트들이 그것을 태운다. 그러므로 이 항목은
**「문서의 거짓」이지 「회귀」가 아니다** — 그래도 고친다. ***정정문이 새 부패의 운반체가
된다***(§27-c): 다음 사람이 *"순서는 안 건드렸구나"* 로 읽고 재검증을 생략한다.
달라지는 것은 **태울 수 있는가**다.

### 2-b. ★하지 않는 것

- **분양·경매·POI·개발계획 마커는 건드리지 않는다** — 형제를 함께 꺼내면 회귀 면적만 커진다.
  ★단 **「결함이 실거래 전용」이라는 뜻이 아니다** — §3-2 대로 형제도 **실측 SURVIVED** 다. 별건으로 간다.
- **팝업 내용·색 팔레트·라벨 문구를 바꾸지 않는다.**
- 백엔드·계약·저장 변경 **0**.

---

## 3. ★검증하지 못한 것

1. **실브라우저 실측 없음** — jsdom 은 레이아웃·CSS 를 안 잰다. 마커가 **화면에 보이는지**는 배포 후.
2. **형제 마커는 여전히 무잠금** — ★**정정(적대 리뷰 MAJOR-4)**: 초판은 이것을 **「미측정」**
   이라 적었으나 **틀렸다. 실측했고 SURVIVED 였다**(2026-09-09):
   · 분양 `status` 를 `"미정"` 으로 고정 → **386파일 초록**(`npx vitest run components lib` · R2 재현: 3,534 green)
   · POI 색을 하나로 고정 → 같음
   ★**대조군**: 같은 도구·같은 스코프에서 실거래 축 변이는 **CAUGHT** 다 — 도구가 죽은 것이 아니다.
   ★**지금 구조로는 행위 검증이 불가능하다** — `presalePopupHtml`·`auctionPopupHtml` 은
   **export 조차 안 돼 있다**. 별건 PR 에서 `buildMarketMarker` 와 같은 형태로 꺼낸다.
   부채는 `SatongMultiMap.markerWiring.test.ts` 의 **`it.todo` 로 초록 안에** 있다(§C-13).
   ★초판은 이 `it.todo` 를 **산문으로만 약속하고 코드에 0건**이었다 — 리뷰가 산출물로 잡았다(§F-24).
3. **`bounds.extend` 무잠금** — ★**미측정이 아니라 실측 SURVIVED**(R2 MINOR-1):
   그 줄을 지우면 지도가 실거래 마커로 **fit 하지 않는데 228건 초록**이다. 이 PR 이 그 줄을
   건드리지 않았으므로 **선재 부채**로 남긴다(초록 안 `it.todo`). ★초판 §2-a 는 그것을
   *"누적 상태라 마커 하나의 관심사가 아니다"* 로 정당화했는데, **그 논법이 바로 `addTo` 에서
   기각당한 그 논법**이다 — 정당화를 지우고 부채로 적는다.
4. **전체 스코프(`npx vitest run`)로는 변이 판정이 안 난다** — 이 머신에서 430파일
   **4,037 passed · 실패 0** 인데 `[vitest-worker]: Timeout calling "onTaskUpdate"` 때문에
   **rc=1** 이라 도구가 `exit 13 / UNDECIDED` 를 낸다(R2 MINOR-4 실측). 증거를 낼 때는
   `components lib`(386파일) 또는 `components/map/__tests__`(32파일)을 쓴다.
5. §0 조회 신뢰도(볼트 훼손).

---

## 4. 되돌리기 경로

단일 PR revert. **프론트 함수 추출 + 락**뿐이며 계약·저장·백엔드 변경 **0**.

---

## 5. 잠금 — ★**진짜 Leaflet 으로 행위**

| 잠그는 명제 | 형태 |
|---|---|
| ★**두 모집단** | 같은 `item` 을 `commercial` entry / `land` entry 로 만들면 **팝업 유형과 마커 색이 둘 다 갈린다** |
| ★**동일성** | 팝업이 말하는 유형 = `entry.type` · 마커 `fillColor` = `entry.color` (**한 entry 에서 나온 짝**) |
| **크기 배선** | `item.count` 가 반지름에 실린다(상한 18) |
| **라벨** | 라벨 텍스트에 이름+가격이 실린다 |
| ★**레이어 부착**(MAJOR-1) | `group` 을 주면 `getLayers()` 가 0→1→2 로 는다 · **안 주면 안 붙인다**(대칭) |
| ★**라벨 버짓**(MAJOR-3) | 버짓 안=상시 · 버짓 밖=hover · **경계가 `<` 인가 `<=` 인가**까지 |
| ★**평당 우선**(MAJOR-2) | `pyeongFirst` 두 모집단이 **다른 라벨 문자열**을 낸다 |
| ★**전월세 모집단** | `kind:"rent"` 가 보증금 축을 그린다(매매만 태우면 절반이 샌다) |
| ★**순서 의존**(#1024) | `tooltip.options.interactive === true` — `bindPopup` 이 라벨보다 먼저여야 성립 |
| **점 클릭 격리** | `bubblingMouseEvents: false` 가 유지된다(지도 클릭으로 안 번진다) |
| **호출부 배선** | effect 가 `entry` 를 **통째로** 넘긴다(소스 락 — 약함을 명시) |

### ★변이 실측 — R1·R2 **두 라운드**

★**«N/N CAUGHT» 뒤에 «그 N 을 누가 골랐나»를 붙인다.** R1 후 내가 고른 6개는 **전부 함수 안
층**이었고 6/6 CAUGHT 였다. 그런데 독립 리뷰가 **한 층 위(호출부 `opts`)** 에 넣자
**8/8 SURVIVED** 였다 — 내가 고친 결함이 **한 칸 옮겨갔을 뿐**이었다.

| # | 변이 | R1 후 | R2 반영 후 |
|---|---|---|---|
| M1 | `addTo(opts.group)` → `void opts;` | CAUGHT | CAUGHT |
| M2 | 함수 안 `pyeongFirst` → `false` | CAUGHT | CAUGHT |
| M3 | 함수 안 `permanent: true` | CAUGHT | CAUGHT |
| M3b | 경계 `<` → `<=` | CAUGHT | CAUGHT |
| M4 | `interactive` → `false`(#1024) | CAUGHT | CAUGHT |
| M5 | 함수 안 `opts.kind` → `"trade"` | CAUGHT | CAUGHT |
| **R2-1** | **호출부** `ordinal: 0` 고정 | **SURVIVED** | **CAUGHT** |
| **R2-2** | **호출부** `typeLabelLimit: 999` | **SURVIVED** | **CAUGHT** |
| **R2-3** | **호출부** `pyeongFirst: false` 고정 | **SURVIVED** | **CAUGHT** |
| **R2-4** | **호출부** `kind: "trade"` 고정 | **SURVIVED** | **CAUGHT** |
| **R2-5** | 버짓 밖에 라벨을 **아예 안 붙인다** | **SURVIVED** | **CAUGHT** |
| **R2-6** | `pyeongFirst: !opts.pyeongFirst`(방향 반전) | **SURVIVED** | **CAUGHT** |
| **R2-8** | 대칭 테스트의 프로덕션 호출 삭제(공허성) | **SURVIVED** | **CAUGHT** |
| R2-7 | `bounds.extend` 제거 | SURVIVED | **SURVIVED**(§3-3 부채) |

기준선 초록 **222건**(스코프 `components/map/__tests__` · 32파일).

★**처방의 축**: 「호출부를 소스로 잠근다」가 아니라 **effect 자체를 태운다**.
`lib/leaflet-loader.ts` 가 CDN 이 아니라 **번들 `import("leaflet")`** 이라
`render(<SatongMultiMap …/>)` 만으로 **진짜 지도가 뜨고 마커가 DOM 에 그려진다**
(실측 — 형제 스모크의 *"CDN 이라 onload 가 발화하지 않는다"* 주석은 **낡았다**).
새 하네스 `components/map/__tests__/SatongMultiMap.marketEffectWiring.test.tsx` 가 **사용자가 보는 DOM**(마커 `path` ·
`.leaflet-tooltip` 텍스트)으로 네 축을 한 번에 잠근다.

★**내 픽스처가 한 축을 무력화했다**(실측): 전월세 그룹에 매매가를 안 실어서 `kind` 고정
변이가 **바꿀 것이 없어 SURVIVED** 했다. ***분기를 만들었으면 그 분기를 태우는 행이
픽스처에 있어야 한다*** — 가격 필드를 양쪽 다 싣자 CAUGHT 로 뒤집혔다.

★**닫지 못하는 것**: 실브라우저(§3-1) · **형제 마커**(§3-2) · **`bounds.extend`**(§3-3) — 셋 다 **미측정이 아니라 실측 SURVIVED** 다.
