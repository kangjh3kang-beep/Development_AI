/**
 * 필지 주소 표시는 **한 벌**이다 — `preferredEntryAddress` 가 PNU 로 지번을 파생한다.
 *
 * ## 왜 생겼나 (2026-08-21 · 사용자 재신고 — 지번 실종 **7세대**)
 *
 * `/ko/permits` 좌측 목록 77행이 전부 `"경기도 오산시 내삼미동"`(동 단위)으로 보였는데,
 * **같은 데이터**가 메인 대시보드에서는 `"내삼미동 467-1"` 로 정상 표시됐다.
 * 면적(53·684·876·843㎡)이 양쪽에서 같은 순서로 일치해 **같은 필지**임이 확증됐다 —
 * 즉 데이터는 **진짜 PNU 를 갖고 있었고**, 갈린 것은 **표시 구현**이었다.
 *
 * 표시 구현이 **세 벌**이었다:
 *   · `parcelDisplayAddress(address, pnu)` — PNU 로 파생 ○ (대시보드 계열)
 *   · `joinAddressJibun(addr, jibun, …)`   — 결합 ○        (사통맵 계열)
 *   · `preferredEntryAddress(e)`           — **pnu 를 받지도 않았다** ✗
 *
 * `#719` 는 주석에 *"구현 두 벌 금지"* 라고 적었는데 **세 번째가 있었다.** 표시층 수정이
 * 여섯 번 반복된 이유가 이것이다 — 매번 **자기가 보고 있던 표면**만 고쳤다.
 */
import { describe, expect, it } from "vitest";

import { entriesToParcelRows, parcelDataToRows, preferredEntryAddress } from "@/lib/parcel-rows";

const 동 = "경기도 오산시 내삼미동";
const 진짜PNU = "4137010900100380000"; // → 지번 38

describe("preferredEntryAddress — 두 모집단이 다른 결과를 낸다", () => {
  it("★사용자 시나리오: 동 단위 주소 + 진짜 PNU → 지번이 파생된다", () => {
    expect(preferredEntryAddress({ fullAddress: 동, pnu: 진짜PNU })).toBe(`${동} 38`);
  });

  it("★대조군: 같은 주소인데 PNU 가 없으면 **그대로**다(없는 지번을 지어내지 않는다)", () => {
    expect(preferredEntryAddress({ fullAddress: 동 })).toBe(동);
    expect(preferredEntryAddress({ fullAddress: 동, pnu: null })).toBe(동);
  });

  it("★대조군: 가짜 PNU(주소 합성 문자열)는 파생하지 않는다", () => {
    expect(preferredEntryAddress({ fullAddress: 동, pnu: 동 })).toBe(동);
  });

  it("주소가 이미 지번을 가지면 **이중 부착하지 않는다**", () => {
    const 지번포함 = `${동} 741`;
    expect(preferredEntryAddress({ fullAddress: 지번포함, pnu: 진짜PNU })).toBe(지번포함);
  });

  it("종전 규칙 무회귀 — 바레 번지는 fullAddress 로 승격된다", () => {
    expect(preferredEntryAddress({
      jibunAddress: "56-1", fullAddress: "용인시 수지구 신봉동 56-1",
    })).toBe("용인시 수지구 신봉동 56-1");
  });

  it("종전 규칙 무회귀 — 셋 다 없으면 도로명으로 떨어진다", () => {
    expect(preferredEntryAddress({ roadAddress: "판교역로 166" })).toBe("판교역로 166");
  });
});

describe("★백엔드로 나가는 payload 도 함께 낫는다", () => {
  it("entriesToParcelRows 의 address 가 지번을 담는다", () => {
    const rows = entriesToParcelRows([
      { fullAddress: 동, pnu: 진짜PNU, areaSqm: 53 },
      { fullAddress: 동, pnu: "4137010900100380001", areaSqm: 684 },
    ] as never);
    // ★표시만의 문제가 아니었다 — 통합분석 요청이 77행 전부 동일 주소로 나가고 있었다.
    expect(rows.map((r) => r.address)).toEqual([`${동} 38`, `${동} 38-1`]);
    // 공허한 참 방지 — 두 행이 실제로 **서로 다른** 값이어야 배선이 살아 있다.
    expect(new Set(rows.map((r) => r.address)).size).toBe(2);
  });
});

