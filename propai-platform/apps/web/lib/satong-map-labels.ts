/**
 * 사통맵 라벨(마커 상시 툴팁) 시스템 공용화 — 라벨 폭주·이중 박스·겹침(S1) 봉합의 단일 계약.
 *
 * 종전엔 실거래·분양·경매·POI·개발계획 5곳이 각자 인라인 `bindTooltip` 을 호출하고,
 * 레이어별로 `개수 ≤ 32` 만 판정해 합산 최대 ~160개 상시 라벨이 지도를 살포했다.
 * 여기서 (1) 전역 라벨 버짓 + 줌 LOD 판정을 순수 함수로 모으고,
 *        (2) 라벨 부착을 `bindSatongLabel` 한 곳으로 단일화한다.
 *
 * ★박스 스타일은 `.satong-tooltip` 전역(무레이어) CSS 가 담당한다(globals.css) —
 *   Leaflet 기본 흰 박스·테두리·padding·화살표를 무력화해 '이중 박스'를 제거한다.
 *   이 헬퍼는 라벨 내용을 textContent(안전한 텍스트 노드)로만 넣어 XSS 여지를 없앤다.
 */

/** z=17(근접)에서 허용하는 전역 상시 라벨 상한(모든 레이어 합산). */
export const SATONG_LABEL_BUDGET = 64;
/** z≥18(초근접) 상한 — 확대로 화면 밀도가 낮아지면 사실상 전 마커 상시 표시(정보 상시화). */
export const SATONG_LABEL_BUDGET_NEAR = 96;
/** 15~16(중간 줌)에서 허용하는 축소 상한 — '상위 N'만 상시 표시. */
export const SATONG_LABEL_BUDGET_MID = 24;

export type SatongLabelLOD = "all" | "top" | "hover-only";

/**
 * 줌 레벨 → 라벨 LOD(Level of Detail).
 *   z≥17: 전체(버짓 한도 내) · 15~16: 상위 N · <15: hover-only(상시 라벨 0, 겹침 방지).
 */
export function satongLabelLOD(zoom: number): SatongLabelLOD {
  if (zoom >= 17) return "all";
  if (zoom >= 15) return "top";
  return "hover-only";
}

/** 줌 레벨에 대응하는 전역 상시 라벨 버짓(상한).
 *
 * ★2026-07-17 정보 상시화: "마우스를 올려야만 보인다"는 불편을 줄이기 위해 버짓 상향
 *   (48/16 → 96·64/24) — 확대할수록 화면 공간이 생기므로 상시 라벨을 늘린다(jootek류
 *   가격 pill 패턴). 겹침 방지는 여전히 버짓 상한+선택 라벨 줌 롤업이 담당한다. */
export function satongLabelBudget(zoom: number): number {
  if (zoom >= 18) return SATONG_LABEL_BUDGET_NEAR;
  const lod = satongLabelLOD(zoom);
  if (lod === "all") return SATONG_LABEL_BUDGET;
  if (lod === "top") return SATONG_LABEL_BUDGET_MID;
  return 0;
}

/** 레이어별 라벨 후보 수(좌표 있는 마커 수). */
export interface SatongLabelLayerCount {
  id: string;
  count: number;
}

/**
 * 전역 버짓을 레이어 우선순위 순서로 배분한다.
 * 반환: layer id → 그 레이어에서 상시(permanent)로 표시 가능한 라벨 수(선두 N개).
 *
 * ★핵심: 합산이 버짓을 넘지 않는다(∑ 반환값 ≤ satongLabelBudget(zoom)). 앞 레이어가 버짓을
 *   먼저 소진하면 뒤 레이어는 0(=전부 hover)이 된다. 각 레이어는 마커를 순서대로 그리며
 *   `순번 < 반환값` 인 마커만 상시 라벨을 붙인다(줌아웃·밀집 시 자동 hover 강등).
 */
export function planSatongLabels(
  zoom: number,
  layers: SatongLabelLayerCount[],
): Record<string, number> {
  let remaining = satongLabelBudget(zoom);
  const out: Record<string, number> = {};
  for (const layer of layers) {
    const take = Math.max(0, Math.min(Math.max(0, layer.count), remaining));
    out[layer.id] = take;
    remaining -= take;
  }
  return out;
}

/** bindSatongLabel 옵션. */
export interface BindSatongLabelOptions {
  /** 상시(true) / hover(false) 표시 — planSatongLabels 판정 결과를 넘긴다. */
  permanent: boolean;
  /** 마커 위쪽 오프셋(px, 양수). 마커 반경만큼 띄운다. 기본 8. */
  offsetY?: number;
}

