"use client";

/**
 * 프로젝트 주소 입력 바 — 전 모듈 공통.
 *
 * 1) 이전에 분석한 프로젝트를 선택해 주소를 불러와 "이어서 분석" (프로젝트 연동)
 * 2) 카카오 주소 검색(GlobalAddressSearch)으로 신규/변경 입력
 * 3) 프로젝트 생성 시 입력한 주소(ProjectContextStore.siteAnalysis.address)를 자동 로드
 *
 * 각 작업 공간의 일반 텍스트 주소 입력(<Input value={form.address} />)을
 * 이 컴포넌트로 일괄 대체하여 주소 입력 UX를 단일화한다.
 */

import { useEffect } from "react";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

interface ProjectAddressInputProps {
  /** 현재 주소 값 (호스트 폼 state) */
  value: string;
  /** 주소 확정/변경 시 호출 */
  onChange: (address: string) => void;
  /** 라벨 (기본: 대지 주소) */
  label?: string;
  /** 검색창 placeholder */
  placeholder?: string;
  /** 추가 CSS */
  className?: string;
  /** 비활성화 */
  disabled?: boolean;
  /** 프로젝트 선택 드롭다운 숨김 (기본 표시) */
  hideProjectPicker?: boolean;
  /** 프로젝트 선택 드롭다운 앞 라벨 (기본 없음) */
  pickerLabel?: string;
  /**
   * (호환용) 과거 multi 옵트인 prop — 현재는 전 플랫폼이 항상 다필지 UI라 무시된다.
   */
  multi?: boolean;
  /** 다필지 목록 변경 콜백 — 등록된 전 필지 주소 배열 전달(옵션) */
  onParcelsChange?: (addresses: string[]) => void;
  /**
   * ProjectContextStore(SSOT) 기록 여부 — 기본 true(프로젝트 주소바는 primary를 store에 기록).
   * 활성 프로젝트와 무관한 탐색용이면 false로 끌 수 있다.
   */
  writeToContext?: boolean;
}

export function ProjectAddressInput({
  value,
  onChange,
  label = "대지 주소",
  placeholder = "주소를 검색하세요",
  className = "",
  disabled = false,
  hideProjectPicker = false,
  pickerLabel,
  multi: _multi,
  onParcelsChange,
  writeToContext = true,
}: ProjectAddressInputProps) {
  void _multi; // 호환용(무시) — 항상 다필지 UI
  const projects = useProjectStore((s) => s.projects);
  const snapshots = useProjectContextStore((s) => s.snapshots);
  const setProject = useProjectContextStore((s) => s.setProject);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const ctxAddress = useProjectContextStore((s) => s.siteAnalysis?.address);
  const ctxProjectId = useProjectContextStore((s) => s.projectId);

  // 드롭다운은 "분석을 실행한" 프로젝트만 노출(단순 생성/약식 검색 제외).
  // 분석 신호: status가 draft가 아니거나, 컨텍스트 스냅샷에 완료 단계가 기록됨.
  // (아직 분석된 게 하나도 없으면 로더 기능 보존을 위해 전체 노출)
  const analyzedProjects = projects.filter(
    (p) => p.status !== "draft" || (snapshots?.[p.id]?.completedStages?.length ?? 0) > 0,
  );
  const pickerProjects = analyzedProjects.length > 0 ? analyzedProjects : projects;

  // 활성 프로젝트가 있을 때만 컨텍스트 주소를 자동 반영.
  // (약식 검색 결과가 모든 페이지의 주소 필드로 새는 것을 차단 — 프로젝트 분석본만 전파)
  useEffect(() => {
    if (!value && ctxAddress && ctxProjectId) {
      onChange(ctxAddress);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctxAddress, ctxProjectId]);

  // 이전 프로젝트 선택 → 컨텍스트 전환 + 분석 복원 (이어서 분석)
  const handleSelectProject = (id: string) => {
    if (!id) return;
    const p = projects.find((x) => x.id === id);
    if (!p) return;
    // setProject가 해당 프로젝트의 이전 분석 스냅샷을 복원한다.
    setProject(p.id, p.name, p.status);
    // 스냅샷이 없거나(미분석) 비어 있는 항목은 프로젝트 레코드 값으로 보강.
    const areaNum = p.area ? Number(String(p.area).replace(/[^0-9.]/g, "")) : null;
    updateSiteAnalysis({
      address: p.address,
      pnu: p.pnu || null,
      ...(areaNum && areaNum > 0 ? { landAreaSqm: areaNum } : {}),
    });
    onChange(p.address);
  };

  const handleAddressChange = (entries: AddressEntry[]) => {
    const primary = entries.length > 0
      ? (entries[0].jibunAddress || entries[0].fullAddress || entries[0].roadAddress)
      : "";
    onChange(primary);
    // 다필지: 등록된 전 필지 주소 배열을 호스트로 전달(호스트가 쓰면 활용).
    const all = entries
      .map((e) => e.jibunAddress || e.fullAddress || e.roadAddress)
      .filter(Boolean);
    onParcelsChange?.(all);
  };

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
          {label}
        </span>
        {!hideProjectPicker && pickerProjects.length > 0 && (
          <div className="flex max-w-[60%] items-center gap-2">
            {pickerLabel && (
              <span className="shrink-0 text-[11px] font-bold text-[var(--text-tertiary)]">{pickerLabel}</span>
            )}
          <select
            value={ctxProjectId ?? ""}
            disabled={disabled}
            onChange={(e) => handleSelectProject(e.target.value)}
            className="min-w-0 flex-1 truncate rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] focus:outline-none focus:border-[var(--accent-strong)] disabled:opacity-50"
            title="이전에 분석한 프로젝트를 선택해 이어서 분석"
          >
            <option value="">분석한 프로젝트 불러오기…</option>
            {pickerProjects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}{p.address ? ` — ${p.address}` : ""}
              </option>
            ))}
          </select>
          </div>
        )}
      </div>

      {/* single 모드: key={value}로 프로젝트 선택/자동로드 시 재마운트해 initialAddress 갱신.
          multi 모드: 안정 key로 유지(값 변경에 필지 목록이 초기화되지 않도록). */}
      {/* 전 플랫폼 공통: 항상 다필지 UI(검색 추가 + 엑셀 일괄등록).
          key는 프로젝트 전환 시에만 재마운트(편집 중 필지 목록 유지),
          writeToContext=true로 primary 주소를 store(SSOT)에 기록(단일 동작 보존). */}
      <GlobalAddressSearch
        key={ctxProjectId || "addr"}
        single={false}
        initialAddress={value || undefined}
        placeholder={placeholder}
        disabled={disabled}
        writeToContext={writeToContext}
        onChange={handleAddressChange}
      />
    </div>
  );
}
