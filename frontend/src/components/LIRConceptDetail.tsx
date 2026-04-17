import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ArrowLeft, ExternalLink, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import type { LIRConceptDetail as LIRConceptDetailType } from '@/lib/api';
import LIRScoreRadar from '@/components/LIRScoreRadar';

interface Props {
  conceptId: string;
  onBack: () => void;
}

const RING_COLORS: Record<string, string> = {
  adopt: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  trial: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
  assess: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  hold: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400',
  noise: 'bg-zinc-50 text-zinc-400 dark:bg-zinc-900 dark:text-zinc-500',
};

const TIER_LABELS: Record<string, string> = {
  T1: 'Academic',
  T2: 'Open Source',
  T3: 'Community',
  T4: 'Mainstream',
};

const LIRConceptDetail: React.FC<Props> = ({ conceptId, onBack }) => {
  const [detail, setDetail] = useState<LIRConceptDetailType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .lirConceptDetail(conceptId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conceptId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">
        Concept not found.
        <Button variant="ghost" size="sm" onClick={onBack} className="ml-2">
          Back
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0 mt-0.5">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-bold">{detail.canonical_name}</h2>
            <Badge className={RING_COLORS[detail.ring] || RING_COLORS.noise}>
              {detail.ring.toUpperCase()}
            </Badge>
            <span className="text-xs text-muted-foreground">
              Score: {(detail.composite_score * 100).toFixed(0)}%
            </span>
          </div>
          {detail.description && (
            <p className="text-sm text-muted-foreground mt-1">{detail.description}</p>
          )}
          <div className="flex flex-wrap gap-1 mt-2">
            {detail.domain_tags.map((tag) => (
              <Badge key={tag} variant="outline" className="text-[10px]">
                {tag}
              </Badge>
            ))}
            {detail.aliases.length > 0 && (
              <span className="text-[10px] text-muted-foreground ml-1">
                aka: {detail.aliases.join(', ')}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Scores radar + meta */}
      <div className="flex gap-4 items-start">
        <LIRScoreRadar scores={detail.scores} size={200} />
        <div className="space-y-2 text-xs">
          <div>
            <span className="text-muted-foreground">Signals:</span>{' '}
            <span className="font-medium">{detail.signal_count}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Source tiers:</span>{' '}
            {detail.source_tiers.map((t) => (
              <Badge key={t} variant="outline" className="text-[10px] ml-1">
                {TIER_LABELS[t] || t}
              </Badge>
            ))}
          </div>
          <div>
            <span className="text-muted-foreground">First seen:</span>{' '}
            <span>{detail.created_at ? new Date(detail.created_at).toLocaleDateString() : '—'}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Last updated:</span>{' '}
            <span>{detail.updated_at ? new Date(detail.updated_at).toLocaleDateString() : '—'}</span>
          </div>
          {/* Individual score bars */}
          <div className="space-y-1 pt-1">
            {(['convergence', 'velocity', 'novelty', 'authority', 'pattern_match'] as const).map(
              (key) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-20 text-muted-foreground capitalize text-[10px]">
                    {key === 'pattern_match' ? 'Pattern' : key}
                  </span>
                  <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all"
                      style={{ width: `${(detail.scores[key] || 0) * 100}%` }}
                    />
                  </div>
                  <span className="w-8 text-right">{((detail.scores[key] || 0) * 100).toFixed(0)}%</span>
                </div>
              ),
            )}
          </div>
        </div>
      </div>

      {/* Evidence list */}
      <div>
        <h3 className="text-sm font-semibold mb-2">
          Evidence ({detail.evidence.length} signals)
        </h3>
        <ScrollArea className="max-h-[400px]">
          <div className="space-y-2">
            {detail.evidence.map((ev) => (
              <div
                key={ev.signal_id}
                className="p-2.5 rounded-md border border-border bg-card/50 text-xs space-y-1"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[9px]">
                    {TIER_LABELS[ev.tier] || ev.tier}
                  </Badge>
                  <Badge variant="outline" className="text-[9px]">
                    {ev.source_id}
                  </Badge>
                  {ev.published_date && (
                    <span className="text-muted-foreground">
                      {new Date(ev.published_date).toLocaleDateString()}
                    </span>
                  )}
                  <span className="text-muted-foreground ml-auto">
                    novelty: {(ev.stated_novelty * 100).toFixed(0)}% | relevance:{' '}
                    {(ev.relevance_score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-foreground">{ev.summary}</p>
                {ev.evidence_quote && (
                  <p className="text-muted-foreground italic">"{ev.evidence_quote}"</p>
                )}
                {ev.url && (
                  <a
                    href={ev.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Source
                  </a>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
};

export default LIRConceptDetail;
