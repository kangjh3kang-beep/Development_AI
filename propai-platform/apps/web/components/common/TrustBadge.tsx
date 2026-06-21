"use client";

/**
 * TrustBadge — "위변조 방지·신뢰 검증" 신뢰 표식.
 *
 * 블록체인/STO 같은 전문용어 대신 사용자 언어로, 우리 분석원장(해시체인 append-only,
 * content_hash+prev_hash 무결성)을 근거로 한 "위변조 방지" 신뢰를 보고서·핵심 분석
 * 결과 상단에 가볍게 표출한다.
 *
 * 순수 표식(추가 네트워크 호출 없음). 실제 변조 탐지/계산검증은 VerificationBadge가 담당.
 */

export function TrustBadge({
  label = "분석 원장 봉인 · 위변조 방지",
  note = "분석 결과는 해시체인 원장에 봉인되어 위·변조 시 즉시 탐지됩니다.",
  className = "",
}: {
  label?: string;
  note?: string;
  className?: string;
}) {
  return (
    <div
      className={`inline-flex items-center gap-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-2 ${className}`}
      title={note}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 text-emerald-400"
        aria-hidden="true"
      >
        <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
      <span className="text-[11px] font-bold leading-tight text-emerald-300">{label}</span>
    </div>
  );
}
