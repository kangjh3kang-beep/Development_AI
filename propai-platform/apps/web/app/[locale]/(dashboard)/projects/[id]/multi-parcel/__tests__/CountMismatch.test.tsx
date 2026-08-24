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
 * ★className(스타일) 변이 생존은 **의도된 미잠금**이다 — 계약은 "거짓 단언을 멈추고
 *   불일치를 고지한다"이지 색상·여백이 아니다(잠그면 정상 리스타일이 위반이 된다).
 *
 * ★처방: 두 신호가 어긋나면 그 사실을 말한다(고치는 방법까지). 침묵·거짓단언 금지.
 *
 * ## ★★2026-08-24 — 이 테스트가 초록인데 **라이브에서 발화하지 않았다**
 *
 * 수용시험(Playwright · 라이브 · 프로젝트 `49b59c62` 포항 호미곶 대보리 산 1-1) 결과
 * `data-testid=parcel-count-mismatch` **0건**, *"단일 필지입니다."* 가 **그대로** 있었다.
 *
 * 원인은 **아래 픽스처들이 라이브에 없는 모양**이라는 것이다. 라이브 실측:
 *   · 영속 스냅샷 `snapshots[pid].siteAnalysis` : `parcelCount=2` · `parcels.length=2`
 *   · ★활성 슬라이스 `state.siteAnalysis`(화면이 읽는 것) : `parcelCount=0` · `parcels=[]`
 *
 * 즉 **탐지기가 결함이 파괴하는 바로 그 신호를 입력으로 썼다** — 결함이 클수록 조용해진다.
 * A~D 는 `parcelCount` 를 **활성에 손으로 넣어** 통과했으므로 그 붕괴 경로를 안 태웠다.
 * ★그래서 아래 **E~G** 를 더한다: **활성이 무너지고 스냅샷만 살아 있는** 모양이다.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko", id: "p1" }),
}));
vi.mock("@/lib/api-client", () => ({
  apiClient: { post: vi.fn(() => new Promise(() => {})), get: vi.fn(() => new Promise(() => {})) },
}));
vi.mock("@/components/map/ParcelBoundaryMap", () => ({ ParcelBoundaryMap: () => null }));

let siteState: Record<string, unknown> | null = null;
/** 영속 스냅샷 — ★활성이 무너져도 살아남는 쪽. 라이브가 실제로 이런 모양을 준다. */
let snapState: Record<string, unknown> | null = null;
vi.mock("@/store/useProjectContextStore", () => ({
  useProjectContextStore: (sel: (s: unknown) => unknown) =>
    sel({ siteAnalysis: siteState, snapshots: snapState ? { p1: { siteAnalysis: snapState } } : {} }),
}));

import Page from "@/app/[locale]/(dashboard)/projects/[id]/multi-parcel/page";

const MISMATCH_RE = /필지 목록을 불러오지 못했습니다/;

beforeEach(() => {
  siteState = null;
  snapState = null;
});

describe("등록 필지 수 ↔ 필지 목록 불일치", () => {
  it("A) parcelCount=7 인데 목록이 없으면 **거짓 단언 대신 불일치를 고지**한다", () => {
    siteState = { address: "충청북도 제천시 모산동 123-1", parcelCount: 7, parcels: [] };
    render(<Page />);

    expect(screen.getByText(MISMATCH_RE)).toBeInTheDocument();
    // ★testid 를 **양성에서** 잠근다(#755 에서 같은 걸 놓쳤다) — 안 잠그면 testid 가 바뀌어도
    //   아래 음성 단언들이 '없음'으로 통과해 공허해진다.
    expect(screen.getByTestId("parcel-count-mismatch")).toBeInTheDocument();
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
  // ── ★E~G: **라이브가 실제로 주는 모양** — 활성 슬라이스가 0 으로 무너지고 스냅샷만 살아 있다 ──
  //   A~D 는 `parcelCount` 를 활성에 손으로 넣어 통과했다. 그 모양은 라이브에 없다.

  it("E) ★활성이 0 으로 무너져도 **스냅샷이 살아 있으면** 거짓 단언을 멈춘다(라이브 실측 형상)", () => {
    // 프로젝트 49b59c62 실측: 활성 parcelCount=0·parcels=[] / 스냅샷 parcelCount=2·parcels 2개
    siteState = { address: "경상북도 포항시 남구 호미곶면 대보리 산 1-1", parcelCount: 0, parcels: [] };
    snapState = {
      address: "경상북도 포항시 남구 호미곶면 대보리 산 1-1",
      parcelCount: 2,
      parcels: [{ address: "…산 1-1" }, { address: "…산 1-2" }],
    };
    render(<Page />);

    expect(screen.getByTestId("parcel-count-mismatch")).toBeInTheDocument();
    expect(screen.getByText(MISMATCH_RE)).toBeInTheDocument();
    expect(screen.queryByText("단일 필지입니다.")).not.toBeInTheDocument();
  });

  it("F) ★음성 짝 — 스냅샷도 단일이면 종전 문구 그대로(위양성 방지)", () => {
    // ★E 와 **활성이 똑같다**. 갈리는 것은 스냅샷뿐이다 —
    //   이게 없으면 "활성이 0 이면 무조건 고지한다"는 배선으로도 E 가 통과해 잠금이 공허해진다.
    siteState = { address: "경상북도 포항시 남구 호미곶면 대보리 산 1-1", parcelCount: 0, parcels: [] };
    snapState = { address: "경상북도 포항시 남구 호미곶면 대보리 산 1-1", parcelCount: 1, parcels: [] };
    render(<Page />);

    expect(screen.getByText("단일 필지입니다.")).toBeInTheDocument();
    expect(screen.queryByTestId("parcel-count-mismatch")).not.toBeInTheDocument();
  });

  it("G) ★스냅샷에 `parcelCount` 가 없어도 **목록 길이**가 증거다", () => {
    // 스냅샷이 parcelCount 없이 parcels 만 갖는 경우도 실재한다(두 필드가 따로 붕괴한다).
    siteState = { address: "경상북도 포항시 남구 호미곶면 대보리 산 1-1", parcelCount: 0, parcels: [] };
    snapState = { address: "…", parcels: [{ address: "…산 1-1" }, { address: "…산 1-2" }] };
    render(<Page />);

    expect(screen.getByTestId("parcel-count-mismatch")).toBeInTheDocument();
    expect(screen.queryByText("단일 필지입니다.")).not.toBeInTheDocument();
  });

});
