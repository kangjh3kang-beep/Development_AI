/**
 * PreCheck → 프로젝트 생성 핸드오프(경량 단일 출처).
 *
 * 새 라우트/스토어를 만들지 않고, 90초 PreCheck 결과(주소·용도지역·면적·추천
 * 개발방식)를 sessionStorage로 projects/new 한 화면에만 전달한다.
 *   - PreCheckWorkspace: 결과 ok일 때 CTA에서 write + projects/new로 router.push
 *   - NewProjectPage: mount 1회 read·소비(consume) 후 즉시 삭제(잔존 방지)
 *   - 경매(AuctionWorkspace)·G2B(G2BBidDashboard) "프로젝트 생성" CTA도 동일 경로 재사용
 *     (source/memo는 옵셔널 — 기존 작성·소비 코드 무수정 동작)
 */

export const PRECHECK_HANDOFF_KEY = "propai_precheck_handoff";

export interface PreCheckHandoff {
  address: string;
  zoneType: string | null;
  areaSqm: number | null;
  pnu: string | null;
  /** 추천 개발방식(예: "M06") */
  bestMethod: string | null;
  /** 추천 개발방식 한글명(예: "일반분양(공동주택)") */
  bestMethodName: string | null;
  /**
   * 핸드오프 출처 — 발굴(경매·G2B) 진입을 구분(미지정 시 precheck로 간주).
   * 옵셔널 추가 필드: consume 검증식(address만 검사)은 불변 → 구 핸드오프와 하위호환.
   */
  source?: "precheck" | "auction" | "g2b";
  /** 발굴 출처 메모(예: 온비드 물건관리번호, G2B 공고명) — projects/new 선채움용 */
  memo?: string | null;
}

/** 핸드오프를 sessionStorage에 기록한다(PreCheck·대시보드 체험분석 공용). 실패는 무시. */
export function writePreCheckHandoff(h: PreCheckHandoff): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(PRECHECK_HANDOFF_KEY, JSON.stringify(h));
  } catch {
    /* 무시 */
  }
}

/** projects/new에서 핸드오프를 1회 읽고 즉시 제거한다(consume). 실패는 무시. */
export function consumePreCheckHandoff(): PreCheckHandoff | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(PRECHECK_HANDOFF_KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(PRECHECK_HANDOFF_KEY);
    const parsed = JSON.parse(raw) as PreCheckHandoff;
    if (!parsed || typeof parsed.address !== "string" || !parsed.address.trim()) return null;
    return parsed;
  } catch {
    return null;
  }
}
