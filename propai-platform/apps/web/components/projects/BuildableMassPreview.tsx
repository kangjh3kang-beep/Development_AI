"use client";

/**
 * BuildableMassPreview — 건축가능 규모를 개략 3D 매스로 미리보기(P3.5 매스 백본 ②·D2).
 *
 * 두 모드를 토글로 제공:
 *  - 법정 최대: SSOT(실효 용적률/건폐율·통합 대지면적)에서 파생한 법정 한도 매스(기본).
 *  - 실측 대표: GET /api/v1/mass-templates(이 지역 같은 종류 건축물의 실측 중앙값)로 그린 매스.
 *    region(주소→시군구)에 실측 표본이 있을 때만 토글 노출 — 없으면 법정 최대만(graceful).
 *
 * 검증된 ProposalMassPreview(frameloop=demand·autoRotate/HDR 금지·b5f216e 회귀가드)를 재사용한다.
 * ★blind 3D 신작 아님 — 기존 매스 프리뷰에 규모 입력만 공급. 무거운 WebGL은 '3D 보기' 게이트로만 마운트.
 *
 * 근사: 건축면적=대지×건폐율, 최대층수=floor(용적률÷건폐율)(법정 FAR 초과 방지). 바닥은 정사각 근사.
 *   실측 모드: 층수는 실측 중앙값(median_floors) 우선. 정북일조·동간거리·정밀 층분할 미반영(설계 스튜디오).
 *   가짜값 금지: 한도/면적 미확보 시 미표시(null), 실측 표본 없으면 실측 모드 미노출.
 */

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Box } from "lucide-react";

import { apiClient } from "@/lib/api-client";
import { selectMassTemplate, validMassTemplates, type MassTemplate } from "@/lib/mass-template";

const ProposalMassPreview = dynamic(
  () => import("@/components/design/ProposalMassPreview").then((m) => m.ProposalMassPreview),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-64 w-full items-center justify-center rounded-lg border border-[var(--line)] text-xs text-[var(--text-hint)]">
        3D 매스 로딩…
      </div>
    ),
  },
);

type LookupResp = { region: string; count: number; templates: MassTemplate[] };

