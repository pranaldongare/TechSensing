import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Briefcase, Loader2, Plus, X, History, Play, RotateCcw,
  Sparkles, Calendar, ExternalLink,
} from 'lucide-react';
import { api } from '@/lib/api';
import type {
  KeyCompaniesReport,
  KeyCompaniesHistoryItem,
  KeyCompanyBriefing,
  KeyCompanyUpdate,
} from '@/lib/api';
import { toast } from '@/components/ui/use-toast';
import SafeMarkdownRenderer from '@/components/SafeMarkdownRenderer';

const POLL_INTERVAL_MS = 4_000;
const MAX_POLL_COUNT = 300; // ~20 minutes
const MAX_COMPANIES = 12;
const MIN_PERIOD_DAYS = 1;
const MAX_PERIOD_DAYS = 30;

const categoryTone = (category: string): string => {
  switch ((category || '').toLowerCase()) {
    case 'product launch': return 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200';
    case 'funding': return 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-200';
    case 'acquisition': return 'bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-900/40 dark:text-orange-200';
    case 'partnership': return 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/40 dark:text-blue-200';
    case 'research': return 'bg-purple-100 text-purple-800 border-purple-300 dark:bg-purple-900/40 dark:text-purple-200';
    case 'technical': return 'bg-sky-100 text-sky-800 border-sky-300 dark:bg-sky-900/40 dark:text-sky-200';
    case 'regulatory': return 'bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-900/40 dark:text-rose-200';
    case 'people': return 'bg-indigo-100 text-indigo-800 border-indigo-300 dark:bg-indigo-900/40 dark:text-indigo-200';
    default: return 'bg-muted text-muted-foreground border-border';
  }
};

