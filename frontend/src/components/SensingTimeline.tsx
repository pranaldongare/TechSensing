import React, { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import type { TimelineData } from '@/lib/api';

const RING_VALUE: Record<string, number> = {
  Adopt: 1,
  Trial: 2,
  Assess: 3,
  Hold: 4,
};

const RING_COLOR: Record<string, string> = {
  Adopt: '#059669',
  Trial: '#2563EB',
  Assess: '#D97706',
  Hold: '#DC2626',
};

const QUADRANT_COLOR: Record<string, string> = {
  Techniques: '#1ebccd',
  Platforms: '#f38a3e',
  Tools: '#86b82a',
  'Languages & Frameworks': '#b32059',
};

interface SensingTimelineProps {
  data: TimelineData;
}

const SensingTimeline: React.FC<SensingTimelineProps> = ({ data }) => {
  const [selectedQuadrant, setSelectedQuadrant] = useState<string | null>(null);

  const technologies = useMemo(() => {
    if (!selectedQuadrant) return data.technologies;
    return data.technologies.filter(t => t.quadrant === selectedQuadrant);
  }, [data.technologies, selectedQuadrant]);

  // Get unique report dates sorted
  const reportDates = useMemo(() => {
    const dates = new Set<string>();
    for (const tech of data.technologies) {
      for (const entry of tech.entries) {
        dates.add(entry.report_date);
      }
    }
    return [...dates].sort();
  }, [data.technologies]);

  if (data.technologies.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        <p className="text-sm">Generate multiple reports for the same domain to see timeline data.</p>
      </div>
    );
  }

  if (reportDates.length < 2) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        <p className="text-sm">Need at least 2 reports to show a timeline. Generate another report for this domain.</p>
      </div>
    );
  }

  const chartWidth = Math.max(600, reportDates.length * 120);
  const chartHeight = 300;
  const paddingLeft = 60;
  const paddingRight = 40;
  const paddingTop = 30;
  const paddingBottom = 60;
  const plotWidth = chartWidth - paddingLeft - paddingRight;
  const plotHeight = chartHeight - paddingTop - paddingBottom;

  const xScale = (i: number) => paddingLeft + (i / Math.max(reportDates.length - 1, 1)) * plotWidth;
  const yScale = (ring: string) => {
    const val = RING_VALUE[ring] || 2.5;
    return paddingTop + ((val - 1) / 3) * plotHeight;
  };

  return (
    <div className="space-y-4">
      {/* Quadrant filters */}
      <div className="flex flex-wrap gap-2 justify-center">
        {Object.entries(QUADRANT_COLOR).map(([name, color]) => (
          <button
            key={name}
            onClick={() => setSelectedQuadrant(selectedQuadrant === name ? null : name)}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              selectedQuadrant === name ? 'ring-2 ring-offset-1' : selectedQuadrant ? 'opacity-40' : ''
            }`}
            style={{ borderColor: color, color }}
          >
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            {name}
          </button>
        ))}
      </div>

      {/* SVG Timeline Chart */}
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="w-full max-w-full h-auto"
          style={{ minWidth: '500px', fontFamily: 'ui-sans-serif, system-ui, sans-serif' }}
        >
          {/* Y-axis ring labels + grid lines */}
          {['Adopt', 'Trial', 'Assess', 'Hold'].map(ring => {
            const y = yScale(ring);
            return (
              <g key={ring}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={chartWidth - paddingRight}
                  y2={y}
                  stroke="currentColor"
                  strokeOpacity={0.1}
                  strokeDasharray="4,4"
                />
                <text
                  x={paddingLeft - 8}
                  y={y}
                  fontSize={10}
                  fill={RING_COLOR[ring]}
                  textAnchor="end"
                  dominantBaseline="central"
                  fontWeight="500"
                >
                  {ring}
                </text>
              </g>
            );
          })}

          {/* X-axis date labels */}
          {reportDates.map((date, i) => {
            const x = xScale(i);
            const d = new Date(date);
            const label = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            return (
              <g key={date}>
                <line
                  x1={x}
                  y1={paddingTop}
                  x2={x}
                  y2={chartHeight - paddingBottom}
                  stroke="currentColor"
                  strokeOpacity={0.08}
                />
                <text
                  x={x}
                  y={chartHeight - paddingBottom + 16}
                  fontSize={9}
                  fill="currentColor"
                  fillOpacity={0.5}
                  textAnchor="middle"
                >
                  {label}
                </text>
              </g>
            );
          })}

          {/* Technology lines */}
          {technologies.map((tech) => {
            const color = QUADRANT_COLOR[tech.quadrant] || '#6b7280';
            const points: { x: number; y: number; ring: string }[] = [];

            for (const entry of tech.entries) {
              const dateIdx = reportDates.indexOf(entry.report_date);
              if (dateIdx >= 0) {
                points.push({
                  x: xScale(dateIdx),
                  y: yScale(entry.ring),
                  ring: entry.ring,
                });
              }
            }

            if (points.length < 1) return null;

            const pathD = points.map((p, i) =>
              i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`
            ).join(' ');

            return (
              <g key={tech.technology_name}>
                {/* Line */}
                {points.length > 1 && (
                  <path
                    d={pathD}
                    fill="none"
                    stroke={color}
                    strokeWidth={1.5}
                    strokeOpacity={0.6}
                  />
                )}
                {/* Dots */}
                {points.map((p, i) => (
                  <g key={i}>
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={4}
                      fill={color}
                      stroke="white"
                      strokeWidth={1.5}
                    />
                    {/* Label on last point */}
                    {i === points.length - 1 && (
                      <text
                        x={p.x + 6}
                        y={p.y + 3}
                        fontSize={8}
                        fill={color}
                        fontWeight="500"
                      >
                        {tech.technology_name.length > 20
                          ? tech.technology_name.slice(0, 18) + '...'
                          : tech.technology_name}
                      </text>
                    )}
                  </g>
                ))}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Technology list */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        {technologies.map(tech => {
          const latest = tech.entries[tech.entries.length - 1];
          const first = tech.entries[0];
          const moved = first && latest && first.ring !== latest.ring;
          return (
            <div key={tech.technology_name} className="flex items-center gap-2 p-2 rounded border text-xs">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: QUADRANT_COLOR[tech.quadrant] || '#6b7280' }}
              />
              <span className="font-medium truncate flex-1">{tech.technology_name}</span>
              <Badge
                variant="outline"
                className="text-[10px] shrink-0"
                style={{ color: RING_COLOR[latest?.ring || 'Trial'] }}
              >
                {latest?.ring || '?'}
              </Badge>
              {moved && (
                <span className="text-amber-500 text-[10px]" title={`Was ${first.ring}`}>
                  {RING_VALUE[first.ring] > RING_VALUE[latest.ring] ? '↑' : '↓'}
                </span>
              )}
              <span className="text-muted-foreground text-[10px]">{tech.entries.length}x</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default SensingTimeline;
