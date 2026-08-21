/**
 * 사통맵 **정직 배선·데드존** 소스 불변식 — R2 HIGH-2 봉합.
 *
 * ★왜 이 파일이 필요한가: R2가 이번 라운드의 프론트 봉합 3건(신뢰성 단서 배선 · 칩바
 *   데드존 재봉합 · 노후도 칩 데드존)을 **동시에 되돌리는 변이**를 넣었는데 vitest 1646건이
 *   **전건 통과**했다. 즉 "R1 지적을 봉합했다"는 주장 자체가 코드로 잠기지 않아, 다음 세션이
 *   무심코 되돌려도 CI 4게이트가 전부 초록이다.
 *
 * ★특히 데드존(`pointer-events`)은 **같은 자리에서 두 번 틀린** 지점이다:
 *   1차 — `pointer-events-auto`를 제거했으나 조상 체인이 전부 `auto`라 **no-op**(R1 HIGH-4)
 *   2차 — `pointer-events-none`을 직접 부여해 실제로 봉합
 *   CSS 상속이라는 미묘한 규칙에 의존하는 수정이라 회귀락 없이 두면 안 된다.
 *
 * ★한계를 밝힌다: 이건 **소스 수준 검사**이지 런타임 증명이 아니다(도구 자신이 그렇게 명시).
 *   실제 클릭 투과·배너 표시는 배포 후 사람이 확인해야 한다. 다만 "되돌리면 조용히 통과"는
 *   막는다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan, assertWiredThrough } from "@/lib/source-invariant";

/** apps/web 기준 상대 경로의 소스를 줄 배열로 읽는다(불변식용). */
function sourceLines(file: string): string[] {
  return readFileSync(resolve(process.cwd(), file), "utf-8").split("\n");
}

/** `pattern`에 처음 매치되는 줄 번호(1-indexed). 없으면 -1. */
function lineOf(lines: string[], pattern: RegExp): number {
  const i = lines.findIndex((t) => pattern.test(t));
  return i < 0 ? -1 : i + 1;
}

