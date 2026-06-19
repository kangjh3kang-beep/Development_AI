"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";
import { ImageUpload } from "@/components/ui/ImageUpload";
import { apiClient } from "@/lib/api-client";
import { consumePreCheckHandoff, type PreCheckHandoff } from "@/components/precheck/handoff";

export default function NewProjectPage() {
  const router = useRouter();
  const { locale } = useParams() as { locale: string };
  const addProject = useProjectStore(state => state.addProject);
  const clearProject = useProjectContextStore(state => state.clearProject);
  const setProject = useProjectContextStore(state => state.setProject);
  const updateSiteAnalysis = useProjectContextStore(state => state.updateSiteAnalysis);

  // 새 프로젝트 진입 시 이전 데이터 초기화 후 PreCheck 핸드오프(있으면) 1회 소비 (mount 1회)
  const [handoff] = useState<PreCheckHandoff | null>(() => {
    clearProject();
    const h = consumePreCheckHandoff();
    // PreCheck 결과를 부지분석 컨텍스트에 시드(주소 선택 시 GlobalAddressSearch가 정밀 보강).
    if (h) {
      updateSiteAnalysis({
        address: h.address,
        zoneCode: h.zoneType,
        landAreaSqm: h.areaSqm,
        pnu: h.pnu,
      });
    }
    return h;
  });

  const [name, setName] = useState("");
  const [location, setLocation] = useState(handoff?.address ?? "");
  const [siteImageUrl, setSiteImageUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 주소가 선택되면 GlobalAddressSearch가 /zoning/comprehensive를 호출하여
  // PNU·용도지역·면적·조례 등 부지분석 데이터를 store(siteAnalysis)에 자동 저장한다.
  const handleAddressChange = (entries: AddressEntry[]) => {
    if (entries.length > 0) {
      setLocation(entries[0].fullAddress);
    } else {
      setLocation("");
    }
  };

  const handleSubmit = async () => {
    if (!name.trim() || !location.trim()) return;
    setIsSubmitting(true);

    // ★항상 '최신' siteAnalysis를 읽는다. 다필지 보강(enrichParcels)은 비동기라, 제출 직전 막
    //   완료된 통합 면적(landAreaSqm=Σ, landAreaSqmTotal)이 여기 반영돼 있어야 신규 프로젝트로
    //   정확히 승계된다(대표 1필지 면적이 통합을 덮던 근본버그 방지).
    const currentSiteAnalysis = useProjectContextStore.getState().siteAnalysis;
    let projectId = "";

    // store 저장은 localStorage 용량초과(QuotaExceededError) 등으로 실패할 수 있으나
    // 그래도 프로젝트 생성·이동은 반드시 진행되도록 각 단계를 개별 try로 격리한다.
    try {
      projectId = addProject({
        name,
        address: location,
        pnu: currentSiteAnalysis?.pnu ?? "",
        area: currentSiteAnalysis?.landAreaSqm ? String(currentSiteAnalysis.landAreaSqm) : "0",
        type: "mixed",
        siteImageUrl: siteImageUrl || undefined,
        // 다필지 통합 분석으로 생성된 경우 필지 수 캡처(대표지번 외 N필지 표기용).
        // enrichParcels가 기록하는 통합 메타(parcelCount)를 우선 사용 — parcels 배열은
        // 다필지 보강 경로에서 채워지지 않으므로(통합은 landAreaSqmTotal/parcelCount로 기록)
        // parcels?.length만 보면 항상 미설정이라 "외 N필지" 표기가 누락되던 결함을 함께 해소.
        parcelCount:
          (currentSiteAnalysis?.parcelCount && currentSiteAnalysis.parcelCount > 1
            ? currentSiteAnalysis.parcelCount
            : currentSiteAnalysis?.parcels?.length) || undefined,
      });
    } catch (err) {
      console.error("프로젝트 저장 경고(이동은 계속):", err);
    }

    // 서비스 사용료: 프로젝트 생성 1건 차감(로그인 구독자, best-effort — 실패해도 진행)
    try {
      await apiClient.post("/billing/charge", { body: { action: "project_create" }, useMock: false });
    } catch { /* 비로그인/실패 무시 */ }

    // 백엔드 영속화: 실제 projects row 생성 → 파이프라인 메타데이터(GET /projects/{id}) 로드 가능.
    // 부지분석 면적을 시드로 전달(점진 강화의 출발점). best-effort — 실패해도 로컬 ID로 진행.
    let backendId = "";
    try {
      const areaNum = currentSiteAnalysis?.landAreaSqm ? Number(currentSiteAnalysis.landAreaSqm) : 0;
      const res = await apiClient.post<{ id: string }>("/projects", {
        body: { name, address: location || undefined, ...(areaNum > 0 ? { total_area_sqm: areaNum } : {}) },
        useMock: false,
      });
      backendId = res?.id || "";
    } catch (err) {
      console.error("백엔드 프로젝트 생성 경고(로컬로 진행):", err);
    }
    const targetId = backendId || projectId || `tmp-${Date.now()}`;

    try {
      // ★setProject(신규 id)는 cross-module을 INITIAL로 리셋하므로, 전환 '직전'의 최신
      //   siteAnalysis(통합 면적·용도지역 등 다필지 보강 결과 포함)를 캡처해 전환 후 재시드한다.
      //   (전환 시 통합 분석이 통째로 비워지고 대표 1필지만 남던 근본버그의 직접 방지선.)
      const latestSite = useProjectContextStore.getState().siteAnalysis ?? currentSiteAnalysis;
      // address를 함께 넘겨 신규 프로젝트 시드 주소가 비지 않게 한다(빈 시드 → null 잔류 방지).
      setProject(targetId, name, "draft", location);
      const restored = latestSite ?? {
        estimatedValue: null, landAreaSqm: null, zoneCode: null, address: location, pnu: null,
      };
      if (!restored.address) restored.address = location;
      // 통합 면적(landAreaSqm=Σ·landAreaSqmTotal·parcelCount 등 다필지 메타 포함)을 그대로 재시드.
      useProjectContextStore.getState().updateSiteAnalysis(restored);
    } catch (err) {
      console.error("컨텍스트 저장 경고(이동은 계속):", err);
    }

    // 이동: 백엔드 UUID 우선(targetId는 위에서 계산). 실패 시 로컬/임시 ID로 진입.
    try {
      router.push(`/${locale}/projects/${targetId}`);
    } catch (err) {
      console.error("이동 실패:", err);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-10 pb-20 max-w-3xl mx-auto mt-4">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <span className="cc-meta">NEW PROJECT · INTAKE CONSOLE</span>
          <span className="cc-live"><i />READY</span>
        </div>
        <h1 className="text-4xl font-[900] tracking-tighter text-[var(--text-primary)]">
          새 프로젝트 <span className="text-[var(--accent-strong)]">_</span>
        </h1>
        <p className="text-[var(--text-secondary)] font-medium">
          프로젝트명과 주소만 입력하면 됩니다. 주소를 선택하는 즉시 AI 부지분석이 시작되며,
          이어서 최적 사업모델을 추천합니다.
        </p>
      </div>

      {/* ── 단일 입력 콘솔 ── */}
      <section className="cc-bracketed cc-panel transition-all focus-within:border-[var(--accent-strong)]/50 focus-within:shadow-[var(--shadow-lg),var(--data-glow)]">
        <div className="cc-grid-bg opacity-40" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <header className="cc-panel__head relative z-10">
          <div className="flex items-center gap-3">
            <span className="cc-chip-data">STEP 01</span>
            <span className="cc-label">프로젝트 메타데이터</span>
          </div>
        </header>
        <div className="relative z-10 cc-panel__body space-y-6">
          <div className="grid gap-2">
            <label className="cc-label">프로젝트 명칭</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 성수 IT밸리 복합개발"
              className="w-full rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-4 px-5 text-sm font-bold placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/30 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)] relative z-10"
            />
          </div>

          <div className="grid gap-2 relative z-10">
            <label className="cc-label">소재지 (주소 검색)</label>
            <GlobalAddressSearch
              onChange={handleAddressChange}
              initialAddress={handoff?.address}
              placeholder="주소를 검색하세요 (다필지 입력 가능)"
            />
            <p className="text-[11px] font-medium text-[var(--text-hint)] mt-1">
              주소를 선택하면 용도지역·대지면적·공시지가·지자체 조례를 자동 조회합니다.
            </p>
            {handoff && (
              <p className="mt-1 inline-flex w-fit items-center gap-1.5 rounded-lg border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-2.5 py-1 text-[11px] font-semibold text-[var(--accent-strong)]">
                ✦ 90초 PreCheck 결과 승계됨
                {handoff.zoneType ? ` · ${handoff.zoneType}` : ""}
                {handoff.bestMethodName ? ` · 추천 ${handoff.bestMethodName}` : ""}
              </p>
            )}
          </div>

          <div className="grid gap-2 mt-4 relative z-10">
            <label className="cc-label">현장(부지) 이미지 등록</label>
            <ImageUpload 
              value={siteImageUrl}
              onChange={setSiteImageUrl}
              label="클릭하거나 현장 사진을 드래그하여 업로드하세요"
            />
          </div>
        </div>
      </section>

      {/* ── 요약 + 시작 ── */}
      <section className="cc-bracketed cc-panel">
        <div className="cc-grid-bg cc-grid-bg--radial opacity-40" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <header className="cc-panel__head relative z-10">
          <div className="flex items-center gap-3">
            <span className="cc-chip-data">STEP 02</span>
            <span className="cc-label">분석 시작</span>
          </div>
          <span className="cc-live"><i />{isSubmitting ? "RUNNING" : "STANDBY"}</span>
        </header>
        <div className="relative z-10 cc-panel__body">

        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm">
              <span className="cc-label w-16">프로젝트</span>
              <span className="text-[var(--text-primary)] font-bold truncate max-w-[280px]">{name || "-"}</span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <span className="cc-label w-16">위치</span>
              <span className="text-[var(--text-primary)] font-bold truncate max-w-[280px]">{location || "-"}</span>
            </div>
          </div>

          <button
            onClick={handleSubmit}
            disabled={!name.trim() || !location.trim() || isSubmitting}
            className="w-full sm:w-auto relative overflow-hidden rounded-2xl py-4 px-10 text-sm font-black transition-all shadow-[var(--shadow-md)] flex items-center justify-center gap-2
            cursor-pointer disabled:cursor-not-allowed
            bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] text-white hover:shadow-[0_0_20px_rgba(45,212,191,0.4)] hover:-translate-y-0.5
            disabled:from-[var(--surface-tertiary)] disabled:to-[var(--surface-tertiary)] disabled:text-[var(--text-secondary)] disabled:shadow-none"
          >
            {isSubmitting ? (
              <>
                <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                분석 시작 중...
              </>
            ) : (
              "프로젝트 시작 →"
            )}
          </button>
        </div>

        <div className="mt-6 pt-6 border-t border-[var(--line)] flex items-start gap-3 text-[var(--text-hint)]">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
          <p className="text-xs leading-relaxed font-medium">
            프로젝트가 생성되면 부지분석이 자동으로 진행되고, 결과를 확인한 뒤 최적 사업모델 Top 3 추천으로 이어집니다.
            용도·활성 모듈은 분석 과정에서 자동으로 결정됩니다.
          </p>
        </div>
        </div>
      </section>
    </div>
  );
}
