import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// DESIGN.md B1 "공공데이터 고지" 계약: 모든 데이터 뷰 하단에 출처·갱신일·참고용 문구를
// 표시하는 공용 컴포넌트. 11px · --on-surface-muted · 상단 1px --border-muted.
// (화면 배선은 P2b 범위 — 이 컴포넌트는 정의만 제공한다.)

const DEFAULT_NOTE = "참고용 · 법적 효력 없음";

interface DataSourceNoticeProps extends HTMLAttributes<HTMLParagraphElement> {
  /** 데이터 출처(예: "국토교통부 실거래가"). */
  source: string;
  /** 갱신일(예: "2026-07-12"). 없으면 생략. */
  updatedAt?: string;
  /** 참고 문구. 기본값 "참고용 · 법적 효력 없음". */
  note?: string;
}

export function DataSourceNotice({
  source,
  updatedAt,
  note = DEFAULT_NOTE,
  className,
  ...props
}: DataSourceNoticeProps) {
  const parts = [
    `출처: ${source}`,
    updatedAt ? `갱신 ${updatedAt}` : null,
    note,
  ].filter(Boolean) as string[];

  return (
    <p
      className={cn("pt-2 leading-relaxed", className)}
      style={{
        fontSize: "11px",
        color: "var(--on-surface-muted)",
        borderTop: "1px solid var(--border-muted)",
      }}
      {...props}
    >
      {parts.join(" · ")}
    </p>
  );
}
