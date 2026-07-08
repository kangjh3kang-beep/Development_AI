import type {
  DigitalTwinAnomalyPoint,
  DigitalTwinDashboardData,
  ParkingDashboardData,
  ParkingRecord,
  SafetyDashboardData,
  SafetyViolation,
  STTTranscript,
} from "@/components/cad/types";

/* ── Part-M: 안전 관제 Mock ── */

const mockSafetyViolations: SafetyViolation[] = [
  { id: "sv-1", camera_id: "cam-01", violation_type: "helmet_off", confidence: 0.94, detected_at: "2026-03-22T09:12:33Z", frame_url: null, zone: "A구역" },
  { id: "sv-2", camera_id: "cam-02", violation_type: "vest_off", confidence: 0.88, detected_at: "2026-03-22T09:15:10Z", frame_url: null, zone: "B구역" },
  { id: "sv-3", camera_id: "cam-01", violation_type: "helmet_off", confidence: 0.91, detected_at: "2026-03-22T09:22:45Z", frame_url: null, zone: "A구역" },
  { id: "sv-4", camera_id: "cam-03", violation_type: "vest_off", confidence: 0.87, detected_at: "2026-03-22T09:31:12Z", frame_url: null, zone: "C구역" },
  { id: "sv-5", camera_id: "cam-02", violation_type: "helmet_off", confidence: 0.96, detected_at: "2026-03-22T09:45:02Z", frame_url: null, zone: "B구역" },
  { id: "sv-6", camera_id: "cam-01", violation_type: "vest_off", confidence: 0.82, detected_at: "2026-03-22T10:03:18Z", frame_url: null, zone: "A구역" },
  { id: "sv-7", camera_id: "cam-04", violation_type: "helmet_off", confidence: 0.93, detected_at: "2026-03-22T10:15:44Z", frame_url: null, zone: "D구역" },
  { id: "sv-8", camera_id: "cam-02", violation_type: "helmet_off", confidence: 0.89, detected_at: "2026-03-22T10:28:51Z", frame_url: null, zone: "B구역" },
];

export const mockSafetyDashboard: SafetyDashboardData = {
  stream_url: "/api/v1/safety/stream-proxy",
  violations: mockSafetyViolations,
  stats: {
    total_violations_today: 8,
    helmet_off_count: 5,
    vest_off_count: 3,
    active_cameras: 4,
  },
};

/* ── Part-M: 주차 관제 Mock ── */

const mockParkingRecords: ParkingRecord[] = [
  { id: "pr-1", plate_number: "12가3456", event_type: "entry", camera_id: "park-cam-1", zone: "지하1층", recorded_at: "2026-03-22T07:32:10Z" },
  { id: "pr-2", plate_number: "34나7890", event_type: "entry", camera_id: "park-cam-1", zone: "지하1층", recorded_at: "2026-03-22T07:45:23Z" },
  { id: "pr-3", plate_number: "56다1234", event_type: "entry", camera_id: "park-cam-2", zone: "지하2층", recorded_at: "2026-03-22T08:01:45Z" },
  { id: "pr-4", plate_number: "12가3456", event_type: "exit", camera_id: "park-cam-1", zone: "지하1층", recorded_at: "2026-03-22T08:55:30Z" },
  { id: "pr-5", plate_number: "78라5678", event_type: "entry", camera_id: "park-cam-2", zone: "지하2층", recorded_at: "2026-03-22T09:10:12Z" },
  { id: "pr-6", plate_number: "90마9012", event_type: "entry", camera_id: "park-cam-1", zone: "지하1층", recorded_at: "2026-03-22T09:22:55Z" },
  { id: "pr-7", plate_number: "34나7890", event_type: "exit", camera_id: "park-cam-1", zone: "지하1층", recorded_at: "2026-03-22T10:05:18Z" },
  { id: "pr-8", plate_number: "23바4567", event_type: "entry", camera_id: "park-cam-2", zone: "지하2층", recorded_at: "2026-03-22T10:30:44Z" },
];

export const mockParkingDashboard: ParkingDashboardData = {
  records: mockParkingRecords,
  stats: {
    total_today: 8,
    currently_parked: 4,
    capacity: 120,
    occupancy_rate: 0.68,
  },
};

/* ── Part-L: WebRTC 회의록 Mock ── */

export const mockSTTTranscripts: STTTranscript[] = [
  { id: "t1", speaker: "김현장", text: "3층 슬라브 타설 상태 확인 부탁합니다.", timestamp: "2026-03-22T10:01:12Z" },
  { id: "t2", speaker: "이감리", text: "네, 콘크리트 양생 상태는 양호합니다. 철근 배근 간격도 규정 내입니다.", timestamp: "2026-03-22T10:01:45Z" },
  { id: "t3", speaker: "김현장", text: "외벽 방수 시공은 언제 시작하나요?", timestamp: "2026-03-22T10:02:30Z" },
  { id: "t4", speaker: "박시공", text: "내일 오전부터 시작 예정입니다. 자재는 이미 입고 완료했습니다.", timestamp: "2026-03-22T10:03:05Z" },
  { id: "t5", speaker: "이감리", text: "방수 시공 전 표면 건조 상태 반드시 확인해 주세요.", timestamp: "2026-03-22T10:03:28Z" },
];

/* ── Part-L: 디지털 트윈 이상 감지 Mock ── */

function generateAnomalyTimeSeries(): DigitalTwinAnomalyPoint[] {
  const points: DigitalTwinAnomalyPoint[] = [];
  const sensorTypes = ["temperature", "vibration", "pressure", "humidity"];
  const baseDate = new Date("2026-03-22T00:00:00Z");

  for (let hour = 0; hour < 24; hour++) {
    for (const sensorType of sensorTypes) {
      const ts = new Date(baseDate.getTime() + hour * 3600_000).toISOString();
      const baseValue = sensorType === "temperature" ? 22 : sensorType === "vibration" ? 0.5 : sensorType === "pressure" ? 101.3 : 55;
      const noise = (Math.random() - 0.5) * 2;
      const value = baseValue + noise;

      // 특정 시간대에 이상 감지 주입
      const isAnomaly = (hour === 7 || hour === 14 || hour === 19) && sensorType === "vibration";
      const anomalyScore = isAnomaly ? -(0.3 + Math.random() * 0.2) : 0.1 + Math.random() * 0.3;

      points.push({
        timestamp: ts,
        sensor_type: sensorType,
        value: isAnomaly ? baseValue + 5 + Math.random() * 3 : value,
        anomaly_score: Number(anomalyScore.toFixed(4)),
        is_anomaly: isAnomaly,
        severity: isAnomaly && anomalyScore < -0.3 ? "critical" : isAnomaly ? "warning" : "info",
      });
    }
  }
  return points;
}

export const mockDigitalTwinDashboard: DigitalTwinDashboardData = {
  anomalies: generateAnomalyTimeSeries(),
  summary: {
    total_sensors: 48,
    anomalies_detected: 3,
    critical_count: 2,
    warning_count: 1,
    last_scan_at: "2026-03-22T10:30:00Z",
  },
};
