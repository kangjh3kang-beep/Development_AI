"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { apiClient, ApiClientError } from "@/lib/api-client";

/* ──────────────────────────────────────────────────────────────
   나라장터(G2B) 입찰공고 상세 모달
   - 목록 카드 클릭 → 이 모달이 풍부한 공식 상세페이지급 정보를 표시
   - 하단 "AI 정밀 입찰 분석" CTA → onAnalyze(bidId, bidName)로 분석 모달 연결
   - 백엔드 GET /api/v1/g2b/bids/{bidId}/detail 의 detail 섹션을 점진 렌더
   - detail이 없는 구버전 백엔드에서는 기본 6필드 + 두 버튼으로 graceful fallback
   ────────────────────────────────────────────────────────────── */

/* ── 백엔드 계약 타입 ── */
type LabeledItem = { label: string; value: string };
type G2BAttachment = { name: string; url: string };
type G2BContact = {
  org?: string | null;
  demand_org?: string | null;
  name?: string | null;
  tel?: string | null;
  email?: string | null;
  exec_name?: string | null;
  opening_place?: string | null;
};
type G2BDetailSections = {
  general: LabeledItem[];
  restriction: LabeledItem[];
  schedule: LabeledItem[];
  price: LabeledItem[];
  attachments: G2BAttachment[];
  contact: G2BContact;
  links: Record<string, string>;
};
type G2BBidDetail = {
  id: string;
  bid_notice_no: string;
  bid_notice_nm: string;
  bid_type: string;
  org_name: string;
  org_type?: string | null;
  estimated_price?: number | null;
  region_sido?: string | null;
  region_sigungu?: string | null;
  bid_close_dt?: string | null;
  g2b_url?: string | null;
  status: string;
  award_rate?: number | null;
  bid_count?: number | null;
  detail: G2BDetailSections;
};

/* 목록에서 이미 보유한 기본필드(즉시 표시용 시드) */
export type G2BBidSeed = {
  id: string;
  bid_notice_no: string;
  bid_notice_nm: string;
  bid_type: string;
  org_name: string;
  org_type: string | null;
  estimated_price: number | null;
  bid_close_dt: string | null;
  region_sido: string | null;
  status: string;
  award_rate?: number | null;
  g2b_url: string | null;
};

