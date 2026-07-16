"use client";

/**
 * DesignAuditWorkspace — 설계안 AI 심사(DA-7) 4단 스테퍼 워크스페이스.
 *
 *  ⑴ 부지: 활성 프로젝트 부지(useProjectContextStore.siteAnalysis) **읽기 전용** 사용
 *          또는 주소 직접 입력(로컬 state) — 이 화면은 컨텍스트 스토어를 절대 수정하지 않는다.
 *  ⑵ 개요: BriefUploadStep(PDF/텍스트 → POST /design-audit/extract-brief)
 *          + ParamConfirmStep(필드 그리드 — '추출'/'수동' 출처 배지·quote 툴팁·수정).
 *  ⑶ 도면: IFC 업로드 슬롯 + DXF 업로드 슬롯(.dxf · 20MB — CAD 2.0 내보내기 호환).
 *  ⑷ 실행: POST /design-audit/run-upload/jobs(제출, multipart: payload JSON + ifc_file?
 *          + dxf_file?) → job_id 즉시 반환 → GET /design-audit/run-upload/jobs/{id} 폴링
 *          (등기 권리분석 lib/registry-analyze.ts 패턴 재사용) → AuditReportView 전환.
 *          진행 중 job_id는 sessionStorage에 보존해 탭 종료·리로드 후에도 재진입 시 폴링을
 *          이어간다(이전엔 단일 블로킹 POST라 리로드 시 진행이 통째로 유실됐다 — 로드맵②).
 *
 * 정직성 원칙: 빈 결과·서버 오류는 메시지 그대로 노출, 가짜값·임의 링크 생성 금지. 실행 중
 * 표시는 잡 상태(pending/running) 기반 실측 경과 시간만 — 가짜 단계진행 연출 없음.
 * apiClient v1 패턴 + 디자인 토큰(CSS 변수)만 사용.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Boxes, Construction, DraftingCompass, Folder, Settings } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { DesignData } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveDominantZone } from "@/lib/zoning-ssot";
import type { Locale } from "@/i18n/config";
import {
  BriefUploadStep,
  apiErrorMessage,
  type BriefField,
} from "./BriefUploadStep";
import { ParamConfirmStep } from "./ParamConfirmStep";
import { AuditReportView, type DesignAuditReport } from "./AuditReportView";
import { AnnotatedSitePlanCard } from "@/components/cad/AnnotatedSitePlanCard";
import {
  auditFindingsToLegal,
  auditSchematicGeometry,
  auditVerdict,
} from "./auditAnnotation";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";

/* ── 스테퍼 정의 ── */

const STEPS = [
  { key: "site", label: "부지", desc: "프로젝트 선택 또는 주소" },
  { key: "brief", label: "개요", desc: "건축개요 업로드·확인" },
  { key: "drawing", label: "도면", desc: "IFC·DXF 첨부(선택)" },
  { key: "run", label: "실행", desc: "AI 심사 실행" },
] as const;

/* ── 실행 중 표시할 '심사 점검 항목' 목록 — 순차 완료 연출이 아니라 이 심사가 다루는 범위를 나열만 한다. ── */

const ENGINE_STEPS = [
  "개요·도면 파라미터 정규화",
  "법규 한도 검증 (건폐율·용적률·높이)",
  "일조·이격거리 검토",
  "주차 설치기준 검토",
  "피난·방화 체크",
  "인근 인허가 사례 비교",
  "인센티브 경로 탐색",
  "리스크·사각지대 스캔",
];

const MAX_IFC_BYTES = 200 * 1024 * 1024; // 200MB — BIM 모델 상한(클라이언트 사전 차단)
const MAX_DXF_BYTES = 20 * 1024 * 1024; // 20MB — DXF 상한(백엔드 import-dxf 한도와 동일)

