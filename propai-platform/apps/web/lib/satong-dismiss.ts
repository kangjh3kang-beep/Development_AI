/**
 * ESC 해제 조정기 — **가장 위 표면 하나만** 닫는다.
 *
 * ★이 조정기는 **사통맵 전용이 아니다** — 앱 전역 모달이 함께 쓴다.
 *   (파일명이 `satong-` 으로 시작하는 것은 처음 만들어진 자리가 사통맵이었기 때문이고,
 *    내용은 처음부터 범용이다. 이름을 바꾸면 진행 중인 사통맵 작업과 충돌하므로 그대로 둔다.)
 *   소비처: `components/precheck/SatongMapShell.tsx` · `components/map/SatongMultiMap.tsx`
 *          · 앱 모달 13개 표면(`__tests__/modal-dismiss.contract.test.tsx` 가 전수 파생으로 감시).
 *
 * ## 왜 필요한가 (2026-08-17 라이브 실측)
 *
 * `/ko/precheck` 에서:
 *
 *     지도 클릭      → clickMenu(z470) 열림 · role=dialog 0
 *     레일 버튼 클릭 → clickMenu **여전히 열림** + role=dialog **1**   ← 동시 개방
 *     **ESC 1회**    → **둘 다 닫힘**
 *
 * `SatongMultiMap` 의 ESC 효과는 주석에 *"ESC 단계적 해제 — ①팝오버 → ②측정 종료 →
 * ③결과 지우기"* 라고 **선언**한다. 그 단계는 **그 컴포넌트 안에서만** 성립했다.
 * `SatongMapShell` 이 레일·베이스맵 팝오버용 ESC 핸들러를 `window` 에 따로 걸어,
 * 같은 keydown 에 **조율 없이 함께** 발화했다. 사용자는 한 번 눌렀는데 둘이 사라진다.
 *
 * ## 왜 `defaultPrevented` 만으로는 안 되나
 *
 * 서로 양보시키는 최소 처방(`if (ev.defaultPrevented) return`)은 **등록 순서가 승부를
 * 정한다.** 등록 순서는 마운트·이펙트 순서에 따라 바뀌므로, z 서열
 * (`clickMenu` 470 > `railPopover` 430)과 어긋날 수 있다.
 * → 그건 **"우연에 기댄 순서"** 이고, 이 저장소가 방금 `layerRail` rung 으로 없앤 바로 그 형태다.
 *   같은 실수를 ESC 에서 되풀이하지 않는다.
 *
 * ## 그래서 z 를 받는다
 *
 * 등록할 때 **표면의 z(SSOT rung)** 를 함께 준다. ESC 는 **열려 있는 것 중 z 최댓값** 하나만
 * 닫는다. 순서가 **값으로 선언**되고, 마운트 순서와 무관해진다.
 *
 * ★단계적 해제(측정 종료·결과 지우기)는 **표면이 아니다** — 아주 낮은 z 로 등록해
 *   "열린 표면이 없을 때만" 차례가 오게 한다. 종전 동작(①→②→③)이 그대로 보존된다.
 *
 * ## 경계 (정직)
 *
 * - 이 조정기는 **ESC 만** 다룬다. 외부 포인터다운 닫힘은 각 표면이 그대로 갖는다
 *   (그건 대상 판정이 표면마다 달라 일반화가 이득보다 위험하다).
 * - 입력 요소에 붙은 `onKeyDown` ESC(검색 콤보박스 등)는 **포커스가 있을 때만** 발화하므로
 *   여기 편입하지 않는다. 문서 전역 리스너끼리의 충돌만 조정 대상이다.
 */

import { useEffect, useRef } from "react";

import { SATONG_CONTENT_Z } from "./satong-map-z";

/**
 * **해제 순서** 층위(ESC 전용 SSOT).
 *
 * ★화면에 그려지는 z(페인트 층위)와 **같은 뜻이 아니다.** 저장소 전역 모달의 페인트 z 는
 *   40/50/800/1000 으로 흩어져 있고(실측), 그 값을 통일하는 것은 회귀 위험이 커서 이번 범위가
 *   아니다. 그래서 여기서는 "무엇이 먼저 닫혀야 하는가"만 **역할별로** 선언하고, 값은 화면
 *   층위 SSOT(`SATONG_CONTENT_Z`)에서 파생시켜 두 사다리가 갈라지지 않게 묶어 둔다.
 */
