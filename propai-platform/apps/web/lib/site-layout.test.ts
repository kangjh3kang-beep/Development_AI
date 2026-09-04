/**
 * 배치도 파생 로직(W3) — 대안 선택·오버레이 구성의 순수함수 계약.
 *
 * 고정하는 계약:
 *   ① 대안 키는 (유형×각도) — kind만으로는 중복이라 토글 키가 될 수 없다
 *   ② 선택 키가 없으면 best → 첫 번째로 폴백하고, 유효하지 않은 키는 무시한다
 *   ③ ★ok:false거나 기하가 없으면 오버레이는 **null**(가짜 배치 금지)
 *   ④ 오버레이는 서버 기하를 **그대로** 통과시킨다(프론트가 도형을 만들지 않는다)
 */
import { describe, expect, it } from "vitest";

import {
  buildLayoutOverlay,
  resolveSelectedOption,
  siteLayoutOptionKey,
  type SiteLayoutOption,
  type SiteLayoutResult,
} from "@/lib/site-layout";

const GEO = (tag: string) => ({
  type: "Polygon",
  coordinates: [[[127, 37], [127.001, 37], [127.001, 37.001], [127, 37.001], [127, 37]]],
  _tag: tag,
} as unknown as SiteLayoutOption["buildings_geojson"] extends null ? never : any);

function option(kind: string, angle: number, extra: Partial<SiteLayoutOption> = {}): SiteLayoutOption {
  return {
    kind,
    angle_deg: angle,
    buildings: 3,
    floors: 5,
    height_m: 15,
    spacing_meaningful: true,
    spacing_m: 12,
    buildings_geojson: {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: { dong: 1, floors: 5 }, geometry: GEO(`${kind}${angle}`) }],
    },
    ...extra,
  };
}

const OK_RESULT: SiteLayoutResult = {
  ok: true,
  honest_notes: ["v1 한계: 축정렬 직사각형 동·균일 세트백·동지 일조 근사."],
  buildable_geojson: GEO("buildable"),
  buildable_area_sqm: 820,
  setback_m: 3,
  options: [option("판상형", 0), option("판상형", 30), option("탑상형", 0)],
  best: option("판상형", 30),
};

describe("siteLayoutOptionKey — 유형×각도", () => {
  it("① kind만으로는 구분되지 않는 대안을 각도까지 넣어 구분한다", () => {
    const a = siteLayoutOptionKey(option("판상형", 0));
    const b = siteLayoutOptionKey(option("판상형", 30));
    expect(a).not.toBe(b);
    // 같은 조합이면 같은 키(재조회로 순서가 바뀌어도 선택이 유지된다).
    expect(siteLayoutOptionKey(option("판상형", 0))).toBe(a);
  });
});

describe("resolveSelectedOption — 선택·폴백", () => {
  it("② 선택 키가 있으면 그 대안", () => {
    const picked = resolveSelectedOption(OK_RESULT, "탑상형@0");
    expect(picked?.kind).toBe("탑상형");
  });

  it("② 선택 키가 없으면 best로 폴백한다", () => {
    const picked = resolveSelectedOption(OK_RESULT, null);
    expect(siteLayoutOptionKey(picked!)).toBe("판상형@30");
  });

  it("② 유효하지 않은 키는 무시하고 best로 폴백한다(빈 화면 금지)", () => {
    const picked = resolveSelectedOption(OK_RESULT, "없는유형@999");
    expect(siteLayoutOptionKey(picked!)).toBe("판상형@30");
  });

  it("② best가 목록에 없으면 첫 번째로 폴백한다", () => {
    const picked = resolveSelectedOption(
      { ...OK_RESULT, best: option("중정형", 45) }, null,
    );
    expect(siteLayoutOptionKey(picked!)).toBe("판상형@0");
  });

  it("② 대안 0건이면 null(없는 대안을 만들지 않는다)", () => {
    expect(resolveSelectedOption({ ...OK_RESULT, options: [], best: null }, null)).toBeNull();
    expect(resolveSelectedOption(null, null)).toBeNull();
  });
});

