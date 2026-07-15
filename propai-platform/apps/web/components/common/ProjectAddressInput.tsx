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
import { parcelAddressList, preferredEntryAddress } from "@/lib/parcel-rows";
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
   * 다필지 상세 변경 콜백 — 면적·용도지역·용적/건폐 등 전체 AddressEntry 배열 전달(옵션).
   * 호스트가 통합면적 집계·대표 pnu/좌표 확정 등 SSOT 단일화에 사용한다(onParcelsChange의 상세판).
   */
  onEntriesChange?: (entries: AddressEntry[]) => void;
  /**
   * ProjectContextStore(SSOT) 기록 여부 — 기본 true(프로젝트 주소바는 primary를 store에 기록).
   * 활성 프로젝트와 무관한 탐색용이면 false로 끌 수 있다.
   */
  writeToContext?: boolean;
  /** 단일 필지 검색 모드 여부 (지도가 숨겨지고 심플 텍스트 인풋만 표시) */
  single?: boolean;
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
  onEntriesChange,
  writeToContext = true,
  single = false,
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
    // setProject가 해당 프로젝트의 이전 분석 스냅샷을 복원한다(동기 set — 직후 getState로 읽을 수 있다).
    setProject(p.id, p.name, p.status);

    // 스냅샷이 없거나(미분석) 비어 있는 항목**만** 프로젝트 레코드 값으로 보강한다.
    //
    // ★이 가드가 없으면(종전 코드) 복원 스냅샷의 정확한 면적을 프로젝트 레코드 p.area 로 무조건
    //   덮어써 면적이 갈라진다 — 실측된 상도동 사례: 스냅샷 landAreaSqmTotal=3,059(정답)인데
    //   p.area=11,465(대지지분 미적용 원면적 합계 = 11,229+236)가 landAreaSqm 에만 기록돼
    //   landAreaSqm(11,465) ≠ landAreaSqmTotal(3,059) 분기가 발생했다. 그 결과 effectiveLandAreaSqm
    //   을 쓰는 ContextHeader 는 3,059 를, raw 를 읽는 표면은 11,465 를 보여줬다(같은 화면 두 숫자).
    //   게다가 이 값은 scheduleSnapshotSync 로 서버 스냅샷에까지 영속된다.
    //   ※두 필드에 독립 writer 가 있는 게 구조적 원인이다(여기는 landAreaSqm 단독,
    //     ProjectAnalysisSummary 는 landAreaSqmTotal 단독). 아래처럼 '빈 값일 때만' 쓰면
    //     이미 확보된 분석 결과를 레코드 값이 침범하지 못한다.
    const restoredSA = useProjectContextStore.getState().siteAnalysis;
    const areaNum = p.area ? Number(String(p.area).replace(/[^0-9.]/g, "")) : null;
    const shouldSeedArea =
      areaNum != null && areaNum > 0 && (restoredSA?.landAreaSqm ?? null) == null;
    updateSiteAnalysis({
      address: p.address,
      // pnu 도 빈 값으로 복원값을 지우지 않는다(p.pnu 미보유 프로젝트에서 || null 이 클로버함).
      ...(p.pnu ? { pnu: p.pnu } : {}),
      ...(shouldSeedArea ? { landAreaSqm: areaNum } : {}),
    });

    // ★다필지 하이드레이션 — 복원된 스냅샷의 전 필지를 호스트로 전파한다.
    //
    // 이게 없으면: 사통맵에서 5필지로 등록한 프로젝트를 골라도 호스트는 대표주소 1개만 받아
    // 화면(인테이크 목록·구획도·통합 종합분석)이 1필지로 렌더된다. 반면 ContextHeader 는
    // store 의 sa.parcelCount 를 직접 읽어 "통합 5필지"를 표시하므로 같은 화면에서 숫자가 갈린다.
    // 더 위험한 것은 규모 판정이다 — 1필지(446평)와 통합(925평)은 권고 개발방식 자체가 달라진다.
    // (satong-map-selection.ts 가 parcelCount 와 parcels[] 를 함께 기록하므로 배열은 권위 출처다.)
    const restored = useProjectContextStore.getState().siteAnalysis;
    const restoredAddrs = parcelAddressList(restored?.parcels);
    // 대표주소를 항상 선두에 고정하고 중복 제거(호스트 계약: all[0]=대표, 나머지=추가필지).
    const all = [p.address, ...restoredAddrs.filter((a) => a && a !== p.address)].filter(Boolean);
    onChange(p.address);
    // ★단일필지여도 **반드시** 호출한다 — 호출을 건너뛰면 호스트의 extra 가 '이전 프로젝트'의
    //   필지로 남아 교차오염이 된다(5필지 A → 1필지 B 전환 시 B 화면에 A 의 4필지가 잔류해
    //   "5개 필지 통합" 날조·B 구획도에 A 필지 렌더·A 필지로 유료 등기조회 발주·인허가 분석이
    //   두 프로젝트를 혼합). 호스트 계약(setAddr(all[0]); setExtra(all.slice(1)))이 단일필지에서
    //   extra=[] 로 정확히 정리하므로, 항상 호출하는 것이 유일하게 안전하다.
    onParcelsChange?.(all);
  };

  const handleAddressChange = (entries: AddressEntry[]) => {
    // ★대표 주소는 공용 정규화로 — jibunAddress 가 법정동 빠진 바레 번지면 fullAddress 우선(지오코딩 성공률↑).
    const primary = entries.length > 0 ? preferredEntryAddress(entries[0]) : "";
    onChange(primary);
    // 다필지: 등록된 전 필지 주소 배열을 호스트로 전달(호스트가 쓰면 활용).
    const all = entries
      .map((e) => preferredEntryAddress(e))
      .filter(Boolean);
    onParcelsChange?.(all);
    // 상세판: 면적·용도지역·용적/건폐 포함 전체 entries를 호스트로 전달(SSOT 단일화용).
    onEntriesChange?.(entries);
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
        single={single}
        initialAddress={value || undefined}
        placeholder={placeholder}
        disabled={disabled}
        writeToContext={writeToContext}
        onChange={handleAddressChange}
      />
    </div>
  );
}
