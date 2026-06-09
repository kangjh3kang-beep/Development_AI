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

export type CadRect = {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number;
  label?: string;
};

export type CadCircle = {
  id: string;
  cx: number;
  cy: number;
  radius: number;
  label?: string;
};

export type CadText = {
  id: string;
  x: number;
  y: number;
  text: string;
  fontSize?: number;
  rotation?: number;
};

export type CadTool = "select" | "point" | "line" | "polygon" | "text" | "rect" | "circle";

/** 설계 도면 파트 (공정별 구분) */
export type CadPart = "ARCH" | "STRUCT" | "MEP" | "LAND" | "CIVIL";

/** v61 레이어 설정. */
export type LayerConfig = {
  name: string;
  color: string;
  weight: number;
  visible: boolean;
  locked: boolean;
};

export type CadAnalysisMarker = {
  id: string;
  x: number;
  y: number;
  severity: "high" | "med" | "low";
  desc: string;
};

export type CadState = {
  points: CadPoint[];
  lines: CadLine[];
  polygons: CadPolygon[];
  rects: CadRect[];
  circles: CadCircle[];
  texts: CadText[];
  floorCount: number;
  buildingHeightM: number;
  scale: number;
  analysisMarkers: CadAnalysisMarker[];
  isAnalyzing: boolean;
};

export type CadSnapshot = Readonly<CadState>;

/** 백엔드 POST /api/v1/building-compliance/check 요청 바디. */
export type DesignPayload = {
  points: Array<{ id: string; x: number; y: number; label?: string }>;
  lines: Array<{ id: string; startPointId: string; endPointId: string }>;
  surfaces: Array<{ id: string; pointIds: string[] }>;
  rects?: Array<{ id: string; x: number; y: number; width: number; height: number }>;
  circles?: Array<{ id: string; cx: number; cy: number; radius: number }>;
  texts?: Array<{ id: string; x: number; y: number; text: string }>;
  floor_count: number;
  building_height_m: number;
  scale: number;
};

/** AI 자동 설계 요청/응답 타입. */
export type AutoDesignRequest = {
  site_area_sqm: number;
  site_shape?: Array<{ x: number; y: number }>;
  site_width_m?: number;
  site_depth_m?: number;
  zone_code: string;
  building_use: string;
  target_unit_types: string[];
  floor_height_m: number;
  setback_m: { north: number; south: number; east: number; west: number; };
};

export type AutoDesignSummary = {
  building_area_sqm: number;
  total_floor_area_sqm: number;
  num_floors: number;
  building_height_m: number;
  bcr_percent: number;
  far_percent: number;
  total_units: number;
  parking_count: number;
  core_count?: number;
  units_per_floor?: number;
};

export type AutoDesignCompliance = {
  bcr_ok: boolean;
  far_ok: boolean;
  height_ok: boolean;
  setback_ok: boolean;
  parking_ok?: boolean;
  all_pass?: boolean;
};

export type AutoDesignResponse = {
  design_payload: DesignPayload;
  summary: AutoDesignSummary;
  compliance: AutoDesignCompliance;
};

export type DesignAlternativesResponse = {
  alternatives: AutoDesignResponse[];
};

/** 평형 배분 한 줄(distribution 항목) — 믹스 표시는 ratio_pct만 신뢰. */
export type UnitMixRow = {
  code: string;
  name: string;
  area_sqm: number;
  ratio_pct: number;
};

export type UnitMixBlock = {
  distribution: UnitMixRow[];
  /** 이론치(총 세대). 화면 표기에는 쓰지 않음(summary.total_units가 실건축가능). */
  optimizer_total_units?: number;
};

/** 법정 한도(슬라이더 하드캡용). zone_code로 조회. */
export type LegalLimitsResponse = {
  zone_code: string;
  max_bcr_percent: number;
  max_far_percent: number;
  max_height_m: number;
  min_setback_m: number;
  sunlight_hours: number;
};

/** 자연어 설계 의도 파싱 결과. */
export type DesignIntent = {
  target_units: number | null;
  unit_mix: Record<string, number> | null;
  building_use: string | null;
  priority: "yield" | "livability" | "balanced";
  target_margin_pct: number | null;
  notes: string;
  source: "llm" | "rule" | "empty";
  suggested_unit_types: string[];
};

export type ParseIntentResponse = {
  intent: DesignIntent;
};

/** Phase 2 Top3 설계안 — 정렬: 준수 우선·score desc. */
export type DesignAlternative = {
  rank: number;
  alternative_name: string;
  priority: "yield" | "livability" | "balanced";
  summary: AutoDesignSummary;
  compliance: AutoDesignCompliance;
  unit_mix: UnitMixBlock;
  design_payload: DesignPayload;
  score: number;
  compliant: boolean;
};

export type DesignAlternativesV2Response = {
  alternatives: DesignAlternative[];
  recommended_index: number;
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
