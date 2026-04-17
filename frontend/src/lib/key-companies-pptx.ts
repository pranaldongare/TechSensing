/* eslint-disable @typescript-eslint/no-explicit-any */
import PptxGenJS from 'pptxgenjs';
import type { KeyCompaniesReport, KeyCompanyBriefing } from './api';

const PRIMARY = '1e3a5f';
const ACCENT = 'f59e0b';
const SLATE_TEXT = '1f2937';
const SLATE_MUTED = '64748b';

function sanitize(s: string | undefined | null): string {
  if (!s) return '';
  return String(s)
    .replace(/≥/g, '>=')
    .replace(/≤/g, '<=')
    .replace(/×/g, 'x')
    .replace(/[""]/g, '"')
    .replace(/‑|–|—/g, '-');
}

function truncate(s: string, n: number): string {
  const clean = sanitize(s);
  return clean.length <= n ? clean : clean.slice(0, n - 1) + '…';
}

function titleBar(slide: PptxGenJS.Slide, title: string) {
  slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
    x: 0,
    y: 0,
    w: 10,
    h: 0.6,
    fill: { color: PRIMARY },
    line: { color: PRIMARY },
  });
  slide.addText(title, {
    x: 0.3,
    y: 0.12,
    w: 9.4,
    h: 0.36,
    fontSize: 18,
    bold: true,
    color: 'FFFFFF',
  });
}

/** Download a PPTX for a Key Companies briefing (#21). */
export async function downloadKeyCompaniesPptx(
  report: KeyCompaniesReport,
  filename?: string,
): Promise<void> {
  const pres = new PptxGenJS();
  pres.defineLayout({ name: 'KC16x9', width: 10, height: 5.625 });
  pres.layout = 'KC16x9';

  // ── Cover slide ──
  {
    const slide = pres.addSlide();
    slide.background = { color: 'F8FAFC' };
    slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
      x: 0,
      y: 0,
      w: 10,
      h: 1.6,
      fill: { color: PRIMARY },
      line: { color: PRIMARY },
    });
    slide.addText('Key Companies — Weekly Briefing', {
      x: 0.5,
      y: 0.3,
      w: 9,
      h: 0.6,
      fontSize: 28,
      bold: true,
      color: 'FFFFFF',
    });
    slide.addText(
      `${report.period_start || '—'} → ${report.period_end || '—'}`,
      {
        x: 0.5,
        y: 0.95,
        w: 9,
        h: 0.4,
        fontSize: 16,
        color: 'E0E7FF',
      },
    );
    slide.addText(
      [
        { text: `Companies analyzed: ${report.companies_analyzed.length}\n` },
        {
          text: report.highlight_domain
            ? `Highlight domain: ${report.highlight_domain}\n`
            : '',
        },
        {
          text: `Total updates: ${(report.briefings || []).reduce(
            (s, b) => s + (b.updates?.length || 0),
            0,
          )}`,
        },
      ],
      {
        x: 0.5,
        y: 1.9,
        w: 9,
        h: 2,
        fontSize: 14,
        color: SLATE_TEXT,
      },
    );
    slide.addText(report.companies_analyzed.join(' · '), {
      x: 0.5,
      y: 4.2,
      w: 9,
      h: 0.8,
      fontSize: 12,
      color: SLATE_MUTED,
    });
  }

  // ── Cross-company summary ──
  if (report.cross_company_summary) {
    const slide = pres.addSlide();
    titleBar(slide, 'Cross-company summary');
    slide.addText(truncate(report.cross_company_summary, 1800), {
      x: 0.4,
      y: 0.9,
      w: 9.2,
      h: 4.4,
      fontSize: 14,
      color: SLATE_TEXT,
      valign: 'top',
    });
  }

  // ── Domain rollup ──
  if (report.domain_rollup && report.domain_rollup.length > 0) {
    const slide = pres.addSlide();
    titleBar(slide, 'Domain rollup');
    const rows: PptxGenJS.TableRow[] = [
      [
        { text: 'Domain', options: { bold: true, fill: { color: 'EEF2FF' } } },
        { text: 'Updates', options: { bold: true, fill: { color: 'EEF2FF' } } },
        {
          text: 'Companies',
          options: { bold: true, fill: { color: 'EEF2FF' } },
        },
      ],
      ...report.domain_rollup
        .slice(0, 12)
        .map(
          (d) =>
            [
              { text: sanitize(d.domain) },
              { text: String(d.update_count) },
              { text: String(d.company_count) },
            ] as PptxGenJS.TableRow,
        ),
    ];
    slide.addTable(rows, {
      x: 0.5,
      y: 0.9,
      w: 9,
      fontSize: 12,
      color: SLATE_TEXT,
      border: { type: 'solid', pt: 0.5, color: 'E2E8F0' },
    });
  }

  // ── Per-company slides ──
  (report.briefings || []).forEach((b: KeyCompanyBriefing) => {
    const slide = pres.addSlide();
    titleBar(slide, b.company || 'Company');

    // Top-right meta (momentum + update count)
    const metaLines = [
      `Updates: ${b.updates?.length || 0}`,
      `Sources: ${b.sources_used || 0}`,
    ];
    if (b.momentum?.score !== undefined) {
      const score = Math.round(b.momentum.score || 0);
      const band = score >= 70 ? 'High' : score >= 40 ? 'Moderate' : 'Quiet';
      metaLines.push(`Momentum: ${score} (${band})`);
    }
    slide.addText(metaLines.join('  ·  '), {
      x: 0.4,
      y: 0.68,
      w: 9.2,
      h: 0.3,
      fontSize: 11,
      color: ACCENT,
      italic: true,
    });

    if (b.overall_summary) {
      slide.addText(truncate(b.overall_summary, 600), {
        x: 0.4,
        y: 1.0,
        w: 9.2,
        h: 1.4,
        fontSize: 12,
        color: SLATE_TEXT,
        valign: 'top',
      });
    }

    const updates = (b.updates || []).slice(0, 4);
    updates.forEach((u, idx) => {
      const y = 2.5 + idx * 0.7;
      slide.addText(
        [
          {
            text: `[${u.category || 'Other'}] `,
            options: { bold: true, color: '9a3412' },
          },
          {
            text: truncate(u.headline, 140),
            options: { color: SLATE_TEXT },
          },
        ],
        {
          x: 0.4,
          y,
          w: 9.2,
          h: 0.4,
          fontSize: 12,
        },
      );
      if (u.summary) {
        slide.addText(truncate(u.summary, 200), {
          x: 0.6,
          y: y + 0.35,
          w: 9,
          h: 0.32,
          fontSize: 10,
          color: SLATE_MUTED,
        });
      }
    });
  });

  // ── Closing slide (methodology) ──
  {
    const slide = pres.addSlide();
    titleBar(slide, 'About this briefing');
    slide.addText(
      'This briefing was generated by Tech Sensing — Key Companies. ' +
        'Evidence is aggregated across DuckDuckGo web search and, when enabled, ' +
        'RSS feeds, GitHub, arXiv, press wires, YouTube, EDGAR filings, and patents. ' +
        'Confidence in single-sourced claims is automatically downgraded. ' +
        'Momentum, sentiment, and diff-vs-previous-run are computed locally.',
      {
        x: 0.5,
        y: 1.2,
        w: 9,
        h: 3,
        fontSize: 13,
        color: SLATE_TEXT,
        valign: 'top',
      },
    );
  }

  const base =
    report.period_start && report.period_end
      ? `KeyCompanies_${report.period_start}_to_${report.period_end}.pptx`
      : 'KeyCompanies.pptx';
  await pres.writeFile({ fileName: filename || base });
}
