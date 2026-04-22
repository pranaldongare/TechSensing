import React, { useState, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Cpu, RefreshCw, ExternalLink, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import type { ModelRelease } from '@/lib/api';

interface ModelReleasesViewProps {
  /** If provided, show these releases initially (from report) */
  initialReleases?: ModelRelease[];
}

const ModelReleasesView: React.FC<ModelReleasesViewProps> = ({ initialReleases }) => {
  const [releases, setReleases] = useState<ModelRelease[]>(initialReleases || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lookbackDays, setLookbackDays] = useState('30');
  const [lastFetched, setLastFetched] = useState<string | null>(
    initialReleases?.length ? 'from report' : null
  );

  const fetchReleases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.sensingModelReleases(parseInt(lookbackDays));
      setReleases(result.model_releases);
      setLastFetched(new Date().toLocaleTimeString());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch model releases');
    } finally {
      setLoading(false);
    }
  }, [lookbackDays]);

  const aaReleases = useMemo(
    () => releases.filter((r) => r.data_source === 'Artificial Analysis'),
    [releases]
  );
  const hfReleases = useMemo(
    () => releases.filter((r) => r.data_source !== 'Artificial Analysis'),
    [releases]
  );

  return (
    <div className="space-y-6 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5 text-purple-600" />
          <h2 className="text-lg font-semibold">Latest Model Releases</h2>
          {releases.length > 0 && (
            <Badge variant="secondary" className="text-xs">{releases.length}</Badge>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Lookback:</span>
            <Select value={lookbackDays} onValueChange={setLookbackDays}>
              <SelectTrigger className="w-24 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">7 days</SelectItem>
                <SelectItem value="14">14 days</SelectItem>
                <SelectItem value="30">30 days</SelectItem>
                <SelectItem value="60">60 days</SelectItem>
                <SelectItem value="90">90 days</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            size="sm"
            onClick={fetchReleases}
            disabled={loading}
            className="gap-1.5"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            {loading ? 'Fetching...' : 'Fetch Releases'}
          </Button>
        </div>
      </div>

      {lastFetched && (
        <p className="text-xs text-muted-foreground">
          Last updated: {lastFetched}
        </p>
      )}

      {error && (
        <Card className="border-destructive">
          <CardContent className="py-3 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!loading && releases.length === 0 && !error && (
        <Card>
          <CardContent className="py-12 text-center">
            <Cpu className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
            <p className="text-sm text-muted-foreground">
              Click "Fetch Releases" to get the latest model releases from Artificial Analysis and HuggingFace.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Artificial Analysis Table */}
      {aaReleases.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Artificial Analysis
            </h3>
            <Badge variant="secondary" className="text-xs">{aaReleases.length}</Badge>
          </div>
          <div className="overflow-x-auto border rounded-lg">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b bg-muted/30 text-left">
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Model</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Organization</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Date</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Status</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Modality</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Benchmarks & Pricing</th>
                </tr>
              </thead>
              <tbody>
                {aaReleases.map((mr, idx) => (
                  <tr key={idx} className="border-b last:border-b-0 hover:bg-muted/50 transition-colors">
                    <td className="py-2 px-3 font-medium">
                      <ModelLink name={mr.model_name} url={mr.source_url} />
                    </td>
                    <td className="py-2 px-3 text-muted-foreground">{mr.organization}</td>
                    <td className="py-2 px-3 text-muted-foreground whitespace-nowrap">{mr.release_date}</td>
                    <td className="py-2 px-3">
                      <StatusBadge status={mr.release_status} />
                    </td>
                    <td className="py-2 px-3">
                      {mr.modality && (
                        <Badge variant="secondary" className="text-xs">{mr.modality}</Badge>
                      )}
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground max-w-md">
                      {mr.notable_features}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* HuggingFace Table */}
      {hfReleases.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              HuggingFace
            </h3>
            <Badge variant="secondary" className="text-xs">{hfReleases.length}</Badge>
          </div>
          <div className="overflow-x-auto border rounded-lg">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b bg-muted/30 text-left">
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Model</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Organization</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Date</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Parameters</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Type</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Modality</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Open Source</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">License</th>
                  <th className="py-2.5 px-3 font-semibold text-xs text-muted-foreground">Notable Features</th>
                </tr>
              </thead>
              <tbody>
                {hfReleases.map((mr, idx) => (
                  <tr key={idx} className="border-b last:border-b-0 hover:bg-muted/50 transition-colors">
                    <td className="py-2 px-3 font-medium">
                      <ModelLink name={mr.model_name} url={mr.source_url} />
                    </td>
                    <td className="py-2 px-3 text-muted-foreground">{mr.organization}</td>
                    <td className="py-2 px-3 text-muted-foreground whitespace-nowrap">{mr.release_date}</td>
                    <td className="py-2 px-3">
                      {mr.parameters && (
                        <Badge variant="outline" className="text-xs font-mono">{mr.parameters}</Badge>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      {mr.model_type && (
                        <Badge variant="secondary" className="text-xs">{mr.model_type}</Badge>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      {mr.modality && (
                        <Badge variant="secondary" className="text-xs">{mr.modality}</Badge>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      <OpenSourceBadge value={mr.is_open_source} />
                    </td>
                    <td className="py-2 px-3">
                      {mr.license && (
                        <Badge variant="outline" className="text-xs">{mr.license}</Badge>
                      )}
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground max-w-xs">{mr.notable_features}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

function ModelLink({ name, url }: { name: string; url: string }) {
  if (!url) return <>{name}</>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-purple-700 dark:text-purple-300 hover:underline flex items-center gap-1"
    >
      {name}
      <ExternalLink className="w-3 h-3 shrink-0" />
    </a>
  );
}

function StatusBadge({ status }: { status: string }) {
  const st = (status || 'Unknown').trim();
  const cls =
    st === 'Released'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200 border-emerald-300'
      : st === 'Announced'
      ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200 border-sky-300'
      : st === 'Upcoming'
      ? 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200 border-violet-300'
      : st === 'Preview'
      ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 border-amber-300'
      : 'bg-muted text-muted-foreground';
  return <Badge variant="outline" className={`text-xs whitespace-nowrap ${cls}`}>{st}</Badge>;
}

function OpenSourceBadge({ value }: { value: string }) {
  const src = (value || 'Unknown').trim();
  const cls =
    src === 'Open'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200 border-emerald-300'
      : src === 'Closed'
      ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200 border-rose-300'
      : src === 'Mixed'
      ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 border-amber-300'
      : 'bg-muted text-muted-foreground';
  return <Badge variant="outline" className={`text-xs ${cls}`}>{src}</Badge>;
}

export default ModelReleasesView;
