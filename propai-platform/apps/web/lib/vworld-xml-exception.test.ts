import { describe, expect, it } from "vitest";

import { classifyVWorldXmlException, extractVWorldXmlExceptionDetail } from "./vworld-xml-exception";

describe("classifyVWorldXmlException", () => {
  it("실측 무제공영역 문구(FileNotFound)는 coverage로 분류한다", () => {
    expect(classifyVWorldXmlException("<ExceptionReport>FileNotFound</ExceptionReport>")).toBe("coverage");
    expect(classifyVWorldXmlException("filenotfound: no tile")).toBe("coverage"); // 대소문자 무관
  });

  it("실측 무제공영역 문구(서비스 제공영역이 아닙니다)는 coverage로 분류한다", () => {
    expect(
      classifyVWorldXmlException("<ExceptionReport>서비스 제공영역이 아닙니다</ExceptionReport>"),
    ).toBe("coverage");
  });

  it("★인증/권한 오류 문구는 auth로 분류한다(무음 흡수 금지)", () => {
    expect(
      classifyVWorldXmlException(
        '<ServiceException code="INVALID_KEY">인증에 실패했습니다</ServiceException>',
      ),
    ).toBe("auth");
  });

  it("★불명(coverage 문구가 없는 그 외 전부)은 안전 측(auth=503 승격)으로 분류한다", () => {
    expect(classifyVWorldXmlException("<ServiceException>unexpected internal error</ServiceException>")).toBe(
      "auth",
    );
    expect(classifyVWorldXmlException("")).toBe("auth");
  });
});

describe("extractVWorldXmlExceptionDetail", () => {
  it("★2026-07-17 라이브 채증 원문(INVALID_RANGE — WMS VERSION 1.1.1 거부)에서 code·메시지를 추출한다", () => {
    // 실제 VWorld 응답 원문 그대로 — 지적타일 실패의 진짜 근본원인이 "키"가 아니라
    // "VERSION 파라미터"였음을 code로 즉시 구분할 수 있어야 한다.
    const live =
      '<?xml version="1.0" encoding="UTF-8" ?>\n<ServiceExceptionReport version="1.3.0" xmlns="http://www.opengis.net/ogc">\n<ServiceException code="INVALID_RANGE">VERSION 파라미터의 값이 유효한 범위를 넘었습니다. 유효한 파라미터 값의 범위 : [1.3.0], 입력한 파라미터 값 : 1.1.1</ServiceException>\n</ServiceExceptionReport>';
    const detail = extractVWorldXmlExceptionDetail(live);
    expect(detail.code).toBe("INVALID_RANGE");
    expect(detail.message).toContain("VERSION 파라미터");
  });

  it("INVALID_KEY(키 미등록) 원문에서 code를 추출한다", () => {
    const detail = extractVWorldXmlExceptionDetail(
      '<ServiceExceptionReport><ServiceException code="INVALID_KEY">등록되지 않은 인증키입니다.</ServiceException></ServiceExceptionReport>',
    );
    expect(detail.code).toBe("INVALID_KEY");
    expect(detail.message).toBe("등록되지 않은 인증키입니다.");
  });

  it("code 속성이 없거나 XML이 아니면 undefined(분류에는 영향 없음)", () => {
    expect(extractVWorldXmlExceptionDetail("<ServiceException>no code attr</ServiceException>")).toEqual({
      code: undefined,
      message: "no code attr",
    });
    expect(extractVWorldXmlExceptionDetail("not xml at all")).toEqual({ code: undefined, message: undefined });
    expect(extractVWorldXmlExceptionDetail("")).toEqual({ code: undefined, message: undefined });
  });

  it("긴 메시지는 120자로 절단한다(로그 폭주 방지)", () => {
    const long = `<ServiceException code="X">${"가".repeat(300)}</ServiceException>`;
    expect(extractVWorldXmlExceptionDetail(long).message).toHaveLength(120);
  });
});
