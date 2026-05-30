"use client";

import { useState } from "react";

/* ── Types ── */

interface SiteAnalysisDetailProps {
  data: Record<string, unknown>;
}

/* ── Helpers ── */

const SQM_PER_PYEONG = 3.3058;

function sqmToPyeong(sqm: number): string {
  return (sqm / SQM_PER_PYEONG).toFixed(1);
}

function formatArea(sqm: unknown): string {
  if (typeof sqm !== "number" || sqm <= 0) return "-";
  return `${sqm.toLocaleString("ko-KR")} m² (${sqmToPyeong(sqm)}평)`;
}

function formatWon(value: unknown): string {
  if (typeof value !== "number" || value <= 0) return "-";
  if (value >= 1e8) return `${(value / 1e8).toFixed(1)}억원`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)}만원`;
  return `${value.toLocaleString("ko-KR")}원`;
}

function formatPct(value: unknown): string {
  if (typeof value !== "number") return "-";
  return `${value.toFixed(1)}%`;
}

function n(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function s(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  return String(value);
}

/* ── Resolve nested or flat data helpers ── */

function resolve(data: Record<string, unknown>, nested: string, ...flatKeys: string[]): unknown {
  // Try nested first
  const nestedVal = data[nested];
  if (nestedVal != null && typeof nestedVal === "object") return nestedVal;
  // Try flat: return first non-null
  for (const key of flatKeys) {
    if (data[key] != null) return data[key];
  }
  return null;
}

function obj(val: unknown): Record<string, unknown> {
  if (val != null && typeof val === "object" && !Array.isArray(val)) return val as Record<string, unknown>;
  return {};
}

function arr(val: unknown): unknown[] {
  return Array.isArray(val) ? val : [];
}

/* ── Category Card ── */

interface CategoryCardProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function CategoryCard({ title, icon, children, defaultOpen = false }: CategoryCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] overflow-hidden transition-all">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--surface-strong)] transition-colors"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent-strong)] shrink-0">
          {icon}
        </span>
        <span className="flex-1 text-sm font-bold text-[var(--text-primary)] tracking-tight">{title}</span>
        <svg
          width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="var(--text-tertiary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          className={`shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-[var(--line)]">
          {children}
        </div>
      )}
    </div>
  );
}

/* ── Field Row ── */

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] px-3 py-2">
      <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider uppercase mb-0.5">{label}</p>
      <p className="text-xs font-bold text-[var(--text-primary)]">{value || "-"}</p>
    </div>
  );
}

function NoData() {
  return <p className="text-xs text-[var(--text-hint)] italic py-2">데이터 없음</p>;
}

/* ── Icons (inline SVG) ── */

const IconPin = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" />
    <circle cx="12" cy="10" r="3" />
  </svg>
);

const IconRuler = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z" />
    <path d="m14.5 12.5 2-2" /><path d="m11.5 9.5 2-2" /><path d="m8.5 6.5 2-2" /><path d="m17.5 15.5 2-2" />
  </svg>
);

const IconBuilding = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="2" width="16" height="20" rx="2" ry="2" /><path d="M9 22v-4h6v4" /><path d="M8 6h.01" /><path d="M16 6h.01" /><path d="M12 6h.01" /><path d="M12 10h.01" /><path d="M12 14h.01" /><path d="M16 10h.01" /><path d="M16 14h.01" /><path d="M8 10h.01" /><path d="M8 14h.01" />
  </svg>
);

const IconWon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 0 1 0 4H8" /><path d="M12 18V6" />
  </svg>
);

const IconOffice = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="7" width="20" height="14" rx="2" ry="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
  </svg>
);

const IconSubway = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="3" width="16" height="16" rx="2" /><path d="M4 11h16" /><path d="M12 3v8" /><path d="m8 19-2 3" /><path d="m18 22-2-3" /><path d="M8 15h0" /><path d="M16 15h0" />
  </svg>
);

const IconWarning = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4" /><path d="M12 17h.01" />
  </svg>
);

/* ── Progress Bar ── */

