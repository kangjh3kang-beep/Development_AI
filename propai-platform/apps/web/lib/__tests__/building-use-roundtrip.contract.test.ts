/**
 * ★정본 코드가 **자기 자신으로 돌아오는가**, 그리고 어댑터가 **소비처의 키 도메인**을 쓰는가.
 *
 * 왜 이 파일이 따로 있나(2026-09-12 · 적대 리뷰가 런타임으로 잡은 결함 2건):
 *   ① `normalizeBuildingUse(정본코드)` 가 **11종 중 7종에서 null** 이었다 → 모달에서
 *      그 용도를 고르면 `if (next)` 가 거짓이라 **무언 실패**(오류도 토스트도 없다).
 *   ② 어댑터가 **한국어 라벨**을 공사비 소비처에 실어 **HIT 0/11** — 전 용도가
 *      아파트 단가로 접혔다(근생 180만 → 220만 = +22%).
 *
 * ★종전 락이 왜 못 잡았나 — **존재만 단언**했다:
 *      expect(codes).toContain("retail")        // 렌더된 option 이 있는가
 *      expect(got).toEqual({ … buildingUse: "공동주택" })  // ★틀린 값을 잠갔다
 *   《존재를 잠그면 행위는 안 잠긴다》. 그래서 여기서는 **전 코드를 실제로 태우고**,
 *   기대값을 **소비처 파일에서 파생**한다(내가 적은 문자열과 비교하면 그 자체가 순환이다).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  BUILDING_USE_CODES,
  BUILDING_USE_LABEL,
  __rawAliasToCode,
  normalizeBuildingUse,
} from "@/lib/building-use";
import { __codeToCostKey, toConstructionCostAreas } from "@/lib/building-overview-adapters";
import { emptyBuildingOverview, makeUseLine } from "@/lib/building-overview";

/** 소비처의 키 집합을 **그 파일에서 파생**한다 — 손으로 옮겨 적으면 그 순간 상한이 된다. */
function costKeysFromConsumer(): Set<string> {
  const src = readFileSync(join(process.cwd(), "lib/kr-construction-cost.ts"), "utf8");
  const m = src.match(/BASE_COST_PER_SQM[^=]*=\s*\{([\s\S]*?)\n\};/);
  if (!m) throw new Error("BASE_COST_PER_SQM 를 못 찾았다 — 조회기가 죽었다(이름이 바뀌었나)");
  return new Set([...m[1].matchAll(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/gm)].map((x) => x[1]));
}

describe("★정본 코드 왕복 — 고른 것이 실제로 적용되는가", () => {
  it("[공허 진리 가드] 모집단이 비어 있지 않다", () => {
    expect(BUILDING_USE_CODES.length).toBeGreaterThanOrEqual(11);
  });

  it("★★모든 정본 코드가 자기 자신으로 정규화된다 — 하나라도 null 이면 그 용도는 무언 실패다", () => {
    const dead = BUILDING_USE_CODES.filter((c) => normalizeBuildingUse(c) !== c);
    expect(dead, `정규화가 삼키는 코드(고르면 아무 일도 안 일어난다): ${dead.join(", ")}`).toEqual(
      [],
    );
  });

  it("[대조군] 한국어 라벨도 여전히 돌아온다 — 항등을 넣느라 동의어를 깨지 않았다", () => {
    const dead = BUILDING_USE_CODES.filter((c) => normalizeBuildingUse(BUILDING_USE_LABEL[c]) !== c);
    expect(dead, `라벨 경로가 깨졌다: ${dead.join(", ")}`).toEqual([]);
  });

  it("[판별력] 모르는 문자열은 여전히 null 이다 — 「전부 통과」 구현은 이 줄에서 죽는다", () => {
    for (const junk of ["", "  ", "zzz없는용도", "apartment2", "공동주택외"]) {
      expect(normalizeBuildingUse(junk), `${junk} 가 코드로 둔갑했다`).toBeNull();
    }
  });

  it("★★항등 등재가 **다른 뜻을 덮어쓰지 않는다** — 덮어쓰면 동의어가 조용히 사라진다", () => {
    const clobbered = BUILDING_USE_CODES.filter(
      (c) => c in __rawAliasToCode && __rawAliasToCode[c] !== c,
    );
    expect(
      clobbered,
      `정본 코드가 이미 **다른 코드의 동의어**였다 — 항등이 그 뜻을 덮어쓴다: ${clobbered
        .map((c) => `${c}→${__rawAliasToCode[c]}`)
        .join(", ")}`,
    ).toEqual([]);
  });

  it("★모달이 넘기는 경로 그대로 태운다 — makeUseLine 이 전 코드를 받아들인다", () => {
    const rejected = BUILDING_USE_CODES.filter((c) => makeUseLine(c, 100) === null);
    expect(rejected, `용도 줄을 못 만드는 코드: ${rejected.join(", ")}`).toEqual([]);
  });
});

describe("★어댑터가 **소비처의 키 도메인**을 쓰는가 — 이름이 아니라 조회 성공으로", () => {
  it("[조회기 생존] 소비처 표를 실제로 읽었다", () => {
    const keys = costKeysFromConsumer();
    expect(keys.size, "소비처 키를 못 모았다 — 파서가 죽었다").toBeGreaterThanOrEqual(5);
    expect(keys.has("apartment"), "대조군 키가 없다 — 잘못된 표를 읽었다").toBe(true);
  });

  it("★★어댑터가 내보내는 값은 **전부** 소비처 표에 있거나 null 이다(빈 문자열 금지)", () => {
    const keys = costKeysFromConsumer();
    const bad = BUILDING_USE_CODES.map((c) => [c, __codeToCostKey[c]] as const).filter(
      ([, k]) => k !== null && !keys.has(k),
    );
    expect(
      bad,
      `소비처가 모르는 키 → apartment 로 조용히 폴백된다: ${bad.map(([c, k]) => `${c}→${k}`).join(", ")}`,
    ).toEqual([]);
  });

  it("★★실제 어댑터 출력을 소비처 표에 **넣어 본다** — 표를 우회하는 경로가 없어야 한다", () => {
    const keys = costKeysFromConsumer();
    for (const code of BUILDING_USE_CODES) {
      const o = { ...emptyBuildingOverview(), aboveGroundGfaSqm: 1000, uses: [makeUseLine(code, 1000)!] };
      const got = toConstructionCostAreas(o);
      expect(got, `${code}: 어댑터가 null 을 냈다 — 연면적이 있는데도`).not.toBeNull();
      const k = got!.buildingUse;
      // 「모름」은 null 이어야 한다. 빈 문자열이면 소비처의 `?? apartment` 가 삼킨다.
      expect(k === null || keys.has(k), `${code} → ${JSON.stringify(k)} 가 소비처 표에 없다`).toBe(
        true,
      );
      expect(k, `${code}: 빈 문자열은 「모름」이 아니라 **아파트로 둔갑**한다`).not.toBe("");
    }
  });

  it("[판별력 대조군] 아는 용도는 실제로 **아파트가 아닌** 키를 낸다 — 전부 null 인 구현을 죽인다", () => {
    const o = { ...emptyBuildingOverview(), aboveGroundGfaSqm: 1000, uses: [makeUseLine("neighborhood", 1000)!] };
    expect(toConstructionCostAreas(o)?.buildingUse).toBe("neighborhood");
    const o2 = { ...emptyBuildingOverview(), aboveGroundGfaSqm: 1000, uses: [makeUseLine("retail", 1000)!] };
    expect(toConstructionCostAreas(o2)?.buildingUse).toBe("commercial");
  });
});
