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
import { describe, expect, it } from "vitest";

import { assertWiredThrough } from "@/lib/source-invariant";

describe("정직 배선 — AVM 신뢰성 단서는 시세가 **있을 때도** 렌더된다", () => {
  it("★AVM 존재 가지에 단서 배너가 있다(빈 상태 가지에만 있으면 경고가 영영 안 뜬다)", () => {
    // 가장 위험한 단서("반경 필터 미적용")는 정의상 AVM이 **존재할 때** 붙는다.
    // 그래서 이 배너가 사라지면 사용자는 반경 보증 없는 시세를 경고 없이 본다.
    // ★불변식 설계 주의: `data-testid` 존재만 보면 **도달 가능성**을 잠그지 못한다.
    //   조건을 `{false ? (`로 바꾸는 변이에서 testid는 그대로 남아 통과했다(실측).
    //   그래서 **조건식 자체**를 스코프로 잡는다 — 조건이 사라지면 매치 0건 → 하드 실패.
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
        scope: /className="pointer-events-none absolute left-4 top-4 z-\[380\]/,
        mustContain: "pointer-events-none",
        minMatches: 1,
      }),
    ).not.toThrow();
  });

  it("★개발여력 범례에 `pointer-events-auto`가 없다(표시 전용 카드)", () => {
    expect(() =>
      assertWiredThrough({
        file: "components/map/SatongMultiMap.tsx",
        scope: /개발여력 = \(실효−현황\)\/실효 용적률/,
        mustContain: "개발여력",
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
