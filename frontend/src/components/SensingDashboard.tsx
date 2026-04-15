import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, TrendingUp, Zap, Target } from 'lucide-react';
import { api } from '@/lib/api';
import type { CrossDomainDashboard } from '@/lib/api';

interface SensingDashboardProps {
  onSelectDomain?: (domain: string) => void;
}

const SensingDashboard: React.FC<SensingDashboardProps> = ({ onSelectDomain }) => {
  const [dashboard, setDashboard] = useState<CrossDomainDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.sensingDashboard();
        setDashboard(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        Loading dashboard...
      </div>
    );
  }

  if (error) {
    return <div className="text-center py-12 text-muted-foreground">{error}</div>;
  }

  if (!dashboard || dashboard.domains.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No reports yet. Generate a sensing report to see your dashboard.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="text-2xl font-bold">{dashboard.total_domains}</div>
            <div className="text-xs text-muted-foreground">Domains Tracked</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="text-2xl font-bold">{dashboard.total_radar_items}</div>
            <div className="text-xs text-muted-foreground">Total Radar Items</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="text-2xl font-bold text-emerald-600">{dashboard.total_new_items}</div>
            <div className="text-xs text-muted-foreground">New Items</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="text-2xl font-bold text-amber-600">{dashboard.total_alerts}</div>
            <div className="text-xs text-muted-foreground">Alerts</div>
          </CardContent>
        </Card>
      </div>

      {/* Domain cards */}
      <div>
        <h3 className="text-lg font-semibold mb-3">Tracked Domains</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {dashboard.domains.map((d) => (
            <Card
              key={d.domain}
              className="cursor-pointer hover:border-primary transition-colors"
              onClick={() => onSelectDomain?.(d.domain)}
            >
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{d.domain}</CardTitle>
                <p className="text-xs text-muted-foreground">{d.report_date}</p>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="outline">{d.total_radar_items} items</Badge>
                  {d.new_items_count > 0 && (
                    <Badge className="bg-emerald-100 text-emerald-800" variant="secondary">
                      {d.new_items_count} new
                    </Badge>
                  )}
                  {d.moved_items_count > 0 && (
                    <Badge className="bg-amber-100 text-amber-800" variant="secondary">
                      {d.moved_items_count} moved
                    </Badge>
                  )}
                  {d.weak_signal_count > 0 && (
                    <Badge variant="outline" className="text-violet-600">
                      {d.weak_signal_count} weak signals
                    </Badge>
                  )}
                </div>
                {d.adopt_ring_items.length > 0 && (
                  <div className="text-xs">
                    <span className="font-medium text-emerald-600">Adopt:</span>{' '}
                    {d.adopt_ring_items.slice(0, 3).join(', ')}
                    {d.adopt_ring_items.length > 3 && ` +${d.adopt_ring_items.length - 3}`}
                  </div>
                )}
                {d.top_trends.length > 0 && (
                  <div className="text-xs text-muted-foreground">
                    Trends: {d.top_trends.join(', ')}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Recent Adopt Items */}
      {dashboard.recent_adopt_items.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Target className="w-5 h-5 text-emerald-600" />
            Recently Adopted Technologies
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {dashboard.recent_adopt_items.slice(0, 10).map((item, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm p-2 border rounded-md">
                <Badge className="bg-emerald-100 text-emerald-800" variant="secondary">Adopt</Badge>
                <span className="font-medium">{item.name}</span>
                <span className="text-xs text-muted-foreground ml-auto">{item.domain}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Movements */}
      {dashboard.recent_movements.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-amber-600" />
            Recent Ring Movements
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {dashboard.recent_movements.slice(0, 10).map((m, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm p-2 border rounded-md">
                <span className="font-medium">{m.name}</span>
                <span className="text-xs text-muted-foreground">{m.from_ring} → {m.to_ring}</span>
                <span className="text-xs text-muted-foreground ml-auto">{m.domain}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SensingDashboard;
