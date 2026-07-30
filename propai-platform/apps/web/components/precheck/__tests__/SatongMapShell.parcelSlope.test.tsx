/**
 * SatongMapShell — 필지 경사도 온디맨드 배선(W2) 관통 테스트.
 *
 * ★순수 컴포넌트 테스트로 부족한 지점(W1 회고): 표시 계약이 전부 초록이어도 셸이 조회를
 *   붙이지 않으면 화면엔 버튼만 남는다. 그리고 이 기능의 진짜 위험은 **표시가 아니라 호출 빈도**다
 *   — 표고 원천이 1 req/s 공개 제한인데 서버에 캐시가 없고 전역 리미터도 없다. 그래서
 *   ①실제 호출 발생 ②세션 캐시로 재조회 제거 ③인플라이트 1건 ④스테일 필지 오부착 차단
 *   ⑤계정 격리를 전부 관통 검증한다.
 */
import { useEffect, type ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  SATONG_PARCEL_SLOPE_KEY,
  readSatongViewCache,
  writeSatongViewCache,
  writeSatongMapSelection,
} from "@/components/precheck/satong-map-selection";
import { clearOnLogout } from "@/lib/projectSync";
import type { TerrainResult } from "@/components/terrain/types";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: { topRightSlot?: ReactNode }) => {
      useEffect(() => {}, []);
      return <div data-testid="dynamic-map-stub">{props.topRightSlot}</div>;
    };
    return DynamicStub;
  },
}));

/** terrain/analyze 호출을 계측·제어하는 대역. 그 외 요청은 영구 pending. */
const terrain = {
  calls: [] as Array<{ pnu: string | null; address: string | null }>,
  resolve: null as ((v: TerrainResult) => void) | null,
  reject: null as ((e: unknown) => void) | null,
};

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: vi.fn(pending),
      put: vi.fn(pending),
      patch: vi.fn(pending),
      delete: vi.fn(pending),
      getV2: vi.fn(pending),
      postV2: vi.fn(pending),
      putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
      post: vi.fn((path: string, opts?: { body?: Record<string, unknown> }) => {
        if (path !== "/terrain/analyze") return pending();
        terrain.calls.push({
          pnu: (opts?.body?.pnu as string | null) ?? null,
          address: (opts?.body?.address as string | null) ?? null,
        });
        return new Promise<TerrainResult>((res, rej) => {
          terrain.resolve = res;
          terrain.reject = rej;
        });
      }),
    },
  };
});

const ADDR_A = "경상북도 포항시 남구 호미곶면 대보리 산1-1";
const PNU_A = "4711025029000010001";
const ADDR_B = "경상북도 포항시 남구 호미곶면 대보리 산2-2";
const PNU_B = "4711025029000020002";

const RESULT_A: TerrainResult = {
  ok: true,
  pnu: PNU_A,
  slope: { mean_pct: 18.4, max_pct: 27.1, aspect_deg: 142, class: "경사", detail: "평균경사 18.4% / 최대 27.1% — 경사." },
  confidence: 0.85,
  note: "참고용(EXPERIMENTAL): SRTM 30m 광역 표고 기반 — 정밀 측량이 아님.",
};

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({
      projectId: null, projectName: "", projectStatus: "", siteAnalysis: null,
    });
  });
}

function seedTwoParcels() {
  writeSatongMapSelection([
    { id: "P-a", address: ADDR_A, pnu: PNU_A, source: "map", areaSqm: 147078, zoneType: "보전관리지역", jimok: "임야" },
    { id: "P-b", address: ADDR_B, pnu: PNU_B, source: "map", areaSqm: 5000, zoneType: "보전관리지역", jimok: "임야" },
  ]);
}

