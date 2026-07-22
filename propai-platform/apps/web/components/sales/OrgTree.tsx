"use client";

/**
 * 분양 조직도 — ltree 계층 트리 + 직속 지정 파이프라인(모바일 우선 UX).
 * 백엔드: GET /sales/org/tree · GET /sales/org/context · POST /sales/org/nodes
 *        · PATCH /sales/org/nodes/{id}/move
 *
 * ★[모바일 재설계(2026-07-23)] 과거 화면은 데스크톱 폼 문법(상위/직급/이름 3연 셀렉트 + 행마다
 *   '이동…' 셀렉트)이라 스마트폰에서 가독성·직관력이 무너졌다. 재설계 원칙:
 *   ① '내 조직' 카드 — 서버 /org/context 가 알려주는 내 직급·열람 범위·지정 가능 직급을 먼저 보여줘
 *      "내가 여기서 뭘 할 수 있는지"를 화면이 스스로 설명한다.
 *   ② 추가는 '노드에서 시작' — 전역 폼(상위 셀렉트) 대신 트리의 노드를 탭 → 액션시트 → "하위 추가".
 *      부모가 먼저 정해지므로 직급 선택지는 매트릭스∩위계 교집합만 남는다(서버가 거부할 선택지 제거).
 *   ③ 트리는 아코디언 — 하위가 많아도 접어서 스캔 가능. 행 전체가 터치 대상(44px).
 *   ④ 이동도 액션시트에서 — 행마다 붙던 '이동…' 셀렉트 제거(시각 소음 제거).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, ChevronDown, ChevronRight, Plus } from "lucide-react";
import { salesApi } from "@/lib/salesApi";
import { ApiClientError } from "@/lib/api-client";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import {
  NODE_TYPE_LABEL, ROLE_LABEL, nodeTypeOptions, nodeTypeLabel, orgRank, addableChildTypes,
} from "@/components/sales-app/roleConfig";

interface Node { id: string; path: string; node_type: string; display_name?: string | null }
/** GET /org/context 응답 — 프론트 게이팅의 서버 SSOT(권한 판단을 프론트가 재발명하지 않는다). */
interface OrgCtx { role: string; org_path: string; addable_types: string[]; scope: "site" | "subtree" }

// ★[정합(iter-6)] 로스터 표는 상위 N명만 그린다(긴 조직 잘림). 표시행 합(footer '행 합')은 반드시
//   '실제로 그린 행들'의 합과 일치해야 한다(과거엔 footer 가 서버 전체 로스터 합 roster_totals 를
//   썼는데, 31명+ 현장에선 화면 30행 합 ≠ footer 라 사용자가 데이터 오류로 오해했다). 표시상한과
//   합산을 순수 헬퍼로 분리해 화면·footer 가 같은 한 부를 쓰게 하고, 회귀를 테스트로 고정한다.
export const ROSTER_DISPLAY_LIMIT = 30;
type RosterRow = { contracts: number; customers: number; work_logs: number };
/** 주어진 로스터 행들의 활동 합계(계약·고객·업무일지) — 표시행 합/전체 합 어디서나 동일 규칙. */
export function sumRosterRows(rows: RosterRow[]): RosterRow {
  return rows.reduce(
    (acc, r) => ({
      contracts: acc.contracts + (r.contracts || 0),
      customers: acc.customers + (r.customers || 0),
      work_logs: acc.work_logs + (r.work_logs || 0),
    }),
    { contracts: 0, customers: 0, work_logs: 0 },
  );
}

// ★[라벨 SSOT(2026-07-22 봉합)] node_type→한국어 라벨 정본은 roleConfig.NODE_TYPE_LABEL 한 부.
// ★export: OrgTree.contract.test.ts 가 SSOT 패리티와 '트리배지=로스터표' 동일문자열을 회귀로 고정.
export const NODE_TYPES = nodeTypeOptions();
export const LABEL: Record<string, string> = { ...NODE_TYPE_LABEL }; // 방어적 복사(SSOT 원본 오염 차단)

/**
 * 이동 가능한 새 상위 후보 — 순수 헬퍼(테스트 고정).
 * 제외: 자기 자신, 자기 자손(순환 방지 — ltree 경계는 반드시 `path + "."` 로 비교한다:
 * 과거 `startsWith(n.path)` 는 "r.n1" 이 "r.n10" 을 자손으로 오인해 형제를 후보에서 잘못 제외했다),
 * 현재 부모(제자리 이동 무의미), 위계 위반(새 상위는 나보다 서열이 높아야 — 서버 400과 동일 술어).
 */
