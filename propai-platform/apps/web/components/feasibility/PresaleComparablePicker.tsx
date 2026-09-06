"use client";

/**
 * 분양사례에서 **평당 분양가를 골라 채우는** 입력 보조.
 *
 * 사용자 요청(2026-09-06): *«분양가는 **반경을 표시**하고 **목록화해 선택**하거나
 * **입력**할 수 있도록 해 분양가를 현실화해야 매출이 현실화되고 수지분석표가 정밀해진다»*
 *
 * ★**계수를 지어내지 않는다.** 도보 역세권·브랜드·향 프리미엄은 데이터로 안 잡히지만,
 *   **사용자가 사례를 고르면 그 프리미엄이 값에 이미 들어 있다.**
 *
 * ★**반경은 사용자가 고른다.** 라이브 실측(마석우리·24개월): 3km 0건 · 10km 0건 ·
 *   15km 4건 · 20km **28건**(최근접 10.6km). «3km 기본»으로 박으면 **아무것도 안 나온다.**
 *
 * ★표기는 **공급면적 기준 평당가** — 수지의 「평당 분양가」와 같은 눈금이다.
 *   (실거래 마커는 **전용** 기준이라 눈금이 다르다 — 그 혼동이 이번 신고의 절반이었다.)
 */

import { useState } from "react";

import {
  RADIUS_OPTIONS_M,
  fetchNearbyPresale,
  fetchPresaleModels,
  medianPerPyeong,
  type PresaleComparable,
} from "@/lib/presale-comparables";

export function PresaleComparablePicker({
  address,
  onPick,
}: {
  address: string;
  /** 고른 평당가(원/평·공급 기준)를 돌려준다. */
  onPick: (perPyeongWon: number, label: string) => void;
}) {
  const [radius, setRadius] = useState<number>(10000);
  const [items, setItems] = useState<PresaleComparable[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = async () => {
    if (busy) return;
    setBusy(true);
    setOpenId(null);
    try {
      const r = await fetchNearbyPresale(address, radius);
      setItems(r.items);
      setNote(r.note);
    } finally {
      setBusy(false);
    }
  };

  const expand = async (it: PresaleComparable) => {
    if (openId === it.house_manage_no) { setOpenId(null); return; }
    setOpenId(it.house_manage_no);
    if (it.models.length) return;
    const models = await fetchPresaleModels(it.house_manage_no, it.pblanc_no);
    setItems((prev) => prev.map((x) => x.house_manage_no === it.house_manage_no
      ? { ...x, models, median_per_pyeong_man: medianPerPyeong(models) } : x));
  };

  return (
    <div data-testid="presale-picker" className="mt-2 rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3">
      <div className="flex items-center gap-2">
        <p className="text-[11px] font-bold tracking-wider text-[var(--text-hint)]">
          주변 분양사례에서 고르기
        </p>
        <select
          data-testid="presale-radius"
          value={radius}
          onChange={(e) => setRadius(Number(e.target.value))}
          className="h-8 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--surface-strong)] px-2 text-xs text-[var(--text-primary)]"
        >
          {RADIUS_OPTIONS_M.map((m) => (
            <option key={m} value={m}>반경 {m / 1000}km</option>
          ))}
        </select>
        <button
          data-testid="presale-load"
          onClick={() => void load()}
          disabled={busy || !address.trim()}
          className="h-8 rounded-[var(--radius-sm)] border border-[var(--line)] px-3 text-xs font-semibold text-[var(--text-primary)] disabled:opacity-40"
        >
          {busy ? "조회 중…" : "조회"}
        </button>
      </div>

      {/* ★0건도 사유와 함께 말한다 — 「없다」와 「못 봤다」는 다르다. */}
      {!busy && items.length === 0 && (note || openId === null) && (
        <p data-testid="presale-empty" className="mt-2 text-[11px] text-[var(--text-hint)]">
          {note ?? `반경 ${radius / 1000}km 안에 분양 공고가 없습니다 — 반경을 넓혀 보세요.`}
        </p>
      )}

      {items.length > 0 && (
        <ul className="mt-2 space-y-1">
          {items.map((it) => (
            <li key={it.house_manage_no} className="rounded-md border border-[var(--line)] px-2 py-1.5">
              <button
                data-testid={`presale-item-${it.house_manage_no}`}
                onClick={() => void expand(it)}
                className="flex w-full items-center justify-between gap-2 text-left"
              >
                <span className="truncate text-xs font-semibold text-[var(--text-primary)]">
                  {it.name}
                </span>
                {/* ★거리를 항상 보여 준다 — 반경 안이라도 «얼마나 가까운가»가 판단을 가른다. */}
                <span className="shrink-0 text-[10px] text-[var(--text-hint)]">
                  {it.distance_m != null ? `${(it.distance_m / 1000).toFixed(1)}km` : "거리 미상"}
                </span>
              </button>

              {openId === it.house_manage_no && (
                <div className="mt-1.5 space-y-1">
                  {it.models.length === 0 && (
                    <p className="text-[10px] text-[var(--text-hint)]">주택형·분양가를 불러오는 중…</p>
                  )}
                  {it.models.map((m) => (
                    <div key={m.house_ty} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="text-[var(--text-secondary)]">
                        {m.house_ty} · 공급 {m.supply_area_m2?.toFixed(1) ?? "—"}㎡
                      </span>
                      {/* ★분양가가 없으면 **버튼을 주지 않는다** — 지어낸 값을 못 고르게. */}
                      {m.per_pyeong_man != null ? (
                        <button
                          data-testid={`presale-pick-${m.house_ty}`}
                          onClick={() => onPick(m.per_pyeong_man! * 10000,
                            `${it.name} ${m.house_ty}(공급 ${m.supply_area_m2?.toFixed(1)}㎡)`)}
                          className="shrink-0 rounded border border-[var(--accent-strong)] px-2 py-0.5 font-semibold text-[var(--accent-strong)]"
                        >
                          {m.per_pyeong_man.toLocaleString()}만원/평 적용
                        </button>
                      ) : (
                        <span className="shrink-0 text-[var(--text-hint)]">분양가 미공개</span>
                      )}
                    </div>
                  ))}
                  {it.median_per_pyeong_man != null && (
                    <p className="text-[10px] text-[var(--text-hint)]">
                      단지 중앙 {it.median_per_pyeong_man.toLocaleString()}만원/평(공급)
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
