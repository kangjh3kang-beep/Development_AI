/**
 * 표본 셀렉터 배선 불변식 — 소비처가 정말 공용 셀렉터를 거치는지 고정한다.
 *
 * ## 왜 필요한가
 *
 * `/zoning/nearby-map` 의 `categories[*].groups` 는 성격이 다른 셋이 섞인 리스트다
 * (위치 확인 / 위치 개략(동 단위) / 위치 미확인). 이걸 그냥 순회해 평균·건수를 만들고
 * "반경 N" 라벨을 붙이면 거짓 진술이 된다. 2026-08-02 감사에서 소비처 6곳 중 4곳이
 * 이 상태였고, 그중 둘은 **가격 누산이 아니라 카운트 표시**라 어떤 lint 문법으로도
 * 걸리지 않았다(`NearbyTransactionsMap` 의 유형 칩, `SatongMultiMap` 의 로컬 재구현 셀렉터).
 *
 * ## 왜 소스 검사인가
 *
 * CI eslint 는 `--max-warnings` 미설정이라 경고 규칙이 아무것도 차단하지 않고, ast-grep 은
 * 이 저장소에 없다. 그리고 이 계약은 "런타임에 무엇이 일어나는가"가 아니라 **"어느 함수를
 * 거치는가"** 라는 정적 사실이라 행위 테스트로 닿기 어렵다(`source-invariant.ts` 의 한계 고백 참조).
 *
 * ## 스코프 설계 — 사슬로 묶는다
 *
 * 한 줄만 잠그면 우회가 쉽다. 누산 게이트(조건) → 게이트의 출처(판정) → 판정의 출처(셀렉터)
 * **3연쇄**를 각각 잠가, 어느 고리를 끊어도 실패하게 한다. 상한만 걸면 샌다 — 양쪽 결박.
 */

import { describe, it, expect } from "vitest";
import { assertWiredThrough } from "@/lib/source-invariant";

