// Construtores dos graficos das quatro dimensoes (cadencia, pacing, zonas,
// terreno). Compartilhados entre a aba Treinador (insight curto) e a aba
// Tecnica (guia detalhado), para nao duplicar a logica.
import { ChartConfiguration } from 'chart.js';
import { CLIMB, INK, MUTED, SECONDARY, WATT } from '../core/theme';
import { InsightSummary } from '../core/models';

// Segundos por categoria -> barras de minutos. Cor unica ou por barra.
export function buildBars(
  seconds: Record<string, number>,
  color: string | string[],
): ChartConfiguration | null {
  const labels = Object.keys(seconds);
  if (!labels.length) {
    return null;
  }
  return {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'min',
          data: labels.map((k) => Math.round(seconds[k] / 60)),
          backgroundColor: color,
          borderRadius: 2,
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { title: { display: true, text: 'minutos' } }, x: { grid: { display: false } } },
    },
  };
}

export function buildPacing(summary: InsightSummary): ChartConfiguration | null {
  const q = summary.pacing.quarters_power;
  if (!q?.length) {
    return null;
  }
  return {
    type: 'bar',
    data: {
      labels: ['1º quarto', '2º', '3º', 'fim'],
      datasets: [{ label: 'W', data: q, backgroundColor: WATT, borderRadius: 2 }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { title: { display: true, text: 'potência (W)' } }, x: { grid: { display: false } } },
    },
  };
}

// A faixa ideal (75-90) ganha o verde; as outras ficam em tinta.
export function cadenceColors(summary: InsightSummary): string[] {
  return Object.keys(summary.cadence.seconds).map((k) => (k.startsWith('Ideal') ? CLIMB : INK));
}

// Cores do grafico de terreno: subida (verde), plano (neutro), descida (grafite).
export const TERRAIN_COLORS = [CLIMB, MUTED, SECONDARY];

export const ZONE_COLOR = WATT;