/**
 * 사통맵 마커에 표준 라벨 툴팁을 부착한다(인라인 bindTooltip 5곳의 단일 대체).
 *
 * ★PR#329 R1 리뷰(LOW2) 반영 — 미사용 `L`(Leaflet 전역) 파라미터 제거. 콘텐츠 노드는
 *   전역 `document`로 직접 만들 뿐 Leaflet 네임스페이스가 필요 없었다(호출부는 `marker`가
 *   이미 Leaflet 인스턴스라 L을 별도로 넘길 이유가 없다).
 *
 * @param marker  대상 Leaflet 마커/서클마커
 * @param text    라벨 텍스트(원문 — textContent로 안전하게 삽입, 이스케이프 불필요)
 * @param opts    permanent/offsetY
 */
/** 라벨 클릭 처리를 위해 필요한 최소 계약(구조적 타이핑 — Leaflet 전체를 끌어오지 않는다). */
type SatongLabelHost = {
  bindTooltip: (content: unknown, options: unknown) => unknown;
  on?: (type: string, fn: (e: unknown) => void) => unknown;
  getTooltip?: () => { getElement?: () => HTMLElement | undefined } | undefined;
  getPopup?: () => unknown;
  openPopup?: () => unknown;
};

/**
 * 라벨(툴팁) DOM 에 클릭 처리를 건다 — **지도로 새지 않게** 하고, 팝업이 있으면 **그것을 연다**.
 *
 * ★★2026-09-09 사용자 신고③의 **나머지 절반**: *"토지로 필지로 표시되고 **인식되는건가**"*.
 *   #1018 이 「표시」를 고쳤고(유형 배지) 여기서 「인식」을 고친다.
 *
 * ★실측(jsdom + **진짜 Leaflet 1.9.4**): 툴팁 DOM 에 `click` 을 디스패치하면
 *   `map.on("click")` 이 **1회 발화**한다. 그리고 그 핸들러는 `setClickMenu(...)` =
 *   **필지 선택 팝오버**를 연다(`SatongMultiMap.tsx`). 가드는 `readOnly` 뿐인데 신고 화면은
 *   그 prop 을 **안 넘긴다**(0건). ⇒ 가격 라벨을 누르면 **엉뚱한 필지 선택이 열린다.**
 *
 * ★**`bindTooltip(..., { interactive: true })` 는 쓰지 않는다 — 효과가 없다.**
 *   Leaflet 1.9.4 원문 `Tooltip` 블록(`leaflet-src.js:10642~10870`)에 **`interactive` 언급이 0건**
 *   이고 `Tooltip._initLayout` 도 그 옵션을 보지 않는다(실측). 그래서 **DOM 에 직접** 건다.
 *
 * ★브라우저와 jsdom 의 **경로가 다르다**(정직 표기):
 *   · 브라우저 — `pointer-events:none` 이면 라벨이 클릭을 **안 받고** 아래(지도)로 통과
 *   · jsdom    — `pointer-events` 를 **무시**하고 라벨이 받아 **버블링**
 *   **결과는 같다**(지도 click 발화). 그래서 이 함수는 **양쪽 모두** 막도록
 *   `stopPropagation` + `preventDefault` 를 걸고, CSS 는 `pointer-events: auto` 로 둔다
 *   (브라우저에서 라벨이 **클릭을 받아야** 이 핸들러가 산다).
 */
function bindClickToLabelEl(host: SatongLabelHost): void {
  const el = host.getTooltip?.()?.getElement?.();
  if (!el) return;
  const marked = el as HTMLElement & { __satongClickBound?: boolean };
  if (marked.__satongClickBound) return; // 중복 바인딩 금지(툴팁은 열릴 때마다 이 경로를 탄다)
  marked.__satongClickBound = true;
  el.addEventListener("click", (ev: MouseEvent) => {
    // ★항상 삼킨다 — 팝업이 없어도(측정·선택 앵커) **지도로 새면 안 된다**.
    ev.stopPropagation();
    ev.preventDefault();
    // ★팝업이 있으면 연다. **호출부별 분기를 두지 않는다**(목록은 곧 상한) —
    //   «팝업을 가졌는가»를 물어서 가른다.
    // ★★`getPopup?.()` 가드를 지우는 변이는 **SURVIVED 이고 그 생존은 등가다** —
    //   Leaflet 의 `openPopup` 이 `if (this._popup) {…}` 로 시작해 팝업이 없으면 **무동작**이다
    //   (`leaflet-src.js:10517-10518` 원문 확인). 즉 Leaflet 호스트에서는 가르는 입력이 없다.
    //   ★그래도 남긴다: 이 함수의 인자는 **구조적 타입**(`SatongLabelHost`)이라 Leaflet 이 아닌
    //     호스트도 받을 수 있고, 그때 «팝업이 없는데 여는» 호출이 무해하다는 보장이 없다.
    //     §변이 규율 — **설명할 수 없는 생존만 구멍**이다. 사유를 여기 적고 점수용 단언은 만들지 않는다.
    if (typeof host.openPopup === "function" && host.getPopup?.()) host.openPopup();
  });
}

