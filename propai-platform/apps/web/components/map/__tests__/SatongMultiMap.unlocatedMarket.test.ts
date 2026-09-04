/**
 * 지도에 **못 찍는** 실거래를 버리지 않는다 — 목록으로 되살린다.
 *
 * ## 왜 생겼나 (2026-08-21 · 사용자 "각 정보가 지도에 안 나온다")
 *
 * 국토부가 단독·토지·상업 지번을 `2**` 로 가려 보내면 좌표를 찍을 수 없다(원천 한계).
 * 백엔드는 그것을 **버리지 않고** `location_status:"unlocated"` 로 보존해 왔다
 * (*"반경 밖으로 단정하지 않는다 — 무날조"*). 그런데 **지도는 건수만 표시하고 내용을 버렸다.**
 *
 * 라이브 실측(제천 모산동 123-1·10km): **56그룹 476건**이 payload 에 동·지번·평균가·면적·
 * 거래일까지 실려 있는데 화면에 0. 그중 **토지매매만 362건** — 토지 개발자에게 가장 중요한
 * 데이터가 100% 보이지 않았다. 전형적인 *"코드는 있는데 소비처 없음"*.
 *
 * ## 무엇을 잠그나 (두 모집단)
 *
 * "unlocated 를 모은다"만 잠그면 **전부 다 모아도** 통과한다. 그래서 같은 실행에서
 * **①좌표 없는 것은 목록에 넣고 ②이미 지도에 찍힌 것(located·approximate)은 넣지 않는다**
 * 를 함께 단언한다. 후자가 깨지면 같은 거래가 지도와 목록에 **이중 계상**된다.
 */
import { describe, expect, it } from "vitest";

import { collectUnlocatedMarketGroups } from "@/components/map/SatongMultiMap";

const payload = {
  center: { lat: 37.1, lon: 128.2 },
  categories: {
    land_trade: {
      groups: [
        { name: "강제동 2**", dong: "강제동", jibun: "2**", count: 23, avg_price_10k: 5000,
          location_status: "unlocated" },
        { name: "모산동 3**", dong: "모산동", jibun: "3**", count: 41, avg_price_10k: 8000,
          location_status: "unlocated" },
        // ★지도에 이미 찍힌 것 — 목록에 들어오면 이중 계상이다.
        { name: "정밀필지", dong: "청전동", jibun: "12-3", count: 99, lat: 37.1, lon: 128.2,
          avg_price_10k: 1000, location_status: "located" },
        { name: "동대표점", dong: "용두동", count: 88, lat: 37.2, lon: 128.3,
          location_status: "approximate" },
      ],
    },
  },
} as never;

describe("위치 미확인 실거래 — 버리지 않고 목록으로", () => {
  it("★좌표 없는 그룹을 **거래 많은 순**으로 모은다", () => {
    const rows = collectUnlocatedMarketGroups(payload);
    expect(rows).toHaveLength(2);                       // 공허한 참 방지 — 실제로 모였다
    expect(rows.map((r) => r.label)).toEqual(["모산동 3**", "강제동 2**"]);
    expect(rows[0].count).toBe(41);
    expect(rows[0].avg).toBe(8000);
  });

  it("★대조군 — 이미 지도에 찍힌 것은 목록에 넣지 않는다(이중 계상 금지)", () => {
    const labels = collectUnlocatedMarketGroups(payload).map((r) => r.label);
    expect(labels).not.toContain("청전동 12-3");   // located
    expect(labels.some((l) => l.includes("용두동"))).toBe(false); // approximate
    // 부재 단언만으로 두지 않는다 — 남은 둘이 **실제로 마스킹분**임을 함께 단언한다.
    expect(labels.every((l) => l.includes("**"))).toBe(true);
  });

  it("빈 payload 에도 안전하다(무자료를 지어내지 않는다)", () => {
    expect(collectUnlocatedMarketGroups(null)).toEqual([]);
    expect(collectUnlocatedMarketGroups({ center: null } as never)).toEqual([]);
  });
});
