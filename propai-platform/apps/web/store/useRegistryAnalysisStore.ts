import { create } from "zustand";
import { persist } from "zustand/middleware";
import { createAccountScopedStorage } from "@/lib/account-scoped-storage";

/**
 * 필지별 **등기 권리분석 결과** 보관 — 프로젝트별 영속.
 *
 * ## 왜 필요한가 (2026-08-24 사용자 신고)
 *
 * *"이전에는 하단에 필지별 권리분석 리스트가 있고 상세를 누르면 볼 수 있었는데 사라졌다."*
 *
 * 사라진 게 아니라 **처음부터 휘발성이었다.** 그 리스트는 화면 상태(`batchResults`)에만
 * 있었고 아무 데도 저장되지 않았다. 그래서:
 *  · 새로고침하면 없어진다
 *  · 토지조서에서 `?addr=` 로 들어오면 단건 조회만 돌아 리스트가 아예 안 만들어진다
 *    (사용자 스크린샷의 URL 이 정확히 이 경우다)
 *  · **개별 `분석` 버튼으로 한 필지씩 돌리면 리스트에 쌓이지도 않았다** — 전체 분석만 쌓았다
 *
 * 필지당 1,200원이 나가는 산출물이 새로고침 한 번에 화면에서 사라지는 것은 결함이다.
 * 필지 행(`useLandScheduleStore`)은 이미 영속인데 **분석 결과만** 안 남아 있었다.
 *
 * ## 왜 서버에서 복원하지 않는가 (의도적 선택)
 *
 * 서버에는 성공한 분석이 7일 캐시로 남아 있어 "주소 목록을 주면 캐시된 분석을 돌려주는"
 * 조회 전용 엔드포인트를 만들 수도 있었다. **만들지 않았다** — 그 캐시는 테넌트 공유라,
 * 무과금 조회 통로를 열면 **임의 주소를 넣어 소유자 정보를 수확**할 수 있게 된다.
 * 지금은 캐시 미스 때 드는 발급 비용이 그 남용을 막는 유일한 문턱이다.
 * 사용자 자기 화면의 자기 결과를 되살리는 데 새 노출면을 만들 이유가 없다.
 */

/** 저장하는 분석 결과. 화면 목록·상세가 쓰는 만큼만 담는다(원본 전문은 담지 않는다). */
export type StoredAnalysis = {
  jibun: string;
  rowId: string;
  /** `/registry/analyze` 응답. null 이면 요청 자체가 실패한 건. */
  result: Record<string, unknown> | null;
  /** 저장 시각(ISO) — 언제 분석분인지 화면이 말할 수 있어야 한다. */
  savedAt: string;
};

/** 활성 프로젝트가 없을 수 있다 — 그 경우도 `_default` 로 담아 결과를 버리지 않는다. */
export type ProjectKey = string | null | undefined;

type State = {
  byProject: Record<string, StoredAnalysis[]>;
  /** 한 필지 결과를 넣거나 갱신한다(같은 rowId 는 덮어쓴다 — 재분석이 쌓이지 않게). */
  upsert: (projectId: ProjectKey, item: Omit<StoredAnalysis, "savedAt">) => void;
  /** 필지 행이 삭제되면 그 결과도 지운다(유령 행 방지). */
  remove: (projectId: ProjectKey, rowId: string) => void;
  clear: (projectId: ProjectKey) => void;
};

/**
 * persist 이름 — **레거시 공유키 그대로**다. 실제 저장키는 `createAccountScopedStorage` 가
 * 읽기/쓰기 시점에 `__<uid>` 를 붙여 만든다(`propai-registry-analysis__<userId>`).
 *
 * ★이름을 바꾸지 않는 이유: 이 값은 **레거시 원본을 읽는 주소**이기도 하다. 바꾸면 계정별
 *   키로 옮겨 가기 전의 등기 권리분석 결과이 **고아**가 된다 — 사용자가 이미 낸 돈이다.
 */
export const REGISTRY_ANALYSIS_STORE_KEY = "propai-registry-analysis";

const KEY = (projectId: ProjectKey) => projectId || "_default";

export const useRegistryAnalysisStore = create<State>()(
  persist(
    (set) => ({
      byProject: {},

      upsert: (projectId, item) =>
        set((s) => {
          const k = KEY(projectId);
          const cur = s.byProject[k] ?? [];
          const next = cur.filter((x) => x.rowId !== item.rowId);
          // 순서는 **분석한 순서**를 유지한다(행 순서로 재정렬하면 방금 돌린 것이 어디 갔는지 모른다).
          next.push({ ...item, savedAt: new Date().toISOString() });
          return { byProject: { ...s.byProject, [k]: next } };
        }),

      remove: (projectId, rowId) =>
        set((s) => {
          const k = KEY(projectId);
          const cur = s.byProject[k];
          if (!cur) return s;
          return { byProject: { ...s.byProject, [k]: cur.filter((x) => x.rowId !== rowId) } };
        }),

      clear: (projectId) =>
        set((s) => {
          const k = KEY(projectId);
          if (!s.byProject[k]) return s;
          const rest = { ...s.byProject };
          delete rest[k];
          return { byProject: rest };
        }),
    }),
    { name: REGISTRY_ANALYSIS_STORE_KEY, storage: createAccountScopedStorage<State>() },
  ),
);
