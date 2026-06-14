"use client";

/**
 * SP2-5 프로젝트 회의방 랜딩 — 좌측 사이드바 "설계 참고 > 프로젝트 회의방" 진입점.
 *
 * 단일출처 useProjectStore(드롭다운·프로젝트 관리와 공유)를 재사용해 프로젝트를 리스트로 배치하고,
 * 각 프로젝트를 해당 회의방(/projects/{id}/collaboration)으로 연결한다. 새 데이터 fetch·가짜 목록 없음.
 */

import Link from "next/link";
import { useEffect } from "react";
import { useProjectStore } from "@/store/useProjectStore";

export function MeetingRoomsListClient({ locale }: { locale: string }) {
  const projects = useProjectStore((s) => s.projects);
  const syncing = useProjectStore((s) => s.syncing);
  const syncFromBackend = useProjectStore((s) => s.syncFromBackend);

  useEffect(() => {
    void syncFromBackend();
  }, [syncFromBackend]);

  return (
    <div data-testid="meeting-rooms" className="flex flex-col gap-3">
      {projects.length === 0 ? (
        <p
          data-testid="meeting-rooms-empty"
          className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 text-sm text-[var(--text-hint)]"
        >
          {syncing
            ? "프로젝트를 불러오는 중…"
            : "회의방을 열 프로젝트가 없습니다. 프로젝트를 먼저 생성하세요."}
        </p>
      ) : (
        <ul className="grid gap-3">
          {projects.map((p) => (
            <li key={p.id}>
              <Link
                data-testid="meeting-room-link"
                href={`/${locale}/projects/${p.id}/collaboration`}
                className="flex items-center justify-between gap-4 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4 transition-all hover:-translate-y-0.5 hover:border-[var(--accent-strong)]/40 hover:bg-[var(--surface)]"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-black text-[var(--text-primary)]">
                    {p.name || p.address || "(이름 없음)"}
                  </p>
                  {p.address && (
                    <p className="mt-0.5 truncate text-xs text-[var(--text-hint)]">{p.address}</p>
                  )}
                </div>
                <span className="shrink-0 rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[11px] font-black text-[var(--accent-strong)]">
                  회의방 입장 →
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
