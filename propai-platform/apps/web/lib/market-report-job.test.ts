import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api-client";
import {
  MARKET_REPORT_JOB_STORAGE_KEY,
  clearActiveMarketReportJob,
  readActiveMarketReportJob,
  resumeMarketReportJob,
  saveActiveMarketReportJob,
  submitMarketReportJob,
} from "@/lib/market-report-job";

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
}));

describe("market-report-job — sessionStorage 잡 복원", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("saveActiveMarketReportJob → readActiveMarketReportJob 왕복", () => {
    saveActiveMarketReportJob("job-123", 1_700_000_000_000);
    const raw = window.sessionStorage.getItem(MARKET_REPORT_JOB_STORAGE_KEY);
    expect(raw).not.toBeNull();
    // address 미전달 시 null로 저장(구 호출부 무회귀).
    expect(readActiveMarketReportJob()).toEqual({ jobId: "job-123", startedAt: 1_700_000_000_000, address: null });
  });

  it("saveActiveMarketReportJob(address 포함) → readActiveMarketReportJob이 address를 보존한다", () => {
    saveActiveMarketReportJob("job-124", 1_700_000_000_001, "서울시 강남구");
    expect(readActiveMarketReportJob()).toEqual({
      jobId: "job-124",
      startedAt: 1_700_000_000_001,
      address: "서울시 강남구",
    });
  });

  it("저장된 잡이 없으면 null", () => {
    expect(readActiveMarketReportJob()).toBeNull();
  });

  it("손상된(JSON 아닌) 값은 null을 반환한다(크래시 없음)", () => {
    window.sessionStorage.setItem(MARKET_REPORT_JOB_STORAGE_KEY, "{invalid-json");
    expect(readActiveMarketReportJob()).toBeNull();
  });

  it("jobId가 없는 값은 흔적을 지우고 null을 반환한다", () => {
    window.sessionStorage.setItem(MARKET_REPORT_JOB_STORAGE_KEY, JSON.stringify({ startedAt: 1 }));
    expect(readActiveMarketReportJob()).toBeNull();
    expect(window.sessionStorage.getItem(MARKET_REPORT_JOB_STORAGE_KEY)).toBeNull();
  });

  it("clearActiveMarketReportJob은 흔적을 제거한다", () => {
    saveActiveMarketReportJob("job-456", Date.now());
    clearActiveMarketReportJob();
    expect(readActiveMarketReportJob()).toBeNull();
  });
});

describe("market-report-job — submitMarketReportJob(제출+폴링)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("캐시 적중 시 제출 응답에 result가 바로 실려오면 폴링 없이 즉시 반환한다", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      job_id: null,
      status: "done",
      result: { avm: null, totalCount: 5 },
    });
    const result = await submitMarketReportJob({ address: "서울시 강남구" });
    expect(result).toEqual({ avm: null, totalCount: 5 });
    expect(apiClient.get).not.toHaveBeenCalled();
    // 캐시 적중 경로는 폴링 자체가 없으므로 진행 잡 흔적을 남기지 않는다.
    expect(readActiveMarketReportJob()).toBeNull();
  });

  it("job_id가 없고 완료도 아니면 제출 실패로 처리한다", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ job_id: null, status: "pending" });
    await expect(submitMarketReportJob({ address: "서울시 강남구" })).rejects.toThrow(
      "보고서 작업 제출에 실패했습니다.",
    );
  });

  it("제출 시 body.address를 stale 가드 재료로 sessionStorage에 함께 저장한다", async () => {
    vi.useFakeTimers();
    vi.mocked(apiClient.post).mockResolvedValue({ job_id: "job-addr", status: "pending" });
    vi.mocked(apiClient.get).mockResolvedValueOnce({ status: "done", result: { ok: true } });

    const promise = submitMarketReportJob({ address: "서울시 강남구" });
    // 폴링 시작 전(비동기 마이크로태스크 이후) sessionStorage에 address가 실려있어야 한다.
    await vi.advanceTimersByTimeAsync(0);
    expect(readActiveMarketReportJob()?.address).toBe("서울시 강남구");

    await vi.advanceTimersByTimeAsync(4000);
    await promise;
  });

  it("제출 후 폴링으로 완료되면 결과를 반환하고 흔적을 제거한다", async () => {
    vi.useFakeTimers();
    vi.mocked(apiClient.post).mockResolvedValue({ job_id: "job-789", status: "pending" });
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ status: "pending" })
      .mockResolvedValueOnce({ status: "done", result: { totalCount: 42 } });

    const promise = submitMarketReportJob<{ totalCount: number }>({ address: "서울시 강남구" });

    // 폴링 간격(4초) x 2회 진행.
    await vi.advanceTimersByTimeAsync(4000);
    await vi.advanceTimersByTimeAsync(4000);

    const result = await promise;
    expect(result).toEqual({ totalCount: 42 });
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(readActiveMarketReportJob()).toBeNull(); // 완료 시 제거
  });

  it("폴링 중 오류 상태(error)이면 사유를 담아 throw하고 흔적을 제거한다", async () => {
    vi.useFakeTimers();
    vi.mocked(apiClient.post).mockResolvedValue({ job_id: "job-err", status: "pending" });
    vi.mocked(apiClient.get).mockResolvedValueOnce({ status: "error", error: "잔액 부족" });

    const promise = submitMarketReportJob({ address: "서울시 강남구" });
    const assertion = expect(promise).rejects.toThrow("잔액 부족");
    await vi.advanceTimersByTimeAsync(4000);
    await assertion;
    expect(readActiveMarketReportJob()).toBeNull();
  });
});

