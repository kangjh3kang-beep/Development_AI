"use client";

/**
 * 배치 미리보기 섹션 — 필지 상세 온디맨드(사통맵 v2 W3).
 *
 * 설계사가 필지를 보고 묻는 것: **"여기에 어떻게 몇 동을 앉힐 수 있나."** 값·기하는 전부
 * 서버 산정(`POST /api/v1/analysis/site-layout` → `cad/site_layout_service`)이고 이 컴포넌트는
 * 표시와 대안 토글만 한다(프론트에서 동을 배치하거나 일조를 재판정하지 않는다).
 *
 * ★정직 표기(이 컴포넌트의 존재 이유):
 *   ① 서버 `honest_notes`(v1 한계: 축정렬 직사각형 동·균일 세트백·동지 일조 근사)를 **그대로** 옮긴다.
 *      이건 **부지 설계 대안이 아니라 볼륨 감**이라는 사실이 흐려지면 도면처럼 오독된다.
 *   ② `spacing_meaningful=false`(단일동)면 **인동간격을 표시하지 않는다** — 인접동이 없어
 *      개념 자체가 무의미한데 숫자를 보이면 오도다.
 *   ③ `ok:false`는 "0동"이 아니라 **산출 불가 + 서버 사유**로 표기한다(가짜 배치 금지).
 *   ④ 세대수·yield는 추정이므로 "추정" 라벨을 값에 붙인다.
 */

import { Building2 } from "lucide-react";

import {
  siteLayoutOptionKey,
  type SiteLayoutOption,
  type SiteLayoutResult,
} from "@/lib/site-layout";

export type ParcelLayoutStatus = "idle" | "loading" | "done" | "error";

