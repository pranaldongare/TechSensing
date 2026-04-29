import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import SafeMarkdownRenderer from '@/components/SafeMarkdownRenderer';
import {
  ChevronDown, ChevronRight, ExternalLink, Clock, TrendingUp,
  Lightbulb, FileText, Building2, Cpu, Target, Newspaper, Link2, Play,
  ThumbsUp, ThumbsDown, RefreshCw, Loader2, AlertTriangle, ArrowUp,
  ArrowDown, Minus, Info, Zap, Network, Database, Edit3, LayoutGrid, Download,
} from 'lucide-react';
import { api } from '@/lib/api';
import type {
  SensingReport, SensingRadarItem, SensingRadarItemDetail, SensingMarketSignal,
  SensingHeadlineMove, SensingTrendingVideo, SensingTopEvent, SensingBlindSpot,
  TopicPreferences, ModelRelease, Annotation, OnepagerCard,
} from '@/lib/api';
import { downloadOnepagerPptx } from '@/lib/sensing-onepager-pptx';
import { downloadOnepagerPdf } from '@/lib/sensing-onepager-pdf';
import SensingRelationshipGraph from '@/components/SensingRelationshipGraph';

interface Meta {
  tracking_id: string;
  domain: string;
  raw_article_count: number;
  deduped_article_count: number;
  classified_article_count: number;
  execution_time_seconds: number;
  generated_at: string;
}

interface SensingReportRendererProps {
  report: SensingReport;
  meta: Meta;
  highlightTechnology?: string;
  onDeepDive?: (technologyName: string) => void;
  topicPreferences?: TopicPreferences | null;
  onTopicInterest?: (techName: string, interest: 'interested' | 'not_interested' | 'neutral') => void;
  onSourceFeedback?: (sourceName: string, vote: 'up' | 'down') => void;
  annotations?: Record<string, Annotation>;
  onAnnotate?: (key: string, note: string) => void;
}

const impactColors: Record<string, string> = {
  'High': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  'Medium': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  'Low': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
};

const priorityColors: Record<string, string> = {
  'Critical': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  'High': 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  'Medium': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  'Low': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
};

