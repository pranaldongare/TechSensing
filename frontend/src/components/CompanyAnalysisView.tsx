import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Building2, Loader2, Plus, X, History, Play, RotateCcw,
  Download, FileText, ChevronDown, ChevronRight, Sparkles,
  FileSpreadsheet, Presentation,
} from 'lucide-react';
import { api } from '@/lib/api';
import type {
  CompanyAnalysisReport,
  CompanyAnalysisHistoryItem,
} from '@/lib/api';
import { toast } from '@/components/ui/use-toast';
import { downloadCompanyAnalysisPdf } from '@/lib/sensing-report-pdf';
import { downloadCompanyAnalysisPptx } from '@/lib/sensing-report-pptx';
import {
  downloadCompanyAnalysisCsv,
  downloadCompanyAnalysisXls,
} from '@/lib/sensing-report-csv';
import { downloadCompanyAnalysisMarkdown } from '@/lib/sensing-report-md';
import { FileCode, Globe } from 'lucide-react';
import ContradictionAlert from '@/components/ContradictionAlert';
import HallucinationFlag from '@/components/HallucinationFlag';
import OpportunityThreatPanel from '@/components/OpportunityThreatPanel';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import ConfidenceDot from '@/components/ConfidenceDot';
import SourceEvidencePanel from '@/components/SourceEvidencePanel';
import CostTelemetryBadge from '@/components/CostTelemetryBadge';
import CompetitiveOverlapMatrix from '@/components/CompetitiveOverlapMatrix';
import StrategicThemesCluster from '@/components/StrategicThemesCluster';
import InvestmentSignalChart from '@/components/InvestmentSignalChart';
import CompanyTimelineView from '@/components/CompanyTimelineView';

interface RadarItemLite {
  name: string;
  quadrant?: string;
  ring?: string;
  signal_strength?: number;
}

interface CompanyAnalysisViewProps {
  reportTrackingId?: string;
  domain?: string;
  radarItems?: RadarItemLite[];
  /** Standalone mode: user inputs both companies and technology areas
   *  manually (no parent report). Defaults to true when reportTrackingId
   *  is not provided. */
  standalone?: boolean;
}

const POLL_INTERVAL_MS = 4_000;
const MAX_POLL_COUNT = 300; // ~20 minutes
const MAX_TECHS = 8;
const MAX_COMPANIES = 10;

const ringTone = (ring?: string): string => {
  switch ((ring || '').toLowerCase()) {
    case 'adopt': return 'bg-green-100 text-green-800 border-green-200';
    case 'trial': return 'bg-blue-100 text-blue-800 border-blue-200';
    case 'assess': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'hold': return 'bg-red-100 text-red-800 border-red-200';
    default: return 'bg-muted text-foreground border-border';
  }
};

const stanceTone = (stance: string): string => {
  const s = stance.toLowerCase();
  if (s.includes('heavily') || s.includes('leader')) return 'bg-green-100 text-green-800 border-green-200';
  if (s.includes('invest') || s.includes('building')) return 'bg-blue-100 text-blue-800 border-blue-200';
  if (s.includes('exploring') || s.includes('early')) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
  if (s.includes('no visible') || s.includes('absent')) return 'bg-muted text-muted-foreground border-border';
  if (s.includes('defensive') || s.includes('cautious')) return 'bg-orange-100 text-orange-800 border-orange-200';
  return 'bg-muted text-foreground border-border';
};

const confidencePct = (c: number): string => `${Math.round((c || 0) * 100)}%`;

