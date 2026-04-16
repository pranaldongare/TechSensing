import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import SafeMarkdownRenderer from '@/components/SafeMarkdownRenderer';
import {
  ChevronDown, ChevronRight, ExternalLink, Clock, TrendingUp,
  Lightbulb, FileText, Building2, Cpu, Target, Newspaper, Link2, Play, Zap,
  ThumbsUp, ThumbsDown,
} from 'lucide-react';
import type {
  SensingReport, SensingRadarItem, SensingRadarItemDetail, SensingMarketSignal,
  SensingHeadlineMove, SensingTrendingVideo, WeakSignal, TopicPreferences, ModelRelease,
} from '@/lib/api';

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

const SensingReportRenderer: React.FC<SensingReportRendererProps> = ({ report, meta, highlightTechnology, onDeepDive, topicPreferences, onTopicInterest, onSourceFeedback }) => {
  const [expandedTrends, setExpandedTrends] = useState<Set<number>>(new Set());
  const [expandedRadarDetails, setExpandedRadarDetails] = useState<Set<number>>(new Set());
  const [expandedSignals, setExpandedSignals] = useState<Set<number>>(new Set());
  const scrollContainerRef = useRef<HTMLDivElement>(null);

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
          </CardContent>
        </Card>

        {/* Headline Moves */}
        {report.headline_moves?.length > 0 && (
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
        )}

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
                    {trend.evidence?.length > 0 && (
                      <div className="mt-3">
                        <span className="text-xs font-medium">Evidence:</span>
                        <ul className="list-disc list-inside text-xs text-muted-foreground mt-1 space-y-0.5">
                          {trend.evidence.map((e, i) => (
                            <li key={i}>{e}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <SourceLinks urls={trend.source_urls} />
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}

        {/* Market Signals */}
        {report.market_signals?.length > 0 && (
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

        {/* Emerging Signals (Weak Signals) */}
        {report.weak_signals && report.weak_signals.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Zap className="w-5 h-5 text-orange-500" />
              Emerging Signals ({report.weak_signals.length})
            </h3>
            <p className="text-sm text-muted-foreground -mt-1">
              Technologies with low visibility but accelerating growth — potential breakouts.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {report.weak_signals.map((ws: WeakSignal, idx: number) => {
                const accelColor =
                  ws.acceleration_rate >= 3 ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' :
                  ws.acceleration_rate >= 2 ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' :
                  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300';
                // Sparkline from trajectory
                const pts = ws.trajectory || [];
                const maxCount = Math.max(...pts.map(p => p.article_count), 1);
                const sparkW = 80;
                const sparkH = 24;
                const sparkPoints = pts.map((p, i) =>
                  `${(i / Math.max(pts.length - 1, 1)) * sparkW},${sparkH - (p.article_count / maxCount) * sparkH}`
                ).join(' ');

                return (
                  <Card key={idx} className="border-l-4 border-l-orange-400">
                    <div className="p-3 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm">{ws.technology_name}</span>
                        <Badge className={accelColor} variant="secondary">
                          {ws.acceleration_rate.toFixed(1)}x
                        </Badge>
                        <Badge variant="outline" className="text-xs font-mono">
                          DVI {(ws.dvi_score * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="flex-1">
                          <div className="text-xs text-muted-foreground mb-1">
                            Strength: {(ws.current_strength * 100).toFixed(0)}%
                          </div>
                          <div className="w-full bg-muted rounded-full h-1.5">
                            <div
                              className="bg-orange-400 h-1.5 rounded-full"
                              style={{ width: `${ws.current_strength * 100}%` }}
                            />
                          </div>
                        </div>
                        {pts.length >= 2 && (
                          <svg width={sparkW} height={sparkH} className="shrink-0">
                            <polyline
                              points={sparkPoints}
                              fill="none"
                              stroke="#f97316"
                              strokeWidth="1.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Tracked across {ws.run_count} runs &middot; First seen {new Date(ws.first_seen).toLocaleDateString()}
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>
        )}

        {/* Latest Model Releases (GenAI domains only) */}
        {report.model_releases && report.model_releases.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Cpu className="w-5 h-5 text-purple-600" />
              Latest Model Releases ({report.model_releases.length})
            </h3>
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
                    <h4 className="font-medium">{rec.title}</h4>
                    <p className="text-sm text-muted-foreground mt-1">{rec.description}</p>
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
      </div>
    </ScrollArea>
  );
};

export default SensingReportRenderer;
