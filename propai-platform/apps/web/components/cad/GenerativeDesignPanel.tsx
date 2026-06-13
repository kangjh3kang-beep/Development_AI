"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { EvidencePanel, type EvidenceItem, type EvidenceLegalRef } from "@/components/common/EvidencePanel";
import { useSpeechToText } from "@/lib/use-speech-to-text";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ReferenceAssemblyCard } from "@/components/cad/ReferenceAssemblyCard";
import type {
  DesignAlternative,
  DesignAlternativesV2Response,
  AutoDesignResponse,
  DesignIntent,
  LegalLimitsResponse,
  ParseIntentResponse,
  ReferenceResultBlock,
  SimilarRefV2,
} from "@/components/cad/types";

/**
 * Phase 2 · 생성 UX (CAD 스튜디오 내장)
 * ─────────────────────────────────────────────────────────────
 * 비전문가가 말(자연어)이나 슬라이더로 설계 의도를 주면,
 *  1) 자연어 → 설계 의도 파싱(parse-intent)으로 폼 자동 채움
 *  2) 법정 한도(legal-limits)로 슬라이더 max를 하드캡(법규 초과 입력 불가)
 *  3) Top3 설계안(design-alternatives) 생성 → 카드 선택 → 스튜디오 로드
 *  4) 단일 자동설계(auto-design)도 유지
 *
 * 선택한 설계안은 모세혈관 SSOT(useProjectContextStore.designData)에 기록하여
 * 본 스튜디오의 2D 도면·3D BIM이 동일 기하로 자동 재생성되도록 한다.
 * (SSOT가 유일 출처 — 구세대 Konva 캔버스 스토어로 가던 죽은 경로는 제거됨)
 */

const ZONE_OPTIONS = [
  { code: "1R", label: "제1종일반주거" },
  { code: "2R", label: "제2종일반주거" },
  { code: "3R", label: "제3종일반주거" },
  { code: "QR", label: "준주거" },
  { code: "GC", label: "일반상업" },
  { code: "NC", label: "근린상업" },
  { code: "QI", label: "준공업" },
];

const UNIT_TYPE_OPTIONS = ["29A", "39A", "59A", "74A", "84A", "114A"];

type LensItem = { lens: string; label: string; score: number; basis: string; hint: string };
type DesignEval = {
  violations: { field: string; rule: string; message: string; severity: string }[];
  lenses: { lenses: LensItem[]; overall: number };
};
type DesignOperateResponse = DesignEval & {
  design_payload: AutoDesignResponse["design_payload"];
  summary: AutoDesignResponse["summary"];
  applied_changes: string[];
  spec?: { target_unit_types?: string[] };
};
// U4: 유사 사례 타입은 SimilarRefV2(types.ts)로 승격 — v2 확장 필드는 전부 optional(하위호환).

const PRIORITY_LABELS: Record<DesignIntent["priority"], string> = {
  yield: "수익 최대화",
  livability: "거주성 우선",
  balanced: "균형형",
};

/**
 * W-A 신설 summary 확장 필드 — 구버전 백엔드 응답엔 없으므로 전부 optional.
 * 부재 시 어떤 것도 추정·표시하지 않는다(가짜값 금지 — 있을 때만 렌더).
 */
type SummaryExtras = {
  /** 목표(슬라이더)를 막은 바인딩 제약 코드/이름 (예: "far", "height"). */
  binding_constraint?: string | null;
  /** 산출 근거(세트백 실값·일조캡 여부·층수 바인딩·주차/코어 산식 등). */
  basis?: unknown;
};

/** 바인딩 제약 코드 → 사용자 라벨. 미등록 코드는 원문 그대로 표기(정직). */
const BINDING_CONSTRAINT_LABELS: Record<string, string> = {
  far: "법정 용적률",
  bcr: "법정 건폐율",
  height: "높이 제한",
  daylight: "정북일조 사선",
  sunlight: "일조 기준",
  setback: "세트백",
  parking: "주차 대수",
  units: "세대수",
};

/** W-A 신설 산출 근거 키 → 사용자 라벨. 미등록 키는 키 이름 그대로(정직). */
const BASIS_KEY_LABELS: Record<string, string> = {
  // W-A 실응답 키(auto_design_engine summary["basis"])
  setback_applied_m: "적용 세트백",
  sunlight: "정북일조 높이캡",
  floors_binding_constraint: "층수 결정 요인",
  applied_limits: "적용 한도",
  parking_formula: "주차 산식",
  core_formula: "코어 산식",
  // 변형 키 호환(타 경로/구버전 응답 대비 — 라벨만 매핑, 값 추정 없음)
  setback: "적용 세트백",
  setback_m: "적용 세트백",
  daylight_cap: "정북일조 높이캡",
  daylight_capped: "정북일조 높이캡",
  floors_binding: "층수 결정 요인",
  num_floors: "층수 산정",
  parking: "주차 산식",
  core: "코어 산식",
};

