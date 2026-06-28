"use client";

/**
 * 글로벌 주소 검색 컴포넌트 — 단일/다필지 입력 지원.
 *
 * 카카오 주소 검색 API로 주소를 입력하면:
 * 1. PNU 자동 추출 (VWORLD PARCEL 지오코딩)
 * 2. ProjectContextStore에 저장 (Single Source of Truth)
 * 3. 전체 모듈에 자동 반영 (Once-and-Done Input)
 *
 * UX 원칙:
 * - Single Source of Truth (NN/G EAS Framework)
 * - Once-and-Done Input (Chrome 연구: 25% 완료율 향상)
 * - Progressive Disclosure (Jakob Nielsen, 1995)
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { AlertTriangle, BarChart3, Building2, Landmark, MapPin, Search } from "lucide-react";
import { KakaoAddressSearch, type KakaoAddressResult } from "@/components/ui/KakaoAddressSearch";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient, apiV1BaseUrl } from "@/lib/api-client";
import { scheduleSnapshotSync } from "@/lib/projectSync";
import { LandShareModal } from "@/components/operations/LandShareModal";
import { dynamicMap, MapShell } from "@/components/common/MapShell";
import type { ParcelAtPointResult } from "@/components/map/ParcelPickerMap";

// 지도 클릭 필지 선택 컴포넌트 — SSR 없이 동적 로드(Leaflet은 window 필요)
const ParcelPickerMapDynamic = dynamicMap(
  () => import("@/components/map/ParcelPickerMap"),
  { pick: "ParcelPickerMap", height: 360, loadingMessage: "필지 선택 지도 로딩…" },
);

// 행 불변 식별자 — 객체 spread({...a})로 보존되므로 참조 교체에 영향받지 않는 안정 매칭 키.
let _uidSeq = 0;
function newUid(): string {
  _uidSeq += 1;
  return `p${_uidSeq}_${Math.floor(Math.random() * 1e6)}`;
}

// 특이부지(개발 부적합·후순위 대상) 판정 — 다필지에서 '대표' 필지를 고를 때 입력 순서가 아니라
//   개발가능성 우선으로 정렬하기 위한 진단 헬퍼. 두 신호를 합친다:
//   (1) 백엔드 enrich가 준 specialParcel.is_special(학교용지·GB·맹지 등 게이트 결과 — 가장 신뢰).
//   (2) 지목(jimok)이 도로·구거·하천·제방·유지·철도·학교·공원·전·답·임야·산림 등 '단독개발 부적합'.
//   둘 중 하나라도 해당하면 후순위. (백엔드 게이트가 아직 안 왔어도 지목만으로 1차 차단.)
const SPECIAL_JIMOK_KEYWORDS = [
  "도로", "구거", "하천", "제방", "유지", "철도", "철도용지", "수도용지",
  "학교", "학교용지", "공원", "유원지", "묘지", "종교용지", "사적지",
  "전", "답", "과수원", "목장용지", "임야", "산림", "광천지", "염전",
];
function _isSpecialParcel(opts: { jimok?: string | null; isSpecial?: boolean | null }): boolean {
  // (1) 백엔드 게이트 결과가 명시적으로 특이부지면 즉시 후순위.
  if (opts.isSpecial === true) return true;
  // (2) 지목 키워드 매칭 — 공백 제거 후 정확 일치 우선, 없으면 부분 포함도 검사
  //     (예 "도로" 단독·"철도용지"). '대' '공장용지' '창고용지' 등 개발 가능 지목은 비대상.
  const j = (opts.jimok || "").replace(/\s+/g, "");
  if (!j) return false;
  return SPECIAL_JIMOK_KEYWORDS.some((kw) => j === kw || j.includes(kw));
}

export interface AddressEntry {
  __uid?: string; // 행 불변 식별자(토지정보 보강 매칭용)
  fullAddress: string;
  jibunAddress: string;
  roadAddress: string;
  sido: string;
  sigungu: string;
  bname: string;
  zonecode: string;
  bcode: string; // 법정동 코드 (10자리) — PNU 구성에 사용
  areaSqm?: number; // 면적 (m²) — 공공데이터(공부상) 우선. API에서 자동 반영
  areaPyeong?: number; // 면적 (평) — 자동 환산
  areaInputSqm?: number; // 엑셀 입력 면적(비권위·참고용) — 공부상과 크게 다르면 보존
  areaWarning?: string | null; // 엑셀 입력↔공부상 면적 괴리 경고(공부상 채택했음을 정직 고지)
  // ── 필지별 토지정보(/zoning/parcels-info 일괄 보강) — 등록된 모든 필지가 갖는다 ──
  pnu?: string; // PNU(19자리)
  zoneCode?: string; // 용도지역
  bcrPct?: number; // 건폐율 — 실효값(조례 반영, 단일분석과 일치)
  farPct?: number; // 용적률 — 실효값(조례 반영, 단일분석과 일치)
  bcrLegalPct?: number; // 건폐율 법정상한(보조 라벨용)
  farLegalPct?: number; // 용적률 법정상한(보조 라벨용)
  // ── 특이부지(임야·산지/농지/GB/맹지/학교용지 등) — 단일분석과 동일 게이트 요약 ──
  specialParcel?: {
    is_special?: boolean;
    developability?: string | null;
    resolvable?: string | null;
    severity_label?: string | null;
    factors?: string[];
    warning?: string | null;
    honest_disclosure?: string | null;
  } | null;
  jimok?: string; // 지목(형질)
  officialPrice?: number; // 개별공시지가(원/㎡)
  // ── 집합건물(공동주택·빌라) 플래그 — 호실/대지지분 안내용 ──
  isAggregate?: boolean;
  buildingName?: string;
  mainPurpose?: string;
  unitCount?: number;
  // 토지정보 보강 결과. partial = PNU는 확보했으나 용도지역 등 일부 미확보(재보강 가능).
  infoStatus?: "ok" | "partial" | "ambiguous" | "failed";
}

/** 종합 토지분석 결과 요약 — onAnalyzed 콜백으로 전달(store 비기록 모드에서도 면적 자동채움 등 유지) */
export interface AddressAnalysisSummary {
  address: string;
  pnu: string | null;
  landAreaSqm: number | null;
  zoneCode: string | null;
  effectiveBcr: number | null;
  effectiveFar: number | null;
  dataSource: string | null;
}

interface GlobalAddressSearchProps {
  /** 단일 필지만 허용 */
  single?: boolean;
  /** 주소 변경 시 콜백 */
  onChange?: (addresses: AddressEntry[]) => void;
  /** 추가 CSS */
  className?: string;
  /** placeholder */
  placeholder?: string;
  /** 비활성화 */
  disabled?: boolean;
  /** 초기 주소 (스토어에서 가져온 값 사전 표시) */
  initialAddress?: string;
  /**
   * WP-D: ProjectContextStore(SSOT) 기록 여부 — 기본 true(기존 동작 불변).
   * false면 store에 일절 기록하지 않고 onChange/onAnalyzed 콜백으로만 데이터를 전달한다
   * (활성 프로젝트와 무관한 검색이 updateSiteAnalysis→withSnap 스냅샷을 오염시키는 사슬 차단).
   */
  writeToContext?: boolean;
  /** 종합 토지분석 도착 시 콜백 — writeToContext=false 소비자(PreCheck 등)의 면적 자동채움용 */
  onAnalyzed?: (analysis: AddressAnalysisSummary) => void;
}

