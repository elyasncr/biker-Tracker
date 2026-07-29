export interface ActivitySummary {
  id: number;
  source: string;
  file_name: string | null;
  started_at: string;
  sport: string;
  device: string | null;
  title: string | null;
  duration_s: number;
  moving_time_s: number;
  distance_km: number;
  elevation_gain_m: number;
  calories: number | null;
  avg_speed_kmh: number | null;
  max_speed_kmh: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_cadence: number | null;
  avg_power: number | null;
  max_power: number | null;
  normalized_power: number | null;
  intensity_factor: number | null;
  tss: number | null;
  variability_index: number | null;
  trimp: number | null;
  bike_id: number | null;
  bike_name: string | null;
  sensor_signature: string | null;
  power_is_estimated: boolean;
  max_cadence: number | null;
  avg_temperature: number | null;
  max_temperature: number | null;
  descent_m: number | null;
  grade_up_avg: number | null;
  grade_up_max: number | null;
  grade_down_avg: number | null;
  grade_down_max: number | null;
  vam_up_avg: number | null;
  vam_up_max: number | null;
  altitude_min: number | null;
  altitude_avg: number | null;
  altitude_max: number | null;
}

export interface ActivityDetail extends ActivitySummary {
  notes: string | null;
  power_curve: Record<string, number> | null;
  hr_zones_s: Record<string, number> | null;
  power_zones_s: Record<string, number> | null;
  streams: Record<string, (number | null)[]> | null;
  sensors: Record<string, string | null>[] | null;
}

export interface Totals {
  activities: number;
  distance_km: number;
  moving_time_h: number;
  elevation_gain_m: number;
  tss: number;
  avg_speed_kmh: number | null;
  longest_ride_km: number | null;
  biggest_climb_m: number | null;
}

export interface TrendPoint {
  period: string;
  activities: number;
  distance_km: number;
  moving_time_h: number;
  elevation_gain_m: number;
  tss: number;
  avg_speed_kmh: number | null;
  avg_power: number | null;
}

export interface PmcPoint {
  date: string;
  load: number;
  ctl: number;
  atl: number;
  tsb: number;
}

export interface PowerCurvePoint {
  seconds: number;
  watts: number;
  activity_id: number;
  date: string;
}

export interface ZoneBucket {
  zone: string;
  seconds: number;
}

export interface Zones {
  heart_rate: ZoneBucket[];
  power: ZoneBucket[];
}

export interface RecordEntry {
  value: number;
  activity_id: number;
  date: string;
}

export type Records = Record<string, RecordEntry | null>;

export interface SyncResult {
  scanned: number;
  imported: number;
  skipped: number;
  failed: number;
  errors: string[];
  data_dir: string;
}

export interface AthleteSettings {
  ftp_watts: number;
  hr_max: number;
  hr_rest: number;
  data_dir: string;
  igpsport_enabled: boolean;
}

// --- Telemetria estilo F1 ------------------------------------------------

export interface Reason {
  kind: string;
  impact: number;
  text: string;
}

export interface Segment {
  terrain: 'subida' | 'plano' | 'descida';
  gradient: number;
  start_index: number;
  end_index: number;
  start_km: number;
  end_km: number;
  distance_m: number;
  duration_s: number;
  elevation_m: number;
  vam: number | null;
  avg_speed_kmh: number | null;
  avg_power: number | null;
  avg_hr: number | null;
  avg_cadence: number | null;
  torque_nm: number | null;
  variability: number | null;
  coasting_ratio: number;
  lat: number | null;
  lon: number | null;
}

export interface SegmentHighlight extends Segment {
  efficiency: number;
  score: number;
  verdict: string;
  reasons: Reason[];
}

export interface CadenceReport {
  available: boolean;
  avg_rpm: number | null;
  bands: { band: string; seconds: number; rpm_low: number }[];
  by_terrain: Record<string, number>;
  coasting_s: number;
  mashing_s: number;
  avg_torque_nm: number | null;
  insight: string | null;
}

export interface Split {
  km: number;
  duration_s: number;
  speed_kmh: number;
  elevation_m: number;
  avg_hr: number | null;
  avg_power: number | null;
  avg_cadence: number | null;
}

