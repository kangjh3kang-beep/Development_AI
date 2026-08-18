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

import { cleanup, fireEvent, render } from "@testing-library/react";
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
  // ★스코프는 CSS 와 **정확히 같은 한 겹**이다(`:has(> [트리거])` = 지도의 부모).
  //   R3 에서 두 겹(`> * >`)을 걷어냈다 — 그 단계가 컴포넌트 경계를 넘어 남의 크롬을 흐렸다.
  const scope = map.parentElement;
  if (!scope) throw new Error("지도 루트에 부모가 없다 — 하네스가 깨졌다");
  const found = new Set<HTMLElement>();
  for (const el of scope.querySelectorAll<HTMLElement>("*")) {
    if (el === map || map.contains(el)) continue;
    if (!isPositioned(el)) continue;
    let boxed = false;
    for (let a = el.parentElement; a && a !== scope; a = a.parentElement) {
      if (isContainingBlock(a)) { boxed = true; break; }
    }
    if (!boxed) found.add(el);
  }
  return [...found];
}

/**
 * **표시는 달았는데 계약이 못 닿는** 요소 — 조용한 무배선의 정확한 형태다.
 * 지도를 래퍼로 한 겹 더 감싸고 그 래퍼의 형제에 표시를 달면 CSS 가 안 닿는데 화면은 그대로다.
 */
