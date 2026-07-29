import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ChartConfiguration } from 'chart.js';
import { ApiService } from '../core/api.service';
import { ActivityDetail, Analysis, Bike, ClimbComparison, RouteData } from '../core/models';
import { ChartComponent } from '../shared/chart.component';
import { RouteMapComponent } from '../shared/route-map.component';
import { TelemetryComponent } from '../shared/telemetry-panel.component';
import { DurationPipe, NumPipe, RideDatePipe } from '../shared/format.pipe';
import { GRID, INK, PULSE, WATT, WATT_FILL } from '../core/theme';

@Component({
  selector: 'app-activity-detail',
  standalone: true,
  imports: [
    RouterLink,
    FormsModule,
    ChartComponent,
    RouteMapComponent,
    TelemetryComponent,
    DurationPipe,
    NumPipe,
    RideDatePipe,
  ],
  template: `
    @if (ride(); as r) {
      <section class="section">
        <div class="section-head">
          <div>
            <span class="eyebrow">
              {{ r.started_at | rideDate }} · {{ r.device ?? 'iGPSPORT' }}
            </span>
            <h1>{{ r.title }}</h1>
            <div class="bike-pick">
              <span class="eyebrow">Bike</span>
              <select [ngModel]="r.bike_id ?? 0" (ngModelChange)="trocarBike($event)">
                <option [ngValue]="0">— nenhuma —</option>
                @for (b of bikes(); track b.id) {
                  <option [ngValue]="b.id">{{ b.name }}</option>
                }
              </select>
            </div>
          </div>
          <a class="hint" routerLink="/treinos">← voltar</a>
        </div>

        <!-- Perfil de altimetria como faixa de abertura: a silhueta do pedal -->
        @if (profilePath()) {
          <div class="card" style="padding:0; overflow:hidden; margin-bottom:20px">
            <!-- Hex inline aqui e a excecao consciente a regra do theme.ts: SVG
                 em template nao importa TypeScript. -->
            <svg viewBox="0 0 1000 130" preserveAspectRatio="none" style="display:block; width:100%; height:130px">
              <path [attr.d]="profilePath()" fill="rgba(31,122,94,.15)" stroke="#1F7A5E" stroke-width="1.5" />
            </svg>
          </div>
        }

        @if (routeData()?.available) {
          <div class="card" style="padding:0; overflow:hidden; margin-bottom:20px">
            <app-route-map [points]="routeData()!.points" [best]="best()" [worst]="worst()" />
          </div>
        } @else if (routeData()) {
          <div class="notice">{{ routeData()!.reason }}</div>
        }

        <div class="grid cols-4" style="margin-bottom:20px">
          <div class="plate">
            <span class="value">{{ r.distance_km | num: 1 }}</span><span class="unit">km</span>
            <span class="label">Distância</span>
          </div>
          <div class="plate">
            <span class="value">{{ r.moving_time_s | duration }}</span>
            <span class="label">Tempo</span>
            <div class="foot">média {{ r.avg_speed_kmh | num: 1 }} km/h</div>
          </div>
          <div class="plate climb">
            <span class="value">{{ r.elevation_gain_m | num: 0 }}</span><span class="unit">m</span>
            <span class="label">Altimetria</span>
          </div>
          @if (r.avg_hr) {
            <div class="plate pulse">
              <span class="value">{{ r.avg_hr | num: 0 }}</span><span class="unit">bpm</span>
              <span class="label">FC média</span>
              <div class="foot">máx {{ r.max_hr | num: 0 }}</div>
            </div>
          } @else {
            <div class="plate">
              <span class="value" style="color:var(--secondary)">—</span>
              <span class="label">Sem cinta cardíaca</span>
              <div class="foot">a análise mede resultado, não custo</div>
            </div>
          }
          <div class="plate watt">
            <span class="value">{{ r.avg_power | num: 0 }}</span><span class="unit">W</span>
            <span class="label">
              {{ r.power_is_estimated ? 'Potência estimada' : 'Potência medida' }}
            </span>
            <div class="foot">máx {{ r.max_power | num: 0 }} W</div>
          </div>
          <div class="plate watt">
            <span class="value">{{ r.normalized_power | num: 0 }}</span><span class="unit">W</span>
            <span class="label">Potência normalizada</span>
            <div class="foot">VI {{ r.variability_index | num: 2 }}</div>
          </div>
          <div class="plate">
            <span class="value">{{ r.intensity_factor | num: 2 }}</span>
            <span class="label">Intensidade</span>
            <div class="foot">IF sobre o FTP</div>
          </div>
          <div class="plate">
            <span class="value">{{ r.tss | num: 0 }}</span><span class="unit">TSS</span>
            <span class="label">Carga</span>
            <div class="foot">
              @if (r.trimp) { TRIMP {{ r.trimp | num: 0 }} } @else { calculada da potência estimada }
            </div>
          </div>
          <div class="plate">
            <span class="value">{{ r.moving_time_s | duration }}</span>
            <span class="label">Cronômetro</span>
            <div class="foot">tempo total {{ r.duration_s | duration }}</div>
          </div>
          <div class="plate">
            <span class="value">{{ r.max_cadence | num: 0 }}</span><span class="unit">rpm</span>
            <span class="label">Cadência máxima</span>
          </div>
          <div class="plate climb">
            <span class="value">{{ r.grade_up_avg | num: 1 }}</span><span class="unit">%</span>
            <span class="label">Grau+ méd / máx</span>
            <div class="foot">máximo {{ r.grade_up_max | num: 1 }}% · Grau- {{ r.grade_down_avg | num: 1 }}%</div>
          </div>
          <div class="plate climb">
            <span class="value">{{ r.vam_up_avg | num: 0 }}</span><span class="unit">m/h</span>
            <span class="label">VAM+ méd</span>
            <div class="foot">pico {{ r.vam_up_max | num: 0 }} m/h</div>
          </div>
          <div class="plate climb">
            <span class="value">{{ r.descent_m | num: 0 }}</span><span class="unit">m</span>
            <span class="label">Declínio cumulativo</span>
            <div class="foot">altitude {{ r.altitude_min | num: 0 }}–{{ r.altitude_max | num: 0 }} m</div>
          </div>
        </div>

        @if (r.power_is_estimated) {
          <div class="notice">
            <strong>A potência deste treino foi calculada, não medida.</strong> Sem potenciômetro, ela vem da física:
            atrito do pneu, gravidade na subida, arrasto do ar e inércia, a partir da velocidade, da inclinação e do
            peso configurado. Erra tipicamente de 10 a 15% contra um potenciômetro real, e erra mais com vento forte.
            Mas erra de forma consistente — então serve para comparar seus treinos entre si, que é o que interessa
            aqui. Só não compare com o número do potenciômetro de outra pessoa.
          </div>
        }

        <div class="section-head" style="margin-top:32px">
          <h2>Telemetria</h2>
          <span class="hint">onde você ganhou e onde perdeu, com o motivo</span>
        </div>
        <app-telemetry [analysis]="analysis()" [climbs]="climbs()" />

        <div class="card" style="margin:32px 0 20px">
          <h2>Ao longo do pedal</h2>
          <div class="chart-box tall">
            @if (streamConfig(); as cfg) { <app-chart [config]="cfg" /> }
          </div>
        </div>

        <div class="grid cols-2">
          @if (curveConfig(); as cfg) {
            <div class="card">
              <h2>Curva de potência deste treino</h2>
              <div class="chart-box"><app-chart [config]="cfg" /></div>
            </div>
          }
          @if (zoneConfig(); as cfg) {
            <div class="card">
              <h2>Tempo por zona</h2>
              <div class="chart-box"><app-chart [config]="cfg" /></div>
            </div>
          }
        </div>
      </section>
    } @else {
      <p class="eyebrow">Carregando treino…</p>
    }
  `,
  styles: [
    `
      .bike-pick { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
      .bike-pick select {
        font-family: var(--body);
        font-size: 0.9rem;
        color: var(--ink);
        border: 1px solid var(--rule);
        border-radius: var(--radius);
        padding: 5px 8px;
        background: #fff;
      }
    `,
  ],
})
export class ActivityDetailComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);

  ride = signal<ActivityDetail | null>(null);
  analysis = signal<Analysis | null>(null);
  routeData = signal<RouteData | null>(null);
  climbs = signal<ClimbComparison[]>([]);
  streamConfig = signal<ChartConfiguration | null>(null);
  curveConfig = signal<ChartConfiguration | null>(null);
  zoneConfig = signal<ChartConfiguration | null>(null);
  profilePath = signal('');
  bikes = signal<Bike[]>([]);

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    this.api.activity(id).subscribe((data) => {
      this.ride.set(data);
      this.buildStreams(data);
      this.buildCurve(data);
      this.buildZones(data);
      this.buildProfile(data);
    });
    this.api.analysis(id).subscribe({ next: (data) => this.analysis.set(data), error: () => this.analysis.set(null) });
    this.api.route(id).subscribe({ next: (data) => this.routeData.set(data), error: () => this.routeData.set(null) });
    this.api
      .similarSegments(id)
      .subscribe({ next: (data) => this.climbs.set(data.comparisons), error: () => this.climbs.set([]) });
    this.api.bikes().subscribe((data) => this.bikes.set(data));
  }

  /**
   * Trocar a bike muda a analise, nao so o rotulo: peso, pneu e postura entram
   * na estimativa de potencia, e a transmissao declarada e o que gera a
   * cobertura de marchas. Por isso recarrega a analise junto.
   */
  trocarBike(bikeId: number): void {
    const id = this.ride()?.id;
    if (!id) {
      return;
    }
    this.api.updateActivity(id, { bike_id: bikeId }).subscribe(() => {
      this.api.activity(id).subscribe((data) => this.ride.set(data));
      this.api.analysis(id).subscribe((data) => this.analysis.set(data));
    });
  }

  best() {
    return this.analysis()?.highlights?.best ?? null;
  }

  worst() {
    return this.analysis()?.highlights?.worst ?? null;
  }

  private buildStreams(ride: ActivityDetail): void {
    const streams = ride.streams ?? {};
    const labels = (streams['t'] ?? []).map((seconds) => this.clock(Number(seconds)));
    const datasets = [];

    if (streams['speed']) {
      datasets.push({
        label: 'Velocidade (km/h)',
        data: streams['speed'],
        borderColor: INK,
        borderWidth: 1.2,
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'y',
      });
    }
    if (streams['hr']) {
      datasets.push({
        label: 'FC (bpm)',
        data: streams['hr'],
        borderColor: PULSE,
        borderWidth: 1.2,
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'y1',
      });
    }
    if (streams['power']) {
      datasets.push({
        label: 'Potência (W)',
        data: streams['power'],
        borderColor: WATT,
        borderWidth: 1,
        pointRadius: 0,
        tension: 0.1,
        yAxisID: 'y1',
      });
    }

    this.streamConfig.set({
      type: 'line',
      data: { labels, datasets },
      options: {
        scales: {
          y: { position: 'left', grid: { color: GRID }, title: { display: true, text: 'km/h' } },
          y1: { position: 'right', grid: { display: false }, title: { display: true, text: 'bpm / W' } },
          x: { ticks: { maxTicksLimit: 12 }, grid: { display: false } },
        },
        plugins: { legend: { labels: { boxWidth: 10, boxHeight: 10 } } },
      },
    });
  }

  private buildCurve(ride: ActivityDetail): void {
    if (!ride.power_curve) {
      return;
    }
    const entries = Object.entries(ride.power_curve).sort((a, b) => Number(a[0]) - Number(b[0]));
    this.curveConfig.set({
      type: 'line',
      data: {
        labels: entries.map(([seconds]) => this.shortDuration(Number(seconds))),
        datasets: [
          {
            label: 'W',
            data: entries.map(([, watts]) => watts),
            borderColor: WATT,
            backgroundColor: WATT_FILL,
            fill: true,
            borderWidth: 2,
            pointRadius: 3,
          },
        ],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: 'watts' } } } },
    });
  }

  private buildZones(ride: ActivityDetail): void {
    const source = ride.power_zones_s ?? ride.hr_zones_s;
    if (!source) {
      return;
    }
    const color = ride.power_zones_s ? WATT : PULSE;
    const entries = Object.entries(source);
    this.zoneConfig.set({
      type: 'bar',
      data: {
        labels: entries.map(([zone]) => zone),
        datasets: [
          {
            label: 'min',
            data: entries.map(([, seconds]) => Math.round(seconds / 60)),
            backgroundColor: color,
            borderRadius: 2,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: { x: { title: { display: true, text: 'minutos' } } },
      },
    });
  }

  /** Desenha a silhueta do relevo do pedal como um path SVG. */
  private buildProfile(ride: ActivityDetail): void {
    const altitude = (ride.streams?.['altitude'] ?? []).filter((v): v is number => v !== null);
    if (altitude.length < 4) {
      return;
    }
    const min = Math.min(...altitude);
    const max = Math.max(...altitude);
    const span = max - min || 1;
    const step = 1000 / (altitude.length - 1);

    let path = 'M 0 130';
    altitude.forEach((value, index) => {
      const x = index * step;
      const y = 125 - ((value - min) / span) * 110;
      path += ' L ' + x.toFixed(1) + ' ' + y.toFixed(1);
    });
    path += ' L 1000 130 Z';
    this.profilePath.set(path);
  }

  private clock(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h > 0 ? h + ':' + String(m).padStart(2, '0') : m + 'min';
  }

  private shortDuration(seconds: number): string {
    if (seconds < 60) {
      return seconds + 's';
    }
    if (seconds < 3600) {
      return seconds / 60 + 'min';
    }
    return seconds / 3600 + 'h';
  }
}
