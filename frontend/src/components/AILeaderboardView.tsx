import React, { useState, useCallback, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart3, RefreshCw, ExternalLink, Loader2, ArrowUpDown, Download } from 'lucide-react';
import { api } from '@/lib/api';
import type { AILeaderboardData, LeaderboardLLMEntry, LeaderboardMediaEntry } from '@/lib/api';

function downloadCsv(filename: string, rows: Record<string, unknown>[], columns: string[]) {
  const header = columns.join(',');
  const lines = rows.map((r) =>
    columns.map((c) => {
      const v = String(r[c] ?? '').replace(/"/g, '""');
      return `"${v}"`;
    }).join(',')
  );
  const blob = new Blob([header + '\n' + lines.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const LLM_COLS = ['rank', 'model_name', 'organization', 'slug', 'intelligence_index', 'mmlu_pro', 'gpqa',
  'speed', 'tokens_per_second', 'price'];
const MEDIA_COLS = ['rank', 'model_name', 'organization', 'slug', 'elo', 'release_date'];

const AILeaderboardView: React.FC = () => {
  const [data, setData] = useState<AILeaderboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState('llm_quality');

  const fetchLeaderboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.sensingAILeaderboard();
      setData(result.categories);
      setLastFetched(new Date().toLocaleTimeString());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch leaderboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeaderboard();
  }, [fetchLeaderboard]);

  const handleExportCsv = useCallback(() => {
    if (!data) return;
    const isMedia = ['image_generation', 'video_generation', 'speech'].includes(activeCategory);
    const cols = isMedia ? MEDIA_COLS : LLM_COLS;
    const rows = data[activeCategory as keyof typeof data] as Record<string, unknown>[];
    if (!rows?.length) return;
    downloadCsv(`ai-leaderboard-${activeCategory}-${new Date().toISOString().slice(0, 10)}.csv`, rows, cols);
  }, [data, activeCategory]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-blue-600" />
          <h2 className="text-lg font-semibold">AI Model Rankings</h2>
        </div>
        <div className="flex items-center gap-3">
          {lastFetched && (
            <span className="text-xs text-muted-foreground">Updated: {lastFetched}</span>
          )}
          <Button size="sm" onClick={fetchLeaderboard} disabled={loading} className="gap-1.5">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            {loading ? 'Loading...' : 'Refresh'}
          </Button>
          {data && (
            <Button size="sm" variant="outline" onClick={handleExportCsv} className="gap-1.5">
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </Button>
          )}
        </div>
      </div>

      {error && (
        <Card className="border-destructive">
          <CardContent className="py-3 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {!loading && !data && !error && (
        <Card>
          <CardContent className="py-12 text-center">
            <BarChart3 className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
            <p className="text-sm text-muted-foreground">Loading AI leaderboard data...</p>
          </CardContent>
        </Card>
      )}

      {data && (
        <Tabs value={activeCategory} onValueChange={setActiveCategory}>
          <TabsList className="flex-wrap h-auto gap-1 p-1">
            <TabsTrigger value="llm_quality">
              LLM Quality
              <Badge variant="secondary" className="ml-1.5 text-xs">{data.llm_quality.length}</Badge>
            </TabsTrigger>
            <TabsTrigger value="llm_speed">
              LLM Speed
              <Badge variant="secondary" className="ml-1.5 text-xs">{data.llm_speed.length}</Badge>
            </TabsTrigger>
            <TabsTrigger value="llm_price">
              LLM Price
              <Badge variant="secondary" className="ml-1.5 text-xs">{data.llm_price.length}</Badge>
            </TabsTrigger>
            <TabsTrigger value="image_generation">
              Image
              <Badge variant="secondary" className="ml-1.5 text-xs">{data.image_generation.length}</Badge>
            </TabsTrigger>
            <TabsTrigger value="video_generation">
              Video
              <Badge variant="secondary" className="ml-1.5 text-xs">{data.video_generation.length}</Badge>
            </TabsTrigger>
            <TabsTrigger value="speech">
              Speech
              <Badge variant="secondary" className="ml-1.5 text-xs">{data.speech.length}</Badge>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="llm_quality">
            <LLMQualityTable entries={data.llm_quality} />
          </TabsContent>
          <TabsContent value="llm_speed">
            <LLMSpeedTable entries={data.llm_speed} />
          </TabsContent>
          <TabsContent value="llm_price">
            <LLMPriceTable entries={data.llm_price} />
          </TabsContent>
          <TabsContent value="image_generation">
            <MediaTable entries={data.image_generation} />
          </TabsContent>
          <TabsContent value="video_generation">
            <MediaTable entries={data.video_generation} />
          </TabsContent>
          <TabsContent value="speech">
            <MediaTable entries={data.speech} />
          </TabsContent>
        </Tabs>
      )}

      {/* Source attribution */}
      <p className="text-xs text-muted-foreground flex items-center gap-1">
        Data from{' '}
        <a href="https://artificialanalysis.ai" target="_blank" rel="noopener noreferrer"
           className="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-0.5">
          Artificial Analysis <ExternalLink className="w-3 h-3" />
        </a>
      </p>
    </div>
  );
};

/* ── Sorting hook ── */

type SortConfig<K extends string> = { key: K; dir: 'asc' | 'desc' };

function useSortable<T, K extends string>(
  data: T[],
  defaultKey: K,
  defaultDir: 'asc' | 'desc' = 'desc',
) {
  const [sort, setSort] = useState<SortConfig<K>>({ key: defaultKey, dir: defaultDir });

  const toggle = (key: K) =>
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' },
    );

  const sorted = [...data].sort((a, b) => {
    const av = (a as Record<string, unknown>)[sort.key];
    const bv = (b as Record<string, unknown>)[sort.key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return sort.dir === 'asc' ? cmp : -cmp;
  });

  return { sorted, sort, toggle };
}

function SortHeader({ label, sortKey, current, onToggle }: {
  label: string;
  sortKey: string;
  current: SortConfig<string>;
  onToggle: (key: string) => void;
}) {
  const active = current.key === sortKey;
  return (
    <th
      className="py-2.5 px-3 font-semibold text-xs text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors"
      onClick={() => onToggle(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${active ? 'text-foreground' : 'opacity-30'}`} />
      </span>
    </th>
  );
}

function ModelLink({ name, slug }: { name: string; slug: string }) {
  if (!slug) return <>{name}</>;
  return (
    <a
      href={`https://artificialanalysis.ai/models/${slug}`}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-700 dark:text-blue-300 hover:underline inline-flex items-center gap-1"
    >
      {name}
      <ExternalLink className="w-3 h-3 shrink-0" />
    </a>
  );
}

function fmtNum(v: number | null | undefined, decimals = 1): string {
  if (v == null) return '—';
  return Number(v).toFixed(decimals);
}

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return '—';
  return `$${Number(v).toFixed(2)}`;
}

/* ── LLM Quality Table ── */

function LLMQualityTable({ entries }: { entries: LeaderboardLLMEntry[] }) {
  const { sorted, sort, toggle } = useSortable(entries, 'rank', 'asc');
  const th = (label: string, key: string) => (
    <SortHeader label={label} sortKey={key} current={sort} onToggle={toggle} />
  );

  return (
    <div className="overflow-x-auto border rounded-lg mt-2">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b bg-muted/30 text-left">
            {th('#', 'rank')}
            {th('Model', 'model_name')}
            {th('Organization', 'organization')}
            {th('Intelligence Index', 'intelligence_index')}
            {th('MMLU Pro', 'mmlu_pro')}
            {th('GPQA', 'gpqa')}
            {th('Speed (tok/s)', 'speed')}
            {th('Price/1M', 'price')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((e, i) => (
            <tr key={i} className="border-b last:border-b-0 hover:bg-muted/50 transition-colors">
              <td className="py-2 px-3 text-muted-foreground font-mono text-xs">{e.rank}</td>
              <td className="py-2 px-3 font-medium"><ModelLink name={e.model_name} slug={e.slug} /></td>
              <td className="py-2 px-3 text-muted-foreground">{e.organization}</td>
              <td className="py-2 px-3 font-mono">{fmtNum(e.intelligence_index)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtNum(e.mmlu_pro)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtNum(e.gpqa)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtNum(e.speed, 0)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtPrice(e.price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── LLM Speed Table ── */

function LLMSpeedTable({ entries }: { entries: LeaderboardLLMEntry[] }) {
  const { sorted, sort, toggle } = useSortable(entries, 'rank', 'asc');
  const th = (label: string, key: string) => (
    <SortHeader label={label} sortKey={key} current={sort} onToggle={toggle} />
  );

  return (
    <div className="overflow-x-auto border rounded-lg mt-2">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b bg-muted/30 text-left">
            {th('#', 'rank')}
            {th('Model', 'model_name')}
            {th('Organization', 'organization')}
            {th('Tokens/sec', 'tokens_per_second')}
            {th('Intelligence Index', 'intelligence_index')}
            {th('Price/1M', 'price')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((e, i) => (
            <tr key={i} className="border-b last:border-b-0 hover:bg-muted/50 transition-colors">
              <td className="py-2 px-3 text-muted-foreground font-mono text-xs">{e.rank}</td>
              <td className="py-2 px-3 font-medium"><ModelLink name={e.model_name} slug={e.slug} /></td>
              <td className="py-2 px-3 text-muted-foreground">{e.organization}</td>
              <td className="py-2 px-3 font-mono">{fmtNum(e.tokens_per_second, 0)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtNum(e.intelligence_index)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtPrice(e.price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── LLM Price Table ── */

function LLMPriceTable({ entries }: { entries: LeaderboardLLMEntry[] }) {
  const { sorted, sort, toggle } = useSortable(entries, 'rank', 'asc');
  const th = (label: string, key: string) => (
    <SortHeader label={label} sortKey={key} current={sort} onToggle={toggle} />
  );

  return (
    <div className="overflow-x-auto border rounded-lg mt-2">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b bg-muted/30 text-left">
            {th('#', 'rank')}
            {th('Model', 'model_name')}
            {th('Organization', 'organization')}
            {th('Price/1M tokens', 'price')}
            {th('Intelligence Index', 'intelligence_index')}
            {th('Speed (tok/s)', 'speed')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((e, i) => (
            <tr key={i} className="border-b last:border-b-0 hover:bg-muted/50 transition-colors">
              <td className="py-2 px-3 text-muted-foreground font-mono text-xs">{e.rank}</td>
              <td className="py-2 px-3 font-medium"><ModelLink name={e.model_name} slug={e.slug} /></td>
              <td className="py-2 px-3 text-muted-foreground">{e.organization}</td>
              <td className="py-2 px-3 font-mono">{fmtPrice(e.price)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtNum(e.intelligence_index)}</td>
              <td className="py-2 px-3 font-mono text-muted-foreground">{fmtNum(e.speed, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Media Table (Image / Video / Speech) ── */

function MediaTable({ entries }: { entries: LeaderboardMediaEntry[] }) {
  const { sorted, sort, toggle } = useSortable(entries, 'rank', 'asc');
  const th = (label: string, key: string) => (
    <SortHeader label={label} sortKey={key} current={sort} onToggle={toggle} />
  );

  return (
    <div className="overflow-x-auto border rounded-lg mt-2">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b bg-muted/30 text-left">
            {th('#', 'rank')}
            {th('Model', 'model_name')}
            {th('Organization', 'organization')}
            {th('ELO', 'elo')}
            {th('Release', 'release_date')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((e, i) => (
            <tr key={i} className="border-b last:border-b-0 hover:bg-muted/50 transition-colors">
              <td className="py-2 px-3 text-muted-foreground font-mono text-xs">{e.rank}</td>
              <td className="py-2 px-3 font-medium"><ModelLink name={e.model_name} slug={e.slug} /></td>
              <td className="py-2 px-3 text-muted-foreground">{e.organization}</td>
              <td className="py-2 px-3 font-mono">{fmtNum(e.elo, 0)}</td>
              <td className="py-2 px-3 text-muted-foreground whitespace-nowrap">{e.release_date || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default AILeaderboardView;
