import {
  AfterViewInit,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import * as L from 'leaflet';
import { RouteAdvicePoint, RoutePoint } from '../core/models';
import { CLIMB, PAPER, SECONDARY, WATT } from '../core/theme';

// Verde para trecho bom, laranja (potencia) para trecho a melhorar.
function verdictColor(p: RouteAdvicePoint): string {
  return p.verdict === 'bom' ? CLIMB : WATT;
}

// Mapa do percurso com os pontos de melhoria ancorados: a linha do trajeto em
// tom neutro, pinos numerados nos trechos-chave e o trecho ativo aceso. O
// destaque e a "seta" que liga a recomendacao (na lista ao lado) ao ponto do
// mapa, controlada pelo input `active`.
@Component({
  selector: 'app-advice-map',
  standalone: true,
  template: '<div #map class="advice-map"></div>',
  styles: [
    `
      .advice-map {
        width: 100%; height: 420px; border: 1px solid var(--rule);
        border-radius: var(--radius); overflow: hidden;
      }
    `,
  ],
})
export class AdviceMapComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() points: RoutePoint[] = [];
  @Input() advice: RouteAdvicePoint[] = [];
  @Input() active: number | null = null;
  @Output() activeChange = new EventEmitter<number | null>();

  @ViewChild('map', { static: true }) mapRef!: ElementRef<HTMLDivElement>;

  private map?: L.Map;
  private trackLayer = L.layerGroup();
  private pinLayer = L.layerGroup();
  private highlightLayer = L.layerGroup();

  ngAfterViewInit(): void {
    this.build();
  }

  ngOnChanges(ch: SimpleChanges): void {
    if (!this.map) {
      return;
    }
    // Rota + enquadramento so quando muda o treino; no hover (active) so o destaque.
    if (ch['points'] || ch['advice']) {
      this.drawTrack();
    }
    this.drawHighlight();
  }

  ngOnDestroy(): void {
    this.map?.remove();
  }

  private build(): void {
    this.map = L.map(this.mapRef.nativeElement, { scrollWheelZoom: false, attributionControl: true });
    const esri = 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors';
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      attribution: esri,
      maxZoom: 16,
    }).addTo(this.map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 16,
    }).addTo(this.map);
    this.trackLayer.addTo(this.map);
    this.highlightLayer.addTo(this.map);
    this.pinLayer.addTo(this.map);
    this.drawTrack();
    this.drawHighlight();
  }

  private drawTrack(): void {
    if (!this.map || !this.points.length) {
      return;
    }
    this.trackLayer.clearLayers();
    this.pinLayer.clearLayers();

    L.polyline(
      this.points.map((p) => [p.lat, p.lon] as L.LatLngExpression),
      { color: SECONDARY, weight: 4, opacity: 0.85, lineCap: 'round' },
    ).addTo(this.trackLayer);

    for (const a of this.advice) {
      this.pinLayer.addLayer(this.pin(a, a.order === this.active));
    }

    const bounds = L.latLngBounds(this.points.map((p) => [p.lat, p.lon] as L.LatLngExpression));
    this.map.fitBounds(bounds, { padding: [26, 26] });
  }

  private drawHighlight(): void {
    if (!this.map) {
      return;
    }
    this.highlightLayer.clearLayers();
    const a = this.advice.find((x) => x.order === this.active);
    if (!a) {
      // Sem trecho ativo, redesenha os pinos no estado normal.
      this.redrawPins();
      return;
    }
    const slice = this.points.filter((p) => p.i >= a.start_index && p.i <= a.end_index);
    if (slice.length) {
      const latlngs = slice.map((p) => [p.lat, p.lon] as L.LatLngExpression);
      const color = verdictColor(a);
      // Halo largo por baixo + a rota acesa na cor do veredito (verde/laranja).
      L.polyline(latlngs, { color, weight: 14, opacity: 0.25, lineCap: 'round' }).addTo(this.highlightLayer);
      L.polyline(latlngs, { color, weight: 6, opacity: 1, lineCap: 'round' }).addTo(this.highlightLayer);
    }
    this.redrawPins();
  }

  private redrawPins(): void {
    this.pinLayer.clearLayers();
    for (const a of this.advice) {
      this.pinLayer.addLayer(this.pin(a, a.order === this.active));
    }
  }

  private pin(a: RouteAdvicePoint, isActive: boolean): L.Marker {
    const size = isActive ? 30 : 24;
    const bg = verdictColor(a);
    const icon = L.divIcon({
      className: '',
      html:
        '<div style="background:' + bg + ';color:' + PAPER + ';width:' + size + 'px;height:' + size +
        'px;border-radius:50%;display:flex;align-items:center;justify-content:center;' +
        'font:600 ' + (isActive ? 14 : 12) + 'px/1 IBM Plex Mono,monospace;' +
        'box-shadow:0 1px 5px rgba(0,0,0,.35);border:2px solid ' + PAPER + '">' + a.order + '</div>',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
    const marker = L.marker([a.lat, a.lon], { icon, zIndexOffset: isActive ? 1000 : 0 });
    marker.on('click', () => this.activeChange.emit(a.order));
    marker.on('mouseover', () => this.activeChange.emit(a.order));
    return marker;
  }
}
