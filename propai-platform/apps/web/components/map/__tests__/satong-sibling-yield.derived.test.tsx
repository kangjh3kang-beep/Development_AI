/**
 * 상세정보팝업 **양보 계약**의 형제 표면 락 — **렌더된 DOM** 에서 파생으로 전수 수집한다.
 *
 * ## 왜 소스 텍스트에서 DOM 으로 옮겼나 (2026-08-19)
 *
 * 첫 판은 여는 태그 텍스트에서 `absolute|fixed` **리터럴**을 찾았다. 리뷰어가 뚫었다:
 * 양보 표시를 지우고 같은 요소의 `className` 을 파일 상단 상수로 **호이스팅**했더니
 * 파생 락·런타임 락이 **모두 SURVIVED**(대조군: 표시만 지우면 CAUGHT). 즉 이 저장소에서
 * 가장 자연스러운 리팩토링이 그대로 우회로였다.
 * → 분류 키를 **렌더 결과**로 옮긴다. `className` 이 어디에 쓰였든 DOM 에는 같은 문자열이
 *   남으므로 그 변이가 죽는다. (jsdom 은 CSS 를 계산하지 않지만 클래스 **문자열**은 남는다.)
 *
 * ## 수집 범위 = CSS 도달 범위 (일부러 일치시킨다)
 *
 * CSS 는 `:has(> [트리거])` / `:has(> * > [트리거])` 로 지도의 **부모·조부모 스코프**를 덮는다.
 * 이 수집기도 딱 그 두 스코프를 훑는다. 범위가 어긋나면 "CSS 는 안 닿는데 락은 초록"인
 * 조용한 무배선이 다시 생긴다.
 * ★앞선 형제도 **포함**한다. 한때 "지도보다 먼저 그려지니 못 덮는다"고 적었는데 거짓이다 —
 *   DOM 순서가 페인트를 정하는 건 z-index:auto/0 끼리일 때뿐이고, 이 저장소 오버레이는
 *   전부 z-[400](양수)이라 지도(z:0) 뒤에 그려진다.
 * ★**자체 기준면 안에 갇힌 것은 뺀다**(위양성 방지). 조상 중에 relative/absolute/fixed/sticky 가
 *   있으면 그 박스를 못 벗어나므로 지도 위로 갈 수 없다. 이걸 안 뺐더니 흐름 카드 안의
 *   장식 배지 점(`absolute -right-1 -top-1`)이 위반으로 신고됐다(리뷰어 실증).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SATONG_POPUP_YIELD } from "@/lib/satong-map-z";
import { __stripCommentsForScan } from "@/lib/source-invariant";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: postMock, get: postMock },
  ApiClientError: class ApiClientError extends Error {},
}));

// 지도 엔진 스텁 — 실물의 **루트 계약**(트리거 속성)만 흉내 낸다. 실물이 그 계약을 지키는지는
// `SatongMultiMap.popupYieldRoot.test.tsx` 가 실물 렌더로 따로 잠근다(스텁 우회 방지).
vi.mock("@/components/map/SatongMultiMap", () => ({
  SatongMultiMap: () => (
    <div data-testid="satong-multi-map" {...{ [SATONG_POPUP_YIELD.wrapperAttr]: "false" }} />
  ),
}));

const WEB_ROOT = join(__dirname, "..", "..", "..");
const MAP_TAG_RE = /(?<![A-Za-z0-9_$])<SatongMultiMap/;
const POSITION = new Set(["absolute", "fixed"]);
const CONTAINING = new Set(["relative", "absolute", "fixed", "sticky"]);

/** Tailwind 변형 접두(`md:absolute`)를 떼고 마지막 토큰만 본다. */
const tokens = (el: Element) => [...el.classList].map((c) => c.split(":").pop() ?? c);
const isPositioned = (el: Element) => tokens(el).some((t) => POSITION.has(t));
const isContainingBlock = (el: Element) => tokens(el).some((t) => CONTAINING.has(t));

