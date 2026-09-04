/**
 * 등기부 PDF 일괄 다운로드 버튼의 **렌더 락**.
 *
 * 중심 요구는 "받아진다"가 아니라 **"빠진 걸 말한다"** 다 — 라이브에서 저장된 서명 URL 중
 * 상당수가 이미 만료돼 있었고(발급 후 30일), 조용히 묶으면 누른 건수보다 적은 ZIP 이 나온다.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RegistryPdfBundleButton } from "../RegistryPdfBundleButton";

const EXPIRED =
  '{"statusCode":"400","error":"InvalidJWT","message":"\\"exp\\" claim timestamp check failed"}';

beforeEach(() => {
  // 저장 경로는 이 테스트의 대상이 아니다 — 다만 **불리는지**는 본다.
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:x"), writable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), writable: true });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "good"
        ? { ok: true, status: 200, text: async () => "", arrayBuffer: async () => new TextEncoder().encode("PDF").buffer }
        : { ok: false, status: 400, text: async () => EXPIRED, arrayBuffer: async () => new ArrayBuffer(0) },
    ),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("등기부 PDF 일괄 다운로드", () => {
  it("★받을 수 있는 건수를 버튼에 적는다(PDF 없는 행은 세지 않는다)", () => {
    render(
      <RegistryPdfBundleButton
        sources={[
          { jibun: "가", pdfUrl: "good" },
          { jibun: "나", pdfUrl: null },
        ]}
      />,
    );
    expect(screen.getByTestId("pdf-bundle-button").textContent).toContain("(1건)");
  });

  it("★받을 게 없으면 **왜 못 누르는지** 말한다 — 비활성만 두면 고장으로 읽힌다", () => {
    render(<RegistryPdfBundleButton sources={[{ jibun: "가", pdfUrl: null }]} />);
    expect(screen.getByTestId("pdf-bundle-button")).toBeDisabled();
    expect(screen.getByTestId("pdf-bundle-empty").textContent).toContain("발급된 등기부 PDF 가 없습니다");
  });

  it("★★끝나면 제외된 건을 **지번까지** 보여 준다", async () => {
    render(
      <RegistryPdfBundleButton
        sources={[
          { jibun: "내삼미동 448-2", pdfUrl: "good" },
          { jibun: "내삼미동 347-8", pdfUrl: "stale" },
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId("pdf-bundle-button"));
    await waitFor(() => expect(screen.getByTestId("pdf-bundle-summary")).toBeTruthy());
    expect(screen.getByTestId("pdf-bundle-summary").textContent).toContain("2건 중 1건");
    const excluded = screen.getByTestId("pdf-bundle-excluded").textContent!;
    expect(excluded).toContain("내삼미동 347-8");
    expect(excluded).toContain("만료");
  });

  it("★대조군 — 전부 담기면 제외 목록을 그리지 않는다(없는 경고를 만들지 않는다)", async () => {
    render(<RegistryPdfBundleButton sources={[{ jibun: "가", pdfUrl: "good" }]} />);
    fireEvent.click(screen.getByTestId("pdf-bundle-button"));
    await waitFor(() => expect(screen.getByTestId("pdf-bundle-summary")).toBeTruthy());
    expect(screen.queryByTestId("pdf-bundle-excluded")).toBeNull();
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it("담긴 게 0건이면 파일을 만들지 않는다(빈 ZIP 을 성공처럼 주지 않는다)", async () => {
    render(<RegistryPdfBundleButton sources={[{ jibun: "가", pdfUrl: "stale" }]} />);
    fireEvent.click(screen.getByTestId("pdf-bundle-button"));
    await waitFor(() => expect(screen.getByTestId("pdf-bundle-summary")).toBeTruthy());
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