export function moveTargets(all: Node[], node: Node): Node[] {
  const parentPath = node.path.includes(".") ? node.path.slice(0, node.path.lastIndexOf(".")) : "";
  return all.filter((x) =>
    x.id !== node.id &&
    x.path !== node.path &&
    !x.path.startsWith(node.path + ".") &&
    x.path !== parentPath &&
    orgRank(x.node_type) < orgRank(node.node_type));
}

const fcls = "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export default function OrgTree({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [ctx, setCtx] = useState<OrgCtx | null>(null);
  const [busy, setBusy] = useState(false);
  // loaded: 조직도를 한 번 불러왔는지 표시(false면 '불러오는 중' 회색 자리표시를 보여줌).
  const [loaded, setLoaded] = useState(false);
  // 아코디언 펼침 상태(node.id 집합). 최초 로드 시 상위 2계층만 펼친다(긴 조직 스캔성).
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // 행 탭 → 액션시트. mode: 액션 목록 → 하위추가 폼 → 이동 대상 선택.
  const [sheet, setSheet] = useState<{ node: Node; mode: "actions" | "add" | "move" } | null>(null);
  // 최상위(대행사) 추가 폼 — 본사 권한(scope=site)에서만 노출.
  const [rootAdd, setRootAdd] = useState(false);
  const [newType, setNewType] = useState("");
  const [name, setName] = useState("");

  // Ov: 백엔드 TeamOverviewResponse(overview.py) 의 superset 중 프론트가 소비하는 키.
  // ★[혼동해소(iter-3)] totals(범위 안 전체 노드 합 — 본사 AGENCY/SUBAGENCY 귀속분 포함)와
  //   roster_totals(아래 표에 보이는 직급 행만의 합)를 둘 다 받아 화면에 명시한다.
  type Totals = { contracts: number; customers: number; work_logs: number };
  type Ov = { members: number; totals: Totals; roster_totals?: Totals; roster: { node_id: string; name: string; role_label: string; assigned: boolean; contracts: number; customers: number; work_logs: number; tax_type?: string }[] };
  const [ov, setOv] = useState<Ov | null>(null);
  // ★[정직성(iter-7)] team-overview 로드 실패를 화면에 명시한다(4xx=권한, 5xx/0=서버·연결).
  const [ovErr, setOvErr] = useState<{ kind: "auth" | "server"; status: number } | null>(null);
  // #5 해촉/정산 — 노드 수수료 정산 명세(기발생−기지급=미지급, 세금분개).
  type Settle = { tax_type: string; contracts: number; earned_gross: number; paid_gross: number; outstanding_gross: number; settlement: { withholding: number; vat: number; net: number; total_paid: number } };
  const [settle, setSettle] = useState<{ name: string; data: Settle } | null>(null);

  const load = useCallback(() => {
    api.get<Node[]>("/org/tree").then((r) => setNodes(r || [])).catch(() => setNodes([])).finally(() => setLoaded(true));
    // 컨텍스트 실패는 치명 아님 — 카드 미표시 + 추가 게이팅이 보수적(추가 버튼 숨김)으로 동작한다.
    api.get<OrgCtx>("/org/context").then((r) => setCtx(r)).catch(() => setCtx(null));
    api.get<Ov>("/org/team-overview")
      .then((r) => { setOv(r); setOvErr(null); })
      .catch((e) => {
        const status = e instanceof ApiClientError ? e.status : 0;
        setOv(null);
        setOvErr({ kind: status >= 400 && status < 500 ? "auth" : "server", status });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  const tree = useMemo(() => nodes.slice().sort((a, b) => a.path.localeCompare(b.path)), [nodes]);
  const depth = (p: string) => p.split(".").length - 1;
  // 서브트리 스코프 뷰(본부장 등)에선 내 노드가 depth>0 이어도 '이 화면의 루트'다 — 절대 depth 가
  // 아니라 화면 안 최소 depth 를 0 으로 보는 상대 계층으로 그린다.
  const minDepth = useMemo(() => tree.reduce((m, n) => Math.min(m, depth(n.path)), Infinity), [tree]);
  const level = (n: Node) => depth(n.path) - minDepth;
  const childrenOf = useCallback(
    (n: Node) => tree.filter((x) => x.path.startsWith(n.path + ".") && depth(x.path) === depth(n.path) + 1),
    [tree]);
  const roots = useMemo(() => tree.filter((n) => level(n) === 0), [tree]); // eslint-disable-line react-hooks/exhaustive-deps

  // 최초 로드(또는 조직 변경) 시 상위 2계층 펼침 — 이후 사용자의 접기/펼치기는 보존한다.
  useEffect(() => {
    setExpanded((prev) => {
      if (prev.size > 0) return prev;
      return new Set(tree.filter((n) => level(n) <= 1).map((n) => n.id));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree]);
  const toggle = (id: string) => setExpanded((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  // 내가 이 부모 아래에 추가할 수 있는 직급 — 서버 매트릭스(addable_types)∩위계.
  // ★[배포순서 회귀 방지] /org/context 는 이 트랙에서 신설된 엔드포인트라, 프론트(158)가 백엔드(168)
  //   보다 먼저 배포되면 404 → ctx=null 이 된다. 이때 빈 배열(fail-closed)로 두면 조직도 추가/이동
  //   기능이 통째로 사라지는 회귀이므로, ctx 실패 시엔 '구버전 동작'(전 직급 노출·위계 필터만)으로
  //   폴백한다 — 실제 권한 판정은 어차피 서버(매트릭스+위계+스코프)가 강제하므로 보안 저하가 아니다.
  const legacyAllTypes = NODE_TYPES.map((t) => t.value);
  const addableUnder = useCallback(
    (parentType: string | null) =>
      ctx ? addableChildTypes(ctx.addable_types, parentType)
        : legacyAllTypes.filter((t) => parentType === null || orgRank(t) > orgRank(parentType)),
    [ctx]); // eslint-disable-line react-hooks/exhaustive-deps
  const canAddRoot = ctx ? addableUnder(null).length > 0 && ctx.scope === "site" : true;
  // 이동 백엔드는 대행본사/시행사/총괄관리자 전용 — 그 외 역할에 눌러봤자 403 인 버튼을 숨긴다
  // (R1 MINOR). ctx 미로드(구백엔드)면 구버전처럼 노출하고 서버 판정에 위임한다.
  const canMove = ctx ? ["AGENCY", "DEVELOPER", "SUPERADMIN"].includes(ctx.role) : true;

  const addNode = async (parent: Node | null) => {
    if (!name.trim() || !newType) return;
    setBusy(true);
    try {
      await api.post("/org/nodes", { node_type: newType, parent_id: parent?.id, display_name: name.trim() });
      setName(""); setNewType(""); setSheet(null); setRootAdd(false);
      if (parent) setExpanded((prev) => new Set(prev).add(parent.id)); // 새 자식이 바로 보이게 펼침.
      load();
    } catch (e) { alert(e instanceof Error && e.message ? e.message : "추가 실패(권한을 확인하세요)"); }
    finally { setBusy(false); }
  };
  const move = async (node: Node, newParentId: string) => {
    try { await api.patch(`/org/nodes/${node.id}/move`, { new_parent_id: newParentId }); setSheet(null); load(); }
    catch (e) { alert(e instanceof Error && e.message ? e.message : "이동 실패(권한/순환 확인)"); }
  };
  const seedDefault = async () => {
    if (!confirm("기본조직(대행사→본부장→5팀×10명)을 생성할까요? 빈 조직에서만 가능합니다.")) return;
    setBusy(true);
    try {
      const r = await api.post<{ ok: boolean; total?: number; note?: string }>("/org/seed-default", {});
      if (r?.ok) load(); else alert(r?.note || "생성 실패");
    } catch { alert("기본조직 생성 실패(권한을 확인하세요)."); }
    finally { setBusy(false); }
  };
  const setTax = async (nodeId: string, taxType: string) => {
    try { await api.post("/commission/tax-pref", { node_id: nodeId, tax_type: taxType }); load(); }
    catch { alert("세금유형 저장 실패(권한 확인)"); }
  };
  // P2-3 인원배정: 같은 조직 사용자를 이메일로 노드에 배정/해제(미배정 해소).
  // ★UX 감사(2026-07-23) 지적 반영: 모바일에서 최악이던 브라우저 prompt() 대신 인라인 배정 시트
  //   (이메일 입력 폼)로 교체 — 결과/오류도 시트 안에 표시한다.
  const [assign, setAssign] = useState<{ nodeId: string; name: string; email: string; err: string | null; busy: boolean } | null>(null);
  const submitAssign = async () => {
    if (!assign || !assign.email.trim()) return;
    setAssign({ ...assign, busy: true, err: null });
    try {
      await api.post<{ name: string }>(`/org/nodes/${assign.nodeId}/assign`, { email: assign.email.trim() });
      setAssign(null); load();
    } catch (e) {
      setAssign((prev) => prev && { ...prev, busy: false, err: e instanceof Error && e.message ? e.message : "배정 실패(같은 조직 가입자인지 확인하세요)" });
    }
  };
  const unassignUser = async (nodeId: string) => {
    if (!confirm("이 인원 배정을 해제할까요? (노드·실적은 유지)")) return;
    try { await api.post(`/org/nodes/${nodeId}/unassign`, {}); load(); }
    catch (e) { alert(e instanceof Error && e.message ? e.message : "해제 실패"); }
  };
  const loadSettle = async (nodeId: string, name2: string) => {
    try { const d = await api.get<Settle>(`/commission/settle-summary?node_id=${nodeId}`); setSettle({ name: name2, data: d }); }
    catch (e) { alert(e instanceof Error && e.message ? e.message : "정산 명세 조회 실패"); }
  };
  const won = (n: number) => `${(n || 0).toLocaleString()}원`;

  // 오버레이(액션시트/배정/정산) 오픈 중 배경 스크롤 잠금 — 닫히면 해제(R1 MINOR).
  // FieldNav 시트에서 배운 교훈: CSS 로만 숨기면 body 부수효과가 남는다 — 상태로 잠그고 cleanup.
  const anyOverlay = !!(sheet || assign || settle);
  useEffect(() => {
    if (!anyOverlay) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [anyOverlay]);

  // ★표시행(상위 N명)과 그 합을 한 번만 계산해, 표 본문(.map)과 footer '행 합'이 같은 한 부를 쓴다.
  const rosterAll = ov?.roster ?? [];
  const rosterShown = rosterAll.slice(0, ROSTER_DISPLAY_LIMIT);
  const shownTotals = sumRosterRows(rosterShown);
  const isTruncated = rosterAll.length > rosterShown.length;
  const tNonZero = (t?: Totals) => !!t && (t.contracts > 0 || t.customers > 0 || t.work_logs > 0);
  const hasOvData = !!ov && (ov.members > 0 || tNonZero(ov.totals) || tNonZero(ov.roster_totals));

  /** 하위추가 폼(공용) — 부모 고정 + 직급 칩(허용 교집합만) + 이름. sheet/루트 양쪽에서 사용.
   * ★렌더 '함수'로 호출한다(JSX 컴포넌트 금지) — 컴포넌트를 함수 안에서 정의해 <AddForm/> 으로
   *   쓰면 렌더마다 컴포넌트 정체성이 바뀌어 입력 필드가 매 키입력마다 재마운트(포커스 소실)된다. */
  const renderAddForm = (parent: Node | null) => {
    const types = addableUnder(parent ? parent.node_type : null);
    return (
      <div className="space-y-3">
        <p className="text-xs text-[var(--text-tertiary)]">
          상위: <b className="text-[var(--text-primary)]">{parent ? `${nodeTypeLabel(parent.node_type)} ${parent.display_name ?? ""}` : "최상위(현장 직속)"}</b>
        </p>
        <div>
          <p className="mb-1.5 text-[10px] text-[var(--text-tertiary)]">직급 (내 권한으로 지정 가능한 직급만 표시)</p>
          <div className="flex flex-wrap gap-1.5">
            {types.map((t) => (
              <button key={t} onClick={() => setNewType(t)}
                className={`min-h-9 rounded-full border px-3 text-xs font-bold ${newType === t
                  ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                  : "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)]"}`}>
                {nodeTypeLabel(t)}
              </button>
            ))}
          </div>
        </div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="이름 (예: 김본부)"
          className={`${fcls} w-full`} onKeyDown={(e) => { if (e.key === "Enter") void addNode(parent); }} />
        <button onClick={() => addNode(parent)} disabled={busy || !name.trim() || !newType}
          className="min-h-11 w-full rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-black text-white disabled:opacity-40">
          ＋ 추가
        </button>
      </div>
    );
  };

  /** 트리 한 행 — 행 전체 터치(44px). 좌측 셰브론=접기/펼치기, 행 탭=액션시트. */
  const renderRow = (n: Node) => {
    const kids = childrenOf(n);
    const open = expanded.has(n.id);
    return (
      <div key={n.id}>
        <div className="flex min-h-11 items-center gap-1 rounded-lg hover:bg-[var(--surface)]"
          style={{ paddingLeft: `${Math.min(level(n), 4) * 14}px` }}>
          {kids.length > 0 ? (
            <button onClick={() => toggle(n.id)} aria-label={open ? "접기" : "펼치기"} aria-expanded={open}
              className="flex size-9 shrink-0 items-center justify-center text-[var(--text-tertiary)]">
              {open ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
            </button>
          ) : <span className="size-9 shrink-0" />}
          <button onClick={() => { setRootAdd(false); setNewType(""); setName(""); setSheet({ node: n, mode: "actions" }); }}
            className="flex min-h-11 min-w-0 flex-1 items-center gap-2 text-left">
            <span className="shrink-0 rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-xs font-semibold text-[var(--accent-strong)]">{LABEL[n.node_type] ?? n.node_type}</span>
            <span className="truncate text-sm font-semibold text-[var(--text-primary)]">{n.display_name ?? "-"}</span>
            {kids.length > 0 && <span className="shrink-0 text-[10px] text-[var(--text-hint)]">하위 {kids.length}</span>}
          </button>
        </div>
        {open && kids.map((k) => renderRow(k))}
      </div>
    );
  };

  // 처음 불러오는 중이면 회색 자리표시(스켈레톤)로 빈 화면 깜빡임을 막는다.
  if (!loaded) return <SkeletonLoader count={3} itemClassName="h-16 rounded-xl mb-3" />;
  const sheetTypes = sheet ? addableUnder(sheet.node.node_type) : [];
  const sheetMoveTargets = sheet && canMove ? moveTargets(tree, sheet.node) : [];
  return (
    <div className="space-y-4">
      {/* ① 내 조직 카드 — 내 직급·열람 범위·지정 가능 직급(서버 /org/context SSOT). */}
      {ctx && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 sm:p-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-[var(--accent-soft)] px-2.5 py-1 font-black text-[var(--accent-strong)]">{ROLE_LABEL[ctx.role] ?? ctx.role}</span>
            <span className="text-[var(--text-tertiary)]">{ctx.scope === "site" ? "전체 조직 열람" : "내 하위 조직만 열람"}</span>
          </div>
          <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">
            {ctx.addable_types.length > 0 ? (
              <>지정 가능 직급: {ctx.addable_types.map((t) => <b key={t} className="mr-1 text-[var(--text-primary)]">{nodeTypeLabel(t)}</b>)}
                <span className="text-[var(--text-hint)]"> — 조직 노드를 탭해 하위를 추가하세요.</span></>
            ) : "조직원 지정 권한이 없는 직급입니다(열람 전용)."}
          </p>
        </div>
      )}

      {/* ★[정직성(iter-7)] team-overview 로드 실패를 숨기지 않고 인라인 안내. 권한(4xx)/서버(5xx) 구분. */}
      {ovErr && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 text-xs text-[var(--text-secondary)]">
          {ovErr.kind === "auth" ? (
            <span>팀 현황을 볼 권한이 없거나 현장 접근이 만료되었습니다(코드 {ovErr.status}). 현장 재진입 또는 관리자에게 권한을 확인하세요.</span>
          ) : (
            <span>팀 현황을 불러오지 못했습니다(서버 오류{ovErr.status ? ` 코드 ${ovErr.status}` : "·연결 실패"}). 잠시 후 다시 시도하세요.</span>
          )}
        </div>
      )}

      {/* P2-3 팀 현황(내 하위 조직 활동 집계) */}
      {hasOvData && ov && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          {/* 헤더는 '전체 합(totals)' — 아래 표의 행 합과 다를 수 있어 '전체 합(본사 포함)'을 명시. */}
          <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            <span className="font-bold text-[var(--text-secondary)]">팀 현황(하위 조직)</span>
            <span className="text-[var(--text-tertiary)]">관리대상 <b className="text-[var(--text-primary)]">{ov.members}</b>명</span>
            <span className="text-[var(--text-tertiary)]">전체 계약 <b className="text-[var(--accent-strong)]">{ov.totals.contracts}</b></span>
            <span className="text-[var(--text-tertiary)]">전체 고객 <b className="text-[var(--accent-strong)]">{ov.totals.customers}</b></span>
            <span className="text-[var(--text-tertiary)]">전체 업무일지 <b className="text-[var(--accent-strong)]">{ov.totals.work_logs}</b></span>
            <span className="text-[9px] text-[var(--text-hint)]">전체 합(본사 포함)</span>
          </div>
          <div className="max-h-40 overflow-auto">
            <table className="w-full min-w-[560px] text-[11px]">
              <thead><tr className="text-[var(--text-hint)]"><th className="text-left font-medium">직급</th><th className="text-left font-medium">이름</th><th className="text-center font-medium">인원</th><th className="text-right font-medium">계약</th><th className="text-right font-medium">고객</th><th className="text-right font-medium">업무일지</th><th className="text-right font-medium">수수료세금</th><th className="text-center font-medium">정산</th></tr></thead>
              <tbody>
                {rosterShown.map((r, i) => (
                  // 미배정 행은 흐리게 — '아직 사람이 연결 안 된 자리'를 시각으로 구분(배정 버튼은 선명 유지).
                  <tr key={i} className={`border-t border-[var(--line)]/50 ${r.assigned ? "" : "opacity-60"}`}>
                    <td className="py-0.5 text-[var(--text-tertiary)]">{r.role_label}</td>
                    <td className="text-[var(--text-secondary)]">{r.name}{!r.assigned && <span className="ml-1 text-[9px] text-[var(--text-hint)]">(미배정)</span>}</td>
                    <td className="text-center">
                      {r.assigned ? (
                        <button onClick={() => unassignUser(r.node_id)} className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[9px] text-[var(--text-tertiary)]" title="배정 해제">해제</button>
                      ) : (
                        <button onClick={() => setAssign({ nodeId: r.node_id, name: r.name, email: "", err: null, busy: false })} className="rounded border border-[var(--accent-strong)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--accent-strong)] opacity-100">배정</button>
                      )}
                    </td>
                    <td className="text-right text-[var(--text-primary)]">{r.contracts}</td>
                    <td className="text-right text-[var(--text-primary)]">{r.customers}</td>
                    <td className="text-right text-[var(--text-primary)]">{r.work_logs}</td>
                    <td className="text-right"><select value={r.tax_type || "WITHHOLDING"} onChange={(e) => setTax(r.node_id, e.target.value)} className="rounded border border-[var(--line)] bg-[var(--surface-strong)] px-1 py-0.5 text-[10px] text-[var(--text-secondary)]"><option value="WITHHOLDING">3.3% 원천</option><option value="VAT">부가세10%</option></select></td>
                    <td className="text-center"><button onClick={() => loadSettle(r.node_id, r.name)} className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-secondary)]" title="해촉/정산 명세">정산</button></td>
                  </tr>
                ))}
              </tbody>
              {/* ★[정합(iter-6)] footer '행 합'은 반드시 '실제로 그린 행(상위 N명)'의 합(shownTotals). */}
              <tfoot>
                <tr className="border-t-2 border-[var(--line)] font-bold text-[var(--text-secondary)]">
                  <td className="py-0.5" colSpan={3}>행 합(표시 {rosterShown.length}명)</td>
                  <td className="text-right text-[var(--text-primary)]">{shownTotals.contracts}</td>
                  <td className="text-right text-[var(--text-primary)]">{shownTotals.customers}</td>
                  <td className="text-right text-[var(--text-primary)]">{shownTotals.work_logs}</td>
                  <td colSpan={2} />
                </tr>
                {/* 표가 잘린 경우에만(전체 > 표시) 서버 전체 로스터 합을 별도 행으로 명시. */}
                {isTruncated && ov.roster_totals && (
                  <tr className="border-t border-[var(--line)] text-[var(--text-tertiary)]">
                    <td className="py-0.5" colSpan={3}>로스터 전체 합({rosterAll.length}명)</td>
                    <td className="text-right">{ov.roster_totals.contracts}</td>
                    <td className="text-right">{ov.roster_totals.customers}</td>
                    <td className="text-right">{ov.roster_totals.work_logs}</td>
                    <td colSpan={2} />
                  </tr>
                )}
              </tfoot>
            </table>
          </div>
          {isTruncated && (
            <p className="mt-1 text-[10px] font-semibold text-[var(--text-tertiary)]">
              상위 {rosterShown.length}명 표시 (총 {rosterAll.length}명) — 표 하단 <b>로스터 전체 합</b>은 전체 인원 기준입니다.
            </p>
          )}
          <p className="mt-1 text-[10px] text-[var(--text-hint)]">
            ※ 헤더 <b>전체 합</b>은 범위 안 전체 노드(본사 대행본사·대행지사 귀속 포함) 합계,
            표 하단 <b>행 합</b>은 <b>위 표에 보이는 행</b>(상위 {rosterShown.length}명)만의 합계입니다.
            인원이 많아 일부만 표시된 경우 <b>로스터 전체 합</b>(전체 직급 인원)을 함께 표기합니다 —
            본사에 직접 귀속된 실적이 있으면 전체 합이 더 클 수 있습니다.
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-hint)]">근태·수수료·단체메시지는 각 전용 탭(수수료·방문 데스크·소셜)에서 관리합니다.</p>
        </div>
      )}

      {/* ③ 조직 트리(아코디언). 헤더에 최상위(대행사) 추가 — 본사 권한(scope=site)에서만. */}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 sm:p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-bold text-[var(--text-secondary)]">조직 트리</span>
          {canAddRoot && (
            <button onClick={() => { setRootAdd((v) => !v); setNewType(""); setName(""); }}
              className="inline-flex min-h-9 items-center gap-1 rounded-lg border border-[var(--accent-strong)] px-2.5 text-xs font-black text-[var(--accent-strong)]">
              <Plus className="size-3.5" aria-hidden /> 대행사 추가
            </button>
          )}
        </div>
        {rootAdd && canAddRoot && (
          <div className="mb-3 rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3">{renderAddForm(null)}</div>
        )}
        {tree.length === 0 && (
          <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-[var(--text-secondary)]">
              조직 노드가 없습니다. {canAddRoot ? "위 '대행사 추가'로 최상위부터 만들거나, 기본조직을 한 번에 생성하세요." : "관리자가 조직을 구성하면 여기에 표시됩니다."}
            </p>
            {canAddRoot && (
              <button onClick={seedDefault} disabled={busy}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--accent-strong)] px-3 text-xs font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50">
                <Building2 className="size-4" aria-hidden /> 기본조직 생성 (대행사→본부장→5팀×10명)
              </button>
            )}
          </div>
        )}
        <div className="space-y-0.5">{roots.map((n) => renderRow(n))}</div>
      </div>
      <p className="text-[11px] text-[var(--text-hint)]">계층(대행본사＞대행지사＞본부장＞이사＞팀장＞직원)은 수수료 2단 배분의 기준이 됩니다. 이동 시 하위 조직도 함께 이동합니다.</p>

      {/* ②④ 행 액션시트 — 모바일은 하단 시트, 데스크톱(sm+)은 중앙 카드. */}
      {sheet && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center" onClick={() => setSheet(null)}>
          <div className="w-full rounded-t-2xl border border-[var(--line)] bg-[var(--surface)] p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-[var(--shadow-lg)] sm:mx-4 sm:max-w-md sm:rounded-2xl sm:pb-4"
            onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-2 font-black text-[var(--text-primary)]">
                <span className="rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-xs font-semibold text-[var(--accent-strong)]">{LABEL[sheet.node.node_type] ?? sheet.node.node_type}</span>
                {sheet.node.display_name ?? "-"}
              </h3>
              <button onClick={() => setSheet(null)} aria-label="닫기" className="flex size-9 items-center justify-center text-[var(--text-tertiary)]">✕</button>
            </div>
            {sheet.mode === "actions" && (
              <div className="space-y-1.5">
                {sheetTypes.length > 0 && (
                  <button onClick={() => { setNewType(sheetTypes.length === 1 ? sheetTypes[0] : ""); setName(""); setSheet({ ...sheet, mode: "add" }); }}
                    className="flex min-h-12 w-full items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 text-left text-sm font-bold text-[var(--text-primary)]">
                    <Plus className="size-4 text-[var(--accent-strong)]" aria-hidden />
                    여기에 하위 추가
                    <span className="ml-auto text-[10px] font-normal text-[var(--text-hint)]">{sheetTypes.map(nodeTypeLabel).join("·")}</span>
                  </button>
                )}
                {sheetMoveTargets.length > 0 && (
                  <button onClick={() => setSheet({ ...sheet, mode: "move" })}
                    className="flex min-h-12 w-full items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 text-left text-sm font-bold text-[var(--text-primary)]">
                    <ChevronRight className="size-4 text-[var(--text-tertiary)]" aria-hidden />
                    다른 상위로 이동
                  </button>
                )}
                {sheetTypes.length === 0 && sheetMoveTargets.length === 0 && (
                  <p className="py-2 text-center text-xs text-[var(--text-tertiary)]">이 노드에서 할 수 있는 조직 작업이 없습니다(권한/위계).</p>
                )}
              </div>
            )}
            {sheet.mode === "add" && renderAddForm(sheet.node)}
            {sheet.mode === "move" && (
              <div className="max-h-72 space-y-1 overflow-auto">
                <p className="mb-1 text-[10px] text-[var(--text-tertiary)]">새 상위를 선택하세요 (하위 조직도 함께 이동합니다)</p>
                {sheetMoveTargets.map((x) => (
                  <button key={x.id} onClick={() => move(sheet.node, x.id)}
                    className="flex min-h-11 w-full items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 text-left text-sm text-[var(--text-primary)]"
                    style={{ paddingLeft: `${12 + Math.min(depth(x.path) - minDepth, 4) * 12}px` }}>
                    <span className="rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--accent-strong)]">{LABEL[x.node_type] ?? x.node_type}</span>
                    <span className="truncate">{x.display_name ?? "-"}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 인원배정 시트 — prompt() 대체(모바일 우선). 이메일 입력·오류를 시트 안에서 처리. */}
      {assign && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center" onClick={() => setAssign(null)}>
          <div className="w-full rounded-t-2xl border border-[var(--line)] bg-[var(--surface)] p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-[var(--shadow-lg)] sm:mx-4 sm:max-w-md sm:rounded-2xl sm:pb-4"
            onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-black text-[var(--text-primary)]">인원 배정 — {assign.name}</h3>
              <button onClick={() => setAssign(null)} aria-label="닫기" className="flex size-9 items-center justify-center text-[var(--text-tertiary)]">✕</button>
            </div>
            <div className="space-y-3">
              <input type="email" value={assign.email} autoFocus
                onChange={(e) => setAssign({ ...assign, email: e.target.value })}
                onKeyDown={(e) => { if (e.key === "Enter") void submitAssign(); }}
                placeholder="배정할 사용자 이메일(같은 조직 가입자)" className={`${fcls} w-full`} />
              {assign.err && <p className="text-xs text-[var(--status-error,#D05050)]">{assign.err}</p>}
              <button onClick={submitAssign} disabled={assign.busy || !assign.email.trim()}
                className="min-h-11 w-full rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-black text-white disabled:opacity-40">
                배정
              </button>
            </div>
          </div>
        </div>
      )}

      {/* #5 해촉/정산 명세 모달 */}
      {settle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setSettle(null)}>
          <div className="mx-4 w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 shadow-[var(--shadow-lg)]" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-black text-[var(--text-primary)]">해촉/정산 명세 — {settle.name}</h3>
              <button onClick={() => setSettle(null)} className="text-[var(--text-tertiary)]">✕</button>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">계약 기여</span><b className="text-[var(--text-primary)]">{settle.data.contracts}건</b></div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">기발생 수수료</span><b className="text-[var(--text-primary)]">{won(settle.data.earned_gross)}</b></div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">기지급</span><b className="text-emerald-400">{won(settle.data.paid_gross)}</b></div>
              <div className="flex justify-between border-t border-[var(--line)] pt-1.5"><span className="font-bold text-[var(--text-primary)]">미지급 정산액</span><b className="text-[var(--accent-strong)]">{won(settle.data.outstanding_gross)}</b></div>
              <div className="mt-2 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-2.5 text-xs">
                <p className="mb-1 font-bold text-[var(--text-secondary)]">{settle.data.tax_type === "VAT" ? "부가세 10%(세금계산서)" : "원천징수 3.3%(사업소득)"}</p>
                {settle.data.tax_type === "VAT" ? (
                  <>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">부가세</span><span>{won(settle.data.settlement.vat)}</span></div>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">지급총액(공급가+부가세)</span><b>{won(settle.data.settlement.total_paid)}</b></div>
                  </>
                ) : (
                  <>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">원천징수(3.3%)</span><span className="text-rose-400">−{won(settle.data.settlement.withholding)}</span></div>
                    <div className="flex justify-between"><span className="text-[var(--text-tertiary)]">실수령</span><b className="text-[var(--accent-strong)]">{won(settle.data.settlement.net)}</b></div>
                  </>
                )}
              </div>
              <p className="mt-1 text-[10px] text-[var(--text-hint)]">※ 환수(계약취소)분 제외·기발생 기준. 자금이체는 시스템이 수행하지 않습니다(명세 산출).</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
