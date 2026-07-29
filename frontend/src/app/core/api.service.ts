import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Analysis,
  Bike,
  ClimbComparison,
  RouteData,
  UnassignedGroup,
  ActivityDetail,
  ActivitySummary,
  AthleteSettings,
  CoachGoal,
  CoachReading,
  DrivetrainPresets,
  PmcPoint,
  PowerCurvePoint,
  Records,
  SyncResult,
  Totals,
  TrendPoint,
  WeightLogEntry,
  Zones,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = '/api';

  activities(limit = 100, offset = 0): Observable<ActivitySummary[]> {
    const params = new HttpParams().set('limit', limit).set('offset', offset);
    return this.http.get<ActivitySummary[]>(this.base + '/activities', { params });
  }

  activity(id: number): Observable<ActivityDetail> {
    return this.http.get<ActivityDetail>(this.base + '/activities/' + id);
  }

  deleteActivity(id: number): Observable<void> {
    return this.http.delete<void>(this.base + '/activities/' + id);
  }

  totals(days?: number): Observable<Totals> {
    return this.http.get<Totals>(this.base + '/stats/totals', { params: this.days(days) });
  }

  trend(groupBy: 'week' | 'month' = 'week', days = 365): Observable<TrendPoint[]> {
    const params = new HttpParams().set('group_by', groupBy).set('days', days);
    return this.http.get<TrendPoint[]>(this.base + '/stats/trend', { params });
  }

  pmc(days = 180): Observable<PmcPoint[]> {
    return this.http.get<PmcPoint[]>(this.base + '/stats/pmc', { params: new HttpParams().set('days', days) });
  }

  powerCurve(days?: number): Observable<PowerCurvePoint[]> {
    return this.http.get<PowerCurvePoint[]>(this.base + '/stats/power-curve', { params: this.days(days) });
  }

  zones(days = 90): Observable<Zones> {
    return this.http.get<Zones>(this.base + '/stats/zones', { params: new HttpParams().set('days', days) });
  }

  records(): Observable<Records> {
    return this.http.get<Records>(this.base + '/stats/records');
  }

  settings(): Observable<AthleteSettings> {
    return this.http.get<AthleteSettings>(this.base + '/stats/settings');
  }

  sync(force = false): Observable<SyncResult> {
    return this.http.post<SyncResult>(this.base + '/sync', null, { params: new HttpParams().set('force', force) });
  }

  upload(file: File): Observable<{ status: string; activity_id?: number; message?: string }> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<{ status: string; activity_id?: number; message?: string }>(this.base + '/upload', form);
  }

  analysis(id: number): Observable<Analysis> {
    return this.http.get<Analysis>(this.base + '/activities/' + id + '/analysis');
  }

  route(id: number): Observable<RouteData> {
    return this.http.get<RouteData>(this.base + '/activities/' + id + '/route');
  }

  similarSegments(id: number): Observable<{ comparisons: ClimbComparison[] }> {
    return this.http.get<{ comparisons: ClimbComparison[] }>(this.base + '/activities/' + id + '/similar-segments');
  }

  bikes(): Observable<Bike[]> {
    return this.http.get<Bike[]>(this.base + '/bikes');
  }

  createBike(payload: Partial<Bike>): Observable<{ id: number; name: string }> {
    return this.http.post<{ id: number; name: string }>(this.base + '/bikes', payload);
  }

  updateBike(id: number, payload: Partial<Bike>): Observable<{ id: number; name: string }> {
    return this.http.patch<{ id: number; name: string }>(this.base + '/bikes/' + id, payload);
  }

  drivetrainPresets(): Observable<DrivetrainPresets> {
    return this.http.get<DrivetrainPresets>(this.base + '/bikes/drivetrain-presets');
  }

  updateActivity(id: number, changes: { bike_id?: number }): Observable<ActivitySummary> {
    let params = new HttpParams();
    if (changes.bike_id !== undefined) {
      params = params.set('bike_id', changes.bike_id);
    }
    return this.http.patch<ActivitySummary>(this.base + '/activities/' + id, null, { params });
  }

  deleteBike(id: number): Observable<void> {
    return this.http.delete<void>(this.base + '/bikes/' + id);
  }

  assignRange(bikeId: number, start: string, end: string): Observable<{ assigned: number; message: string }> {
    const params = new HttpParams().set('start', start).set('end', end);
    return this.http.post<{ assigned: number; message: string }>(
      this.base + '/bikes/' + bikeId + '/assign-range',
      null,
      { params },
    );
  }

  unassigned(): Observable<UnassignedGroup[]> {
    return this.http.get<UnassignedGroup[]>(this.base + '/bikes/unassigned');
  }

  claim(bikeId: number, activityId: number): Observable<{ message: string; also_assigned: number }> {
    return this.http.post<{ message: string; also_assigned: number }>(
      this.base + '/bikes/' + bikeId + '/claim/' + activityId,
      null,
    );
  }

  private days(value?: number): HttpParams {
    let params = new HttpParams();
    if (value) {
      params = params.set('days', value);
    }
    return params;
  }

  coach(): Observable<CoachReading> {
    return this.http.get<CoachReading>(this.base + '/coach');
  }

  setGoal(goal: CoachGoal): Observable<CoachGoal> {
    return this.http.put<CoachGoal>(this.base + '/coach/goal', goal);
  }

  weightLog(): Observable<WeightLogEntry[]> {
    return this.http.get<WeightLogEntry[]>(this.base + '/weight');
  }

  logWeight(measured_on: string, weight_kg: number): Observable<unknown> {
    return this.http.post(this.base + '/weight', { measured_on, weight_kg });
  }
}
