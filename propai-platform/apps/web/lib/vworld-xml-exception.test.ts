import { describe, expect, it } from "vitest";

import {
  classifyVWorldXmlException,
  extractVWorldXmlExceptionDetail,
  isVWorldKeyFault,
} from "./vworld-xml-exception";

/** 2026-07-17 라이브 채증 원문 — WMTS(OWS 1.1)는 WMS와 스키마가 다르다.
 *  회색 배경지도 전역 미표시의 근본: tiletype "gray"는 실존하지 않는 값이었고,
 *  상류가 유효값을 본문에 직접 열거해 줬다. */
const OWS_TILETYPE_LIVE = `<?xml version="1.0" encoding="UTF-8"?>
<ExceptionReport xmlns="http://www.opengis.net/ows/1.1"
\txmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
\txsi:schemaLocation="http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd"
\tversion="1.1.0" xml:lang="kor">
\t<Exception exceptionCode="InvalidParameterValue" locator="tiletype">
\t\t<ExceptionText>
<![CDATA[tiletype 파라미터의 값이 유효한 범위를 넘었습니다. 유효한 파라미터 값의 범위 : [Base, midnight, Hybrid, Satellite, white], 입력한 파라미터 값 : gray]]>
</ExceptionText>
\t</Exception>
</ExceptionReport>`;

/** 2026-07-17 라이브 채증 — 같은 exceptionCode(InvalidParameterValue)인데 locator만 다르다.
 *  이래서 code 단독 판정이 위험하다(키 결함 vs 레이어명 오기 — 조치가 정반대). */
const OWS_KEY_LIVE = `<?xml version="1.0" encoding="UTF-8"?>
<ExceptionReport xmlns="http://www.opengis.net/ows/1.1" version="1.1.0" xml:lang="kor">
\t<Exception exceptionCode="InvalidParameterValue" locator="key">
\t\t<ExceptionText><![CDATA[등록되지 않은 인증키입니다.]]></ExceptionText>
\t</Exception>
</ExceptionReport>`;

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

  it("★OWS(WMTS) ExceptionReport에서 code·locator·CDATA 메시지를 추출한다", () => {
    // 종전 파서는 WMS 형식만 알아 WMTS에서 code 추출이 100% 실패했다 →
    // 모든 WMTS 오류가 "(auth/unknown)"으로 은폐(회색 배경지도 미표시의 진단을 막은 근본).
    const detail = extractVWorldXmlExceptionDetail(OWS_TILETYPE_LIVE);
    expect(detail.code).toBe("InvalidParameterValue");
    expect(detail.locator).toBe("tiletype");
    expect(detail.message).toContain("tiletype 파라미터");
    expect(detail.message).not.toContain("CDATA"); // CDATA 래퍼는 벗겨서 담는다
  });

  it("★<ExceptionReport>·<ExceptionText>를 <Exception>으로 오탐하지 않는다(접두 동일)", () => {
    // \s 경계가 없으면 <ExceptionReport ...>가 먼저 매칭돼 엉뚱한 속성을 잡는다.
    const detail = extractVWorldXmlExceptionDetail(OWS_TILETYPE_LIVE);
    expect(detail.code).not.toBe("1.1.0"); // ExceptionReport@version 오탐 금지
  });

  it("OWS 키 오류 원문에서 locator=key를 추출한다", () => {
    const detail = extractVWorldXmlExceptionDetail(OWS_KEY_LIVE);
    expect(detail.code).toBe("InvalidParameterValue");
    expect(detail.locator).toBe("key");
    expect(detail.message).toBe("등록되지 않은 인증키입니다.");
  });
});

describe("isVWorldKeyFault", () => {
  it("WMS 키 결함 코드(INVALID_KEY·INCORRECT_KEY)는 키 결함으로 인정한다", () => {
    expect(isVWorldKeyFault({ code: "INVALID_KEY" })).toBe(true);
    expect(isVWorldKeyFault({ code: "INCORRECT_KEY" })).toBe(true);
  });

  it("WMS 파라미터 오류(INVALID_RANGE)는 키 결함이 아니다(재시도 무의미)", () => {
    expect(isVWorldKeyFault({ code: "INVALID_RANGE" })).toBe(false);
  });

  it("★OWS 키 오류(InvalidParameterValue + locator=key)는 키 결함으로 인정한다", () => {
    expect(isVWorldKeyFault(extractVWorldXmlExceptionDetail(OWS_KEY_LIVE))).toBe(true);
  });

  it("★OWS 레이어명 오기(같은 code + locator=tiletype)는 키 결함이 아니다", () => {
    // code만으로 판정하면 여기서 true가 되어, 키를 바꿔도 안 고쳐질 오류에
    // 무의미한 폴백 재중계가 돌아 지연만 2배가 된다 — locator로 갈라야 하는 이유.
    expect(isVWorldKeyFault(extractVWorldXmlExceptionDetail(OWS_TILETYPE_LIVE))).toBe(false);
  });

  it("code 없음·null·undefined는 키 결함이 아니다", () => {
    expect(isVWorldKeyFault({})).toBe(false);
    expect(isVWorldKeyFault(null)).toBe(false);
    expect(isVWorldKeyFault(undefined)).toBe(false);
  });
});
