import { describe, expect, it } from "vitest";

import { classifyVWorldXmlException } from "./vworld-xml-exception";

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
