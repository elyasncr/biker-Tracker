import {
  AfterViewInit,
  Component,
  ElementRef,
  Input,
  OnChanges,
  OnDestroy,
  ViewChild,
} from '@angular/core';
import * as L from 'leaflet';
import { RoutePoint, SegmentHighlight } from '../core/models';

export type MapMetric = 'speed' | 'power' | 'hr' | 'cadence' | 'altitude';

interface Ramp {
  label: string;
  unit: string;
  colors: string[];
}

const RAMPS: Record<MapMetric, Ramp> = {
  speed: { label: 'Velocidade', unit: 'km/h', colors: ['#9db4c4', '#4f7d96', '#16303f'] },
  power: { label: 'Potencia', unit: 'W', colors: ['#f0dcae', '#e2ad3c', '#a8620a'] },
  hr: { label: 'Frequencia cardiaca', unit: 'bpm', colors: ['#e8bcc9', '#d15b7f', '#8c0f38'] },
  cadence: { label: 'Cadencia', unit: 'rpm', colors: ['#b7d8cd', '#4f9e88', '#1c5546'] },
  altitude: { label: 'Altitude', unit: 'm', colors: ['#cfd9c4', '#8aa06f', '#4a5c33'] },
};

@Component({
  selector: 'app-route-map',
  standalone: true,
  template: `
    <div class="map-toolbar">
      <span class="eyebrow">Colorir por</span>
      @for (option of available; track option) {
        <button class="chip" [class.active]="metric === option" (click)="setMetric(option)">
          {{ ramps[option].label }}
        </button>
      }
      <span class="scale" [style.background]="scaleGradient()"></span>
      <span class="mono scale-labels">{{ range()[0] }} – {{ range()[1] }} {{ ramps[metric].unit }}</span>
    </div>
    <div #map class="map-canvas"></div>
  `,
  styles: [
    `
      :host { display: block; }
      .map-toolbar {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        padding: 12px 14px;
        border-bottom: 1px solid var(--rule);
      }
      .map-canvas { height: 460px; width: 100%; }
      .scale {
        width: 90px;
        height: 8px;
        border-radius: 4px;
        margin-left: auto;
      }
      .scale-labels { font-size: 0.7rem; color: var(--graphite); }
      @media (max-width: 620px) {
        .map-canvas { height: 320px; }
        .scale, .scale-labels { display: none; }
      }
    `,
  ],
})
export class RouteMapComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input({ required: true }) points: RoutePoint[] = [];
  @Input() best: SegmentHighlight | null = null;
  @Input() worst: SegmentHighlight | null = null;

  @ViewChild('map') mapRef!: ElementRef<HTMLDivElement>;

  readonly ramps = RAMPS;
  metric: MapMetric = 'speed';
  available: MapMetric[] = ['speed'];

  private map?: L.Map;
  private trackLayer = L.layerGroup();
  private markerLayer = L.layerGroup();

  ngAfterViewInit(): void {
    this.buildMap();
  }

  ngOnChanges(): void {
    this.available = (['speed', 'power', 'hr', 'cadence', 'altitude'] as MapMetric[]).filter((m) =>
      this.points.some((p) => p[m] !== null && p[m] !== undefined),
    );
    if (!this.available.includes(this.metric) && this.available.length) {
      this.metric = this.available[0];
    }
    if (this.map) {
      this.draw();
    }
  }

  ngOnDestroy(): void {
    this.map?.remove();
  }

  setMetric(metric: MapMetric): void {
    this.metric = metric;
    this.draw();
  }

  range(): [number, number] {
    const values = this.values();
    if (!values.length) {
      return [0, 0];
    }
    return [Math.round(this.quantile(values, 0.05)), Math.round(this.quantile(values, 0.95))];
  }

  scaleGradient(): string {
    return 'linear-gradient(to right, ' + RAMPS[this.metric].colors.join(', ') + ')';
  }

  private buildMap(): void {
    this.map = L.map(this.mapRef.nativeElement, { scrollWheelZoom: false, attributionControl: true });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      maxZoom: 19,
    }).addTo(this.map);
    this.trackLayer.addTo(this.map);
    this.markerLayer.addTo(this.map);
    this.draw();
  }

  /**
   * O trajeto e desenhado em pedacos curtos, cada um com a cor do valor medio
   * daquele pedaco. E o que transforma a linha num grafico sobre o mapa: da para
   * ver a subida onde a potencia subiu e o trecho onde a velocidade caiu.
   */
  private draw(): void {
    if (!this.map || !this.points.length) {
      return;
    }
    this.trackLayer.clearLayers();
    this.markerLayer.clearLayers();

    const values = this.values();
    const low = values.length ? this.quantile(values, 0.05) : 0;
    const high = values.length ? this.quantile(values, 0.95) : 1;
    const chunk = Math.max(2, Math.floor(this.points.length / 240));

    for (let i = 0; i < this.points.length - 1; i += chunk) {
      const slice = this.points.slice(i, Math.min(i + chunk + 1, this.points.length));
      const latlngs = slice.map((p) => [p.lat, p.lon] as L.LatLngExpression);
      const metricValues = slice.map((p) => p[this.metric]).filter((v): v is number => v !== null && v !== undefined);
      const avg = metricValues.length ? metricValues.reduce((a, b) => a + b, 0) / metricValues.length : low;
      L.polyline(latlngs, {
        color: this.colorFor(avg, low, high),
        weight: 5,
        opacity: 0.95,
        lineCap: 'round',
      }).addTo(this.trackLayer);
    }

    this.kilometreMarkers();
    this.marker(this.points[0], 'Largada', '#16303f');
    this.marker(this.points[this.points.length - 1], 'Chegada', '#16303f');

    if (this.best) {
      this.highlight(this.best, 'MELHOR', '#2e7d6b');
    }
    if (this.worst) {
      this.highlight(this.worst, 'PIOR', '#b81d4c');
    }

    const bounds = L.latLngBounds(this.points.map((p) => [p.lat, p.lon] as L.LatLngExpression));
    this.map.fitBounds(bounds, { padding: [24, 24] });
  }

  private highlight(segment: SegmentHighlight, label: string, color: string): void {
    const slice = this.points.filter((p) => p.i >= segment.start_index && p.i <= segment.end_index);
    if (!slice.length) {
      return;
    }
    L.polyline(
      slice.map((p) => [p.lat, p.lon] as L.LatLngExpression),
      { color, weight: 10, opacity: 0.35, lineCap: 'round' },
    ).addTo(this.markerLayer);

    const anchor = slice[Math.floor(slice.length / 2)];
    const icon = L.divIcon({
      className: '',
      html:
        '<div style="background:' +
        color +
        ';color:#fff;font:600 10px/1 IBM Plex Mono,monospace;letter-spacing:.1em;' +
        'padding:5px 8px;border-radius:2px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.3)">' +
        label +
        '</div>',
      iconAnchor: [22, 10],
    });
    L.marker([anchor.lat, anchor.lon], { icon })
      .bindPopup(
        '<strong>' +
          label +
          ' MOMENTO</strong><br>km ' +
          segment.start_km +
          ' a ' +
          segment.end_km +
          '<br>' +
          segment.terrain +
          ', ' +
          segment.gradient +
          '%',
      )
      .addTo(this.markerLayer);
  }

  /** Marcos de quilometro, como o app do iGPSPORT mostra na tela do trajeto. */
  private kilometreMarkers(): void {
    const total = this.points[this.points.length - 1]?.km ?? 0;
    if (total < 2) {
      return;
    }
    const step = total > 60 ? 10 : total > 25 ? 5 : 2;
    let next = step;
    for (const point of this.points) {
      if (point.km !== null && point.km >= next) {
        const icon = L.divIcon({
          className: '',
          html:
            '<div style="background:#16303f;color:#fff;font:500 10px/1 IBM Plex Mono,monospace;' +
            'width:20px;height:20px;border-radius:50%;display:flex;align-items:center;' +
            'justify-content:center;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.35)">' +
            next +
            '</div>',
          iconAnchor: [12, 12],
        });
        L.marker([point.lat, point.lon], { icon }).bindPopup('km ' + next).addTo(this.markerLayer);
        next += step;
        if (next > total) {
          break;
        }
      }
    }
  }

  private marker(point: RoutePoint, label: string, color: string): void {
    L.circleMarker([point.lat, point.lon], {
      radius: 6,
      color: '#fff',
      weight: 2,
      fillColor: color,
      fillOpacity: 1,
    })
      .bindPopup(label)
      .addTo(this.markerLayer);
  }

  private values(): number[] {
    return this.points.map((p) => p[this.metric]).filter((v): v is number => v !== null && v !== undefined);
  }

  private colorFor(value: number, low: number, high: number): string {
    const colors = RAMPS[this.metric].colors;
    const span = high - low || 1;
    const t = Math.min(1, Math.max(0, (value - low) / span));
    const scaled = t * (colors.length - 1);
    const index = Math.min(colors.length - 2, Math.floor(scaled));
    return this.mix(colors[index], colors[index + 1], scaled - index);
  }

  private mix(from: string, to: string, t: number): string {
    const parse = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    const [r1, g1, b1] = parse(from);
    const [r2, g2, b2] = parse(to);
    const channel = (a: number, b: number) => Math.round(a + (b - a) * t);
    return 'rgb(' + channel(r1, r2) + ',' + channel(g1, g2) + ',' + channel(b1, b2) + ')';
  }

  private quantile(values: number[], q: number): number {
    const sorted = [...values].sort((a, b) => a - b);
    const pos = (sorted.length - 1) * q;
    const base = Math.floor(pos);
    const rest = pos - base;
    return sorted[base + 1] !== undefined ? sorted[base] + rest * (sorted[base + 1] - sorted[base]) : sorted[base];
  }
}
