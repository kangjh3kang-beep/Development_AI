"use client";

/**
 * DesignAuditWorkspace — 설계안 AI 심사(DA-7) 4단 스테퍼 워크스페이스.
 *
 *  ⑴ 부지: 활성 프로젝트 부지(useProjectContextStore.siteAnalysis) **읽기 전용** 사용
 *          또는 주소 직접 입력(로컬 state) — 이 화면은 컨텍스트 스토어를 절대 수정하지 않는다.
 *  ⑵ 개요: BriefUploadStep(PDF/텍스트 → POST /design-audit/extract-brief)
 *          + ParamConfirmStep(필드 그리드 — '추출'/'수동' 출처 배지·quote 툴팁·수정).
 *  ⑶ 도면: IFC 업로드 슬롯 + DXF 업로드 슬롯(.dxf · 20MB — CAD 2.0 내보내기 호환).
 *  ⑷ 실행: POST /design-audit/run(multipart: payload JSON + ifc_file? + dxf_file?) →
 *          로딩 중 엔진 체크리스트(예상 진행 표시) → AuditReportView 전환.
 *
 * 정직성 원칙: 빈 결과·서버 오류는 메시지 그대로 노출, 가짜값·임의 링크 생성 금지.
 * apiClient v1 패턴 + 디자인 토큰(CSS 변수)만 사용.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Boxes, CheckCircle2, Construction, DraftingCompass, Folder, Settings } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
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

/* ── 스테퍼 정의 ── */

const STEPS = [
  { key: "site", label: "부지", desc: "프로젝트 선택 또는 주소" },
  { key: "brief", label: "개요", desc: "건축개요 업로드·확인" },
  { key: "drawing", label: "도면", desc: "IFC·DXF 첨부(선택)" },
  { key: "run", label: "실행", desc: "AI 심사 실행" },
] as const;

/* ── 실행 로딩 엔진 체크리스트(예상 진행 표시 — 결과 아님) ── */

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
  const [engineIdx, setEngineIdx] = useState(0);

  /* 실행 중 엔진 체크리스트 진행 표시 — 타이머 기반 "예상" 진행(결과 아님, 라벨로 고지). */
  useEffect(() => {
    if (!running) {
      setEngineIdx(0);
      return;
    }
    const timer = setInterval(() => {
      setEngineIdx((prev) => Math.min(prev + 1, ENGINE_STEPS.length - 1));
    }, 2500);
    return () => clearInterval(timer);
  }, [running]);

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
        zoneCode: siteAnalysis?.zoneCode ?? null,
        // ★다필지면 통합 면적 — 심의 면적/도식 footprint가 통합 부지 기준이 되도록.
        landAreaSqm: effectiveLandAreaSqm(siteAnalysis),
      }
    : {
        address: manualAddress.trim(),
        pnu: null,
        zoneCode: null,
        landAreaSqm: manualArea,
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
            zone_code: site.zoneCode || null,
            land_area_sqm: site.landAreaSqm ?? null,
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
        }),
      );
      if (ifcFile) fd.append("ifc_file", ifcFile);
      if (dxfFile) fd.append("dxf_file", dxfFile);
      const r = await apiClient.post<DesignAuditReport>("/design-audit/run-upload", {
        body: fd,
        timeoutMs: 300_000, // 다단계 엔진 심사 — 기본 120s보다 넉넉히(무한대기는 차단)
      });
      if (!r || typeof r !== "object") {
        throw new Error("심사 응답이 비어 있습니다 — 잠시 후 다시 시도하세요.");
      }
      setReport(r);
    } catch (e) {
      setRunError(apiErrorMessage(e, "설계안 심사 실행에 실패했습니다. 잠시 후 다시 시도하세요."));
    } finally {
      setRunning(false);
    }
  }

  /* 추출/수동 필드 수 — 실행 요약 표기 */
  const extractedCount = fields.filter((f) => f.source === "extracted").length;
  const userCount = fields.length - extractedCount;

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
          <AuditReportView report={report} onReset={() => setReport(null)} />
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
                              ["용도지역", siteAnalysis.zoneCode || "—"],
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
                    }}
                  />
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
                  /* 로딩 — 엔진 체크리스트(예상 진행 표시) */
                  <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
                    <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]">
                      <Settings className="size-4 animate-spin" aria-hidden />AI 심사 엔진 실행 중…
                    </p>
                    <ul className="mt-3 grid gap-1.5">
                      {ENGINE_STEPS.map((label, i) => (
                        <li key={label} className="flex items-center gap-2 text-[12px]">
                          {i < engineIdx ? (
                            <CheckCircle2 className="size-3.5 text-[var(--status-success)]" aria-hidden />
                          ) : i === engineIdx ? (
                            <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--accent-strong)]" />
                          ) : (
                            <span className="inline-block h-2.5 w-2.5 rounded-full border border-[var(--line-strong)]" />
                          )}
                          <span
                            className={
                              i <= engineIdx
                                ? "font-semibold text-[var(--text-primary)]"
                                : "text-[var(--text-hint)]"
                            }
                          >
                            {label}
                          </span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-3 text-[11px] text-[var(--text-hint)]">
                      단계 표시는 예상 진행이며, 서버 심사가 끝나면 결과 보고서로 전환됩니다.
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
