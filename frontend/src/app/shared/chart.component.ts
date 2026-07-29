import {
  AfterViewInit,
  Component,
  ElementRef,
  Input,
  OnChanges,
  OnDestroy,
  ViewChild,
} from '@angular/core';
import { Chart, ChartConfiguration, registerables } from 'chart.js';
import { FONT_BODY, RULE, SECONDARY } from '../core/theme';

Chart.register(...registerables);

// Defaults alinhados ao sistema visual: Inter nos rotulos, secundario na cor
// (7,00:1 sobre o papel), e algarismos alinhados como no resto do app.
Chart.defaults.font.family = FONT_BODY;
Chart.defaults.font.size = 11;
Chart.defaults.color = SECONDARY;
Chart.defaults.borderColor = RULE;

@Component({
  selector: 'app-chart',
  standalone: true,
  template: '<canvas #canvas></canvas>',
  styles: [':host { display: block; position: relative; height: 100%; }'],
})
export class ChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input({ required: true }) config!: ChartConfiguration;
  @ViewChild('canvas') canvasRef!: ElementRef<HTMLCanvasElement>;

  private chart?: Chart;

  ngAfterViewInit(): void {
    this.render();
  }

  ngOnChanges(): void {
    if (this.chart) {
      this.render();
    }
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private render(): void {
    if (!this.canvasRef || !this.config) {
      return;
    }
    this.chart?.destroy();
    this.chart = new Chart(this.canvasRef.nativeElement, {
      ...this.config,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        ...(this.config.options ?? {}),
      },
    });
  }
}
