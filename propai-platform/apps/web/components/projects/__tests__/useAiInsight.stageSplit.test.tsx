/**
 * useAiInsight 2단계 전환 회귀락 — 이 카드가 라이브에서 100% 실패하던 결함의 잠금.
 *
 * ★무슨 일이 있었나(2026-08-02 실측): 이 훅은 종합분석을 **해석까지 한 번에** 요청했다.
 * 해석 2종은 125초 넘게 걸려서 중간 경로가 응답을 자르고, 그 전에 클라이언트 90초 타임아웃이
 * 먼저 터진다. 캐시가 가장 두터운 주소도 99.9초, 신규 주소는 125.2초에 잘렸다 —
 * 즉 사용자에게는 언제나 "AI 해석 생성에 실패했습니다"만 보였다.
 *
 * 종합분석 화면은 이미 2단계로 고쳤는데 **같은 API를 쓰는 이 형제 소비처만 남아 있었다.**
 * 그래서 잠그는 것은 "빠르다"가 아니라 **"해석을 1단계 요청에 얹지 않는다"** 이다.
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const routes = new Map<string, () => Promise<unknown>>();
const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>((path: string) => {
  const h = routes.get(path);
  return h ? h() : Promise.resolve({});
});
function onPost(path: string, handler: () => Promise<unknown>) {
  routes.set(path, handler);
}
function callsTo(path: string) {
  return post.mock.calls.filter((c) => c[0] === path);
}

const getRoutes = new Map<string, () => Promise<unknown>>();
const get = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(async (path: string) => {
  const h = getRoutes.get(path);
  return h ? h() : {};
});
function onGet(path: string, handler: () => Promise<unknown>) {
  getRoutes.set(path, handler);
}

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (path: string, opts?: unknown) => post(path, opts),
    get: (path: string, opts?: unknown) => get(path, opts),
  },
  hasAccessToken: () => true,
  resolveApiOrigin: () => "http://localhost:8000",
  apiV1BaseUrl: () => "http://localhost:8000/api/v1",
  ApiClientError: class ApiClientError extends Error {},
}));

import { useAiInsight } from "@/components/projects/useAiInsight";

const ADDRESS = "경북 포항시 남구 호미곶면 대보리 산1-1";
const CORE = { address: ADDRESS, zone_type: "보전관리지역", ai_interpretation: null };
const PARTS = { ai_interpretation: { overall_summary: "개발 제약이 큽니다." } };

beforeEach(() => {
  post.mockClear();
  get.mockClear();
  routes.clear();
  getRoutes.clear();
  try {
    window.localStorage.clear();
  } catch {
    /* jsdom quota */
  }
});

