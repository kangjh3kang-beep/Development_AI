/**
 * VWorld WMS/WMTS 200+XML(ServiceExceptionReport) 본문 분류 — 공용 헬퍼.
 *
 * ★배경(PR#329 R1 리뷰 MEDIUM2): VWorld는 인증 실패·권한 없음도 HTTP 200 + XML
 *   ExceptionReport로 반환한다(정상적 '무제공영역(coverage gap)'과 동일한 전송 형태).
 *   종전 프록시(vworld-wms-proxy.ts·vworld-wmts-proxy.ts)는 content-type이 xml이기만
 *   하면 본문을 읽지 않고 전부 투명타일로 흡수했다 — 키 미설정·쿼터 초과 같은 실제
 *   인증/권한 오류까지 "정상 무제공영역"으로 위장돼 무음 실패했다(무목업 원칙 위반).
 *
 * 이 분류기는 XML 본문 텍스트를 읽어 (1) 실측 확인된 무제공영역 문구("FileNotFound"·
 * "제공영역")만 좁게 coverage로 인정하고, (2) 그 외 전부(인증/권한 키워드 포함, 불명 문구
 * 포함)는 auth로 승격해 프록시가 503으로 관측 가능하게 만든다.
 *
 * ★트레이드오프(정직 고지): VWorld가 무제공영역 문구를 변경하면 coverage 판정이
 *   실패해 정상 케이스도 503(지도 회색)으로 보일 수 있다 — "조용히 넘어가는 실패"보다
 *   "시끄러운 실패"를 택한 것(무목업 원칙 우선). 실측 문구는 두 프록시의 기존 vitest
 *   회귀(FileNotFound·서비스 제공영역이 아닙니다)로 고정한다.
 */

export type VWorldXmlExceptionKind = "coverage" | "auth";

const COVERAGE_PATTERN = /filenotfound|제공\s*영역/i;

/**
 * XML ExceptionReport 본문 텍스트를 분류한다.
 *   coverage → 정상 무제공영역(투명타일로 흡수, 지도 유지)
 *   auth     → 인증/권한/불명 오류(503으로 승격 — 무음 실패 금지)
 */
export function classifyVWorldXmlException(xmlText: string): VWorldXmlExceptionKind {
  return COVERAGE_PATTERN.test(xmlText) ? "coverage" : "auth";
}

/** ServiceException 원인 상세 — code(예: INVALID_KEY·INVALID_RANGE)와 메시지 본문. */
export interface VWorldXmlExceptionDetail {
  /** 오류 코드 — WMS `<ServiceException code="...">` 또는 OWS `<Exception exceptionCode="...">`.
   *  (없으면 undefined) */
  code?: string;
  /** 예외 요소의 텍스트(없으면 undefined, 120자 절단). OWS는 `<ExceptionText>` CDATA를 벗겨 담는다. */
  message?: string;
  /** OWS 전용 — 문제가 된 파라미터명(`locator="tiletype"`·`locator="key"`). WMS엔 없다.
   *  ★OWS의 exceptionCode는 InvalidParameterValue 하나로 뭉뚱그려지므로, 원인 구분은
   *   locator로만 가능하다(tiletype=레이어명 오기 / key=인증키 무효 — 조치가 정반대). */
  locator?: string;
}

// ★(?:\s[^>]*)?> 경계 필수 — 단순 [^>]* 는 <ServiceExceptionReport>(접두 동일)도 매칭해
//   Report 태그부터 캡처가 시작되는 오탐이 났다(테스트로 고정).
const CODE_PATTERN = /<ServiceException\s[^>]*\bcode="([^"]+)"/i;
const MESSAGE_PATTERN = /<ServiceException(?:\s[^>]*)?>([\s\S]*?)<\/ServiceException>/i;

// ── OWS 1.1 ExceptionReport (WMTS 계열) ──
// ★2026-07-17 라이브 채증: WMS(ServiceExceptionReport/ServiceException@code)와 WMTS
//   (OWS ExceptionReport/Exception@exceptionCode)는 **XML 스키마가 다르다**. 종전 파서는
//   WMS 형식만 알아 WMTS 응답에서 code 추출이 100% 실패했고, 그 결과 (1)모든 WMTS 오류가
//   "(auth/unknown)"으로 뭉뚱그려져 진짜 원인(tiletype 오기)이 은폐됐으며 (2)키-오류
//   페일오버(isVWorldKeyFault)가 단 한 번도 발화하지 못했다(code가 항상 undefined).
// ★`<Exception\s` 경계 필수 — <ExceptionReport>·<ExceptionText>가 접두 동일이라 \s 없이는 오탐.
// ★첫 <Exception ...> 여는 태그를 통째로 먼저 잘라낸 뒤 그 안에서만 속성을 뽑는다.
//   code/locator를 문서 전역에서 각각 독립 검색하면, OWS 1.1이 Exception을 unbounded로
//   허용하므로 서로 다른 Exception 요소의 속성이 조합돼 유령 detail이 만들어진다
//   (예: 1번 요소의 code + 2번 요소의 locator="key" → 키 결함 오판 → 무의미 재중계).
const OWS_ELEMENT_PATTERN = /<(?:\w+:)?Exception\s[^>]*>/i;
const OWS_CODE_ATTR = /\bexceptionCode="([^"]+)"/i;
const OWS_LOCATOR_ATTR = /\blocator="([^"]+)"/i;
const OWS_TEXT_PATTERN = /<(?:\w+:)?ExceptionText(?:\s[^>]*)?>([\s\S]*?)<\/(?:\w+:)?ExceptionText>/i;
// OWS ExceptionText 본문은 CDATA로 감싸 오는 것이 실측 기본형.
const CDATA_PATTERN = /^\s*<!\[CDATA\[([\s\S]*?)\]\]>\s*$/;

