import PptxGenJS from 'pptxgenjs';
import type {
    SensingReportData, SensingRadarItem, CompanyAnalysisReport,
} from './api';
import { renderRadarToCanvas } from './sensing-report-pdf';

// ── Color constants ──────────────────────────────────────────────────────
const COLORS = {
    banner: '1e3a5f',
    white: 'FFFFFF',
    lightBg: 'F8FAFC',
    accent: 'f59e0b',
    textDark: '1F2937',
    textMuted: '64748B',
    border: 'E2E8F0',
    adopt: '059669',
    trial: '2563EB',
    assess: 'D97706',
    hold: 'DC2626',
    impactHigh: 'DC2626',
    impactMed: 'D97706',
    impactLow: '059669',
    quadTechniques: '1ebccd',
    quadPlatforms: 'f38a3e',
    quadTools: '86b82a',
    quadLanguages: 'b32059',
};

function ringColor(ring: string): string {
    if (ring === 'Adopt') return COLORS.adopt;
    if (ring === 'Trial') return COLORS.trial;
    if (ring === 'Assess') return COLORS.assess;
    return COLORS.hold;
}

function impactColor(level: string): string {
    if (level === 'High') return COLORS.impactHigh;
    if (level === 'Medium') return COLORS.impactMed;
    return COLORS.impactLow;
}

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

