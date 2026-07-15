"use client";

/**
 * MarkdownLite — 경량·안전 마크다운 렌더러(공용).
 *
 * 왜 필요한가(쉬운 설명):
 *   AI(LLM) 응답은 보통 마크다운 서식(## 제목, **굵게**, - 목록, --- 구분선)으로 온다.
 *   이걸 `whitespace-pre-wrap` 일반 문단으로 그대로 뿌리면 사용자 화면에 `##`·`**`·`---`
 *   같은 기호가 날것으로 노출돼 읽기 어렵다. 이 컴포넌트는 그 서식을 사람이 읽기 좋은
 *   제목·굵은 글씨·목록·구분선으로 바꿔 준다.
 *
 * 보안(XSS 안전):
 *   innerHTML / dangerouslySetInnerHTML을 절대 쓰지 않는다. 텍스트를 파싱해 React 요소로만
 *   조립하므로 응답에 섞인 <script> 등은 실행되지 않고 그냥 문자로 표시된다.
 *
 * 지원 문법(핵심만 — '경량'):
 *   - 제목: #, ##, ###…(최대 6단계)
 *   - 굵게: **텍스트**   · 기울임: *텍스트* 또는 _텍스트_
 *   - 인라인 코드: `코드`
 *   - 링크: [보이는글자](https://url)  (http/https/mailto/상대경로만 허용 — 그 외는 링크 안 함)
 *   - 불릿 목록: -, *, +  · 번호 목록: 1. 2. 3.
 *   - 인용: > 인용문
 *   - 구분선: ---, ***, ___
 *   - 문단: 빈 줄로 구분. 문단 안 줄바꿈은 <br/>로 보존(정보 손실 0).
 *
 * 디자인:
 *   래퍼(className)에서 글자 크기·색을 상속받는다 — 호출부가 기존 `<p>`에 쓰던 크기/색 클래스를
 *   그대로 넘기면 톤이 유지된다. 제목만 --text-primary + 굵게로 계층을 준다. 한국어 줄바꿈은
 *   break-keep(단어 중간 안 끊김). 디자인 토큰(CSS 변수)만 사용.
 */

import React from "react";

/** 링크 URL 안전성 검사 — 허용 스킴만 통과(javascript: 등 위험 스킴 차단). 통과 못하면 null. */
function safeHref(url: string): string | null {
  const u = url.trim();
  if (/^(https?:\/\/|mailto:)/i.test(u)) return u;
  if (u.startsWith("/") || u.startsWith("#")) return u; // 앱 내부 상대경로·앵커
  return null;
}

