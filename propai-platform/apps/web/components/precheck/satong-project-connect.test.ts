import { describe, expect, it } from "vitest";

import { addressTokenMismatch } from "@/store/useProjectContextStore";
import {
  deriveProjectNameFromParcels,
  selectionMismatchesProject,
} from "./satong-project-connect";

describe("deriveProjectNameFromParcels", () => {
  it("단일 필지 주소의 마지막 두 토큰(동·지번)으로 이름을 만든다", () => {
    expect(
      deriveProjectNameFromParcels([{ address: "경기도 용인시 수지구 고기동 689" }]),
    ).toBe("고기동 689");
  });

  it("다필지면 '외 N필지'를 붙인다", () => {
    const parcels = Array.from({ length: 9 }, (_, i) => ({
      address: i === 0 ? "경기도 용인시 수지구 고기동 689" : `경기도 용인시 수지구 고기동 ${690 + i}`,
    }));
    expect(deriveProjectNameFromParcels(parcels)).toBe("고기동 689 외 8필지");
  });

  it("대표 필지 주소가 없으면 null(무날조)", () => {
    expect(deriveProjectNameFromParcels([{ address: "" }])).toBeNull();
    expect(deriveProjectNameFromParcels([])).toBeNull();
  });
});

describe("selectionMismatchesProject", () => {
  it("같은 지역(동일 시군구·법정동)이면 false", () => {
    expect(
      selectionMismatchesProject(
        "경기도 용인시 수지구 고기동 689",
        "경기도 용인시 수지구 고기동 689",
      ),
    ).toBe(false);
  });

  it("다른 지역(시군구)이면 addressRegionMismatch 실동작에 따라 true", () => {
    expect(
      selectionMismatchesProject(
        "서울특별시 동작구 상도동 123",
        "경기도 용인시 수지구 고기동 689",
      ),
    ).toBe(true);
  });

  it("같은 동, 다른 번지(인접 필지 추가)는 지역 비교로는 불일치가 아니다(F2 — 가드 과발화 방지)", () => {
    // selectionMismatchesProject는 번지를 무시하는 addressRegionMismatch를 쓰므로
    // 지도에서 인접 필지(같은 법정동, 다른 번지)를 프로젝트에 추가하는 정상 워크플로우가
    // '불일치'로 오판되지 않는다.
    expect(
      selectionMismatchesProject(
        "경기도 용인시 수지구 고기동 689",
        "경기도 용인시 수지구 고기동 690",
      ),
    ).toBe(false);
    // 대조: 번지까지 엄격히 보는 기존 addressTokenMismatch(setProject 오염가드용)는 여전히
    // 같은 동·다른 번지를 불일치로 본다 — 두 함수의 기준이 의도적으로 다름을 문서화.
    expect(
      addressTokenMismatch(
        "경기도 용인시 수지구 고기동 689",
        "경기도 용인시 수지구 고기동 690",
      ),
    ).toBe(true);
  });

  it("주소가 결측이면 보수적으로 false", () => {
    expect(selectionMismatchesProject(null, "경기도 용인시 수지구 고기동 689")).toBe(false);
    expect(selectionMismatchesProject("경기도 용인시 수지구 고기동 689", undefined)).toBe(false);
    expect(selectionMismatchesProject("", "")).toBe(false);
  });
});

describe("deriveProjectNameFromParcels — 축약 전에 PNU 로 지번을 파생한다", () => {
  const DONG = "경기도 오산시 내삼미동";

  it("★PNU 가 있으면 프로젝트 이름부터 필지를 특정한다", () => {
    expect(
      deriveProjectNameFromParcels([{ address: DONG, pnu: "4137011000104670001" }]),
    ).toBe("내삼미동 467-1");
  });

  it("★PNU 가 없으면 지어내지 않는다 — 실제 신고 프로젝트 이름이 이것이다", () => {
    expect(
      deriveProjectNameFromParcels(Array.from({ length: 77 }, () => ({ address: DONG, pnu: null }))),
    ).toBe("오산시 내삼미동 외 76필지");
  });

  it("★가짜 PNU(주소가 PNU 칸에 들어앉음)도 지번을 만들지 못한다", () => {
    expect(deriveProjectNameFromParcels([{ address: DONG, pnu: DONG }])).toBe("오산시 내삼미동");
  });
});
