"use client";

/**
 * AI 건축 설계 스튜디오 — 한국 건축법 기반 즉시 계산 + AI 심층 분석 + 매싱 옵션.
 * 프로젝트 탭과 독립 메뉴(/design-studio) 양쪽에서 재사용(projectId 주입).
 */

import React, { useState, useMemo, useEffect, useRef } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { AlertTriangle, Check, CheckCircle2, Lightbulb } from "lucide-react";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { getZoningSpec, calcMaxGrossArea, calcParkingRequired, normalizeZoning } from "@/lib/kr-building-regulations";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { useProjectStore } from "@/store/useProjectStore";
import { NumberInput } from "@/components/common/NumberInput";
import { SolarEnvelopeCard } from "@/components/projects/SolarEnvelopeCard";

// 일반인용 쉬운 설명(용어 풀이) — '쉬운 설명' 토글 시 표시
const EASY: Record<string, string> = {
  건폐율: "땅 면적 중 건물 1층이 덮을 수 있는 비율. 높을수록 넓게 지음.",
  용적률: "땅 면적 대비 전체 층 바닥면적 합의 비율. 높을수록 많이(높이) 지음.",
  "예상 층수": "용적률·높이제한으로 지을 수 있는 대략의 층수.",
  "주차 대수": "법으로 확보해야 하는 최소 주차 칸 수.",
  "최대 연면적": "모든 층 바닥면적을 합한 최대 건축 가능 면적(분양·사업성의 기준).",
  매싱: "건물 덩어리의 배치 모양(판상형=일자, 타워형=고층 1동 등).",
  일조: "겨울에도 햇빛이 드는지(정북일조)·그림자 길이. 인접 대지·민원과 직결.",
};

type DesignResult = {
  buildingCoverage?: { value: number; max: number; unit: string };
  floorAreaRatio?: { value: number; max: number; unit: string };
  maxFloors?: number;
  maxHeight?: { value: number; unit: string };
  totalGrossArea?: { value: number; unit: string };
  parkingRequired?: number;
  setbacks?: { front: number; side: number; rear: number; unit: string };
  massingOptions?: Array<{ name: string; description: string; efficiency: number }>;
  summary?: string;
};

/* ── ① 주소 정합성 가드 — 부지분석(siteAnalysis)이 "현 프로젝트 주소"의 결과인지 판정 ──
   프로젝트 레코드(useProjectStore) 주소와 siteAnalysis.address를 정규화(시군구·법정동·번지
   토큰) 비교한다. 다른 프로젝트의 잔류 스냅샷이 폼 시드·designData를 오염시키는 것을 차단.
   판정 불가(주소 한쪽 부재, 도로명↔지번 혼용 등)는 null을 반환해 과차단을 막는다(하위호환). */

/** 주소에서 비교용 핵심 토큰 추출: 행정구역(…시/군/구/읍/면/동/리/가/로/길)·번지(숫자). */
function addressKeyTokens(addr?: string | null): { region: string[]; jibun: string | null; road: boolean } {
  const toks = (addr || "")
    .replace(/\([^)]*\)/g, " ") // 괄호 부가표기 제거
    .split(/[\s,]+/)
    .filter(Boolean);
  const region: string[] = [];
  let jibun: string | null = null;
  let road = false;
  for (const t of toks) {
    if (/^산?\d+(-\d+)?(번지)?$/.test(t)) {
      jibun = t.replace(/번지$/, "");
    } else if (/(로|길)$/.test(t)) {
      road = true;
      region.push(t);
    } else if (/(시|군|구|읍|면|동|리|가)$/.test(t)) {
      // 광역단위 표기 차이("서울특별시" vs "서울시") 흡수
      region.push(t.replace(/(특별자치시|특별자치도|특별시|광역시)$/, "시"));
    }
  }
  return { region, jibun, road };
}

/** 동일 부지 여부: true=일치 / false=불일치 확정 / null=판정 불가(차단하지 않음). */
function isSameSite(a?: string | null, b?: string | null): boolean | null {
  const A = (a || "").replace(/\s+/g, "");
  const B = (b || "").replace(/\s+/g, "");
  if (!A || !B) return null; // 한쪽 주소 부재 — 판정 불가
  if (A === B || A.includes(B) || B.includes(A)) return true;
  const ka = addressKeyTokens(a);
  const kb = addressKeyTokens(b);
  // 도로명 표기 vs 지번 표기 혼용은 토큰 비교가 불가능 — 판정 보류(과차단 방지)
  if (ka.road !== kb.road) return null;
  // 번지가 양쪽 모두 있고 다르면 다른 부지로 확정
  if (ka.jibun && kb.jibun && ka.jibun !== kb.jibun) return false;
  const [shorter, longer] =
    ka.region.length <= kb.region.length ? [ka.region, kb.region] : [kb.region, ka.region];
  if (shorter.length === 0) return null; // 비교 가능한 행정구역 토큰 없음 — 판정 불가
  return shorter.every((t) => longer.includes(t));
}

/* ── ③ 매싱 실프리뷰 기하 모델 ──
   calc(kr-building-regulations 법정한도) 실값으로 footprint를 산출해 2분할 도식
   (좌: 미니 배치평면, 우: 악소노메트릭 층 슬래브)을 구동한다. blocks 좌표는
   부지 정사각(한 변 siteSide m = √대지면적, 원점=북서) 기준 미터 단위. */
type MassingBlock = { x: number; y: number; w: number; h: number }; // w=폭(동서)·h=깊이(남북), m
type MassingGeom = { floors: number; blocks: MassingBlock[]; siteSide: number };
type MassingKind = "slab" | "tower" | "lshape" | "court";

