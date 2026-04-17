import React, { useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink, Quote } from 'lucide-react';
import type { ClaimEvidence } from '@/lib/api';
import ConfidenceDot from '@/components/ConfidenceDot';

interface Props {
  /**
   * Per-claim evidence. Usually populated only when the source-evidence
   * feature is on (#25). When empty, the panel falls back to the raw
   * source URL list so old reports still render something useful.
   */
  evidence?: ClaimEvidence[];
  sourceUrls?: string[];
  defaultOpen?: boolean;
}

const hostname = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

const SourceEvidencePanel: React.FC<Props> = ({
  evidence,
  sourceUrls,
  defaultOpen = false,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  const hasEvidence = !!evidence && evidence.length > 0;
  const urls = hasEvidence
    ? []
    : (sourceUrls || []).filter(Boolean);
  if (!hasEvidence && urls.length === 0) return null;

  const count = hasEvidence ? evidence!.length : urls.length;

  return (
    <div className="mt-2 rounded border border-border bg-muted/30 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1 px-2 py-1 text-left text-muted-foreground hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <span>
          {hasEvidence ? 'Evidence' : 'Sources'} · {count}
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-border px-2 py-2">
          {hasEvidence
            ? evidence!.map((e, idx) => (
                <div
                  key={idx}
                  className="rounded border border-border/60 bg-background/60 p-2"
                >
                  <div className="flex items-start gap-2">
                    <Quote className="mt-0.5 h-3 w-3 flex-shrink-0 text-muted-foreground" />
                    <div className="flex-1">
                      <div className="text-foreground">{e.claim}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <ConfidenceDot
                          confidence={e.confidence}
                          size={8}
                          label
                        />
                        {e.is_single_source && (
                          <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                            single source
                          </span>
                        )}
                        {(e.source_urls || []).map((u, i) => (
                          <a
                            key={i}
                            href={u}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="inline-flex items-center gap-1 text-[11px] text-primary underline hover:text-primary/80"
                          >
                            {hostname(u)}
                            <ExternalLink className="h-2.5 w-2.5" />
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            : urls.map((u, idx) => (
                <a
                  key={idx}
                  href={u}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="flex items-center gap-1 text-primary underline hover:text-primary/80"
                >
                  {hostname(u)}
                  <ExternalLink className="h-2.5 w-2.5" />
                </a>
              ))}
        </div>
      )}
    </div>
  );
};

export default SourceEvidencePanel;
