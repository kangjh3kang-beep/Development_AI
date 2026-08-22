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

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const el = ref.current;
      if (!el) return;
      trapFocus(el, e);
    };
    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      // ★사라진 요소로 돌려보내지 않는다(언마운트된 버튼 등) — 그러면 포커스가 body 로 튄다.
      if (restoreTo && document.contains(restoreTo)) restoreTo.focus?.();
    };
  }, [ref, open]);
}