export function GlobalAddressSearch({
  single = false,
  onChange,
  className = "",
  placeholder = "주소를 검색하세요",
  disabled = false,
  initialAddress,
  writeToContext = true,
  onAnalyzed,
}: GlobalAddressSearchProps) {
  const [addresses, setAddresses] = useState<AddressEntry[]>(() => {
    if (initialAddress) {
      return [{ __uid: newUid(), fullAddress: initialAddress, jibunAddress: "", roadAddress: "", sido: "", sigungu: "", bname: "", zonecode: "", bcode: "" }];
    }
    return [];
  });
  const [isSearching, setIsSearching] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  // 다음(Daum) 팝업 외부제어 — 통합검색에서 '건물명·아파트로 찾기' 보조링크로만 연다.
  const [kakaoOpen, setKakaoOpen] = useState(false);
  // 지번 직접검색(VWorld) — Daum이 못 찾는 지번·산·농지 등을 직접 입력으로 해석.
  const [directQuery, setDirectQuery] = useState("");
  const [directBusy, setDirectBusy] = useState(false);
  const [directMsg, setDirectMsg] = useState("");
  // 토지지번검색(자동완성) — 타이핑하면 후보를 띄워 선택(다음 주소검색 UX).
  type AddrCandidate = { address: string; road_address?: string; pnu?: string | null; lat?: number | null; lon?: number | null; kind?: string };
  const [candidates, setCandidates] = useState<AddrCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [showCandidates, setShowCandidates] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeq = useRef(0); // 응답 경합 가드: 마지막 요청만 반영(stale 응답 무시)
  const [shareParcel, setShareParcel] = useState<AddressEntry | null>(null); // 호실/대지지분 모달 대상
  const enrichSeq = useRef(0); // 토지정보 보강 응답 경합 가드(stale 머지 차단)
  // WP-D: store 비기록 모드(writeToContext=false)의 요약 표시·콜백용 로컬 분석값.
  const [localAnalysis, setLocalAnalysis] = useState<AddressAnalysisSummary | null>(null);
  // 지도 클릭 필지 선택 패널 표시 여부(다필지 모드 전용)
  const [showMapPicker, setShowMapPicker] = useState(false);
  // 수동 재보강 진행중인 필지 uid 집합 — 버튼 '조회중…' 표시 + 중복클릭 가드(이중요청 방지).
  const [rerunningUids, setRerunningUids] = useState<Set<string>>(new Set());
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 로컬 state가 있으면 그것을 표시, 없으면 빈 상태 (siteAnalysis 참조 제거 — 새 프로젝트 시 이전 데이터 잔류 방지)
  const displayAddresses = addresses;

  // 다필지 표시용 행 데이터 — 지번(번지) 우선 + 면적/평 + 상태(면적확보/보완필요).
  // 대량(수백 필지) 가독성: 요약 헤더 + 스크롤 컴팩트 리스트로 일목요연하게.
  const parcelRows = useMemo(() =>
    displayAddresses.map((a) => {
      // 라벨 = 법정동(소재지)+지번이 모두 보이게. 엑셀(소재지·지번 분리 양식)은 jibunAddress가
      //   번지만("211-443")이라 법정동이 빠진다 → fullAddress가 그 번지를 포함하고 더 길면
      //   fullAddress("서울특별시 동작구 상도동 211-443")를 쓴다. 검색분(도로명 fullAddress)은
      //   지번을 포함하지 않으므로 jibunAddress(지번) 유지.
      const jb = (a.jibunAddress || "").trim();
      const full = (a.fullAddress || "").trim();
      const label = (full && jb && full.includes(jb) && full.length > jb.length)
        ? full
        : (jb || full);
      return {
        label: label || "(주소 미상)",
        areaSqm: a.areaSqm ?? null,
        areaInputSqm: a.areaInputSqm ?? null,
        areaWarning: a.areaWarning ?? null,
        zoneCode: a.zoneCode ?? null,
        bcrPct: a.bcrPct ?? null,
        farPct: a.farPct ?? null,             // 실효값(조례 반영)
        bcrLegalPct: a.bcrLegalPct ?? null,   // 건폐율 법정상한(보조 표기)
        farLegalPct: a.farLegalPct ?? null,   // 용적률 법정상한(보조 표기)
        specialParcel: a.specialParcel ?? null,
        jimok: a.jimok ?? null,
        isAggregate: a.isAggregate ?? false,
        unitCount: a.unitCount ?? null,
        pnu: a.pnu ?? null,
        entry: a,
      };
    }), [displayAddresses]);

  const parcelStats = useMemo(() => {
    const n = parcelRows.length;
    const withArea = parcelRows.filter((r) => r.areaSqm && r.areaSqm > 0);
    const totalSqm = withArea.reduce((s, r) => s + (r.areaSqm || 0), 0);
    // 지역(시군구) 수 — "시 구" 앞 2토큰 기준
    const regions = new Set(parcelRows.map((r) => r.label.split(" ").slice(0, 2).join(" ")).filter(Boolean));
    return { n, withAreaCnt: withArea.length, needFixCnt: n - withArea.length, totalSqm, regionCnt: regions.size };
  }, [parcelRows]);

  // ★표시용 '대표' 필지 — enrichParcels의 SSOT 기록과 동일한 개발가능성 우선 정렬을 미러링한다
  //   (입력 순서 valid[0] 아님). 부지분석/하류는 통합값을 쓰고, 대표는 '표시용 폴백'임을 명확히
  //   하기 위한 라벨·지목·특이여부만 계산한다. 단일필지/유효<2면 null(기존 단일표시 무회귀).
  const repInfo = useMemo(() => {
    const usable = parcelRows
      .filter((r) => r.areaSqm && r.areaSqm > 0)
      .map((r) => ({
        label: r.label,
        area: r.areaSqm || 0,
        jimok: r.jimok || "",
        special: _isSpecialParcel({ jimok: r.jimok, isSpecial: r.specialParcel?.is_special }),
      }));
    if (usable.length < 2) return null; // 다필지(유효 2+)에서만 대표 개념 적용
    const sorted = [...usable].sort((a, b) => {
      if (a.special !== b.special) return a.special ? 1 : -1;
      return b.area - a.area;
    });
    const rep = sorted.find((p) => !p.special) ?? sorted[0];
    const allSpecial = sorted.every((p) => p.special); // 전 필지 특이 → 대표도 특이(경고)
    return { label: rep.label, jimok: rep.jimok, area: rep.area, isSpecial: rep.special, allSpecial, count: usable.length };
  }, [parcelRows]);

  // 종합 토지 분석 자동 트리거 (주소 입력 즉시 백그라운드 실행)
  // 카카오에서 얻은 bcode(법정동코드) + 지번주소를 백엔드에 전달하여 토지정보 조회
  const triggerComprehensiveAnalysis = useCallback(async (address: string, bcode?: string, jibunAddress?: string) => {
    // WP-D race 가드: 트리거 시점의 활성 projectId 캡처 — 응답 도착 시
    // 불일치(분석 중 프로젝트 전환)면 store 기록을 중단해 오염을 차단한다.
    const triggeredProjectId = useProjectContextStore.getState().projectId;
    setIsAnalyzing(true);
    try {
      const data = await apiClient.post<{
        pnu: string | null;
        coordinates: { lat: number; lon: number } | null;
        zone_type: string | null;
        zone_limits: { max_bcr_pct: number; max_far_pct: number } | null;
        land_register: { land_category: string; area_sqm: number; official_price_per_sqm: number } | null;
        building_info: { building_name: string; main_purpose: string; total_area_sqm: number; ground_floors: number } | null;
        official_prices: Array<{ pnu: string; year: number; price_per_sqm: number }>;
        local_ordinance: { sido: string; sigungu: string | null; effective_bcr: number; effective_far: number; source: string } | null;
      }>("/zoning/comprehensive", {
        body: { address, bcode: bcode ?? "", jibun_address: jibunAddress ?? "" },
        useMock: false,
      });

      const analyzedAreaSqm = data.land_register?.area_sqm
        ?? (data as Record<string, unknown>).land_area_sqm as number | undefined
        ?? null;

      // 로컬 요약/콜백 — store와 무관하게 전달(비기록 모드의 면적 자동채움 등 기존 동작 유지).
      const summary: AddressAnalysisSummary = {
        address,
        pnu: data.pnu ?? null,
        landAreaSqm: analyzedAreaSqm,
        zoneCode: data.zone_type ?? null,
        effectiveBcr: data.local_ordinance?.effective_bcr ?? null,
        effectiveFar: data.local_ordinance?.effective_far ?? null,
        dataSource: "백엔드 API (bcode:" + (bcode ?? "없음") + ")",
      };
      setLocalAnalysis(summary);
      // 필지 칩에 면적 자동 반영(로컬 state) — onChange 데이터(areaSqm)로도 노출된다.
      if (analyzedAreaSqm && analyzedAreaSqm > 0) {
        setAddresses((prev) => prev.map((a) =>
          a.fullAddress === address || a.jibunAddress === address
            ? { ...a, areaSqm: analyzedAreaSqm, areaPyeong: analyzedAreaSqm / 3.305785 }
            : a,
        ));
      }
      onAnalyzed?.(summary);

      // WP-D 가드: 비기록 모드면 store 기록 생략, 트리거 시점과 활성 프로젝트가
      // 다르면(전환 race) 기록 중단 — 무관 프로젝트 스냅샷 오염 차단.
      // ★단, '프로젝트 생성 핸드오프'는 예외다: STEP01에서 검색을 시작하면 아직 프로젝트가
      //   없어 triggeredProjectId=null이고, 사용자가 '프로젝트 시작'을 누르면 null→신규 id로
      //   전환된다. 이 검색 결과는 바로 그 신규 프로젝트의 것이므로(무관 프로젝트가 아님)
      //   기록을 막지 말아야 한다. 실제 오염은 '서로 다른 실제 id'로 전환됐을 때만 발생하므로
      //   triggeredProjectId가 null이면(생성 전 검색) 현재 활성 프로젝트로의 기록을 허용한다.
      const activePid = useProjectContextStore.getState().projectId;
      const ownershipMismatch = triggeredProjectId !== null && activePid !== triggeredProjectId;
      if (!writeToContext || ownershipMismatch) {
        return;
      }

      // ★다필지 통합면적 보존 가드(AutoZoningBadge/LandIntelligencePanel과 동일 계약 — 이 경로가
      //   누락돼 있었다): 이 /zoning/comprehensive는 '대표 1필지' 분석이라 analyzedAreaSqm은 대표
      //   면적(작은 값)이다. SSOT가 이미 다필지 통합(parcelCount>1 && landAreaSqmTotal>0)이면
      //   landAreaSqm을 대표값으로 덮으면 통합면적이 무너지고(상도동 11,229㎡→236㎡), enrichParcels의
      //   통합값과 번갈아 기록돼 useEffect 진동(#185 렌더루프)을 유발한다. 다필지면 landAreaSqm 키를
      //   빼서 통합 면적/메타를 보존한다(라이브 SSOT를 읽어 stale 클로저 회피).
      const curSA = useProjectContextStore.getState().siteAnalysis;
      const isMultiParcel = (curSA?.parcelCount ?? 1) > 1
        && typeof curSA?.landAreaSqmTotal === "number" && curSA.landAreaSqmTotal > 0;
      const basePayload = {
        address,
        pnu: data.pnu ?? siteAnalysis?.pnu ?? null,
        estimatedValue: siteAnalysis?.estimatedValue ?? null,
        zoneCode: data.zone_type ?? siteAnalysis?.zoneCode ?? null,
        coordinates: data.coordinates ?? undefined,
        officialPrices: data.official_prices?.map((p) => ({ pnu: p.pnu, year: p.year, pricePerSqm: p.price_per_sqm })),
        ordinance: data.local_ordinance ? {
          sido: data.local_ordinance.sido,
          sigungu: data.local_ordinance.sigungu,
          nationalBcr: data.zone_limits?.max_bcr_pct ?? 60,
          nationalFar: data.zone_limits?.max_far_pct ?? 250,
          ordinanceBcr: data.local_ordinance.effective_bcr,
          ordinanceFar: data.local_ordinance.effective_far,
          effectiveBcr: data.local_ordinance.effective_bcr,
          effectiveFar: data.local_ordinance.effective_far,
          source: data.local_ordinance.source,
          legalBasis: "",
        } : undefined,
        buildingInfo: data.building_info ? {
          buildingName: data.building_info.building_name,
          mainPurpose: data.building_info.main_purpose,
          totalAreaSqm: data.building_info.total_area_sqm,
          groundFloors: data.building_info.ground_floors,
          structure: "",
          useApprovalDate: "",
        } : undefined,
        dataSource: "백엔드 API (bcode:" + (bcode ?? "없음") + ")",
        fetchedAt: new Date().toISOString(),
      };
      updateSiteAnalysis(
        isMultiParcel
          ? basePayload // 다필지: landAreaSqm 미포함 → 통합 면적 보존(진동 차단)
          : { ...basePayload, landAreaSqm: analyzedAreaSqm ?? siteAnalysis?.landAreaSqm ?? null },
      );
    } catch {
      // 분석 실패해도 주소는 이미 저장됨
    } finally {
      setIsAnalyzing(false);
    }
  }, [siteAnalysis, updateSiteAnalysis, writeToContext, onAnalyzed]);

  // ★등록된 '모든' 필지의 토지정보(면적·용도지역·건폐/용적·지목·공시지가)+집합건물 여부 일괄 보강.
  //   (처음 1필지만 분석되던 근본문제 해결 — 개별등록·엑셀 공통). 주소 매칭으로 머지.
  // 보강 자기치유 재시도용 — uid별 시도 횟수(무한루프 방지: 최대 2회). 컴포넌트 수명 동안 유지.
  const enrichTries = useRef<Map<string, number>>(new Map());
  // enrichParcels 자기참조용 ref(재시도 setTimeout에서 최신 함수를 호출 — 순환 의존 회피).
  const enrichParcelsRef = useRef<(entries: AddressEntry[]) => Promise<void>>(async () => {});
  const enrichParcels = useCallback(async (entries: AddressEntry[]) => {
    // WP-D race 가드: 진입 시점의 활성 projectId 캡처 — 장시간 보강(청크당 90s) 중 사용자가
    //   다른 프로젝트로 전환하면, 통합 면적 기록이 무관 프로젝트 SSOT(및 스냅샷)를 오염시키지
    //   않도록 기록 직전 재확인한다(triggerComprehensiveAnalysis와 동일 패턴 — 계정격리).
    const triggeredProjectId = useProjectContextStore.getState().projectId;
    // ★공공데이터(공부상) 우선 원칙: 엑셀/parse-parcels가 채운 면적·용도지역은 '비권위 입력'이라
    //   신뢰하지 않는다. 주소나 PNU로 조회 가능한 필지는, 엑셀에 면적·용도가 이미 차 있어도
    //   1회 공공데이터 조회로 교차검증한다(괴리 시 공부상 채택+경고). 이미 공공데이터로 검증된
    //   행(infoStatus==="ok")만 재조회를 건너뛴다(중복 외부콜 방지). 이게 누락돼 엑셀 잔여값
    //   (예 상도동 210-453=543·211-204=8500)이 영구 미검증으로 남던 근본버그를 해소한다.
    const need = entries.filter((e) =>
      (e.fullAddress || e.jibunAddress || e.pnu) &&
      // ★'ok'여도 핵심값(용도지역·면적) 미확보면 재조회 대상으로 본다. 백엔드가 zone_type=null인데
      //   status='ok'를 반환하던 무성실패로 infoStatus='ok'로 굳은 필지(예 상도동 210-453)를,
      //   재보강 버튼이 enrichParcels에 넘겨도 이 need 필터(과거 infoStatus!=='ok'만 봄)가 제외해
      //   'need.length===0 → return'으로 아무것도 못 하던 버그를 해소(버튼 stuck감지 !zoneCode와 일치).
      (e.infoStatus !== "ok" || !e.zoneCode || !(e.areaSqm && e.areaSqm > 0)),
    );
    if (need.length === 0) return;
    // ★형제 bcode 전파는 '시군구가 같은 형제'에 한해서만 — 안전 가드(근본수정).
    //   [버그] 과거엔 같은 '동명'만으로 형제 bcode를 물려줬다. 그런데 백엔드 _geocode_fill의
    //   C2 보강(시군구 없는 순수 동명 + 번지 → 단일 법정동 수렴 시 자동확정→ok)은 입력 bcode가
    //   '없을 때만' 동작한다. 동명만 같고 시군구는 다를 수 있는 bcode를 물려주면, 그 자동확정
    //   경로가 꺼지고(in_bcode 비어있지 않음) 오히려 시군구 strict 대조(C2)에서 동명이의로
    //   ambiguous 강등된다. → 시군구 없는 '첫' 짧은주소 필지(예 "상도동 211-204")만 zone·면적이
    //   누락되던 근본원인. 백엔드는 짧은주소를 단독으로 주면 ok로 잘 해소하므로(라이브 확인),
    //   '동명만 같은' 불확실 bcode는 물려주지 않고 백엔드 자동해소에 맡긴다.
    //   전파는 동+시군구가 모두 같은(주소에 시군구 토큰이 실제로 포함된) 형제에게만 허용한다.
    const dongOf = (addr: string): string => {
      const m = (addr || "").match(/([가-힣]+(?:동|읍|면|리))(?:\s|$)/);
      return m ? m[1] : "";
    };
    // 시군구 토큰("○○시 ○○구"/"○○군" 등)을 주소에서 추출 — 같은 동명이라도 시군구가 다르면
    //   전파 금지(동명이의 오매칭 방지). 시군구가 없으면 ""(전파 키에서 제외 → 자동해소 위임).
    const sigunguOf = (addr: string): string => {
      const m = (addr || "").match(/((?:[가-힣]+특별자치도|[가-힣]+특별자치시|[가-힣]+특별시|[가-힣]+광역시|[가-힣]+도)\s+)?([가-힣]+시\s+[가-힣]+구|[가-힣]+시|[가-힣]+군|[가-힣]+구)(?:\s|$)/);
      return m ? (m[0] || "").trim() : "";
    };
    // 키 = "시군구|동" 조합(동명만으로는 전파하지 않음). 시군구가 없으면 키를 만들지 않는다.
    const sgDongBcode = new Map<string, string>();
    for (const e of entries) {
      // ★검증된 bcode만 형제전파 학습 — PNU 동반(실제 조회로 확정)만 신뢰한다.
      //   엑셀 입력 bcode는 양식 예시값(의정부 4115·강남 1168)이 1~2행에 남아 주소와 어긋날 수
      //   있어 형제 학습에서 제외(오염 전파 방지). PNU 없는 엑셀 bcode는 백엔드가 주소로 재해소.
      const b = e.pnu && e.pnu.length >= 10 ? e.pnu.slice(0, 10) : "";
      const src = e.fullAddress || e.jibunAddress || "";
      const sg = sigunguOf(src);
      const d = dongOf(src);
      if (b && b.length >= 10 && sg && d && !sgDongBcode.has(`${sg}|${d}`)) sgDongBcode.set(`${sg}|${d}`, b.slice(0, 10));
    }
    const bcodeFor = (e: AddressEntry): string => {
      const src = e.fullAddress || e.jibunAddress || "";
      const sg = sigunguOf(src);
      // ★엑셀 bcode 오염 가드(근본수정 v2): 양식 예시 bcode(의정부 4115010100·강남 1168010100)가
      //   예시행에 남아 주소(동작구 상도동)와 지역이 어긋나면 잘못된 지역을 조회해 용도지역/건폐/
      //   용적을 못 불러온다('보완필요' 고착·재보강 반복 무효). ★이전 버전이 '시군구 미파싱 단축주소
      //   (!sg)에선 bcode가 힌트로 필요'하다며 오염 bcode를 신뢰한 것이 바로 그 버그 — 단축주소
      //   "상도동 210-453"+오염bcode가 이 분기를 타 의정부에서 조회→영구 실패. 따라서 PNU가 동반된
      //   bcode(실제 조회로 확정)일 때만 신뢰하고, PNU 없는 입력 bcode는 전부 버려 백엔드가 주소로
      //   재해소(VWorld 지오코딩→올바른 PNU·bcode)하게 한다.
      if (e.bcode && e.pnu) return e.bcode;
      // 시군구가 없는 짧은주소는 형제 bcode를 물려받지 않는다 → 백엔드 C2 자동해소(ok)에 위임.
      if (!sg) return "";
      const d = dongOf(src);
      return (d && sgDongBcode.get(`${sg}|${d}`)) || "";
    };
    type P = {
      __rid?: number; address?: string | null; jibun?: string | null;
      area_sqm?: number | null; area_input_sqm?: number | null; area_warning?: string | null;
      zone_type?: string | null; jimok?: string | null;
      pnu?: string | null; official_price_per_sqm?: number | null; bcr_pct?: number | null; far_pct?: number | null;
      // bcr_pct/far_pct = 실효값(조례 반영). 법정상한은 *_legal_pct(보조 라벨용).
      bcr_legal_pct?: number | null; far_legal_pct?: number | null;
      special_parcel?: {
        is_special?: boolean; developability?: string | null; resolvable?: string | null;
        severity_label?: string | null; factors?: string[]; warning?: string | null; honest_disclosure?: string | null;
      } | null;
      building?: { is_aggregate?: boolean; building_name?: string; main_purpose?: string; unit_count?: number | null } | null;
      status?: string | null;
    };
    const seq = ++enrichSeq.current;
    // ★제출 완전성 게이트용 진행 신호: 다필지 보강이 시작되면 pending=true.
    //   모든 청크 완료(또는 중단) 후 finishPending()으로 1회 false. finishPending은 '이 run이
    //   여전히 최신(seq===enrichSeq.current)일 때만' 끈다 — 새 보강이 시작돼 stale로 빠진
    //   run의 종료가 활성 run의 pending을 잘못 끄는 것을 막는다(경합 가드와 협조).
    //   단일필지·미검색은 enrichParcels가 호출되지 않거나 need.length===0으로 조기반환해
    //   여기 도달하지 않으므로 pending은 항상 false(무회귀).
    useProjectContextStore.getState().setParcelEnrichPending(true);
    const finishPending = () => {
      if (seq === enrichSeq.current) {
        useProjectContextStore.getState().setParcelEnrichPending(false);
      }
    };
    const CHUNK = 60; // 필지당 최대 3 외부콜 — 타임아웃 회피 위해 분할 호출(부분결과 즉시 반영)
    // 전 청크 보강 결과를 uid별로 누적(통합 면적은 청크별 중간이 아니라 '완료 후 1회'만 기록).
    const enrichedByUid = new Map<string, P>();
    // need 내 인덱스(=__rid)와 entry 참조를 함께 보존 → 주소 충돌 없이 정확 매칭.
    for (let start = 0; start < need.length; start += CHUNK) {
      const slice = need.slice(start, start + CHUNK);
      let parcels: P[] = [];
      try {
        const r = await apiClient.post<{ parcels: P[] }>("/zoning/parcels-info", {
          // area_input_sqm: 엑셀 입력 면적(비권위)을 함께 보내 백엔드가 공부상과 교차검증→괴리 시
          //   공부상 채택 + area_warning 생성하게 한다(_enrich_fill 신뢰루프 활성화).
          body: { parcels: slice.map((e, i) => ({ __rid: i, address: e.fullAddress, jibun: e.jibunAddress || e.fullAddress, pnu: e.pnu, bcode: bcodeFor(e), area_input_sqm: e.areaInputSqm ?? e.areaSqm ?? null })) },
          useMock: false, timeoutMs: 90000,
        });
        parcels = r.parcels || [];
      } catch {
        continue; // 이 청크 실패는 '보완필요'로 남김(가짜 생성 없음)
      }
      if (seq !== enrichSeq.current) { finishPending(); return; } // 더 새로운 보강이 시작됐으면 stale 머지 폐기
      // 결과 __rid(슬라이스 인덱스)→해당 행의 불변 uid로 변환해 매칭.
      //   (참조매칭은 triggerComprehensiveAnalysis가 객체를 교체하면 깨지지만, uid는 spread로 보존돼 안전.)
      const byUid = new Map<string, P>();
      for (const p of parcels) {
        if (typeof p.__rid !== "number") continue;
        const uid = slice[p.__rid]?.__uid;
        if (uid) { byUid.set(uid, p); enrichedByUid.set(uid, p); }
      }
      setAddresses((prev) => prev.map((a) => {
        const m = a.__uid ? byUid.get(a.__uid) : undefined;
        if (!m) return a;
        // ★공공데이터(공부상) 우선: parcels-info status=ok이고 공부상 면적이 있으면 엑셀 입력값을
        //   '덮어쓴다'(엑셀은 비권위). 백엔드가 괴리(>1.5x)를 감지하면 area_input_sqm(원입력)과
        //   area_warning을 함께 반환 → 입력값 보존+정직 경고. 백엔드 미보정(경고 없음)이라도
        //   공부상 면적이 오면 그 값을 채택한다(엑셀 잔류 방지). status가 ok가 아니면(애매/실패)
        //   공부상 미확보이므로 기존 엑셀값을 유지(가짜값 금지).
        const publicArea = m.status === "ok" ? m.area_sqm : null;
        const nextArea = publicArea ?? a.areaSqm;
        // ★백엔드가 시군구 없는 짧은주소("상도동 211-204")를 자동해소하면 전체 시군구 주소
        //   ("서울특별시 동작구 상도동 211-204")로 반환한다(C2 보강). status=ok일 때만 그 완전한
        //   주소로 갱신해 라벨·지역수 통계가 정확해지게 한다(기존 입력보다 길/완전할 때만 채택).
        const resolvedAddr = (m.status === "ok" && m.address && m.address.trim().length > (a.fullAddress || "").trim().length)
          ? m.address.trim() : null;
        return {
          ...a,
          fullAddress: resolvedAddr ?? a.fullAddress,
          areaSqm: nextArea,
          areaPyeong: nextArea ? nextArea / 3.305785 : a.areaPyeong,
          // 엑셀 입력값 보존(참고용) — 백엔드가 보정한 경우 그 원입력, 아니면 직전 areaSqm.
          areaInputSqm: m.area_input_sqm ?? a.areaInputSqm,
          areaWarning: m.area_warning ?? a.areaWarning ?? null,
          pnu: m.pnu || a.pnu,
          zoneCode: m.zone_type || a.zoneCode,
          bcrPct: m.bcr_pct ?? a.bcrPct,
          farPct: m.far_pct ?? a.farPct,
          bcrLegalPct: m.bcr_legal_pct ?? a.bcrLegalPct,
          farLegalPct: m.far_legal_pct ?? a.farLegalPct,
          specialParcel: m.special_parcel ?? a.specialParcel,
          jimok: m.jimok || a.jimok,
          officialPrice: m.official_price_per_sqm ?? a.officialPrice,
          isAggregate: m.building?.is_aggregate ?? a.isAggregate ?? false,
          buildingName: m.building?.building_name || a.buildingName,
          mainPurpose: m.building?.main_purpose || a.mainPurpose,
          unitCount: m.building?.unit_count ?? a.unitCount,
          infoStatus: (m.status as AddressEntry["infoStatus"]) || a.infoStatus,
        };
      }));
    }

    if (seq !== enrichSeq.current) { finishPending(); return; } // 더 새로운 보강이 시작됐으면 이후 단계(자기치유·SSOT) 폐기

    // ── 자기치유 재시도: 끝내 ok가 아닌 필지가 있으면 1회 더 보강(모든 필지가 결국 enrich) ──
    //   무목업: 전송 실패·경합 등 일시 사유로 누락된 필지를 백엔드 단독해소(라이브 검증됨)로 다시
    //   채운다. uid별 최대 2시도로 무한루프를 막고, 끝내 미해소면 정직하게 '보완필요'로만 남긴다.
    //   최신 state를 functional updater로 읽어(경합 무관) ok 아닌 필지를 모은다.
    let latest: AddressEntry[] = [];
    setAddresses((prev) => { latest = prev; return prev; });
    // ★재시도 예약 여부 — true면 이 run은 pending을 끄지 않고, 예약된 재시도(새 seq로 pending을
    //   다시 true)가 신호 수명을 이어받는다. 끄고-켜는 깜빡임으로 제출 게이트가 잠깐 열리는 것 방지.
    let retryScheduled = false;
    if (latest.length > 0) {
      const stillNeed = latest.filter((a) => {
        if (!a.__uid) return false;
        // ★'ok'여도 핵심값(용도지역·면적) 미확보면 자기치유 재시도 대상(무성실패 보완·need 필터와 일치).
        //   enrichTries 최대 2시도 캡으로 무한루프는 방지된다.
        if (a.infoStatus === "ok" && a.zoneCode && a.areaSqm && a.areaSqm > 0) return false;
        if (!(a.fullAddress || a.jibunAddress || a.pnu)) return false;
        return (enrichTries.current.get(a.__uid) ?? 0) < 2; // 최대 2시도
      });
      if (stillNeed.length > 0) {
        for (const a of stillNeed) {
          if (a.__uid) enrichTries.current.set(a.__uid, (enrichTries.current.get(a.__uid) ?? 0) + 1);
        }
        retryScheduled = true;
        // 다음 틱에 재보강(현 호출 스택 밖에서 새 seq로 — 경합 가드와 자연스럽게 협조).
        //   pending은 끄지 않는다(재시도가 인계). 단, 재시도 함수가 즉시 need.length===0으로
        //   조기반환하면 pending이 영영 true로 남을 수 있으므로, 그 경우엔 여기서 끈다(안전 가드).
        setTimeout(() => {
          const before = enrichSeq.current;
          void enrichParcelsRef.current(stillNeed);
          // enrichParcels가 동기 구간에서 seq를 증가시키지 않았다면(need.length===0 조기반환)
          //   인계가 일어나지 않은 것 → 이 run의 신호를 정리한다(stuck-true 방지).
          if (enrichSeq.current === before) finishPending();
        }, 400);
      }
    }

    // ── 전 청크 완료 후 통합 면적 기록(SSOT) — 1회만 ──
    // WP-D: store 비기록 모드면 생략(콜백 전용). 단일/미확보 회귀 0: 유효필지 2개 미만이면 변경 없음.
    if (!writeToContext) { if (!retryScheduled) finishPending(); return; }
    // 프로젝트 전환 중이면 기록 중단(무관 프로젝트 SSOT 오염 차단 — 계정격리).
    // ★생성 핸드오프 예외: 보강 시작 시점에 프로젝트가 없었으면(triggeredProjectId=null) 그 검색은
    //   곧 생성될 신규 프로젝트의 것이다. null→신규 id 전환은 '무관 프로젝트로의 전환'이 아니므로
    //   통합 면적 기록을 막지 않는다(이게 막혀서 통합 11,229이 설계/사업개요에 도달하지 못하던
    //   근본버그). 실제 오염(서로 다른 실제 id로 전환)일 때만 차단해 계정격리는 유지한다.
    const activePidForSsot = useProjectContextStore.getState().projectId;
    if (triggeredProjectId !== null && activePidForSsot !== triggeredProjectId) { if (!retryScheduled) finishPending(); return; }
    // ★'전체' 필지의 최신 state(latest=방금 functional updater로 읽음) + 이번 보강 누적값을 병합해
    //   '최종 유효 면적'을 산출한다. entries(이 호출의 입력)는 재시도 시 부분집합일 수 있으므로
    //   전체 합계는 반드시 latest(전 필지 최신값) 기준으로 계산해야 통합 면적이 정확하다.
    //   무목업: status ok(애매·실패 제외) + 면적>0 필지만 합산(미확보 필지는 제외).
    const basis = latest.length > 0 ? latest : entries;
    const valid = basis
      .map((e) => {
        const m = e.__uid ? enrichedByUid.get(e.__uid) : undefined;
        const area = (m?.area_sqm ?? e.areaSqm) ?? 0;
        const status = (m?.status ?? e.infoStatus) ?? null;
        const zone = m?.zone_type ?? e.zoneCode ?? null;
        // 토지조서 SSOT(parcels) 배선용 필지별 데이터 — 보강(m) 우선, 로컬 entry 폴백.
        //   무목업: 없는 값은 빈 문자열(가짜 미생성). ownerType은 무료 API 미제공이라 항상 "".
        const pnu = (m?.pnu ?? e.pnu) ?? "";
        const address = (m?.address ?? e.fullAddress ?? e.jibunAddress) ?? "";
        const landCategory = (m?.jimok ?? e.jimok) ?? "";
        // 개발가능성 우선정렬용 특이부지 판정(지목 + 백엔드 게이트) — '대표' 선정의 핵심.
        const special = _isSpecialParcel({ jimok: landCategory, isSpecial: (m?.special_parcel ?? e.specialParcel)?.is_special });
        // ★K1: 대표(개발가능 필지)로 종합/시나리오 분석을 '재조준'하기 위해 bcode·지번도 함께 보존.
        //   (도로 등 특이부지가 입력 1번이라 분석이 거기 고정되던 근본버그 해소 — analysisAddress 보정.)
        const bcode = (e.bcode || (pnu && pnu.length >= 10 ? pnu.slice(0, 10) : "")) ?? "";
        const jibun = (e.jibunAddress || address) ?? "";
        return { area, status, zone, pnu, address, landCategory, special, bcode, jibun };
      })
      // status가 명시적으로 ok가 아닌 경우(ambiguous/failed)는 제외, 면적>0만.
      .filter((p) => p.area > 0 && (p.status == null || p.status === "ok"));

    // 유효 필지 1개 이하(단일/미확보) → SSOT 변경 없음(기존 대표 landAreaSqm 유지).
    if (valid.length < 2) { if (!retryScheduled) finishPending(); return; }

    // ★개발가능성 우선 정렬 — '대표' 필지를 입력 순서(valid[0])가 아니라 '개발 가능한 가장 큰
    //   필지'로 고른다. (근본버그: 입력 순서가 [도로, 주거]면 도로=특이부지가 대표가 되어 부지분석이
    //   왜곡됐다.) 1차 키=개발가능(특이부지 후순위), 동급이면 2차 키=면적 큰 순. 안정정렬을 위해
    //   stable sort(Array.prototype.sort는 ES2019+ 안정)로 동값 입력순서 유지.
    //   ★주의: 통합 합계(totalSqm)·zoneMixed는 '모든' 유효필지 기준이라 정렬과 무관하게 동일하다.
    //   parcels 배열도 이 정렬을 반영해 토지조서 시드가 대표 필지를 앞에 두게 한다(일관성).
    valid.sort((a, b) => {
      if (a.special !== b.special) return a.special ? 1 : -1; // 특이부지를 뒤로
      return b.area - a.area; // 동급이면 면적 큰 순
    });

    const totalSqm = valid.reduce((s, p) => s + p.area, 0);
    // ★대표 = 정렬 후 '개발가능' 첫 필지. 전부 특이부지면(개발가능 필지 없음) 정렬 후 첫 필지를
    //   표시용 폴백으로 쓰되, 면적 큰 순 첫 항목이 된다(여전히 합계는 통합값 유지).
    //   (대표 지목·특이여부의 화면 표시는 repInfo 메모가 동일 정렬을 미러링해 처리 — SSOT 스키마
    //   미변경: 통합 면적 메타만 기록하고 persist/migrate는 미접촉한다.)
    const repDevelopable = valid.find((p) => !p.special) ?? valid[0];
    const repArea = repDevelopable?.area ?? null; // 대표 = 개발가능 첫 필지 면적
    const zones = new Set(valid.map((p) => p.zone).filter((z): z is string => !!z));

    // ★#185 무한렌더 가드: 자기치유 재시도(2회)·다청크 완료가 '동일 통합값'을 반복 기록하면
    //   siteAnalysis 전체 구독자(GlobalAddressSearch·LandIntelligencePanel 등)가 매번 리렌더돼
    //   업데이트 깊이 초과(Minified React #185) 크래시로 이어진다. 직전 SSOT와 통합 스칼라값이
    //   모두 같고 필지 수도 같으면 재기록을 생략해 리렌더 연쇄를 끊는다(값 변화 시에는 정상 기록).
    {
      const curSA = useProjectContextStore.getState().siteAnalysis;
      // zone 시그니처(필지별 용도지역 순열) — 면적·필지수가 이미 안정된 뒤 어떤 필지의 zone만
      //   늦게 해소되는 경우에도 zoneCode가 끝까지 영속되도록 비교에 포함한다(스칼라 join 비교라
      //   #185 무한렌더 루프를 되살리지 않는다: 한 번 영속되면 다음 패스엔 두 시그니처가 같아 생략).
      const curZoneSig = (curSA?.parcels ?? []).map((p) => p.zoneCode ?? "").join("|");
      const newZoneSig = valid.map((p) => p.zone ?? "").join("|");
      if (
        curSA &&
        curSA.landAreaSqmTotal === totalSqm &&
        curSA.parcelCount === valid.length &&
        curSA.repLandAreaSqm === repArea &&
        (curSA.zoneMixed ?? false) === (zones.size >= 2) &&
        (curSA.parcels?.length ?? 0) === valid.length &&
        curZoneSig === newZoneSig
      ) {
        // 동일 통합값(zone 포함) → 재기록 생략. 통합 메타가 이미 완전 상태이므로 보강 완료.
        if (!retryScheduled) finishPending();
        return;
      }
    }
    // ★대표 분석(triggerComprehensiveAnalysis)이 landAreaSqm=대표를 쓴 뒤 여기서 통합으로 갱신.
    //   경합 시 통합이 최종(이 호출이 enrichParcels 완료 시점 = 대표 분석 이후).
    updateSiteAnalysis({
      landAreaSqm: totalSqm,
      landAreaSqmTotal: totalSqm,
      repLandAreaSqm: repArea,
      parcelCount: valid.length,
      zoneMixed: zones.size >= 2,
      // ★토지조서 SSOT 배선: 다필지 배열을 기록해 LandSchedule·Registry 시드 useEffect가
      //   집계값이 아닌 실제 필지목록으로 표를 자동 복원하게 한다('절반만 배선된 SSOT' 해소).
      //   ParcelData 타입 정합(pnu/address/areaSqm/landCategory/ownerType), 누락필드는 "".
      parcels: valid.map((p) => ({
        pnu: p.pnu,
        address: p.address,
        areaSqm: p.area,
        landCategory: p.landCategory,
        ownerType: "",
        zoneCode: p.zone ?? null, // 용도지역 동반 기록 → 프로젝트 스코프 화면도 면적가중 우세용도 통합 가능
      })),
    });

    // ★H2: 보강 완료 직후 서버 스냅샷 푸시를 명시적으로 예약한다. 평소엔 store 구독
    //   (ProjectSyncProvider)이 updateSiteAnalysis 변화에 자동 예약하지만, 여기서 직접
    //   호출해 전체 필지(parcels[])가 담긴 siteAnalysis가 /projects/{id}.analysis_snapshot에
    //   확실히 영속되게 한다(재진입 시 1필지 스냅샷이 통합 필지를 덮어쓰던 H2 타이밍 버그 방지).
    //   debounce·UUID·SSOT 무결성 가드는 scheduleSnapshotSync 내부에서 동일 적용된다.
    scheduleSnapshotSync();

    // ★K3 재조준 폐기(이전 'K1 대표 재조준' 제거): 다필지는 이제 LandIntelligencePanel이
    //   /zoning/integrated-analysis로 전체 통합분석(면적가중 건폐/용적·통합GFA·인접성·통합 시나리오)을
    //   소비하므로, 여기서 대표 단일필지로 SSOT.address를 비동기 변경하며 종합분석을 다시 쏠 필요가 없다.
    //   재조준은 오히려 SSOT.address를 보강 완료 시점에 바꿔 '다른 주소 결과' 불일치 경고와
    //   React #185 연쇄를 유발했었다(원인). 도로 등 특이부지 할루시네이션 2차방어선은
    //   LandIntelligencePanel의 specialGateTentative(통합 developability 합류 포함)가 독립적으로
    //   담당하므로 재조준을 제거해도 유지된다. 1차 종합분석(handleAddressSelect의
    //   triggerComprehensiveAnalysis, 첫 페인트·단일필지용)은 그대로 유지된다.
    //   위에서 기록한 통합 면적 메타(landAreaSqmTotal·repLandAreaSqm·parcelCount·parcels)만 보존한다.

    // ★보강 완료(통합 SSOT 기록 성공) — 진행 신호 해제(재시도 예약 시엔 재시도가 인계).
    if (!retryScheduled) finishPending();
  }, [writeToContext, updateSiteAnalysis]);
  // 재시도 setTimeout이 항상 최신 enrichParcels를 호출하도록 ref 동기화(렌더마다 갱신).
  enrichParcelsRef.current = enrichParcels;

  // ★수동 재보강(재실행) — 자동 재시도 2회 소진 후 '보완필요'로 굳은 필지를 사용자가 직접 다시
  //   조회한다. 핵심: enrichTries를 0으로 리셋해야 enrichParcels 내부 자기치유 게이트(최대 2시도)에
  //   다시 걸려 재시도가 실효한다. 백엔드 연도폴백+status 정직화(partial)와 합쳐, 일시장애가 아닌
  //   '데이터 부재'였던 필지도 공공데이터 갱신 시 채워질 기회를 준다. 무목업: 끝내 미해소면 다시
  //   정직하게 '보완필요'로 남는다(가짜 zone 생성 없음).
  const manualRerun = useCallback(async (targets: AddressEntry[]) => {
    const valid = targets.filter((e) => e.__uid && (e.fullAddress || e.jibunAddress || e.pnu));
    if (valid.length === 0) return;
    // 중복클릭 가드: 이미 재보강 중인 필지는 제외.
    const fresh = valid.filter((e) => !rerunningUids.has(e.__uid as string));
    if (fresh.length === 0) return;
    for (const e of fresh) {
      if (e.__uid) enrichTries.current.set(e.__uid, 0); // 시도횟수 리셋 → 자기치유 재가동
    }
    setRerunningUids((prev) => {
      const next = new Set(prev);
      for (const e of fresh) if (e.__uid) next.add(e.__uid);
      return next;
    });
    try {
      await enrichParcelsRef.current(fresh);
    } finally {
      setRerunningUids((prev) => {
        const next = new Set(prev);
        for (const e of fresh) if (e.__uid) next.delete(e.__uid);
        return next;
      });
    }
  }, [rerunningUids]);

  const handleAddressSelect = useCallback((result: KakaoAddressResult) => {
    const entry: AddressEntry = {
      __uid: newUid(),
      fullAddress: result.fullAddress,
      jibunAddress: result.jibunAddress,
      roadAddress: result.roadAddress,
      sido: result.sido,
      sigungu: result.sigungu,
      bname: result.bname,
      zonecode: result.zonecode,
      bcode: result.bcode,
    };

    let newAddresses: AddressEntry[];
    if (single) {
      newAddresses = [entry];
    } else {
      // 다필지: 중복이면 조기 반환(불필요한 종합분석·보강 재발사 차단).
      if (addresses.some((a) => a.fullAddress === entry.fullAddress)) {
        setIsSearching(false);
        onChange?.(addresses);
        return;
      }
      newAddresses = [...addresses, entry];
    }

    setAddresses(newAddresses);
    setIsSearching(false);

    // ProjectContextStore에 자동 저장 (Single Source of Truth)
    // 주소만 즉시 저장, 나머지 필드는 기존값 유지 (partial merge)
    // WP-D: writeToContext=false면 store 기록 생략(콜백 전용 모드).
    const primary = newAddresses[0];
    if (primary) {
      if (writeToContext) {
        updateSiteAnalysis({
          address: primary.fullAddress,
        });
      }

      // 자동 종합 분석 트리거 (bcode + 지번주소 포함) — 대표 필지는 store/파이프라인용 풀분석.
      triggerComprehensiveAnalysis(primary.fullAddress, primary.bcode, primary.jibunAddress);
    }
    // ★등록된 모든 필지(대표 포함)의 토지정보 일괄 보강 — 비대표 필지도 면적·용도·건폐/용적이 채워진다.
    if (!single) void enrichParcels(newAddresses);

    onChange?.(newAddresses);
  }, [single, addresses, siteAnalysis, updateSiteAnalysis, onChange, writeToContext, triggerComprehensiveAnalysis, enrichParcels]);

  const handleRemove = useCallback((index: number) => {
    const newAddresses = addresses.filter((_, i) => i !== index);
    setAddresses(newAddresses);

    // 첫 번째 주소가 변경되면 store 업데이트 (partial merge)
    // WP-D: writeToContext=false면 store 기록 생략(콜백 전용 모드).
    if (newAddresses.length > 0 && writeToContext) {
      updateSiteAnalysis({
        address: newAddresses[0].fullAddress,
      });
    }

    onChange?.(newAddresses);
  }, [addresses, siteAnalysis, updateSiteAnalysis, onChange, writeToContext]);

  // 지번/주소 직접검색(VWorld) → 해석되면 필지로 추가(Daum이 못 찾는 지번 대응).
  const handleDirectAdd = useCallback(async () => {
    const q = directQuery.trim();
    if (!q || directBusy) return;
    setDirectBusy(true);
    setDirectMsg("");
    try {
      const r = await apiClient.post<{
        found: boolean; address?: string; jibun_address?: string;
        pnu?: string | null; bcode?: string | null; reason?: string;
      }>("/zoning/geocode", { body: { query: q }, useMock: false, timeoutMs: 30000 });
      if (!r.found) {
        setDirectMsg(r.reason || "해당 주소/지번을 찾지 못했습니다.");
        return;
      }
      // KakaoAddressResult 형태로 변환해 기존 추가 로직(handleAddressSelect) 재사용.
      handleAddressSelect({
        fullAddress: r.address || q,
        jibunAddress: r.jibun_address || r.address || q,
        roadAddress: "",
        sido: "", sigungu: "", bname: "", buildingName: "",
        zonecode: "", bcode: r.bcode || "",
      });
      setDirectQuery("");
      setDirectMsg("");
    } catch {
      setDirectMsg("검색 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setDirectBusy(false);
    }
  }, [directQuery, directBusy, handleAddressSelect]);

  // 토지지번검색 자동완성 — 입력 디바운스(350ms) 후 후보 조회(다음 주소검색처럼).
  const runSearch = useCallback(async (q: string) => {
    const query = q.trim();
    if (query.length < 2) { setCandidates([]); setShowCandidates(false); return; }
    const mySeq = ++searchSeq.current; // 이 요청의 순번
    setSearching(true);
    try {
      const r = await apiClient.post<{ candidates: AddrCandidate[] }>(
        "/zoning/search", { body: { query, size: 8 }, useMock: false, timeoutMs: 15000 },
      );
      if (mySeq !== searchSeq.current) return; // 더 새로운 요청이 떴으면 stale 응답 폐기
      setCandidates(r.candidates || []);
      setShowCandidates(true);
    } catch {
      if (mySeq === searchSeq.current) setCandidates([]);
    } finally {
      if (mySeq === searchSeq.current) setSearching(false);
    }
  }, []);

  const onDirectChange = useCallback((v: string) => {
    setDirectQuery(v);
    setDirectMsg("");
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => void runSearch(v), 350);
  }, [runSearch]);

  // 지도 단일 클릭 필지 선택(하위호환) → KakaoAddressResult 형태로 변환 후 기존 추가 로직 재사용.
  // bcode는 PNU 앞 10자리로 구성(pickCandidate 패턴 동일).
  const handleMapPick = useCallback((parcel: ParcelAtPointResult) => {
    if (!parcel.found || !parcel.address) return;
    const bcode = parcel.bcode || (parcel.pnu && parcel.pnu.length >= 10 ? parcel.pnu.slice(0, 10) : "");
    handleAddressSelect({
      fullAddress: parcel.address,
      jibunAddress: parcel.jibun || parcel.address,
      roadAddress: "",
      sido: "", sigungu: "", bname: "", buildingName: "",
      zonecode: "", bcode,
    });
    // 지도 패널은 필지 추가 후 닫는다(사용자가 원하면 다시 열 수 있음)
    setShowMapPicker(false);
  }, [handleAddressSelect]);

  // 지도 다중 선택 완료 콜백 — staged 배열을 일괄로 기존 handleAddressSelect 경로에 넣는다.
  // 각 필지를 KakaoAddressResult 형태로 변환해 순차 추가(중복은 handleAddressSelect 내부에서 방지).
  const handleMapPickMany = useCallback((parcels: ParcelAtPointResult[]) => {
    if (parcels.length === 0) return;

    // 현재 addresses를 읽어 중복 체크용 Set 생성(함수 호출 시점 스냅샷).
    // handleAddressSelect 내부에서도 중복 체크하므로 실질적으로 이중 방어.
    const existingAddresses = new Set(addresses.map((a) => a.fullAddress));

    let merged = [...addresses];

    for (const parcel of parcels) {
      if (!parcel.found || !parcel.address) continue;
      const fullAddress = parcel.address;
      if (existingAddresses.has(fullAddress)) continue; // 이미 있으면 건너뜀
      existingAddresses.add(fullAddress);

      const bcode = parcel.bcode || (parcel.pnu && parcel.pnu.length >= 10 ? parcel.pnu.slice(0, 10) : "");
      const entry: AddressEntry = {
        __uid: newUid(),
        fullAddress,
        jibunAddress: parcel.jibun || fullAddress,
        roadAddress: "",
        sido: "", sigungu: "", bname: "", zonecode: "", bcode,
        pnu: parcel.pnu,
        // parcel-at-point가 이미 반환한 토지정보 활용(enrichParcels 부담 최소화)
        ...(parcel.area_sqm != null ? { areaSqm: parcel.area_sqm, areaPyeong: parcel.area_sqm / 3.305785 } : {}),
        ...(parcel.zone_type ? { zoneCode: parcel.zone_type } : {}),
        ...(parcel.jimok ? { jimok: parcel.jimok } : {}),
        ...(parcel.bcr_pct != null ? { bcrPct: parcel.bcr_pct } : {}),
        ...(parcel.far_pct != null ? { farPct: parcel.far_pct } : {}),
      };
      merged = [...merged, entry];
    }

    if (merged.length === addresses.length) {
      // 새로 추가된 필지가 없으면 패널만 닫음
      setShowMapPicker(false);
      return;
    }

    setAddresses(merged);

    // 대표 필지(첫 번째)로 store·종합분석 갱신(기존 handleAddressSelect 동작 동일)
    const primary = merged[0];
    if (primary) {
      if (writeToContext) {
        updateSiteAnalysis({ address: primary.fullAddress });
      }
      triggerComprehensiveAnalysis(primary.fullAddress, primary.bcode, primary.jibunAddress);
    }

    // 토지정보가 완전히 채워지지 않은 필지 보강(면적·용도지역 등)
    if (!single) void enrichParcels(merged);

    onChange?.(merged);
    setShowMapPicker(false);
  }, [addresses, single, writeToContext, updateSiteAnalysis, triggerComprehensiveAnalysis, enrichParcels, onChange]);

  // 후보 선택 → 필지로 추가(PNU 보유 시 bcode 직접 구성, 종합분석 재실행).
  const pickCandidate = useCallback((c: AddrCandidate) => {
    const bcode = c.pnu && c.pnu.length >= 10 ? c.pnu.slice(0, 10) : "";
    handleAddressSelect({
      fullAddress: c.address,
      jibunAddress: c.address,
      roadAddress: c.road_address || "",
      sido: "", sigungu: "", bname: "", buildingName: "",
      zonecode: "", bcode,
    });
    setDirectQuery("");
    setCandidates([]);
    setShowCandidates(false);
    setDirectMsg("");
  }, [handleAddressSelect]);

  // 하단 요약 표시용 — store 기록 모드면 SSOT(siteAnalysis), 비기록 모드면 로컬 분석값만
  // 사용한다(무관 프로젝트의 store 데이터가 비기록 화면에 표시되는 혼선 방지).
  const displayAnalysis = writeToContext
    ? siteAnalysis
      ? {
          zoneCode: siteAnalysis.zoneCode,
          landAreaSqm: siteAnalysis.landAreaSqm,
          effectiveBcr: siteAnalysis.ordinance?.effectiveBcr ?? null,
          effectiveFar: siteAnalysis.ordinance?.effectiveFar ?? null,
          dataSource: siteAnalysis.dataSource ?? null,
        }
      : null
    : localAnalysis;

  // ── 다필지 엑셀 업로드 — 토지조서 양식 업로드 → 필지 추출(주소만 적어도 PNU·면적·용도 자동보강) ──
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadInfo, setUploadInfo] = useState<{ note: string; registry?: string } | null>(null);

  const handleExcelUpload = useCallback(async (file: File) => {
    setUploading(true);
    setUploadInfo(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiClient.post<{
        parcels?: Array<{ address?: string | null; jibun?: string | null; bcode?: string | null; pnu?: string | null; area_sqm?: number | null; zone_type?: string | null; jimok?: string | null; official_price_per_sqm?: number | null }>;
        note?: string; error?: string; registry_guidance?: { message?: string };
      }>("/zoning/parse-parcels", { body: fd, useMock: false, timeoutMs: 120000 });
      if (res.error) { setUploadInfo({ note: res.error }); return; }
      // parse-parcels가 이미 채운 면적·용도지역·지목·공시지가를 보존(이전엔 areaSqm만 받고 폐기).
      const entries: AddressEntry[] = (res.parcels ?? [])
        .filter((p) => (p.address || p.pnu))
        .map((p) => {
          // ★소재지(동)와 지번(번지)이 분리된 양식이면 결합해 '완전한 지번주소'를 fullAddress로.
          //   (이게 누락돼 동 단위 주소만 들어가 부지분석·구획도가 동 대표필지로 수렴하던 근본버그.)
          const addr = (p.address || "").trim();
          const jb = (p.jibun || "").trim();
          const full = (jb && addr && !addr.includes(jb)) ? `${addr} ${jb}` : (addr || jb || p.pnu || "");
          return ({
          __uid: newUid(),
          fullAddress: full,
          jibunAddress: jb || addr || "",
          roadAddress: "", sido: "", sigungu: "", bname: "", zonecode: "",
          bcode: p.bcode || "",
          pnu: p.pnu || undefined,
          ...(p.area_sqm ? { areaSqm: p.area_sqm, areaPyeong: p.area_sqm / 3.305785 } : {}),
          ...(p.zone_type ? { zoneCode: p.zone_type } : {}),
          ...(p.jimok ? { jimok: p.jimok } : {}),
          ...(p.official_price_per_sqm ? { officialPrice: p.official_price_per_sqm } : {}),
        });
        });
      // ★같은 필지가 여러 행(공유지분·다소유자)으로 들어오면 병합셀 forward-fill 후 같은
      //   지번으로 복원돼 분석 목록에 중복 표시된다(211-443이 5번 등). 분석 목록은 '필지 단위'
      //   이므로 PNU(없으면 주소)로 1필지=1행 정리한다. 소유자별·세대별 상세(대지지분 등)는
      //   토지조서 메뉴에서 관리한다(중앙분석센터=부지분석, 토지조서=권리/세대 관리로 역할분리).
      const seenKey = new Set<string>();
      const uniqEntries = entries.filter((e) => {
        const key = (e.pnu || e.fullAddress || "").replace(/\s+/g, "");
        if (key && seenKey.has(key)) return false; // 키 있고 이미 본 필지만 중복 제거
        if (key) seenKey.add(key);
        return true; // 빈 키(주소·PNU 모두 없는 행)는 제거하지 않고 보존(데이터 손실 방지)
      });
      const dupRemoved = entries.length - uniqEntries.length;
      // ★업로드한 필지를 앞에 둔다(기존 검색분은 뒤로 보존, 혼용 가능). 방금 올린 토지조서가
      //   대표(primary)가 되어 이전에 검색한 주소가 분석에 잔류하는 오류를 막는다.
      const merged = single
        ? uniqEntries.slice(0, 1)
        : [...uniqEntries, ...addresses.filter((a) => !uniqEntries.some((e) => e.fullAddress === a.fullAddress))];
      setAddresses(merged);

      // ★검색 경로(handleAddressSelect)와 동일하게 대표 필지로 store 갱신 + 종합분석 재실행.
      //   (이게 누락돼 엑셀 업로드 시 이전 검색 주소의 분석이 그대로 표시되던 버그를 근본수정.)
      const primary = merged[0];
      if (primary) {
        if (writeToContext) updateSiteAnalysis({ address: primary.fullAddress });
        triggerComprehensiveAnalysis(primary.fullAddress, primary.bcode, primary.jibunAddress);
      }
      onChange?.(merged);
      // 중복(같은 필지 다중행)을 정리했으면 안내에 표기 — 사용자가 '왜 줄었지' 혼란 방지.
      const dupNote = dupRemoved > 0 ? ` · 동일 필지 ${dupRemoved}행 통합(공유지분 등은 토지조서에서 관리)` : "";
      setUploadInfo({ note: (res.note || `${uniqEntries.length}필지 등록`) + dupNote, registry: res.registry_guidance?.message });
      // 건폐율/용적률·집합건물(빌라) 여부 보강 — parse-parcels엔 없는 항목을 일괄 채운다.
      // ★재업로드 시 자기치유 재시도 카운터 초기화 — 직전 업로드에서 2회 소진한 필지도 다시 보강 시도(무한 아님).
      enrichTries.current.clear();
      if (!single) void enrichParcels(merged);
    } catch (e: any) {
      setUploadInfo({ note: e?.message || "엑셀 처리 실패" });
    } finally {
      setUploading(false);
    }
  }, [single, addresses, onChange, writeToContext, updateSiteAnalysis, triggerComprehensiveAnalysis, enrichParcels]);

  const downloadTemplate = useCallback(async () => {
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiV1BaseUrl()}/zoning/land-schedule-template`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "PropAI_토지조서_양식.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setUploadInfo({ note: "양식 다운로드 실패 — 잠시 후 다시 시도해 주세요." });
    }
  }, []);

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {/* 등록된 필지 목록 — 요약 헤더 + 컴팩트 스크롤 리스트(대량 필지 가독성 극대화) */}
      {displayAddresses.length > 0 && (
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden">
          {/* 요약 헤더: 필지수·합계면적·면적확보/보완필요·지역수 */}
          {displayAddresses.length > 1 && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--line)] bg-[var(--surface-muted)]/50 px-3 py-2 text-[11px]">
              <span className="font-bold text-[var(--text-primary)]">필지 {parcelStats.n.toLocaleString()}개</span>
              {parcelStats.totalSqm > 0 && (
                <span className="text-[var(--accent-strong)] font-bold">합계 {Math.round(parcelStats.totalSqm).toLocaleString()}㎡ ({(parcelStats.totalSqm / 3.305785).toFixed(1)}평)</span>
              )}
              {parcelStats.regionCnt > 0 && <span className="text-[var(--text-secondary)]">지역 {parcelStats.regionCnt}곳</span>}
              <span className="text-[var(--text-secondary)]">면적확보 <b className="text-[var(--text-primary)]">{parcelStats.withAreaCnt}</b></span>
              {parcelStats.needFixCnt > 0 && (
                <span className="rounded bg-[color-mix(in_srgb,var(--status-warning)_15%,transparent)] px-1.5 py-0.5 font-semibold text-[var(--status-warning)]">보완필요 {parcelStats.needFixCnt}</span>
              )}
              {/* ★일괄 재보강: 면적/용도지역 미확보(infoStatus≠ok) 필지를 한 번에 다시 조회.
                  자동 재시도 2회 소진 후 굳은 필지의 수동 복구경로(추적 fix_design의 '전체 재보강'). */}
              {(() => {
                const stuck = displayAddresses.filter((a) =>
                  (a.fullAddress || a.jibunAddress || a.pnu) &&
                  (!(a.areaSqm && a.areaSqm > 0) || (a.infoStatus != null && a.infoStatus !== "ok") || !a.zoneCode),
                );
                if (stuck.length === 0) return null;
                const anyBusy = stuck.some((a) => a.__uid && rerunningUids.has(a.__uid));
                return (
                  <button
                    type="button"
                    disabled={anyBusy}
                    onClick={() => { void manualRerun(stuck); }}
                    title="보완필요 필지의 토지정보를 한 번에 다시 조회합니다"
                    className="rounded border border-[var(--line)] bg-[var(--surface-soft)] px-1.5 py-0.5 font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] disabled:opacity-50"
                  >
                    {anyBusy ? "조회중…" : `↻ 보완필요 ${stuck.length}건 재보강`}
                  </button>
                );
              })()}
            </div>
          )}
          {/* 대표 필지 안내(다필지 전용) — 부지분석은 '통합' 기준이고, 아래 표기는 표시용 대표(개발가능
              우선)임을 명확히 한다. 입력 순서가 아니라 '개발 가능한 가장 큰 필지'를 대표로 고른다. */}
          {repInfo && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-[var(--line)] bg-[var(--surface-muted)]/30 px-3 py-1.5 text-[10.5px]">
              <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 font-bold text-[var(--accent-strong)]">통합 분석</span>
              <span className="text-[var(--text-secondary)]">부지분석은 <b className="text-[var(--text-primary)]">{repInfo.count}필지 통합</b> 기준</span>
              <span className="text-[var(--text-hint)]">·</span>
              <span className="text-[var(--text-secondary)]" title={repInfo.label}>
                대표(표시용): <b className="text-[var(--text-primary)]">{repInfo.label}</b>
                {repInfo.jimok ? ` · 지목 ${repInfo.jimok}` : ""}
              </span>
              {parcelStats.regionCnt > 1 && (
                <span className="rounded bg-[color-mix(in_srgb,var(--accent-strong)_12%,transparent)] px-1.5 py-0.5 font-semibold text-[var(--accent-strong)]">혼재 지역 {parcelStats.regionCnt}곳</span>
              )}
              {repInfo.allSpecial && (
                <span
                  className="inline-flex items-center gap-1 rounded bg-[color-mix(in_srgb,var(--status-warning)_16%,transparent)] px-1.5 py-0.5 font-bold text-[var(--status-warning)]"
                  title="모든 필지가 특이부지(도로·하천·학교용지 등)로 분류됐습니다. 대표는 표시용 폴백이며 단독 개발가능성은 개별 필지 게이트를 확인하세요."
                >
                  <AlertTriangle className="size-3" aria-hidden /> 대표가 특이부지 — 개별 게이트 확인
                </span>
              )}
            </div>
          )}
          {/* 컴팩트 리스트: 지번 + 토지정보(면적·용도지역·건폐/용적·지목) 2행 + 공동주택(호실·대지지분) */}
          <ul className={`divide-y divide-[var(--line)]/60 ${displayAddresses.length > 8 ? "max-h-[360px] overflow-y-auto" : ""}`}>
            {parcelRows.map((row, idx) => (
              <li key={`${row.label}-${idx}`} className="flex items-start gap-2 px-3 py-1.5 hover:bg-[var(--surface-muted)]/40">
                <span className="mt-0.5 w-7 shrink-0 text-right text-[10px] tabular-nums text-[var(--text-hint)]">{idx + 1}</span>
                <div className="min-w-0 flex-1">
                  {/* 1행: 지번 + 면적 + (보완필요 시) 재보강 버튼 */}
                  <div className="flex items-center gap-2">
                    <span className="flex-1 truncate text-[12px] font-medium text-[var(--text-primary)]" title={row.label}>{row.label}</span>
                    {row.areaSqm && row.areaSqm > 0 ? (
                      <span className="shrink-0 text-[10px] font-bold tabular-nums text-[var(--accent-strong)]">
                        {Math.round(row.areaSqm).toLocaleString()}㎡ · {(row.areaSqm / 3.305785).toFixed(1)}평
                      </span>
                    ) : (
                      <span className="shrink-0 rounded bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] px-1 py-0.5 text-[9px] font-semibold text-[var(--status-warning)]">{isAnalyzing ? "조회중…" : "보완필요"}</span>
                    )}
                    {/* ★재보강(재실행): 면적 미확보 또는 용도지역 미확보(infoStatus≠ok) 필지만 노출.
                        클릭 시 해당 필지만 시도횟수 리셋 후 재조회(공공데이터 갱신분 반영 기회). */}
                    {(() => {
                      const uid = row.entry.__uid;
                      const needFix = !(row.areaSqm && row.areaSqm > 0) || (row.entry.infoStatus != null && row.entry.infoStatus !== "ok") || !row.zoneCode;
                      if (!needFix || !uid) return null;
                      const busy = rerunningUids.has(uid);
                      return (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => { void manualRerun([row.entry]); }}
                          title="이 필지의 토지정보(용도지역·면적 등)를 다시 조회합니다"
                          className="shrink-0 rounded border border-[var(--line)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] disabled:opacity-50"
                        >
                          {busy ? "조회중…" : "↻ 재보강"}
                        </button>
                      );
                    })()}
                  </div>
                  {/* 엑셀 입력↔공부상 면적 괴리 경고 — 공부상(권원) 채택했음을 정직 고지(입력값 참고 보존) */}
                  {row.areaWarning && (
                    <div className="mt-0.5 flex items-start gap-1 text-[9.5px] text-[var(--status-warning)]" title={row.areaWarning}>
                      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-[color-mix(in_srgb,var(--status-warning)_14%,transparent)] px-1 py-0.5 font-bold"><AlertTriangle className="size-3" aria-hidden /> 면적 보정</span>
                      <span className="min-w-0 flex-1">
                        입력 {row.areaInputSqm ? Math.round(row.areaInputSqm).toLocaleString() : "—"}㎡ → 공부상 채택(입력값 점검 필요)
                      </span>
                    </div>
                  )}
                  {/* 2행: 용도지역·건폐/용적(실효)·지목 + 공동주택(빌라) 배지 */}
                  {(row.zoneCode || row.bcrPct || row.jimok || row.isAggregate) && (
                    <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[9.5px] text-[var(--text-secondary)]">
                      {row.zoneCode && <span className="rounded bg-[var(--accent-soft)] px-1 py-0.5 font-semibold text-[var(--accent-strong)]">{row.zoneCode}</span>}
                      {(row.bcrPct || row.farPct) && (
                        <span>
                          건폐 {row.bcrPct ?? "—"}% · 용적 {row.farPct ?? "—"}%
                          {row.farPct != null && <span className="text-[var(--text-hint)]">(실효)</span>}
                          {/* 실효가 법정상한보다 낮을 때만 법정상한을 보조로 병기(정직·과다표시 방지) */}
                          {row.farLegalPct != null && row.farPct != null && row.farLegalPct > row.farPct && (
                            <span className="text-[var(--text-hint)]"> · 법정상한 {row.farLegalPct}%</span>
                          )}
                        </span>
                      )}
                      {row.jimok && <span>지목 {row.jimok}</span>}
                      {row.isAggregate && (
                        <button
                          type="button"
                          onClick={() => setShareParcel(row.entry)}
                          title="공동주택(빌라) — 호실·세대 대지지분 보기/반영"
                          className="inline-flex items-center gap-1 rounded bg-[color-mix(in_srgb,var(--accent-strong)_14%,transparent)] px-1.5 py-0.5 font-bold text-[var(--accent-strong)] hover:bg-[color-mix(in_srgb,var(--accent-strong)_24%,transparent)]"
                        >
                          <Building2 className="size-3" aria-hidden /> 공동주택{row.unitCount ? ` ${row.unitCount}세대` : ""} · 호실/대지지분 ▸
                        </button>
                      )}
                    </div>
                  )}
                  {/* 3행: 특이부지(임야·산지/농지/GB/맹지/학교용지 등) 배지 + 경고 — 단일분석과 동일 게이트 */}
                  {row.specialParcel?.is_special && (
                    <div className="mt-0.5 flex flex-wrap items-start gap-1 text-[9.5px]">
                      <span
                        className="inline-flex shrink-0 items-center gap-1 rounded bg-[color-mix(in_srgb,var(--status-warning)_16%,transparent)] px-1 py-0.5 font-bold text-[var(--status-warning)]"
                        title={row.specialParcel.honest_disclosure || undefined}
                      >
                        <AlertTriangle className="size-3 shrink-0" aria-hidden /> 특이부지
                        {row.specialParcel.factors?.length ? ` · ${row.specialParcel.factors.join("·")}` : ""}
                        {row.specialParcel.severity_label ? ` (${row.specialParcel.severity_label})` : ""}
                      </span>
                      {row.specialParcel.warning && (
                        <span className="min-w-0 flex-1 text-[var(--status-warning)]" title={row.specialParcel.warning}>
                          {row.specialParcel.warning.replace(/^\[특이부지\]\s*/, "")}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => handleRemove(idx)}
                  className="mt-0.5 shrink-0 rounded p-0.5 text-[var(--text-hint)] hover:bg-red-500/10 hover:text-red-500 transition-colors"
                  aria-label="필지 삭제"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 다필지 안내 — 검색 추가와 엑셀 일괄등록이 병행됨을 명시(단일 모드는 숨김) */}
      {!single && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[12px] text-[var(--text-secondary)]">
          <span className="text-[13px] font-bold text-[var(--text-primary)]">다필지 등록</span>
          <span className="inline-flex items-center gap-1 rounded-md bg-[var(--accent-soft)] px-2 py-0.5 font-semibold text-[var(--accent-strong)]"><Search className="size-3" aria-hidden /> 검색으로 한 필지씩 추가</span>
          <span className="text-[var(--text-hint)]">또는</span>
          <span className="inline-flex items-center gap-1 rounded-md bg-[var(--accent-soft)] px-2 py-0.5 font-semibold text-[var(--accent-strong)]"><BarChart3 className="size-3" aria-hidden /> 엑셀로 일괄 등록</span>
          <span className="text-[var(--text-hint)]">— 둘 다 사용 가능(혼용 OK)</span>
        </div>
      )}

      {/* 주소·지번 검색
          · 단일 모드: 기존 다음(Daum) 주소검색 박스(회귀 없음)
          · 다필지 모드: 통합 스마트 검색 — VWorld 지번·도로명 자동완성(기본, 산·농지·맹지·나대지까지)
            + '건물명·아파트로 찾기'(다음, 보조). 두 검색을 한 입력 프레임으로 통합(중복 제거). */}
      {single ? (
        (isSearching || displayAddresses.length === 0) ? (
          <KakaoAddressSearch onSelect={handleAddressSelect} placeholder={placeholder} disabled={disabled} />
        ) : (
          <button
            type="button"
            onClick={() => setIsSearching(true)}
            className="w-full rounded-xl border border-dashed border-[var(--line-strong)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] transition-all"
          >
            주소 변경
          </button>
        )
      ) : (
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/40 px-3 py-2.5">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-[12px] font-bold text-[var(--text-secondary)]"><Search className="size-3.5" aria-hidden /> 지번·주소 검색</span>
            {/* 보조: 건물명·아파트는 다음(Daum)이 강함 → 팝업으로 보완(데이터소스 보완) */}
            <button
              type="button"
              disabled={disabled}
              onClick={() => setKakaoOpen(true)}
              className="inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-semibold text-[var(--accent-strong)] hover:underline disabled:opacity-50"
            >
              <Building2 className="size-3.5" aria-hidden /> 건물명·아파트로 찾기 →
            </button>
          </div>
          <div className="relative flex flex-wrap items-center gap-2">
            <div className="relative min-w-[160px] flex-1">
              <input
                value={directQuery}
                disabled={disabled || directBusy}
                onChange={(e) => onDirectChange(e.target.value)}
                onFocus={() => { if (candidates.length) setShowCandidates(true); }}
                onBlur={() => setTimeout(() => setShowCandidates(false), 150)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (candidates.length) pickCandidate(candidates[0]); else void handleDirectAdd(); } }}
                placeholder="지번·도로명 검색 (예: 의정부동 224, 산 12-3, 판교역로 166)"
                aria-label="지번·도로명 주소 검색"
                className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 py-1.5 text-[12px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
              {/* 자동완성 후보 드롭다운 */}
              {showCandidates && (candidates.length > 0 || searching) && (
                <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-64 overflow-y-auto rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
                  {searching && <li className="px-3 py-2 text-[11px] text-[var(--text-tertiary)]">검색 중…</li>}
                  {candidates.map((c, i) => (
                    <li key={`${c.address}-${i}`}>
                      <button
                        type="button"
                        onMouseDown={(e) => { e.preventDefault(); pickCandidate(c); }}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[11px] hover:bg-[var(--accent-soft)]"
                      >
                        <span className="truncate text-[var(--text-primary)]">{c.address}</span>
                        <span className="shrink-0 rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">{c.kind || "지번"}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button
              type="button"
              disabled={disabled || directBusy || !directQuery.trim()}
              onClick={() => { if (candidates.length) pickCandidate(candidates[0]); else void handleDirectAdd(); }}
              className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 disabled:opacity-50"
            >
              {directBusy ? "검색 중…" : "＋ 추가"}
            </button>
          </div>
          {directMsg && <p className="mt-1 flex items-center gap-1 text-[12px] font-semibold text-amber-500"><AlertTriangle className="size-3.5 shrink-0" aria-hidden /> {directMsg}</p>}
          <p className="mt-1 text-[10px] text-[var(--text-hint)]">지번·산·농지·맹지·나대지는 지번검색, 아파트·건물명은 ‘건물명·아파트로 찾기’(다음)를 쓰세요.</p>
          {/* 다음(Daum) 팝업 — 외부제어(보조): 건물명·아파트 검색. 닫힘 시 트리거 박스 미표시. */}
          <KakaoAddressSearch open={kakaoOpen} onOpenChange={setKakaoOpen} onSelect={handleAddressSelect} disabled={disabled} />
        </div>
      )}

      {/* 다른 등록 방식 — 엑셀 일괄 등록 + 지도 클릭 선택(전체폭 스택).
          (주소·지번 검색은 위 통합 검색으로 일원화. single 모드는 이 영역 미렌더 — 회귀 없음) */}
      {!single && (
      <div className="grid grid-cols-1 gap-2">
      {/* 다필지 엑셀 등록 — 토지조서 양식 업로드/다운로드(주소만 적어도 PNU·면적·용도·공시지가 자동보강).
          주소·지번 검색은 위 통합 검색(VWorld 자동완성 + 다음 보조)으로 일원화 — 여긴 엑셀·지도만. */}
        <div className="flex h-full flex-col rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/40 px-3 py-2.5">
          <span className="mb-1.5 inline-flex items-center gap-1.5 text-[12px] font-bold text-[var(--text-secondary)]"><BarChart3 className="size-3.5" aria-hidden /> 엑셀로 다필지 등록</span>
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleExcelUpload(f); e.target.value = ""; }}
            />
            <button
              type="button"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-1.5 text-[12px] font-bold text-[var(--text-primary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
            >
              <BarChart3 className="size-3.5" aria-hidden /> {uploading ? "처리 중…" : "엑셀 파일 선택"}
            </button>
            <button
              type="button"
              onClick={() => void downloadTemplate()}
              className="text-[12px] font-semibold text-[var(--accent-strong)] underline-offset-2 hover:underline"
            >
              양식 다운로드 ↓
            </button>
          </div>
          <span className="mt-1.5 text-[11px] text-[var(--text-hint)]">주소·지번만 적어도 PNU·면적·용도지역·공시지가 자동수집</span>
          {uploadInfo && (
            <div className="mt-2 rounded-md border border-[var(--line)] bg-[var(--surface)]/60 px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)]">
              <p className="flex items-start gap-1"><MapPin className="mt-0.5 size-3 shrink-0" aria-hidden /><span>{uploadInfo.note}</span></p>
              {uploadInfo.registry && <p className="mt-1 flex items-start gap-1 font-semibold text-amber-500"><Landmark className="mt-0.5 size-3 shrink-0" aria-hidden /><span>{uploadInfo.registry}</span></p>}
            </div>
          )}
        </div>

      {/* 지도에서 선택 — 지도를 직접 클릭해 필지를 추가(다필지 모드 전용). 행 전체(2열) span. */}
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/40 px-3 py-2.5 md:col-span-2">
          {/* 토글 헤더 버튼 */}
          <button
            type="button"
            disabled={disabled}
            onClick={() => setShowMapPicker((v) => !v)}
            className="flex w-full items-center justify-between gap-2 text-[12px] font-bold text-[var(--text-secondary)] hover:text-[var(--accent-strong)] transition-colors disabled:opacity-50"
          >
            <span className="flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>
              지도에서 선택
            </span>
            {/* 열림/닫힘 화살표 */}
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
              style={{ transform: showMapPicker ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>
              <path d="m6 9 6 6 6-6"/>
            </svg>
          </button>
          {/* 지도 패널 — 토글 열릴 때만 마운트(Leaflet은 DOM 필요) */}
          {showMapPicker && (
            <div className="mt-2">
              <MapShell height={360} label="필지 선택 지도" loadingMessage="필지 선택 지도 로딩…">
                <ParcelPickerMapDynamic onPick={handleMapPick} onPickMany={handleMapPickMany} height={360} />
              </MapShell>
            </div>
          )}
        </div>
      </div>
      )}

      {/* 분석 중 표시 */}
      {isAnalyzing && (
        <div className="flex items-center gap-2 text-xs text-[var(--accent-strong)]">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
          토지정보 종합 분석 중...
        </div>
      )}

      {/* 분석 완료 — 기본 정보 요약 (기록 모드: SSOT / 비기록 모드: 로컬 분석값) */}
      {!isAnalyzing && displayAnalysis?.zoneCode && displayAddresses.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[10px]">
          <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 font-bold text-[var(--accent-strong)]">
            {displayAnalysis.zoneCode}
          </span>
          {displayAnalysis.landAreaSqm && (
            <span className="text-[var(--text-secondary)]">
              {/* 다필지(repInfo 존재)면 통합 면적임을 명확히 라벨링(대표 1필지 면적 아님) */}
              {repInfo ? `통합 ${repInfo.count}필지 ` : ""}{displayAnalysis.landAreaSqm.toLocaleString()}m²
            </span>
          )}
          {displayAnalysis.effectiveBcr && (
            <span className="text-[var(--text-hint)]">
              건폐율 {displayAnalysis.effectiveBcr}% · 용적률 {displayAnalysis.effectiveFar}%
            </span>
          )}
          {displayAnalysis.dataSource && (
            <span className="text-[var(--text-hint)]">
              ({displayAnalysis.dataSource})
            </span>
          )}
        </div>
      )}

      {/* 공동주택(빌라) 호실·세대 대지지분 모달 — 검색/등록한 필지에서 바로 호실 분석/반영 */}
      {shareParcel && (
        <LandShareModal
          jibun={shareParcel.jibunAddress || shareParcel.fullAddress}
          pnu={shareParcel.pnu}
          onClose={() => setShareParcel(null)}
          onApplyArea={() => { /* 검색 컨텍스트에선 행 면적 갱신 불필요(토지조서에서 반영) */ }}
        />
      )}
    </div>
  );
}