describe("useAiInsight 2단계", () => {
  it("★1단계는 include_interpretation:false로 부른다(해석을 얹지 않는다)", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => PARTS);

    const { result } = renderHook(() => useAiInsight(ADDRESS));
    await act(async () => {
      await result.current.run();
    });

    const calls = callsTo("/analysis/comprehensive");
    expect(calls).toHaveLength(1);
    const [, opts] = calls[0] as [string, { body: Record<string, unknown> }];
    // ★이 단언이 깨지면 결함이 그대로 돌아온 것이다(엣지 컷오프에 다시 걸린다).
    expect(opts.body.include_interpretation).toBe(false);
  });

  it("해석은 별도 호출로 받아 1단계 결과 위에 병합한다", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => PARTS);

    const { result } = renderHook(() => useAiInsight(ADDRESS));
    await act(async () => {
      await result.current.run();
    });

    const interpCalls = callsTo("/analysis/interpretation");
    expect(interpCalls).toHaveLength(1);
    const [, opts] = interpCalls[0] as [string, { body: { result?: unknown } }];
    expect(opts.body.result).toMatchObject({ zone_type: "보전관리지역" });

    await waitFor(() => expect(result.current.ai?.overall_summary).toBe("개발 제약이 큽니다."));
    expect(result.current.error).toBe("");
  });

  it("작업번호를 받으면 폴링해서 결과를 가져온다", async () => {
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => ({ job_id: "interp_abc" }));
    let polls = 0;
    onGet("/analysis/interpretation/interp_abc", async () => {
      polls += 1;
      return polls >= 2 ? { status: "done", result: PARTS } : { status: "pending" };
    });

    const { result } = renderHook(() => useAiInsight(ADDRESS));
    await act(async () => {
      await result.current.run();
    });

    await waitFor(() => expect(result.current.ai?.overall_summary).toBe("개발 제약이 큽니다."), {
      timeout: 15000,
    });
    expect(polls).toBeGreaterThanOrEqual(2);
  }, 20000);

  it("★화면을 떠나면 폴링이 멈춘다(사라진 화면이 계속 조회하지 않는다)", async () => {
    // 이 훅은 모든 탭 상단 스트립에 붙어 있어 탭만 바꿔도 언마운트된다. 취소가 없으면
    // 최대 5분간 3초마다 조회가 계속된다(2단계 전환으로 대기창이 90초 → 300초로 늘었다).
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => ({ job_id: "interp_zzz" }));
    let polls = 0;
    onGet("/analysis/interpretation/interp_zzz", async () => {
      polls += 1;
      return { status: "pending" }; // 끝나지 않는 잡
    });

    const { result, unmount } = renderHook(() => useAiInsight(ADDRESS));
    await act(async () => {
      void result.current.run();
      await new Promise((r) => setTimeout(r, 3500)); // 최소 1회 폴링
    });
    expect(polls).toBeGreaterThanOrEqual(1);

    unmount();
    const afterUnmount = polls;
    await new Promise((r) => setTimeout(r, 7000)); // 취소가 없으면 2회 이상 더 돈다
    expect(polls).toBe(afterUnmount);
  }, 20000);

  it("★주소가 바뀌면 이전 주소의 해석이 화면에 뜨지 않는다", async () => {
    // 이 훅은 address를 prop으로 받으므로 **언마운트 없이** 대상이 바뀐다. 취소하지 않으면
    // 이전 주소의 해석이 뒤늦게 도착해 새 주소 화면에 엉뚱한 값이 표시된다(적대검증 실측).
    onPost("/analysis/comprehensive", async () => CORE);
    onPost("/analysis/interpretation", async () => ({ job_id: "interp_addr" }));
    let polls = 0;
    onGet("/analysis/interpretation/interp_addr", async () => {
      polls += 1;
      // 첫 폴링은 미완, 이후 A 주소 해석을 돌려준다(주소 전환 뒤 도착하는 상황).
      return polls >= 2
        ? { status: "done", result: { ai_interpretation: { overall_summary: "A주소 해석" } } }
        : { status: "pending" };
    });

    const { result, rerender } = renderHook(({ addr }) => useAiInsight(addr), {
      initialProps: { addr: ADDRESS },
    });
    await act(async () => {
      void result.current.run();
      await new Promise((r) => setTimeout(r, 3500));
    });

    // 주소 전환 — 진행 중이던 A 주소 폴링은 취소돼야 한다.
    // (취소 catch가 setLoading을 부르므로 act로 감싼다 — 안 감싸면 경고만 남는다.)
    // ★스냅샷은 **취소가 정착한 뒤** 찍는다. 전환 직후에 찍으면 이미 대기 중이던 폴링 1회가
    //   뒤늦게 잡혀 취소가 정상 동작해도 실패한다(타이밍 취약 단언 회피).
    let afterSwitch = 0;
    await act(async () => {
      rerender({ addr: "서울특별시 강남구 테헤란로 152" });
      await new Promise((r) => setTimeout(r, 3500)); // 취소 정착 + 대기 중이던 1회 소화
      afterSwitch = polls;
      await new Promise((r) => setTimeout(r, 7000)); // 취소가 없으면 2회 이상 더 돈다
    });

    expect(polls).toBe(afterSwitch);          // 폴링 정지
    expect(result.current.ai).toBeNull();     // A의 해석이 B 화면에 뜨지 않는다
    // 로딩이 영구 true로 굳지 않는다(굳으면 중복 가드에 걸려 다시는 실행되지 않는다).
    expect(result.current.loading).toBe(false);
  }, 20000);
});
