"use client";

import { useCallback, useState } from "react";
import { useCadStore } from "@/store/use-cad-store";
import { NumberInput } from "@/components/common/NumberInput";
import type {
  AutoDesignRequest,
  AutoDesignResponse,
  AutoDesignSummary,
  AutoDesignCompliance,
} from "@/components/cad/types";

const ZONE_OPTIONS = [
  { code: "1R", label: "제1종일반주거" },
  { code: "2R", label: "제2종일반주거" },
  { code: "3R", label: "제3종일반주거" },
  { code: "GC", label: "일반상업" },
  { code: "NC", label: "근린상업" },
  { code: "QI", label: "준공업" },
  { code: "QR", label: "준주거" },
];

const UNIT_TYPE_OPTIONS = ["59A", "74A", "84A", "114A"];

const BUILDING_USE_OPTIONS = ["공동주택", "근린생활시설", "업무시설", "오피스텔"];

type AutoDesignPanelProps = {
  projectId: string;
};

export function AutoDesignPanel({ projectId }: AutoDesignPanelProps) {
  const loadDesignPayload = useCadStore((s) => s.loadDesignPayload);

  // 폼 상태
  const [siteArea, setSiteArea] = useState(500);
  const [zoneCode, setZoneCode] = useState("2R");
  const [buildingUse, setBuildingUse] = useState("공동주택");
  const [unitTypes, setUnitTypes] = useState<string[]>(["84A"]);
  const [floorHeight, setFloorHeight] = useState(3.0);
  const [setback, setSetback] = useState({
    north: 3.0,
    south: 2.0,
    east: 1.5,
    west: 1.5,
  });

  // 결과 상태
  const [result, setResult] = useState<AutoDesignResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleUnitType = useCallback((type: string) => {
    setUnitTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  }, []);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { generateAutoDesign } = await import("@/lib/parametric-design-engine");
      const body: AutoDesignRequest = {
        site_area_sqm: siteArea,
        zone_code: zoneCode,
        building_use: buildingUse,
        target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
        floor_height_m: floorHeight,
        setback_m: setback,
      };
      // 로컬 엔진으로 즉시 생성 (백엔드 불필요)
      const data = generateAutoDesign(body);
      setResult(data);
      // 자동으로 캔버스에 적용
      loadDesignPayload(data.design_payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "설계 생성 실패");
    } finally {
      setLoading(false);
    }
  }, [siteArea, zoneCode, buildingUse, unitTypes, floorHeight, setback, loadDesignPayload]);

  const handleApply = useCallback(() => {
    if (!result) return;
    loadDesignPayload(result.design_payload);
  }, [result, loadDesignPayload]);

  const handleExportDxf = useCallback(async () => {
    if (!result) return;
    try {
      const { downloadDXF } = await import("@/lib/dxf-exporter");
      downloadDXF(result.design_payload, "floor_plan.dxf");
    } catch {
      setError("DXF 다운로드 실패");
    }
  }, [result]);

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
        AI 자동 설계
      </h3>

      {/* 입력 폼 */}
      <div className="grid gap-2 text-xs">
        <label className="flex items-center justify-between gap-2">
          <span className="text-[var(--text-secondary)]">대지면적 (m²)</span>
          <NumberInput
            allowDecimal
            value={siteArea}
            onChange={(n) => setSiteArea(n ?? 0)}
            className="w-20 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-right text-sm"
          />
        </label>

        <label className="flex items-center justify-between gap-2">
          <span className="text-[var(--text-secondary)]">용도지역</span>
          <select
            value={zoneCode}
            onChange={(e) => setZoneCode(e.target.value)}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-sm"
            aria-label="용도지역"
          >
            {ZONE_OPTIONS.map((z) => (
              <option key={z.code} value={z.code}>
                {z.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center justify-between gap-2">
          <span className="text-[var(--text-secondary)]">건축 용도</span>
          <select
            value={buildingUse}
            onChange={(e) => setBuildingUse(e.target.value)}
            className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-sm"
            aria-label="건축 용도"
          >
            {BUILDING_USE_OPTIONS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center justify-between gap-2">
          <span className="text-[var(--text-secondary)]">세대 유형</span>
          <div className="flex gap-1">
            {UNIT_TYPE_OPTIONS.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => toggleUnitType(t)}
                className={`rounded-lg px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  unitTypes.includes(t)
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--surface-soft)] text-[var(--text-tertiary)]"
                }`}
                aria-pressed={unitTypes.includes(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <label className="flex items-center justify-between gap-2">
          <span className="text-[var(--text-secondary)]">층고 (m)</span>
          <input
            type="number"
            min={2.5}
            step={0.1}
            value={floorHeight}
            onChange={(e) => setFloorHeight(Number(e.target.value))}
            className="w-16 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-right text-sm"
            aria-label="층고"
          />
        </label>

        {/* 세트백 */}
        <div className="space-y-1">
          <span className="text-[var(--text-secondary)]">세트백 (m)</span>
          <div className="grid grid-cols-4 gap-1">
            {(["north", "south", "east", "west"] as const).map((dir) => (
              <label key={dir} className="text-center">
                <span className="text-[10px] text-[var(--text-hint)]">
                  {dir === "north"
                    ? "북"
                    : dir === "south"
                      ? "남"
                      : dir === "east"
                        ? "동"
                        : "서"}
                </span>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={setback[dir]}
                  onChange={(e) =>
                    setSetback((prev) => ({
                      ...prev,
                      [dir]: Number(e.target.value),
                    }))
                  }
                  className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-1 py-0.5 text-center text-[11px]"
                  aria-label={`세트백 ${dir}`}
                />
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* 생성 버튼 */}
      <button
        type="button"
        onClick={handleGenerate}
        disabled={loading}
        className="rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white transition-opacity disabled:opacity-50"
      >
        {loading ? "생성 중..." : "AI 자동 설계 생성"}
      </button>

      {/* 에러 */}
      {error && (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}

      {/* 결과 요약 */}
      {result && (
        <div className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <h4 className="text-xs font-semibold text-[var(--text-secondary)]">
            생성 결과
          </h4>
          <SummaryMetrics summary={result.summary} compliance={result.compliance} />

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleApply}
              className="flex-1 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white"
            >
              캔버스에 적용
            </button>
            <button
              type="button"
              onClick={handleExportDxf}
              className="flex-1 rounded-xl bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] border border-[var(--line)]"
            >
              DXF 다운로드
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryMetrics({
  summary,
  compliance,
}: {
  summary: AutoDesignSummary;
  compliance: AutoDesignCompliance;
}) {
  const metrics = [
    {
      label: "건폐율",
      value: `${summary.bcr_percent.toFixed(1)}%`,
      pass: compliance.bcr_ok,
    },
    {
      label: "용적률",
      value: `${summary.far_percent.toFixed(1)}%`,
      pass: compliance.far_ok,
    },
    {
      label: "층수",
      value: `${summary.num_floors}F`,
      pass: compliance.height_ok,
    },
    {
      label: "높이",
      value: `${summary.building_height_m.toFixed(1)}m`,
      pass: compliance.height_ok,
    },
    {
      label: "세대수",
      value: `${summary.total_units}세대`,
      pass: true,
    },
    {
      label: "주차",
      value: `${summary.parking_count}대`,
      pass: true,
    },
  ];

  return (
    <div className="grid grid-cols-3 gap-1.5">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="flex items-center gap-1 rounded-lg bg-[var(--surface-soft)] px-2 py-1"
        >
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${m.pass ? "bg-emerald-500" : "bg-red-500"}`}
          />
          <div>
            <div className="text-[10px] text-[var(--text-hint)]">{m.label}</div>
            <div className="text-xs font-semibold text-[var(--text-primary)]">
              {m.value}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