/**
 * 지도(트리거를 단 요소)의 **부모·조부모 스코프**에서 지도를 덮을 수 있는 요소를 전수 수집.
 * 지도 **내부**는 제외한다 — 그건 지도 컴포넌트 자신의 계약이고 자손 매치로 이미 덮인다.
 */
function collectOverlays(container: HTMLElement): HTMLElement[] {
  const map = container.querySelector(`[${SATONG_POPUP_YIELD.wrapperAttr}]`);
  if (!map) throw new Error("지도 루트를 찾지 못했다 — 프로브 하네스가 깨졌다(공허한 초록 금지)");
  const scopes = [map.parentElement, map.parentElement?.parentElement].filter(Boolean) as Element[];
  const found = new Set<HTMLElement>();
  for (const scope of scopes) {
    for (const el of scope.querySelectorAll<HTMLElement>("*")) {
      if (el === map || map.contains(el)) continue;
      if (!isPositioned(el)) continue;
      let boxed = false;
      for (let a = el.parentElement; a && a !== scope; a = a.parentElement) {
        if (isContainingBlock(a)) { boxed = true; break; }
      }
      if (!boxed) found.add(el);
    }
  }
  return [...found];
}

/** 위반 요소를 소스에서 되짚어 `파일:줄` 을 만든다(분류 비용을 낮춘다). */
function locate(file: string, el: HTMLElement): string {
  const needle = (el.getAttribute("class") ?? "").slice(0, 40);
  if (needle) {
    const lines = readFileSync(join(WEB_ROOT, file), "utf8").split("\n");
    const idx = lines.findIndex((l) => l.includes(needle));
    if (idx >= 0) return `${file}:${idx + 1}`;
  }
  return `${file}:?(소스에서 못 찾음 — 상수 호이스팅일 수 있다. class 로 grep 하라)`;
}

/**
 * 소비처별 처분. **소스 파생 목록과 집합이 같아야** 한다 — 새 소비처가 생기면 빨강이 되어
 * "프로브를 붙일지, 오버레이가 없는지"를 사람이 판정하게 만든다(목록이 조용히 stale 되지 않는다).
 */
const DISPOSITION: Record<string, "probe" | "no-sibling-overlay"> = {
  "components/map/NearbyTransactionsMap.tsx": "probe",
  "components/map/ParcelBoundaryMap.tsx": "probe",
  "components/precheck/ZoningSignalMap.tsx": "probe",
  "components/common/GlobalAddressSearch.tsx": "no-sibling-overlay",
  "components/operations/LandScheduleClient.tsx": "no-sibling-overlay",
  "components/precheck/SatongMapShell.tsx": "no-sibling-overlay",
};

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next" || name === "__tests__") continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, acc);
    else if (name.endsWith(".tsx") && !name.includes(".test.")) acc.push(full);
  }
  return acc;
}

const consumers = walk(join(WEB_ROOT, "components"))
  .concat(walk(join(WEB_ROOT, "app")))
  .filter((f) => MAP_TAG_RE.test(__stripCommentsForScan(readFileSync(f, "utf8"), f)))
  .map((f) => relative(WEB_ROOT, f))
  .sort();