describe("정직 배선 — AVM 신뢰성 단서는 시세가 **있을 때도** 렌더된다", () => {
  it("★AVM 존재 가지에 단서 배너가 있다(빈 상태 가지에만 있으면 경고가 영영 안 뜬다)", () => {
    // 가장 위험한 단서("반경 필터 미적용")는 정의상 AVM이 **존재할 때** 붙는다.
    // 그래서 이 배너가 사라지면 사용자는 반경 보증 없는 시세를 경고 없이 본다.
    // ★불변식 설계 주의(2회 교정):
    //   1차 — `data-testid` **존재**만 검사 → 조건을 `{false ? (`로 바꿔도 통과(실측).
    //   2차 — **조건식 존재**를 검사 → 배너를 **빈 상태 가지로 이전**하면 조건 줄은 그대로
    //         남으므로 여전히 통과(실측). 그런데 **위치가 결함의 전부**였다 —
    //         R2-HIGH-1은 "조건이 없다"가 아니라 "조건이 빈 상태 가지에만 있다"였다.
    //   → 3차: **행 순서**로 잠근다. 배너는 AVM 가지 안, 즉
    //     `※ 참고 추정치` 줄보다 **앞**이고 빈 상태 문구 줄보다 **앞**이어야 한다.
    //   ★R4 지적(교체 ≠ 추가): 3차가 2차를 **교체**하는 바람에 조건 변조
    //     (`{false && results.avmCaveat ? (`)가 다시 통과했다 — 피처 플래그 도입이나
    //     조건 축소(`&& confidence < 0.5`)처럼 **현실적 등가물**이 있고, 후자는 하필
    //     고신뢰 케이스에서 경고를 지운다. 그래서 세 검사를 **함께** 건다:
    //     ①존재(아래 앵커 단언) ②조건(별도 assertWiredThrough) ③위치(행 순서).
    const lines = sourceLines("components/operations/MarketInsightsWorkspaceClient.tsx");
    const avmBranch = lineOf(lines, /\{results\?\.avm \? \(/);
    const banner = lineOf(lines, /data-testid="avm-caveat"/);
    const disclaimer = lineOf(lines, /※ 주변 아파트 실거래 평당가 가중평균/);
    const emptyState = lineOf(lines, /주변 아파트 실거래가 없어 시세를 추정할 수 없습니다/);

    expect(avmBranch, "AVM 가지 시작(`{results?.avm ? (`)을 찾지 못했다 — 스코프 갱신 필요")
      .toBeGreaterThan(0);
    expect(banner, "단서 배너(avm-caveat)가 사라졌다").toBeGreaterThan(0);
    expect(disclaimer, "AVM 가지의 면책 문구를 찾지 못했다 — 스코프 갱신 필요").toBeGreaterThan(0);
    expect(emptyState, "빈 상태 문구를 찾지 못했다 — 스코프 갱신 필요").toBeGreaterThan(0);

    // ★핵심: 배너가 AVM 가지 **안**에 있다 — **양쪽으로** 묶는다.
    //   ★자체 적발(insight-loop): 종전엔 상한(`banner < disclaimer`)만 걸어서, 배너를 파일
    //   앞쪽의 **무관한 위치**로 옮겨도 통과했다(실측: 1030행으로 이동해도 6/6 통과).
    //   "면책보다 앞이면 어디든"은 "AVM 가지 안"이 아니다 — 하한을 함께 건다.
    expect(banner, "단서 배너가 AVM 가지 **시작보다 앞**에 있다 — 다른 섹션으로 새어나갔다")
      .toBeGreaterThan(avmBranch);
    expect(banner, "단서 배너가 AVM 가지 밖으로 이동했다 — 위험한 단서가 다시 도달 불가능해진다")
      .toBeLessThan(disclaimer);
    expect(disclaimer, "AVM 가지가 빈 상태 가지보다 뒤에 있다 — 구조 가정이 깨졌다")
      .toBeLessThan(emptyState);

    // ★②조건 검사(R3에서 걸었다가 R4에서 교체돼 열렸던 것을 되살린다).
    //   조건이 `{false && ...}`나 `{flag && ...}`로 바뀌면 이 스코프가 0건 → 하드 실패.
    expect(() =>
      assertWiredThrough({
        file: "components/operations/MarketInsightsWorkspaceClient.tsx",
        scope: /\{results\.avmCaveat \? \(/,
        mustContain: "results.avmCaveat",
        minMatches: 1,
      }),
    ).not.toThrow();
  });

  it("★서버 단서를 페이로드에서 실제로 읽는다(필드 개명 시 조용히 끊기는 것 방지)", () => {
    expect(() =>
      assertWiredThrough({
        file: "components/operations/MarketInsightsWorkspaceClient.tsx",
        scope: /avmCaveat: payload\./,
        mustContain: "avm_caveat",
        minMatches: 1,
      }),
    ).not.toThrow();
  });
});

describe("침묵 데드존 — 표시 전용 오버레이가 지도 클릭을 삼키지 않는다", () => {
  it("★상단 칩바는 `pointer-events-none`이다 — 인터랙티브 자식이 0이므로", () => {
    // ★`pointer-events-auto`를 **빼는 것만으로는 no-op**이다(초깃값이 auto이고 조상 체인이
    //   전부 auto였다 — R1 HIGH-4에서 실제로 그렇게 틀렸다). `none`을 직접 걸어야 한다.
    expect(() =>
      assertWiredThrough({
        file: "components/precheck/SatongMapShell.tsx",
        // ★2026-08-17 — 스코프에서 `pointer-events-none` 과 `z-[380]` 을 **뺐다.**
        //   ①`z-[380]` 은 SSOT rung(`SATONG_UI_Z.badgeRow`)으로 옮겨 더 이상 클래스에 없다.
        //   ②종전 스코프는 `pointer-events-none` 을 **포함**했고 `mustContain` 도 같은 값이라
        //     "스코프가 단언을 함의"하는 형태였다. 탐지 자체는 `minMatches` 가 떠받쳤지만
        //     (속성을 지우면 스코프가 안 맞아 매치 0 → 실패), **실패 메시지가 원인을 오도**했다
        //     — "스코프가 어긋났다"(요소가 옮겨짐)와 "속성이 사라졌다"(데드존 복원)는 **처방이 다르다.**
        //   → 이제 스코프는 **슬롯 정체성만**(좌상단 칩바 레이아웃) 잡고, 단언은 속성이 한다.
        scope: /className="[^"]*absolute left-4 top-4 flex flex-wrap items-center gap-2"/,
        mustContain: "pointer-events-none",
        minMatches: 1,
      }),
    ).not.toThrow();
  });

  it("★개발여력 범례에 `pointer-events-auto`가 없다(표시 전용 카드)", () => {
    // ★R3-MED-1 교정 — 종전 스코프는 **텍스트 줄**(`개발여력 = ...`)이었고
    //   `pointer-events-auto`는 **그 위 className 줄**에 들어간다. 즉 검사 범위 밖이라
    //   데드존 복원 변이가 **통과했다**(실측). 바로 아래 #5에서 같은 함정을 적발해 파일에
    //   기록해놓고 형제 불변식에 그대로 남긴 것 — **전역 스윕 미완의 3회차 재발**이다.
    expect(() =>
      assertWiredThrough({
        file: "components/map/SatongMultiMap.tsx",
        scope: /className="w-fit max-w-\[240px\] rounded-xl/,
        mustContain: "max-w-[240px]",
        mustNotContain: "pointer-events-auto",
        minMatches: 1,
      }),
    ).not.toThrow();
  });

  it("★노후도 '건물 정보 없음' 칩에 `pointer-events-auto`가 없다(표시 전용)", () => {
    // ★이 도구는 **줄 단위**다. 텍스트 줄(`노후도 — 건물 정보 없음`)을 스코프로 잡으면
    //   `className=` 줄은 검사 범위 밖이라, 거기에 `pointer-events-auto`를 되살리는 변이가
    //   **통과했다**(실측). className 줄을 직접 스코프로 잡아야 한다.
    expect(() =>
      assertWiredThrough({
        file: "components/map/SatongMultiMap.tsx",
        scope: /className="inline-flex w-fit items-center gap-1 rounded-full bg-\[var\(--glass-bg-strong\)\]/,
        mustContain: "inline-flex",
        mustNotContain: "pointer-events-auto",
        minMatches: 1,
      }),
    ).not.toThrow();
  });
});

describe("VWorld 줌 하한 — 지도·타일 양쪽에 걸려 있다", () => {
  it("★지도 생성 옵션에 minZoom이 있다(없으면 z0까지 축소돼 전 타일 503)", () => {
    // 라이브 실측: z5 → 503 InvalidParameterValue/tilematrix · z6~z19 → 200.
    // ★역설적으로 규제/지적 WMS를 켜 두면 그쪽 minZoom:7이 하한을 올려 이 버그를 **가린다**
    //   — "레이어를 끄면 지도가 깨진다"는 반직관적 재현 조건이라 더더욱 잠가야 한다.
    expect(() =>
      assertWiredThrough({
        file: "components/map/SatongMultiMap.tsx",
        scope: /minZoom: VWORLD_TILE_MIN_ZOOM,/,
        mustContain: "VWORLD_TILE_MIN_ZOOM",
        minMatches: 2, // 지도 옵션 1 + 타일 레이어 1 — 한쪽만 있으면 하한이 새어나간다
      }),
    ).not.toThrow();
  });
});

describe("적응형 반경 — 조용히 넓히지 않는다(2026-08-21)", () => {
  // ★이 PR 이 스스로 선언한 원칙이 **코드로 잠기지 않으면** 다음 사람이 배너만 지운다.
  //   그러면 사용자는 10km 떨어진 거래를 '주변'으로 읽는다 — 결함을 고치면서 더 나쁜
  //   오도를 만드는 것이다. 그래서 요청 배선과 고지 배선을 **둘 다** 잠근다.
  //
  // ★한계를 밝힌다(이 파일 머리글과 동일): **소스 수준 검사**이지 런타임 증명이 아니다.
  //   배너가 실제 화면에 뜨는지는 배포 후 사람이 확인해야 한다. 다만 `__stripCommentsForScan`
  //   으로 주석을 걷어낸 뒤 보므로 **주석처리 변이에는 뚫리지 않는다**.
  const scan = (file: string) =>
    __stripCommentsForScan(readFileSync(resolve(process.cwd(), file), "utf-8"), file);

  it("지도 요청이 적응형 반경을 켠다 — 끄면 1km 고정으로 되돌아간다", () => {
    const src = scan("components/precheck/SatongMapShell.tsx");
    // 공허한 참 방지 — nearby-map 요청 자체가 있어야 이 단언이 의미를 가진다.
    expect(src).toContain("/zoning/nearby-map");
    expect(src).toContain("auto_expand_radius: true");
  });

  it("배너가 확대 사실을 고지한다 — 확대만 하고 말하지 않으면 오도가 된다", () => {
    const src = scan("components/map/SatongMultiMap.tsx");
    // ★타입 **선언**이 아니라 **소비**에 앵커한다 — 첫 매치를 잡으면 `radius_expanded?: boolean`
    //   선언줄에 걸려, 필드를 선언만 하고 아무도 안 쓰는 상태에서도 초록이 된다
    //   (이 저장소가 반복해 데인 "정의만 하고 소비처 0" 그 형태다).
    const i = src.indexOf("marketPayload.radius_expanded");
    expect(i, "확대 고지 분기가 사라졌다(선언만 남고 소비가 없다)").toBeGreaterThan(-1);
    const block = src.slice(i, i + 800);
    // 고지가 실제로 **배너 목록에 들어가야** 화면에 뜬다(변수만 읽고 버리면 무의미).
    expect(block).toContain("cutParts");
    // 요청값·유효값을 **둘 다** 보여야 무엇이 바뀌었는지 화면만으로 판별된다.
    expect(block).toContain("radius_requested_m");
    expect(block).toContain("radius_m");
  });

  it("★대조군 — 적응형은 지도만 켠다(탁상감정·시세 경로 오염 금지)", () => {
    // 사통맵 외의 nearby-map 소비처가 플래그를 켜면 그쪽 '반경 N 안' 고지가 거짓이 된다.
    for (const f of [
      "components/map/NearbyTransactionsMap.tsx",
      "components/market/ConversationalMarketPanel.tsx",
    ]) {
      expect(scan(f), `${f} 가 적응형을 켰다`).not.toContain("auto_expand_radius");
    }
  });
});
