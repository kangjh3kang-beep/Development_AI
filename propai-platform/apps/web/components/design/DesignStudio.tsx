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
import { useAIAnalyze, useAIReady, extractStructuredFromText, cleanFenceText } from "@/lib/ai-analyze-client";
import { getZoningSpec, calcMaxGrossArea, calcParkingRequired, normalizeZoning, getZoningList } from "@/lib/kr-building-regulations";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveFarPct, resolveBcrPct } from "@/lib/zoning-ssot";
import { resolveCanonicalFloors } from "@/lib/design-ssot";
import { contractCanonicalFloors } from "@/lib/design-contract";
import { useProjectStore } from "@/store/useProjectStore";
import { NumberInput } from "@/components/common/NumberInput";
import { InspectorGrid } from "@/components/common/InspectorGrid";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { SolarEnvelopeCard } from "@/components/projects/SolarEnvelopeCard";
import { SeedDesignMassComparison } from "@/components/design/SeedDesignMassComparison";

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

const ZONING_OPTIONS = getZoningList();

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

/**
 * 매싱 입체(축측투영) 대형 미리보기 — 우측 캔버스의 '입체 3D' 뷰.
 * ★중요: WebGL/Three.js를 절대 쓰지 않는다. 순수 SVG 축측투영(axonometric)으로만 입체를
 *   '느낌'만 보여준다(진짜 인터랙티브 3D·BIM은 onOpen3D 핸드오프 버튼이 담당).
 * 투영 수학은 MassingDiagram의 우측 악소노메트릭과 동일하되 캔버스를 꽉 채우는 큰 SVG로 그린다.
 * floorHeightM: 층고(m) — 폼의 floorHeight를 받아 입체 높이를 실값으로 계산(없으면 3.3m 가정).
 */
function MassingAxon3D({ geom, floorHeightM, active }: { geom: MassingGeom | null; floorHeightM?: number; active?: boolean }) {
  const c = active ? "var(--accent-strong)" : "var(--text-tertiary)";
  const fill = active ? "var(--accent-soft)" : "var(--surface-muted)";

  // 기하 데이터가 없으면 안내 텍스트만(무목업 — 가짜 입체를 그리지 않는다).
  if (!geom || geom.blocks.length === 0) {
    return (
      <svg viewBox="0 0 280 200" className="h-full w-full">
        <text x="140" y="100" textAnchor="middle" fontSize="11" fill="var(--text-hint)">
          입체 미리보기를 만들 기하 데이터가 없습니다
        </text>
      </svg>
    );
  }

  const KX = 0.5, KY = 0.3; // 깊이 단축 계수(MassingDiagram과 동일)
  const fh = floorHeightM && floorHeightM > 0 ? floorHeightM : 3.3; // 층고(m) — 없으면 3.3 가정
  const hM = geom.floors * fh; // 건물 총 높이(m) = 층수 × 층고

  const S = geom.siteSide;
  // 모든 블록의 투영 범위(extent)로 origin/scale 자동 맞춤(MassingDiagram의 s2 방식 차용).
  let extX = 1, extY = 1;
  for (const b of geom.blocks) {
    const dist = S - (b.y + b.h);
    extX = Math.max(extX, b.x + dist * KX + b.w + b.h * KX);
    extY = Math.max(extY, hM + dist * KY + b.h * KY);
  }
  const PAD = 18;
  const AW = 280 - PAD * 2, AH = 200 - PAD * 2 - 16; // 하단 라벨 여백 확보
  const s2 = Math.min(AW / extX, AH / extY);
  const AYB = 200 - 28; // 지반선 y
  const AX = PAD;
  const ordered = [...geom.blocks].sort((a, b) => a.y - b.y); // 북(후면)부터 — 전면이 덮도록
  const b0 = geom.blocks[0];

  return (
    <svg viewBox="0 0 280 200" className="h-full w-full">
      {/* 지반선 */}
      <line x1={AX - 6} y1={AYB + 2} x2="272" y2={AYB + 2} stroke={c} strokeWidth="1" opacity="0.4" />
      {ordered.map((b, i) => {
        const dist = S - (b.y + b.h);
        const fx = AX + (b.x + dist * KX) * s2;
        const fy = AYB - dist * KY * s2;
        const w = b.w * s2;
        const H = hM * s2;
        const ox = b.h * KX * s2;
        const oy = b.h * KY * s2;
        // 층 슬래브 라인 — 과밀 방지로 60층까지만 그린다(라벨엔 실제 floors 표기).
        const slabs: number[] = [];
        for (let f = 1; f < geom.floors && f <= 60; f++) slabs.push(fy - (H * f) / geom.floors);
        return (
          <g key={`x${i}`}>
            {/* 상면(지붕) */}
            <polygon points={`${fx},${fy - H} ${fx + ox},${fy - H - oy} ${fx + w + ox},${fy - H - oy} ${fx + w},${fy - H}`} fill={c} opacity="0.22" />
            {/* 측면(우측 깊이면) */}
            <polygon points={`${fx + w},${fy - H} ${fx + w + ox},${fy - H - oy} ${fx + w + ox},${fy - oy} ${fx + w},${fy}`} fill={c} opacity="0.38" />
            {/* 전면 */}
            <rect x={fx} y={fy - H} width={w} height={H} fill={fill} stroke={c} strokeWidth="1" />
            {/* 층 슬래브 라인(가는 선) */}
            {slabs.map((sy, j) => (
              <line key={j} x1={fx} y1={sy} x2={fx + w} y2={sy} stroke={c} strokeWidth="0.5" opacity="0.5" />
            ))}
          </g>
        );
      })}
      {/* N 방위(작게) */}
      <g opacity="0.8">
        <line x1={AX + 8} y1={28} x2={AX + 8} y2={16} stroke={c} strokeWidth="1" />
        <polygon points={`${AX + 5},${19} ${AX + 8},${13} ${AX + 11},${19}`} fill={c} />
        <text x={AX + 8} y={40} textAnchor="middle" fontSize="9" fill={c} fontWeight="700">N</text>
      </g>
      {/* 치수/정보 라벨 — 무날조: geom 실값만. 좌하단 동 규모, 우하단 층수·높이·층고 가정. */}
      <text x={AX} y="190" fontSize="9" fill="var(--text-hint)">동 약 {Math.round(b0.w)}×{Math.round(b0.h)}m</text>
      <text x="272" y="184" textAnchor="end" fontSize="9" fill="var(--text-hint)">{geom.floors}층 · 약 {Math.round(hM)}m</text>
      <text x="272" y="194" textAnchor="end" fontSize="8" fill="var(--text-hint)">층고 {fh}m 가정</text>
    </svg>
  );
}

// ② 폼 기본값 — projectId 전환 리셋·시드 해제 시 복귀 기준(단일 정의).
// floorHeight = 층고(m) 기본 3.0(범위 2.4~4.5) — SolarEnvelopeCard로 전달해 층수 천장을 재계산.
const DEFAULT_FORM = { landArea: "500", zoning: "제2종일반주거지역", buildingUse: "공동주택", floorHeight: "3.0" };

