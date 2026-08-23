/**
 * 등록 필지 수와 필지 목록이 어긋나면 **"단일 필지입니다"라고 단언하지 않는다** (2026-08-23).
 *
 * ★사용자 신고 + 스크린샷 증거: 같은 화면이 위아래로 **자기모순**이었다.
 *     라이프사이클 헤더 : "모산동 123-1 **외 6필지**"   ← parcelCount = 7
 *     본문/우측 패널    : "**단일 필지입니다**"          ← parcels 배열이 비어 1개로 폴백
 *     필지 구획도       : "1필지 · 3,836㎡"
 *
 * ★원인: 이 화면은 `parcels` 배열만 보고 판정한다 —
 *     const list = (ssotParcels ?? []).map(p => p.address).filter(Boolean);
 *     if (list.length > 0) return list;
 *     return site?.address ? [site.address] : [];      // ← 1개로 폴백
 *   `parcelCount`(=7)를 **알면서도** "단일 필지"라고 단언하니 **거짓 표시**다.
 *   사용자는 "왜 다필지를 넣었는데 단필지로 나오지?"만 남는다.
 *
 * ★처방: 두 신호가 어긋나면 그 사실을 말한다(고치는 방법까지). 침묵·거짓단언 금지.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko", id: "p1" }),
}));
vi.mock("@/lib/api-client", () => ({
  apiClient: { post: vi.fn(() => new Promise(() => {})), get: vi.fn(() => new Promise(() => {})) },
}));
vi.mock("@/components/map/ParcelBoundaryMap", () => ({ ParcelBoundaryMap: () => null }));

let siteState: Record<string, unknown> | null = null;
vi.mock("@/store/useProjectContextStore", () => ({
  useProjectContextStore: (sel: (s: unknown) => unknown) => sel({ siteAnalysis: siteState }),
}));

import Page from "@/app/[locale]/(dashboard)/projects/[id]/multi-parcel/page";

const MISMATCH_RE = /필지 목록을 불러오지 못했습니다/;

describe("등록 필지 수 ↔ 필지 목록 불일치", () => {
  it("A) parcelCount=7 인데 목록이 없으면 **거짓 단언 대신 불일치를 고지**한다", () => {
    siteState = { address: "충청북도 제천시 모산동 123-1", parcelCount: 7, parcels: [] };
    render(<Page />);

    expect(screen.getByText(MISMATCH_RE)).toBeInTheDocument();
    // ★거짓 단언이 사라져야 한다 — 이게 사용자가 본 그 문장이다.
    expect(screen.queryByText("단일 필지입니다.")).not.toBeInTheDocument();
  });

  it("B) 진짜 단일 필지면 종전 문구 그대로(위양성 방지)", () => {
    siteState = { address: "충청북도 제천시 모산동 123-1", parcelCount: 1, parcels: [] };
    render(<Page />);

    expect(screen.getByText("단일 필지입니다.")).toBeInTheDocument();
    expect(screen.queryByText(MISMATCH_RE)).not.toBeInTheDocument();
  });

  it("C) parcelCount 자체가 없으면 종전 동작(무회귀)", () => {
    siteState = { address: "충청북도 제천시 모산동 123-1", parcels: [] };
    render(<Page />);

    expect(screen.getByText("단일 필지입니다.")).toBeInTheDocument();
    expect(screen.queryByText(MISMATCH_RE)).not.toBeInTheDocument();
  });

  it("D) 목록이 2개면 통합 경로 — 두 문구 모두 없다", () => {
    siteState = {
      address: "충청북도 제천시 모산동 123-1",
      parcelCount: 2,
      parcels: [{ address: "충청북도 제천시 모산동 123-1" }, { address: "충청북도 제천시 모산동 123-2" }],
    };
    render(<Page />);

    expect(screen.queryByText("단일 필지입니다.")).not.toBeInTheDocument();
    expect(screen.queryByText(MISMATCH_RE)).not.toBeInTheDocument();
  });
});
