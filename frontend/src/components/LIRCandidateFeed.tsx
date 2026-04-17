import React, { useEffect, useState, useCallback } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Loader2,
  RefreshCw,
  ExternalLink,
  TrendingUp,
  Zap,
  ChevronRight,
} from 'lucide-react';
import { api } from '@/lib/api';
import type { LIRCandidate, LIRSourceInfo } from '@/lib/api';
import { toast } from '@/components/ui/use-toast';
import LIRScoreRadar from '@/components/LIRScoreRadar';
import LIRConceptDetail from '@/components/LIRConceptDetail';

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

/** Tiny inline sparkline from weekly counts. */
const Sparkline: React.FC<{ data: number[]; width?: number; height?: number }> = ({
  data,
  width = 60,
  height = 18,
}) => {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 1);
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - (v / max) * height;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} className="inline-block ml-1">
      <polyline
        points={points}
        fill="none"
        stroke="hsl(var(--primary))"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
};

const LIRCandidateFeed: React.FC = () => {
  const [candidates, setCandidates] = useState<LIRCandidate[]>([]);
  const [sources, setSources] = useState<LIRSourceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pollId, setPollId] = useState<string | null>(null);
  const [ringFilter, setRingFilter] = useState<string>('all');
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);

  const loadCandidates = useCallback(async () => {
    try {
      const params: { ring?: string } = {};
      if (ringFilter !== 'all') params.ring = ringFilter;
      const res = await api.lirCandidates(params);
      setCandidates(res.candidates);
    } catch {
      // Silently fail on initial load — data may not exist yet
    }
  }, [ringFilter]);

  const loadSources = useCallback(async () => {
    try {
      const res = await api.lirSources();
      setSources(res.sources);
    } catch {}
  }, []);

  useEffect(() => {
    Promise.all([loadCandidates(), loadSources()]).finally(() => setLoading(false));
  }, [loadCandidates, loadSources]);

  // Polling for refresh
  useEffect(() => {
    if (!pollId) return;
    let count = 0;
    const interval = window.setInterval(async () => {
      count += 1;
      if (count > 180) {
        window.clearInterval(interval);
        setRefreshing(false);
        setPollId(null);
        toast({ title: 'LIR refresh timed out', variant: 'destructive' });
        return;
      }
      try {
        const res = await api.lirStatus(pollId);
        if (res.status === 'completed') {
          window.clearInterval(interval);
          setRefreshing(false);
          setPollId(null);
          if (res.data) {
            setCandidates(res.data.candidates);
            toast({
              title: 'LIR refresh complete',
              description: `${res.data.meta.total_signals_extracted} signals from ${res.data.meta.total_items_ingested} items. ${res.data.meta.new_concepts} new concepts.`,
            });
          } else {
            await loadCandidates();
          }
        } else if (res.status === 'failed') {
          window.clearInterval(interval);
          setRefreshing(false);
          setPollId(null);
          toast({
            title: 'LIR refresh failed',
            description: res.error || 'Unknown error',
            variant: 'destructive',
          });
        }
      } catch {
        // transient — keep polling
      }
    }, 5_000);
    return () => window.clearInterval(interval);
  }, [pollId, loadCandidates]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const res = await api.lirRefresh();
      setPollId(res.tracking_id);
      toast({ title: 'LIR pipeline started', description: 'Scanning sources for emerging signals...' });
    } catch (err) {
      setRefreshing(false);
      toast({
        title: 'Failed to start LIR refresh',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  // Concept detail view
  if (selectedConcept) {
    return (
      <LIRConceptDetail
        conceptId={selectedConcept}
        onBack={() => setSelectedConcept(null)}
      />
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500" />
            Leading Indicators
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Forward-looking signals from {sources.length} sources across{' '}
            {new Set(sources.map((s) => s.tier)).size} tiers
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={ringFilter} onValueChange={setRingFilter}>
            <SelectTrigger className="w-[120px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All rings</SelectItem>
              <SelectItem value="adopt">Adopt</SelectItem>
              <SelectItem value="trial">Trial</SelectItem>
              <SelectItem value="assess">Assess</SelectItem>
              <SelectItem value="hold">Hold</SelectItem>
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5 mr-1" />
            )}
            {refreshing ? 'Scanning...' : 'Refresh'}
          </Button>
        </div>
      </div>

      {/* Empty state */}
      {candidates.length === 0 && !refreshing && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <TrendingUp className="w-10 h-10 text-muted-foreground mb-3" />
            <p className="text-sm font-medium">No leading indicators yet</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              Click "Refresh" to scan academic papers, open-source repos, community
              discussions, and vendor announcements for emerging technology signals.
            </p>
            <Button size="sm" className="mt-4" onClick={handleRefresh} disabled={refreshing}>
              {refreshing ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
              Run First Scan
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Refreshing overlay */}
      {refreshing && candidates.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary mb-3" />
            <p className="text-sm font-medium">Scanning sources...</p>
            <p className="text-xs text-muted-foreground mt-1">
              This may take a few minutes. Polling {sources.length} adapters.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Candidate list */}
      {candidates.length > 0 && (
        <ScrollArea className="max-h-[calc(100vh-280px)]">
          <div className="space-y-2 pr-2">
            {candidates.map((c) => (
              <Card
                key={c.concept_id}
                className="cursor-pointer hover:border-primary/40 transition-colors"
                onClick={() => setSelectedConcept(c.concept_id)}
              >
                <CardContent className="p-3">
                  <div className="flex items-start gap-3">
                    {/* Mini radar */}
                    <div className="shrink-0 hidden sm:block">
                      <LIRScoreRadar scores={c.scores} size={90} />
                    </div>

                    {/* Main content */}
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm truncate">
                          {c.canonical_name}
                        </span>
                        <Badge
                          className={`text-[10px] ${RING_COLORS[c.ring] || RING_COLORS.noise}`}
                        >
                          {c.ring.toUpperCase()}
                        </Badge>
                        <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                          {(c.composite_score * 100).toFixed(0)}%
                        </span>
                        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                      </div>

                      {c.description && (
                        <p className="text-xs text-muted-foreground line-clamp-1">
                          {c.description}
                        </p>
                      )}

                      <div className="flex items-center gap-3 text-[10px] text-muted-foreground flex-wrap">
                        <span>{c.signal_count} signals</span>
                        <span>
                          {c.source_tiers.map((t) => TIER_LABELS[t] || t).join(', ')}
                        </span>
                        {c.domain_tags.length > 0 && (
                          <span>{c.domain_tags.slice(0, 3).join(', ')}</span>
                        )}
                        {c.velocity_trend && c.velocity_trend.length > 1 && (
                          <Sparkline data={c.velocity_trend} />
                        )}
                      </div>

                      {/* Top evidence */}
                      {c.top_evidence.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-0.5">
                          {c.top_evidence.slice(0, 2).map((ev, i) => (
                            <a
                              key={i}
                              href={ev.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-0.5 text-[10px] text-primary hover:underline max-w-[200px] truncate"
                            >
                              <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                              {ev.title || ev.source}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};

export default LIRCandidateFeed;
