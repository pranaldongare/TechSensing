import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Sparkles, Archive, RotateCcw } from 'lucide-react';
import type { DiffStatus, DiffSummary, DiffTag } from '@/lib/api';

interface ChipProps {
  diff?: DiffTag;
}

const cls = (status: DiffStatus): string => {
  switch (status) {
    case 'NEW':
      return 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200';
    case 'ONGOING':
      return 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-200';
    case 'RESOLVED':
      return 'bg-slate-100 text-slate-800 border-slate-300 dark:bg-slate-900/40 dark:text-slate-200';
  }
};

/** Per-update NEW/ONGOING/RESOLVED chip (#12). */
export const DiffChip: React.FC<ChipProps> = ({ diff }) => {
  if (!diff || !diff.status) return null;
  return (
    <Badge
      variant="outline"
      className={`text-[10px] ${cls(diff.status)}`}
      title={
        diff.previous_headline
          ? `Matched prior: ${diff.previous_headline}`
          : undefined
      }
    >
      {diff.status}
    </Badge>
  );
};

interface SummaryProps {
  diffSummary?: DiffSummary | null;
}

/**
 * Banner shown above the briefings list summarizing NEW / ONGOING /
 * RESOLVED counts and listing up to 5 closed topics.
 */
const KeyCompaniesDiffView: React.FC<SummaryProps> = ({ diffSummary }) => {
  if (!diffSummary) return null;
  const resolved = diffSummary.resolved_topics || [];
  return (
    <div className="rounded border border-border bg-card/50 p-3 text-xs">
      <div className="mb-2 flex flex-wrap items-center gap-2 font-semibold">
        <span className="inline-flex items-center gap-1">
          <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
          {diffSummary.new_count} NEW
        </span>
        <span className="inline-flex items-center gap-1">
          <RotateCcw className="h-3.5 w-3.5 text-amber-500" />
          {diffSummary.ongoing_count} ONGOING
        </span>
        {resolved.length > 0 && (
          <span className="inline-flex items-center gap-1">
            <Archive className="h-3.5 w-3.5 text-slate-500" />
            {resolved.length} RESOLVED
          </span>
        )}
      </div>
      {resolved.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
            Closed topics since previous briefing
          </div>
          <ul className="space-y-0.5">
            {resolved.slice(0, 5).map((r, i) => (
              <li key={i} className="flex items-start gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {r.company}
                </Badge>
                <span className="text-muted-foreground">{r.headline}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default KeyCompaniesDiffView;
