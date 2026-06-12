/* eslint-disable @typescript-eslint/no-explicit-any */
type TDocumentDefinitions = any;
type Content = any;

import pdfMake from 'pdfmake/build/pdfmake';
import 'pdfmake/build/vfs_fonts';
import type { OnepagerCard } from './api';

const g: any = (typeof window !== 'undefined' ? window : globalThis) as any;
if (g?.pdfMake?.vfs) {
    (pdfMake as any).vfs = g.pdfMake.vfs;
}

type Layout = 'compact' | 'detailed';

// ── Color palette ──────────────────────────────────────────────────────────
const COLORS = {
    banner: '#1e3a5f',
    white: '#FFFFFF',
    textDark: '#1F2937',
    textMuted: '#64748B',
    border: '#E2E8F0',
    bulletMarker: '#DC2626',
    sourceLink: '#2563EB',
    footerBg: '#111827',
};

const CATEGORY_COLORS = [
    '#0D9488', '#059669', '#7C3AED', '#EA580C', '#2563EB', '#DC2626', '#DB2777', '#4F46E5',
];

// ── Helpers ──────────────────────────────────────────────────────────────

function sanitize(s: string | undefined | null): string {
    if (!s) return '';
    return String(s)
        .replace(/[–—]/g, '-')
        .replace(/[""]/g, '"')
        .replace(/'/g, "'")
        .replace(/ /g, ' ');
}

function truncate(s: string, max: number): string {
    const clean = sanitize(s);
    return clean.length > max ? clean.slice(0, max - 3) + '...' : clean;
}

/** Split **markdown bold** markers into a pdfmake rich-text array (bold+italic). */
function parseEmphasis(s: string): Content {
    const parts = sanitize(s).split('**');
    const out: any[] = [];
    parts.forEach((p, i) => {
        if (!p) return;
        out.push(i % 2 === 1 ? { text: p, bold: true, italics: true } : { text: p });
    });
    return out.length ? out : [{ text: sanitize(s) }];
}

function sortByCategory(cards: OnepagerCard[]): OnepagerCard[] {
    const tagOrder = new Map<string, number>();
    let idx = 0;
    for (const c of cards) {
        if (!tagOrder.has(c.category_tag)) tagOrder.set(c.category_tag, idx++);
    }
    return [...cards].sort(
        (a, b) => (tagOrder.get(a.category_tag) ?? 0) - (tagOrder.get(b.category_tag) ?? 0),
    );
}

function buildCategoryColorMap(cards: OnepagerCard[]): Map<string, string> {
    const map = new Map<string, string>();
    let ci = 0;
    for (const c of cards) {
        if (!map.has(c.category_tag)) {
            map.set(c.category_tag, CATEGORY_COLORS[ci % CATEGORY_COLORS.length]);
            ci++;
        }
    }
    return map;
}

function whoLine(card: OnepagerCard): string {
    const org = card.organization || card.actor || '';
    const people = (card.people || []).slice(0, 2);
    return sanitize([org, ...people].filter(Boolean).join('  ·  '));
}

function metricsLine(card: OnepagerCard): string {
    const ms = card.metrics || [];
    if (!ms.length) return '';
    return ms
        .map((m) => `${m.label} ${m.value}${m.comparison ? ` (${m.comparison})` : ''}`)
        .join('   ·   ');
}

/** Build the pdfmake content for a single card cell. */
function buildCardContent(card: OnepagerCard, categoryColor: string, detailed: boolean): Content {
    const initial = (card.organization || card.actor || card.card_title || '?').charAt(0).toUpperCase();

    const stack: Content[] = [
        // Headline row with icon
        {
            columns: [
                {
                    width: 20,
                    stack: [{
                        table: {
                            widths: [16],
                            body: [[{
                                text: initial, fontSize: 10, bold: true, color: COLORS.white,
                                fillColor: categoryColor, alignment: 'center', margin: [0, 2, 0, 2] as any,
                            }]],
                        },
                        layout: 'noBorders',
                    }],
                },
                {
                    text: truncate(card.card_title, detailed ? 110 : 80),
                    fontSize: detailed ? 10 : 9, bold: true, color: COLORS.textDark,
                    margin: [4, 2, 0, 0] as any,
                },
            ],
            columnGap: 0,
            margin: [0, 0, 0, 3] as any,
        },
    ];

    // Organization + people subtitle
    const who = whoLine(card);
    if (who) {
        stack.push({ text: who, fontSize: detailed ? 8 : 7, italics: true, color: COLORS.textMuted, margin: [0, 0, 0, 2] as any });
    }

    // Metrics strip
    const metrics = metricsLine(card);
    if (metrics) {
        stack.push({ text: truncate(metrics, detailed ? 260 : 140), fontSize: detailed ? 8 : 7, bold: true, color: categoryColor, margin: [0, 0, 0, 3] as any });
    }

    // Bullets
    const maxBullets = detailed ? 6 : (metrics ? 2 : 3);
    for (const b of card.bullets.slice(0, maxBullets)) {
        stack.push({
            columns: [
                { text: '×', width: 8, fontSize: 8, color: COLORS.bulletMarker, bold: true },
                { text: parseEmphasis(truncate(b, 170)), fontSize: detailed ? 8 : 7.5, color: COLORS.textDark },
            ],
            columnGap: 3,
            margin: [0, 1, 0, 1] as any,
        });
    }

    // Source link
    stack.push({
        text: sanitize(card.source_label || 'See Full Article'),
        fontSize: 6.5, color: COLORS.sourceLink, decoration: 'underline', margin: [0, 4, 0, 0] as any,
        ...(card.source_url ? { link: card.source_url } : {}),
    });

    return { margin: [0, 0, 0, 0] as any, stack };
}

/** Build a 2-column card table for a chunk of cards (≤8). */
function buildTable(chunk: OnepagerCard[], colorMap: Map<string, string>, detailed: boolean): Content {
    const leftCards: OnepagerCard[] = [];
    const rightCards: OnepagerCard[] = [];
    chunk.forEach((c, i) => (i % 2 === 0 ? leftCards : rightCards).push(c));

    const buildSpanInfo = (colCards: OnepagerCard[]) => {
        const info: { tag: string; color: string; isStart: boolean; spanRows: number }[] = [];
        let i = 0;
        while (i < colCards.length) {
            const tag = colCards[i].category_tag;
            let count = 1;
            while (i + count < colCards.length && colCards[i + count].category_tag === tag) count++;
            for (let j = 0; j < count; j++) {
                info.push({
                    tag, color: colorMap.get(tag) || CATEGORY_COLORS[0],
                    isStart: j === 0, spanRows: j === 0 ? count : 0,
                });
            }
            i += count;
        }
        return info;
    };

    const leftSpanInfo = buildSpanInfo(leftCards);
    const rightSpanInfo = buildSpanInfo(rightCards);
    const maxRows = Math.max(leftCards.length, rightCards.length, 1);
    const tableBody: any[][] = [];

    // Vertical (stacked-character) rail text so it stays legible in a narrow column.
    const railText = (tag: string) => (tag || '').split('').join('\n');

    for (let r = 0; r < maxRows; r++) {
        const row: any[] = [];

        if (r < leftSpanInfo.length && leftSpanInfo[r].isStart) {
            row.push({
                text: railText(leftSpanInfo[r].tag), fontSize: 7, bold: true, color: COLORS.white,
                fillColor: leftSpanInfo[r].color, alignment: 'center', margin: [0, 6, 0, 6] as any,
                rowSpan: leftSpanInfo[r].spanRows,
            });
        } else if (r < leftSpanInfo.length) {
            row.push({ text: '', fillColor: leftSpanInfo[r].color });
        } else {
            row.push({ text: '' });
        }

        if (r < leftCards.length) {
            row.push(buildCardContent(leftCards[r], colorMap.get(leftCards[r].category_tag) || CATEGORY_COLORS[0], detailed));
        } else {
            row.push({ text: '' });
        }

        row.push({ text: '', border: [false, false, false, false] });

        if (r < rightSpanInfo.length && rightSpanInfo[r].isStart) {
            row.push({
                text: railText(rightSpanInfo[r].tag), fontSize: 7, bold: true, color: COLORS.white,
                fillColor: rightSpanInfo[r].color, alignment: 'center', margin: [0, 6, 0, 6] as any,
                rowSpan: rightSpanInfo[r].spanRows,
            });
        } else if (r < rightSpanInfo.length) {
            row.push({ text: '', fillColor: rightSpanInfo[r].color });
        } else {
            row.push({ text: '' });
        }

        if (r < rightCards.length) {
            row.push(buildCardContent(rightCards[r], colorMap.get(rightCards[r].category_tag) || CATEGORY_COLORS[0], detailed));
        } else {
            row.push({ text: '' });
        }

        tableBody.push(row);
    }

    return {
        table: { headerRows: 0, widths: [18, '*', 8, 18, '*'], body: tableBody },
        layout: {
            hLineWidth: () => 0.5,
            vLineWidth: () => 0.5,
            hLineColor: () => COLORS.border,
            vLineColor: () => COLORS.border,
            paddingLeft: () => 6,
            paddingRight: () => 6,
            paddingTop: () => 5,
            paddingBottom: () => 5,
        },
    };
}

// ── Main export function ─────────────────────────────────────────────────

export async function downloadOnepagerPdf(
    cards: OnepagerCard[],
    domain: string,
    dateRange: string,
    layout: Layout = 'compact',
): Promise<void> {
    const sorted = sortByCategory(cards);
    const colorMap = buildCategoryColorMap(sorted);
    const detailed = layout === 'detailed';

    // Compact: one table (≤8 cards) on a single page.
    // Detailed: 4 cards per page (2×2), paginated, with fuller card content.
    const perPage = detailed ? 4 : 8;
    const chunks: OnepagerCard[][] = [];
    for (let i = 0; i < sorted.length && i < (detailed ? sorted.length : 8); i += perPage) {
        chunks.push(sorted.slice(i, i + perPage));
    }
    if (chunks.length === 0) chunks.push([]);

    const content: Content[] = [];
    chunks.forEach((chunk, ci) => {
        content.push(buildTable(chunk, colorMap, detailed));
        if (ci < chunks.length - 1) content.push({ text: '', pageBreak: 'after' });
    });

    const docDefinition: TDocumentDefinitions = {
        pageSize: 'LETTER',
        pageOrientation: 'landscape',
        pageMargins: [20, 60, 20, 30] as any,
        header: {
            columns: [
                { text: 'WEEKLY TECH SENSING', fontSize: 16, bold: true, color: COLORS.white, margin: [25, 15, 0, 0] as any },
                { text: `${sanitize(domain)}  |  ${sanitize(dateRange)}`, fontSize: 9, color: '#B0BEC5', alignment: 'right', margin: [0, 20, 25, 0] as any },
            ],
            margin: [0, 0, 0, 0] as any,
            canvas: [{ type: 'rect', x: 0, y: 0, w: 792, h: 45, color: COLORS.banner }],
        },
        footer: {
            canvas: [{ type: 'rect', x: 0, y: 0, w: 792, h: 15, color: COLORS.footerBg }],
        },
        content,
    };

    pdfMake.createPdf(docDefinition).download('Weekly Tech Sensing One-Pager.pdf');
}
