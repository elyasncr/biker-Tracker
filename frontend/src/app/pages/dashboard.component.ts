import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ChartConfiguration } from 'chart.js';
import { forkJoin } from 'rxjs';
import { ApiService } from '../core/api.service';
import { AthleteSettings, Records, Totals } from '../core/models';
import { ChartComponent } from '../shared/chart.component';
import { DurationPipe, NumPipe, RideDatePipe } from '../shared/format.pipe';
import { CLIMB, GRID, INK, INK_FILL, PULSE, WATT, WATT_FILL } from '../core/theme';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [RouterLink, ChartComponent, DurationPipe, NumPipe, RideDatePipe],
  template: `
    @if (loading()) {
      <p class="eyebrow">Carregando…</p>
    } @else if (empty()) {
      <div class="empty">
        <h2>Nenhum treino ainda</h2>
        <p>
          Exporte os pedais do app iGPSPORT em <code>.fit</code> e solte os arquivos na pasta
          <code>{{ settings()?.data_dir }}</code>.
        </p>
        <p>Depois clique em "Ler pasta data/" aqui em cima. Duplicados sao ignorados pelo hash do arquivo.</p>
      </div>
    } @else {
      <!-- Placas de numero: o total da janela escolhida -->
      <section class="section">
        <div class="section-head">
          <h1>Evolucao</h1>
          <div class="chips">
            @for (option of windows; track option.days) {
              <button class="chip" [class.active]="window() === option.days" (click)="setWindow(option.days)">
                {{ option.label }}
              </button>
            }
          </div>
          <span class="hint">FTP {{ settings()?.ftp_watts }} W · FC max {{ settings()?.hr_max }}</span>
        </div>

        <div class="grid cols-4">
          <div class="plate">
            <span class="label">Distancia</span>
            <span class="value">{{ totals()?.distance_km | num: 0 }}</span><span class="unit">km</span>
            <div class="foot">{{ totals()?.activities }} pedais</div>
          </div>
          <div class="plate climb">
            <span class="label">Altimetria</span>
            <span class="value">{{ totals()?.elevation_gain_m | num: 0 }}</span><span class="unit">m</span>
            <div class="foot">maior subida: {{ totals()?.biggest_climb_m | num: 0 }} m</div>
          </div>
          <div class="plate">
            <span class="label">Tempo em movimento</span>
            <span class="value">{{ totals()?.moving_time_h | num: 1 }}</span><span class="unit">h</span>
            <div class="foot">media {{ totals()?.avg_speed_kmh | num: 1 }} km/h</div>
          </div>
          <div class="plate watt">
            <span class="label">Carga (TSS)</span>
            <span class="value">{{ totals()?.tss | num: 0 }}</span>
            <div class="foot">soma do periodo</div>
          </div>
        </div>
      </section>

      <!-- Volume por semana ou mes -->
      <section class="section">
        <div class="section-head">
          <h2>Volume</h2>
          <div class="chips">
            <button class="chip" [class.active]="groupBy() === 'week'" (click)="setGroup('week')">Semana</button>
            <button class="chip" [class.active]="groupBy() === 'month'" (click)="setGroup('month')">Mes</button>
          </div>
          <span class="hint">barras = km · linha = carga</span>
        </div>
        <div class="card">
          <div class="chart-box tall">
            @if (trendConfig(); as cfg) { <app-chart [config]="cfg" /> }
          </div>
        </div>
      </section>

      <!-- Condicionamento, fadiga e forma -->
      <section class="section">
        <div class="section-head">
          <h2>Condicionamento e forma</h2>
          <span class="hint">CTL = base · ATL = fadiga · TSB = frescor</span>
        </div>
        <div class="card">
          <div class="chart-box tall">
            @if (pmcConfig(); as cfg) { <app-chart [config]="cfg" /> }
          </div>
          <p class="hint" style="margin-top:12px">
            TSB positivo quer dizer descansado; muito negativo por muitos dias seguidos costuma anteceder estafa.
          </p>
        </div>
      </section>

      <div class="grid cols-2">
        <!-- Curva de potencia -->
        <section class="card">
          <h2>Melhores esforcos</h2>
          @if (hasPower()) {
            <div class="chart-box">
              @if (powerConfig(); as cfg) { <app-chart [config]="cfg" /> }
            </div>
          } @else {
            <p class="hint">Sem dados de potencia nos arquivos. A evolucao esta sendo medida por FC e velocidade.</p>
          }
        </section>

        <!-- Tempo por zona -->
        <section class="card">
          <h2>Tempo por zona</h2>
          <div class="chart-box">
            @if (zonesConfig(); as cfg) { <app-chart [config]="cfg" /> }
          </div>
        </section>
      </div>

      <!-- Recordes -->
      <section class="section" style="margin-top:44px">
        <div class="section-head"><h2>Recordes pessoais</h2></div>
        <div class="grid cols-3">
          @for (item of recordList(); track item.label) {
            <a class="plate" [routerLink]="['/treinos', item.activityId]">
              <span class="label">{{ item.label }}</span>
              <span class="value">{{ item.display }}</span><span class="unit">{{ item.unit }}</span>
              <div class="foot">{{ item.date | rideDate: false }}</div>
            </a>
          }
        </div>
      </section>

      <!-- Ultimos pedais -->
      <section class="section">
        <div class="section-head">
          <h2>Ultimos pedais</h2>
          <a class="hint" routerLink="/treinos">ver todos →</a>
        </div>
        <div class="card">
          <table class="table-cards">
            <thead>
              <tr>
                <th>Data</th>
                <th class="num">km</th>
                <th class="num">Tempo</th>
                <th class="num">Media</th>
                <th class="num">Subida</th>
                <th class="num">FC</th>
                <th class="num">NP</th>
                <th class="num">TSS</th>
              </tr>
            </thead>
            <tbody>
              @for (ride of recent(); track ride.id) {
                <tr [routerLink]="['/treinos', ride.id]">
                  <td data-label="Data">{{ ride.started_at | rideDate }}</td>
                  <td class="num" data-label="km">{{ ride.distance_km | num: 1 }}</td>
                  <td class="num" data-label="Tempo">{{ ride.moving_time_s | duration }}</td>
                  <td class="num" data-label="Media">{{ ride.avg_speed_kmh | num: 1 }}</td>
                  <td class="num" data-label="Subida">{{ ride.elevation_gain_m | num: 0 }}</td>
                  <td class="num" data-label="FC">{{ ride.avg_hr | num: 0 }}</td>
                  <td class="num" data-label="NP">{{ ride.normalized_power | num: 0 }}</td>
                  <td class="num" data-label="TSS">{{ ride.tss | num: 0 }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    }
  `,
})
export class DashboardComponent implements OnInit {
  private api = inject(ApiService);

