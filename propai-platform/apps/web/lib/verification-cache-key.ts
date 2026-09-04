/**
 * 검증 배지 캐시 키 — **정본 한 곳**.
 *
 * 왜 따로 빼는가: 계정 격리 와이프 목록(`lib/projectSync.ts`)이 이 접두를
 * `"propai_verification_"` 로 적어 두고 있었는데 **실제 키는 `propai_verify_`** 였다.
 * 그래서 그 접두 스윕은 **한 번도 매치된 적이 없고**, 계정을 바꿔도 이전 계정의
 * 검증 결과 캐시가 그대로 남았다(격리 구멍).
 *
 * 문자열을 두 곳에 손으로 적으면 또 갈린다 — 만드는 쪽과 지우는 쪽이 **같은 상수**를 본다.
 */
export const VERIFY_CACHE_PREFIX = "propai_verify_";

/** `propai_verify_<분석유형>_<컨텍스트해시>` */
export function verificationCacheKey(analysisType: string, contextHash: string): string {
  return `${VERIFY_CACHE_PREFIX}${analysisType}_${contextHash}`;
}
