"use client";

/**
 * 인스펙터/폼 그리드 공용 컴포넌트 — 화면(뷰포트) 크기가 아니라 "이 그리드가 놓인 칸의 실제 폭"에
 * 반응한다. 그래서 좁은 칸(예: 좌측 인스펙터 컬럼) 안에 들어가도 칸마다 최소폭(minItemRem)을
 * 지켜, 한글 라벨/입력칸이 글자 하나씩 세로로 무너지는 현상을 구조적으로 막는다(전역 표준).
 *
 * 동작 원리(쉬운 설명):
 *   - repeat(auto-fit, minmax(Xrem, 1fr)) = "한 칸을 최소 Xrem은 주되, 폭이 남으면 똑같이 나눠 채워라".
 *   - 폭이 넉넉하면 종전처럼 여러 열(3~4열)을 유지하고(넓은 화면 무회귀),
 *     폭이 모자라면 자동으로 열 수를 줄여(→ 결국 1열) 라벨이 절대 1글자로 안 무너진다.
 *
 * ★ Tailwind v4 동적 클래스 주의: `gap-${n}`이나 `grid-cols-[...]`를 문자열로 만들면
 *   빌드 시 사용처를 못 찾아 스타일이 통째로 사라질(purge) 수 있다. 그래서 열 정의와 간격을
 *   모두 인라인 style로 직접 준다(클래스 생성에 의존하지 않아 항상 안전).
 *
 * 사용:
 *   <InspectorGrid minItemRem={12}>…셀들…</InspectorGrid>   // 라벨+입력이 펴지게 넉넉히
 *   <InspectorGrid minItemRem={7}>…칩들…</InspectorGrid>     // 좁아도 되는 칩
 */

import React from "react";

export function InspectorGrid({
  minItemRem = 11,
  gap = 4,
  className = "",
  children,
}: {
  minItemRem?: number; // 한 칸의 최소 가로폭(rem). 라벨/입력이 펴질 만큼 크게.
  gap?: number;        // 칸 사이 간격. Tailwind 단위(4 = 1rem)와 동일하게 0.25rem 곱.
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`grid ${className}`}
      style={{
        // 화면이 아닌 '이 그리드가 놓인 칸'의 실제 폭에 반응하는 핵심 한 줄.
        gridTemplateColumns: `repeat(auto-fit, minmax(${minItemRem}rem, 1fr))`,
        gap: `${gap * 0.25}rem`,
      }}
    >
      {children}
    </div>
  );
}
