/* eslint-disable @typescript-eslint/no-explicit-any */
type TDocumentDefinitions = any;
type Content = any;

import pdfMake from 'pdfmake/build/pdfmake';
import 'pdfmake/build/vfs_fonts';
import type {
    SensingReportData, SensingRadarItem, SensingHeadlineMove,
    SensingTopEvent, SensingBlindSpot,
    CompanyAnalysisReport,
} from './api';

const g: any = (typeof window !== 'undefined' ? window : globalThis) as any;
if (g?.pdfMake?.vfs) {
    (pdfMake as any).vfs = g.pdfMake.vfs;
}

// ── Color palette ──────────────────────────────────────────────────────────
const colors = {
    bannerBg: '#1e3a5f',
    primary: '#1e3a5f',
    accent: '#f59e0b',
    // Section tones
    executive: { bg: '#EFF6FF', text: '#1E40AF' },
    headline: { bg: '#FFF7ED', text: '#9A3412' },
    trends: { bg: '#FEF3C7', text: '#B45309' },
    radar: { bg: '#ECFDF5', text: '#047857' },
    market: { bg: '#EDE9FE', text: '#6D28D9' },
    sections: { bg: '#F0F9FF', text: '#0369A1' },
    recommendations: { bg: '#FFF7ED', text: '#C2410C' },
    articles: { bg: '#F1F5F9', text: '#475569' },
    bottomLine: { bg: '#FFF1F2', text: '#9F1239' },
    blindSpots: { bg: '#FEFCE8', text: '#A16207' },
    topEvents: { bg: '#FFF7ED', text: '#9A3412' },
    // General
    slate600: '#475569',
    slate800: '#1F2937',
    slate500: '#64748B',
    border: '#E2E8F0',
    // Impact
    impactHigh: { bg: '#FEE2E2', text: '#991B1B' },
    impactMed: { bg: '#FEF3C7', text: '#92400E' },
    impactLow: { bg: '#D1FAE5', text: '#065F46' },
    // Ring
    adopt: '#059669',
    trial: '#2563EB',
    assess: '#D97706',
    hold: '#DC2626',
};

