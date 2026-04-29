/* eslint-disable @typescript-eslint/no-explicit-any */
type TDocumentDefinitions = any;
type Content = any;

import pdfMake from 'pdfmake/build/pdfmake';
import 'pdfmake/build/vfs_fonts';
import type { KeyCompaniesReport, KeyCompanyBriefing } from './api';

const g: any = (typeof window !== 'undefined' ? window : globalThis) as any;
if (g?.pdfMake?.vfs) {
  (pdfMake as any).vfs = g.pdfMake.vfs;
}

const colors = {
  bannerBg: '#1e3a5f',
  primary: '#1e3a5f',
  accent: '#f59e0b',
  header: { bg: '#EEF2FF', text: '#3730A3' },
  summary: { bg: '#EFF6FF', text: '#1E40AF' },
  company: { bg: '#F5F3FF', text: '#6D28D9' },
  rollup: { bg: '#ECFDF5', text: '#047857' },
  meta: { bg: '#F1F5F9', text: '#475569' },
  slate600: '#475569',
  slate800: '#1F2937',
  slate500: '#64748B',
  border: '#E2E8F0',
  // Category tones
  productLaunch: { bg: '#D1FAE5', text: '#065F46' },
  funding: { bg: '#FEF3C7', text: '#92400E' },
  acquisition: { bg: '#FED7AA', text: '#9A3412' },
  partnership: { bg: '#DBEAFE', text: '#1E40AF' },
  research: { bg: '#EDE9FE', text: '#6D28D9' },
  technical: { bg: '#E0F2FE', text: '#075985' },
  regulatory: { bg: '#FFE4E6', text: '#9F1239' },
  people: { bg: '#E0E7FF', text: '#3730A3' },
  other: { bg: '#F1F5F9', text: '#475569' },
};

