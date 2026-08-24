/**
 * 헤더가 **대표 1필지 면적을 "N필지 합계"라고 불렀다** — 거짓 근거.
 *
 * ## 실물(프로덕션 스냅샷)
 *
 * 31~33필지 프로젝트 3건의 `siteAnalysis.landAreaSqm` 이 **543㎡** 였다. 543 은 *분석 주소
 * 필지*(상도동 210-453)의 면적이고, 그중 두 건은 **그 필지가 선택 목록에 아예 없다.**
 * 즉 `siteAnalysis` 는 "분석한 단일 주소"와 "선택한 다필지" **두 모집단**을 한 객체에 담는다.
 *
 * SSOT(`resolveLandArea`)는 이 상태를 이미 정직하게 다룬다 — 다필지인데 통합면적이 없으면
 * 대표 면적을 돌려주되 `basis="representative"` 로 **강등을 사실대로 알린다.**
 * 그런데 헤더는 그 라벨을 **버리고** `isMultiParcel` 만 보고 *"N필지 합계"* 라고 단정했다.
 *
 * ★같은 파일이 바로 옆 용도지역 항목에서 *"거짓 근거는 근거 없음보다 나쁘다"* 라고 적어 뒀다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

import { deriveContextHeaderData } from "@/lib/context-header";

type Ctx = Parameters<typeof deriveContextHeaderData>[0];

function ctxWith(sa: Record<string, unknown>): Ctx {
  return {
    projectId: "p-1",
    projectName: "테스트",
    siteAnalysis: sa,
    designData: null,
  } as unknown as Ctx;
}

describe("헤더 대지면적 — 값과 함께 **그 값이 무엇인지**를 들고 나온다", () => {
  it("★다필지인데 통합면적이 없으면 basis 가 representative 다 — 실물(33필지·543㎡)", () => {
    const d = deriveContextHeaderData(
      ctxWith({
        address: "서울특별시 동작구 상도동 210-453",
        landAreaSqm: 543,
        parcelCount: 33,
        parcels: Array.from({ length: 33 }, (_, i) => ({ address: `상도동 ${i}`, areaSqm: 300 })),
      }),
    );
    expect(d.landAreaSqm, "값 자체는 종전대로(무회귀)").toBe(543);
    expect(
      d.landAreaBasis,
      "SSOT 가 계산한 강등 라벨을 헤더가 버렸다 — 화면이 대표면적을 합계라고 말하게 된다",
    ).toBe("representative");
  });

  it("[양성 대조군] 통합면적이 있으면 integrated 다", () => {
    const d = deriveContextHeaderData(
      ctxWith({
        address: "서울특별시 동작구 상도동 210-453",
        landAreaSqm: 543,
        landAreaSqmTotal: 10686,
        parcelCount: 33,
        parcels: Array.from({ length: 33 }, (_, i) => ({ address: `상도동 ${i}`, areaSqm: 300 })),
      }),
    );
    expect(d.landAreaSqm, "통합면적이 있으면 그걸 쓴다").toBe(10686);
    expect(d.landAreaBasis).toBe("integrated");
  });

  it("[양성 대조군] 단일필지는 single 이다 — 다필지 문구가 새지 않는다", () => {
    const d = deriveContextHeaderData(
      ctxWith({ address: "서울특별시 동작구 상도동 211-204", landAreaSqm: 236, parcelCount: 1 }),
    );
    expect(d.landAreaBasis).toBe("single");
  });

  it("★면적이 없으면 none — 없는 것을 있다고 하지 않는다", () => {
    const d = deriveContextHeaderData(ctxWith({ address: "서울특별시 동작구 상도동 1" }));
    expect(d.landAreaSqm).toBeNull();
    expect(d.landAreaBasis).toBe("none");
  });

  it("★★헤더 근거 문구가 basis 에 결속돼 있다 — isMultiParcel 로 되돌리면 거짓 근거가 부활한다", () => {
    const rel = "components/common/ContextHeader.tsx";
    const exec = __stripCommentsForScan(
      readFileSync(join(__dirname, "..", "..", rel), "utf8"),
      rel,
    );
    // 공허 진리 가드 — 대상 파일을 실제로 읽었는지 먼저 본다.
    expect(exec.length, "대상 파일을 못 읽었다").toBeGreaterThan(1000);
    expect(exec, "근거 문구가 SSOT basis 를 안 본다").toContain('data.landAreaBasis === "integrated"');
    expect(exec, "강등 상태를 말하는 분기가 없다").toContain('data.landAreaBasis === "representative"');
  });
});
