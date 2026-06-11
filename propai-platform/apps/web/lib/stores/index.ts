/**
 * Zustand 스토어 재내보내기.
 *
 * 실제 스토어는 apps/web/store/ 에 위치.
 * lib/stores/ 경로로 접근하는 코드를 위한 프록시.
 */
export { useAppStore } from "../../store/use-app-store";
export { useProjectStore } from "../../store/use-project-store";
