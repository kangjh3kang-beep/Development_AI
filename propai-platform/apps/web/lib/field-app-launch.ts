"use client";

import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * 현장앱(분양앱)을 **독자 창으로 여는 단일 통로**.
 *
 * ## 왜 함수로 빼는가 (2026-09-08)
 *
 * 종전에는 `FieldAppAffordance.tsx` 안에 팝업 features 문자열과 차단 폴백이 **인라인**으로
 * 있었다. 그런데 사용자 신고로 **두 번째 소비처**(플랫폼 → 현장앱 진입)가 필요해졌고,
 * 그것을 각자 구현하면 이 저장소가 반복해서 데인 형태가 그대로 재현된다 —
 * ★*"고친 자리의 형제·미러를 놓친다"*. 한쪽만 폴백을 고치면 다른 쪽은 조용히 옛 동작을 유지한다.
 *
 * 그래서 **창을 여는 판정은 여기 하나뿐**이고, `field-app-launch.wiring.test.ts` 가
 * 「`window.open` 을 담은 파일」을 **파생형**으로 세어 새 소비처가 자동으로 감시망에 들어오게 한다.
 *
 * ## 반환값이 3분기인 이유
 *
 * 호출부는 **기본 이동을 막을지**를 알아야 한다. 창이 떴으면 막아야 하고(안 막으면 원래 창까지
 * 현장앱으로 이동해 **사용자가 플랫폼을 잃는다** — 이 신고의 본체다), 못 떴으면 막으면 안 된다
 * (막으면 아무 데도 못 간다). 불리언으로 뭉개면 그 구별이 사라진다.
 *
 * ★`location=no` 를 넣지 않는다 — 현대 브라우저가 무시하므로 **지키지 못할 약속**이다
 *   (2026-09-07 라이브 실측: 팝업에 주소창이 남았다. 종전 주석이 거짓이었다).
 */

/** 창 열기 결과 — 호출부가 `preventDefault` 여부를 이것으로 정한다. */
export type FieldAppLaunchResult =
  /** 이름 있는 전용 창이 떴다. 호출부는 기본 이동을 **막아야 한다**. */
  | "window"
  /** 팝업이 막혀 새 탭으로 떴다. 원래 창은 보존됐으므로 역시 **막아야 한다**. */
  | "tab"
  /** 둘 다 막혔다. 호출부는 기본 이동을 **막으면 안 된다**(같은 창 이동 = 오늘의 동작). */
  | "same";

/**
 * 팝업 크기 — ★**화면보다 크게 요청하지 않는다.** 일부 브라우저는 화면을 넘는 요청을
 * 통째로 무시해 크기 지정이 전부 날아간다.
 *
 * ★2026-09-08 적대 리뷰 M-4 정정: 종전 판(`Math.max(360, …)`)은 **이 주석을 스스로 깼다** —
 *   `availWidth=320`(초소형 단말)에서 `w=360 > 320` 이 된다. 하한을 바깥에 두면 상한이 무의미하다.
 *   **화면 크기로 한 번 더 clamp** 해서 주석이 참이 되게 한다(경계는 양방향으로 건다).
 *
 * ★그리고 **치수가 바뀐 것을 선언한다**(종전 인라인은 1440×960, 지금은 1180×900).
 *   리팩토링 커밋이 *"동작은 동일"* 이라 적었는데 **거짓이었다** — 값이 달랐다.
 *   현장앱은 모바일 우선 레이아웃이라 1180 이면 충분하고, 넓은 창은 사용자가 늘릴 수 있다.
 */
const POPUP_MAX_W = 1180;
const POPUP_MAX_H = 900;

