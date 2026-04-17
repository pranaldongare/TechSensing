import React from 'react';
import { Gauge } from 'lucide-react';
import type { MomentumSnapshot } from '@/lib/api';

interface Props {
  momentum?: MomentumSnapshot;
  compact?: boolean;
}

// Map 0-100 score to a semantic band.
const band = (score: number): { label: string; cls: string } => {
  if (score >= 70)
    return {
      label: 'High',
      cls: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200',
    };
  if (score >= 40)
    return {
      label: 'Moderate',
      cls: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-200',
    };
  return {
    label: 'Quiet',
    cls: 'bg-muted text-muted-foreground border-border',
  };
};

/** Semicircular gauge + label for per-company momentum (#8). */
const MomentumGauge: React.FC<Props> = ({ momentum, compact }) => {
  if (!momentum) return null;
  const score = Math.max(0, Math.min(100, momentum.score || 0));
  const { label, cls } = band(score);
  const drivers = (momentum.top_drivers || []).slice(0, 3).join(' · ');

  // Visual bar for the score.
  const pct = score / 100;

  return (
    <div
      className={`inline-flex items-center gap-2 rounded border px-2 py-1 text-xs ${cls}`}
      title={`Momentum ${score.toFixed(0)}/100 (${label})${
        drivers ? ` — drivers: ${drivers}` : ''
      }`}
    >
      <Gauge className="h-3.5 w-3.5" />
      <span className="font-medium">{score.toFixed(0)}</span>
      {!compact && (
        <>
          <span className="text-[11px] uppercase tracking-wide">
            {label}
          </span>
          <span
            className="h-1 w-14 overflow-hidden rounded-full bg-background/60"
            aria-hidden
          >
            <span
              className="block h-full bg-current"
              style={{ width: `${pct * 100}%` }}
            />
          </span>
        </>
      )}
    </div>
  );
};

export default MomentumGauge;