/** 객체에서 유한수만 안전 추출(아니면 null — 추정 금지). */
function readFiniteNumber(rec: Record<string, unknown>, key: string): number | null {
  const v = rec[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** summary.basis.applied_limits에서 목표·법정 용적률(%)을 안전 추출(없으면 null). */
function readFarLimits(basis: unknown): { targetFar: number | null; statutoryFar: number | null } {
  const none = { targetFar: null, statutoryFar: null };
  if (!basis || typeof basis !== "object" || Array.isArray(basis)) return none;
  const lim = (basis as { applied_limits?: unknown }).applied_limits;
  if (!lim || typeof lim !== "object" || Array.isArray(lim)) return none;
  const L = lim as Record<string, unknown>;
  const tgt = readFiniteNumber(L, "target_far_percent");
  return {
    targetFar: tgt != null && tgt > 0 ? tgt : null,
    statutoryFar: readFiniteNumber(L, "statutory_max_far_percent"),
  };
}

/** basis 값 → 표시 문자열(불명확한 값은 빈 문자열 → 행 제외, 추정 금지). */
function formatBasisValue(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v.trim();
  if (typeof v === "number") return Number.isFinite(v) ? v.toLocaleString() : "";
  if (typeof v === "boolean") return v ? "적용" : "미적용";
  try {
    return JSON.stringify(v);
  } catch {
    return "";
  }
}

/** basis 항목의 legalRef/legal_ref를 EvidencePanel 칩 형태로 안전 변환. */
function toLegalRef(raw: unknown): EvidenceLegalRef | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as { lawName?: unknown; law_name?: unknown; article?: unknown; title?: unknown; url?: unknown };
  const lawName = typeof r.lawName === "string" ? r.lawName : typeof r.law_name === "string" ? r.law_name : null;
  if (!lawName) return null;
  return {
    lawName,
    article: typeof r.article === "string" ? r.article : null,
    title: typeof r.title === "string" ? r.title : null,
    url: typeof r.url === "string" ? r.url : null,
  };
}

/**
 * W-A summary.basis(배열·객체 모두 허용)를 EvidencePanel 항목으로 변환.
 * 객체형(W-A 실응답)은 알려진 키(세트백 실값·일조캡 여부·층수 바인딩·적용 한도·
 * 주차/코어 산식)를 사람이 읽는 행으로 펼치고, 미등록 키는 원문 그대로 표기한다
 * (추정·가공 금지). 형태 불명 값은 행 제외(빈 패널은 EvidencePanel이 자체 미렌더).
 */
function toEvidenceItems(basis: unknown): EvidenceItem[] {
  if (Array.isArray(basis)) {
    return basis
      .filter((b): b is Record<string, unknown> => !!b && typeof b === "object")
      .map((b) => ({
        label: typeof b.label === "string" ? b.label : "",
        value:
          typeof b.value === "string" || typeof b.value === "number"
            ? b.value
            : formatBasisValue(b.value),
        basis: typeof b.basis === "string" ? b.basis : null,
        legalRef: toLegalRef(b.legalRef ?? b.legal_ref),
      }))
      .filter((it) => it.label && `${it.value}` !== "");
  }
  if (basis && typeof basis === "object") {
    const rec = basis as Record<string, unknown>;
    const items: EvidenceItem[] = [];
    const consumed = new Set<string>();

    // 1) 적용 세트백 실값 — {north,south,east,west}(m)
    const setback = rec.setback_applied_m;
    if (setback && typeof setback === "object" && !Array.isArray(setback)) {
      const sb = setback as Record<string, unknown>;
      const parts = ([["north", "북"], ["south", "남"], ["east", "동"], ["west", "서"]] as const)
        .map(([k, lab]) => {
          const v = readFiniteNumber(sb, k);
          return v != null ? `${lab} ${v}m` : "";
        })
        .filter(Boolean);
      if (parts.length > 0) {
        items.push({ label: "적용 세트백", value: parts.join(" · ") });
        consumed.add("setback_applied_m");
      }
    }

    // 2) 정북일조 높이캡 여부 — {applied, mode, max_height_by_sunlight_m, formula}
    const sun = rec.sunlight;
    if (sun && typeof sun === "object" && !Array.isArray(sun)) {
      const s = sun as Record<string, unknown>;
      if (typeof s.applied === "boolean") {
        const capM = readFiniteNumber(s, "max_height_by_sunlight_m");
        const value = !s.applied
          ? "미적용"
          : s.mode === "step_profile"
            ? "단계후퇴 적용"
            : capM != null
              ? `적용 — 최고 ${capM}m`
              : "적용";
        items.push({
          label: "정북일조 높이캡",
          value,
          basis: typeof s.formula === "string" && s.formula.trim() ? s.formula.trim() : null,
        });
        consumed.add("sunlight");
      }
    }

    // 3) 층수 바인딩 — 어떤 한도가 층수를 결정했는가.
    //    "far"는 적용 한도(min(법정, 목표))가 막은 것이므로 "법정"으로 단정하지 않는다(정직).
    const fb = rec.floors_binding_constraint;
    if (typeof fb === "string" && fb.trim()) {
      const fbKey = fb.trim().toLowerCase();
      items.push({
        label: "층수 결정 요인",
        value:
          fbKey === "far"
            ? "용적률 한도(적용 한도 기준)"
            : BINDING_CONSTRAINT_LABELS[fbKey] ?? fb.trim(),
      });
      consumed.add("floors_binding_constraint");
    }

    // 4) 적용 한도 — min(법정, 목표) 결과와 그 구성값
    const lim = rec.applied_limits;
    if (lim && typeof lim === "object" && !Array.isArray(lim)) {
      const L = lim as Record<string, unknown>;
      const bcrMax = readFiniteNumber(L, "max_bcr_percent");
      const farMax = readFiniteNumber(L, "max_far_percent");
      if (bcrMax != null || farMax != null) {
        const statBcr = readFiniteNumber(L, "statutory_max_bcr_percent");
        const tgtBcr = readFiniteNumber(L, "target_bcr_percent");
        const statFar = readFiniteNumber(L, "statutory_max_far_percent");
        const tgtFar = readFiniteNumber(L, "target_far_percent");
        const basisParts = [
          statBcr != null ? `법정 건폐율 ${statBcr}%` : "",
          tgtBcr != null ? `목표 건폐율 ${tgtBcr}%` : "",
          statFar != null ? `법정 용적률 ${statFar}%` : "",
          tgtFar != null ? `목표 용적률 ${tgtFar}%` : "",
        ].filter(Boolean);
        items.push({
          label: "적용 한도",
          value: [
            bcrMax != null ? `건폐율 ≤${bcrMax}%` : "",
            farMax != null ? `용적률 ≤${farMax}%` : "",
          ]
            .filter(Boolean)
            .join(" · "),
          basis: basisParts.length > 0 ? `min(법정, 목표) — ${basisParts.join(" · ")}` : null,
        });
        consumed.add("applied_limits");
      }
    }

    // 5) 나머지 키(주차/코어 산식 등 문자열 + 미등록 키) — 원문 정직 표기
    for (const [k, v] of Object.entries(rec)) {
      if (consumed.has(k)) continue;
      const value = formatBasisValue(v);
      if (value !== "") items.push({ label: BASIS_KEY_LABELS[k] ?? k, value });
    }
    return items;
  }
  return [];
}

/** FastAPI 422 payload({detail: string | [{loc,msg}...]})에서 첫 메시지만 안전 추출. */
function extractValidationDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown; loc?: unknown };
    const msg = typeof first?.msg === "string" ? first.msg : null;
    const loc = Array.isArray(first?.loc) ? first.loc.filter((p) => p !== "body").join(".") : "";
    if (msg) return loc ? `${loc}: ${msg}` : msg;
  }
  return null;
}

/**
 * ApiClientError.status → 사용자 행동 가능 메시지.
 * 알 수 없는 상태는 상태코드를 정직 표기하고, ApiClientError가 아니면 원문 메시지 유지.
 */
function describeApiError(e: unknown, fallback: string): string {
  if (e instanceof ApiClientError) {
    switch (e.status) {
      case 401:
        return "로그인이 필요합니다 — 로그인 후 다시 시도해 주세요.";
      case 408:
        return "요청 시간이 초과되었습니다 — 잠시 후 다시 시도해 주세요.";
      case 422: {
        const detail = extractValidationDetail(e.payload);
        return detail ? `입력값을 확인해 주세요 — ${detail}` : "입력값을 확인해 주세요(요청 형식 오류).";
      }
      case 429:
        return "요청이 너무 잦습니다 — 잠시 후 다시 시도해 주세요.";
      case 501:
        return "이 기능의 서버 구성이 아직 완료되지 않았습니다(서비스 미구성) — 관리자에게 문의해 주세요.";
      default:
        return `${fallback} (HTTP ${e.status})`;
    }
  }
  return e instanceof Error && e.message ? e.message : fallback;
}

/** 컨텍스트 용도지역명(한글) → 로컬 엔진 단축코드(SSOT 우선 읽기). */
function mapZoneToCode(zone?: string | null): string | null {
  const s = (zone || "").toString();
  if (!s) return null;
  if (/제1종일반주거/.test(s)) return "1R";
  if (/제2종일반주거/.test(s)) return "2R";
  if (/제3종일반주거/.test(s)) return "3R";
  if (/준주거/.test(s)) return "QR";
  if (/일반상업/.test(s)) return "GC";
  if (/근린상업/.test(s)) return "NC";
  if (/준공업/.test(s)) return "QI";
  if (/^(1R|2R|3R|GC|NC|QI|QR)$/.test(s)) return s;
  return null;
}

const PRIORITY_OPTIONS: DesignIntent["priority"][] = ["yield", "balanced", "livability"];

/**
 * §4-A③: 매스 형상 선택 옵션 — 백엔드 MASSING_FORMS(slab/tower/lshape/court)와 정합.
 * value=null은 "자동"(대지 종횡비 기반 — massing_kind 미전송과 동일, 하위호환).
 * 선택값은 단일 자동설계(auto-design)·Top3(design-alternatives) 재생성에 massing_kind로 전달된다.
 */
const MASSING_OPTIONS: { value: string | null; label: string }[] = [
  { value: null, label: "자동" },
  { value: "slab", label: "판상형" },
  { value: "tower", label: "타워형" },
  { value: "lshape", label: "ㄱ자형" },
  { value: "court", label: "중정형" },
];

type GenerativeDesignPanelProps = {
  projectId: string;
  /** 설계안 적용 직후 호출(호스트가 spec 재산출 → 2D/3D 재생성 유도). */
  onApplied?: () => void;
};