/** AI 폴백 등 이름만 있을 때의 형태 매칭(종전 MassingDiagram 매칭 규칙 유지). */
function massingKindFromName(name?: string | null): MassingKind {
  const n = name || "";
  if (n.includes("타워")) return "tower";
  if (n.includes("ㄱ") || n.includes("L")) return "lshape";
  if (n.includes("중정") || n.includes("ㅁ")) return "court";
  return "slab"; // 판상형(기본)
}

/**
 * footprint(=연면적/층수, 건축가능면적 이내)·대지 한 변·층수 실값으로 블록 배치를 생성.
 * 시각 클램프는 도식이 대지경계를 넘지 않게 하기 위한 것으로, 주석 표기는 생성된
 * 블록의 실제 치수를 그대로 사용한다(가짜값 없음 — "약" 표기).
 */
function buildMassingGeom(
  kind: MassingKind,
  footprintSqm: number,
  siteSide: number,
  floors: number,
): MassingGeom | null {
  if (!(footprintSqm > 0) || !(siteSide > 0) || !(floors > 0)) return null;
  const S = siteSide;
  const F = Math.min(footprintSqm, S * S * 0.8); // 도식 안전 클램프
  const m = S * 0.07; // 경계 여백(도식용)
  const inner = S - m * 2;
  const blocks: MassingBlock[] = [];
  if (kind === "tower") {
    // 타워 1동 — 정방형에 가깝게, 중앙 배치
    const w = Math.min(Math.sqrt(F), inner * 0.7);
    const d = Math.min(F / w, inner * 0.9);
    blocks.push({ x: m + (inner - w) / 2, y: m + (inner - d) / 2, w, h: d });
  } else if (kind === "lshape") {
    // L형 2블록 — 남측 가로동(6할) + 서측 세로동(4할)
    const A1 = F * 0.6;
    const A2 = F * 0.4;
    const w1 = Math.min(inner * 0.92, Math.sqrt(3 * A1));
    const d1 = Math.min(A1 / w1, inner * 0.45);
    const d2 = Math.min(Math.sqrt(2.5 * A2), inner * 0.92 - d1);
    const w2 = Math.min(A2 / Math.max(d2, 0.1), inner * 0.5);
    const x0 = m + (inner - w1) / 2;
    const yBar = m + inner - d1;
    blocks.push({ x: x0, y: yBar, w: w1, h: d1 });
    blocks.push({ x: x0, y: Math.max(m, yBar - d2), w: w2, h: Math.min(d2, yBar - m) });
  } else if (kind === "court") {
    // 중정형 — 4변 링(AI 폴백 전용; 로컬 산출 옵션에는 없음)
    const o = inner * 0.85;
    const t = Math.min(o * 0.32, Math.max(o * 0.12, F / (4 * o)));
    const x0 = m + (inner - o) / 2;
    const y0 = m + (inner - o) / 2;
    blocks.push({ x: x0, y: y0, w: o, h: t });
    blocks.push({ x: x0, y: y0 + o - t, w: o, h: t });
    blocks.push({ x: x0, y: y0 + t, w: t, h: o - 2 * t });
    blocks.push({ x: x0 + o - t, y: y0 + t, w: t, h: o - 2 * t });
  } else {
    // 판상형 2개동 — 남향 평행 배치(동서로 긴 슬래브 2장)
    const A1 = F / 2;
    let w = Math.min(inner * 0.92, Math.sqrt(3 * A1));
    let d = A1 / w;
    if (2 * d > inner * 0.84) {
      d = inner * 0.42;
      w = Math.min(A1 / d, inner * 0.92);
    }
    const gap = Math.max((inner - 2 * d) / 3, 0);
    const x = m + (inner - w) / 2;
    blocks.push({ x, y: m + gap, w, h: d });
    blocks.push({ x, y: m + gap * 2 + d, w, h: d });
  }
  return { floors: Math.max(1, Math.round(floors)), blocks, siteSide: S };
}

/**
 * 매싱 도식 — 실측 geom이 있으면 2분할(좌: 배치평면 footprint+대지경계+N방위 /
 * 우: 악소노메트릭 층 슬래브 라인) 실프리뷰, 없으면 종전 이름 매칭 단위도식 폴백
 * (실척 주석 없음 — 정직 표기).
 */
