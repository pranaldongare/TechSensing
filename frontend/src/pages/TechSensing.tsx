import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import {
  Radar, Loader2, History, Trash2, RefreshCw, Download,
  Maximize2, Minimize2, X, Plus, XCircle, RotateCcw, Calendar,
  ChevronDown, ChevronRight, FileUp,
} from 'lucide-react';
import { io, Socket } from 'socket.io-client';
import { api, getAuthToken } from '@/lib/api';
import type { SensingReportData, SensingHistoryItem, ReportComparison, SensingSchedule, TimelineData, OrgTechContext, TopicPreferences } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { API_URL } from '../../config';
import TechRadar from '@/components/TechRadar';
import SensingRelationshipGraph from '@/components/SensingRelationshipGraph';
import SensingReportRenderer from '@/components/SensingReportRenderer';
import SensingComparisonView from '@/components/SensingComparisonView';
import SensingTimeline from '@/components/SensingTimeline';
import SensingDashboard from '@/components/SensingDashboard';
import SensingDeepDive from '@/components/SensingDeepDive';
import SensingCollaboration from '@/components/SensingCollaboration';
import CompanyAnalysisView from '@/components/CompanyAnalysisView';
import LIRCandidateFeed from '@/components/LIRCandidateFeed';
import LIRBacktestViewer from '@/components/LIRBacktestViewer';
import { toast } from '@/components/ui/use-toast';
import type { DeepDiveReport, DeepDiveHistoryItem, SharedReport } from '@/lib/api';
import { downloadSensingReportPdf } from '@/lib/sensing-report-pdf';
import { downloadSensingReportPptx } from '@/lib/sensing-report-pptx';
import AppNavbar from '@/components/AppNavbar';

const POLL_INTERVAL_MS = 10_000;
const MAX_POLL_COUNT = 360; // 1 hour max

type DateRangePreset = 'last_week' | 'last_month' | 'custom' | 'no_range';

