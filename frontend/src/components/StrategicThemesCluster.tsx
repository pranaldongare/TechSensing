import React from 'react';
import { Sparkles } from 'lucide-react';
import type { ThemeCluster } from '@/lib/api';

interface Props {
  themes?: ThemeCluster[];
}

/** Pill-cloud presentation of cross-company strategic themes (#11). */
const StrategicThemesCluster: React.FC<Props> = ({ themes }) => {
  if (!themes || themes.length === 0) return null;
  return (
    <div className="rounded border border-border bg-card/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="h-4 w-4 text-amber-500" />
        Strategic themes across analyzed companies
      </div>
      <div className="space-y-2">
        {themes.map((t, idx) => (
          <div
            key={idx}
            className="rounded border border-border/60 bg-background/50 p-2"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                {t.theme}
              </span>
              {t.companies.slice(0, 6).map((c) => (
                <span
                  key={c}
                  className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                >
                  {c}
                </span>
              ))}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {t.rationale}
            </div>
            {t.technologies.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {t.technologies.slice(0, 8).map((tech) => (
                  <span
                    key={tech}
                    className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default StrategicThemesCluster;