export function GenerativeDesignPanel({ projectId, onApplied }: GenerativeDesignPanelProps) {
  void projectId; // 라우팅 컨텍스트용(현재 호출엔 불필요하나 시그니처 유지)
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  const ctxArea = siteAnalysis?.landAreaSqm ?? null;
  const ctxZone = mapZoneToCode(siteAnalysis?.zoneCode);

  // ── 부지 컨텍스트 기반 폼 상태 ──
  const [siteArea, setSiteArea] = useState(500);
  const [zoneCode, setZoneCode] = useState("2R");
  const [editedArea, setEditedArea] = useState(false);
  const [editedZone, setEditedZone] = useState(false);
  const [autoArea, setAutoArea] = useState(false);
  const [autoZone, setAutoZone] = useState(false);
  const [unitTypes, setUnitTypes] = useState<string[]>(["59A", "84A"]);

  // ── 슬라이더 의도값(법정 한도로 하드캡) ──
  const [bcr, setBcr] = useState(50);
  const [far, setFar] = useState(200);
  const [targetUnits, setTargetUnits] = useState(40);
  const [targetMargin, setTargetMargin] = useState(15);
  const [priority, setPriority] = useState<DesignIntent["priority"]>("balanced");
  // P5: 정북일조 단계후퇴(북측 상부 매스 후퇴). 의도 파싱 또는 토글로 켜짐.
  const [daylightNorth, setDaylightNorth] = useState(false);
  // §4-A③: 매스 형상 선택(null=자동). 단일 자동설계·Top3 재생성에 massing_kind로 전달.
  const [massingKind, setMassingKind] = useState<string | null>(null);
  // §4-B: 유사 참조 사례 기하(종횡비) 반영(기본 ON). 단일·Top3 생성에 use_references로 전달.
  // 명시 매스 형상이 선택돼 있으면 그 형상이 우선(참조는 auto 대안 A에만 영향).
  const [useReferences, setUseReferences] = useState(true);

  // 컨텍스트(SSOT)를 폼에 우선 주입(사용자 수정값 보존)
  useEffect(() => {
    if (ctxArea != null && ctxArea > 0 && !editedArea) {
      setSiteArea(Math.round(ctxArea));
      setAutoArea(true);
    }
    if (ctxZone && !editedZone) {
      setZoneCode(ctxZone);
      setAutoZone(true);
    }
  }, [ctxArea, ctxZone, editedArea, editedZone]);

  // ── 자연어 파싱 ──
  const [intentText, setIntentText] = useState("");
  const [intent, setIntent] = useState<DesignIntent | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  // ── 법정 한도(슬라이더 하드캡) ──
  const [limits, setLimits] = useState<LegalLimitsResponse | null>(null);

  // ── 검증·다각평가(P5) — 법규 위반 + 4관점 점수(전부 커널값 기반) ──
  const [evaluation, setEvaluation] = useState<DesignEval | null>(null);
  const [similar, setSimilar] = useState<SimilarRefV2[]>([]);

  // ── 단일 자동설계 ──
  const [single, setSingle] = useState<AutoDesignResponse | null>(null);
  const [singleLoading, setSingleLoading] = useState(false);
  const [singleError, setSingleError] = useState<string | null>(null);

  // ── Top3 설계안 ──
  const [alternatives, setAlternatives] = useState<DesignAlternative[]>([]);
  const [recommendedIdx, setRecommendedIdx] = useState<number | null>(null);
  const [altLoading, setAltLoading] = useState(false);
  const [altError, setAltError] = useState<string | null>(null);
  // 구버전 API 응답(rank 부재) 등 비치명 경고 — 빈 화면 대신 보정 사실을 정직 고지.
  const [altWarning, setAltWarning] = useState<string | null>(null);
  const [selectedRank, setSelectedRank] = useState<number | null>(null);
  // §4-B: Top3 응답의 유사사례 조회 결과(A 대안 참조 비례 적용 여부·사유 — 정직 표기용).
  const [altReference, setAltReference] = useState<ReferenceResultBlock | null>(null);

  // 용도지역 변경 시 법정 한도 조회 → 슬라이더 max 하드캡
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<LegalLimitsResponse>(`/drawing/legal-limits?zone_code=${encodeURIComponent(zoneCode)}`)
      .then((data) => {
        if (cancelled) return;
        setLimits(data);
        // 한도 초과 입력은 즉시 클램프
        setBcr((v) => Math.min(v, data.max_bcr_percent));
        setFar((v) => Math.min(v, data.max_far_percent));
      })
      .catch(() => {
        if (!cancelled) setLimits(null);
      });
    return () => {
      cancelled = true;
    };
  }, [zoneCode]);

  const toggleUnitType = useCallback((type: string) => {
    setUnitTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  }, []);

  // 음성 입력(STT) — 말로 설계 의도를 받아 텍스트박스에 채움(브라우저 네이티브).
  const stt = useSpeechToText((t) => setIntentText(t));

  // 생성 직후 검증·다각평가 조회(/design-operate, text="" → LLM 미사용·결정론).
  const fetchEvaluation = useCallback(async () => {
    try {
      const data = await apiClient.post<DesignEval>("/drawing/design-operate", {
        body: {
          text: "",
          site_area_sqm: siteArea,
          zone_code: zoneCode,
          building_use: intent?.building_use ?? "공동주택",
          target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
          priority: "balanced",
        },
      });
      setEvaluation(data);
    } catch {
      /* 평가 실패는 무시 — 설계 생성 자체는 정상 */
    }
    // 유사 표준설계 사례(P7→U4 v2) — 라이브러리 메타 유사도 Top5(+용도지역 적합성).
    // zone_code는 R6 신설 파라미터 — 구버전 백엔드는 무시(additive·하위호환).
    try {
      const sim = await apiClient.get<{ items: SimilarRefV2[] }>(
        `/design-references/similar?building_use=${encodeURIComponent(intent?.building_use ?? "공동주택")}&area_sqm=${siteArea}&zone_code=${encodeURIComponent(zoneCode)}&unit_types=${encodeURIComponent((unitTypes.length > 0 ? unitTypes : ["84A"]).join(","))}&k=5`,
        { useMock: false },
      );
      setSimilar(sim.items || []);
    } catch {
      /* 사례 없음/미설정 — 무시 */
    }
  }, [siteArea, zoneCode, intent, unitTypes]);

  // ── 자연어/음성 설계 편집(P6) — 현재 설계를 말로 수정 → 커널 재생성 → 2D/3D/BIM/QTO 전파 ──
  const [editText, setEditText] = useState("");
  const [editing, setEditing] = useState(false);
  const [appliedChanges, setAppliedChanges] = useState<string[]>([]);
  const editStt = useSpeechToText((t) => setEditText(t));

  // 1) 자연어 → 설계 의도(폼 자동 채움)
  const handleParse = useCallback(async () => {
    const text = intentText.trim();
    if (!text) return;
    setParsing(true);
    setParseError(null);
    try {
      const data = await apiClient.post<ParseIntentResponse>("/drawing/parse-intent", {
        body: { text, site_area_sqm: siteArea, zone_code: zoneCode },
      });
      const it = data.intent;
      setIntent(it);
      // 폼 자동 채움(파싱된 값만 반영, 한도는 클램프)
      if (it.target_units != null && it.target_units > 0) setTargetUnits(it.target_units);
      if (it.target_margin_pct != null && it.target_margin_pct > 0)
        setTargetMargin(Math.min(60, it.target_margin_pct));
      if (it.priority) setPriority(it.priority);
      if (it.suggested_unit_types?.length) setUnitTypes(it.suggested_unit_types);
      // P5: "북측 일조 확보" 등 정북일조 의도 → 단계후퇴 ON(매스 자동 후퇴)
      if (it.daylight_north) setDaylightNorth(true);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "해석에 실패했습니다.");
    } finally {
      setParsing(false);
    }
  }, [intentText, siteArea, zoneCode]);

  // 적용 공통: SSOT(designData)에 기록 → 스튜디오 2D/3D 자동 재생성
  const applyDesign = useCallback(
    (payload: AutoDesignResponse["design_payload"], summary: AutoDesignResponse["summary"]) => {
      // payload는 호출부 시그니처 호환을 위해 유지(구세대 캔버스 로드 경로는 제거됨 — 기하 출처는 SSOT 단일화).
      void payload;
      // 모세혈관 SSOT — 스튜디오 spec 재산출의 단일 출처(공사비·수지 다운스트림 전파)
      updateDesignData({
        totalGfaSqm: summary.total_floor_area_sqm,
        floorCount: summary.num_floors,
        buildingType: intent?.building_use ?? "공동주택",
        bcr: summary.bcr_percent,
        far: summary.far_percent,
        // 세대 구성도 SSOT에 기록 — 도면·해석·수지의 "세대수·평형 부재" 해소.
        unitCount: summary.total_units ?? null,
        unitTypes: unitTypes.length > 0 ? unitTypes : null,
        efficiencyPct: null,
        // P5: 정북일조 단계후퇴 적용 여부 — 3D 매스 후퇴 렌더의 SSOT
        daylightNorth: (summary as { daylight_step?: boolean }).daylight_step ?? daylightNorth,
      });
      markStageComplete("design");
      onApplied?.();
    },
    [updateDesignData, markStageComplete, intent, unitTypes, daylightNorth, onApplied],
  );

  // 자연어/음성 설계 편집(P6) — 현재 설계를 말로 수정 → 커널 재생성 → applyDesign으로 2D/3D/BIM/QTO 전파
  const handleEdit = useCallback(async () => {
    const text = editText.trim();
    if (!text) return;
    setEditing(true);
    try {
      const data = await apiClient.post<DesignOperateResponse>("/drawing/design-operate", {
        body: {
          text,
          site_area_sqm: siteArea,
          zone_code: zoneCode,
          building_use: intent?.building_use ?? "공동주택",
          target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
          priority: "balanced",
        },
      });
      if (data.design_payload && data.summary) {
        applyDesign(data.design_payload, data.summary); // 2D/3D/BIM/QTO 단일기하 전파
        setEvaluation(data);
        setAppliedChanges(data.applied_changes ?? []);
        if (Array.isArray(data.spec?.target_unit_types)) setUnitTypes(data.spec.target_unit_types);
      }
      setEditText("");
    } catch {
      /* 편집 실패는 무시 — 기존 설계 유지 */
    } finally {
      setEditing(false);
    }
  }, [editText, siteArea, zoneCode, intent, unitTypes, applyDesign]);

  // 4) 단일 자동설계
  const handleSingle = useCallback(async () => {
    setSingleLoading(true);
    setSingleError(null);
    try {
      const data = await apiClient.post<AutoDesignResponse>("/drawing/auto-design", {
        body: {
          site_area_sqm: siteArea,
          zone_code: zoneCode,
          building_use: intent?.building_use ?? "공동주택",
          target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
          floor_height_m: 3.0,
          daylight_north: daylightNorth,
          // 법규 슬라이더 의도값 — W-A 백엔드가 목표 BCR/FAR·우선순위로 수용(구버전은 무시).
          target_bcr_percent: bcr,
          target_far_percent: far,
          priority,
          // §4-A③: 매스 형상(null=자동) — 백엔드가 형상별 결정론 매스로 재산출(구버전은 무시).
          massing_kind: massingKind,
          // §4-B: 유사 참조 사례 기하(종횡비) 반영(구버전은 무시). 명시 형상이 우선.
          use_references: useReferences,
        },
      });
      setSingle(data);
      applyDesign(data.design_payload, data.summary);
      fetchEvaluation();
    } catch (e) {
      setSingleError(describeApiError(e, "자동설계에 실패했습니다."));
    } finally {
      setSingleLoading(false);
    }
  }, [siteArea, zoneCode, intent, unitTypes, daylightNorth, bcr, far, priority, massingKind, useReferences, applyDesign, fetchEvaluation]);

  // 3) Top3 설계안 생성
  const handleAlternatives = useCallback(async () => {
    setAltLoading(true);
    setAltError(null);
    setAltWarning(null);
    try {
      const data = await apiClient.post<DesignAlternativesV2Response>(
        "/drawing/design-alternatives",
        {
          body: {
            site_area_sqm: siteArea,
            zone_code: zoneCode,
            target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
            count: 3,
            daylight_north: daylightNorth,
            // 법규 슬라이더 의도값 — W-A 백엔드가 목표 BCR/FAR·우선순위로 수용(구버전은 무시).
            target_bcr_percent: bcr,
            target_far_percent: far,
            priority,
            // §4-A③: A 대안이 선택 형상을 따름(B=타워·C=ㄱ자 고정 다양화, 구버전은 무시).
            massing_kind: massingKind,
            // §4-B: 유사 참조 사례 기하 반영 — A 대안에만 적용(B/C는 명시 형상 우선).
            use_references: useReferences,
          },
        },
      );
      setAltReference(data.reference ?? null);  // 정직 표기용 — 조회 결과(적용/미적용·사유)
      const raw = data.alternatives ?? [];
      // 응답 가드: 구버전 API가 rank를 누락해도 표시 순서(idx+1)로 보정 — 빈 화면 방지.
      const missingRank = raw.some((a) => typeof (a as { rank?: unknown }).rank !== "number");
      const normalized = raw.map((a, idx) =>
        typeof (a as { rank?: unknown }).rank === "number" ? a : { ...a, rank: idx + 1 },
      );
      setAlternatives(normalized);
      if (missingRank) {
        setAltWarning("구버전 API 응답 — 설계안 순위(rank)가 없어 표시 순서로 자동 보정했습니다.");
      }
      setRecommendedIdx(
        typeof data.recommended_index === "number" ? data.recommended_index : null,
      );
      setSelectedRank(null);
    } catch (e) {
      setAltError(describeApiError(e, "설계안 생성에 실패했습니다."));
    } finally {
      setAltLoading(false);
    }
  }, [siteArea, zoneCode, unitTypes, daylightNorth, bcr, far, priority, massingKind, useReferences]);

  const handleSelectAlt = useCallback(
    (alt: DesignAlternative) => {
      applyDesign(alt.design_payload, alt.summary);
      setSelectedRank(alt.rank);
      fetchEvaluation();
    },
    [applyDesign, fetchEvaluation],
  );

  // 선택된 설계안 — 산출 근거(W-A summary.basis)를 카드(버튼) 밖에서 렌더하기 위함.
  const selectedAlt =
    selectedRank != null ? alternatives.find((a) => a.rank === selectedRank) ?? null : null;

  return (
    <div className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 lg:p-8">
      {/* 헤더 */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="cc-meta">AI 설계 생성 · GENERATIVE</span>
          <span className="cc-live">
            <i />PHASE 2
          </span>
        </div>
        <p className="text-[11px] font-bold text-[var(--text-hint)]">
          말이나 슬라이더로 의도를 주면 법규에 맞는 설계안을 만들어 드립니다
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        {/* ── 좌: 자연어 + 슬라이더 입력 ── */}
        <div className="flex flex-col gap-6">
          {/* 1) 자연어 입력 */}
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
            <h4 className="mb-2 text-sm font-black text-[var(--text-primary)]">
              원하는 설계를 말이나 음성으로 설명하세요
            </h4>
            <div className="relative">
              <textarea
                value={intentText}
                onChange={(e) => setIntentText(e.target.value)}
                placeholder="예) 원룸 위주 50세대, 수익 최대"
                rows={2}
                className="w-full resize-none rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 pr-11 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
                aria-label="설계 의도 자연어 입력"
              />
              {stt.supported && (
                <button
                  type="button"
                  onClick={() => (stt.listening ? stt.stop() : stt.start())}
                  title={stt.listening ? "음성 입력 중지" : "음성으로 입력"}
                  aria-label={stt.listening ? "음성 입력 중지" : "음성으로 입력"}
                  className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full border transition-all ${stt.listening ? "border-red-500/50 bg-red-500/15 text-red-400 animate-pulse" : "border-[var(--line)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"}`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" />
                  </svg>
                </button>
              )}
            </div>
            {stt.listening && (
              <p className="mt-1 text-[11px] font-bold text-red-400">🎙️ 듣는 중… 말씀하세요</p>
            )}
            {stt.error && (
              <p className="mt-1 text-[11px] text-[var(--text-hint)]">{stt.error}</p>
            )}
            <button
              type="button"
              onClick={handleParse}
              disabled={parsing || !intentText.trim()}
              className="mt-2 w-full rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white transition-opacity disabled:opacity-40"
            >
              {parsing ? "해석 중…" : "해석"}
            </button>

            {parseError && (
              <p className="mt-2 text-xs font-bold text-[var(--status-error)]" role="alert">
                {parseError}
              </p>
            )}

            {intent && (
              <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <div className="mb-1.5 flex items-center gap-2">
                  <span className="text-[9px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">
                    해석 결과
                  </span>
                  {intent.source === "rule" && (
                    <span className="rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-hint)] border border-[var(--line)]">
                      키워드 기반
                    </span>
                  )}
                  {intent.source === "llm" && (
                    <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--accent-strong)]">
                      AI 해석
                    </span>
                  )}
                </div>
                <p className="text-[12px] leading-relaxed text-[var(--text-secondary)]">
                  {intent.notes || "설계 의도를 반영했습니다."}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-bold">
                  {intent.target_units != null && intent.target_units > 0 && (
                    <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[var(--text-secondary)] border border-[var(--line)]">
                      목표 {intent.target_units}세대
                    </span>
                  )}
                  <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[var(--text-secondary)] border border-[var(--line)]">
                    {PRIORITY_LABELS[intent.priority]}
                  </span>
                  {intent.suggested_unit_types?.slice(0, 4).map((t) => (
                    <span
                      key={t}
                      className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[var(--text-secondary)] border border-[var(--line)]"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* 부지·용도지역·세대유형 */}
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
            <h4 className="mb-3 text-sm font-black text-[var(--text-primary)]">부지 조건</h4>
            <div className="grid gap-3 text-xs">
              <label className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1 text-[var(--text-secondary)]">
                  대지면적 (㎡)
                  {autoArea && !editedArea && (
                    <span className="rounded bg-[var(--status-success)]/15 px-1 text-[9px] font-bold text-[var(--status-success)]">
                      자동
                    </span>
                  )}
                </span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={siteArea}
                  onChange={(e) => {
                    setSiteArea(Number(e.target.value));
                    setEditedArea(true);
                  }}
                  className="w-24 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-right text-sm text-[var(--text-primary)]"
                  aria-label="대지면적"
                />
              </label>

              <label className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1 text-[var(--text-secondary)]">
                  용도지역
                  {autoZone && !editedZone && (
                    <span className="rounded bg-[var(--status-success)]/15 px-1 text-[9px] font-bold text-[var(--status-success)]">
                      자동
                    </span>
                  )}
                </span>
                <select
                  value={zoneCode}
                  onChange={(e) => {
                    setZoneCode(e.target.value);
                    setEditedZone(true);
                  }}
                  className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-sm text-[var(--text-primary)]"
                  aria-label="용도지역"
                >
                  {ZONE_OPTIONS.map((z) => (
                    <option key={z.code} value={z.code}>
                      {z.label}
                    </option>
                  ))}
                </select>
              </label>

              <div>
                <span className="text-[var(--text-secondary)]">선호 평형</span>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {UNIT_TYPE_OPTIONS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => toggleUnitType(t)}
                      className={`rounded-lg px-2.5 py-1 text-[11px] font-bold transition-colors ${
                        unitTypes.includes(t)
                          ? "bg-[var(--accent-strong)] text-white"
                          : "bg-[var(--surface-soft)] text-[var(--text-tertiary)] border border-[var(--line)]"
                      }`}
                      aria-pressed={unitTypes.includes(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* 2) 법규 슬라이더 — max를 법정 한도로 하드캡 */}
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
            <h4 className="mb-1 text-sm font-black text-[var(--text-primary)]">법규 슬라이더</h4>
            <p className="mb-4 text-[11px] font-bold text-[var(--text-hint)]">
              {limits
                ? `${zoneCode} 법정 한도 안에서만 조절됩니다`
                : "법정 한도를 불러오는 중…"}
            </p>
            <div className="flex flex-col gap-4">
              <LegalSlider
                label="건폐율"
                unit="%"
                value={bcr}
                min={10}
                max={limits?.max_bcr_percent ?? 60}
                step={1}
                onChange={setBcr}
                capLabel={limits ? `법정 건폐율 ≤${limits.max_bcr_percent}%` : undefined}
              />
              <LegalSlider
                label="용적률"
                unit="%"
                value={far}
                min={50}
                max={limits?.max_far_percent ?? 250}
                step={10}
                onChange={setFar}
                capLabel={limits ? `법정 용적률 ≤${limits.max_far_percent}%` : undefined}
              />
              <LegalSlider
                label="목표 세대수"
                unit="세대"
                value={targetUnits}
                min={2}
                max={300}
                step={1}
                onChange={setTargetUnits}
              />
              <LegalSlider
                label="목표 마진"
                unit="%"
                value={targetMargin}
                min={0}
                max={40}
                step={1}
                onChange={setTargetMargin}
              />
            </div>

            {/* 우선순위 */}
            <div className="mt-4">
              <span className="text-[11px] font-bold text-[var(--text-secondary)]">우선순위</span>
              <div className="mt-1.5 grid grid-cols-3 gap-1.5">
                {PRIORITY_OPTIONS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPriority(p)}
                    className={`rounded-lg px-2 py-1.5 text-[11px] font-bold transition-colors ${
                      priority === p
                        ? "bg-[var(--accent-strong)] text-white"
                        : "bg-[var(--surface-soft)] text-[var(--text-tertiary)] border border-[var(--line)]"
                    }`}
                    aria-pressed={priority === p}
                  >
                    {PRIORITY_LABELS[p]}
                  </button>
                ))}
              </div>
            </div>

            {/* §4-A③: 매스 형상 — 선택 시 생성/재생성에 massing_kind 전달(결정론 매스 변형) */}
            <div className="mt-4">
              <span className="text-[11px] font-bold text-[var(--text-secondary)]">매스 형상</span>
              <div className="mt-1.5 grid grid-cols-5 gap-1.5">
                {MASSING_OPTIONS.map((m) => (
                  <button
                    key={m.label}
                    type="button"
                    onClick={() => setMassingKind(m.value)}
                    className={`rounded-lg px-2 py-1.5 text-[11px] font-bold transition-colors ${
                      massingKind === m.value
                        ? "bg-[var(--accent-strong)] text-white"
                        : "bg-[var(--surface-soft)] text-[var(--text-tertiary)] border border-[var(--line)]"
                    }`}
                    aria-pressed={massingKind === m.value}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-[10px] leading-tight text-[var(--text-tertiary)]">
                단일 자동설계는 선택 형상으로 매스를 재산출합니다. Top3는 A=선택(자동 시 대지비율)·B=타워·C=ㄱ자로 다양화됩니다.
              </p>
            </div>

            {/* P5: 정북일조 단계후퇴 토글 — 켜면 상부 층이 북측으로 자동 후퇴(일조 확보, 더 높이) */}
            <div className="mt-4">
              <button
                type="button"
                onClick={() => setDaylightNorth((v) => !v)}
                aria-pressed={daylightNorth}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors ${
                  daylightNorth
                    ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15"
                    : "border-[var(--line)] bg-[var(--surface-soft)]"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="text-[13px]">☀</span>
                  <span className="text-[11px] font-bold text-[var(--text-secondary)]">정북일조 단계후퇴</span>
                </span>
                <span className={`text-[10px] font-black ${daylightNorth ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]"}`}>
                  {daylightNorth ? "ON" : "OFF"}
                </span>
              </button>
              <p className="mt-1 text-[10px] leading-tight text-[var(--text-tertiary)]">
                북측 일조 확보 — 상부 층을 정북 사선제한(높이/2)만큼 자동 후퇴시켜 더 높이 짓습니다.
                음성/자연어로 &ldquo;북측 일조 확보&rdquo;라고 말해도 자동으로 켜집니다.
              </p>
            </div>

            {/* §4-B: 참조 사례 반영 토글 — 켜면 유사 사례 기하(종횡비)를 합성 매스에 주입 */}
            <div className="mt-4">
              <button
                type="button"
                onClick={() => setUseReferences((v) => !v)}
                aria-pressed={useReferences}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors ${
                  useReferences
                    ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15"
                    : "border-[var(--line)] bg-[var(--surface-soft)]"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="text-[13px]">▦</span>
                  <span className="text-[11px] font-bold text-[var(--text-secondary)]">참조 사례 반영</span>
                </span>
                <span className={`text-[10px] font-black ${useReferences ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]"}`}>
                  {useReferences ? "ON" : "OFF"}
                </span>
              </button>
              <p className="mt-1 text-[10px] leading-tight text-[var(--text-tertiary)]">
                관리자가 등록한 유사 사례(용도·면적·평형·용도지역) 중 기하 보유 최상위 사례의 종횡비를
                합성 매스에 반영합니다. 부합 사례가 없으면 자동으로 미적용(정직 표기). 매스 형상을 직접
                고르면 그 형상이 우선합니다.
              </p>
            </div>
          </section>
        </div>

        {/* ── 우: 생성 액션 + 결과 ── */}
        <div className="flex flex-col gap-4">
          {/* 생성 버튼 2종 */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={handleAlternatives}
              disabled={altLoading}
              className="rounded-2xl bg-[var(--accent-strong)] px-4 py-4 text-sm font-black text-white shadow-[var(--shadow-lg)] transition-opacity disabled:opacity-40"
            >
              {altLoading ? "설계안 생성 중…" : "Top3 설계안 생성"}
            </button>
            <button
              type="button"
              onClick={handleSingle}
              disabled={singleLoading}
              className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-4 text-sm font-black text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-soft)] disabled:opacity-40"
            >
              {singleLoading ? "자동설계 중…" : "단일 자동설계"}
            </button>
          </div>

          {(altError || singleError) && (
            <p className="text-xs font-bold text-[var(--status-error)]" role="alert">
              {altError || singleError}
            </p>
          )}

          {/* 비치명 경고(예: 구버전 API 응답 rank 보정) — 결과는 표시하되 사실을 고지 */}
          {altWarning && (
            <p className="text-[11px] font-bold text-amber-400" role="status">
              ⚠ {altWarning}
            </p>
          )}

          {/* 검증·다각평가(P5) — 법규 위반 + 4관점 점수(전부 커널값 기반) */}
          {evaluation && <EvaluationCard ev={evaluation} />}

          {/* 유사 사례 기반 설계안(U4·R6~R8) — 기하 보유 사례는 현재 부지에 맞춰 조립 가능 */}
          {similar.length > 0 && (
            <section className="mt-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
              <h4 className="mb-2 text-sm font-black text-[var(--text-primary)]">유사 사례 기반 설계안 <span className="text-[var(--text-hint)]">({similar.length})</span></h4>
              <div className="space-y-2">
                {similar.map((r) => (
                  <ReferenceAssemblyCard
                    key={r.id}
                    item={r}
                    siteContext={{
                      siteArea,
                      zoneCode,
                      buildingUse: intent?.building_use ?? "공동주택",
                      unitTypes: unitTypes.length > 0 ? unitTypes : ["84A"],
                    }}
                    onApply={(p, s) => {
                      applyDesign(p, s); // 기존 SSOT 경로 재사용 — 2D/3D/BIM/QTO 단일기하 전파
                    }}
                  />
                ))}
              </div>
              <p className="mt-2 text-[10px] text-[var(--text-hint)]">※ 관리자가 등록한 사례를 용도·면적·평형·용도지역 유사도로 검색. 기하 보유 사례는 부지에 맞춘 초안 조립 후 검증 통과 시에만 적용됩니다.</p>
            </section>
          )}

          {/* 설계 편집(P6) — 말/음성으로 현재 설계 수정 → 2D/3D/BIM/QTO 단일기하 전파 */}
          {(single || selectedRank != null) && (
            <section className="mt-4 rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--surface)] p-5">
              <h4 className="mb-2 text-sm font-black text-[var(--text-primary)]">설계 편집 — 말이나 음성으로 수정</h4>
              <div className="relative">
                <input
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleEdit(); }}
                  placeholder="예) 층수 3개 더 올리고 84A 위주로, 거주성 우선"
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 pr-11 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
                  aria-label="설계 편집 자연어 입력"
                />
                {editStt.supported && (
                  <button
                    type="button"
                    onClick={() => (editStt.listening ? editStt.stop() : editStt.start())}
                    title={editStt.listening ? "음성 입력 중지" : "음성으로 편집"}
                    aria-label={editStt.listening ? "음성 입력 중지" : "음성으로 편집"}
                    className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full border transition-all ${editStt.listening ? "border-red-500/50 bg-red-500/15 text-red-400 animate-pulse" : "border-[var(--line)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"}`}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" />
                    </svg>
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={handleEdit}
                disabled={editing || !editText.trim()}
                className="mt-2 w-full rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white transition-opacity disabled:opacity-40"
              >
                {editing ? "편집 적용 중…" : "편집 적용"}
              </button>
              {editStt.listening && <p className="mt-1 text-[11px] font-bold text-red-400">🎙️ 듣는 중… 말씀하세요</p>}
              {appliedChanges.length > 0 && (
                <p className="mt-2 text-[11px] font-bold text-emerald-500">적용됨: {appliedChanges.join(" · ")}</p>
              )}
              <p className="mt-1 text-[10px] text-[var(--text-hint)]">편집은 즉시 2D 도면·3D BIM·물량(QTO)에 동일 기하로 반영됩니다.</p>
            </section>
          )}

          {/* 단일 자동설계 결과 */}
          {single && (
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">
                  단일 자동설계
                </span>
                <div className="flex items-center gap-1.5">
                  <ReferenceChip summary={single.summary} />
                  <MassingChip summary={single.summary} />
                  <ComplianceBadge ok={!!single.compliance.all_pass} />
                </div>
              </div>
              <SummaryRow summary={single.summary} />
              {/* §4-B: 참조 조회가 미적용일 때만 사유 정직 고지(적용 시엔 위 칩이 표시) */}
              <ReferenceUnusedNote reference={single.reference} />
              {/* W-A: 목표(슬라이더) 미달 시 바인딩 제약 — 응답에 있을 때만 표시(정직) */}
              <BindingConstraintChip summary={single.summary} />
              <p className="mt-2 text-[10px] font-bold text-[var(--status-success)]">
                스튜디오에 적용됨 — 2D/3D가 갱신됩니다
              </p>
              {/* W-A: 산출 근거(세트백 실값·일조캡·층수 바인딩·주차/코어 산식) — 접이식 */}
              <BasisSection summary={single.summary} className="mt-2" />
            </div>
          )}

          {/* 부지가 작아 세대 구성이 불가한 경우 — 엔진이 정직하게 0세대로 응답(가짜 세대 금지). */}
          {alternatives.length > 0 && alternatives.every((a) => (a.summary.total_units ?? 0) === 0) && (
            <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 p-4 text-[12px] font-bold leading-relaxed text-[var(--status-warning)]" role="status">
              ⚠ 현재 대지면적·용도지역·선호 평형으로는 세대 구성이 어렵습니다(전 설계안 0세대).
              대지면적을 키우거나, 더 작은 평형(예: 29A·39A)을 선택하거나, 용적률·세대수 목표를 조정해 다시 생성해 보세요.
              <span className="mt-1 block text-[10px] font-bold text-[var(--text-hint)]">가짜 세대수를 만들지 않고 정직하게 표기합니다.</span>
            </div>
          )}

          {/* §4-B: Top3에서 참조 미적용 시 사유 정직 고지(적용 시엔 A 카드 칩이 표시) */}
          {alternatives.length > 0 && <ReferenceUnusedNote reference={altReference} />}

          {/* Top3 카드 */}
          {alternatives.length > 0 ? (
            <div className="grid gap-3" role="group" aria-label="Top3 설계안">
              {alternatives.map((alt, idx) => {
                const recommended = recommendedIdx === idx;
                const selected = selectedRank === alt.rank;
                return (
                  <button
                    key={alt.rank}
                    type="button"
                    onClick={() => handleSelectAlt(alt)}
                    aria-label={`${alt.alternative_name} 설계안 선택`}
                    aria-pressed={selected}
                    className={`group relative rounded-2xl border p-4 text-left transition-all ${
                      selected
                        ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[var(--shadow-lg)]"
                        : "border-[var(--line)] bg-[var(--surface)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-soft)]"
                    }`}
                  >
                    {/* 추천 배지 */}
                    {recommended && (
                      <span className="absolute -top-2 left-4 rounded-full bg-[var(--accent-strong)] px-2.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-white shadow-md">
                        ★ 추천
                      </span>
                    )}
                    <div className="mb-2.5 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-black text-[var(--text-primary)]">
                          {alt.alternative_name}
                        </span>
                        <span className="text-[10px] font-bold text-[var(--text-hint)]">
                          {PRIORITY_LABELS[alt.priority]}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <ReferenceChip summary={alt.summary} />
                        <MassingChip summary={alt.summary} />
                        <ComplianceBadge ok={alt.compliant ?? !!alt.compliance.all_pass} />
                      </div>
                    </div>

                    {/* 핵심 수치(cc-num) — total_units는 실건축가능치 신뢰 */}
                    <div className="grid grid-cols-4 gap-2">
                      <Metric label="세대" value={`${alt.summary.total_units}`} />
                      <Metric label="층수" value={`${alt.summary.num_floors}F`} />
                      <Metric label="건폐율" value={`${alt.summary.bcr_percent.toFixed(0)}%`} />
                      <Metric label="용적률" value={`${alt.summary.far_percent.toFixed(0)}%`} />
                    </div>

                    {/* W-A: 목표(슬라이더) 미달 시 바인딩 제약 — 응답에 있을 때만 표시(정직) */}
                    <BindingConstraintChip summary={alt.summary} />

                    {/* 평형배분 미니바(ratio_pct만 사용) */}
                    {alt.unit_mix?.distribution?.length > 0 && (
                      <div className="mt-3">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
                            평형 배분
                          </span>
                          <span className="text-[10px] font-black tabular-nums text-[var(--accent-strong)]">
                            점수 {Math.round(alt.score)}
                          </span>
                        </div>
                        <MixBar distribution={alt.unit_mix.distribution} />
                      </div>
                    )}

                    {selected && (
                      <p className="mt-2.5 text-[10px] font-black text-[var(--accent-strong)]">
                        ✓ 스튜디오에 로드됨 — 2D/3D가 이 설계안으로 갱신됩니다
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            !altLoading &&
            !single && (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface)] p-10 text-center">
                <span className="text-2xl">✦</span>
                <p className="text-sm font-black text-[var(--text-secondary)]">
                  아직 생성된 설계안이 없습니다
                </p>
                <p className="max-w-xs text-[11px] leading-relaxed text-[var(--text-hint)]">
                  말로 설명하거나 슬라이더로 의도를 정한 뒤 위 버튼으로 설계안을 생성하세요. 가짜
                  수치는 표시하지 않습니다.
                </p>
              </div>
            )
          )}

          {/* W-A: 선택 설계안 산출 근거 — 카드(버튼) 중첩을 피해 그리드 밖에서 렌더 */}
          {selectedAlt && (
            <BasisSection summary={selectedAlt.summary} title="선택 설계안 산출 근거" />
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * W-A: 목표 미달 바인딩 제약 칩 — 실제 목표 미달일 때만 표시(정직 게이트).
 *
 * W-A 응답은 binding_constraint를 항상 포함(기본 "far")하므로 필드 존재만으론
 * "목표 미달"을 단정할 수 없다. 다음을 모두 만족할 때만 칩을 띄운다:
 *  · 목표 용적률(슬라이더)이 basis.applied_limits에 기록돼 있고
 *  · 달성 용적률이 목표보다 낮으며(허용오차 0.5%p — 반올림 노이즈 차단)
 *  · 막은 것이 외부 한도일 때(height/sunlight/setback, 또는 법정 FAR<목표).
 *    binding=far인데 법정≥목표면 자기 목표가 캡(층수 정수화) — 칩 비표시.
 * 구버전 응답(필드 부재)은 어떤 것도 표시하지 않는다(가짜 경고 금지).
 */
function BindingConstraintChip({ summary }: { summary: AutoDesignResponse["summary"] }) {
  const s = summary as AutoDesignResponse["summary"] & SummaryExtras;
  const code =
    typeof s.binding_constraint === "string" ? s.binding_constraint.trim().toLowerCase() : "";
  if (!code) return null;
  const { targetFar, statutoryFar } = readFarLimits(s.basis);
  if (targetFar == null) return null;
  if (!(summary.far_percent < targetFar - 0.5)) return null;
  if (code === "far" && !(statutoryFar != null && statutoryFar < targetFar)) return null;
  const label = BINDING_CONSTRAINT_LABELS[code] ?? code;
  return (
    <span
      className="mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-black"
      style={{
        color: "var(--status-warning)",
        background: "color-mix(in srgb, var(--status-warning) 14%, transparent)",
        border: "1px solid color-mix(in srgb, var(--status-warning) 40%, transparent)",
      }}
    >
      목표 미달 — {label} 한도가 막음
    </span>
  );
}

/**
 * W-A: 산출 근거 접이식 섹션 — summary.basis(신설)를 EvidencePanel로 렌더.
 * 구버전 응답(필드 부재)·형태 불명 값은 렌더하지 않는다(가짜 근거 금지).
 */
function BasisSection({
  summary,
  title = "산출 근거",
  className = "",
}: {
  summary: AutoDesignResponse["summary"];
  title?: string;
  className?: string;
}) {
  const items = toEvidenceItems((summary as AutoDesignResponse["summary"] & SummaryExtras).basis);
  if (items.length === 0) return null;
  return <EvidencePanel title={title} items={items} defaultOpen={false} className={className} />;
}

/** 법정 한도로 max를 하드캡한 슬라이더(토큰색 accent-color). */
function LegalSlider({
  label,
  unit,
  value,
  min,
  max,
  step,
  onChange,
  capLabel,
}: {
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  capLabel?: string;
}) {
  // 한도 변경으로 max보다 큰 값이 남아있으면 표시상으로도 클램프
  const clamped = Math.min(value, max);
  const pct = max > min ? ((clamped - min) / (max - min)) * 100 : 0;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-bold text-[var(--text-secondary)]">{label}</span>
        <span className="text-sm font-black tabular-nums text-[var(--text-primary)]">
          {clamped}
          <span className="ml-0.5 text-[10px] font-bold text-[var(--text-hint)]">{unit}</span>
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={clamped}
        onChange={(e) => onChange(Math.min(Number(e.target.value), max))}
        aria-label={`${label} (${unit})`}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full"
        style={{
          accentColor: "var(--accent-strong)",
          background: `linear-gradient(90deg, var(--accent-strong) ${pct}%, var(--line) ${pct}%)`,
        }}
      />
      {capLabel && (
        <p className="mt-1 text-[10px] font-bold text-[var(--text-hint)]">{capLabel}</p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--surface-soft)] px-2 py-1.5 text-center">
      <div className="cc-num text-base leading-none">{value}</div>
      <div className="mt-1 text-[9px] font-bold uppercase tracking-wide text-[var(--text-hint)]">
        {label}
      </div>
    </div>
  );
}

function SummaryRow({
  summary,
}: {
  summary: {
    total_units: number;
    num_floors: number;
    bcr_percent: number;
    far_percent: number;
    building_height_m: number;
    parking_count: number;
  };
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <Metric label="세대" value={`${summary.total_units}`} />
      <Metric label="층수" value={`${summary.num_floors}F`} />
      <Metric label="높이" value={`${summary.building_height_m.toFixed(0)}m`} />
      <Metric label="건폐율" value={`${summary.bcr_percent.toFixed(0)}%`} />
      <Metric label="용적률" value={`${summary.far_percent.toFixed(0)}%`} />
      <Metric label="주차" value={`${summary.parking_count}`} />
    </div>
  );
}

/**
 * §4-A: 적용된 매스 형상 라벨 칩 — summary.massing_label이 있을 때만 표시(정직 게이트).
 * 구버전 응답(필드 부재)·auto(자동)는 칩을 띄우지 않는다(가짜·중복 표기 금지).
 */
function MassingChip({ summary }: { summary: AutoDesignResponse["summary"] }) {
  const label = typeof summary.massing_label === "string" ? summary.massing_label.trim() : "";
  // auto(자동·대지비율)는 별도 선택 형상이 아니므로 칩 비표시 — 명시 형상만 강조.
  if (!label || !summary.massing_kind || summary.massing_kind === "auto") return null;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-black"
      style={{
        color: "var(--accent-strong)",
        background: "var(--accent-soft)",
        border: "1px solid color-mix(in srgb, var(--accent-strong) 35%, transparent)",
      }}
    >
      {label}
    </span>
  );
}

/**
 * §4-B: 적용된 참조 사례 라벨 칩 — summary.reference.used일 때만 표시(정직 게이트).
 * 미적용·구버전 응답(필드 부재)은 칩을 띄우지 않는다(가짜·중복 표기 금지).
 */
function ReferenceChip({ summary }: { summary: AutoDesignResponse["summary"] }) {
  const ref = summary.reference;
  if (!ref || !ref.used) return null;
  const title = typeof ref.title === "string" ? ref.title.trim() : "";
  const sim = typeof ref.similarity === "number" && Number.isFinite(ref.similarity)
    ? Math.round(ref.similarity)
    : null;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-black"
      style={{
        color: "var(--status-success)",
        background: "color-mix(in srgb, var(--status-success) 14%, transparent)",
        border: "1px solid color-mix(in srgb, var(--status-success) 38%, transparent)",
      }}
      title={typeof ref.basis === "string" ? ref.basis : undefined}
    >
      참조{title ? ` · ${title}` : ""}{sim != null ? ` ${sim}` : ""}
    </span>
  );
}

/**
 * §4-B: 참조 조회 결과가 '미적용'일 때만 사유를 정직 고지(used=true는 칩이 대신 표시).
 * 블록 자체가 없으면(use_references=false·구버전) 아무것도 렌더하지 않는다.
 */
function ReferenceUnusedNote({ reference }: { reference?: ReferenceResultBlock | null }) {
  if (!reference || reference.used) return null;
  const note = typeof reference.note === "string" ? reference.note.trim() : "";
  return (
    <p className="mt-1.5 text-[10px] font-bold text-[var(--text-hint)]">
      ▦ 참조 사례 미적용{note ? ` — ${note}` : ""}
    </p>
  );
}

function ComplianceBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-black"
      style={{
        color: ok ? "var(--status-success)" : "var(--status-warning)",
        background: ok
          ? "color-mix(in srgb, var(--status-success) 16%, transparent)"
          : "color-mix(in srgb, var(--status-warning) 16%, transparent)",
        border: `1px solid color-mix(in srgb, ${
          ok ? "var(--status-success)" : "var(--status-warning)"
        } 40%, transparent)`,
      }}
    >
      {ok ? "법규 적합" : "법규 검토"}
    </span>
  );
}

/** 평형배분 미니바 — distribution의 ratio_pct만 사용(이론치 혼동 금지). */
function MixBar({
  distribution,
}: {
  distribution: Array<{ code: string; name: string; ratio_pct: number }>;
}) {
  const palette = [
    "var(--accent-strong)",
    "color-mix(in srgb, var(--accent-strong) 70%, var(--surface))",
    "color-mix(in srgb, var(--accent-strong) 45%, var(--surface))",
    "color-mix(in srgb, var(--accent-strong) 28%, var(--surface))",
  ];
  const total = distribution.reduce((s, d) => s + (d.ratio_pct || 0), 0) || 100;
  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--surface-soft)]">
        {distribution.map((d, i) => (
          <div
            key={d.code}
            style={{
              width: `${(d.ratio_pct / total) * 100}%`,
              background: palette[i % palette.length],
            }}
            title={`${d.name} ${Math.round(d.ratio_pct)}%`}
          />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
        {distribution.map((d, i) => (
          <span key={d.code} className="flex items-center gap-1 text-[9px] font-bold text-[var(--text-secondary)]">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: palette[i % palette.length] }}
            />
            {d.code} {Math.round(d.ratio_pct)}%
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * 검증·다각평가 카드(P5) — 법규 위반 배지 + 4관점(수익/거주/법규/시공) 점수 바.
 * 모든 수치는 설계 엔진(커널) 산출값 기준 — LLM 생성 아님(가짜수치 없음).
 */
function EvaluationCard({ ev }: { ev: DesignEval }) {
  const lenses = ev.lenses?.lenses ?? [];
  const overall = ev.lenses?.overall ?? 0;
  const errors = (ev.violations ?? []).filter((v) => v.severity === "error");
  const warns = (ev.violations ?? []).filter((v) => v.severity === "warn");
  const barColor = (s: number) => (s >= 80 ? "#10b981" : s >= 60 ? "#f59e0b" : "#ef4444");
  return (
    <section className="mt-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-black text-[var(--text-primary)]">법규 검증 · 다각 평가</h4>
        <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-black text-[var(--accent-strong)]">종합 {overall}점</span>
      </div>
      {errors.length === 0 && warns.length === 0 ? (
        <p className="mb-3 text-xs font-bold text-emerald-500">✓ 법정 한도 내 적합 — 위반 없음</p>
      ) : (
        <div className="mb-3 space-y-1">
          {errors.map((v, i) => (
            <p key={`e${i}`} className="text-xs font-bold text-red-400">⚠️ {v.message}</p>
          ))}
          {warns.map((v, i) => (
            <p key={`w${i}`} className="text-[11px] text-amber-400">· {v.message}</p>
          ))}
        </div>
      )}
      <div className="space-y-2">
        {lenses.map((L) => (
          <div key={L.lens}>
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-bold text-[var(--text-secondary)]">{L.label}</span>
              <span className="font-black text-[var(--text-primary)]">{L.score}</span>
            </div>
            <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
              <div className="h-full rounded-full" style={{ width: `${L.score}%`, backgroundColor: barColor(L.score) }} />
            </div>
            <p className="mt-0.5 text-[10px] text-[var(--text-hint)]">{L.basis}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[10px] text-[var(--text-hint)]">※ 모든 수치는 설계 엔진 산출값 기준(가짜수치 없음). 법규 위반은 표시·차단됩니다.</p>
    </section>
  );
}
