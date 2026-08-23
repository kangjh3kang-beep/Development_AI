import { describe, it, expect } from "vitest";
import {
  effectiveLandAreaSqm,
  blendedFarPct,
  resolveLandArea,
  resolveParcelCount,
  isMultiParcel,
  hasParcelRows,
  landAreaBasisNote,
} from "./site-area";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";

// 테스트는 헬퍼가 읽는 필드(landAreaSqm/landAreaSqmTotal/parcelCount)만 의미가 있다.
// SiteAnalysisData의 나머지 필수 필드는 검증과 무관하므로 부분 객체로 구성한다.
function sa(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return partial as SiteAnalysisData;
}

// getZoningSpec 실측(kr-building-regulations ZONING_DB):
//   제1종일반주거=200 · 제2종일반주거=250 · 제3종일반주거=300 · 일반상업=1300
function parcel(zoneCode: string, areaSqm: number, i = 0) {
  return { pnu: `p${i}`, address: `필지${i}`, areaSqm, landCategory: "대", ownerType: "미확인", zoneCode };
}

describe("effectiveLandAreaSqm — 유효 대지면적(다필지 통합 우선)", () => {
  it("다필지: 통합면적(landAreaSqmTotal)을 우선 반환한다", () => {
    // 상도동 시나리오: 대표 236㎡인데 단일 분석이 landAreaSqm을 236으로 덮어써도
    // parcelCount>1 && landAreaSqmTotal>0 이면 통합 779㎡를 돌려줘야 한다.
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 236, landAreaSqmTotal: 779, parcelCount: 2 }),
    );
    expect(v).toBe(779);
  });

  it("단일필지: landAreaSqm을 그대로 반환한다", () => {
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 540, landAreaSqmTotal: null, parcelCount: 1 }),
    );
    expect(v).toBe(540);
  });

  it("parcelCount 미설정: 단일로 보고 landAreaSqm을 반환한다", () => {
    const v = effectiveLandAreaSqm(sa({ landAreaSqm: 312 }));
    expect(v).toBe(312);
  });

  it("미확보: 면적이 둘 다 없으면 null(0 강제 금지)", () => {
    expect(effectiveLandAreaSqm(sa({ landAreaSqm: null }))).toBeNull();
    expect(effectiveLandAreaSqm(null)).toBeNull();
    expect(effectiveLandAreaSqm(undefined)).toBeNull();
  });

  it("다필지인데 통합면적이 비정상(0/null)이면 단일/대표(landAreaSqm)로 폴백한다", () => {
    // 통합 메타가 아직 안 들어왔거나 0이면 통합을 신뢰하지 않고 landAreaSqm 사용.
    expect(
      effectiveLandAreaSqm(
        sa({ landAreaSqm: 236, landAreaSqmTotal: 0, parcelCount: 2 }),
      ),
    ).toBe(236);
    expect(
      effectiveLandAreaSqm(
        sa({ landAreaSqm: 236, landAreaSqmTotal: null, parcelCount: 2 }),
      ),
    ).toBe(236);
  });

  it("단일필지에서 통합면적이 우연히 있어도(파셀1) 통합을 쓰지 않는다", () => {
    // parcelCount=1이면 다필지가 아니므로 landAreaSqm 우선(통합 메타 잔류 영향 차단).
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 400, landAreaSqmTotal: 779, parcelCount: 1 }),
    );
    expect(v).toBe(400);
  });
});

describe("blendedFarPct — 유효 용적률 상한(다필지=면적가중평균)", () => {
  it("단일필지: 대표 용도지역 상한을 그대로 반환한다", () => {
    expect(blendedFarPct(sa({ zoneCode: "제2종일반주거지역" }))).toBe(250);
  });

  it("다필지: 필지별 용적률을 면적가중평균한다(백엔드 _blended_far 미러)", () => {
    // 1000㎡ 제1종(200) + 1000㎡ 일반상업(1300) → (200*1000+1300*1000)/2000 = 750
    const v = blendedFarPct(
      sa({
        parcelCount: 2,
        parcels: [parcel("제1종일반주거지역", 1000, 1), parcel("일반상업지역", 1000, 2)] as never,
      }),
    );
    expect(v).toBe(750);
  });

  it("★혼합지에서 대표필지값과 확연히 다르다(P0 회귀 방지)", () => {
    // 대표(첫 필지)만 보면 200이지만, 상업이 섞이면 가중평균은 그보다 크다.
    // 통합면적 × 대표FAR(200) 이 아니라 가중FAR 을 써야 함을 못박는다.
    const v = blendedFarPct(
      sa({
        parcelCount: 2,
        parcels: [parcel("제1종일반주거지역", 500, 1), parcel("일반상업지역", 1500, 2)] as never,
      }),
    );
    // (200*500 + 1300*1500)/2000 = (100000+1950000)/2000 = 1025
    expect(v).toBe(1025);
    expect(v).not.toBe(200); // 대표필지값이 아님
  });

  it("면적 일부 누락 시 단순평균으로 폴백한다", () => {
    // 한 필지 면적이 0 → 단순평균 (200+300)/2 = 250
    const v = blendedFarPct(
      sa({
        parcelCount: 2,
        parcels: [parcel("제1종일반주거지역", 0, 1), parcel("제3종일반주거지역", 1000, 2)] as never,
      }),
    );
    expect(v).toBe(250);
  });

  it("용도지역을 하나도 못 읽으면 null(무목업 — 0 강제 금지)", () => {
    expect(blendedFarPct(sa({ parcelCount: 2, parcels: [] as never }))).toBeNull();
    expect(blendedFarPct(sa({}))).toBeNull();
  });

  it("다필지지만 필지 zoneCode 가 전무하면 대표 zoneCode 로 폴백한다", () => {
    const v = blendedFarPct(
      sa({
        zoneCode: "제2종일반주거지역",
        parcelCount: 2,
        parcels: [parcel("", 500, 1), parcel("", 500, 2)] as never,
      }),
    );
    expect(v).toBe(250); // 대표 폴백
  });
});


