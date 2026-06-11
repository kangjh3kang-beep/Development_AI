"use client";

/**
 * LegalRefChip — 법령 원문(law.go.kr) 딥링크 칩 (공용).
 *
 * 근거 수치 옆에 "법령명 조문" 라벨을 작은 칩으로 달아, 클릭 1회로 국가법령정보센터
 * 현행본 원문을 새 탭에서 확인하게 한다(예: [건축법 제61조 원문]).
 *
 * 정직성 가드(할루시네이션 링크 금지):
 *  - `url`이 없거나 http/https 스킴이 아니면 **링크 없이 텍스트만** 렌더한다.
 *    (레지스트리 미검증 근거는 url을 비워 보내므로 자연히 텍스트로 폴백)
 *  - 링크일 때만 target="_blank" rel="noopener noreferrer"로 안전하게 새 탭 오픈.
 *
 * URL 형식은 백엔드(legal_reference_registry)가 보장하는 law.go.kr 한글주소
 * (/법령/{명}/제{N}조, /자치법규/{조례명})만 들어온다고 가정한다. 이 컴포넌트는
 * 스킴만 한 번 더 방어한다(잘못된 링크보다 무링크가 안전).
 *
 * 순수 presentational — 네트워크 호출·store 접근 없음. 디자인 토큰(CSS 변수)만 사용.
 */

/** http/https 스킴만 통과(javascript:·data: 등 차단). 실패 시 null → 무링크 폴백. */
function safeHref(url?: string | null): string | null {
  if (!url || typeof url !== "string") return null;
  const trimmed = url.trim();
  if (!trimmed) return null;
  try {
    const u = new URL(trimmed);
    if (u.protocol === "http:" || u.protocol === "https:") return trimmed;
  } catch {
    /* 상대경로·비정상 URL은 링크로 쓰지 않는다(정직성) */
  }
  return null;
}

/** lawName + article → 칩 라벨. 빈 article은 생략(공백 군더더기 방지). */
function refLabel(lawName: string, article?: string | null): string {
  const a = article?.trim();
  return a ? `${lawName} ${a}` : lawName;
}

export function LegalRefChip({
  lawName,
  article,
  title,
  url,
  className = "",
}: {
  /** 공식 법령명 (예: "건축법", "국토의 계획 및 이용에 관한 법률 시행령"). */
  lawName: string;
  /** 조문 (예: "제61조"). 없으면 법령명만 표기. */
  article?: string | null;
  /** 조문 제목 (예: "일조 등의 확보를 위한 높이제한") — title 안내문에 부연. */
  title?: string | null;
  /** law.go.kr 한글주소 딥링크. 없거나 http(s)가 아니면 링크 없이 텍스트만 렌더. */
  url?: string | null;
  className?: string;
}) {
  // 법령명조차 없으면 단정하지 않고 미표시(빈 칩 방지·정직성).
  if (!lawName || !lawName.trim()) return null;

  const href = safeHref(url);
  const label = refLabel(lawName, article);
  const hint = title?.trim() ? `${label} — ${title.trim()}` : label;

  // 법전(book) 아이콘 — 법령 원문임을 시각적으로 알린다.
  const icon = (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
      aria-hidden="true"
    >
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );

  const baseCls =
    "inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold leading-none";

  // 링크 가능: 클릭 시 새 탭(law.go.kr 현행본). accent 색으로 클릭 가능함을 표시.
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title={`${hint} (원문 보기)`}
        aria-label={`${hint} 법령 원문 새 탭에서 열기`}
        className={`${baseCls} border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-strong)]/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)]/40 ${className}`}
      >
        {icon}
        <span>{label}</span>
        {/* 새 탭 열림을 알리는 외부링크 아이콘 */}
        <svg
          width="9"
          height="9"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="shrink-0 opacity-70"
          aria-hidden="true"
        >
          <path d="M15 3h6v6" />
          <path d="M10 14 21 3" />
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
        </svg>
      </a>
    );
  }

  // 무링크 폴백: url 미검증/부재 → 텍스트 칩만(절대 가짜 링크를 만들지 않는다).
  return (
    <span
      title={hint}
      aria-label={`법령 근거: ${hint}`}
      className={`${baseCls} border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-tertiary)] ${className}`}
    >
      {icon}
      <span>{label}</span>
    </span>
  );
}
