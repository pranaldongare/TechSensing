import React from 'react';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Minus, Users } from 'lucide-react';

export interface HiringSnapshot {
  total_postings: number;
  seniority_breakdown: string[];
  domains: string[];
  trend_vs_previous: 'up' | 'flat' | 'down' | 'unknown';
}

interface Props {
  hiring?: HiringSnapshot | null;
  compact?: boolean;
}

const trendIcon = (trend: string) => {
  switch (trend) {
    case 'up':
      return <TrendingUp className="w-3 h-3 text-green-600 dark:text-green-400" />;
    case 'down':
      return <TrendingDown className="w-3 h-3 text-red-500 dark:text-red-400" />;
    case 'flat':
      return <Minus className="w-3 h-3 text-muted-foreground" />;
    default:
      return null;
  }
};

/**
 * Renders hiring signal snapshot for a company (#31).
 * Use `compact` for inline badge in BriefingCard headers.
 */
const HiringSignalsPanel: React.FC<Props> = ({ hiring, compact }) => {
  if (!hiring || hiring.total_postings === 0) return null;

  if (compact) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
        <Users className="w-3 h-3" />
        {hiring.total_postings} jobs
        {trendIcon(hiring.trend_vs_previous)}
      </span>
    );
  }

  return (
    <div className="rounded-md border p-3 space-y-2">
      <div className="flex items-center gap-2 text-xs font-medium">
        <Users className="w-3.5 h-3.5 text-primary" />
        Hiring signals
        <Badge variant="outline" className="text-[10px]">
          {hiring.total_postings} postings
        </Badge>
        {trendIcon(hiring.trend_vs_previous)}
        {hiring.trend_vs_previous !== 'unknown' && (
          <span className="text-[10px] text-muted-foreground">
            {hiring.trend_vs_previous} vs last run
          </span>
        )}
      </div>

      {hiring.seniority_breakdown.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {hiring.seniority_breakdown.map((s, i) => (
            <Badge
              key={i}
              variant="outline"
              className="text-[10px] bg-muted/40"
            >
              {s}
            </Badge>
          ))}
        </div>
      )}

      {hiring.domains.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {hiring.domains.map((d) => (
            <Badge
              key={d}
              variant="secondary"
              className="text-[10px]"
            >
              {d}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
};

export default HiringSignalsPanel;
