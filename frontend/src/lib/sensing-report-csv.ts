/**
 * Tabular exports for sensing data (#22).
 *
 * Two formats, no extra deps:
 *   - CSV    — RFC-4180 compliant; opens in Excel / Sheets / Numbers.
 *   - XLS    — HTML-table with `.xls` extension and
 *              `application/vnd.ms-excel` MIME type. Excel opens these
 *              natively as a "Web Worksheet". This avoids pulling in
 *              SheetJS / ExcelJS (~1MB of bundle).
 */

import type {
  CompanyAnalysisReport,
  KeyCompaniesReport,
  KeyCompanyUpdate,
} from './api';

function escapeCsv(v: unknown): string {
  const s = v === null || v === undefined ? '' : String(v);
  if (/[",\r\n]/.test(s)) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function toCsv(rows: (string | number)[][]): string {
  return rows.map((r) => r.map(escapeCsv).join(',')).join('\r\n');
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function escapeHtml(v: unknown): string {
  const s = v === null || v === undefined ? '' : String(v);
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

interface Sheet {
  name: string;
  rows: (string | number)[][];
}

function buildXlsHtml(sheets: Sheet[]): string {
  // Office "Web Archive" spreadsheet — Excel opens as multi-sheet.
  const tables = sheets
    .map((sheet) => {
      const [header, ...body] = sheet.rows;
      const thead = header
        ? `<thead><tr>${header
            .map((h) => `<th>${escapeHtml(h)}</th>`)
            .join('')}</tr></thead>`
        : '';
      const tbody = body
        .map(
          (r) =>
            `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`,
        )
        .join('');
      return `<table>${thead}<tbody>${tbody}</tbody></table>`;
    })
    .join('<br/>');
  return `<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body>${tables}</body></html>`;
}

// ────────────────────────── Key Companies ─────────────────────────

function keyCompaniesRows(
  report: KeyCompaniesReport,
): (string | number)[][] {
  const header: (string | number)[] = [
    'Company',
    'Date',
    'Category',
    'Domain',
    'Headline',
    'Summary',
    'Sentiment',
    'Diff',
    'Source URL',
  ];
  const rows: (string | number)[][] = [header];
  for (const b of report.briefings || []) {
    for (const u of (b.updates || []) as KeyCompanyUpdate[]) {
      rows.push([
        b.company,
        u.date || '',
        u.category || '',
        u.domain || '',
        u.headline || '',
        u.summary || '',
        u.sentiment || '',
        u.diff?.status || '',
        u.source_url || '',
      ]);
    }
  }
  return rows;
}

function keyCompaniesRollupRows(
  report: KeyCompaniesReport,
): (string | number)[][] {
  const header: (string | number)[] = [
    'Domain',
    'Update count',
    'Company count',
  ];
  const rows: (string | number)[][] = [header];
  for (const d of report.domain_rollup || []) {
    rows.push([d.domain, d.update_count, d.company_count]);
  }
  return rows;
}

function keyCompaniesMomentumRows(
  report: KeyCompaniesReport,
): (string | number)[][] {
  const header: (string | number)[] = [
    'Company',
    'Momentum score',
    'Update count',
    'Sources used',
    'Top drivers',
  ];
  const rows: (string | number)[][] = [header];
  for (const b of report.briefings || []) {
    rows.push([
      b.company,
      b.momentum?.score ?? '',
      b.updates?.length ?? 0,
      b.sources_used ?? 0,
      (b.momentum?.top_drivers || []).join(' · '),
    ]);
  }
  return rows;
}

/** CSV: flat updates table. */
export function downloadKeyCompaniesCsv(
  report: KeyCompaniesReport,
  filename?: string,
): void {
  const csv = toCsv(keyCompaniesRows(report));
  triggerDownload(
    new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }),
    filename || 'key_companies_updates.csv',
  );
}

/** XLS: three sheets — Updates, Domain rollup, Momentum. */
export function downloadKeyCompaniesXls(
  report: KeyCompaniesReport,
  filename?: string,
): void {
  const html = buildXlsHtml([
    { name: 'Updates', rows: keyCompaniesRows(report) },
    { name: 'DomainRollup', rows: keyCompaniesRollupRows(report) },
    { name: 'Momentum', rows: keyCompaniesMomentumRows(report) },
  ]);
  triggerDownload(
    new Blob(['\uFEFF' + html], {
      type: 'application/vnd.ms-excel;charset=utf-8',
    }),
    filename || 'key_companies.xls',
  );
}

// ────────────────────────── Company Analysis ──────────────────────

function companyAnalysisFindingsRows(
  report: CompanyAnalysisReport,
): (string | number)[][] {
  const header: (string | number)[] = [
    'Company',
    'Technology',
    'Stance',
    'Confidence',
    'Summary',
    'Products',
    'Recent developments',
    'Partnerships',
    'Investment signal',
    'Sources',
  ];
  const rows: (string | number)[][] = [header];
  for (const p of report.company_profiles || []) {
    for (const f of p.technology_findings || []) {
      rows.push([
        p.company,
        f.technology || '',
        f.stance || '',
        f.confidence ?? '',
        f.summary || '',
        (f.specific_products || []).join(' · '),
        (f.recent_developments || []).join(' · '),
        (f.partnerships || []).join(' · '),
        f.investment_signal || '',
        (f.source_urls || []).join(' | '),
      ]);
    }
  }
  return rows;
}

function companyAnalysisInvestmentRows(
  report: CompanyAnalysisReport,
): (string | number)[][] {
  const header: (string | number)[] = [
    'Company',
    'Event type',
    'Amount (USD)',
    'Amount (text)',
    'Date',
    'Description',
    'Source URL',
  ];
  const rows: (string | number)[][] = [header];
  for (const e of report.investment_signals || []) {
    rows.push([
      e.company,
      e.event_type,
      e.amount_usd ?? '',
      e.amount_text || '',
      e.date || '',
      e.description || '',
      e.source_url || '',
    ]);
  }
  return rows;
}

function companyAnalysisMatrixRows(
  report: CompanyAnalysisReport,
): (string | number)[][] {
  const technologies = report.technologies_analyzed || [];
  const header: (string | number)[] = ['Company', ...technologies];
  const rows: (string | number)[][] = [header];
  for (const p of report.company_profiles || []) {
    const byTech: Record<string, string> = {};
    for (const f of p.technology_findings || []) {
      const conf =
        typeof f.confidence === 'number'
          ? `${Math.round(f.confidence * 100)}%`
          : '';
      byTech[f.technology] =
        [f.stance, conf].filter(Boolean).join(' · ') || '—';
    }
    rows.push([
      p.company,
      ...technologies.map((t) => byTech[t] || '—'),
    ]);
  }
  return rows;
}

/** CSV: per-finding rows. */
export function downloadCompanyAnalysisCsv(
  report: CompanyAnalysisReport,
  filename?: string,
): void {
  const csv = toCsv(companyAnalysisFindingsRows(report));
  triggerDownload(
    new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }),
    filename || 'company_analysis_findings.csv',
  );
}

/** XLS: Findings, Comparative Matrix, Investment Signals. */
export function downloadCompanyAnalysisXls(
  report: CompanyAnalysisReport,
  filename?: string,
): void {
  const html = buildXlsHtml([
    { name: 'Findings', rows: companyAnalysisFindingsRows(report) },
    { name: 'Matrix', rows: companyAnalysisMatrixRows(report) },
    { name: 'Investment', rows: companyAnalysisInvestmentRows(report) },
  ]);
  triggerDownload(
    new Blob(['\uFEFF' + html], {
      type: 'application/vnd.ms-excel;charset=utf-8',
    }),
    filename || 'company_analysis.xls',
  );
}