function stripCdata(raw: string): string {
  return (CDATA_PATTERN.exec(raw)?.[1] ?? raw).trim();
}

/**
 * ServiceExceptionReport에서 원인 code·메시지를 추출한다 — 오류 표면화용.
 *
 * ★배경(2026-07-17 지적타일 진단): 종전 프록시는 auth/불명을 전부
 *   "(auth/unknown)"으로 뭉뚱그려 503을 냈다. 실제 원인이 INVALID_RANGE(WMS VERSION
 *   1.1.1 미지원 — 파라미터 오류)였는데도 "키 미설정" 계열로 오독됐다. code를 그대로
 *   표면화하면 INVALID_KEY(키 미등록)·UNREGISTERED_DOMAIN(도메인)·INVALID_RANGE(파라미터)
 *   가 즉시 구분된다. 추출 실패 시 undefined — 분류(classify)에는 영향 없음.
 */
export function extractVWorldXmlExceptionDetail(xmlText: string): VWorldXmlExceptionDetail {
  // WMS(ServiceException) 우선 → 없으면 OWS(Exception). 두 스키마는 상호배타라 순서 무관하지만,
  // WMS가 기존 계약이므로 먼저 시도해 회귀 위험을 0으로 둔다.
  const wmsCode = CODE_PATTERN.exec(xmlText)?.[1]?.trim() || undefined;
  const wmsMessage = MESSAGE_PATTERN.exec(xmlText)?.[1]?.trim() || undefined;
  if (wmsCode || wmsMessage) {
    return { code: wmsCode, message: wmsMessage ? wmsMessage.slice(0, 120) : undefined };
  }

  // 첫 Exception 요소의 여는 태그 안에서만 속성을 뽑는다(요소 간 속성 혼합 방지).
  const owsTag = OWS_ELEMENT_PATTERN.exec(xmlText)?.[0] ?? "";
  const code = OWS_CODE_ATTR.exec(owsTag)?.[1]?.trim() || undefined;
  const locator = OWS_LOCATOR_ATTR.exec(owsTag)?.[1]?.trim() || undefined;
  const rawText = OWS_TEXT_PATTERN.exec(xmlText)?.[1];
  const message = rawText ? stripCdata(rawText).slice(0, 120) || undefined : undefined;
  return { code, message, locator };
}

/** 키 자체 무효 코드(라이브 채증: INVALID_KEY 2026-07-17 로컬, INCORRECT_KEY 2026-07-17 프로드).
 *  파라미터 오류(INVALID_RANGE 등)와 달리 다른 키(관리자 등록)로 재시도할 가치가 있다. */
export const VWORLD_KEY_FAULT_CODES = new Set(["INVALID_KEY", "INCORRECT_KEY"]);

/**
 * 다른 키(관리자 등록)로 재시도할 가치가 있는 "키 자체 무효" 오류인지 판정한다.
 *
 * · WMS  — code가 INVALID_KEY·INCORRECT_KEY (코드만으로 확정. locator 개념 없음).
 * · OWS  — ★**locator 단독으로 판정한다.** code는 InvalidParameterValue 하나가 tiletype
 *          오기(레이어명 문제 — 키를 바꿔도 절대 안 고쳐짐)와 키 무효 양쪽에 공용이라
 *          code만으로는 판정 불가다. 반대로 locator="key"는 그 자체로 "key 파라미터가
 *          문제"라는 상류의 단언이므로 code를 함께 요구할 이유가 없다 — 오히려 상류가
 *          code를 바꾸면(NoApplicableCode 등) 게이트가 통째로 죽어, 이 함수가 고치려던
 *          "무음 페일오버 불발"이 그대로 재현된다.
 *          (라이브 채증 2026-07-17: locator=key → "등록되지 않은 인증키입니다",
 *           locator=tiletype → "유효한 파라미터 값의 범위 : [...]".)
 */
export function isVWorldKeyFault(detail?: VWorldXmlExceptionDetail | null): boolean {
  if (detail?.locator?.toLowerCase() === "key") return true;
  const code = detail?.code;
  return !!code && VWORLD_KEY_FAULT_CODES.has(code);
}