/** 프로브 — 지도 **형제**가 실제로 렌더되는 상태를 만든다. */
const PROBES: Array<{ file: string; label: string; mount: () => Promise<HTMLElement> }> = [
  {
    file: "components/map/NearbyTransactionsMap.tsx",
    label: "실거래 조회실패 + 분양 0곳(하단 리본 2종)",
    mount: async () => {
      postMock.mockImplementation(async (path: string) =>
        path === "/zoning/nearby-map"
          ? { center: { lat: 37.57, lon: 126.98 }, radius_m: 1000, lawd_cd: "11110", months: [], categories: {}, fetch_failed: true, note: "조회 실패" }
          : { available: false, items: [] },
      );
      const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
      const { container, findByText } = render(<NearbyTransactionsMap address="서울 종로구 청운동 1-1" />);
      await findByText(/조회 실패/);
      return container;
    },
  },
  {
    file: "components/map/NearbyTransactionsMap.tsx",
    label: "로딩 스크림(전면 차단)",
    mount: async () => {
      postMock.mockImplementation(() => new Promise<never>(() => {}));
      const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
      const { container } = render(<NearbyTransactionsMap address="서울 종로구 청운동 1-1" />);
      return container;
    },
  },
  {
    file: "components/map/NearbyTransactionsMap.tsx",
    label: "선택 유형 거래 0건(하단 pill)",
    mount: async () => {
      postMock.mockImplementation(async (path: string) =>
        path === "/zoning/nearby-map"
          ? {
              center: { lat: 37.57, lon: 126.98 },
              radius_m: 1000,
              lawd_cd: "11110",
              months: [],
              // 기본 선택(kind=trade · type=apt)에 **빈 그룹**을 준다 → "해당 유형 최근 거래 없음".
              categories: { apt_trade: { label: "아파트", type: "apt", kind: "trade", count: 0, groups: [] } },
            }
          : { available: false, items: [] },
      );
      const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
      const { container, findByText } = render(<NearbyTransactionsMap address="서울 종로구 청운동 1-1" />);
      await findByText(/해당 유형 최근 거래 없음/);
      return container;
    },
  },
  {
    file: "components/map/ParcelBoundaryMap.tsx",
    label: "경계 조회 중(전면 스크림)",
    mount: async () => {
      postMock.mockImplementation(() => new Promise<never>(() => {}));
      const { ParcelBoundaryMap } = await import("@/components/map/ParcelBoundaryMap");
      const { container } = render(<ParcelBoundaryMap parcels={["서울 종로구 청운동 1-1"]} />);
      return container;
    },
  },
  {
    file: "components/precheck/ZoningSignalMap.tsx",
    label: "구획 데이터 없음(하단 리본)",
    mount: async () => {
      const { ZoningSignalMap } = await import("@/components/precheck/ZoningSignalMap");
      const { container } = render(<ZoningSignalMap geojson={null} signals={[]} centerHint={{ lat: 37.57, lon: 126.98 }} />);
      return container;
    },
  },
];