export async function downloadSensingReportPptx(
    data: SensingReportData,
    radarImageDataUrl?: string,
): Promise<void> {
    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_WIDE'; // 13.33 x 7.5
    pptx.author = 'Knowledge Synthesis Platform';
    pptx.subject = `Tech Sensing - ${data.report.domain}`;
    pptx.title = data.report.report_title || 'Tech Sensing Report';

    const { report, meta } = data;

    // ── Slide 1: Title ──
    const slide1 = pptx.addSlide();
    slide1.addShape(pptx.ShapeType.rect, {
        x: 0, y: 0, w: '100%', h: '100%',
        fill: { color: COLORS.banner },
    });
    slide1.addText(sanitize(report.report_title) || 'Tech Sensing Report', {
        x: 0.8, y: 1.5, w: 11.7, h: 1.2,
        fontSize: 32, bold: true, color: COLORS.white,
        align: 'center',
    });
    slide1.addText(sanitize(report.domain), {
        x: 0.8, y: 2.8, w: 11.7, h: 0.6,
        fontSize: 20, color: COLORS.accent,
        align: 'center',
    });
    slide1.addText(
        `${sanitize(report.date_range)}  |  ${report.total_articles_analyzed} articles analyzed  |  Generated in ${meta.execution_time_seconds}s`,
        {
            x: 0.8, y: 3.6, w: 11.7, h: 0.5,
            fontSize: 12, color: 'B0BEC5',
            align: 'center',
        }
    );
    slide1.addText(new Date(meta.generated_at).toLocaleDateString(), {
        x: 0.8, y: 4.3, w: 11.7, h: 0.4,
        fontSize: 11, color: '90A4AE',
        align: 'center',
    });

    // ── Slide 2: Executive Summary ──
    const slide2 = pptx.addSlide();
    addSlideHeader(slide2, 'Executive Summary');
    slide2.addText(sanitize(report.executive_summary), {
        x: 0.6, y: 1.2, w: 12.1, h: 5.5,
        fontSize: 14, color: COLORS.textDark,
        lineSpacingMultiple: 1.3,
        valign: 'top',
    });

    // ── Headline Moves slides ──
    if (report.headline_moves?.length > 0) {
        const movesPerSlide = 5;
        for (let i = 0; i < report.headline_moves.length; i += movesPerSlide) {
            const chunk = report.headline_moves.slice(i, i + movesPerSlide);
            const slide = pptx.addSlide();
            const pageNum = Math.floor(i / movesPerSlide) + 1;
            const totalPages = Math.ceil(report.headline_moves.length / movesPerSlide);
            addSlideHeader(slide, `Headline Moves${totalPages > 1 ? ` (${pageNum}/${totalPages})` : ''}`);

            let y = 1.2;
            for (let j = 0; j < chunk.length; j++) {
                const move = chunk[j];
                const num = i + j + 1;

                slide.addText([
                    { text: `${num}. `, options: { bold: true, color: COLORS.accent, fontSize: 11 } },
                    { text: sanitize(move.headline), options: { fontSize: 11, color: COLORS.textDark } },
                ], { x: 0.5, y, w: 12.3, h: 0.4 });

                slide.addText([
                    { text: sanitize(move.actor), options: { bold: true, fontSize: 9, color: '1E40AF' } },
                    { text: `  |  ${sanitize(move.segment)}`, options: { fontSize: 9, color: COLORS.textMuted } },
                ], { x: 0.8, y: y + 0.38, w: 11.5, h: 0.3 });

                y += 0.85;
            }
        }
    }

    // ── Slide 3: Technology Radar ──
    if (report.radar_items?.length > 0) {
        const slide3 = pptx.addSlide();
        addSlideHeader(slide3, 'Technology Radar');

        // Radar image
        let radarImg = radarImageDataUrl;
        if (!radarImg) {
            try {
                radarImg = renderRadarToCanvas(report.radar_items);
            } catch { /* fall through */ }
        }

        if (radarImg) {
            slide3.addImage({
                data: radarImg,
                x: 0.15, y: 1.1, w: 5.8, h: 5.8,
            });
        }

        // Radar summary table on the right
        const ringCounts: Record<string, number> = { Adopt: 0, Trial: 0, Assess: 0, Hold: 0 };
        for (const item of report.radar_items) {
            if (ringCounts[item.ring] !== undefined) ringCounts[item.ring]++;
        }

        const tableRows: PptxGenJS.TableRow[] = [
            [
                { text: 'Ring', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark } },
                { text: 'Count', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark, align: 'center' } },
            ],
            ...(['Adopt', 'Trial', 'Assess', 'Hold'] as const).map(ring => ([
                { text: ring, options: { fontSize: 10, color: ringColor(ring), bold: true } },
                { text: String(ringCounts[ring]), options: { fontSize: 10, align: 'center' as const } },
            ])),
        ];

        slide3.addTable(tableRows, {
            x: 6.3, y: 1.3, w: 3.5,
            border: { type: 'solid' as const, pt: 0.5, color: COLORS.border },
            colW: [2.0, 1.5],
        });

        // Quadrant legend
        const quadrants = [
            { name: 'Techniques', color: COLORS.quadTechniques },
            { name: 'Platforms', color: COLORS.quadPlatforms },
            { name: 'Tools', color: COLORS.quadTools },
            { name: 'Languages & Frameworks', color: COLORS.quadLanguages },
        ];
        let qy = 3.8;
        for (const q of quadrants) {
            slide3.addShape(pptx.ShapeType.rect, {
                x: 6.4, y: qy, w: 0.2, h: 0.2,
                fill: { color: q.color },
            });
            slide3.addText(q.name, {
                x: 6.75, y: qy - 0.02, w: 3, h: 0.25,
                fontSize: 9, color: COLORS.textDark,
            });
            qy += 0.35;
        }

        // New items count
        const newCount = report.radar_items.filter(i => i.is_new).length;
        const movedCount = report.radar_items.filter(i => i.moved_in).length;
        if (newCount > 0 || movedCount > 0) {
            slide3.addText(
                `${report.radar_items.length} technologies tracked  |  ${newCount} new  |  ${movedCount} moved`,
                { x: 6.3, y: 5.6, w: 6, h: 0.3, fontSize: 9, color: COLORS.textMuted }
            );
        }
    }

    // ── Slide 4-5: Key Trends ──
    if (report.key_trends?.length > 0) {
        const trendsPerSlide = 4;
        for (let i = 0; i < report.key_trends.length; i += trendsPerSlide) {
            const chunk = report.key_trends.slice(i, i + trendsPerSlide);
            const slide = pptx.addSlide();
            const pageNum = Math.floor(i / trendsPerSlide) + 1;
            const totalPages = Math.ceil(report.key_trends.length / trendsPerSlide);
            addSlideHeader(slide, `Key Trends${totalPages > 1 ? ` (${pageNum}/${totalPages})` : ''}`);

            const tableRows: PptxGenJS.TableRow[] = [
                [
                    { text: 'Trend', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark } },
                    { text: 'Impact', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark, align: 'center' } },
                    { text: 'Horizon', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark, align: 'center' } },
                    { text: 'Description', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark } },
                ],
            ];

            for (const trend of chunk) {
                tableRows.push([
                    { text: sanitize(trend.trend_name), options: { fontSize: 10, bold: true } },
                    { text: trend.impact_level, options: { fontSize: 9, color: impactColor(trend.impact_level), bold: true, align: 'center' } },
                    { text: sanitize(trend.time_horizon), options: { fontSize: 9, align: 'center' } },
                    { text: truncate(trend.description, 200), options: { fontSize: 9, color: COLORS.textMuted } },
                ]);
            }

            slide.addTable(tableRows, {
                x: 0.5, y: 1.2, w: 12.3,
                border: { type: 'solid' as const, pt: 0.5, color: COLORS.border },
                colW: [2.5, 1.0, 1.2, 7.6],
                autoPage: false,
            });
        }
    }

    // ── Slide 6: Market Signals ──
    if (report.market_signals?.length > 0) {
        const signalsPerSlide = 5;
        for (let i = 0; i < report.market_signals.length; i += signalsPerSlide) {
            const chunk = report.market_signals.slice(i, i + signalsPerSlide);
            const slide = pptx.addSlide();
            addSlideHeader(slide, 'Market Signals');

            const tableRows: PptxGenJS.TableRow[] = [
                [
                    { text: 'Company / Player', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark } },
                    { text: 'Segment', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark } },
                    { text: 'Signal', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark } },
                    { text: 'Strategic Intent', options: { bold: true, fill: { color: COLORS.lightBg }, fontSize: 10, color: COLORS.textDark } },
                ],
            ];

            for (const signal of chunk) {
                tableRows.push([
                    { text: sanitize(signal.company_or_player), options: { fontSize: 10, bold: true } },
                    { text: sanitize(signal.segment), options: { fontSize: 9, color: COLORS.textMuted } },
                    { text: truncate(signal.signal, 150), options: { fontSize: 9, color: COLORS.textMuted } },
                    { text: truncate(signal.strategic_intent, 120), options: { fontSize: 9, color: COLORS.textMuted } },
                ]);
            }

            slide.addTable(tableRows, {
                x: 0.5, y: 1.2, w: 12.3,
                border: { type: 'solid' as const, pt: 0.5, color: COLORS.border },
                colW: [2.2, 1.6, 4.5, 4.0],
                autoPage: false,
            });
        }
    }

    // ── Slide 7: Recommendations ──
    if (report.recommendations?.length > 0) {
        const slide = pptx.addSlide();
        addSlideHeader(slide, 'Recommendations');

        let y = 1.2;
        for (const rec of report.recommendations.slice(0, 6)) {
            const priorityColor = rec.priority === 'Critical' ? COLORS.impactHigh :
                rec.priority === 'High' ? COLORS.impactHigh :
                rec.priority === 'Medium' ? COLORS.impactMed : COLORS.impactLow;

            slide.addText([
                { text: `[${rec.priority}] `, options: { bold: true, color: priorityColor, fontSize: 11 } },
                { text: sanitize(rec.title), options: { bold: true, fontSize: 11 } },
            ], { x: 0.6, y, w: 12, h: 0.35 });

            slide.addText(truncate(rec.description, 250), {
                x: 0.8, y: y + 0.35, w: 11.8, h: 0.5,
                fontSize: 9, color: COLORS.textMuted,
                valign: 'top',
            });

            y += 0.95;
        }
    }

    // ── Slide 8: Technology Deep Dives (top items) ──
    if (report.radar_item_details?.length > 0) {
        const itemsPerSlide = 3;
        const maxSlides = 3; // Limit to 9 items total
        const items = report.radar_item_details.slice(0, itemsPerSlide * maxSlides);

        for (let i = 0; i < items.length; i += itemsPerSlide) {
            const chunk = items.slice(i, i + itemsPerSlide);
            const slide = pptx.addSlide();
            addSlideHeader(slide, 'Technology Deep Dives');

            let y = 1.2;
            for (const item of chunk) {
                const radarItem = report.radar_items?.find(r => r.name === item.technology_name);
                const ringText = radarItem ? ` [${radarItem.ring} / ${radarItem.quadrant}]` : '';

                slide.addText([
                    { text: sanitize(item.technology_name), options: { bold: true, fontSize: 12, color: COLORS.textDark } },
                    { text: ringText, options: { fontSize: 10, color: radarItem ? ringColor(radarItem.ring) : COLORS.textMuted } },
                ], { x: 0.5, y, w: 12.3, h: 0.35 });

                slide.addText(truncate(item.what_it_is, 300), {
                    x: 0.7, y: y + 0.35, w: 11.9, h: 0.7,
                    fontSize: 9, color: COLORS.textMuted,
                    valign: 'top',
                });

                slide.addText(truncate(item.why_it_matters, 300), {
                    x: 0.7, y: y + 1.05, w: 11.9, h: 0.7,
                    fontSize: 9, color: COLORS.textMuted,
                    italic: true,
                    valign: 'top',
                });

                y += 1.95;
            }
        }
    }

    // Generate and download
    const safeName = (report.report_title || 'Tech Sensing Report')
        .replace(/[^a-z0-9\-\s]/gi, '').trim() || 'Tech Sensing Report';
    await pptx.writeFile({ fileName: `${safeName}.pptx` });
}

