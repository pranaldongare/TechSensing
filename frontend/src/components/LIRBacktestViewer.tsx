import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, Play, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '@/lib/api';
import type {
  LIRBacktestResult,
  LIRBacktestConceptResult,
  LIRBacktestSnapshot,
} from '@/lib/api';

const RING_COLORS: Record<string, string> = {
  adopt: 'bg-green-500',
  trial: 'bg-blue-500',
  assess: 'bg-amber-500',
  hold: 'bg-zinc-400',
  noise: 'bg-zinc-200 dark:bg-zinc-700',
};

const RING_BADGE_COLORS: Record<string, string> = {
  adopt: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  trial: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
  assess: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  hold: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400',
  noise: 'bg-zinc-50 text-zinc-400 dark:bg-zinc-900 dark:text-zinc-500',
};

// Simple inline sparkline (SVG)
const MiniTimeline: React.FC<{
  snapshots: LIRBacktestSnapshot[];
  width?: number;
  height?: number;
}> = ({ snapshots, width = 280, height = 50 }) => {
  if (!snapshots.length) return null;

  const maxComposite = Math.max(...snapshots.map((s) => s.composite), 0.01);
  const xStep = width / Math.max(snapshots.length - 1, 1);

  const points = snapshots.map((s, i) => ({
    x: i * xStep,
    y: height - (s.composite / maxComposite) * (height - 4) - 2,
    ring: s.ring,
  }));

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  // Ring threshold lines
  const thresholds = [
    { ring: 'assess', y: height - (0.5 / maxComposite) * (height - 4) - 2 },
    { ring: 'trial', y: height - (0.7 / maxComposite) * (height - 4) - 2 },
    { ring: 'adopt', y: height - (0.85 / maxComposite) * (height - 4) - 2 },
  ].filter((t) => t.y >= 0 && t.y <= height);

  return (
    <svg width={width} height={height} className="overflow-visible">
      {/* Threshold bands */}
      {thresholds.map((t) => (
        <line
          key={t.ring}
          x1={0}
          y1={t.y}
          x2={width}
          y2={t.y}
          stroke="currentColor"
          strokeWidth={0.5}
          strokeDasharray="4 4"
          className="text-muted-foreground/30"
        />
      ))}
      {/* Score line */}
      <path d={pathD} fill="none" stroke="hsl(var(--primary))" strokeWidth={1.5} />
      {/* Ring-colored dots */}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={2}
          className={`${RING_COLORS[p.ring] || 'fill-zinc-400'}`}
          style={{ fill: 'currentColor' }}
        />
      ))}
    </svg>
  );
};

interface ConceptRowProps {
  result: LIRBacktestConceptResult;
}

const ConceptRow: React.FC<ConceptRowProps> = ({ result }) => {
  const [expanded, setExpanded] = useState(false);
  const latest = result.snapshots[result.snapshots.length - 1];

  return (
    <div className="border border-border rounded-md overflow-hidden">
      <button
        className="w-full flex items-center gap-3 p-3 hover:bg-accent/50 transition-colors text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{result.canonical_name}</span>
            {latest && (
              <Badge className={`text-[9px] ${RING_BADGE_COLORS[latest.ring] || ''}`}>
                {latest.ring.toUpperCase()}
              </Badge>
            )}
          </div>
          <div className="flex gap-3 text-[10px] text-muted-foreground mt-0.5">
            {result.first_assess_week != null && (
              <span>Assess: week {result.first_assess_week}</span>
            )}
            {result.first_trial_week != null && (
              <span>Trial: week {result.first_trial_week}</span>
            )}
            {result.first_adopt_week != null && (
              <span>Adopt: week {result.first_adopt_week}</span>
            )}
          </div>
        </div>
        <MiniTimeline snapshots={result.snapshots} width={180} height={32} />
        {expanded ? (
          <ChevronUp className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        )}
      </button>
      {expanded && (
        <div className="border-t border-border p-3 bg-card/50">
          <MiniTimeline snapshots={result.snapshots} width={500} height={80} />
          <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
            {result.snapshots.map((s, i) => (
              <div
                key={i}
                className="flex items-center gap-1 text-muted-foreground"
              >
                <span className="font-mono">w{s.week_offset}</span>
                <Badge
                  className={`text-[8px] px-1 py-0 ${RING_BADGE_COLORS[s.ring] || ''}`}
                >
                  {s.ring}
                </Badge>
                <span>{(s.composite * 100).toFixed(0)}%</span>
                <span className="text-muted-foreground/50">({s.signal_count}sig)</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const LIRBacktestViewer: React.FC = () => {
  const [result, setResult] = useState<LIRBacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cleanup = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const { tracking_id } = await api.lirBacktestRun({ step_weeks: 4 });

      // Poll for completion
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.lirBacktestStatus(tracking_id);
          if (status.status === 'completed' && status.data) {
            cleanup();
            setResult(status.data);
            setLoading(false);
          } else if (status.status === 'failed') {
            cleanup();
            setError(status.error || 'Backtest failed');
            setLoading(false);
          }
        } catch {
          cleanup();
          setError('Failed to check backtest status');
          setLoading(false);
        }
      }, 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start backtest');
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Backtest Viewer</h3>
          <p className="text-[10px] text-muted-foreground">
            Replay historical data through the scoring engine to evaluate early detection.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={runBacktest}
          disabled={loading}
          className="text-xs"
        >
          {loading ? (
            <>
              <Loader2 className="w-3 h-3 mr-1 animate-spin" /> Running...
            </>
          ) : (
            <>
              <Play className="w-3 h-3 mr-1" /> Run Backtest
            </>
          )}
        </Button>
      </div>

      {error && (
        <div className="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 p-2 rounded-md">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-2">
          <div className="flex gap-3 text-[10px] text-muted-foreground">
            <span>
              {result.total_concepts} concepts | {result.start_date.split('T')[0]} →{' '}
              {result.end_date.split('T')[0]}
            </span>
            <span>{result.execution_time_seconds.toFixed(1)}s</span>
            <span>Weights: {Object.entries(result.weights_used).map(([k, v]) => `${k}=${v}`).join(', ')}</span>
          </div>

          <ScrollArea className="max-h-[500px]">
            <div className="space-y-1.5">
              {result.concept_results
                .filter((cr) => cr.snapshots.length > 0)
                .sort((a, b) => {
                  const aLast = a.snapshots[a.snapshots.length - 1]?.composite || 0;
                  const bLast = b.snapshots[b.snapshots.length - 1]?.composite || 0;
                  return bLast - aLast;
                })
                .map((cr) => (
                  <ConceptRow key={cr.concept_id} result={cr} />
                ))}
            </div>
          </ScrollArea>

          {result.errors.length > 0 && (
            <div className="text-[10px] text-muted-foreground">
              {result.errors.length} errors during backtest
            </div>
          )}
        </div>
      )}

      {!result && !loading && !error && (
        <div className="text-center text-sm text-muted-foreground py-8">
          Click "Run Backtest" to replay historical data and evaluate early detection performance.
        </div>
      )}
    </div>
  );
};

export default LIRBacktestViewer;