/* ── 유틸 ── */
function formatKRW(v: number | null | undefined): string {
  if (v == null) return "-";
  if (Math.abs(v) >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(1)}억원`;
  if (Math.abs(v) >= 1_0000) return `${(v / 1_0000).toFixed(0)}만원`;
  return `${v.toLocaleString()}원`;
}

function daysUntil(dt: string | null | undefined): number | null {
  if (!dt) return null;
  const diff = new Date(dt).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

function ddayMeta(dt: string | null | undefined): { text: string; cls: string } | null {
  const days = daysUntil(dt);
  if (days == null) return null;
  if (days < 0) return { text: "마감", cls: "bg-[var(--surface-strong)] text-[var(--text-hint)] border-[var(--line)]" };
  if (days === 0) return { text: "D-DAY", cls: "bg-[var(--status-error)]/20 text-[var(--status-error)] border-[var(--status-error)]/40 animate-pulse" };
  if (days <= 3) return { text: `D-${days}`, cls: "bg-[var(--status-error)]/20 text-[var(--status-error)] border-[var(--status-error)]/40 animate-pulse" };
  if (days <= 7) return { text: `D-${days}`, cls: "bg-[var(--status-warning)]/20 text-[var(--status-warning)] border-[var(--status-warning)]/40" };
  return { text: `D-${days}`, cls: "bg-[var(--surface-strong)] text-[var(--text-secondary)] border-[var(--line)]" };
}

/* 첫 링크 우선순위로 나라장터 상세 링크 결정 */
function pickG2bUrl(detail?: G2BDetailSections | null, fallback?: string | null): string | null {
  if (detail?.links) {
    const links = detail.links;
    return links.g2b_detail || links.g2b || links.detail || fallback || null;
  }
  return fallback || null;
}

/* 담당자 카드에 표시할 항목이 하나라도 있는지 */
function hasContact(c?: G2BContact | null): boolean {
  if (!c) return false;
  return Boolean(c.org || c.demand_org || c.name || c.tel || c.email || c.exec_name || c.opening_place);
}

export function G2BBidDetailModal({
  seed,
  onClose,
  onAnalyze,
}: {
  /** 목록에서 클릭한 카드의 기본 필드(즉시 표시) */
  seed: G2BBidSeed;
  onClose: () => void;
  /** 하단 CTA → 기존 AI 정밀분석 모달 오픈 */
  onAnalyze: (bidId: string, bidName: string) => void;
}) {
  const [detail, setDetail] = useState<G2BBidDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 상세 엔드포인트는 기존 요약(/g2b/bids/{id})과 충돌을 피해 /detail 하위 경로로 신설됨.
      const data = await apiClient.get<G2BBidDetail>(`/g2b/bids/${seed.id}/detail`);
      setDetail(data);
    } catch (e) {
      // detail 없는 구버전(404 등)은 에러가 아니라 fallback 처리.
      // 그 외 네트워크/서버 오류만 정직하게 표기(가짜 데이터 금지).
      if (e instanceof ApiClientError && e.status === 404) {
        setDetail(null);
      } else {
        setError("상세 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
      }
    } finally {
      setLoading(false);
    }
  }, [seed.id]);

  useEffect(() => { fetchDetail(); }, [fetchDetail]);

  // 표시값: detail 도착 시 우선, 미도착 시 seed로 폴백(점진 렌더)
  const title = detail?.bid_notice_nm ?? seed.bid_notice_nm;
  const bidType = detail?.bid_type ?? seed.bid_type;
  const estimated = detail?.estimated_price ?? seed.estimated_price;
  const closeDt = detail?.bid_close_dt ?? seed.bid_close_dt;
  const bidNo = detail?.bid_notice_no ?? seed.bid_notice_no;
  const dday = ddayMeta(closeDt);
  const sections = detail?.detail ?? null;
  const g2bUrl = pickG2bUrl(sections, detail?.g2b_url ?? seed.g2b_url);

  // 키보드 ESC 닫기 + 스크롤 락
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4"
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-label={`입찰공고 상세 ${title}`}
      >
        <motion.div
          initial={{ scale: 0.96, y: 24 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 24 }}
          transition={{ type: "spring", stiffness: 320, damping: 30 }}
          className="cc-bracketed relative flex w-full max-w-3xl flex-col max-h-[90vh] overflow-hidden rounded-[var(--radius-md)] border-2 border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-2xl ring-1 ring-black/40"
          onClick={(e) => e.stopPropagation()}
        >
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--tr" />
          <i className="cc-bracket cc-bracket--bl" />
          <i className="cc-bracket cc-bracket--br" />

          {/* ── 헤더 ── */}
          <header className="relative overflow-hidden border-b border-[var(--line)] bg-[var(--surface-soft)] px-6 py-5">
            <div className="cc-grid-bg opacity-40" />
            <div className="relative z-10 flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="cc-meta">G2B · BID DETAIL</span>
                  <span className="cc-live"><i />LIVE</span>
                </div>
                <h2 className="text-lg font-[900] leading-snug text-[var(--text-primary)]">{title}</h2>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-black text-[var(--accent-strong)]">{bidType}</span>
                  {dday && <span className={`rounded-md border px-2 py-0.5 text-[11px] font-black ${dday.cls}`}>{dday.text}</span>}
                  <span className="cc-num text-[var(--text-hint)] text-[11px] font-bold">공고 {bidNo}</span>
                </div>
              </div>
              <button
                onClick={onClose}
                aria-label="닫기"
                className="cc-interactive shrink-0 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 text-2xl leading-none text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                ×
              </button>
            </div>
            {/* 추정가격 강조 */}
            <div className="relative z-10 mt-4 flex items-baseline gap-2">
              <span className="cc-label">ESTIMATED PRICE</span>
              <span className="cc-num cc-num--data text-2xl font-[1000] tracking-tight">{formatKRW(estimated)}</span>
            </div>
          </header>

          {/* ── 본문(스크롤) ── */}
          <div className="relative flex-1 overflow-y-auto px-6 py-5">
            {loading && <DetailSkeleton />}

            {!loading && error && (
              <div className="rounded-[var(--radius-md)] border border-[var(--status-error)]/40 bg-[var(--status-error)]/10 p-4 text-sm text-[var(--status-error)]">
                {error}
                <button
                  onClick={fetchDetail}
                  className="ml-2 underline underline-offset-2 hover:opacity-80"
                >
                  다시 시도
                </button>
              </div>
            )}

            {!loading && !error && (
              <div className="space-y-5">
                {/* fallback: detail 없으면 기본 6필드만 */}
                {!sections && (
                  <Section label="공고 개요">
                    <ItemGrid
                      items={[
                        { label: "발주기관", value: seed.org_name },
                        { label: "기관유형", value: seed.org_type || "-" },
                        { label: "지역", value: seed.region_sido || "전국" },
                        { label: "입찰마감", value: closeDt ? new Date(closeDt).toLocaleString("ko-KR") : "-" },
                        { label: "공고번호", value: bidNo },
                        { label: "상태", value: seed.status },
                      ]}
                    />
                  </Section>
                )}

                {/* 1. 공고일반 */}
                {sections && sections.general.length > 0 && (
                  <Section label="공고 일반">
                    <ItemGrid items={sections.general} />
                  </Section>
                )}

                {/* 2. 투찰제한·자격 (경고 톤) */}
                {sections && sections.restriction.length > 0 && (
                  <Section label="투찰제한 · 자격">
                    <div className="space-y-2">
                      {sections.restriction.map((it, i) => (
                        <div
                          key={`${it.label}-${i}`}
                          className="flex items-start justify-between gap-3 rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/8 px-3.5 py-2.5"
                        >
                          <span className="cc-label shrink-0 text-[var(--status-warning)]">{it.label}</span>
                          <span className="text-right text-sm font-semibold text-[var(--text-primary)]">{it.value}</span>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {/* 3. 입찰진행 일정 (타임라인) */}
                {sections && sections.schedule.length > 0 && (
                  <Section label="입찰진행 일정">
                    <ol className="relative space-y-3 border-l border-[var(--line)] pl-5">
                      {sections.schedule.map((it, i) => (
                        <li key={`${it.label}-${i}`} className="relative">
                          <span className="absolute -left-[1.4rem] top-1 h-2.5 w-2.5 rounded-full border-2 border-[var(--data-accent)] bg-[var(--surface-strong)]" />
                          <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <span className="text-sm font-bold text-[var(--text-primary)]">{it.label}</span>
                            <span className="cc-num text-xs font-semibold text-[var(--text-secondary)]">{it.value}</span>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </Section>
                )}

                {/* 4. 가격·관급 */}
                {sections && sections.price.length > 0 && (
                  <Section label="가격 · 관급">
                    <div className="space-y-2">
                      {sections.price.map((it, i) => (
                        <div
                          key={`${it.label}-${i}`}
                          className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3.5 py-2.5"
                        >
                          <span className="cc-label">{it.label}</span>
                          <span className="cc-num cc-num--data text-sm font-[900]">{it.value}</span>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {/* 5. 첨부파일 */}
                {sections && sections.attachments.length > 0 && (
                  <Section label="첨부파일">
                    <div className="space-y-1.5">
                      {sections.attachments.map((f, i) => (
                        <a
                          key={`${f.url}-${i}`}
                          href={f.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="cc-interactive flex items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] hover:border-[var(--accent-strong)]/40"
                        >
                          <span className="text-base shrink-0" aria-hidden>📎</span>
                          <span className="min-w-0 flex-1 truncate font-semibold">{f.name}</span>
                          <span className="cc-meta shrink-0 text-[var(--accent-strong)]">↓</span>
                        </a>
                      ))}
                    </div>
                  </Section>
                )}

                {/* 6. 담당자·기관 */}
                {sections && hasContact(sections.contact) && (
                  <Section label="담당자 · 기관">
                    <div className="grid gap-3 sm:grid-cols-2">
                      {sections.contact.org && <ContactTile label="공고기관" value={sections.contact.org} />}
                      {sections.contact.demand_org && <ContactTile label="수요기관" value={sections.contact.demand_org} />}
                      {sections.contact.name && <ContactTile label="담당자" value={sections.contact.name} />}
                      {sections.contact.tel && <ContactTile label="연락처" value={sections.contact.tel} href={`tel:${sections.contact.tel}`} />}
                      {sections.contact.email && <ContactTile label="이메일" value={sections.contact.email} href={`mailto:${sections.contact.email}`} />}
                      {sections.contact.exec_name && <ContactTile label="집행관" value={sections.contact.exec_name} />}
                      {sections.contact.opening_place && <ContactTile label="개찰장소" value={sections.contact.opening_place} full />}
                    </div>
                  </Section>
                )}
              </div>
            )}
          </div>

          {/* ── 하단 액션바 ── */}
          <footer className="flex items-center gap-3 border-t border-[var(--line)] bg-[var(--surface-soft)] px-6 py-4">
            {g2bUrl ? (
              <a
                href={g2bUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] py-3 text-center text-sm font-bold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)] hover:border-[var(--accent-strong)]/40"
              >
                나라장터에서 입찰하기 →
              </a>
            ) : (
              <span className="flex-1 rounded-xl border border-dashed border-[var(--line)] py-3 text-center text-xs font-semibold text-[var(--text-hint)]">
                나라장터 링크 미제공
              </span>
            )}
            <button
              onClick={() => onAnalyze(seed.id, title)}
              className="flex-[1.4] rounded-xl bg-[var(--accent-strong)] py-3 text-center text-sm font-black text-white shadow-[var(--shadow-md)] transition hover:opacity-90"
            >
              🧠 AI 정밀 입찰 분석
            </button>
          </footer>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

/* ── 섹션 래퍼(cc-panel) ── */
function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="cc-panel">
      <header className="cc-panel__head">
        <span className="cc-meta">{label}</span>
      </header>
      <div className="cc-panel__body">{children}</div>
    </section>
  );
}

/* ── LabeledItem 그리드 ── */
function ItemGrid({ items }: { items: LabeledItem[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map((it, i) => (
        <div key={`${it.label}-${i}`} className="min-w-0">
          <p className="cc-label mb-1">{it.label}</p>
          <p className="cc-num break-words text-sm font-bold text-[var(--text-primary)]">{it.value}</p>
        </div>
      ))}
    </div>
  );
}

/* ── 담당자 타일(연락처는 링크) ── */
function ContactTile({ label, value, href, full = false }: { label: string; value: string; href?: string; full?: boolean }) {
  const body = href ? (
    <a href={href} className="cc-interactive break-words text-sm font-bold text-[var(--accent-strong)] hover:underline">{value}</a>
  ) : (
    <p className="break-words text-sm font-bold text-[var(--text-primary)]">{value}</p>
  );
  return (
    <div className={`rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-3 ${full ? "sm:col-span-2" : ""}`}>
      <p className="cc-label mb-1">{label}</p>
      {body}
    </div>
  );
}

/* ── 로딩 스켈레톤(cc-grid-bg) ── */
function DetailSkeleton() {
  return (
    <div className="relative space-y-4">
      <div className="cc-grid-bg opacity-30" />
      {[0, 1, 2].map((i) => (
        <div key={i} className="relative rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="mb-3 h-2.5 w-24 animate-pulse rounded bg-[var(--surface-strong)]" />
          <div className="grid gap-3 sm:grid-cols-2">
            {[0, 1, 2, 3].map((j) => (
              <div key={j} className="space-y-1.5">
                <div className="h-2 w-16 animate-pulse rounded bg-[var(--surface-strong)]" />
                <div className="h-3.5 w-28 animate-pulse rounded bg-[var(--surface-strong)]" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default G2BBidDetailModal;