function unreachableMarked(container: HTMLElement): HTMLElement[] {
  const map = container.querySelector(`[${SATONG_POPUP_YIELD.wrapperAttr}]`);
  const scope = map?.parentElement;
  if (!map || !scope) return [];
  const marked = container.querySelectorAll<HTMLElement>(
    `[${SATONG_POPUP_YIELD.passiveAttr}], [${SATONG_POPUP_YIELD.exemptAttr}]`,
  );
  return [...marked].filter((el) => !scope.contains(el));
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
const PROBED_FILES = [
  "components/map/NearbyTransactionsMap.tsx",
  "components/map/ParcelBoundaryMap.tsx",
  "components/precheck/ZoningSignalMap.tsx",
];

const DISPOSITION: Record<string, "probe" | "no-sibling-overlay"> = {
  "components/map/NearbyTransactionsMap.tsx": "probe",
  "components/map/ParcelBoundaryMap.tsx": "probe",
  "components/precheck/ZoningSignalMap.tsx": "probe",
  "components/common/GlobalAddressSearch.tsx": "no-sibling-overlay",
  "components/operations/LandScheduleClient.tsx": "no-sibling-overlay",
  "components/precheck/SatongMapShell.tsx": "no-sibling-overlay",
};

/**
 * 프로브 대상 파일에서 **지도 형제 자리의 절대위치 여는 태그 수**를 센다(앞뒤 양쪽).
 * 이 값이 렌더 커버리지의 **하한**이 된다 — 사람이 센 숫자로 굳는 것을 막는다.
 * ★한때 하한이 `>= 5` 였고 실제 수집도 정확히 5였다. 여유가 0이라 "5면 충분"이 되어,
 *   프로브 없는 분기 3개(오류 패널·위치확인불가 리본·분양 0곳 pill)가 감시망 밖이었다.
 *   그 중 하나는 표시를 지워도 118 테스트가 전원 통과했다(리뷰어 실증 — 구판 대비 회귀).
 * ★리터럴 스캔이라 상수 호이스팅에 뚫린다. 그래도 **하한 산출**에만 쓰므로, 뚫리면 하한이
 *   낮아질 뿐 위반을 놓치지 않는다(정본은 렌더 수집이다).
 */
function siblingTagCountInSource(file: string): number {
  const src = __stripCommentsForScan(readFileSync(join(WEB_ROOT, file), "utf8"), join(WEB_ROOT, file));
  const lines = src.split("\n");
  let count = 0;
  lines.forEach((line, i) => {
    if (!MAP_TAG_RE.test(line)) return;
    const indent = line.length - line.trimStart().length;
    const scan = (from: number, step: number) => {
      for (let j = from; j >= 0 && j < lines.length; j += step) {
        if (!lines[j].trim()) continue;
        if (lines[j].length - lines[j].trimStart().length < indent) break;
        if (/\b(absolute|fixed)\b/.test(lines[j])) count += 1;
      }
    };
    scan(i + 1, 1); // 뒤따르는 형제
    scan(i - 1, -1); // ★앞선 형제도 센다 — CSS 는 이제 양쪽을 덮는다
  });
  return count;
}

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
    file: "components/map/NearbyTransactionsMap.tsx",
    label: "조회 실패(전면 오류 패널 — 유일한 '면제' 요소)",
    mount: async () => {
      // ★이 프로브가 없어서 `exemptReasons`(닫힌 집합 + inset-0 요구)가 **공허**했다:
      //   코드베이스의 유일한 면제 요소가 이 패널인데 그 상태를 아무도 만들지 않았다.
      postMock.mockImplementation(async () => { throw new Error("network down"); });
      const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
      const { container, findByText } = render(<NearbyTransactionsMap address="서울 종로구 청운동 1-1" />);
      await findByText(/지도 표시 실패/);
      return container;
    },
  },
  {
    file: "components/map/NearbyTransactionsMap.tsx",
    label: "좌표 폴백까지 실패(상단 '위치 확인 불가' 리본)",
    mount: async () => {
      postMock.mockImplementation(async (path: string) => {
        if (path === "/zoning/nearby-map") return { center: null, radius_m: 1000, lawd_cd: "11110", months: [], categories: {} };
        if (path === "/zoning/parcel-boundaries") throw new Error("timeout");
        return { available: false, items: [] };
      });
      const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
      const { container, findByText } = render(<NearbyTransactionsMap address="서울 종로구 청운동 1-1" pnu="1111010100100010000" />);
      await findByText(/위치 확인 불가/);
      return container;
    },
  },
  {
    file: "components/map/NearbyTransactionsMap.tsx",
    label: "분양 겹쳐보기 ON · 0곳(하단 pill)",
    mount: async () => {
      postMock.mockImplementation(async (path: string) =>
        path === "/zoning/nearby-map"
          ? { center: { lat: 37.57, lon: 126.98 }, radius_m: 1000, lawd_cd: "11110", months: [], categories: {} }
          : { available: false, items: [] },
      );
      const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
      const { container, findByRole, findByText } = render(<NearbyTransactionsMap address="서울 종로구 청운동 1-1" />);
      fireEvent.click(await findByRole("button", { name: /분양 겹쳐보기/ }));
      await findByText(/반경 내 분양 단지 없음/);
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

/**
 * 프로브를 **깨끗한 문서에서** 마운트한다.
 * ★RTL 의 바인딩된 쿼리는 `baseElement`(= document.body)를 본다 — 앞 프로브의 렌더가 남아 있으면
 *   `findByRole` 이 "여러 개 찾음"으로 죽는다(실측). 프로브마다 문서를 비운다.
 */
async function mountProbe(probe: (typeof PROBES)[number]): Promise<HTMLElement> {
  cleanup();
  postMock.mockReset();
  return probe.mount();
}

describe("사통맵 형제 오버레이 — 팝업 양보 계약 파생 락(렌더 기반)", () => {
  beforeEach(() => { postMock.mockReset(); });

  it("공허 진리 가드 — 소스에서 소비처를 실제로 찾았고, 처분표와 집합이 같다", () => {
    expect(consumers.length).toBeGreaterThanOrEqual(4); // 실측 6
    // 새 소비처가 생기면 여기서 빨강 — 처분을 강제한다(목록이 조용히 stale 되지 않는다).
    expect(consumers).toEqual(Object.keys(DISPOSITION).sort());
    expect(PROBES.length).toBeGreaterThanOrEqual(3);
  });

  it("★렌더된 형제 오버레이는 전부 '양보'(완전/시각) 또는 '열거된 면제 사유'를 단다", async () => {
    const reasons = SATONG_POPUP_YIELD.exemptReasons;
    const violations: string[] = [];
    const coveredClasses = new Set<string>();
    const stagesSeen = new Set<string>();

    for (const probe of PROBES) {
      const container = await mountProbe(probe);

      // ★계약이 **못 닿는 자리에 표시를 단** 경우 — 화면은 그대로인데 코드는 고친 줄 안다.
      for (const el of unreachableMarked(container)) {
        violations.push(
          `${probe.label} → ${locate(probe.file, el)} :: 표시는 있으나 계약 스코프 밖이다 ` +
            "(오버레이는 지도 루트의 **직계 형제**여야 한다 — SATONG_POPUP_YIELD 문서 참조)",
        );
      }

      for (const el of collectOverlays(container)) {
        coveredClasses.add(el.getAttribute("class") ?? "");
        const chrome = el.getAttribute(SATONG_POPUP_YIELD.passiveAttr);
        const exempt = el.getAttribute(SATONG_POPUP_YIELD.exemptAttr);
        if (chrome) stagesSeen.add(chrome);
        const at = `${probe.label} → ${locate(probe.file, el)}`;
        const fullBleed = tokens(el).includes(SATONG_POPUP_YIELD.visualOnlyRequiredClass);

        if (chrome === SATONG_POPUP_YIELD.passiveVisualValue) {
          // ★NEW-3: 단계 **선택**을 잠근다. 상시 고지형을 시각만 양보로 강등하면 흐려진 채
          //   팝업 위 클릭을 계속 삼켜 "가려서 못 누르는" 상태가 그 밴드에서 부활한다.
          if (!fullBleed) {
            violations.push(`${at} :: 시각만 양보(${chrome})는 전면(${SATONG_POPUP_YIELD.visualOnlyRequiredClass}) 차단형에만 준다 — 상시 고지형은 완전 양보여야 한다`);
          }
          continue;
        }
        if (chrome === SATONG_POPUP_YIELD.passiveValue) {
          if (fullBleed) {
            violations.push(`${at} :: 전면 오버레이를 완전 양보로 두면 조회 중 지도가 조작된다 — ${SATONG_POPUP_YIELD.passiveVisualValue} 를 쓰라`);
          }
          continue;
        }
        if (chrome) { violations.push(`${at} :: 알 수 없는 양보 값 "${chrome}"`); continue; }

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

    // ★공허 진리 가드를 단언 **앞**에. 하한은 사람이 센 숫자가 아니라 **소스 파생값**이다 —
    //   분기가 늘면 하한이 따라 올라가 "프로브 없는 분기"가 자동으로 빨강이 된다.
    const required = PROBED_FILES.reduce((sum, f) => sum + siblingTagCountInSource(f), 0);
    expect(required, "소스에서 형제 오버레이를 하나도 못 셌다 — 스캐너가 깨졌다").toBeGreaterThanOrEqual(8);
    expect(
      coveredClasses.size,
      `프로브가 덮은 형제 오버레이가 ${coveredClasses.size}종뿐이다(소스 파생 하한 ${required}) — ` +
        "덮이지 않은 분기가 남아 있다. 그 상태를 만드는 프로브를 추가하라",
    ).toBeGreaterThanOrEqual(required);
    // 대조군: 두 단계가 **둘 다** 실제로 쓰인다 — 한쪽으로 몰리면 구분이 이름만 남는다.
    expect([...stagesSeen].sort()).toEqual(
      [SATONG_POPUP_YIELD.passiveValue, SATONG_POPUP_YIELD.passiveVisualValue].sort(),
    );
    expect(violations).toEqual([]);
  });

  it("★면제 채널이 **실제 대상 위에서** 검사된다 — 분기 로직만 멀쩡한 상태 금지", async () => {
    // 리뷰어 실증: 닫힌 집합·requiredClass 를 도입했는데 코드베이스의 유일한 면제 요소를
    // 렌더하는 프로브가 없어, 열거 밖 사유로 바꿔도 전원 통과했다(도달 불가 분기).
    const seen: string[] = [];
    for (const probe of PROBES) {
      for (const el of collectOverlays(await mountProbe(probe))) {
        const exempt = el.getAttribute(SATONG_POPUP_YIELD.exemptAttr);
        if (exempt) seen.push(exempt);
      }
    }
    expect(seen.length, "면제 요소를 렌더하는 프로브가 하나도 없다 — 면제 규칙이 공허하다").toBeGreaterThanOrEqual(1);
    for (const id of new Set(seen)) {
      expect(SATONG_POPUP_YIELD.exemptReasons.map((r) => r.id)).toContain(id);
    }
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
        // ★앞뒤 **양쪽**을 본다 — CSS 가 이제 앞선 형제도 덮으므로 한쪽만 보면 비대칭이 된다.
        const scan = (from: number, step: number) => {
          for (let j = from; j >= 0 && j < lines.length; j += step) {
            if (!lines[j].trim()) continue;
            if (lines[j].length - lines[j].trimStart().length < indent) break;
            if (/\b(absolute|fixed)\b/.test(lines[j])) offenders.push(`${file}:${j + 1}`);
          }
        };
        scan(i + 1, 1);
        scan(i - 1, -1);
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
  it.todo("지도를 래퍼로 감싸고 **표시 없는** 오버레이를 래퍼 형제에 두는 경우 — CSS 도 락도 못 잡는다(잔여 위험)");
});