// ★P3(추천→설계 연결): 추천 개발모델명(designData.buildingType, 예 '아파트'·'오피스텔'·'주상복합')을
//   설계 폼의 건물용도 옵션(공동주택/업무시설/근린생활시설/숙박시설/판매시설/교육연구시설)으로 매핑.
//   매핑 불가 시 null(시드 안 함 — 추측 금지). 키워드 기반(개발모델 명칭 다양성 흡수).
const _BUILDING_USE_OPTIONS = ["공동주택", "업무시설", "근린생활시설", "숙박시설", "판매시설", "교육연구시설"];
function mapBuildingTypeToUse(buildingType: string | null | undefined): string | null {
  const t = (buildingType || "").trim();
  if (!t) return null;
  if (_BUILDING_USE_OPTIONS.includes(t)) return t; // 이미 정식 용도명
  // 개발모델 명칭 → 건축법 용도 키워드 매핑.
  if (/아파트|공동주택|도시형생활주택|주상복합|연립|다세대|타운하우스|빌라|주택조합|재건축|재개발/.test(t)) return "공동주택";
  if (/오피스텔|업무|사무|지식산업|오피스/.test(t)) return "업무시설";
  if (/근린생활|상가|상업|점포|소매/.test(t)) return "근린생활시설";
  if (/숙박|호텔|생활숙박|레지던스/.test(t)) return "숙박시설";
  if (/판매|쇼핑|백화점|마트|물류/.test(t)) return "판매시설";
  if (/교육|연구|학교|병원|의료/.test(t)) return "교육연구시설";
  return null; // 미상 — 시드 안 함(무목업)
}

// SolarEnvelopeCard가 부모로 리프트하는 결과(상단 '예상 층수' 카드 배선용) — 필요한 필드만.
type EnvLift = {
  recommended_floors_low?: number; recommended_floors_high?: number;
  arithmetic_min_floors?: number; max_floors?: number; floor_height_m?: number;
};

