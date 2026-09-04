/**
 * 모달 **포커스 생명주기** — 초기 포커스 · 트랩 · 복귀.
 *
 * ## 왜 생겼나 (2026-08-22)
 *
 * `#697` 이 모달 **ESC 계약**을 전역 봉합했지만, 범위를 정직하게 적어 두었다:
 * *"이번 계약은 ESC 만 다룬다. 포커스 트랩·초기 포커스·포커스 복귀는 폼 표면에서 회귀
 * 위험이 커서 다음 단계로 미뤘다."* — 착수 시점 실측 **13개 표면 전부 0/13**.
 *
 * ★그리고 `trapFocus`(`hooks/useAccessibility.ts`)는 **이미 있었는데 소비처가 0** 이었다.
 *   빠진 것은 트랩 알고리즘이 아니라 **생명주기**(언제 잡고 언제 돌려주나)다.
 *   그래서 알고리즘을 다시 만들지 않고 그 함수를 **감싼다**(구현 두 벌 금지).
 *
 * ## 계약
 *
 * · 열리면 컨테이너 안 **첫 포커스 가능 요소**로 옮긴다(없으면 컨테이너 자신).
 * · 열려 있는 동안 `Tab`/`Shift+Tab` 을 컨테이너 안에 **가둔다**.
 * · 닫히면 **열기 전에 포커스를 갖고 있던 요소**로 되돌린다.
 *
 * ★ESC 는 여기서 다루지 않는다 — `registerDismissible`(lib/satong-dismiss)이 z 순서로
 *   조정하는 별개 계약이다. 두 곳에서 ESC 를 처리하면 한 번 눌러 둘이 닫힌다(#697 이 겪은 결함).
 */
import { useEffect, useRef, type RefObject } from "react";

import { trapFocus } from "@/hooks/useAccessibility";

function firstFocusable(container: HTMLElement): HTMLElement | null {
  const nodes = container.querySelectorAll<HTMLElement>(
    'a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])',
  );
  for (const el of Array.from(nodes)) {
    if (!el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true") return el;
  }
  return null;
}

/**
 * @param ref  모달 컨테이너(백드롭이 아니라 **대화상자 본체**)
 * @param open 열림 여부 — `false` 면 아무것도 하지 않고, `true`→`false` 전이에 포커스를 되돌린다.
 */
export function useModalFocus(ref: RefObject<HTMLElement | null>, open: boolean): void {
  // ★복귀 대상은 **렌더 단계**에서 잡는다 — 이펙트에서 읽으면 이미 늦다.
  //   React 의 `autoFocus` 는 커밋 때 발화하므로, 이펙트 시점의 `activeElement` 는 **모달
  //   안**이다. 그걸 복귀 대상으로 삼으면 닫을 때 자기 자신으로 돌아가는 무동작이 된다
  //   (실측: ConfirmDeleteModal 의 입력창이 autoFocus 다).
  const restoreRef = useRef<HTMLElement | null>(null);
  if (open && restoreRef.current === null && typeof document !== "undefined") {
    restoreRef.current = document.activeElement as HTMLElement | null;
  }
  if (!open && restoreRef.current !== null) restoreRef.current = null;

  useEffect(() => {
    if (!open) return;
    const container = ref.current;
    if (!container) return;
    const restoreTo = restoreRef.current;

    // ★**이미 모달 안에 포커스가 있으면 빼앗지 않는다.**
    //   저자가 `autoFocus` 로 지정한 대상(예: 확인 입력창)을 첫 포커스 요소(예: "복사" 버튼)로
    //   옮기면 그건 개선이 아니라 **회귀**다. 초기 포커스는 "밖에 있을 때만" 넣는다.
    if (!container.contains(document.activeElement)) {
      (firstFocusable(container) ?? container).focus?.();
    }

    // ★훅이 **실제로 어느 요소를 가뒀는지** 표시한다(2026-08-22 추가).
    //
    //   이게 없으면 잠금이 성립하지 않는다. `#750` 은 *"ref 를 백드롭에 달아도 통과하는 것을
    //   막는다"* 고 선언했지만 **막지 못했다**(실측: ref 를 백드롭으로 옮겨도 76건 전부 초록).
    //   이유는 우리 모달이 전부 `백드롭 > 본체` 구조이고 백드롭의 유일한 요소 자식이 본체라,
    //   `focusables(백드롭) === focusables(본체)` 여서 **결과로는 구분이 안 되기 때문**이다.
    //   → 결과가 같으면 **대상 자체를 관측 가능**하게 만들어야 한다.
    container.setAttribute("data-modal-focus", "1");

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const el = ref.current;
      if (!el) return;
      // ★**중첩 트랩에는 양보한다**(2026-08-23 추가 — `AuctionWorkspace` 라이트박스에서 드러났다).
      //
      //   모달 안에서 또 하나가 열리는 표면이 있다(상세 모달 > 사진 확대 라이트박스).
      //   안쪽이 **내 DOM 안에** 렌더되면 내 `focusables` 는 안쪽 것까지 포함하므로,
      //   안쪽의 마지막 요소가 우연히 내 마지막이 아닐 때만 우연히 동작한다 —
      //   즉 **레이아웃에 따라 뚫린다**. 우연에 기대지 않고 소유권을 명시한다.
      //
      //   ESC 계약은 이미 z 사다리(`DISMISS_Z.nestedOverModal`)로 같은 문제를 풀었다.
      //   포커스 계약에는 그 개념이 없어 **비대칭**이었다 — 여기서 맞춘다.
      const inner = el.querySelector<HTMLElement>("[data-modal-focus]");
      if (inner && inner !== el && inner.contains(document.activeElement)) return;
      trapFocus(el, e);
    };
    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      container.removeAttribute("data-modal-focus");
      // ★사라진 요소로 돌려보내지 않는다(언마운트된 버튼 등) — 그러면 포커스가 body 로 튄다.
      if (restoreTo && document.contains(restoreTo)) restoreTo.focus?.();
    };
  }, [ref, open]);
}

/**
 * **마운트 자체가 열림**인 표면용 — `useModalFocus(ref, true)` 의 대칭 래퍼.
 *
 * ## 왜 필요한가
 *
 * 이 저장소의 모달은 두 가지 방식으로 열린다:
 *
 *     open prop 방식   : 부모가 항상 렌더하고 `open` 으로 켠다  → `useModalFocus(ref, open)`
 *     마운트=열림 방식 : 부모가 열 때만 렌더한다               → **넣을 `open` 인자가 없다**
 *
 * ESC 계약은 이 둘을 **이미 갈라 놓았다**(`useDismissible` 11곳 / `useDismissibleWhileMounted`
 * 5곳). 그런데 포커스 계약에는 앞의 것만 있었다 — 그 **비대칭**이 5표면이 미배선으로 남은
 * 진짜 이유였다(*"드로어라 규약이 다르다"* 같은 표면별 사유가 아니라).
 *
 * ★`useModalFocus(ref, true)` 를 호출부마다 손으로 쓰지 않는 이유: 계약 테스트가
 *   *"열림 인자에 상수 리터럴을 쓰지 않는다"* 를 검사한다(열림 검사 누락과 구분되지 않기
 *   때문). 여기 한 곳에서만 `true` 를 쓰고, 호출부는 **의도를 이름으로** 말한다.
 */
export function useModalFocusWhileMounted(ref: RefObject<HTMLElement | null>): void {
  useModalFocus(ref, true);
}