describe("SatongMapShell 경사도 온디맨드 배선(W2)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
    terrain.calls = [];
    terrain.resolve = null;
    terrain.reject = null;
  });

  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("① 상세를 열면 '미조회'이고, 버튼을 눌러야 실제로 조회가 나간다(자동 조회 금지)", async () => {
    seedTwoParcels();
    render(<SatongMapShell locale="ko" />);

    fireEvent.click(screen.getByText("대보리 산1-1"));
    const panel = screen.getByTestId("parcel-detail-panel");
    expect(within(panel).getByTestId("parcel-slope-section")).toBeInTheDocument();
    // ★자동 조회하지 않는다 — 1req/s 제한을 사용자 훑기로 넘기지 않기 위한 핵심 계약.
    expect(terrain.calls).toHaveLength(0);

    fireEvent.click(within(panel).getByTestId("parcel-slope-request"));
    expect(terrain.calls).toEqual([{ pnu: PNU_A, address: ADDR_A }]);
    expect(within(panel).getByTestId("parcel-slope-loading")).toBeInTheDocument();

    await act(async () => {
      terrain.resolve?.(RESULT_A);
    });
    expect(screen.getByTestId("parcel-slope-mean").textContent).toBe("18.4%");
    expect(screen.getByTestId("parcel-slope-note").textContent).toBe(RESULT_A.note);
  });

  it("★② 인플라이트 1건 — 버튼 연타가 중복 호출을 만들지 않는다(1req/s 보호)", async () => {
    seedTwoParcels();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    const panel = screen.getByTestId("parcel-detail-panel");

    const btn = within(panel).getByTestId("parcel-slope-request");
    // ★한 batch 안에서 연타해야 가드에 도달한다: fireEvent는 매 호출마다 act를 flush해
    //   첫 클릭 직후 버튼이 언마운트되고(로딩 전환) 이후 클릭이 핸들러에 닿지 않는다 —
    //   그러면 인플라이트 가드를 제거해도 테스트가 통과하는 가짜 안전이 된다(변이로 실증).
    //   native click 3회를 하나의 act로 묶어 재렌더 전에 핸들러가 3번 호출되게 한다.
    await act(async () => {
      btn.click();
      btn.click();
      btn.click();
    });

    expect(terrain.calls).toHaveLength(1);
    await act(async () => {
      terrain.resolve?.(RESULT_A);
    });
  });

  it("★③ 세션 캐시 — 같은 필지를 다시 열면 재조회 없이 즉시 표시된다", async () => {
    seedTwoParcels();
    render(<SatongMapShell locale="ko" />);

    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-slope-request"));
    await act(async () => {
      terrain.resolve?.(RESULT_A);
    });
    expect(terrain.calls).toHaveLength(1);

    // 다른 필지로 갔다가 돌아온다.
    fireEvent.click(screen.getByText("대보리 산2-2"));
    expect(screen.queryByTestId("parcel-slope-mean")).not.toBeInTheDocument(); // B는 미조회
    fireEvent.click(screen.getByText("대보리 산1-1"));

    // ★재조회가 나가지 않고 캐시로 즉시 표시된다.
    expect(terrain.calls).toHaveLength(1);
    expect(screen.getByTestId("parcel-slope-mean").textContent).toBe("18.4%");
  });

  it("★④ 스테일 가드 — 조회 중 다른 필지로 옮기면 남의 경사도가 붙지 않는다", async () => {
    seedTwoParcels();
    render(<SatongMapShell locale="ko" />);

    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-slope-request"));

    // 응답 도착 전에 B로 전환
    fireEvent.click(screen.getByText("대보리 산2-2"));
    await act(async () => {
      terrain.resolve?.(RESULT_A); // A의 결과가 늦게 도착
    });

    // ★B 화면에 A의 수치가 붙으면 안 된다.
    expect(screen.queryByTestId("parcel-slope-mean")).not.toBeInTheDocument();
    expect(screen.getByTestId("parcel-slope-request")).toBeInTheDocument(); // B는 여전히 미조회

    // 그러나 A의 결과는 캐시에 남아 A를 다시 열면 재조회 없이 보인다(버리지 않는다).
    fireEvent.click(screen.getByText("대보리 산1-1"));
    expect(terrain.calls).toHaveLength(1);
    expect(screen.getByTestId("parcel-slope-mean").textContent).toBe("18.4%");
  });

  it("⑤ ok:false — 조회 실패로 표기하고 수치를 만들지 않는다", async () => {
    seedTwoParcels();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-slope-request"));

    await act(async () => {
      terrain.resolve?.({ ok: false, message: "주소/PNU로 좌표 또는 필지를 확인하지 못했습니다." });
    });

    expect(screen.getByTestId("parcel-slope-error").textContent).toContain("조회 실패");
    expect(screen.queryByTestId("parcel-slope-mean")).not.toBeInTheDocument();
  });

  it("⑤-b 네트워크 예외 — 실패 표기 + 재조회 가능(인플라이트 잠금이 풀린다)", async () => {
    seedTwoParcels();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-slope-request"));

    await act(async () => {
      terrain.reject?.(new Error("boom"));
    });
    await waitFor(() => expect(screen.getByTestId("parcel-slope-error")).toBeInTheDocument());

    // ★잠금이 풀려 재조회가 실제로 나간다(영구 잠김이면 사용자가 복구 불가).
    fireEvent.click(screen.getByRole("button", { name: "다시 조회" }));
    expect(terrain.calls).toHaveLength(2);
  });

  it("★⑥ 계정 격리 — 로그아웃 와이프가 경사도 뷰 캐시를 지운다", () => {
    writeSatongViewCache<TerrainResult>(
      SATONG_PARCEL_SLOPE_KEY,
      new Map([["PNU-PREV-ACCOUNT", RESULT_A]]),
    );
    expect(window.sessionStorage.getItem(SATONG_PARCEL_SLOPE_KEY)).not.toBeNull();

    clearOnLogout();

    expect(window.sessionStorage.getItem(SATONG_PARCEL_SLOPE_KEY)).toBeNull();
    expect(readSatongViewCache<TerrainResult>(SATONG_PARCEL_SLOPE_KEY).size).toBe(0);
  });
});
