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
