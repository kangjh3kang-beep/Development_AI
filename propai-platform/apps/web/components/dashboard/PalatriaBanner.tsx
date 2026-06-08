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
        {/* 배경 사진(스카이게러지 럭셔리 차고 거실) + 어둠 오버레이(글자 가독성).
            이미지는 Supabase Storage에 호스팅된 실사진 URL을 사용한다. 우측에 차량이 보이도록
            오른쪽 정렬, 좌측은 아래 veil로 어둡게 덮어 글자가 또렷하게 보이게 한다. */}
        <div
          className="palatria-banner__bg"
          aria-hidden="true"
          style={{
            backgroundImage:
              'url("https://ykmeconwqbathcdejalr.supabase.co/storage/v1/object/public/section-media/images/1778997596187_na152fkgwnp.png")',
            backgroundPosition: "right center",
          }}
        />
        <div className="palatria-banner__veil" aria-hidden="true" />

        {/* 좌측: 실제 골드 크라운 'P' 로고 + 브랜드명 */}
        <div className="palatria-banner__brand">
          {/* 팔라트리아 공식 로고(투명 webp) — 다크 배경에 그대로 얹힌다. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="https://www.skygarage.net/logo-palatria.webp"
            alt="팔라트리아 로고"
            className="palatria-banner__logo"
          />
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
