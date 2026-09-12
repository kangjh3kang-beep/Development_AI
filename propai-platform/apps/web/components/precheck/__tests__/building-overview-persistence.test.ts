/**
 * ★사용자가 **손으로 친 건축개요**가 새로고침을 넘어 살아남는가 — 그리고 **버려야 할 때 버리는가**.
 *
 * 왜(2026-09-12 · 적대 리뷰): `buildingOverview` 가 `useState` 에만 있어 참조가 3건뿐이었고
 * (선언·writer·자기 되먹임) **새로고침 한 번에 전부 소실**됐다.
 *
 * ★「부른다」를 잠그지 않는다 — 저장 함수 호출을 단언하면 그 함수가 아무것도 안 해도 초록이다.
 *   여기서는 **저장소를 실제로 왕복**시킨다(쓰고 → 지우고 → 다시 읽는다).
 * ★두 모집단을 같은 실행에서 본다: **남아야 할 것이 남고, 지워져야 할 것이 지워지는가.**
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  SATONG_BUILDING_OVERVIEW_KEY,
  readSatongBuildingOverview,
  writeSatongBuildingOverview,
} from "@/components/precheck/satong-map-selection";

const SAMPLE = {
  landAreaSqm: 1234,
  landAreaOrigin: "manual",
  aboveGroundGfaSqm: 5678,
  basementGfaSqm: 900,
  uses: [{ use: "retail", rawUse: null, gfaSqm: 5678, unitCount: null, avgExclusiveSqm: null }],
};

describe("★건축개요 세션 미러 — 행위로 잠근다", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("[공허 진리 가드] 시작 상태는 비어 있다 — 안 그러면 아래 왕복이 무의미하다", () => {
    expect(readSatongBuildingOverview()).toBeNull();
  });

  it("★★쓴 값이 **새 읽기**에서 그대로 돌아온다(새로고침 시뮬레이션 — 메모리 경유 금지)", () => {
    writeSatongBuildingOverview(SAMPLE);
    // ★메모리 참조가 아니라 **직렬화된 저장소**를 거쳤는지 확인한다.
    expect(window.sessionStorage.getItem(SATONG_BUILDING_OVERVIEW_KEY)).toBeTruthy();
    const back = readSatongBuildingOverview() as typeof SAMPLE;
    expect(back).not.toBe(SAMPLE); // 같은 객체면 저장소를 안 탄 것이다
    expect(back).toEqual(SAMPLE);
    expect(back.landAreaSqm, "숫자가 문자열로 굳지 않았다").toBe(1234);
  });

  it("★★null 을 쓰면 **지운다** — 빈 객체를 남기면 「입력됨」 배지가 거짓말한다", () => {
    writeSatongBuildingOverview(SAMPLE);
    expect(readSatongBuildingOverview()).not.toBeNull();
    writeSatongBuildingOverview(null);
    expect(window.sessionStorage.getItem(SATONG_BUILDING_OVERVIEW_KEY)).toBeNull();
    expect(readSatongBuildingOverview()).toBeNull();
  });

  it("★손상된 값은 **부분 복원하지 않는다** — 0 을 채워 되살리면 「모름」이 유효값을 입는다", () => {
    for (const junk of ["{", "null", '"문자열"', "[1,2]", "123"]) {
      window.sessionStorage.setItem(SATONG_BUILDING_OVERVIEW_KEY, junk);
      expect(readSatongBuildingOverview(), `${junk} 가 객체로 둔갑했다`).toBeNull();
    }
  });

  it("[판별력 대조군] 정상 객체는 여전히 통과한다 — 「전부 null」 구현을 죽인다", () => {
    window.sessionStorage.setItem(SATONG_BUILDING_OVERVIEW_KEY, JSON.stringify({ landAreaSqm: 1 }));
    expect(readSatongBuildingOverview()).toEqual({ landAreaSqm: 1 });
  });

  it("★★계정 격리 — 이 키가 와이프 목록에 **실제로 실려** 있다(전례: 선택 키가 빠져 샜다)", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    // ★`process.cwd()` 는 vitest 설정상 apps/web 이다(형제 계약 테스트들이 같은 기준을 쓴다).
    const src = readFileSync(join(process.cwd(), "lib/projectSync.ts"), "utf8");
    expect(
      src.includes("SATONG_BUILDING_OVERVIEW_KEY"),
      "와이프 목록에 없다 — 계정 전환 시 남의 건축개요가 남는다",
    ).toBe(true);
    // 대조군: 조회기 생존(이미 실려 있어야 할 형제 키가 보이는가)
    expect(src.includes("SATONG_MAP_SELECTION_KEY"), "조회기가 죽었다").toBe(true);
  });
});