describe("표본 셀렉터 배선 불변식", () => {
  describe("MarketInsightsWorkspaceClient — 헤드라인·유형별 평균가", () => {
    it("가격 누산이 집계가능 게이트를 통과한다", () => {
      // 종전 결함: 가격 누산이 `dist === null` 분기보다 **위에** 있어, 반경 버킷에서 제외한
      //   그룹을 헤드라인 평균가에는 그대로 넣었다(호미곶 실측 산술 일치로 확정).
      assertWiredThrough({
        file: "components/operations/MarketInsightsWorkspaceClient.tsx",
        scope: /if \(g\.avg_price_10k/,
        mustContain: "aggregatable",
        minMatches: 1,
      });
    });

    it("집계가능 판정이 셀렉터 결과에서 나온다", () => {
      // 여기가 끊어지면 위 게이트는 이름만 남고 판정은 아무 근거 없이 true 가 될 수 있다.
      assertWiredThrough({
        file: "components/operations/MarketInsightsWorkspaceClient.tsx",
        scope: /const aggregatable\b/,
        mustContain: "locatedKeys.has",
        minMatches: 1,
      });
    });

    it("판정 집합이 공용 셀렉터로 만들어진다(로컬 재구현 금지)", () => {
      // ★`lat != null` 같은 자체 판정으로 되돌리는 변이를 여기서 막는다. 좌표가 있어도
      //   법정동 대표점이거나 다동 병합이면 그룹을 대표하지 않는데, 자체 판정은 그걸 모른다.
      assertWiredThrough({
        file: "components/operations/MarketInsightsWorkspaceClient.tsx",
        scope: /const locatedKeys\b/,
        mustContain: "selectLocatedGroups",
        mustNotContain: /g\.lat/,
        minMatches: 1,
      });
    });
  });

  describe("ConversationalMarketPanel — 평균·중앙값·월별추이", () => {
    it("거래 수집 순회가 셀렉터를 거친다", () => {
      assertWiredThrough({
        file: "components/market/ConversationalMarketPanel.tsx",
        scope: /for \(const g of /,
        mustContain: "selectLocatedGroups",
        minMatches: 1,
      });
    });

    it("표면 문구가 요청 radius 를 직접 조립하지 않는다", () => {
      // 종전엔 `주변 반경 ${(result.radius_m / 1000).toFixed(1)}km` 로 **요청값을 문자열에
      //   박아** 반경 필터 적용 여부와 무관하게 단언했다. 라벨은 표본 근거에서만 생성한다.
      assertWiredThrough({
        file: "components/market/ConversationalMarketPanel.tsx",
        // ★스코프는 **검사하려는 내용이 있는 줄**을 골라야 한다. `const summaryText` 로 잡으면
        //   선언 줄만 걸리고 문구는 다음 줄이라 항상 위반이 된다(도구가 줄 단위라서 — 기준선
        //   에서 바로 드러났다). 질의 보간이 있는 줄이 곧 문구 조립 줄이다.
        //   ★2차 교정: `${result.query}` 만으로는 무관한 채팅 제목 줄(389행)까지 걸린다.
        //   요약 문구는 질의를 **따옴표로 감싸** 인용하므로 그 형태로 구분한다.
        scope: /"\$\{result\.query\}"/,
        mustContain: /sampleScope|sample_label/,
        mustNotContain: /radius_m\s*\/\s*1000/,
        minMatches: 1,
      });
    });
  });

  describe("NearbyTransactionsMap — 유형 칩 건수", () => {
    it("칩 건수가 혼합 count 가 아니라 위치 확인분이다", () => {
      // ★이 소비처는 가격을 만지지 않아 "가격 누산 금지" 류 규칙에 **원리적으로 안 걸린다**.
      //   그런데 바로 위 헤더가 "반경 N"을 말하므로 혼합 건수를 찍으면 그 반경 주장과 결합해
      //   "반경 안에 N건"으로 읽힌다. 카운트 표시도 봉합 대상이다.
      // ★사슬 2링크 — 판정 출처와 소비를 각각 잠근다. 한 줄만 잠그면 리팩터로 줄이 나뉠 때
      //   스코프에서 빠져나간다(실제로 M-4 수정 중 이 검사가 그 상태를 잡았다 — 도구가 줄 단위).
      assertWiredThrough({
        file: "components/map/NearbyTransactionsMap.tsx",
        scope: /const chipBasis = /,
        mustContain: "selectLocatedGroups",
        minMatches: 1,
      });
      assertWiredThrough({
        file: "components/map/NearbyTransactionsMap.tsx",
        scope: /const count = /,
        mustContain: "chipBasis",
        minMatches: 1,
      });
    });

    it("개략 좌표분을 칩에 병기해 지도 마커와의 불일치를 설명한다", () => {
      // ★M-4 — 칩은 위치확인분만 세는데 마커는 개략분도 찍는다(기준이 다르다).
      //   설명이 없으면 "토지 0" 칩 아래에 토지 마커가 보이는 모순만 남는다.
      assertWiredThrough({
        file: "components/map/NearbyTransactionsMap.tsx",
        scope: /const approxOnMap = /,
        mustContain: "chipBasis.approximateCount",
        minMatches: 1,
      });
    });
  });

  describe("SatongMultiMap — 마커 표본", () => {
    it("마커 셀렉터를 로컬 재구현하지 않는다", () => {
      // 지도 마커는 "좌표가 있으면 찍는다"가 맞다(개략 좌표도 점으로는 유효) — 집계 기준과
      // **다르다**. 그래서 마커 전용 셀렉터를 쓰되, 판정이 두 곳에 흩어지지 않게 한다.
      assertWiredThrough({
        file: "components/map/SatongMultiMap.tsx",
        // ★`^\s*groups: ` 로 잡으면 **타입 선언**(`groups: SatongMarketGroup[];`)까지 걸려
        //   기준선에서 실패한다. 렌더 엔트리를 만드는 줄만 고른다(category 를 소비하는 줄).
        scope: /groups: .*category/,
        mustContain: "selectMappableGroups",
        mustNotContain: /!!g\.lat/,
        minMatches: 1,
      });
    });
  });

  describe("공용 셀렉터 자체", () => {
    it("집계용과 마커용 기준이 분리되어 있다", async () => {
      // 두 기준을 하나로 합치면(예: 마커도 located 만) 지도에서 데이터가 사라지거나,
      // 반대로 집계에 개략 좌표가 섞인다. 분리 자체가 계약이다.
      const mod = await import("@/lib/market/comparable-sample");
      expect(typeof mod.selectLocatedGroups).toBe("function");
      expect(typeof mod.selectMappableGroups).toBe("function");
      expect(mod.selectLocatedGroups).not.toBe(mod.selectMappableGroups);
    });
  });
});