// 인라인 토큰(굵게/기울임/코드/링크)을 한 번에 잡는 정규식. 순서대로 우선순위를 갖는다.
//   1: **굵게**  2: `코드`  3: [글자](url)  4: *기울임*  5: _기울임_
const INLINE_RE =
  /(\*\*(?!\s)([^*]+?)\*\*)|(`([^`]+?)`)|(\[([^\]]+?)\]\(([^)\s]+?)\))|(\*(?!\s)([^*]+?)\*)|(_(?!\s)([^_]+?)_)/g;

/** 한 줄(또는 <br/>로 이어붙일 단위) 안의 인라인 마크다운을 React 노드 배열로 변환. */
function parseInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let idx = 0;
  INLINE_RE.lastIndex = 0;
  while ((match = INLINE_RE.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const key = `${keyBase}-i${idx++}`;
    if (match[1]) {
      nodes.push(
        <strong key={key} className="font-bold text-[var(--text-primary)]">
          {match[2]}
        </strong>,
      );
    } else if (match[3]) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-[var(--surface-strong)] px-1 py-0.5 font-mono text-[0.85em] text-[var(--text-primary)]"
        >
          {match[4]}
        </code>,
      );
    } else if (match[5]) {
      const href = safeHref(match[7]);
      nodes.push(
        href ? (
          <a
            key={key}
            href={href}
            target={href.startsWith("http") ? "_blank" : undefined}
            rel={href.startsWith("http") ? "noopener noreferrer" : undefined}
            className="font-semibold text-[var(--accent-strong)] underline underline-offset-2"
          >
            {match[6]}
          </a>
        ) : (
          // 위험/미상 스킴 링크는 보이는 글자만 텍스트로(링크 미부여 — 무XSS).
          <span key={key}>{match[6]}</span>
        ),
      );
    } else if (match[8]) {
      nodes.push(<em key={key}>{match[9]}</em>);
    } else if (match[10]) {
      nodes.push(<em key={key}>{match[11]}</em>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length > 0 ? nodes : [text];
}

/** 문단 안 여러 줄을 <br/>로 이어붙여(정보 손실 0) 인라인 파싱 결과를 반환. */
function renderParagraphLines(lines: string[], keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  lines.forEach((ln, i) => {
    if (i > 0) out.push(<br key={`${keyBase}-br${i}`} />);
    out.push(...parseInline(ln, `${keyBase}-l${i}`));
  });
  return out;
}

const HEADING_CLASS: Record<number, string> = {
  1: "text-[1.1em] font-black text-[var(--text-primary)]",
  2: "text-[1.05em] font-black text-[var(--text-primary)]",
  3: "text-[1em] font-bold text-[var(--text-primary)]",
  4: "text-[0.95em] font-bold text-[var(--text-primary)]",
  5: "text-[0.9em] font-bold text-[var(--text-secondary)]",
  6: "text-[0.9em] font-bold text-[var(--text-secondary)]",
};

/**
 * 마크다운 텍스트를 블록(제목·목록·인용·구분선·문단) React 요소로 조립.
 * 순수 함수(부작용 없음) — 렌더 시 1회 호출.
 */
function renderBlocks(src: string): React.ReactNode[] {
  const lines = src.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const raw = lines[i];
    const line = raw.trim();

    // 빈 줄 — 블록 구분(스킵).
    if (line === "") {
      i++;
      continue;
    }

    // 구분선(--- / *** / ___)
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
      blocks.push(<hr key={`b${key++}`} className="my-3 border-[var(--line)]" />);
      i++;
      continue;
    }

    // 제목(#…######)
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      blocks.push(
        <p key={`b${key++}`} className={`break-keep ${HEADING_CLASS[level]}`}>
          {parseInline(h[2], `h${key}`)}
        </p>,
      );
      i++;
      continue;
    }

    // 인용(> …) — 연속 인용 줄 묶기
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
        quote.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      blocks.push(
        <blockquote
          key={`b${key++}`}
          className="break-keep border-l-2 border-[var(--accent-strong)]/40 pl-3 text-[var(--text-secondary)]"
        >
          {renderParagraphLines(quote, `q${key}`)}
        </blockquote>,
      );
      continue;
    }

    // 불릿 목록(-, *, +) — 연속 항목 묶기
    if (/^[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*+]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={`b${key++}`} className="list-disc space-y-1 break-keep pl-5">
          {items.map((it, j) => (
            <li key={j}>{parseInline(it, `ul${key}-${j}`)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    // 번호 목록(1. 2. …) — 연속 항목 묶기
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={`b${key++}`} className="list-decimal space-y-1 break-keep pl-5">
          {items.map((it, j) => (
            <li key={j}>{parseInline(it, `ol${key}-${j}`)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // 문단 — 다음 빈 줄/특수 블록 시작 전까지 묶기(문단 안 줄바꿈은 <br/> 보존)
    const para: string[] = [];
    while (i < lines.length) {
      const cur = lines[i].trim();
      if (
        cur === "" ||
        /^(-{3,}|\*{3,}|_{3,})$/.test(cur) ||
        /^#{1,6}\s+/.test(cur) ||
        /^>\s?/.test(cur) ||
        /^[-*+]\s+/.test(cur) ||
        /^\d+\.\s+/.test(cur)
      ) {
        break;
      }
      para.push(cur);
      i++;
    }
    blocks.push(
      <p key={`b${key++}`} className="break-keep leading-relaxed">
        {renderParagraphLines(para, `p${key}`)}
      </p>,
    );
  }

  return blocks;
}

/**
 * MarkdownLite — text(마크다운)를 안전하게 렌더. 값이 비면 아무것도 그리지 않는다(무목업).
 *
 * @param text     렌더할 마크다운/일반 텍스트(LLM 응답 등).
 * @param className 래퍼 div 클래스 — 호출부가 기존 <p>에 쓰던 글자 크기·색을 그대로 넘긴다.
 */
export function MarkdownLite({
  text,
  className = "",
}: {
  text: string | null | undefined;
  className?: string;
}) {
  if (typeof text !== "string" || !text.trim()) return null;
  return <div className={`space-y-2 ${className}`}>{renderBlocks(text)}</div>;
}
