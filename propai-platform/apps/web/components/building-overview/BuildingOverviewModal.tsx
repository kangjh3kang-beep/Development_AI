"use client";

/**
 * 건축개요 입력 모달 — 통합 필지 입력에서 연다.
 *
 * ★대지면적은 선택 필지 합계에서 **자동 산입**하되, `deriveLandAreaIntake` 가
 *   보류하면 넣지 않고 **사유를 보여 준다**(2026-08-23 「15.86km 6필지 통합 5,781㎡」 사고).
 * ★용적률·건폐율은 **저장하지 않고 파생 표시**한다 — 저장하면 원본과 갈린다.
 * ★자동값과 사람이 덮어쓴 값을 **구별해 표시**한다. 같은 모양이면 그 값을 못 믿는다.
 */
import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useModalFocus } from "@/hooks/useModalFocus";
import { DISMISS_Z, useDismissible } from "@/lib/satong-dismiss";

import {
  type BuildingOverview,
  deriveBcrPct,
  deriveFarPct,
  derivePyeong,
  deriveTotalGfaSqm,
  emptyBuildingOverview,
  fieldsForUse,
  validateBuildingOverview,
} from "@/lib/building-overview";
import { type LandAreaIntake } from "@/lib/building-overview-intake";
import { buildingUseOptions } from "@/lib/building-use";
import { makeUseLine } from "@/lib/building-overview";

type Props = {
  open: boolean;
  /** 선택 필지에서 계산한 자동 산입 결과(보류 사유 포함). */
  intake: LandAreaIntake;
  initial?: BuildingOverview | null;
  onSave: (overview: BuildingOverview) => void;
  onCancel: () => void;
};