// onOpen3D: (선택) 우측 캔버스의 "3D·BIM 편집실로 →" 버튼이 호출. 부모(DesignWorkspace)가
//   3D 스텝(draw)으로 전환하는 함수를 넘긴다. 없으면 버튼을 숨겨(무WebGL) 기존 lazy 3D 아키텍처 보존.
export function DesignStudio({ projectId, onOpen3D }: { projectId?: string; onOpen3D?: () => void }) {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<DesignResult>();
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  // ★P3: 추천(AutoRecommend)이 기록한 건물용도(designData.buildingType)를 설계 폼 시드로 읽는다.
  const recommendedBuildingType = useProjectContextStore((s) => s.designData?.buildingType);
  // ★C2R 계약 정본 층수(envelope_result.metrics.canonical_floors) — store에 환류된 계약이 있으면
  //   층수 정본의 1순위 권위 소스로 쓴다(아래 resolveCanonicalFloors 호출들에 주입). 없으면 null →
  //   종전 우선순위(일조 권장→recFloors)로 폴백(additive·무회귀). compliance 객체 참조만 구독.
  const designCompliance = useProjectContextStore((s) => s.designData?.compliance);
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
  // 우측 캔버스 2D/3D 인라인 토글 — "2d"=배치평면(MassingDiagram), "3d"=축측투영 입체(MassingAxon3D·SVG).
  const [canvasView, setCanvasView] = useState<"2d" | "3d">("2d");
  // ②③ 일조 인벨로프 결과 리프트 — 상단 '예상 층수' 카드를 실무 권장 범위로 배선(ceil(FAR/BCR) 날조 제거).
  const [envResult, setEnvResult] = useState<EnvLift | null>(null);

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
        // P3 정합: buildingUse도 landArea/zoning과 동일하게 미수정 시 기본값 복귀(타 부지 추천 잔류 차단).
        const buildingUse = userEdited ? prev.buildingUse : DEFAULT_FORM.buildingUse;
        if (landArea === prev.landArea && zoning === prev.zoning && buildingUse === prev.buildingUse) return prev;
        return { ...prev, landArea, zoning, buildingUse };
      });
      return;
    }
    const seededZone = normalizeZoning(siteAnalysis.zoneCode) || siteAnalysis.zoneCode || null;
    // ★다필지면 통합 면적(effectiveLandAreaSqm)으로 폼을 시드한다 — 단일 PNU 분석이
    //   landAreaSqm을 대표값으로 덮어써도 설계가 통합 면적 기준으로 GFA를 계산하게.
    const seedArea = effectiveLandAreaSqm(siteAnalysis);
    // ★P3: 추천 건물용도(designData.buildingType)를 폼 건물용도로 시드(매핑 성공 시·사용자 미수정 시).
    //   추천 '주상복합'→'공동주택' 등. 매핑 불가/미입력이면 기존값 유지(무목업·추측 금지).
    const seededUse = !userEdited ? mapBuildingTypeToUse(recommendedBuildingType) : null;
    setForm((prev) => ({
      ...prev,
      landArea: seedArea ? String(seedArea) : prev.landArea,
      zoning: !zoneEdited && seededZone ? seededZone : prev.zoning,
      buildingUse: seededUse || prev.buildingUse,
    }));
  }, [siteAnalysis, zoneEdited, isSiteMatched, userEdited, recommendedBuildingType]);

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

  // 자동 시드 여부 — 부지분석이 대지면적을 주고(주소 일치), 사용자가 아직 손대지 않은 상태.
  // 이때는 일반인에게 편집 폼 대신 '확정 칩'(읽기전용)만 보여주고, 편집 폼은 고급 서랍 뒤로 숨긴다.
  // userEdited면(사용자가 직접 수정) 종전 편집 동선을 그대로 보존(무회귀).
  const seededLandAreaSqm = effectiveLandAreaSqm(siteAnalysis);
  // ★레이아웃 게이트(layoutSeeded)는 userEdited에 의존하지 않는다 — 부지분석이 연동되면(주소 일치+면적
  //   확보) '칩+고급서랍' 레이아웃을 쓴다. 편집해도 레이아웃이 안 바뀌어 입력칸이 언마운트되지 않으므로
  //   타이핑 중 포커스 상실이 없다(서랍 안 NumberInput은 키 입력마다 onChange라 이 분리가 필수).
  const layoutSeeded = isSiteMatched && seededLandAreaSqm != null;
  // '부지분석 자동' vs '직접 수정' 배지는 칩 렌더에서 !userEdited로 직접 분기한다(별도 변수 불필요).

  const localCalc = useMemo(() => {
    const area = Number(form.landArea) || 0;
    const spec = getZoningSpec(effectiveZoning);
    if (!spec || area <= 0) return null;
    // 실효 용적률 우선: 부지분석(special_parcel/조례/계획 반영) 실효 용적률이 있으면
    // 법정상한(kr-building-regulations spec.floorAreaRatioMax) 대신 이를 진실원으로 쓴다.
    // ★SSOT 읽기 통일: resolveFarPct(통합 > 실효 > 법정)로 일원화 — 다필지에서는 통합 실효가
    //   대표 1필지 실효를 대체한다(인벨로프 카드·사업개요와 일관). 주소 불일치 잔류 스냅샷이 다른
    //   부지값을 구동하지 않도록 일치(또는 미실행) 시에만 적용. 미확보 시 법정상한 폴백 — 무회귀.
    const resolvedFar = resolveFarPct(siteAnalysis);
    const effFarPct =
      siteMatch !== "mismatch" && resolvedFar != null && resolvedFar > 0
        ? resolvedFar
        : null;
    const farUsed = effFarPct ?? spec.floorAreaRatioMax; // 적용 용적률(%) — 실효 우선, 법정 폴백
    const farIsEffective = effFarPct != null;            // 실효값 적용 여부(라벨·근거 표기용)
    const maxGross = effFarPct != null ? area * (effFarPct / 100) : calcMaxGrossArea(area, effectiveZoning);
    const parking = calcParkingRequired(maxGross, form.buildingUse);
    // 실효 건폐율 우선: FAR과 동일하게 resolveBcrPct(통합 > 실효 > 법정)가 있으면 법정상한
    // (buildingCoverageMax) 대신 사용. 주소 불일치 잔류 스냅샷 방지를 위해 siteMatch !== "mismatch"
    // 조건 동일하게 적용. 미확보 시 법정상한 폴백 — 무회귀.
    const resolvedBcr = resolveBcrPct(siteAnalysis);
    const effBcrPct =
      siteMatch !== "mismatch" && resolvedBcr != null && resolvedBcr > 0
        ? resolvedBcr
        : null;
    const bcrUsed = effBcrPct ?? spec.buildingCoverageMax;  // 적용 건폐율(%) — 실효 우선, 법정 폴백
    const bcrIsEffective = effBcrPct != null;               // 실효값 적용 여부(라벨·근거 표기용)
    const buildableArea = area * (bcrUsed / 100);
    const minFloorsFromFar = farUsed > 0 ? Math.ceil(maxGross / buildableArea) : 1;
    const heightPerFloor = Number(form.floorHeight) || 3.3;
    // 높이제한이 없으면(일반상업·준주거 등) 높이 캡을 적용하지 않는다 — 용적률/건폐율만 층수를
    // 지배한다. 종전 25층 매직캡은 1300% 상업을 25층으로 과소왜곡했음(무날조). 무한대로 두면
    // maxFloors=min(산술하한, ∞)=산술하한(불변), recFloors는 FAR(round(far/20))을 반영해 65층으로.
    const maxFloorsByHeight = spec.heightLimit ? Math.floor(spec.heightLimit / heightPerFloor) : Number.POSITIVE_INFINITY;
    const maxFloors = Math.min(minFloorsFromFar, maxFloorsByHeight); // 산술하한(건폐율 만충) — 법적 개념 아님
    // ★실무 권장 층수(매싱 도식·설명용) — 산술하한(maxFloors)을 그대로 "N층 2개동"으로 노출하면
    //   과소(4층 등) 오도. 쾌적 건폐율 20% 가정(round(FAR/20))으로 보정하되 높이제한·산술하한 이내로
    //   클램프해 무날조. 정본 층수 정렬을 위해 maxHeight 계산보다 먼저 산출한다.
    const recFloors = Math.max(maxFloors, Math.min(maxFloorsByHeight, Math.round(farUsed / 20)));
    // 높이제한이 없을 땐 권장 층수(recFloors) × 층고로 예상 높이를 잡아 층수 정본과 높이를 정합시킨다
    // (종전 maxFloors=산술하한 기준이면 65층 권장과 어긋난 낮은 높이를 표시했음).
    const maxHeight = spec.heightLimit || (recFloors * heightPerFloor);
    const heightNote = spec.heightLimit ? "법적 높이 제한" : "예상 높이 (제한 없음)";
    // ③ 매싱 실프리뷰 — calc 실값(연면적·층수·건축가능면적) 기반 footprint 기하 생성.
    const siteSide = Math.sqrt(area);
    const footprintFor = (floors: number) =>
      Math.min(maxGross / Math.max(floors, 1), buildableArea);
    return {
      buildingCoverage: bcrUsed, floorAreaRatio: farUsed,
      bcrIsEffective, bcrLegalMax: spec.buildingCoverageMax,
      farIsEffective, farLegalMax: spec.floorAreaRatioMax,
      maxFloors, recFloors, maxHeight: Math.round(maxHeight * 10) / 10,
      buildableArea: Math.round(buildableArea * 10) / 10, maxGrossArea: Math.round(maxGross * 10) / 10,
      parking, heightNote, siteSide, setbacks: { front: 6, side: 1.5, rear: 2, unit: "m" },
      massingOptions: [
        { name: "판상형", description: `${recFloors}층 2개동, 남향 배치`, efficiency: 78, geom: buildMassingGeom("slab", footprintFor(recFloors), siteSide, recFloors) },
        { name: "타워형", description: `${recFloors + 2}층 1개동, 중앙코어`, efficiency: 72, geom: buildMassingGeom("tower", footprintFor(recFloors + 2), siteSide, recFloors + 2) },
        { name: "ㄱ자형", description: `${recFloors}층, 소음차폐 배치`, efficiency: 75, geom: buildMassingGeom("lshape", footprintFor(recFloors), siteSide, recFloors) },
      ],
    };
  }, [
    form.landArea,
    form.floorHeight,
    effectiveZoning,
    form.buildingUse,
    siteAnalysis?.integratedFarEffPct,
    siteAnalysis?.integratedBcrEffPct,
    siteAnalysis?.effectiveFarPct,
    siteAnalysis?.effectiveBcrPct,
    siteAnalysis?.nationalFarPct,
    siteAnalysis?.nationalBcrPct,
    siteMatch,
  ]);

  const handleAIAnalyze = () => {
    mutate({ domain: "design", context: { landArea: `${form.landArea}㎡`, zoningDistrict: form.zoning, buildingUse: form.buildingUse, projectId } });
  };

  const ai = aiResult?.data;
  // ★raw JSON 노출 해소(전역 공용 헬퍼): AI가 구조화 데이터(data) 없이 텍스트로만 줄 때,
  //  extractStructuredFromText로 JSON을 추출해 승격한다(summary/매싱안 있는 설계 응답만 채택).
  //  실패 시 cleanFenceText로 코드펜스 제거한 정제 텍스트만 보여 raw 코드블록 노출을 막는다.
  const aiText = aiResult?.text;
  const aiFromText = useMemo<DesignResult | null>(() => {
    const obj = ai ? null : extractStructuredFromText<DesignResult>(aiText);
    return obj && (obj.summary || Array.isArray(obj.massingOptions)) ? obj : null;
  }, [ai, aiText]);
  const aiEff = ai ?? aiFromText;   // 구조화 우선, 없으면 텍스트에서 추출한 구조
  const aiCleanText = cleanFenceText(aiText);
  const calc = localCalc;

  // ★층수 단일 진실원천(SSOT) — 축측 도식·예상층수 카드·우측 메트릭칩이 모두 이 한 값을 보게 한다.
  //   종전엔 축측(25층 매직캡)·예상(43~65)·칩(65)이 3중 불일치했음. 일조 인벨로프 권장(있으면)
  //   > calc.recFloors(FAR 반영 현실권장) 순으로 도출하고, 셋 다 없으면 null(무날조 — 화면 "—").
  // ★C2R 계약 정본 층수 — store 환류 계약(designCompliance)에서 안전 추출(없거나 0이면 null).
  //   resolveCanonicalFloors의 1순위 인자로 주입 → 계약값이 있으면 그것을 정본으로 채택(무회귀).
  const contractFloors = contractCanonicalFloors(designCompliance);
  const canonicalFloors = calc ? resolveCanonicalFloors(envResult, calc.recFloors, contractFloors) : null;
  // ★매싱 도식(좌측 대안카드·우측 캔버스)이 '같은 층수'로 그려지도록 geom 산출 층수를 단일화.
  //   정본(canonicalFloors)→권장(recFloors) 순. 좌우가 이 한 값을 공유해 슬래브 수 불일치를 차단.
  const floorsForGeom = canonicalFloors ?? calc?.recFloors ?? null;

  // ②③ 상단 '예상 층수' 카드 값(정직화) — ceil(FAR/BCR)인 calc.maxFloors는 '산술하한'이라
  //   '예상'으로 노출하면 과소(4층 등) 오도. 일조 인벨로프 결과가 있으면 실무 권장 범위를,
  //   없으면(미매칭) 로컬 현실추정(low=round(FAR/30)·high=round(FAR/20))을 표시한다(가짜값 0·무날조).
  const expectedFloors = useMemo<{ val: string; sub: string } | null>(() => {
    if (!calc) return null;
    const fh = envResult?.floor_height_m ?? (Number(form.floorHeight) || 3.0);
    if (envResult && (envResult.recommended_floors_low != null || envResult.recommended_floors_high != null)) {
      const lo = envResult.recommended_floors_low;
      const hi = envResult.recommended_floors_high;
      const val =
        lo != null && hi != null && hi > lo ? `${lo}~${hi}층`
        : lo != null ? `${lo}층`
        : hi != null ? `${hi}층` : "—";
      // 범위(권장 밴드)와 단일 정본 칩의 관계를 명시 — 칩·축측은 정본 상한(canonicalFloors)을 쓴다.
      const sub = canonicalFloors != null ? `권장 밴드 · 정본 ${canonicalFloors}층 적용(층고 ${fh}m·일조)` : `실무 권장(층고 ${fh}m·일조 반영)`;
      return { val, sub };
    }
    // 미매칭 — 로컬 현실추정(쾌적 건폐율 20~30% 가정). ★ceil(FAR/BCR)=산술하한(maxFloors) 노출 금지.
    const far = calc.floorAreaRatio;
    // FAR이 없으면 정본 층수(canonicalFloors)→권장(recFloors) 순으로(산술하한 maxFloors 노출 금지·무날조).
    if (!(far > 0)) {
      const val = canonicalFloors != null ? `${canonicalFloors}층` : `${calc.recFloors}층`;
      return { val, sub: `권장(용적률 기준)` };
    }
    const low = Math.max(1, Math.round(far / 30));
    const high = Math.max(low, Math.round(far / 20));
    const val = high > low ? `${low}~${high}층` : `${low}층`;
    return { val, sub: `실무 권장(추정)` };
  }, [calc, envResult, form.floorHeight, canonicalFloors]);

  // ★활성 매싱안 단일출처(SSOT) — 좌측 '매싱 대안 비교' 카드와 우측 캔버스가 동일한 활성안을
  //   보게 한다. 옵션 목록·활성 판정·geom·우측 지표를 한 번에 도출(좌측에서 옵션 클릭 시 우측 즉시 갱신).
  //   활성 판정 규칙은 좌측 매싱 블록과 동일: 사용자가 고른 안이 있으면 그 안, 없으면 추천(최고 효율).
  const activeMassing = useMemo(() => {
    if (!calc) return null;
    // 옵션 목록: AI 산출값이 있으면 우선, 없으면 로컬 산출 옵션(좌측 매싱 블록과 동일 소스).
    const opts: Array<{ name: string; description: string; efficiency: number; geom?: MassingGeom | null }> =
      Array.isArray(aiEff?.massingOptions) ? aiEff.massingOptions : calc.massingOptions;
    if (!opts.length) return null;
    const best = Math.max(...opts.map((o) => o.efficiency || 0));
    // 선택 우선 — 사용자가 고른 대안이 활성, 미선택이면 추천(최고효율). 좌측 카드와 동일.
    const active =
      (selectedMassing ? opts.find((o) => o.name === selectedMassing) : null) ??
      opts.find((o) => (o.efficiency || 0) === best) ??
      opts[0];
    // ★층수 정본(canonicalFloors)으로 floors·geom을 둘 다 통일한다 — 종전엔 floors는 인벨로프
    //   권장(65), geom은 active.geom(=calc.recFloors 기준)이라 칩 층수와 축측 슬래브 수가 어긋났음.
    //   geom을 active.geom 대신 정본 층수로 재생성해 "축측 슬래브 수 == 칩 층수"가 되게 한다.
    //   ★좌측 대안카드와 동일한 컴포넌트 레벨 floorsForGeom을 공유한다(좌우 단일 참조).
    const geomFloors = floorsForGeom ?? calc.recFloors;
    const fpForFloors = Math.min(calc.maxGrossArea / Math.max(geomFloors, 1), calc.buildableArea);
    const geom = buildMassingGeom(
      massingKindFromName(active.name),
      fpForFloors,
      calc.siteSide,
      geomFloors,
    );
    // 우측 지표(무날조 — calc/envResult 실값만). 층수는 정본(canonicalFloors) — null이면 칩에서 "—".
    const floors = canonicalFloors;
    // 예상 전용 연면적 = 최대 연면적 × 효율(%) — 좌측 카드의 estGfa와 동일 식.
    const estGfa = calc.maxGrossArea ? Math.round(calc.maxGrossArea * ((active.efficiency || 0) / 100)) : null;
    return { active, geom, isBest: (active.efficiency || 0) === best, floors, estGfa };
    // envResult는 canonicalFloors(→floorsForGeom)에 이미 반영돼 deps에서 생략(중복 의존 경고 방지).
  }, [calc, aiEff, selectedMassing, canonicalFloors, floorsForGeom]);

  // 부지분석에 계산을 구동할 실데이터(면적 또는 용도지역)가 있는가 — designData 기록 게이트.
  const hasRealSiteData = !!(siteAnalysis && (((siteAnalysis.landAreaSqm ?? 0) > 0) || siteAnalysis.zoneCode));
  const seedEffectiveFarPct =
    siteMatch !== "mismatch"
      ? (siteAnalysis?.integratedFarEffPct ?? siteAnalysis?.effectiveFarPct ?? siteAnalysis?.ordinance?.effectiveFar ?? null)
      : null;
  const seedEffectiveBcrPct =
    siteMatch !== "mismatch"
      ? (siteAnalysis?.integratedBcrEffPct ?? siteAnalysis?.effectiveBcrPct ?? siteAnalysis?.ordinance?.effectiveBcr ?? null)
      : null;

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
    // 층수 정본(canonicalFloors) — 산술하한(calc.maxFloors)을 store에 영속화하면 BIM·하류가
    // 과소 층수(4층 등)를 쓰게 됨. 정본 미확보 시 권장(recFloors) 폴백(무날조).
    // ★C2R 계약 정본 층수(contractFloors)를 1순위로 — store에 환류된 계약이 있으면 그 층수를
    //   store(floorCount)에 영속화한다(권위 소스). 없으면 종전(일조 권장→recFloors) 폴백(무회귀).
    const floorCount = resolveCanonicalFloors(envResult, calc.recFloors, contractFloors) ?? calc.recFloors;
    // ── 매스 기하(massGeom) 1회 기록 — site/generate가 정한 건물 덩어리를 draw(3D)로 전파 ──
    // 왜(쉬운 설명): 도면 단계가 이 모양을 받으면 /mass 재산출 없이 같은 층수·footprint로 3D를 그린다.
    //   여기(부지 기반 설계)는 단일 매스라 podium/tower는 null(주상복합 2단 매스는 추천안 적용 경로에서 채움).
    //   건축면적(footprint)=연면적÷층수(건축가능면적 이내)로 실값 산출, 폭·깊이는 정사각 근사.
    const footprintSqm =
      floorCount > 0
        ? Math.min(calc.maxGrossArea / floorCount, calc.buildableArea)
        : calc.buildableArea;
    const side = footprintSqm > 0 ? Math.sqrt(footprintSqm) : 0; // 정사각 근사 한 변(m)
    const massGeom = footprintSqm > 0 && side > 0
      ? {
          buildingWidthM: Math.round(side * 10) / 10,
          buildingDepthM: Math.round(side * 10) / 10,
          footprintSqm: Math.round(footprintSqm * 10) / 10,
          massingProfile: null,          // 단일 매스(주상복합 2단 아님)
          podium: null,
          tower: null,
          floorsForUnits: floorCount > 0 ? floorCount : null,
          residentialGfaSqm: null,       // 부지 기반 단계는 주거전용 분해 없음 → null(무날조)
        }
      : null;
    const next = {
      totalGfaSqm: calc.maxGrossArea,
      floorCount,
      bcr: calc.buildingCoverage,
      far: calc.floorAreaRatio,
      buildingType: form.buildingUse,
      massGeom,
    };
    const cur = useProjectContextStore.getState().designData;
    const curMassW = cur?.massGeom?.buildingWidthM ?? null;
    const unchanged =
      cur != null &&
      cur.totalGfaSqm === next.totalGfaSqm &&
      cur.floorCount === next.floorCount &&
      cur.bcr === next.bcr &&
      cur.far === next.far &&
      cur.buildingType === next.buildingType &&
      curMassW === (massGeom?.buildingWidthM ?? null);
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
    envResult,
    contractFloors,
  ]);

  // ── INPUT 편집 필드(공용) ──
  // 부지연동(layoutSeeded)이면 고급 서랍 안에, 아닐 때는 본문에 직접 노출하므로 한 곳에 정의해 재사용한다.
  // (핸들러·setUserEdited 등 기존 동작 무변경 — 위치만 분기.)
  const landAreaField = (
    <div className="min-w-0">
      <label className="cc-label mb-2 block whitespace-nowrap">대지면적 (㎡)</label>
      <NumberInput allowDecimal placeholder="500" value={form.landArea === "" ? null : Number(form.landArea)} onChange={(n) => { setUserEdited(true); setForm((f) => ({ ...f, landArea: n != null ? String(n) : "" })); }}
        className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
    </div>
  );
  const zoningField = (
    <div className="min-w-0">
      <label className="cc-label mb-2 block whitespace-nowrap">용도지역</label>
      <select value={effectiveZoning} onChange={(e) => { setZoneEdited(true); setUserEdited(true); setForm((f) => ({ ...f, zoning: e.target.value })); }}
        className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
        {ZONING_OPTIONS.map((z) => <option key={z.key} value={z.key}>{z.name}</option>)}
      </select>
    </div>
  );
  const buildingUseField = (
    <div className="min-w-0">
      <label className="cc-label mb-2 block whitespace-nowrap">건물용도</label>
      <select value={form.buildingUse} onChange={(e) => { setUserEdited(true); setForm((f) => ({ ...f, buildingUse: e.target.value })); }}
        className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
        {["공동주택","업무시설","근린생활시설","숙박시설","판매시설","교육연구시설"].map((u) => <option key={u} value={u}>{u}</option>)}
      </select>
    </div>
  );
  // ③ 층고(m) — 일조 인벨로프 층수 천장 환산용 전문 파라미터. 일반인 기본화면에서는 빼고
  //    항상 고급 서랍 안에 둔다(미입력 시 기본 3.0 폴백은 기존대로).
  const floorHeightField = (
    <div className="min-w-0">
      <label className="cc-label mb-2 block whitespace-nowrap">층고 (m)</label>
      <NumberInput allowDecimal placeholder="3.0"
        value={form.floorHeight === "" ? null : Number(form.floorHeight)}
        onChange={(n) => {
          // 층고 범위 2.4~4.5m 클램프(빈값 허용 — 미입력 시 기본 3.0 폴백).
          const clamped = n == null ? "" : String(Math.min(4.5, Math.max(2.4, n)));
          setUserEdited(true);
          setForm((f) => ({ ...f, floorHeight: clamped }));
        }}
        className="w-full min-w-0 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
      <p className="mt-1 text-[10px] text-[var(--text-hint)]">기본 3.0m · 일조 천장 층수 환산</p>
    </div>
  );

  return (
    // @container: 이 스튜디오가 놓인 '칸의 실제 폭'에 반응한다(뷰포트 아님). 설계 스튜디오
    //   통합 작업면(DesignWorkspace)의 좁은 중앙 뷰포트에 임베드돼도, 아래 2열 분할이
    //   컨테이너 폭 기준으로만 펼쳐져 인스펙터 컬럼이 굶지 않는다 → 한글 캡션이 1글자 세로로
    //   무너지던 현상을 구조적으로 차단(InspectorGrid의 '전역 표준'을 최상위 분할에도 적용).
    //   전폭(프로젝트 설계 페이지)에선 종전처럼 2열로 펼쳐진다(무회귀).
    <div className="@container space-y-8">
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

      {/* ── 2열 레이아웃 ──
          좌측(인스펙터): 입력 + 결과 패널들을 순서대로. 큰 화면에서는 독립 스크롤.
          우측(캔버스): 활성 매싱안의 대형 2D 배치도 + 핵심 지표 + 3D 핸드오프. 큰 화면에서는 sticky 고정.
          작은 화면에서는 1열로 자연스럽게 세로 스택(종전과 동일). */}
      <div className="grid grid-cols-1 gap-8 @4xl:grid-cols-[minmax(0,1fr)_minmax(0,30rem)]">
        {/* 좌측 인스펙터 — 입력·결과 패널(스크롤). 큰 화면에서 독립 스크롤로 우측 캔버스와 분리. */}
        <div className="min-w-0 space-y-6 @4xl:max-h-[calc(100vh-12rem)] @4xl:overflow-y-auto @4xl:pr-2">

      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-6 border border-[var(--line-strong)]">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="cc-label text-[var(--text-secondary)]">INPUT · PARAMS</span>
          <h2 className="text-lg font-black text-[var(--text-primary)]">설계 조건</h2>
        </div>
        {/* 입력 영역 — 부지분석 연동 시(layoutSeeded) 일반인은 '확정 칩'(읽기전용)만 보고,
            편집은 '직접 조정(고급)' 서랍에서. 미연동/사용자 직접수정 시 종전처럼 편집 폼을 직접 노출. */}
        {/* ★레이아웃은 layoutSeeded(=부지연동)로만 분기 — 편집해도 폼이 같은 부모(서랍) 안에 머물러
            언마운트/포커스 상실이 없다. 칩 값은 '현재값'(편집 반영)을 보여주고, 편집은 서랍에서 한다. */}
        {layoutSeeded ? (
          <>
            {/* 확정 칩 3개 — 현재 적용값(편집하면 즉시 반영). 아직 미수정이면 '부지분석 자동' 배지. */}
            <InspectorGrid minItemRem={9}>
              {[
                { label: "대지면적", value: `${Math.round(form.landArea ? Number(form.landArea) : seededLandAreaSqm!).toLocaleString()} ㎡` },
                { label: "용도지역", value: effectiveZoning },
                { label: "건물용도", value: form.buildingUse },
              ].map((chip) => (
                <div key={chip.label} className="min-w-0 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3">
                  <div className="mb-1 flex items-center gap-1.5">
                    <span className="cc-label whitespace-nowrap text-[var(--text-secondary)]">{chip.label}</span>
                    {!userEdited ? (
                      <span className="inline-flex shrink-0 items-center rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--text-tertiary)]" title="부지분석이 자동 반영한 값 — 재분석 시 갱신됩니다. 직접 조정하려면 아래 '직접 조정(고급)'을 펼치세요.">부지분석 자동</span>
                    ) : (
                      <span className="inline-flex shrink-0 items-center rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--accent-strong)]" title="직접 조정한 값입니다.">직접 수정</span>
                    )}
                  </div>
                  <p className="cc-num truncate text-base font-black text-[var(--text-primary)]" title={chip.value}>{chip.value}</p>
                </div>
              ))}
            </InspectorGrid>
            {/* 직접 조정(고급) — 펼치면 편집 폼 4필드 그대로. 폼은 layoutSeeded 동안 항상 이 서랍 안에
                머무르므로(편집해도 부모 불변) 타이핑 중 포커스가 유지된다. */}
            <AdvancedDrawer label="직접 조정(고급)" className="mt-4">
              <InspectorGrid minItemRem={12}>
                {landAreaField}
                {zoningField}
                {buildingUseField}
                {floorHeightField}
              </InspectorGrid>
            </AdvancedDrawer>
          </>
        ) : (
          <>
            {/* 미연동(부지분석 없음) — 사용자가 입력해야 하므로 편집 폼 직접 노출. 층고만 고급 서랍으로. */}
            <InspectorGrid minItemRem={12}>
              {landAreaField}
              {zoningField}
              {buildingUseField}
            </InspectorGrid>
            <AdvancedDrawer label="고급 설정" className="mt-4">
              <InspectorGrid minItemRem={12}>
                {floorHeightField}
              </InspectorGrid>
            </AdvancedDrawer>
          </>
        )}
        {/* 부지분석 연동 안내 — 자동 LLM 호출은 과금 이슈로 하지 않고, 버튼 클릭 시 실행됨을 알린다.
            키 유무와 무관하게 연동 사실은 알린다(키 없으면 등록 후 가능 안내). */}
        {layoutSeeded && (
          <p className="mt-4 text-[11px] leading-snug text-[var(--text-hint)]">
            {isReady
              ? "부지분석 연동됨 — 심층 분석을 실행하면 AI 설계 의견이 추가됩니다."
              : "부지분석 연동됨 — API 키 등록 후 심층 분석으로 AI 설계 의견을 추가할 수 있습니다."}
          </p>
        )}
        <button onClick={handleAIAnalyze} disabled={isPending || !isReady || !form.landArea}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-blue-600 to-cyan-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "심층 분석 중…" : !isReady ? "API 키를 먼저 등록하세요 (아래 법규 계산은 즉시 가능)" : "심층 설계 분석"}
        </button>
      </motion.div>

      {/* ② 지역 실측 전형 매스 비교 — seed-design 연동. 주소가 있을 때만(부지분석 연동) 노출.
          법정 최대 vs 동네 실측 전형(건축물대장 중앙값 시드)을 나란히 비교해 과도한 사업규모를 방지. */}
      {siteAnalysis?.address && (
        <SeedDesignMassComparison
          address={siteAnalysis.address}
          landAreaSqm={Number(form.landArea) || effectiveLandAreaSqm(siteAnalysis) || 0}
          zoning={effectiveZoning}
          buildingUse={form.buildingUse}
          floorHeightM={Number(form.floorHeight) || 3}
          effectiveFarPct={seedEffectiveFarPct}
          effectiveBcrPct={seedEffectiveBcrPct}
          disabled={siteMatch === "mismatch"}
        />
      )}

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

          {/* 자동계산 칩 — 칩은 폭이 좁아도 무방하므로 칸 최소폭 7rem(컨테이너 실폭 반응).
              넓으면 종전처럼 4열, 좁아지면 2열→1열로 우아하게 접힘. */}
          <InspectorGrid minItemRem={7}>
            {[
              { label: "건폐율", val: `${calc.buildingCoverage}%`, sub: calc.bcrIsEffective ? `실효(법정상한 ${calc.bcrLegalMax}%)` : `법정상한 ${calc.bcrLegalMax}%`, color: "text-blue-400" },
              { label: "용적률", val: `${calc.floorAreaRatio}%`, sub: calc.farIsEffective ? `실효(법정상한 ${calc.farLegalMax}%)` : `법정상한 ${calc.farLegalMax}%`, color: "text-emerald-400" },
              // 예상 층수 — 정본(canonicalFloors) 기준. 폴백도 산술하한(maxFloors) 대신 정본→권장(recFloors).
              // 산술하한은 sub에 '근거'로만 작게 부기해 정본 층수와 구분(무날조 투명성).
              { label: "예상 층수", val: expectedFloors?.val ?? (canonicalFloors != null ? `${canonicalFloors}층` : `${calc.recFloors}층`), sub: `${expectedFloors?.sub ?? `${calc.maxHeight}m (${calc.heightNote})`} · 산술하한 ${calc.maxFloors}층(건폐율 만충)`, color: "text-purple-400" },
              { label: "주차 대수", val: `${calc.parking}대`, sub: "주차장법 기준", color: "text-amber-400" },
            ].map((k) => (
              <div key={k.label} className="cc-panel cc-interactive min-w-0 p-5 text-center">
                <p className={`cc-label ${k.color} mb-2`}>{k.label}</p>
                <p className="cc-num text-2xl font-black">{k.val}</p>
                <p className="text-[10px] text-[var(--text-hint)]">{k.sub}</p>
                {easy && EASY[k.label] && <p className="mt-1.5 text-[10px] leading-snug text-[var(--accent-strong)]">{EASY[k.label]}</p>}
              </div>
            ))}
          </InspectorGrid>

          {/* 법규 적합 체크리스트 — 적용값이 법정 한도 이내인지 한눈에 */}
          <div className="cc-panel p-6">
            <div className="mb-3 flex items-center gap-2.5">
              <span className="cc-label text-[var(--text-secondary)]">COMPLIANCE CHECK</span>
              <h3 className="text-sm font-black text-[var(--text-primary)]">법규 적합 체크리스트</h3>
            </div>
            {easy && <p className="mb-2 text-[11px] text-[var(--accent-strong)]">적용 설계값이 법으로 정한 한도 안에 들어오는지 확인합니다. ✓면 통과예요.</p>}
            {/* ★무날조: 적용값 vs 법정상한을 '실제 비교'한다. 적용 건폐율/용적률은 종상향·인센티브로
                법정상한을 넘을 수 있으므로(실효값) 항상 '적합'으로 단정하지 않고 실비교로 적합/초과를 가린다.
                종전 자가비교(적용=한도) 행은 제거. 높이는 법정 제한이 없으면(상업·준주거) '제한 없음'으로 정직 표기. */}
            <div className="space-y-1.5">
              {[
                { k: "건폐율", v: Number(calc.buildingCoverage), max: Number(calc.bcrLegalMax) },
                { k: "용적률", v: Number(calc.floorAreaRatio), max: Number(calc.farLegalMax) },
              ].map((row) => {
                const ok = row.v <= row.max + 1e-6;
                return (
                  <div key={row.k} className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs">
                    <span className="font-bold text-[var(--text-secondary)]">{row.k}</span>
                    <span className="cc-num text-[var(--text-hint)]">적용 {row.v}% / 법정상한 {row.max}%</span>
                    <span className="inline-flex items-center gap-1 font-black" style={{ color: ok ? "var(--status-success)" : "var(--status-error)" }}>{ok ? (<><CheckCircle2 className="size-3.5" aria-hidden />적합</>) : (<><AlertTriangle className="size-3.5" aria-hidden />초과</>)}</span>
                  </div>
                );
              })}
              {/* 높이 — 법정 제한이 있으면 그 사실을, 없으면(상업·준주거 등) '제한 없음'을 정직 표기(녹색 단정 금지). */}
              <div className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-xs">
                <span className="font-bold text-[var(--text-secondary)]">높이</span>
                <span className="cc-num text-[var(--text-hint)]">{calc.heightNote === "법적 높이 제한" ? `법정 제한 ${calc.maxHeight}m 적용` : `제한 없음 (약 ${calc.maxHeight}m)`}</span>
              </div>
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
                farLimitPct={resolveFarPct(siteAnalysis) ?? undefined}
                bcrLimitPct={resolveBcrPct(siteAnalysis) ?? undefined}
                floorHeightM={form.floorHeight ? Number(form.floorHeight) : undefined}
                onResult={(r) => setEnvResult(r)}
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
              {aiEff?.setbacks ? (
                <span className="rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">AI 분석 산출값</span>
              ) : (
                <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold text-amber-500">기본 가정치</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              {[
                { label: "전면", val: aiEff?.setbacks?.front ?? calc.setbacks.front },
                { label: "측면", val: aiEff?.setbacks?.side ?? calc.setbacks.side },
                { label: "후면", val: aiEff?.setbacks?.rear ?? calc.setbacks.rear },
              ].map((s) => (
                <div key={s.label} className="rounded-xl bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                  <p className="cc-label text-[var(--text-hint)]">{s.label}</p>
                  <p className="cc-num text-xl font-black">{s.val}<span className="text-xs ml-0.5">m</span></p>
                </div>
              ))}
            </div>
            {!aiEff?.setbacks && (
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
                Array.isArray(aiEff?.massingOptions) ? aiEff.massingOptions : calc.massingOptions;
              const best = Math.max(...opts.map((o) => o.efficiency || 0));
              // 매싱 대안 카드 — 카드 안에 배치도(MassingDiagram)+설명이 들어가 충분히 넓어야 의미가 있다.
              // 그래서 칸 최소폭을 14rem으로 크게(컨테이너 실폭 반응). 넓으면 3열, 좁아지면 자연히 1~2열.
              return (
                <InspectorGrid minItemRem={14} gap={3} className="mt-2 [&>button]:min-w-0">
                  {opts.map((m, i) => {
                    const isBest = (m.efficiency || 0) === best;
                    // 선택 우선 — 사용자가 고른 대안이 활성. 미선택이면 추천(최고효율)이 활성.
                    const isActive = selectedMassing ? m.name === selectedMassing : isBest;
                    const estGfa = calc.maxGrossArea ? Math.round(calc.maxGrossArea * (m.efficiency / 100)) : null;
                    // ③ 실프리뷰 geom — 좌측 카드도 우측 캔버스와 '같은 정본 층수(floorsForGeom)'로
                    //    재생성한다. m.geom(calc recFloors 기준)을 그대로 쓰면 정본(canonicalFloors)과
                    //    어긋나 좌 '22층'·우 '65층'처럼 보이므로, 정본 층수로 통일(좌우 단일 참조·무날조).
                    const geomFloors = floorsForGeom ?? calc.recFloors;
                    const geom = buildMassingGeom(
                      massingKindFromName(m.name),
                      Math.min(calc.maxGrossArea / Math.max(geomFloors, 1), calc.buildableArea),
                      calc.siteSide,
                      geomFloors,
                    );
                    return (
                      <button
                        key={i}
                        type="button"
                        onClick={() => setSelectedMassing((cur) => (cur === m.name ? null : m.name))}
                        aria-pressed={selectedMassing === m.name}
                        aria-label={`${m.name} 매싱안 선택`}
                        className={`relative min-w-0 overflow-hidden cursor-pointer rounded-xl border p-4 text-left transition-all ${isActive ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[var(--shadow-md)]" : "border-[var(--line)] bg-[var(--surface-muted)] hover:border-[var(--line-strong)] hover:bg-[var(--surface)]"}`}
                      >
                        {isBest && <span className="absolute right-3 top-3 rounded-full bg-[var(--accent-strong)] px-2 py-0.5 text-[9px] font-black text-white">★ 추천</span>}
                        <MassingDiagram name={m.name} active={isActive} geom={geom} />
                        <p className="mt-1 text-sm font-bold text-[var(--text-primary)] break-words">{m.name}</p>
                        <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-secondary)] break-words line-clamp-2">{m.description}</p>
                        <div className="mt-2 flex items-center gap-2 min-w-0">
                          <div className="h-2 flex-1 min-w-0 rounded-full bg-[var(--line)]"><div className="h-2 rounded-full" style={{ width: `${m.efficiency}%`, background: isActive ? "var(--accent-strong)" : "#60a5fa" }} /></div>
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
                </InspectorGrid>
              );
            })()}
          </div>

          {aiEff?.summary && (
            <div className="glass rounded-2xl p-6 border border-blue-500/20 bg-blue-500/5">
              <h3 className="text-lg font-black text-blue-400 mb-2">AI 설계 의견</h3>
              <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiEff.summary}</p>
            </div>
          )}

          {/* 구조화 추출 실패 시에만 정제 텍스트(코드펜스 제거) 표시 — raw JSON 코드블록 노출 방지. */}
          {aiResult && !aiEff && aiCleanText && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">AI 설계 결과</h3>
              <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiCleanText}</p>
            </div>
          )}
        </motion.div>
      )}
        </div>
        {/* ── 우측 캔버스(sticky) ── 활성 매싱안의 대형 2D 배치도 + 핵심 지표 + 3D 핸드오프.
            큰 화면에서 좌측 스크롤과 무관하게 항상 보이도록 고정. 작은 화면에서는 좌측 아래로 흐른다.
            ★WebGL/Three.js 3D 캔버스를 여기 직접 마운트하지 않는다 — 2D(MassingDiagram=SVG) 전용.
            기존 lazy 3D는 'draw' 스텝에서만 마운트(컨텍스트 고갈 방지)하며, 여기선 버튼으로 핸드오프만 한다. */}
        <div className="min-w-0 @4xl:sticky @4xl:top-6 @4xl:h-[calc(100vh-12rem)]">
          <div className="cc-panel flex h-full flex-col gap-4 overflow-hidden p-5">
            <div className="flex items-center gap-2.5">
              <span className="cc-label text-[var(--text-secondary)]">CANVAS · {canvasView === "3d" ? "3D 입체" : "2D 평면"}</span>
              <h3 className="text-sm font-black text-[var(--text-primary)]">매싱 배치 미리보기</h3>
              {calc && activeMassing && (
                <span className="ml-auto rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
                  {activeMassing.active.name}{activeMassing.isBest ? " · 추천" : " · 선택"}
                </span>
              )}
            </div>

            {calc && activeMassing ? (
              <>
                {/* 2D 평면 / 3D 입체 인라인 토글(세그먼트) — 캔버스 측에서 뷰를 바로 전환.
                    ★3D는 순수 SVG 축측투영(MassingAxon3D)일 뿐 WebGL 컨텍스트를 새로 띄우지 않는다. */}
                <div className="flex gap-1.5">
                  {([
                    { key: "2d" as const, label: "평면 2D" },
                    { key: "3d" as const, label: "입체 3D" },
                  ]).map((opt) => {
                    const on = canvasView === opt.key;
                    return (
                      <button
                        key={opt.key}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setCanvasView(opt.key)}
                        className={`rounded-xl border px-3 py-1.5 text-xs font-bold transition-colors ${
                          on
                            ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                            : "border-[var(--line)] text-[var(--text-secondary)]"
                        }`}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>

                {/* 대형 미리보기 — 2D는 MassingDiagram(배치평면), 3D는 MassingAxon3D(축측투영 입체·SVG).
                    min-h로 최소 높이만 보장하고, 좁은 임베드(1열)에선 100vh 강제 높이가 없어 거대 공백을
                    만들지 않는다(전폭 2열에선 부모 h-full로 종전처럼 확장). */}
                <div className="flex min-h-[16rem] flex-1 items-center justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface-muted)] p-4">
                  <div className="h-full w-full">
                    {canvasView === "2d" ? (
                      <MassingDiagram name={activeMassing.active.name} active geom={activeMassing.geom} />
                    ) : (
                      <MassingAxon3D
                        geom={activeMassing.geom}
                        floorHeightM={form.floorHeight ? Number(form.floorHeight) : undefined}
                        active
                      />
                    )}
                  </div>
                </div>

                {/* 3D 뷰 정직 고지 — 개념 입체일 뿐, 정밀 3D·BIM은 아래 핸드오프 버튼으로. */}
                {canvasView === "3d" && (
                  <p className="text-[11px] leading-snug text-[var(--text-hint)]">
                    개념 입체(축측투영) — 정밀 3D·BIM은 아래 편집실에서
                  </p>
                )}

                {/* 핵심 지표 칩 — 활성안 기준. 무날조: calc/envResult 실값만, 없으면 "—".
                    ★칸 실폭 기준(@container): 좁은 임베드 칸에선 2열, 넓으면 3열(뷰포트 sm: 대신 @sm:) */}
                <div className="grid grid-cols-2 gap-2 @sm:grid-cols-3">
                  {[
                    { label: "층수", val: activeMassing.floors != null ? `${activeMassing.floors}층` : "—" },
                    { label: "건축면적", val: calc.buildableArea != null ? `${Math.round(calc.buildableArea).toLocaleString()}㎡` : "—" },
                    { label: "예상 전용 연면적", val: activeMassing.estGfa != null ? `${activeMassing.estGfa.toLocaleString()}㎡` : "—" },
                    { label: "효율", val: activeMassing.active.efficiency != null ? `${activeMassing.active.efficiency}%` : "—" },
                    // BCR/FAR은 좌측 calc 확정값으로 단일화 — calc는 이미 주소 정합성(mismatch) 가드를
                    // 통과한 buildingCoverage/floorAreaRatio라, 다른 부지 잔류 분석이 칩을 오염시키지 않게
                    // 가드를 자동 상속하고 좌·우 출처가 한곳으로 묶인다(SSOT).
                    { label: "건폐율(BCR)", val: calc.buildingCoverage != null ? `${calc.buildingCoverage}%` : "—" },
                    { label: "용적률(FAR)", val: calc.floorAreaRatio != null ? `${calc.floorAreaRatio}%` : "—" },
                  ].map((chip) => (
                    <div key={chip.label} className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-center">
                      <p className="cc-label text-[10px] text-[var(--text-hint)]">{chip.label}</p>
                      <p className="cc-num text-sm font-black text-[var(--text-primary)]">{chip.val}</p>
                    </div>
                  ))}
                </div>

                {/* 3D·BIM 핸드오프 — onOpen3D가 있을 때만 노출(없으면 숨김). 여기서 WebGL을 직접 띄우지 않는다. */}
                {onOpen3D && (
                  <button
                    type="button"
                    onClick={onOpen3D}
                    className="w-full rounded-2xl bg-gradient-to-r from-blue-600 to-cyan-600 py-3 text-sm font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99]"
                  >
                    3D·BIM 편집실로 →
                  </button>
                )}
              </>
            ) : (
              // designData(부지면적·용도지역) 게이트 미충족 — 안내 플레이스홀더.
              <div className="flex min-h-[16rem] flex-1 items-center justify-center rounded-2xl border border-dashed border-[var(--line)] bg-[var(--surface-muted)] p-6 text-center">
                <p className="text-sm leading-snug text-[var(--text-hint)]">
                  부지면적·용도지역을 입력하면<br />매싱 미리보기가 표시됩니다
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
