/** CAD 파라메트릭 에디터 타입 정의. */

export type CadPoint = {
  id: string;
  x: number;
  y: number;
  label?: string;
};

export type CadLine = {
  id: string;
  startPointId: string;
  endPointId: string;
};

export type CadPolygon = {
  id: string;
  pointIds: string[];
  fill: string;
  label?: string;
};

export type CadTool = "select" | "point" | "line" | "polygon";

export type CadState = {
  points: CadPoint[];
  lines: CadLine[];
  polygons: CadPolygon[];
  floorCount: number;
  buildingHeightM: number;
  scale: number;
};

export type CadSnapshot = Readonly<CadState>;

/** 백엔드 POST /api/v1/building-compliance/check 요청 바디. */
export type DesignPayload = {
  points: Array<{ id: string; x: number; y: number }>;
  lines: Array<{ id: string; startPointId: string; endPointId: string }>;
  surfaces: Array<{ id: string; pointIds: string[] }>;
  floor_count: number;
  building_height_m: number;
  scale: number;
};

export type ComplianceViolation = {
  violation_type: string;
  severity: "error" | "warning";
  message: string;
  current_value: number;
  limit_value: number;
};

export type ComplianceCheckResponse = {
  is_compliant: boolean;
  violations: ComplianceViolation[];
  building_coverage_ratio: { current: number; limit: number; pass: boolean };
  floor_area_ratio: { current: number; limit: number; pass: boolean };
  max_height: { current: number; limit: number; pass: boolean };
  setback: { current: number; limit: number; pass: boolean };
  sunlight: { current: number; limit: number; pass: boolean };
};

export type ComplianceCheckRequest = {
  project_id: string;
  design: DesignPayload;
};

/** 대시보드 분석용 타입. */
export type InvestmentFeature = {
  feature: string;
  score: number;
  maxScore: number;
};

export type InvestmentMetrics = {
  features: InvestmentFeature[];
  avm_estimate_krw: number;
  avm_confidence: number;
  irr_percent: number;
  cap_rate_percent: number;
  noi_krw: number;
  monthly_trend: Array<{ month: string; value: number }>;
};

export type IoTSensorReading = {
  timestamp: string;
  sensor_id: string;
  sensor_type: string;
  value: number;
  unit: string;
};

export type MaintenanceAlert = {
  id: string;
  equipment_name: string;
  alert_type: string;
  severity: "critical" | "warning" | "info";
  predicted_failure_date: string;
  confidence: number;
  message: string;
};

export type IoTDashboardData = {
  sensors: IoTSensorReading[];
  alerts: MaintenanceAlert[];
  sensor_summary: Array<{ type: string; count: number; avg_value: number; unit: string }>;
};

export type ESGMetric = {
  id: string;
  label: string;
  value: number;
  unit: string;
  target: number;
  trend: "up" | "down" | "stable";
};

export type ESGDashboardData = {
  overall_score: number;
  gresb_rating: string;
  metrics: ESGMetric[];
  carbon_by_scope: Array<{ scope: string; tco2e: number }>;
};

/** Phase 4 — 스마트 안전/비전/주차 타입. */
export type SafetyViolation = {
  id: string;
  camera_id: string;
  violation_type: "helmet_off" | "vest_off";
  confidence: number;
  detected_at: string;
  frame_url: string | null;
  zone: string;
};

export type SafetyDashboardData = {
  stream_url: string;
  violations: SafetyViolation[];
  stats: {
    total_violations_today: number;
    helmet_off_count: number;
    vest_off_count: number;
    active_cameras: number;
  };
};

export type ParkingRecord = {
  id: string;
  plate_number: string;
  event_type: "entry" | "exit";
  camera_id: string;
  zone: string;
  recorded_at: string;
};

export type ParkingDashboardData = {
  records: ParkingRecord[];
  stats: {
    total_today: number;
    currently_parked: number;
    capacity: number;
    occupancy_rate: number;
  };
};

/** Phase 4 — WebRTC / 디지털 트윈 타입. */
export type WebRTCSessionInfo = {
  session_id: string;
  status: "waiting" | "active" | "ended";
  participants: string[];
  created_at: string;
};

export type STTTranscript = {
  id: string;
  speaker: string;
  text: string;
  timestamp: string;
};

export type DigitalTwinAnomalyPoint = {
  timestamp: string;
  sensor_type: string;
  value: number;
  anomaly_score: number;
  is_anomaly: boolean;
  severity: "info" | "warning" | "critical";
};

export type DigitalTwinDashboardData = {
  anomalies: DigitalTwinAnomalyPoint[];
  summary: {
    total_sensors: number;
    anomalies_detected: number;
    critical_count: number;
    warning_count: number;
    last_scan_at: string;
  };
};

/** Phase 4 — SRE/DevOps 관제 타입. */
export type SREMetric = {
  name: string;
  value: number;
  unit: string;
  status: "healthy" | "degraded" | "critical";
  trend: "up" | "down" | "stable";
};

export type BackupLogEntry = {
  id: string;
  backup_type: string;
  status: "success" | "failed" | "in_progress";
  size_mb: number;
  duration_seconds: number;
  started_at: string;
  completed_at: string | null;
};

export type SREDashboardData = {
  metrics: SREMetric[];
  backup_logs: BackupLogEntry[];
  uptime_percent: number;
  avg_response_ms: number;
  error_rate_percent: number;
  grafana_embed_url: string;
};
