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
  /** `<ServiceException code="...">`의 code 속성(없으면 undefined). */
  code?: string;
  /** ServiceException 요소의 텍스트(없으면 undefined, 120자 절단). */
  message?: string;
}

// ★(?:\s[^>]*)?> 경계 필수 — 단순 [^>]* 는 <ServiceExceptionReport>(접두 동일)도 매칭해
//   Report 태그부터 캡처가 시작되는 오탐이 났다(테스트로 고정).
const CODE_PATTERN = /<ServiceException\s[^>]*\bcode="([^"]+)"/i;
const MESSAGE_PATTERN = /<ServiceException(?:\s[^>]*)?>([\s\S]*?)<\/ServiceException>/i;

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
  const code = CODE_PATTERN.exec(xmlText)?.[1]?.trim() || undefined;
  const rawMessage = MESSAGE_PATTERN.exec(xmlText)?.[1]?.trim() || undefined;
  return { code, message: rawMessage ? rawMessage.slice(0, 120) : undefined };
}
