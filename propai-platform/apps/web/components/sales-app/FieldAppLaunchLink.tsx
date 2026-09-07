"use client";

import type { MouseEvent, ReactNode } from "react";

import { launchFieldApp, shouldInterceptFieldAppClick } from "@/lib/field-app-launch";

/**
 * 플랫폼 → 현장앱(분양앱) **진입 링크**. 눌러도 **지금 창을 잃지 않는다.**
 *
 * ## 왜 필요한가 (2026-09-08 사용자 신고)
 *
 * > *"메인플랫폼에서 분양앱을 누르면 새창이 아닌 같은 창에서 이동하면서
 * >   메인플랫폼 이용자는 다시 메인플랫폼으로 이동하지못하는 번거러움이 발생하고 있어"*
 *
 * 진입점이 평범한 `<Link>` 라 **같은 창에서 이동**했고, 현장앱 셸에는 복귀로가 없어서
 * (`(fieldapp)` 레이아웃이 `HomeLink` 를 상속하지 않는다) 사용자가 갇혔다.
 *
 * ★**근본은 「복귀로가 없다」가 아니라 「진입이 창을 빼앗는다」**이다. 창을 안 빼앗으면
 *   복귀로가 없어도 사용자는 원래 창으로 그냥 돌아간다 — 그래서 처방이 여기다.
 *
 * ## 왜 `<button>` 이 아니라 `<a href>` 인가
 *
 * `onClick` 만 있는 `<button>` 으로 만들면 **가운데클릭·⌘클릭·「새 탭에서 열기」·링크 복사**가
 * 전부 죽고, JS 가 실패하면 아무 데도 못 간다. `href` 를 그대로 두고 클릭만 가로채면
 * **모든 기존 경로가 살아 있고**, 창을 못 열었을 때 기본 이동이 그대로 일어난다
 * (= 오늘의 동작). ★즉 **최악의 경우가 회귀가 아니다.**
 *
 * ## 브라우저가 이미 새 컨텍스트를 여는 클릭은 건드리지 않는다
 *
 * ⌘/Ctrl/Shift 클릭이나 가운데 버튼은 사용자가 **명시적으로** 새 탭·새 창을 요구한 것이다.
 * 거기에 `preventDefault` 를 걸면 사용자의 의도를 가로채게 된다.
 */
export default function FieldAppLaunchLink({
  href,
  className,
  children,
  onLaunched,
}: {
  href: string;
  className?: string;
  children: ReactNode;
  /** 테스트·계측용 훅(선택). 실제로 무엇으로 열렸는지 알려 준다. */
  onLaunched?: (how: "window" | "tab" | "same") => void;
}) {
  function handleClick(e: MouseEvent<HTMLAnchorElement>) {
    // ★가로챌지 말지는 **공용 판정**을 쓴다(형제 렌더러와 두 벌이 되지 않게).
    if (!shouldInterceptFieldAppClick(e)) return;

    const how = launchFieldApp(href);
    onLaunched?.(how);

    // ★창(또는 탭)이 떴을 때만 기본 이동을 막는다. 막지 않으면 **원래 창까지 현장앱으로
    //   이동해** 사용자가 플랫폼을 잃는다 — 그것이 이 신고의 본체다.
    //   반대로 둘 다 막혔으면(`"same"`) **막으면 안 된다** — 막는 순간 버튼이 죽는다.
    if (how !== "same") e.preventDefault();
  }

  return (
    <a href={href} className={className} onClick={handleClick}>
      {children}
    </a>
  );
}