const ringColors: Record<string, string> = {
  'Adopt': 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  'Trial': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  'Assess': 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  'Hold': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

const eventTypeColors: Record<string, string> = {
  'product_launch': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  'partnership': 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  'funding': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  'regulation': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  'research': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  'strategic_move': 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
};

const effortColors: Record<string, string> = {
  'Low': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  'Medium': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  'High': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

const urgencyColors: Record<string, string> = {
  'Immediate': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  'Short-term': 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  'Medium-term': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  'Long-term': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
};

const MomentumIcon: React.FC<{ momentum?: string }> = ({ momentum }) => {
  if (momentum === 'rising') return <ArrowUp className="w-3 h-3 text-green-600" />;
  if (momentum === 'declining') return <ArrowDown className="w-3 h-3 text-red-600" />;
  return <Minus className="w-3 h-3 text-gray-400" />;
};

const RING_ORDER = ['Adopt', 'Trial', 'Assess', 'Hold'];

const formatViewCount = (count: number): string => {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M views`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K views`;
  return `${count} views`;
};

/** Compact inline source links — renders [1] [2] [3] badges linking to article URLs */
const SourceLinks: React.FC<{ urls?: string[] }> = ({ urls }) => {
  if (!urls?.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1 mt-2">
      <Link2 className="w-3 h-3 text-muted-foreground shrink-0" />
      <span className="text-[10px] text-muted-foreground mr-0.5">Sources:</span>
      {urls.map((url, i) => (
        <a
          key={i}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          title={url}
          className="inline-flex items-center justify-center w-5 h-5 rounded text-[10px] font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50 transition-colors"
        >
          {i + 1}
        </a>
      ))}
    </div>
  );
};

const SensingReportRenderer: React.FC<SensingReportRendererProps> = ({ report, meta, highlightTechnology, onDeepDive, topicPreferences, onTopicInterest, onSourceFeedback, annotations, onAnnotate }) => {
  const [expandedTrends, setExpandedTrends] = useState<Set<number>>(new Set());
  const [expandedRadarDetails, setExpandedRadarDetails] = useState<Set<number>>(new Set());
  const [expandedSignals, setExpandedSignals] = useState<Set<number>>(new Set());
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());
  const [editingAnnotation, setEditingAnnotation] = useState<string | null>(null);
  const [annotationDraft, setAnnotationDraft] = useState('');

  const [showRelationships, setShowRelationships] = useState(false);
  const [showProvenance, setShowProvenance] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // One-pager state
  const [onepagerOpen, setOnepagerOpen] = useState(false);
  const [onepagerSelected, setOnepagerSelected] = useState<Set<number>>(new Set());
  const [onepagerLoading, setOnepagerLoading] = useState(false);

  // Auto-expand and scroll to highlighted technology
  useEffect(() => {
    if (!highlightTechnology || !report.radar_item_details) return;
    const idx = report.radar_item_details.findIndex(
      d => d.technology_name.toLowerCase() === highlightTechnology.toLowerCase()
    );
    if (idx >= 0) {
      setExpandedRadarDetails(prev => new Set(prev).add(idx));
      // Delay scroll to allow expansion render
      setTimeout(() => {
        const el = document.getElementById(`radar-detail-${idx}`);
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 100);
    }
  }, [highlightTechnology, report.radar_item_details]);

  const toggleSet = (setter: React.Dispatch<React.SetStateAction<Set<number>>>, idx: number) => {
    setter(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  // ── One-pager helpers ──
  const toggleOnepagerSelection = (idx: number) => {
    setOnepagerSelected(prev => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else if (next.size < 8) {
        next.add(idx);
      }
      return next;
    });
  };

  const handleOnepagerGenerate = async (format: 'pptx' | 'pdf') => {
    if (onepagerSelected.size === 0 || !report.top_events) return;
    setOnepagerLoading(true);
    try {
      const indices = Array.from(onepagerSelected).sort((a, b) => a - b);
      const result = await api.sensingOnepager(meta.tracking_id, indices);

      // Enrich cards with source_url and actor from original events
      const enrichedCards: OnepagerCard[] = result.cards.map((card, i) => {
        const origIdx = indices[i];
        const orig = report.top_events![origIdx];
        return {
          ...card,
          source_url: orig?.source_urls?.[0] || '',
          actor: orig?.actor || '',
        };
      });

      if (format === 'pptx') {
        await downloadOnepagerPptx(enrichedCards, result.domain, result.date_range);
      } else {
        await downloadOnepagerPdf(enrichedCards, result.domain, result.date_range);
      }
      setOnepagerOpen(false);
    } catch (e) {
      console.error('One-pager generation failed:', e);
    } finally {
      setOnepagerLoading(false);
    }
  };

  return (
    <ScrollArea className="h-full">
      <div className="space-y-8 py-2 px-1 max-w-5xl mx-auto">
        {/* Report Title + Meta */}
        <div>
          <h2 className="text-xl font-bold mb-2">{report.report_title}</h2>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">{report.domain}</Badge>
            <Badge variant="outline">{report.date_range}</Badge>
            <Badge variant="outline">{report.total_articles_analyzed} articles analyzed</Badge>
            <Badge variant="outline">{Math.round(meta.execution_time_seconds / 60)}m generation time</Badge>
            {report.report_confidence && (
              <Badge variant={report.report_confidence === 'high' ? 'default' : report.report_confidence === 'medium' ? 'secondary' : 'destructive'}>
                Confidence: {report.report_confidence}
              </Badge>
            )}
          </div>
        </div>

        {/* Confidence Note */}
        {report.confidence_note && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-900/30 border border-slate-200 dark:border-slate-800 text-xs text-muted-foreground">
            <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-500" />
            <span>{report.confidence_note}</span>
          </div>
        )}

        {/* Bottom Line */}
        {report.bottom_line && (
          <Card className="border-l-4 border-l-rose-600 bg-rose-50/50 dark:bg-rose-950/20">
            <CardContent className="py-4">
              <div className="flex items-start gap-3">
                <Zap className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold text-rose-800 dark:text-rose-300 mb-1">Bottom Line</h3>
                  <p className="text-sm text-foreground">{report.bottom_line}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Executive Summary */}
        <Card className="border-l-4 border-l-blue-600">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-600" />
              Executive Summary
            </CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm dark:prose-invert max-w-none">
            <SafeMarkdownRenderer content={report.executive_summary} />
            {report.topic_highlights && report.topic_highlights.length > 0 && (
              <div className="not-prose mt-4 pt-3 border-t">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">At a Glance</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {report.topic_highlights.map((th, idx) => (
                    <div key={idx} className="flex items-start gap-2 p-2 rounded-md bg-blue-50/50 dark:bg-blue-950/20">
                      <Badge variant="secondary" className="text-[10px] shrink-0 mt-0.5">{th.topic}</Badge>
                      <span className="text-xs text-muted-foreground leading-relaxed">{th.update}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top Events (v2.0) or Headline Moves (legacy) */}
        {report.top_events && report.top_events.length > 0 ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-orange-500" />
                Top {report.top_events.length} Events
              </h3>
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setOnepagerSelected(new Set()); setOnepagerOpen(true); }}
              >
                <LayoutGrid className="w-4 h-4 mr-1.5" />
                One-Pager
              </Button>
            </div>
            {report.top_events.map((event: SensingTopEvent, idx: number) => (
              <Card key={idx} className="overflow-hidden border-l-4 border-l-orange-400">
                <button
                  onClick={() => toggleSet(setExpandedEvents, idx)}
                  className="w-full text-left p-4 flex items-start justify-between hover:bg-muted/50 transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 text-xs font-bold flex items-center justify-center">
                        {idx + 1}
                      </span>
                      <span className="font-medium text-sm">{event.headline}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <Badge variant="outline" className="text-xs">{event.actor}</Badge>
                      <Badge className={eventTypeColors[event.event_type] || 'bg-gray-100'} variant="secondary">
                        {event.event_type?.replace('_', ' ')}
                      </Badge>
                      {event.segment && (
                        <Badge variant="secondary" className="text-xs">{event.segment}</Badge>
                      )}
                    </div>
                  </div>
                  {expandedEvents.has(idx) ? (
                    <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  )}
                </button>
                {expandedEvents.has(idx) && (
                  <div className="px-4 pb-4 border-t space-y-3 mt-0">
                    {event.impact_summary && (
                      <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3 mt-3">
                        <h5 className="text-xs font-semibold text-orange-700 dark:text-orange-300 mb-1">Impact</h5>
                        <p className="text-sm text-muted-foreground">{event.impact_summary}</p>
                      </div>
                    )}
                    {event.strategic_intent && (
                      <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3">
                        <h5 className="text-xs font-semibold text-orange-700 dark:text-orange-300 mb-1">Strategic Intent</h5>
                        <p className="text-sm text-muted-foreground">{event.strategic_intent}</p>
                      </div>
                    )}
                    {event.recommendation && (
                      <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg p-3 flex items-start gap-2">
                        <Lightbulb className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
                        <div>
                          <h5 className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 mb-0.5">Recommendation</h5>
                          <p className="text-sm text-muted-foreground">{event.recommendation}</p>
                        </div>
                      </div>
                    )}
                    {event.related_technologies?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        <span className="text-xs font-medium text-muted-foreground">Related:</span>
                        {event.related_technologies.map((t, i) => (
                          <Badge key={i} variant="outline" className="text-xs">{t}</Badge>
                        ))}
                      </div>
                    )}
                    <SourceLinks urls={event.source_urls} />
                  </div>
                )}
              </Card>
            ))}
          </div>
        ) : report.headline_moves && report.headline_moves.length > 0 ? (
          <Card className="border-l-4 border-l-orange-500">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-orange-500" />
                Top {report.headline_moves.length} Headline Moves
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3">
                {report.headline_moves.map((move: SensingHeadlineMove, idx: number) => (
                  <li key={idx} className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 text-xs font-bold flex items-center justify-center mt-0.5">
                      {idx + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm">{move.headline}</p>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <Badge variant="outline" className="text-xs">{move.actor}</Badge>
                        {move.segment && (
                          <Badge variant="secondary" className="text-xs">{move.segment}</Badge>
                        )}
                        <SourceLinks urls={move.source_urls} />
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        ) : null}

        {/* Key Trends */}
        {report.key_trends?.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-amber-600" />
              Key Trends ({report.key_trends.length})
            </h3>
            {report.key_trends.map((trend, idx) => (
              <Card key={idx} className="overflow-hidden">
                <button
                  onClick={() => toggleSet(setExpandedTrends, idx)}
                  className="w-full text-left p-4 flex items-start justify-between hover:bg-muted/50 transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{trend.trend_name}</span>
                      <Badge className={impactColors[trend.impact_level] || 'bg-gray-100'} variant="secondary">
                        {trend.impact_level}
                      </Badge>
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {trend.time_horizon}
                      </span>
                    </div>
                  </div>
                  {expandedTrends.has(idx) ? (
                    <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  )}
                </button>
                {expandedTrends.has(idx) && (
                  <div className="px-4 pb-4 border-t">
                    <p className="text-sm mt-3 text-muted-foreground">{trend.description}</p>
                    {trend.deep_dive ? (
                      <div className="mt-3 prose prose-sm dark:prose-invert max-w-none border-l-2 border-amber-300 pl-3">
                        <SafeMarkdownRenderer content={trend.deep_dive} />
                      </div>
                    ) : trend.evidence?.length > 0 ? (
                      <div className="mt-3">
                        <span className="text-xs font-medium">Evidence:</span>
                        <ul className="list-disc list-inside text-xs text-muted-foreground mt-1 space-y-0.5">
                          {trend.evidence.map((e, i) => (
                            <li key={i}>{e}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <SourceLinks urls={trend.source_urls} />
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}

        {/* Market Signals (legacy — hidden when top_events present) */}
        {!(report.top_events && report.top_events.length > 0) && report.market_signals?.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Building2 className="w-5 h-5 text-violet-600" />
              Market Signals ({report.market_signals.length})
            </h3>
            <p className="text-sm text-muted-foreground -mt-1">
              What prominent players are doing and where the industry is heading.
            </p>
            {report.market_signals.map((signal: SensingMarketSignal, idx: number) => (
              <Card key={idx} className="overflow-hidden border-l-4 border-l-violet-400">
                <button
                  onClick={() => toggleSet(setExpandedSignals, idx)}
                  className="w-full text-left p-4 flex items-start justify-between hover:bg-muted/50 transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-violet-700 dark:text-violet-300">
                        {signal.company_or_player}
                      </span>
                      {signal.segment && (
                        <Badge variant="secondary" className="text-xs">{signal.segment}</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{signal.signal}</p>
                  </div>
                  {expandedSignals.has(idx) ? (
                    <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  )}
                </button>
                {expandedSignals.has(idx) && (
                  <div className="px-4 pb-4 border-t space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                      <div className="bg-violet-50 dark:bg-violet-900/20 rounded-lg p-3">
                        <h5 className="text-xs font-semibold text-violet-700 dark:text-violet-300 mb-1">
                          Strategic Intent
                        </h5>
                        <p className="text-sm text-muted-foreground">{signal.strategic_intent}</p>
                      </div>
                      <div className="bg-violet-50 dark:bg-violet-900/20 rounded-lg p-3">
                        <h5 className="text-xs font-semibold text-violet-700 dark:text-violet-300 mb-1">
                          Industry Impact
                        </h5>
                        <p className="text-sm text-muted-foreground">{signal.industry_impact}</p>
                      </div>
                    </div>
                    {signal.related_technologies?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        <span className="text-xs font-medium text-muted-foreground">Related:</span>
                        {signal.related_technologies.map((t, i) => (
                          <Badge key={i} variant="outline" className="text-xs">{t}</Badge>
                        ))}
                      </div>
                    )}
                    <SourceLinks urls={signal.source_urls} />
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}

        {/* Latest Model Releases (GenAI domains only) */}
        {report.model_releases && report.model_releases.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Cpu className="w-5 h-5 text-purple-600" />
                Latest Model Releases ({report.model_releases.length})
              </h3>
              <RefreshModelReleasesButton trackingId={meta.tracking_id} onRefresh={(releases) => { report.model_releases = releases; }} />
            </div>
            <p className="text-sm text-muted-foreground -mt-1">
              Recent AI model announcements and releases.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b text-left">
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Model</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Organization</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Date</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Status</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Parameters</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Type</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Modality</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">Source</th>
                    <th className="py-2 pr-3 font-semibold text-xs text-muted-foreground">License</th>
                    <th className="py-2 font-semibold text-xs text-muted-foreground">Notable Features</th>
                  </tr>
                </thead>
                <tbody>
                  {report.model_releases.map((mr: ModelRelease, idx: number) => (
                    <tr key={idx} className="border-b last:border-b-0 hover:bg-muted/50 transition-colors">
                      <td className="py-2 pr-3 font-medium">
                        {mr.source_url ? (
                          <a
                            href={mr.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-purple-700 dark:text-purple-300 hover:underline flex items-center gap-1"
                          >
                            {mr.model_name}
                            <ExternalLink className="w-3 h-3 shrink-0" />
                          </a>
                        ) : (
                          mr.model_name
                        )}
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground">{mr.organization}</td>
                      <td className="py-2 pr-3 text-muted-foreground whitespace-nowrap">{mr.release_date}</td>
                      <td className="py-2 pr-3">
                        {(() => {
                          const st = (mr.release_status || 'Unknown').trim();
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
                          return (
                            <Badge variant="outline" className={`text-xs whitespace-nowrap ${cls}`}>{st}</Badge>
                          );
                        })()}
                      </td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline" className="text-xs font-mono">{mr.parameters}</Badge>
                      </td>
                      <td className="py-2 pr-3">
                        <Badge variant="secondary" className="text-xs">{mr.model_type}</Badge>
                      </td>
                      <td className="py-2 pr-3">
                        <Badge variant="secondary" className="text-xs">{mr.modality}</Badge>
                      </td>
                      <td className="py-2 pr-3">
                        {(() => {
                          const src = (mr.is_open_source || 'Unknown').trim();
                          const cls =
                            src === 'Open'
                              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200 border-emerald-300'
                              : src === 'Closed'
                              ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200 border-rose-300'
                              : src === 'Mixed'
                              ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 border-amber-300'
                              : 'bg-muted text-muted-foreground';
                          return (
                            <Badge variant="outline" className={`text-xs ${cls}`}>{src}</Badge>
                          );
                        })()}
                      </td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline" className="text-xs">{mr.license}</Badge>
                      </td>
                      <td className="py-2 text-xs text-muted-foreground max-w-xs">{mr.notable_features}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Technology Deep Dives (Radar Item Details) */}
        {report.radar_item_details?.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Cpu className="w-5 h-5 text-emerald-600" />
              Technology Deep Dives ({report.radar_item_details.length})
            </h3>
            <p className="text-sm text-muted-foreground -mt-1">
              Detailed analysis of each technology on the radar.
            </p>
            {report.radar_item_details.map((item: SensingRadarItemDetail, idx: number) => {
              const radarItem = report.radar_items?.find(r => r.name === item.technology_name);
              return (
                <Card key={idx} id={`radar-detail-${idx}`} className={`overflow-hidden border-l-4 border-l-emerald-400${highlightTechnology?.toLowerCase() === item.technology_name.toLowerCase() ? ' ring-2 ring-emerald-400' : ''}`}>
                  <button
                    onClick={() => toggleSet(setExpandedRadarDetails, idx)}
                    className="w-full text-left p-4 flex items-start justify-between hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold">{item.technology_name}</span>
                        {radarItem && (
                          <>
                            <Badge className={ringColors[radarItem.ring] || 'bg-gray-100'} variant="secondary">
                              {radarItem.ring}
                            </Badge>
                            {radarItem.momentum && (
                              <span className="flex items-center gap-0.5" title={`Momentum: ${radarItem.momentum}`}>
                                <MomentumIcon momentum={radarItem.momentum} />
                                <span className="text-[10px] text-muted-foreground capitalize">{radarItem.momentum}</span>
                              </span>
                            )}
                            <Badge variant="outline" className="text-xs">{radarItem.quadrant}</Badge>
                            {radarItem.trl && (
                              <Badge variant="outline" className="text-xs font-mono">TRL {radarItem.trl}</Badge>
                            )}
                            {(radarItem.patent_count ?? 0) > 0 && (
                              <Badge variant="outline" className="text-xs font-mono text-blue-600 dark:text-blue-400 border-blue-300 dark:border-blue-700">
                                {radarItem.patent_count} {radarItem.patent_count === 1 ? 'patent' : 'patents'}
                              </Badge>
                            )}
                            {radarItem.lifecycle_stage && (
                              <Badge variant="outline" className="text-xs capitalize text-violet-600 dark:text-violet-400 border-violet-300 dark:border-violet-700">
                                {radarItem.lifecycle_stage.replace('_', ' ')}
                              </Badge>
                            )}
                            {radarItem.funding_signal && (
                              <Badge variant="outline" className="text-xs text-green-600 dark:text-green-400 border-green-300 dark:border-green-700">
                                $ Funded
                              </Badge>
                            )}
                            {radarItem.moved_in && (
                              <Badge className="bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300" variant="secondary">
                                {RING_ORDER.indexOf(radarItem.ring) < RING_ORDER.indexOf(radarItem.moved_in) ? '\u2191' : '\u2193'} Moved from {radarItem.moved_in}
                              </Badge>
                            )}
                          </>
                        )}
                        {onTopicInterest && (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                const isActive = topicPreferences?.interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase());
                                onTopicInterest(item.technology_name, isActive ? 'neutral' : 'interested');
                              }}
                              title="Interested"
                              className={`p-0.5 rounded transition-colors ${
                                topicPreferences?.interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase())
                                  ? 'text-emerald-600'
                                  : 'text-muted-foreground/40 hover:text-emerald-600'
                              }`}
                            >
                              <ThumbsUp className="w-3 h-3" />
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                const isActive = topicPreferences?.not_interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase());
                                onTopicInterest(item.technology_name, isActive ? 'neutral' : 'not_interested');
                              }}
                              title="Not interested"
                              className={`p-0.5 rounded transition-colors ${
                                topicPreferences?.not_interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase())
                                  ? 'text-red-600'
                                  : 'text-muted-foreground/40 hover:text-red-600'
                              }`}
                            >
                              <ThumbsDown className="w-3 h-3" />
                            </button>
                          </>
                        )}
                      </div>
                      {!expandedRadarDetails.has(idx) && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{item.what_it_is}</p>
                      )}
                    </div>
                    {expandedRadarDetails.has(idx) ? (
                      <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                    )}
                  </button>
                  {expandedRadarDetails.has(idx) && (
                    <div className="px-4 pb-4 border-t space-y-4 mt-3">
                      <div>
                        <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-1">What It Is</h5>
                        <p className="text-sm text-muted-foreground">{item.what_it_is}</p>
                      </div>
                      <div>
                        <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-1">Why It Matters</h5>
                        <p className="text-sm text-muted-foreground">{item.why_it_matters}</p>
                      </div>
                      <div>
                        <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-1">Current State</h5>
                        <p className="text-sm text-muted-foreground">{item.current_state}</p>
                      </div>
                      {item.key_players?.length > 0 && (
                        <div>
                          <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-1">Key Players</h5>
                          <div className="flex flex-wrap gap-1.5">
                            {item.key_players.map((p, i) => (
                              <Badge key={i} variant="outline" className="text-xs">{p}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {item.practical_applications?.length > 0 && (
                        <div>
                          <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-1">
                            Practical Applications
                          </h5>
                          <ul className="list-disc list-inside text-sm text-muted-foreground space-y-0.5">
                            {item.practical_applications.map((a, i) => (
                              <li key={i}>{a}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {item.quantitative_highlights && item.quantitative_highlights.length > 0 && (
                        <div className="p-2.5 rounded bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/50 dark:border-amber-800/30">
                          <h5 className="text-xs font-semibold text-amber-700 dark:text-amber-300 mb-1.5">
                            Key Numbers & Metrics
                          </h5>
                          <ul className="space-y-1">
                            {item.quantitative_highlights.map((q, i) => (
                              <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                                <span className="text-amber-600 font-bold mt-px shrink-0">#</span>
                                <span>{q}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {item.hiring_indicators && (
                        <div className="flex items-start gap-2 p-2 rounded bg-blue-50/50 dark:bg-blue-950/20">
                          <Building2 className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                          <div>
                            <h5 className="text-xs font-semibold text-blue-700 dark:text-blue-300 mb-0.5">
                              Hiring Indicators
                            </h5>
                            <p className="text-xs text-muted-foreground">{item.hiring_indicators}</p>
                          </div>
                        </div>
                      )}
                      {item.recommendation && (
                        <div className="flex items-start gap-2 p-2.5 rounded bg-indigo-50/50 dark:bg-indigo-950/20 border border-indigo-200/50 dark:border-indigo-800/30">
                          <Lightbulb className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
                          <div>
                            <h5 className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 mb-0.5">
                              Recommendation
                            </h5>
                            <p className="text-xs text-muted-foreground">{item.recommendation}</p>
                          </div>
                        </div>
                      )}
                      {/* Annotation */}
                      {(() => {
                        const aKey = `${meta.tracking_id}:radar:${item.technology_name}`;
                        const existing = annotations?.[aKey];
                        const isEditing = editingAnnotation === aKey;
                        return (
                          <div className="mt-1">
                            {existing && !isEditing && (
                              <div className="flex items-start gap-2 p-2 rounded bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800">
                                <Edit3 className="w-3.5 h-3.5 text-yellow-600 shrink-0 mt-0.5" />
                                <p className="text-xs text-yellow-800 dark:text-yellow-200 flex-1">{existing.note}</p>
                                {onAnnotate && (
                                  <button
                                    className="text-xs text-yellow-600 hover:underline shrink-0"
                                    onClick={(e) => { e.stopPropagation(); setEditingAnnotation(aKey); setAnnotationDraft(existing.note); }}
                                  >Edit</button>
                                )}
                              </div>
                            )}
                            {isEditing && onAnnotate && (
                              <div className="flex gap-2 mt-1" onClick={(e) => e.stopPropagation()}>
                                <input
                                  className="flex-1 text-xs border rounded px-2 py-1"
                                  value={annotationDraft}
                                  onChange={(e) => setAnnotationDraft(e.target.value)}
                                  placeholder="Add a note..."
                                  autoFocus
                                  onKeyDown={(e) => { if (e.key === 'Enter') { onAnnotate(aKey, annotationDraft); setEditingAnnotation(null); } if (e.key === 'Escape') setEditingAnnotation(null); }}
                                />
                                <button
                                  className="text-xs text-primary hover:underline"
                                  onClick={() => { onAnnotate(aKey, annotationDraft); setEditingAnnotation(null); }}
                                >Save</button>
                                <button
                                  className="text-xs text-muted-foreground hover:underline"
                                  onClick={() => setEditingAnnotation(null)}
                                >Cancel</button>
                              </div>
                            )}
                            {!existing && !isEditing && onAnnotate && (
                              <button
                                className="text-xs text-muted-foreground/60 hover:text-muted-foreground flex items-center gap-1 mt-1"
                                onClick={(e) => { e.stopPropagation(); setEditingAnnotation(aKey); setAnnotationDraft(''); }}
                              >
                                <Edit3 className="w-3 h-3" /> Add note
                              </button>
                            )}
                          </div>
                        );
                      })()}
                      <SourceLinks urls={item.source_urls} />
                      {(() => {
                        const videos = report.trending_videos?.filter(
                          (v: SensingTrendingVideo) => v.technology_name === item.technology_name
                        );
                        if (!videos?.length) return null;
                        return (
                          <div>
                            <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-2 flex items-center gap-1">
                              <Play className="w-3 h-3" />
                              Trending Videos
                            </h5>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {videos.map((video: SensingTrendingVideo, vi: number) => (
                                <a
                                  key={vi}
                                  href={video.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="group block rounded-lg border bg-card hover:bg-muted/50 transition-colors overflow-hidden"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {video.thumbnail_url && (
                                    <div className="relative aspect-video bg-muted">
                                      <img
                                        src={video.thumbnail_url}
                                        alt={video.title}
                                        className="w-full h-full object-cover"
                                        loading="lazy"
                                      />
                                      {video.duration && (
                                        <span className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] px-1 py-0.5 rounded">
                                          {video.duration}
                                        </span>
                                      )}
                                    </div>
                                  )}
                                  <div className="p-2">
                                    <p className="text-xs font-medium line-clamp-2 group-hover:text-emerald-600 transition-colors">
                                      {video.title}
                                    </p>
                                    <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                                      {video.uploader && <span>{video.uploader}</span>}
                                      {video.view_count > 0 && (
                                        <span>{formatViewCount(video.view_count)}</span>
                                      )}
                                    </div>
                                  </div>
                                </a>
                              ))}
                            </div>
                          </div>
                        );
                      })()}
                      <div className="flex items-center gap-3 mt-2">
                        {onDeepDive && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onDeepDive(item.technology_name); }}
                            className="text-xs text-emerald-600 hover:text-emerald-700 font-medium flex items-center gap-1"
                          >
                            <Target className="w-3 h-3" />
                            Deep Dive Analysis
                          </button>
                        )}
                        {onTopicInterest && (
                          <div className="flex items-center gap-1 ml-auto">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                const isActive = topicPreferences?.interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase());
                                onTopicInterest(item.technology_name, isActive ? 'neutral' : 'interested');
                              }}
                              title="Interested — boost in future reports"
                              className={`p-1 rounded transition-colors ${
                                topicPreferences?.interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase())
                                  ? 'text-emerald-600 bg-emerald-100 dark:bg-emerald-900/30'
                                  : 'text-muted-foreground hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20'
                              }`}
                            >
                              <ThumbsUp className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                const isActive = topicPreferences?.not_interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase());
                                onTopicInterest(item.technology_name, isActive ? 'neutral' : 'not_interested');
                              }}
                              title="Not interested — suppress in future reports"
                              className={`p-1 rounded transition-colors ${
                                topicPreferences?.not_interested.some(t => t.toLowerCase() === item.technology_name.toLowerCase())
                                  ? 'text-red-600 bg-red-100 dark:bg-red-900/30'
                                  : 'text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20'
                              }`}
                            >
                              <ThumbsDown className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}

        {/* Report Sections (Detailed Analysis) */}
        {report.report_sections?.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Target className="w-5 h-5 text-sky-600" />
              Detailed Analysis
            </h3>
            {report.report_sections.map((section, idx) => (
              <Card key={idx}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{section.section_title}</CardTitle>
                </CardHeader>
                <CardContent className="prose prose-sm dark:prose-invert max-w-none">
                  <SafeMarkdownRenderer content={section.content} />
                  <SourceLinks urls={section.source_urls} />
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Recommendations */}
        {report.recommendations?.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-orange-500" />
              Recommendations
            </h3>
            {report.recommendations.map((rec, idx) => (
              <Card key={idx} className="p-4">
                <div className="flex items-start gap-3">
                  <Badge
                    className={priorityColors[rec.priority] || 'bg-gray-100'}
                    variant="secondary"
                  >
                    {rec.priority}
                  </Badge>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="font-medium">{rec.title}</h4>
                      {rec.effort && (
                        <Badge className={effortColors[rec.effort] || 'bg-gray-100'} variant="secondary">
                          {rec.effort} effort
                        </Badge>
                      )}
                      {rec.urgency && (
                        <Badge className={urgencyColors[rec.urgency] || 'bg-gray-100'} variant="secondary">
                          {rec.urgency}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">{rec.description}</p>
                    {rec.rationale && (
                      <p className="text-xs text-muted-foreground mt-2 italic border-l-2 border-orange-300 pl-2">
                        {rec.rationale}
                      </p>
                    )}
                    {rec.related_trends?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {rec.related_trends.map((t, i) => (
                          <Badge key={i} variant="outline" className="text-xs">{t}</Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Blind Spots */}
        {report.blind_spots && report.blind_spots.length > 0 && (
          <Card className="border-l-4 border-l-yellow-500 bg-yellow-50/50 dark:bg-yellow-950/20">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-yellow-600" />
                Coverage Blind Spots ({report.blind_spots.length})
              </CardTitle>
              <p className="text-xs text-muted-foreground">
                Topics, regions, or perspectives that may be underrepresented in this report.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              {report.blind_spots.map((spot: SensingBlindSpot, idx: number) => (
                <div key={idx} className="flex items-start gap-3 p-3 rounded-lg bg-yellow-100/50 dark:bg-yellow-900/20">
                  <AlertTriangle className="w-4 h-4 text-yellow-600 shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <h5 className="text-sm font-medium">{spot.area}</h5>
                    <p className="text-xs text-muted-foreground mt-1">{spot.why_it_matters}</p>
                    {spot.suggested_sources?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        <span className="text-[10px] text-muted-foreground">Look at:</span>
                        {spot.suggested_sources.map((s, i) => (
                          <Badge key={i} variant="outline" className="text-[10px]">{s}</Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Technology Relationships */}
        {report.relationships && report.relationships.relationships?.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <button
                onClick={() => setShowRelationships(!showRelationships)}
                className="flex items-center gap-2 w-full text-left"
              >
                {showRelationships ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                <CardTitle className="text-lg flex items-center gap-2">
                  <Network className="w-5 h-5 text-indigo-600" />
                  Technology Relationships
                </CardTitle>
              </button>
            </CardHeader>
            {showRelationships && (
              <CardContent>
                <div className="h-[500px]">
                  <SensingRelationshipGraph
                    relationships={report.relationships}
                    radarItems={report.radar_items || []}
                  />
                </div>
              </CardContent>
            )}
          </Card>
        )}

        {/* Notable Articles */}
        {report.notable_articles?.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Newspaper className="w-5 h-5 text-slate-600" />
              Notable Articles
            </h3>
            <div className="space-y-2">
              {report.notable_articles.map((article, idx) => (
                <Card key={idx} className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-medium hover:underline flex items-center gap-1"
                      >
                        {article.title}
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <Badge variant="outline" className="text-xs">{article.source}</Badge>
                        {onSourceFeedback && (
                          <>
                            <button onClick={() => onSourceFeedback(article.source, 'up')} title="Good source" className="p-0.5 text-muted-foreground/40 hover:text-emerald-600 transition-colors">
                              <ThumbsUp className="w-3 h-3" />
                            </button>
                            <button onClick={() => onSourceFeedback(article.source, 'down')} title="Poor source" className="p-0.5 text-muted-foreground/40 hover:text-red-600 transition-colors">
                              <ThumbsDown className="w-3 h-3" />
                            </button>
                          </>
                        )}
                        <Badge variant="outline" className="text-xs">{article.quadrant}</Badge>
                        <Badge className={ringColors[article.ring] || 'bg-gray-100'} variant="secondary">
                          {article.ring}
                        </Badge>
                        {article.topic_category && (
                          <Badge variant="secondary" className="text-xs">{article.topic_category}</Badge>
                        )}
                        {article.industry_segment && (
                          <Badge variant="secondary" className="text-xs">{article.industry_segment}</Badge>
                        )}
                        <span className="text-xs text-muted-foreground">
                          Score: {article.relevance_score?.toFixed(2)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{article.summary}</p>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Data Provenance */}
        <Card className="bg-muted/30">
          <CardHeader className="pb-2">
            <button
              onClick={() => setShowProvenance(!showProvenance)}
              className="flex items-center gap-2 w-full text-left"
            >
              {showProvenance ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground">
                <Database className="w-4 h-4" />
                Data Provenance
              </CardTitle>
            </button>
          </CardHeader>
          {showProvenance && (
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                <div>
                  <span className="text-muted-foreground block">Raw Articles</span>
                  <span className="font-medium">{meta.raw_article_count}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block">After Dedup</span>
                  <span className="font-medium">{meta.deduped_article_count}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block">Classified</span>
                  <span className="font-medium">{meta.classified_article_count}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block">Generation Time</span>
                  <span className="font-medium">{meta.execution_time_seconds}s</span>
                </div>
              </div>
              {report.confidence_factors && (
                <div className="mt-3 pt-3 border-t">
                  <span className="text-xs text-muted-foreground block mb-2">Confidence Factors</span>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                    {Object.entries(report.confidence_factors).map(([key, val]) => (
                      <div key={key}>
                        <span className="text-muted-foreground block capitalize">{key.replace(/_/g, ' ')}</span>
                        <span className="font-medium">{typeof val === 'number' ? val.toFixed(2) : String(val)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          )}
        </Card>
      </div>

      {/* One-Pager Topic Selection Dialog */}
      <Dialog open={onepagerOpen} onOpenChange={setOnepagerOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <LayoutGrid className="w-5 h-5" />
              Select Topics for One-Pager
            </DialogTitle>
            <DialogDescription>
              Choose up to 8 top events to include in the one-pager export. Selected: {onepagerSelected.size}/8
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto space-y-1 pr-2">
            {report.top_events?.map((event: SensingTopEvent, idx: number) => {
              const isSelected = onepagerSelected.has(idx);
              const isDisabled = !isSelected && onepagerSelected.size >= 8;
              return (
                <label
                  key={idx}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    isSelected ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50'
                  } ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <Checkbox
                    checked={isSelected}
                    disabled={isDisabled}
                    onCheckedChange={() => toggleOnepagerSelection(idx)}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 text-[10px] font-bold flex items-center justify-center">
                        {idx + 1}
                      </span>
                      <span className="font-medium text-sm truncate">{event.headline}</span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <Badge variant="outline" className="text-[10px] h-5">{event.actor}</Badge>
                      <Badge variant="secondary" className="text-[10px] h-5">
                        {event.event_type?.replace('_', ' ')}
                      </Badge>
                      {event.segment && (
                        <Badge variant="secondary" className="text-[10px] h-5">{event.segment}</Badge>
                      )}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
          <DialogFooter className="flex items-center gap-2 pt-3 border-t">
            <Button variant="ghost" onClick={() => setOnepagerOpen(false)} disabled={onepagerLoading}>
              Cancel
            </Button>
            <Button
              variant="outline"
              onClick={() => handleOnepagerGenerate('pdf')}
              disabled={onepagerSelected.size === 0 || onepagerLoading}
            >
              {onepagerLoading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Download className="w-4 h-4 mr-1.5" />}
              PDF
            </Button>
            <Button
              onClick={() => handleOnepagerGenerate('pptx')}
              disabled={onepagerSelected.size === 0 || onepagerLoading}
            >
              {onepagerLoading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Download className="w-4 h-4 mr-1.5" />}
              PPTX
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </ScrollArea>
  );
};

function RefreshModelReleasesButton({ trackingId, onRefresh }: { trackingId?: string; onRefresh: (releases: ModelRelease[]) => void }) {
  const [loading, setLoading] = useState(false);

  const handleRefresh = async () => {
    setLoading(true);
    try {
      const result = await api.sensingModelReleases(30, trackingId);
      onRefresh(result.model_releases);
    } catch {
      // silent fail — user can retry
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleRefresh}
      disabled={loading}
      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
      title="Refresh model releases from HuggingFace + blogs"
    >
      {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
      {loading ? 'Refreshing...' : 'Refresh'}
    </button>
  );
}

export default SensingReportRenderer;
