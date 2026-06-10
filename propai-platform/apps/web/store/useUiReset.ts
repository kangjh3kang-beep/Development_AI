import { create } from "zustand";

/**
 * "홈으로" 전역 신호. 중앙분석센타/로고를 눌렀을 때 이미 같은 라우트(/{locale})에 있으면
 * Next <Link>는 리마운트하지 않아 분석뷰가 그대로 남는다. 이 nonce를 올려 대시보드 분석 패널이
 * 입력(랜딩) 상태로 리셋되도록 한다(새로고침 없이 본 홈화면 복귀).
 */
interface UiResetState {
  homeNonce: number;
  goHome: () => void;
}

export const useUiReset = create<UiResetState>((set) => ({
  homeNonce: 0,
  goHome: () => set((s) => ({ homeNonce: s.homeNonce + 1 })),
}));