function MassingDiagram({ name, active, geom }: { name: string; active?: boolean; geom?: MassingGeom | null }) {
  const c = active ? "var(--accent-strong)" : "var(--text-tertiary)";
  const fill = active ? "var(--accent-soft)" : "var(--surface-muted)";

  if (!geom || geom.blocks.length === 0) {
    // 폴백: 종전 간이 3D 도식(이름 매칭) — 실척 정보가 없으므로 치수 주석을 달지 않는다.
    const n = name || "";
    const blocks =
      n.includes("타워") ? [{ x: 40, y: 14, w: 20, h: 46 }]
      : n.includes("ㄱ") || n.includes("L") ? [{ x: 18, y: 34, w: 44, h: 16 }, { x: 18, y: 18, w: 16, h: 32 }]
      : n.includes("중정") || n.includes("ㅁ") ? [{ x: 16, y: 18, w: 14, h: 40 }, { x: 70, y: 18, w: 14, h: 40 }, { x: 16, y: 18, w: 68, h: 12 }, { x: 16, y: 46, w: 68, h: 12 }]
      : [{ x: 14, y: 22, w: 30, h: 38 }, { x: 56, y: 22, w: 30, h: 38 }]; // 판상형(기본)
    return (
      <svg viewBox="0 0 100 70" className="h-16 w-full">
        <line x1="6" y1="62" x2="94" y2="62" stroke={c} strokeWidth="1" opacity="0.4" />
        {blocks.map((b, i) => (
          <g key={i}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="1.5" fill={fill} stroke={c} strokeWidth="1.4" />
            <polygon points={`${b.x},${b.y} ${b.x + 5},${b.y - 5} ${b.x + b.w + 5},${b.y - 5} ${b.x + b.w},${b.y}`} fill={c} opacity="0.25" />
            <polygon points={`${b.x + b.w},${b.y} ${b.x + b.w + 5},${b.y - 5} ${b.x + b.w + 5},${b.y + b.h - 5} ${b.x + b.w},${b.y + b.h}`} fill={c} opacity="0.4" />
          </g>
        ))}
      </svg>
    );
  }

  const S = geom.siteSide;
  const fl = geom.floors;
  // 좌측 패널: 배치평면(부지좌표 m → px)
  const PX = 6, PY = 6, PS = 72;
  const s = PS / S;
  // 우측 패널: 악소노메트릭(깊이 단축 투영 + 층 슬래브)
  const AX = 106, AYB = 82, AW = 88, AH = 70;
  const KX = 0.5, KY = 0.3; // 깊이 단축 계수
  const hM = fl * 3.3; // 층고 3.3m 가정(localCalc와 동일)
  let extX = 1;
  let extY = 1;
  for (const b of geom.blocks) {
    const dist = S - (b.y + b.h); // 남측 경계로부터의 거리(후방 블록은 우상향 이동)
    extX = Math.max(extX, b.x + dist * KX + b.w + b.h * KX);
    extY = Math.max(extY, hM + dist * KY + b.h * KY);
  }
  const s2 = Math.min(AW / extX, AH / extY);
  const ordered = [...geom.blocks].sort((a, b) => a.y - b.y); // 북측(후면)부터 — 전면 블록이 덮도록
  const b0 = geom.blocks[0];

  return (
    <svg viewBox="0 0 200 96" className="h-24 w-full">
      {/* 좌: 미니 배치평면 — 대지경계(파선) + footprint */}
      <rect x={PX} y={PY} width={PS} height={PS} fill="none" stroke={c} strokeWidth="0.8" strokeDasharray="3 2" opacity="0.55" />
      {geom.blocks.map((b, i) => (
        <rect key={`p${i}`} x={PX + b.x * s} y={PY + b.y * s} width={b.w * s} height={b.h * s} rx="0.8" fill={fill} stroke={c} strokeWidth="1.1" />
      ))}
      {/* N 방위(정북=위) */}
      <g opacity="0.8">
        <line x1={PX + PS - 7} y1={PY + 13} x2={PX + PS - 7} y2={PY + 5} stroke={c} strokeWidth="0.9" />
        <polygon points={`${PX + PS - 9},${PY + 7} ${PX + PS - 7},${PY + 3} ${PX + PS - 5},${PY + 7}`} fill={c} />
        <text x={PX + PS - 7} y={PY + 19} textAnchor="middle" fontSize="5" fill={c} fontWeight="700">N</text>
      </g>
      {/* footprint 폭×깊이 실척 주석 */}
      <text x={PX} y={86} fontSize="5" fill="var(--text-hint)">동 약 {Math.round(b0.w)}×{Math.round(b0.h)}m</text>
      <text x={PX} y={93} fontSize="4.5" fill="var(--text-hint)">대지변 약 {Math.round(S)}m · 정사각 가정</text>
      {/* 우: 악소노메트릭 — 지반선 + 층 슬래브 라인 */}
      <line x1={AX - 4} y1={AYB + 1} x2="198" y2={AYB + 1} stroke={c} strokeWidth="0.8" opacity="0.4" />
      {ordered.map((b, i) => {
        const dist = S - (b.y + b.h);
        const fx = AX + (b.x + dist * KX) * s2;
        const fy = AYB - dist * KY * s2;
        const w = b.w * s2;
        const H = hM * s2;
        const ox = b.h * KX * s2;
        const oy = b.h * KY * s2;
        const slabs: number[] = [];
        for (let f = 1; f < fl && f <= 40; f++) slabs.push(fy - (H * f) / fl);
        return (
          <g key={`a${i}`}>
            <polygon points={`${fx},${fy - H} ${fx + ox},${fy - H - oy} ${fx + w + ox},${fy - H - oy} ${fx + w},${fy - H}`} fill={c} opacity="0.22" />
            <polygon points={`${fx + w},${fy - H} ${fx + w + ox},${fy - H - oy} ${fx + w + ox},${fy - oy} ${fx + w},${fy}`} fill={c} opacity="0.38" />
            <rect x={fx} y={fy - H} width={w} height={H} fill={fill} stroke={c} strokeWidth="1" />
            {slabs.map((sy, j) => (
              <line key={j} x1={fx} y1={sy} x2={fx + w} y2={sy} stroke={c} strokeWidth="0.45" opacity="0.55" />
            ))}
          </g>
        );
      })}
      <text x="198" y={93} textAnchor="end" fontSize="5" fill="var(--text-hint)">{fl}층 슬래브</text>
    </svg>
  );
}

// ② 폼 기본값 — projectId 전환 리셋·시드 해제 시 복귀 기준(단일 정의).
const DEFAULT_FORM = { landArea: "500", zoning: "제2종일반주거지역", buildingUse: "공동주택" };