describe("buildLayoutOverlay — ★가짜 배치 금지", () => {
  it("③ ok:false면 오버레이 null — **기하가 있어도** 그리지 않는다(가짜 배치 금지)", () => {
    // ★픽스처는 백엔드 실제 실패형태를 따른다: 서버는 `ok: bool(options)`이고 buildable_geojson은
    //   항상 낸다 → **동이 하나도 안 들어가는 필지**가 ok=false + 기하 보유다. 기하 없는
    //   픽스처를 쓰면 ok 검사를 지워도 결과가 같아 가드가 검증되지 않는다(변이로 실증).
    const noFit: SiteLayoutResult = {
      ok: false,
      honest_notes: ["세트백 적용 후 건축가능 영역에 표준 동이 들어가지 않습니다."],
      buildable_geojson: GEO("buildable"),
      buildable_area_sqm: 40,
      setback_m: 3,
      options: [],
      best: null,
    };
    expect(buildLayoutOverlay(noFit, null)).toBeNull();

    // 폴리곤 미확보(기하 자체가 없는) 실패형태도 동일하게 null.
    expect(
      buildLayoutOverlay(
        { ok: false, honest_notes: ["토지 경계(폴리곤) 데이터 미확보 — 배치도 산출 불가."], options: [], best: null },
        null,
      ),
    ).toBeNull();
  });

  it("③ ok:true인데 기하가 전혀 없으면 null", () => {
    expect(
      buildLayoutOverlay(
        { ok: true, options: [{ ...option("판상형", 0), buildings_geojson: null }], buildable_geojson: null },
        null,
      ),
    ).toBeNull();
  });

  it("③ null·undefined 입력은 null", () => {
    expect(buildLayoutOverlay(null, null)).toBeNull();
    expect(buildLayoutOverlay(undefined, null)).toBeNull();
  });

  it("④ 서버 기하를 그대로 통과시킨다(프론트가 도형을 만들지 않는다)", () => {
    const ov = buildLayoutOverlay(OK_RESULT, "탑상형@0");
    expect(ov).not.toBeNull();
    // 동일 참조 — 변형·재구성 없음.
    expect(ov!.buildable).toBe(OK_RESULT.buildable_geojson);
    expect(ov!.buildings).toBe(
      OK_RESULT.options!.find((o) => siteLayoutOptionKey(o) === "탑상형@0")!.buildings_geojson,
    );
  });

  it("④ 대안 전환 시 오버레이의 동 기하가 그 대안의 것으로 바뀐다(잔존 금지)", () => {
    const a = buildLayoutOverlay(OK_RESULT, "판상형@0");
    const b = buildLayoutOverlay(OK_RESULT, "탑상형@0");
    expect(a!.buildings).not.toBe(b!.buildings);
  });

  it("④ 건축가능 영역만 있고 대안 기하가 없어도 오버레이는 생성된다(세트백 밴드는 유효 정보)", () => {
    const ov = buildLayoutOverlay(
      { ...OK_RESULT, options: [{ ...option("판상형", 0), buildings_geojson: null }], best: null },
      null,
    );
    expect(ov?.buildable).toBe(OK_RESULT.buildable_geojson);
    expect(ov?.buildings).toBeNull();
  });
});


describe("buildLayoutOverlay — 정북 밴드(W3-b) 판정은 **서버를 따른다**", () => {
  const BAND = { type: "Polygon", coordinates: [[[0, 0]]] } as never;

  const RESULT = (over: Record<string, unknown> = {}) =>
    ({
      ok: true,
      buildable_geojson: { type: "Polygon", coordinates: [[[1, 1]]] },
      options: [{
        kind: "판상형", angle_deg: 0, buildings: 2, floors: 15, height_m: 45,
        spacing_meaningful: true, spacing_m: 30, total_units_est: 100,
        north_light_band_geojson: BAND, north_light_setback_m: 22.5,
      }],
      ...over,
    }) as never;

  it("★applies:true면 선택 대안의 밴드를 싣는다", () => {
    const o = buildLayoutOverlay(RESULT({ north_light: { applies: true } }), null);
    expect(o?.northLightBand).toBe(BAND);
  });

  it("★applies:false면 대안에 기하가 있어도 **싣지 않는다** — 화면이 용도지역을 다시 판정하지 않는다", () => {
    const o = buildLayoutOverlay(
      RESULT({ north_light: { applies: false, reason: "전용·일반주거지역에만 적용" } }), null,
    );
    expect(o?.northLightBand).toBeNull();
  });

  it("★north_light가 아예 없으면(구버전 응답·슬림 누락) 싣지 않는다(낙관 금지)", () => {
    const o = buildLayoutOverlay(RESULT(), null);
    expect(o?.northLightBand).toBeNull();
  });

  it("밴드만 있고 다른 기하가 없어도 오버레이를 만든다(제약은 보여준다)", () => {
    const o = buildLayoutOverlay(
      RESULT({
        north_light: { applies: true },
        buildable_geojson: null,
        options: [{ kind: "판상형", angle_deg: 0, buildings: 0, floors: 0, height_m: 0,
          spacing_meaningful: false, total_units_est: 0, north_light_band_geojson: BAND }],
      }),
      null,
    );
    expect(o).not.toBeNull();
    expect(o?.northLightBand).toBe(BAND);
  });
});
