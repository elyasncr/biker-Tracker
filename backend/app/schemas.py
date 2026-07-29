from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActivitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    file_name: str | None
    started_at: datetime
    sport: str
    device: str | None
    title: str | None
    duration_s: float
    moving_time_s: float
    distance_km: float
    elevation_gain_m: float
    calories: int | None
    avg_speed_kmh: float | None
    max_speed_kmh: float | None
    avg_hr: float | None
    max_hr: float | None
    avg_cadence: float | None
    avg_power: float | None
    max_power: float | None
    normalized_power: float | None
    intensity_factor: float | None
    tss: float | None
    variability_index: float | None
    trimp: float | None
    max_cadence: float | None = None
    avg_temperature: float | None = None
    max_temperature: float | None = None
    descent_m: float | None = None
    grade_up_avg: float | None = None
    grade_up_max: float | None = None
    grade_down_avg: float | None = None
    grade_down_max: float | None = None
    vam_up_avg: float | None = None
    vam_up_max: float | None = None
    altitude_min: float | None = None
    altitude_avg: float | None = None
    altitude_max: float | None = None
    power_is_estimated: bool = False
    bike_id: int | None = None
    bike_name: str | None = None
    sensor_signature: str | None = None


class ActivityDetail(ActivitySummary):
    notes: str | None
    power_curve: dict | None
    hr_zones_s: dict | None
    power_zones_s: dict | None
    streams: dict | None = None
    sensors: list | None = None


class Totals(BaseModel):
    activities: int
    distance_km: float
    moving_time_h: float
    elevation_gain_m: float
    tss: float
    avg_speed_kmh: float | None
    longest_ride_km: float | None
    biggest_climb_m: float | None


class TrendPoint(BaseModel):
    period: str
    activities: int
    distance_km: float
    moving_time_h: float
    elevation_gain_m: float
    tss: float
    avg_speed_kmh: float | None
    avg_power: float | None


class PmcPoint(BaseModel):
    date: str
    load: float
    ctl: float
    atl: float
    tsb: float


class SyncResult(BaseModel):
    scanned: int
    imported: int
    skipped: int
    failed: int
    errors: list[str]
    data_dir: str
