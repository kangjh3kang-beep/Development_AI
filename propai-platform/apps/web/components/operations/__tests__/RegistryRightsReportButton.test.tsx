/**
 * 권리분석 보고서 버튼의 **렌더 락**.
 *
 * 중심 요구: "받아진다"가 아니라 **분모를 말하는가**. 미분석 필지가 있는데 "보고서 받기"만
 * 있으면 사용자는 전 필지가 담긴 줄 안다 — 문서가 "N필지 전부 안전"으로 읽힌다.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RegistryRightsReportButton } from "../RegistryRightsReportButton";

vi.mock("@/lib/api-client", () => ({
  apiClient: { getRuntimeConfig: () => ({ apiBaseUrl: "https://api.test" }) },
}));

const 성공 = { jibun: "가", result: { status: "ok", ai: { generated: true } } };
const 폴백 = { jibun: "나", result: { status: "ok", ai: { generated: false } } };

let calls: { url: string; body: unknown }[] = [];

beforeEach(() => {
  calls = [];
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:x"), writable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), writable: true });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: { body: string }) => {
      calls.push({ url, body: JSON.parse(init.body) });
      return { ok: true, status: 200, blob: async () => new Blob(["x"]) };
    }),
  );
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
    await waitFor(() => expect(calls).toHaveLength(1));
    const body = calls[0].body as { items: { jibun: string }[]; format: string };
    expect(body.items.map((i) => i.jibun)).toEqual(["가", "나"]);
    expect(body.format).toBe("pdf");
    expect(calls[0].url).toBe("https://api.test/registry/rights-report");
  });

  it("DOCX 버튼은 format 을 바꿔 보낸다(두 버튼이 같은 일을 하지 않는다)", async () => {
    render(<RegistryRightsReportButton items={[성공]} />);
    fireEvent.click(screen.getByTestId("rights-report-docx"));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect((calls[0].body as { format: string }).format).toBe("docx");
  });

  it("★서버가 준 사유를 그대로 보여 준다(HTTP 코드만 보이면 못 고친다)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 400,
        json: async () => ({ detail: "한 번에 300필지까지 가능합니다" }),
      })),
    );
    render(<RegistryRightsReportButton items={[성공]} />);
    fireEvent.click(screen.getByTestId("rights-report-pdf"));
    await waitFor(() => expect(screen.getByTestId("rights-report-error")).toBeTruthy());
    expect(screen.getByTestId("rights-report-error").textContent).toContain("300필지");
  });

  it("결과가 없으면 누를 수 없다", () => {
    render(<RegistryRightsReportButton items={[]} />);
    expect(screen.getByTestId("rights-report-pdf")).toBeDisabled();
  });
});
