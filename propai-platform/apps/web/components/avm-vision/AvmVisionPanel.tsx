"use client";

/**
 * Flagship B — 이미지융합 AVM (PoC) 패널.
 * 항공 정사영상(VWorld) + 추출 특징(영상분석/공간컨텍스트 추론) → 실험적 AVM 보정 전/후.
 *
 * ⚠ EXPERIMENTAL: 검증된 CNN/MAPE 주장 없음. 상한 ±8% 제한된 "참고용 실험 보정"이다.
 *   할루시네이션 방지 철학에 따라 가용값만 표시(null graceful)하고 폴백 사유를 note에 명시한다.
 */

import { useCallback, useState } from "react";
import { AlertTriangle, FlaskConical, Map, Satellite } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import type { AvmVisionResult, RoadFrontage } from "./types";

const VWORLD_API_KEY = process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? "";

const eok = (v: number | null | undefined) =>
  v == null ? "—" : `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 2 })}억`;
const won = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v).toLocaleString()}원`);
const pct1 = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

const ROAD_LABEL: Record<RoadFrontage, string> = { good: "양호", normal: "보통", poor: "불량" };
const ROAD_COLOR: Record<RoadFrontage, string> = { good: "#10b981", normal: "#f59e0b", poor: "#ef4444" };

/**
 * VWorld 항공영상 썸네일 URL.
 *
 * ★키 이원 계약(PR#329 R1 리뷰 HIGH 반영 — 정직 명시, `lib/vworld-client.ts` 상단
 *   독스트링과 동일 계약): 여기서 쓰는 `NEXT_PUBLIC_VWORLD_API_KEY`는 공개(도메인
 *   제한) 키 — 브라우저 노출을 전제로 발급되며 VWorld 콘솔의 Referer/도메인
 *   화이트리스트가 보호 기제다. 사통맵 타일 프록시가 쓰는 서버 전용 키
 *   (`VWORLD_API_KEY`)와는 별개 계약이며 섞이지 않는다.
 * getmap 엔드포인트는 Referer 헤더를 요구하므로 Next.js 프록시(/api/vworld/data?service=image)를 경유한다.
 * (브라우저 <img>는 Referer를 설정할 수 없어 직접 호출 시 403/빈응답 위험)
 */
function thumbUrl(center: [number, number], zoom: number): string | null {
  if (!VWORLD_API_KEY) return null;
  const [lon, lat] = center;
  const z = Math.max(7, Math.min(18, Math.round(zoom)));
  const qs = new URLSearchParams({
    service: "image",
    request: "getmap",
    basemap: "PHOTO",
    crs: "EPSG:4326",
    center: `${lon},${lat}`,
    zoom: String(z),
    size: "512,512",
    format: "png",
    version: "2.0",
    key: VWORLD_API_KEY,
  });
  return `/api/vworld/data?${qs.toString()}`;
}

function FeatureBar({ label, value, color }: { label: string; value: number; color: string }) {
  const w = Math.max(2, Math.min(100, Math.round(value * 100)));
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-[var(--text-tertiary)]">{label}</span>
        <span className="text-[11px] font-bold text-[var(--text-secondary)]">{pct1(value)}</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-[var(--surface-strong)]">
        <div className="h-2 rounded-full" style={{ width: `${w}%`, background: color }} />
      </div>
    </div>
  );
}

export function AvmVisionPanel({
  address,
  baseValueWon,
  baseValuePerSqmWon,
  pnu,
}: {
  /** 상위 화면(예상시세)에서 확보된 대상지 주소 */
  address?: string;
  /** 상위에서 산출된 기준값(있으면 재산출 없이 융합) */
  baseValueWon?: number | null;
  baseValuePerSqmWon?: number | null;
  pnu?: string | null;
}) {
  const [addr, setAddr] = useState(address ?? "");
  const [baseInput, setBaseInput] = useState<string>("");
  const [res, setRes] = useState<AvmVisionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [imgOk, setImgOk] = useState(true);

  const run = useCallback(async () => {
    const a = (addr || address || "").trim();
    if (!a && !pnu) {
      setErr("대상지 주소를 입력하세요.");
      return;
    }
    setBusy(true);
    setErr(null);
    setImgOk(true);
    try {
      const overrideBase = baseInput ? Number(baseInput.replace(/[^0-9.]/g, "")) : null;
      const d = await apiClient.post<AvmVisionResult>("/avm-vision/analyze", {
        body: {
          address: a || null,
          pnu: pnu ?? null,
          base_value_won: overrideBase ?? baseValueWon ?? null,
          base_value_per_sqm_won: baseValuePerSqmWon ?? null,
        },
      });
      if (d?.ok) setRes(d);
      else setErr(d?.message || "이미지융합 분석 실패 — 기준값·좌표를 확보하지 못했습니다.");
    } catch {
      setErr("분석 요청 실패 — 네트워크 확인 후 다시 시도하세요.");
    } finally {
      setBusy(false);
    }
  }, [addr, address, pnu, baseInput, baseValueWon, baseValuePerSqmWon]);

  const inp =
    "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)] outline-none";

  const f = res?.features;
  const img = res?.image;
  const adj = res?.adjustment_pct ?? 0;
  const up = adj > 0;
  const down = adj < 0;
  const adjColor = up ? "#10b981" : down ? "#ef4444" : "var(--text-tertiary)";
  const url = img?.available && img.center && img.zoom != null ? thumbUrl(img.center, img.zoom) : null;
  const isImageSrc = f?.source === "image";

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <Satellite className="size-6 text-[var(--text-secondary)]" aria-hidden />
            <div>
              <h2 className="flex items-center gap-2 text-base font-black text-[var(--text-primary)]">
                이미지융합 AVM
                <span className="rounded-full border border-violet-500/40 bg-violet-500/15 px-2 py-0.5 text-[10px] font-black tracking-widest text-violet-300">
                  EXPERIMENTAL
                </span>
              </h2>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                항공 정사영상·공간컨텍스트 특징으로 기준시세를 <b>상한 ±8%</b> 내에서 보정하는{" "}
                <b>참고용 실험 보정(PoC)</b>입니다. 검증된 가치 단정이 아닙니다.
              </p>
            </div>
          </div>
        </div>

        {/* 입력 */}
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="min-w-[240px] flex-1 text-xs text-[var(--text-secondary)]">
            대상지 주소
            <input
              className={`${inp} mt-1`}
              value={addr}
              onChange={(e) => setAddr(e.target.value)}
              placeholder="지번/도로명 주소"
            />
          </label>
          <label className="w-40 text-xs text-[var(--text-secondary)]">
            기준시세(원, 선택)
            <input
              className={`${inp} mt-1`}
              value={baseInput}
              onChange={(e) => setBaseInput(e.target.value)}
              placeholder={baseValueWon ? `상위 ${won(baseValueWon)}` : "미입력 시 자동"}
              inputMode="numeric"
            />
          </label>
          <button
            onClick={() => void run()}
            disabled={busy}
            className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "영상 분석 중…" : (<><Satellite className="size-4" aria-hidden /> 이미지융합 분석</>)}
          </button>
        </div>

        {err && (
          <p className="mt-3 flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            <AlertTriangle className="size-3.5 shrink-0" aria-hidden /> {err}
          </p>
        )}

        {res?.ok && (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {/* 항공 썸네일 / 특징 카드 */}
            <div className="grid gap-4">
              <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]">
                {url && imgOk ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={url}
                    alt="대상지 항공 정사영상(VWorld)"
                    width={512}
                    height={512}
                    className="h-auto w-full"
                    onError={() => setImgOk(false)}
                  />
                ) : (
                  <div className="flex aspect-square w-full flex-col items-center justify-center gap-2 p-6 text-center">
                    <Map className="size-8 text-[var(--text-tertiary)]" aria-hidden />
                    <p className="text-xs font-bold text-[var(--text-secondary)]">
                      {img?.available ? "영상 분석 완료(서버측)" : "항공영상 미취득"}
                    </p>
                    <p className="text-[11px] text-[var(--text-hint)]">
                      {img?.available
                        ? "썸네일 직접 표시는 생략되고 특징만 표시됩니다."
                        : "공간컨텍스트 추론(프록시)으로 보정합니다."}
                    </p>
                  </div>
                )}
                <div className="flex items-center justify-between gap-2 border-t border-[var(--line)] px-3 py-2">
                  <span className="text-[10px] text-[var(--text-hint)]">
                    {img?.source ? `출처 ${img.source}` : "항공영상 출처 없음"}
                  </span>
                  <span
                    className="rounded-full px-2 py-0.5 text-[10px] font-black"
                    style={{
                      color: isImageSrc ? "#a78bfa" : "#fbbf24",
                      background: isImageSrc ? "rgba(167,139,250,0.15)" : "rgba(251,191,36,0.15)",
                    }}
                  >
                    {isImageSrc ? "영상분석" : "공간컨텍스트 추론"}
                  </span>
                </div>
              </div>
            </div>

            {/* 추출 특징 */}
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
              <p className="mb-3 text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                추출 특징
              </p>
              <div className="grid gap-3">
                {f?.green_ratio != null && (
                  <FeatureBar label="식생비율(green)" value={f.green_ratio} color="#22c55e" />
                )}
                {f?.built_ratio != null && (
                  <FeatureBar label="시가화율(built)" value={f.built_ratio} color="#60a5fa" />
                )}
                {f?.edge_density != null && (
                  <FeatureBar label="개발강도(edge)" value={f.edge_density} color="#818cf8" />
                )}
                {f?.poi_density != null && (
                  <FeatureBar label="주변 POI 밀도" value={f.poi_density} color="#f472b6" />
                )}
                <div className="grid grid-cols-2 gap-2 pt-1">
                  {f?.road_frontage && (
                    <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2">
                      <p className="text-[10px] text-[var(--text-hint)]">도로 접면</p>
                      <p className="text-xs font-black" style={{ color: ROAD_COLOR[f.road_frontage] }}>
                        {ROAD_LABEL[f.road_frontage]}
                      </p>
                    </div>
                  )}
                  {f?.terrain && (
                    <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2">
                      <p className="text-[10px] text-[var(--text-hint)]">지세/형상</p>
                      <p className="text-xs font-bold text-[var(--text-secondary)]">{f.terrain}</p>
                    </div>
                  )}
                </div>
                {f?.detail && (
                  <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-hint)]">{f.detail}</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* AVM 보정 전/후 */}
        {res?.ok && (
          <div className="mt-4 rounded-xl border border-[var(--accent-strong)]/25 bg-[var(--accent-soft)] p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">기준시세</p>
                <p className="text-xl font-[1000] text-[var(--text-secondary)]">{eok(res.base_value_won)}</p>
              </div>
              <div className="flex flex-col items-center">
                <span className="text-2xl" style={{ color: adjColor }}>
                  →
                </span>
                <span className="text-sm font-black" style={{ color: adjColor }}>
                  {up ? "+" : ""}
                  {adj.toFixed(1)}%
                </span>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">
                  보정 후(실험)
                </p>
                <p className="text-2xl font-[1000]" style={{ color: adjColor }}>
                  {eok(res.adjusted_value_won)}
                </p>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-3">
              <span className="text-[11px] font-bold text-[var(--text-tertiary)]">신뢰도</span>
              <div className="h-2 flex-1 rounded-full bg-[var(--surface-strong)]">
                <div
                  className="h-2 rounded-full"
                  style={{
                    width: `${Math.round((res.confidence ?? 0) * 100)}%`,
                    background: res.confidence >= 0.5 ? "#3b82f6" : "#f59e0b",
                  }}
                />
              </div>
              <span className="text-xs font-[1000] text-[var(--text-secondary)]">
                {Math.round((res.confidence ?? 0) * 100)}%
              </span>
            </div>

            {res.rationale && (
              <p className="mt-3 rounded-lg border border-[var(--line)]/60 bg-[var(--surface-soft)] px-3 py-2 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                <b className="text-[var(--text-primary)]">보정 근거</b> · {res.rationale}
              </p>
            )}
          </div>
        )}

        {/* note · sources · 면책 */}
        {res?.ok && (res.note || res.sources?.length) && (
          <div className="mt-3 space-y-1.5">
            {res.note && (
              <p className="inline-flex items-start gap-1.5 rounded-lg border border-violet-500/25 bg-violet-500/10 px-3 py-2 text-[11px] leading-relaxed text-violet-200">
                <FlaskConical className="mt-0.5 size-3.5 shrink-0" aria-hidden />{res.note}
              </p>
            )}
            {res.sources?.length > 0 && (
              <p className="text-[10px] text-[var(--text-hint)]">출처 · {res.sources.join(" · ")}</p>
            )}
            <p className="text-[10px] leading-relaxed text-[var(--text-hint)]">
              ※ 본 보정은 실험적 PoC 결과로 법적·평가적 효력이 없으며, 참고 지표로만 활용하세요.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
