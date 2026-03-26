// PropAI v30.0 - SSE 이벤트 타입 (부록 B 기준)

import type { TaskStatus, AgentStepName } from './enums';

/** SSE 이벤트 공통 필드 */
export interface SSEBaseEvent {
  event_id: string;
  timestamp: string;
}

/** 에이전트 오케스트레이션 진행 이벤트 */
export interface AgentProgressEvent extends SSEBaseEvent {
  type: 'agent_progress';
  project_id: string;
  step: AgentStepName;
  status: TaskStatus;
  progress_pct: number;
  message?: string;
}

/** 태스크 상태 변경 이벤트 */
export interface TaskStatusEvent extends SSEBaseEvent {
  type: 'task_status';
  task_id: string;
  status: TaskStatus;
  result?: unknown;
  error?: string | null;
}

/** 실시간 알림 이벤트 */
export interface NotificationEvent extends SSEBaseEvent {
  type: 'notification';
  user_id: string;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error';
  action_url?: string;
}

export type SSEEvent = AgentProgressEvent | TaskStatusEvent | NotificationEvent;