function FarProgressBar({ base, allowed, cap }: { base: number; allowed: number; cap: number }) {
  const max = cap * 1.1;
  const basePct = (base / max) * 100;
  const allowedPct = (allowed / max) * 100;
  const capPct = (cap / max) * 100;

  return (
    <div className="mt-2">
      <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">기부체납 인센티브 용적률</p>
      <div className="relative h-6 rounded-full bg-[var(--surface-strong)] border border-[var(--line)] overflow-hidden">
        <div className="absolute inset-y-0 left-0 rounded-full bg-blue-500/30" style={{ width: `${capPct}%` }} />
        <div className="absolute inset-y-0 left-0 rounded-full bg-blue-500/50" style={{ width: `${allowedPct}%` }} />
        <div className="absolute inset-y-0 left-0 rounded-full bg-[var(--accent-strong)]" style={{ width: `${basePct}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-[var(--text-secondary)] mt-1">
        <span>기본 {base}%</span>
        <span>허용 {allowed}%</span>
        <span>상한 {cap}%</span>
      </div>
    </div>
  );
}

/* ── Donation Simulation Table ── */

function DonationSimTable({ baseFar, capFar }: { baseFar: number; capFar: number }) {
  const rows: { pct: number; far: number }[] = [];
  for (let pct = 0; pct <= 30; pct += 5) {
    const far = Math.min(baseFar + ((capFar - baseFar) * pct) / 30, capFar);
    rows.push({ pct, far: Math.round(far * 10) / 10 });
  }

  return (
    <div className="mt-3">
      <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">기부체납 시뮬레이션</p>
      <div className="overflow-x-auto">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="border-b border-[var(--line)]">
              <th className="text-left py-1 px-2 font-bold text-[var(--text-secondary)]">기부체납률</th>
              <th className="text-right py-1 px-2 font-bold text-[var(--text-secondary)]">적용 용적률</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.pct} className="border-b border-[var(--line)]/50">
                <td className="py-1 px-2 text-[var(--text-primary)]">{r.pct}%</td>
                <td className="py-1 px-2 text-right font-bold text-[var(--text-primary)]">{r.far}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Main Component ── */

export function SiteAnalysisDetail({ data }: SiteAnalysisDetailProps) {
  // 1. 기본 토지정보
  const basic = obj(data.basic);
  const landAddress = s(basic.address || data.address);
  const pnu = s(basic.pnu || data.pnu_codes);
  const landCategory = s(basic.land_category || data.land_category);
  const landAreaSqm = n(basic.land_area_sqm ?? data.land_area_sqm);
  const ownerType = s(basic.owner_type || data.owner_type);

  // 2. 용도지역/법규한도
  const zoning = obj(data.zoning);
  const zoneType = s(zoning.zone_type || data.zone_type);
  const nationalBcr = n(zoning.national_bcr ?? data.national_bcr);
  const nationalFar = n(zoning.national_far ?? data.national_far);
  const ordinanceBcr = n(zoning.ordinance_bcr ?? data.ordinance_bcr);
  const ordinanceFar = n(zoning.ordinance_far ?? data.ordinance_far);
  const effectiveBcr = n(zoning.effective_bcr ?? data.max_bcr ?? data.effective_bcr);
  const effectiveFar = n(zoning.effective_far ?? data.max_far ?? data.effective_far);
  const heightLimit = n(zoning.height_limit ?? data.height_limit);
  const baseFar = n(zoning.base_far ?? data.base_far) ?? effectiveFar;
  const allowedFar = n(zoning.allowed_far ?? data.allowed_far);
  const capFar = n(zoning.cap_far ?? data.cap_far);

  // 3. 개발 가능 유형 (backend returns dict with allowed_types array)
  const devTypesRaw = data.development_types;
  const devTypes = Array.isArray(devTypesRaw)
    ? devTypesRaw
    : arr((devTypesRaw as Record<string, unknown>)?.allowed_types);

  // 4. 공시지가/시세
  const pricing = obj(data.pricing);
  const officialPrice = n(pricing.official_land_price ?? data.official_land_price);
  const totalLandValue = n(pricing.total_land_value ?? data.estimated_value);
  const transactions = obj(pricing.transactions ?? data.transactions);
  const recentDeals = arr(pricing.recent_deals ?? data.recent_deals);

  // 5. 기존 건축물
  const building = obj(data.building ?? data.building_info);

  // 6. 주변 인프라
  const infra = obj(data.infrastructure);

  // 7. 규제 사항
  const regulations = obj(data.regulations);
  const specialDistricts = arr(data.special_districts ?? regulations.special_districts);
  const landUsePlan = obj(regulations.land_use_plan ?? data.land_use_plan);
  const landUseRegs = arr(
    landUsePlan.districts ?? landUsePlan.regulations ?? regulations.land_use_plan ?? data.land_use_plan
  );
  const warnings = arr(regulations.warnings ?? data.warnings);

  const hasBasic = landAddress || pnu || landAreaSqm;
  const hasZoning = zoneType || effectiveBcr || effectiveFar;
  const hasDevTypes = devTypes.length > 0;
  const hasPricing = officialPrice || totalLandValue || recentDeals.length > 0;
  const hasBuilding = Object.keys(building).length > 0 &&
    Boolean(s(building.buildingName || building.building_name) || n(building.totalAreaSqm ?? building.total_area_sqm));
  const hasInfra = Object.keys(infra).length > 0;
  const hasRegulations = specialDistricts.length > 0 || landUseRegs.length > 0 || warnings.length > 0;

  return (
    <div className="space-y-2">
      {/* 1. 기본 토지정보 */}
      <CategoryCard title="기본 토지정보" icon={IconPin} defaultOpen={true}>
        {hasBasic ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {landAddress && <Field label="주소" value={landAddress} />}
            {pnu && <Field label="PNU" value={typeof pnu === "string" && pnu.startsWith("[") ? pnu : s(pnu)} />}
            {landCategory && <Field label="지목" value={landCategory} />}
            {landAreaSqm && <Field label="대지면적" value={formatArea(landAreaSqm)} />}
            {ownerType && <Field label="소유구분" value={ownerType} />}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 2. 용도지역/법규한도 */}
      <CategoryCard title="용도지역 · 법규한도" icon={IconRuler} defaultOpen={true}>
        {hasZoning ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {zoneType && <Field label="용도지역" value={zoneType} />}
              {nationalBcr != null && <Field label="법정 건폐율 (국토계획법)" value={formatPct(nationalBcr)} />}
              {nationalFar != null && <Field label="법정 용적률 (국토계획법)" value={formatPct(nationalFar)} />}
              {ordinanceBcr != null && <Field label="조례 건폐율 (지자체)" value={formatPct(ordinanceBcr)} />}
              {ordinanceFar != null && <Field label="조례 용적률 (지자체)" value={formatPct(ordinanceFar)} />}
              {effectiveBcr != null && <Field label="실효 건폐율" value={formatPct(effectiveBcr)} />}
              {effectiveFar != null && <Field label="실효 용적률" value={formatPct(effectiveFar)} />}
              {heightLimit != null && heightLimit > 0 && <Field label="높이제한" value={`${heightLimit}m`} />}
            </div>
            {s(zoning.ordinance_source) && (
              <p className="text-[10px] text-[var(--text-hint)] mt-1">출처: {s(zoning.ordinance_source)}</p>
            )}
            {baseFar != null && allowedFar != null && capFar != null && (
              <>
                <FarProgressBar base={baseFar} allowed={allowedFar} cap={capFar} />
                <DonationSimTable baseFar={baseFar} capFar={capFar} />
              </>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 3. 개발 가능 유형 */}
      <CategoryCard title="개발 가능 유형" icon={IconBuilding}>
        {hasDevTypes ? (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1.5">
              {devTypes.map((item, i) => {
                const dt = obj(item);
                const name = s(dt.type_name || dt.name || dt.type || item);
                const recommended = Boolean(dt.recommended);
                const restricted = Boolean(dt.restricted);
                return (
                  <span
                    key={i}
                    className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-bold border transition-all ${
                      restricted
                        ? "bg-gray-500/10 text-[var(--text-hint)] border-gray-500/20 line-through"
                        : recommended
                        ? "bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] border-[var(--accent-strong)]/30"
                        : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border-[var(--line)]"
                    }`}
                  >
                    {recommended && <span className="mr-1">★</span>}
                    {name}
                  </span>
                );
              })}
            </div>
            {/* Conditions */}
            {devTypes.some((item) => obj(item).conditions || obj(item).condition) && (
              <div className="space-y-1 mt-2">
                {devTypes.map((item, i) => {
                  const dt = obj(item);
                  const condition = s(dt.conditions || dt.condition);
                  if (!condition) return null;
                  return (
                    <p key={i} className="text-[10px] text-[var(--text-secondary)]">
                      <span className="font-bold">{s(dt.type_name || dt.name || dt.type)}:</span> {condition}
                    </p>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 4. 공시지가/시세 */}
      <CategoryCard title="공시지가 · 시세" icon={IconWon}>
        {hasPricing ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {officialPrice != null && (
                <>
                  <Field label="공시지가 (원/m²)" value={formatWon(officialPrice)} />
                  {landAreaSqm && (
                    <Field label="공시지가 총액" value={formatWon(officialPrice * landAreaSqm)} />
                  )}
                </>
              )}
              {totalLandValue != null && !landAreaSqm && (
                <Field label="추정가치" value={formatWon(totalLandValue)} />
              )}
            </div>
            {/* 인근 실거래가 요약 */}
            {Object.keys(transactions).length > 0 && (
              <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-2">인근 실거래가 요약</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {transactions.count != null && <Field label="거래건수" value={`${transactions.count}건`} />}
                  {transactions.avg_price != null && <Field label="평균가" value={formatWon(transactions.avg_price)} />}
                  {transactions.max_price != null && <Field label="최고가" value={formatWon(transactions.max_price)} />}
                  {transactions.min_price != null && <Field label="최저가" value={formatWon(transactions.min_price)} />}
                </div>
              </div>
            )}
            {/* 최근 거래 목록 */}
            {recentDeals.length > 0 && (
              <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-2">최근 거래 (상위 5건)</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="border-b border-[var(--line)]">
                        <th className="text-left py-1 px-2 font-bold text-[var(--text-secondary)]">거래일</th>
                        <th className="text-left py-1 px-2 font-bold text-[var(--text-secondary)]">면적</th>
                        <th className="text-right py-1 px-2 font-bold text-[var(--text-secondary)]">금액</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recentDeals.slice(0, 5).map((deal, i) => {
                        const d = obj(deal);
                        return (
                          <tr key={i} className="border-b border-[var(--line)]/50">
                            <td className="py-1 px-2 text-[var(--text-primary)]">{s(d.date || d.deal_date)}</td>
                            <td className="py-1 px-2 text-[var(--text-primary)]">{formatArea(n(d.area_sqm))}</td>
                            <td className="py-1 px-2 text-right font-bold text-[var(--text-primary)]">{formatWon(n(d.price || d.amount))}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 5. 기존 건축물 */}
      <CategoryCard title="기존 건축물" icon={IconOffice}>
        {hasBuilding ? (
          (() => {
            const bName = s(building.buildingName || building.building_name);
            const bPurpose = s(building.mainPurpose || building.main_purpose);
            const bStructure = s(building.structure);
            const bArea = n(building.totalAreaSqm ?? building.total_area_sqm);
            const bFloors = n(building.groundFloors ?? building.ground_floors ?? building.floors);
            const bApproval = s(building.useApprovalDate || building.use_approval_date);
            return (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {bName && <Field label="건축물명" value={bName} />}
                {bPurpose && <Field label="주용도" value={bPurpose} />}
                {bStructure && <Field label="구조" value={bStructure} />}
                {bArea != null && <Field label="연면적" value={formatArea(bArea)} />}
                {bFloors != null && <Field label="층수" value={`${bFloors}층`} />}
                {bApproval && <Field label="사용승인일" value={bApproval} />}
              </div>
            );
          })()
        ) : (
          <p className="text-xs text-[var(--text-hint)] italic py-2">기존 건축물 없음 (나대지)</p>
        )}
      </CategoryCard>

      {/* 6. 주변 인프라 */}
      <CategoryCard title="주변 인프라" icon={IconSubway}>
        {hasInfra ? (
          <div className="space-y-3">
            {/* 최근접 지하철역 */}
            {infra.nearest_subway != null && (
              <div className="grid grid-cols-2 gap-2">
                <Field label="최근접 지하철역" value={String(obj(infra.nearest_subway).name ?? "")} />
                <Field label="거리" value={`${n(obj(infra.nearest_subway).distance_m) ?? "-"}m`} />
              </div>
            )}
            {/* 인근 학교 */}
            {arr(infra.schools).length > 0 && (
              <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-2">인근 학교</p>
                <div className="space-y-1">
                  {arr(infra.schools).map((school, i) => {
                    const sc = obj(school);
                    return (
                      <div key={i} className="flex items-center justify-between text-[11px]">
                        <span className="text-[var(--text-primary)] font-medium">
                          {String(sc.name ?? "")}
                          {sc.type != null && <span className="ml-1 text-[var(--text-hint)]">({String(sc.type)})</span>}
                        </span>
                        <span className="text-[var(--text-secondary)]">{n(sc.distance_m) ?? "-"}m</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 7. 규제 사항 */}
      <CategoryCard title="규제 사항" icon={IconWarning}>
        {hasRegulations ? (
          <div className="space-y-3">
            {/* 토지이용계획 규제 */}
            {landUseRegs.length > 0 && (
              <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-2">토지이용계획 규제</p>
                <div className="space-y-1">
                  {landUseRegs.map((reg, i) => {
                    const r = obj(reg);
                    return (
                      <div key={i} className="flex items-center gap-2 text-[11px]">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                        <span className="text-[var(--text-primary)]">{s(r.district_name || r.districtName || r.name || reg)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {/* 특수구역 */}
            {specialDistricts.length > 0 && (
              <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                <p className="text-[10px] font-bold text-[var(--text-hint)] mb-2">특수구역</p>
                <div className="flex flex-wrap gap-1.5">
                  {specialDistricts.map((d, i) => (
                    <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      {s(obj(d).name || d)}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {/* 경고 사항 */}
            {warnings.length > 0 && (
              <div className="rounded-lg bg-red-500/5 border border-red-500/20 p-3">
                <p className="text-[10px] font-bold text-red-400 mb-2">경고 사항</p>
                <div className="space-y-1">
                  {warnings.map((w, i) => (
                    <div key={i} className="flex items-start gap-2 text-[11px]">
                      <span className="text-red-400 mt-0.5 shrink-0">!</span>
                      <span className="text-red-300">{s(w)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>
    </div>
  );
}