export function BuildableMassPreview({
  farPct, bcrPct, areaSqm, region,
}: {
  farPct?: number | null;
  bcrPct?: number | null;
  areaSqm?: number | null;
  region?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"legal" | "real">("legal");
  const [selectedType, setSelectedType] = useState<string | null>(null);  // 선택 건축물종류(미선택=대표)
  // 조회 결과를 '어느 region 것인지'와 함께 보관(전 종류 목록) → region 변경 시 stale은 match로 무시
  //   (effect 본문 동기 setState 없이 갱신; setState는 async 콜백에서만).
  const [fetched, setFetched] = useState<{ region: string; templates: MassTemplate[] } | null>(null);

  const r = (region ?? "").trim();

  // 이 지역 실측 매스(전 종류·표본수 내림차순) 조회 — region 있을 때만. 무자료/오류는 미표시(graceful).
  useEffect(() => {
    if (!r) return;
    let alive = true;
    apiClient
      .get<LookupResp>(`/mass-templates?region=${encodeURIComponent(r)}`)
      .then((resp) => {
        if (!alive) return;
        setFetched({ region: r, templates: resp?.templates ?? [] });
      })
      .catch(() => {
        if (alive) setFetched({ region: r, templates: [] });
      });
    return () => {
      alive = false;
    };
  }, [r]);

  // 실효 한도·대지면적이 유효할 때만(가짜 규모 금지).
  if (!farPct || !bcrPct || !areaSqm || farPct <= 0 || bcrPct <= 0 || areaSqm <= 0) return null;

  // 현재 region 매칭분만 사용(stale 무시) → 건폐·용적 유효 종류 목록 + 선택 종류(없으면 대표=첫).
  const valid = fetched && fetched.region === r ? validMassTemplates(fetched.templates) : [];
  const real = selectMassTemplate(valid, selectedType);   // selectedType가 valid에 없으면 대표로 자동 폴백
  const useReal = mode === "real" && !!real;
  const effBcr = useReal ? real!.median_bcr_pct! : bcrPct;
  const effFar = useReal ? real!.median_far_pct! : farPct;

  const footprint = areaSqm * (effBcr / 100);                // 건축면적(㎡) = 대지 × 건폐율
  // 층수: 실측 모드는 실측 중앙값(median_floors) 우선(실제 표본), 없으면 floor(용적률÷건폐율).
  //   ★floor — round면 법정 FAR를 초과하는 매스를 그릴 수 있어 '법정 최대' 표방과 모순.
  const floors =
    useReal && (real!.median_floors ?? 0) > 0
      ? Math.max(1, Math.round(real!.median_floors!))
      : Math.max(1, Math.floor(effFar / effBcr));
  const sideExact = Math.round(Math.sqrt(footprint));        // 정사각 근사 변길이(m) — 표기용(실측 근사)
  const side = Math.max(4, sideExact);                       // 3D 가시성 하한(소형 필지 1m 큐브 방지)

  const title = useReal ? "실측 대표 매스 3D(근사)" : "법정 최대 매스 3D(근사)";

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <Box className="size-4 text-[var(--accent-strong)]" aria-hidden /> {title}
        </p>
        <button onClick={() => setOpen((v) => !v)}
          className="rounded-lg border border-[var(--accent-strong)] bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-black text-white transition hover:opacity-90">
          {open ? "닫기" : "3D 보기"}
        </button>
      </div>

      {/* 실측 표본이 있을 때만 모드 토글 + 종류 선택 노출(없으면 법정 최대만) */}
      {valid.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-[var(--line)] p-0.5 text-[11px] font-bold">
            <button onClick={() => setMode("legal")}
              className={`rounded-md px-2 py-0.5 transition ${mode === "legal" ? "bg-[var(--accent-strong)] text-white" : "text-[var(--text-secondary)]"}`}>
              법정 최대
            </button>
            <button onClick={() => setMode("real")}
              className={`rounded-md px-2 py-0.5 transition ${mode === "real" ? "bg-[var(--accent-strong)] text-white" : "text-[var(--text-secondary)]"}`}>
              실측 대표
            </button>
          </div>
          {/* 실측 모드·종류 2개 이상일 때만 건축물종류 드롭다운(현재 선택 종류=real) */}
          {mode === "real" && valid.length > 1 && (
            <select
              aria-label="건축물종류 선택"
              value={real?.building_type ?? ""}
              onChange={(e) => setSelectedType(e.target.value)}
              className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[11px] font-bold text-[var(--text-primary)]"
            >
              {valid.map((t) => (
                <option key={t.building_type} value={t.building_type}>
                  {t.building_type} ({t.sample_count}표본)
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
        건축면적 ~{Math.round(footprint).toLocaleString()}㎡(약 {sideExact}×{sideExact}m) · {useReal ? "대표" : "최대"} {floors}층
        {useReal ? "(이 지역 실측 중앙값)" : "(용적률÷건폐율 근사)"}
      </p>

      {useReal && (
        <p className="mt-0.5 text-[10px] text-[var(--text-hint)]">
          실측 출처: {real!.building_type} {real!.sample_count}개 표본 · 건폐 {real!.median_bcr_pct}% · 용적 {real!.median_far_pct}%
          {(real!.median_floors ?? 0) > 0 ? ` · ${real!.median_floors}층` : ""}
        </p>
      )}

      {open && (
        <div className="mt-2">
          <ProposalMassPreview width={side} depth={side} floors={floors} />
          <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-hint)]">
            {useReal
              ? "★이 지역 같은 종류 건축물의 실측 중앙값을 이 부지 대지면적에 적용한 직사각형 근사 매스(정밀 BIM 아님)."
              : "★법정 최대 규모의 직사각형 근사 매스(정밀 BIM 아님). 최대 층수=floor(용적률÷건폐율)·법정 한도 내."}
            {" "}정북일조·동간거리 미반영. 정밀 매스·층분할·평면은 설계 스튜디오에서.
          </p>
        </div>
      )}
    </div>
  );
}
