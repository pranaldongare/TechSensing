import React, { useMemo } from 'react';
import { DollarSign, TrendingUp } from 'lucide-react';
import type { InvestmentEvent, InvestmentEventType } from '@/lib/api';

interface Props {
  events?: InvestmentEvent[];
}

const EVENT_COLORS: Record<InvestmentEventType, string> = {
  Funding: 'bg-emerald-500',
  Acquisition: 'bg-violet-500',
  IPO: 'bg-sky-500',
  Divestiture: 'bg-rose-500',
  Partnership: 'bg-amber-500',
  Hiring: 'bg-slate-400',
  Other: 'bg-muted-foreground',
};

const formatUsd = (n: number): string => {
  if (!n) return '—';
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
};

/** Stacked-bar chart grouping investment events per company (#30). */
const InvestmentSignalChart: React.FC<Props> = ({ events }) => {
  const { totals, maxTotal, breakdown } = useMemo(() => {
    const totals: Record<string, number> = {};
    const breakdown: Record<string, Partial<Record<InvestmentEventType, number>>> = {};
    for (const ev of events || []) {
      if (!ev.amount_usd) continue;
      totals[ev.company] = (totals[ev.company] || 0) + ev.amount_usd;
      const row = breakdown[ev.company] || {};
      row[ev.event_type] = (row[ev.event_type] || 0) + ev.amount_usd;
      breakdown[ev.company] = row;
    }
    return {
      totals,
      maxTotal: Math.max(1, ...Object.values(totals)),
      breakdown,
    };
  }, [events]);

  if (!events || events.length === 0) return null;

  const rows = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const noAmount = (events || []).filter((e) => !e.amount_usd);

  return (
    <div className="rounded border border-border bg-card/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <DollarSign className="h-4 w-4 text-emerald-500" />
        Investment signals
      </div>

      {rows.length > 0 ? (
        <div className="space-y-1.5">
          {rows.map(([company, total]) => {
            const row = breakdown[company] || {};
            const pctTotal = (total / maxTotal) * 100;
            return (
              <div key={company} className="text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{company}</span>
                  <span className="text-muted-foreground">
                    {formatUsd(total)}
                  </span>
                </div>
                <div className="mt-0.5 flex h-3 w-full overflow-hidden rounded bg-muted/40">
                  {(Object.keys(row) as InvestmentEventType[]).map((kind) => {
                    const v = row[kind] || 0;
                    const pct = (v / maxTotal) * 100;
                    return (
                      <span
                        key={kind}
                        className={`${EVENT_COLORS[kind]}`}
                        style={{ width: `${pct}%` }}
                        title={`${kind}: ${formatUsd(v)}`}
                      />
                    );
                  })}
                  <span
                    className="bg-transparent"
                    style={{ width: `${100 - pctTotal}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">
          No dollar-denominated events found.
        </div>
      )}

      {noAmount.length > 0 && (
        <div className="mt-3 border-t border-border pt-2">
          <div className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <TrendingUp className="h-3.5 w-3.5" />
            Additional signals ({noAmount.length})
          </div>
          <div className="flex flex-wrap gap-1.5">
            {noAmount.slice(0, 12).map((e, idx) => (
              <span
                key={idx}
                className={`rounded px-1.5 py-0.5 text-[10px] text-white ${
                  EVENT_COLORS[e.event_type]
                }`}
                title={e.description}
              >
                {e.company}: {e.event_type}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-2 border-t border-border pt-2 text-[10px] text-muted-foreground">
        {(Object.keys(EVENT_COLORS) as InvestmentEventType[]).map((k) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span
              className={`inline-block h-2 w-2 rounded ${EVENT_COLORS[k]}`}
            />
            {k}
          </span>
        ))}
      </div>
    </div>
  );
};

export default InvestmentSignalChart;
