/**
 * Markdown export for sensing reports (#23).
 *
 * Deterministic renderer that mirrors the on-screen structure so the file
 * can round-trip into a Notion page, GitHub wiki, Obsidian vault, etc.
 *
 * Usage:
 *   const md = renderKeyCompaniesMarkdown(report);
 *   downloadMarkdown(md, 'briefing.md');
 *
 * Everything here is plain CommonMark — no HTML, no Notion-specific syntax
 * — so the output is portable. Notion-specific block conversion lives in
 * `notion-export.ts`.
 */

import type {
  CompanyAnalysisReport,
  CompanyProfile,
  CompanyTechFinding,
  KeyCompaniesReport,
  KeyCompanyBriefing,
  KeyCompanyUpdate,
} from './api';

// ─────────────────────────── primitives ───────────────────────────

function escapePipes(s: string): string {
  // Needed inside GFM tables.
  return s.replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

function heading(level: number, text: string): string {
  return `${'#'.repeat(Math.min(Math.max(level, 1), 6))} ${text}`;
}

function bullet(text: string): string {
  return `- ${text}`;
}

function link(text: string, url: string): string {
  const t = (text || url || '').trim() || url;
  return `[${t}](${url})`;
}

function table(header: string[], rows: string[][]): string {
  const head = `| ${header.map(escapePipes).join(' | ')} |`;
  const sep = `| ${header.map(() => '---').join(' | ')} |`;
  const body = rows
    .map((r) => `| ${r.map(escapePipes).join(' | ')} |`)
    .join('\n');
  return [head, sep, body].filter(Boolean).join('\n');
}

function blockquote(text: string): string {
  return text
    .split('\n')
    .map((l) => `> ${l}`)
    .join('\n');
}

function section(text: string): string {
  // Strips trailing whitespace and guarantees one blank line after.
  return text.replace(/[\t ]+$/gm, '').replace(/\n+$/, '') + '\n\n';
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

/** Save a markdown string to disk. */
export function downloadMarkdown(md: string, filename: string): void {
  triggerDownload(
    new Blob([md], { type: 'text/markdown;charset=utf-8' }),
    filename,
  );
}

// ─────────────────────── Key Companies renderer ───────────────────

function renderUpdate(u: KeyCompanyUpdate, idx: number): string {
  const pills: string[] = [];
  if (u.category) pills.push(`**${u.category}**`);
  if (u.date) pills.push(u.date);
  if (u.domain) pills.push(u.domain);
  if (u.diff?.status) pills.push(`_${u.diff.status}_`);
  if (u.sentiment && u.sentiment !== 'neutral') pills.push(u.sentiment);
  const meta = pills.length ? ` _(${pills.join(' · ')})_` : '';
  const headline = u.source_url
    ? link(u.headline || u.source_url, u.source_url)
    : u.headline;
  const body = u.summary ? `\n  ${u.summary.replace(/\n+/g, '\n  ')}` : '';
  return `${idx + 1}. ${headline}${meta}${body}`;
}

function renderBriefing(b: KeyCompanyBriefing): string {
  const parts: string[] = [];
  parts.push(heading(3, b.company));

  if (b.domains_active?.length) {
    parts.push(`_Domains active:_ ${b.domains_active.join(', ')}`);
  }

  if (b.momentum && typeof b.momentum.score === 'number') {
    const band =
      b.momentum.score >= 70
        ? 'High'
        : b.momentum.score >= 40
          ? 'Moderate'
          : 'Quiet';
    parts.push(
      `_Momentum: **${Math.round(b.momentum.score)}** (${band})` +
        (b.momentum.top_drivers?.length
          ? ` · drivers: ${b.momentum.top_drivers.join(', ')}`
          : '') +
        '_',
    );
  }

  if (b.overall_summary) parts.push(b.overall_summary);

  if (b.key_themes?.length) {
    parts.push('**Key themes:** ' + b.key_themes.map((t) => `\`${t}\``).join(' '));
  }

  if (b.updates?.length) {
    parts.push(`**Updates (${b.updates.length}):**`);
    parts.push(b.updates.map((u, i) => renderUpdate(u, i)).join('\n'));
  }

  parts.push(`_Sources used: ${b.sources_used || 0}_`);
  return section(parts.join('\n\n'));
}

/** Render the full Key Companies briefing as Markdown. */
export function renderKeyCompaniesMarkdown(
  report: KeyCompaniesReport,
): string {
  const out: string[] = [];
  out.push(
    section(
      heading(1, 'Key Companies — Weekly Briefing') +
        `\n\n_${report.period_start} → ${report.period_end} · ${report.companies_analyzed.length} companies_`,
    ),
  );

  if (report.highlight_domain) {
    out.push(section(`**Highlight domain:** ${report.highlight_domain}`));
  }

  if (report.diff_summary) {
    const ds = report.diff_summary;
    out.push(
      section(
        heading(2, 'Changes since last briefing') +
          '\n\n' +
          `- NEW updates: **${ds.new_count}**\n- ONGOING updates: **${ds.ongoing_count}**` +
          (ds.resolved_topics?.length
            ? '\n\n**Closed topics:**\n' +
              ds.resolved_topics
                .map((r) => bullet(`${r.company} — ${r.headline}`))
                .join('\n')
            : ''),
      ),
    );
  }

  if (report.cross_company_summary) {
    out.push(
      section(
        heading(2, 'Cross-company summary') +
          '\n\n' +
          blockquote(report.cross_company_summary),
      ),
    );
  }

  if (report.domain_rollup?.length) {
    out.push(
      section(
        heading(2, 'Domain rollup') +
          '\n\n' +
          table(
            ['Domain', 'Updates', 'Companies'],
            report.domain_rollup.map((d) => [
              d.domain,
              String(d.update_count),
              String(d.company_count),
            ]),
          ),
      ),
    );
  }

  if (report.briefings?.length) {
    out.push(heading(2, 'Per-company briefings') + '\n\n');
    for (const b of report.briefings) out.push(renderBriefing(b));
  }

  return out.join('');
}

/** Download Key Companies as a .md file. */
export function downloadKeyCompaniesMarkdown(
  report: KeyCompaniesReport,
  filename?: string,
): void {
  const base =
    report.period_start && report.period_end
      ? `KeyCompanies_${report.period_start}_to_${report.period_end}.md`
      : 'KeyCompanies.md';
  downloadMarkdown(renderKeyCompaniesMarkdown(report), filename || base);
}

// ───────────────────── Company Analysis renderer ───────────────────

function renderFinding(f: CompanyTechFinding): string {
  const parts: string[] = [];
  parts.push(heading(4, f.technology));
  const confidencePct = Math.round((f.confidence || 0) * 100);
  parts.push(
    `_Confidence: **${confidencePct}%** · Stance: ${f.stance || 'n/a'}_`,
  );
  if (f.summary) parts.push(f.summary);

  if (f.specific_products?.length) {
    parts.push(
      '**Products / artifacts:**\n' +
        f.specific_products.map(bullet).join('\n'),
    );
  }

  if (f.recent_developments?.length) {
    parts.push(
      '**Recent developments:**\n' +
        f.recent_developments.map(bullet).join('\n'),
    );
  }

  if (f.partnerships?.length) {
    parts.push('**Partnerships:**\n' + f.partnerships.map(bullet).join('\n'));
  }

  if (f.investment_signal) {
    parts.push(`**Investment signal:** ${f.investment_signal}`);
  }

  if (f.source_urls?.length) {
    parts.push(
      '**Sources:**\n' +
        f.source_urls.map((u, i) => bullet(`[${i + 1}] ${link(u, u)}`)).join('\n'),
    );
  }

  return parts.join('\n\n');
}

function renderProfile(p: CompanyProfile): string {
  const parts: string[] = [];
  parts.push(heading(3, p.company));
  if (p.overall_summary) parts.push(p.overall_summary);
  if (p.strengths?.length) {
    parts.push('**Strengths:**\n' + p.strengths.map(bullet).join('\n'));
  }
  if (p.gaps?.length) {
    parts.push('**Gaps:**\n' + p.gaps.map(bullet).join('\n'));
  }
  for (const f of p.technology_findings || []) {
    parts.push(renderFinding(f));
  }
  parts.push(`_Sources used: ${p.sources_used || 0}_`);
  return section(parts.join('\n\n'));
}

/** Render the full Company Analysis report as Markdown. */
export function renderCompanyAnalysisMarkdown(
  report: CompanyAnalysisReport,
): string {
  const out: string[] = [];
  out.push(
    section(
      heading(1, 'Company Analysis') +
        `\n\n_${report.companies_analyzed.length} companies × ${report.technologies_analyzed.length} technologies_` +
        (report.domain ? ` · Domain: **${report.domain}**` : ''),
    ),
  );

  if (report.executive_summary) {
    out.push(
      section(
        heading(2, 'Executive summary') +
          '\n\n' +
          blockquote(report.executive_summary),
      ),
    );
  }

  if (report.opportunity_threat) {
    const ot = report.opportunity_threat;
    const parts: string[] = [heading(2, 'Opportunity / threat')];
    if (ot.org_context_used) {
      parts.push(`_Context: ${ot.org_context_used}_`);
    }
    if (ot.opportunities?.length) {
      parts.push(
        '**Opportunities**\n' + ot.opportunities.map(bullet).join('\n'),
      );
    }
    if (ot.threats?.length) {
      parts.push('**Threats**\n' + ot.threats.map(bullet).join('\n'));
    }
    if (ot.recommended_actions?.length) {
      parts.push(
        '**Recommended actions**\n' +
          ot.recommended_actions.map(bullet).join('\n'),
      );
    }
    out.push(section(parts.join('\n\n')));
  }

  if (report.strategic_themes?.length) {
    out.push(
      section(
        heading(2, 'Strategic themes') +
          '\n\n' +
          report.strategic_themes
            .map(
              (t) =>
                `- **${t.theme}** — ${t.rationale || ''}` +
                (t.companies?.length
                  ? `\n  - Companies: ${t.companies.join(', ')}`
                  : '') +
                (t.technologies?.length
                  ? `\n  - Technologies: ${t.technologies.join(', ')}`
                  : ''),
            )
            .join('\n'),
      ),
    );
  }

  if (report.comparative_matrix?.length) {
    out.push(
      section(
        heading(2, 'Comparative matrix') +
          '\n\n' +
          table(
            ['Technology', 'Leader', 'Rationale'],
            report.comparative_matrix.map((r) => [
              r.technology,
              r.leader,
              r.rationale,
            ]),
          ),
      ),
    );
  }

  if (report.investment_signals?.length) {
    out.push(
      section(
        heading(2, 'Investment signals') +
          '\n\n' +
          table(
            ['Company', 'Event', 'Amount (USD)', 'Date', 'Description'],
            report.investment_signals.map((e) => [
              e.company,
              e.event_type,
              e.amount_usd ? String(e.amount_usd) : '',
              e.date || '',
              e.description || '',
            ]),
          ),
      ),
    );
  }

  if (report.company_profiles?.length) {
    out.push(heading(2, 'Company profiles') + '\n\n');
    for (const p of report.company_profiles) out.push(renderProfile(p));
  }

  return out.join('');
}

/** Download Company Analysis as a .md file. */
export function downloadCompanyAnalysisMarkdown(
  report: CompanyAnalysisReport,
  filename?: string,
): void {
  const base = `CompanyAnalysis_${report.companies_analyzed.length}co_${report.technologies_analyzed.length}tech.md`;
  downloadMarkdown(renderCompanyAnalysisMarkdown(report), filename || base);
}