  readonly windows = [
    { label: '30 dias', days: 30 },
    { label: '90 dias', days: 90 },
    { label: '12 meses', days: 365 },
    { label: 'Tudo', days: 0 },
  ];

  loading = signal(true);
  empty = signal(false);
  window = signal(90);
  groupBy = signal<'week' | 'month'>('week');

  settings = signal<AthleteSettings | null>(null);
  totals = signal<Totals | null>(null);
  recent = signal<import('../core/models').ActivitySummary[]>([]);
  hasPower = signal(false);

  trendConfig = signal<ChartConfiguration | null>(null);
  pmcConfig = signal<ChartConfiguration | null>(null);
  powerConfig = signal<ChartConfiguration | null>(null);
  zonesConfig = signal<ChartConfiguration | null>(null);
  recordList = signal<{ label: string; display: string; unit: string; date: string; activityId: number }[]>([]);

  ngOnInit(): void {
    this.load();
  }

  setWindow(days: number): void {
    this.window.set(days);
    this.load();
  }

  setGroup(group: 'week' | 'month'): void {
    this.groupBy.set(group);
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    const days = this.window() || undefined;

    forkJoin({
      settings: this.api.settings(),
      totals: this.api.totals(days),
      trend: this.api.trend(this.groupBy(), this.window() || 3650),
      pmc: this.api.pmc(this.window() || 3650),
      power: this.api.powerCurve(days),
      zones: this.api.zones(this.window() || 3650),
      records: this.api.records(),
      recent: this.api.activities(8),
    }).subscribe({
      next: (data) => {
        this.settings.set(data.settings);
        this.totals.set(data.totals);
        this.recent.set(data.recent);
        this.empty.set(data.totals.activities === 0 && data.recent.length === 0);
        this.hasPower.set(data.power.length > 0);
        this.buildTrend(data.trend);
        this.buildPmc(data.pmc);
        this.buildPower(data.power);
        this.buildZones(data.zones);
        this.buildRecords(data.records);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.empty.set(true);
      },
    });
  }

