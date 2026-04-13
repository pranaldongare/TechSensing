import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ArrowRight } from 'lucide-react';
import type { ReportComparison } from '@/lib/api';

interface SensingComparisonViewProps {
  comparison: ReportComparison;
}

const statusColors: Record<string, string> = {
  added: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  removed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  moved: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  unchanged: 'bg-gray-100 text-gray-600 dark:bg-gray-800/30 dark:text-gray-400',
  new: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  continuing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
};

const ringColors: Record<string, string> = {
  Adopt: 'text-emerald-600',
  Trial: 'text-blue-600',
  Assess: 'text-amber-600',
  Hold: 'text-red-600',
};

const SensingComparisonView: React.FC<SensingComparisonViewProps> = ({ comparison }) => {
  const radarNonUnchanged = comparison.radar_diff.filter(d => d.status !== 'unchanged');
  const radarUnchanged = comparison.radar_diff.filter(d => d.status === 'unchanged');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Summary */}
      <div className="text-center space-y-2">
        <div className="flex items-center justify-center gap-3 text-sm text-muted-foreground">
          <span className="font-medium">{comparison.report_a_title}</span>
          <ArrowRight className="w-4 h-4" />
          <span className="font-medium">{comparison.report_b_title}</span>
        </div>
        <Badge variant="outline" className="text-sm px-4 py-1">
          {comparison.summary}
        </Badge>
      </div>

      {/* Radar Changes */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Radar Changes ({radarNonUnchanged.length} changes)</CardTitle>
        </CardHeader>
        <CardContent>
          {radarNonUnchanged.length === 0 ? (
            <p className="text-sm text-muted-foreground">No radar changes between these reports.</p>
          ) : (
            <div className="space-y-2">
              {radarNonUnchanged.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3 p-2 rounded-md border text-sm"
                >
                  <Badge className={statusColors[item.status] || ''} variant="secondary">
                    {item.status}
                  </Badge>
                  <span className="font-medium flex-1">{item.name}</span>
                  <span className="text-xs text-muted-foreground">{item.quadrant}</span>
                  {item.status === 'moved' && item.previous_ring && item.current_ring && (
                    <span className="flex items-center gap-1 text-xs">
                      <span className={ringColors[item.previous_ring] || ''}>{item.previous_ring}</span>
                      <ArrowRight className="w-3 h-3" />
                      <span className={ringColors[item.current_ring] || ''}>{item.current_ring}</span>
                    </span>
                  )}
                  {item.status === 'added' && item.current_ring && (
                    <Badge variant="outline" className="text-xs">
                      {item.current_ring}
                    </Badge>
                  )}
                  {item.status === 'removed' && item.previous_ring && (
                    <Badge variant="outline" className="text-xs line-through">
                      {item.previous_ring}
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          )}
          {radarUnchanged.length > 0 && (
            <p className="text-xs text-muted-foreground mt-3">
              + {radarUnchanged.length} unchanged technologies
            </p>
          )}
        </CardContent>
      </Card>

      {/* Trend Changes */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Trend Changes</CardTitle>
        </CardHeader>
        <CardContent>
          {comparison.trend_diff.length === 0 ? (
            <p className="text-sm text-muted-foreground">No trend data to compare.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {comparison.trend_diff.map((trend, idx) => (
                <Badge
                  key={idx}
                  className={statusColors[trend.status] || ''}
                  variant="secondary"
                >
                  {trend.status === 'removed' ? <span className="line-through">{trend.name}</span> : trend.name}
                  <span className="ml-1 opacity-70 text-xs">({trend.status})</span>
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Signal Changes */}
      {(comparison.new_signals.length > 0 || comparison.removed_signals.length > 0) && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Market Signal Changes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {comparison.new_signals.length > 0 && (
              <div>
                <span className="text-xs font-medium text-green-700 dark:text-green-400">New signals:</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {comparison.new_signals.map((s, i) => (
                    <Badge key={i} className={statusColors.added} variant="secondary">{s}</Badge>
                  ))}
                </div>
              </div>
            )}
            {comparison.removed_signals.length > 0 && (
              <div>
                <span className="text-xs font-medium text-red-700 dark:text-red-400">No longer present:</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {comparison.removed_signals.map((s, i) => (
                    <Badge key={i} className={statusColors.removed} variant="secondary">{s}</Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default SensingComparisonView;
