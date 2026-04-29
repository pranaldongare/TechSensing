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
    bulletMarker: 'DC2626',  // Red × marker
    sourceLink: '2563EB',
    footerBg: '111827',
};

// 8 rotating category sidebar colors
const CATEGORY_COLORS = [
    '0D9488',  // teal
    '059669',  // green
    '7C3AED',  // purple
    'EA580C',  // orange
    '2563EB',  // blue
    'DC2626',  // red
    'DB2777',  // pink
    '4F46E5',  // indigo
];

// ── Layout constants (inches, on 13.33 × 7.5 widescreen) ────────────────
const TITLE_BAR_H = 0.55;
const FOOTER_H = 0.2;
const GRID_TOP = 0.68;
const GRID_BOTTOM = 7.5 - FOOTER_H - 0.05;
const ROW_COUNT = 4;
const ROW_GAP = 0.06;
const SIDEBAR_W = 0.32;
const ICON_SIZE = 0.32;
const CARD_LEFT_MARGIN = 0.12;

const TOTAL_GRID_H = GRID_BOTTOM - GRID_TOP;
const ROW_H = (TOTAL_GRID_H - (ROW_COUNT - 1) * ROW_GAP) / ROW_COUNT;

// Column positions
const COL1_X = 0.4;
const COL2_X = 6.88;
const CARD_W = 5.95;

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

/** Sort cards by category_tag so same-category cards are adjacent. */
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

/** Build a global color map from category_tag → color for all cards. */
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

interface SidebarSpan {
    tag: string;
    color: string;
    startRow: number;  // Row index within the column
    spanRows: number;
}

/**
 * Compute sidebar spans for a single column's cards.
 * Consecutive cards with the same category_tag share a merged sidebar.
 */
function buildSidebarSpans(
    columnCards: OnepagerCard[],
    colorMap: Map<string, string>,
): SidebarSpan[] {
    const spans: SidebarSpan[] = [];
    let i = 0;
    while (i < columnCards.length) {
        const tag = columnCards[i].category_tag;
        let count = 1;
        while (i + count < columnCards.length && columnCards[i + count].category_tag === tag) {
            count++;
        }
        spans.push({
            tag,
            color: colorMap.get(tag) || CATEGORY_COLORS[0],
            startRow: i,
            spanRows: count,
        });
        i += count;
    }
    return spans;
}

/**
 * Render sidebar spans for one column.
 */
function renderSidebars(
    slide: PptxGenJS.Slide,
    spans: SidebarSpan[],
    colX: number,
): void {
    for (const span of spans) {
        const y = GRID_TOP + span.startRow * (ROW_H + ROW_GAP);
        const h = span.spanRows * ROW_H + (span.spanRows - 1) * ROW_GAP;

        slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
            x: colX, y, w: SIDEBAR_W, h,
            fill: { color: span.color },
            rectRadius: 0.04,
        });
        slide.addText(span.tag, {
            x: colX, y, w: SIDEBAR_W, h,
            fontSize: 7, bold: true, color: COLORS.white,
            align: 'center', valign: 'middle',
            rotate: 270,
        });
    }
}

/**
 * Render a single card at the given grid position.
 */