const CompanyAnalysisView: React.FC<CompanyAnalysisViewProps> = ({
  reportTrackingId,
  domain,
  radarItems = [],
  standalone,
}) => {
  const isStandalone = standalone ?? !reportTrackingId;

  const [companyInput, setCompanyInput] = useState('');
  const [companies, setCompanies] = useState<string[]>([]);
  // In standalone mode there are no radar items, so initial selection is empty
  const [selectedTechs, setSelectedTechs] = useState<string[]>(() =>
    isStandalone ? [] : radarItems.slice(0, MAX_TECHS).map((r) => r.name),
  );
  const [customTechs, setCustomTechs] = useState<string[]>([]);
  const [customTechInput, setCustomTechInput] = useState('');
  const [showTechs, setShowTechs] = useState(true);

  // Standalone-only: editable domain
  const [domainInput, setDomainInput] = useState(domain || '');

  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  const [trackingId, setTrackingId] = useState<string | null>(null);

  const [report, setReport] = useState<CompanyAnalysisReport | null>(null);
  const [history, setHistory] = useState<CompanyAnalysisHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const pollRef = useRef<number | null>(null);
  const pollCountRef = useRef(0);

  // Reset state when radarItems / parent report changes
  useEffect(() => {
    if (!isStandalone) {
      setSelectedTechs(radarItems.slice(0, MAX_TECHS).map((r) => r.name));
    }
  }, [radarItems, isStandalone]);

  useEffect(() => {
    setDomainInput(domain || '');
  }, [domain]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      // In report-linked mode, filter by the parent id; otherwise list all
      const res = await api.sensingCompanyAnalysisHistory(
        isStandalone ? undefined : reportTrackingId,
      );
      const items = res.analyses || [];
      // In standalone mode, only show standalone (no parent) analyses
      const filtered = isStandalone
        ? items.filter((a) => !a.report_tracking_id)
        : items;
      setHistory(filtered);
    } catch {
      // Silent failure — history is nice-to-have
    } finally {
      setHistoryLoading(false);
    }
  }, [reportTrackingId, isStandalone]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollCountRef.current = 0;
  };

  useEffect(() => () => stopPolling(), []);

  const startPolling = (tid: string) => {
    stopPolling();
    pollCountRef.current = 0;
    pollRef.current = window.setInterval(async () => {
      pollCountRef.current += 1;
      if (pollCountRef.current > MAX_POLL_COUNT) {
        stopPolling();
        setStatus('error');
        toast({
          title: 'Analysis timed out',
          description: 'Company analysis took too long. Please try with fewer companies or technologies.',
          variant: 'destructive',
        });
        return;
      }
      try {
        const res = await api.sensingCompanyAnalysisStatus(tid);
        if (res.status === 'completed' && res.data) {
          stopPolling();
          setReport(res.data.report);
          setStatus('complete');
          setProgress(100);
          setProgressMessage('Analysis complete');
          loadHistory();
        } else if (res.status === 'failed') {
          stopPolling();
          setStatus('error');
          toast({
            title: 'Analysis failed',
            description: res.error || 'Unknown error',
            variant: 'destructive',
          });
        } else {
          setProgress((p) => Math.min(p + 2, 90));
        }
      } catch {
        // Keep polling through transient errors
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

  const allSelectedTechs = useMemo(
    () => [...selectedTechs, ...customTechs],
    [selectedTechs, customTechs],
  );

  const toggleTech = (name: string) => {
    setSelectedTechs((prev) => {
      if (prev.includes(name)) return prev.filter((t) => t !== name);
      if (allSelectedTechs.length >= MAX_TECHS) return prev;
      return [...prev, name];
    });
  };

  const addCustomTech = () => {
    const raw = customTechInput.trim();
    if (!raw) return;
    if (allSelectedTechs.length >= MAX_TECHS) {
      toast({
        title: 'Max technologies reached',
        description: `Up to ${MAX_TECHS} technologies can be analyzed at a time.`,
      });
      return;
    }
    // Split comma-separated entries, dedup across both lists
    const parts = raw.split(',').map((s) => s.trim()).filter(Boolean);
    const lower = new Set(allSelectedTechs.map((t) => t.toLowerCase()));
    const fresh = parts.filter((p) => !lower.has(p.toLowerCase()));
    const remaining = MAX_TECHS - allSelectedTechs.length;
    setCustomTechs((prev) => [...prev, ...fresh.slice(0, remaining)]);
    setCustomTechInput('');
  };

  const removeCustomTech = (name: string) => {
    setCustomTechs((prev) => prev.filter((t) => t !== name));
  };

  const selectAllTechs = () => {
    const top = radarItems.slice(0, MAX_TECHS - customTechs.length).map((r) => r.name);
    setSelectedTechs(top);
  };
  const clearTechs = () => {
    setSelectedTechs([]);
    setCustomTechs([]);
  };

  const handleRun = async () => {
    const finalCompanies = companies.length > 0
      ? companies
      : companyInput.trim().split(',').map((s) => s.trim()).filter(Boolean);

    if (finalCompanies.length === 0) {
      toast({ title: 'Add at least one company', description: 'Enter company names to analyze.', variant: 'destructive' });
      return;
    }

    const finalTechs = allSelectedTechs;
    if (isStandalone && finalTechs.length === 0) {
      toast({
        title: 'Add at least one technology',
        description: 'Enter technology or area names to analyze.',
        variant: 'destructive',
      });
      return;
    }

    if (isStandalone && !domainInput.trim()) {
      toast({
        title: 'Domain required',
        description: 'Enter the industry or domain label for this analysis.',
        variant: 'destructive',
      });
      return;
    }

    if (!isStandalone && !reportTrackingId) {
      toast({
        title: 'No report loaded',
        description: 'Open a Tech Sensing report first.',
        variant: 'destructive',
      });
      return;
    }

    setStatus('running');
    setReport(null);
    setProgress(5);
    setProgressMessage('Starting analysis...');

    try {
      const res = await api.sensingCompanyAnalysisStart({
        report_tracking_id: isStandalone ? '' : (reportTrackingId || ''),
        company_names: finalCompanies.slice(0, MAX_COMPANIES),
        technology_names: finalTechs,
        domain: isStandalone ? domainInput.trim() : (domain || undefined),
      });
      setTrackingId(res.tracking_id);
      setCompanies(finalCompanies.slice(0, MAX_COMPANIES));
      setCompanyInput('');
      startPolling(res.tracking_id);
    } catch (e: unknown) {
      setStatus('error');
      const msg = e instanceof Error ? e.message : 'Failed to start analysis';
      toast({ title: 'Failed to start', description: msg, variant: 'destructive' });
    }
  };

  const handleRerun = () => {
    setReport(null);
    setStatus('idle');
    setProgress(0);
    setProgressMessage('');
    setTrackingId(null);
  };

  const handleLoadHistory = async (tid: string) => {
    try {
      setStatus('running');
      setProgressMessage('Loading saved analysis...');
      setProgress(50);
      const res = await api.sensingCompanyAnalysisLoad(tid);
      setReport(res.report);
      setCompanies(res.meta.companies || []);
      // Restore tech lists: treat everything as "custom" when in standalone
      // (no radar items to match against)
      const techs = res.meta.technologies || [];
      if (isStandalone) {
        setSelectedTechs([]);
        setCustomTechs(techs);
      } else {
        const radarSet = new Set(radarItems.map((r) => r.name.toLowerCase()));
        const matched = techs.filter((t) => radarSet.has(t.toLowerCase()));
        const custom = techs.filter((t) => !radarSet.has(t.toLowerCase()));
        setSelectedTechs(matched);
        setCustomTechs(custom);
      }
      setTrackingId(tid);
      setStatus('complete');
      setProgress(100);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load analysis';
      toast({ title: 'Failed to load', description: msg, variant: 'destructive' });
      setStatus('idle');
    }
  };

  const handleDownloadPdf = async () => {
    if (!report) return;
    try {
      await downloadCompanyAnalysisPdf({ report });
    } catch (e) {
      toast({ title: 'PDF failed', description: String(e), variant: 'destructive' });
    }
  };

  const handleDownloadPptx = async () => {
    if (!report) return;
    try {
      await downloadCompanyAnalysisPptx({ report });
    } catch (e) {
      toast({ title: 'PPTX failed', description: String(e), variant: 'destructive' });
    }
  };

  const historyPanel = (
    <div className="border rounded-lg">
      <button
        onClick={() => setShowHistory(!showHistory)}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        {showHistory ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <History className="w-3 h-3" />
        Previous Analyses {history.length ? `(${history.length})` : ''}
        {historyLoading && <Loader2 className="w-3 h-3 animate-spin" />}
      </button>
      {showHistory && history.length > 0 && (
        <div className="max-h-40 overflow-y-auto px-3 pb-2">
          <div className="space-y-1">
            {history.map((h) => (
              <button
                key={h.tracking_id}
                onClick={() => handleLoadHistory(h.tracking_id)}
                className={`flex items-center justify-between w-full text-left px-2 py-1.5 rounded text-xs hover:bg-muted/50 transition-colors ${
                  trackingId === h.tracking_id ? 'bg-muted font-medium' : ''
                }`}
              >
                <div className="flex-1 min-w-0">
                  <span className="block truncate">
                    {(h.companies || []).join(', ') || 'Untitled'}
                  </span>
                  <span className="text-muted-foreground">
                    {h.generated_at ? new Date(h.generated_at).toLocaleString() : ''}
                    {h.technologies && h.technologies.length > 0
                      ? ` · ${h.technologies.length} techs`
                      : ''}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  // --- Rendering ---

  if (status === 'running') {
    return (
      <div className="space-y-4">
        {historyPanel}
        <Card>
          <CardContent className="py-12 text-center space-y-4">
            <Loader2 className="w-10 h-10 animate-spin mx-auto text-primary" />
            <div className="space-y-2">
              <p className="text-sm font-medium">{progressMessage || 'Analyzing...'}</p>
              <div className="max-w-md mx-auto">
                <Progress value={progress} />
              </div>
              <p className="text-xs text-muted-foreground">
                Running per-company searches and LLM synthesis. This can take several minutes.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (status === 'complete' && report) {
    return <ReportView
      report={report}
      trackingId={trackingId}
      onRerun={handleRerun}
      onDownloadPdf={handleDownloadPdf}
      onDownloadPptx={handleDownloadPptx}
      historyPanel={historyPanel}
    />;
  }

  // idle or error → input form
  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      {historyPanel}

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Building2 className="w-4 h-4" />
            Company Analysis
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="text-xs text-muted-foreground">
            {isStandalone ? (
              <>
                Analyze any companies against any set of technology areas.
                For each pair we search the web, synthesize findings with
                an LLM, and produce a comparative view.
              </>
            ) : (
              <>
                Enter competitor, partner, or vendor names and select which
                technologies from the radar to analyze. For each pair, we
                search the web, synthesize findings with an LLM, and produce
                a comparative view. Domain: <strong>{domain || 'Unknown'}</strong>
              </>
            )}
          </div>

          {/* Standalone-only: domain */}
          {isStandalone && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Domain / industry</label>
              <Input
                placeholder="e.g. Generative AI, Electric Vehicles, Quantum Computing"
                value={domainInput}
                onChange={(e) => setDomainInput(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                This label anchors web searches and is referenced in the LLM prompt.
              </p>
            </div>
          )}

          {/* Companies */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Companies ({companies.length}/{MAX_COMPANIES})</label>
            <div className="flex gap-2">
              <Input
                placeholder="Add company (e.g. OpenAI, Anthropic) — comma-separated OK"
                value={companyInput}
                onChange={(e) => setCompanyInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addCompanyFromInput();
                  }
                }}
                disabled={companies.length >= MAX_COMPANIES}
              />
              <Button
                type="button"
                variant="outline"
                onClick={addCompanyFromInput}
                disabled={!companyInput.trim() || companies.length >= MAX_COMPANIES}
              >
                <Plus className="w-4 h-4" />
              </Button>
            </div>
            {companies.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {companies.map((c) => (
                  <Badge key={c} variant="secondary" className="gap-1 pr-1">
                    {c}
                    <button
                      onClick={() => removeCompany(c)}
                      className="ml-0.5 rounded-sm opacity-60 hover:opacity-100"
                      aria-label={`Remove ${c}`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          {/* Technologies / Areas */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">
                {isStandalone ? 'Technology areas' : 'Technologies'} ({allSelectedTechs.length}/{MAX_TECHS})
              </label>
              <div className="flex gap-2">
                {!isStandalone && radarItems.length > 0 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={selectAllTechs}
                  >
                    Top {Math.min(MAX_TECHS, radarItems.length)}
                  </Button>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={clearTechs}
                >
                  Clear
                </Button>
                {!isStandalone && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => setShowTechs((v) => !v)}
                  >
                    {showTechs ? 'Hide list' : 'Show list'}
                  </Button>
                )}
              </div>
            </div>

            {/* Radar items list (report-linked mode only) */}
            {!isStandalone && showTechs && (
              <div className="border rounded-md">
                <div
                  className="h-64 overflow-y-auto p-2"
                  onWheelCapture={(e) => e.stopPropagation()}
                >
                  <div className="space-y-1.5">
                    {radarItems.length === 0 && (
                      <div className="text-xs text-muted-foreground p-2">
                        No radar items available for this report.
                      </div>
                    )}
                    {radarItems.map((r) => {
                      const checked = selectedTechs.includes(r.name);
                      const disabled = !checked && allSelectedTechs.length >= MAX_TECHS;
                      return (
                        <label
                          key={r.name}
                          className={`flex items-center gap-2 py-1 px-1.5 rounded hover:bg-muted/50 text-sm ${
                            disabled ? 'opacity-50' : 'cursor-pointer'
                          }`}
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={() => toggleTech(r.name)}
                            disabled={disabled}
                          />
                          <span className="flex-1 truncate">{r.name}</span>
                          {r.ring && (
                            <Badge variant="outline" className={`text-[10px] h-5 ${ringTone(r.ring)}`}>
                              {r.ring}
                            </Badge>
                          )}
                          {r.quadrant && (
                            <Badge variant="outline" className="text-[10px] h-5">
                              {r.quadrant}
                            </Badge>
                          )}
                        </label>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* Custom / manual tech input */}
            <div className="space-y-2 pt-1">
              <label className="text-xs font-medium text-muted-foreground">
                {isStandalone
                  ? 'Enter technology or area names'
                  : 'Add custom technology (not in radar)'}
              </label>
              <div className="flex gap-2">
                <Input
                  placeholder={
                    isStandalone
                      ? 'e.g. Small language models, LiDAR, Solid-state batteries — comma-separated OK'
                      : 'e.g. In-house compiler, proprietary format — comma-separated OK'
                  }
                  value={customTechInput}
                  onChange={(e) => setCustomTechInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addCustomTech();
                    }
                  }}
                  disabled={allSelectedTechs.length >= MAX_TECHS}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={addCustomTech}
                  disabled={!customTechInput.trim() || allSelectedTechs.length >= MAX_TECHS}
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
              {customTechs.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {customTechs.map((t) => (
                    <Badge
                      key={t}
                      variant="secondary"
                      className="gap-1 pr-1 border-dashed"
                    >
                      <Sparkles className="w-3 h-3 opacity-60" />
                      {t}
                      <button
                        onClick={() => removeCustomTech(t)}
                        className="ml-0.5 rounded-sm opacity-60 hover:opacity-100"
                        aria-label={`Remove ${t}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Run button */}
          <div className="flex justify-end">
            <Button onClick={handleRun} disabled={status === 'running'}>
              <Play className="w-4 h-4 mr-2" />
              Run Analysis
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// --- Results sub-component ---

interface ReportViewProps {
  report: CompanyAnalysisReport;
  trackingId: string | null;
  onRerun: () => void;
  onDownloadPdf: () => void;
  onDownloadPptx: () => void;
  historyPanel: React.ReactNode;
}

const ReportView: React.FC<ReportViewProps> = ({
  report, trackingId, onRerun, onDownloadPdf, onDownloadPptx, historyPanel,
}) => {
  const { companies_analyzed, technologies_analyzed, company_profiles, comparative_matrix, executive_summary } = report;

  const findingFor = useMemo(() => {
    const map = new Map<string, Map<string, typeof report.company_profiles[number]['technology_findings'][number]>>();
    for (const p of company_profiles) {
      const tech = new Map<string, typeof p.technology_findings[number]>();
      for (const f of p.technology_findings) {
        tech.set(f.technology.toLowerCase(), f);
      }
      map.set(p.company.toLowerCase(), tech);
    }
    return map;
  }, [company_profiles]);

  return (
    <div className="space-y-4 max-h-[80vh] overflow-y-auto pr-2">
      {historyPanel}

      {/* Header actions */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">Company Analysis</h2>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>
              {companies_analyzed.length} companies × {technologies_analyzed.length} technologies
            </span>
            <CostTelemetryBadge trackingId={trackingId} />
          </div>
        </div>
        <div className="flex gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <Download className="w-4 h-4 mr-1.5" /> Export
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem onClick={onDownloadPdf}>
                <FileText className="w-4 h-4 mr-2" />
                PDF (formatted report)
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onDownloadPptx}>
                <Presentation className="w-4 h-4 mr-2" />
                PowerPoint (PPTX)
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => downloadCompanyAnalysisCsv(report)}
              >
                <FileSpreadsheet className="w-4 h-4 mr-2" />
                CSV (per-finding rows)
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => downloadCompanyAnalysisXls(report)}
              >
                <FileSpreadsheet className="w-4 h-4 mr-2" />
                Excel (Findings / Matrix / Investment)
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => downloadCompanyAnalysisMarkdown(report)}
              >
                <FileCode className="w-4 h-4 mr-2" />
                Markdown (.md)
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={async () => {
                  if (!trackingId) {
                    toast({
                      title: 'Not available',
                      description:
                        'Run/load an analysis first so it is saved server-side.',
                      variant: 'destructive',
                    });
                    return;
                  }
                  try {
                    const res =
                      await api.sensingExportCompanyAnalysisToNotion({
                        tracking_id: trackingId,
                      });
                    toast({
                      title: 'Exported to Notion',
                      description: res.page?.url || 'Page created.',
                    });
                  } catch (err) {
                    toast({
                      title: 'Notion export failed',
                      description:
                        err instanceof Error ? err.message : 'Unknown error',
                      variant: 'destructive',
                    });
                  }
                }}
              >
                <Globe className="w-4 h-4 mr-2" />
                Notion page
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" size="sm" onClick={onRerun}>
            <RotateCcw className="w-4 h-4 mr-1" /> New
          </Button>
        </div>
      </div>

      {/* Executive summary */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Sparkles className="w-4 h-4" /> Executive Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm whitespace-pre-wrap leading-relaxed text-muted-foreground">
            {executive_summary}
          </div>
        </CardContent>
      </Card>

      {/* Comparative matrix */}
      {comparative_matrix.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Comparative Matrix</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left border-b">
                    <th className="py-2 pr-3 font-medium">Technology</th>
                    <th className="py-2 pr-3 font-medium">Leader</th>
                    <th className="py-2 pr-3 font-medium">Rationale</th>
                  </tr>
                </thead>
                <tbody>
                  {comparative_matrix.map((row) => (
                    <tr key={row.technology} className="border-b last:border-0">
                      <td className="py-2 pr-3 font-medium">{row.technology}</td>
                      <td className="py-2 pr-3">
                        {row.leader === 'Unclear' ? (
                          <Badge variant="outline" className="text-muted-foreground">Unclear</Badge>
                        ) : (
                          <Badge className="bg-primary text-primary-foreground">{row.leader}</Badge>
                        )}
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground text-xs">{row.rationale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Phase 6 — Opportunity/Threat framing */}
      <OpportunityThreatPanel data={report.opportunity_threat} />

      {/* Phase 3 — Strategic themes (LLM-extracted) */}
      <StrategicThemesCluster themes={report.strategic_themes} />

      {/* Phase 3 — Competitive overlap matrix */}
      <CompetitiveOverlapMatrix
        cells={report.overlap_matrix}
        technologies={technologies_analyzed}
      />

      {/* Phase 3 — Investment signals */}
      <InvestmentSignalChart events={report.investment_signals} />

      {/* Phase 3 — Cross-run company timeline (read-only) */}
      <CompanyTimelineView
        companies={companies_analyzed}
        heading="Company activity timeline"
      />

      {/* Phase 6 — Contradiction + hallucination alerts */}
      {(report.contradictions?.length || report.unsupported_claims?.length) ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Trust signals</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-4">
            <ContradictionAlert contradictions={report.contradictions} />
            <HallucinationFlag unsupportedClaims={report.unsupported_claims} />
          </CardContent>
        </Card>
      ) : null}

      {/* Per-company profiles */}
      <div className="space-y-3">
        {company_profiles.map((profile) => (
          <Card key={profile.company}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4" />
                  {profile.company}
                </div>
                <Badge variant="outline" className="text-[10px]">
                  {profile.sources_used} source{profile.sources_used === 1 ? '' : 's'}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                {profile.overall_summary}
              </div>

              {(profile.strengths.length > 0 || profile.gaps.length > 0) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {profile.strengths.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold mb-1 text-green-700">Strengths</div>
                      <ul className="list-disc pl-4 space-y-0.5 text-xs text-muted-foreground">
                        {profile.strengths.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                  )}
                  {profile.gaps.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold mb-1 text-orange-700">Gaps</div>
                      <ul className="list-disc pl-4 space-y-0.5 text-xs text-muted-foreground">
                        {profile.gaps.map((g, i) => <li key={i}>{g}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              <Accordion type="multiple" className="border-t pt-1">
                {technologies_analyzed.map((tech) => {
                  const f = findingFor.get(profile.company.toLowerCase())?.get(tech.toLowerCase());
                  if (!f) return null;
                  const dim = f.confidence < 0.2;
                  return (
                    <AccordionItem key={tech} value={tech} className="border-b last:border-0">
                      <AccordionTrigger className="py-2 text-sm hover:no-underline">
                        <div className={`flex items-center gap-2 flex-1 text-left ${dim ? 'opacity-60' : ''}`}>
                          <span className="font-medium">{tech}</span>
                          {f.stance && (
                            <Badge variant="outline" className={`text-[10px] ${stanceTone(f.stance)}`}>
                              {f.stance}
                            </Badge>
                          )}
                          <span className="flex items-center gap-1.5 text-xs text-muted-foreground ml-auto mr-2">
                            <ConfidenceDot confidence={f.confidence} size={8} />
                            confidence {confidencePct(f.confidence)}
                          </span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className={`space-y-2 text-xs ${dim ? 'opacity-80' : ''}`}>
                        <p className="text-muted-foreground leading-relaxed">{f.summary}</p>
                        {f.specific_products.length > 0 && (
                          <div>
                            <span className="font-semibold">Products: </span>
                            <span className="text-muted-foreground">{f.specific_products.join(', ')}</span>
                          </div>
                        )}
                        {f.recent_developments.length > 0 && (
                          <div>
                            <div className="font-semibold mb-0.5">Recent developments</div>
                            <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                              {f.recent_developments.map((d, i) => <li key={i}>{d}</li>)}
                            </ul>
                          </div>
                        )}
                        {f.partnerships.length > 0 && (
                          <div>
                            <span className="font-semibold">Partnerships: </span>
                            <span className="text-muted-foreground">{f.partnerships.join(', ')}</span>
                          </div>
                        )}
                        {f.investment_signal && (
                          <div>
                            <span className="font-semibold">Investment signal: </span>
                            <span className="text-muted-foreground">{f.investment_signal}</span>
                          </div>
                        )}
                        <SourceEvidencePanel
                          evidence={
                            (f as unknown as { evidence?: import('@/lib/api').ClaimEvidence[] })
                              .evidence
                          }
                          sourceUrls={f.source_urls}
                        />
                      </AccordionContent>
                    </AccordionItem>
                  );
                })}
              </Accordion>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default CompanyAnalysisView;