describe("market-report-job — resumeMarketReportJob(리로드 복원 이어서 폴링)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.mocked(apiClient.get).mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("신규 제출 없이 기존 job_id를 이어서 폴링해 완료 결과를 반환한다", async () => {
    vi.useFakeTimers();
    saveActiveMarketReportJob("job-resume", Date.now());
    vi.mocked(apiClient.get).mockResolvedValueOnce({ status: "done", result: { ok: true } });

    const promise = resumeMarketReportJob<{ ok: boolean }>("job-resume");
    await vi.advanceTimersByTimeAsync(4000);
    const result = await promise;

    expect(result).toEqual({ ok: true });
    expect(readActiveMarketReportJob()).toBeNull();
  });

  it("currentAddress가 저장된 address와 같으면(주소 불변) 정상 재개한다", async () => {
    vi.useFakeTimers();
    saveActiveMarketReportJob("job-same-addr", Date.now(), "서울시 강남구");
    vi.mocked(apiClient.get).mockResolvedValueOnce({ status: "done", result: { ok: true } });

    const promise = resumeMarketReportJob<{ ok: boolean }>("job-same-addr", "서울시 강남구");
    await vi.advanceTimersByTimeAsync(4000);
    const result = await promise;

    expect(result).toEqual({ ok: true });
    expect(readActiveMarketReportJob()).toBeNull();
  });

  it("stale 가드: currentAddress가 저장된 address와 다르면 폴링 없이 스킵하고 흔적을 제거한다(null 반환)", async () => {
    saveActiveMarketReportJob("job-stale", Date.now(), "서울시 강남구");

    const result = await resumeMarketReportJob<{ ok: boolean }>("job-stale", "부산시 해운대구");

    expect(result).toBeNull();
    expect(apiClient.get).not.toHaveBeenCalled(); // 폴링 자체가 시작되지 않아야 한다
    expect(readActiveMarketReportJob()).toBeNull(); // 흔적 제거
  });

  it("currentAddress를 전달하지 않으면 가드를 건너뛰고 기존 동작대로 재개한다(무회귀)", async () => {
    vi.useFakeTimers();
    saveActiveMarketReportJob("job-noaddr", Date.now(), "서울시 강남구");
    vi.mocked(apiClient.get).mockResolvedValueOnce({ status: "done", result: { ok: true } });

    const promise = resumeMarketReportJob<{ ok: boolean }>("job-noaddr");
    await vi.advanceTimersByTimeAsync(4000);
    const result = await promise;

    expect(result).toEqual({ ok: true });
  });

  it("저장된 잡에 address가 없으면(구 데이터) 가드를 건너뛰고 재개한다(무회귀)", async () => {
    vi.useFakeTimers();
    saveActiveMarketReportJob("job-legacy", Date.now()); // address 미전달 → null 저장
    vi.mocked(apiClient.get).mockResolvedValueOnce({ status: "done", result: { ok: true } });

    const promise = resumeMarketReportJob<{ ok: boolean }>("job-legacy", "아무 주소");
    await vi.advanceTimersByTimeAsync(4000);
    const result = await promise;

    expect(result).toEqual({ ok: true });
  });
});