/**
 * ★기준 SSOT 계약(R1) — 두 모집단이 **갈린 상태**를 픽스처로 만든다.
 *
 * 왜 이렇게 쓰는가: 이 저장소에서 반복된 실패는 "픽스처가 두 모집단을 안 가르는" 것이었다.
 * parcelCount 와 parcels.length 가 **같은 값**인 픽스처만 쓰면, 판정 배선을 끊어도 결과가
 * 같아서 테스트가 초록으로 남는다. 아래는 전부 **둘이 다른** 상태다.
 *
 * 아래 상수(REP/TOTAL)는 **동작을 재기 위한 픽스처**다 — 특정 사용자 화면의 관측 기록이 아니다
 * (실수 #39: 인계 서술을 실측으로 승격시켰다가 정정). 이 파일이 잠그는 것은
 * *"두 모집단이 갈린 입력에 리졸버가 무엇을 돌려주는가"* 이고, 그건 여기서 직접 태워 확인한다.
 * 형태 자체(헤더는 parcelCount 로 "N필지", 본문은 parcels 가 비어 "단일 필지")는
 * #772·#773 이 보고·봉합한 계열이다.
 */
describe("기준 SSOT — 필지 수·면적 기준(basis)", () => {
  const TOTAL = 164823;
  const REP = 3836;

  it("[A] parcelCount=7 · parcels=[] — 목록이 비어도 다필지로 보고 통합면적을 쓴다", () => {
    const r = resolveLandArea(sa({ parcelCount: 7, parcels: [], landAreaSqm: REP, landAreaSqmTotal: TOTAL }));
    expect(r.valueSqm).toBe(TOTAL);
    expect(r.basis).toBe("integrated");
    expect(r.parcelCount).toBe(7);
    // ★두 모집단이 갈렸다는 사실 자체가 화면에 전달돼야 한다(침묵 금지).
    expect(r.populationsDisagree).toBe(true);
  });

  it("[B] parcelCount 부재 · parcels 7개 — 목록만 있어도 다필지다(종전엔 대표 3,836㎡ 로 축약됐다)", () => {
    const r = resolveLandArea(
      sa({ parcels: [parcel("1R", 23546, 0), parcel("1R", 23546, 1), parcel("1R", 23546, 2),
           parcel("1R", 23546, 3), parcel("1R", 23546, 4), parcel("1R", 23546, 5), parcel("1R", 23546, 6)],
           landAreaSqm: REP, landAreaSqmTotal: TOTAL }),
    );
    // ★이 한 줄이 회귀 락이다 — 판정을 parcelCount 단독으로 되돌리면 REP(3836)이 나와 죽는다.
    expect(r.valueSqm).toBe(TOTAL);
    expect(r.basis).toBe("integrated");
    expect(r.parcelCount).toBe(7);
    // 한쪽이 아직 없는 것은 '불일치'가 아니라 '미완' — 거짓 경고를 내지 않는다.
    expect(r.populationsDisagree).toBe(false);
  });

  it("다필지인데 통합면적 미확보 — 값은 대표면적이되 강등을 basis 로 고지한다(무회귀·무침묵)", () => {
    const r = resolveLandArea(sa({ parcelCount: 7, parcels: [], landAreaSqm: REP, landAreaSqmTotal: null }));
    expect(r.valueSqm).toBe(REP); // 값은 그대로(하류 무회귀)
    expect(r.basis).toBe("representative"); // 그러나 '대표필지 면적'임을 말한다
  });

  it("단일필지 — basis=single, 통합 라벨을 붙이지 않는다", () => {
    const r = resolveLandArea(sa({ parcelCount: 1, parcels: [parcel("1R", REP)], landAreaSqm: REP }));
    expect(r.basis).toBe("single");
    expect(r.parcelCount).toBe(1);
    expect(r.populationsDisagree).toBe(false);
  });

  it("면적 미확보 — 0 으로 채우지 않는다(무날조)", () => {
    const r = resolveLandArea(sa({ parcelCount: 3, parcels: [], landAreaSqm: null, landAreaSqmTotal: null }));
    expect(r.valueSqm).toBeNull();
    expect(r.basis).toBe("none");
  });

  it("선택 해제(parcelCount=0 · parcels=[]) — 단일로 보고 통합면적 잔류값을 되살리지 않는다", () => {
    const r = resolveLandArea(sa({ parcelCount: 0, parcels: [], landAreaSqm: REP, landAreaSqmTotal: TOTAL }));
    expect(r.parcelCount).toBe(0);
    expect(r.valueSqm).toBe(REP);
    expect(r.basis).toBe("single");
  });

  it("★두 질문은 서로 다른 답을 낸다 — 사실 판정(isMultiParcel) vs 목록 보유(hasParcelRows)", () => {
    const headerOnly = sa({ parcelCount: 7, parcels: [], landAreaSqm: REP, landAreaSqmTotal: TOTAL });
    // 부지는 다필지다 — 목록이 아직 안 왔다고 "단일 필지입니다"라고 단언하면 안 된다(#773).
    expect(isMultiParcel(headerOnly)).toBe(true);
    // 그러나 필지별 행을 보내야 하는 경로는 아직 보낼 것이 없다.
    expect(hasParcelRows(headerOnly)).toBe(false);
    // 이 픽스처에서 두 판정이 같은 값이면 락이 공허해진다 — 다름을 명시적으로 못박는다.
    expect(isMultiParcel(headerOnly)).not.toBe(hasParcelRows(headerOnly));
  });

  it("blendedFarPct 는 목록 보유(hasParcelRows)를 따른다 — 빈 배열로 가중평균을 시도하지 않는다", () => {
    // parcelCount=7 이지만 목록이 없으므로 가중 불가 → 대표 용도지역 상한(1R=200)으로 정직 폴백.
    expect(blendedFarPct(sa({ parcelCount: 7, parcels: [], zoneCode: "1R" }))).toBe(200);
  });

  it("resolveParcelCount — 두 모집단 중 큰 쪽을 믿는다(축약 방향의 피해가 더 크다)", () => {
    expect(resolveParcelCount(sa({ parcelCount: 7, parcels: [] }))).toBe(7);
    expect(resolveParcelCount(sa({ parcels: [parcel("1R", 1), parcel("1R", 1)] }))).toBe(2);
    expect(resolveParcelCount(sa({}))).toBe(0);
    expect(resolveParcelCount(null)).toBe(0);
  });
});