/** 경과 초 → "m:ss" 표기 — 실제 경과 시간만 표시(가짜 단계진행 연출 대체·정직). */
function formatElapsed(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${String(rem).padStart(2, "0")}`;
}

/* ── 로드맵② — 잡 제출+폴링(lib/registry-analyze.ts analyzeRegistry 패턴 재사용) ──
   design-runs(WP-L)는 사전 존재 run_id의 승인/실행 "상태"만 옮기는 전이 API라 매 실행이
   신규 job_id를 그 자리에서 발급하는 이 화면에는 맞지 않아(백엔드 design_audit.py 잡 엔드포인트
   주석 참조), 등기 권리분석과 동일한 제출+폴링 패턴을 그대로 재사용한다. */

const AUDIT_JOB_STORAGE_KEY = "propai:design-audit:active-job";

type AuditJobSubmitResp = { job_id: string | null; status: string };
type AuditJobStatusResp = { status: string; result?: DesignAuditReport; error?: string };

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** job_id 폴링(4초 간격·최대 8분 — 예상 소요 3~5분 + 여유). 완료 시 보고서, 실패 시 에러 throw. */
async function pollDesignAuditJob(jobId: string): Promise<DesignAuditReport> {
  const deadline = Date.now() + 8 * 60 * 1000;
  while (Date.now() < deadline) {
    await sleep(4000);
    let s: AuditJobStatusResp;
    try {
      s = await apiClient.get<AuditJobStatusResp>(
        `/design-audit/run-upload/jobs/${encodeURIComponent(jobId)}`,
        { timeoutMs: 15000 },
      );
    } catch {
      continue; // 네트워크 일시 오류 → 다음 폴링 재시도
    }
    if (s.status === "done" && s.result) return s.result;
    if (s.status === "error") throw new Error(s.error || "설계안 심사 실행에 실패했습니다.");
  }
  throw new Error("설계안 심사 시간이 초과되었습니다. 잠시 후 다시 시도하세요.");
}

/** ★매스 브릿지 — 설계 스튜디오 산출 매스(designData) → 심사 개요 필드(BriefField[]) 매핑.
 *
 * 키/라벨/단위는 백엔드 표준(design_audit.brief_extractor.BRIEF_FIELDS + _BRIEF_UNITS)과 1:1이라
 * run-upload가 brief.fields[{key,value}] → params dict로 그대로 소비한다(라우터 705~707).
 * 값이 실재할 때만 담는다(무날조 — 없는 값은 생략). 대지면적·용도지역(zone)은 ⑴부지 입력이
 * 권위 출처이므로 여기서 중복 시드하지 않는다(혼입 방지). 출처는 'user' — 업로드 문서에서
 * 추출한 값이 아니라 사용자 프로젝트의 설계 산출값임을 뜻한다(안내 문구로 출처를 별도 명시). */
function briefFieldsFromDesignData(d: DesignData): BriefField[] {
  const out: BriefField[] = [];
  const addNum = (
    key: string,
    label: string,
    unit: string | null,
    v: number | null | undefined,
  ) => {
    if (typeof v !== "number" || !Number.isFinite(v) || v <= 0) return;
    // 정수 성격(층수·세대수)은 정수로, 그 외는 소수 1자리 반올림 표기.
    const isCount = key === "floors_above" || key === "units";
    const value = isCount ? String(Math.round(v)) : String(Math.round(v * 10) / 10);
    out.push({ key, label, value, extractedValue: "", unit, quote: null, source: "user" });
  };
  const addStr = (key: string, label: string, v: string | null | undefined) => {
    const s = (v ?? "").toString().trim();
    if (!s) return;
    out.push({ key, label, value: s, extractedValue: "", unit: null, quote: null, source: "user" });
  };
  addNum("building_area_sqm", "건축면적(㎡)", "㎡", d.massGeom?.footprintSqm ?? null);
  addNum("total_floor_area_sqm", "연면적(㎡)", "㎡", d.totalGfaSqm);
  addNum("bcr_pct", "건폐율(%)", "%", d.bcr);
  addNum("far_pct", "용적률(%)", "%", d.far);
  addNum("building_height_m", "건축물 높이(m)", "m", d.heightM ?? null);
  addNum("floors_above", "지상 층수", "층", d.floorCount);
  addNum("units", "세대수", "세대", d.unitCount ?? null);
  addStr("building_use", "주용도", d.buildingType);
  return out;
}

/** 부지분석 SSOT의 조례 데이터(OrdinanceData) → 백엔드 legal_zone_limits.applicable_limits_for
 * 계약(regulation_payload.local_ordinance)으로 옮겨 담는다(변환만 — 값 생성 금지).
 *
 * 실신호(ordinanceFar/ordinanceBcr/effectiveFar/effectiveBcr/source) 전무 시 null(미전송과
 * 동치) — 백엔드 _extract_ordinance_far가 어차피 source(법정상한 폴백 등)로 재검증하므로
 * 여기서는 존재하는 값만 그대로 relay한다(무날조 — 프론트가 조례 여부를 판정하지 않는다).
 */
function buildRegulationPayload(
  ordinance:
    | {
        ordinanceFar?: number | null;
        ordinanceBcr?: number | null;
        effectiveFar?: number | null;
        effectiveBcr?: number | null;
        source?: string | null;
      }
    | null
    | undefined,
): { local_ordinance: Record<string, unknown> } | null {
  if (!ordinance) return null;
  const hasSignal =
    ordinance.ordinanceFar != null ||
    ordinance.ordinanceBcr != null ||
    ordinance.effectiveFar != null ||
    ordinance.effectiveBcr != null ||
    !!ordinance.source;
  if (!hasSignal) return null;
  return {
    local_ordinance: {
      ordinance_far: ordinance.ordinanceFar ?? null,
      ordinance_bcr: ordinance.ordinanceBcr ?? null,
      effective_far: ordinance.effectiveFar ?? null,
      effective_bcr: ordinance.effectiveBcr ?? null,
      source: ordinance.source || null,
    },
  };
}

export function DesignAuditWorkspace({
  locale,
  showHeader = true,
}: {
  locale: Locale;
  showHeader?: boolean;
}) {
  /* 컨텍스트 스토어 — 읽기 전용 구독(액션 호출 금지: 이 화면은 스토어를 수정하지 않는다). */
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  // ★매스 브릿지(모세혈관) — 설계 스튜디오 산출 매스(designData)를 심사 개요에 자동 시드(읽기 전용 구독).
  const designData = useProjectContextStore((s) => s.designData);

  const [step, setStep] = useState(0);
  const [maxVisited, setMaxVisited] = useState(0);

  /* ⑴ 부지 — 프로젝트 컨텍스트 사용 vs 주소 직접 입력(로컬 state만).
     초기값은 SSR과 동일한 "manual"로 결정적으로 두고(하이드레이션 불일치 방지),
     마운트 후 아래 효과에서만 프로젝트 모드로 전환한다. */
  const [siteMode, setSiteMode] = useState<"project" | "manual">("manual");
  const [manualAddress, setManualAddress] = useState("");
  const [manualAreaSqm, setManualAreaSqm] = useState("");
  // 프로젝트(주소 보유)가 있으면(사용자 선택 전·수동주소 미입력일 때만)
  // 프로젝트 모드로 1회 자동 전환 — 사용자가 모드를 만지면 더 이상 개입하지 않는다.
  const modeTouched = useRef(false);
  useEffect(() => {
    if (!modeTouched.current && projectId && siteAnalysis?.address && !manualAddress) {
      setSiteMode("project");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, siteAnalysis?.address]);

  /* ⑵ 개요 — 추출 필드(출처 배지·수정) */
  const [fields, setFields] = useState<BriefField[]>([]);
  const [briefId, setBriefId] = useState<string | null>(null);
  const [briefNote, setBriefNote] = useState<string | null>(null);
  // 설계 스튜디오 매스를 개요에 자동 시드했는지(안내 문구 표기용) + 1회 시드 가드.
  const [seededFromDesign, setSeededFromDesign] = useState(false);
  const designSeedRef = useRef(false);

  /* ★매스 브릿지 — 설계 스튜디오가 산출한 매스(designData)를 심사 개요 필드로 1회 자동 시드한다.
     - 있을 때만: 매핑 가능한 값이 하나라도 있을 때만(없으면 무시 — 무날조).
     - 무손상: 이미 추출/수동 입력한 개요(fields)가 있으면 덮지 않는다(기존 업로드 경로 보존).
     출처는 'user'(업로드 문서 추출이 아니라 사용자 프로젝트 설계값) — 아래 안내 문구로 출처를 명시한다. */
  useEffect(() => {
    if (designSeedRef.current) return; // 1회만 시드(사용자 편집·추출을 재덮어쓰지 않음)
    if (fields.length > 0) return; // 이미 개요값이 있으면 시드 안 함(무손상)
    if (!designData) return;
    const seeded = briefFieldsFromDesignData(designData);
    if (seeded.length === 0) return; // 매핑 가능한 값이 하나도 없으면 시드 안 함
    designSeedRef.current = true;
    setFields(seeded);
    setSeededFromDesign(true);
  }, [designData, fields.length]);

  /* ⑶ 도면 — IFC·DXF 파일(선택) */
  const ifcRef = useRef<HTMLInputElement>(null);
  const [ifcFile, setIfcFile] = useState<File | null>(null);
  const [ifcError, setIfcError] = useState("");
  const dxfRef = useRef<HTMLInputElement>(null);
  const [dxfFile, setDxfFile] = useState<File | null>(null);
  const [dxfError, setDxfError] = useState("");

  /* ⑷ 실행 */
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [report, setReport] = useState<DesignAuditReport | null>(null);
  // 실행 경과 시간(초) — 실제 시간만 표기(가짜 단계진행 연출 금지·정직).
  const [elapsedSec, setElapsedSec] = useState(0);
  // AI 보조(사각지대 쟁점 생성) 옵트인 — 종전엔 use_llm 미전송이라 백엔드 기본값(True)에 암묵
  // 의존해 항상 ON이었다. 기본 true로 유지해 기존 동작을 보존하면서, 끄면 규칙기반 심사만
  // 받을 수 있게 한다(D1).
  const [useLlm, setUseLlm] = useState(true);
  // 잡 실제 시작 시각(ms) — 리로드 복원 시에도 실제 경과(원래 시작 시각 기준)를 이어서 표시하기
  // 위해 ref로 보존(state로 하면 setRunning(true)와의 렌더 순서 경합이 생길 수 있어 ref 사용).
  const jobStartedAtRef = useRef<number | null>(null);

  /* 실행 중 경과 시간(초) 카운터 — 실제 진행과 무관한 '가짜 단계 연출'을 제거한 정직한 시계.
     엔진 단계는 아래에서 '이 심사가 점검하는 항목'으로 나열만 하고, 진행 상태는 단일 '진행 중'으로
     표시한다(잡 상태 기반 — 완료되면 결과 보고서로 자동 전환). 리로드로 복원된 실행은
     jobStartedAtRef가 원래 시작 시각을 담고 있어 경과 시간이 0으로 리셋되지 않는다. */
  useEffect(() => {
    if (!running) {
      setElapsedSec(0);
      jobStartedAtRef.current = null;
      return;
    }
    const startedAt = jobStartedAtRef.current ?? Date.now();
    setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    const timer = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [running]);

  /* 리로드·재진입 복원 — 탭 종료·새로고침으로 진행 중이던 잡을 sessionStorage에서 찾아 이어서
     폴링한다(마운트 1회만). 이전엔 단일 블로킹 POST라 리로드하면 진행 자체가 유실됐다(로드맵②). */
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.sessionStorage.getItem(AUDIT_JOB_STORAGE_KEY);
    if (!raw) return;
    let parsed: { jobId?: string; startedAt?: number } | null = null;
    try {
      parsed = JSON.parse(raw) as { jobId?: string; startedAt?: number };
    } catch {
      parsed = null;
    }
    if (!parsed?.jobId) {
      window.sessionStorage.removeItem(AUDIT_JOB_STORAGE_KEY);
      return;
    }
    let cancelled = false;
    jobStartedAtRef.current = parsed.startedAt ?? Date.now();
    setRunning(true);
    setRunError("");
    goTo(3); // 진행 패널이 보이는 ⑷ 실행 단계로 복귀(goTo는 함수 선언 — 호이스팅으로 안전 호출)
    pollDesignAuditJob(parsed.jobId)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e) => {
        if (!cancelled) {
          setRunError(apiErrorMessage(e, "설계안 심사 실행에 실패했습니다. 잠시 후 다시 시도하세요."));
        }
      })
      .finally(() => {
        if (cancelled) return;
        setRunning(false);
        window.sessionStorage.removeItem(AUDIT_JOB_STORAGE_KEY);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* 현재 부지 해석 — project 모드는 컨텍스트 스냅샷을 그대로 읽기만 한다. */
  const usingProject = siteMode === "project" && !!projectId && !!siteAnalysis;
  const manualArea = (() => {
    const n = Number(manualAreaSqm.replace(/[^0-9.]/g, ""));
    return Number.isFinite(n) && n > 0 ? n : null;
  })();
  const site = usingProject
    ? {
        address: siteAnalysis?.address ?? "",
        pnu: siteAnalysis?.pnu ?? null,
        // ★용도지역은 SSOT 리더(resolveDominantZone)로 읽는다 — 다필지 통합 대표(우세) 용도지역
        //   우선, 없으면 단일 zoneCode(직독 대신 단일 계약으로 통합·백엔드 zone_type 봉합).
        zoneCode: resolveDominantZone(siteAnalysis),
        // 시군구(조례 딥링크·인센티브 resolver용) — 부지분석 조례 SSOT에서 도출.
        sigungu: siteAnalysis?.ordinance?.sigungu ?? null,
        // ★다필지면 통합 면적 — 심의 면적/도식 footprint가 통합 부지 기준이 되도록.
        landAreaSqm: effectiveLandAreaSqm(siteAnalysis),
        // 조례·실효한도 페이로드(인센티브 조례계층 실효한도 산정용) — SSOT에 실신호 있을 때만.
        regulationPayload: buildRegulationPayload(siteAnalysis?.ordinance),
      }
    : {
        address: manualAddress.trim(),
        pnu: null,
        zoneCode: null,
        sigungu: null,
        landAreaSqm: manualArea,
        regulationPayload: null,
      };
  const siteReady = !!site.address || !!site.pnu;

  function goTo(next: number) {
    const clamped = Math.max(0, Math.min(next, STEPS.length - 1));
    setStep(clamped);
    setMaxVisited((v) => Math.max(v, clamped));
  }

  /* ⑵ 개요 필드 수정 — 추출 원본과 같아지면 '추출', 달라지면 'user'(수동)로 전환. */
  function handleFieldChange(key: string, value: string) {
    setFields((prev) =>
      prev.map((f) =>
        f.key === key
          ? { ...f, value, source: value === f.extractedValue ? "extracted" : "user" }
          : f,
      ),
    );
  }

  function handleIfcPick(picked: File | null) {
    setIfcError("");
    if (!picked) {
      setIfcFile(null);
      return;
    }
    if (!/\.ifc$/i.test(picked.name)) {
      setIfcError("IFC 파일(.ifc)만 첨부할 수 있습니다.");
      return;
    }
    if (picked.size > MAX_IFC_BYTES) {
      setIfcError("파일이 너무 큽니다(최대 200MB).");
      return;
    }
    setIfcFile(picked);
  }

  function handleDxfPick(picked: File | null) {
    setDxfError("");
    if (!picked) {
      setDxfFile(null);
      return;
    }
    if (!/\.dxf$/i.test(picked.name)) {
      setDxfError("DXF 파일(.dxf)만 첨부할 수 있습니다. DWG는 CAD에서 'DXF로 저장' 후 첨부하세요.");
      return;
    }
    if (picked.size > MAX_DXF_BYTES) {
      setDxfError("파일이 너무 큽니다(최대 20MB).");
      return;
    }
    setDxfFile(picked);
  }

  /* ⑷ 실행 — multipart(payload JSON + ifc_file? + dxf_file?) → 보고서 전환 */
  async function runAudit() {
    if (!siteReady) {
      setRunError("부지 정보가 필요합니다 — 1단계에서 프로젝트를 선택하거나 주소를 입력하세요.");
      goTo(0);
      return;
    }
    const startedAt = Date.now();
    jobStartedAtRef.current = startedAt;
    setRunning(true);
    setRunError("");
    try {
      const fd = new FormData();
      fd.append(
        "payload",
        JSON.stringify({
          site: {
            project_id: usingProject ? projectId : null,
            address: site.address || null,
            pnu: site.pnu || null,
            // 백엔드 run()이 zone_type←zone_code 폴백으로 봉합(용도지역이 한도의존 엔진에 도달).
            zone_code: site.zoneCode || null,
            sigungu: site.sigungu || null,
            land_area_sqm: site.landAreaSqm ?? null,
            // 조례·실효한도 페이로드(SSOT에 실신호 있을 때만 — 없으면 null, 날조 금지).
            regulation_payload: site.regulationPayload ?? null,
          },
          brief: {
            brief_id: briefId,
            fields: fields.map((f) => ({
              key: f.key,
              label: f.label,
              value: f.value,
              unit: f.unit ?? null,
              quote: f.quote ?? null,
              source: f.source, // extracted | user — 수동 수정값 구분 전달
            })),
          },
          drawing: {
            ifc_filename: ifcFile?.name ?? null,
            dxf_filename: dxfFile?.name ?? null,
          },
          use_llm: useLlm,
        }),
      );
      if (ifcFile) fd.append("ifc_file", ifcFile);
      if (dxfFile) fd.append("dxf_file", dxfFile);
      // ★로드맵② — 블로킹 단일 POST 대신 잡 제출+폴링(등기 권리분석 패턴 재사용). 제출 자체는
      // 파싱·DXF/IFC 검증만 하므로 빠르다(무거운 심사는 서버 백그라운드).
      const job = await apiClient.post<AuditJobSubmitResp>("/design-audit/run-upload/jobs", {
        body: fd,
        timeoutMs: 60_000,
      });
      if (!job?.job_id) {
        throw new Error("심사 작업 제출에 실패했습니다 — 잠시 후 다시 시도하세요.");
      }
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(
          AUDIT_JOB_STORAGE_KEY,
          JSON.stringify({ jobId: job.job_id, startedAt }),
        );
      }
      const r = await pollDesignAuditJob(job.job_id);
      if (!r || typeof r !== "object") {
        throw new Error("심사 응답이 비어 있습니다 — 잠시 후 다시 시도하세요.");
      }
      setReport(r);
    } catch (e) {
      setRunError(apiErrorMessage(e, "설계안 심사 실행에 실패했습니다. 잠시 후 다시 시도하세요."));
    } finally {
      setRunning(false);
      if (typeof window !== "undefined") window.sessionStorage.removeItem(AUDIT_JOB_STORAGE_KEY);
    }
  }

  /* 추출/수동 필드 수 — 실행 요약 표기 */
  const extractedCount = fields.filter((f) => f.source === "extracted").length;
  const userCount = fields.length - extractedCount;

  /* ⑤ 제출번들(zip) — 실제 프로젝트(usingProject)이고 설계 스튜디오 매스(massGeom)가 실재할
     때만(=도면세트 있음) AuditReportView에 다운로드 버튼 소재를 넘긴다. 대지폭·깊이 등 미보유
     항목은 값을 지어내지 않고 생략(백엔드 SubmissionBundleRequest 기본값에 위임 — 그 기본값은
     API 계약 자체가 선언한 것이라 프론트 날조가 아니다). */
  const bundleProjectId = usingProject ? projectId : null;
  const bundleContext =
    bundleProjectId && designData?.massGeom?.buildingWidthM && designData?.massGeom?.buildingDepthM
      ? {
          buildingWidthM: designData.massGeom.buildingWidthM,
          buildingDepthM: designData.massGeom.buildingDepthM,
          floorCount: designData.floorCount ?? null,
          buildingUse: designData.buildingType ?? null,
          zoneCode: site.zoneCode ?? null,
          projectName: projectName ?? null,
          unitTypes: designData.unitTypes ?? null,
          households: designData.unitCount ?? null,
        }
      : null;

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* 헤더 */}
      {showHeader ? (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            <div className="flex items-center gap-3">
              <Construction className="size-7 text-[var(--accent-strong)]" aria-hidden />
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <span className="cc-meta">DESIGN · AI AUDIT</span>
                  <span className="cc-chip-data">DA-7</span>
                </div>
                <h1 className="text-lg font-black text-[var(--text-primary)]">AI 설계분석</h1>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  부지·건축개요·도면(IFC·DXF)을 입력하면 법규 적합성(건폐율·용적률·일조·주차·피난)과
                  인근 인허가 사례 비교·인센티브 경로·사각지대를 AI가 사전 심사합니다.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {report ? (
        /* 실행 완료 → 보고서 뷰 + §4-C 후속: 법규 준수 배치도(findings→도면 주석, audit↔drawing) */
        <>
          <AuditReportView
            report={report}
            onReset={() => setReport(null)}
            projectId={bundleProjectId}
            bundleContext={bundleContext}
          />
          {(() => {
            const legal = auditFindingsToLegal(report);
            const geometry = auditSchematicGeometry(site.landAreaSqm, legal);
            // 건폐율 finding·대지면적이 없으면 카드 미표시(건물 footprint 도출 불가 — 정직)
            return geometry ? (
              <AnnotatedSitePlanCard
                geometry={geometry}
                findings={legal}
                verdict={auditVerdict(report)}
              />
            ) : null;
          })()}
        </>
      ) : (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            {/* 4단 스테퍼 바 */}
            <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {STEPS.map((s, i) => {
                const active = i === step;
                const visited = i <= maxVisited;
                return (
                  <li key={s.key}>
                    <button
                      type="button"
                      disabled={
                        running ||
                        (!visited && i > maxVisited + 1) ||
                        (i > 0 && !siteReady)
                      }
                      onClick={() => goTo(i)}
                      aria-current={active ? "step" : undefined}
                      className={`flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left transition-colors disabled:opacity-50 ${
                        active
                          ? "border-[var(--accent-strong)]/50 bg-[var(--accent-soft)]"
                          : "border-[var(--line)] bg-[var(--surface-soft)] hover:border-[var(--accent-strong)]/40"
                      }`}
                    >
                      <span
                        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-black ${
                          active
                            ? "bg-[var(--accent-strong)] text-white"
                            : "border border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]"
                        }`}
                      >
                        {i + 1}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-bold text-[var(--text-primary)]">
                          {s.label}
                        </span>
                        <span className="block truncate text-[10px] text-[var(--text-hint)]">
                          {s.desc}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>

            {/* ── 단계 본문 ── */}
            <div className="mt-5">
              {/* ⑴ 부지 */}
              {step === 0 && (
                <div className="grid gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    {(
                      [
                        ["project", "프로젝트 부지 사용"],
                        ["manual", "주소 직접 입력"],
                      ] as const
                    ).map(([v, label]) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => {
                          modeTouched.current = true;
                          setSiteMode(v);
                        }}
                        className={`rounded-lg px-3 py-1.5 text-[11px] font-bold ${
                          siteMode === v
                            ? "bg-[var(--accent-strong)] text-white"
                            : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)]"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>

                  {siteMode === "project" ? (
                    projectId && siteAnalysis ? (
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                        <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--accent-strong)]">
                          <Folder className="size-3.5" aria-hidden />{projectName || "활성 프로젝트"} — 부지분석 데이터(읽기 전용)
                        </p>
                        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                          {(
                            [
                              ["주소", siteAnalysis.address || "—"],
                              // ★SSOT 리더 — 다필지 통합 대표(우세) 용도지역 우선(직독 대신 단일 계약).
                              ["용도지역", resolveDominantZone(siteAnalysis) || "—"],
                              [
                                "대지면적",
                                (() => {
                                  // ★다필지면 통합 면적 표시(대표값 표시로 인한 혼동 방지).
                                  const a = effectiveLandAreaSqm(siteAnalysis);
                                  return a != null && a > 0
                                    ? `${Math.round(a).toLocaleString()}㎡`
                                    : "—";
                                })(),
                              ],
                              ["PNU", siteAnalysis.pnu || "—"],
                            ] as const
                          ).map(([k, v]) => (
                            <div
                              key={k}
                              className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-2.5"
                            >
                              <p className="text-[10px] text-[var(--text-tertiary)]">{k}</p>
                              <p
                                className="mt-0.5 truncate text-xs font-bold text-[var(--text-primary)]"
                                title={String(v)}
                              >
                                {v}
                              </p>
                            </div>
                          ))}
                        </div>
                        <p className="mt-2 text-[11px] text-[var(--text-hint)]">
                          ※ 부지분석 값은 읽기 전용으로 사용되며, 이 화면에서 수정되지 않습니다.
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/[0.06] p-4 text-xs text-[var(--status-warning)]">
                        활성 프로젝트가 없습니다 —{" "}
                        <Link
                          href={`/${locale}/projects`}
                          className="font-bold underline underline-offset-2"
                        >
                          프로젝트 관리
                        </Link>
                        에서 프로젝트를 선택하거나, 위에서 &quot;주소 직접 입력&quot;으로 전환하세요.
                      </div>
                    )
                  ) : (
                    <div className="grid gap-2 sm:grid-cols-[2fr_1fr]">
                      <div>
                        <span className="block text-[11px] font-semibold text-[var(--text-tertiary)]">
                          대지 주소
                        </span>
                        <input
                          value={manualAddress}
                          onChange={(e) => setManualAddress(e.target.value)}
                          placeholder="예: 서울특별시 강남구 역삼동 736-1"
                          className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                        />
                      </div>
                      <div>
                        <span className="block text-[11px] font-semibold text-[var(--text-tertiary)]">
                          대지면적 ㎡ (선택)
                        </span>
                        <input
                          value={manualAreaSqm}
                          onChange={(e) => setManualAreaSqm(e.target.value)}
                          inputMode="decimal"
                          placeholder="예: 1250"
                          className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ⑵ 개요 */}
              {step === 1 && (
                <div className="grid gap-4">
                  <BriefUploadStep
                    disabled={running}
                    onExtracted={(extracted, meta) => {
                      setFields(extracted);
                      setBriefId(meta.briefId);
                      setBriefNote(meta.message);
                      setSeededFromDesign(false); // 추출값이 설계 시드를 대체 — 시드 안내 문구 해제
                    }}
                  />
                  {seededFromDesign && fields.length > 0 && (
                    <p className="rounded-lg border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
                      설계 스튜디오에서 산출된 매스 값(층수·연면적·건폐/용적률 등)을 개요에 불러왔습니다.
                      값을 확인·수정하거나, 위에서 개요 문서를 업로드하면 추출값으로 대체됩니다.
                    </p>
                  )}
                  {briefNote?.trim() && (
                    <p className="text-[11px] text-[var(--text-hint)]">{briefNote.trim()}</p>
                  )}
                  <ParamConfirmStep
                    fields={fields}
                    disabled={running}
                    onChange={handleFieldChange}
                  />
                </div>
              )}

              {/* ⑶ 도면 */}
              {step === 2 && (
                <div className="grid gap-3 md:grid-cols-2">
                  {/* IFC 업로드 슬롯 */}
                  <div className="rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
                    <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
                      <Boxes className="size-4" aria-hidden />BIM 모델 (IFC) <span className="font-normal text-[var(--text-hint)]">— 선택</span>
                    </p>
                    <p className="mt-1 text-[11px] text-[var(--text-hint)]">
                      IFC를 첨부하면 도면 기반 수치(층고·면적·코어 등)까지 심사 범위가 넓어집니다.
                      미첨부 시 개요·부지 기반 항목만 심사합니다.
                    </p>
                    <input
                      ref={ifcRef}
                      type="file"
                      accept=".ifc"
                      className="hidden"
                      disabled={running}
                      onChange={(e) => handleIfcPick(e.target.files?.[0] ?? null)}
                    />
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => ifcRef.current?.click()}
                        disabled={running}
                        className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
                      >
                        IFC 파일 선택
                      </button>
                      {ifcFile && (
                        <span className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                          <span
                            className="max-w-[200px] truncate font-semibold text-[var(--text-primary)]"
                            title={ifcFile.name}
                          >
                            {ifcFile.name}
                          </span>
                          <span className="text-[var(--text-hint)]">
                            {(ifcFile.size / 1024 / 1024).toFixed(1)}MB
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setIfcFile(null);
                              if (ifcRef.current) ifcRef.current.value = "";
                            }}
                            disabled={running}
                            title="첨부 제거"
                            className="text-[var(--status-error)] disabled:opacity-50"
                          >
                            ✕
                          </button>
                        </span>
                      )}
                    </div>
                    {ifcError && (
                      <p className="mt-2 text-[11px] font-semibold text-[var(--status-error)]">
                        {ifcError}
                      </p>
                    )}
                  </div>

                  {/* DXF 업로드 슬롯 — CAD 2.0 편집본 DXF 호환(.dxf · 최대 20MB) */}
                  <div className="rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
                    <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
                      <DraftingCompass className="size-4" aria-hidden />CAD 도면 (DXF) <span className="font-normal text-[var(--text-hint)]">— 선택</span>
                    </p>
                    <p className="mt-1 text-[11px] text-[var(--text-hint)]">
                      DXF를 첨부하면 도면 파일이 심사 요청에 함께 전송됩니다(.dxf · 최대 20MB).
                      CAD 2.0의 &quot;편집본 DXF&quot; 내보내기 파일을 그대로 첨부할 수 있습니다.
                    </p>
                    <input
                      ref={dxfRef}
                      type="file"
                      accept=".dxf"
                      className="hidden"
                      disabled={running}
                      onChange={(e) => handleDxfPick(e.target.files?.[0] ?? null)}
                    />
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => dxfRef.current?.click()}
                        disabled={running}
                        className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
                      >
                        DXF 파일 선택
                      </button>
                      {dxfFile && (
                        <span className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                          <span
                            className="max-w-[200px] truncate font-semibold text-[var(--text-primary)]"
                            title={dxfFile.name}
                          >
                            {dxfFile.name}
                          </span>
                          <span className="text-[var(--text-hint)]">
                            {(dxfFile.size / 1024 / 1024).toFixed(1)}MB
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setDxfFile(null);
                              if (dxfRef.current) dxfRef.current.value = "";
                            }}
                            disabled={running}
                            title="첨부 제거"
                            className="text-[var(--status-error)] disabled:opacity-50"
                          >
                            ✕
                          </button>
                        </span>
                      )}
                    </div>
                    {dxfError && (
                      <p className="mt-2 text-[11px] font-semibold text-[var(--status-error)]">
                        {dxfError}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* ⑷ 실행 */}
              {step === 3 &&
                (running ? (
                  /* 로딩 — 정직 표기: 실제 진행률을 알 수 없으므로 '진행 중' 단일 상태 + 실제 경과 시간만
                     표시한다. 아래 목록은 '이 심사가 점검하는 항목'을 나열만 한 것(순차 완료 연출 아님). */
                  <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]">
                        <Settings className="size-4 animate-spin" aria-hidden />AI 심사 진행 중…
                      </p>
                      <span
                        className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-strong)] px-2.5 py-1 font-mono text-[11px] font-bold tabular-nums text-[var(--text-secondary)]"
                        title="실행 시작 후 실제 경과 시간"
                      >
                        경과 {formatElapsed(elapsedSec)}
                      </span>
                    </div>
                    <p className="mt-3 text-[11px] font-semibold text-[var(--text-secondary)]">
                      이 심사가 점검하는 항목
                    </p>
                    <ul className="mt-1.5 grid gap-1.5 sm:grid-cols-2">
                      {ENGINE_STEPS.map((label) => (
                        <li
                          key={label}
                          className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]"
                        >
                          <span
                            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--line-strong)]"
                            aria-hidden
                          />
                          <span>{label}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-3 text-[11px] text-[var(--text-hint)]">
                      예상 소요 3~5분입니다. 단계별 진행률은 실제 진행과 다를 수 있어 표시하지 않으며(정직하게
                      생략), 서버 심사가 끝나면 결과 보고서로 자동 전환됩니다. 심사는 서버에서 계속 진행되므로
                      탭을 닫거나 새로고침해도 안전합니다 — 다시 열면 진행 상황을 이어서 확인합니다.
                    </p>
                  </div>
                ) : (
                  <div className="grid gap-3">
                    {/* 입력 요약 */}
                    <div className="grid gap-2 sm:grid-cols-3">
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                          ① 부지
                        </p>
                        <p
                          className="mt-1 truncate text-xs font-bold text-[var(--text-primary)]"
                          title={site.address || undefined}
                        >
                          {site.address || "미입력"}
                        </p>
                        <p className="text-[10px] text-[var(--text-hint)]">
                          {usingProject ? `프로젝트 연동 (${projectName || projectId})` : "직접 입력"}
                          {site.landAreaSqm
                            ? ` · ${Math.round(site.landAreaSqm).toLocaleString()}㎡`
                            : ""}
                        </p>
                      </div>
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                          ② 개요
                        </p>
                        <p className="mt-1 text-xs font-bold text-[var(--text-primary)]">
                          {fields.length > 0 ? `${fields.length}개 필드` : "개요 없음"}
                        </p>
                        <p className="text-[10px] text-[var(--text-hint)]">
                          {fields.length > 0
                            ? `추출 ${extractedCount} · 수동 ${userCount}`
                            : "개요 기반 검증 항목 제한"}
                        </p>
                      </div>
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                          ③ 도면
                        </p>
                        <p
                          className="mt-1 truncate text-xs font-bold text-[var(--text-primary)]"
                          title={[ifcFile?.name, dxfFile?.name].filter(Boolean).join(" · ") || undefined}
                        >
                          {ifcFile || dxfFile
                            ? [ifcFile?.name, dxfFile?.name].filter(Boolean).join(" · ")
                            : "도면 미첨부"}
                        </p>
                        <p className="text-[10px] text-[var(--text-hint)]">
                          {ifcFile ? "도면 기반 항목 포함" : "개요·부지 기반 항목만"}
                          {dxfFile ? " · DXF 동봉" : ""}
                        </p>
                      </div>
                    </div>

                    {/* AI 보조(사각지대 쟁점 생성) 옵트인 — 기본 on(기존 동작 보존). 끄면 규칙기반 심사만. */}
                    <UseLlmToggle
                      checked={useLlm}
                      onChange={setUseLlm}
                      className="mb-3 flex w-fit cursor-pointer items-center gap-2 text-[11px] text-[var(--text-secondary)]"
                    />
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => void runAudit()}
                        disabled={!siteReady}
                        title={!siteReady ? "1단계에서 부지(주소)를 먼저 입력하세요." : undefined}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--accent-strong)] px-6 py-2.5 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
                      >
                        <Construction className="size-4" aria-hidden />AI 설계분석 실행
                      </button>
                      {!siteReady && (
                        <span className="text-xs text-[var(--text-hint)]">
                          부지(주소) 입력 후 실행할 수 있습니다.
                        </span>
                      )}
                      {runError && (
                        <span className="text-xs font-semibold text-[var(--status-error)]">
                          {runError}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
            </div>

            {/* 이전/다음 네비게이션 */}
            <div className="mt-5 flex items-center justify-between border-t border-[var(--line)] pt-4">
              <button
                type="button"
                onClick={() => goTo(step - 1)}
                disabled={step === 0 || running}
                className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-40"
              >
                ← 이전
              </button>
              {step < STEPS.length - 1 ? (
                <button
                  type="button"
                  onClick={() => goTo(step + 1)}
                  disabled={running || (step === 0 && !siteReady)}
                  title={
                    step === 0 && !siteReady
                      ? "프로젝트를 선택하거나 주소를 입력해야 다음으로 진행합니다."
                      : undefined
                  }
                  className="rounded-xl bg-[var(--accent-strong)] px-5 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
                >
                  다음 →
                </button>
              ) : (
                <span className="text-[11px] text-[var(--text-hint)]">
                  실행 결과는 이 자리에서 보고서로 전환됩니다.
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