export function ParcelLayoutSection({
  status,
  result,
  errorMessage,
  selectedOption,
  selectedKey,
  otherRequestInFlight,
  onRequest,
  onSelectOption,
  onSeedDesign,
}: {
  status: ParcelLayoutStatus;
  result?: SiteLayoutResult | null;
  errorMessage?: string | null;
  selectedOption?: SiteLayoutOption | null;
  selectedKey?: string | null;
  /** 다른 필지의 조회가 진행 중 — 지금 누르면 무시된다는 사실을 고지한다. */
  otherRequestInFlight?: boolean;
  onRequest: () => void;
  onSelectOption: (key: string) => void;
  /**
   * ★W4 매스 시드 인계 — "이 안으로 설계 시작". 표시 전용 섹션이므로 **저장·이동은 셸이** 한다
   *   (여기서 sessionStorage를 만지면 같은 로직이 소비처마다 흩어진다 — W2·W3와 동일 계약).
   *   미전달이면 CTA 자체를 그리지 않는다(죽은 버튼 금지).
   */
  onSeedDesign?: (option: SiteLayoutOption) => void;
}) {
  const options = result?.options ?? [];
  const notes = result?.honest_notes ?? [];

  return (
    <div
      data-testid="parcel-layout-section"
      className="col-span-2 border-t border-[var(--border-muted)] pt-2"
    >
      <div className="flex items-center justify-between gap-2">
        <dt className="flex items-center gap-1.5 font-black text-[var(--text-hint)]">
          <Building2 className="size-3.5 shrink-0" aria-hidden />
          배치 미리보기(볼륨 감)
        </dt>
        {status === "idle" || status === "error" ? (
          <button
            type="button"
            onClick={onRequest}
            data-testid="parcel-layout-request"
            /* ★모바일 IA P2(R1 봉합) — py-0.5+text-[10px] ≈ 18px 로 이 상세 패널에서 가장 작았다.
               필지 상세 팝오버 안이라 빗나간 탭이 팝오버 밖 지도로 샌다. */
            className="inline-flex min-h-11 shrink-0 items-center rounded-full border border-[var(--border-muted)] px-2 py-0.5 text-[10px] font-black text-[var(--accent-strong)] transition hover:bg-[var(--surface-muted)]"
          >
            {status === "error" ? "다시 조회" : "배치 조회"}
          </button>
        ) : null}
      </div>

      {status === "idle" ? (
        <p className="mt-1 text-[10px] font-semibold text-[var(--text-hint)]">
          미조회 — 대지 경계를 세트백 오프셋해 동을 배치해 봅니다(도면이 아니라 볼륨 감).
        </p>
      ) : null}

      {otherRequestInFlight ? (
        <p
          data-testid="parcel-layout-busy-other"
          className="mt-1 text-[10px] font-semibold text-[var(--status-warning)]"
        >
          다른 필지 배치를 조회하는 중입니다 — 끝난 뒤 다시 시도해 주세요.
        </p>
      ) : null}

      {status === "loading" ? (
        <p
          data-testid="parcel-layout-loading"
          className="mt-1 text-[11px] font-semibold text-[var(--text-hint)]"
        >
          배치 산출 중…
        </p>
      ) : null}

      {status === "error" ? (
        <p
          data-testid="parcel-layout-error"
          className="mt-1 break-keep text-[11px] font-semibold text-[var(--status-error)]"
        >
          {/* ★실패를 "0동"으로 표기하지 않는다(무날조). */}
          산출 불가 — {errorMessage || "배치를 산출하지 못했습니다."}
        </p>
      ) : null}

      {status === "done" && result && !result.ok ? (
        <div data-testid="parcel-layout-unavailable" className="mt-1">
          {/* ★서버가 폴리곤 미확보 등으로 ok:false를 주면 사유를 그대로 보여준다. */}
          <p className="break-keep text-[11px] font-semibold text-[var(--status-warning)]">
            배치 산출 불가 — 임의 배치를 만들지 않습니다.
          </p>
          {notes.map((n, i) => (
            <p key={i} className="mt-0.5 break-keep text-[10px] font-semibold text-[var(--text-hint)]">
              {n}
            </p>
          ))}
        </div>
      ) : null}

      {status === "done" && result?.ok && selectedOption ? (
        <>
          {/* ── 대안 토글: 서버가 낸 (유형×각도) 조합을 그대로 나열한다 ── */}
          {options.length > 1 ? (
            <div
              data-testid="parcel-layout-options"
              className="mt-1.5 flex flex-wrap gap-1"
              role="group"
              aria-label="배치 대안"
            >
              {options.map((o) => {
                const key = siteLayoutOptionKey(o);
                const active = key === (selectedKey ?? siteLayoutOptionKey(selectedOption));
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onSelectOption(key)}
                    aria-pressed={active}
                    data-testid={`parcel-layout-option-${key}`}
                    /* ★모바일 IA P2(R2 봉합) — 위 조회 버튼과 **완전히 같은 치수**(px-2 py-0.5
                       text-[10px] ≈ 18px)인데 미수정으로 남아 있었다. 조회 성공 뒤에만 렌더되는
                       대안 칩이라 스윕 상태(idle)에 안 잡혔다 — "검사는 있는데 대상이 DOM 에
                       없다"의 또 다른 사례. */
                    className={`inline-flex min-h-11 items-center rounded-full border px-2 py-0.5 text-[10px] font-black transition ${
                      active
                        ? "border-[var(--accent-strong)] text-[var(--accent-strong)]"
                        : "border-[var(--border-muted)] text-[var(--text-hint)] hover:bg-[var(--surface-muted)]"
                    }`}
                  >
                    {o.kind} {o.angle_deg}°
                  </button>
                );
              })}
            </div>
          ) : null}

          <dd className="mt-1.5 grid grid-cols-3 gap-x-2 text-center">
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)]">동수</p>
              <p
                data-testid="parcel-layout-buildings"
                className="font-mono font-bold text-[var(--text-primary)]"
              >
                {selectedOption.buildings}동
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)]">층수</p>
              <p className="font-mono font-bold text-[var(--text-primary)]">
                {selectedOption.floors}층
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)]">최고높이</p>
              <p className="font-mono font-bold text-[var(--text-primary)]">
                {selectedOption.height_m}m
              </p>
            </div>
          </dd>

          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {/* ★단일동이면 인동간격을 아예 표시하지 않는다(개념 무의미 — 오도 방지). */}
            {selectedOption.spacing_meaningful && selectedOption.spacing_m != null ? (
              <span
                data-testid="parcel-layout-spacing"
                className="rounded-full border border-[var(--border-muted)] px-1.5 py-px text-[10px] font-bold text-[var(--text-secondary)]"
              >
                인동간격 {selectedOption.spacing_m}m
              </span>
            ) : null}
            {selectedOption.daylight ? (
              <span
                data-testid="parcel-layout-daylight"
                className="rounded-full px-1.5 py-px text-[10px] font-black"
                style={{
                  color: selectedOption.daylight.meets_sunlight
                    ? "var(--status-success)"
                    : "var(--status-warning)",
                  border: `1px solid ${
                    selectedOption.daylight.meets_sunlight
                      ? "var(--status-success)"
                      : "var(--status-warning)"
                  }`,
                }}
                title="일조권 충족 판정(09~15 연속 2h 또는 08~16 총 4h) — 서버 근사"
              >
                일조 {selectedOption.daylight.meets_sunlight ? "충족" : "미충족"}
                {selectedOption.daylight.direct_sun_hours != null
                  ? ` · 직사광 ${selectedOption.daylight.direct_sun_hours}h`
                  : ""}
              </span>
            ) : null}
          </div>

          <dl className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
            {selectedOption.yield_pct != null ? (
              <div className="flex justify-between gap-1">
                <dt className="font-bold text-[var(--text-hint)]">연면적 실현율(추정)</dt>
                <dd
                  data-testid="parcel-layout-yield"
                  className="font-mono font-bold text-[var(--text-primary)]"
                >
                  {selectedOption.yield_pct}%
                </dd>
              </div>
            ) : null}
            {selectedOption.openness_pct != null ? (
              <div className="flex justify-between gap-1">
                <dt className="font-bold text-[var(--text-hint)]">오픈스페이스</dt>
                <dd className="font-mono font-bold text-[var(--text-primary)]">
                  {selectedOption.openness_pct}%
                </dd>
              </div>
            ) : null}
            {selectedOption.total_units_est != null ? (
              <div className="flex justify-between gap-1">
                <dt className="font-bold text-[var(--text-hint)]">세대수(추정)</dt>
                <dd className="font-mono font-bold text-[var(--text-primary)]">
                  {selectedOption.total_units_est}세대
                </dd>
              </div>
            ) : null}
            {result.buildable_area_sqm != null && result.setback_m != null ? (
              <div className="flex justify-between gap-1">
                <dt className="font-bold text-[var(--text-hint)]">건축가능(세트백 {result.setback_m}m)</dt>
                <dd className="font-mono font-bold text-[var(--text-primary)]">
                  {Math.round(result.buildable_area_sqm).toLocaleString()}㎡
                </dd>
              </div>
            ) : null}
          </dl>

          {/* ★W4 인계 CTA — 고른 안의 **층수만** 설계 시드로 넘긴다. 층수가 없으면 넘길 게
              없으므로 그리지 않는다(무날조). 문구에 "상한"을 박아, 이 값이 법정 용량을
              부풀리지 않는다는 사실이 화면에서도 드러나게 한다. */}
          {/* ★R2 MEDIUM-1: 부지 면적을 모르면 수신측이 **무조건 거부**한다(다필지 판정 불가).
              그 상태로 버튼을 그리면 눌러도 아무 일이 없는 죽은 버튼이 된다 — 아예 그리지 않고
              사유를 밝힌다. */}
          {onSeedDesign && selectedOption.floors > 0 && !(result.land_area_sqm ?? 0) ? (
            <p className="mt-2 break-keep border-t border-[var(--border-muted)] pt-2 text-[10px] font-semibold leading-relaxed text-[var(--text-hint)]">
              이 필지의 면적을 확인하지 못해 설계 인계는 제공하지 않습니다(다른 부지에 잘못
              적용되는 것을 막기 위함).
            </p>
          ) : null}
          {onSeedDesign && selectedOption.floors > 0 && (result.land_area_sqm ?? 0) > 0 ? (
            <div className="mt-2 border-t border-[var(--border-muted)] pt-2">
              <button
                type="button"
                data-testid="parcel-layout-seed-design"
                onClick={() => onSeedDesign(selectedOption)}
                /* ★모바일 IA P2(R2 봉합) — py-1.5+text-[11px] ≈ 27px 미달. 설계엔진에 시드를
                   넘기는 **상태 변경 액션**이라 오탭 비용이 크다. */
                className="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-[var(--accent-strong)] bg-[var(--accent-strong)]/10 px-2 py-1.5 text-[11px] font-black text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-strong)]/20"
              >
                이 안으로 설계 시작 ({selectedOption.kind} {selectedOption.floors}층)
              </button>
              <p className="mt-1 break-keep text-[10px] font-semibold leading-relaxed text-[var(--text-hint)]">
                고른 안의 층수를 설계 시드로 넘깁니다. 층수는 <b>상한으로만</b> 작용해 법정·조례
                한도를 넘겨 부풀리지 않습니다(한도가 더 엄격하면 한도가 적용). 동 배치 도형은
                넘어가지 않습니다 — 설계엔진이 풋프린트를 시드로 받지 않습니다.
              </p>
            </div>
          ) : null}

          {/* ★W3-b 정북 일조 이격 — 적용되면 수치를, 아니면 **사유를** 보여준다.
              밴드가 안 보이는 이유를 화면이 말하지 않으면 사용자는 "제약 없음"으로 읽는다. */}
          {result.north_light ? (
            <div
              data-testid="parcel-layout-north-light"
              className="mt-2 border-t border-[var(--border-muted)] pt-2"
            >
              {result.north_light.applies && selectedOption.north_light_setback_m ? (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-black text-[var(--text-hint)]">정북 일조 이격</span>
                    <span className="font-mono font-bold text-amber-500">
                      {selectedOption.north_light_setback_m}m
                    </span>
                  </div>
                  <p className="mt-1 break-keep text-[10px] font-semibold leading-relaxed text-[var(--text-hint)]">
                    지도의 주황 띠는 <b>{selectedOption.height_m}m 높이 기준</b>으로 건축할 수 없는
                    북측 영역입니다. 높이가 바뀌면 띠도 바뀝니다.
                  </p>
                </>
              ) : (
                <p className="break-keep text-[10px] font-semibold leading-relaxed text-[var(--text-hint)]">
                  {result.north_light.reason ?? "정북 일조 이격을 판정하지 못했습니다."}
                </p>
              )}
            </div>
          ) : null}

          {/* ★서버 honest_notes 원문 — v1 한계가 흐려지면 볼륨 감이 도면으로 오독된다. */}
          {notes.length > 0 ? (
            <div
              data-testid="parcel-layout-notes"
              className="mt-1.5 border-t border-[var(--border-muted)] pt-1.5"
            >
              {notes.map((n, i) => (
                <p
                  key={i}
                  className="break-keep text-[10px] font-semibold leading-relaxed text-[var(--text-hint)]"
                >
                  {n}
                </p>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export default ParcelLayoutSection;