  private buildTrend(points: import('../core/models').TrendPoint[]): void {
    this.trendConfig.set({
      type: 'bar',
      data: {
        labels: points.map((p) => p.period),
        datasets: [
          {
            type: 'bar',
            label: 'Distancia (km)',
            data: points.map((p) => p.distance_km),
            backgroundColor: INK,
            borderRadius: 2,
            yAxisID: 'y',
            order: 2,
          },
          {
            type: 'line',
            label: 'Carga (TSS)',
            data: points.map((p) => p.tss),
            borderColor: WATT,
            backgroundColor: WATT,
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.25,
            yAxisID: 'y1',
            order: 1,
          },
        ],
      },
      options: {
        scales: {
          y: { position: 'left', grid: { color: GRID }, title: { display: true, text: 'km' } },
          y1: { position: 'right', grid: { display: false }, title: { display: true, text: 'TSS' } },
          x: { grid: { display: false } },
        },
        plugins: { legend: { labels: { boxWidth: 10, boxHeight: 10 } } },
      },
    });
  }

  private buildPmc(points: import('../core/models').PmcPoint[]): void {
    this.pmcConfig.set({
      type: 'line',
      data: {
        labels: points.map((p) => p.date),
        datasets: [
          {
            label: 'CTL (base)',
            data: points.map((p) => p.ctl),
            borderColor: INK,
            backgroundColor: INK_FILL,
            fill: true,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
          },
          {
            label: 'ATL (fadiga)',
            data: points.map((p) => p.atl),
            borderColor: PULSE,
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.3,
          },
          {
            label: 'TSB (forma)',
            data: points.map((p) => p.tsb),
            borderColor: CLIMB,
            borderWidth: 1.5,
            borderDash: [4, 3],
            pointRadius: 0,
            tension: 0.3,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        scales: {
          y: { grid: { color: GRID } },
          y1: { position: 'right', grid: { display: false } },
          x: { ticks: { maxTicksLimit: 10 }, grid: { display: false } },
        },
        plugins: { legend: { labels: { boxWidth: 10, boxHeight: 10 } } },
      },
    });
  }

  private buildPower(points: import('../core/models').PowerCurvePoint[]): void {
    this.powerConfig.set({
      type: 'line',
      data: {
        labels: points.map((p) => this.shortDuration(p.seconds)),
        datasets: [
          {
            label: 'Melhor potencia media (W)',
            data: points.map((p) => p.watts),
            borderColor: WATT,
            backgroundColor: WATT_FILL,
            fill: true,
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: WATT,
            tension: 0.2,
          },
        ],
      },
      options: {
        scales: {
          y: { grid: { color: GRID }, title: { display: true, text: 'watts' } },
          x: { grid: { display: false }, title: { display: true, text: 'duracao do esforco' } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  private buildZones(zones: import('../core/models').Zones): void {
    const source = zones.power.length ? zones.power : zones.heart_rate;
    const color = zones.power.length ? WATT : PULSE;
    this.zonesConfig.set({
      type: 'bar',
      data: {
        labels: source.map((z) => z.zone),
        datasets: [
          {
            label: 'Horas',
            data: source.map((z) => Math.round((z.seconds / 3600) * 10) / 10),
            backgroundColor: color,
            borderRadius: 2,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        scales: {
          x: { grid: { color: GRID }, title: { display: true, text: 'horas' } },
          y: { grid: { display: false } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  private buildRecords(records: Records): void {
    const map: { key: string; label: string; unit: string; digits: number }[] = [
      { key: 'longest_distance_km', label: 'Pedal mais longo', unit: 'km', digits: 1 },
      { key: 'biggest_climb_m', label: 'Mais altimetria', unit: 'm', digits: 0 },
      { key: 'fastest_avg_kmh', label: 'Media mais rapida', unit: 'km/h', digits: 1 },
      { key: 'top_speed_kmh', label: 'Velocidade maxima', unit: 'km/h', digits: 1 },
      { key: 'best_normalized_power', label: 'Melhor NP', unit: 'W', digits: 0 },
      { key: 'hardest_tss', label: 'Treino mais duro', unit: 'TSS', digits: 0 },
    ];

    this.recordList.set(
      map
        .map((item) => {
          const entry = records[item.key];
          if (!entry) {
            return null;
          }
          return {
            label: item.label,
            display: entry.value.toLocaleString('pt-BR', {
              minimumFractionDigits: item.digits,
              maximumFractionDigits: item.digits,
            }),
            unit: item.unit,
            date: entry.date,
            activityId: entry.activity_id,
          };
        })
        .filter((item): item is NonNullable<typeof item> => item !== null),
    );
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