describe("사통맵 형제 오버레이 — 팝업 양보 계약 파생 락(렌더 기반)", () => {
  beforeEach(() => { postMock.mockReset(); });

  it("공허 진리 가드 — 소스에서 소비처를 실제로 찾았고, 처분표와 집합이 같다", () => {
    expect(consumers.length).toBeGreaterThanOrEqual(4); // 실측 6
    // 새 소비처가 생기면 여기서 빨강 — 처분을 강제한다(목록이 조용히 stale 되지 않는다).
    expect(consumers).toEqual(Object.keys(DISPOSITION).sort());
    expect(PROBES.length).toBeGreaterThanOrEqual(3);
  });

  it("★렌더된 형제 오버레이는 전부 '양보'(완전/시각) 또는 '열거된 면제 사유'를 단다", async () => {
    const allowedChrome: string[] = [SATONG_POPUP_YIELD.passiveValue, SATONG_POPUP_YIELD.passiveVisualValue];
    const reasons = SATONG_POPUP_YIELD.exemptReasons;
    const violations: string[] = [];
    let collected = 0;

    for (const probe of PROBES) {
      const container = await probe.mount();
      const overlays = collectOverlays(container);
      collected += overlays.length;
      for (const el of overlays) {
        const chrome = el.getAttribute(SATONG_POPUP_YIELD.passiveAttr);
        const exempt = el.getAttribute(SATONG_POPUP_YIELD.exemptAttr);
        const at = `${probe.label} → ${locate(probe.file, el)}`;
        if (chrome) {
          if (!allowedChrome.includes(chrome)) violations.push(`${at} :: 알 수 없는 양보 값 "${chrome}"`);
          continue;
        }
        if (exempt) {
          const reason = reasons.find((r) => r.id === exempt);
          if (!reason) { violations.push(`${at} :: 열거되지 않은 면제 사유 "${exempt}" — SATONG_POPUP_YIELD.exemptReasons 에 추가하고 근거를 적어라`); continue; }
          // ★사유가 **말이 되는 형태**인지까지 본다 — "전면 차단"이라면 실제로 전면이어야 한다.
          if (!tokens(el).includes(reason.requiredClass)) {
            violations.push(`${at} :: 면제 "${exempt}" 는 ${reason.requiredClass} 를 요구하는데 없다(면제 남용)`);
          }
          continue;
        }
        violations.push(`${at} :: 양보 표시도 면제 사유도 없다 — 팝업을 항상 덮는다`);
      }
    }

    // 공허 진리 가드를 단언 **앞**에: 수집이 0이면 "위반 0"은 아무 뜻도 없다.
    expect(collected, "형제 오버레이를 하나도 수집하지 못했다 — 프로브가 상태를 못 만든 것이다").toBeGreaterThanOrEqual(5);
    expect(violations).toEqual([]);
  });

  it("★두 양보 단계가 실제로 **둘 다** 쓰인다 — 한쪽으로 몰리면 구분이 이름만 남는다", async () => {
    const values = new Set<string>();
    for (const probe of PROBES) {
      for (const el of collectOverlays(await probe.mount())) {
        const v = el.getAttribute(SATONG_POPUP_YIELD.passiveAttr);
        if (v) values.add(v);
      }
    }
    expect([...values].sort()).toEqual(
      [SATONG_POPUP_YIELD.passiveValue, SATONG_POPUP_YIELD.passiveVisualValue].sort(),
    );
  });

  it("프로브 없는 소비처는 소스에도 형제 오버레이가 없다(약한 2차망 — 리터럴 기반)", () => {
    // ★정직: 이 검사는 `absolute` **리터럴**을 본다. className 을 상수로 호이스팅하면 뚫린다.
    //   정본은 위 렌더 프로브다. 여기는 "프로브를 안 붙인 파일이 조용히 오버레이를 얻는" 경우를
    //   싸게 잡는 보조망일 뿐이다.
    const offenders: string[] = [];
    for (const [file, disposition] of Object.entries(DISPOSITION)) {
      if (disposition !== "no-sibling-overlay") continue;
      const src = __stripCommentsForScan(readFileSync(join(WEB_ROOT, file), "utf8"), join(WEB_ROOT, file));
      const lines = src.split("\n");
      lines.forEach((line, i) => {
        if (!MAP_TAG_RE.test(line)) return;
        const indent = line.length - line.trimStart().length;
        for (let j = i + 1; j < lines.length; j += 1) {
          if (!lines[j].trim()) continue;
          if (lines[j].length - lines[j].trimStart().length < indent) break;
          if (/\b(absolute|fixed)\b/.test(lines[j])) offenders.push(`${file}:${j + 1}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });

  it("★트리거가 지도 **루트**에 붙고, 값이 팝업 상태에 묶여 있다", () => {
    const file = join(WEB_ROOT, "components/map/SatongMultiMap.tsx");
    const src = __stripCommentsForScan(readFileSync(file, "utf8"), file);
    const triggerIdx = src.indexOf("SATONG_POPUP_YIELD.wrapperAttr");
    expect(triggerIdx).toBeGreaterThan(-1);
    // 종전 위치(지도 래퍼)로 되돌아가면 깨진다 — 래퍼는 트리거보다 **뒤**에 나와야 한다.
    expect(triggerIdx).toBeLessThan(src.indexOf('wrapperClass("relative")'));
    // ★변이 검증이 만들어 낸 케이스: 값을 상수 "false" 로 굳혀도 아무도 안 죽었다(SURVIVED).
    //   Leaflet 이 jsdom 에서 안 떠 열림 상태를 실물로 만들 수 없어 소스로 본다.
    expect(src.slice(triggerIdx, triggerIdx + 200)).toContain("detailPopupOpen");
  });

  it.todo("프로브 없는 소비처도 렌더로 태운다 — SatongMapShell 등은 마운트 비용이 커 미착수(부채)");
});
