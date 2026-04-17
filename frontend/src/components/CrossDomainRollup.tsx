import React from 'react';
import { BarChart3 } from 'lucide-react';
import type { DomainRollupEntry } from '@/lib/api';

interface Props {
  rollup?: DomainRollupEntry[];
}

/** Stacked horizontal bars showing update distribution by domain (#29). */
const CrossDomainRollup: React.FC<Props> = ({ rollup }) => {
  if (!rollup || rollup.length === 0) return null;
  const total = rollup.reduce((sum, d) => sum + (d.update_count || 0), 0);
  if (total === 0) return null;

  const sorted = [...rollup].sort(
    (a, b) => (b.update_count || 0) - (a.update_count || 0),
  );

  return (
    <div className="rounded border border-border bg-card/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <BarChart3 className="h-4 w-4 text-indigo-500" />
        Domain rollup
      </div>
      <div className="space-y-1.5">
        {sorted.map((d) => {
          const pct = (d.update_count / total) * 100;
          return (
            <div key={d.domain} className="text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium">{d.domain}</span>
                <span className="text-muted-foreground">
                  {d.update_count} upd · {d.company_count} co.
                </span>
              </div>
              <div className="mt-0.5 h-2 overflow-hidden rounded bg-muted/40">
                <span
                  className="block h-full bg-indigo-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default CrossDomainRollup;