export function DesignStudio({ projectId }: { projectId?: string }) {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<DesignResult>();
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const [easy, setEasy] = useState(false);   // 일반인용 쉬운 설명 토글

  // ① 정합성 가드 — 프로젝트 레코드 주소 vs siteAnalysis.address 정규화 비교.
  const effectiveProjectId = projectId ?? ctxProjectId ?? null;
  const projectRecord = useProjectStore((s) =>
    effectiveProjectId ? s.projects.find((p) => p.id === effectiveProjectId) : undefined,
  );
  const params = useParams();
  const locale = typeof params?.locale === "string" ? params.locale : "ko";
  const siteAnalysisHref = effectiveProjectId
    ? `/${locale}/projects/${effectiveProjectId}/site-analysis`
    : `/${locale}/projects`;
  // "match"   : 주소 일치(또는 판정 불가 — 과차단 방지) → 연동 라벨·시드 허용
  // "mismatch": 다른 주소의 잔류 분석 결과 → 경고 라벨 + 시드/designData 기록 차단
  // "none"    : 부지분석 미실행 → 안내 + 부지분석 링크
  const siteMatch: "match" | "mismatch" | "none" = useMemo(() => {
    if (!siteAnalysis) return "none";
    return isSameSite(projectRecord?.address, siteAnalysis.address) === false ? "mismatch" : "match";
  }, [siteAnalysis, projectRecord?.address]);
  const isSiteMatched = siteMatch === "match";

  const [form, setForm] = useState({ ...DEFAULT_FORM });
  // 사용자가 용도지역을 수동 변경하면 부지분석 SSOT 시드를 더 이상 덮어쓰지 않는다.
  const [zoneEdited, setZoneEdited] = useState(false);
  // 사용자가 폼(면적·용도지역·건물용도)을 직접 수정했는가 — 부지분석 미실행 상태에서도
  // 사용자 직접 입력 기반 계산은 designData에 기록을 허용하기 위한 신호(②).
  const [userEdited, setUserEdited] = useState(false);
  // 매싱 대안 사용자 선택(판상형/타워형/ㄱ자형). null이면 추천(최고 효율)이 활성.
  const [selectedMassing, setSelectedMassing] = useState<string | null>(null);

  // ② projectId 변경 시 폼 기본값 리셋 — 이전 프로젝트의 시드/입력값 잔류 차단.
  const prevProjectRef = useRef(effectiveProjectId);
  useEffect(() => {
    if (prevProjectRef.current === effectiveProjectId) return;
    prevProjectRef.current = effectiveProjectId;
    setForm({ ...DEFAULT_FORM });
    setZoneEdited(false);
    setUserEdited(false);
  }, [effectiveProjectId]);

  // 부지분석(SSOT)에서 대지면적·용도지역을 시드한다. 용도지역은 변형 표기
  // (예: "일반상업", 공백/괄호 포함)를 정규화하여 calc 한도가 정식 키와 정합되게 한다.
  // 정규화 실패 시 원문을 보존(드롭다운 표시·SolarEnvelope zone 폴백 유지).
  // ① 가드: 주소 일치(match) 시에만 시드. 미실행(none)·불일치(mismatch)면 시드를 차단하고
  // 잔류 시드값을 기본값으로 복귀시키되, 사용자가 직접 수정한 값은 보존한다.
  useEffect(() => {
    if (!siteAnalysis || !isSiteMatched) {
      setForm((prev) => {
        const landArea = userEdited ? prev.landArea : DEFAULT_FORM.landArea;
        const zoning = zoneEdited ? prev.zoning : DEFAULT_FORM.zoning;
        if (landArea === prev.landArea && zoning === prev.zoning) return prev;
        return { ...prev, landArea, zoning };
      });
      return;
    }
    const seededZone = normalizeZoning(siteAnalysis.zoneCode) || siteAnalysis.zoneCode || null;
    // ★다필지면 통합 면적(effectiveLandAreaSqm)으로 폼을 시드한다 — 단일 PNU 분석이
    //   landAreaSqm을 대표값으로 덮어써도 설계가 통합 면적 기준으로 GFA를 계산하게.
    const seedArea = effectiveLandAreaSqm(siteAnalysis);
    setForm((prev) => ({
      ...prev,
      landArea: seedArea ? String(seedArea) : prev.landArea,
      zoning: !zoneEdited && seededZone ? seededZone : prev.zoning,
    }));
  }, [siteAnalysis, zoneEdited, isSiteMatched, userEdited]);

  // 용도지역 단일출처(SSOT) 해소: 사용자가 직접 수정하지 않았으면 부지분석
  // zoneCode를 정규화한 값을 GFA 계산의 진실원으로 사용한다. form.zoning은 비동기
  // 시드(effect)라 초기 1프레임 동안 기본값(제2종)일 수 있는데, 그 사이 designData-write
  // effect가 250% 기본 GFA를 store에 영속화하던 R1 회귀를 차단한다(과소 GFA→ROI 오염).
  // ① 가드: 주소 불일치 시 다른 부지의 zoneCode가 계산을 구동하지 않도록 일치 시에만 사용.
  const effectiveZoning = useMemo(() => {
    if (zoneEdited) return form.zoning;
    if (!isSiteMatched) return form.zoning;
    return normalizeZoning(siteAnalysis?.zoneCode) || form.zoning;
  }, [zoneEdited, form.zoning, siteAnalysis?.zoneCode, isSiteMatched]);

  const localCalc = useMemo(() => {
    const area = Number(form.landArea) || 0;
    const spec = getZoningSpec(effectiveZoning);
    if (!spec || area <= 0) return null;
    // 실효 용적률 우선: 부지분석(special_parcel/조례/계획 반영) effectiveFarPct가 있으면
    // 법정상한(kr-building-regulations spec.floorAreaRatioMax) 대신 이를 진실원으로 쓴다.
    // 주소 불일치 잔류 스냅샷이 다른 부지값을 구동하지 않도록 일치(또는 미실행) 시에만 적용.
    // 미확보 시 기존 동작(법정상한 폴백) 유지 — 무회귀.
    const effFarPct =
      siteMatch !== "mismatch" && typeof siteAnalysis?.effectiveFarPct === "number" && siteAnalysis.effectiveFarPct > 0
        ? siteAnalysis.effectiveFarPct
        : null;
    const farUsed = effFarPct ?? spec.floorAreaRatioMax; // 적용 용적률(%) — 실효 우선, 법정 폴백
    const farIsEffective = effFarPct != null;            // 실효값 적용 여부(라벨·근거 표기용)
    const maxGross = effFarPct != null ? area * (effFarPct / 100) : calcMaxGrossArea(area, effectiveZoning);
    const parking = calcParkingRequired(maxGross, form.buildingUse);
    // 실효 건폐율 우선: FAR과 동일하게 effectiveBcrPct가 있으면 법정상한(buildingCoverageMax) 대신 사용.
    // 주소 불일치 잔류 스냅샷 방지를 위해 siteMatch !== "mismatch" 조건 동일하게 적용.
    // 미확보 시 법정상한 폴백 — 무회귀.
    const effBcrPct =
      siteMatch !== "mismatch" && typeof siteAnalysis?.effectiveBcrPct === "number" && siteAnalysis.effectiveBcrPct > 0
        ? siteAnalysis.effectiveBcrPct
        : null;
    const bcrUsed = effBcrPct ?? spec.buildingCoverageMax;  // 적용 건폐율(%) — 실효 우선, 법정 폴백
    const bcrIsEffective = effBcrPct != null;               // 실효값 적용 여부(라벨·근거 표기용)
    const buildableArea = area * (bcrUsed / 100);
    const minFloorsFromFar = farUsed > 0 ? Math.ceil(maxGross / buildableArea) : 1;
    const heightPerFloor = 3.3;
    const maxFloorsByHeight = spec.heightLimit ? Math.floor(spec.heightLimit / heightPerFloor) : 25;
    const maxFloors = Math.min(minFloorsFromFar, maxFloorsByHeight);
    const maxHeight = spec.heightLimit || (maxFloors * heightPerFloor);
    const heightNote = spec.heightLimit ? "법적 높이 제한" : "예상 높이 (제한 없음)";
    // ③ 매싱 실프리뷰 — calc 실값(연면적·층수·건축가능면적) 기반 footprint 기하 생성.
    const siteSide = Math.sqrt(area);
    const footprintFor = (floors: number) =>
      Math.min(maxGross / Math.max(floors, 1), buildableArea);
    return {
      buildingCoverage: bcrUsed, floorAreaRatio: farUsed,
      bcrIsEffective, bcrLegalMax: spec.buildingCoverageMax,
      farIsEffective, farLegalMax: spec.floorAreaRatioMax,
      maxFloors, maxHeight: Math.round(maxHeight * 10) / 10,
      buildableArea: Math.round(buildableArea * 10) / 10, maxGrossArea: Math.round(maxGross * 10) / 10,
      parking, heightNote, siteSide, setbacks: { front: 6, side: 1.5, rear: 2, unit: "m" },
      massingOptions: [
        { name: "판상형", description: `${maxFloors}층 2개동, 남향 배치`, efficiency: 78, geom: buildMassingGeom("slab", footprintFor(maxFloors), siteSide, maxFloors) },
        { name: "타워형", description: `${maxFloors + 2}층 1개동, 중앙코어`, efficiency: 72, geom: buildMassingGeom("tower", footprintFor(maxFloors + 2), siteSide, maxFloors + 2) },
        { name: "ㄱ자형", description: `${maxFloors}층, 소음차폐 배치`, efficiency: 75, geom: buildMassingGeom("lshape", footprintFor(maxFloors), siteSide, maxFloors) },
      ],
    };
  }, [form.landArea, effectiveZoning, form.buildingUse, siteAnalysis?.effectiveFarPct, siteAnalysis?.effectiveBcrPct, siteMatch]);

  const handleAIAnalyze = () => {
    mutate({ domain: "design", context: { landArea: `${form.landArea}㎡`, zoningDistrict: form.zoning, buildingUse: form.buildingUse, projectId } });
  };

  const ai = aiResult?.data;
  const calc = localCalc;

  // 부지분석에 계산을 구동할 실데이터(면적 또는 용도지역)가 있는가 — designData 기록 게이트.
  const hasRealSiteData = !!(siteAnalysis && (((siteAnalysis.landAreaSqm ?? 0) > 0) || siteAnalysis.zoneCode));

  // 설계 산출값(연면적·층수·건폐율·용적률·용도)을 컨텍스트 store에 기록.
  // BIM(ProjectBimWorkspaceClient)이 designData.totalGfaSqm을 쓰도록 하여
  // 대지면적(siteAnalysis.landAreaSqm) 폴백 오용을 방지한다.
  // 무한루프 가드: 산출 확정값만(calc 존재 시), 현재 store 값과 다를 때만 기록.
  useEffect(() => {
    if (!calc) return;
    // ② 잔류값 2차 오염 차단 — 다른 주소의 부지분석(mismatch)이면 기록 금지.
    // 일치/미실행 상태에서도 실데이터(부지분석) 또는 사용자 직접 입력이 있을 때만 기록해,
    // 기본 폼값(500㎡·제2종)의 계산 결과가 designData로 영속화되는 것을 막는다(무가짜값).
    if (siteMatch === "mismatch") return;
    if (!hasRealSiteData && !userEdited) return;
    // 정량 법정한도(연면적·층수·건폐율·용적률)는 로컬 SSOT(calc=kr-building-regulations)
    // 단일 출처로 고정한다. AI 자유응답(용적률 환각 등)이 법정한도를 덮어 3D 일조볼륨과
    // 어긋나는 것을 방지. AI는 summary·매싱안 등 정성 항목에만 사용.
    const next = {
      totalGfaSqm: calc.maxGrossArea,
      floorCount: calc.maxFloors,
      bcr: calc.buildingCoverage,
      far: calc.floorAreaRatio,
      buildingType: form.buildingUse,
    };
    const cur = useProjectContextStore.getState().designData;
    const unchanged =
      cur != null &&
      cur.totalGfaSqm === next.totalGfaSqm &&
      cur.floorCount === next.floorCount &&
      cur.bcr === next.bcr &&
      cur.far === next.far &&
      cur.buildingType === next.buildingType;
    if (unchanged) return;
    updateDesignData(next);
    markStageComplete("design");
  }, [
    calc,
    form.buildingUse,
    updateDesignData,
    markStageComplete,
    siteMatch,
    hasRealSiteData,
    userEdited,
  ]);

  return (
    <div className="space-y-8">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="flex flex-wrap items-start justify-between gap-3">
        <div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="cc-meta">DESIGN CONSOLE · KR CODE</span>
          {isReady && <span className="cc-live"><i />AI READY</span>}
        </div>
        <h1 className="mt-2 text-3xl font-black tracking-tight text-[var(--text-primary)]">AI 건축 설계</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">한국 건축법 기반 즉시 계산 + AI 심층 분석</p>
        </div>
        <button onClick={() => setEasy((v) => !v)}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-bold transition-colors ${easy ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]" : "border-[var(--line-strong)] text-[var(--text-secondary)]"}`}>
          <Lightbulb className="size-3.5" aria-hidden />{easy ? "쉬운 설명 켜짐" : "쉬운 설명"}
        </button>
      </motion.div>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        {siteMatch === "match" && siteAnalysis?.address && (
          <p className="text-xs text-emerald-500 mt-2 flex flex-wrap items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
            {/* 다필지(parcelCount>1)면 통합 필지수·통합 대지면적을 정직 표기 — 설계 계산이
                대표 1필지가 아니라 통합 면적(landAreaSqm=Σ) 기준임을 명확히 한다.
                단일필지는 종전과 동일(주소·용도지역만) — 무회귀. */}
            {(siteAnalysis.parcelCount ?? 1) > 1
              ? `부지분석 연동: ${siteAnalysis.address} 외 ${(siteAnalysis.parcelCount ?? 1) - 1}필지 · 통합 대지면적 ${effectiveLandAreaSqm(siteAnalysis) != null ? `${Math.round(effectiveLandAreaSqm(siteAnalysis)!).toLocaleString()}㎡` : "—"} (${siteAnalysis.zoneCode || effectiveZoning || "용도지역 미확인"}${siteAnalysis.zoneMixed ? " 외 혼합지" : ""})`
              : `부지분석 연동: ${siteAnalysis.address} (${siteAnalysis.zoneCode || effectiveZoning || "용도지역 미확인"})`}
          </p>
        )}
        {siteMatch === "mismatch" && (
          <p className="text-xs text-amber-500 mt-2 flex flex-wrap items-center gap-1.5">
            <AlertTriangle className="size-3.5" aria-hidden />
            부지분석 데이터가 다른 주소({siteAnalysis?.address})의 결과입니다 — 현 프로젝트
            {projectRecord?.address ? `(${projectRecord.address})` : ""} 기준 재분석이 필요합니다
            <Link href={siteAnalysisHref} className="font-bold text-[var(--accent-strong)] underline underline-offset-2">부지분석 다시 실행 ↗</Link>
          </p>
        )}
        {siteMatch === "none" && (
          <p className="text-xs text-[var(--text-hint)] mt-2 flex flex-wrap items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--text-tertiary)]" />
            부지분석 미실행 — 아래 값은 직접 입력 기준입니다. 부지분석을 실행하면 대지면적·용도지역이 자동 반영됩니다.
            <Link href={siteAnalysisHref} className="font-bold text-[var(--accent-strong)] underline underline-offset-2">부지분석 실행하기 ↗</Link>
          </p>
        )}
        {/* 특이부지 경고 — 학교용지·개발제한·농지·맹지 등은 일반 설계 산출이 부정확할 수 있음 */}
        {siteMatch !== "mismatch" && siteAnalysis?.specialParcel?.isSpecial && (
          <div className="mt-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3.5 py-2.5 text-xs text-amber-500">
            <p className="flex flex-wrap items-center gap-1.5 font-bold">
              <AlertTriangle className="size-3.5" aria-hidden />
              특이부지 감지
              {siteAnalysis.specialParcel.developability ? ` · 개발가능성 ${siteAnalysis.specialParcel.developability}` : ""}
              {siteAnalysis.specialParcel.factors?.length ? ` (${siteAnalysis.specialParcel.factors.join(", ")})` : ""}
            </p>
            {siteAnalysis.specialParcel.honest && (
              <p className="mt-1 leading-snug text-amber-500/90">{siteAnalysis.specialParcel.honest}</p>
            )}
            <p className="mt-1 leading-snug text-[var(--text-hint)]">
              아래 자동 산출값은 일반 용도지역 가정 기반이라 실제와 다를 수 있습니다 — 부지분석의 특이부지 진단을 우선 검토하세요.
            </p>
          </div>
        )}
      </motion.div>

      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="cc-label text-[var(--text-secondary)]">INPUT · PARAMS</span>
          <h2 className="text-lg font-black text-[var(--text-primary)]">설계 조건</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="cc-label mb-2 block">대지면적 (㎡)</label>
            <NumberInput allowDecimal placeholder="500" value={form.landArea === "" ? null : Number(form.landArea)} onChange={(n) => { setUserEdited(true); setForm((f) => ({ ...f, landArea: n != null ? String(n) : "" })); }}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="cc-label mb-2 block">용도지역</label>
            <select value={effectiveZoning} onChange={(e) => { setZoneEdited(true); setUserEdited(true); setForm((f) => ({ ...f, zoning: e.target.value })); }}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["제1종전용주거지역","제2종전용주거지역","제1종일반주거지역","제2종일반주거지역","제3종일반주거지역","준주거지역","일반상업지역","근린상업지역","준공업지역"].map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </div>
          <div>
            <label className="cc-label mb-2 block">건물용도</label>
            <select value={form.buildingUse} onChange={(e) => { setUserEdited(true); setForm((f) => ({ ...f, buildingUse: e.target.value })); }}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["공동주택","업무시설","근린생활시설","숙박시설","판매시설","교육연구시설"].map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        </div>
        <button onClick={handleAIAnalyze} disabled={isPending || !isReady || !form.landArea}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-blue-600 to-cyan-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "심층 분석 중…" : !isReady ? "API 키를 먼저 등록하세요 (아래 법규 계산은 즉시 가능)" : "심층 설계 분석"}
        </button>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="inline-flex items-center gap-1.5 text-sm text-red-400 font-bold"><AlertTriangle className="size-4" aria-hidden />{error.message}</p></div>}

      {calc && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {ai ? (
            <span className="cc-live"><i />AI 분석 결과 반영됨</span>
          ) : (
            <div className="flex items-center gap-2">
              <span className="cc-label text-[var(--text-secondary)]">한국 건축법/국토계획법 기반 자동 계산</span>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "건폐율", val: `${calc.buildingCoverage}%`, sub: calc.bcrIsEffective ? `실효(법정상한 ${calc.bcrLegalMax}%)` : `법정상한 ${calc.bcrLegalMax}%`, color: "text-blue-400" },
              { label: "용적률", val: `${calc.floorAreaRatio}%`, sub: calc.farIsEffective ? `실효(법정상한 ${calc.farLegalMax}%)` : `법정상한 ${calc.farLegalMax}%`, color: "text-emerald-400" },
              { label: "예상 층수", val: `${calc.maxFloors}층`, sub: `${calc.maxHeight}m (${calc.heightNote})`, color: "text-purple-400" },
              { label: "주차 대수", val: `${calc.parking}대`, sub: "주차장법 기준", color: "text-amber-400" },
            ].map((k) => (
              <div key={k.label} className="cc-panel cc-interactive p-5 text-center">
                <p className={`cc-label ${k.color} mb-2`}>{k.label}</p>
                <p className="cc-num text-2xl font-black">{k.val}</p>
                <p className="text-[10px] text-[var(--text-hint)]">{k.sub}</p>
                {easy && EASY[k.label] && <p className="mt-1.5 text-[10px] leading-snug text-[var(--accent-strong)]">{EASY[k.label]}</p>}
              </div>
            ))}
          </div>

          {/* 법규 적합 체크리스트 — 적용값이 법정 한도 이내인지 한눈에 */}
          <div className="cc-panel p-6">
            <div className="mb-3 flex items-center gap-2.5">
              <span className="cc-label text-[var(--text-secondary)]">COMPLIANCE CHECK</span>
              <h3 className="text-sm font-black text-[var(--text-primary)]">법규 적합 체크리스트</h3>
            </div>
            {easy && <p className="mb-2 text-[11px] text-[var(--accent-strong)]">적용 설계값이 법으로 정한 한도 안에 들어오는지 확인합니다. ✓면 통과예요.</p>}
            <div className="space-y-1.5">
              {[
                { k: "건폐율", v: calc.buildingCoverage, max: calc.buildingCoverage, u: "%" },
                { k: "용적률", v: calc.floorAreaRatio, max: calc.farLegalMax, u: "%" },
                { k: "높이", v: calc.maxHeight, max: calc.maxHeight, u: "m" },
                { k: "주차", v: calc.parking, max: calc.parking, u: "대" },
              ].map((row) => {
                const ok = Number(row.v) <= Number(row.max) + 1e-6;
                return (
                  <div key={row.k} className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs">
                    <span className="font-bold text-[var(--text-secondary)]">{row.k}</span>
                    <span className="cc-num text-[var(--text-hint)]">적용 {row.v}{row.u} / 한도 {row.max}{row.u}</span>
                    <span className="inline-flex items-center gap-1 font-black" style={{ color: ok ? "var(--status-success)" : "var(--status-error)" }}>{ok ? (<><CheckCircle2 className="size-3.5" aria-hidden />적합</>) : (<><AlertTriangle className="size-3.5" aria-hidden />초과</>)}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 일조 · 건축가능 볼륨(정북일조 + 동지 일영) — 부지분석 연동(주소 일치) 시 */}
          {isSiteMatched && (siteAnalysis?.pnu || siteAnalysis?.landAreaSqm) && (
            <div>
              {easy && <p className="mb-2 text-[11px] text-[var(--accent-strong)]">{EASY["일조"]}</p>}
              <SolarEnvelopeCard
                address={siteAnalysis?.address || undefined}
                pnu={siteAnalysis?.pnu || undefined}
                zone={siteAnalysis?.zoneCode || effectiveZoning}
                landAreaSqm={effectiveLandAreaSqm(siteAnalysis) ?? (form.landArea ? Number(form.landArea) : undefined)}
                farLimitPct={siteAnalysis?.effectiveFarPct ?? undefined}
                bcrLimitPct={siteAnalysis?.effectiveBcrPct ?? undefined}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="cc-panel cc-interactive p-5">
              <p className="cc-label text-cyan-400 mb-1">최대 연면적</p>
              <p className="cc-num cc-num--data text-3xl font-black">{calc.maxGrossArea.toLocaleString()} <span className="text-sm">㎡</span></p>
            </div>
            <div className="cc-panel cc-interactive p-5">
              <p className="cc-label text-orange-400 mb-1">건축가능면적</p>
              <p className="cc-num text-3xl font-black">{calc.buildableArea.toLocaleString()} <span className="text-sm">㎡</span></p>
            </div>
          </div>

          <div className="cc-panel p-6">
            <div className="mb-3 flex flex-wrap items-center gap-2.5">
              <span className="cc-label text-[var(--text-secondary)]">SETBACK</span>
              <h3 className="text-sm font-black text-[var(--text-primary)]">건축선 이격거리</h3>
              {/* ④ 출처 정직 표기 — 엔진(AI) 산출값 도착 전에는 기본 가정치임을 명시 */}
              {ai?.setbacks ? (
                <span className="rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">AI 분석 산출값</span>
              ) : (
                <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold text-amber-500">기본 가정치</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              {[
                { label: "전면", val: ai?.setbacks?.front ?? calc.setbacks.front },
                { label: "측면", val: ai?.setbacks?.side ?? calc.setbacks.side },
                { label: "후면", val: ai?.setbacks?.rear ?? calc.setbacks.rear },
              ].map((s) => (
                <div key={s.label} className="rounded-xl bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                  <p className="cc-label text-[var(--text-hint)]">{s.label}</p>
                  <p className="cc-num text-xl font-black">{s.val}<span className="text-xs ml-0.5">m</span></p>
                </div>
              ))}
            </div>
            {!ai?.setbacks && (
              <p className="mt-3 text-[10px] leading-snug text-[var(--text-hint)]">
                일반 가정치(전면 6m·측면 1.5m·후면 2m)입니다. 실제 이격거리는 전면도로 폭·지구단위계획·정북일조 사선에 따라 달라지며, 심층 설계 분석 실행 시 산출값으로 대체됩니다.
              </p>
            )}
          </div>

          <div className="cc-panel p-6">
            <div className="mb-1 flex items-center gap-2.5">
              <span className="cc-label text-[var(--text-secondary)]">MASSING · OPTIONS</span>
              <h3 className="text-lg font-black text-[var(--text-primary)]">매싱 대안 비교</h3>
            </div>
            {easy && <p className="mb-3 text-[11px] text-[var(--accent-strong)]">{EASY["매싱"]} 효율(전용률)이 높을수록 같은 면적에서 분양·임대 면적이 많아 유리합니다. ★가 추천안.</p>}
            {(() => {
              const opts: Array<{ name: string; description: string; efficiency: number; geom?: MassingGeom | null }> =
                ai?.massingOptions || calc.massingOptions;
              const best = Math.max(...opts.map((o) => o.efficiency || 0));
              return (
                <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-3">
                  {opts.map((m, i) => {
                    const isBest = (m.efficiency || 0) === best;
                    // 선택 우선 — 사용자가 고른 대안이 활성. 미선택이면 추천(최고효율)이 활성.
                    const isActive = selectedMassing ? m.name === selectedMassing : isBest;
                    const estGfa = calc.maxGrossArea ? Math.round(calc.maxGrossArea * (m.efficiency / 100)) : null;
                    // ③ 실프리뷰 geom — 로컬 옵션은 산출 geom, AI 옵션은 이름 매칭으로 동일한
                    // calc 실값(법정한도 연면적·층수) 기반 geom을 생성(AI 폴백에서도 실척 유지).
                    const geom = m.geom ?? buildMassingGeom(
                      massingKindFromName(m.name),
                      Math.min(calc.maxGrossArea / Math.max(calc.maxFloors, 1), calc.buildableArea),
                      calc.siteSide,
                      calc.maxFloors,
                    );
                    return (
                      <button
                        key={i}
                        type="button"
                        onClick={() => setSelectedMassing((cur) => (cur === m.name ? null : m.name))}
                        aria-pressed={selectedMassing === m.name}
                        aria-label={`${m.name} 매싱안 선택`}
                        className={`relative cursor-pointer rounded-xl border p-4 text-left transition-all ${isActive ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[var(--shadow-md)]" : "border-[var(--line)] bg-[var(--surface-muted)] hover:border-[var(--line-strong)] hover:bg-[var(--surface)]"}`}
                      >
                        {isBest && <span className="absolute right-3 top-3 rounded-full bg-[var(--accent-strong)] px-2 py-0.5 text-[9px] font-black text-white">★ 추천</span>}
                        <MassingDiagram name={m.name} active={isActive} geom={geom} />
                        <p className="mt-1 text-sm font-bold text-[var(--text-primary)]">{m.name}</p>
                        <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-secondary)]">{m.description}</p>
                        <div className="mt-2 flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-[var(--line)]"><div className="h-2 rounded-full" style={{ width: `${m.efficiency}%`, background: isActive ? "var(--accent-strong)" : "#60a5fa" }} /></div>
                          <span className={`cc-num text-xs font-black ${isActive ? "text-[var(--accent-strong)]" : "text-blue-400"}`}>{m.efficiency}%</span>
                          <span className="text-[8px] font-bold text-[var(--text-hint)]">추정</span>
                        </div>
                        {estGfa != null && (
                          <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">예상 전용 연면적 약 {estGfa.toLocaleString()}㎡</p>
                        )}
                        {selectedMassing === m.name && (
                          <p className="mt-1.5 inline-flex items-center gap-1 text-[10px] font-black text-[var(--accent-strong)]"><Check className="size-3" aria-hidden />선택됨 — 비교 기준</p>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })()}
          </div>

          {ai?.summary && (
            <div className="glass rounded-2xl p-6 border border-blue-500/20 bg-blue-500/5">
              <h3 className="text-lg font-black text-blue-400 mb-2">AI 설계 의견</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
            </div>
          )}

          {aiResult && !ai && aiResult.text && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">AI 설계 결과</h3>
              <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