describe("landAreaBasisNote — 기준 고지문(화면 문구 SSOT)", () => {
  const TOTAL = 164823;
  const REP = 3836;

  it("통합면적 — 몇 필지 기준인지 말한다", () => {
    const note = landAreaBasisNote(
      sa({ parcelCount: 2, parcels: [parcel("1R", 100, 0), parcel("1R", 200, 1)],
           landAreaSqm: REP, landAreaSqmTotal: TOTAL }),
    );
    expect(note).toBe("통합 2필지 기준");
  });

  it("★필지 수는 세는데 목록이 없다 — 그 사실을 덧붙인다(#773 의 '단일 필지입니다' 단언 재발 방지)", () => {
    const note = landAreaBasisNote(
      sa({ parcelCount: 7, parcels: [], landAreaSqm: REP, landAreaSqmTotal: TOTAL }),
    );
    expect(note).toContain("통합 7필지 기준");
    expect(note).toContain("필지 목록은 아직 수신되지 않아");
  });

  it("★다필지인데 통합면적 미확보 — '대표필지 1곳의 면적'임을 명시한다(침묵 금지)", () => {
    const note = landAreaBasisNote(
      sa({ parcelCount: 7, parcels: [], landAreaSqm: REP, landAreaSqmTotal: null }),
    );
    expect(note).toContain("대표필지 1곳의 면적");
    expect(note).toContain("7필지 통합면적은 아직 확보되지 않았습니다");
  });

  it("단일필지 — 군더더기를 붙이지 않는다(null)", () => {
    expect(landAreaBasisNote(sa({ parcelCount: 1, landAreaSqm: REP }))).toBeNull();
  });

  it("면적 미확보 — 고지문 없음(없는 값에 라벨을 붙이지 않는다)", () => {
    expect(landAreaBasisNote(sa({ parcelCount: 7, parcels: [], landAreaSqm: null }))).toBeNull();
    expect(landAreaBasisNote(null)).toBeNull();
  });

  it("★대조군 — 단일필지와 다필지가 **다른 문구**를 낸다(어느 상태든 같은 문구면 락이 공허하다)", () => {
    const single = landAreaBasisNote(sa({ parcelCount: 1, landAreaSqm: REP }));
    const multi = landAreaBasisNote(
      sa({ parcelCount: 2, parcels: [parcel("1R", 1, 0), parcel("1R", 2, 1)],
           landAreaSqm: REP, landAreaSqmTotal: TOTAL }),
    );
    const degraded = landAreaBasisNote(sa({ parcelCount: 2, parcels: [], landAreaSqm: REP }));
    expect(new Set([single, multi, degraded]).size).toBe(3);
  });
});
