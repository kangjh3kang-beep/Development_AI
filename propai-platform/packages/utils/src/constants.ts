// PropAI v30.0 - 공유 상수

/** 1평 = 3.3058 ㎡ */
export const SQM_PER_PYEONG = 3.3058;

/** 프로젝트 상태 한글 라벨 */
export const PROJECT_STATUS_LABELS: Record<string, string> = {
  draft: '초안',
  planning: '기획',
  design: '설계',
  permit: '인허가',
  construction: '시공',
  completed: '완료',
  archived: '보관',
};

/** 사용자 역할 한글 라벨 */
export const USER_ROLE_LABELS: Record<string, string> = {
  admin: '관리자',
  manager: '매니저',
  analyst: '분석가',
  viewer: '조회자',
};

/** 에스크로 상태 한글 라벨 */
export const ESCROW_STATUS_LABELS: Record<string, string> = {
  pending_funding: '입금 대기',
  funded: '입금 완료',
  released: '방출',
  disputed: '분쟁',
  refunded: '환불',
  cancelled: '취소',
  failed: '실패',
};

/** 하자 심각도 한글 라벨 */
export const DEFECT_SEVERITY_LABELS: Record<string, string> = {
  EMERGENCY: '긴급',
  HIGH: '높음',
  MEDIUM: '보통',
  LOW: '낮음',
};

/** API 버전 */
export const API_VERSION = 'v1';

/** 페이지네이션 기본값 */
export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;