function addSlideHeader(slide: PptxGenJS.Slide, title: string): void {
    slide.addShape('rect' as unknown as PptxGenJS.ShapeType, {
        x: 0, y: 0, w: '100%', h: 0.9,
        fill: { color: COLORS.banner },
    });
    slide.addText(title, {
        x: 0.5, y: 0.15, w: 12, h: 0.6,
        fontSize: 22, bold: true, color: COLORS.white,
    });
}


// ── Company Analysis PPTX ────────────────────────────────────────────────

function confidenceFill(c: number): string {
    if (c >= 0.7) return 'D1FAE5';
    if (c >= 0.4) return 'FEF3C7';
    if (c >= 0.1) return 'FFEDD5';
    return 'F1F5F9';
}

export async function downloadCompanyAnalysisPptx(
    data: { report: CompanyAnalysisReport },
    _filename?: string,
): Promise<void> {
    const { report } = data;

    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_WIDE';
    pptx.author = 'Knowledge Synthesis Platform';
    pptx.subject = `Company Analysis - ${report.domain}`;
    pptx.title = `Company Analysis - ${report.domain}`;

    // ── Slide 1: Title ──
    const title = pptx.addSlide();
    title.addShape('rect' as unknown as PptxGenJS.ShapeType, {
        x: 0, y: 0, w: '100%', h: '100%',
        fill: { color: COLORS.banner },
    });
    title.addText('Company Analysis', {
        x: 0.8, y: 1.8, w: 11.7, h: 1.0,
        fontSize: 34, bold: true, color: COLORS.white, align: 'center',
    });
    title.addText(sanitize(report.domain), {
        x: 0.8, y: 3.0, w: 11.7, h: 0.6,
        fontSize: 22, color: COLORS.accent, align: 'center',
    });
    title.addText(
        `${report.companies_analyzed.length} companies  |  ${report.technologies_analyzed.length} technologies`,
        {
            x: 0.8, y: 3.8, w: 11.7, h: 0.5,
            fontSize: 14, color: 'B0BEC5', align: 'center',
        },
    );
    title.addText(
        `Companies: ${report.companies_analyzed.map(sanitize).join(', ')}`,
        {
            x: 0.8, y: 4.6, w: 11.7, h: 0.6,
            fontSize: 12, color: '90A4AE', align: 'center',
        },
    );
    title.addText(new Date().toLocaleDateString(), {
        x: 0.8, y: 5.6, w: 11.7, h: 0.4,
        fontSize: 11, color: '90A4AE', align: 'center',
    });

    // ── Slide 2: Executive Summary ──
    if (report.executive_summary) {
        const slide = pptx.addSlide();
        addSlideHeader(slide, 'Executive Summary');
        slide.addText(sanitize(report.executive_summary), {
            x: 0.6, y: 1.2, w: 12.1, h: 5.5,
            fontSize: 14, color: COLORS.textDark,
            lineSpacingMultiple: 1.3,
            valign: 'top',
        });
    }

    // ── Slide 3: Comparative Matrix ──
    if (report.comparative_matrix.length > 0) {
        const slide = pptx.addSlide();
        addSlideHeader(slide, 'Comparative Matrix');
        const rows: PptxGenJS.TableRow[] = [
            [
                { text: 'Technology', options: { bold: true, fill: { color: COLORS.banner }, color: COLORS.white, fontSize: 12 } },
                { text: 'Leader', options: { bold: true, fill: { color: COLORS.banner }, color: COLORS.white, fontSize: 12 } },
                { text: 'Rationale', options: { bold: true, fill: { color: COLORS.banner }, color: COLORS.white, fontSize: 12 } },
            ],
        ];
        for (const row of report.comparative_matrix) {
            rows.push([
                { text: sanitize(row.technology), options: { bold: true, fontSize: 11, color: COLORS.textDark } },
                {
                    text: sanitize(row.leader),
                    options: {
                        bold: true, fontSize: 11,
                        color: row.leader === 'Unclear' ? COLORS.textMuted : '1E3A5F',
                    },
                },
                { text: sanitize(row.rationale), options: { fontSize: 10, color: COLORS.textMuted } },
            ]);
        }
        slide.addTable(rows, {
            x: 0.5, y: 1.2, w: 12.3,
            colW: [3.0, 2.0, 7.3],
            border: { type: 'solid', pt: 0.5, color: COLORS.border },
            fontFace: 'Arial',
        });
    }

    // ── Per-company slides ──
    for (const profile of report.company_profiles) {
        const slide = pptx.addSlide();
        addSlideHeader(slide, sanitize(profile.company));

        // Overall summary
        slide.addText(sanitize(profile.overall_summary), {
            x: 0.5, y: 1.0, w: 12.3, h: 1.3,
            fontSize: 12, color: COLORS.textDark, valign: 'top',
            lineSpacingMultiple: 1.2,
        });

        // Strengths / Gaps
        if (profile.strengths.length > 0) {
            slide.addText('Strengths', {
                x: 0.5, y: 2.3, w: 6.0, h: 0.3,
                fontSize: 11, bold: true, color: COLORS.adopt,
            });
            slide.addText(
                profile.strengths.map((s) => `• ${sanitize(s)}`).join('\n'),
                {
                    x: 0.5, y: 2.6, w: 6.0, h: 0.9,
                    fontSize: 10, color: COLORS.textDark, valign: 'top',
                },
            );
        }
        if (profile.gaps.length > 0) {
            slide.addText('Gaps', {
                x: 6.8, y: 2.3, w: 6.0, h: 0.3,
                fontSize: 11, bold: true, color: COLORS.impactMed,
            });
            slide.addText(
                profile.gaps.map((g) => `• ${sanitize(g)}`).join('\n'),
                {
                    x: 6.8, y: 2.6, w: 6.0, h: 0.9,
                    fontSize: 10, color: COLORS.textDark, valign: 'top',
                },
            );
        }

        // Findings table
        if (profile.technology_findings.length > 0) {
            const rows: PptxGenJS.TableRow[] = [
                [
                    { text: 'Technology', options: { bold: true, fill: { color: COLORS.banner }, color: COLORS.white, fontSize: 10 } },
                    { text: 'Stance', options: { bold: true, fill: { color: COLORS.banner }, color: COLORS.white, fontSize: 10 } },
                    { text: 'Conf.', options: { bold: true, fill: { color: COLORS.banner }, color: COLORS.white, fontSize: 10 } },
                    { text: 'Summary', options: { bold: true, fill: { color: COLORS.banner }, color: COLORS.white, fontSize: 10 } },
                ],
            ];
            for (const f of profile.technology_findings) {
                rows.push([
                    { text: sanitize(f.technology), options: { fontSize: 9, bold: true } },
                    { text: sanitize(f.stance || '—'), options: { fontSize: 9 } },
                    {
                        text: `${Math.round((f.confidence || 0) * 100)}%`,
                        options: {
                            fontSize: 9, bold: true, align: 'center',
                            fill: { color: confidenceFill(f.confidence) },
                        },
                    },
                    {
                        text: truncate(f.summary, 280),
                        options: { fontSize: 8, color: COLORS.textMuted },
                    },
                ]);
            }
            slide.addTable(rows, {
                x: 0.5, y: 3.7, w: 12.3,
                colW: [2.3, 2.0, 1.0, 7.0],
                border: { type: 'solid', pt: 0.5, color: COLORS.border },
                fontFace: 'Arial',
                autoPage: true,
                autoPageRepeatHeader: true,
            });
        }
    }

    const safeName = `Company Analysis - ${report.domain}`
        .replace(/[^a-z0-9\-\s]/gi, '').trim() || 'Company Analysis';
    await pptx.writeFile({ fileName: `${safeName}.pptx` });
}