describe("★형제 빌더도 함께 낫는다 — 같은 파일 안에서 하나만 고치는 것을 막는다", () => {
  it("parcelDataToRows(store 경유) 의 address 도 지번을 담는다", () => {
    const rows = parcelDataToRows([
      { address: 동, pnu: 진짜PNU, areaSqm: 53 },
      { address: 동, pnu: "4137010900104670001", areaSqm: 684 },
    ]);
    expect(rows.map((r) => r.address)).toEqual([`${동} 38`, `${동} 467-1`]);
    // 공허한 참 방지 — 두 행이 실제로 갈려야 배선이 살아 있다.
    expect(new Set(rows.map((r) => r.address)).size).toBe(2);
  });

  it("★대조군 — PNU 가 없으면 그대로다(무날조)", () => {
    const rows = parcelDataToRows([{ address: 동, areaSqm: 53 }]);
    expect(rows[0].address).toBe(동);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 2026-09-02 — 표시만이 아니라 **전송**도 한 벌이다.
// `parcelDataToRows` 는 payload 에 `pnu` 를 싣는데, 종전엔 `p.pnu ?`(참/거짓)만 봐서
// PNU 칸의 오염값이 **그대로 백엔드로 나갔다**. 볼트 2026-08-20 실측: 서버가 그것을 echo 하고
// `jibun:null · area_sqm:0 · zone_type:null · age_status:"lookup_failed"` 를 돌려준다 —
// **필지 보강 전체가 조용히 죽는다**(표시만의 문제가 아니다).
// ★두 모집단: 진짜는 실리고, 오염은 **키 자체가 없다**(`null` 로 싣지 않는다 — 무날조).
// ────────────────────────────────────────────────────────────────────────────
describe("★parcelDataToRows — 오염된 PNU 는 요청 본문에 싣지 않는다", () => {
  const 오염 = ["◀ 전성결", "store-rep-경기도 오산시 내삼미동", "413701100010467000"];

  it("모집단 A(진짜 PNU) — pnu 가 실린다", () => {
    const rows = parcelDataToRows([
      { address: "경기도 오산시 내삼미동", areaSqm: 53, pnu: "4137011000104670001" },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].pnu).toBe("4137011000104670001");
  });

  it("★모집단 B(오염 PNU) — pnu **키가 아예 없다**(null 로도 싣지 않는다)", () => {
    for (const bad of 오염) {
      const rows = parcelDataToRows([
        { address: "경기도 오산시 내삼미동", areaSqm: 53, pnu: bad },
      ]);
      expect(rows).toHaveLength(1);
      expect("pnu" in rows[0]).toBe(false);
      expect(JSON.stringify(rows[0])).not.toContain(bad);
    }
  });
});

// ────────────────────────────────────────────────────────────────────────────
// ★부채 — 같은 수정을 했지만 **잠기지 않은** 자리(변이 실측 SURVIVED, 2026-09-02).
//   커밋 메시지에만 적으면 드러나지 않으므로 초록 안에 남긴다.
// ────────────────────────────────────────────────────────────────────────────
describe("★부채 — 오염 PNU 무해화가 잠기지 않은 표면", () => {
  it.todo(
    "LandShareModal: `/zoning/land-share` 요청이 오염 PNU 대신 주소로 떨어지는가 " +
      "— 수정은 했으나 변이 M6(`length >= 19` 로 되돌림)이 SURVIVED. fetch 모킹 + 렌더가 필요하다",
  );
  it.todo(
    "PersonaPanel: requestBody.bcode 가 오염 PNU 에서 파생되지 않는가 " +
      "— 수정은 했으나 변이 M8(검증 제거)이 SURVIVED. useMemo 를 태우려면 스토어 주입 렌더가 필요하다",
  );
});