function attachLabelClick(host: SatongLabelHost): void {
  if (typeof host.on !== "function") return;
  // 툴팁 DOM 은 **열린 뒤에야** 존재하므로 열림마다 건다(hover 라벨은 매번 새로 만들어진다).
  host.on("tooltipopen", () => bindClickToLabelEl(host));
  // ★★그리고 **이미 열려 있는 경우**를 함께 처리한다 — 그것이 이 함수의 첫 판을 죽였다:
  //   `permanent: true` 는 마커가 이미 지도에 있으면 `bindTooltip` 이 **즉시** 툴팁을 열어
  //   `tooltipopen` 이 **이 리스너를 달기 전에** 발화한다(실측: 상시 라벨 3케이스 전부 실패,
  //   hover 케이스만 통과 — 그 비대칭이 원인을 가리켰다).
  //   ★한쪽만 걸면 반대쪽이 무제한이 된다(§D-19) — 두 경로를 **한 쌍**으로 건다.
  bindClickToLabelEl(host);
}

export function bindSatongLabel(
  marker: SatongLabelHost,
  text: string,
  opts: BindSatongLabelOptions,
): unknown {
  // 내용은 텍스트 노드로만 — HTML 주입(XSS) 여지 제거. 박스 스타일은 .satong-tooltip CSS 담당.
  const el = typeof document !== "undefined" ? document.createElement("span") : null;
  const content: unknown = el ? ((el.textContent = text), el) : text;
  const bound = marker.bindTooltip(content, {
    permanent: opts.permanent,
    direction: "top",
    offset: [0, -(opts.offsetY ?? 8)],
    className: "satong-tooltip",
  });
  attachLabelClick(marker);
  return bound;
}

/**
 * 실거래 라벨의 **금액 표기** 조립 — 총액·평당 **병기** 계약(2026-09-04 사용자 요청).
 *
 * ★종전엔 either/or 였다(`unit-price` 토글이 총액을 평당으로 **대체**). 한쪽을 보려면
 *   다른 쪽을 포기해야 했고, 컨트롤 설명도 *"총액 대신 평당가로 표시"* 라 적혀 있었다.
 *   이제 **둘 다 항상** 보이고, 토글은 **어느 쪽을 앞에 둘지**만 정한다.
 *
 * ★평당가는 **서버가 준 값**만 쓴다(정본 `per_pyeong_10k`, 유효숫자 3자리).
 *   여기서 `총액 ÷ 면적` 을 다시 계산하지 않는다 — 그 나눗셈은 원천이 이미 평당으로 정한
 *   값을 역산하는 것이라 **없는 가격차를 만든다**(#930 이 실측으로 확인).
 *
 * ★없는 값은 **생략**한다. `0` 을 찍지 않는다 — "평당 0원"으로 읽힌다.
 */
export function composeMarketPriceTag(opts: {
  kind: "trade" | "rent";
  /** 이미 포맷된 총액 문자열(예 `"3.6억"`). 없으면 null. */
  totalText: string | null | undefined;
  /** 서버가 준 평당가(만원/평). 면적 결측 등이면 null/undefined. */
  perPyeong10k: number | null | undefined;
  /** `unit-price` 컨트롤 — 켜면 평당가를 앞에 둔다. */
  pyeongFirst: boolean;
}): string {
  if (opts.kind !== "trade") return "";
  const total = opts.totalText ? String(opts.totalText) : null;
  const pp =
    typeof opts.perPyeong10k === "number" && Number.isFinite(opts.perPyeong10k) && opts.perPyeong10k > 0
      ? `${opts.perPyeong10k.toLocaleString()}만/평`
      : null;
  const ordered = opts.pyeongFirst ? [pp, total] : [total, pp];
  const shown = ordered.filter((v): v is string => !!v);
  return shown.length ? ` ${shown.join(" · ")}` : "";
}