function popupFeatures(): string {
  const availW = window.screen?.availWidth ?? POPUP_MAX_W;
  const availH = window.screen?.availHeight ?? POPUP_MAX_H;
  // ★상한 하나만 건다 — **화면을 넘지 않는다**가 이 함수의 유일한 불변식이다.
  //   ★2026-09-08 적대 리뷰: 종전 판은 `Math.min(availW, Math.max(MIN, Math.min(MAX, availW)))`
  //     였는데 이것은 **대수적으로** `Math.min(MAX, availW)` 와 항상 같다(모든 availW 에서 실측 확인).
  //     즉 `POPUP_MIN_W`/`POPUP_MIN_H` 는 **결과에 영향을 주지 않는 죽은 상수**였다.
  //     「하한을 건다」는 의도였다면 그 코드는 그것을 **하지 않고 있었다** — 지워서 정직하게 만든다.
  //     (하한이 정말 필요해지면 그때 «화면보다 크게 요청하지 않는다» 와 충돌하지 않는 형태로 넣어라.)
  const w = Math.min(POPUP_MAX_W, availW);
  const h = Math.min(POPUP_MAX_H, availH);
  const left = Math.max(0, Math.round((availW - w) / 2));
  const top = Math.max(0, Math.round((availH - h) / 2));
  return `popup=yes,width=${w},height=${h},left=${left},top=${top},menubar=no,toolbar=no,status=no,resizable=yes,scrollbars=yes`;
}

/**
 * ★**클릭을 가로챌 것인가** — 이 판정도 공용이다(2026-09-08 적대 리뷰 M-3).
 *
 * 종전엔 `FieldAppLaunchLink` 와 `SidebarNav` 가 **각자** 판정했고 실제로 갈려 있었다:
 * 한쪽은 `defaultPrevented`·`button` 을 보고 다른 쪽은 안 봤다. 공용화가 «창을 여는 함수»
 * 까지만 가고 **«무엇을 가로챌지»는 두 벌로 남은** 것이다 — 이 PR 이 막겠다고 선언한 그 형태다.
 *
 * ★`button !== 0` 과 `defaultPrevented` 는 **도달 불가일 수 있다**(정직하게 적는다):
 *   현대 브라우저에서 가운데클릭은 `auxclick`, 우클릭은 `contextmenu` 를 내므로 `click` 의
 *   `button` 은 사실상 항상 0 이고, 이 앵커에 `preventDefault` 를 부르는 다른 핸들러도 없다.
 *   **jsdom 으로는 원리적으로 못 재므로 미측정**이다. 방어로 남기되 «실동작한다»고 말하지 않는다.
 */
export function shouldInterceptFieldAppClick(e: {
  button: number;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  defaultPrevented: boolean;
}): boolean {
  if (e.defaultPrevented) return false;
  if (e.button !== 0) return false;
  // 수식키 클릭은 사용자가 **명시적으로** 새 탭·새 창을 요구한 것이다 — 브라우저에 맡긴다.
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
  return true;
}

/**
 * 대상이 **우리 오리진**인가 — `noopener` 를 뺄 수 있는지의 유일한 판정자.
 *
 * ★동일 오리진에서는 `noopener` 가 **얻는 것이 없다**(SOP 상 이미 접근 가능하다). 반면
 *   잃는 것은 크다 — sessionStorage 상속이 끊겨 **현장 비밀번호를 다시 묻게 된다**(실측).
 *   교차 오리진에서는 반대로 `noopener` 가 실재하는 방어이므로 **유지한다.**
 *   상대 URL 은 현재 주소를 기준으로 해석된다(오늘의 모든 호출부가 상대 경로다).
 */
function sameOrigin(target: string): boolean {
  try {
    return new URL(target, window.location.href).origin === window.location.origin;
  } catch {
    return false; // 파싱 불가는 «모른다» 이고, 모르면 안전한 쪽(noopener)으로 간다.
  }
}

