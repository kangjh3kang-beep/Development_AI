import React from "react";

/**
 * 스카이게러지 '팔라트리아' 프리미엄 배너.
 * - 차세대 모빌리티 특허 시스템(세대 직입·자율주행 발렛주차)을 알리는 브랜드 배너.
 * - 클릭하면 외부 사이트(skygarage.net)로 이동.
 * - 사진(첨부 이미지)은 배경 슬롯 `/images/palatria-hero.jpg`로 들어간다.
 *   파일이 아직 없으면 골드 그라데이션이 대신 보여(깨지지 않음), 파일만 올리면 사진 배경이 적용된다.
 * - 색은 이 브랜드 전용 골드(팔라트리아 아이덴티티)라 배너 안에서만 로컬로 정의한다(전역 토큰 오염 없음).
 */
export function PalatriaBanner() {
  return (
    <section className="relative z-10 w-full">
      <a
        href="http://www.skygarage.net"
        target="_blank"
        rel="noopener noreferrer"
        className="palatria-banner group"
        aria-label="스카이게러지 팔라트리아 — 차세대 모빌리티 특허 시스템 (새 창)"
      >
        {/* 배경 사진(있으면) + 어둠 오버레이(글자 가독성) */}
        <div className="palatria-banner__bg" aria-hidden="true" />
        <div className="palatria-banner__veil" aria-hidden="true" />

        {/* 좌측: 왕관 모티프 + 브랜드명 */}
        <div className="palatria-banner__brand">
          {/* 골드 왕관(브랜드 심볼) — 간결한 SVG */}
          <svg className="palatria-banner__crown" width="34" height="26" viewBox="0 0 34 26" fill="none" aria-hidden="true">
            <path d="M2 24h30M3 22 1 7l8 6 8-11 8 11 8-6-2 15H3Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
          </svg>
          <div className="palatria-banner__brandtext">
            <span className="palatria-banner__eyebrow">SKY GARAGE · 스카이게러지</span>
            <strong className="palatria-banner__name">팔라트리아</strong>
          </div>
        </div>

        {/* 중앙: 타이포그래피 카피 */}
        <div className="palatria-banner__copy">
          <h3 className="palatria-banner__headline">차세대 모빌리티 특허 시스템</h3>
          <p className="palatria-banner__sub">세대 직입 · 자율주행 발렛주차 시스템</p>
          <p className="palatria-banner__tagline">주거문화의 패러다임이 바뀐다</p>
        </div>

        {/* 우측: 바로가기 */}
        <div className="palatria-banner__cta">
          <span>자세히 보기</span>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
          </svg>
        </div>
      </a>
    </section>
  );
}
