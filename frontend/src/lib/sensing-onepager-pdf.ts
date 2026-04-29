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
    '#0D9488',  // teal
    '#059669',  // green
    '#7C3AED',  // purple
    '#EA580C',  // orange
    '#2563EB',  // blue
    '#DC2626',  // red
    '#DB2777',  // pink
    '#4F46E5',  // indigo
];

// ── Helpers ──────────────────────────────────────────────────────────────

function sanitize(s: string | undefined | null): string {
    if (!s) return '';
    return String(s)
        .replace(/[–—]/g, '-')
        .replace(/[""]/g, '"')
        .replace(/'/g, "'")
        .replace(/\u202F/g, ' ');
}

function truncate(s: string, max: number): string {
    const clean = sanitize(s);
    return clean.length > max ? clean.slice(0, max - 3) + '...' : clean;
}

function sortByCategory(cards: OnepagerCard[]): OnepagerCard[] {
    const tagOrder = new Map<string, number>();
    let idx = 0;
    for (const c of cards) {
        if (!tagOrder.has(c.category_tag)) {
            tagOrder.set(c.category_tag, idx++);
        }
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

/**
 * Build the pdfmake content for a single card cell (one table cell).
 */
function buildCardContent(card: OnepagerCard, categoryColor: string): Content {
    const actorInitial = (card.actor || card.card_title || '?').charAt(0).toUpperCase();

    const bulletItems: Content[] = card.bullets.slice(0, 5).map(b => ({
        columns: [
            { text: '\u00d7', width: 8, fontSize: 8, color: COLORS.bulletMarker, bold: true },
            { text: truncate(b, 150), fontSize: 7.5, color: COLORS.textDark },
        ],
        columnGap: 3,
        margin: [0, 1, 0, 1] as any,
    }));

    return {
        margin: [0, 0, 0, 0] as any,
        stack: [
            // Headline row with icon
            {
                columns: [
                    // Icon circle (simulated with a colored square + letter)
                    {
                        width: 20,
                        stack: [{
                            table: {
                                widths: [16],
                                body: [[{
                                    text: actorInitial,
                                    fontSize: 10,
                                    bold: true,
                                    color: COLORS.white,
                                    fillColor: categoryColor,
                                    alignment: 'center',
                                    margin: [0, 2, 0, 2] as any,
                                }]],
                            },
                            layout: 'noBorders',
                        }],
                    },
                    // Headline text
                    {
                        text: truncate(card.card_title, 80),
                        fontSize: 9,
                        bold: true,
                        color: COLORS.textDark,
                        margin: [4, 2, 0, 0] as any,
                    },
                ],
                columnGap: 0,
                margin: [0, 0, 0, 4] as any,
            },
            // Bullets
            ...bulletItems,
            // Source link
            {
                text: sanitize(card.source_label || 'See Full Article'),
                fontSize: 6.5,
                color: COLORS.sourceLink,
                decoration: 'underline',
                margin: [0, 4, 0, 0] as any,
                ...(card.source_url ? { link: card.source_url } : {}),
            },
        ],
    };
}

// ── Main export function ─────────────────────────────────────────────────

export async function downloadOnepagerPdf(
    cards: OnepagerCard[],
    domain: string,
    dateRange: string,
): Promise<void> {
    const sorted = sortByCategory(cards);
    const colorMap = buildCategoryColorMap(sorted);

    // Split into left (even) and right (odd) columns
    const leftCards: OnepagerCard[] = [];
    const rightCards: OnepagerCard[] = [];
    for (let i = 0; i < sorted.length && i < 8; i++) {
        if (i % 2 === 0) leftCards.push(sorted[i]);
        else rightCards.push(sorted[i]);
    }

    // Build table rows: each row has [left_sidebar, left_card, gap, right_sidebar, right_card]
    const maxRows = Math.max(leftCards.length, rightCards.length, 1);
    const tableBody: any[][] = [];

    // Track category spans for sidebars
    const buildSpanInfo = (colCards: OnepagerCard[]) => {
        const info: { tag: string; color: string; isStart: boolean; spanRows: number }[] = [];
        let i = 0;
        while (i < colCards.length) {
            const tag = colCards[i].category_tag;
            let count = 1;
            while (i + count < colCards.length && colCards[i + count].category_tag === tag) {
                count++;
            }
            for (let j = 0; j < count; j++) {
                info.push({
                    tag,
                    color: colorMap.get(tag) || CATEGORY_COLORS[0],
                    isStart: j === 0,
                    spanRows: j === 0 ? count : 0,
                });
            }
            i += count;
        }
        return info;
    };

    const leftSpanInfo = buildSpanInfo(leftCards);
    const rightSpanInfo = buildSpanInfo(rightCards);

    for (let r = 0; r < maxRows; r++) {
        const row: any[] = [];

        // Left sidebar
        if (r < leftSpanInfo.length && leftSpanInfo[r].isStart) {
            row.push({
                text: leftSpanInfo[r].tag,
                fontSize: 7,
                bold: true,
                color: COLORS.white,
                fillColor: leftSpanInfo[r].color,
                alignment: 'center',
                margin: [0, 6, 0, 6] as any,
                rowSpan: leftSpanInfo[r].spanRows,
            });
        } else if (r < leftSpanInfo.length) {
            row.push({ text: '', fillColor: leftSpanInfo[r].color });
        } else {
            row.push({ text: '' });
        }

        // Left card
        if (r < leftCards.length) {
            const color = colorMap.get(leftCards[r].category_tag) || CATEGORY_COLORS[0];
            row.push(buildCardContent(leftCards[r], color));
        } else {
            row.push({ text: '' });
        }

        // Gap
        row.push({ text: '', border: [false, false, false, false] });

        // Right sidebar
        if (r < rightSpanInfo.length && rightSpanInfo[r].isStart) {
            row.push({
                text: rightSpanInfo[r].tag,
                fontSize: 7,
                bold: true,
                color: COLORS.white,
                fillColor: rightSpanInfo[r].color,
                alignment: 'center',
                margin: [0, 6, 0, 6] as any,
                rowSpan: rightSpanInfo[r].spanRows,
            });
        } else if (r < rightSpanInfo.length) {
            row.push({ text: '', fillColor: rightSpanInfo[r].color });
        } else {
            row.push({ text: '' });
        }

        // Right card
        if (r < rightCards.length) {
            const color = colorMap.get(rightCards[r].category_tag) || CATEGORY_COLORS[0];
            row.push(buildCardContent(rightCards[r], color));
        } else {
            row.push({ text: '' });
        }

        tableBody.push(row);
    }

    const docDefinition: TDocumentDefinitions = {
        pageSize: 'LETTER',
        pageOrientation: 'landscape',
        pageMargins: [20, 60, 20, 30] as any,

        header: {
            columns: [
                {
                    text: 'WEEKLY TECH SENSING',
                    fontSize: 16,
                    bold: true,
                    color: COLORS.white,
                    margin: [25, 15, 0, 0] as any,
                },
                {
                    text: `${sanitize(domain)}  |  ${sanitize(dateRange)}`,
                    fontSize: 9,
                    color: '#B0BEC5',
                    alignment: 'right',
                    margin: [0, 20, 25, 0] as any,
                },
            ],
            margin: [0, 0, 0, 0] as any,
            canvas: [{
                type: 'rect',
                x: 0, y: 0,
                w: 792, h: 45,
                color: COLORS.banner,
            }],
        },

        footer: {
            canvas: [{
                type: 'rect',
                x: 0, y: 0,
                w: 792, h: 15,
                color: COLORS.footerBg,
            }],
        },

        content: [
            {
                table: {
                    headerRows: 0,
                    widths: [18, '*', 8, 18, '*'],
                    body: tableBody,
                },
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
            },
        ],
    };

    pdfMake.createPdf(docDefinition).download('Weekly Tech Sensing One-Pager.pdf');
}
