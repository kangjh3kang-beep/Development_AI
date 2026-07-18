import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { optionsSummary, useAnalysisHistory } from "@/lib/use-analysis-history";

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn() },
  hasAccessToken: vi.fn(),
}));

// hasAccessToken은 별도 export이므로 모킹 모듈에서 다시 가져와 mockReturnValue를 제어한다.
import { hasAccessToken } from "@/lib/api-client";

describe("useAnalysisHistory", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(hasAccessToken).mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("주소가 없으면 조회 없이 빈 상태를 반환한다", async () => {
    vi.mocked(hasAccessToken).mockReturnValue(true);
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "market_report", address: "", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries).toEqual([]);
    expect(result.current.latest).toBeNull();
    expect(apiClient.get).not.toHaveBeenCalled();
  });

  it("비로그인(토큰 없음)이면 조회 없이 빈 상태를 반환한다(오류 아님)", async () => {
    vi.mocked(hasAccessToken).mockReturnValue(false);
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구 역삼동 1", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries).toEqual([]);
    expect(result.current.error).toBe("");
    expect(apiClient.get).not.toHaveBeenCalled();
  });

  it("401/403은 오류가 아니라 빈 상태로 정직 처리한다", async () => {
    vi.mocked(hasAccessToken).mockReturnValue(true);
    vi.mocked(apiClient.get).mockRejectedValue(new ApiClientError("unauthorized", 401, null));
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구 역삼동 1", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries).toEqual([]);
    expect(result.current.error).toBe("");
  });

  it("5xx/네트워크 오류는 error 메시지를 남기고 빈 목록을 유지한다", async () => {
    vi.mocked(hasAccessToken).mockReturnValue(true);
    vi.mocked(apiClient.get).mockRejectedValue(new ApiClientError("server error", 500, null));
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구 역삼동 1", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries).toEqual([]);
    expect(result.current.error).not.toBe("");
  });

  it("정상 응답 시 버전 내림차순으로 정렬하고 최신 엔트리를 노출한다", async () => {
    vi.mocked(hasAccessToken).mockReturnValue(true);
    vi.mocked(apiClient.get).mockResolvedValue([
      { version: 1, created_at: "2026-07-01T00:00:00Z", content_hash: "a", payload: { profit_rate_pct: 10 } },
      { version: 3, created_at: "2026-07-15T00:00:00Z", content_hash: "c", payload: { profit_rate_pct: 12 } },
      { version: 2, created_at: "2026-07-08T00:00:00Z", content_hash: "b", payload: { profit_rate_pct: 11 } },
    ]);
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "feasibility", address: "서울시 강남구 역삼동 1", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries.map((e) => e.version)).toEqual([3, 2, 1]);
    expect(result.current.latest?.version).toBe(3);
    expect(apiClient.get).toHaveBeenCalledWith(
      expect.stringContaining("/analysis-ledger/history?"),
      expect.objectContaining({ useMock: false, skipSessionExpiry: true }),
    );
  });

  it("{history:[...]} 래핑 응답(실제 백엔드 봉투 — analysis_ledger.py `/history`)을 정확히 읽는다", async () => {
    // ★버그 수정 회귀 테스트: 라우터는 `{ok, count, history}`를 내려준다(entries가 아니다).
    //   과거 코드는 `r?.entries`만 읽어 실운영에서 이 shape를 받으면 항상 빈 배열이었다 —
    //   이 테스트는 수정 전 코드였다면 FAIL했을 것이다(entries가 아닌 history 키 사용).
    vi.mocked(hasAccessToken).mockReturnValue(true);
    vi.mocked(apiClient.get).mockResolvedValue({
      ok: true,
      count: 1,
      history: [{ version: 1, created_at: "2026-07-01T00:00:00Z", content_hash: "a", payload: {} }],
    });
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "regulation", address: "서울시 강남구 역삼동 1", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries).toHaveLength(1);
    expect(result.current.latest?.version).toBe(1);
  });

  it("{entries:[...]} 래핑(레거시 방어 폴백)도 배열 응답과 동일하게 처리한다", async () => {
    vi.mocked(hasAccessToken).mockReturnValue(true);
    vi.mocked(apiClient.get).mockResolvedValue({
      entries: [{ version: 1, created_at: "2026-07-01T00:00:00Z", content_hash: "a", payload: {} }],
    });
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "regulation", address: "서울시 강남구 역삼동 1", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries).toHaveLength(1);
  });

  describe("isChanged — signature_parts idx2~4 비교(해시 비교 완전 제거)", () => {
    beforeEach(() => {
      vi.mocked(hasAccessToken).mockReturnValue(true);
    });

    // 실제 백엔드 shape: sha256[:16] 해시(input_signature) + 평문 배열(signature_parts)이
    //   항상 함께 적재된다(ledger_adapters.record_user_analysis). 두 키를 동시에 채워
    //   "해시가 있어도 절대 쓰지 않는다"를 증명한다.
    const REALISTIC_HASH = "a1b2c3d4e5f6a7b8"; // sha256 앞 16자 형태(join 문자열과 무관한 해시값)

    it("★변이 실증: idx0/1(주소·PNU)이 달라도 idx2~4가 같으면 변동 없음(false) — 수정 전 코드라면 " +
      "input_signature(해시)를 우선 비교해 무조건 true였다", async () => {
      vi.mocked(apiClient.get).mockResolvedValue([
        {
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          content_hash: "a",
          payload: {
            input_signature: REALISTIC_HASH,
            signature_parts: ["서울시 강남구", "1234", "1", "True", "a=1"],
          },
        },
      ]);
      const { result } = renderHook(() =>
        useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: "1234" }),
      );
      await waitFor(() => expect(result.current.loading).toBe(false));
      // idx0(address)·idx1(pnu)는 히스토리 조회 시점에 이미 다른 값으로 넣어봐도(체인 불변
      //   파트라 비교 제외) idx2~4(parcel_count/use_llm/options)만 저장값과 같으면 false.
      expect(
        result.current.isChanged(["완전히 다른 주소", "9999999999", "1", "True", "a=1"]),
      ).toBe(false);
    });

    it("idx2(parcel_count)가 다르면 변동 있음(true)", async () => {
      vi.mocked(apiClient.get).mockResolvedValue([
        {
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          content_hash: "a",
          payload: {
            input_signature: REALISTIC_HASH,
            signature_parts: ["서울시 강남구", "1234", "1", "True", ""],
          },
        },
      ]);
      const { result } = renderHook(() =>
        useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: "1234" }),
      );
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.isChanged(["서울시 강남구", "1234", "2", "True", ""])).toBe(true);
    });

    it("idx3(use_llm)은 대소문자 무관 비교 — 백엔드 'True'/'False' vs 프론트 'true'/'false'는 동일값", async () => {
      vi.mocked(apiClient.get).mockResolvedValue([
        {
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          content_hash: "a",
          payload: {
            input_signature: REALISTIC_HASH,
            signature_parts: ["서울시 강남구", "1234", "1", "True", ""],
          },
        },
      ]);
      const { result } = renderHook(() =>
        useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: "1234" }),
      );
      await waitFor(() => expect(result.current.loading).toBe(false));
      // 프론트는 String(true) === "true"(소문자) — 대소문자만 다르면 변동 아님(false).
      expect(result.current.isChanged(["서울시 강남구", "1234", "1", "true", ""])).toBe(false);
      // 실제 값이 다르면(True→false) 변동 있음(true).
      expect(result.current.isChanged(["서울시 강남구", "1234", "1", "false", ""])).toBe(true);
    });

    it("idx4(options_summary)가 다르면 변동 있음(true) — optionsSummary() canonical 문자열 비교", async () => {
      vi.mocked(apiClient.get).mockResolvedValue([
        {
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          content_hash: "a",
          payload: {
            input_signature: REALISTIC_HASH,
            signature_parts: ["서울시 강남구", "1234", "1", "True", "a=1,b=2"],
          },
        },
      ]);
      const { result } = renderHook(() =>
        useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: "1234" }),
      );
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.isChanged(["서울시 강남구", "1234", "1", "True", "a=1,b=2"])).toBe(false);
      expect(result.current.isChanged(["서울시 강남구", "1234", "1", "True", "a=1,b=3"])).toBe(true);
    });

    it("idx5+(예: market_report 필지세트 지문)는 프론트가 재계산 불가라 비교에서 제외한다", async () => {
      vi.mocked(apiClient.get).mockResolvedValue([
        {
          version: 1,
          created_at: "2026-07-01T00:00:00Z",
          content_hash: "a",
          payload: {
            input_signature: REALISTIC_HASH,
            // 6번째 파트(필지세트 지문) — 백엔드만 계산 가능.
            signature_parts: ["서울시 강남구", "1234", "2", "True", "", "9f8e7d6c5b4a"],
          },
        },
      ]);
      const { result } = renderHook(() =>
        useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: "1234" }),
      );
      await waitFor(() => expect(result.current.loading).toBe(false));
      // 프론트는 5파트만 조립해서 넘긴다(6번째가 없어도) — idx2~4만 같으면 false.
      expect(result.current.isChanged(["서울시 강남구", "1234", "2", "True", ""])).toBe(false);
    });

    it("signature_parts 자체가 없으면(구버전 데이터) 비교 기준 없음으로 간주해 가짜 변동 배너를 띄우지 않는다(false)", async () => {
      vi.mocked(apiClient.get).mockResolvedValue([
        { version: 1, created_at: "2026-07-01T00:00:00Z", content_hash: "a", payload: { input_signature: REALISTIC_HASH } },
      ]);
      const { result } = renderHook(() =>
        useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: "1234" }),
      );
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.isChanged(["아무 값이나", "0000", "9", "false", "x"])).toBe(false);
    });

    it("히스토리가 없으면(latest=null) 변동 없음(false)", async () => {
      vi.mocked(apiClient.get).mockResolvedValue([]);
      const { result } = renderHook(() =>
        useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: "1234" }),
      );
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.latest).toBeNull();
      expect(result.current.isChanged(["아무 값이나"])).toBe(false);
    });
  });

  it("refetch()를 호출하면 다시 조회한다", async () => {
    vi.mocked(hasAccessToken).mockReturnValue(true);
    vi.mocked(apiClient.get).mockResolvedValue([]);
    const { result } = renderHook(() =>
      useAnalysisHistory({ analysisType: "market_report", address: "서울시 강남구", pnu: null }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(apiClient.get).toHaveBeenCalledTimes(1);
    await act(async () => {
      await result.current.refetch();
    });
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });
});

describe("optionsSummary — 백엔드 ledger_adapters._options_summary() TS 미러", () => {
  it("빈/비-dict 옵션은 빈 문자열(옵션 없음과 동일 취급)", () => {
    expect(optionsSummary(undefined)).toBe("");
    expect(optionsSummary(null)).toBe("");
    expect(optionsSummary({})).toBe("");
  });

  it("키 정렬(중첩 dict 포함) — 백엔드 test_build_signature_parts_order_and_normalization과 동일 값", () => {
    // 백엔드: build_signature_parts(options={"b": 1, "a": {"z": 2, "y": 1}}) → parts[4] == "a={y:1,z:2},b=1"
    expect(optionsSummary({ b: 1, a: { z: 2, y: 1 } })).toBe("a={y:1,z:2},b=1");
  });

  it("삽입 순서와 무관하게 동일 문자열(정렬 정규화)", () => {
    expect(optionsSummary({ x: 1, y: 2 })).toBe(optionsSummary({ y: 2, x: 1 }));
  });

  it("bool은 Python str() 표기(True/False)로 — JS 소문자 true/false를 쓰면 저장값과 어긋난다", () => {
    expect(optionsSummary({ sgis: true, kosis: false })).toBe("kosis=False,sgis=True");
  });
});
