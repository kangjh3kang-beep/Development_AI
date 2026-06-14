"use client";

import { useEffect, useState } from "react";
import { apiV1BaseUrl } from "@/lib/api-client";
import type { AnnotatedSiteGeometry, LegalFinding } from "@/components/cad/types";

/**
 * §4-C 법규 준수 배치도 — 8엔진/설계 compliance findings를 배치도 SVG에 주석화해 표시한다.
 *
 * 백엔드 `/drawing/annotated-site-plan`(결정론)이 footprint 색·범례·정북일조 표시를 그린
 * SVG를 반환하면, 보안을 위해 Blob URL <img>로 렌더한다(dangerouslySetInnerHTML 미사용 —
 * img로 로드된 SVG는 스크립트 미실행). geometry가 없으면 아무것도 렌더하지 않는다(정직).
 */
export function AnnotatedSitePlanCard({
  geometry,
  findings,
  verdict,
}: {
  geometry: AnnotatedSiteGeometry | null;
  findings: LegalFinding[];
  verdict?: string | null;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!geometry) {
      setUrl(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setError(null);
    (async () => {
      try {
        const res = await fetch(`${apiV1BaseUrl()}/drawing/annotated-site-plan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...geometry, findings, verdict: verdict ?? null }),
          signal: AbortSignal.timeout(30000),
        });
        if (!res.ok) {
          if (!cancelled) setError("법규 주석 배치도를 불러오지 못했습니다.");
          return;
        }
        const svg = await res.text();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
        setUrl(objectUrl);
      } catch {
        if (!cancelled) setError("법규 주석 배치도 요청에 실패했습니다.");
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [geometry, findings, verdict]);

  if (!geometry) return null;

  return (
    <section className="mt-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-black text-[var(--text-primary)]">법규 준수 배치도</h4>
        <span className="text-[10px] font-bold text-[var(--text-hint)]">건폐·용적·일조 심사 주석</span>
      </div>
      {error ? (
        <p className="text-[11px] font-bold text-[var(--status-error)]" role="alert">
          {error}
        </p>
      ) : url ? (
        // eslint-disable-next-line @next/next/no-img-element -- Blob URL SVG는 next/image 비대상(보안상 img 로드)
        <img
          src={url}
          alt="법규 주석 배치도 — 건폐율·용적률·일조 심사 결과"
          className="w-full rounded-lg border border-[var(--line)] bg-white"
        />
      ) : (
        <p className="text-[11px] font-bold text-[var(--text-hint)]">배치도 생성 중…</p>
      )}
      <p className="mt-2 text-[10px] leading-tight text-[var(--text-tertiary)]">
        부지 경계는 대지면적 기반 개략(도식)이며 건물 치수는 설계 산출값(일부 미제공 시 면적 기반
        개략)입니다. 건폐/용적/일조 위반은 도면에 ✓/⚠/✗로 표기됩니다 — 보유 데이터 기반
        자동심사(보조)로 인허가권자 판단을 대체하지 않습니다.
      </p>
    </section>
  );
}