export const DISMISS_Z = {
  /**
   * 전체 화면을 덮는 앱 모달(`role="dialog" aria-modal="true"` 표면 기본값).
   * 화면 층위 계약의 모달 칸을 그대로 쓴다.
   */
  appModal: SATONG_CONTENT_Z.appModal,
  /**
   * **다른 표면 위에** 겹쳐 뜨는 표면. 아래 표면보다 **먼저** 닫혀야 한다.
   *
   * ★왜 별도 칸이 필요한가 — 같은 파일 안에서 두 표면이 겹치는 경우가 실재한다(실측):
   *   · 경매 상세 모달(`AuctionWorkspace`) 위에 사진 라이트박스가 열린다 — **페인트 z 가
   *     둘 다 `z-[800]` 로 같다.**
   *   · 조직도(`OrgTree`) 액션시트 위에 인원배정 시트가 **열릴 수 있었다** — 둘 다 `z-50` 이고
   *     JSX 순서상 배정 시트가 위에 그려진다. 시트가 화면을 덮어도 뒤쪽 '배정' 버튼에 Tab 으로
   *     도달할 수 있어서다(포커스 트랩 부재). 지금은 여는 쪽에서 상대를 닫아 **겹치지 않게**
   *     막아 뒀지만, 칸은 그대로 갈라 둔다 — 그 상호배타가 깨져도 순서가 우연에 기대지 않도록.
   *   같은 값으로 등록하면 조정기는 "먼저 등록된 쪽"을 닫는다 — 그건 이 조정기가 없애려던
   *   **등록 순서 의존** 그 자체다. 그래서 해제 순서에서만 한 칸 위로 선언한다.
   *
   * ★정정(2026-08-18 R2) — 초판 주석은 *"`DocumentViewerModal` 안에서 `ConfirmDeleteModal`
   *   이 열린다"* 고 단정했으나 **거짓이다.** `ConfirmDeleteModal` 의 소비처는
   *   `components/projects/ProjectsOverviewClient.tsx` **하나뿐**이고, 문서뷰어 쪽 삭제는
   *   `ProjectCollaborationDocumentExchange.tsx` 에서 확인창 **없이** 바로 지운다.
   *   두 모달이 같은 화면에 함께 존재한 적이 없다. 초판이 근거로 삼은 것은 실제 사용처가
   *   아니라 문서뷰어 안의 **주석 한 줄**(“층위·포털 관례는 ConfirmDeleteModal 을 따른다”)을
   *   역방향 grep 이 집은 것이었다 — **매치는 사용처가 아니다.**
   *   ★그래도 `ConfirmDeleteModal` 은 이 칸을 쓴다: 되돌릴 수 없는 삭제를 확인하는 창은
   *     무엇 위에 뜨든 가장 먼저 닫혀야 한다(단독으로 열려도 최댓값이라 동작은 같다).
   */
  nestedOverModal: SATONG_CONTENT_Z.appModal + 1,
  /**
   * 전역 내비게이션 표면(데스크톱 `WorkspaceNavBar` 플라이아웃 · 모바일 `FieldNav` 전체메뉴 시트).
   * 그 위에 모달이 열리면 모달이 먼저 닫힌다.
   * 화면 층위도 실제로 모달보다 아래다(플라이아웃 z-[700] · 시트 z-40 < 모달 z-50/800 — 실측).
   */
  navSheet: SATONG_CONTENT_Z.appNavFlyout,
  /**
   * 전체화면 오버레이 **해제**(CAD/BIM 전체화면 · 지도 CSS 폴백 전체화면).
   *
   * ★화면 층위는 가장 **위**(`appFullscreen` 9990)인데 해제 순서는 가장 **아래**다 — 모순이 아니라
   *   이 두 사다리가 다른 것을 뜻하기 때문이다. 전체화면은 **가장 바깥 그릇**이므로, 그 안에서
   *   열린 팝오버·모달을 먼저 닫고 **맨 마지막에** 벗는 것이 맞다. 페인트 값을 그대로 가져오면
   *   팝오버를 열어 둔 채 ESC 를 눌렀을 때 전체화면부터 벗겨진다(사용자 의도와 반대).
   * ★`SatongMultiMap` 의 측정 해제 센티널(-1)보다도 **뒤**에 온다 — 측정 중이면 측정을 먼저
   *   정리하고 전체화면을 벗는다. 그 상수는 해당 모듈 안의 지역 const 라 여기서 임포트하지
   *   않는다(값 -1 을 기준으로 한 칸 아래라는 사실만 여기 적어 둔다).
   * ★라이브 미검증 — jsdom 은 전체화면 API 를 흉내 내지 못한다. 순서는 값으로 잠갔지만
   *   실제 브라우저에서의 체감은 확인하지 못했다.
   */
  fullscreenExit: -2,
} as const;

type Entry = { z: number; close: () => void };

const entries = new Map<number, Entry>();
let seq = 0;
let bound = false;

