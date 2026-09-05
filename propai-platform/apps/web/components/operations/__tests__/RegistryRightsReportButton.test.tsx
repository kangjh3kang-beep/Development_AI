/**
 * 권리분석 보고서 버튼의 **렌더 락**.
 *
 * 중심 요구: "받아진다"가 아니라 **분모를 말하는가**. 미분석 필지가 있는데 "보고서 받기"만
 * 있으면 사용자는 전 필지가 담긴 줄 안다 — 문서가 "N필지 전부 안전"으로 읽힌다.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "@/lib/api-client";

import { RegistryRightsReportButton } from "../RegistryRightsReportButton";

// ★`apiClient.download` **만** 갈아 끼운다. `apiErrorMessage` 는 **진짜**를 쓴다 —
//   그것이 서버 사유를 꺼내는 층이고, 목으로 대체하면 «사유를 보여 준다» 계약이 무잠금이 된다.
//   (종전 이 파일은 `apiClient` 를 통째로 얕게 목해서, 컴포넌트가 `download` 로 옮겨간 순간
//    세 계약이 한꺼번에 깨졌다. 형제 테스트를 안 돌린 채 이관한 결과다.)
// ★`vi.mock` 은 **호이스팅**된다 — 평범한 `const` 로 두면 팩토리가 그것보다 먼저 평가돼
//   `Cannot access 'download' before initialization` 이 난다(첫 실행 실측).
const { download } = vi.hoisted(() => ({ download: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, download } };
});

const 성공 = { jibun: "가", result: { status: "ok", ai: { generated: true } } };
const 폴백 = { jibun: "나", result: { status: "ok", ai: { generated: false } } };

type DownloadCall = [string, { method?: string; body?: Record<string, unknown> }];
const calls = () => download.mock.calls as unknown as DownloadCall[];

beforeEach(() => {
  download.mockReset();
  download.mockResolvedValue(new Blob(["x"]));
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:x"), writable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), writable: true });
});
afterEach(() => vi.unstubAllGlobals());

describe("권리분석 보고서 다운로드", () => {
  it("★★분모를 적는다 — 미분석이 있으면 그 수까지 말한다", () => {
    render(<RegistryRightsReportButton items={[성공, 폴백]} />);
    const scope = screen.getByTestId("rights-report-scope").textContent!;
    expect(scope).toContain("분석 1 / 전체 2");
    expect(scope).toContain("미분석 1");
  });

  it("대조군 — 전부 분석됐으면 미분석 문구를 만들지 않는다", () => {
    render(<RegistryRightsReportButton items={[성공]} />);
    const scope = screen.getByTestId("rights-report-scope").textContent!;
    expect(scope).toContain("전체 1필지 분석 완료");
    expect(scope).not.toContain("미분석");
  });

  it("★미분석 필지도 **요청에 포함**해 보낸다 — 빼면 보고서가 전부 안전이라 말한다", async () => {
    render(<RegistryRightsReportButton items={[성공, 폴백]} />);
    fireEvent.click(screen.getByTestId("rights-report-pdf"));
    await waitFor(() => expect(calls()).toHaveLength(1));
    const [path, init] = calls()[0];
    const body = init.body as { items: { jibun: string }[]; format: string };
    expect(body.items.map((i) => i.jibun)).toEqual(["가", "나"]);
    expect(body.format).toBe("pdf");
    expect(path).toBe("/registry/rights-report");
    expect(init.method).toBe("POST");
  });

  it("DOCX 버튼은 format 을 바꿔 보낸다(두 버튼이 같은 일을 하지 않는다)", async () => {
    render(<RegistryRightsReportButton items={[성공]} />);
    fireEvent.click(screen.getByTestId("rights-report-docx"));
    await waitFor(() => expect(calls()).toHaveLength(1));
    expect((calls()[0][1].body as { format: string }).format).toBe("docx");
  });

  it("★★공용 클라이언트를 **경유한다** — 손수 fetch 로 되돌아가면 401 갱신을 못 받는다", async () => {
    // 결함이 살던 자리에 대한 직접 단언. 배선이 끊기면 `download` 가 안 불린다.
    const raw = vi.fn();
    vi.stubGlobal("fetch", raw);
    render(<RegistryRightsReportButton items={[성공]} />);
    fireEvent.click(screen.getByTestId("rights-report-pdf"));
    await waitFor(() => expect(calls()).toHaveLength(1));
    expect(raw).not.toHaveBeenCalled();
  });

  it("★서버가 준 사유를 그대로 보여 준다(HTTP 코드만 보이면 못 고친다)", async () => {
    // ★진짜 `ApiClientError` 를 던진다 — 사유는 `payload.detail` 에 있고 `message` 는 상수다.
    download.mockRejectedValue(
      new ApiClientError("API 요청 처리에 실패했습니다.", 400, {
        detail: "한 번에 300필지까지 가능합니다",
      }),
    );
    render(<RegistryRightsReportButton items={[성공]} />);
    fireEvent.click(screen.getByTestId("rights-report-pdf"));
    await waitFor(() => expect(screen.getByTestId("rights-report-error")).toBeTruthy());
    expect(screen.getByTestId("rights-report-error").textContent).toContain("300필지");
  });

  it("★사유가 없는 실패도 **단서를 남긴다** — 타임아웃·네트워크가 한 문장으로 뭉개지지 않는다", async () => {
    // 세 모집단. 이것이 없으면 「전부 같은 fallback」 구현이 위 테스트를 통과한다.
    for (const [err, expected] of [
      [new ApiClientError("요청 시간이 초과되었습니다(300초). 서버 응답이 지연되고 있습니다.", 408, null), "초과"],
      [new ApiClientError("네트워크 오류 — 연결이 지연되거나 끊겼습니다. 다시 시도해 주세요.", 0, null), "네트워크"],
      [new ApiClientError("API 요청 처리에 실패했습니다.", 502, null), "HTTP 502"],
    ] as const) {
      download.mockRejectedValueOnce(err);
      const { unmount } = render(<RegistryRightsReportButton items={[성공]} />);
      fireEvent.click(screen.getByTestId("rights-report-pdf"));
      await waitFor(() =>
        expect(screen.getByTestId("rights-report-error").textContent).toContain(expected),
      );
      unmount();
    }
  });

  it("결과가 없으면 누를 수 없다", () => {
    render(<RegistryRightsReportButton items={[]} />);
    expect(screen.getByTestId("rights-report-pdf")).toBeDisabled();
  });
});
