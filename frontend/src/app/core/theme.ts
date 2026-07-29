/**
 * Fonte unica de cor do app, para o JavaScript.
 *
 * O CSS tem as mesmas cores em `:root` do styles.css. Este arquivo existe porque
 * Chart.js e Leaflet precisam do valor em JS, nao em CSS - e antes disso cada
 * componente declarava o proprio hexadecimal. Eram 28 ocorrencias em 6 arquivos,
 * o que transformava "trocar a paleta" numa cacada onde sempre sobrava uma tela.
 *
 * REGRA: nenhum hexadecimal fora deste arquivo. Se precisar de uma cor, importe.
 */

/** Superficie e texto. */
export const PAPER = '#FBFAF7';
export const PAPER_DEEP = '#F2EFE8';
export const RULE = '#DDD8CC';
/** Subtexto e rotulos. 7,00:1 sobre o papel - passa AAA. */
export const SECONDARY = '#5A564D';
/** Texto principal. 16,70:1. */
export const INK = '#1A1A18';
/** SO decorativo e desabilitado. 3,53:1 - reprova em AA, nunca use em texto a ler. */
export const MUTED = '#8A8578';

/**
 * Familias semanticas. Cada cor significa UMA coisa - nunca decore com elas.
 * As tres tem contraste proximo de proposito (5,60 / 5,10 / 5,03), para que
 * nenhuma se destaque por acidente de luminosidade.
 */
export const PULSE = '#B8324A'; // frequencia cardiaca
export const WATT = '#9A5D04'; // potencia
export const CLIMB = '#1F7A5E'; // altimetria

/** Versoes translucidas, para preenchimento sob linha de grafico. */
export const INK_FILL = 'rgba(26, 26, 24, 0.08)';
export const CLIMB_FILL = 'rgba(31, 122, 94, 0.15)';
export const WATT_FILL = 'rgba(154, 93, 4, 0.12)';
export const GRID = 'rgba(26, 26, 24, 0.07)';

/** Trilho de barra: o vazio precisa ser visivel. */
export const TRACK = '#EFEADE';
export const TRACK_EDGE = '#C4BCA8';

/**
 * Rampas do mapa de trajeto, uma por metrica. Cada uma vai do claro ao escuro
 * da familia correspondente - velocidade e altitude nao tem familia propria e
 * usam tinta e verde respectivamente.
 */
export const MAP_RAMPS = {
  speed: ['#C3CBD4', '#6E7E8E', '#1A1A18'],
  power: ['#EBD5A8', '#C79433', '#9A5D04'],
  hr: ['#E9C0C9', '#CE6D80', '#B8324A'],
  cadence: ['#BDD8CE', '#5E9E88', '#1F7A5E'],
  altitude: ['#D4D2C4', '#8F9A7E', '#4A5C33'],
} as const;

export const FONT_BODY = "Inter, system-ui, -apple-system, sans-serif";
export const FONT_DISPLAY = "Fraunces, 'Times New Roman', serif";
