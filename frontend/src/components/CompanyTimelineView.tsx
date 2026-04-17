import React, { useEffect, useMemo, useState } from 'react';
import { Calendar, ExternalLink, RefreshCcw } from 'lucide-react';
import { api, type CompanyTimeline, type CompanyTimelineEvent } from '@/lib/api';

interface Props {
  /** If set, only fetch/render this company's timeline. */
  companies?: string[];
  /** Optional: render into an existing parent that supplied the data. */
  preloaded?: CompanyTimeline[];
  /** Callers can pass a caption overriding the default heading. */
  heading?: string;
}

// Category -> color class. Unknown categories fall back to neutral.
const CATEGORY_COLORS: Record<string, string> = {
  'Product Launch': 'bg-emerald-500',
  'Research Publication': 'bg-violet-500',
  'Model Release': 'bg-sky-500',
  'Funding': 'bg-amber-500',
  'Acquisition': 'bg-rose-500',
  'Partnership': 'bg-teal-500',
  'Regulatory': 'bg-orange-500',
  'Layoff': 'bg-slate-500',
  'Technical Blog': 'bg-indigo-500',
  'Analysis': 'bg-muted-foreground',
  'Other': 'bg-muted-foreground',
};

const colorFor = (category: string): string =>
  CATEGORY_COLORS[category] || 'bg-muted-foreground';

const groupByMonth = (
  events: CompanyTimelineEvent[],
): Array<[string, CompanyTimelineEvent[]]> => {
  const m = new Map<string, CompanyTimelineEvent[]>();
  for (const e of events) {
    const k = e.month_bucket || 'unknown';
    const arr = m.get(k) || [];
    arr.push(e);
    m.set(k, arr);
  }
  return Array.from(m.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
};

/**
 * Per-company timeline view (#14) — aggregates events from Key Companies
 * and Company Analysis runs, grouped by month, color-coded by category.
 */
const CompanyTimelineView: React.FC<Props> = ({
  companies,
  preloaded,
  heading,
}) => {
  const [timelines, setTimelines] = useState<CompanyTimeline[]>(
    preloaded || [],
  );
  const [loading, setLoading] = useState(!preloaded);
  const [error, setError] = useState<string>('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.sensingCompanyTimeline(companies || []);
      setTimelines(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (preloaded) {
      setTimelines(preloaded);
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(companies || [])]);

  const categoryLegend = useMemo(() => {
    const seen = new Set<string>();
    for (const t of timelines) {
      for (const e of t.events) seen.add(e.category);
    }
    return Array.from(seen).slice(0, 12);
  }, [timelines]);

  return (
    <div className="rounded border border-border bg-card/50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Calendar className="h-4 w-4 text-sky-500" />
          {heading || 'Company timeline'}
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          disabled={loading}
        >
          <RefreshCcw
            className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`}
          />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-2 text-xs text-rose-600">{error}</div>
      )}

      {timelines.length === 0 && !loading && (
        <div className="text-xs text-muted-foreground">
          No historical events yet — run Company Analysis or Key Companies
          a few times to populate this timeline.
        </div>
      )}

      <div className="space-y-4">
        {timelines.map((t) => {
          const months = groupByMonth(t.events);
          return (
            <div key={t.company}>
              <div className="mb-1 flex items-center justify-between">
                <div className="font-medium">{t.company}</div>
                <div className="text-[11px] text-muted-foreground">
                  {t.first_seen?.slice(0, 10) || '—'} →{' '}
                  {t.last_seen?.slice(0, 10) || '—'} · {t.events.length}{' '}
                  event(s)
                </div>
              </div>
              <div className="space-y-2">
                {months.map(([month, evs]) => (
                  <div
                    key={month}
                    className="rounded border border-border/60 bg-background/40 p-2"
                  >
                    <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {month}
                    </div>
                    <ul className="space-y-1">
                      {evs.map((e, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-2 text-xs"
                        >
                          <span
                            className={`mt-1 inline-block h-2 w-2 flex-shrink-0 rounded-full ${colorFor(
                              e.category,
                            )}`}
                            title={e.category}
                          />
                          <div className="flex-1">
                            <span className="text-foreground">
                              {e.headline}
                            </span>
                            {e.source_url && (
                              <a
                                href={e.source_url}
                                target="_blank"
                                rel="noreferrer noopener"
                                className="ml-2 inline-flex items-center gap-0.5 text-primary underline"
                              >
                                <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            )}
                            <div className="text-[10px] text-muted-foreground">
                              {e.category} ·{' '}
                              {e.source === 'company_analysis'
                                ? 'Analysis'
                                : 'Brief'}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {categoryLegend.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-2 text-[10px] text-muted-foreground">
          {categoryLegend.map((c) => (
            <span key={c} className="inline-flex items-center gap-1">
              <span
                className={`inline-block h-2 w-2 rounded-full ${colorFor(
                  c,
                )}`}
              />
              {c}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export default CompanyTimelineView;
