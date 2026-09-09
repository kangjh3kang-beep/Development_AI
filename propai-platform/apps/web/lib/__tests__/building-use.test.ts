import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  BUILDING_USE_CODES,
  BUILDING_USE_LABEL,
  buildingUseOptions,
  normalizeBuildingUse,
} from "@/lib/building-use";

const WEB = path.resolve(__dirname, "..", "..");

/** ★원천 목록을 **파일에서 읽는다** — 여기 손으로 옮겨 적으면 원천이 바뀔 때 조용히 갈린다. */
function readList(rel: string, re: RegExp): string[] {
  const src = fs.readFileSync(path.join(WEB, rel), "utf-8");
  const m = re.exec(src);
  if (!m) throw new Error(`원천 목록을 못 찾았다: ${rel} — 판정 불가`);
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

const SOURCES: Array<[string, () => string[]]> = [
  [
    "design-references.USES",
    () => readList("app/[locale]/(dashboard)/settings/design-references/page.tsx", /const USES = \[([^\]]+)\]/),
  ],
  [
    "DesignStudio._BUILDING_USE_OPTIONS",
    () => readList("components/design/DesignStudio.tsx", /_BUILDING_USE_OPTIONS = \[([^\]]+)\]/),
  ],
];

describe("건축물 용도 정본", () => {
  it("★코드와 라벨이 1:1 이고 중복이 없다", () => {
    expect(BUILDING_USE_CODES.length).toBeGreaterThanOrEqual(11); // 모집단 하한
    expect(new Set(BUILDING_USE_CODES).size).toBe(BUILDING_USE_CODES.length);
    const labels = BUILDING_USE_CODES.map((c) => BUILDING_USE_LABEL[c]);
    expect(labels.every(Boolean)).toBe(true);
    expect(new Set(labels).size).toBe(labels.length); // ★라벨이 겹치면 화면에서 구별 불가
  });

  it("★옵션은 정본에서 파생된다(두 번 적지 않는다)", () => {
    const opts = buildingUseOptions();
    expect(opts.map((o) => o.code)).toEqual([...BUILDING_USE_CODES]);
  });

  it("★모르는 값은 null 이다 — 유효값으로 둔갑시키지 않는다", () => {
    for (const bad of ["", "   ", "없는용도", "토지", "기타", null, undefined]) {
      expect(normalizeBuildingUse(bad as string | null), String(bad)).toBeNull();
    }
    // ★대조군 — 아는 값은 반드시 매핑된다(위 단언이 「전부 null」로 공허해지지 않게)
    expect(normalizeBuildingUse("공동주택")).toBe("apartment");
  });

  it("★경매·탄소 축의 항목은 **들어오지 않는다**(축을 섞지 않았음)", () => {
    // 그 목록에만 있던 것들 — 건축개요 용도가 아니다
    for (const outAxis of ["토지", "공장", "기타", "다세대", "주택", "hospital"]) {
      expect(normalizeBuildingUse(outAxis), outAxis).toBeNull();
    }
  });

  it("★실측된 동의어가 전부 정본으로 합쳐진다", () => {
    const pairs: Array<[string, string]> = [
      ["아파트", "apartment"],
      ["아파트/공동주택", "apartment"],
      ["오피스", "office"],
      ["상가", "retail"],
      ["지식산업센터/창고", "knowledge"],
      // 기존 영문 value
      ["townhouse", "rowhouse"],
      ["single_house", "detached"],
      ["commercial", "retail"],
      ["warehouse", "knowledge"],
    ];
    for (const [alias, code] of pairs) expect(normalizeBuildingUse(alias), alias).toBe(code);
  });

  it.each(SOURCES)("★원천 목록 %s 의 항목이 **전부** 정본으로 정규화된다", (_name, load) => {
    const list = load();
    expect(list.length, "원천 목록이 비었다 — 판정 불가").toBeGreaterThanOrEqual(5);
    const unmapped = list.filter((x) => normalizeBuildingUse(x) === null);
    expect(unmapped, "정본이 못 덮는 원천 항목").toEqual([]);
  });
});