const KeyCompaniesView: React.FC = () => {
  const [companyInput, setCompanyInput] = useState('');
  const [companies, setCompanies] = useState<string[]>([]);
  const [highlightDomain, setHighlightDomain] = useState('');
  const [periodDays, setPeriodDays] = useState<number>(7);

  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  const [report, setReport] = useState<KeyCompaniesReport | null>(null);
  const [trackingId, setTrackingId] = useState<string | null>(null);

  const [history, setHistory] = useState<KeyCompaniesHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const pollRef = useRef<number | null>(null);
  const pollCountRef = useRef(0);

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollCountRef.current = 0;
  };

  useEffect(() => () => stopPolling(), []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await api.sensingKeyCompaniesHistory();
      setHistory(res.briefings || []);
    } catch (err) {
      // silent
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const startPolling = (tid: string) => {
    stopPolling();
    pollCountRef.current = 0;
    pollRef.current = window.setInterval(async () => {
      pollCountRef.current += 1;
      if (pollCountRef.current > MAX_POLL_COUNT) {
        stopPolling();
        setStatus('error');
        toast({
          title: 'Briefing timed out',
          description: 'Key Companies briefing took too long. Try fewer companies.',
          variant: 'destructive',
        });
        return;
      }
      try {
        const res = await api.sensingKeyCompaniesStatus(tid);
        if (res.status === 'completed' && res.data) {
          stopPolling();
          setReport(res.data.report);
          setStatus('complete');
          setProgress(100);
          setProgressMessage('Briefing complete');
          loadHistory();
        } else if (res.status === 'failed') {
          stopPolling();
          setStatus('error');
          toast({
            title: 'Briefing failed',
            description: res.error || 'Unknown error',
            variant: 'destructive',
          });
        } else {
          setProgress((p) => Math.min(p + 2, 90));
        }
      } catch {
        // transient — keep polling
      }
    }, POLL_INTERVAL_MS);
  };

  const addCompanyFromInput = () => {
    const raw = companyInput.trim();
    if (!raw) return;
    const parts = raw.split(',').map((s) => s.trim()).filter(Boolean);
    const next = Array.from(new Set([...companies, ...parts])).slice(0, MAX_COMPANIES);
    setCompanies(next);
    setCompanyInput('');
  };

  const removeCompany = (name: string) => {
    setCompanies((prev) => prev.filter((c) => c !== name));
  };

  const canStart = useMemo(
    () => companies.length > 0 && status !== 'running',
    [companies.length, status],
  );

  const handleStart = async () => {
    if (!canStart) return;
    try {
      setStatus('running');
      setProgress(5);
      setProgressMessage('Starting weekly briefing...');
      setReport(null);

      const res = await api.sensingKeyCompaniesStart({
        company_names: companies,
        highlight_domain: highlightDomain.trim(),
        period_days: periodDays,
      });
      setTrackingId(res.tracking_id);
      startPolling(res.tracking_id);
    } catch (err) {
      setStatus('error');
      toast({
        title: 'Failed to start',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const handleReset = () => {
    stopPolling();
    setStatus('idle');
    setReport(null);
    setTrackingId(null);
    setProgress(0);
    setProgressMessage('');
  };

  const handleLoadHistory = async (tid: string) => {
    try {
      const data = await api.sensingKeyCompaniesLoad(tid);
      setReport(data.report);
      setCompanies(data.report.companies_analyzed || []);
      setHighlightDomain(data.report.highlight_domain || '');
      setPeriodDays(data.report.period_days || 7);
      setStatus('complete');
      setProgress(100);
      setTrackingId(tid);
    } catch (err) {
      toast({
        title: 'Failed to load',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  // ---- RENDER ----

  const showInputMode = status === 'idle' && !report;
  const showRunning = status === 'running';
  const showResults = status === 'complete' && !!report;

  return (
    <div className="flex flex-col gap-4 min-h-0">
      {showInputMode && (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-4">
          {/* --- Input panel --- */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Briefcase className="w-4 h-4 text-primary" />
                Weekly Briefing Setup
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Companies to track
                  <span className="text-xs text-muted-foreground font-normal ml-2">
                    (up to {MAX_COMPANIES}; comma-separated accepted)
                  </span>
                </label>
                <div className="flex gap-2">
                  <Input
                    value={companyInput}
                    onChange={(e) => setCompanyInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addCompanyFromInput();
                      }
                    }}
                    placeholder="e.g. Google, OpenAI, Anthropic, IBM"
                    disabled={companies.length >= MAX_COMPANIES}
                  />
                  <Button
                    type="button"
                    onClick={addCompanyFromInput}
                    disabled={!companyInput.trim() || companies.length >= MAX_COMPANIES}
                    variant="secondary"
                  >
                    <Plus className="w-4 h-4" /> Add
                  </Button>
                </div>
                {companies.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {companies.map((c) => (
                      <Badge
                        key={c}
                        variant="secondary"
                        className="gap-1 pl-2 pr-1 py-1 text-xs"
                      >
                        {c}
                        <button
                          type="button"
                          onClick={() => removeCompany(c)}
                          className="ml-1 p-0.5 rounded-sm hover:bg-foreground/10"
                          aria-label={`Remove ${c}`}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Highlight domain
                  <span className="text-xs text-muted-foreground font-normal ml-2">
                    (optional — leave blank for cross-domain)
                  </span>
                </label>
                <Input
                  value={highlightDomain}
                  onChange={(e) => setHighlightDomain(e.target.value)}
                  placeholder="e.g. Generative AI, Quantum Computing, Cybersecurity"
                />
                <p className="text-xs text-muted-foreground">
                  We always cover cross-domain activity; a highlight domain
                  just biases the search toward that area.
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Lookback window
                </label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={MIN_PERIOD_DAYS}
                    max={MAX_PERIOD_DAYS}
                    value={periodDays}
                    onChange={(e) => {
                      const n = parseInt(e.target.value, 10);
                      if (!Number.isFinite(n)) return;
                      setPeriodDays(Math.max(MIN_PERIOD_DAYS, Math.min(MAX_PERIOD_DAYS, n)));
                    }}
                    className="w-24"
                  />
                  <span className="text-sm text-muted-foreground">days (default 7)</span>
                </div>
              </div>

              <div className="pt-2">
                <Button
                  type="button"
                  onClick={handleStart}
                  disabled={!canStart}
                  className="w-full"
                >
                  <Play className="w-4 h-4 mr-2" />
                  Run Weekly Briefing
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* --- History panel --- */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <History className="w-4 h-4 text-primary" />
                Previous Briefings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {historyLoading && (
                <div className="text-xs text-muted-foreground flex items-center gap-2">
                  <Loader2 className="w-3 h-3 animate-spin" /> Loading...
                </div>
              )}
              {!historyLoading && history.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No previous briefings yet.
                </p>
              )}
              {!historyLoading && history.length > 0 && (
                <div className="max-h-96 overflow-y-auto space-y-2 pr-1">
                  {history.map((h) => (
                    <button
                      key={h.tracking_id}
                      type="button"
                      onClick={() => handleLoadHistory(h.tracking_id)}
                      className="w-full text-left border rounded-md p-2 hover:bg-muted transition-colors"
                    >
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Calendar className="w-3 h-3" />
                        {h.period_start || '?'} → {h.period_end || '?'}
                      </div>
                      <div className="text-sm font-medium truncate">
                        {(h.companies || []).slice(0, 4).join(', ') || '(no companies)'}
                        {h.companies.length > 4 && ` +${h.companies.length - 4}`}
                      </div>
                      {h.highlight_domain && (
                        <Badge variant="outline" className="text-[10px] mt-1">
                          {h.highlight_domain}
                        </Badge>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {showRunning && (
        <Card>
          <CardContent className="py-10 flex flex-col items-center gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <div className="text-center space-y-2 max-w-md">
              <p className="font-medium">Researching {companies.length} companies...</p>
              <p className="text-sm text-muted-foreground">
                {progressMessage || 'Running searches and synthesis.'}
              </p>
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-muted-foreground">{progress}%</p>
            </div>
          </CardContent>
        </Card>
      )}

      {showResults && report && (
        <div className="space-y-4">
          {/* Header row with metadata + reset */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="outline" className="gap-1">
                <Calendar className="w-3 h-3" />
                {report.period_start} → {report.period_end}
              </Badge>
              <Badge variant="outline">
                {report.companies_analyzed.length} companies
              </Badge>
              {report.highlight_domain && (
                <Badge variant="outline">
                  Highlight: {report.highlight_domain}
                </Badge>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={handleReset}>
              <RotateCcw className="w-4 h-4 mr-1.5" />
              New Briefing
            </Button>
          </div>

          {/* Cross-company summary */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" />
                This Week Across All Companies
              </CardTitle>
            </CardHeader>
            <CardContent>
              {report.cross_company_summary ? (
                <SafeMarkdownRenderer content={report.cross_company_summary} />
              ) : (
                <p className="text-sm text-muted-foreground">
                  No cross-company summary generated.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Per-company briefings */}
          <div className="space-y-3">
            {report.briefings.map((b) => (
              <BriefingCard key={b.company} briefing={b} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const BriefingCard: React.FC<{ briefing: KeyCompanyBriefing }> = ({ briefing }) => {
  const hasUpdates = briefing.updates && briefing.updates.length > 0;
  return (
    <Card className="overflow-hidden border-l-4 border-l-primary/70">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <CardTitle className="text-base flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-primary" />
              {briefing.company}
            </CardTitle>
            {briefing.domains_active && briefing.domains_active.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {briefing.domains_active.map((d) => (
                  <Badge
                    key={d}
                    variant="outline"
                    className="text-[10px] py-0"
                  >
                    {d}
                  </Badge>
                ))}
              </div>
            )}
          </div>
          <Badge variant="secondary" className="text-xs shrink-0">
            {briefing.updates.length} updates · {briefing.sources_used} sources
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {briefing.overall_summary && (
          <SafeMarkdownRenderer content={briefing.overall_summary} />
        )}
        {briefing.key_themes && briefing.key_themes.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {briefing.key_themes.map((t, i) => (
              <Badge
                key={i}
                variant="outline"
                className="text-[11px] bg-muted/40"
              >
                {t}
              </Badge>
            ))}
          </div>
        )}
        {hasUpdates && (
          <Accordion type="single" collapsible className="w-full">
            <AccordionItem value="updates">
              <AccordionTrigger className="text-sm">
                View {briefing.updates.length} updates
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-2">
                  {briefing.updates.map((u, idx) => (
                    <UpdateRow key={idx} update={u} />
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
      </CardContent>
    </Card>
  );
};

const UpdateRow: React.FC<{ update: KeyCompanyUpdate }> = ({ update }) => {
  return (
    <div className="border rounded-md p-3 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" className={`${categoryTone(update.category)} text-[10px]`}>
          {update.category || 'Other'}
        </Badge>
        {update.date && (
          <span className="text-muted-foreground flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            {update.date}
          </span>
        )}
        {update.domain && (
          <Badge variant="outline" className="text-[10px]">
            {update.domain}
          </Badge>
        )}
      </div>
      <div className="font-medium text-sm leading-snug">
        {update.source_url ? (
          <a
            href={update.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline inline-flex items-center gap-1"
          >
            {update.headline}
            <ExternalLink className="w-3 h-3" />
          </a>
        ) : (
          update.headline
        )}
      </div>
      {update.summary && (
        <div className="text-xs text-muted-foreground leading-relaxed">
          <SafeMarkdownRenderer content={update.summary} />
        </div>
      )}
    </div>
  );
};

export default KeyCompaniesView;