/** 숫자 입력 — 빈 칸은 **null**(0 이 아니다). */
function numField(v: number | null): string {
  return v === null ? "" : String(v);
}
function parseNum(s: string): number | null {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t.replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}
/** 파생값 표시 — 못 재면 「—」. **0% 라고 쓰지 않는다.** */
function pct(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(1)}%`;
}

export function BuildingOverviewModal({ open, intake, initial, onSave, onCancel }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [o, setO] = useState<BuildingOverview>(emptyBuildingOverview());

  // ★훅은 early return 앞에(조건부 호출 금지 — ConfirmDeleteModal 의 주석과 같은 규율)
  useModalFocus(dialogRef, open);
  useDismissible(DISMISS_Z.appModal, open, onCancel);

  // ★effect 로 setState 하지 않는다(연쇄 렌더) — React 공식 **「렌더 중 조정」** 패턴으로
  //   직전에 반영한 열림 신호를 상태에 들고 비교한다. 닫히면 신호가 null 로 돌아가므로
  //   **다시 열 때 같은 필지여도 초기화가 다시 돈다**(신호를 안 비우면 두 번째 열기가 조용히 낡는다).
  const syncKey = open ? `open|${intake.autoLandAreaSqm ?? "null"}` : null;
  const [syncedFor, setSyncedFor] = useState<string | null>(null);
  if (syncKey !== syncedFor) {
    setSyncedFor(syncKey);
    if (syncKey !== null) {
      const start = initial ?? emptyBuildingOverview();
      setO({
        ...start,
        // ★열 때마다 자동 산입을 다시 적용한다 — 필지가 바뀌었을 수 있다.
        //   단 사람이 덮어쓴 값(manual)은 **보존**한다.
        landAreaSqm: start.landAreaOrigin === "manual" ? start.landAreaSqm : intake.autoLandAreaSqm,
        landAreaOrigin: start.landAreaOrigin === "manual" ? "manual" : "auto",
      });
    }
  }

  const far = useMemo(() => deriveFarPct(o), [o]);
  const bcr = useMemo(() => deriveBcrPct(o), [o]);
  const totalGfa = useMemo(() => deriveTotalGfaSqm(o), [o]);
  const issues = useMemo(() => validateBuildingOverview(o), [o]);

  if (!open || typeof document === "undefined") return null;

  const setNum = (k: "buildingAreaSqm" | "aboveGroundGfaSqm" | "basementGfaSqm", s: string) =>
    setO((p) => ({ ...p, [k]: parseNum(s) }));

  const body = (
    // ★백드롭 z 는 **계약값 `SATONG_CONTENT_Z.appModal`(=800)** 이다. 임의의 큰 수가 아니다 —
    //   지도 공존 화면에서 오버레이(380~500)·ContextHeader(600)·네비 플라이아웃(700)이
    //   백드롭을 관통한 사고가 그 상수를 만들었고, 이 모달이 바로 그 화면에서 열린다.
    //   (`layer-ladder.contract` 가 지도 폐포에서 백드롭을 **파생으로** 모아 이 값을 강제한다.)
    // ★`role="dialog"`·`aria-modal` 은 **백드롭**에, 트랩 ref 는 **본체**에 — 형제 3표면이
    //   전부 이 모양이고(ConfirmDeleteModal·LandShareModal·ConsentModal), 계약 락이
    //   `role=dialog` 요소를 백드롭으로 보고 **그 안에 트랩 컨테이너가 따로 있는지**를 관측한다.
    //   둘을 한 요소에 겹치면 트랩 범위가 백드롭까지 넓어진 것과 구별되지 않는다.
    <div
      role="dialog"
      aria-modal="true"
      aria-label="건축개요 입력"
      className="fixed inset-0 z-[800] flex items-center justify-center bg-black/50 p-4"
    >
      <div
        ref={dialogRef}
        data-testid="building-overview-modal"
        className="w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-6 shadow-2xl"
        style={{ maxHeight: "90vh" }}
      >
        <h2 className="text-lg font-bold text-[var(--text-primary)]">건축개요 입력</h2>

        {/* 대지면적 — 자동/수동을 구별해 보여 준다 */}
        <div className="mt-5 grid gap-1.5">
          <span className="text-sm font-medium text-[var(--text-secondary)]">
            대지면적 (m²){" "}
            <span
              data-testid="land-origin"
              className="ml-1 rounded px-1.5 py-0.5 text-[11px] font-bold text-[var(--text-tertiary)]"
            >
              {o.landAreaOrigin === "manual" ? "직접 입력" : "선택 필지 합계"}
            </span>
          </span>
          <input
            data-testid="land-area"
            inputMode="decimal"
            value={numField(o.landAreaSqm)}
            onChange={(e) =>
              setO((p) => ({ ...p, landAreaSqm: parseNum(e.target.value), landAreaOrigin: "manual" }))
            }
            className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
          />
          {intake.withheldReason ? (
            <p data-testid="intake-withheld" role="status" className="text-xs text-[rgb(146,64,14)]">
              {intake.withheldReason} 직접 입력해 주세요.
            </p>
          ) : null}
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {(
            [
              ["buildingAreaSqm", "건축면적 (m²)"],
              ["aboveGroundGfaSqm", "지상 연면적 (m²)"],
              ["basementGfaSqm", "지하 연면적 (m²)"],
            ] as const
          ).map(([k, label]) => (
            <label key={k} className="grid gap-1.5 text-sm">
              <span className="font-medium text-[var(--text-secondary)]">{label}</span>
              <input
                data-testid={k}
                inputMode="decimal"
                value={numField(o[k])}
                onChange={(e) => setNum(k, e.target.value)}
                className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
              />
            </label>
          ))}
        </div>

        {/* ★파생 — 저장하지 않는다. 못 재면 「—」 */}
        <dl className="mt-5 grid grid-cols-3 gap-3 rounded-xl bg-[var(--surface-muted)] p-3 text-sm">
          <div>
            <dt className="text-xs text-[var(--text-tertiary)]">연면적 합계</dt>
            <dd data-testid="derived-gfa" className="font-bold">
              {totalGfa === null ? "—" : `${totalGfa.toLocaleString()} m²`}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--text-tertiary)]">용적률(지상 기준)</dt>
            <dd data-testid="derived-far" className="font-bold">{pct(far)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--text-tertiary)]">건폐율</dt>
            <dd data-testid="derived-bcr" className="font-bold">{pct(bcr)}</dd>
          </div>
        </dl>

        {/* 용도 구성 — 정본에서 파생한 선택지 */}
        <div className="mt-5 grid gap-2">
          <span className="text-sm font-medium text-[var(--text-secondary)]">용도 구성</span>
          {o.uses.map((line, i) => (
            <div key={i} className="flex gap-2">
              <select
                data-testid={`use-${i}`}
                value={line.use}
                onChange={(e) =>
                  setO((p) => {
                    const uses = [...p.uses];
                    const next = makeUseLine(e.target.value, line.gfaSqm);
                    if (next) uses[i] = { ...next, unitCount: line.unitCount, avgExclusiveSqm: line.avgExclusiveSqm, rawUse: null };
                    return { ...p, uses };
                  })
                }
                className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
              >
                {buildingUseOptions().map((op) => (
                  <option key={op.code} value={op.code}>{op.label}</option>
                ))}
              </select>
              <input
                data-testid={`use-gfa-${i}`}
                inputMode="decimal"
                value={numField(line.gfaSqm)}
                onChange={(e) =>
                  setO((p) => {
                    const uses = [...p.uses];
                    uses[i] = { ...uses[i], gfaSqm: parseNum(e.target.value) ?? 0 };
                    return { ...p, uses };
                  })
                }
                placeholder="연면적 (m²)"
                className="flex-1 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
              />
              {/* ★용도에 따라 **다른 항목**을 묻는다(요청: 평형·상가·오피스별 입력항목).
                  구성은 `fieldsForUse` 가 정본 코드에서 결정한다 — 여기서 분기를
                  손으로 적으면 새 용도가 조용히 기본값으로 떨어진다. */}
              <input
                data-testid={`use-units-${i}`}
                inputMode="numeric"
                value={numField(line.unitCount)}
                onChange={(e) =>
                  setO((p) => {
                    const uses = [...p.uses];
                    uses[i] = { ...uses[i], unitCount: parseNum(e.target.value) };
                    return { ...p, uses };
                  })
                }
                placeholder={fieldsForUse(line.use).unitLabel}
                aria-label={`${fieldsForUse(line.use).unitLabel} ${i + 1}`}
                className="w-24 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
              />
              <input
                data-testid={`use-avg-${i}`}
                inputMode="decimal"
                value={numField(line.avgExclusiveSqm)}
                onChange={(e) =>
                  setO((p) => {
                    const uses = [...p.uses];
                    uses[i] = { ...uses[i], avgExclusiveSqm: parseNum(e.target.value) };
                    return { ...p, uses };
                  })
                }
                placeholder={fieldsForUse(line.use).areaLabel}
                aria-label={`${fieldsForUse(line.use).areaLabel} ${i + 1}`}
                className="w-36 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
              />
              {/* ★평형은 **파생 표시**다(저장하지 않는다). 못 재면 「—」 — 0평이라 쓰지 않는다.
                  평형을 관행적으로 쓰지 않는 용도(상가·오피스 등)에는 아예 안 보여 준다. */}
              {fieldsForUse(line.use).pyeong ? (
                <span
                  data-testid={`use-pyeong-${i}`}
                  className="self-center text-xs font-bold text-[var(--text-secondary)]"
                >
                  {derivePyeong(line.avgExclusiveSqm) === null
                    ? "—"
                    : `${derivePyeong(line.avgExclusiveSqm)!.toFixed(1)}평`}
                </span>
              ) : null}
            </div>
          ))}
          <button
            type="button"
            data-testid="add-use"
            onClick={() =>
              setO((p) => {
                const line = makeUseLine("공동주택", 0);
                return line ? { ...p, uses: [...p.uses, { ...line, rawUse: null }] } : p;
              })
            }
            className="justify-self-start rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs font-bold"
          >
            + 용도 추가
          </button>
        </div>

        {/* ★모순만 신고한다 — 부분 입력은 막지 않는다 */}
        {issues.length > 0 ? (
          <ul data-testid="overview-issues" role="status" className="mt-4 grid gap-1">
            {issues.map((it, i) => (
              <li key={i} className="text-xs text-[rgb(146,64,14)]">{it.message}</li>
            ))}
          </ul>
        ) : null}

        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-lg border border-[var(--line)] px-4 py-2 text-sm">
            취소
          </button>
          <button
            type="button"
            data-testid="overview-save"
            onClick={() => onSave(o)}
            className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(body, document.body);
}
