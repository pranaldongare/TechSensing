import PptxGenJS from 'pptxgenjs';
import type { OnepagerCard } from './api';

// ── Color constants ──────────────────────────────────────────────────────
const COLORS = {
    banner: '1e3a5f',
    white: 'FFFFFF',
    lightBg: 'F8FAFC',
    textDark: '1F2937',
    textMuted: '64748B',
    border: 'E2E8F0',
    bulletMarker: 'DC2626',
    sourceLink: '2563EB',
    footerBg: '111827',
};

// 8 rotating category sidebar colors
const CATEGORY_COLORS = [
    '0D9488', '059669', '7C3AED', 'EA580C', '2563EB', 'DC2626', 'DB2777', '4F46E5',
];

// ── Layout constants (inches, on 13.33 × 7.5 widescreen) ────────────────
const TITLE_BAR_H = 0.55;
const FOOTER_H = 0.2;
const GRID_TOP = 0.68;
const GRID_BOTTOM = 7.5 - FOOTER_H - 0.05;
const ROW_GAP = 0.06;
const SIDEBAR_W = 0.32;
const ICON_SIZE = 0.32;
const CARD_LEFT_MARGIN = 0.12;
const COL1_X = 0.4;
const COL2_X = 6.88;
const CARD_W = 5.95;

type Layout = 'compact' | 'detailed';

// ── Helpers ──────────────────────────────────────────────────────────────

function sanitize(s: string | undefined | null): string {
    if (!s) return '';
    return String(s)
        .replace(/[–—]/g, '-')
        .replace(/[""]/g, '"')
        .replace(/'/g, "'")
        .replace(/ /g, ' ');
}

function truncate(s: string, max: number): string {
    const clean = sanitize(s);
    return clean.length > max ? clean.slice(0, max - 3) + '...' : clean;
}

/** Split a string on **markdown bold** markers into emphasized/normal segments. */
function parseEmphasis(s: string): { text: string; em: boolean }[] {
    const parts = sanitize(s).split('**');
    const out: { text: string; em: boolean }[] = [];
    parts.forEach((p, i) => { if (p) out.push({ text: p, em: i % 2 === 1 }); });
    return out.length ? out : [{ text: sanitize(s), em: false }];
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

/** Org + (up to 2) people, for the card subtitle. */
function whoLine(card: OnepagerCard): string {
    const org = card.organization || card.actor || '';
    const people = (card.people || []).slice(0, 2);
    const parts = [org, ...people].filter(Boolean);
    return sanitize(parts.join('  ·  '));
}

/** A single line summarizing the boxed metrics. */
function metricsLine(card: OnepagerCard): string {
    const ms = card.metrics || [];
    if (!ms.length) return '';
    return ms
        .map((m) => `${m.label} ${m.value}${m.comparison ? ` (${m.comparison})` : ''}`)
        .join('   ·   ');
}

interface SidebarSpan { tag: string; color: string; startRow: number; spanRows: number; }

function buildSidebarSpans(columnCards: OnepagerCard[], colorMap: Map<string, string>): SidebarSpan[] {
    const spans: SidebarSpan[] = [];
    let i = 0;
    while (i < columnCards.length) {
        const tag = columnCards[i].category_tag;
        let count = 1;
        while (i + count < columnCards.length && columnCards[i + count].category_tag === tag) count++;
        spans.push({ tag, color: colorMap.get(tag) || CATEGORY_COLORS[0], startRow: i, spanRows: count });
        i += count;
    }
    return spans;
}

function renderSidebars(slide: PptxGenJS.Slide, spans: SidebarSpan[], colX: number, rowH: number): void {
    for (const span of spans) {
        const y = GRID_TOP + span.startRow * (rowH + ROW_GAP);
        const h = span.spanRows * rowH + (span.spanRows - 1) * ROW_GAP;
        slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
            x: colX, y, w: SIDEBAR_W, h, fill: { color: span.color }, rectRadius: 0.04,
        });
        slide.addText(span.tag, {
            x: colX, y, w: SIDEBAR_W, h,
            fontSize: 8, bold: true, color: COLORS.white,
            align: 'center', valign: 'middle',
            // PowerPoint-native vertical text so the label runs cleanly down the
            // rail (rotate:270 rotated the box and clipped/misaligned the text).
            vert: 'vert270',
        });
    }
}