function renderCard(
    slide: PptxGenJS.Slide,
    card: OnepagerCard,
    colX: number,
    row: number,
    categoryColor: string,
): void {
    const cardX = colX + SIDEBAR_W + 0.06;
    const cardW = CARD_W - SIDEBAR_W - 0.06;
    const cardY = GRID_TOP + row * (ROW_H + ROW_GAP);

    // Card background
    slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
        x: cardX, y: cardY, w: cardW, h: ROW_H,
        fill: { color: COLORS.white },
        line: { color: COLORS.border, width: 0.5 },
        rectRadius: 0.04,
    });

    // Actor icon circle
    const iconX = cardX + 0.1;
    const iconY = cardY + 0.1;
    const actorInitial = (card.actor || card.card_title || '?').charAt(0).toUpperCase();

    slide.addShape('ellipse' as unknown as PptxGenJS.ShapeType, {
        x: iconX, y: iconY, w: ICON_SIZE, h: ICON_SIZE,
        fill: { color: categoryColor },
    });
    slide.addText(actorInitial, {
        x: iconX, y: iconY, w: ICON_SIZE, h: ICON_SIZE,
        fontSize: 13, bold: true, color: COLORS.white,
        align: 'center', valign: 'middle',
    });

    // Headline
    const textX = iconX + ICON_SIZE + CARD_LEFT_MARGIN;
    const textW = cardW - (ICON_SIZE + CARD_LEFT_MARGIN + 0.3);

    slide.addText(truncate(card.card_title, 80), {
        x: textX, y: cardY + 0.08, w: textW, h: 0.3,
        fontSize: 10, bold: true, color: COLORS.textDark,
        valign: 'top',
    });

    // Bullets
    const bulletY = cardY + 0.38;
    const bulletH = ROW_H - 0.58;
    const bulletTexts: PptxGenJS.TextProps[] = [];
    const maxBullets = Math.min(card.bullets.length, 5);

    for (let b = 0; b < maxBullets; b++) {
        if (b > 0) {
            bulletTexts.push({ text: '\n', options: { fontSize: 2, breakType: 'none' } });
        }
        bulletTexts.push({
            text: '\u00d7  ',
            options: { fontSize: 8.5, color: COLORS.bulletMarker, bold: true },
        });
        bulletTexts.push({
            text: truncate(card.bullets[b], 150),
            options: { fontSize: 8, color: COLORS.textDark },
        });
    }

    slide.addText(bulletTexts, {
        x: textX, y: bulletY, w: textW, h: bulletH,
        valign: 'top',
        lineSpacingMultiple: 1.15,
        paraSpaceAfter: 2,
    });

    // Source link
    const linkY = cardY + ROW_H - 0.2;
    slide.addText(sanitize(card.source_label || 'See Full Article'), {
        x: textX, y: linkY, w: textW, h: 0.18,
        fontSize: 7, color: COLORS.sourceLink,
        underline: { style: 'sng' },
        ...(card.source_url ? { hyperlink: { url: card.source_url } } : {}),
    });
}

// ── Main export function ─────────────────────────────────────────────────

export async function downloadOnepagerPptx(
    cards: OnepagerCard[],
    domain: string,
    dateRange: string,
): Promise<void> {
    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_WIDE'; // 13.33 × 7.5
    pptx.author = 'Knowledge Synthesis Platform';
    pptx.subject = `Weekly Tech Sensing - ${domain}`;
    pptx.title = 'Weekly Tech Sensing';

    const sorted = sortByCategory(cards);
    const colorMap = buildCategoryColorMap(sorted);

    // Split into left-column (even indices) and right-column (odd indices)
    const leftCards: OnepagerCard[] = [];
    const rightCards: OnepagerCard[] = [];
    for (let i = 0; i < sorted.length && i < ROW_COUNT * 2; i++) {
        if (i % 2 === 0) leftCards.push(sorted[i]);
        else rightCards.push(sorted[i]);
    }

    const slide = pptx.addSlide();

    // ── Title bar ──
    slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
        x: 0, y: 0, w: '100%', h: TITLE_BAR_H,
        fill: { color: COLORS.banner },
    });
    slide.addText('WEEKLY TECH SENSING', {
        x: 0.4, y: 0.08, w: 5, h: 0.4,
        fontSize: 20, bold: true, color: COLORS.white,
    });
    slide.addText(`${sanitize(domain)}  |  ${sanitize(dateRange)}`, {
        x: 7, y: 0.12, w: 5.9, h: 0.32,
        fontSize: 10, color: 'B0BEC5', align: 'right',
    });

    // ── Footer bar ──
    slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
        x: 0, y: 7.5 - FOOTER_H, w: '100%', h: FOOTER_H,
        fill: { color: COLORS.footerBg },
    });

    // ── Left-column sidebars ──
    const leftSpans = buildSidebarSpans(leftCards, colorMap);
    renderSidebars(slide, leftSpans, COL1_X);

    // ── Right-column sidebars ──
    const rightSpans = buildSidebarSpans(rightCards, colorMap);
    renderSidebars(slide, rightSpans, COL2_X);

    // ── Render left-column cards ──
    for (let r = 0; r < leftCards.length; r++) {
        const card = leftCards[r];
        const color = colorMap.get(card.category_tag) || CATEGORY_COLORS[0];
        renderCard(slide, card, COL1_X, r, color);
    }

    // ── Render right-column cards ──
    for (let r = 0; r < rightCards.length; r++) {
        const card = rightCards[r];
        const color = colorMap.get(card.category_tag) || CATEGORY_COLORS[0];
        renderCard(slide, card, COL2_X, r, color);
    }

    // Generate and download
    await pptx.writeFile({ fileName: 'Weekly Tech Sensing One-Pager.pptx' });
}
