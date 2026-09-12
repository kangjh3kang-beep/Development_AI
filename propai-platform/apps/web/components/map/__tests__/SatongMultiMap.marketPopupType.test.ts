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
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

import {
  marketPopupHtml,
  marketTypeLabelFromCategoryKey,
  type SatongMarketGroup,
} from "@/components/map/SatongMultiMap";
import { MARKET_TRADE_TYPES } from "@/lib/satong-map-layers";

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

  it("★★무날조 — 유형을 모르면 **아무것도 찍지 않는다**(명제를 그대로 단언한다)", () => {
    // ★★적대 리뷰 MAJOR-3: 초판은 `not.toContain("undefined")` · `not.toContain("미상")` 로
    //   **낱말 두 개만** 금지했다. 그래서 «모르는 키를 **그대로** 찍는» 변이
    //   (`MARKET_TYPE_LABELS[k] ?? k`)가 **SURVIVED** 했다 — 미상 키가 굵은 배지로 렌더되는데도.
    //   ⇒ 선언한 명제는 «아무것도 안 찍는다» 이므로 **바이트 동일성**으로 단언한다.
    const 없음 = marketPopupHtml(신고그룹, "trade", undefined);
    for (const 모르는키 of ["zzz-없는유형", "constructor", "__proto__", "toString", ""]) {
      // ★`constructor`·`__proto__`·`toString` — `Object.fromEntries` 산물은 **프로토타입 체인이
      //   살아 있어** 이 키들이 truthy 를 돌려준다(실증: `Function`). 자기 키만 보게 좁혔다.
      expect(marketPopupHtml(신고그룹, "trade", 모르는키), 모르는키).toBe(없음);
    }
    // ★공허 진리 가드 — «전부 빈 문자열» 구현을 배제한다(팝업 자체는 살아 있다).
    expect(없음).toContain("화도읍 창현리 736-1");
    // ★그리고 아는 키는 **달라야** 한다 — 위 동일성이 «항상 같다» 로 만족되면 안 된다.
    expect(marketPopupHtml(신고그룹, "trade", "commercial")).not.toBe(없음);
  });

  it("★파생형 — **6종 전수**가 각자의 라벨을 낸다(어휘가 늘면 자동으로 감시망에)", () => {
    // ★공허 진리 가드 — 모집단이 비면 아래 루프가 아무것도 안 본다.
    expect(MARKET_TRADE_TYPES.length).toBeGreaterThanOrEqual(6);
    for (const t of MARKET_TRADE_TYPES) {
      expect(marketPopupHtml(신고그룹, "trade", t.key), t.key).toContain(t.label);
      // ★★초판은 여기서 `expect(MARKET_TYPE_LABELS[t.key]).toBe(t.label)` 을 했는데,
      //   그 맵이 `Object.fromEntries(MARKET_TRADE_TYPES.map(...))` 산물이라 **구조적으로 항상 참**
      //   = 장식이었다(적대 리뷰 m3). 걷어냈다. 「두 벌 어휘 방지」는 **아래 소스 락**이 맡는다.
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

  describe("★★배선 락 — 유형 인자가 **필수**다(호출부가 빼면 tsc 가 잡는다)", () => {
    // ★★이 describe 가 있는 이유: 초판은 `marketType?` 였고, **호출부에서 인자를 빼는 변이가
    //   SURVIVED** 했다. 함수는 잠갔는데 **배선 층이 무잠금**이라는 반복 결함이다.
    //   그 배선은 Leaflet effect 안이라 목이 없는 이 파일에서는 **행위로 못 태운다** →
    //   **타입 계약**으로 옮겼다: 필수 인자면 누락이 **TS2554** 이고 CI 타입체크가 잡는다
    //   (실증: 호출부에서 인자를 빼니 `error TS2554: Expected 3 arguments, but got 2`).
    //
    // ★★그리고 **내 첫 락이 틀렸다**: `marketPopupHtml.length === 3` 으로 잠갔는데
    //   TypeScript 의 `?` 는 JS 로 **기본값 없는 평범한 인자**가 되어 `length` 가 **그대로 3**
    //   이다. 즉 판별력 0이었고 변이가 그것을 드러냈다(«대리 변수를 잠그면 속성은 안 잠긴다»).
    //   → **선언 자체**를 본다. 소스 락이라 약하지만, 주석은 `__stripCommentsForScan` 으로
    //     걷어내므로 **주석처리 변이에는 뚫리지 않는다**(그 헬퍼는 네 번 뚫린 이력을 안고 고쳐진 정본).
    const scan = (file: string) =>
      __stripCommentsForScan(readFileSync(resolve(process.cwd(), file), "utf-8"), file);

    it("선언이 `marketType?` 로 되돌려지지 않았다 — 되돌리면 호출부 누락이 **조용해진다**", () => {
      const src = scan("components/map/SatongMultiMap.tsx");
      const i = src.indexOf("export function marketPopupHtml");
      // ★공허 진리 가드 — 선언을 못 찾으면 아래 단언이 «없어서 통과» 가 된다.
      expect(i, "선언을 못 찾았다 — 조회기 사망(리팩토링됐나?)").toBeGreaterThan(-1);
      const sig = src.slice(i, i + 220);

      // ★양성 — 필수 형태가 실재한다(대조군: 이게 없으면 아래 음성이 공허하다).
      expect(sig, `시그니처: ${sig}`).toContain("marketType: string | undefined");
      // ★음성 — 선택적 형태로 되돌아가지 않았다.
      expect(sig).not.toContain("marketType?");
      // ★★그리고 **기본값 붙이기**도 막는다(적대 리뷰 M7): `= undefined` 를 붙이면
      //   `TS2554` 가 **사라진다**(실증: 붙이고 호출부 인자를 빼니 TS2554 0건).
      //   즉 «진짜 게이트는 tsc» 가 **한 토큰으로 무력화**된다.
      expect(sig, "기본값이 붙으면 호출부 누락이 tsc 를 통과한다").not.toMatch(/marketType[^,)]*=\s*undefined/);
    });

    it("★팝업 조립부가 유형을 **entry 에서** 넘긴다(effect 호출부 아님 — 이름을 정직하게)", () => {
      // ★★2026-09-09 R2 정정 — 이 락의 이름은 «호출부»였는데, 리팩토링 후 이 자리는
      //   **`buildMarketMarker` 함수 본문 안**이다. 진짜 effect 호출부(`:3029`)는 이 락의
      //   **시야 밖**이고, 그쪽은 이제 `SatongMultiMap.marketEffectWiring.test.tsx` 가
      //   **DOM 으로** 태운다. ***이름과 명제가 어긋나면 다음 사람이 덮였다고 오독한다.***
      // ★★2026-09-09 정정 — 이 락이 호출 모양을 **리터럴**(`marketPopupHtml(item, kind, type)`)로
      //   봤는데, 마커 생성이 `buildMarketMarker` 로 추출되면서 **깨졌다.**
      //   계약(«호출부가 유형을 실제로 넘긴다»)은 **그대로**이므로 ***깨진 쪽은 락이다*** —
      //   코드를 되돌리지 않고 락을 고친다(볼트 `2026-09-03_락이_리팩토링에_깨지면…` 그대로).
      // ★그리고 **모양이 아니라 명제**로 좁힌다: 3번째 인자가 **entry 에서 온 유형**이어야 한다.
      const src = scan("components/map/SatongMultiMap.tsx");
      const i = src.indexOf("marketPopupHtml(item,");
      expect(i, "팝업 호출부를 못 찾았다 — 조회기 사망").toBeGreaterThan(-1);
      const call = src.slice(i, src.indexOf(")", i) + 1);
      // ★양성 — 유형 인자가 실린다(어디서 오든 «entry 의 type» 이어야 한다).
      expect(call, `호출부: ${call}`).toMatch(/marketPopupHtml\(item,\s*[\w.]+,\s*entry\.type\)/);
      // ★음성 — 리터럴로 못 박지 않았다(그것이 #1018 이 잡은 「모든 마커가 아파트」다).
      expect(call).not.toMatch(/marketPopupHtml\(item,\s*[\w.]+,\s*["'`]/);
    });

    it("★두 벌 어휘 방지 — 라벨을 **파생 맵**에서 얻는다(인라인 리터럴 맵 금지)", () => {
      // ★★적대 리뷰 M3: 라벨을 인라인 리터럴 맵에서 얻는 변이가 **SURVIVED** 했다.
      //   값이 같으면 행위로는 못 가른다 — 그래서 **출처**를 본다(소스 락이라 약하다).
      //   이 저장소는 두 벌 어휘로 이미 두 번 데였다(`boundary`↔`parcel-boundary` ·
      //   `hybrid`↔`aerial`) — 그래서 「출처 하나」가 계약이다.
      const src = scan("components/map/SatongMultiMap.tsx");
      const i = src.indexOf("const typeLabel =");
      expect(i, "배지 조립부를 못 찾았다 — 조회기 사망").toBeGreaterThan(-1);
      const block = src.slice(i, i + 300);
      // ★★「이름이 있다」로 보면 안 된다 — 바로 위 `hasOwnProperty.call(MARKET_TYPE_LABELS, …)`
      //   가드 줄에 그 이름이 **이미 있어서**, 값을 인라인 리터럴 맵에서 얻는 변이가 **SURVIVED**
      //   했다(실측). ***이름이 있는 것과 그것을 쓰는 것은 다르다.***
      //   → **실제 조회식**을 본다.
      expect(block, `배지 조립부: ${block.slice(0, 200)}`).toContain("? MARKET_TYPE_LABELS[marketType]");
      // ★음성 — 인라인 리터럴 맵으로 갈아끼우지 않았다(두 벌 어휘의 씨앗).
      expect(block).not.toMatch(/\?\s*\(\{\s*apt\s*:/);
    });
  });

  describe("★★형제 표면 — 「위치 미확인」 목록도 유형을 말한다(적대 리뷰 MAJOR-4)", () => {
    // ★팝업과 **완전히 같은** «값은 손에 있는데 안 찍는다» 가 형제에도 있었다. 그리고 그 목록이
    //   특히 중요하다 — 같은 파일 실측 주석: *"56그룹 476건 중 토지매매만 362건"*.
    //   지도에 못 찍는 거래가 나타나는 **유일한 표면**이다.
    it("★★두 모집단 — 카테고리 키가 유형을 가른다", () => {
      expect(marketTypeLabelFromCategoryKey("land_trade")).toBe("토지");
      expect(marketTypeLabelFromCategoryKey("commercial_trade")).toBe("상업업무용");
      // ★전월세 접미도 같은 규칙(백엔드가 `{tkey}_rent` 로도 만든다)
      expect(marketTypeLabelFromCategoryKey("officetel_rent")).toBe("오피스텔");
    });

    it("★파생형 — **6종 전수**가 `_trade` 접미에서 자기 라벨을 낸다", () => {
      expect(MARKET_TRADE_TYPES.length).toBeGreaterThanOrEqual(6); // 공허 진리 가드
      for (const t of MARKET_TRADE_TYPES) {
        expect(marketTypeLabelFromCategoryKey(`${t.key}_trade`), t.key).toBe(t.label);
      }
    });

    it("★★무날조 — 모르는 키·프로토타입 키는 **undefined**(팝업 배지와 같은 정책)", () => {
      for (const k of ["zzz_trade", "constructor_trade", "__proto__", "toString", ""]) {
        expect(marketTypeLabelFromCategoryKey(k), k).toBeUndefined();
      }
      // ★대조군 — 조회기가 살아 있다(아는 키는 값을 낸다).
      expect(marketTypeLabelFromCategoryKey("apt_trade")).toBe("아파트");
    });

    it("★접미가 없어도 동작한다 — 키 형태가 바뀌어도 조용히 죽지 않는다", () => {
      expect(marketTypeLabelFromCategoryKey("land")).toBe("토지");
    });
  });

  // ★부채를 초록 안에 남긴다(§C-13).
  // ★★2026-09-09 — 여기 있던 `it.todo` 두 건을 **갱신**한다(#1024). 그대로 두면 다음 사람이
  //   미수정으로 오독한다(§C-12) — 적대 리뷰가 그 방치를 지적했다.
  //   ① «라벨 클릭이 필지 팝오버로 샌다» → **고쳤다**(#1024). 그리고 그때 적은
  //      *"`bindSatongLabel` 은 **5개 레이어 공용**이라 별건"* 은 **거짓이었다** — 소비처는 **8곳**이다.
  //   ② «Leaflet 목이 필요하다» → **틀렸다.** 목은 필요 없었다 — `leaflet` 이 의존성에 선언돼 있고
  //      **jsdom 에서 그대로 돈다**(`lib/__tests__/satong-label-click.test.ts` 가 그 하네스를 쓴다).
  //      ★남은 것은 「목이 없다」가 아니라 **「이 파일의 effect 를 그 하네스로 아직 안 태웠다」**이다.
  it.todo(
    "`SatongMultiMap` 의 지도 effect 를 **진짜 Leaflet 하네스**로 태운다 — 배선 동일성 축" +
      "(호출부에서 `const type = \"apt\"` 로 바꿔치기해도 초록)이 아직 무잠금이다. " +
      "하네스는 이제 있다(#1024) — 목이 없어서가 아니라 아직 안 쓴 것이다",
  );

  it.todo(
    "마커 **라벨**에도 유형을 넣는다 — 지금은 이름+가격뿐이라 팝업을 열어야만 유형을 안다. " +
      "라벨 버짓·겹침 규약(labelPlan)을 함께 봐야 해서 이 PR 범위 밖",
  );
  it.todo(
    "「평균 N평」의 의미가 유형마다 다르다(건물=전용면적 / 토지=거래면적) — 유형을 적어 해석은 " +
      "가능해졌지만 라벨 자체는 여전히 같은 말로 다른 것을 가리킨다",
  );
});
