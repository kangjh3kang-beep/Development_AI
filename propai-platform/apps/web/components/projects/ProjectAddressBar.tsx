"use client";

import { useProjectContextStore } from "@/store/useProjectContextStore";
import Link from "next/link";
import { useParams } from "next/navigation";

/**
 * 프로젝트 하위 페이지에 현재 분석 대상 주소를 상시 표시하는 바.
 * 부지분석에서 설정한 주소/용도지역/건폐율/용적률을 한눈에 보여줍니다.
 * 클릭하면 부지분석 페이지로 이동하여 주소를 변경할 수 있습니다.
 */
export function ProjectAddressBar() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const complianceData = useProjectContextStore((s) => s.complianceData);

  // 주소가 없으면 안내 메시지 표시
  if (!siteAnalysis?.address) {
    return (
      <Link
        href={`/${locale}/projects/${id}/site-analysis`}
        className="flex items-center gap-2 rounded-xl bg-[var(--surface-muted)] border border-[var(--line)] px-4 py-2.5 text-sm text-[var(--text-hint)] hover:bg-[var(--surface-soft)] transition-colors"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="shrink-0"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <span>분석할 부지의 주소를 입력하세요 &rarr; 부지분석으로 이동</span>
      </Link>
    );
  }

  return (
    <Link
      href={`/${locale}/projects/${id}/site-analysis`}
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-[var(--surface-muted)] border border-[var(--line)] px-4 py-2.5 text-sm hover:bg-[var(--surface-soft)] transition-colors group"
    >
      {/* 핀 아이콘 */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 text-[var(--accent-strong)]"
      >
        <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
        <circle cx="12" cy="10" r="3" />
      </svg>

      {/* 주소 */}
      <span className="font-bold text-[var(--text-primary)]">
        {siteAnalysis.address}
      </span>

      {/* 구분선 */}
      <span className="text-[var(--line-strong)]">|</span>

      {/* 용도지역 (있을 경우) */}
      {siteAnalysis.zoneCode && (
        <>
          <span className="text-[var(--text-secondary)]">
            {siteAnalysis.zoneCode}
          </span>
          <span className="text-[var(--line-strong)]">|</span>
        </>
      )}

      {/* 건폐율/용적률 적합 여부 (있을 경우) */}
      {complianceData && (
        <span className="text-[var(--text-hint)]">
          건폐율{" "}
          {complianceData.bcrCompliant ? "적합" : "초과"} · 용적률{" "}
          {complianceData.farCompliant ? "적합" : "초과"}
        </span>
      )}

      {/* 변경 힌트 */}
      <span className="text-[10px] text-[var(--text-hint)] opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
        변경하기 &rarr;
      </span>
    </Link>
  );
}