export function launchFieldApp(url?: string): FieldAppLaunchResult {
  if (typeof window === "undefined") return "same";
  const target = url ?? window.location.href;

  // ★★**오리진 판정이 맨 앞이다**(2026-09-08 적대 리뷰 후속 — 내 테스트가 잡았다).
  //   종전엔 `sameOrigin` 을 **폴백에만** 걸어서, 주 경로가 교차 오리진 대상에게
  //   **현장앱 이름을 주고 `noopener` 없이** 열었다 — F1 가드가 지키려던 **바로 그 노출**이다.
  //   가드를 한 갈래에만 걸면 나머지 갈래가 그대로 뚫린다(§처방 범위 = 결함 범위).
  if (!sameOrigin(target)) {
    // 교차 오리진 — 이름을 주지 않고 `noopener` 를 유지한다.
    //   ★`noopener` 가 설정되면 `window.open` 은 **명세상 `null` 을 반환한다.**
    //     반환값으로 성공을 판정하면 **정상으로 열린 탭을 실패로 읽는다** ⇒ 반환값을 보지 않는다.
    //   ★★**반대 방향 비용도 적는다**(적대 리뷰 MINOR-3): `noopener` 라 성공/차단을 **구별할 수 없으므로**,
    //     **차단된 경우에도 `"tab"` 을 낸다** → 호출부가 기본 이동을 막아 **아무 일도 안 일어난다**
    //     (갈래 ③이 피하겠다고 쓴 그 실패다). 성공을 실패로 읽는 쪽보다 낫다고 판단했지만
    //     **한쪽만 참인 계약이 아니라 양쪽을 다 적어 둔다** — 조건 없는 단정은 참일 때도 검증 불가다.
    //   ★오늘 이 갈래는 **도달 불가**다(호출부 5곳이 전부 상대경로 또는 현재 주소).
    //     그래도 두는 이유: `launchFieldApp` 은 `url` 을 받는 공개 함수라 다음 호출부가
    //     외부 주소를 넘길 수 있고, 그때 조용히 틀리는 것보다 계약이 있는 편이 낫다.
    window.open(target, "_blank", "noopener,noreferrer");
    return "tab";
  }

  // ①이름 있는 전용 창 — 같은 이름으로 다시 열면 **그 창이 재사용**된다(창이 늘어나지 않는다).
  //   그 이름이 곧 현장앱 정체성 판별자다(`useFieldAppShell` 의 `inSeparateWindow`).
  //
  //   ★★**비용**(2026-09-08 적대 리뷰 MINOR-2 — 종전 주석은 이득만 적었다):
  //     이미 그 이름의 창이 있으면 **사용자가 보던 화면을 덮어쓴다.** 구체적으로,
  //     탭 B 에서 현장 X 를 입력 중인데 탭 A 에서 현장 Y 로 진입하면 **탭 B 가 Y 로 이동한다**
  //     (구판 `_blank` 폴백은 매번 새 탭이라 B 가 보존됐다).
  //     그래도 이쪽을 고른 이유는 구판이 sessionStorage 를 잃어 **2차 비밀번호를 다시 묻기**
  //     때문이다 — 화면 전환보다 그쪽이 손실에 가깝다. **맞바꾼 것이지 공짜가 아니다.**
  const win = window.open(target, FIELD_APP_WINDOW_NAME, popupFeatures());
  if (win) {
    try {
      win.focus();
    } catch {
      /* 포커스는 부가 기능이다 — 실패해도 창은 떴다. */
    }
    return "window";
  }

  // ②팝업 차단 → **같은 이름의 탭**(features 없이). 세부 근거는 위 주석 블록에 있다.
  const tab = window.open(target, FIELD_APP_WINDOW_NAME);
  if (tab) {
    try {
      tab.focus();
    } catch {
      /* 포커스는 부가 기능이다. */
    }
    return "tab";
  }

  // ③둘 다 막혔다. 여기서 조용히 실패하면 **버튼이 죽은 것처럼 보인다** —
  //   호출부가 기본 이동을 그대로 두게 해서 최소한 오늘의 동작은 보장한다.
  return "same";
}
