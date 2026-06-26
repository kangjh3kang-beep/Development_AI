"use client";

/**
 * BuildableMassPreview — 법정 최대 건축가능 규모를 개략 3D 매스로 미리보기(P3.5 매스 백본 ②).
 *
 * SSOT(실효 용적률/건폐율·통합 대지면적)에서 파생해, 검증된 ProposalMassPreview(frameloop=demand·
 * autoRotate/HDR 금지·b5f216e 회귀가드)를 재사용한다. ★blind 3D 신작 아님 — 기존 매스 프리뷰에
 * '법정 최대 규모' 입력만 공급. 무거운 WebGL은 '3D 보기' 버튼 게이트로만 마운트(진입멈춤 방지).
 *
 * 근사: 건축면적=대지×건폐율, 연면적=대지×용적률, 최대층수=floor(용적률÷건폐율)(건폐율 만충 시 법정
 *   연면적 상한 — round가 아닌 floor로 법정 FAR 초과 매스 방지). 바닥은 정사각 근사(직사각형).
 *   정북일조·동간거리·정밀 층분할 미반영 → 정밀은 설계 스튜디오.
 *   가짜값 금지: 실효 한도/면적 미확보 시 미표시(null).
 */

import { useState } from "react";
import dynamic from "next/dynamic";
import { Box } from "lucide-react";

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

export function BuildableMassPreview({
  farPct, bcrPct, areaSqm,
}: {
  farPct?: number | null;
  bcrPct?: number | null;
  areaSqm?: number | null;
}) {
  const [open, setOpen] = useState(false);

  // 실효 한도·대지면적이 유효할 때만(가짜 규모 금지).
  if (!farPct || !bcrPct || !areaSqm || farPct <= 0 || bcrPct <= 0 || areaSqm <= 0) return null;

  const footprint = areaSqm * (bcrPct / 100);                // 건축면적(㎡) = 대지 × 건폐율
  // 최대 층수(근사) = floor(용적률 ÷ 건폐율). ★floor — round면 6층=300%>290% 식으로 법정 FAR를 초과하는
  //   매스를 그릴 수 있어, '법정 최대'를 표방하는 본 카드와 모순. floor로 법정 한도 내 보장.
  const floors = Math.max(1, Math.floor(farPct / bcrPct));
  const sideExact = Math.round(Math.sqrt(footprint));        // 정사각 근사 변길이(m) — 표기용(실측 근사)
  const side = Math.max(4, sideExact);                       // 3D 가시성 하한(소형 필지 1m 큐브 방지)

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <Box className="size-4 text-[var(--accent-strong)]" aria-hidden /> 법정 최대 매스 3D(근사)
        </p>
        <button onClick={() => setOpen((v) => !v)}
          className="rounded-lg border border-[var(--accent-strong)] bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-black text-white transition hover:opacity-90">
          {open ? "닫기" : "3D 보기"}
        </button>
      </div>
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
        건축면적 ~{Math.round(footprint).toLocaleString()}㎡(약 {sideExact}×{sideExact}m) · 최대 {floors}층(용적률÷건폐율 근사)
      </p>
      {open && (
        <div className="mt-2">
          <ProposalMassPreview width={side} depth={side} floors={floors} />
          <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-hint)]">
            ★법정 최대 규모의 직사각형 근사 매스(정밀 BIM 아님). 최대 층수=floor(용적률÷건폐율)·법정 한도 내 ·
            정북일조·동간거리 미반영. 정밀 매스·층분할·평면은 설계 스튜디오에서.
          </p>
        </div>
      )}
    </div>
  );
}