export interface CoverageBand {
  development_m: number;
  gears: string[];
  label: string;
  seconds: number;
  used: boolean;
}

export interface GearCoverage {
  bands: CoverageBand[];
  off_gear_seconds: number;
  off_gear_ratio: number;
  bands_used: number;
  bands_total: number;
  insight: string;
}

export interface DrivetrainPresets {
  chainrings: { label: string; value: number[] }[];
  cassettes: { label: string; value: number[] }[];
  wheels: { label: string; value: number }[];
}

export interface GearReport {
  available: boolean;
  histogram?: { development_m: number; seconds: number }[];
  gears_used?: { development_m: number; share: number }[];
  median_development_m?: number;
  spread_m?: number;
  insight?: string;
  coverage?: GearCoverage;
}

export interface Analysis {
  available: boolean;
  reason?: string;
  basis?: string;
  has_hr?: boolean;
  gears?: GearReport;
  segments: Segment[];
  highlights: { best: SegmentHighlight | null; worst: SegmentHighlight | null; ranking?: SegmentHighlight[] };
  baseline: Record<string, number | null>;
  cadence: CadenceReport;
  splits: Split[];
  pacing: { available: boolean; quarters?: number[]; change_pct?: number; verdict?: string; unit?: string };
}

export interface RoutePoint {
  i: number;
  lat: number;
  lon: number;
  speed: number | null;
  hr: number | null;
  power: number | null;
  cadence: number | null;
  altitude: number | null;
  km: number | null;
}

export interface RouteData {
  available: boolean;
  reason?: string;
  points: RoutePoint[];
  bounds?: { south: number; north: number; west: number; east: number };
}

export interface ClimbComparison {
  segment: Segment;
  attempts: { activity_id: number; date: string; duration_s: number; vam: number | null; avg_power: number | null }[];
  personal_best_s: number;
  delta_s: number;
  verdict: string;
}

// --- Bikes ---------------------------------------------------------------

export interface BikeStats {
  activities: number;
  distance_km: number;
  moving_time_h: number;
  elevation_gain_m: number;
  last_ride: string | null;
  chain_due_in_km: number | null;
}

export interface Bike {
  id: number;
  name: string;
  brand: string | null;
  model: string | null;
  year: number | null;
  kind: string;
  weight_kg: number | null;
  crr: number | null;
  cda: number | null;
  wheel_circumference_mm: number | null;
  chainrings: number[] | null;
  cassette: number[] | null;
  notes: string | null;
  is_default: boolean;
  signatures: string[];
  stats: BikeStats;
}

export interface UnassignedGroup {
  signature: string | null;
  count: number;
  sample_activity_id: number;
  rides: { id: number; title: string | null; date: string }[];
}

// --- Treinador -----------------------------------------------------------

export interface Readiness {
  state: 'sem_historico' | 'folga' | 'leve' | 'convite' | 'livre';
  severity: string;
  rides_needed: number;
  headline: string;
  detail: string;
}

export interface Prescription {
  kind: 'folga' | 'pedal' | 'bonus';
  minutes: number | null;
  zone: string | null;
  headline: string;
  detail: string;
}

export interface ConsistencyWeek {
  week: string;
  rides: number;
  minutes: number;
  met_goal: boolean;
}

export interface WeightProgress {
  current_kg: number;
  first_kg: number;
  change_kg: number;
  target_kg: number | null;
  series: { date: string; weight_kg: number }[];
}

export interface Fitness {
  ctl: number;
  series: { date: string; ctl: number }[];
  depends_on_estimated_ftp: boolean;
}

export interface CoachGoal {
  rides_per_week: number;
  minutes_per_week: number;
  target_weight_kg: number | null;
}

export interface GoalSuggestion {
  minutes_per_week: number;
  rides_per_week: number;
  reason: string;
}

export interface CoachReading {
  readiness: Readiness;
  prescription: Prescription;
  progress: {
    consistency: { weeks: ConsistencyWeek[]; goal_rides: number; goal_minutes: number };
    weight: WeightProgress | null;
    fitness: Fitness;
  };
  goal: CoachGoal;
  goal_suggestion: GoalSuggestion | null;
  ftp_is_default: boolean;
}

export interface WeightLogEntry {
  measured_on: string;
  weight_kg: number;
  note: string | null;
}
