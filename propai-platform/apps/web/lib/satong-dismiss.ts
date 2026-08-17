/**
 * ESC 해제 조정기 — **가장 위 표면 하나만** 닫는다.
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

type Entry = { z: number; close: () => void };

const entries = new Map<number, Entry>();
let seq = 0;
let bound = false;

function onKeyDown(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  if (entries.size === 0) return;

  let top: Entry | null = null;
  for (const entry of entries.values()) {
    if (!top || entry.z > top.z) top = entry;
  }
  if (!top) return;

  // ★하나만 닫는다. 나머지는 다음 ESC 를 기다린다.
  top.close();
  // 아직 마이그레이션되지 않은 외부 리스너가 같은 keydown 에 또 발화하지 않도록 표시한다
  // (조정기 밖 핸들러가 `defaultPrevented` 를 보면 양보할 수 있게 하는 최소 협조).
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

/** 테스트 전용 — 등록 현황(개수와 z 목록). 공허한 초록을 막기 위한 관찰창이다. */
export function __dismissibleSnapshot(): { count: number; zs: number[] } {
  return { count: entries.size, zs: [...entries.values()].map((e) => e.z).sort((a, b) => a - b) };
}
