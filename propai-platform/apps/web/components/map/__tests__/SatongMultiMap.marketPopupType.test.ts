/**
 * ★★사용자 신고③(2026-09-08) — 실거래 마커가 **무엇의 거래인지 말하지 않았다**.
 *
 * *"여기는 오피스 건축물인데 토지로 필지로 표시되고 인식되는건가?"*
 * 실측: 팝업 인자가 `(group, kind)` 둘뿐이었고 `kind` 는 **매매/전월세** 축이다. 유형은
 * 상위 카테고리에만 있었고, 렌더 루프가 `const { type … }` 로 **이미 꺼내 놓고도** 안 넘겼다.
 * ⇒ 유형을 아는 유일한 통로가 **마커 색**(대리 변수)이었다.
 *
 * ★★이 파일이 **소스 스캔이 아니라 산출물을 태우는** 이유: `SatongMultiMap` 엔 Leaflet 목이
 * 없어 effect 본체가 테스트에서 한 번도 안 돈다(2026-09-07 실측: 그 안의 `false` 변이가
 * 64파일 468건을 전부 통과). 그래서 팝업을 **순수 함수로 export 해** HTML 을 직접 검사한다.
 */
import { describe, expect, it } from "vitest";

import { marketPopupHtml, type SatongMarketGroup } from "@/components/map/SatongMultiMap";
import { MARKET_TRADE_TYPES, MARKET_TYPE_LABELS } from "@/lib/satong-map-layers";

/** 신고 스크린샷을 그대로 옮긴 픽스처 — 건물 속성(준공·층)과 토지 속성(용도지역)이 **섞여** 있다. */
const 신고그룹: SatongMarketGroup = {
  name: "화도읍 창현리 736-1",
  dong: "창현리",
  jibun: "736-1",
  lat: 37.6,
  lon: 127.3,
  count: 5,
  avg_area_m2: 32.4,
  avg_price_10k: 8250,
  min_price_10k: 8250,
  max_price_10k: 8250,
  build_year: 2012,
  land_use: "근린상업",
  distance_m: 199,
  deals: [
    { deal_date: "2026년 8월 21일", price_10k_won: 8250, area_m2: 33.0, floor: 8 },
  ] as SatongMarketGroup["deals"],
};

describe("★신고③ — 팝업이 「무엇의 거래인지」 말한다", () => {
  it("★★두 모집단 — **같은 그룹**이 유형에 따라 다른 이름을 낸다", () => {
    const 상업 = marketPopupHtml(신고그룹, "trade", "commercial");
    const 토지 = marketPopupHtml(신고그룹, "trade", "land");

    // 모집단 A — 신고 그대로의 상업업무용
    expect(상업).toContain("상업업무용");
    expect(상업).not.toContain("토지");

    // 모집단 B — ★A 만 재면 «항상 상업업무용» 도 만점이다.
    expect(토지).toContain("토지");
    expect(토지).not.toContain("상업업무용");
  });

  it("★★무날조 — 유형을 모르면 **아무것도 찍지 않는다**", () => {
    const 미상 = marketPopupHtml(신고그룹, "trade", "zzz-없는유형");
    const 무인자 = marketPopupHtml(신고그룹, "trade");
    for (const html of [미상, 무인자]) {
      // 「유형 미상」·「undefined」 같은 말을 지어내면 안 된다 — 모름을 유효값으로 표현하지 않는다.
      expect(html).not.toContain("undefined");
      expect(html).not.toContain("미상");
      // ★대조군 — 그래도 팝업 자체는 살아 있다(«전부 빈 문자열» 구현을 배제한다).
      expect(html).toContain("화도읍 창현리 736-1");
    }
  });

  it("★파생형 — **6종 전수**가 각자의 라벨을 낸다(어휘가 늘면 자동으로 감시망에)", () => {
    // ★공허 진리 가드 — 모집단이 비면 아래 루프가 아무것도 안 본다.
    expect(MARKET_TRADE_TYPES.length).toBeGreaterThanOrEqual(6);
    for (const t of MARKET_TRADE_TYPES) {
      expect(marketPopupHtml(신고그룹, "trade", t.key), t.key).toContain(t.label);
      // 라벨 출처가 파생 맵과 같아야 한다(두 벌 어휘 방지).
      expect(MARKET_TYPE_LABELS[t.key], t.key).toBe(t.label);
    }
  });

  it("★★전월세도 유형을 말한다 — 매매만 고치면 절반이 샌다", () => {
    const 월세 = marketPopupHtml(
      { ...신고그룹, avg_deposit_10k: 1000, avg_monthly_10k: 50 },
      "rent",
      "officetel",
    );
    expect(월세).toContain("오피스텔");
    // ★대조군 — 전월세 축 자체가 살아 있다(보증금 줄이 그려진다).
    expect(월세).toContain("보증금");
  });

  it("★교체가 아니라 **추가**다 — 기존 줄이 하나도 안 죽었다", () => {
    const html = marketPopupHtml(신고그룹, "trade", "commercial");
    for (const 조각 of [
      "화도읍 창현리 736-1", // 이름
      "창현리 736-1",        // 지번 줄
      "2012년 준공",          // 건물 속성
      "용도지역 근린상업",     // 토지 속성(★P9 — 정당한 데이터라 걷어내지 않는다)
      "선택 필지에서",         // 거리
      "최저",                 // 범위
      "㎡당",                 // 단가
      "8층",                  // 딜 행
    ]) {
      expect(html, 조각).toContain(조각);
    }
  });

  // ★부채를 초록 안에 남긴다(§C-13).
  it.todo(
    "마커 **라벨**에도 유형을 넣는다 — 지금은 이름+가격뿐이라 팝업을 열어야만 유형을 안다. " +
      "라벨 버짓·겹침 규약(labelPlan)을 함께 봐야 해서 이 PR 범위 밖",
  );
  it.todo(
    "「평균 N평」의 의미가 유형마다 다르다(건물=전용면적 / 토지=거래면적) — 유형을 적어 해석은 " +
      "가능해졌지만 라벨 자체는 여전히 같은 말로 다른 것을 가리킨다",
  );
});
