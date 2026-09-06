import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api-client", () => ({ apiClient: { post: vi.fn(), get: vi.fn() } }));
import { apiClient } from "@/lib/api-client";
import {
  RADIUS_OPTIONS_M, fetchNearbyPresale, fetchPresaleModels, medianPerPyeong,
} from "../presale-comparables";

const post = apiClient.post as unknown as ReturnType<typeof vi.fn>;
const get = apiClient.get as unknown as ReturnType<typeof vi.fn>;

describe("분양사례 — 반경 선택 · 주택형별 분양가", () => {
  beforeEach(() => { post.mockReset(); get.mockReset(); });

  it("★반경 기본값을 3km 로 박지 않는다 — 지역에 따라 0건이다", () => {
    // 라이브 실측(마석우리 24개월): 3km 0건 · 5km 0건 · 10km 0건 · 15km 4건 · 20km 28건
    expect(RADIUS_OPTIONS_M).toContain(3000);
    expect(RADIUS_OPTIONS_M, "20km 선택지가 없으면 이 사업지에서 아무것도 못 본다")
      .toContain(20000);
    // ★단조 증가(선택지가 뒤섞이면 사용자가 못 읽는다)
    for (let i = 1; i < RADIUS_OPTIONS_M.length; i++) {
      expect(RADIUS_OPTIONS_M[i]).toBeGreaterThan(RADIUS_OPTIONS_M[i - 1]);
    }
  });

  it("★★공급면적 기준 평당가를 파생한다 — 서버가 안 준다", async () => {
    // 라이브 실측: 오남역 서희스타힐스 059.7153A · 공급 83.9533㎡ · 55,400만원
    get.mockResolvedValue({ models: [
      { house_ty: "059.7153A", supply_area_m2: "83.9533", price_man: 55400 },
    ]});
    const models = await fetchPresaleModels("2026000365", "2026000365");
    expect(models).toHaveLength(1);
    // 55,400 ÷ (83.9533 ÷ 3.305785) = 2,181만원/평
    expect(models[0].per_pyeong_man).toBe(2181);
    expect(medianPerPyeong(models)).toBe(2181);
  });

  it("★분양가 없는 주택형은 **지어내지 않는다**", async () => {
    get.mockResolvedValue({ models: [
      { house_ty: "A", supply_area_m2: "84", price_man: null },
      { house_ty: "B", supply_area_m2: null, price_man: 50000 },
      { house_ty: "C", supply_area_m2: "84", price_man: 60000 },
    ]});
    const models = await fetchPresaleModels("x", "y");
    expect(models[0].per_pyeong_man).toBeNull();
    expect(models[1].per_pyeong_man).toBeNull();
    expect(models[2].per_pyeong_man).toBeGreaterThan(0);
    // ★중앙값은 **산출 가능한 것만** 쓴다(null 을 0 으로 세면 값이 무너진다)
    expect(medianPerPyeong(models)).toBe(models[2].per_pyeong_man);
  });

  it("★목록과 상세는 다른 호출이다 — 목록에 분양가가 없다(실측)", async () => {
    post.mockResolvedValue({ items: [
      { house_manage_no: "1", pblanc_no: "1", name: "오남역 서희스타힐스",
        address: "경기도 남양주시 오남읍", distance_m: 10635 },
    ]});
    const { items } = await fetchNearbyPresale("경기도 남양주시 화도읍 마석우리 265-1", 20000);
    expect(items).toHaveLength(1);
    expect(items[0].distance_m).toBe(10635);
    // ★목록 단계에서는 분양가가 비어 있다 — 상세를 부르기 전에 값을 만들지 않는다
    expect(items[0].models).toEqual([]);
    expect(items[0].median_per_pyeong_man).toBeNull();
  });

  it("★빈 주소는 호출하지 않고, 실패 사유는 삼키지 않는다", async () => {
    const r1 = await fetchNearbyPresale("   ", 5000);
    expect(post).not.toHaveBeenCalled();
    expect(r1.note).toContain("주소");

    post.mockImplementationOnce(() => Promise.reject(new Error("502 Bad Gateway")));
    const r2 = await fetchNearbyPresale("주소", 5000);
    expect(r2.items).toEqual([]);
    expect(r2.note, "실패 사유가 화면까지 안 온다").toContain("502");
  });

  it("★평당 상수를 새로 만들지 않는다(formatters 정본)", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const src = fs.readFileSync(path.resolve(__dirname, "../presale-comparables.ts"), "utf8");
    const code = src.split("\n").map((l) => l.replace(/\/\/.*$/, "")).join("\n")
      .replace(/\/\*[\s\S]*?\*\//g, "");
    expect(/\b3\.30[0-9]*\b/.test(code), "평당 상수를 자기가 갖고 있다").toBe(false);
  });
});

describe("배선 — 수지 폼이 실제로 쓰는가", () => {
  it("★★수지 입력폼이 선택기를 렌더하고 분양가 칸에 꽂는다", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const src = fs.readFileSync(
      path.resolve(__dirname, "../../components/feasibility/ModuleInputForm.tsx"), "utf8");
    const code = src.split("\n").map((l) => l.replace(/\/\/.*$/, "")).join("\n")
      .replace(/\/\*[\s\S]*?\*\//g, "");

    // ① 렌더한다(만들고 안 부르면 소비처 0)
    expect(code, "선택기를 렌더하지 않는다 — 소비처 0").toContain("<PresaleComparablePicker");
    // ② ★고른 값이 **분양가 칸에 꽂힌다**(이름만 있고 값이 안 실리면 장식)
    const at = code.indexOf("<PresaleComparablePicker");
    const block = code.slice(at, at + 500);
    expect(block, "onPick 이 avg_sale_price_per_pyeong 을 안 바꾼다")
      .toContain("avg_sale_price_per_pyeong: won");
    // ③ ★근거를 남긴다
    // ★부분 문자열로 잠그면 `picked-basis-x` 같은 변형이 통과한다(실측 SURVIVED).
    //   **경계를 건다** — 따옴표까지 포함해 정확한 testid 를 요구한다.
    expect(code, "어느 사례에서 온 값인지 화면에 안 남는다").toContain('"picked-basis"');
    // ④ ★라벨이 **면적 기준**을 말한다(전용/공급 혼동이 이번 신고의 절반)
    expect(code, "분양가 라벨이 공급 기준임을 말하지 않는다").toContain("평당 분양가(공급)");
  });
});
