import React from 'react';
import type { OverlapCell } from '@/lib/api';

interface Props {
  cells?: OverlapCell[];
  technologies?: string[];
}

/**
 * Heatmap showing how many analyzed companies are active in both
 * technology A and technology B (#10).
 *
 * Cells are click-free; hover shows the list of overlap companies.
 */
const CompetitiveOverlapMatrix: React.FC<Props> = ({ cells, technologies }) => {
  if (!cells || cells.length === 0) return null;

  // Derive axis order if not supplied.
  const axis =
    technologies && technologies.length
      ? technologies
      : Array.from(new Set(cells.map((c) => c.technology_a))).sort();

  // Build lookup { "tA|tB": cell }.
  const byKey = new Map<string, OverlapCell>();
  let max = 0;
  for (const c of cells) {
    byKey.set(`${c.technology_a}|${c.technology_b}`, c);
    if (c.overlap_count > max) max = c.overlap_count;
  }
  if (max === 0) return null;

  const cellColor = (count: number): string => {
    if (count <= 0) return 'bg-muted/40';
    const ratio = count / max;
    if (ratio >= 0.75) return 'bg-emerald-500/70 text-white';
    if (ratio >= 0.5) return 'bg-emerald-400/60 text-white';
    if (ratio >= 0.25) return 'bg-amber-400/60';
    return 'bg-amber-300/40';
  };

  return (
    <div className="overflow-x-auto rounded border border-border bg-card/50">
      <div className="min-w-max p-3">
        <div className="mb-2 text-sm font-semibold">
          Competitive overlap — companies active in both technologies
        </div>
        <table className="border-collapse text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-card/50 px-2 py-1 text-right text-muted-foreground">
                &nbsp;
              </th>
              {axis.map((t) => (
                <th
                  key={t}
                  className="whitespace-nowrap px-2 py-1 font-medium text-muted-foreground"
                  style={{ minWidth: 72 }}
                  title={t}
                >
                  <div className="truncate" style={{ maxWidth: 96 }}>
                    {t}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {axis.map((a) => (
              <tr key={a}>
                <td
                  className="sticky left-0 z-10 bg-card/50 px-2 py-1 text-right font-medium text-muted-foreground"
                  title={a}
                >
                  <div className="truncate" style={{ maxWidth: 160 }}>
                    {a}
                  </div>
                </td>
                {axis.map((b) => {
                  if (a === b) {
                    return (
                      <td
                        key={`${a}|${b}`}
                        className="border border-border bg-muted/20 text-center text-[10px] text-muted-foreground"
                      >
                        —
                      </td>
                    );
                  }
                  const cell = byKey.get(`${a}|${b}`);
                  const count = cell?.overlap_count ?? 0;
                  const tip = cell
                    ? `${count} company/companies active in both: ${
                        cell.overlap_companies.join(', ') || '—'
                      }`
                    : '';
                  return (
                    <td
                      key={`${a}|${b}`}
                      title={tip}
                      className={`border border-border text-center font-medium ${cellColor(
                        count,
                      )}`}
                      style={{ minWidth: 56, height: 32 }}
                    >
                      {count || ''}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default CompetitiveOverlapMatrix;
