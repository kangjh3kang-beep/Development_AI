"use client";

/**
 * 프로젝트 주소 입력 바 — 전 모듈 공통.
 *
 * 1) 이전에 분석한 프로젝트를 선택해 주소를 불러와 "이어서 분석" (프로젝트 연동)
 * 2) 카카오 주소 검색(GlobalAddressSearch)으로 신규/변경 입력
 * 3) 프로젝트 생성 시 입력한 주소(ProjectContextStore.siteAnalysis.address)를 자동 로드
 *
 * 각 워크스페이스의 일반 텍스트 주소 입력(<Input value={form.address} />)을
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
}

export function ProjectAddressInput({
  value,
  onChange,
  label = "대지 주소",
  placeholder = "주소를 검색하세요",
  className = "",
  disabled = false,
  hideProjectPicker = false,
}: ProjectAddressInputProps) {
  const projects = useProjectStore((s) => s.projects);
  const setProject = useProjectContextStore((s) => s.setProject);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const ctxAddress = useProjectContextStore((s) => s.siteAnalysis?.address);
  const ctxProjectId = useProjectContextStore((s) => s.projectId);

  // 프로젝트 생성/직전 분석에서 입력한 주소를 자동 반영 (호스트 값이 비어있을 때만)
  useEffect(() => {
    if (!value && ctxAddress) {
      onChange(ctxAddress);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctxAddress]);

  // 이전 프로젝트 선택 → 컨텍스트 전환 + 주소 로드 (이어서 분석)
  const handleSelectProject = (id: string) => {
    if (!id) return;
    const p = projects.find((x) => x.id === id);
    if (!p) return;
    setProject(p.id, p.name, p.status);
    updateSiteAnalysis({ address: p.address, pnu: p.pnu || null });
    onChange(p.address);
  };

  const handleAddressChange = (entries: AddressEntry[]) => {
    onChange(entries.length > 0 ? entries[0].fullAddress : "");
  };

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
          {label}
        </span>
        {!hideProjectPicker && projects.length > 0 && (
          <select
            value={ctxProjectId ?? ""}
            disabled={disabled}
            onChange={(e) => handleSelectProject(e.target.value)}
            className="max-w-[55%] truncate rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] focus:outline-none focus:border-[var(--accent-strong)] disabled:opacity-50"
            title="이전에 분석한 프로젝트를 선택해 이어서 분석"
          >
            <option value="">분석한 프로젝트 불러오기…</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}{p.address ? ` — ${p.address}` : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* key={value}로 프로젝트 선택/자동로드 시 GlobalAddressSearch를 재마운트해
          initialAddress(최초 1회만 반영)를 갱신한다. */}
      <GlobalAddressSearch
        key={value || "empty"}
        single
        initialAddress={value || undefined}
        placeholder={placeholder}
        disabled={disabled}
        onChange={handleAddressChange}
      />
    </div>
  );
}