function renderCard(
    slide: PptxGenJS.Slide,
    card: OnepagerCard,
    colX: number,
    row: number,
    categoryColor: string,
    rowH: number,
    detailed: boolean,
): void {
    const cardX = colX + SIDEBAR_W + 0.06;
    const cardW = CARD_W - SIDEBAR_W - 0.06;
    const cardY = GRID_TOP + row * (rowH + ROW_GAP);

    slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
        x: cardX, y: cardY, w: cardW, h: rowH,
        fill: { color: COLORS.white }, line: { color: COLORS.border, width: 0.5 }, rectRadius: 0.04,
    });

    // Actor/org icon circle
    const iconX = cardX + 0.1;
    const iconY = cardY + 0.1;
    const initial = (card.organization || card.actor || card.card_title || '?').charAt(0).toUpperCase();
    slide.addShape('ellipse' as unknown as PptxGenJS.ShapeType, {
        x: iconX, y: iconY, w: ICON_SIZE, h: ICON_SIZE, fill: { color: categoryColor },
    });
    slide.addText(initial, {
        x: iconX, y: iconY, w: ICON_SIZE, h: ICON_SIZE,
        fontSize: 13, bold: true, color: COLORS.white, align: 'center', valign: 'middle',
    });

    const textX = iconX + ICON_SIZE + CARD_LEFT_MARGIN;
    const textW = cardW - (ICON_SIZE + CARD_LEFT_MARGIN + 0.3);
    let y = cardY + 0.08;

    // Title
    slide.addText(truncate(card.card_title, detailed ? 110 : 80), {
        x: textX, y, w: textW, h: 0.3, fontSize: detailed ? 12 : 10, bold: true,
        color: COLORS.textDark, valign: 'top',
    });
    y += detailed ? 0.34 : 0.3;

    // Organization + people subtitle
    const who = whoLine(card);
    if (who) {
        slide.addText(who, {
            x: textX, y, w: textW, h: 0.16, fontSize: detailed ? 9 : 8,
            italic: true, color: COLORS.textMuted, valign: 'top',
        });
        y += detailed ? 0.2 : 0.18;
    }

    // Metrics strip
    const metrics = metricsLine(card);
    if (metrics) {
        slide.addText(truncate(metrics, detailed ? 260 : 140), {
            x: textX, y, w: textW, h: detailed ? 0.3 : 0.18, fontSize: detailed ? 9 : 8,
            bold: true, color: categoryColor, valign: 'top',
        });
        y += detailed ? 0.32 : 0.2;
    }

    // Bullets
    const maxBullets = detailed ? Math.min(card.bullets.length, 6) : Math.min(card.bullets.length, metrics ? 2 : 3);
    const bulletTexts: PptxGenJS.TextProps[] = [];
    for (let b = 0; b < maxBullets; b++) {
        if (b > 0) bulletTexts.push({ text: '\n', options: { fontSize: 2, breakType: 'none' } });
        bulletTexts.push({ text: '×  ', options: { fontSize: 8.5, color: COLORS.bulletMarker, bold: true } });
        for (const seg of parseEmphasis(truncate(card.bullets[b], 170))) {
            bulletTexts.push({
                text: seg.text,
                options: { fontSize: detailed ? 9 : 8, color: COLORS.textDark, bold: seg.em, italic: seg.em },
            });
        }
    }
    const bulletH = (cardY + rowH - 0.2) - y;
    if (bulletTexts.length && bulletH > 0.1) {
        slide.addText(bulletTexts, {
            x: textX, y, w: textW, h: bulletH, valign: 'top', lineSpacingMultiple: 1.15, paraSpaceAfter: 2,
        });
    }

    // Source link
    slide.addText(sanitize(card.source_label || 'See Full Article'), {
        x: textX, y: cardY + rowH - 0.2, w: textW, h: 0.18,
        fontSize: 7, color: COLORS.sourceLink, underline: { style: 'sng' },
        ...(card.source_url ? { hyperlink: { url: card.source_url } } : {}),
    });
}

// ── Main export function ─────────────────────────────────────────────────

export async function downloadOnepagerPptx(
    cards: OnepagerCard[],
    domain: string,
    dateRange: string,
    layout: Layout = 'compact',
): Promise<void> {
    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_WIDE';
    pptx.author = 'Knowledge Synthesis Platform';
    pptx.subject = `Weekly Tech Sensing - ${domain}`;
    pptx.title = 'Weekly Tech Sensing';

    const sorted = sortByCategory(cards);
    const colorMap = buildCategoryColorMap(sorted);

    const rowsPerSlide = layout === 'detailed' ? 2 : 4;
    const cardsPerSlide = rowsPerSlide * 2;
    const rowH = (GRID_BOTTOM - GRID_TOP - (rowsPerSlide - 1) * ROW_GAP) / rowsPerSlide;

    for (let start = 0; start < sorted.length; start += cardsPerSlide) {
        const chunk = sorted.slice(start, start + cardsPerSlide);
        const slide = pptx.addSlide();

        // Title bar
        slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
            x: 0, y: 0, w: '100%', h: TITLE_BAR_H, fill: { color: COLORS.banner },
        });
        slide.addText('WEEKLY TECH SENSING', {
            x: 0.4, y: 0.08, w: 5, h: 0.4, fontSize: 20, bold: true, color: COLORS.white,
        });
        slide.addText(`${sanitize(domain)}  |  ${sanitize(dateRange)}`, {
            x: 7, y: 0.12, w: 5.9, h: 0.32, fontSize: 10, color: 'B0BEC5', align: 'right',
        });

        // Footer bar
        slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
            x: 0, y: 7.5 - FOOTER_H, w: '100%', h: FOOTER_H, fill: { color: COLORS.footerBg },
        });

        const leftCards: OnepagerCard[] = [];
        const rightCards: OnepagerCard[] = [];
        chunk.forEach((c, i) => (i % 2 === 0 ? leftCards : rightCards).push(c));

        renderSidebars(slide, buildSidebarSpans(leftCards, colorMap), COL1_X, rowH);
        renderSidebars(slide, buildSidebarSpans(rightCards, colorMap), COL2_X, rowH);

        leftCards.forEach((c, r) =>
            renderCard(slide, c, COL1_X, r, colorMap.get(c.category_tag) || CATEGORY_COLORS[0], rowH, layout === 'detailed'));
        rightCards.forEach((c, r) =>
            renderCard(slide, c, COL2_X, r, colorMap.get(c.category_tag) || CATEGORY_COLORS[0], rowH, layout === 'detailed'));
    }

    await pptx.writeFile({ fileName: 'Weekly Tech Sensing One-Pager.pptx' });
}
