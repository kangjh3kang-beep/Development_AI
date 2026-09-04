"use client";

import dynamic from "next/dynamic";
import { registerDismissible } from "@/lib/satong-dismiss";
import { SATONG_POPUP_YIELD, SATONG_UI_Z } from "@/lib/satong-map-z";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  Building2,
  CheckCircle2,
  ChevronRight,
  Download,
  FileSpreadsheet,
  Gavel,
  Home,
  Landmark,
  Layers,
  Image as ImageIcon,
  LineChart,
  Loader2,
  MapIcon,
  MapPin,
  Mountain,
  Route,
  Search,
  Sparkles,
  Trash2,
  TrainFront,
  X,
  TrendingUp,
  Eye,
} from "lucide-react";
import {
  type ChangeEvent,
  type ComponentType,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { useToastOptional } from "@propai/ui"; // UX 트랙 C3 — 내보내기 완료 등 일시 고지용(호스트 없으면 인라인 폴백)
import { ApiClientError, apiClient, apiV1BaseUrl, hasAccessToken } from "@/lib/api-client";
import { formatArea, formatPercent, formatPercentPoint } from "@/lib/formatters"; // 면적·비율 표기 SSOT(비율=정수 반올림 금지·0과 미확보 구분)
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { AnalysisPipelineStepbar, type PipelineStep } from "@/components/common/AnalysisPipelineStepbar"; // UX 트랙 C4 — 엑셀 업로드 진행표시(기존 프리미티브 재사용)
import { ContextHeader } from "@/components/common/ContextHeader"; // 집계 SSOT 단일표면(UX 트랙 B2)
import { DataSourceNotice } from "@/components/ui/DataSourceNotice";
import { DominantConstraintBanner } from "@/components/precheck/DominantConstraintBanner"; // W1 지배 제약 — 필지 상세 최상단
import {
  ParcelSlopeSection,
  type ParcelSlopeStatus,
} from "@/components/precheck/ParcelSlopeSection"; // W2 경사도 — 필지 상세 온디맨드
import type { TerrainResult } from "@/components/terrain/types";
import {
  ParcelLayoutSection,
  type ParcelLayoutStatus,
} from "@/components/precheck/ParcelLayoutSection"; // W3 배치 미리보기
import { buildMassSeedHandoff, writeMassSeedHandoff } from "@/lib/satong-mass-seed"; // W4 매스 시드 인계
import {
  buildLayoutOverlay,
  resolveSelectedOption,
  siteLayoutOptionKey,
  type SiteLayoutOption,
  type SiteLayoutResult,
} from "@/lib/site-layout";
import type {
  ParcelAtPointResult,
  SatongAuctionItem,
  SatongDevelopmentPayload,
  SatongMarketPayload,
  SatongMultiMapProps,
  SatongPoiPayload,
  SatongPresaleItem,
} from "@/components/map/SatongMultiMap";
import {
  MARKET_RENT_TYPES,
  MARKET_TRADE_TYPES,
  isRenderableSatongMapLayer,
  resolveSelectionAnchor,
  type DominantConstraint,
  type SatongMapFeature,
  type SatongMapLayerId,
  type SatongMapLayerState,
  capacityRatio,
  resolveVWorldBaseLayer,
} from "@/lib/satong-map-layers";
import { buildSelectionGeoJson, buildSelectionKml, kakaoRoadviewUrl } from "@/lib/satong-export";
import { joinAddressJibun, normalizePnu } from "@/lib/pnu";
import { isSameParcel } from "@/lib/parcel-entry-identity";
import { countJibunHealTargets, healParcelJibunByPoint } from "@/lib/parcel-jibun-heal";
import { ParcelJibunLabel } from "@/components/precheck/ParcelJibunLabel";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { restoreSnapshot } from "@/lib/projectSync";
import { createProjectFromParcels } from "@/lib/satong-project-create";
import { marketRadiusRequest } from "@/lib/market/market-radius";
import {
  SATONG_PARCEL_SLOPE_KEY,
  SATONG_SITE_LAYOUT_KEY,
  dominantConstraintKey,
  readDominantConstraintCache,
  readSatongViewCache,
  writeSatongViewCache,
  readSatongMapSelection,
  emptySelectionSiteAnalysisPatch,
  selectionToSiteAnalysisPatch,
  siteAnalysisToSelection,
  writeDominantConstraintCache,
  writeSatongMapSelection,
  type SatongSelectionParcel,
} from "./satong-map-selection";
import {
  deriveProjectNameFromParcels,
  selectionMismatchesProject,
} from "./satong-project-connect";
import { classifySelection, selectionIntegrityNotice } from "@/lib/selection-integrity";
import {
  selectionContaminationKey,
  trackSelectionContamination,
} from "@/lib/growth/selection-contamination";
import { useSatongMapPrefs } from "@/store/useSatongMapPrefsStore";

// ★UX 트랙 D3(지도 높이 반응형 — 진단G 실측): 종전 고정 720px는 모바일에서 지도가
//   화면 대부분을 점유했다. clamp(하한, 선호값, 상한) — 60dvh를 선호하되 satong-map-z.ts
//   계약(측정 rail↔줌 충돌 방지 — 지도 높이 500px 미만 배치 금지)의 하한 500px을 보장하고,
//   기존 720px을 상한으로 유지해 데스크톱은 무회귀(넉넉한 뷰포트에서 60dvh가 이미 ≥720px).
const SATONG_MAP_HEIGHT = "clamp(500px, 60dvh, 720px)";

// 레일 폭과 팝오버 앵커의 단일 출처.
//   레일은 접힘 w-16(64px)·펼침 w-32(128px)이고 right-4(16px)에 붙는다. 팝오버는 레일을
//   가리지 않도록 그 왼쪽에 서야 하므로 앵커도 레일 상태를 따라가야 한다.
//   ★실결함: 팝오버가 접힘 폭 기준 right-20으로 고정돼 있어, 레일 기본값이 펼침으로 바뀐 뒤
//     팝오버가 레일 왼쪽 열 버튼 7개를 통째로 덮고 z(430>420)까지 높아 클릭도 막았다.
//     두 값을 한 곳에서 파생시켜 한쪽만 바뀌는 재발을 구조적으로 차단한다.
//   ★좁은 화면(<sm)은 옆에 세우지 않고 전폭으로 편다. 레일을 피해 옆으로 밀면 남는 폭이
//     100px 남짓이 되어(375px 폰 기준 컨테이너 281px − 176px) 2열 컨트롤과 '지도에 표시'
//     확정 버튼이 들어가지 못한다 — 레일을 안 가리려다 확정 경로를 막는 역효과.
//     모바일에선 전폭 오버레이가 레일을 덮지만, 팝오버는 '확정 단계'라 그동안 레일 탐색이
//     필요 없다(닫으면 레일이 다시 온전히 보인다).
const RAIL_POPOVER_ANCHOR = {
  // right-36(144px) = right-4(16) + w-32(128) — 레일과 정확히 맞닿는다(여백 0).
  pinned: "inset-x-4 sm:inset-x-auto sm:right-36 sm:w-[min(360px,calc(100%-176px))]",
  // right-20(80px) = right-4(16) + w-16(64)
  collapsed: "inset-x-4 sm:inset-x-auto sm:right-20 sm:w-[min(360px,calc(100%-112px))]",
} as const;

/**
 * ★레일 hover '전환' 의도 지연(ms).
 *
 * 레일이 2열(`railPinned` 펼침 = `grid-cols-2`)이고 팝오버는 레일 **바깥 왼쪽**(`right-36`)에
 * 뜬다. 그래서 **오른쪽 열 아이콘에서 팝오버로 가려면 왼쪽 열 위를 반드시 지나야** 하는데,
 * 지나가는 순간 그 아이콘의 mouseenter가 즉시 다른 레이어로 팝오버를 갈아치워 정작 열려던
 * 팝오버가 사라졌다(사용자 지적). 1열이던 시절엔 없던 **2열 전환이 만든 회귀**다.
 *
 * ★임계 근거(모델 — 실측 아님, 가정을 밝힌다): 레일 실측 CSS로 재구성하면 오른쪽 열 아이콘
 * 좌단(우측 끝에서 76px)에서 팝오버(144px)까지 68px 중 **51px가 왼쪽 열 아이콘**이다. 즉
 * 통과 구간의 3/4이 장애물이고 자유 통로는 8px(열 간격)+9px(패딩)뿐이다. 단절 없는 1회
 * 포인팅이면 통과 체류가 100ms 안팎이지만, **트랙패드·비숙련·저감도 포인터**나 방금 뜬
 * 팝오버를 읽느라 손이 잠깐 멎는 gaze-lead 구간에서는 150ms를 넘겨 방어가 뚫린다(보수적
 * Fitts 계수 기준 최하단 행 대각 동선에서 ~172ms). 그래서 임계를 250ms로 둔다 — 통상적인
 * hover-intent 관행(200~300ms) 안이고, 의도적 전환의 체감 지연보다 **목적 팝오버가 사라지는
 * 파괴적 실패**를 피하는 쪽이 사용자 지적에 부합한다. 실제 포인터 속도 로그는 **미측정**이다.
 * ★첫 열기(아무 팝오버도 없을 때)에는 지연을 걸지 않아 반응성을 그대로 보존한다.
 */
const HOVER_SWITCH_DELAY_MS = 250;

/**
 * 모바일 IA P1 — 연결된 프로젝트의 대상(주소·필지)이 도착하기를 기다리는 유예(ms).
 *
 * ★왜 시간인가: `projectId` 는 있는데 대상이 없는 상태에서 "복원이 오는 중"과 "원래 없음"을
 *   상태만으로 가를 수 없다. 프로젝트 목록은 `page_size=20` 으로 잘려 오고(프론트가 page 를
 *   보내지 않는다) 동기화 실패 시 조용히 비며, `syncing` 은 렌더 시점 캡처값이라 콜드 스타트에서
 *   항상 false 다 — 둘 다 정착 신호가 되지 못한다(R2 실측). 그래서 추론 대신 **기다려 본다**.
 * ★유예 안에 대상이 오면 판정 이펙트가 재실행되며 cleanup 이 타이머를 취소하므로 접힘이 유지된다.
 * ★2초는 임의 상수다(스냅샷 복원 왕복의 실측 분포는 **미측정**). 짧으면 복원된 프로젝트의 접힘을
 *   잃고, 길면 대상 없는 사용자가 빈 화면을 그만큼 오래 본다. 후자가 이 수정이 없애려던 증상이라
 *   보수적으로 짧은 쪽에 두되, 늦은 도착의 대가(접힘 상실)는 감수한다.
 */
const TARGET_RESTORE_GRACE_MS = 2000;

function railPopoverAnchor(pinned: boolean): string {
  return pinned ? RAIL_POPOVER_ANCHOR.pinned : RAIL_POPOVER_ANCHOR.collapsed;
}

const SatongMultiMap = dynamic<SatongMultiMapProps>(
  () =>
    import("@/components/map/SatongMultiMap").then(
      (mod) => mod.SatongMultiMap as ComponentType<SatongMultiMapProps>,
    ),
  {
    ssr: false,
    loading: () => (
      <div
        className="grid place-items-center rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] text-sm font-bold text-[var(--text-secondary)]"
        style={{ height: SATONG_MAP_HEIGHT }}
      >
        <span className="inline-flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          통합지도를 불러오는 중
        </span>
      </div>
    ),
  },
);

type SearchCandidate = {
  address?: string | null;
  road_address?: string | null;
  jibun?: string | null;
  pnu?: string | null;
  kind?: string | null;
  lat?: number | null;
  lon?: number | null;
};

type SearchResponse = {
  candidates?: SearchCandidate[];
};

type GeocodeResponse = {
  found?: boolean;
  address?: string | null;
  road_address?: string | null;
  jibun_address?: string | null;
  pnu?: string | null;
  bcode?: string | null;
  lat?: number | null;
  lon?: number | null;
  reason?: string | null;
};

/**
 * `/zoning/parse-parcels` 응답 1행.
 *
 * ★`lat`/`lon` 을 **일부러 받지 않는다**(2026-08-20 백엔드 실측). 백엔드 `_geocode_fill` 은
 *   `p["lat"]/p["lon"]` 을 박은 **뒤에** "번지 없이 동·읍·면 단위" 가드로 `p["pnu"]` 를 보류한다.
 *   즉 해석에 실패한 행일수록 **동 대표지점 좌표**가 실려 오고, 같은 동 77행이면 77개가
 *   전부 같은 좌표다. 그걸 받아 좌표 치유를 돌리면 77행이 전부 같은 필지로 해석된다.
 *   PNU 로 이미 복구되므로 좌표를 들일 이유도 없다 — 안 받는 것이 방어다.
 *   (2차 방어선은 `lib/parcel-jibun-heal` 의 "좌표 공유 필지 제외".)
 */
type ParsedParcel = {
  address?: string | null;
  jibun?: string | null;
  pnu?: string | null;
  area_sqm?: number | null;
  zone_type?: string | null;
  jimok?: string | null;
  official_price_per_sqm?: number | null;
  // ★검증 리포트(additive) — 행별 최종분류. 구버전 응답(필드 부재)과 호환되도록 옵셔널.
  verification_status?: "verified" | "corrected" | "needs_review" | null;
  verification_reasons?: string[] | null;
  injectable?: boolean | null;
};

type VerificationCorrection = {
  field?: string | null;
  before?: string | number | null;
  after?: string | number | null;
  reason?: string | null;
};

type VerificationReport = {
  counts?: { verified?: number; corrected?: number; needs_review?: number; excluded?: number } | null;
  corrections?: VerificationCorrection[] | null;
  warnings?: string[] | null;
  llm_used?: boolean | null;
  passes?: number | null;
};

type ParseParcelsResponse = {
  parcels?: ParsedParcel[];
  note?: string | null;
  error?: string | null;
  verification_report?: VerificationReport | null;
};

type SatongParcel = SatongSelectionParcel;

type LayerStatus = "active" | "ready" | "needs-source";

type SatongLayer = {
  id: SatongMapLayerId;
  label: string;
  shortLabel: string;
  description: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  status: LayerStatus;
  tone: string;
  source: string;
  controls: SatongLayerControl[];
};

type SatongLayerControl = {
  id: string;
  label: string;
  mapEffect: boolean;
  description?: string;
};

type OutputAction = {
  id: string;
  label: string;
  description: string;
  href: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  tone: string;
};

/**
 * 통합지도 레이어 정의 레지스트리.
 * 정직 라벨 원칙: 지도에 실데이터가 렌더링되는(mapEffect) 레이어의 source 는
 * '연동 필요'가 아니라 실제 연동된 원천을 기술해야 한다.
 * (테스트 검증용으로 export — components/precheck/__tests__/SatongMapShell.layers.test.ts)
 */
// ★팝오버 헤더 on/off 미노출 레이어(R1 M-3/M-4/M-D — 단발 예외 대신 패턴 상수화).
//   terrain : on/off 소유자가 베이스맵 스위처(끄면 배경지도가 조용히 롤백·라벨도 거짓)
//   cadastre: 기반 레이어라 끌 수 없음(토글 무동작 = 죽은 버튼)
const LAYERS_WITHOUT_POPOVER_TOGGLE = new Set<SatongMapLayerId>(["terrain", "cadastre"]);

const LAYERS: SatongLayer[] = [
  {
    id: "cadastre",
    label: "지적도",
    shortLabel: "지적",
    description: "필지 경계, 지목, 면적, PNU를 선택 기준으로 사용합니다.",
    // ★WP-M4: 레일 앵커(지도 레이어 관리)의 MapIcon과 중복 인지되던 것을 Layers로 교체(아이콘-기능 1:1).
    icon: Layers,
    status: "active",
    tone: "bg-lime-100 text-lime-950 border-lime-200",
    source: "필지 클릭 API + 지적 경계",
    controls: [
      { id: "boundary", label: "필지 경계", mapEffect: true },
      { id: "selected", label: "선택 필지", mapEffect: true },
      { id: "neighbors", label: "주변 필지", mapEffect: false, description: "주변 필지 벡터 API 연결 후 활성화" },
    ],
  },
  {
    id: "zoning",
    label: "용도지역",
    shortLabel: "용도",
    description: "선택 필지의 용도지역을 색상으로 구분해 지도에 반영합니다.",
    icon: Landmark,
    status: "active",
    tone: "bg-sky-100 text-sky-950 border-sky-200",
    source: "공간정보(토지특성정보) API 연동",
    controls: [
      { id: "land-use", label: "용도지역", mapEffect: true },
      { id: "land-use-wide", label: "전국 지적편집도", mapEffect: true, description: "화면 전체를 용도지역 색상으로 표시(VWorld)" },
      // ★규제 오버레이(2026-07-17 잠금 해제): 아래 2개는 "원천 연결 후 활성화" 플레이스홀더로
      //   설계돼 있었고, VWorld WMS 원천(GetCapabilities+GetMap 매트릭스 채증)이 확보되어
      //   설계 의도대로 활성화한다. 매핑은 satong-map-layers.REGULATION_WMS_BY_CONTROL 단일 SSOT.
      { id: "district-unit", label: "지구단위", mapEffect: true, description: "지구단위계획 구역을 지도에 표시(VWorld)" },
      { id: "development-limit", label: "개발행위 제한", mapEffect: true, description: "개발행위허가 제한구역을 지도에 표시(VWorld)" },
      { id: "water-protect", label: "상수원보호", mapEffect: true, description: "상수원보호구역 — 개발행위 제한 요인(VWorld)" },
      { id: "edu-protect", label: "교육환경보호", mapEffect: true, description: "교육환경보호구역 — 숙박·위락 업종 인허가 직결(VWorld)" },
      { id: "height-district", label: "고도지구", mapEffect: true, description: "고도지구 — 건축물 높이 제한(VWorld)" },
    ],
  },
  {
    id: "official-price",
    label: "공시지가",
    shortLabel: "공시",
    description: "선택 필지의 개별공시지가(㎡당 단가)를 지도에 색상으로 반영합니다.",
    icon: LineChart,
    status: "active",
    tone: "bg-emerald-100 text-emerald-950 border-emerald-200",
    source: "공간정보(VWorld NED) 토지특성 API 연동",
    controls: [
      { id: "unit-price", label: "㎡당 단가", mapEffect: true },
      { id: "year", label: "연도", mapEffect: false, description: "연도별 공시지가 이력 연결 후 활성화" },
      { id: "change-rate", label: "변동률", mapEffect: false, description: "연도별 공시지가 이력 연결 후 활성화" },
    ],
  },
  {
    // WS-D① 개발여력 히트맵(선택필지 MVP) — (실효FAR−현황FAR)/실효FAR 코로플레스.
    // 실효=calc_effective_far 7계층 min(서버)·현황=건축물대장 전동 연면적합/대지면적(서버).
    // 미상 필지는 무색+무자료 고지(무날조). 뷰포트 전역 배치 산출은 후속(배치 엔드포인트).
    id: "capacity",
    label: "개발여력",
    shortLabel: "여력",
    description: "실효 용적률 대비 남은 개발 여력을 색상으로 표시합니다(지을 수 있는 만큼 못 지은 땅 발굴).",
    icon: TrendingUp,
    status: "active",
    tone: "bg-green-100 text-green-950 border-green-200",
    source: "실효한도(7계층)+건축물대장 연면적 서버 산정",
    controls: [
      { id: "far-headroom", label: "용적 여력", mapEffect: true },
    ],
  },
  {
    id: "age",
    label: "노후도",
    shortLabel: "노후",
    description: "건축물대장 기반 준공연도(연식)를 색상으로 구분합니다. 나대지·미준공은 표시하지 않습니다.",
    icon: Building2,
    status: "active",
    tone: "bg-rose-100 text-rose-950 border-rose-200",
    source: "건축물대장 표제부(건축HUB, 사용승인일)",
    controls: [
      { id: "building-age", label: "건축연도", mapEffect: true },
      { id: "structure", label: "구조", mapEffect: false, description: "건축물대장 구조 필드 연결 후 활성화" },
      { id: "floors", label: "층수", mapEffect: false, description: "건축물대장 층수 필드 연결 후 활성화" },
      { id: "purpose", label: "주용도", mapEffect: false, description: "건축물대장 주용도 필드 연결 후 활성화" },
    ],
  },
  {
    id: "transactions",
    label: "실거래·시세",
    shortLabel: "시세",
    description: "선택 필지 주변(1km·최근 3개월) 실거래를 마커로 지도에 반영합니다. 필지를 먼저 선택하세요.",
    icon: Home,
    status: "active",
    tone: "bg-blue-100 text-blue-950 border-blue-200",
    source: "국토교통부 실거래가(주변 1km·최근 3개월)",
    controls: [
      // ★유형 다중 표시(분석품질 레인G P0): 종전 "거래유형" 단일 스텁을 6개 실제 유형
      // 토글로 승격(다중 선택 — 개발 실무는 토지·상업업무용도 필수). 라벨은 색상 SSOT
      // (lib/satong-map-layers.MARKET_TRADE_TYPES)와 동일 출처.
      ...MARKET_TRADE_TYPES.map((t) => ({ id: `type-${t.key}`, label: t.label, mapEffect: true })),
      // 매매/전월세 — 배타 전환(handleLayerControlClick kind- 분기). kind 자체가 백엔드
      // 카테고리 키(`${type}_${kind}`)의 축이라 동시선택은 무의미.
      { id: "kind-trade", label: "매매", mapEffect: true },
      { id: "kind-rent", label: "전월세", mapEffect: true },
      { id: "deal-year", label: "거래연도", mapEffect: false, description: "거래연도 필터 — 향후 제공" },
      { id: "total-price", label: "총액", mapEffect: false, description: "총액 필터 — 향후 제공" },
      { id: "unit-price", label: "평당가 라벨", mapEffect: true, description: "실거래 라벨을 총액 대신 평당가로 표시" },
    ],
  },
  {
    id: "presale",
    label: "분양정보",
    shortLabel: "분양",
    description: "선택 필지(또는 지도 중심) 주변 3km의 분양단지를 마커로 표시합니다.",
    icon: Sparkles,
    status: "active",
    tone: "bg-violet-100 text-violet-950 border-violet-200",
    source: "청약홈 분양정보(주변 3km)",
    controls: [
      { id: "supply-type", label: "공급유형", mapEffect: false, description: "공급유형 필터 — 향후 제공" },
      { id: "presale-price", label: "분양가", mapEffect: false, description: "분양가 필터 — 향후 제공" },
      { id: "move-in", label: "입주시기", mapEffect: false, description: "입주시기 필터 — 향후 제공" },
    ],
  },
  {
    id: "auction",
    label: "공·경매",
    shortLabel: "경매",
    description: "선택 필지 주변(10km)의 온비드 공매 물건을 마커로 표시합니다. 로그인이 필요할 수 있습니다.",
    icon: Gavel,
    status: "active",
    tone: "bg-amber-100 text-amber-950 border-amber-200",
    source: "온비드 공매(주변 10km·감정가/최저가)",
    controls: [
      { id: "appraisal", label: "감정가", mapEffect: false, description: "감정가 필터 — 향후 제공" },
      { id: "minimum-bid", label: "최저가", mapEffect: false, description: "최저가 필터 — 향후 제공" },
      { id: "bid-date", label: "입찰일", mapEffect: false, description: "입찰일 필터 — 향후 제공" },
      { id: "bid-rate", label: "낙찰률", mapEffect: false, description: "낙찰률 필터 — 향후 제공" },
    ],
  },
  {
    id: "poi",
    label: "교통·편의 POI",
    shortLabel: "POI",
    description: "선택 필지 주변(800m)의 역·학교·상권·공원·병원을 마커로 표시합니다. 필지를 먼저 선택하세요.",
    icon: TrainFront,
    status: "active",
    tone: "bg-cyan-100 text-cyan-950 border-cyan-200",
    source: "Kakao Local 반경검색(카카오 로컬)",
    controls: [
      { id: "station", label: "역", mapEffect: true },
      { id: "school", label: "학교", mapEffect: true },
      { id: "commerce", label: "상권", mapEffect: true },
      { id: "park", label: "공원", mapEffect: true },
      { id: "hospital", label: "병원", mapEffect: true },
    ],
  },
  {
    id: "development",
    label: "개발계획",
    shortLabel: "개발",
    description: "선택 필지 주변(1km)의 도시계획시설(철도·역사 등 계획·결정)을 마커로 표시합니다. 필지를 먼저 선택하세요.",
    icon: Route,
    status: "active",
    tone: "bg-violet-100 text-violet-950 border-violet-200",
    source: "VWorld 도시계획시설(UPIS 계열)",
    controls: [
      { id: "facilities", label: "도시계획시설", mapEffect: true },
    ],
  },
  {
    id: "terrain",
    label: "지형도·항공뷰",
    shortLabel: "지형",
    description: "경사, 고저차, 항공사진을 사업 리스크와 설계 제약에 반영합니다.",
    icon: Mountain,
    status: "ready",
    tone: "bg-stone-100 text-stone-950 border-stone-200",
    source: "VWorld WMTS 프록시 연동(기본·위성·항공뷰)",
    controls: [
      { id: "base", label: "기본지도", mapEffect: true },
      { id: "satellite", label: "위성", mapEffect: true },
      { id: "hybrid", label: "항공뷰", mapEffect: true },
      { id: "elevation", label: "표고", mapEffect: false, description: "표고/경사도 격자 원천 연결 후 활성화" },
      { id: "gray", label: "회색지도", mapEffect: true, description: "저채도 배경 — 데이터 대비 강조" },
    ],
  },
  {
    id: "roadview",
    label: "로드뷰",
    shortLabel: "로드",
    description: "접도, 가로환경, 출입구 후보를 현장감 있게 확인합니다.",
    icon: Eye,   // ★아이콘-기능 1:1 — 개발계획과 Route 글리프가 중복이었다
    status: "needs-source",
    tone: "bg-slate-100 text-slate-950 border-slate-200",
    source: "카카오 로드뷰 SDK 연동 필요",
    controls: [
      { id: "roadview", label: "로드뷰", mapEffect: false },
      { id: "frontage", label: "접도", mapEffect: false },
      { id: "vehicle-access", label: "차량 진입", mapEffect: false },
      { id: "pedestrian-access", label: "보행 접근", mapEffect: false },
    ],
  },
];

export { LAYERS as SATONG_MAP_SHELL_LAYERS };

// 항공뷰 썸네일 베이스맵 스위처(jootek 패리티) — terrain 컨트롤 재사용.
// ★스와치=실물 타일 미리보기(2026-07-17 직관력 보강): 스와치의 본질은 "이 버튼을 누르면
//   실제로 보이는 지도"의 미리보기라, 같은 프록시(/tiles/vworld/wmts)의 실제 타일을 쓴다
//   — 실서비스(카카오·네이버·jootek) 관행. 생성/장식 이미지는 실렌더와 어긋나는 약속이라
//   무목업 원칙에 반한다. 자기 오리진 프록시 경유 = CSP 안전(외부 host 아님 — 종전
//   "외부 이미지 금지" 의도 유지). 그라디언트 클래스는 타일 로드 실패 시 폴백으로 잔존.
//   대표 타일 z12/1583/3492 = 서울 도심(한강·시가지·산 대비로 4스타일 차이가 명확 —
//   2026-07-17 라이브 4종 200 실측). Hybrid는 실렌더와 동일하게 위성 위 라벨 합성.
const SWATCH_TILE_BASE = "/tiles/vworld/wmts";
const SWATCH_TILE_ZYX = "12/1583/3492";
const BASEMAP_SWITCHES = [
  { id: "base", label: "일반", base: "Base", swatch: "bg-gradient-to-br from-slate-100 via-emerald-50 to-emerald-100",
    tiles: [`${SWATCH_TILE_BASE}/Base/${SWATCH_TILE_ZYX}.png`] },
  { id: "satellite", label: "위성", base: "Satellite", swatch: "bg-gradient-to-br from-slate-800 via-emerald-950 to-slate-900",
    tiles: [`${SWATCH_TILE_BASE}/Satellite/${SWATCH_TILE_ZYX}.jpeg`] },
  { id: "hybrid", label: "하이브리드", base: "Hybrid", swatch: "bg-gradient-to-br from-slate-700 via-sky-950 to-slate-800",
    // CSS 다중 배경은 먼저 쓴 것이 위 — 라벨(Hybrid)을 위성 위에 얹는 실렌더 합성과 동일.
    tiles: [`${SWATCH_TILE_BASE}/Hybrid/${SWATCH_TILE_ZYX}.png`, `${SWATCH_TILE_BASE}/Satellite/${SWATCH_TILE_ZYX}.jpeg`] },
  // ★id("gray")=UI 컨트롤 식별자(:1353 상호배타 해제셋 키·LAYERS 정의와 일치) /
  //   base("white")=VWorld tiletype 정본 — 별개 네임스페이스라 분리 유지한다.
  //   종전 base:"gray"는 상류 미존재값이라 회색 선택 시 배경지도가 통째로 사라졌다.
  { id: "gray", label: "회색", base: "white", swatch: "bg-gradient-to-br from-slate-200 to-slate-400",
    tiles: [`${SWATCH_TILE_BASE}/white/${SWATCH_TILE_ZYX}.png`] },
] as const;

const sourceLabel: Record<SatongParcel["source"], string> = {
  search: "검색",
  excel: "엑셀",
  map: "지도",
};

function getCandidateLabel(candidate: SearchCandidate): string {
  return (
    candidate.address ||
    candidate.road_address ||
    candidate.jibun ||
    candidate.pnu ||
    "주소 미확인"
  );
}

function normalizeKey(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

/**
 * 선택목록 병합(addParcels) 의 **필지 정체성 키**.
 *
 * ★★2026-08-20 CRITICAL — `pnu || address` 만으로는 **77필지가 1필지로 지워진다.**
 *   신고 프로젝트는 77필지의 **주소가 전부 같다**(`경기도 오산시 내삼미동`). 종전에는 PNU 칸에
 *   들어앉은 서로 다른 **가짜값**이 우연히 유일성을 제공하고 있었다 — 그 가짜를 정화하는 순간
 *   유일성이 사라져 `new Map(prev.map(p => [parcelKey(p), p]))` 가 77개를 한 키로 접고,
 *   `syncParcelsToStores` 가 그 1건을 **영속**한다(지도에서 필지 하나만 클릭해도 발화).
 *
 *   그래서 PNU 가 없으면 **필지별 유일 id** 로 떨어진다. 복원 id 는 `store-${index}-${address}`
 *   라 필지마다 다르고, 삽입 경로 id 는 `pnu || normalizeKey(address)` 라 기존 중복제거 계약이
 *   그대로 유지된다(같은 주소를 두 번 담으면 여전히 1건 — 무회귀).
 *
 * ★저장소 기준선과 같은 처방이다: `ParcelSurveyQuotePanel` 이 PNU 없는 필지에
 *   `project-idx:${i}:${address}` 를 붙여 같은 함정을 이미 풀어 놨다.
 */
function parcelKey(parcel: Pick<SatongParcel, "address" | "pnu" | "id">): string {
  // ★구현은 `dominantConstraintKey`(satong-map-selection) 한 곳이다 — 선택목록 병합과 뷰 캐시가
  //   **같은 정체성 규칙**을 써야 한다(두 벌이면 한쪽만 고쳐진다. 이 PR 이 반복해서 만난 함정).
  return dominantConstraintKey(parcel);
}

/**
 * ★리뷰(HIGH) 근치 — pnu/주소 키 이중성 승격.
 *
 * 시드 필지(엑셀·지오코딩)는 pnu 미확보 상태로 selectedParcels 에 들어온다(pnu=null, 키=주소).
 * 이후 지도 boundary 보강(/zoning/parcel-boundaries)이 real 19자리 pnu 를 채워 돌려주는데,
 * 종전 handleBoundaryEnriched 병합은 기존 p.pnu 를 그대로 유지해 이 real pnu 를 버렸다 —
 * autoStage(parcelMembershipKey, real pnu 기준)는 이후 계속 이 필지를 "미등록"으로 오판했고,
 * mergeSatongMapFeatures("지적 N건" 등 칩 집계)도 같은 물리 필지를 pnu-키/주소-키 2건으로 쪼갰다.
 *
 * 이 함수는 existingPnu 가 있으면 그대로 보존(real→real 덮어쓰기 금지 — 무날조), 없을 때만
 * boundaryPnu 로 승격한다. handleBoundaryEnriched 한 곳에서 이 값을 채택하면 이후 파생되는
 * selectedMapFeatures·mergeSatongMapFeatures·parcelMembershipKey 가 모두 같은 real pnu 로
 * 수렴해 칩·CTA·merge 카운트가 한 번에 정합해진다(공용화 치유).
 */
export function healParcelPnu(
  existingPnu: string | null | undefined,
  boundaryPnu: string | null | undefined,
): string | null {
  // ★2026-08-20 보강: "기존이 있으면 보존" 의 **기존**은 **진짜 PNU** 여야 한다.
  //   과거 저장분에는 PNU 칸에 주소 합성문자열이 들어앉아 있어(satong-map-selection 주석 참조),
  //   그 가짜가 "기존 값" 으로 인정돼 경계응답의 **진짜 PNU 승격을 영구히 막았다**.
  //   그래서 양쪽 모두 normalizePnu 를 통과시킨다 — 진짜끼리는 기존 우선(무날조 유지).
  return normalizePnu(existingPnu) || normalizePnu(boundaryPnu) || null;
}



function statusText(status: LayerStatus): string {
  if (status === "active") return "활성";
  if (status === "ready") return "준비";
  return "연동 필요";
}

function statusClass(status: LayerStatus): string {
  if (status === "active") return "bg-[var(--status-success)]/15 text-[var(--status-success)]";
  if (status === "ready") return "bg-[var(--accent-strong)]/15 text-[var(--accent-strong)]";
  return "bg-[var(--status-warning)]/15 text-[var(--status-warning)]";
}



function parseGeocodeToParcel(
  query: string,
  response: GeocodeResponse,
  source: SatongParcel["source"],
): SatongParcel {
  const address =
    response.address ||
    response.road_address ||
    response.jibun_address ||
    query;
  return {
    id: response.pnu || normalizeKey(address),
    address,
    pnu: response.pnu ?? null,
    lat: response.lat ?? null,
    lon: response.lon ?? null,
    source,
  };
}

function parsedParcelToSelection(parcel: ParsedParcel, index: number): SatongParcel {
  // ★`address || jibun` 이 아니라 **결합**이다(joinAddressJibun 주석 = 이 결함의 진짜 상류).
  //   소재지·지번이 분리된 엑셀 양식에서 `||` 는 지번을 평가조차 하지 않아 통째로 버렸다.
  const address = joinAddressJibun(parcel.address, parcel.jibun, parcel.pnu || "엑셀 등록 필지");
  return {
    // ★PNU 도 지번도 없어 주소가 동 단위뿐이면 **행 번호**로 구분한다. 안 그러면 같은 동
    //   77행이 한 키로 접혀 목록에 1건만 남는다(#672 가 신고된 바로 그 증상).
    //   대가: 같은 엑셀을 두 번 올리면 행이 중복된다 — **보이고 지울 수 있는** 문제이고
    //   조용히 사라지는 것보다 낫다(저장소 기준선 ParcelSurveyQuotePanel 과 같은 처방).
    id: parcel.pnu || `excel-${index}-${normalizeKey(address)}`,
    address,
    pnu: parcel.pnu ?? null,
    areaSqm: parcel.area_sqm ?? null,
    zoneType: parcel.zone_type ?? null,
    jimok: parcel.jimok ?? null,
    officialPricePerSqm: parcel.official_price_per_sqm ?? null,
    source: "excel",
  };
}

function mapParcelToSelection(parcel: ParcelAtPointResult): SatongParcel {
  // 지도 클릭도 같은 결합 규칙을 쓴다(형제 스윕 — 한쪽만 고치면 다시 갈린다).
  // ※ 폴백 문자열("지도 선택 필지")은 지도 클릭 응답이 주소·지번·PNU 를 **전부** 못 준 경우만
  //   쓰인다. 엑셀 경로의 같은 폴백은 excelJibun 테스트가 잠근다(행이 조용히 사라지는 것 차단).
  const address = joinAddressJibun(parcel.address, parcel.jibun, parcel.pnu || "지도 선택 필지");
  return {
    id: parcel.pnu || normalizeKey(address),
    address,
    pnu: parcel.pnu ?? null,
    lat: parcel.lat ?? null,
    lon: parcel.lon ?? null,
    areaSqm: parcel.area_sqm ?? null,
    zoneType: parcel.zone_type ?? null,
    jimok: parcel.jimok ?? null,
    officialPricePerSqm: parcel.official_price_per_sqm ?? null,
    builtYear: parcel.built_year ?? null,
    buildingAgeYears: parcel.building_age_years ?? null,
    geometry: parcel.geometry,
    source: "map",
  };
}

export function SatongMapShell({
  locale,
  defaultCollapsed = false,
  hasTarget: hasTargetProp,
  showContextHeader = false,
}: {
  locale: string;
  /** true면 접힌 요약(1줄)+"지도 열기" 토글로 시작한다(UX 트랙 B4 — 착지 페이지 반복
   *  렌더 완화). 기본 false(펼침 — 입력 주화면인 /ko·/precheck는 호출측에서 생략해 무회귀). */
  defaultCollapsed?: boolean;
  /**
   * ★호출측이 "이 화면에서 대상이란 무엇인가"를 주입한다(2026-08-06 후속 4단계).
   *
   * 셸이 아는 대상은 주소·필지지만, 화면마다 의미가 다르다 — 토지조서에서 사용자가 채워야
   * 하는 것은 **편입토지 행(rows)** 이라, 주소만 있고 행이 0건이면 셸이 접힌 채로 남아
   * "상단 통합 지도의 지번·주소 검색으로 등록하세요"라는 그 페이지 안내가 **접힌 컨트롤을
   * 가리키는** 상태가 됐다(P1 이 덮지 못한 조합).
   *
   * 미주입이면 셸 기본 판정(주소·필지)을 그대로 쓴다 — 무회귀가 기본값이다.
   */
  hasTarget?: boolean;
  /** true면 셸 내부에 ContextHeader(프로젝트·주소·PNU·용도지역·대지면적 SSOT)를 sticky로
   *  얹는다(UX 트랙 B2 — 집계 단일표면). 기본 false — 이 셸을 직접 렌더하는 기존 단위테스트가
   *  선택 필지 카드의 주소 title과 ContextHeader 주소 칩의 title이 겹쳐 getByTitle 단일매치
   *  계약을 깨는 회귀가 실측 확인됐다(무회귀 우선). 호출측 페이지가 명시적으로 켠 경우에만
   *  렌더한다 — market-insights처럼 이미 더 정밀한 자체 ContextHeader를 셸 위에 별도로 둔
   *  호출측은 켜지 않는다(중복 렌더 방지). */
  showContextHeader?: boolean;
}) {
  const router = useRouter();
  // ★UX 트랙 C3: 앱 셸 최상위(레이아웃)에 마운트된 ToastProvider가 있으면 일시 고지(예:
  //   내보내기 완료)를 토스트로 올린다. 이 셸을 단독 렌더하는 기존 계약 테스트 다수가
  //   ToastProvider 없이 렌더하므로(무회귀 — 그 테스트들은 건드리지 않는다), 관대한
  //   useToastOptional()을 써서 Provider 부재 시 null로 안전 강등하고 인라인 폴백으로 돌아간다.
  const toast = useToastOptional();
  const updateSiteAnalysis = useProjectContextStore((state) => state.updateSiteAnalysis);
  const projectId = useProjectContextStore((state) => state.projectId);
  const setProject = useProjectContextStore((state) => state.setProject);
  const clearProject = useProjectContextStore((state) => state.clearProject);
  const projects = useProjectStore((state) => state.projects);
  const syncFromBackend = useProjectStore((state) => state.syncFromBackend);

  useEffect(() => {
    if (!projects.length) void syncFromBackend();
  }, [projects.length, syncFromBackend]);

  // 읽기 셀렉터 — 활성 프로젝트 siteAnalysis 전체를 구독(SSOT). parcels[]뿐 아니라 레거시
  //   단일필지(top-level 주소·좌표만) 프로젝트도 비동기 스냅샷 복원 도착을 감지해야 하므로
  //   객체 단위로 읽는다. sessionStorage(자기세션 선택)가 우선, 이건 폴백/전환 시드용.
  const storeSiteAnalysis = useProjectContextStore((state) => state.siteAnalysis);
  // 연결 대상: "new"=새 프로젝트로 등록(기본) · "none"=연결 안 함(약식) · 그 외=기존 프로젝트 id.
  //   기본을 '새 프로젝트'로 두는 이유: 마지막 활성 프로젝트가 영속 기본값이면 다른 지역 필지
  //   선택이 그 프로젝트 siteAnalysis를 조용히 덮어쓴다(교차오염). 이어하기(컨텍스트에 진행 중
  //   프로젝트+데이터가 있는 경우)만 예외로 그 프로젝트를 유지한다.
  const [connectTarget, setConnectTarget] = useState<"new" | "none" | string>(() => "new");
  const [connectNotice, setConnectNotice] = useState("");
  const connectInitRef = useRef(false);
  useEffect(() => {
    if (connectInitRef.current) return;
    if (!projectId) {
      connectInitRef.current = true; // 연결된 프로젝트 없음 — 기본 'new' 확정
      return;
    }
    if (storeSiteAnalysis?.address || storeSiteAnalysis?.parcels?.length) {
      connectInitRef.current = true;
      setConnectTarget(projectId); // 이어하기 예외
      return;
    }
    // projectId는 있지만 데이터(주소·필지)가 아직 도착 전(스냅샷 복원 비동기 대기) — 여기서
    // 래치하지 않는다. 다음 storeSiteAnalysis 갱신 때 이 이펙트가 다시 실행돼 재평가한다
    // (늦은 복원 허용 — F5, 조기 래치로 '이어하기' 판정을 놓치지 않는다).
  }, [projectId, storeSiteAnalysis]);
  const [query, setQuery] = useState("");
  const [searchCandidates, setSearchCandidates] = useState<SearchCandidate[]>([]);
  // ★UX 트랙 C6: 검색 후보 콤보박스의 키보드 하이라이트 인덱스(-1=없음). 후보 목록이
  //   바뀔 때마다(새 검색·선택·닫기) 아래 이펙트가 리셋한다.
  const [activeCandidateIndex, setActiveCandidateIndex] = useState(-1);
  const searchListboxId = useId();
  useEffect(() => {
    setActiveCandidateIndex(-1);
  }, [searchCandidates]);
  const [searchStatus, setSearchStatus] = useState<"idle" | "loading" | "error">("idle");
  const [searchError, setSearchError] = useState("");
  const [selectedParcels, setSelectedParcels] = useState<SatongParcel[]>([]);

  // ★선택 무결성(2026-08-23 · 사용자 신고 후속) — "이게 하나의 개발 부지인가".
  //   합계 면적을 "통합 대지면적"이라 부르기 전에 그 전제를 검사한다. 실측으로 15.86km
  //   떨어진 6필지가 "통합 5,781㎡"로 묶여 있었고, 소유자명(`◀ 전성결`)이 주소 칸에
  //   들어온 프로젝트도 있었다. ★막지 않고 고지한다 — 원거리 묶음은 후보지 비교라는
  //   정당한 워크플로우일 수 있다(290km 건이 그렇게 보인다).
  const selectionIntegrity = useMemo(
    () => classifySelection(selectedParcels),
    [selectedParcels],
  );
  const integrityNotice = useMemo(
    () => selectionIntegrityNotice(selectionIntegrity),
    [selectionIntegrity],
  );
  // ★관측(2026-08-24) — 고지는 위에서 하지만 **빈도는 아무도 몰랐다.**
  //   빈도를 모르면 "이미 오염된 프로젝트를 정리할지"를 근거 없이 결정하게 된다.
  //   ★렌더 중이 아니라 effect 에서 보낸다(적재는 부작용이다). 같은 오염을 재렌더마다
  //     다시 세지 않도록 판정 서명으로 1회만 보낸다 — 필지가 바뀌어 판정이 달라지면
  //     그건 **새 사실**이므로 다시 보낸다.
  const contaminationSentKeyRef = useRef<string | null>(null);
  useEffect(() => {
    const key = selectionContaminationKey(selectionIntegrity);
    if (contaminationSentKeyRef.current === key) return;
    contaminationSentKeyRef.current = key;
    // route 는 null 로 넘긴다 — collector 가 `window.location` 에서 채운다(SSOT 한 곳).
    trackSelectionContamination(selectionIntegrity, null);
  }, [selectionIntegrity]);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "loading" | "error">("idle");
  const [uploadNote, setUploadNote] = useState("");
  // ★UX 트랙 C4(사용자 지적): 다필지 엑셀 업로드는 최대 180초가 걸릴 수 있는데 종전엔
  //   스피너 1개뿐 — 진행 단계·경과·취소가 전혀 없었다. 경과초는 실측(setInterval)만 쓴다
  //   (가짜 진행률 금지 — 정확한 %는 서버에 없으므로 표기하지 않는다).
  const [uploadElapsedSec, setUploadElapsedSec] = useState(0);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const uploadCancelledRef = useRef(false);
  useEffect(() => {
    if (uploadStatus !== "loading") return;
    const startedAt = Date.now();
    setUploadElapsedSec(0);
    const interval = setInterval(() => {
      setUploadElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [uploadStatus]);
  // ★검증 리포트(T5) — 업로드 직후 4분류 카운트·보정내역·확인필요 사유를 패널로 노출.
  const [verificationReport, setVerificationReport] = useState<VerificationReport | null>(null);
  const [uploadParcels, setUploadParcels] = useState<ParsedParcel[]>([]);
  // ★use_llm 옵트인(T1) — 기존 동작 보존을 위해 기본 true(비표준 양식 자동 LLM 보조 유지).
  const [useLlm, setUseLlm] = useState(true);
  const [focusTarget, setFocusTarget] = useState<{ lat: number; lon: number; label?: string } | null>(null);
  // ★영속(2026-09-04). 저장은 **배열**이다 — `Set` 은 `JSON.stringify` 로 `{}` 가 되어 안 남는다.
  //   소비처 9곳이 `.has()` 를 쓰므로 여기서 `useMemo` 로 `Set` 을 파생한다.
  //   ★스토어 액션이 **변화 없으면 같은 배열 참조**를 돌려주므로 이 memo 도 재계산되지 않는다
  //   — 그 계약이 깨지면 `mapLayerState` identity 가 바뀌고 오버레이·POI effect 가 전량
  //   재생성된다(«깜빡임의 근원»). `#965` 2차 리뷰가 정확히 그 축에서 회귀를 잡았다.
  const enabledLayerIds = useSatongMapPrefs((s) => s.enabledLayerIds);
  const toggleLayerEnabledAction = useSatongMapPrefs((s) => s.toggleLayerEnabled);
  const ensureLayerEnabled = useSatongMapPrefs((s) => s.ensureLayerEnabled);
  const enabledLayers = useMemo(
    () => new Set<SatongMapLayerId>(enabledLayerIds as SatongMapLayerId[]),
    [enabledLayerIds],
  );
  // ★초기화자를 **이름 있는 값**으로 뺀다(#959). 종전에는 인라인 화살표였고, 락이 그것을
  //   **소스 모양**으로 잠갔다 — 모양 락은 서식에 깨지고(위양성), 관계 락으로 바꾸니
  //   `() => ({ ...defaultControlsByLayer(), cadastre: [] })` 처럼 **관계는 유지한 채 계약을
  //   깨는** 변이가 샜다(위음성). 값으로 빼면 테스트가 **실행해서** 잴 수 있다.
  // ★영속 + 셀렉터 전용(2026-09-04). `useState` 지연 초기값으로 스토어를 읽지 **않는다** —
  //   `lib/hydration/render-path-store-reads.ts` 가 판정하는 위험 ①(렌더 중 라이브 읽기)에
  //   **지연 초기값이 포함**되고, 이 저장소에는 그 형태로 프로덕션 React #418 이 난 실화가 있다.
  //   셀렉터 읽기는 `zustand/middleware` 가 `api.getInitialState` 를 덮어써서 원리적으로 안전하다.
  const layerControls = useSatongMapPrefs((s) => s.controlsByLayer);
  const setLayerControls = useSatongMapPrefs((s) => s.setControlsByLayer);
  const [activeLayerId, setActiveLayerId] = useState<SatongMapLayerId | null>(null);
  const [isOutputDockOpen, setIsOutputDockOpen] = useState(true);
  // ★UX 트랙 B4 — 착지 페이지(분석/시장/토지조서)는 같은 지도셸이 반복 렌더돼 매번 첫 화면을
  //   방금 떠난 지도가 차지했다. defaultCollapsed=true인 호출측만 접힌 요약으로 시작하고,
  //   사용자가 "지도 열기"를 누르면 이 컴포넌트 인스턴스는 그대로 유지한 채(재마운트 없음 —
  //   선택·레이어 상태 보존) 펼침으로 전환한다.
  const [isShellExpanded, setIsShellExpanded] = useState(!defaultCollapsed);
  // ★모바일 IA P1(2026-08-06) — 접기를 **대상 유무에 종속**시킨다.
  //   B4의 원 의도(착지 페이지에서 방금 떠난 지도가 첫 화면을 또 먹는 문제)는 여전히 유효하나,
  //   접기가 대상 확정 여부와 **무관하게** 걸려 있었다. 대상이 없으면 접힌 셸에 남는 것은
  //   "지도에서 필지를 선택하면 요약이 표시됩니다" 한 줄과 "지도 열기" 버튼뿐이고, 주소 입력·
  //   엑셀 업로드·프로젝트 연결이 전부 접혀 있다 — **이 셸이 이 세 페이지의 유일한 주소 진입
  //   경로**인데(분석·시장·토지조서 어디에도 자체 주소 입력이 없다) 그것을 접어 버린 것이다.
  //   사용자 지적("모바일에서 주소 입력을 못 찾겠다")의 나머지 절반이 여기다.
  //
  //   ★대상이 있으면 접힘 유지(무회귀), 없으면 펼친다. 판정을 **effect 에서** 하는 이유:
  //   selectedParcels 는 useState([]) 로 시작해 아래 하이드레이션 이펙트가 채우므로 마운트
  //   시점 판정은 **항상 "대상 없음"**이 되어 defaultCollapsed 를 통째로 무력화한다.
  //   ★projectId 가 있는데 대상이 없을 때가 어렵다 — "복원이 오는 중"과 "원래 없음"이 같아 보인다.
  //   초판은 `if (projectId) return`(무기한 보류)이었는데 그러면 LandScheduleClient 가 통째로 죽는다
  //   (그 페이지는 `if (!projectId) return <안내>` **뒤에** 이 셸을 렌더해 projectId 가 항상 truthy).
  //   2판은 프로젝트 **목록**을 정착 신호로 썼는데 그것도 틀렸다(R2 지적 HIGH 2건, 프로브로 재현):
  //     · `syncing` 은 렌더 시점에 캡처된 값이라 **콜드 스타트에서 항상 false** 다. 목록을 채우는
  //       이펙트가 같은 커밋에서 먼저 set 해도 이 클로저는 못 본다 → 가드가 **발화하지 않는다**.
  //     · 목록은 `page_size=20` 기본값으로 **잘려 온다**(프론트가 page 파라미터를 안 보낸다).
  //       동기화 실패 시엔 catch 가 조용히 빈 목록을 유지한다. 즉 "목록에 없음 = 삭제·권한없음"은
  //       **거짓 불변식**이고, 21번째 이후의 멀쩡한 프로젝트가 접힘을 잃는다.
  //   ★그래서 상태를 **추론하지 않고 기다려 본다**. 유예 안에 대상이 오면 이펙트가 재실행되며
  //   cleanup 이 타이머를 취소하므로 접힘이 그대로 유지되고, 오지 않으면 없는 것으로 보고 편다.
  //   목록·동기화 플래그·페이지네이션과 **무관**해지는 것이 이 설계의 요점이다.
  //   ★늦게(유예 후) 도착하면 이미 펼쳐진 채로 남아 B4 접힘을 잃는다 — 그 대가를 감수한다.
  //   반대 위험(대상이 영영 안 와서 **입력이 영구히 접힌 화면**)이 명백히 더 나쁘기 때문이다.
  //
  //   ★호출측 주입으로 해소됨(2026-08-06 후속 4단계): 종전에는 "대상"이 **셸의 대상**(주소·필지)
  //   뿐이라 `주소 있는 프로젝트 + 편입토지 0건` 조합에서 여전히 접혔고, 토지조서의 빈 상태
  //   안내("상단 통합 지도의 지번·주소 검색…으로 등록하세요")가 접힌 컨트롤을 가리켰다.
  //   지금은 **위 `hasTarget` prop** 으로 호출측이 그 화면의 대상 정의를 주입한다
  //   (토지조서 = `rows.length > 0`). 미주입이면 셸 기본 판정 그대로 — 무회귀가 기본값이다.
  //
  //   ★1회 래치(ref)를 쓰지 않는다 — 처음엔 넣었다가 **철회**했다. 래치 제거 변이가 생존해
  //   들여다보니 래치가 막는 경로가 없었다: 이 셸에서 펼침은 (이 마운트 수명 안에서) 단방향이다
  //   (setIsShellExpanded(false) 호출이 파일 전체에 없다 — "지도 열기"도 펼치는 방향뿐. 재마운트
  //   시엔 useState 초기값으로 다시 접힌 채 시작하고 이 이펙트가 다시 평가한다).
  //   그래서 "사용자 조작을 덮지 않으려면 래치가 필요하다"는 전제 자체가 성립하지 않았다.
  //   오히려 래치가 있으면 **프로젝트 연결을 해제**했을 때(clearProject → siteAnalysis null)
  //   입력이 접힌 채 남아 이 수정이 없애려던 화면으로 되돌아간다 — 정책과 반대로 작동하는
  //   코드였다. 조건부 재평가가 곧 정책이다(대상이 없어지면 입력이 다시 나온다).
  //   ※ 초판 주석은 이 경로를 "필지를 전부 지웠을 때"라고 썼는데 **틀렸다**(R1 지적 MEDIUM):
  //     clearParcels→syncParcelsToStores([]) 는 parcels/parcelCount 만 비우고 address 는 의도적으로
  //     보존하므로 hasTarget 이 계속 참이다. 실재하는 경로는 연결 해제 쪽이고, 테스트도 그쪽을 잠갔다.
  useEffect(() => {
    if (!defaultCollapsed) return; // 펼침이 기본인 호출측(/ko·/precheck)은 무관 — 무회귀
    // ★호출측 주입이 있으면 그것이 이 화면의 "대상" 정의다(없으면 셸 기본 판정 — 무회귀).
    const hasTarget =
      hasTargetProp ??
      (selectedParcels.length > 0 ||
        !!storeSiteAnalysis?.address ||
        !!storeSiteAnalysis?.parcels?.length);
    if (hasTarget) return; // 대상 있음 — 접힌 요약이 의미를 가지므로 그대로 둔다
    if (!projectId) {
      setIsShellExpanded(true); // 미연결 + 대상 없음 — 기다릴 것이 없다(즉시 확정)
      return;
    }
    // 연결됐는데 대상이 없다 — 복원이 오는 중일 수도, 원래 없을 수도 있다. 기다려 보고 판정한다.
    // 유예 안에 대상이 도착하면 이 이펙트가 재실행되고 아래 cleanup 이 타이머를 취소한다.
    const timer = setTimeout(() => setIsShellExpanded(true), TARGET_RESTORE_GRACE_MS);
    return () => clearTimeout(timer);
  }, [defaultCollapsed, hasTargetProp, selectedParcels.length, storeSiteAnalysis, projectId]);
  // ── WS-C 필지 상세 패널 — 지도 폴리곤/카드 클릭 → 통합 정보(개요·공시지가·노후도)와
  //    산출물 원클릭 퍼널. 단일 팝오버 원칙: 레이어 설정 패널과 동시 표출 금지(상호 배타).
  const [detailFeature, setDetailFeature] = useState<SatongMapFeature | null>(null);
  // ★W1 지배 제약 캐시(state 아님 — ref + sessionStorage). 경계 응답에서만 오는 값이라 좌측
  //   카드 클릭 경로가 쓰는 selectedMapFeatures(선택 SSOT 유래)엔 없다. state로 두면 매 경계
  //   응답마다 새 객체 identity가 selectedMapFeatures → SatongMultiMap props로 번져 경계 재조회
  //   루프를 만든다(identity churn — 이 저장소에서 이미 겪은 결함). ref는 렌더를 유발하지 않는다.
  //   ★R1 MEDIUM-3: ref만 쓰면 소프트 내비(산출물 페이지 왕복)로 셸이 재마운트될 때 캐시가
  //     비고, selectionBoundaryReady(geometry+연식 보유)가 true라 경계 재조회도 스킵돼 배너가
  //     **무음 소실**됐다. 그래서 표시 캐시를 sessionStorage에 함께 둔다 — 선택 SSOT(필지 데이터)가
  //     아니라 **뷰 캐시**라서 프로젝트 스냅샷·산출물 페이로드를 오염시키지 않는다.
  const dominantConstraintByKeyRef = useRef<Map<string, DominantConstraint | null>>(
    readDominantConstraintCache<DominantConstraint>(),
  );
  const rememberDominantConstraints = useCallback(
    (entries: Array<[string, DominantConstraint | null]>) => {
      if (!entries.length) return;
      for (const [key, value] of entries) dominantConstraintByKeyRef.current.set(key, value);
      writeDominantConstraintCache<DominantConstraint>(dominantConstraintByKeyRef.current);
    },
    [],
  );
  const resolveDominantConstraint = useCallback(
    (feature: SatongMapFeature): DominantConstraint | null =>
      feature.dominantConstraint ??
      dominantConstraintByKeyRef.current.get(dominantConstraintKey(feature)) ??
      null,
    [],
  );
  // ── W2 필지 경사도(온디맨드) ────────────────────────────────────────────────
  //  표고 원천(OpenTopoData)이 **1 req/s 공개 제한 + 서버 캐시 없음**이라 필지를 열 때마다
  //  자동 조회하면 사용자가 빠르게 훑는 순간 그 제한을 넘긴다(전역 리미터 없음). 그래서
  //  ①명시적 요청(버튼) ②세션 뷰 캐시로 재조회 제거 ③인플라이트 1건 제한으로 묶는다.
  // 상세 대상의 최신 스냅샷 — 비동기 응답의 스테일 판정에 쓴다(렌더 중 쓰기 금지 → effect에서 갱신).
  const detailFeatureRef = useRef<SatongMapFeature | null>(null);
  const parcelSlopeByKeyRef = useRef<Map<string, TerrainResult | null>>(
    readSatongViewCache<TerrainResult>(SATONG_PARCEL_SLOPE_KEY),
  );
  const [slopeStatus, setSlopeStatus] = useState<ParcelSlopeStatus>("idle");
  const [slopeResult, setSlopeResult] = useState<TerrainResult | null>(null);
  const [slopeError, setSlopeError] = useState<string | null>(null);
  // ★진행 중인 **필지 키**를 담는다(단순 boolean 금지) — boolean이면 A 조회 중 B로 갔다가
  //   A로 복귀할 때 캐시에 값이 없어 idle로 재설정되고, 다시 뜬 버튼을 눌러도 잠금이 걸려
  //   **아무 반응 없는 죽은 버튼**이 된다(R1 MEDIUM). 키를 알면 로딩 상태를 복원할 수 있다.
  const slopeInFlightKeyRef = useRef<string | null>(null);
  // 표시용 busy — 동기 가드는 위 ref가 담당하고(렌더 무관), 이 state는 "다른 필지 조회 중"
  //   고지에만 쓴다. 버튼은 계속 눌 수 있게 남긴다(가드 자체를 테스트가 관통해야 하므로).
  const [slopeBusy, setSlopeBusy] = useState(false);

  /** 상세 대상이 바뀔 때 경사도 표시를 그 필지 기준으로 재설정(캐시 적중이면 즉시 표시). */
  const syncSlopeForFeature = useCallback((feature: SatongMapFeature | null) => {
    if (!feature) {
      setSlopeStatus("idle");
      setSlopeResult(null);
      setSlopeError(null);
      return;
    }
    const key = dominantConstraintKey(feature);
    const cached = parcelSlopeByKeyRef.current.get(key);
    if (cached) {
      setSlopeStatus("done");
      setSlopeResult(cached);
      setSlopeError(null);
    } else if (slopeInFlightKeyRef.current === key) {
      // ★그 필지의 조회가 아직 진행 중이면 로딩을 복원한다 — idle로 두면 "조회" 버튼이 다시
      //   뜨는데 잠금 때문에 눌러도 무반응이라 사용자에겐 고장으로 보인다(R1 MEDIUM).
      setSlopeStatus("loading");
      setSlopeResult(null);
      setSlopeError(null);
    } else {
      setSlopeStatus("idle");
      setSlopeResult(null);
      setSlopeError(null);
    }
  }, []);

  const requestParcelSlope = useCallback(async () => {
    const feature = detailFeatureRef.current;
    if (!feature) return;
    if (slopeInFlightKeyRef.current !== null) return; // 인플라이트 1건 — 연타·전역 폭주 차단(1req/s)
    const key = dominantConstraintKey(feature);
    const cached = parcelSlopeByKeyRef.current.get(key);
    if (cached) {
      setSlopeStatus("done");
      setSlopeResult(cached);
      return;
    }
    if (!feature.pnu && !feature.address) {
      setSlopeStatus("error");
      setSlopeError("PNU·주소가 없어 표고를 조회할 수 없습니다.");
      return;
    }
    slopeInFlightKeyRef.current = key;
    setSlopeBusy(true);
    setSlopeStatus("loading");
    setSlopeError(null);
    try {
      const res = await apiClient.post<TerrainResult>("/terrain/analyze", {
        body: { pnu: feature.pnu || null, address: feature.address || null },
      });
      const failed = !res || res.ok === false;
      // ★실패(ok:false)는 **캐시하지 않는다**(R1 HIGH). 캐시하면 ①"다시 조회"가 캐시 히트로
      //   끝나 재요청이 아예 안 나가고 ②slope 없는 객체가 status="done"으로 들어가 실제 사유
      //   (주소/PNU 미확인 등) 대신 "표고 표본 부족"이라는 **엉뚱한 문구**가 표시된다.
      //   OpenTopoData 일시 장애·주소 미해석은 백엔드가 정상적으로 내는 실패 모드다.
      if (!failed) {
        // ★스테일 가드: 조회 중 사용자가 다른 필지를 열었어도 결과는 캐시에 넣어 다시 열 때
        //   즉시 표시되게 한다(표시만 그 필지 기준으로 건너뛴다).
        //   ★화면이 쓰는 필드만 담는다 — cross_section.points(31점)·earthwork는 렌더에 쓰이지
        //   않는데 sessionStorage 용량만 먹는다(R1 LOW).
        const slim: TerrainResult = {
          ok: true,
          slope: res.slope,
          confidence: res.confidence,
          note: res.note,
          resolution_m: res.resolution_m,
        };
        parcelSlopeByKeyRef.current.set(key, slim);
        writeSatongViewCache<TerrainResult>(SATONG_PARCEL_SLOPE_KEY, parcelSlopeByKeyRef.current);
      }
      const current = detailFeatureRef.current;
      if (!current || dominantConstraintKey(current) !== key) return;
      if (failed) {
        setSlopeStatus("error");
        setSlopeError(res?.message || "표고 데이터를 확인하지 못했습니다.");
        return;
      }
      setSlopeStatus("done");
      setSlopeResult(res);
    } catch (e) {
      const current = detailFeatureRef.current;
      if (current && dominantConstraintKey(current) === key) {
        setSlopeStatus("error");
        setSlopeError(e instanceof ApiClientError ? e.message : "네트워크 오류");
      }
    } finally {
      slopeInFlightKeyRef.current = null;
      setSlopeBusy(false);
    }
  }, []);

  // ── W3 배치 미리보기(온디맨드) ──────────────────────────────────────────────
  //  경사도(W2)와 달리 외부 레이트리밋은 없다(서버 순수 CPU·shapely). 그래도 무거운 기하
  //  연산이고 사용자가 필지를 훑을 때마다 돌 이유가 없어 **명시적 요청**으로 둔다
  //  ("선택형 분석 기본" 원칙). 가드 3종은 W2와 동일 계약으로 맞춘다(패턴 발산 방지).
  const parcelLayoutByKeyRef = useRef<Map<string, SiteLayoutResult | null>>(
    readSatongViewCache<SiteLayoutResult>(SATONG_SITE_LAYOUT_KEY),
  );
  const [layoutStatus, setLayoutStatus] = useState<ParcelLayoutStatus>("idle");
  const [layoutResult, setLayoutResult] = useState<SiteLayoutResult | null>(null);
  const [layoutError, setLayoutError] = useState<string | null>(null);
  const [layoutOptionKey, setLayoutOptionKey] = useState<string | null>(null);
  const layoutInFlightKeyRef = useRef<string | null>(null);
  const [layoutBusy, setLayoutBusy] = useState(false);

  const syncLayoutForFeature = useCallback((feature: SatongMapFeature | null) => {
    if (!feature) {
      setLayoutStatus("idle");
      setLayoutResult(null);
      setLayoutError(null);
      setLayoutOptionKey(null);
      return;
    }
    const key = dominantConstraintKey(feature);
    const cached = parcelLayoutByKeyRef.current.get(key);
    if (cached) {
      setLayoutStatus("done");
      setLayoutResult(cached);
      setLayoutError(null);
      // 대안 선택은 필지가 바뀌면 초기화 — 남의 대안 키가 남으면 best로 폴백돼 오도된다.
      setLayoutOptionKey(null);
    } else if (layoutInFlightKeyRef.current === key) {
      setLayoutStatus("loading");
      setLayoutResult(null);
      setLayoutError(null);
      setLayoutOptionKey(null);
    } else {
      setLayoutStatus("idle");
      setLayoutResult(null);
      setLayoutError(null);
      setLayoutOptionKey(null);
    }
  }, []);

  /**
   * ★W4 — 고른 배치안을 설계 스튜디오로 인계한다.
   *
   * 저장·이동을 **여기(셸)에서** 한다: 표시 전용 섹션이 sessionStorage와 라우팅을 만지면
   * 같은 로직이 소비처마다 흩어진다(W2·W3에서 세운 계약과 동일).
   * 필지 식별자를 함께 실어야 수신측이 **다른 필지의 선택을 조용히 적용하는 일**을 막는다.
   */
  const handleSeedDesign = useCallback(
    (option: SiteLayoutOption) => {
      const feature = detailFeatureRef.current;
      const handoff = buildMassSeedHandoff({
        pnu: feature?.pnu ?? null,
        address: feature?.address ?? null,
        kind: option.kind,
        angleDeg: option.angle_deg,
        floors: option.floors,
        // ★R1 HIGH-3: 이 층수가 산정된 부지 면적을 함께 싣는다(다필지 합산 부지에 단일필지
        //   기준 층수가 조용히 적용되던 결함 봉합 — 수신측이 면적으로 대조한다).
        //   ★출처는 **배치가 실제로 산정된 면적** = `land_area_sqm`이다(서버가 클라이언트
        //   입력 지적면적을 우선 사용하고, 없을 때만 폴리곤으로 폴백해 되돌려준다).
        //   ★R3 HIGH 봉합 — 여기 `parcel_area_sqm`을 쓰면 **폴리곤 기하 근사**가 실린다.
        //   수신측이 대조하는 값은 지적면적이므로 **서로 다른 물리량을 2%로 비교**하게 되고,
        //   같은 서비스가 두 값의 20% 괴리까지 정상으로 취급하므로(괴리 시에만 note 고지)
        //   같은 필지가 "다른 부지"로 판정돼 **사실이 아닌 배너**가 뜬다 — 이 PR이 없애려는
        //   바로 그 결함 클래스다.
        areaSqm: layoutResult?.land_area_sqm ?? feature?.areaSqm ?? null,
        now: Date.now(),
      });
      // 층수가 없으면 넘길 게 없다 — 빈 인계를 남겨 수신측이 헛돌게 하지 않는다.
      if (!handoff) return;
      writeMassSeedHandoff(handoff);
      router.push(`/${locale}/design-studio`);
    },
    [layoutResult, locale, router],
  );

  const requestParcelLayout = useCallback(async () => {
    const feature = detailFeatureRef.current;
    if (!feature) return;
    if (layoutInFlightKeyRef.current !== null) return; // 인플라이트 1건(전역)
    const key = dominantConstraintKey(feature);
    const cached = parcelLayoutByKeyRef.current.get(key);
    if (cached) {
      setLayoutStatus("done");
      setLayoutResult(cached);
      return;
    }
    // ★기하가 없으면 서버가 ok:false를 줄 뿐이라 헛호출이 된다 — 사유를 먼저 밝힌다.
    if (!feature.geometry && !feature.pnu) {
      setLayoutStatus("error");
      setLayoutError("대지 경계(폴리곤)·PNU가 없어 배치를 산출할 수 없습니다.");
      return;
    }
    layoutInFlightKeyRef.current = key;
    setLayoutBusy(true);
    setLayoutStatus("loading");
    setLayoutError(null);
    try {
      const res = await apiClient.post<SiteLayoutResult>("/analysis/site-layout", {
        body: {
          // 지도가 이미 가진 기하를 그대로 넘긴다(서버 재조회 회피). 없으면 pnu로 서버가 조회.
          parcel_geojson: (feature.geometry as Record<string, unknown> | null) ?? null,
          pnu: feature.pnu || null,
          zone_type: feature.zoneType || "",
          bcr_pct: feature.effectiveBcrPct ?? null,
          far_pct: feature.effectiveFarPct ?? null,
          land_area_sqm: feature.areaSqm ?? null,
          priority: "balanced",
        },
      });
      // ★ok:false는 캐시하지 않는다 — 재조회를 막고 사유를 둔갑시킨다(W2 R1 HIGH 교훈).
      //   단 ok:true면 캐시(무거운 기하 재계산 회피).
      let slim: SiteLayoutResult | null = null;
      if (res && res.ok) {
        // ★캐시 슬림(R1 MEDIUM): 화면·지도가 읽지 않는 필드는 담지 않는다. 가장 큰
        //   parcel_geojson은 지도가 이미 자기 필지 폴리곤을 그리므로 불필요하고, guidance·
        //   용도지역·면적 등 메타도 이 패널이 쓰지 않는다.
        //   ★단 **options는 모든 대안의 buildings_geojson을 그대로 유지**한다 — W2(경사도)가
        //   "렌더에 안 쓰이는 필드"를 잘라낸 것과 달리, 여기서는 캐시 히트 후에도 사용자가
        //   대안을 토글할 수 있어야 하고 그 순간 각 대안의 기하가 필요하다. 잘라내면 토글이
        //   빈 오버레이가 되거나 재조회를 유발한다(같은 인프라를 쓰지만 결정이 다른 이유).
        slim = {
          ok: true,
          honest_notes: res.honest_notes,
          buildable_geojson: res.buildable_geojson,
          buildable_area_sqm: res.buildable_area_sqm,
          // ★W4: 인계 대조 면적의 정본 — 배치가 **실제로 산정된** 부지 면적(지적 우선).
          //   슬림에서 빠져 있으면 CTA 게이트가 항상 거짓이 되어 인계 버튼이 영영 안 뜬다.
          land_area_sqm: res.land_area_sqm,
          setback_m: res.setback_m,
          // ★W3-b: 정북 밴드 판정은 서버 응답에만 있다. 슬림에서 빠지면 캐시 히트 후
          //   `applies`가 undefined가 되어 **밴드가 영영 안 그려진다**(W4에서 같은 클래스의
          //   결함을 겪었다 — 새로 소비하는 필드는 화이트리스트를 반드시 확인한다).
          north_light: res.north_light,
          options: res.options,
          best: res.best,
        };
        parcelLayoutByKeyRef.current.set(key, slim);
        writeSatongViewCache<SiteLayoutResult>(
          SATONG_SITE_LAYOUT_KEY, parcelLayoutByKeyRef.current,
        );
      }
      const current = detailFeatureRef.current;
      if (!current || dominantConstraintKey(current) !== key) return;
      if (!res) {
        setLayoutStatus("error");
        setLayoutError("배치를 산출하지 못했습니다.");
        return;
      }
      // ok:false도 "done"으로 두고 서버 honest_notes를 화면이 그대로 고지한다
      //   (가짜 배치 대신 사유 표기 — 컴포넌트의 unavailable 분기).
      setLayoutStatus("done");
      // ★상태에도 캐시와 **같은 shape**(성공 시 slim)를 넣는다 — 신규 응답은 전체, 캐시 히트는
      //   slim이면 "처음엔 되는데 재방문하면 조용히 undefined"인 함정이 남는다(R2 지적).
      setLayoutResult(res.ok && slim ? slim : res);
      setLayoutOptionKey(null);
    } catch (e) {
      const current = detailFeatureRef.current;
      if (current && dominantConstraintKey(current) === key) {
        setLayoutStatus("error");
        setLayoutError(e instanceof ApiClientError ? e.message : "네트워크 오류");
      }
    } finally {
      layoutInFlightKeyRef.current = null;
      setLayoutBusy(false);
    }
  }, []);

  const openFeatureDetail = useCallback((feature: SatongMapFeature) => {
    // ★단일 팝오버 불변식 — right-20 top-20 z-430 좌표를 공유하는 3패널(필지상세·레이어·
    //   베이스맵)은 동시에 뜰 수 없다. 봉합은 '생산 근원'인 이 함수에서 한다 — 호출부
    //   (좌측 필지 카드·지도 피처 클릭)마다 닫기를 흩뿌리면 새 호출부가 생길 때 또 샌다.
    setBasemapOpen(false);
    // ★같은 이유로 지배 제약 합류도 여기서 한다 — 두 호출부(카드/지도)가 각자 채우면
    //   한쪽만 고쳐지는 발산이 생긴다. 피처가 이미 값을 갖고 있으면(지도 경계 유래) 그것이
    //   우선, 없으면 경계 응답 캐시에서 같은 필지 키로 찾는다.
    const dominantConstraint = resolveDominantConstraint(feature);
    setDetailFeature(dominantConstraint ? { ...feature, dominantConstraint } : feature);
    setActiveLayerId(null);
  }, [resolveDominantConstraint]);
  // ★경사도 표시를 상세 대상에 맞추는 배선은 **여기 한 곳**이다 — setDetailFeature 호출부가
  //   5곳(열기·유령패널 닫기·초기화·경계합류·삭제)이라 각자 동기화하면 새 호출부가 생길 때 또
  //   샌다(W1 openFeatureDetail 교훈과 동일). detailFeature를 관찰해 일괄 처리한다.
  useEffect(() => {
    detailFeatureRef.current = detailFeature;
  }, [detailFeature]);
  // ★키(필지 동일성) 기준으로만 재설정한다 — 경계 합류로 detailFeature **객체 identity**가
  //   바뀔 때(같은 필지) 로딩 중이던 경사도 상태가 초기화되지 않게.
  const detailParcelKey = detailFeature ? dominantConstraintKey(detailFeature) : null;
  useEffect(() => {
    // detailFeatureRef는 ref라 deps가 아니다 — 트리거는 detailParcelKey(필지 동일성) 뿐.
    syncSlopeForFeature(detailFeatureRef.current);
    syncLayoutForFeature(detailFeatureRef.current);
  }, [detailParcelKey, syncSlopeForFeature, syncLayoutForFeature]);
  // I5: 선택 필지 GeoJSON 내보내기 결과 고지(제외 건수 정직 표기).
  const [exportNote, setExportNote] = useState("");
  // ★R1(stale 고지): 선택이 바뀌면(추가·삭제·초기화·프로젝트 전환) 지난 내보내기 고지를
  //   비운다 — "3필지 내보냄"이 4필지 상태에 잔존하는 정직-고지 역위반 방지.
  useEffect(() => {
    setExportNote("");
  }, [selectedParcels]);
  // ★WP-M2: "초기화"(clearParcels)가 지도 내부 staged·녹색 폴리곤도 청소하도록 보내는 신호(nonce).
  //   증가할 때마다 SatongMultiMap이 handleClearAll을 실행한다(종전엔 목록만 비고 지도엔 잔존).
  const [clearNonce, setClearNonce] = useState(0);
  // ★R2(MEDIUM): 지도에 찍었지만 아직 [완료]를 안 눌러 selectedParcels엔 없는 staged(녹색) 개수.
  //   SatongMultiMap 내부 상태라 Shell은 원래 볼 수 없었다 — onStagedCountChange로 역전파해,
  //   "확정 선택은 0건이지만 staged는 있다"는 상황에서도 연결전환 고지가 무음이 되지 않게 한다.
  const [stagedCount, setStagedCount] = useState(0);
  // ★WP-M4: 레일(레이어 아이콘 세로바) 클릭 고정 토글 — hover 없이 터치로도 전개 가능하게.
  // ★UX 트랙 C1(사용자 지적): 기본값이 false(접힘)라 h-28 클리핑에 걸려 14개 레이어 중 2개만
  //   보였다(터치 기기에서 hover 전개 자체가 불가 — 발견성 후퇴). 기본을 펼침(true)으로 바꿔
  //   최초 진입부터 전 레이어가 보이게 한다. 사용자가 명시적으로 접으면(false) 그 상태는
  //   기존 핀 토글 로직 그대로 존중한다(접힘 상태의 시각 처리는 렌더 className에서 보정).
  const [railPinned, setRailPinned] = useState(true);
  // 베이스맵 팝오버 열림 — 레이어 팝오버(activeLayerId)와 상호배타(같은 좌표를 쓰므로).
  const [basemapOpen, setBasemapOpen] = useState(false);
  // 새 프로젝트 생성 인플라이트 표시(버튼 disabled용) — 실제 중복차단은 creatingProjectRef(F4).
  const [creatingProject, setCreatingProject] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const basemapPopoverRef = useRef<HTMLDivElement | null>(null);
  const creatingProjectRef = useRef(false);

  // ── PR#221 프로젝트 전환/하이드레이션 상태 refs(컴포넌트 상단으로 이동 — F1: 아래 콜백들이
  //   detachProjectCarryingSelection 등에서 참조할 수 있도록 다른 ref 선언 옆에 둔다. 로직은
  //   기존과 동일 — 하이드레이션 이펙트 본문은 원래 위치에 그대로 있다) ──
  const hydratedRef = useRef(false);
  // 직전 projectId(undefined=첫 실행 센티널)와, 전환 후 스토어 시드 허용 여부.
  const prevProjectIdRef = useRef<string | null | undefined>(undefined);
  const projectSeedArmedRef = useRef(false);
  // 마지막으로 시드한 내용의 지문 — siteAnalysis 객체 참조만 바뀌고 내용이 같은 갱신
  //   (updatedAt 등 무관 필드 변경)에 재시드·지도 이동이 반복되지 않게 한다. ""=전환 직후.
  const lastSeedKeyRef = useRef("");
  // 전환 후 지도 이동(포커스)을 아직 못 했는지 — 좌표가 보강으로 늦게 와도 딱 1회만 이동.
  const projectFocusPendingRef = useRef(false);
  // ★R2(HIGH): 현재 selectedParcels의 소유권 — 프로젝트에서 상속(시드)된 값이면 그 projectId,
  //   사용자가 직접 편집(추가·삭제)했으면 null. 드롭다운으로 연결 대상을 바꿀 때 이 값으로
  //   "지금 해제하려는 프로젝트가 남긴 선택인지"를 판별해 그 경우만 정리한다 — addParcels의
  //   교차오염 가드(:1179)가 사용자 선택을 항상 보존하는 것과 대칭. 부분 소유(시드+사용자 추가
  //   혼재)는 사용자 편집이 한 번이라도 있으면 null(사용자 소유)로 굳는다(addParcels/removeParcel
  //   이 무조건 null로 설정 — 데이터 손실보다 잔존이 덜 위험하다는 보존 우선 원칙, 잔존분은
  //   사용자가 명시적으로 지울 수 있다).
  const selectionOwnerProjectIdRef = useRef<string | null>(null);

  // ★R2b(HIGH): sessionStorage write 통로를 이 한 곳으로 강제한다 — 소유권을 매 호출부가
  //   각자 실어야 한다면 한 곳이라도 빠뜨리는 순간 재발한다(실제로 세션 미러 경로가 그렇게
  //   샜다: 소유권 ref는 컴포넌트 인스턴스에만 있어 재마운트를 못 넘기고, 산출물로 갔다가
  //   소프트 내비로 돌아오는 흔한 재진입에서 사용자 소유로 영구 오분류됐다 — PROBE_P3).
  //   selectionOwnerProjectIdRef.current를 항상 함께 기록해 재마운트를 넘어 소유권 판별이
  //   살아남게 한다(구조적으로 누락 불가 — 모든 호출부가 이 콜백 하나만 거친다).
  const saveSelectionForOutputs = useCallback((parcels: SatongParcel[]) => {
    writeSatongMapSelection(parcels, selectionOwnerProjectIdRef.current);
  }, []);

  // 의도적 프로젝트 해제(선택 유지): 전환 이펙트가 P→null을 '프로젝트 전환'으로 오인해
  //   방금 담은 선택·sessionStorage를 지우지 않도록, 이펙트가 볼 직전값을 미리 null로 맞춘다.
  //   (자동시드도 함께 disarm — 해제 후 스토어 갱신이 선택을 덮지 않게.)
  const detachProjectCarryingSelection = useCallback(() => {
    prevProjectIdRef.current = null;
    hydratedRef.current = true;
    projectSeedArmedRef.current = false;
    clearProject();
  }, [clearProject]);

  const selectedTotalArea = useMemo(
    () => selectedParcels.reduce((sum, parcel) => sum + (parcel.areaSqm ?? 0), 0),
    [selectedParcels],
  );

  const activeLayer = useMemo(
    () => LAYERS.find((layer) => layer.id === activeLayerId) ?? null,
    [activeLayerId],
  );

  const activeLayers = useMemo(
    () => LAYERS.filter((layer) => enabledLayers.has(layer.id)),
    [enabledLayers],
  );


  const handleSelectProject = useCallback((id: string) => {
    if (!id) return;
    const p = projects.find((x) => x.id === id);
    if (!p) return;
    setProject(p.id, p.name, p.status, p.address || undefined);
    void restoreSnapshot(p.id);
  }, [projects, setProject]);

  // handleConnectTargetChange 정의는 아래(clearParcels 정의 직후)로 이동했다 — 레인F P0-1:
  //   전환 시 선택 필지까지 정리하려면 정본 clearParcels()를 호출해야 하는데, clearParcels는
  //   이 지점보다 한참 뒤에 정의된다(같은 렌더 내 TDZ). 재배치로 정의 순서를 맞췄다(로직은
  //   그 위치에서 그대로 확인 가능 — 기능 이동 없음).

  const selectedMapFeatures = useMemo<SatongMapFeature[]>(
    () =>
      selectedParcels.map((parcel) => ({
        id: parcel.id,
        address: parcel.address,
        pnu: parcel.pnu,
        lat: parcel.lat,
        lon: parcel.lon,
        areaSqm: parcel.areaSqm,
        zoneType: parcel.zoneType,
        jimok: parcel.jimok,
        officialPricePerSqm: parcel.officialPricePerSqm,
        builtYear: parcel.builtYear,
        buildingAgeYears: parcel.buildingAgeYears,
        ageStatus: parcel.ageStatus,
        effectiveFarPct: parcel.effectiveFarPct,
        effectiveBcrPct: parcel.effectiveBcrPct,
        // ★실효값과 **함께** 실어야 화면이 "왜 그 값인지"를 말할 수 있다 — 여기를 빠뜨리면
        //   타입·병합은 맞는데 팝오버에만 값이 안 와서 소비처가 조용히 0 이 된다(RED 로 적발).
        legalFarPct: parcel.legalFarPct,
        farBasis: parcel.farBasis,
        currentFarPct: parcel.currentFarPct,
        geometry: parcel.geometry,
        source: parcel.source,
      })),
    [selectedParcels],
  );

  // W3 파생값 — 선택 대안과 지도 오버레이. 기하는 서버 산정분만 통과시킨다(가짜 배치 금지).
  const layoutSelectedOption = useMemo(
    () => resolveSelectedOption(layoutResult, layoutOptionKey),
    [layoutResult, layoutOptionKey],
  );
  const layoutOverlay = useMemo(
    () => buildLayoutOverlay(layoutResult, layoutOptionKey),
    [layoutResult, layoutOptionKey],
  );

  const mapLayerState = useMemo<SatongMapLayerState>(
    // ★스토어 배열을 **직접** 쓴다. 종전 `Array.from(enabledLayers)` 는 memo 가 돌 때마다
    //   **새 배열**을 만들었다 — 이 값이 그대로 `layerState` 로 내려간다.
    () => ({ enabledLayerIds, controlsByLayer: layerControls }),
    [enabledLayerIds, layerControls],
  );

  // I5+V3: 선택 필지 → GeoJSON/KML 파일 다운로드(순수 직렬화는 satong-export — 테스트 고정).
  //   포맷별 중복을 공용 실행기로 일원화(버그수정 정책 — 공용화).
  const exportSelection = useCallback(
    (format: "geojson" | "kml") => {
      const built =
        format === "kml" ? buildSelectionKml(selectedMapFeatures) : buildSelectionGeoJson(selectedMapFeatures);
      if (built.included === 0) {
        // ★UX 트랙 C3 결정: 이 경고는 인라인 유지(토스트로 옮기지 않음) — ①행동 유도문(지도에서
        //   필지를 선택한 뒤 다시 시도)이라 사용자가 조치하는 동안 계속 보여야 하고, ②계약 테스트
        //   (SatongMapShell.detailPanel.test.tsx "I5 내보내기")가 ToastProvider 없이 셸을 단독
        //   렌더한 채 이 문구를 screen.getByText로 고정한다 — 무회귀 우선.
        setExportNote(
          "내보낼 경계(geometry) 보유 필지가 없습니다 — 지도에서 필지를 선택(경계 조회)한 뒤 다시 시도하세요.",
        );
        return;
      }
      setExportNote(""); // 직전 경고가 남아있었다면 정리
      const mime = format === "kml" ? "application/vnd.google-earth.kml+xml" : "application/geo+json";
      const blob = new Blob([built.json], { type: mime });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `satong-parcels-${built.included}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      // R1: click() 직후 동기 revoke는 일부 환경에서 다운로드를 끊을 수 있어 다음 틱으로 지연.
      setTimeout(() => URL.revokeObjectURL(url), 0);
      // ★UX 트랙 C3: 완료 확인은 뒤에 남는 패널이 없는 순수 일시 고지라 토스트가 적합하다.
      //   ToastProvider가 있으면 토스트로, 없으면(계약 테스트 등) 기존 인라인 문구로 폴백한다.
      const doneMessage = `${format === "kml" ? "KML" : "GeoJSON"} ${built.included}필지 내보냄${built.skipped ? ` · 경계 없음 ${built.skipped}필지 제외(정직 고지)` : ""}`;
      if (toast) {
        toast.push({ variant: "success", description: doneMessage });
      } else {
        setExportNote(doneMessage);
      }
    },
    [selectedMapFeatures, toast],
  );

  // ── 실거래·시세 레이어 배선: 레이어 ON + 선택필지 있으면 주변 실거래(nearby-map) 조회 ──
  //   렌더(마커·반경·팝업)는 SatongMultiMap에 완비 — 여기서는 데이터만 주입한다.
  //   실패는 fetch_failed로 정직 전달(지도에 "조회 실패" 노트), 무선택·레이어 OFF는 null(마커 제거).
  const [marketPayload, setMarketPayload] = useState<SatongMarketPayload | null>(null);
  /**
   * 실거래 반경 — `null` 이면 **자동**(1km 로 조회 후 희소하면 백엔드가 넓힌다).
   *
   * ★형제 패리티: `NearbyTransactionsMap` 은 500m/1km/3km 선택을 이미 갖고 있는데
   *   사통맵만 하드코딩이었다(2026-08-21 실측 — 그 비대칭이 "실거래가 안 보인다"의 절반).
   * ★**수동 선택은 자동확대를 끈다.** 사용자가 1km 를 고른 뒤에도 서버가 3km 로 넓히면
   *   그 컨트롤은 거짓말이 된다 — 고른 값이 곧 적용값이어야 한다.
   */
  const [marketRadiusM, setMarketRadiusM] = useState<number | null>(null);
  const marketEnabled = enabledLayers.has("transactions");
  //   ★의존성은 원시값(pnu·address)으로 — 선택목록 참조가 바뀌어도 anchor가 같으면 재조회 안 함
  //     (#178 교훈: 참조 churn이 이펙트 무한/중복 실행을 유발).
  //   anchor = 첫 선택 필지(생성자들이 address를 항상 채우므로 사실상 selectedParcels[0]).
  const marketAnchor = useMemo(
    () => selectedParcels.find((p) => p.pnu || p.address) ?? null,
    [selectedParcels],
  );
  const marketAnchorPnu = marketAnchor?.pnu || "";
  const marketAnchorAddress = marketAnchor?.address || "";
  // ★지도 현재중심(P1) — 선택필지 없을 때 지역레이어(POI·개발계획)의 폴백 앵커. 원시값(lat/lon)만
  //   의존성에 쓴다(#178). SatongMultiMap의 moveend가 반올림·디바운스해 통지하므로 재조회 폭주 없음.
  const [mapCenter, setMapCenter] = useState<{ lat: number; lon: number } | null>(null);
  useEffect(() => {
    if (!marketEnabled || (!marketAnchorPnu && !marketAnchorAddress)) {
      setMarketPayload(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongMarketPayload>("/zoning/nearby-map", {
          body: {
            address: marketAnchorAddress || undefined,
            pnu: marketAnchorPnu || undefined,
            ...marketRadiusRequest(marketRadiusM),
            months: 3,
          },
          useMock: false,
          timeoutMs: 90000,
        });
        if (!cancelled) {
          // 백엔드 소프트 실패(HTTP 200 + {error, center:null})도 fetch_failed로 승격해
          // 지도에 "조회 불가" 노트를 정직 표기(침묵 빈지도 방지 — 리뷰 LOW 반영).
          const soft = res as SatongMarketPayload & { error?: string };
          if (soft.error || !soft.center?.lat) {
            setMarketPayload({
              center: null,
              fetch_failed: true,
              note: soft.error || "주변 실거래 조회 불가(지역코드 미확인)",
            });
          } else {
            setMarketPayload(res);
          }
        }
      } catch {
        if (!cancelled) {
          setMarketPayload({ center: null, fetch_failed: true, note: "주변 실거래 조회 실패" });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [marketEnabled, marketAnchorPnu, marketAnchorAddress, marketRadiusM]);

  // ── 교통·편의 POI 레이어 배선: 레이어 ON + 선택필지 있으면 주변 POI(/site-score/poi-infra) 조회 ──
  //   렌더(카테고리 색상 마커·팝업)는 SatongMultiMap에 구현 — 여기서는 데이터만 주입.
  //   실패/키미설정은 available:false로 정직 전달(지도 노트), OFF/무선택은 null(마커 제거).
  //   의존성은 원시값(lat·lon·address) — 참조 churn 재조회 방지(#178 교훈, 실거래와 동일 패턴).
  const [poiPayload, setPoiPayload] = useState<SatongPoiPayload | null>(null);
  const poiEnabled = enabledLayers.has("poi");
  // ★좌표 앵커 공용화(resolveSelectionAnchor — satong-map-layers): 종전 '첫 필지의 lat/lon'만
  //   보던 단선을 ①좌표 보유 첫 필지 ②경계(geometry) 대표점 ③(무선택시) 지도중심 순으로 해소.
  //   좌표 없는 선택(엑셀 PNU행·프로젝트 시드)도 경계보강 도착 즉시 앵커가 살아나 분양·경매·
  //   개발계획 조회가 자동 재개된다. 선택이 있는데 좌표·경계가 전무하면 null 유지(엉뚱한
  //   지도중심 조회 역전 차단 — 기존 계약 보존, 리뷰 LOW). 이펙트 의존성은 원시값만(#178).
  const selectionAnchor = useMemo(
    () => resolveSelectionAnchor(selectedParcels, mapCenter),
    [selectedParcels, mapCenter],
  );
  const anchorLat = selectionAnchor?.lat ?? null;
  const anchorLon = selectionAnchor?.lon ?? null;
  // 앵커 필지의 주소 — 좌표와 같은 필지 기준. 다필지에서 첫 필지(주소)와 앵커(좌표)가 서로
  //   다른 필지를 가리키던 조합 불일치 해소(리뷰 LOW): POI 보조주소·경매 region이 앵커 필지를 따른다.
  const anchorAddress = selectionAnchor?.address ?? "";
  // 선택은 있는데 좌표·경계가 아직 없음(경계보강 대기) — 좌표 레이어의 정직 노트용.
  const anchorPending = selectedParcels.length > 0 && selectionAnchor == null;
  // 경계보강 진행상태(SatongMultiMap→onBoundaryStatusChange) — 영구 실패면 "확인 중" 노트를
  //   "확인 실패"로 정직 강등한다(진행 중인 척 위장 금지, 리뷰 LOW).
  const [boundaryFailed, setBoundaryFailed] = useState(false);
  const handleBoundaryStatusChange = useCallback(
    (status: "idle" | "loading" | "ready" | "error") => setBoundaryFailed(status === "error"),
    [],
  );
  // 좌표 레이어(개발계획·분양·경매) 공용 대기 노트 — 상태 3분류를 한 곳에서 만든다.
  const anchorWaitNote = useCallback(
    (label: string) =>
      anchorPending
        ? boundaryFailed
          ? `${label}: 필지 좌표 확인 실패(경계 조회 불가)`
          : `${label}: 선택 필지 좌표 확인 중(경계 보강 후 자동 조회)`
        : `${label}: 지도를 이동하면 지도 중심 기준으로 조회합니다`,
    [anchorPending, boundaryFailed],
  );
  useEffect(() => {
    if (!poiEnabled || (anchorLat == null && !marketAnchorAddress)) {
      setPoiPayload(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongPoiPayload>("/site-score/poi-infra", {
          body: {
            lat: anchorLat ?? undefined,
            lon: anchorLon ?? undefined,
            // 좌표가 있으면 앵커 필지의 주소(좌표·주소 동일 출처), 좌표 전무 시에만 첫 필지 주소 폴백.
            address: (anchorLat != null ? anchorAddress : marketAnchorAddress) || undefined,
            radius_m: 800,
          },
          useMock: false,
          timeoutMs: 60000,
        });
        if (!cancelled) setPoiPayload(res);
      } catch {
        if (!cancelled) setPoiPayload({ available: false, reason: "POI 조회 실패" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [poiEnabled, anchorLat, anchorLon, anchorAddress, marketAnchorAddress]);

  // ── 개발계획 레이어 배선: 레이어 ON + 앵커 좌표 있으면 주변 도시계획시설 조회 ──
  //   /zoning/development-facilities 는 lat/lon 필수(주소 지오코딩 없음).
  //   ★앵커 미해소 시에도 침묵하지 않는다 — 빈 facilities + 대기/안내 note 정직 전달(무날조).
  const [developmentPayload, setDevelopmentPayload] = useState<SatongDevelopmentPayload | null>(null);
  const developmentEnabled = enabledLayers.has("development");
  useEffect(() => {
    if (!developmentEnabled) {
      setDevelopmentPayload(null);
      return;
    }
    if (anchorLat == null || anchorLon == null) {
      // 레이어는 켜졌는데 조회 기준 좌표가 아직 없음 — 종전엔 payload null(노트조차 없는
      // 침묵 빈지도, 정직원칙 역위반)이었다. 상태를 구분해 지도에 노트로 알린다.
      setDevelopmentPayload({ facilities: [], note: anchorWaitNote("개발계획") });
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongDevelopmentPayload>("/zoning/development-facilities", {
          // kinds:"all" — 지도 레이어는 전체 도시계획시설(도로·광장·학교·유통 등) 표시.
          //   (기본 "rail"은 입지 신호용 철도 전용 — 기존 소비처 동작 보존)
          body: { lat: anchorLat, lon: anchorLon, radius_m: 1000, kinds: "all" },
          useMock: false,
          timeoutMs: 60000,
        });
        if (!cancelled) setDevelopmentPayload(res);
      } catch {
        if (!cancelled) {
          setDevelopmentPayload({ facilities: [], note: "개발계획(도시계획시설) 조회 실패" });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [developmentEnabled, anchorLat, anchorLon, anchorWaitNote]);

  // ── 분양정보 레이어 배선(실데이터): 레이어 ON + 앵커좌표(또는 주소) → 청약홈(/presale/nearby) ──
  //   렌더(마커·팝업)는 SatongMultiMap의 presaleItems에 완비. 실패/무자료는 [](정직 "분양 무자료").
  //   ★무목업: 종전 가상단지(Math.random) 목업을 실데이터로 대체. 패턴은 실거래·POI와 동일.
  //   ★주소 폴백: 서버(presale.nearby)가 좌표 없이 address만 와도 지오코딩으로 해소하므로,
  //     좌표 미확보 선택(엑셀 PNU행 등)도 주소로 즉시 조회한다(앵커 단선 해소).
  const [presaleItems, setPresaleItems] = useState<SatongPresaleItem[] | null>(null);
  const [presaleNote, setPresaleNote] = useState("");
  const presaleEnabled = enabledLayers.has("presale");
  useEffect(() => {
    if (!presaleEnabled) {
      setPresaleItems(null);
      setPresaleNote("");
      return;
    }
    if (anchorLat == null && !marketAnchorAddress) {
      // 좌표도 주소도 없음 — 침묵 대신 상태를 노트로 알린다(정직원칙).
      setPresaleItems(null);
      setPresaleNote(anchorWaitNote("분양"));
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<{ available?: boolean; items?: SatongPresaleItem[] }>(
          "/presale/nearby",
          {
            body: {
              lat: anchorLat ?? undefined,
              lon: anchorLon ?? undefined,
              // 좌표가 없을 때만 주소 전달 — 서버 지오코딩 1회로 해소(좌표 있으면 좌표 우선).
              address: anchorLat == null ? marketAnchorAddress || undefined : undefined,
              radius_m: 3000,
            },
            useMock: false,
            timeoutMs: 30000,
          },
        );
        if (!cancelled) {
          setPresaleItems(
            (res.items ?? []).filter(
              (item) => typeof item.lat === "number" && typeof item.lon === "number",
            ),
          );
          setPresaleNote("");
        }
      } catch {
        if (!cancelled) {
          setPresaleItems([]); // 가짜 생성 금지
          setPresaleNote("분양: 조회 실패"); // 무자료와 실패를 구분(정직원칙)
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [presaleEnabled, anchorLat, anchorLon, anchorWaitNote, marketAnchorAddress]);

  // ── 공·경매 레이어 배선(실데이터): 온비드 검색(/auction/search) → 주소 지오코딩(/auction/geocode)
  //   → 앵커 반경(10km) 필터. 지역(시/도) 우선 검색, 0건이면 전국 폴백. 좌표 미확인 물건은
  //   스킵(가짜 좌표 금지).
  //   ★인증 정직화: /auction/search만 RBAC 게이트(RequirePermission) — 종전엔 비로그인 401이
  //     catch로 삼켜져 "경매 무자료"로 오표기됐고, 전역 세션만료 처리(로그인 리다이렉트)가
  //     발동해 지도에서 튕겨나갔다. ①토큰 없으면 호출 전 게이트(무의미한 401 왕복 차단)
  //     ②호출은 skipSessionExpiry로 리다이렉트 옵트아웃 ③401/403은 무자료가 아니라
  //     "로그인/권한 필요" 노트로 구분 표기.
  const [auctionItems, setAuctionItems] = useState<SatongAuctionItem[] | null>(null);
  const [auctionNote, setAuctionNote] = useState("");
  const auctionEnabled = enabledLayers.has("auction");
  useEffect(() => {
    if (!auctionEnabled) {
      setAuctionItems(null);
      setAuctionNote("");
      return;
    }
    if (anchorLat == null || anchorLon == null) {
      setAuctionItems(null);
      setAuctionNote(anchorWaitNote("경매"));
      return;
    }
    // 토큰 존재는 반응형 신호가 아니다(localStorage 직독) — 이 화면엔 인라인 로그인이 없어
    // 로그인은 항상 /login 라우트 이동→복귀 리마운트로 해소되므로 stale 위험은 이론적(리뷰 MEDIUM 수용).
    // 인라인 로그인 UI가 생기면 인증 스토어 구독으로 교체할 것.
    if (!hasAccessToken()) {
      setAuctionItems(null);
      setAuctionNote("경매: 로그인 후 조회 가능합니다");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        type AuctionSearchItem = {
          id?: number | string;
          address?: string | null;
          status?: string | null;
          appraisal_price?: number | null;
          min_bid_price?: number | null;
          bid_end?: string | null;
        };
        // 앵커 필지 주소의 시/도 토큰을 **원형 그대로** 전달(예: "충청북도") — 저장 축약형("충북")
        // 정규화는 서버 공용 _sido_from_address가 담당(진실원천 1곳, 프론트 재구현 금지 — QA MEDIUM).
        // ★좌표(하버사인 필터)와 같은 앵커 필지의 주소를 쓴다 — 다필지에서 region과 거리필터가
        //   서로 다른 필지 기준이 되던 조합 불일치 해소(리뷰 LOW). 앵커 주소 부재 시 첫 필지 폴백.
        const region = (anchorAddress || marketAnchorAddress).split(" ")[0] || "";
        const fetchPage = (r?: string) =>
          apiClient.get<{ items?: AuctionSearchItem[] }>(
            `/auction/search?page_size=60${r ? `&region=${encodeURIComponent(r)}` : ""}`,
            // skipSessionExpiry: 선택형 지도 레이어가 만료 세션에서 전역 로그인 리다이렉트를
            // 발동하지 않게 옵트아웃 — 401/403은 아래 catch가 정직 노트로 처리한다.
            { useMock: false, timeoutMs: 30000, skipSessionExpiry: true },
          );
        let res = region ? await fetchPage(region) : await fetchPage();
        if (region && !(res.items ?? []).length) res = await fetchPage(); // 지역 0건 → 전국 폴백
        const items = (res.items ?? []).filter((item) => (item.address ?? "").trim());
        if (!items.length) {
          if (!cancelled) setAuctionItems([]);
          return;
        }
        const geo = await apiClient.post<{ located?: { key: string; lat: number; lon: number }[] }>(
          "/auction/geocode",
          {
            body: {
              items: items.slice(0, 60).map((item, index) => ({
                key: String(item.id ?? index),
                address: item.address,
              })),
            },
            useMock: false,
            timeoutMs: 60000,
          },
        );
        const located = new Map((geo.located ?? []).map((l) => [l.key, l]));
        const toRad = (d: number) => (d * Math.PI) / 180;
        const near = items
          .map((item, index): SatongAuctionItem | null => {
            const loc = located.get(String(item.id ?? index));
            if (!loc) return null;
            // 하버사인 거리(m) — 앵커 반경 10km만 채택.
            const dLat = toRad(loc.lat - anchorLat);
            const dLon = toRad(loc.lon - anchorLon);
            const h =
              Math.sin(dLat / 2) ** 2 +
              Math.cos(toRad(anchorLat)) * Math.cos(toRad(loc.lat)) * Math.sin(dLon / 2) ** 2;
            const distanceM = Math.round(2 * 6371000 * Math.asin(Math.sqrt(h)));
            if (distanceM > 10000) return null;
            return {
              address: item.address ?? undefined,
              status: item.status ?? undefined,
              appraisal_price: item.appraisal_price ?? undefined,
              minimum_bid_price: item.min_bid_price ?? undefined,
              bid_date: item.bid_end ?? undefined,
              lat: loc.lat,
              lon: loc.lon,
              distance_m: distanceM,
            };
          })
          .filter((item): item is SatongAuctionItem => item != null)
          .sort((a, b) => (a.distance_m ?? 0) - (b.distance_m ?? 0))
          .slice(0, 30);
        if (!cancelled) {
          setAuctionItems(near);
          setAuctionNote("");
        }
      } catch (err) {
        if (cancelled) return;
        // 인증/권한 실패는 '무자료'가 아니다 — 상태를 구분해 정직 표기.
        if (err instanceof ApiClientError && (err.status === 401 || err.status === 403)) {
          setAuctionItems(null);
          setAuctionNote(
            err.status === 403
              ? "경매: 조회 권한이 없는 계정입니다"
              : "경매: 로그인 후 조회 가능합니다",
          );
        } else {
          setAuctionItems([]); // 가짜 생성 금지
          setAuctionNote("경매: 조회 실패"); // 무자료와 실패를 구분(정직원칙)
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auctionEnabled, anchorLat, anchorLon, anchorAddress, anchorWaitNote, marketAnchorAddress]);

  const outputActions: OutputAction[] = useMemo(
    () => [
      {
        id: "analysis",
        label: "종합 부지분석",
        description: "다필지·규제·입지",
        href: `/${locale}/analysis`,
        icon: MapPin,
        // 산출물 dock: primary 1개(부지분석) + 글래스 3개 — DESIGN.md B5 Output Actions.
        tone: "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)]",
      },
      {
        id: "permits",
        label: "인허가 체크리스트",
        description: "허가 가능성·보완 항목",
        href: `/${locale}/permits`,
        icon: CheckCircle2,
        tone: "border-[var(--border-muted)] bg-[var(--surface-strong)] text-[var(--text-primary)]",
      },
      {
        id: "market",
        label: "시장·분양 리포트",
        description: "시세·수요·공급",
        href: `/${locale}/market-insights`,
        icon: LineChart,
        tone: "border-[var(--border-muted)] bg-[var(--surface-strong)] text-[var(--text-primary)]",
      },
      {
        id: "design",
        label: "건축개요·CAD 계획도면",
        description: "법규 맞춤 계획안",
        href: `/${locale}/design-studio`,
        icon: Building2,
        tone: "border-[var(--border-muted)] bg-[var(--surface-strong)] text-[var(--text-primary)]",
      },
    ],
    [locale],
  );

  const commitParcelsToContext = useCallback(
    (parcels: SatongParcel[]) => {
      const patch = selectionToSiteAnalysisPatch(parcels);
      if (!patch) return;
      updateSiteAnalysis(patch, { source: "user" });
    },
    [updateSiteAnalysis],
  );

  // 선택목록 → SSOT(store)·sessionStorage 동기화 공용통로. commitParcelsToContext는 빈 배열에
  //   no-op이므로, 빈 목록이면 store 필지를 명시 정리한다 — 안 지우면 ①재마운트 시 스토어 폴백
  //   하이드레이션이 삭제한 필지를 부활시키고 ②/analysis가 옛 주소를 계속 분석한다(P1 감사).
  //   삭제·전체취소 등 모든 경로가 이 통로를 쓰게 해 경로 간 비대칭 재발을 막는다.
  const syncParcelsToStores = useCallback(
    (parcels: SatongParcel[]) => {
      if (parcels.length > 0) {
        commitParcelsToContext(parcels);
      } else if (useProjectContextStore.getState().siteAnalysis != null) {
        // ★R2(LOW): siteAnalysis가 이미 null이면(예: 방금 clearProject로 프로젝트 해제 직후)
        //   빈 patch를 merge하지 않는다 — updateSiteAnalysis는 null일 때 기본 빈 객체와
        //   merge하므로, 여기서 그냥 호출하면 null→"내용 없는 빈 객체"로 부활시켜 다른 화면의
        //   "분석 없음" 판정을 오염시킨다.
        // ★파생 집계까지 함께 되돌린다(2026-08-23 · 사용자 신고 근본). 종전에는 여기서
        //   `parcels`·`parcelCount` 두 개만 0 으로 만들어, 그 목록에서 계산된 면적 합계
        //   (`landAreaSqm`/`landAreaSqmTotal`/`repLandAreaSqm`)와 `zoneMixed` 가 **유령으로
        //   살아남았다** — 화면이 "단일 필지입니다"라면서 동시에 통합면적 164,823㎡ 를 보이고,
        //   그 유령 면적이 설계·수지로 흘러 총사업비를 부풀렸다(라이브 실측 2건).
        //   되돌림 값은 쓰기 함수와 같은 모듈에 두어 **한 곳만 고치면 대칭이 유지**되게 한다.
        updateSiteAnalysis(emptySelectionSiteAnalysisPatch(), { source: "user" });
      }
      saveSelectionForOutputs(parcels);
    },
    [commitParcelsToContext, updateSiteAnalysis, saveSelectionForOutputs],
  );

  const addParcels = useCallback(
    (incoming: SatongParcel[]) => {
      if (incoming.length === 0) return;
      // ★교차오염 가드: 기존 프로젝트 연결 상태에서 그 프로젝트 주소와 지역이 다른 필지가
      //   들어오면, 프로젝트를 덮지 않도록 '새 프로젝트로 등록' 모드로 자동 전환한다.
      //   clearProject 직접 호출 대신 detachProjectCarryingSelection을 쓴다 — 전환 이펙트가
      //   이 해제를 '프로젝트 전환'으로 오인해 방금 추가한 필지·sessionStorage를 지우는 것을
      //   막는다(F1: prevProjectIdRef를 미리 null로 맞춰 이펙트가 전환으로 보지 않게 한다).
      if (projectId && connectTarget === projectId) {
        const projAddr = projects.find((p) => p.id === projectId)?.address || storeSiteAnalysis?.address;
        if (selectionMismatchesProject(projAddr, incoming[0]?.address)) {
          detachProjectCarryingSelection();
          setConnectTarget("new");
          setConnectNotice("선택 필지가 연결 프로젝트 주소와 달라 '새 프로젝트로 등록'으로 전환했습니다.");
        }
      }
      projectSeedArmedRef.current = false; // 사용자 직접 편집 — 자동시드 중지(선택 소유권 이전)
      selectionOwnerProjectIdRef.current = null; // ★R2: 사용자 편집 — 이후 소유권은 사용자(부분편집도 동일)
      setSelectedParcels((prev) => {
        const byKey = new Map(prev.map((parcel) => [parcelKey(parcel), parcel]));
        incoming.forEach((parcel) => {
          const key = parcelKey(parcel);
          const current = byKey.get(key);
          byKey.set(key, {
            ...current,
            ...parcel,
            areaSqm: parcel.areaSqm ?? current?.areaSqm ?? null,
            zoneType: parcel.zoneType ?? current?.zoneType ?? null,
            jimok: parcel.jimok ?? current?.jimok ?? null,
          });
        });
        const next = Array.from(byKey.values());
        syncParcelsToStores(next);
        return next;
      });
    },
    [syncParcelsToStores, projectId, connectTarget, projects, storeSiteAnalysis, detachProjectCarryingSelection],
  );

  const removeParcel = useCallback(
    (id: string) => {
      projectSeedArmedRef.current = false; // 사용자 직접 편집 — 자동시드 중지(선택 소유권 이전)
      selectionOwnerProjectIdRef.current = null; // ★R2: 사용자 편집 — 이후 소유권은 사용자(부분편집도 동일)
      setSelectedParcels((prev) => {
        const removed = prev.find((parcel) => parcel.id === id);
        const next = prev.filter((parcel) => parcel.id !== id);
        syncParcelsToStores(next); // 빈 배열이면 store·sessionStorage 모두 정리(부활 방지)
        // ★R1 HIGH(유령 패널): 삭제한 필지가 상세 패널에 떠 있으면 함께 닫는다 —
        //   화면엔 삭제된 필지, 퍼널은 남은 선택으로 실행되는 오도 조합 차단.
        if (removed) {
          setDetailFeature((current) =>
            current &&
            // ★종전 `(removed.pnu && …) || current.address === removed.address` 는 **PNU 가
            //   서로 달라도 주소만 같으면 참**이라, 같은 동 주소의 **다른 필지** 패널을 닫았다.
            isSameParcel(current, removed)
              ? null
              : current,
          );
        }
        return next;
      });
    },
    [syncParcelsToStores],
  );

  // ── 지번 자가치유(좌표 앵커) ────────────────────────────────────────────────
  //  PNU 도 없고 주소에 지번도 없는 필지를, **좌표가 있을 때만** /zoning/parcel-at-point 로
  //  해석해 진짜 PNU·주소를 채운다. 규칙·무날조 경계는 lib/parcel-jibun-heal 주석 참조.
  //  ★의존성은 selectedParcels 배열이 아니라 **미해석 건수**다 — 배열을 의존성에 두면
  //    치유가 배열을 갱신 → 이펙트 재발화 → 무한 루프가 된다. 건수는 치유 성공만큼 줄어든다.
  const healTargetCount = countJibunHealTargets(selectedParcels);
  const selectedParcelsRef = useRef(selectedParcels);
  selectedParcelsRef.current = selectedParcels;
  const syncParcelsToStoresRef = useRef(syncParcelsToStores);
  syncParcelsToStoresRef.current = syncParcelsToStores;
  useEffect(() => {
    if (healTargetCount === 0) return;
    let cancelled = false;
    void (async () => {
      const snapshot = selectedParcelsRef.current;
      const healed = await healParcelJibunByPoint(
        snapshot,
        async (point) => {
          const result = await apiClient.post<ParcelAtPointResult>("/zoning/parcel-at-point", {
            body: { lat: point.lat, lon: point.lon },
            useMock: false,
            timeoutMs: 20000,
          });
          return result?.found === false ? null : result;
        },
        { limit: 4, isCancelled: () => cancelled },
      );
      if (cancelled || healed.length === 0) return;
      setSelectedParcels((prev) => {
        // 스냅샷 이후 목록이 바뀌었으면(추가·삭제) 인덱스가 어긋나므로 폐기한다 —
        // 다음 렌더에서 미해석 건수가 그대로라 이펙트가 다시 돈다(무날조: 틀린 행에 안 쓴다).
        // ★이 줄은 **의도된 이중 가드(조기 탈출)** 다 — 정확성은 아래
        //   `parcel !== snapshot[index]` 참조 동등성이 단독으로 보장한다(길이가 달라져 인덱스가
        //   밀리면 그 비교가 반드시 어긋난다). 그래서 이 줄만 지우는 변이는 **생존이 정상**이고,
        //   락은 아래 줄에 걸려 있다(변이 점수 부풀리기 방지 — 사실을 여기 적는다).
        if (prev.length !== snapshot.length) return prev;
        const next = prev.map((parcel, index) => {
          const hit = healed.find((h) => h.index === index);
          if (!hit || parcel !== snapshot[index]) return parcel;
          return {
            ...parcel,
            pnu: hit.pnu,
            // 서버가 지번 붙은 주소를 주면 채택한다(없으면 기존 주소 유지 — 무날조).
            address: hit.address?.trim() || parcel.address,
          };
        });
        syncParcelsToStoresRef.current(next);
        return next;
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [healTargetCount]);

  // ★R2(관심사 분리): "확정 선택(selectedParcels) 정리"와 "지도 staged 폴리곤 정리"를 분리한다.
  //   staged(지도에 찍었지만 [완료] 안 누른 임시 클릭)는 아직 확정 선택이 아니라 소유권 개념이
  //   없다 — 프로젝트 문맥이 바뀌면 누구 선택이든 상관없이 항상 청소해도 안전하다. 반면
  //   확정 선택은 "누가 담았나"에 따라 지워도 되는지가 갈린다(아래 handleConnectTargetChange의
  //   selectionOwnerProjectIdRef 판별). 두 함수를 쪼개 각 호출부가 필요한 것만 조합하게 한다.
  const clearConfirmedSelectionUi = useCallback(() => {
    setSelectedParcels([]);
    setFocusTarget(null);
    setDetailFeature(null); // ★R1 HIGH: 상세 패널(유령 패널) 잔존 방지
    selectionOwnerProjectIdRef.current = null; // 빈 목록은 소유자가 없다
  }, []);

  const bumpMapClearSignal = useCallback(() => {
    setClearNonce((n) => n + 1); // ★WP-M2: 지도 staged·녹색 폴리곤도 함께 청소(잔존 방지)
  }, []);

  // ★레인F P0-2: clearParcels(전체 초기화 버튼)와 프로젝트 전환 이펙트처럼 "확정목록+지도"를
  //   무조건 통째로 비워야 하는 호출부를 위한 번들 — 부분 청소가 필요한 handleConnectTargetChange
  //   는 아래에서 두 함수를 따로 조합한다(중복 구현 금지 — 항상 이 두 함수를 통해서만 청소).
  const clearSelectionUiArtifacts = useCallback(() => {
    clearConfirmedSelectionUi();
    bumpMapClearSignal();
  }, [clearConfirmedSelectionUi, bumpMapClearSignal]);

  const clearParcels = useCallback(() => {
    projectSeedArmedRef.current = false; // 사용자 직접 편집 — 자동시드 중지(선택 소유권 이전)
    clearSelectionUiArtifacts();
    syncParcelsToStores([]);
  }, [clearSelectionUiArtifacts, syncParcelsToStores]);

  // ★레인F P0-1(사용자 버그리포트) → R2(HIGH) 재교정: "새 프로젝트로 등록"·"연결 안 함"으로
  //   전환해도 이전 프로젝트에서 상속된 선택 필지가 잔존하던 결함을 고친다. 단, R1 리뷰어
  //   프로브가 실증했듯 무조건 clearParcels()는 "방금 사용자가 지도로 직접 담은 선택"까지
  //   지워 addParcels 가드 경로(선택 항상 보존)와 정반대 계약이 됐다 — 소유권으로 가른다.
  //   selectionOwnerProjectIdRef가 "지금 해제하려는 프로젝트"와 같을 때만(=순수 상속, 사용자
  //   편집이 한 번도 없었을 때만) 확정목록을 지운다. staged(지도 임시 클릭)는 확정 선택이
  //   아니므로 소유권과 무관하게 항상 청소한다(R1b 결정 유지).
  const handleConnectTargetChange = useCallback((value: string) => {
    setConnectNotice("");
    if (value === "new" || value === "none") {
      setConnectTarget(value);
      // ★Open Question(저비용 대응): 렌더 시점 클로저 대신 스토어의 현재값을 읽어, 혹시라도
      //   stale closure로 엉뚱한 프로젝트를 대상으로 판단·해제하는 것을 원천 차단한다(기존
      //   "초기화" 버튼류에도 있던 저확신 우려 — 여기서 같이 닫는다. 비용 없음).
      const activeProjectId = useProjectContextStore.getState().projectId;
      const ownedByDetachingProject =
        activeProjectId != null && selectionOwnerProjectIdRef.current === activeProjectId;
      // 활성 프로젝트가 있으면 해제(스냅샷 보존) — 이후 선택·커밋이 그 프로젝트를 덮지
      //   않게. clearProject 직접 호출 대신 detachProjectCarryingSelection을 써서 전환
      //   이펙트가 이 해제를 '프로젝트 전환'으로 오인하지 않게 한다(F1).
      if (activeProjectId) detachProjectCarryingSelection();
      bumpMapClearSignal(); // staged는 소유권 무관 — 항상 청소(R1b)
      if (ownedByDetachingProject && selectedParcels.length > 0) {
        clearConfirmedSelectionUi();
        syncParcelsToStores([]); // store·sessionStorage까지 함께 정리(부활 방지)
        setConnectNotice("연결 대상을 바꿔 선택 필지를 비웠습니다.");
      } else if (stagedCount > 0) {
        // 확정목록은 보존(사용자 소유이거나 이미 0건)했지만 지도의 임시 선택은 정리했다 —
        //   staged만 있고 selectedParcels가 0인 경우에도 무음이 되지 않게(R2 MEDIUM).
        setConnectNotice("연결 대상을 바꿔 지도에 임시로 찍어둔 선택을 정리했습니다.");
      }
      return;
    }
    setConnectTarget(value);
    handleSelectProject(value); // 기존 경로(setProject+restoreSnapshot) 재사용 — PR#221 시드가 이어짐
  }, [
    detachProjectCarryingSelection,
    handleSelectProject,
    selectedParcels.length,
    stagedCount,
    clearConfirmedSelectionUi,
    bumpMapClearSignal,
    syncParcelsToStores,
  ]);

  const runDirectGeocode = useCallback(
    async (rawQuery: string) => {
      const trimmed = rawQuery.trim();
      if (!trimmed) return;
      setSearchStatus("loading");
      setSearchError("");
      try {
        const geocoded = await apiClient.post<GeocodeResponse>("/zoning/geocode", {
          body: { query: trimmed },
          useMock: false,
          timeoutMs: 20000,
        });
        if (!geocoded.found) {
          setSearchStatus("error");
          setSearchError(geocoded.reason || "검색 결과를 찾지 못했습니다.");
          return;
        }
        const parcel = parseGeocodeToParcel(trimmed, geocoded, "search");
        addParcels([parcel]);
        if (parcel.lat != null && parcel.lon != null) {
          setFocusTarget({ lat: parcel.lat, lon: parcel.lon, label: parcel.address });
        }
        setSearchCandidates([]);
        setSearchStatus("idle");
      } catch {
        setSearchStatus("error");
        setSearchError("주소 검색 중 오류가 발생했습니다.");
      }
    },
    [addParcels],
  );

  const handleCandidatePick = useCallback(
    async (candidate: SearchCandidate) => {
      const label = getCandidateLabel(candidate);
      setQuery(label);
      setSearchCandidates([]);
      if (candidate.pnu || (candidate.lat != null && candidate.lon != null)) {
        const parcel: SatongParcel = {
          id: candidate.pnu || normalizeKey(label),
          address: label,
          pnu: candidate.pnu ?? null,
          lat: candidate.lat ?? null,
          lon: candidate.lon ?? null,
          source: "search",
        };
        addParcels([parcel]);
        if (parcel.lat != null && parcel.lon != null) {
          setFocusTarget({ lat: parcel.lat, lon: parcel.lon, label: parcel.address });
        }
        return;
      }
      await runDirectGeocode(label);
    },
    [addParcels, runDirectGeocode],
  );

  // ★UX 트랙 C6: candidateIndex를 받아 "지금 키보드로 highlight된 후보"를 확정할 수 있게
  //   한다(종전엔 Enter가 항상 후보 0번을 확정해, 방향키로 다른 후보를 골라도 무시됐다).
  //   미전달(버튼 클릭 등 기존 호출부)은 그대로 후보 0번 우선 — 무회귀.
  const handleSearchSubmit = useCallback((candidateIndex?: number) => {
    const candidate = searchCandidates[candidateIndex ?? 0];
    if (candidate) {
      void handleCandidatePick(candidate);
      return;
    }
    void runDirectGeocode(query);
  }, [handleCandidatePick, query, runDirectGeocode, searchCandidates]);

  const handleExcelUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      setUploadStatus("loading");
      setUploadNote("");
      setVerificationReport(null);
      setUploadParcels([]);
      uploadCancelledRef.current = false;
      // ★UX 트랙 C4: 취소 버튼용 AbortController. apiClient에 signal을 직접 넘기면 내부
      //   자동 타임아웃 컨트롤러 생성이 스킵되므로(무한대기 재도입 방지), 동일한 180초
      //   상한을 이 컨트롤러에도 그대로 걸어둔다(무회귀 — 기존 타임아웃 계약 유지).
      const controller = new AbortController();
      uploadAbortRef.current = controller;
      const timeoutTimer = setTimeout(() => controller.abort(), 180000);
      const form = new FormData();
      form.append("file", file);
      form.append("use_llm", String(useLlm));
      try {
        const data = await apiClient.post<ParseParcelsResponse>("/zoning/parse-parcels", {
          body: form,
          useMock: false,
          signal: controller.signal,
          // ★H4-③: LLM 보조 구조인식·반복검증(S1/S3)까지 걸리면 60s로는 대량 엑셀에서 타임아웃이
          //   잦았다 — GlobalAddressSearch(120s)보다 여유 있게 180s로 상향(위 setTimeout으로 대체 집행).
          timeoutMs: 180000,
        });
        if (data.error) {
          setUploadStatus("error");
          setUploadNote(data.error);
          return;
        }
        const allParcels = data.parcels ?? [];
        // ★H3: injectable=False는 백엔드에서 표에서 완전히 제외된 행(합계/집계)에만 쓴다 —
        //   verified/corrected/needs_review는 모두 주입해 주입 후 2차 enrich(/zoning/parcels-info)
        //   의 재지오코딩·재검증으로 자기치유되게 한다(injectable 필드 부재 시 구버전 응답
        //   호환을 위해 기본 포함 — 무회귀). 필터 로직은 그대로 두되(향후 방어), 실제로는
        //   백엔드 계약상 아래 filter가 걸러내는 행은 사실상 없다.
        const injectable = allParcels.filter((p) => p.injectable !== false);
        const parcels = injectable.map((p, i) => parsedParcelToSelection(p, i));
        addParcels(parcels);
        setUploadStatus("idle");
        setUploadParcels(allParcels);
        setVerificationReport(data.verification_report ?? null);
        const skipped = allParcels.length - injectable.length;
        setUploadNote(
          (data.note ||
            (parcels.length > 0
              ? `${parcels.length}개 필지를 지도 선택 목록에 반영했습니다.`
              : "엑셀에서 등록 가능한 필지를 찾지 못했습니다.")) +
            (skipped > 0 ? ` (확인필요 ${skipped}건은 아래 리포트에서 확인)` : ""),
        );
      } catch {
        // ★UX 트랙 C4: 취소 버튼으로 abort된 경우와 실제 실패(네트워크·180초 타임아웃)를
        //   구분해 고지한다 — 취소는 사용자 의도된 행동이라 "오류"로 부르면 정직하지 않다.
        if (uploadCancelledRef.current) {
          setUploadStatus("idle");
          setUploadNote("업로드를 취소했습니다.");
        } else {
          setUploadStatus("error");
          setUploadNote("엑셀 파일 처리 중 오류가 발생했습니다.");
        }
      } finally {
        clearTimeout(timeoutTimer);
        uploadAbortRef.current = null;
        event.target.value = "";
      }
    },
    [addParcels, useLlm],
  );

  // ★UX 트랙 C4: 업로드 취소 — 사용자가 직접 버튼을 눌러야만 발화(자동 타임아웃과 구분).
  const cancelExcelUpload = useCallback(() => {
    uploadCancelledRef.current = true;
    uploadAbortRef.current?.abort();
  }, []);

  // ★무목업: 서버가 단계별 진행률을 주지 않으므로(단일 동기 응답) "수집"만 running으로
  //   표기하고 검증·전문가 LLM 단계는 응답 도착 전까지 idle로 둔다 — 가짜 진행 애니메이션
  //   대신 실제로 아는 사실(요청 전송됨·아직 완료 안 됨)만 정직하게 반영한다.
  const uploadPipelineSteps = useMemo<PipelineStep[]>(
    () => [
      { id: "collect", status: "running", sourceLabel: "엑셀 업로드 → 구조 인식·지오코딩" },
      { id: "verify", status: "idle" },
      { id: "expert", status: "idle", honestBadge: useLlm ? undefined : "LLM 보조 꺼짐" },
    ],
    [useLlm],
  );

  const handleTemplateDownload = useCallback(() => {
    if (typeof window === "undefined") return;
    window.location.href = `${apiV1BaseUrl()}/zoning/land-schedule-template`;
  }, []);

  // ★탐색(browse)과 확정(commit) 분리(2026-07-23 사용자 UX 요청2) — 레일 항목은 '열기만'
  //   한다. 종전엔 레일 클릭이 지도 레이어를 즉시 토글해, 무슨 레이어인지 보려면 반드시
  //   켜야 했다(보기=적용). 이제 롤오버/포커스/클릭은 미리보기 팝오버만 열고, 실제 적용은
  //   팝오버 안의 컨트롤·헤더 on/off에서 한다. 지도 상태는 전혀 건드리지 않는다.
  //   ★토글이 아니라 '지정'이다 — 롤오버로 항목을 옮길 때 같은 항목 재진입이 닫힘으로
  //   해석되면 깜빡인다(전환은 열림 유지가 계약).
  // ★고정(pin)된 패널 id — 클릭으로 연 것만 기록한다. boolean이면 레일 안에서 다른 항목을
  //   '스치기만' 해도 true로 덮여 클릭 확정분이 강등된다(R1 MEDIUM-B 실증).
  const pinnedPanelRef = useRef<SatongMapLayerId | "basemap" | null>(null);
  // 레일 이탈 후 닫힘 유예 — 팝오버는 레일의 '형제'라 경계를 넘는 순간 mouseleave가 발화한다.
  // 유예가 없으면 팝오버에 물리적으로 도달할 수 없다(R1 HIGH-B 실증).
  const hoverCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (hoverCloseTimerRef.current) clearTimeout(hoverCloseTimerRef.current);
  }, []);
  const cancelHoverClose = useCallback(() => {
    if (hoverCloseTimerRef.current) {
      clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
  }, []);

  // ── 레일 hover '전환' 의도 지연(HOVER_SWITCH_DELAY_MS 주석 참조) ──────────────
  const hoverSwitchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (hoverSwitchTimerRef.current) clearTimeout(hoverSwitchTimerRef.current);
  }, []);
  const cancelHoverSwitch = useCallback(() => {
    if (hoverSwitchTimerRef.current) {
      clearTimeout(hoverSwitchTimerRef.current);
      hoverSwitchTimerRef.current = null;
    }
  }, []);

  /**
   * 레일 아이콘 hover → 팝오버 열기 요청(전환만 지연).
   *
   * @param open 실제 열기 동작(openLayerPanel/openBasemapPanel 바인딩)
   * @param alreadyShown 지금 보이는 팝오버가 바로 이 항목인가(같은 항목 재진입은 무동작)
   *
   * ★열기 경로를 **여기 하나로** 모은다 — 레일 항목이 12개+베이스맵이라 각 핸들러에서
   *   따로 지연을 걸면 새 항목이 추가될 때 또 샌다(이 레일에서 반복된 결함 패턴).
   */
  const requestHoverOpen = useCallback(
    (target: SatongMapLayerId | "basemap", open: () => void, alreadyShown: boolean) => {
      cancelHoverClose();
      cancelHoverSwitch();
      if (alreadyShown) return; // 같은 팝오버 — 깜빡임 방지(기존 계약 유지)
      const anyShown = basemapOpen || activeLayerId !== null;
      // ★R1 HIGH-1 봉합: **클릭으로 고정한 항목으로의 복귀는 지연하지 않는다.**
      //   지연하면 복귀가 예약으로 남고, 그 상태로 레일을 벗어나면 `cancelHoverSwitch`가
      //   예약을 죽여 activeLayerId가 고정분으로 돌아오지 못한다 → `shownIsPinned`가 false가
      //   되어 **클릭으로 고정한 팝오버가 닫힌다**(Q2-c 계약 파괴). 스침 방지는 '남의 창을
      //   뺏는 것'을 막자는 것이지 '내 창으로 돌아오는 것'을 막자는 게 아니다.
      //   ★대가도 적는다(R2 MEDIUM): 이 예외 때문에 **고정된 아이콘 1개는 여전히 스침만으로
      //   창을 뺏는다**(A 고정 → B로 전환 → B 팝오버로 가며 A를 통과 → A가 즉시 뜸).
      //   mouseenter 정보만으로는 '스침'과 '복귀'가 구분 불가라 두 계약은 고정분에 대해
      //   **양립 불가**하고, 여기선 "클릭 확정분을 지킨다"를 우선했다. 되돌리지 마라 —
      //   되돌리면 클릭 고정분이 레일 이탈로 닫히는 회귀가 부활한다(테스트 ⑫가 이 선택을 박제).
      if (!anyShown || pinnedPanelRef.current === target) {
        open(); // ★첫 열기·고정분 복귀는 즉시 — 지연은 '남의 창으로의 전환'에만
        return;
      }
      hoverSwitchTimerRef.current = setTimeout(() => {
        hoverSwitchTimerRef.current = null;
        open();
      }, HOVER_SWITCH_DELAY_MS);
    },
    [activeLayerId, basemapOpen, cancelHoverClose, cancelHoverSwitch],
  );

  // ★R1 3차 HIGH-1 봉합 — 닫힘은 상태와 '핀'을 함께 정리해야 한다(원자화). 종전엔 핀을
  //   클릭 토글-닫기 2곳에서만 지워, Esc·X·외부클릭으로 닫으면 핀이 stale로 남고 그 뒤
  //   hover 미리보기들이 "핀이 있으니 닫지 마라"에 걸려 지도 위에 눌러붙었다(2차 롤아웃
  //   계약을 가장 흔한 흐름에서 재파괴). 닫힘 근원이 6곳 흩어져 있어 공용 헬퍼로 추출한다.
  // ★R1 MEDIUM-1(hover 지연) 봉합: 예약 전환 취소도 **여기서** 한다. 취소를 핸들러마다
  //   흩어 배선했더니 Esc·X·외부클릭 3경로가 샜다 — 아이콘 위에서 Esc를 누르면 닫힌 뒤
  //   150ms 후 예약이 발화해 **되살아났다**. 이 헬퍼가 이미 "닫힘 근원 6곳"의 수렴점이므로
  //   한 곳을 고치면 전역이 따라온다(저장소 버그수정 기본정책의 공용화 규칙).
  const closeLayerPanel = useCallback(() => {
    cancelHoverSwitch();
    pinnedPanelRef.current = null;
    setActiveLayerId(null);
  }, [cancelHoverSwitch]);
  const closeBasemapPanel = useCallback(() => {
    cancelHoverSwitch();
    pinnedPanelRef.current = null;
    setBasemapOpen(false);
  }, [cancelHoverSwitch]);

  // ★R1 4·5차 HIGH-2/3 종결 봉합 — 닫힘 근원이 6곳(Esc·외부클릭·X·클릭토글·유예타이머·팝오버
  //   onMouseLeave)이라 헬퍼 위임만으론 매번 한둘이 샌다(타이머 콜백·팝오버 mouseleave는
  //   raw setState). 핀 정리를 '경로'가 아니라 '상태 불변식'으로 세운다.
  //   ★조건은 '완전히 닫힘'이지 '전환'이 아니다 — 배타 상태라 아무 팝오버도 안 보이는
  //   순간(basemapOpen=false AND activeLayerId=null)에만 지운다. 종전 activeLayerId===pin은
  //   A→B 전환 즉시 false가 돼 클릭 확정분을 조기 강등했다(R1 5차 HIGH-3=Q2-c 회귀). basemap↔
  //   layer 스침은 한쪽만 false라 이 조건에 안 걸려 전환으로 올바르게 처리된다(양쪽 필수).
  useEffect(() => {
    const pin = pinnedPanelRef.current;
    if (!pin) return;
    if (!basemapOpen && activeLayerId === null) pinnedPanelRef.current = null;
  }, [activeLayerId, basemapOpen]);

  const openLayerPanel = useCallback((layerId: SatongMapLayerId) => {
    // ★R1 HIGH-2: 여기서 setDetailFeature(null)을 하면 레일 위를 '스치기만' 해도 열려 있던
    //   필지 상세가 파괴되고 Esc로도 복구되지 않는다(접힌 레일이 지도 우상단이라 상시 발생).
    //   시각 배타는 렌더 가드(detailFeature && !activeLayer && !basemapOpen)가 이미 보장하므로
    //   상세는 '가려질' 뿐이고, 팝오버를 닫으면 복원된다. 파괴적 초기화는 의도 경로
    //   (openFeatureDetail)에만 남긴다.
    setBasemapOpen(false);
    setActiveLayerId(layerId);
  }, []);

  // 베이스맵 패널 열기(지정) — 레일 형제와 동일한 롤오버 계약.
  const openBasemapPanel = useCallback(() => {
    // ★R1 HIGH-2 동일 — hover 경로는 필지 상세를 파괴하지 않는다(가림→복원).
    setActiveLayerId(null);
    setBasemapOpen(true);
  }, []);

  // 레이어 on/off — 팝오버 헤더 확정 버튼용(패널 토글 없이 켜짐/꺼짐만 바꾼다).
  // 지적도는 기반 레이어라 끄지 않는다.
  // ★UX 트랙 C2(2026-07-24): 종전엔 좌상단 활성 칩도 이 토글+패널전환을 함께 하는
  //   handleLayerClick을 통해 호출했으나("끄면서 동시에 그 레이어의 설정 팝오버를 여는"
  //   이중 조작 버그였다), 칩을 표시 전용 배지로 강등하며 그 호출부가 사라졌다 —
  //   레이어 조작 경로는 이제 우상단 레일(팝오버 헤더 toggleLayerEnabled) 하나로 일원화됐다.
  const toggleLayerEnabled = useCallback(
    (layerId: SatongMapLayerId) => {
      if (!isRenderableSatongMapLayer(layerId)) return;
      // ★`cadastre` 보호와 «변화 없으면 같은 참조» 는 **스토어 액션**이 지킨다(계약 이식).
      toggleLayerEnabledAction(layerId);
    },
    [toggleLayerEnabledAction],
  );

  const handleLayerControlClick = useCallback((layerId: SatongMapLayerId, control: SatongLayerControl) => {
    if (!control.mapEffect) return;
    // ★이미 켜져 있으면 **같은 참조**를 돌려주는 계약은 스토어 액션으로 옮겼다.
    //   무조건 새로 만들면 mapLayerState memo 가 재계산돼 layerState identity 가 바뀌고,
    //   그걸 deps 로 쓰는 필지 오버레이·POI effect 가 전량 파괴·재생성된다(깜빡임의 근원).
    ensureLayerEnabled(layerId);
    setLayerControls((prev) => {
      const current = new Set(prev[layerId] ?? []);
      if (layerId === "terrain") {
        ["base", "satellite", "hybrid", "aerial", "gray"].forEach((id) => current.delete(id));
        current.add(control.id);
      } else if (layerId === "transactions" && (control.id === "kind-trade" || control.id === "kind-rent")) {
        // 매매/전월세는 배타 전환 — kind 자체가 백엔드 카테고리 키(`${type}_${kind}`)의 축이라
        // 동시선택은 무의미(terrain 베이스맵과 동일한 상호배타 패턴).
        current.delete("kind-trade");
        current.delete("kind-rent");
        current.add(control.id);
      } else if (current.has(control.id)) {
        current.delete(control.id);
      } else {
        current.add(control.id);
      }
      return {
        ...prev,
        [layerId]: Array.from(current),
      };
    });
    // ★deps 에 `setLayerControls` 를 넣는다(2026-09-04): 종전에는 `useState` 세터라 eslint 가
    //   **안정적임을 알고** 생략을 허용했는데, 이제 zustand 액션이라 알 수 없다. 실제로는
    //   스토어 액션이므로 identity 가 안 바뀌어 재생성이 늘지 않는다 — 넣는 쪽이 정직하다.
  }, [setLayerControls]);

  const handleMapPickMany = useCallback(
    (parcels: ParcelAtPointResult[]) => {
      addParcels(parcels.map(mapParcelToSelection));
    },
    [addParcels],
  );

  // ★P1(감사): 지도 경계 API가 보강한 필지 속성(면적·용도·좌표·경계)을 선택목록+SSOT에 병합.
  //   종전엔 지도 내부 dead-end → 검색 등록 필지가 면적 0으로 통합분석에서 침묵 탈락했다.
  //   빈 필드만 채우고(사용자·원천값 우선), 변화가 없으면 setState를 건너뛰어 재조회 루프를 끊는다.
  const handleBoundaryEnriched = useCallback(
    (features: Array<{ pnu?: string | null; address?: string;
      /** 입력 주소 원본 — address 는 지번이 붙어 보강되므로 씨드 매칭은 이 값으로 한다. */
      inputAddress?: string | null; areaSqm?: number | null;
      zoneType?: string | null; jimok?: string | null; lat?: number | null; lon?: number | null;
      officialPricePerSqm?: number | null; builtYear?: number | null;
      buildingAgeYears?: number | null; ageStatus?: string | null;
      effectiveFarPct?: number | null; effectiveBcrPct?: number | null;
      legalFarPct?: number | null; farBasis?: string | null;
      currentFarPct?: number | null; geometry?: unknown;
      dominantConstraint?: DominantConstraint | null }>,
    ) => {
      // ★W1: 지배 제약은 뷰 캐시(ref+sessionStorage)에만 담는다 — 선택 SSOT(필지 객체)에 넣으면
      //   stale 규제가 프로젝트 스냅샷에 박히고, 새 객체 identity가 매 응답마다 변경감지를 참으로
      //   만들어 commit/save 루프를 돈다. 표시 합류는 openFeatureDetail이 담당.
      rememberDominantConstraints(
        features
          .filter((f) => f.pnu || f.address)
          .map((f) => [
            dominantConstraintKey({ pnu: f.pnu ?? null, address: f.address ?? "" }),
            f.dominantConstraint ?? null,
          ]),
      );
      // ★R1 MEDIUM-4: 상세 패널이 **열린 채로** 경계 응답이 도착하는 것이 실제 흐름이다
      //   (필지 담고 바로 카드 클릭 → 경계 왕복 최대 45s). ref 갱신은 렌더를 유발하지 않으므로
      //   종전엔 사용자가 패널을 닫고 다시 열 때까지 영구히 배너를 못 봤다. 열린 필지와 키가
      //   같으면 즉시 합류한다(값이 이미 있으면 스킵 — 불필요한 재렌더·churn 방지).
      // ★같은 이유로 **규제 근거(법정·근거계층)도** 열린 패널에 합류시킨다(2026-08-23).
      //   위 주석이 지배 제약에 대해 적은 사실("패널이 열린 채로 응답이 온다")은 이 값에도
      //   그대로 성립한다 — 그런데 종전엔 지배 제약만 합류시켜, 실효값 아래 근거가
      //   **패널을 닫았다 다시 열기 전까지** 안 떴다(테스트가 그 공백을 잡았다).
      setDetailFeature((current) => {
        if (!current || (current.legalFarPct != null && current.farBasis)) return current;
        const hit = features.find(
          (f) =>
            dominantConstraintKey({ pnu: f.pnu ?? null, address: f.address ?? "" }) ===
            dominantConstraintKey(current),
        );
        if (!hit || (hit.legalFarPct == null && !hit.farBasis)) return current;
        return {
          ...current,
          legalFarPct: current.legalFarPct ?? hit.legalFarPct ?? null,
          farBasis: current.farBasis ?? hit.farBasis ?? null,
        };
      });
      setDetailFeature((current) => {
        if (!current || current.dominantConstraint) return current;
        const hit = features.find(
          (f) =>
            dominantConstraintKey({ pnu: f.pnu ?? null, address: f.address ?? "" }) ===
            dominantConstraintKey(current),
        );
        return hit?.dominantConstraint ? { ...current, dominantConstraint: hit.dominantConstraint } : current;
      });
      setSelectedParcels((prev) => {
        if (!prev.length || !features.length) return prev;
        let changed = false;
        const byKey = new Map<string, (typeof features)[number]>();
        for (const f of features) {
          if (f.pnu) byKey.set(String(f.pnu), f);
          // ★표시 주소는 지번이 붙어 보강되므로 씨드(동 단위)와 어긋난다 — **입력 원본**으로도
          //   건다. 둘 다 걸어야 보강 전/후 응답 모두에서 치유가 끊기지 않는다.
          if (f.inputAddress) byKey.set(f.inputAddress.trim(), f);
          if (f.address) byKey.set(f.address.trim(), f);
        }
        const next = prev.map((p) => {
          const f = (p.pnu && byKey.get(String(p.pnu))) || byKey.get(p.address.trim());
          if (!f) return p;
          const merged = {
            ...p,
            // ★리뷰(HIGH) 근치: 시드 필지(pnu 미확보)의 합성/주소 키를 boundary가 돌려준 real
            //   pnu로 승격한다(기존 real pnu는 보존 — healParcelPnu 참조). 이 한 줄이 칩·CTA·
            //   merge 카운트 이중성의 근원(pnu/주소 키 불일치)을 한 곳에서 치유한다.
            pnu: healParcelPnu(p.pnu, f.pnu),
            areaSqm: p.areaSqm ?? f.areaSqm ?? null,
            zoneType: p.zoneType ?? f.zoneType ?? null,
            jimok: p.jimok ?? f.jimok ?? null,
            lat: p.lat ?? f.lat ?? null,
            lon: p.lon ?? f.lon ?? null,
            officialPricePerSqm: p.officialPricePerSqm ?? f.officialPricePerSqm ?? null,
            builtYear: p.builtYear ?? f.builtYear ?? null,
            buildingAgeYears: p.buildingAgeYears ?? f.buildingAgeYears ?? null,
            // ★WP-M3: 노후도 조회 사유(age_status)를 역전파해 "조회 시도됨"을 SSOT에 남긴다 —
            //   나대지(연식 null)여도 ageStatus가 채워져 경계 재조회 루프가 끊긴다.
            ageStatus: p.ageStatus ?? f.ageStatus ?? null,
            // I7/WS-D — 서버 산정치 역전파(선택 SSOT까지 — orphan handoff 방지).
            effectiveFarPct: p.effectiveFarPct ?? f.effectiveFarPct ?? null,
            legalFarPct: p.legalFarPct ?? f.legalFarPct ?? null,
            farBasis: p.farBasis ?? f.farBasis ?? null,
            effectiveBcrPct: p.effectiveBcrPct ?? f.effectiveBcrPct ?? null,
            currentFarPct: p.currentFarPct ?? f.currentFarPct ?? null,
            geometry: p.geometry ?? f.geometry ?? null,
          };
          if (
            merged.pnu !== p.pnu ||
            merged.areaSqm !== p.areaSqm || merged.zoneType !== p.zoneType ||
            merged.jimok !== p.jimok || merged.lat !== p.lat || merged.lon !== p.lon ||
            merged.officialPricePerSqm !== p.officialPricePerSqm ||
            merged.builtYear !== p.builtYear || merged.buildingAgeYears !== p.buildingAgeYears ||
            merged.ageStatus !== p.ageStatus ||
            merged.effectiveFarPct !== p.effectiveFarPct ||
            merged.effectiveBcrPct !== p.effectiveBcrPct ||
            merged.currentFarPct !== p.currentFarPct ||
            merged.geometry !== p.geometry
          ) {
            changed = true;
            return merged;
          }
          return p;
        });
        if (!changed) return prev; // 무변화 — 참조 유지로 하류 이펙트 재실행 차단
        commitParcelsToContext(next); // SSOT 동기화 → /analysis가 보강 면적을 읽는다
        saveSelectionForOutputs(next);
        return next;
      });
    },
    [commitParcelsToContext, saveSelectionForOutputs, rememberDominantConstraints],
  );

  // 선택 필지로 새 프로젝트 생성·연결(공용) — 셀렉터 아래 버튼과 산출물 실행(연결모드 "new")이 공유.
  // ★인플라이트 가드(F4): 버튼 연타·산출물 클릭 중복이 프로젝트를 여러 개 만들지 않게 한다.
  //   ref=동기 즉시차단, state=버튼 disabled 표시용(둘 다 시작/종료 시 함께 토글).
  const connectAsNewProject = useCallback(async (): Promise<string | null> => {
    if (selectedParcels.length === 0) return null;
    if (creatingProjectRef.current) return null;
    creatingProjectRef.current = true;
    setCreatingProject(true);
    try {
      const created = await createProjectFromParcels(selectedParcels);
      if (!created) {
        setConnectNotice("필지 주소가 없어 프로젝트를 생성할 수 없습니다.");
        return null;
      }
      // setProject 직후 같은 틱에 선택 패치를 커밋 — 전환 이펙트가 실행될 땐 storeSiteAnalysis에
      // 필지가 이미 있어 선택이 그대로 재시드된다(선택 소실 없음, PR#221 상호작용).
      // ★R2(MEDIUM, 의도 명시): 이 null→created.id 전환도 전환 이펙트를 타 clearNonce가 오른다
      //   (지도 staged 폴리곤도 함께 청소됨). 의도한 동작이다 — 방금 확정한 selectedParcels는
      //   위 재시드로 안전하게 복원되고(소실 없음), 프로젝트를 새로 여는 시점에 이 프로젝트와
      //   무관한 잔여 staged(다른 임시 클릭)까지 함께 정리되는 편이 "새 프로젝트 문맥 시작"
      //   의미에 부합한다(드롭다운 전환과 같은 근거). 전환 이펙트도 재시드 시 이 값을 다시
      //   같은 값으로 세팅하지만(대칭), 여기서 동기로 먼저 세팅해두는 이유는 아래 R2b 참고.
      setProject(created.id, created.name, "draft", created.address);
      // ★R2b(HIGH, 쓰기경로 전수감사): 전환 이펙트는 React가 커밋·이펙트를 플러시해야 실행되는데,
      //   그 전에 handleOutputClick 등 호출부가 이 함수의 반환을 이어받아 곧장
      //   saveSelectionForOutputs(selectedParcels)를 호출하면(예: 산출물 이동 직전 기록) 그 시점의
      //   ref가 아직 갱신 전이라 세션 미러에 잘못된(옛) 소유권이 실릴 수 있다. 여기서 동기로
      //   즉시 세팅해 그 경합을 원천 차단한다(효과 대기 불필요 — ref 쓰기는 렌더와 무관).
      selectionOwnerProjectIdRef.current = created.id;
      const patch = selectionToSiteAnalysisPatch(selectedParcels);
      if (patch) updateSiteAnalysis(patch, { source: "user" });
      setConnectTarget(created.id);
      setConnectNotice(`'${created.name}' 프로젝트가 생성·연결되었습니다.`);
      return created.id;
    } finally {
      creatingProjectRef.current = false;
      setCreatingProject(false);
    }
  }, [selectedParcels, setProject, updateSiteAnalysis]);

  const handleCreateProjectNow = useCallback(() => {
    void connectAsNewProject();
  }, [connectAsNewProject]);

  const handleOutputClick = useCallback(
    async (action: OutputAction) => {
      if (connectTarget === "new" && selectedParcels.length > 0) {
        try {
          await connectAsNewProject();
        } catch {
          // best-effort — 생성 실패해도 산출물 이동은 계속(기준선 정신)
        }
      }
      saveSelectionForOutputs(selectedParcels);
      commitParcelsToContext(selectedParcels);
      router.push(action.href);
    },
    [connectAsNewProject, connectTarget, commitParcelsToContext, router, selectedParcels, saveSelectionForOutputs],
  );

  // 최초 1회만 하이드레이션(이후 사용자 선택을 덮지 않도록 ref 가드). 우선순위:
  //   1) sessionStorage(자기세션 선택 — 좌표·경계까지 리치) → 복원(단, 미연결이면 이번 SPA
  //      세션에 기록된 선택만).
  //   2) 비었으면 활성 프로젝트 스토어 필지 폴백 → 연결 프로젝트의 필지를 지도/산출물에 복원.
  //   ★스토어 seed 시 commitParcelsToContext 재호출 금지(이미 스토어에 있는 값 되쓰면 되먹임 루프·#178).
  //   (refs 선언은 컴포넌트 상단으로 이동 — F1 참고)
  //
  //   ★T1(미연결 잔존 차단): 두 복원 경로 모두 브라우저(localStorage store)·탭(sessionStorage)에
  //     영속돼, 프로젝트를 연결하지 않고 검색도 안 한 '신규 진입'에서 이전 세션 선택이 되살아났다.
  //     - projectId가 있으면(이어하기/연결) 기존대로 복원한다(PR#221 스냅샷 하이드레이션 계약 불변).
  //     - 미연결(projectId 없음)이면: sessionStorage는 '이번 SPA 세션에 기록된 것'(sameSpaSession)
  //       일 때만 복원해 SPA 내 라우트 이동 후 복귀는 유지하되, 하드 리로드/새 탭 잔존은 차단한다.
  //       스토어 폴백(경로 2)은 localStorage라 하드 리로드도 넘어 되살아나므로 미연결이면 아예
  //       건너뛴다(SPA 내 복귀는 sessionStorage 경로가 담당).
  const hasConnectedProject = !!projectId;
  useEffect(() => {
    if (hydratedRef.current) return;
    const stored = readSatongMapSelection();
    if (stored?.parcels.length) {
      const restorable = hasConnectedProject || stored.sameSpaSession;
      if (restorable) {
        hydratedRef.current = true;
        setSelectedParcels(stored.parcels);
        // ★R2b(HIGH·PROBE_P3): 세션 미러에 함께 실린 소유권을 복원한다 — 안 하면 재마운트마다
        //   (예: 산출물 페이지 소프트 내비 후 복귀) 상속 선택이 사용자 소유로 영구 오분류돼
        //   드롭다운 전환 시 원 버그리포트 증상이 재현된다. 구 payload(필드 부재)는 undefined
        //   → null(사용자 소유, 안전측)로 취급.
        selectionOwnerProjectIdRef.current = stored.ownerProjectId ?? null;
        // ★★교차 프로젝트 오염 차단(2026-08-24 · 사용자 스크린샷) ──────────────────
        //
        //   증상: 한 화면에서 연결 프로젝트는 "오산시 내삼미동 외 76필지"(헤더 통합 77필지·
        //   86,755㎡)인데 선택 필지는 **모산동 123-1 외 6필지**였다. 두 프로젝트가 겹쳐 보였다.
        //
        //   기전: 위 `restorable` 은 `hasConnectedProject` 만 본다 — **미러의 소유 프로젝트가
        //   지금 연결된 프로젝트인지 묻지 않는다.** 그래서 남의 선택이 복원되고, 그대로
        //   `commitParcelsToContext` 로 **현재 프로젝트에 써 넣어졌다**(화면 오염 → 데이터 오염).
        //
        //   ★A→B **전환** 이펙트는 이 오염을 정확히 막는다(선택·미러 즉시 무효화).
        //     그런데 그 이펙트는 `isFirstRun` 이면 반환한다 — **다른 페이지에서 프로젝트를
        //     바꾼 뒤 이 화면으로 오면 "전환"이 아니라 "첫 실행"** 이라 아무것도 안 지운다.
        //     전환은 잠겼고 **신규 마운트가 안 잠겨** 있었다(계약 비대칭).
        //
        //   처방: 필지 **추가** 경로가 이미 쓰는 **같은 산식**(`selectionMismatchesProject` —
        //   지역 단위 비교, 번지 차이 무시)으로 대조한다. 산식을 새로 만들지 않는다.
        //   ★**막지 않고 고지한다** — 원거리 묶음이 후보지 비교라는 정당한 워크플로우일 수
        //     있다는 기존 결정을 따른다. 선택은 화면에 남기되 **프로젝트에는 커밋하지 않는다.**
        //     소유권도 사용자로 돌려, 이후 드롭다운 전환이 이 선택을 지우지 않게 한다.
        const restoredProjectAddress =
          projects.find((p) => p.id === projectId)?.address || storeSiteAnalysis?.address;
        const foreignToProject =
          !!projectId &&
          selectionMismatchesProject(restoredProjectAddress, stored.parcels[0]?.address);
        // ★2026-08-24 — **정체성 필드가 있는데 판정에 안 쓰이고 있었다.** 바로 세 줄 위에서
        //   `stored.ownerProjectId` 를 읽어 ref 에 넣어 놓고, 판정은 주소 **지역** 대리로만 했다.
        //   그래서 **같은 지역의 다른 프로젝트** 선택은 아무 말 없이 현재 프로젝트에 커밋됐다.
        //   ★그런데 그건 결함이 아니라 **의도된 제품 결정**이다(같은 지역이면 정상 워크플로우로
        //     본다 — 그 결정이 양성 대조군 테스트로 잠겨 있다). 그래서 **차단하지 않는다.**
        //   ★대신 **말한다.** 사용자 신고의 본질은 "커밋됐다"가 아니라 **"화면이 두 프로젝트를
        //     섞어 놓고 아무 말도 안 한다"** 였다. 이 저장소의 원칙("막지 않고 고지한다")대로
        //     정체성이 다르면 그 사실만 알린다 — 커밋 동작은 종전과 **완전히 동일**하다.
        const storedOwner = stored.ownerProjectId; // string | null(사용자 소유) | undefined(구 payload)
        const inheritedFromOtherProject =
          !foreignToProject &&
          typeof storedOwner === "string" &&
          !!projectId &&
          storedOwner !== projectId;
        if (foreignToProject) {
          selectionOwnerProjectIdRef.current = null; // 이 선택의 소유자는 프로젝트가 아니다
          setConnectNotice(
            "이전에 고른 필지가 연결 프로젝트와 다른 지역이라 프로젝트에 반영하지 않았습니다. " +
              "이대로 쓰려면 '새 프로젝트로 등록'을, 프로젝트 필지를 보려면 선택을 비우세요.",
          );
        } else {
          commitParcelsToContext(stored.parcels); // sessionStorage 경로는 기존대로 SSOT 동기화
          if (inheritedFromOtherProject) {
            // 커밋은 했다(같은 지역=정상 워크플로우). 다만 **어디서 온 선택인지**는 말한다.
            setConnectNotice(
              "이전에 고른 필지는 다른 프로젝트에서 가져온 선택입니다. " +
                "현재 프로젝트 기준으로 계속하려면 그대로 두고, 아니면 선택을 비우세요.",
            );
          }
        }
        const focused = stored.parcels.find((parcel) => parcel.lat != null && parcel.lon != null);
        if (focused?.lat != null && focused.lon != null) {
          setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
        }
        return;
      }
      // 미연결 + SPA 세션 불연속(하드 리로드/새 탭) → 이전 세션 선택 복원 금지. sessionStorage
      //   캐시를 정리해 다른 소비처(PreCheckWorkspace·/analysis 산출물)도 잔존을 읽지 않게 한다.
      hydratedRef.current = true;
      setSelectedParcels([]);
      saveSelectionForOutputs([]);
      return;
    }
    // 폴백: 연결 프로젝트 필지로 seed(재커밋 금지 — 이미 스토어 값). 미연결이면 스킵(위 주석).
    if (!hasConnectedProject) return;
    const seeded = siteAnalysisToSelection(storeSiteAnalysis);
    // ★유효 seed(주소 있는 필지)가 하나라도 나왔을 때만 latch. 전부 주소없어 []면 미확정으로 두어
    //   다음 siteAnalysis 변경(늦은 rehydrate) 때 재시도 허용(리뷰 LOW).
    if (seeded.length) {
      hydratedRef.current = true;
      setSelectedParcels(seeded);
      selectionOwnerProjectIdRef.current = projectId; // ★R2: 프로젝트 상속 시드 — 소유권=이 프로젝트
      const focused = seeded.find((parcel) => parcel.lat != null && parcel.lon != null);
      if (focused?.lat != null && focused.lon != null) {
        setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
      }
    }
  }, [commitParcelsToContext, storeSiteAnalysis, hasConnectedProject, projectId, saveSelectionForOutputs]);

  // 프로젝트 전환 감지 → 프로젝트 등록 필지로 선택 복원.
  // ★restoreSnapshot(백엔드 스냅샷 GET)은 비동기라 전환 직후엔 storeSiteAnalysis가 비어있을 수
  //   있다. siteAnalysis를 의존성에 포함해 늦게 도착한 필지도 시드한다(읽기단선 방지).
  //   armed 플래그는 전환 시 켜지고 사용자가 직접 편집(추가·삭제·전체취소)하면 꺼져,
  //   자동시드가 사용자 선택을 덮지 않는다. 첫 마운트는 위 하이드레이션(sessionStorage 우선)이
  //   담당하므로 개입하지 않는다(약식 모드 선택 전멸 회귀 방지).
  useEffect(() => {
    const prev = prevProjectIdRef.current;
    const isFirstRun = prev === undefined;
    const isTransition = !isFirstRun && prev !== (projectId ?? null);
    prevProjectIdRef.current = projectId ?? null;
    if (isFirstRun) return;

    if (isTransition) {
      // 이전 프로젝트 선택이 새 프로젝트로 새지 않도록 선택·sessionStorage 즉시 무효화(교차오염 차단)
      hydratedRef.current = true; // 전환 이후 선택 소유권은 이 이펙트 — 초기 하이드레이션 비활성
      projectSeedArmedRef.current = !!projectId;
      lastSeedKeyRef.current = "";
      projectFocusPendingRef.current = !!projectId;
      // ★레인F P0-2(형제 결함): clearParcels와 동일한 공용 청소(목록·포커스·상세패널·지도
      //   staged 폴리곤)를 호출한다 — 종전엔 clearNonce를 올리지 않아 A→B 전환 시 A의 staged
      //   폴리곤이 지도에 잔존했다. store/sessionStorage는 여기서 직접 처리(아래 그대로) —
      //   syncParcelsToStores를 쓰면 전환 중 방금 복원된 B의 siteAnalysis를 빈 값으로 덮어써
      //   비동기 restoreSnapshot 결과와 경합한다.
      clearSelectionUiArtifacts();
      saveSelectionForOutputs([]);
    }

    if (!projectId || !projectSeedArmedRef.current) return;

    const seeded = siteAnalysisToSelection(storeSiteAnalysis);
    if (seeded.length) {
      // 내용 지문이 같으면 스킵 — siteAnalysis 참조만 바뀐 무관 갱신에 재시드·지도 튐 방지.
      //   지문에 면적·용도지역·좌표·경계 유무를 포함해 보강(enrich) 도착은 반영한다.
      const seedKey = seeded
        .map(
          (p) =>
            `${p.id}:${p.areaSqm ?? ""}:${p.zoneType ?? ""}:${p.lat ?? ""}:${p.lon ?? ""}:${p.geometry ? 1 : 0}`,
        )
        .join("|");
      if (seedKey === lastSeedKeyRef.current) return;
      lastSeedKeyRef.current = seedKey;
      // 시드 출처가 스토어이므로 재커밋 금지(#178 되먹임 방지). sessionStorage만 동기화.
      setSelectedParcels(seeded);
      selectionOwnerProjectIdRef.current = projectId; // ★R2: 프로젝트 상속 시드 — 소유권=이 프로젝트
      saveSelectionForOutputs(seeded);
      // 지도 이동은 전환 후 1회만(좌표가 보강으로 늦게 오면 그때 1회) — 이후 갱신 때
      //   사용자가 보던 화면을 낚아채지 않는다.
      if (projectFocusPendingRef.current) {
        const focused = seeded.find((parcel) => parcel.lat != null && parcel.lon != null);
        if (focused?.lat != null && focused.lon != null) {
          projectFocusPendingRef.current = false;
          setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
        }
      }
    }
  }, [projectId, storeSiteAnalysis, clearSelectionUiArtifacts, saveSelectionForOutputs]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSearchCandidates([]);
      setSearchStatus("idle");
      setSearchError("");
      return;
    }
    let alive = true;
    const timer = window.setTimeout(async () => {
      setSearchStatus("loading");
      setSearchError("");
      try {
        const data = await apiClient.post<SearchResponse>("/zoning/search", {
          body: { query: trimmed },
          useMock: false,
          timeoutMs: 15000,
        });
        if (!alive) return;
        setSearchCandidates(data.candidates ?? []);
        setSearchStatus("idle");
      } catch {
        if (!alive) return;
        setSearchCandidates([]);
        setSearchStatus("error");
        setSearchError("검색 후보를 불러오지 못했습니다.");
      }
    }, 350);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    if (!activeLayerId) return;
    // ★ESC 는 **조정기**를 거친다(lib/satong-dismiss) — 종전에는 이 리스너가 지도의
    //   clickMenu ESC 와 같은 keydown 에 함께 발화해 **한 번에 둘이 닫혔다**(라이브 실측).
    //   이제 z(SSOT rung)가 가장 큰 표면 하나만 닫힌다. 외부 포인터다운은 대상 판정이
    //   표면마다 달라 일반화하지 않고 여기 그대로 둔다.
    const unregister = registerDismissible(SATONG_UI_Z.railPopover, closeLayerPanel);
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (popoverRef.current?.contains(target) || railRef.current?.contains(target)) return;
      closeLayerPanel();
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      unregister();
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, [activeLayerId, closeLayerPanel]);

  // 베이스맵 팝오버도 레이어 팝오버와 동일한 닫힘 계약(Esc·외부 포인터다운) — 같은 좌표에
  // 뜨는 형제 UI라 닫힘 규칙이 다르면 사용자가 두 규칙을 학습해야 한다(일관성).
  useEffect(() => {
    if (!basemapOpen) return;
    // ★ESC 는 **조정기**를 거친다(lib/satong-dismiss) — 종전에는 이 리스너가 지도의
    //   clickMenu ESC 와 같은 keydown 에 함께 발화해 **한 번에 둘이 닫혔다**(라이브 실측).
    //   이제 z(SSOT rung)가 가장 큰 표면 하나만 닫힌다. 외부 포인터다운은 대상 판정이
    //   표면마다 달라 일반화하지 않고 여기 그대로 둔다.
    const unregister = registerDismissible(SATONG_UI_Z.railPopover, closeBasemapPanel);
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (basemapPopoverRef.current?.contains(target) || railRef.current?.contains(target)) return;
      closeBasemapPanel();
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      unregister();
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, [basemapOpen, closeBasemapPanel]);

  // 베이스맵 스위처 — 우상단 레이어 레일의 '베이스맵' 항목이 여는 팝오버 본문(2026-07-23
  // 사용자 UX 요청: 지도 제어 일원화). 이력: 독립 absolute 섬(bottom-20 right-4) → 하단
  // 도크 bottomDockSlot(2026-07-17 겹침 구조 단일화) → 레일 팝오버(현재).
  // ★07-17 겹침 수정은 유지된다 — 도크 슬롯에서 빠져도 칩 행은 자기 flex flow 그대로이고,
  //   폐기됐던 암묵 예약값(152px)을 되살리지 않는다(레일 팝오버는 칩 행과 다른 코너·레이어).
  // ★레일 hover 전개와의 경합도 없다 — 팝오버는 레일 좌측(right-20)에 별도로 뜬다(레이어
  //   팝오버와 동일 좌표 계약). 상호배타: 하나가 열리면 다른 하나는 닫힌다.
  const basemapSwitcherPanel = (
    <div className="grid grid-cols-4 gap-1.5">
      {BASEMAP_SWITCHES.map((opt) => {
        const active = resolveVWorldBaseLayer(mapLayerState) === opt.base;
        return (
          <button
            key={opt.id}
            type="button"
            aria-pressed={active}
            aria-label={`베이스맵: ${opt.label}`}
            title={`베이스맵: ${opt.label}`}
            onClick={() =>
              handleLayerControlClick("terrain", { id: opt.id, label: opt.label, mapEffect: true })
            }
            className={`min-h-11 min-w-11 rounded-xl border p-1 text-center transition ${
              active
                ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15"
                : "border-transparent hover:border-[var(--line-strong)]"
            }`}
          >
            <span
              aria-hidden
              // 실물 타일을 background-image로 — <img>와 달리 로드 실패 시 깨진 아이콘
              // 없이 뒤의 그라디언트(opt.swatch)가 그대로 폴백된다(무음 열화·정직 유지).
              className={`block h-7 w-full rounded-lg border border-black/10 bg-cover bg-center ${opt.swatch}`}
              style={{ backgroundImage: opt.tiles.map((t) => `url(${t})`).join(", ") }}
            />
            <span className="mt-0.5 block text-[10px] font-black text-[var(--text-primary)]">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );

  // ★무목업: 종전 가상 분양단지/경매물건(Math.random) 목업을 실데이터 state로 대체.
  // 분양=/presale/nearby(청약홈)·경매=/auction/search+geocode(온비드) — 위 이펙트에서 조회.
  // ★R1 후속(레인G R2 — MEDIUM 필수): 백엔드 전월세는 4종만 지원(_RENT_TYPES —
  //   토지·상업업무용 전월세 API 자체가 없다). kind로 유형 후보를 좁히지 않으면
  //   기본값(type-land/type-commercial 켜짐) 상태에서 "전월세"를 누르는 즉시
  //   land_rent/commercial_rent(백엔드 부재)를 요청해 범례에 "0건"으로 뜬다 —
  //   미수집을 "거래 없음"으로 오인시키는 결함(무음/오도 클래스). 정답 기준선은
  //   형제 NearbyTransactionsMap(RENT_TYPES=MARKET_RENT_TYPES)과 동일 SSOT 적용.
  // ★UX 트랙 B4 훅 규칙 보정: 이 값은 종전 JSX 안(marketLayer prop)에서 인라인 useMemo로
  //   계산됐다. 아래 접힘 조기 반환을 추가하면서 모든 훅은 그 반환 이전에 실행돼야 하므로
  //   여기로 끌어올린다(계산 로직 무변경 — 위치만 이동).
  const marketLayerValue = useMemo(() => {
    const controls = layerControls.transactions ?? [];
    const kind: "trade" | "rent" = controls.includes("kind-rent") ? "rent" : "trade";
    const supportedTypes = kind === "rent" ? MARKET_RENT_TYPES : MARKET_TRADE_TYPES;
    return {
      kind,
      // ★하드코딩 제거(분석품질 레인G P0-3): 종전 type:"apt" 상수 고정 →
      //   layerState(layerControls) SSOT 참조. 켜진 유형 전부를 SatongMultiMap이
      //   동시 렌더한다(다중 표시).
      types: supportedTypes.map((t) => t.key).filter((key) => controls.includes(`type-${key}`)),
      showPresale: presaleEnabled,
      presaleItems: presaleEnabled ? presaleItems : null,
      showAuction: auctionEnabled,
      auctionItems: auctionEnabled ? auctionItems : null,
    };
  }, [layerControls.transactions, presaleEnabled, presaleItems, auctionEnabled, auctionItems]);

  // ★UX 트랙 B4(착지 페이지 접기) — 접힌 상태는 요약 1줄 + "지도 열기" 토글만 렌더한다.
  //   무거운 지도(SatongMultiMap)·레이어 패널은 마운트하지 않아 착지 페이지 초기 렌더 비용도
  //   함께 준다. 위 모든 훅은 접힘 여부와 무관하게 항상 동일한 순서로 실행되므로(early return은
  //   이 지점 — 모든 훅 호출 이후 — 에서만 이뤄짐) React 훅 규칙을 위반하지 않는다.
  if (!isShellExpanded) {
    return (
      <section className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface)] p-4 shadow-[var(--shadow-lg)] md:p-5">
        {/* ★z-[600] = SATONG_CONTENT_Z.stickyContextHeader — 지도 오버레이(380~500) 위,
            앱 헤더(1000) 아래. 종전 z-30 은 오버레이에 가려졌다(lib/satong-map-z.ts 계약 참조). */}
        {showContextHeader && (
          <ContextHeader sitePipeline className="sticky top-[var(--app-header-offset)] z-[600] mb-3" />
        )}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-panel)] px-4 py-3">
          <div className="min-w-0">
            <p className="font-[family-name:var(--font-display)] label-caps text-[var(--text-tertiary)]">
              Satong Map OS
            </p>
            <p className="mt-0.5 truncate text-sm font-black text-[var(--text-primary)]">
              {selectedParcels.length > 0
                ? `필지 선택 ${selectedParcels.length}건 · 합산 면적 ${formatArea(selectedTotalArea || null, 0)}`
                : "지도에서 필지를 선택하면 여기에 요약이 표시됩니다."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setIsShellExpanded(true)}
            /* ★모바일 IA P0 — 접힌 셸에서 이 버튼은 지도·검색·엑셀 전체로 가는 **유일한 진입점**인데
               h-9(36px)라 44px 터치 타깃 하한 미달이었다(packages/ui Button 은 min-h-11 을 지키는데
               raw <button> 이라 그 계약 밖에 있었다 — 그 계약 테스트는 프리미티브만 렌더한다).
               ★h-9 를 지우고 min-h-11 만 남겼으므로 **시각 높이도 36→44px로 실제 커진다**(의도).
               초판 주석은 "시각 크기는 그대로"라고 썼는데 사실이 아니었다(R1 지적 M3). 감싼 행도
               60→68px 자라지만 고정 높이·overflow 가 없어 클리핑은 없다.
               ★P2(#570)에서 이 파일의 나머지를 봉합했다 — 팝오버 닫기 3종·레이어 토글 칩·컨트롤 칩
               3종·업로드 취소·엑셀 선택·양식 다운로드·산출물 독 토글·미니 산출물 퍼널 4종·새 프로젝트
               생성, 그리고 자식 섹션 2건(ParcelLayoutSection·ParcelSlopeSection 조회 버튼).
               ★P0 시점에 "아직 3건 남았다"고 적었으나 실제로는 더 많았다 — 사람이 센 목록이 곧
               상한이 되는 함정이다. 지금은 렌더 기반 **전수 불변식**이 잠그므로 목록을 세지 않는다
               (SatongMapShell.smoke.test.tsx "44px 터치 타깃 전수 불변식"). */
            className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 text-xs font-black text-[var(--text-primary)] transition-colors hover:border-[var(--accent-strong)]"
          >
            <MapIcon className="size-4" aria-hidden />
            지도 열기
          </button>
        </div>
      </section>
    );
  }

  // ★H2 결함 봉합(2026-07-29): 지도 오버레이(활성 레이어 배지행·레이어 레일·팝오버 3종)를
  //   SatongMultiMap의 '형제'가 아니라 topRightSlot으로 넘겨 풀스크린 래퍼 '안'에 렌더한다.
  //   ★근본원인: 풀스크린은 SatongMultiMap 내부 래퍼에 fixed inset-0 z-[9990](CSS 폴백)을
  //   입히거나 네이티브 Fullscreen API로 그 래퍼만 top layer에 올린다. 셸이 소유한 이
  //   오버레이들은 그 래퍼의 형제라, z를 380/420/430으로 아무리 키워도 폴백에선 9990 밑에
  //   깔리고 네이티브에선 아예 화면 밖으로 밀렸다 — "크게 보려고" 누른 버튼이 정확히
  //   레이어 제어를 없애는 모순이었다. 같은 결함을 하단 선택바에서 '래퍼 안으로 이동'으로
  //   고친 선례(bottomDockSlot)를 셸 오버레이에 그대로 전파한다.
  //   ★앵커 계약: 래퍼는 비풀스크린 relative · CSS 폴백 fixed · 네이티브도 UA가 fixed로
  //   만들므로 absolute 자식의 기준(containing block)은 세 모드 모두에서 유지된다. 비풀스크린
  //   기준면만 '패널 컨테이너'→'지도 래퍼'로 바뀌어 p-2(8px)만큼 안쪽으로 들어오고, 지도 상단
  //   상태줄(로딩·미발견)이 뜨면 지도와 함께 내려간다 — 지도 위 컨트롤이 지도에 붙는 것이
  //   오히려 정상이라 좌표 계약(left-4/right-4/top-4/top-20)은 그대로 둔다.
  const mapOverlays = (
    <>
      <div
        /* ★침묵 데드존 봉합 — 이 칩바는 UX A3에서 자식을 전부 button→span으로 강등
           (허위 어포던스 제거)했는데 컨테이너의 pointer-events-auto는 남겨,
           **어포던스는 없애고 클릭 차단만 남은** 상태였다. 그 면적 위의 지도 클릭이
           무음으로 사라진다.
           ★R1 HIGH-4 재봉합: `pointer-events-auto`를 **빼는 것만으로는 no-op**이다 —
           이 속성의 초깃값이 `auto`이고, 조상 체인(mapOverlays 프래그먼트 → topRightSlot →
           wrapperClass("relative"))에 `pointer-events-none`이 하나도 없기 때문이다.
           그래서 `none`을 **직접** 건다. 인터랙티브 자식이 생기면 그 자식에만 `auto`. */
        {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveValue }}
        /* ★z 는 SSOT 상수를 **인라인 스타일**로 흘려보낸다 — Tailwind v4 는 런타임 문자열
           클래스(`z-[${값}]`)를 생성하지 못한다(satong-map-z.ts 사용 규칙). */
        style={{ zIndex: SATONG_UI_Z.badgeRow }}
        className="pointer-events-none absolute left-4 top-4 flex flex-wrap items-center gap-2"
      >
        {/* ★UX A3: 비인터랙티브 배지(허위 어포던스 제거) — 이전엔 <button>이었으나 onClick이
            event.stopPropagation() 뿐이라 클릭 가능해 보이는데 아무 동작도 없었다. */}
        <span className="rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] px-3 py-2 text-xs font-black text-[var(--text-primary)] shadow-[var(--shadow-lg)] backdrop-blur-[var(--glass-blur)]">
          사통팔땅 멀티지도
        </span>
        {/* ★UX 트랙 C2(사용자 지적 — '편의성 부조화'): 종전엔 이 칩이 <button>이라
            클릭하면 handleLayerClick이 호출돼 "레이어를 끄면서 동시에(방금 끈) 레이어의
            설정 팝오버를 여는" 이중 조작이 됐다(끈 레이어의 설정창이 뜨는 혼란). 레이어
            조작은 우상단 레일 하나로 일원화하고, 이 칩은 "지금 켜진 레이어"를 알려주는
            표시 전용 배지로 강등한다(A3에서 이미 배지화한 상단 라벨과 동일 계약). */}
        {activeLayers.slice(0, 4).map((layer) => (
          <span
            key={layer.id}
            className="rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg)] px-3 py-2 text-xs font-black text-[var(--text-primary)] shadow-[var(--shadow-md)] backdrop-blur-[var(--glass-blur)]"
            title={`${layer.label} 레이어 켜짐`}
          >
            {layer.label}
          </span>
        ))}
        {activeLayers.length > 4 && (
          <span className="rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg)] px-3 py-2 text-xs font-black text-[var(--text-primary)] shadow-[var(--shadow-md)] backdrop-blur-[var(--glass-blur)]">
            +{activeLayers.length - 4}
          </span>
        )}
      </div>

      <div
        ref={railRef}
        data-testid="map-layer-rail"
        // ★사용자 요청('롤아웃하면 창이 닫히고') + R1 MEDIUM-1: hover로 연 팝오버는
        //   레일을 벗어날 때 닫는다. 클릭으로 연 것은 유지해야 팝오버 안 컨트롤로
        //   마우스를 옮겨 확정할 수 있다(고정분은 pinnedPanelRef로 식별·유예 200ms는 팝오버가 취소).
        onMouseLeave={() => {
          // ★R1 3차 HIGH-1: '핀 존재'가 아니라 '지금 보이는 팝오버가 고정분인가'로
          //   판정한다. stale 핀(Esc/X로 닫힌 뒤 잔존)이 무관한 hover 팝오버를
          //   눌러붙게 하던 누수 봉합. (closeLayerPanel/Basemap이 핀을 지우므로
          //   이제 stale은 안 생기지만, 매칭 가드는 그와 무관히도 안전하다.)
          const shownIsPinned =
            pinnedPanelRef.current === "basemap"
              ? basemapOpen
              : pinnedPanelRef.current != null && activeLayerId === pinnedPanelRef.current;
          // 레일을 벗어나면 예약된 전환은 무효다(팝오버로 가는 중이면 팝오버가 취소한다).
          cancelHoverSwitch();
          if (shownIsPinned) return;
          cancelHoverClose();
          hoverCloseTimerRef.current = setTimeout(() => {
            hoverCloseTimerRef.current = null;
            const stillPinned =
              pinnedPanelRef.current === "basemap"
                ? basemapOpen
                : pinnedPanelRef.current != null && activeLayerId === pinnedPanelRef.current;
            if (stillPinned) return;
            setActiveLayerId(null);
            setBasemapOpen(false);
          }, 200); // ★HIGH-B 유예 — 팝오버 onMouseEnter가 취소한다
        }}
        // ★P1(감사): 고정고는 전 버튼 필요고보다 작아 하단(로드뷰 등)이 클리핑돼 도달
        //   불가였음 — 가용고 내 auto + 세로 스크롤로 전 버튼 접근 보장.
        // ★WP-M4: hover 전개에 더해 앵커 클릭 고정(railPinned)으로도 전개 — 터치 기기 대응.
        // ★U3(비반응형 레일): 상한을 컨테이너뿐 아니라 브라우저 뷰포트(dvh)로도 걸어,
        //   지도가 화면보다 클 때 레일이 폴드 밑으로 늘어나 하단 버튼 도달 불가·페이지
        //   스크롤 시 hover 전개가 풀리던 문제를 해소. 고정(핀) 시 2열 그리드로 접어
        //   버튼 높이를 절반으로 — 어떤 뷰포트에서도 전 버튼 가시(현 14개=7행·400px).
        //   dvh 상한은 supports- 가드로 부가(R1 L5: min() 인자에 미지원 단위가 섞이면
        //   선언 전체가 drop돼 상한이 사라짐) · 핀 폭 128px(48px 버튼×2+gap+p — R1 L4).
        // ★2026-07-23(R1 M): 접힌 높이 h-16(=버튼 1개)은 두 번째 자식인 베이스맵 버튼을
        //   숨겨, 터치 기기에서 배경지도 전환이 3탭(앵커→베이스맵→스와치)이 되고 기능
        //   존재 자체가 비가시였다(종전 하단 도크는 항상 가시·1탭). h-28로 앵커+베이스맵
        //   2개를 상시 노출해 1탭 경로를 복원한다(전개 어포던스인 앵커는 그대로 유지).
        // ★UX 트랙 C1(사용자 지적 — '편의성 부조화'): railPinned 기본값을 true로 바꿔
        //   대부분 이 분기 자체를 타지 않게 됐지만, 사용자가 명시적으로 접었을 때도
        //   h-28 overflow-hidden으로 14개 중 2개만 남기는 건 여전히 동일 결함이다.
        //   접힘 상태에서도 1열(단일 컬럼) 전체를 항상 노출하도록 높이 클리핑을 걷어내고
        //   가용고 내 세로 스크롤로 전 버튼 도달을 보장한다(hover 확장은 폭만 넓히는
        //   보조 어포던스로 격하 — 가시성 자체는 더 이상 hover에 의존하지 않는다).
        {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveValue }}
        /* ★종전 `z-[420]` 은 `SATONG_UI_Z.tileFailure` 와 **동률**이었다. 화면 결과(스크림이
           레일 위)는 옳았지만 그건 DOM 순서에서 나온 **우연**이었다 — 셸의 JSX 순서를 바꾸는
           리팩토링 하나로 조용히 뒤집힌다. 이제 `layerRail`(415)로 **값이 순서를 선언**한다. */
        style={{ zIndex: SATONG_UI_Z.layerRail }}
        className={`group absolute right-4 top-20 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg)] p-2 shadow-[var(--shadow-lg)] backdrop-blur-[var(--glass-blur)] transition-all duration-300 ease-in-out ${
          railPinned
            ? "grid w-32 auto-rows-min grid-cols-2 gap-2 h-auto max-h-[calc(100%-120px)] supports-[height:100dvh]:max-h-[min(calc(100%-120px),calc(100dvh-176px))] overflow-y-auto"
            : "flex w-16 flex-col gap-2 h-auto max-h-[calc(100%-120px)] supports-[height:100dvh]:max-h-[min(calc(100%-120px),calc(100dvh-176px))] overflow-y-auto"
        }`}
      >
        {/* 앵커(레이어 관리) 버튼 — ★WP-M4: 죽은 버튼을 클릭 고정 토글로 실기능화(터치 전개).
            아이콘은 MapIcon(지도), 지적도 레이어는 Layers로 분리해 아이콘-기능 1:1. */}
        <button
          type="button"
          onClick={() => {
            // ★레일 1↔2열 토글은 12개 버튼을 리플로우시켜 **마우스를 움직이지 않아도**
            //   커서 밑 아이콘이 바뀐다 → 예약된 전환이 무관한 레이어로 발화한다.
            //   '접기' 버튼이 조용히 팝오버를 갈아치우면 안 되므로 예약·닫힘을 먼저 거둔다.
            cancelHoverSwitch();
            cancelHoverClose();
            setRailPinned((v) => !v);
          }}
          aria-pressed={railPinned}
          aria-label={railPinned ? "레이어 목록 접기" : "레이어 목록 펼치기(고정)"}
          className={`grid size-12 shrink-0 place-items-center rounded-2xl border transition ${
            railPinned
              ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15 text-[var(--accent-strong)]"
              : "border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--accent-strong)] hover:bg-[var(--surface-strong)] group-hover:border-[var(--line-strong)] group-hover:bg-[var(--surface-muted)] group-hover:text-[var(--text-secondary)]"
          }`}
          title={railPinned ? "레이어 목록 고정 해제" : "지도 레이어 관리 (클릭 고정 · hover 전개)"}
        >
          <MapIcon className={`size-5 ${railPinned ? "" : "animate-pulse group-hover:animate-none"}`} aria-hidden />
        </button>

        {/* 베이스맵 — 지도 표시 제어를 우상단 한 코너로 모으는 항목(2026-07-23 사용자
            UX 요청). 종전엔 레일=우상단·베이스맵=우하단으로 제어가 분산돼 있었다. */}
        <button
          type="button"
          // ★레일 형제와 동일 계약 — 롤오버·포커스는 '열기'(지정), 클릭은 토글.
          //   전환 중 같은 항목 재진입이 닫힘이 되면 깜빡이므로 hover는 열기만 한다.
          onMouseEnter={() => requestHoverOpen("basemap", openBasemapPanel, basemapOpen)}
          onMouseLeave={cancelHoverSwitch}
          // ★형제와 동일 계약(HIGH-A) + R1 MEDIUM-C: setDetailFeature(null) 삭제
          //   (레이어 경로는 '가림→복원'인데 베이스맵만 파괴적이라 비대칭이었다).
          onClick={() => {
            cancelHoverClose();
            cancelHoverSwitch(); // 클릭 즉시 확정(형제와 동일 계약)
            const wasPinned = basemapOpen && pinnedPanelRef.current === "basemap";
            if (wasPinned) { closeBasemapPanel(); return; }
            pinnedPanelRef.current = "basemap";
            openBasemapPanel();
          }}
          aria-haspopup="dialog"
          aria-expanded={basemapOpen}
          aria-controls="satong-basemap-popover"
          aria-label="베이스맵 선택"
          title="베이스맵 (일반·위성·하이브리드·회색)"
          className={`grid size-12 shrink-0 place-items-center rounded-2xl border transition ${
            basemapOpen
              ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)] shadow-[var(--shadow-glow)]"
              : "border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--text-secondary)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-strong)]"
          }`}
        >
          <ImageIcon className="size-5" aria-hidden />
        </button>

        {/* 내부 레이어 버튼 리스트 (세로 전개) */}
        {LAYERS.map((layer) => {
          const Icon = layer.icon;
          const enabled = enabledLayers.has(layer.id);
          const isActive = activeLayerId === layer.id;
          return (
            <button
              key={layer.id}
              type="button"
              // ★열기만(확정 아님) — 롤오버·클릭 모두 미리보기 팝오버를 연다.
              //   터치엔 hover가 없으므로 탭(click)도 같은 동작이어야 한다.
              // ★R1 HIGH-1: onFocus는 제거한다 — Tab 이동만으로 팝오버가 연쇄 전환돼
              //   키보드 사용자가 팝오버 안의 확정 버튼에 영영 도달할 수 없었다(마지막
              //   레일 항목은 렌더불가라 on/off 자체가 없음). Enter/Space는 onClick을
              //   발화하므로 키보드 열기 경로는 그대로다.
              // ★전환 지연 경유(HOVER_SWITCH_DELAY_MS) — 팝오버로 가며 스쳐 지나가는
              //   왼쪽 열 아이콘이 목적 팝오버를 갈아치우지 않게 한다.
              onMouseEnter={() =>
                requestHoverOpen(layer.id, () => openLayerPanel(layer.id), activeLayerId === layer.id)
              }
              // 아이콘을 벗어나면 대기 중이던 전환은 취소한다(지나간 것은 의도가 아니다).
              onMouseLeave={cancelHoverSwitch}
              // ★R1 LOW-1: 클릭은 토글 — 레일에서 팝오버를 닫을 수단이 사라졌던 회귀
              //   복원. 깜빡임 논거는 hover에만 유효하고 click에는 적용되지 않는다.
              // ★R1 HIGH-A: 실브라우저는 click 앞에 mouseenter를 반드시 보낸다. 종전
              //   'activeLayerId===id면 닫기'는 hover로 열린 것을 '클릭으로 연 것'으로
              //   오인해 첫 클릭이 항상 닫기가 됐다(더블클릭해야 사용 가능). 클릭은
              //   hover분을 닫지 말고 '고정(pin)'으로 승격하고, 이미 고정된 것만 닫는다.
              onClick={() => {
                cancelHoverClose();
                cancelHoverSwitch(); // 클릭은 즉시 확정 — 예약 전환이 뒤늦게 덮어쓰지 않게
                const wasPinned = activeLayerId === layer.id && pinnedPanelRef.current === layer.id;
                if (wasPinned) { closeLayerPanel(); return; }
                pinnedPanelRef.current = layer.id;
                openLayerPanel(layer.id);
              }}
              aria-haspopup="dialog"
              aria-expanded={activeLayerId === layer.id}
              title={`${layer.label} — 미리보기 열기 (지도 적용은 팝오버에서)`}
              className={`flex min-h-12 w-full shrink-0 flex-col items-center justify-center gap-0 rounded-2xl border px-1 py-1.5 text-[var(--text-secondary)] transition ${
                // ★R1 MEDIUM-5: 채움=적용됨(enabled), 링=선택 중(isActive). 종전엔
                //   미적용 미리보기에 가장 강한 채움이 배정돼 "보기=적용" 오해를
                //   시각 층에서 되살리고 있었다.
                enabled
                  ? `border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)] ${isActive ? "ring-2 ring-[var(--accent-strong)] ring-offset-2 ring-offset-[var(--surface)]" : ""}`
                  : isActive
                    ? "border-[var(--accent-strong)] bg-[var(--surface-panel)] text-[var(--accent-strong)] ring-2 ring-[var(--accent-strong)]"
                    : "border-[var(--border-muted)] bg-[var(--surface-panel)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-strong)]"
              }`}
              aria-label={layer.label}
            >
              {/* 펼침(w-32)에서는 아이콘 밑에 2글자 캡션을 노출한다.
                  ★무라벨 아이콘 12개는 hover가 없는 터치 기기에서 기능을 알 방법이
                    '하나씩 탭'뿐이었다. shortLabel은 이미 12개 전부 정의돼 있는데
                    소비처가 0이라 방치돼 있던 자산 — 새 카피 없이 발견성을 회복한다. */}
              <Icon className="size-5" aria-hidden />
              {railPinned && (
                <span className="mt-0.5 text-[10px] font-bold leading-none">
                  {layer.shortLabel}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* 베이스맵 팝오버 — 레일 '베이스맵' 버튼이 여는 패널. 레이어 팝오버와 같은
          좌표 계약(right-20 top-20)이라 상호배타로 열린다.
          이력: 독립 absolute 섬(~07-16) → 하단 도크(07-17 겹침 단일화) → 레일 팝오버(07-23).
          칩 행의 암묵 예약값(152px)은 07-17에 제거됐고 되살리지 않는다(겹침 수정 유지). */}
      {basemapOpen && (
        <div
          ref={basemapPopoverRef}
          id="satong-basemap-popover"
          role="dialog"
          aria-label="베이스맵"
          // ★팝오버에 도달했다 = 사용자의 목적지다 → 대기 중이던 전환을 취소한다.
          //   이게 없으면 지나온 아이콘의 예약 전환이 뒤늦게 발화해 팝오버가 바뀐다.
          onMouseEnter={() => { cancelHoverClose(); cancelHoverSwitch(); }}
          onMouseLeave={() => { if (pinnedPanelRef.current !== "basemap") setBasemapOpen(false); }}
          className={`absolute ${railPopoverAnchor(railPinned)} top-20 z-[430] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] p-4 shadow-[var(--shadow-xl)] backdrop-blur-xl max-h-[calc(100%-120px)] supports-[height:100dvh]:max-h-[min(calc(100%-120px),calc(100dvh-176px))] overflow-y-auto`}
        >
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-lg font-black text-[var(--text-primary)]">베이스맵</h3>
            <button
              type="button"
              onClick={closeBasemapPanel}
              aria-label="베이스맵 닫기"
              /* ★모바일 IA P2 — size-8(32px)은 44px 터치 타깃 하한 미달이었다. 지도 위 팝오버라
                 빗나간 탭이 지도 클릭으로 새므로 정확도가 특히 중요하다. grid+place-items-center
                 라 min-h/min-w 를 더해도 아이콘은 가운데 그대로다(시각 변화는 상자 크기뿐). */
              className="grid size-8 min-h-11 min-w-11 place-items-center rounded-xl border border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--text-secondary)] transition hover:bg-[var(--surface-strong)]"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
          {basemapSwitcherPanel}
          <p className="mt-3 text-xs font-bold text-[var(--text-tertiary)]">
            배경 지도를 바꿔도 선택 필지·레이어는 유지됩니다.
          </p>
        </div>
      )}

      {activeLayer && (
        <div
          ref={popoverRef}
          role="dialog"
          aria-label={activeLayer.label}
          // ★팝오버 도달 = 목적지 → 대기 중이던 전환 취소(위 베이스맵 팝오버와 동일 계약).
          onMouseEnter={() => { cancelHoverClose(); cancelHoverSwitch(); }}
          onMouseLeave={() => { if (pinnedPanelRef.current !== activeLayer.id) setActiveLayerId(null); }}
          className={`absolute ${railPopoverAnchor(railPinned)} top-20 z-[430] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] p-4 shadow-[var(--shadow-xl)] backdrop-blur-xl max-h-[calc(100%-120px)] supports-[height:100dvh]:max-h-[min(calc(100%-120px),calc(100dvh-176px))] overflow-y-auto`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-black ${statusClass(activeLayer.status)}`}>
                  {statusText(activeLayer.status)}
                </span>
                <span className="text-[11px] font-black uppercase tracking-[0.16em] text-[var(--on-surface-muted)]">
                  Layer
                </span>
              </div>
              <h3 className="mt-2 text-lg font-black text-[var(--text-primary)]">{activeLayer.label}</h3>
            </div>
            <div className="flex items-center gap-1">
              {/* ★확정(commit) 지점 — 레일에서 강제 토글을 걷어낸 대신, 레이어 자체
                  on/off를 여기에 둔다(끄기 수단 보존). 렌더 불가 레이어는 노출하지
                  않는다(지도에 반영되지 않으므로 켜기 약속이 거짓이 된다). */}
              {isRenderableSatongMapLayer(activeLayer.id) && !LAYERS_WITHOUT_POPOVER_TOGGLE.has(activeLayer.id) && (
                <button
                  type="button"
                  onClick={() => toggleLayerEnabled(activeLayer.id)}
                  aria-pressed={enabledLayers.has(activeLayer.id)}
                  /* ★모바일 IA P2 — py-1.5+text-xs ≈ 28px 로 44px 하한 미달이었다.
                     inline-flex+items-center 로 라벨을 세로 가운데 고정한 뒤 히트 영역만 넓힌다. */
                  className={`inline-flex min-h-11 items-center rounded-xl border px-3 py-1.5 text-xs font-black transition ${
                    enabledLayers.has(activeLayer.id)
                      ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)]"
                      : "border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]/40 hover:text-[var(--accent-strong)]"
                  }`}
                  title={enabledLayers.has(activeLayer.id) ? "지도에서 이 레이어 끄기" : "지도에 이 레이어 켜기"}
                >
                  {enabledLayers.has(activeLayer.id) ? "지도 표시 중" : "지도에 표시"}
                </button>
              )}
              <button
                type="button"
                onClick={closeLayerPanel}
                /* ★모바일 IA P2 — p-2(8px) + 아이콘 16px = 32px 라 44px 하한 미달이었다.
                   inline-grid + place-items-center 로 아이콘을 가운데 고정한 뒤 히트 영역만 넓힌다. */
                className="inline-grid min-h-11 min-w-11 place-items-center rounded-full p-2 text-[var(--text-hint)] transition hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
                aria-label="레이어 설정 닫기"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
          </div>
          <p className="mt-2 text-sm font-semibold leading-6 text-[var(--text-secondary)]">
            {activeLayer.description}
          </p>
          <div className="mt-4 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3">
            <p className="text-[11px] font-black uppercase tracking-[0.18em] text-[var(--on-surface-muted)]">
              Source
            </p>
            <p className="mt-1 text-sm font-bold text-[var(--text-secondary)]">{activeLayer.source}</p>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {activeLayer.controls.map((control) => {
              // ★R1 후속(레인G R2): 전월세(kind-rent) 모드에서는 토지·상업업무용 전월세
              //   API 자체가 없다(MARKET_RENT_TYPES=4종) — 켜봐야 무의미한 유형 토글을
              //   비활성화해 "눌러도 0건"이라는 오도적 UX를 원천 차단한다(marketLayer의
              //   kind 필터와 이중 방어).
              const rentModeActive =
                activeLayer.id === "transactions" &&
                (layerControls.transactions ?? []).includes("kind-rent");
              const rentUnsupported =
                rentModeActive &&
                control.id.startsWith("type-") &&
                !MARKET_RENT_TYPES.some((t) => `type-${t.key}` === control.id);
              const effectiveMapEffect = control.mapEffect && !rentUnsupported;
              return (
                <button
                  key={control.id}
                  type="button"
                  disabled={!effectiveMapEffect}
                  onClick={() => handleLayerControlClick(activeLayer.id, control)}
                  title={
                    rentUnsupported
                      ? "전월세는 아파트·연립다세대·단독다가구·오피스텔만 지원합니다(토지·상업업무용 전월세 API 없음)"
                      : control.mapEffect
                        ? `${control.label} 지도 반영`
                        : control.description || "공식 데이터 소스 연결 후 활성화"
                  }
                  /* ★모바일 IA P2 — py-2+text-xs ≈ 32px 로 미달이었다(팝오버를 연 상태의 전수
                     검사가 적발 — 닫힌 상태만 보면 이 칩들은 DOM 에 아예 없다). */
                  className={`inline-flex min-h-11 items-center rounded-2xl border px-3 py-2 text-xs font-black transition ${
                    layerControls[activeLayer.id]?.includes(control.id) && !rentUnsupported
                      ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)]"
                      : effectiveMapEffect
                        ? "border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10 hover:text-[var(--accent-strong)]"
                        : "cursor-not-allowed border-[var(--border-muted)] bg-[var(--surface-muted)] text-[var(--text-hint)]"
                  }`}
                >
                  {control.label}
                </button>
              );
            })}
          </div>
          {!isRenderableSatongMapLayer(activeLayer.id) ? (
            <div className="mt-4 rounded-2xl bg-[var(--status-warning)]/10 px-3 py-2 text-xs font-bold leading-5 text-[var(--status-warning)]">
              이 레이어는 아직 공식 데이터 소스와 지도 렌더러가 연결되지 않아 지도에 표시하지 않습니다.
            </div>
          ) : activeLayer.status !== "active" && (
            <div className="mt-4 rounded-2xl bg-[var(--status-warning)]/10 px-3 py-2 text-xs font-bold leading-5 text-[var(--status-warning)]">
              선택 필지의 실제 속성 데이터가 확보된 범위에서만 지도에 반영됩니다. 무자료 필지는 추정 표시하지 않습니다.
            </div>
          )}
        </div>
      )}

      {/* ── WS-C 필지 상세 패널 — 개요·보유 속성(무자료 '-' 정직표기)·산출물 원클릭 퍼널.
           레이어 패널과 같은 슬롯(상호 배타 — 단일 팝오버 원칙). ── */}
      {/* ★렌더 가드도 3패널 전부를 배타 — 상태 봉합(근원 함수)과 이중 방어. 좌표가
          같은 형제가 늘 때 가드가 따라오지 않으면 겹침이 다시 샌다(07-17 교훈). */}
      {detailFeature && !activeLayer && !basemapOpen && (
        <div
          data-testid="parcel-detail-panel"
          className={`absolute ${railPopoverAnchor(railPinned)} top-20 z-[430] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] p-4 shadow-[var(--shadow-xl)] backdrop-blur-xl max-h-[calc(100%-120px)] supports-[height:100dvh]:max-h-[min(calc(100%-120px),calc(100dvh-176px))] overflow-y-auto`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <span className="text-[11px] font-black uppercase tracking-[0.16em] text-[var(--on-surface-muted)]">
                Parcel
              </span>
              <h3 className="mt-1 flex text-lg font-black text-[var(--text-primary)]">
                <ParcelJibunLabel address={detailFeature.address} pnu={detailFeature.pnu} />
              </h3>
              <p className="truncate text-xs font-semibold text-[var(--text-hint)]">{detailFeature.address}</p>
            </div>
            <button
              type="button"
              onClick={() => setDetailFeature(null)}
              /* ★모바일 IA P2 — 위 두 닫기 버튼과 동일(32px → 44px 히트 영역). */
              className="inline-grid min-h-11 min-w-11 shrink-0 place-items-center rounded-full p-2 text-[var(--text-hint)] transition hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
              aria-label="필지 상세 닫기"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>

          {/* ★W1 지배 제약 — 필지 상세 최상단("무엇이 발목인가"에 한 줄로 답). 서버가 제약
               0건이면 null을 주고 컴포넌트도 null이면 렌더하지 않는다(빈 배너 금지). */}
          <DominantConstraintBanner constraint={detailFeature.dominantConstraint} />

          <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3 text-xs">
            <div>
              <dt className="font-black text-[var(--text-hint)]">면적</dt>
              <dd className="mt-0.5 font-mono font-bold text-[var(--text-primary)]">{formatArea(detailFeature.areaSqm, 0)}</dd>
            </div>
            <div>
              <dt className="font-black text-[var(--text-hint)]">용도지역</dt>
              <dd className="mt-0.5 font-bold text-[var(--text-primary)]">
                {detailFeature.zoneType || "-"}
                {detailFeature.zoneType2 ? ` · ${detailFeature.zoneType2}` : ""}
              </dd>
            </div>
            <div>
              <dt className="font-black text-[var(--text-hint)]">지목</dt>
              <dd className="mt-0.5 font-bold text-[var(--text-primary)]">{detailFeature.jimok || "-"}</dd>
            </div>
            <div>
              <dt className="font-black text-[var(--text-hint)]">개별공시지가</dt>
              <dd className="mt-0.5 font-mono font-bold text-[var(--text-primary)]">
                {detailFeature.officialPricePerSqm
                  ? `${Math.round(detailFeature.officialPricePerSqm).toLocaleString()}원/㎡`
                  : "-"}
              </dd>
            </div>
            <div>
              <dt className="font-black text-[var(--text-hint)]">건물 노후도</dt>
              <dd className="mt-0.5 font-bold text-[var(--text-primary)]">
                {detailFeature.buildingAgeYears != null
                  ? `${detailFeature.buildingAgeYears}년${detailFeature.builtYear ? ` (준공 ${detailFeature.builtYear})` : ""}`
                  : detailFeature.ageStatus === "no_building"
                    // ★단정하지 않는다(2026-08-23) — 백엔드는 이 상태를 "나대지 **추정**"으로
                    //   분류하고, 같은 근거(`lookup_state=="no_data"`)에서 연면적은 보수적으로
                    //   `None`(=현황 용적률 "미확보")으로 둔다. 화면만 "건물 없음"이라 단정하면
                    //   한 화면이 같은 사실을 두고 **확신과 모름을 동시에** 말한다.
                    //   집합건물 대지권 비대표지번·대장 미등재·생성지연에서도 무자료가 나온다.
                    ? "나대지 추정(건축물대장 무자료)"
                    : detailFeature.ageStatus === "no_approval_date"
                      ? "사용승인일 미기재(연식 미상)" // ★R1: 백엔드 4번째 상태 — 나대지와 구분(정직)
                      : detailFeature.ageStatus === "lookup_failed"
                        ? "조회 실패"
                        : detailFeature.ageStatus === "skipped_bulk"
                          ? "대량 선택 생략"
                          : "-"}
              </dd>
            </div>
            <div>
              <dt className="font-black text-[var(--text-hint)]">PNU</dt>
              <dd className="mt-0.5 truncate font-mono font-bold text-[var(--text-secondary)]" title={detailFeature.pnu || undefined}>
                {detailFeature.pnu || "-"}
              </dd>
            </div>
            {/* ── I7 규제 요약 — 실효 한도·현황·개발여력 인라인(경계 응답 서버 산정치 —
                 분석캐시 불요·#387). 미산정 '-' 정직 표기, 전항 미상이면 안내 1줄.
                 상세 산출·근거는 아래 퍼널의 '종합 부지분석'이 담당(중복 CTA 배제). ── */}
            <div className="col-span-2 border-t border-[var(--border-muted)] pt-2">
              <dt className="font-black text-[var(--text-hint)]">규제 요약(실효 한도 — 7계층 min)</dt>
              <dd className="mt-1 grid grid-cols-3 gap-x-2 text-center">
                <div>
                  <p className="text-[10px] font-bold text-[var(--text-hint)]">실효 용적률</p>
                  <p className="font-mono font-bold text-[var(--text-primary)]">
                    {formatPercent(detailFeature.effectiveFarPct)}
                  </p>
                  {/* ★근거 병기(2026-08-23 · 사용자 신고) — 종전엔 실효값만 보여, 보전관리지역에
                      "60%" 만 뜨고 그것이 **법정 80% 를 조례가 깎은 값**이라는 사실이 없었다.
                      사용자는 값이 틀렸다고 신고했지만 값은 정확했다 — 없던 것은 **근거**다.
                      법정값이 실효와 같으면 병기하지 않는다(같은 수를 두 번 보여 주지 않는다). */}
                  {detailFeature.legalFarPct != null
                    && detailFeature.legalFarPct !== detailFeature.effectiveFarPct && (
                    <p
                      data-testid="far-basis-note"
                      className="mt-0.5 text-[9px] font-semibold leading-tight text-[var(--text-hint)]"
                    >
                      법정 {formatPercent(detailFeature.legalFarPct)}
                      {detailFeature.farBasis ? ` · ${detailFeature.farBasis}` : ""}
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-[10px] font-bold text-[var(--text-hint)]">실효 건폐율</p>
                  <p className="font-mono font-bold text-[var(--text-primary)]">
                    {formatPercent(detailFeature.effectiveBcrPct)}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-[var(--text-hint)]">현황 용적률</p>
                  <p className="font-mono font-bold text-[var(--text-primary)]">
                    {formatPercent(detailFeature.currentFarPct)}
                  </p>
                </div>
              </dd>
              {(() => {
                const ratio = capacityRatio(detailFeature.effectiveFarPct, detailFeature.currentFarPct);
                if (ratio == null) {
                  return detailFeature.effectiveFarPct == null && detailFeature.effectiveBcrPct == null && detailFeature.currentFarPct == null ? (
                    <p className="mt-1 text-[10px] font-semibold text-[var(--text-hint)]">
                      산정 자료 미확보 — 용도지역·건축물대장 확보 시 자동 표시(상세는 아래 종합 부지분석)
                    </p>
                  ) : null;
                }
                return (
                  <p className={`mt-1 font-mono text-[11px] font-black ${ratio < 0 ? "text-[#a855f7]" : "text-[var(--status-success)]"}`}>
                    {ratio < 0
                      // ★R1 MAJOR: -ratio*100은 '실효 대비 상대%'라 %p 라벨이 오독(초과 절반
                      //   과소 표기 — 200/260에서 "30%p"로 읽힘). 용적률 초과는 점차이가 관행:
                      //   현황−실효 = 진짜 %p(260−200=60%p). ratio<0이면 두 값 모두 non-null.
                      ? `한도 초과 — 현황이 실효 한도를 ${formatPercentPoint((detailFeature.currentFarPct as number) - (detailFeature.effectiveFarPct as number))} 상회`
                      : `개발여력 ${formatPercent(ratio * 100)} (실효 대비 잔여)`}
                  </p>
                );
              })()}
            </div>

            {/* ★W2 경사도 — 온디맨드(표고 원천 1req/s·서버 무캐시라 명시적 요청).
                 값·한계 문구는 전부 서버 산정(terrain/analyze)이고 여기선 표시만 한다. */}
            <ParcelLayoutSection
              status={layoutStatus}
              result={layoutResult}
              errorMessage={layoutError}
              selectedOption={layoutSelectedOption}
              selectedKey={
                layoutOptionKey ??
                (layoutSelectedOption ? siteLayoutOptionKey(layoutSelectedOption) : null)
              }
              otherRequestInFlight={layoutBusy && layoutStatus !== "loading"}
              onRequest={requestParcelLayout}
              onSelectOption={setLayoutOptionKey}
              onSeedDesign={handleSeedDesign}
            />

            <ParcelSlopeSection
              status={slopeStatus}
              result={slopeResult}
              errorMessage={slopeError}
              // ★다른 필지 조회가 진행 중임을 고지 — 전역 1건 잠금이라 눌러도 무시되는데
              //   아무 피드백이 없으면 "죽은 버튼"으로 보인다(R2 권고 2).
              otherRequestInFlight={slopeBusy && slopeStatus !== "loading"}
              onRequest={requestParcelSlope}
            />

            {detailFeature.officialPricePerSqm && detailFeature.areaSqm ? (
              <div className="col-span-2 border-t border-[var(--border-muted)] pt-2">
                <dt className="font-black text-[var(--text-hint)]">공시지가 총액(참고 — 공시지가×면적)</dt>
                <dd className="mt-0.5 font-mono font-bold text-[var(--accent-strong)]">
                  {Math.round((detailFeature.officialPricePerSqm * detailFeature.areaSqm) / 10_000).toLocaleString()}만원
                </dd>
              </div>
            ) : null}
          </dl>

          {/* 원클릭 산출물 퍼널 — Output Dock과 동일 공용통로(handleOutputClick: 프로젝트 연결 규약 유지) */}
          <p className="mt-3 text-[11px] font-black uppercase tracking-[0.18em] text-[var(--on-surface-muted)]">
            이 선택으로 바로 실행
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {outputActions.map((action) => {
              // ★UX A4(동일 패턴 전파): 이 미니 퍼널은 Output Dock과 달리 사유 문구가
              //   아예 없었다(opacity만) — aria-disabled+title+캡션을 동일하게 인접 배치.
              const miniDisabled = selectedParcels.length === 0;
              return (
                <button
                  key={action.id}
                  type="button"
                  disabled={miniDisabled}
                  aria-disabled={miniDisabled}
                  title={miniDisabled ? "필지를 하나 이상 선택하면 산출물 생성 경로가 활성화됩니다." : undefined}
                  onClick={() => void handleOutputClick(action)}
                  /* ★모바일 IA P2(R1 봉합) — px-3 py-2 ≈ 32px 미달이었다. **과금·LLM 이 걸린 산출물
                     실행 버튼**이라 오탭 비용이 닫기 버튼보다 크다. text-left 를 유지해야 해서
                     flex-col+justify-center 로 세로 가운데 정렬한 뒤 하한만 건다. */
                  className="flex min-h-11 flex-col justify-center rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2 text-left text-xs font-black text-[var(--text-primary)] transition hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {action.label}
                  {miniDisabled && (
                    <span className="mt-0.5 flex items-center gap-1 text-[9px] font-bold underline decoration-dotted underline-offset-2">
                      <AlertTriangle className="size-2.5 shrink-0" aria-hidden />
                      필지 선택 필요
                    </span>
                  )}
                </button>
              );
            })}
            {/* I3: 카카오 로드뷰(현장 확인) — URL 계약 라이브 검증(302→파노라마). 좌표 없으면 미표시(정직). */}
            {(() => {
              const roadview = kakaoRoadviewUrl(detailFeature.lat, detailFeature.lon);
              return roadview ? (
                <a
                  href={roadview}
                  target="_blank"
                  rel="noopener noreferrer"
                  /* ★모바일 IA P2(R2 봉합) — 바로 위 미니 퍼널 4종과 **같은 그리드**인데 이것만
                     32px 로 남아 44/44/44/44 아래 32 한 행이 붙는 상태였다. 터치 타깃 하한에
                     button/a 구분은 없다(불변식 셀렉터도 a[href] 로 넓혔다). */
                  className="col-span-2 inline-flex min-h-11 flex-col justify-center rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2 text-left text-xs font-black text-[var(--text-primary)] transition hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10"
                >
                  <span className="inline-flex items-center gap-1">
                    <Route className="size-3.5" aria-hidden />카카오 로드뷰로 현장 보기 ↗
                  </span>
                </a>
              ) : null;
            })()}
          </div>
          <p className="mt-3 font-mono text-[9px] text-[var(--text-hint)]">
            출처 VWorld·국토교통부 공간정보 — 무자료 항목은 &quot;-&quot;로 표기(추정 금지)
          </p>
        </div>
      )}
    </>
  );

  return (
    <section className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface)] p-4 shadow-[var(--shadow-lg)] md:p-5">
      {/* ★UX 트랙 B2 — 집계 SSOT 단일표면. sticky로 앱 헤더(top-2·z-1000) 바로 아래 고정해
          지도셸을 아래로 스크롤해도 프로젝트·주소·PNU·용도지역·대지면적이 계속 보이게 한다.
          아래 로컬 "합산 면적" 배지는 여기로 흡수되어 제거됨(격리 표면 4→1). "필지 선택 N건"은
          지도 조작 직후 즉시 피드백(선택 반응성 계약 — connectTargetLeak.test.tsx)이라 유지. */}
      {/* ★z-[600] = SATONG_CONTENT_Z.stickyContextHeader (위 접힘 경로와 동일 계약). */}
      {showContextHeader && (
        <ContextHeader sitePipeline className="sticky top-[var(--app-header-offset)] z-[600] mb-4" />
      )}
      <div className="mb-4 flex flex-col gap-3 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-panel)] p-4 shadow-[var(--shadow-sm)] lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="font-[family-name:var(--font-display)] label-caps text-[var(--text-tertiary)]">
            Satong Map OS
          </p>
          {/* ★UX 트랙 B1 — 이 페이지(들)의 문서 개요 h1은 히어로/온보딩 h1이 담당한다.
              지도셸은 상위 h1에 종속된 섹션 제목이므로 h2로 강등(스크린리더·문서 개요 위계 정합). */}
          <h2 className="mt-2 text-2xl font-black tracking-normal text-[var(--text-primary)] md:text-3xl">
            지도 위에서 입력부터 산출물 생성까지 이어갑니다.
          </h2>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-[var(--text-secondary)]">
            지번·주소 검색, 엑셀 다필지 등록, 지도 선택, 레이어 검토를 한 화면에 통합했습니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-[var(--r-pill)] bg-[var(--accent-soft)] px-3 py-2 text-xs font-black text-[var(--accent-strong)]">
            필지 선택 {selectedParcels.length}건
          </span>
        </div>
      </div>

      {/* ★선택 무결성 고지 — 합계를 "통합 대지면적"이라 부르기 전에 전제를 말한다.
          정상이면 아무것도 그리지 않는다(고지 남발은 무시로 이어진다). */}
      {integrityNotice && (
        <div
          data-testid="selection-integrity-notice"
          role="status"
          className={`mt-3 flex items-start gap-2 rounded-[var(--r-card)] border px-3 py-2.5 text-xs font-semibold leading-5 ${
            integrityNotice.tone === "bad"
              ? "border-[var(--status-error)]/30 bg-[var(--status-error)]/10 text-[var(--status-error)]"
              : "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]"
          }`}
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <b className="font-black">{integrityNotice.title}</b>
            <span className="ml-1 font-semibold">{integrityNotice.detail}</span>
          </span>
        </div>
      )}

      <div className="grid min-w-0 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        {/* ★모바일 IA P0(2026-08-05) — 종전 D2(모바일 지도우선)의 `order-2/order-1`을 철회한다.
            D2는 "좌패널이 길어 지도까지 스크롤해야 한다"를 풀려고 <xl 에서 시각 순서만 뒤집었는데,
            그 대가로 **이 페이지의 유일한 진입 행동인 주소 입력이 지도 아래로 내려갔다**
            (라이브 390×844 실측: 입력 도달까지 2.6화면 — 데스크톱 0.9화면의 3배).
            사용자 지적("모바일에서 주소 입력을 못 찾겠다")이 정확히 이 역전이다.

            ★CSS order 를 쓰지 않고 DOM 순서 자체로 배치한다 — 같은 앱이 이미 그 정책을 세워 뒀다
            (ComprehensiveAnalysisPanel 의 관점별 스토리라인: "CSS order로 시각만 바꾸면 화면
            읽기 순서와 스크린리더 읽기 순서가 어긋난다"). 한 앱에 두 정책이 공존하던 것을 하나로 모은다.

            ★뷰포트 조건부 렌더가 아니라 **단순 제거**인 이유: 데스크톱은 종전에도 `xl:order-none`
            (=DOM 순서)이라 무변화이고, 모바일도 원하는 순서가 같은 '입력 먼저'다 — 두 뷰포트의
            목표 순서가 동일하므로 미디어쿼리 훅도, xl 경계 리마운트 위험도 만들 필요가 없다.
            지도가 아래로 밀리는 양은 유계다: 가변 길이인 선택 필지 목록이 max-h-[360px]로 봉인돼 있다. */}
        <aside className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-panel)] p-4 shadow-[var(--shadow-sm)]">
          <div className="rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-secondary)] p-4 text-[var(--text-primary)] shadow-[var(--shadow-md)]">
            <p className="font-[family-name:var(--font-display)] label-caps text-[var(--accent-strong)]">
              Parcel Intake
            </p>
            <h2 className="mt-2 text-xl font-black tracking-normal">통합 필지 입력</h2>
            <p className="mt-2 text-xs font-semibold leading-5 text-[var(--text-secondary)]">
              검색하면 지도 중심이 이동하고, 엑셀을 올리면 다필지 목록이 같은 선택 목록으로 합쳐집니다.
            </p>
          </div>

          {/* 프로젝트 연결 */}
          <div className="mt-4 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3.5">
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-black text-[var(--text-primary)]">
              <Building2 className="size-4 text-[var(--accent-strong)]" aria-hidden />
              연결 프로젝트
            </label>
            <select
              value={connectTarget}
              onChange={(e) => handleConnectTargetChange(e.target.value)}
              className="w-full rounded-[var(--r-input)] border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2.5 text-xs font-bold text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            >
              <option value="new">새 프로젝트로 등록 (기본)</option>
              <option value="none">프로젝트 연결 안 함 (약식 분석)</option>
              <optgroup label="기존 프로젝트에 연결">
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.address ? ` — ${p.address}` : ""}
                  </option>
                ))}
              </optgroup>
            </select>
            {connectTarget === "none" && (
              <p className="mt-2 text-[11px] font-bold leading-4 text-[var(--text-hint)]">
                산출물은 프로젝트에 저장되지 않습니다.
              </p>
            )}
            {connectNotice && (
              <p className="mt-2 rounded-lg bg-[var(--status-success)]/10 px-2.5 py-1.5 text-[11px] font-bold leading-4 text-[var(--status-success)]">
                {connectNotice}
              </p>
            )}
          </div>

          <div className="mt-4 space-y-3">
            <div className="relative">
              <label className="mb-2 flex items-center gap-2 text-xs font-black text-[var(--text-primary)]">
                <Search className="size-4 text-[var(--accent-strong)]" aria-hidden />
                지번·주소 검색
              </label>
              {/* ★UX 트랙 C6(사용자 지적): WAI-ARIA 콤보박스형 자동완성 패턴 배선 — 종전엔
                  listbox/option·aria-activedescendant·방향키 핸들러가 전혀 없었고(스크린
                  리더에 "후보 있음"이 전달 안 됨), Enter는 하이라이트와 무관하게 항상 1번
                  후보를 확정했다. 드롭다운 위치도 top-[78px] 하드코딩(라벨 높이가 바뀌면
                  어긋남)이라 이 행(입력+버튼) 자체를 relative 기준으로 top-full로 바꿔 제거한다.
                  ★role="combobox"는 의도적으로 붙이지 않는다 — 같은 화면의 "연결 프로젝트"
                  네이티브 <select>가 이미 암묵 role="combobox"라, 이 input에도 붙이면
                  screen.getByRole("combobox")(연결 프로젝트 select 대상, 9개 기존 계약
                  테스트 — connectTargetLeak·detailPanel 등)가 "2개 발견"으로 깨진다.
                  aria-autocomplete="list"+aria-controls+aria-activedescendant만으로도
                  자동완성 의미 전달·키보드 내비는 동일하게 보장되며(aria-expanded는 애초
                  textbox 역할엔 미지원 속성이라 함께 제외), listbox/option 쪽 접근성은
                  그대로 완비된다. */}
              <div className="relative flex gap-2">
                <input
                  aria-controls={searchListboxId}
                  aria-autocomplete="list"
                  aria-activedescendant={
                    activeCandidateIndex >= 0 ? `${searchListboxId}-option-${activeCandidateIndex}` : undefined
                  }
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    const visibleCount = Math.min(searchCandidates.length, 6);
                    if (visibleCount > 0) {
                      if (event.key === "ArrowDown") {
                        event.preventDefault();
                        setActiveCandidateIndex((prev) => (prev + 1) % visibleCount);
                        return;
                      }
                      if (event.key === "ArrowUp") {
                        event.preventDefault();
                        setActiveCandidateIndex((prev) => (prev <= 0 ? visibleCount - 1 : prev - 1));
                        return;
                      }
                      if (event.key === "Home") {
                        event.preventDefault();
                        setActiveCandidateIndex(0);
                        return;
                      }
                      if (event.key === "End") {
                        event.preventDefault();
                        setActiveCandidateIndex(visibleCount - 1);
                        return;
                      }
                      if (event.key === "Escape") {
                        event.preventDefault();
                        setSearchCandidates([]);
                        return;
                      }
                    }
                    if (event.key === "Enter") {
                      handleSearchSubmit(activeCandidateIndex >= 0 ? activeCandidateIndex : undefined);
                    }
                  }}
                  placeholder="예: 의정부동 224, 판교역로 166"
                  className="min-w-0 flex-1 rounded-full border border-[var(--border-muted)] bg-[var(--surface-strong)] px-4 py-3 text-sm font-bold text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:bg-[var(--surface-panel)] focus:ring-4 focus:ring-[var(--accent-soft)]"
                />
                <button
                  type="button"
                  onClick={() => handleSearchSubmit()}
                  disabled={!query.trim() || searchStatus === "loading"}
                  className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-[var(--accent-strong)] text-[var(--on-primary)] shadow-[var(--shadow-glow)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
                  aria-label="검색 추가"
                >
                  {searchStatus === "loading" ? (
                    <Loader2 className="size-5 animate-spin" aria-hidden />
                  ) : (
                    <ChevronRight className="size-5" aria-hidden />
                  )}
                </button>
                {searchCandidates.length > 0 && (
                  <ul
                    role="listbox"
                    id={searchListboxId}
                    aria-label="주소 후보"
                    className="absolute left-0 right-14 top-full z-[650] mt-1 overflow-hidden rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] shadow-[var(--shadow-xl)]"
                  >
                    {searchCandidates.slice(0, 6).map((candidate, index) => {
                      const label = getCandidateLabel(candidate);
                      const active = index === activeCandidateIndex;
                      return (
                        <li
                          key={`${label}-${index}`}
                          id={`${searchListboxId}-option-${index}`}
                          role="option"
                          aria-selected={active}
                          onMouseDown={(event) => event.preventDefault()} // 클릭해도 input 포커스를 유지(콤보박스 계약)
                          onMouseEnter={() => setActiveCandidateIndex(index)}
                          onClick={() => void handleCandidatePick(candidate)}
                          className={`flex w-full cursor-pointer items-start gap-3 border-b border-[var(--line)] px-4 py-3 text-left last:border-0 ${
                            active ? "bg-[var(--surface-strong)]" : "hover:bg-[var(--surface-strong)]"
                          }`}
                        >
                          <MapPin className="mt-0.5 size-4 shrink-0 text-[var(--accent-strong)]" aria-hidden />
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-black text-[var(--text-primary)]">
                              {label}
                            </span>
                            <span className="mt-0.5 block text-xs font-semibold text-[var(--text-hint)]">
                              {candidate.kind || candidate.pnu || "주소 후보"}
                            </span>
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              {searchError && (
                <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-[var(--status-error)]">
                  <AlertTriangle className="size-3.5" aria-hidden />
                  {searchError}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                /* ★모바일 IA P2 — py-3+text-xs ≈ 40px 로 44px 하한에 살짝 못 미쳤다(진단서 목록엔
                   없던 건 — 전수 불변식이 찾아냈다). */
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-3 text-xs font-black text-[var(--text-primary)] transition hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10"
              >
                {uploadStatus === "loading" ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <FileSpreadsheet className="size-4 text-[var(--accent-strong)]" aria-hidden />
                )}
                엑셀 파일 선택
              </button>
              <button
                type="button"
                onClick={handleTemplateDownload}
                /* ★모바일 IA P2 — py-3+text-xs ≈ 40px 로 44px 하한에 살짝 못 미쳤다(진단서 목록엔
                   없던 건 — 전수 불변식이 찾아냈다). */
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-3 text-xs font-black text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)]"
              >
                <Download className="size-4" aria-hidden />
                양식 다운로드
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={handleExcelUpload}
              />
            </div>
            {/* ★UX 트랙 C4: 최대 180초 걸리는 업로드 — 스피너 1개뿐이던 걸 단계표시(기존
                AnalysisPipelineStepbar 재사용)+경과초(실측)+취소로 보강한다. */}
            {uploadStatus === "loading" && (
              <div className="space-y-2">
                <AnalysisPipelineStepbar steps={uploadPipelineSteps} title="엑셀 업로드 처리 중" />
                <div className="flex items-center justify-between gap-2 text-[11px] font-bold text-[var(--text-hint)]">
                  <span>{uploadElapsedSec}초 경과 · 최대 180초</span>
                  <button
                    type="button"
                    onClick={cancelExcelUpload}
                    /* ★모바일 IA P2 — py-1+text-[11px] ≈ 24px 로 이 파일에서 가장 작았다.
                       업로드가 최대 180초 도는 동안 **유일한 중단 수단**이라 놓치면 3분을 기다린다. */
                    className="inline-flex min-h-11 shrink-0 items-center rounded-full border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-1 text-[11px] font-black text-[var(--text-secondary)] transition hover:border-[var(--status-error)]/40 hover:text-[var(--status-error)]"
                  >
                    업로드 취소
                  </button>
                </div>
              </div>
            )}
            <UseLlmToggle
              checked={useLlm}
              onChange={setUseLlm}
              label="AI 보조 인식"
              hint="비표준 양식(다중시트·전치·복합셀) 자동 구조분석"
              disabled={uploadStatus === "loading"}
              className="px-1"
            />
            {uploadNote && (
              <p
                className={`rounded-2xl px-3 py-2 text-xs font-bold ${
                  uploadStatus === "error"
                    ? "bg-[var(--status-error)]/10 text-[var(--status-error)]"
                    : "bg-[var(--status-success)]/10 text-[var(--status-success)]"
                }`}
              >
                {uploadNote}
              </p>
            )}
            {verificationReport && (
              <div className="space-y-2 rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] p-3">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-black text-[var(--text-primary)]">업로드 검증 리포트</h4>
                  {verificationReport.llm_used && (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[var(--ai-accent)]/15 px-2 py-0.5 text-[10px] font-black text-[var(--ai-accent)]">
                      <Bot className="size-3" aria-hidden /> LLM 보조 사용
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className="rounded-full bg-[var(--status-success)]/15 px-2 py-1 text-[11px] font-black text-[var(--status-success)]">
                    확인됨 {verificationReport.counts?.verified ?? 0}
                  </span>
                  <span className="rounded-full bg-[var(--status-info)]/15 px-2 py-1 text-[11px] font-black text-[var(--status-info)]">
                    보정됨 {verificationReport.counts?.corrected ?? 0}
                  </span>
                  <span className="rounded-full bg-[var(--status-warning)]/15 px-2 py-1 text-[11px] font-black text-[var(--status-warning)]">
                    확인필요 {verificationReport.counts?.needs_review ?? 0}
                  </span>
                  <span className="rounded-full bg-[var(--surface-muted)] px-2 py-1 text-[11px] font-black text-[var(--text-secondary)]">
                    제외 {verificationReport.counts?.excluded ?? 0}
                  </span>
                </div>
                {/* ★H3: 확인필요 행도 일단 주입되며, 주입 후 2차 조회에서 자동보정을 시도한다는
                    것을 명확히 안내(과거엔 이 자기치유 경로가 자동반영 제외로 조용히 끊겼었음). */}
                {(verificationReport.counts?.needs_review ?? 0) > 0 && (
                  <p className="text-[11px] font-semibold text-[var(--status-warning)]">
                    확인필요 행은 주입 후 자동보정 시도됩니다 — 아래 사유를 확인해 주세요.
                  </p>
                )}
                {(verificationReport.corrections?.length ?? 0) > 0 && (
                  <p className="text-[11px] font-semibold text-[var(--status-info)]">
                    보정 {verificationReport.corrections?.length}건 —{" "}
                    {(verificationReport.corrections ?? [])
                      .slice(0, 3)
                      .map((c) => `${c.field ?? "필드"}: ${c.before ?? "-"}→${c.after ?? "-"}`)
                      .join(" · ")}
                    {(verificationReport.corrections?.length ?? 0) > 3
                      ? ` 외 ${(verificationReport.corrections?.length ?? 0) - 3}건`
                      : ""}
                  </p>
                )}
                {uploadParcels.filter((p) => p.verification_status === "needs_review").length > 0 && (
                  <ul className="space-y-1">
                    {uploadParcels
                      .filter((p) => p.verification_status === "needs_review")
                      .slice(0, 8)
                      .map((p, i) => (
                        <li
                          key={`${p.address ?? p.jibun ?? p.pnu ?? "row"}-${i}`}
                          className="rounded-lg bg-[var(--status-warning)]/10 px-2 py-1.5 text-[11px] font-semibold text-[var(--status-warning)]"
                        >
                          {joinAddressJibun(p.address, p.jibun, p.pnu || `행 ${i + 1}`)} —{" "}
                          {(p.verification_reasons ?? []).join(" · ") || "확인 필요"}
                        </li>
                      ))}
                  </ul>
                )}
                {(verificationReport.warnings?.length ?? 0) > 0 && (
                  /* ★모바일 IA P0 의 논거 보강(R1 지적 L2) — "order 를 지워 지도가 아래로 밀려도
                     밀림은 유계"라는 근거가 성립하려면 이 패널의 가변 블록이 전부 유계여야 한다.
                     검색후보 slice(0,6)·검증대상 slice(0,8)·보정 slice(0,3)·선택필지 max-h-[360px]
                     는 이미 봉인돼 있는데 **이 경고 목록만 무계**였다(엑셀 업로드 시 수십 건 가능).

                     ★절단이 아니라 **유계 스크롤**로 푼다(R2 지적 HIGH). 초판은 slice(0,5) + "외 N건 —
                     전체는 업로드 결과 파일에서 확인하세요"였는데, **그런 결과 파일은 존재하지 않는다**:
                     parse-parcels 응답은 JSON 전용(ParseParcelsResponse)이고 이 화면의 다운로드는
                     업로드용 템플릿과 '선택된 필지' export 둘뿐이라, 선택에 못 들어간 행에 대한 경고는
                     어느 파일에도 없다. 절단을 정직하게 고지하려던 문장이 **없는 회수 경로를 약속**해
                     침묵보다 나쁜 오도가 됐다 — 화면 밖을 가리키는 문구는 그 경로가 실재할 때만 쓴다.
                     max-h + overflow-y-auto 는 밀림을 유계로 만들면서 **전체 도달성도 보존**한다
                     (같은 파일 선택 필지 목록 max-h-[360px] 와 동일 관용구). */
                  <ul className="max-h-[120px] space-y-1 overflow-y-auto">
                    {(verificationReport.warnings ?? []).map((w, i) => (
                      <li key={i} className="text-[11px] font-semibold text-[var(--status-error)]">
                        {w}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* 선택 필지로 새 프로젝트 생성 — 작업 순서(검색→필지 선택→생성)상 지번·주소/엑셀
              입력 아래, 선택 필지 목록 직전에 둔다. 핸들러·조건은 무변경(JSX 재배치만). */}
          {connectTarget === "new" && selectedParcels.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] font-bold leading-4 text-[var(--text-hint)]">
                완료(등록)·산출물 실행 시 &apos;{deriveProjectNameFromParcels(selectedParcels) ?? "새 프로젝트"}&apos; 프로젝트가 자동 생성됩니다.
              </p>
              <button
                type="button"
                onClick={handleCreateProjectNow}
                disabled={creatingProject}
                /* ★모바일 IA P2(R1 봉합) — px-3 py-2 ≈ 32px 미달이었다. */
                className="mt-2 inline-flex min-h-11 w-full items-center justify-center rounded-[var(--r-input)] border border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 px-3 py-2 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-strong)]/15 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creatingProject ? "생성 중…" : "선택 필지로 새 프로젝트 생성"}
              </button>
            </div>
          )}

          <div className="mt-5 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-black text-[var(--text-primary)]">선택 필지</h3>
                <p className="mt-1 text-xs font-semibold text-[var(--text-hint)]">
                  검색·엑셀·지도 선택이 같은 목록으로 통합됩니다.
                </p>
              </div>
              {selectedParcels.length > 0 && (
                <div className="flex items-center gap-1.5">
                  {/* I5: 선택 필지 GeoJSON 내보내기 — 측량·타 GIS 연계(기하 없는 필지는 제외 정직 고지) */}
                  <button
                    type="button"
                    onClick={() => exportSelection("geojson")}
                    title="선택 필지를 GeoJSON(FeatureCollection)으로 내려받기"
                    className="inline-flex min-h-11 items-center justify-center rounded-full border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-1.5 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--accent-strong)]"
                  >
                    GeoJSON
                  </button>
                  <button
                    type="button"
                    onClick={() => exportSelection("kml")}
                    title="선택 필지를 KML(구글어스·측량 호환)로 내려받기 — V3"
                    className="inline-flex min-h-11 items-center justify-center rounded-full border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-1.5 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--accent-strong)]"
                  >
                    KML
                  </button>
                  <button
                    type="button"
                    onClick={clearParcels}
                    className="inline-flex min-h-11 items-center justify-center rounded-full border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-1.5 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--status-error)]"
                  >
                    초기화
                  </button>
                </div>
              )}
            </div>
            {exportNote && (
              <p className="mt-2 text-[11px] font-bold text-[var(--text-hint)]">{exportNote}</p>
            )}

            <div className="mt-3 max-h-[360px] space-y-2 overflow-auto pr-1">
              {selectedParcels.length === 0 ? (
                <div className="rounded-[var(--r-panel)] border border-dashed border-[var(--line-strong)] bg-[var(--surface-panel)] px-4 py-10 text-center">
                  <MapPin className="mx-auto size-8 text-[var(--text-hint)]" aria-hidden />
                  <p className="mt-3 text-sm font-black text-[var(--text-primary)]">
                    아직 선택된 필지가 없습니다.
                  </p>
                  <p className="mt-1 text-xs font-semibold text-[var(--text-hint)]">
                    검색하거나 지도에서 필지를 선택하세요.
                  </p>
                </div>
              ) : (
                // ★U4(카드 과점): 지번 전문·PNU 행이 차지하던 공간 압축 — 1줄 헤더(짧은
                //   지번+면적)+칩 1줄. 전체 주소·PNU는 hover title로 보존(정보 손실 없음).
                selectedParcels.map((parcel, index) => (
                  // 카드 클릭 = 상세 패널 + 지도 포커스(좌표 보유 시) — 카드-지도 연동(WS-C).
                  <div
                    key={`${parcel.id}-${index}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      const feature =
                        selectedMapFeatures.find(
                          // ★같은 동 주소의 다른 필지로 지도가 튀던 자리 — 판정은 한 곳(`isSameParcel`).
                          (f) => isSameParcel(f, parcel),
                        ) ??
                        ({
                          id: parcel.id,
                          address: parcel.address,
                          pnu: parcel.pnu ?? null,
                          areaSqm: parcel.areaSqm ?? null,
                          zoneType: parcel.zoneType ?? null,
                          jimok: parcel.jimok ?? null,
                          source: parcel.source,
                        } satisfies SatongMapFeature);
                      openFeatureDetail(feature);
                      if (feature.lat != null && feature.lon != null) {
                        setFocusTarget({ lat: feature.lat, lon: feature.lon, label: parcel.address });
                      }
                    }}
                    onKeyDown={(e) => {
                      // ★R1: 중첩 삭제버튼에서의 keydown 버블링이 카드 활성(상세 열기)으로
                      //   번지지 않게 target 가드, Space 스크롤은 preventDefault.
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        e.currentTarget.click();
                      }
                    }}
                    className="cursor-pointer rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2 shadow-[var(--shadow-sm)] transition hover:border-[var(--accent-strong)]/40"
                    title={`${parcel.address}${parcel.pnu ? ` · PNU ${parcel.pnu}` : ""} — 클릭: 상세 정보`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      {/* ★인라인 축약(`slice(-2)`)을 걷어낸다 — 먼저 줄이면 동 단위 주소에서
                          지번을 붙일 자리가 사라져 77행이 전부 같은 글자가 됐다(신고 화면 ①). */}
                      <p className="min-w-0 flex-1 text-[13px] font-black text-[var(--text-primary)]">
                        <ParcelJibunLabel address={parcel.address} pnu={parcel.pnu} fallback={parcel.address} />
                      </p>
                      <span className="shrink-0 font-mono text-[11px] font-bold text-[var(--text-secondary)]">
                        {formatArea(parcel.areaSqm, 0)}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation(); // 삭제가 카드 클릭(상세 열기)으로 번지지 않게
                          removeParcel(parcel.id);
                        }}
                        className="grid size-11 shrink-0 place-items-center rounded-full text-[var(--text-hint)] transition hover:bg-[var(--status-error)]/10 hover:text-[var(--status-error)]"
                        aria-label="필지 제거"
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </button>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1 text-[10px] font-bold">
                      <span className="rounded-full bg-[var(--accent-strong)]/10 px-2 py-0.5 text-[var(--accent-strong)]">
                        {sourceLabel[parcel.source]}
                      </span>
                      {parcel.zoneType && (
                        <span className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--text-secondary)]">
                          {parcel.zoneType}
                        </span>
                      )}
                      {parcel.jimok && (
                        <span className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--text-secondary)]">
                          지목 {parcel.jimok}
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </aside>

        {/* 지도 — DOM 순서상 입력(aside) 다음. order 클래스 금지(위 aside 주석의 정책). */}
        <section className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-panel)] p-3 shadow-[var(--shadow-sm)] md:p-4">
          <div
            className="relative overflow-hidden rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--background-deep)]"
            style={{ minHeight: SATONG_MAP_HEIGHT }}
          >
            <div className="p-2">
              <SatongMultiMap
                onPickMany={handleMapPickMany}
                onFeatureClick={openFeatureDetail}
                focusTarget={focusTarget}
                autoPreviewFocus
                height={SATONG_MAP_HEIGHT}
                chrome="immersive"
                selectedParcels={selectedMapFeatures}
                layerState={mapLayerState}
                marketPayload={marketEnabled ? marketPayload : null}
                marketRadiusM={marketRadiusM}
                onMarketRadiusChange={setMarketRadiusM}
                // ★무목업: 종전 가상 분양단지/경매물건(Math.random) 목업을 실데이터 state로 대체.
                // 분양=/presale/nearby(청약홈)·경매=/auction/search+geocode(온비드) — 위 이펙트에서 조회.
                // (계산은 marketLayerValue로 컴포넌트 상단에서 훅 규칙에 맞게 끌어올려짐 — UX 트랙 B4.)
                marketLayer={marketLayerValue}
                // 상태 노트는 marketLayer 밖 별도 prop — 노트만 바뀔 때 마커 이펙트가 재실행되지
                // 않게 한다(리뷰 LOW). 건수 라벨보다 우선 표기(정직원칙).
                presaleNote={presaleEnabled ? presaleNote || null : null}
                auctionNote={auctionEnabled ? auctionNote || null : null}
                poiPayload={poiEnabled ? poiPayload : null}
                developmentPayload={developmentEnabled ? developmentPayload : null}
                onCenterChange={setMapCenter}
                layoutOverlay={layoutOverlay}
              layoutNorthLightSetbackM={layoutSelectedOption?.north_light_setback_m ?? null}
              layoutNorthLightHeightM={layoutSelectedOption?.height_m ?? null}
                onBoundaryEnriched={handleBoundaryEnriched}
                onBoundaryStatusChange={handleBoundaryStatusChange}
                clearSignal={clearNonce}
                onStagedCountChange={setStagedCount}
                // ★H2: 오버레이(배지행·레일·팝오버 3종)를 지도 래퍼 '안'에서 렌더시켜
                //   풀스크린(z-9990)에서도 레이어 제어가 남게 한다. 종전엔 래퍼의 형제라
                //   z(380~430)가 낮아 전부 사라졌고, 큰 화면에서 레이어를 보려는 버튼이
                //   정작 레이어 제어를 없애는 모순이었다.
                topRightSlot={mapOverlays}
              />
            </div>
          </div>

          <div className="mt-3 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-elevated)] p-3 text-[var(--text-primary)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[var(--accent-strong)]">
                  Output Dock
                </p>
                <h3 className="mt-1 text-lg font-black">선택 필지로 만들 산출물</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsOutputDockOpen((value) => !value)}
                /* ★모바일 IA P2 — py-2+text-xs ≈ 32px 로 미달이었다(진단서 목록 밖 — 전수 불변식 적발).
                   산출물 독을 여닫는 유일한 토글이라 놓치면 산출물 목록에 접근할 수 없다. */
                className="inline-flex min-h-11 shrink-0 items-center rounded-full border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-black text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)]"
              >
                {isOutputDockOpen ? "접기" : "열기"}
              </button>
            </div>
            {isOutputDockOpen && (
              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                {outputActions.map((action) => {
                  const Icon = action.icon;
                  const disabled = selectedParcels.length === 0;
                  // ★UX A4: 비활성 사유를 opacity만이 아니라 버튼 안에 인접 배치(제목/aria-disabled/캡션)
                  //   — 이전엔 사유 문구가 그리드 아래 별도 문단으로 분리돼 시각적으로 끊겨 있었다.
                  const disabledReason = "필지를 하나 이상 선택하면 산출물 생성 경로가 활성화됩니다.";
                  return (
                    <button
                      key={action.id}
                      type="button"
                      onClick={() => void handleOutputClick(action)}
                      disabled={disabled}
                      aria-disabled={disabled}
                      title={disabled ? disabledReason : undefined}
                      className={`min-h-[112px] rounded-[var(--r-panel)] border p-3 text-left transition ${action.tone} ${
                        disabled ? "cursor-not-allowed opacity-50" : "hover:-translate-y-0.5 hover:shadow-xl"
                      }`}
                    >
                      <Icon className="size-5" aria-hidden />
                      <span className="mt-4 block text-sm font-black">{action.label}</span>
                      <span className="mt-1 block text-xs font-bold opacity-70">{action.description}</span>
                      {disabled && (
                        // 색은 버튼 자체 tone의 text-* 상속(각 tone이 이미 자기 배경 대비 검증된
                        // 색을 지정)에 맡기고, 밑줄+굵기로만 사유 캡션임을 구분한다 — 새 색을
                        // 얹으면 tone별 배경(accent-strong 등)과의 대비가 깨질 수 있어서다.
                        <span className="mt-1.5 flex items-center gap-1 text-[10px] font-bold underline decoration-dotted underline-offset-2">
                          <AlertTriangle className="size-2.5 shrink-0" aria-hidden />
                          필지 선택 필요
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
            {selectedParcels.length === 0 && (
              <p className="mt-3 text-xs font-semibold text-[var(--text-hint)]">
                필지를 하나 이상 선택하면 산출물 생성 경로가 활성화됩니다.
              </p>
            )}
          </div>

          {/* 공공데이터 고지(DESIGN.md B1) — 지도/산출물 데이터 뷰 하단 공용 컴포넌트. */}
          <DataSourceNotice
            source="VWorld·국토교통부·공공데이터포털"
            note="참고용 · 법적 효력 없음"
          />
        </section>
      </div>
    </section>
  );
}

export default SatongMapShell;