const TechSensing: React.FC = () => {
  const { user } = useAuth();

  // Config state
  const [domain, setDomain] = useState('Generative AI');
  const [customReqs, setCustomReqs] = useState('');
  const [mustInclude, setMustInclude] = useState<string[]>([]);
  const [dontInclude, setDontInclude] = useState<string[]>([]);
  const [mustIncludeInput, setMustIncludeInput] = useState('');
  const [dontIncludeInput, setDontIncludeInput] = useState('');
  const [dateRange, setDateRange] = useState<DateRangePreset>('last_week');
  const [customDays, setCustomDays] = useState(14);

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  const [trackingId, setTrackingId] = useState<string | null>(null);

  // Report state
  const [reportData, setReportData] = useState<SensingReportData | null>(null);
  const [activeTab, setActiveTab] = useState('report');

  // History state
  const [history, setHistory] = useState<SensingHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Full-screen state
  const [isFullScreen, setIsFullScreen] = useState(false);

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState<SensingHistoryItem | null>(null);

  // Drill-through state
  const [highlightTech, setHighlightTech] = useState<string | undefined>();

  // Custom feeds state
  const [feedUrls, setFeedUrls] = useState<string[]>([]);
  const [searchQueries, setSearchQueries] = useState<string[]>([]);
  const [feedInput, setFeedInput] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Document upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [includeVideos, setIncludeVideos] = useState(false);
  const [nlQuery, setNlQuery] = useState('');
  const [stakeholderRole, setStakeholderRole] = useState('general');
  const [queryAnswer, setQueryAnswer] = useState<import('@/lib/api').QueryAnswer | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  // Comparison state
  const [compareA, setCompareA] = useState<string>('');
  const [compareB, setCompareB] = useState<string>('');
  const [comparison, setComparison] = useState<ReportComparison | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  // Schedule state
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
  const [schedules, setSchedules] = useState<SensingSchedule[]>([]);
  const [scheduleFrequency, setScheduleFrequency] = useState('weekly');

  // Timeline state
  const [timelineData, setTimelineData] = useState<TimelineData | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);

  // Org context state
  const [showOrgDialog, setShowOrgDialog] = useState(false);
  const [orgContext, setOrgContext] = useState<OrgTechContext>({ tech_stack: [], industry: '', priorities: [] });
  const [orgStackInput, setOrgStackInput] = useState('');
  const [orgPriorityInput, setOrgPriorityInput] = useState('');

  // Deep dive state
  const [deepDiveResult, setDeepDiveResult] = useState<DeepDiveReport | null>(null);
  const [deepDiveLoading, setDeepDiveLoading] = useState(false);
  const [showDeepDiveDialog, setShowDeepDiveDialog] = useState(false);
  const [deepDiveTrackingId, setDeepDiveTrackingId] = useState<string | null>(null);
  const [deepDiveTechName, setDeepDiveTechName] = useState('');
  const [deepDiveHistory, setDeepDiveHistory] = useState<DeepDiveHistoryItem[]>([]);

  // Collaboration state
  const [shareId, setShareId] = useState<string | null>(null);
  const [showCollabDialog, setShowCollabDialog] = useState(false);

  // Topic preferences state
  const [topicPrefs, setTopicPrefs] = useState<TopicPreferences | null>(null);

  // Refs
  const socketRef = useRef<Socket | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollCountRef = useRef(0);

  const lookbackDays = dateRange === 'no_range' ? 0 : dateRange === 'last_week' ? 7 : dateRange === 'last_month' ? 30 : customDays;

  // Load history, schedules, org context, and alert prefs on mount
  useEffect(() => {
    loadHistory();
    loadSchedules();
    loadOrgContext();
  }, []);

  // Load topic preferences when report domain changes
  useEffect(() => {
    if (reportData?.report?.domain) {
      api.sensingGetTopicPrefs(reportData.report.domain)
        .then(setTopicPrefs)
        .catch(() => setTopicPrefs(null));
    }
  }, [reportData?.report?.domain]);

  // Socket.IO for progress events
  useEffect(() => {
    if (!isGenerating || !trackingId || !user) return;

    const token = getAuthToken();
    const socket = io(API_URL, {
      path: '/socket.io',
      transports: ['websocket', 'polling'],
      auth: token ? { token } : undefined,
    });
    socketRef.current = socket;

    const eventName = `${user.userId}/sensing_progress`;

    socket.on(eventName, (payload: { tracking_id: string; stage: string; progress: number; message: string }) => {
      if (payload.tracking_id !== trackingId) return;

      setProgress(payload.progress);
      setProgressMessage(payload.message);

      if (payload.stage === 'complete') {
        fetchReport(trackingId);
      } else if (payload.stage === 'error') {
        setIsGenerating(false);
        toast({ title: 'Generation Failed', description: payload.message, variant: 'destructive' });
      }
    });

    socket.on('connect_error', () => {
      startPolling(trackingId);
    });

    return () => {
      socket.off(eventName);
      socket.disconnect();
      socketRef.current = null;
    };
  }, [isGenerating, trackingId, user]);

  // ESC to exit full-screen
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullScreen) setIsFullScreen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullScreen]);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await api.sensingHistory();
      setHistory(res.reports || []);
    } catch {
      // Silently handle
    } finally {
      setHistoryLoading(false);
    }
  };

  const startPolling = useCallback((tid: string) => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    pollCountRef.current = 0;

    const poll = async () => {
      if (pollCountRef.current >= MAX_POLL_COUNT) {
        setIsGenerating(false);
        toast({ title: 'Timeout', description: 'Report generation timed out.', variant: 'destructive' });
        return;
      }
      pollCountRef.current++;

      try {
        const res = await api.sensingStatus(tid);
        if (res.status === 'completed' && res.data) {
          setReportData(res.data);
          setIsGenerating(false);
          setProgress(100);
          setProgressMessage('Report ready');
          loadHistory();
          return;
        } else if (res.status === 'failed') {
          setIsGenerating(false);
          toast({ title: 'Generation Failed', description: res.error || 'Unknown error', variant: 'destructive' });
          return;
        }
      } catch {
        // Continue polling
      }

      pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    };

    pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
  }, []);

  const fetchReport = async (tid: string) => {
    try {
      const res = await api.sensingStatus(tid);
      if (res.status === 'completed' && res.data) {
        setReportData(res.data);
        setIsGenerating(false);
        setProgress(100);
        loadHistory();
      } else if (res.status === 'pending') {
        startPolling(tid);
      } else {
        setIsGenerating(false);
        toast({ title: 'Error', description: res.error || 'Failed to load report', variant: 'destructive' });
      }
    } catch {
      startPolling(tid);
    }
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    setProgress(0);
    setProgressMessage('Starting...');
    setReportData(null);

    try {
      let res;
      if (uploadFile) {
        // Document-based pipeline
        res = await api.sensingGenerateFromDocument(
          uploadFile,
          domain,
          customReqs,
          mustInclude.length > 0 ? mustInclude : undefined,
          dontInclude.length > 0 ? dontInclude : undefined,
          lookbackDays,
          includeVideos,
        );
      } else {
        // Normal web-based pipeline
        res = await api.sensingGenerate(
          domain,
          customReqs,
          mustInclude.length > 0 ? mustInclude : undefined,
          dontInclude.length > 0 ? dontInclude : undefined,
          lookbackDays,
          feedUrls.length > 0 ? feedUrls : undefined,
          searchQueries.length > 0 ? searchQueries : undefined,
          includeVideos,
        );
      }
      setTrackingId(res.tracking_id);
      startPolling(res.tracking_id);
    } catch (err) {
      setIsGenerating(false);
      toast({
        title: 'Failed to start',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const handleLoadReport = async (tid: string) => {
    setIsGenerating(true);
    setProgress(50);
    setProgressMessage('Loading report...');
    setTrackingId(tid);
    await fetchReport(tid);
  };

  const handleDeleteReport = async (tid: string) => {
    try {
      await api.sensingDelete(tid);
      setHistory(prev => prev.filter(r => r.tracking_id !== tid));
      if (reportData?.meta.tracking_id === tid) setReportData(null);
      toast({ title: 'Report deleted' });
    } catch {
      toast({ title: 'Failed to delete', variant: 'destructive' });
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleRegenerate = (item: SensingHistoryItem) => {
    // Populate config form with original generation params
    setDomain(item.domain || 'Generative AI');
    setCustomReqs(item.custom_requirements || '');
    setMustInclude(item.must_include || []);
    setDontInclude(item.dont_include || []);

    const days = item.lookback_days ?? 7;
    if (days === 0) {
      setDateRange('no_range');
    } else if (days === 7) {
      setDateRange('last_week');
    } else if (days === 30) {
      setDateRange('last_month');
    } else {
      setDateRange('custom');
      setCustomDays(days);
    }

    // Clear the current report so user sees the config form
    setReportData(null);

    toast({
      title: 'Parameters loaded',
      description: 'Adjust the date range or parameters and click Generate Report.',
    });
  };

  const handleDownloadPdf = async () => {
    if (!reportData) return;
    try {
      await downloadSensingReportPdf(reportData);
      toast({ title: 'PDF download started' });
    } catch {
      toast({ title: 'PDF generation failed', variant: 'destructive' });
    }
  };

  const handleDownloadPptx = async () => {
    if (!reportData) return;
    try {
      await downloadSensingReportPptx(reportData);
      toast({ title: 'PPTX download started' });
    } catch {
      toast({ title: 'PPTX generation failed', variant: 'destructive' });
    }
  };

  const handleCompare = async () => {
    if (!compareA || !compareB || compareA === compareB) return;
    setCompareLoading(true);
    try {
      const result = await api.sensingCompare(compareA, compareB);
      setComparison(result);
    } catch (err: unknown) {
      toast({ title: 'Comparison failed', description: err instanceof Error ? err.message : 'Unknown error', variant: 'destructive' });
    } finally {
      setCompareLoading(false);
    }
  };

  const loadSchedules = async () => {
    try {
      const data = await api.sensingGetSchedules();
      setSchedules(data.schedules);
    } catch { /* ignore */ }
  };

  const handleCreateSchedule = async () => {
    try {
      await api.sensingCreateSchedule({
        domain,
        frequency: scheduleFrequency,
        custom_requirements: customReqs,
        must_include: mustInclude.length > 0 ? mustInclude : null,
        dont_include: dontInclude.length > 0 ? dontInclude : null,
        lookback_days: lookbackDays,
      });
      toast({ title: 'Schedule created' });
      setShowScheduleDialog(false);
      await loadSchedules();
    } catch (err: unknown) {
      toast({ title: 'Failed to create schedule', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    }
  };

  const handleToggleSchedule = async (id: string, enabled: boolean) => {
    try {
      await api.sensingUpdateSchedule(id, { enabled });
      await loadSchedules();
    } catch { /* ignore */ }
  };

  const handleDeleteSchedule = async (id: string) => {
    try {
      await api.sensingDeleteSchedule(id);
      await loadSchedules();
    } catch { /* ignore */ }
  };

  const loadTimeline = async () => {
    setTimelineLoading(true);
    try {
      const data = await api.sensingTimeline(domain);
      setTimelineData(data);
    } catch { /* ignore */ }
    finally { setTimelineLoading(false); }
  };

  const loadOrgContext = async () => {
    try {
      const ctx = await api.sensingGetOrgContext();
      setOrgContext(ctx);
    } catch { /* ignore */ }
  };

  const handleSaveOrgContext = async () => {
    try {
      await api.sensingUpdateOrgContext(orgContext);
      toast({ title: 'Org profile saved' });
      setShowOrgDialog(false);
    } catch (err: unknown) {
      toast({ title: 'Failed to save', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    }
  };

  const handleDeepDive = async (technologyName: string) => {
    setDeepDiveLoading(true);
    setDeepDiveResult(null);
    setShowDeepDiveDialog(true);
    setDeepDiveTechName(technologyName);
    loadDeepDiveHistory();
    try {
      const { tracking_id } = await api.sensingDeepDive(technologyName, domain);
      setDeepDiveTrackingId(tracking_id);
      // Poll for result
      const poll = async () => {
        for (let i = 0; i < 120; i++) {
          await new Promise(r => setTimeout(r, 5000));
          const res = await api.sensingDeepDiveStatus(tracking_id);
          if (res.status === 'completed' && res.data) {
            setDeepDiveResult(res.data);
            setDeepDiveLoading(false);
            loadDeepDiveHistory();
            return;
          }
          if (res.status === 'failed') {
            toast({ title: 'Deep dive failed', description: res.error, variant: 'destructive' });
            setDeepDiveLoading(false);
            setShowDeepDiveDialog(false);
            return;
          }
        }
        toast({ title: 'Deep dive timed out', variant: 'destructive' });
        setDeepDiveLoading(false);
      };
      poll();
    } catch (err: unknown) {
      toast({ title: 'Deep dive failed', description: err instanceof Error ? err.message : '', variant: 'destructive' });
      setDeepDiveLoading(false);
      setShowDeepDiveDialog(false);
    }
  };

  const loadDeepDiveHistory = async () => {
    try {
      const res = await api.sensingDeepDiveHistory();
      setDeepDiveHistory(res.deep_dives || []);
    } catch {
      // Silently handle — history is non-critical
    }
  };

  const handleLoadDeepDive = async (loadTrackingId: string) => {
    setDeepDiveLoading(true);
    setDeepDiveResult(null);
    try {
      const loaded = await api.sensingDeepDiveLoad(loadTrackingId);
      setDeepDiveResult(loaded.report);
      setDeepDiveTrackingId(loadTrackingId);
      setDeepDiveTechName(loaded.meta.technology_name || loaded.report.technology_name);
    } catch (err: unknown) {
      toast({ title: 'Failed to load deep dive', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    } finally {
      setDeepDiveLoading(false);
    }
  };

  const handleShare = async () => {
    if (!reportData) return;
    try {
      const shared = await api.sensingShare(reportData.meta.tracking_id);
      setShareId(shared.share_id);
      setShowCollabDialog(true);
      const url = `${window.location.origin}${window.location.pathname}?shared=${shared.share_id}`;
      navigator.clipboard.writeText(url);
      toast({ title: 'Report shared', description: 'Link copied to clipboard' });
    } catch (err: unknown) {
      toast({ title: 'Share failed', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    }
  };

  const handleTopicInterest = async (techName: string, interest: 'interested' | 'not_interested' | 'neutral') => {
    if (!reportData?.report?.domain) return;
    try {
      const updated = await api.sensingUpdateTopicPref(reportData.report.domain, techName, interest);
      setTopicPrefs(updated);
    } catch (err: unknown) {
      toast({ title: 'Failed to update preference', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    }
  };

  const handleNlQuery = async () => {
    if (!nlQuery.trim()) return;
    setQueryLoading(true);
    setQueryAnswer(null);
    try {
      const answer = await api.sensingQuery(nlQuery.trim(), domain || undefined);
      setQueryAnswer(answer);
    } catch (err: unknown) {
      toast({ title: 'Query failed', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    } finally {
      setQueryLoading(false);
    }
  };

  const handleSourceFeedback = async (sourceName: string, vote: 'up' | 'down') => {
    try {
      await api.sensingSubmitSourceFeedback(sourceName, vote);
      toast({ title: `Source ${vote === 'up' ? 'upvoted' : 'downvoted'}`, description: sourceName });
    } catch (err: unknown) {
      toast({ title: 'Failed to submit feedback', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    }
  };

  const addKeyword = (
    list: string[],
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    inputValue: string,
    inputSetter: React.Dispatch<React.SetStateAction<string>>,
  ) => {
    const trimmed = inputValue.trim();
    if (trimmed && !list.includes(trimmed)) {
      setter([...list, trimmed]);
    }
    inputSetter('');
  };

  const removeKeyword = (
    list: string[],
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    keyword: string,
  ) => {
    setter(list.filter(k => k !== keyword));
  };

  const handleKeywordKeyDown = (
    e: React.KeyboardEvent<HTMLInputElement>,
    list: string[],
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    inputValue: string,
    inputSetter: React.Dispatch<React.SetStateAction<string>>,
  ) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addKeyword(list, setter, inputValue, inputSetter);
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, []);

  // Full-screen report view
  if (isFullScreen && reportData) {
    return (
      <div className="fixed inset-0 z-50 bg-background flex flex-col">
        <div className="flex items-center justify-between px-6 py-3 border-b shrink-0 bg-background">
          <div className="flex items-center gap-3">
            <Radar className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-bold truncate">{reportData.report.report_title}</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleDownloadPdf}>
              <Download className="w-4 h-4 mr-1.5" />
              PDF
            </Button>
            <Button variant="outline" size="sm" onClick={handleDownloadPptx}>
              <Download className="w-4 h-4 mr-1.5" />
              PPTX
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setIsFullScreen(false)}>
              <Minimize2 className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setIsFullScreen(false)}>
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
          <div className="px-6 pt-2 shrink-0">
            <TabsList>
              <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
              <TabsTrigger value="report">Report</TabsTrigger>
              <TabsTrigger value="radar">Technology Radar</TabsTrigger>
              <TabsTrigger value="relationships" disabled={!reportData?.report?.relationships}>Relationships</TabsTrigger>
              <TabsTrigger value="compare" disabled={history.length < 2}>Compare</TabsTrigger>
              <TabsTrigger value="timeline" onClick={() => { if (!timelineData) loadTimeline(); }}>Timeline</TabsTrigger>
              <TabsTrigger value="company-analysis" disabled={!reportData}>Company Analysis</TabsTrigger>
              <TabsTrigger value="leading-indicators">Leading Indicators</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="dashboard" className="flex-1 min-h-0 px-6 pb-4 mt-2 overflow-auto">
            <SensingDashboard onSelectDomain={(d) => { setDomain(d); setActiveTab('report'); }} />
          </TabsContent>
          <TabsContent value="report" className="flex-1 min-h-0 px-6 pb-4 mt-2">
            <SensingReportRenderer report={reportData.report} meta={reportData.meta} highlightTechnology={highlightTech} onDeepDive={handleDeepDive} topicPreferences={topicPrefs} onTopicInterest={handleTopicInterest} onSourceFeedback={handleSourceFeedback} />
          </TabsContent>
          <TabsContent value="radar" className="flex-1 min-h-0 px-6 pb-4 mt-2 overflow-auto">
            <TechRadar items={reportData.report.radar_items || []} onBlipClick={(name) => { setHighlightTech(name); setActiveTab('report'); }} customQuadrants={orgContext.radar_customization?.quadrants} />
          </TabsContent>
          <TabsContent value="relationships" className="flex-1 min-h-0 px-6 pb-4 mt-2">
            {reportData.report.relationships && (
              <SensingRelationshipGraph
                relationships={reportData.report.relationships}
                radarItems={reportData.report.radar_items || []}
                onTechClick={(name) => { setHighlightTech(name); setActiveTab('report'); }}
              />
            )}
          </TabsContent>
          <TabsContent value="compare" className="flex-1 min-h-0 px-6 pb-4 mt-2 overflow-auto">
            <div className="space-y-4">
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Older Report</label>
                  <Select value={compareA} onValueChange={setCompareA}>
                    <SelectTrigger><SelectValue placeholder="Select report..." /></SelectTrigger>
                    <SelectContent>
                      {history.map(h => (
                        <SelectItem key={h.tracking_id} value={h.tracking_id}>
                          {h.report_title} ({new Date(h.generated_at).toLocaleDateString()})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex-1">
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Newer Report</label>
                  <Select value={compareB} onValueChange={setCompareB}>
                    <SelectTrigger><SelectValue placeholder="Select report..." /></SelectTrigger>
                    <SelectContent>
                      {history.map(h => (
                        <SelectItem key={h.tracking_id} value={h.tracking_id}>
                          {h.report_title} ({new Date(h.generated_at).toLocaleDateString()})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button onClick={handleCompare} disabled={!compareA || !compareB || compareA === compareB || compareLoading}>
                  {compareLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Compare'}
                </Button>
              </div>
              {comparison && <SensingComparisonView comparison={comparison} />}
            </div>
          </TabsContent>
          <TabsContent value="timeline" className="flex-1 min-h-0 px-6 pb-4 mt-2 overflow-auto">
            {timelineLoading ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" /></div>
            ) : timelineData ? (
              <SensingTimeline data={timelineData} />
            ) : (
              <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">Loading timeline...</div>
            )}
          </TabsContent>
          <TabsContent value="company-analysis" className="flex-1 min-h-0 px-6 pb-4 mt-2 overflow-auto">
            <CompanyAnalysisView
              reportTrackingId={reportData?.meta?.tracking_id}
              domain={reportData?.report?.domain}
              radarItems={reportData?.report?.radar_items || []}
            />
          </TabsContent>
          <TabsContent value="leading-indicators" className="flex-1 min-h-0 px-6 pb-4 mt-2 overflow-auto">
            <LIRCandidateFeed />
            <div className="mt-6 border-t border-border pt-4">
              <LIRBacktestViewer />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      <AppNavbar />
      <div className="flex-1 flex flex-col p-6 gap-4 overflow-hidden min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Radar className="w-6 h-6 text-primary" />
          <h2 className="text-2xl font-bold">Tech Sensing</h2>
          <Button variant="outline" size="sm" onClick={() => setShowScheduleDialog(true)} className="ml-3">
            <Calendar className="w-4 h-4 mr-1" /> Schedule
            {schedules.length > 0 && <Badge variant="secondary" className="ml-1 text-xs">{schedules.length}</Badge>}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowOrgDialog(true)}>
            Org Profile
          </Button>
        </div>
        {reportData && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const currentItem = history.find(h => h.tracking_id === reportData.meta.tracking_id);
                if (currentItem) {
                  handleRegenerate(currentItem);
                } else {
                  // Fallback: use meta from current report
                  handleRegenerate({
                    tracking_id: reportData.meta.tracking_id,
                    domain: reportData.meta.domain,
                    generated_at: reportData.meta.generated_at,
                    report_title: reportData.report.report_title,
                    total_articles: reportData.report.total_articles_analyzed,
                    custom_requirements: reportData.meta.custom_requirements,
                    must_include: reportData.meta.must_include,
                    dont_include: reportData.meta.dont_include,
                    lookback_days: reportData.meta.lookback_days,
                  });
                }
              }}
              disabled={isGenerating}
            >
              <RotateCcw className="w-4 h-4 mr-1.5" />
              Regenerate
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const currentItem = history.find(h => h.tracking_id === reportData.meta.tracking_id);
                setDeleteTarget(currentItem || {
                  tracking_id: reportData.meta.tracking_id,
                  domain: reportData.meta.domain,
                  generated_at: reportData.meta.generated_at,
                  report_title: reportData.report.report_title,
                  total_articles: reportData.report.total_articles_analyzed,
                });
              }}
            >
              <Trash2 className="w-4 h-4 mr-1.5" />
              Delete
            </Button>
            <Button variant="outline" size="sm" onClick={handleDownloadPdf}>
              <Download className="w-4 h-4 mr-1.5" />
              PDF
            </Button>
            <Button variant="outline" size="sm" onClick={handleDownloadPptx}>
              <Download className="w-4 h-4 mr-1.5" />
              PPTX
            </Button>
            <Button variant="outline" size="sm" onClick={handleShare}>
              Share
            </Button>
            <Button variant="outline" size="sm" onClick={() => setIsFullScreen(true)}>
              <Maximize2 className="w-4 h-4 mr-1.5" />
              Full Screen
            </Button>
          </div>
        )}
      </div>

      {/* Configuration + History row */}
      <div className="flex gap-4 shrink-0 max-h-[380px]">
        {/* Config card */}
        <Card className="flex-1">
          <CardContent className="p-4 space-y-3">
            {/* Ask your radar */}
            <div className="flex gap-2">
              <Input
                value={nlQuery}
                onChange={(e) => setNlQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleNlQuery(); }}
                placeholder="Ask your radar... e.g., 'What happened with RAG frameworks this month?'"
                disabled={queryLoading}
                className="text-sm"
              />
              <Button size="sm" onClick={handleNlQuery} disabled={queryLoading || !nlQuery.trim()}>
                {queryLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Ask'}
              </Button>
            </div>
            {queryAnswer && (
              <Card className="border-l-4 border-l-blue-500 p-3">
                <div className="text-sm prose prose-sm max-w-none dark:prose-invert">{queryAnswer.answer}</div>
                <div className="flex gap-2 mt-2 flex-wrap">
                  <Badge variant={queryAnswer.confidence === 'high' ? 'default' : queryAnswer.confidence === 'medium' ? 'secondary' : 'destructive'}>
                    {queryAnswer.confidence} confidence
                  </Badge>
                  {queryAnswer.technologies_mentioned.map((t) => (
                    <Badge key={t} variant="outline" className="text-xs">{t}</Badge>
                  ))}
                </div>
              </Card>
            )}
            {/* Two-column grid: Left = Domain/Date/Requirements, Right = Keywords */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-3">
              {/* Left column */}
              <div className="space-y-3">
                {/* Domain + Date Range */}
                <div className="flex gap-3">
                  <div className="flex-1">
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                      Domain / Topic
                    </label>
                    <Input
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder="e.g., Generative AI, Robotics, Quantum Computing"
                      disabled={isGenerating}
                    />
                  </div>
                  <div className="w-40">
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                      Date Range
                    </label>
                    <Select
                      value={dateRange}
                      onValueChange={(v) => setDateRange(v as DateRangePreset)}
                      disabled={isGenerating}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="last_week">Last Week</SelectItem>
                        <SelectItem value="last_month">Last Month</SelectItem>
                        <SelectItem value="custom">Custom</SelectItem>
                        <SelectItem value="no_range">No Range</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {dateRange === 'custom' && (
                    <div className="w-28">
                      <label className="text-xs font-medium text-muted-foreground mb-1 block">
                        Days
                      </label>
                      <Input
                        type="number"
                        min={1}
                        max={365}
                        value={customDays}
                        onChange={(e) => setCustomDays(Math.max(1, Math.min(365, parseInt(e.target.value) || 7)))}
                        disabled={isGenerating}
                      />
                    </div>
                  )}
                </div>
                {/* YouTube Videos Toggle + Custom Requirements */}
                <div className="flex gap-3 items-start">
                  <div className="flex-1">
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                      Custom Requirements (optional)
                    </label>
                    <Textarea
                      value={customReqs}
                      onChange={(e) => setCustomReqs(e.target.value)}
                      placeholder="e.g., Focus on enterprise adoption, compare with previous trends..."
                      rows={2}
                      disabled={isGenerating}
                    />
                  </div>
                  <div className="flex items-center gap-2 pt-5">
                    <Switch
                      id="include-videos"
                      checked={includeVideos}
                      onCheckedChange={setIncludeVideos}
                      disabled={isGenerating}
                    />
                    <label htmlFor="include-videos" className="text-xs font-medium text-muted-foreground whitespace-nowrap cursor-pointer">
                      YouTube Videos
                    </label>
                  </div>
                  <div className="pt-3">
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">Audience</label>
                    <Select value={stakeholderRole} onValueChange={setStakeholderRole} disabled={isGenerating}>
                      <SelectTrigger className="w-40">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="general">General</SelectItem>
                        <SelectItem value="cto">CTO / Strategy</SelectItem>
                        <SelectItem value="engineering_lead">Engineering Lead</SelectItem>
                        <SelectItem value="developer">Developer</SelectItem>
                        <SelectItem value="product_manager">Product Manager</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              {/* Right column: Keywords */}
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    Must Include Keywords
                  </label>
                  <div className="flex gap-1.5">
                    <Input
                      value={mustIncludeInput}
                      onChange={(e) => setMustIncludeInput(e.target.value)}
                      onKeyDown={(e) => handleKeywordKeyDown(e, mustInclude, setMustInclude, mustIncludeInput, setMustIncludeInput)}
                      placeholder="Type keyword and press Enter"
                      disabled={isGenerating}
                      className="text-sm"
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      className="shrink-0 h-9 w-9"
                      onClick={() => addKeyword(mustInclude, setMustInclude, mustIncludeInput, setMustIncludeInput)}
                      disabled={isGenerating || !mustIncludeInput.trim()}
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                  {mustInclude.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {mustInclude.map((kw) => (
                        <Badge key={kw} variant="secondary" className="text-xs gap-1 bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
                          {kw}
                          <button onClick={() => removeKeyword(mustInclude, setMustInclude, kw)} disabled={isGenerating}>
                            <XCircle className="w-3 h-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    Don't Include Keywords
                  </label>
                  <div className="flex gap-1.5">
                    <Input
                      value={dontIncludeInput}
                      onChange={(e) => setDontIncludeInput(e.target.value)}
                      onKeyDown={(e) => handleKeywordKeyDown(e, dontInclude, setDontInclude, dontIncludeInput, setDontIncludeInput)}
                      placeholder="Type keyword and press Enter"
                      disabled={isGenerating}
                      className="text-sm"
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      className="shrink-0 h-9 w-9"
                      onClick={() => addKeyword(dontInclude, setDontInclude, dontIncludeInput, setDontIncludeInput)}
                      disabled={isGenerating || !dontIncludeInput.trim()}
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                  {dontInclude.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {dontInclude.map((kw) => (
                        <Badge key={kw} variant="secondary" className="text-xs gap-1 bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                          {kw}
                          <button onClick={() => removeKeyword(dontInclude, setDontInclude, kw)} disabled={isGenerating}>
                            <XCircle className="w-3 h-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Full-width: Advanced Sources + Document Upload side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-3">
              {/* Advanced: Custom Sources */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                  {showAdvanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  Advanced: Custom Sources
                </button>
                {showAdvanced && (
                  <div className="mt-2 space-y-3 p-3 border rounded-md">
                    <div>
                      <label className="text-xs font-medium">Custom RSS Feeds</label>
                      <div className="flex gap-2 mt-1">
                        <Input
                          value={feedInput}
                          onChange={(e) => setFeedInput(e.target.value)}
                          placeholder="https://example.com/feed.xml"
                          className="text-sm"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && feedInput.trim()) {
                              setFeedUrls([...feedUrls, feedInput.trim()]);
                              setFeedInput('');
                            }
                          }}
                        />
                        <Button size="sm" variant="outline" onClick={() => { if (feedInput.trim()) { setFeedUrls([...feedUrls, feedInput.trim()]); setFeedInput(''); } }}>
                          <Plus className="w-3 h-3" />
                        </Button>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {feedUrls.map((url, i) => (
                          <Badge key={i} variant="secondary" className="text-xs gap-1">
                            {url.length > 40 ? url.slice(0, 40) + '...' : url}
                            <XCircle className="w-3 h-3 cursor-pointer" onClick={() => setFeedUrls(feedUrls.filter((_, j) => j !== i))} />
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div>
                      <label className="text-xs font-medium">Custom Search Queries</label>
                      <div className="flex gap-2 mt-1">
                        <Input
                          value={queryInput}
                          onChange={(e) => setQueryInput(e.target.value)}
                          placeholder="e.g., specific technology or framework"
                          className="text-sm"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && queryInput.trim()) {
                              setSearchQueries([...searchQueries, queryInput.trim()]);
                              setQueryInput('');
                            }
                          }}
                        />
                        <Button size="sm" variant="outline" onClick={() => { if (queryInput.trim()) { setSearchQueries([...searchQueries, queryInput.trim()]); setQueryInput(''); } }}>
                          <Plus className="w-3 h-3" />
                        </Button>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {searchQueries.map((q, i) => (
                          <Badge key={i} variant="secondary" className="text-xs gap-1">
                            {q}
                            <XCircle className="w-3 h-3 cursor-pointer" onClick={() => setSearchQueries(searchQueries.filter((_, j) => j !== i))} />
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Document Upload */}
              <div className="border rounded-md p-3 bg-muted/20">
                <div className="flex items-center gap-2 mb-1">
                  <FileUp className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">
                    Source Document (optional)
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  Upload a document — themes will be extracted and combined with web sources.
                </p>
                <input
                  type="file"
                  accept=".pdf,.docx,.doc,.pptx,.xlsx,.csv,.md,.txt"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  disabled={isGenerating}
                  className="text-sm file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 file:cursor-pointer"
                />
                {uploadFile && (
                  <div className="flex items-center gap-2 mt-1.5">
                    <Badge variant="secondary" className="text-xs gap-1">
                      {uploadFile.name}
                      <XCircle className="w-3 h-3 cursor-pointer" onClick={() => setUploadFile(null)} />
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      Document + web sources
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Generate button + progress */}
            <div className="flex items-center gap-3">
              <Button onClick={handleGenerate} disabled={isGenerating || !domain.trim()}>
                {isGenerating ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Generate Report
                  </>
                )}
              </Button>
              {isGenerating && (
                <div className="flex-1 space-y-1">
                  <Progress value={progress} className="h-2" />
                  <p className="text-xs text-muted-foreground">{progressMessage}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* History card */}
        <Card className="w-80 shrink-0 flex flex-col">
          <CardContent className="p-4 flex flex-col flex-1 min-h-0">
            <div className="flex items-center justify-between mb-2 shrink-0">
              <span className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                <History className="w-3 h-3" />
                Report History
              </span>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={loadHistory}>
                <RefreshCw className={`w-3 h-3 ${historyLoading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
            <ScrollArea className="flex-1 min-h-0">
              {history.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">No reports yet</p>
              ) : (
                <div className="space-y-1.5">
                  {history.map((item) => (
                    <div
                      key={item.tracking_id}
                      className={`flex items-center gap-1.5 p-1.5 rounded text-xs hover:bg-muted/50 cursor-pointer group ${
                        reportData?.meta.tracking_id === item.tracking_id ? 'bg-muted' : ''
                      }`}
                    >
                      <button
                        className="flex-1 text-left truncate"
                        onClick={() => handleLoadReport(item.tracking_id)}
                        disabled={isGenerating}
                      >
                        <span className="font-medium block truncate">{item.report_title || item.domain}</span>
                        <span className="text-muted-foreground">
                          {item.generated_at ? new Date(item.generated_at).toLocaleDateString() : ''}
                          {' · '}
                          {item.total_articles} articles
                        </span>
                      </button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 opacity-0 group-hover:opacity-100 shrink-0"
                        title="Regenerate with new parameters"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRegenerate(item);
                        }}
                        disabled={isGenerating}
                      >
                        <RotateCcw className="w-3 h-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 opacity-0 group-hover:opacity-100 shrink-0"
                        title="Delete report"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget(item);
                        }}
                      >
                        <Trash2 className="w-3 h-3 text-destructive" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      {/* Report display — tabs always visible; report-dependent tabs disabled when no report */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
        <TabsList className="shrink-0">
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="report" disabled={!reportData}>Report</TabsTrigger>
          <TabsTrigger value="radar" disabled={!reportData}>Technology Radar</TabsTrigger>
          <TabsTrigger value="relationships" disabled={!reportData?.report?.relationships}>Relationships</TabsTrigger>
          <TabsTrigger value="compare" disabled={!reportData || history.length < 2}>Compare</TabsTrigger>
          <TabsTrigger value="timeline" disabled={!reportData} onClick={() => { if (!timelineData) loadTimeline(); }}>Timeline</TabsTrigger>
          <TabsTrigger value="company-analysis" disabled={!reportData}>Company Analysis</TabsTrigger>
          <TabsTrigger value="leading-indicators">Leading Indicators</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard" className="flex-1 min-h-0 mt-2 overflow-auto">
          <SensingDashboard onSelectDomain={(d) => { setDomain(d); setActiveTab('report'); }} />
        </TabsContent>
        <TabsContent value="report" className="flex-1 min-h-0 mt-2">
          {reportData ? (
            <SensingReportRenderer report={reportData.report} meta={reportData.meta} highlightTechnology={highlightTech} onDeepDive={handleDeepDive} topicPreferences={topicPrefs} onTopicInterest={handleTopicInterest} onSourceFeedback={handleSourceFeedback} />
          ) : !isGenerating ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground py-12">
              <div className="text-center space-y-2">
                <Radar className="w-12 h-12 mx-auto opacity-20" />
                <p className="text-sm">Generate a report or select one from history</p>
              </div>
            </div>
          ) : null}
        </TabsContent>
        <TabsContent value="radar" className="flex-1 min-h-0 mt-2 overflow-auto">
          {reportData && (
            <TechRadar items={reportData.report.radar_items || []} onBlipClick={(name) => { setHighlightTech(name); setActiveTab('report'); }} customQuadrants={orgContext.radar_customization?.quadrants} />
          )}
        </TabsContent>
        <TabsContent value="relationships" className="flex-1 min-h-0 mt-2">
          {reportData?.report?.relationships && (
            <SensingRelationshipGraph
              relationships={reportData.report.relationships}
              radarItems={reportData.report.radar_items || []}
              onTechClick={(name) => { setHighlightTech(name); setActiveTab('report'); }}
            />
          )}
        </TabsContent>
        <TabsContent value="compare" className="flex-1 min-h-0 mt-2 overflow-auto">
          <div className="space-y-4">
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Older Report</label>
                <Select value={compareA} onValueChange={setCompareA}>
                  <SelectTrigger><SelectValue placeholder="Select report..." /></SelectTrigger>
                  <SelectContent>
                    {history.map(h => (
                      <SelectItem key={h.tracking_id} value={h.tracking_id}>
                        {h.report_title} ({new Date(h.generated_at).toLocaleDateString()})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex-1">
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Newer Report</label>
                <Select value={compareB} onValueChange={setCompareB}>
                  <SelectTrigger><SelectValue placeholder="Select report..." /></SelectTrigger>
                  <SelectContent>
                    {history.map(h => (
                      <SelectItem key={h.tracking_id} value={h.tracking_id}>
                        {h.report_title} ({new Date(h.generated_at).toLocaleDateString()})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={handleCompare} disabled={!compareA || !compareB || compareA === compareB || compareLoading}>
                {compareLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Compare'}
              </Button>
            </div>
            {comparison && <SensingComparisonView comparison={comparison} />}
          </div>
        </TabsContent>
        <TabsContent value="timeline" className="flex-1 min-h-0 mt-2 overflow-auto">
          {timelineLoading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" /></div>
          ) : timelineData ? (
            <SensingTimeline data={timelineData} />
          ) : (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">Loading timeline...</div>
          )}
        </TabsContent>
        <TabsContent value="company-analysis" className="flex-1 min-h-0 mt-2 overflow-auto">
          {reportData && (
            <CompanyAnalysisView
              reportTrackingId={reportData?.meta?.tracking_id}
              domain={reportData?.report?.domain}
              radarItems={reportData?.report?.radar_items || []}
            />
          )}
        </TabsContent>
        <TabsContent value="leading-indicators" className="flex-1 min-h-0 mt-2 overflow-auto">
          <LIRCandidateFeed />
          <div className="mt-6 border-t border-border pt-4">
            <LIRBacktestViewer />
          </div>
        </TabsContent>
      </Tabs>

      {/* Schedule dialog */}
      <Dialog open={showScheduleDialog} onOpenChange={setShowScheduleDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Schedule Reports</DialogTitle>
            <DialogDescription>Automatically generate reports on a recurring basis.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Frequency</label>
              <Select value={scheduleFrequency} onValueChange={setScheduleFrequency}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="biweekly">Biweekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-muted-foreground">
              Will use current config: <strong>{domain}</strong>, {lookbackDays === 0 ? 'no time range' : `${lookbackDays} day lookback`}
              {mustInclude.length > 0 && <>, must include: {mustInclude.join(', ')}</>}
            </p>
            <DialogFooter>
              <Button onClick={handleCreateSchedule}>Create Schedule</Button>
            </DialogFooter>
            {schedules.length > 0 && (
              <div className="border-t pt-3 space-y-2">
                <h4 className="text-sm font-medium">Active Schedules</h4>
                {schedules.map(s => (
                  <div key={s.id} className="flex items-center justify-between text-sm p-2 rounded border">
                    <div className="flex-1">
                      <span className="font-medium">{s.domain}</span>
                      <span className="text-muted-foreground ml-2">{s.frequency}</span>
                      {s.next_run && (
                        <span className="text-xs text-muted-foreground ml-2">
                          Next: {new Date(s.next_run).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={s.enabled}
                        onCheckedChange={(checked) => handleToggleSchedule(s.id, checked)}
                      />
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleDeleteSchedule(s.id)}>
                        <Trash2 className="w-3.5 h-3.5 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Report</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{deleteTarget?.report_title || deleteTarget?.domain}"?
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteTarget && handleDeleteReport(deleteTarget.tracking_id)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Org Profile dialog */}
      <Dialog open={showOrgDialog} onOpenChange={setShowOrgDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Organization Profile</DialogTitle>
            <DialogDescription>Set your org context to get personalized recommendations in reports.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Industry</label>
              <Input
                value={orgContext.industry}
                onChange={(e) => setOrgContext({ ...orgContext, industry: e.target.value })}
                placeholder="e.g., Financial Services, Healthcare, Retail"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Tech Stack</label>
              <div className="flex gap-2 mt-1">
                <Input
                  value={orgStackInput}
                  onChange={(e) => setOrgStackInput(e.target.value)}
                  placeholder="e.g., Python, React, AWS"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && orgStackInput.trim()) {
                      setOrgContext({ ...orgContext, tech_stack: [...orgContext.tech_stack, orgStackInput.trim()] });
                      setOrgStackInput('');
                    }
                  }}
                />
                <Button size="sm" variant="outline" onClick={() => {
                  if (orgStackInput.trim()) {
                    setOrgContext({ ...orgContext, tech_stack: [...orgContext.tech_stack, orgStackInput.trim()] });
                    setOrgStackInput('');
                  }
                }}>
                  <Plus className="w-3 h-3" />
                </Button>
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                {orgContext.tech_stack.map((t, i) => (
                  <Badge key={i} variant="secondary" className="text-xs gap-1">
                    {t}
                    <XCircle className="w-3 h-3 cursor-pointer" onClick={() =>
                      setOrgContext({ ...orgContext, tech_stack: orgContext.tech_stack.filter((_, j) => j !== i) })
                    } />
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium">Strategic Priorities</label>
              <div className="flex gap-2 mt-1">
                <Input
                  value={orgPriorityInput}
                  onChange={(e) => setOrgPriorityInput(e.target.value)}
                  placeholder="e.g., Cost reduction, AI adoption"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && orgPriorityInput.trim()) {
                      setOrgContext({ ...orgContext, priorities: [...orgContext.priorities, orgPriorityInput.trim()] });
                      setOrgPriorityInput('');
                    }
                  }}
                />
                <Button size="sm" variant="outline" onClick={() => {
                  if (orgPriorityInput.trim()) {
                    setOrgContext({ ...orgContext, priorities: [...orgContext.priorities, orgPriorityInput.trim()] });
                    setOrgPriorityInput('');
                  }
                }}>
                  <Plus className="w-3 h-3" />
                </Button>
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                {orgContext.priorities.map((p, i) => (
                  <Badge key={i} variant="secondary" className="text-xs gap-1">
                    {p}
                    <XCircle className="w-3 h-3 cursor-pointer" onClick={() =>
                      setOrgContext({ ...orgContext, priorities: orgContext.priorities.filter((_, j) => j !== i) })
                    } />
                  </Badge>
                ))}
              </div>
            </div>
            {/* Radar Quadrant Customization */}
            <div>
              <label className="text-sm font-medium">Custom Radar Quadrants</label>
              <p className="text-xs text-muted-foreground mb-2">
                Customize radar quadrant names and colors. Leave defaults or set your own.
              </p>
              <div className="space-y-2">
                {(orgContext.radar_customization?.quadrants || [
                  { name: 'Techniques', color: '#1ebccd' },
                  { name: 'Platforms', color: '#f38a3e' },
                  { name: 'Tools', color: '#86b82a' },
                  { name: 'Languages & Frameworks', color: '#b32059' },
                ]).map((q, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      type="color"
                      value={q.color || '#888888'}
                      onChange={(e) => {
                        const quads = [...(orgContext.radar_customization?.quadrants || [
                          { name: 'Techniques', color: '#1ebccd' },
                          { name: 'Platforms', color: '#f38a3e' },
                          { name: 'Tools', color: '#86b82a' },
                          { name: 'Languages & Frameworks', color: '#b32059' },
                        ])];
                        quads[i] = { ...quads[i], color: e.target.value };
                        setOrgContext({ ...orgContext, radar_customization: { quadrants: quads } });
                      }}
                      className="w-8 h-8 rounded border cursor-pointer"
                    />
                    <Input
                      value={q.name}
                      onChange={(e) => {
                        const quads = [...(orgContext.radar_customization?.quadrants || [
                          { name: 'Techniques', color: '#1ebccd' },
                          { name: 'Platforms', color: '#f38a3e' },
                          { name: 'Tools', color: '#86b82a' },
                          { name: 'Languages & Frameworks', color: '#b32059' },
                        ])];
                        quads[i] = { ...quads[i], name: e.target.value };
                        setOrgContext({ ...orgContext, radar_customization: { quadrants: quads } });
                      }}
                      placeholder={`Quadrant ${i + 1} name`}
                      className="flex-1"
                    />
                  </div>
                ))}
              </div>
            </div>
            <DialogFooter>
              <Button onClick={handleSaveOrgContext}>Save Profile</Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* Deep Dive dialog */}
      <Dialog open={showDeepDiveDialog} onOpenChange={(open) => {
        setShowDeepDiveDialog(open);
        if (open) loadDeepDiveHistory();
      }}>
        <DialogContent className="max-w-3xl max-h-[85vh]">
          <DialogHeader>
            <DialogTitle>Technology Deep Dive</DialogTitle>
            <DialogDescription>In-depth analysis of the selected technology.</DialogDescription>
          </DialogHeader>
          {deepDiveLoading ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Running deep dive analysis...</p>
              <p className="text-xs text-muted-foreground">This may take a few minutes.</p>
            </div>
          ) : deepDiveResult ? (
            <SensingDeepDive
              report={deepDiveResult}
              trackingId={deepDiveTrackingId || undefined}
              domain={domain}
              deepDiveHistory={deepDiveHistory}
              onLoadDeepDive={handleLoadDeepDive}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Collaboration dialog */}
      <Dialog open={showCollabDialog} onOpenChange={setShowCollabDialog}>
        <DialogContent className="max-w-3xl max-h-[85vh]">
          <DialogHeader>
            <DialogTitle>Collaborate on Report</DialogTitle>
            <DialogDescription>Share, vote on ring placements, and discuss technologies.</DialogDescription>
          </DialogHeader>
          {shareId && reportData ? (
            <SensingCollaboration
              shareId={shareId}
              radarItems={reportData.report.radar_items || []}
            />
          ) : (
            <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin" /></div>
          )}
        </DialogContent>
      </Dialog>
      </div>
    </div>
  );
};

export default TechSensing;