function onKeyDown(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  // 한글 등 IME 로 글자를 **조합하는 중**의 ESC 는 통상 "조합 취소"다. 그때 모달을 통째로 닫으면
  // 사용자가 치던 입력이 함께 날아간다. 이 계약으로 새로 ESC 가 붙은 표면 중 텍스트 입력을
  // 가진 것이 여럿이다(현장 비밀번호·현장 진입·조직도 배정 이메일·삭제 확인 이름).
  // ★부분 검증(정직) — 테스트는 `isComposing: true` 인 이벤트를 **직접 만들어** 이 분기를 태운다.
  //   그러나 실제 한글 IME 가 조합 중 ESC 에 이 플래그를 세우는지는 **브라우저에서 확인하지
  //   못했다**(jsdom 은 IME 를 흉내 내지 못한다). 저비용 방어로 넣어 두되 단정하지 않는다.
  if (event.isComposing) return;
  if (entries.size === 0) return;

  let top: Entry | null = null;
  for (const entry of entries.values()) {
    if (!top || entry.z > top.z) top = entry;
  }
  if (!top) return;

  // ★하나만 닫는다. 나머지는 다음 ESC 를 기다린다.
  top.close();
  // ★정정(2026-08-18 R2) — 초판 주석은 이 호출을 *"조정기 밖 핸들러가 `defaultPrevented` 를
  //   보면 양보할 수 있게 하는 최소 협조"* 라고 설명했다. 그 협조의 **소비처는 전 저장소에
  //   0개였다**(`defaultPrevented` 를 읽는 ESC 핸들러가 없다). 게다가 실제로 충돌하던
  //   `WorkspaceNavBar` 는 `document` 에 걸려 있어 `window` 인 이 조정기보다 **먼저** 발화했다 —
  //   나중에 부르는 preventDefault 는 원리적으로 아무것도 막지 못한다(R2 실측: ESC 1회에
  //   모달과 플라이아웃이 함께 닫혔다).
  //   → 그래서 처방은 이 호출이 아니라 **조정기 밖 ESC 리스너를 0으로 만드는 것**이고,
  //     그 상태는 `__tests__/modal-dismiss.contract.test.tsx` 의 파생 락이 지킨다.
  //   이 호출은 브라우저 기본 동작에 대한 방어로만 남긴다(그 효과는 미검증).
  event.preventDefault();
}

function ensureBound(): void {
  if (bound || typeof window === "undefined") return;
  window.addEventListener("keydown", onKeyDown);
  bound = true;
}

function releaseIfEmpty(): void {
  if (entries.size > 0 || !bound || typeof window === "undefined") return;
  window.removeEventListener("keydown", onKeyDown);
  bound = false;
}

/**
 * 해제 가능한 표면을 등록한다. **열려 있는 동안만** 등록하고, 닫히면 해제한다.
 *
 * @param z 표면의 층위(SSOT rung). ESC 는 이 값이 **가장 큰** 것 하나만 닫는다.
 * @param close 그 표면을 닫는 함수.
 * @returns 등록 해제 함수(`useEffect` 의 cleanup 에 그대로 반환하면 된다).
 */
export function registerDismissible(z: number, close: () => void): () => void {
  const id = ++seq;
  entries.set(id, { z, close });
  ensureBound();
  return () => {
    entries.delete(id);
    releaseIfEmpty();
  };
}

/**
 * React 표면용 얇은 배선 — **열려 있는 동안만** 조정기에 등록한다.
 *
 * 표면마다 `useEffect` + 해제 반환을 손으로 쓰면 (ㄱ)해제를 빠뜨리거나 (ㄴ)닫기 함수가
 * 매 렌더 새로 만들어져 등록/해제가 계속 되풀이된다. 그 둘을 여기서 한 번만 막는다.
 *
 * @param z 해제 순서(`DISMISS_Z` 에서 고른다).
 * @param open 표면이 열려 있는가. `false` 면 등록하지 않는다(닫힌 표면이 ESC 를 먹지 않게).
 * @param close 닫기 함수. 매 렌더 새로 만들어져도 재등록하지 않는다(ref 로 최신값만 따라간다).
 */
export function useDismissible(z: number, open: boolean, close: () => void): void {
  const closeRef = useRef(close);
  useEffect(() => {
    closeRef.current = close;
  });
  useEffect(() => {
    if (!open) return;
    return registerDismissible(z, () => closeRef.current());
  }, [z, open]);
}

/**
 * "이 컴포넌트는 **열려 있을 때만 마운트된다**" 를 이름으로 선언하는 배선.
 *
 * ★왜 별도 함수인가 — `useDismissible(z, true, close)` 처럼 열림 자리에 리터럴 `true` 를 쓰면
 *   (ㄱ)"열림 검사를 빠뜨린 것"과 구분되지 않고 (ㄴ)그 자리를 `false` 로 바꾸는 변이가 어떤
 *   검사에도 걸리지 않는다(R2 실측: SURVIVED). 그래서 리터럴은 파생 락으로 **금지**하고,
 *   의도가 정말 "마운트 = 열림"이면 이 이름을 쓰게 한다.
 * ★한계(정직) — 부모가 이 컴포넌트를 **항상 마운트**하도록 바뀌면 닫힌 표면이 ESC 를 삼킨다.
 *   현재 소비처 4곳의 부모는 전부 조건부 렌더임을 확인했으나, 그 사실을 코드로 강제하지는
 *   못한다(부모 쪽 계약이라 여기서 닿지 않는다).
 */
export function useDismissibleWhileMounted(z: number, close: () => void): void {
  useDismissible(z, true, close);
}

/** 테스트 전용 — 등록 현황(개수와 z 목록). 공허한 초록을 막기 위한 관찰창이다. */
export function __dismissibleSnapshot(): { count: number; zs: number[] } {
  return { count: entries.size, zs: [...entries.values()].map((e) => e.z).sort((a, b) => a - b) };
}