function sanitize(s: string | undefined | null): string {
    if (!s) return '';
    return String(s)
        .replace(/≥/g, '>=').replace(/≤/g, '<=').replace(/×/g, 'x')
        .replace(/±/g, '+/-').replace(/[–—]/g, '-').replace(/[""]/g, '"')
        .replace(/\u202F/g, ' ').replace(/'/g, "'").replace(/‑/g, '-');
}

// ── Helpers ────────────────────────────────────────────────────────────────

function banner(title: string, subtitle: string): Content {
    return {
        table: {
            widths: ['*'],
            body: [[{
                stack: [
                    { text: sanitize(title), fontSize: 20, bold: true, color: '#FFFFFF', alignment: 'center', margin: [0, 0, 0, 4] },
                    ...(subtitle ? [{ text: sanitize(subtitle), fontSize: 10, color: '#E0E7FF', alignment: 'center' }] : []),
                ],
                fillColor: colors.bannerBg,
                margin: [12, 16, 12, 16],
            }]],
        },
        layout: { hLineWidth: () => 0, vLineWidth: () => 0, paddingLeft: () => 0, paddingRight: () => 0, paddingTop: () => 0, paddingBottom: () => 0 },
        margin: [0, 0, 0, 12],
    };
}

function sectionHeader(title: string, tone: { bg: string; text: string }): Content {
    return {
        table: {
            widths: ['*'],
            body: [[{
                text: sanitize(title),
                fontSize: 13, bold: true, color: tone.text,
                fillColor: tone.bg,
                margin: [10, 6, 10, 6],
            }]],
        },
        layout: { hLineWidth: () => 0, vLineWidth: () => 0, paddingLeft: () => 0, paddingRight: () => 0, paddingTop: () => 0, paddingBottom: () => 0 },
        margin: [0, 14, 0, 8],
    };
}

function card(content: Content[], borderColor: string = colors.border): Content {
    return {
        table: {
            widths: ['*'],
            body: [[{ stack: content, margin: [8, 8, 8, 8] }]],
        },
        layout: {
            hLineWidth: () => 0.75, vLineWidth: () => 0.75,
            hLineColor: () => borderColor, vLineColor: () => borderColor,
        },
        margin: [0, 3, 0, 3],
    };
}

function pill(text: string, tone: { bg: string; text: string }): Content {
    return { text: sanitize(text), fontSize: 8, bold: true, color: tone.text, background: tone.bg, margin: [4, 2, 4, 2] };
}

function impactTone(level: string) {
    if (level === 'High') return colors.impactHigh;
    if (level === 'Medium') return colors.impactMed;
    return colors.impactLow;
}

function ringColor(ring: string): string {
    if (ring === 'Adopt') return colors.adopt;
    if (ring === 'Trial') return colors.trial;
    if (ring === 'Assess') return colors.assess;
    return colors.hold;
}

/** Convert inline markdown (**bold**) to pdfmake text array. */
function parseInlineMd(text: string, baseStyle: Record<string, any> = {}): Content {
    const parts: Content[] = [];
    const regex = /\*\*(.+?)\*\*/g;
    let last = 0;
    let m;
    while ((m = regex.exec(text)) !== null) {
        if (m.index > last) {
            parts.push({ text: sanitize(text.slice(last, m.index)), ...baseStyle });
        }
        parts.push({ text: sanitize(m[1]), ...baseStyle, bold: true });
        last = m.index + m[0].length;
    }
    if (last < text.length) {
        parts.push({ text: sanitize(text.slice(last)), ...baseStyle });
    }
    return parts.length === 1 ? parts[0] : { text: parts };
}

/**
 * Convert a block of markdown text to an array of pdfmake content nodes.
 * Supports: ## headings, **bold** inline, - bullet lists, paragraphs.
 */
function markdownToContent(
    md: string,
    baseFontSize = 9,
    baseColor = colors.slate600,
): Content[] {
    if (!md) return [];
    const lines = md.split('\n');
    const result: Content[] = [];
    const baseStyle = { fontSize: baseFontSize, color: baseColor, lineHeight: 1.35 };

    let bulletBuffer: Content[] = [];

    const flushBullets = () => {
        if (bulletBuffer.length > 0) {
            result.push({
                ul: bulletBuffer,
                margin: [0, 2, 0, 4] as any,
            });
            bulletBuffer = [];
        }
    };

    for (const raw of lines) {
        const line = raw.trimEnd();

        // Blank line → flush
        if (!line.trim()) {
            flushBullets();
            continue;
        }

        // ## Heading
        const headingMatch = line.match(/^(#{1,3})\s+(.+)/);
        if (headingMatch) {
            flushBullets();
            const level = headingMatch[1].length; // 1, 2, or 3
            const headingSize = level === 1 ? 13 : level === 2 ? 11 : 10;
            result.push({
                ...parseInlineMd(headingMatch[2], { fontSize: headingSize, color: colors.slate800 }),
                bold: true,
                margin: [0, 6, 0, 3] as any,
            });
            continue;
        }

        // - Bullet item
        const bulletMatch = line.match(/^\s*[-*]\s+(.+)/);
        if (bulletMatch) {
            bulletBuffer.push(parseInlineMd(bulletMatch[1], baseStyle));
            continue;
        }

        // Regular paragraph line
        flushBullets();
        result.push({
            ...parseInlineMd(line, baseStyle),
            margin: [0, 0, 0, 4] as any,
        });
    }

    flushBullets();
    return result;
}

function sourceUrlsBlock(urls?: string[]): Content[] {
    if (!urls?.length) return [];
    const items = urls.map((url, i) => `[${i + 1}] ${sanitize(url)}`).join('  ');
    return [{
        text: `Sources: ${items}`,
        fontSize: 7, color: colors.slate500, italics: true,
        margin: [0, 4, 0, 0] as any,
    }];
}

// ── Radar Canvas Renderer ─────────────────────────────────────────────────

const QUADRANT_DEFS: Record<string, { start: number; end: number; color: string; label: string }> = {
    'Techniques': { start: 90, end: 180, color: '#1ebccd', label: 'Techniques' },
    'Platforms': { start: 0, end: 90, color: '#f38a3e', label: 'Platforms' },
    'Tools': { start: 270, end: 360, color: '#86b82a', label: 'Tools' },
    'Languages & Frameworks': { start: 180, end: 270, color: '#b32059', label: 'Languages & Frameworks' },
};

const RING_DEFS: Record<string, { inner: number; outer: number }> = {
    'Adopt': { inner: 0, outer: 0.25 },
    'Trial': { inner: 0.25, outer: 0.50 },
    'Assess': { inner: 0.50, outer: 0.75 },
    'Hold': { inner: 0.75, outer: 1.0 },
};

const RING_ORDER_PDF = ['Adopt', 'Trial', 'Assess', 'Hold'];

function seededRandom(seed: number): number {
    const x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
}

function hashString(s: string): number {
    let hash = 0;
    for (let i = 0; i < s.length; i++) {
        hash = ((hash << 5) - hash) + s.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash);
}

export function renderRadarToCanvas(items: SensingRadarItem[]): string {
    const size = 600;
    const legendHeight = 80;
    const totalHeight = size + legendHeight;
    const center = size / 2;
    const maxRadius = size / 2 - 40;

    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = totalHeight;
    const ctx = canvas.getContext('2d')!;

    // White background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, size, totalHeight);

    // Ring circles
    for (const ring of RING_ORDER_PDF) {
        const r = RING_DEFS[ring];
        ctx.beginPath();
        ctx.arc(center, center, r.outer * maxRadius, 0, 2 * Math.PI);
        ctx.strokeStyle = '#d1d5db';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    // Ring labels
    ctx.font = '9px sans-serif';
    ctx.fillStyle = '#9ca3af';
    ctx.textAlign = 'center';
    for (const ring of RING_ORDER_PDF) {
        const r = RING_DEFS[ring];
        const labelR = ((r.inner + r.outer) / 2) * maxRadius;
        ctx.fillText(ring, center + labelR, center - 4);
    }

    // Quadrant dividing lines
    ctx.strokeStyle = '#d1d5db';
    ctx.lineWidth = 1;
    for (const deg of [0, 90, 180, 270]) {
        const rad = deg * (Math.PI / 180);
        ctx.beginPath();
        ctx.moveTo(center, center);
        ctx.lineTo(center + maxRadius * Math.cos(rad), center - maxRadius * Math.sin(rad));
        ctx.stroke();
    }

    // Quadrant labels
    ctx.font = 'bold 10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const [key, q] of Object.entries(QUADRANT_DEFS)) {
        const midAngle = ((q.start + q.end) / 2) * (Math.PI / 180);
        const labelR = maxRadius + 22;
        const lx = center + labelR * Math.cos(midAngle);
        const ly = center - labelR * Math.sin(midAngle);
        ctx.fillStyle = q.color;
        ctx.fillText(key, lx, ly);
    }

    // Blips
    for (let idx = 0; idx < items.length; idx++) {
        const item = items[idx];
        const q = QUADRANT_DEFS[item.quadrant];
        const r = RING_DEFS[item.ring];
        if (!q || !r) continue;

        const seed = hashString(item.name + idx);
        const anglePad = 8;
        const angleRange = (q.end - q.start) - 2 * anglePad;
        const angle = (q.start + anglePad + seededRandom(seed) * angleRange) * (Math.PI / 180);

        const radiusPad = 0.03;
        const rMin = (r.inner + radiusPad) * maxRadius;
        const rMax = (r.outer - radiusPad) * maxRadius;
        const radius = rMin + seededRandom(seed + 1) * (rMax - rMin);

        const x = center + radius * Math.cos(angle);
        const y = center - radius * Math.sin(angle);

        // Movement indicator
        if (item.moved_in) {
            ctx.beginPath();
            ctx.arc(x, y, 9, 0, 2 * Math.PI);
            ctx.strokeStyle = '#f59e0b';
            ctx.lineWidth = 2;
            ctx.setLineDash([3, 2]);
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // Blip
        ctx.beginPath();
        if (item.is_new) {
            ctx.moveTo(x, y - 6);
            ctx.lineTo(x + 5.2, y + 3);
            ctx.lineTo(x - 5.2, y + 3);
            ctx.closePath();
        } else {
            ctx.arc(x, y, 5, 0, 2 * Math.PI);
        }
        ctx.fillStyle = q.color;
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    // ── Legend ──────────────────────────────────────────────────────────
    const legendY = size + 8;

    // Separator line
    ctx.strokeStyle = '#e5e7eb';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(40, legendY);
    ctx.lineTo(size - 40, legendY);
    ctx.stroke();

    const ly = legendY + 20;

    // Shape legend — new (triangle) vs existing (circle)
    ctx.fillStyle = '#6b7280';
    ctx.font = 'bold 10px sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';

    // Triangle = New
    let lx = 50;
    ctx.beginPath();
    ctx.moveTo(lx, ly - 5);
    ctx.lineTo(lx + 5, ly + 3);
    ctx.lineTo(lx - 5, ly + 3);
    ctx.closePath();
    ctx.fillStyle = '#6b7280';
    ctx.fill();
    ctx.font = '10px sans-serif';
    ctx.fillStyle = '#374151';
    ctx.fillText('New entry', lx + 10, ly);

    // Circle = Existing
    lx = 140;
    ctx.beginPath();
    ctx.arc(lx, ly, 4, 0, 2 * Math.PI);
    ctx.fillStyle = '#6b7280';
    ctx.fill();
    ctx.font = '10px sans-serif';
    ctx.fillStyle = '#374151';
    ctx.fillText('Existing', lx + 10, ly);

    // Dashed ring = Moved
    lx = 220;
    ctx.beginPath();
    ctx.arc(lx, ly, 6, 0, 2 * Math.PI);
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 2;
    ctx.setLineDash([3, 2]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = '10px sans-serif';
    ctx.fillStyle = '#374151';
    ctx.fillText('Moved', lx + 12, ly);

    // Quadrant color legend
    const qLy = ly + 24;
    let qLx = 50;
    for (const [key, q] of Object.entries(QUADRANT_DEFS)) {
        ctx.beginPath();
        ctx.arc(qLx, qLy, 5, 0, 2 * Math.PI);
        ctx.fillStyle = q.color;
        ctx.fill();
        ctx.font = '10px sans-serif';
        ctx.fillStyle = '#374151';
        ctx.textAlign = 'left';
        ctx.fillText(key, qLx + 10, qLy);
        qLx += ctx.measureText(key).width + 30;
    }

    return canvas.toDataURL('image/png');
}

// ── Build Document ─────────────────────────────────────────────────────────

function buildSensingPdf(data: SensingReportData): TDocumentDefinitions {
    const { report, meta } = data;
    const today = new Date().toLocaleDateString();
    const content: Content[] = [];

    // Title banner
    content.push(banner(
        report.report_title || 'Tech Sensing Report',
        `${report.domain} | ${report.date_range} | ${report.total_articles_analyzed} articles analyzed`,
    ));

    // Meta pills
    content.push({
        columns: [
            pill(`Domain: ${report.domain}`, colors.executive),
            pill(`Period: ${report.date_range}`, colors.executive),
            pill(`Articles: ${report.total_articles_analyzed}`, colors.executive),
            pill(`Generated in ${meta.execution_time_seconds}s`, colors.executive),
        ],
        columnGap: 6,
        margin: [0, 0, 0, 10],
    });

    // Confidence Note
    if (report.confidence_note) {
        content.push({
            text: sanitize(report.confidence_note),
            fontSize: 8, italics: true, color: colors.slate500,
            margin: [0, 0, 0, 8],
        });
    }

    // Bottom Line
    if (report.bottom_line) {
        content.push(card([
            { text: 'BOTTOM LINE', fontSize: 9, bold: true, color: colors.bottomLine.text, margin: [0, 0, 0, 3] },
            { text: sanitize(report.bottom_line), fontSize: 10, color: colors.slate800, lineHeight: 1.4 },
        ], '#FDA4AF'));
    }

    // Executive Summary — parse markdown for bold, headings, bullets
    content.push(sectionHeader('Executive Summary', colors.executive));
    content.push(card(
        markdownToContent(report.executive_summary || '', 10, colors.slate800),
        '#BFDBFE',
    ));

    // Top Events (v2) or Headline Moves (legacy)
    if (report.top_events && report.top_events.length > 0) {
        content.push(sectionHeader(`Top Events (${report.top_events.length})`, colors.topEvents));
        for (let idx = 0; idx < report.top_events.length; idx++) {
            const event = report.top_events[idx] as SensingTopEvent;
            const eventLabel = (event.event_type || '').replace('_', ' ');
            content.push(card([
                {
                    columns: [
                        { text: `${idx + 1}.`, fontSize: 11, bold: true, color: colors.accent, width: 18 },
                        { text: sanitize(event.headline), fontSize: 10, color: colors.slate800, width: '*' },
                    ],
                    columnGap: 4,
                    margin: [0, 0, 0, 3],
                },
                {
                    columns: [
                        pill(event.actor, { bg: '#DBEAFE', text: '#1E40AF' }),
                        pill(eventLabel, colors.topEvents),
                        ...(event.segment ? [pill(event.segment, colors.headline)] : []),
                    ],
                    columnGap: 4,
                    margin: [18, 0, 0, 0],
                },
                ...(event.impact_summary ? [
                    { text: 'Impact:', fontSize: 8, bold: true, color: colors.slate600, margin: [18, 4, 0, 1] as any },
                    { text: sanitize(event.impact_summary), fontSize: 8, color: colors.slate600, margin: [18, 0, 0, 0] as any },
                ] : []),
                ...(event.strategic_intent ? [
                    { text: 'Strategic Intent:', fontSize: 8, bold: true, color: colors.slate600, margin: [18, 3, 0, 1] as any },
                    { text: sanitize(event.strategic_intent), fontSize: 8, color: colors.slate600, margin: [18, 0, 0, 0] as any },
                ] : []),
                ...sourceUrlsBlock(event.source_urls),
            ]));
        }
    } else if (report.headline_moves?.length > 0) {
        content.push(sectionHeader(`Headline Moves (${report.headline_moves.length})`, colors.headline));
        for (let idx = 0; idx < report.headline_moves.length; idx++) {
            const move = report.headline_moves[idx];
            content.push(card([
                {
                    columns: [
                        { text: `${idx + 1}.`, fontSize: 11, bold: true, color: colors.accent, width: 18 },
                        { text: sanitize(move.headline), fontSize: 10, color: colors.slate800, width: '*' },
                    ],
                    columnGap: 4,
                    margin: [0, 0, 0, 3],
                },
                {
                    columns: [
                        pill(move.actor, { bg: '#DBEAFE', text: '#1E40AF' }),
                        pill(move.segment, colors.headline),
                    ],
                    columnGap: 4,
                    margin: [18, 0, 0, 0],
                },
                ...sourceUrlsBlock(move.source_urls),
            ]));
        }
    }

    // Key Trends
    if (report.key_trends?.length > 0) {
        content.push(sectionHeader(`Key Trends (${report.key_trends.length})`, colors.trends));
        for (const trend of report.key_trends) {
            content.push(card([
                {
                    columns: [
                        { text: sanitize(trend.trend_name), fontSize: 11, bold: true, width: '*' },
                        pill(trend.impact_level, impactTone(trend.impact_level)),
                        pill(trend.time_horizon, colors.trends),
                    ],
                    columnGap: 6,
                    margin: [0, 0, 0, 4],
                },
                { text: sanitize(trend.description), fontSize: 9, color: colors.slate600, margin: [0, 0, 0, 4] },
                ...(trend.evidence?.length > 0 ? [{
                    ul: trend.evidence.map(e => ({ text: sanitize(e), fontSize: 8, color: colors.slate500 })),
                    margin: [0, 2, 0, 0] as any,
                }] : []),
                ...sourceUrlsBlock(trend.source_urls),
            ]));
        }
    }

    // Market Signals (legacy — hidden when top_events present)
    if (!(report.top_events && report.top_events.length > 0) && report.market_signals?.length > 0) {
        content.push(sectionHeader(`Market Signals (${report.market_signals.length})`, colors.market));
        content.push({
            text: 'What prominent players are doing and where the industry is heading.',
            fontSize: 9, italics: true, color: colors.slate500, margin: [0, 0, 0, 8],
        });
        for (const signal of report.market_signals) {
            content.push(card([
                {
                    columns: [
                        { text: sanitize(signal.company_or_player), fontSize: 11, bold: true, color: colors.market.text, width: '*' },
                        ...(signal.segment ? [pill(signal.segment, colors.headline)] : []),
                    ],
                    columnGap: 6,
                    margin: [0, 0, 0, 3],
                },
                { text: sanitize(signal.signal), fontSize: 9, color: colors.slate800, margin: [0, 0, 0, 3] },
                {
                    columns: [
                        { stack: [
                            { text: 'Strategic Intent', fontSize: 8, bold: true, color: colors.slate600 },
                            { text: sanitize(signal.strategic_intent), fontSize: 8, color: colors.slate600 },
                        ], width: '*' },
                        { stack: [
                            { text: 'Industry Impact', fontSize: 8, bold: true, color: colors.slate600 },
                            { text: sanitize(signal.industry_impact), fontSize: 8, color: colors.slate600 },
                        ], width: '*' },
                    ],
                    columnGap: 10,
                    margin: [0, 2, 0, 0],
                },
                ...sourceUrlsBlock(signal.source_urls),
            ], '#DDD6FE'));
        }
    }

    // Technology Radar Details
    if (report.radar_item_details?.length > 0) {
        content.push(sectionHeader(`Technology Deep Dives (${report.radar_item_details.length})`, colors.radar));
        for (const item of report.radar_item_details) {
            // Find matching radar item for ring/quadrant
            const radarItem = report.radar_items?.find(r => r.name === item.technology_name);
            content.push(card([
                {
                    columns: [
                        { text: sanitize(item.technology_name), fontSize: 11, bold: true, width: '*' },
                        ...(radarItem ? [
                            pill(radarItem.ring, { bg: '#F0FDF4', text: ringColor(radarItem.ring) }),
                            ...(radarItem.momentum ? [pill(
                                radarItem.momentum === 'rising' ? '\u2191 Rising' : radarItem.momentum === 'declining' ? '\u2193 Declining' : '- Stable',
                                radarItem.momentum === 'rising' ? { bg: '#D1FAE5', text: '#065F46' } : radarItem.momentum === 'declining' ? { bg: '#FEE2E2', text: '#991B1B' } : { bg: '#F1F5F9', text: '#64748B' },
                            )] : []),
                            pill(radarItem.quadrant, colors.radar),
                        ] : []),
                    ],
                    columnGap: 6,
                    margin: [0, 0, 0, 4],
                },
                { text: 'What It Is', fontSize: 9, bold: true, color: colors.slate800, margin: [0, 2, 0, 1] },
                { text: sanitize(item.what_it_is), fontSize: 9, color: colors.slate600, margin: [0, 0, 0, 4] },
                { text: 'Why It Matters', fontSize: 9, bold: true, color: colors.slate800, margin: [0, 2, 0, 1] },
                { text: sanitize(item.why_it_matters), fontSize: 9, color: colors.slate600, margin: [0, 0, 0, 4] },
                { text: 'Current State', fontSize: 9, bold: true, color: colors.slate800, margin: [0, 2, 0, 1] },
                { text: sanitize(item.current_state), fontSize: 9, color: colors.slate600, margin: [0, 0, 0, 4] },
                ...(item.key_players?.length > 0 ? [
                    { text: 'Key Players', fontSize: 9, bold: true, color: colors.slate800, margin: [0, 2, 0, 1] as any },
                    { text: item.key_players.map(sanitize).join(', '), fontSize: 9, color: colors.slate600, margin: [0, 0, 0, 4] as any },
                ] : []),
                ...(item.practical_applications?.length > 0 ? [
                    { text: 'Practical Applications', fontSize: 9, bold: true, color: colors.slate800, margin: [0, 2, 0, 1] as any },
                    { ul: item.practical_applications.map((a: string) => ({ text: sanitize(a), fontSize: 8, color: colors.slate600 })), margin: [0, 0, 0, 0] as any },
                ] : []),
                ...((item as any).quantitative_highlights?.length > 0 ? [
                    { text: 'Key Numbers & Metrics', fontSize: 9, bold: true, color: '#92400E', margin: [0, 4, 0, 1] as any },
                    { ul: (item as any).quantitative_highlights.map((q: string) => ({ text: sanitize(q), fontSize: 8, color: colors.slate600 })), margin: [0, 0, 0, 0] as any },
                ] : []),
                ...sourceUrlsBlock(item.source_urls),
            ], '#A7F3D0'));
        }
    }

    // Technology Radar Overview (table by quadrant)
    if (report.radar_items?.length > 0) {
        content.push(sectionHeader(`Technology Radar (${report.radar_items.length} items)`, colors.radar));

        const quadrants = ['Techniques', 'Platforms', 'Tools', 'Languages & Frameworks'];
        const quadrantColors: Record<string, string> = {
            'Techniques': '#1ebccd',
            'Platforms': '#f38a3e',
            'Tools': '#86b82a',
            'Languages & Frameworks': '#b32059',
        };

        for (const quadrant of quadrants) {
            const items = report.radar_items.filter(r => r.quadrant === quadrant);
            if (items.length === 0) continue;

            // Quadrant sub-header
            content.push({
                text: sanitize(quadrant),
                fontSize: 11, bold: true,
                color: quadrantColors[quadrant] || colors.slate800,
                margin: [0, 8, 0, 4],
            });

            // Table of items in this quadrant
            const ringOrder = ['Adopt', 'Trial', 'Assess', 'Hold'];
            const sorted = [...items].sort((a, b) =>
                ringOrder.indexOf(a.ring) - ringOrder.indexOf(b.ring)
            );

            const tableBody: any[] = [
                [
                    { text: 'Technology', bold: true, fillColor: '#F8FAFC', color: colors.slate800, margin: [4, 3, 4, 3], fontSize: 8 },
                    { text: 'Ring', bold: true, fillColor: '#F8FAFC', color: colors.slate800, margin: [4, 3, 4, 3], fontSize: 8 },
                    { text: 'Momentum', bold: true, fillColor: '#F8FAFC', color: colors.slate800, margin: [4, 3, 4, 3], fontSize: 8 },
                    { text: 'Moved', bold: true, fillColor: '#F8FAFC', color: colors.slate800, margin: [4, 3, 4, 3], fontSize: 8 },
                    { text: 'Description', bold: true, fillColor: '#F8FAFC', color: colors.slate800, margin: [4, 3, 4, 3], fontSize: 8 },
                    { text: 'New?', bold: true, fillColor: '#F8FAFC', color: colors.slate800, margin: [4, 3, 4, 3], fontSize: 8 },
                ],
            ];

            for (const item of sorted) {
                const movedText = item.moved_in ? `From ${item.moved_in}` : '-';
                const momentumText = item.momentum === 'rising' ? '\u2191' : item.momentum === 'declining' ? '\u2193' : '-';
                const momentumColor = item.momentum === 'rising' ? '#065F46' : item.momentum === 'declining' ? '#991B1B' : colors.slate500;
                tableBody.push([
                    { text: sanitize(item.name), margin: [4, 2, 4, 2], fontSize: 8, bold: true },
                    { text: sanitize(item.ring), margin: [4, 2, 4, 2], fontSize: 8, color: ringColor(item.ring) },
                    { text: momentumText, margin: [4, 2, 4, 2], fontSize: 8, color: momentumColor, alignment: 'center' },
                    { text: movedText, margin: [4, 2, 4, 2], fontSize: 7, color: item.moved_in ? '#D97706' : colors.slate500 },
                    { text: sanitize(item.description), margin: [4, 2, 4, 2], fontSize: 7, color: colors.slate600 },
                    { text: item.is_new ? 'NEW' : '-', margin: [4, 2, 4, 2], fontSize: 7, color: item.is_new ? colors.adopt : colors.slate500 },
                ]);
            }

            content.push({
                table: { headerRows: 1, widths: ['auto', 'auto', 'auto', 'auto', '*', 'auto'], body: tableBody },
                layout: {
                    hLineColor: () => colors.border, vLineColor: () => colors.border,
                    hLineWidth: () => 0.5, vLineWidth: () => 0.5,
                },
                margin: [0, 0, 0, 4],
            });
        }
    }

    // Report Sections — parse markdown for bold, headings, bullets
    if (report.report_sections?.length > 0) {
        content.push(sectionHeader('Detailed Analysis', colors.sections));
        for (const section of report.report_sections) {
            content.push(card([
                { text: sanitize(section.section_title), fontSize: 11, bold: true, margin: [0, 0, 0, 4] },
                ...markdownToContent(section.content || '', 9, colors.slate600),
                ...sourceUrlsBlock(section.source_urls),
            ]));
        }
    }

    // Recommendations
    if (report.recommendations?.length > 0) {
        content.push(sectionHeader(`Recommendations (${report.recommendations.length})`, colors.recommendations));
        for (const rec of report.recommendations) {
            content.push(card([
                {
                    columns: [
                        pill(rec.priority, impactTone(rec.priority === 'Critical' ? 'High' : rec.priority)),
                        { text: sanitize(rec.title), fontSize: 10, bold: true, width: '*', margin: [0, 1, 0, 0] },
                        ...(rec.effort ? [pill(`${rec.effort} effort`, rec.effort === 'Low' ? colors.impactLow : rec.effort === 'High' ? colors.impactHigh : colors.impactMed)] : []),
                        ...(rec.urgency ? [pill(rec.urgency, rec.urgency === 'Immediate' ? colors.impactHigh : rec.urgency === 'Short-term' ? colors.impactMed : colors.impactLow)] : []),
                    ],
                    columnGap: 6,
                    margin: [0, 0, 0, 3],
                },
                { text: sanitize(rec.description), fontSize: 9, color: colors.slate600, margin: [0, 0, 0, 3] },
                ...(rec.rationale ? [
                    { text: sanitize(rec.rationale), fontSize: 8, italics: true, color: colors.slate500, margin: [8, 0, 0, 3] as any },
                ] : []),
                ...(rec.related_trends?.length > 0 ? [{
                    columns: rec.related_trends.slice(0, 4).map(t => pill(t, colors.trends)),
                    columnGap: 4,
                }] : []),
            ]));
        }
    }

    // Blind Spots
    if (report.blind_spots && report.blind_spots.length > 0) {
        content.push(sectionHeader(`Coverage Blind Spots (${report.blind_spots.length})`, colors.blindSpots));
        for (const spot of report.blind_spots as SensingBlindSpot[]) {
            content.push(card([
                { text: sanitize(spot.area), fontSize: 10, bold: true, color: colors.blindSpots.text, margin: [0, 0, 0, 2] },
                { text: sanitize(spot.why_it_matters), fontSize: 9, color: colors.slate600, margin: [0, 0, 0, 2] },
                ...(spot.suggested_sources?.length > 0 ? [{
                    text: `Look at: ${spot.suggested_sources.map(sanitize).join(', ')}`,
                    fontSize: 7, italics: true, color: colors.slate500,
                }] : []),
            ], '#FDE68A'));
        }
    }

    // Notable Articles
    if (report.notable_articles?.length > 0) {
        content.push(sectionHeader(`Notable Articles (${report.notable_articles.length})`, colors.articles));
        const tableBody: any[] = [
            [
                { text: 'Title', bold: true, fillColor: colors.articles.bg, color: colors.articles.text, margin: [4, 4, 4, 4] },
                { text: 'Source', bold: true, fillColor: colors.articles.bg, color: colors.articles.text, margin: [4, 4, 4, 4] },
                { text: 'Quadrant', bold: true, fillColor: colors.articles.bg, color: colors.articles.text, margin: [4, 4, 4, 4] },
                { text: 'Ring', bold: true, fillColor: colors.articles.bg, color: colors.articles.text, margin: [4, 4, 4, 4] },
            ],
        ];
        for (const article of report.notable_articles) {
            tableBody.push([
                { text: sanitize(article.title), margin: [4, 3, 4, 3], fontSize: 8 },
                { text: sanitize(article.source), margin: [4, 3, 4, 3], fontSize: 8 },
                { text: sanitize(article.quadrant), margin: [4, 3, 4, 3], fontSize: 8 },
                { text: sanitize(article.ring), margin: [4, 3, 4, 3], fontSize: 8, color: ringColor(article.ring) },
            ]);
        }
        content.push({
            table: { headerRows: 1, widths: ['*', 'auto', 'auto', 'auto'], body: tableBody },
            layout: {
                hLineColor: () => colors.border, vLineColor: () => colors.border,
                hLineWidth: () => 0.5, vLineWidth: () => 0.5,
            },
        });
    }

    return {
        info: {
            title: report.report_title || 'Tech Sensing Report',
            author: 'Knowledge Synthesis Platform',
            subject: `Tech Sensing - ${report.domain}`,
            keywords: 'tech sensing, technology radar, trends',
        },
        pageMargins: [36, 50, 36, 50],
        footer: (currentPage: number, pageCount: number) => ({
            columns: [
                { text: `Tech Sensing Report | ${report.domain} | ${today}`, color: colors.slate500, fontSize: 8 },
                { text: `${currentPage} / ${pageCount}`, alignment: 'right', color: colors.slate500, fontSize: 8 },
            ],
            margin: [36, 10, 36, 0],
        }),
        content,
        defaultStyle: { fontSize: 10, color: colors.slate800 },
    };
}

export async function downloadSensingReportPdf(data: SensingReportData, filename?: string) {
    const doc = buildSensingPdf(data);
    const safe = (data.report.report_title || 'Tech Sensing Report')
        .replace(/[^a-z0-9\-\s]/gi, '').trim() || 'Tech Sensing Report';
    const name = filename || `${safe}.pdf`;
    pdfMake.createPdf(doc).download(name);
}


// ── Board-Ready One-Pager PDF ─────────────────────────────────────────────

function buildBoardPdf(data: SensingReportData): TDocumentDefinitions {
    const { report, meta } = data;
    const content: Content[] = [];

    // Compact title banner
    content.push(banner(
        report.report_title || 'Tech Sensing Report',
        `${report.domain} | ${report.date_range} | Board Summary`,
    ));

    // Bottom Line
    if (report.bottom_line) {
        content.push(card([
            { text: 'BOTTOM LINE', fontSize: 9, bold: true, color: colors.bottomLine.text, margin: [0, 0, 0, 3] },
            { text: sanitize(report.bottom_line), fontSize: 10, color: colors.slate800, lineHeight: 1.4 },
        ], '#FDA4AF'));
    }

    // Executive Summary (truncated)
    if (report.executive_summary) {
        const summary = report.executive_summary.length > 800
            ? report.executive_summary.slice(0, 800) + '...'
            : report.executive_summary;
        content.push(sectionHeader('Executive Summary', colors.executive));
        content.push(card(
            markdownToContent(summary, 9, colors.slate800),
            '#BFDBFE',
        ));
    }

    // Top 5 Events (headline + actor only)
    if (report.top_events && report.top_events.length > 0) {
        const events = report.top_events.slice(0, 5);
        content.push(sectionHeader(`Top Events (${events.length})`, colors.topEvents));
        for (const event of events) {
            content.push(card([
                { text: sanitize((event as SensingTopEvent).headline), fontSize: 9, color: colors.slate800 },
                pill((event as SensingTopEvent).actor, { bg: '#DBEAFE', text: '#1E40AF' }),
            ]));
        }
    }

    // Key Trends (name + impact badge only)
    if (report.key_trends && report.key_trends.length > 0) {
        content.push(sectionHeader(`Key Trends (${report.key_trends.length})`, colors.trends));
        const trendRows: Content[][] = report.key_trends.map((t: any) => [
            { text: sanitize(t.trend_name || t.name), fontSize: 9, color: colors.slate800 },
            pill(t.impact_level || 'Medium', impactTone(t.impact_level || 'Medium')),
        ]);
        content.push({
            table: { widths: ['*', 'auto'], body: trendRows },
            layout: {
                hLineWidth: (_i: number, _node: any) => 0.5,
                vLineWidth: () => 0,
                hLineColor: () => colors.border,
                paddingLeft: () => 6, paddingRight: () => 6,
                paddingTop: () => 4, paddingBottom: () => 4,
            },
            margin: [0, 0, 0, 6],
        });
    }

    // Top 5 Recommendations (title + priority only)
    if (report.recommendations && report.recommendations.length > 0) {
        const recs = report.recommendations.slice(0, 5);
        content.push(sectionHeader(`Top Recommendations (${recs.length})`, colors.recommendations));
        for (const rec of recs) {
            const r = rec as any;
            content.push(card([
                {
                    columns: [
                        { text: sanitize(r.title || r.recommendation), fontSize: 9, color: colors.slate800, width: '*' },
                        ...(r.priority ? [pill(r.priority, impactTone(r.priority === 'High' ? 'High' : r.priority === 'Medium' ? 'Medium' : 'Low'))] : []),
                    ],
                    columnGap: 6,
                },
            ]));
        }
    }

    // Footer
    content.push({
        text: `Generated ${meta.generated_at ? new Date(meta.generated_at).toLocaleDateString() : 'N/A'} | ${report.total_articles_analyzed || 0} articles analyzed`,
        fontSize: 7, color: colors.slate500, alignment: 'right', margin: [0, 12, 0, 0],
    });

    return {
        pageSize: 'A4',
        pageMargins: [36, 36, 36, 36],
        content,
        defaultStyle: { font: 'Roboto' },
    };
}

export async function downloadSensingBoardPdf(data: SensingReportData, filename?: string) {
    const doc = buildBoardPdf(data);
    const safe = (data.report.report_title || 'Board Summary')
        .replace(/[^a-z0-9\-\s]/gi, '').trim() || 'Board Summary';
    const name = filename || `${safe} - Board.pdf`;
    pdfMake.createPdf(doc).download(name);
}


// ── Company Analysis PDF ──────────────────────────────────────────────────

const companyColors = {
    header: { bg: '#EEF2FF', text: '#3730A3' },
    summary: { bg: '#EFF6FF', text: '#1E40AF' },
    matrix: { bg: '#ECFDF5', text: '#047857' },
    company: { bg: '#F5F3FF', text: '#6D28D9' },
    strength: { bg: '#ECFDF5', text: '#047857' },
    gap: { bg: '#FFF7ED', text: '#C2410C' },
};

function confidenceTone(c: number) {
    if (c >= 0.7) return { bg: '#D1FAE5', text: '#065F46' };
    if (c >= 0.4) return { bg: '#FEF3C7', text: '#92400E' };
    if (c >= 0.1) return { bg: '#FFEDD5', text: '#9A3412' };
    return { bg: '#F1F5F9', text: '#475569' };
}

function buildCompanyAnalysisPdf(data: { report: CompanyAnalysisReport }): TDocumentDefinitions {
    const { report } = data;
    const today = new Date().toLocaleDateString();
    const content: Content[] = [];

    // Title banner
    content.push(banner(
        'Company Analysis',
        `${report.domain} | ${report.companies_analyzed.length} companies x ${report.technologies_analyzed.length} technologies`,
    ));

    // Meta pills
    content.push({
        columns: [
            pill(`Domain: ${report.domain}`, companyColors.header),
            pill(`Companies: ${report.companies_analyzed.length}`, companyColors.header),
            pill(`Technologies: ${report.technologies_analyzed.length}`, companyColors.header),
            pill(`Generated: ${today}`, companyColors.header),
        ],
        columnGap: 6,
        margin: [0, 0, 0, 10],
    });

    // Executive summary
    if (report.executive_summary) {
        content.push(sectionHeader('Executive Summary', companyColors.summary));
        content.push(card([
            { text: sanitize(report.executive_summary), fontSize: 10, color: colors.slate800, lineHeight: 1.4 },
        ]));
    }

    // Comparative matrix
    if (report.comparative_matrix.length > 0) {
        content.push(sectionHeader('Comparative Matrix', companyColors.matrix));
        const tableBody: any[] = [
            [
                { text: 'Technology', bold: true, fillColor: companyColors.matrix.bg, color: companyColors.matrix.text, margin: [4, 4, 4, 4] },
                { text: 'Leader', bold: true, fillColor: companyColors.matrix.bg, color: companyColors.matrix.text, margin: [4, 4, 4, 4] },
                { text: 'Rationale', bold: true, fillColor: companyColors.matrix.bg, color: companyColors.matrix.text, margin: [4, 4, 4, 4] },
            ],
        ];
        for (const row of report.comparative_matrix) {
            tableBody.push([
                { text: sanitize(row.technology), margin: [4, 3, 4, 3], fontSize: 9, bold: true },
                { text: sanitize(row.leader), margin: [4, 3, 4, 3], fontSize: 9, color: row.leader === 'Unclear' ? colors.slate500 : colors.primary },
                { text: sanitize(row.rationale), margin: [4, 3, 4, 3], fontSize: 8, color: colors.slate600 },
            ]);
        }
        content.push({
            table: { headerRows: 1, widths: ['auto', 'auto', '*'], body: tableBody },
            layout: {
                hLineColor: () => colors.border, vLineColor: () => colors.border,
                hLineWidth: () => 0.5, vLineWidth: () => 0.5,
            },
        });
    }

    // Per-company profiles
    for (const profile of report.company_profiles) {
        content.push(sectionHeader(profile.company, companyColors.company));

        content.push(card([
            { text: sanitize(profile.overall_summary), fontSize: 10, color: colors.slate800, lineHeight: 1.4 },
        ]));

        if (profile.strengths.length > 0 || profile.gaps.length > 0) {
            const strengthsCol: Content[] = [
                { text: 'Strengths', fontSize: 10, bold: true, color: companyColors.strength.text, margin: [0, 0, 0, 3] },
                ...(profile.strengths.length > 0
                    ? [{ ul: profile.strengths.map((s) => ({ text: sanitize(s), fontSize: 9, color: colors.slate600 })) } as any]
                    : [{ text: '(none identified)', fontSize: 9, color: colors.slate500, italics: true } as any]),
            ];
            const gapsCol: Content[] = [
                { text: 'Gaps', fontSize: 10, bold: true, color: companyColors.gap.text, margin: [0, 0, 0, 3] },
                ...(profile.gaps.length > 0
                    ? [{ ul: profile.gaps.map((g) => ({ text: sanitize(g), fontSize: 9, color: colors.slate600 })) } as any]
                    : [{ text: '(none identified)', fontSize: 9, color: colors.slate500, italics: true } as any]),
            ];
            content.push({
                columns: [
                    { stack: strengthsCol, width: '*' },
                    { stack: gapsCol, width: '*' },
                ],
                columnGap: 12,
                margin: [0, 4, 0, 6],
            });
        }

        // Per-technology findings table
        if (profile.technology_findings.length > 0) {
            const findingsBody: any[] = [
                [
                    { text: 'Technology', bold: true, fillColor: companyColors.company.bg, color: companyColors.company.text, margin: [4, 4, 4, 4] },
                    { text: 'Stance', bold: true, fillColor: companyColors.company.bg, color: companyColors.company.text, margin: [4, 4, 4, 4] },
                    { text: 'Confidence', bold: true, fillColor: companyColors.company.bg, color: companyColors.company.text, margin: [4, 4, 4, 4] },
                    { text: 'Summary', bold: true, fillColor: companyColors.company.bg, color: companyColors.company.text, margin: [4, 4, 4, 4] },
                ],
            ];
            for (const f of profile.technology_findings) {
                const conf = confidenceTone(f.confidence);
                findingsBody.push([
                    { text: sanitize(f.technology), margin: [4, 3, 4, 3], fontSize: 8, bold: true },
                    { text: sanitize(f.stance || '—'), margin: [4, 3, 4, 3], fontSize: 8 },
                    {
                        text: `${Math.round((f.confidence || 0) * 100)}%`,
                        margin: [4, 3, 4, 3], fontSize: 8, bold: true,
                        color: conf.text, fillColor: conf.bg, alignment: 'center',
                    },
                    {
                        stack: [
                            { text: sanitize(f.summary), fontSize: 8, color: colors.slate600 },
                            ...(f.specific_products.length > 0
                                ? [{ text: `Products: ${sanitize(f.specific_products.join(', '))}`, fontSize: 7, color: colors.slate500, margin: [0, 2, 0, 0] } as any]
                                : []),
                            ...(f.recent_developments.length > 0
                                ? [{ text: `Recent: ${sanitize(f.recent_developments.slice(0, 2).join(' | '))}`, fontSize: 7, color: colors.slate500, margin: [0, 2, 0, 0] } as any]
                                : []),
                        ],
                        margin: [4, 3, 4, 3],
                    },
                ]);
            }
            content.push({
                table: { headerRows: 1, widths: ['auto', 'auto', 'auto', '*'], body: findingsBody },
                layout: {
                    hLineColor: () => colors.border, vLineColor: () => colors.border,
                    hLineWidth: () => 0.5, vLineWidth: () => 0.5,
                },
                margin: [0, 4, 0, 12],
            });
        }
    }

    return {
        info: {
            title: `Company Analysis - ${report.domain}`,
            author: 'Knowledge Synthesis Platform',
            subject: `Company Analysis - ${report.domain}`,
            keywords: 'tech sensing, company analysis, competitive intelligence',
        },
        pageMargins: [36, 50, 36, 50],
        footer: (currentPage: number, pageCount: number) => ({
            columns: [
                { text: `Company Analysis | ${report.domain} | ${today}`, color: colors.slate500, fontSize: 8 },
                { text: `${currentPage} / ${pageCount}`, alignment: 'right', color: colors.slate500, fontSize: 8 },
            ],
            margin: [36, 10, 36, 0],
        }),
        content,
        defaultStyle: { fontSize: 10, color: colors.slate800 },
    };
}

export async function downloadCompanyAnalysisPdf(
    data: { report: CompanyAnalysisReport },
    filename?: string,
) {
    const doc = buildCompanyAnalysisPdf(data);
    const safe = `Company Analysis - ${data.report.domain}`
        .replace(/[^a-z0-9\-\s]/gi, '').trim() || 'Company Analysis';
    const name = filename || `${safe}.pdf`;
    pdfMake.createPdf(doc).download(name);
}