function sanitize(s: string | undefined | null): string {
  if (!s) return '';
  return String(s)
    .replace(/≥/g, '>=')
    .replace(/≤/g, '<=')
    .replace(/×/g, 'x')
    .replace(/±/g, '+/-')
    .replace(/[–—]/g, '-')
    .replace(/[""]/g, '"')
    .replace(/\u202F/g, ' ')
    .replace(/'/g, "'")
    .replace(/‑/g, '-');
}

function categoryTone(cat: string) {
  switch ((cat || '').toLowerCase()) {
    case 'product launch':
      return colors.productLaunch;
    case 'funding':
      return colors.funding;
    case 'acquisition':
      return colors.acquisition;
    case 'partnership':
      return colors.partnership;
    case 'research':
      return colors.research;
    case 'technical':
      return colors.technical;
    case 'regulatory':
      return colors.regulatory;
    case 'people':
      return colors.people;
    default:
      return colors.other;
  }
}

function banner(title: string, subtitle: string): Content {
  return {
    table: {
      widths: ['*'],
      body: [
        [
          {
            stack: [
              {
                text: sanitize(title),
                fontSize: 20,
                bold: true,
                color: '#FFFFFF',
                alignment: 'center',
                margin: [0, 0, 0, 4],
              },
              ...(subtitle
                ? [
                    {
                      text: sanitize(subtitle),
                      fontSize: 10,
                      color: '#E0E7FF',
                      alignment: 'center',
                    },
                  ]
                : []),
            ],
            fillColor: colors.bannerBg,
            margin: [12, 16, 12, 16],
          },
        ],
      ],
    },
    layout: {
      hLineWidth: () => 0,
      vLineWidth: () => 0,
      paddingLeft: () => 0,
      paddingRight: () => 0,
      paddingTop: () => 0,
      paddingBottom: () => 0,
    },
    margin: [0, 0, 0, 12],
  };
}

function sectionHeader(
  title: string,
  tone: { bg: string; text: string },
): Content {
  return {
    table: {
      widths: ['*'],
      body: [
        [
          {
            text: sanitize(title),
            fontSize: 13,
            bold: true,
            color: tone.text,
            fillColor: tone.bg,
            margin: [10, 6, 10, 6],
          },
        ],
      ],
    },
    layout: {
      hLineWidth: () => 0,
      vLineWidth: () => 0,
      paddingLeft: () => 0,
      paddingRight: () => 0,
      paddingTop: () => 0,
      paddingBottom: () => 0,
    },
    margin: [0, 14, 0, 8],
  };
}

function pill(
  text: string,
  tone: { bg: string; text: string },
): Content {
  return {
    table: {
      widths: ['auto'],
      body: [
        [
          {
            text: sanitize(text),
            fontSize: 9,
            color: tone.text,
            fillColor: tone.bg,
            margin: [6, 3, 6, 3],
          },
        ],
      ],
    },
    layout: {
      hLineWidth: () => 0,
      vLineWidth: () => 0,
      paddingLeft: () => 0,
      paddingRight: () => 0,
      paddingTop: () => 0,
      paddingBottom: () => 0,
    },
  };
}

function card(content: Content[]): Content {
  return {
    table: {
      widths: ['*'],
      body: [[{ stack: content, margin: [8, 8, 8, 8] }]],
    },
    layout: {
      hLineWidth: () => 0.75,
      vLineWidth: () => 0.75,
      hLineColor: () => colors.border,
      vLineColor: () => colors.border,
    },
    margin: [0, 0, 0, 8],
  };
}

function briefingBlock(b: KeyCompanyBriefing): Content {
  const stack: Content[] = [
    {
      text: sanitize(b.company),
      fontSize: 14,
      bold: true,
      color: colors.company.text,
      margin: [0, 0, 0, 4],
    },
  ];

  if (b.domains_active?.length) {
    stack.push({
      columns: b.domains_active
        .slice(0, 6)
        .map((d) => pill(d, colors.meta)),
      columnGap: 4,
      margin: [0, 0, 0, 6],
    });
  }

  if (b.overall_summary) {
    stack.push({
      text: sanitize(b.overall_summary),
      fontSize: 10,
      color: colors.slate800,
      lineHeight: 1.3,
      margin: [0, 0, 0, 6],
    });
  }

  if (b.momentum?.score !== undefined) {
    const score = Math.round(b.momentum.score || 0);
    const band = score >= 70 ? 'High' : score >= 40 ? 'Moderate' : 'Quiet';
    stack.push({
      columns: [pill(`Momentum: ${score} (${band})`, colors.summary)],
      margin: [0, 0, 0, 6],
    });
  }

  const updates = (b.updates || []).slice(0, 10);
  if (updates.length > 0) {
    stack.push({
      text: `Recent updates (${b.updates.length} total)`,
      fontSize: 10,
      bold: true,
      color: colors.slate600,
      margin: [0, 4, 0, 4],
    });

    updates.forEach((u, idx) => {
      stack.push({
        columns: [
          pill(u.category || 'Other', categoryTone(u.category)),
          ...(u.date
            ? [pill(u.date, colors.meta)]
            : []),
          ...(u.diff?.status
            ? [
                pill(u.diff.status, {
                  bg:
                    u.diff.status === 'NEW'
                      ? '#D1FAE5'
                      : u.diff.status === 'ONGOING'
                        ? '#FEF3C7'
                        : '#F1F5F9',
                  text:
                    u.diff.status === 'NEW'
                      ? '#065F46'
                      : u.diff.status === 'ONGOING'
                        ? '#92400E'
                        : '#475569',
                }),
              ]
            : []),
        ],
        columnGap: 4,
        margin: [0, 2, 0, 2],
      });
      stack.push({
        text: `${idx + 1}. ${sanitize(u.headline)}`,
        fontSize: 10,
        bold: true,
        color: colors.slate800,
        margin: [0, 0, 0, 2],
      });
      if (u.summary) {
        stack.push({
          text: sanitize(u.summary),
          fontSize: 9,
          color: colors.slate600,
          margin: [0, 0, 0, (u as any).quantitative_highlights?.length > 0 ? 2 : 4],
        });
      }
      if ((u as any).quantitative_highlights?.length > 0) {
        stack.push({
          ul: (u as any).quantitative_highlights.map((q: string) => ({
            text: sanitize(q),
            fontSize: 8,
            color: '#92400E',
          })),
          margin: [6, 0, 0, 4],
        });
      }
    });
  }

  return card(stack);
}

function buildKeyCompaniesPdf(
  report: KeyCompaniesReport,
): TDocumentDefinitions {
  const content: Content[] = [];

  content.push(
    banner(
      'Key Companies — Weekly Briefing',
      `${report.period_start} → ${report.period_end} · ${report.companies_analyzed.length} companies`,
    ),
  );

  const metaPills: Content[] = [
    pill(`Period: ${report.period_days}d`, colors.header),
    pill(`Companies: ${report.companies_analyzed.length}`, colors.header),
  ];
  if (report.highlight_domain) {
    metaPills.push(
      pill(`Highlight: ${report.highlight_domain}`, colors.header),
    );
  }
  if (report.diff_summary) {
    metaPills.push(
      pill(`NEW: ${report.diff_summary.new_count}`, colors.productLaunch),
    );
    metaPills.push(
      pill(
        `ONGOING: ${report.diff_summary.ongoing_count}`,
        colors.funding,
      ),
    );
  }
  content.push({
    columns: metaPills,
    columnGap: 4,
    margin: [0, 0, 0, 10],
  });

  if (report.cross_company_summary) {
    content.push(sectionHeader('Cross-company summary', colors.summary));
    content.push({
      text: sanitize(report.cross_company_summary),
      fontSize: 10,
      color: colors.slate800,
      lineHeight: 1.4,
      margin: [0, 0, 0, 8],
    });
  }

  if (report.domain_rollup && report.domain_rollup.length > 0) {
    content.push(sectionHeader('Domain rollup', colors.rollup));
    const total =
      report.domain_rollup.reduce(
        (sum, d) => sum + (d.update_count || 0),
        0,
      ) || 1;
    content.push({
      table: {
        widths: ['*', 80, 80, 80],
        body: [
          [
            {
              text: 'Domain',
              bold: true,
              fontSize: 10,
              color: colors.slate600,
            },
            {
              text: 'Updates',
              bold: true,
              fontSize: 10,
              color: colors.slate600,
            },
            {
              text: 'Companies',
              bold: true,
              fontSize: 10,
              color: colors.slate600,
            },
            {
              text: '%',
              bold: true,
              fontSize: 10,
              color: colors.slate600,
            },
          ],
          ...report.domain_rollup.map((d) => [
            { text: sanitize(d.domain), fontSize: 9 },
            {
              text: String(d.update_count),
              fontSize: 9,
              alignment: 'center',
            },
            {
              text: String(d.company_count),
              fontSize: 9,
              alignment: 'center',
            },
            {
              text: `${Math.round((d.update_count / total) * 100)}%`,
              fontSize: 9,
              alignment: 'center',
            },
          ]),
        ],
      },
      layout: 'lightHorizontalLines',
      margin: [0, 0, 0, 10],
    });
  }

  content.push(sectionHeader('Per-company briefings', colors.company));
  (report.briefings || []).forEach((b) => content.push(briefingBlock(b)));

  if (report.diff_summary?.resolved_topics?.length) {
    content.push(sectionHeader('Closed topics', colors.meta));
    content.push({
      ul: report.diff_summary.resolved_topics.map(
        (r: { company: string; headline: string }) => ({
          text: `${r.company} — ${sanitize(r.headline)}`,
          fontSize: 9,
          color: colors.slate600,
        }),
      ),
      margin: [0, 0, 0, 10],
    });
  }

  return {
    content,
    pageSize: 'A4',
    pageMargins: [40, 40, 40, 40],
    defaultStyle: {
      font: 'Roboto',
      fontSize: 10,
      color: colors.slate800,
    },
    footer: (currentPage: number, pageCount: number) => ({
      text: `${currentPage} / ${pageCount}`,
      alignment: 'center',
      fontSize: 8,
      color: colors.slate500,
      margin: [0, 10, 0, 0],
    }),
  };
}

/** Download a PDF for a Key Companies briefing (#21). */
export async function downloadKeyCompaniesPdf(
  report: KeyCompaniesReport,
  filename?: string,
) {
  const doc = buildKeyCompaniesPdf(report);
  const base =
    (report.period_start && report.period_end
      ? `KeyCompanies_${report.period_start}_to_${report.period_end}`
      : 'KeyCompanies') + '.pdf';
  pdfMake.createPdf(doc).download(filename || base);
}
