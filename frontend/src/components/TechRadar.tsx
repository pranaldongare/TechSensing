import React, { useState, useMemo, useCallback } from 'react';

interface RadarItem {
  name: string;
  quadrant: string;
  ring: string;
  description: string;
  is_new: boolean;
  moved_in?: string | null;
  signal_strength?: number;
  source_count?: number;
  trl?: number;
  patent_count?: number;
}

interface TechRadarProps {
  items: RadarItem[];
  onBlipClick?: (name: string) => void;
  customQuadrants?: { name: string; color: string }[];
}

const DEFAULT_QUADRANTS: { name: string; color: string; start: number; end: number }[] = [
  { name: 'Techniques', color: '#1ebccd', start: 90, end: 180 },
  { name: 'Platforms', color: '#f38a3e', start: 0, end: 90 },
  { name: 'Tools', color: '#86b82a', start: 270, end: 360 },
  { name: 'Languages & Frameworks', color: '#b32059', start: 180, end: 270 },
];

function buildQuadrants(
  custom?: { name: string; color: string }[]
): Record<string, { start: number; end: number; color: string; label: string }> {
  const base = DEFAULT_QUADRANTS;
  if (custom && custom.length === 4) {
    const result: Record<string, { start: number; end: number; color: string; label: string }> = {};
    for (let i = 0; i < 4; i++) {
      result[custom[i].name] = {
        start: base[i].start,
        end: base[i].end,
        color: custom[i].color || base[i].color,
        label: custom[i].name,
      };
    }
    return result;
  }
  const result: Record<string, { start: number; end: number; color: string; label: string }> = {};
  for (const q of base) {
    result[q.name] = { start: q.start, end: q.end, color: q.color, label: q.name };
  }
  return result;
}

const RINGS: Record<string, { inner: number; outer: number; label: string }> = {
  'Adopt': { inner: 0, outer: 0.25, label: 'Adopt' },
  'Trial': { inner: 0.25, outer: 0.50, label: 'Trial' },
  'Assess': { inner: 0.50, outer: 0.75, label: 'Assess' },
  'Hold': { inner: 0.75, outer: 1.0, label: 'Hold' },
};

const RING_ORDER = ['Adopt', 'Trial', 'Assess', 'Hold'];

// Seeded pseudo-random for deterministic positioning
function seededRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

function hashString(s: string): number {
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    hash = ((hash << 5) - hash) + s.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

const TechRadar: React.FC<TechRadarProps> = ({ items, onBlipClick, customQuadrants }) => {
  const [tooltip, setTooltip] = useState<{ x: number; y: number; item: RadarItem } | null>(null);
  const [selectedQuadrant, setSelectedQuadrant] = useState<string | null>(null);

  const QUADRANTS = useMemo(() => buildQuadrants(customQuadrants), [customQuadrants]);

  const size = 600;
  const center = size / 2;
  const maxRadius = size / 2 - 40;

  const blips = useMemo(() => {
    return items.map((item, idx) => {
      const q = QUADRANTS[item.quadrant];
      const r = RINGS[item.ring];
      if (!q || !r) return null;

      const seed = hashString(item.name + idx);
      const anglePad = 8; // degrees padding from edges
      const angleRange = (q.end - q.start) - 2 * anglePad;
      const angle = (q.start + anglePad + seededRandom(seed) * angleRange) * (Math.PI / 180);

      const radiusPad = 0.03;
      const rMin = (r.inner + radiusPad) * maxRadius;
      const rMax = (r.outer - radiusPad) * maxRadius;
      const radius = rMin + seededRandom(seed + 1) * (rMax - rMin);

      const x = center + radius * Math.cos(angle);
      const y = center - radius * Math.sin(angle);

      // Scale blip size by signal_strength (4px base + 4px * strength)
      const blipSize = 4 + 4 * (item.signal_strength || 0.2);
      return { ...item, x, y, color: q.color, blipSize };
    }).filter(Boolean) as (RadarItem & { x: number; y: number; color: string; blipSize: number })[];
  }, [items, center, maxRadius, QUADRANTS]);

  const filteredBlips = selectedQuadrant
    ? blips.filter(b => b.quadrant === selectedQuadrant)
    : blips;

  const handleMouseEnter = useCallback((e: React.MouseEvent, item: RadarItem & { x: number; y: number }) => {
    setTooltip({ x: item.x, y: item.y, item });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  return (
    <div className="flex flex-col items-center gap-4 w-full">
      {/* Legend */}
      <div className="flex flex-wrap gap-3 justify-center">
        {Object.entries(QUADRANTS).map(([key, q]) => (
          <button
            key={key}
            onClick={() => setSelectedQuadrant(selectedQuadrant === key ? null : key)}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all border ${
              selectedQuadrant === key
                ? 'ring-2 ring-offset-1 opacity-100'
                : selectedQuadrant
                ? 'opacity-40'
                : 'opacity-100'
            }`}
            style={{
              borderColor: q.color,
              color: q.color,
              ...(selectedQuadrant === key ? { backgroundColor: q.color + '20', ringColor: q.color } : {}),
            }}
          >
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: q.color }}
            />
            {q.label}
          </button>
        ))}
      </div>

      {/* Ring legend */}
      <div className="flex gap-4 text-xs text-muted-foreground">
        {RING_ORDER.map(ring => (
          <span key={ring} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-muted-foreground/40" />
            {ring}
          </span>
        ))}
        <span className="flex items-center gap-1 ml-2">
          <svg width="10" height="10"><polygon points="5,0 10,10 0,10" fill="currentColor" /></svg>
          New
        </span>
        <span className="flex items-center gap-1 ml-2">
          <svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="none" stroke="#f59e0b" strokeWidth="2" /></svg>
          Moved
        </span>
      </div>

      {/* Radar SVG */}
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="w-full max-w-[600px] h-auto"
        style={{ fontFamily: 'ui-sans-serif, system-ui, sans-serif' }}
      >
        {/* Ring circles */}
        {RING_ORDER.map((ring) => {
          const r = RINGS[ring];
          return (
            <circle
              key={ring}
              cx={center}
              cy={center}
              r={r.outer * maxRadius}
              fill="none"
              stroke="currentColor"
              strokeOpacity={0.15}
              strokeWidth={1}
            />
          );
        })}

        {/* Ring labels */}
        {RING_ORDER.map((ring) => {
          const r = RINGS[ring];
          const labelR = ((r.inner + r.outer) / 2) * maxRadius;
          return (
            <text
              key={`label-${ring}`}
              x={center + labelR}
              y={center - 4}
              fontSize={9}
              fill="currentColor"
              fillOpacity={0.35}
              textAnchor="middle"
            >
              {ring}
            </text>
          );
        })}

        {/* Quadrant dividing lines */}
        {[0, 90, 180, 270].map(deg => {
          const rad = deg * (Math.PI / 180);
          return (
            <line
              key={`line-${deg}`}
              x1={center}
              y1={center}
              x2={center + maxRadius * Math.cos(rad)}
              y2={center - maxRadius * Math.sin(rad)}
              stroke="currentColor"
              strokeOpacity={0.15}
              strokeWidth={1}
            />
          );
        })}

        {/* Quadrant labels */}
        {Object.entries(QUADRANTS).map(([key, q]) => {
          const midAngle = ((q.start + q.end) / 2) * (Math.PI / 180);
          const labelR = maxRadius + 20;
          const lx = center + labelR * Math.cos(midAngle);
          const ly = center - labelR * Math.sin(midAngle);
          return (
            <text
              key={`qlabel-${key}`}
              x={lx}
              y={ly}
              fontSize={10}
              fontWeight="600"
              fill={q.color}
              textAnchor="middle"
              dominantBaseline="central"
            >
              {q.label}
            </text>
          );
        })}

        {/* Blips */}
        {filteredBlips.map((blip, idx) => (
          <g
            key={`${blip.name}-${idx}`}
            onMouseEnter={(e) => handleMouseEnter(e, blip)}
            onMouseLeave={handleMouseLeave}
            onClick={() => onBlipClick?.(blip.name)}
            className="cursor-pointer"
          >
            {/* Movement indicator ring */}
            {blip.moved_in && (
              <circle
                cx={blip.x}
                cy={blip.y}
                r={9}
                fill="none"
                stroke="#f59e0b"
                strokeWidth={2}
                strokeDasharray="3,2"
              />
            )}
            {blip.is_new ? (
              <polygon
                points={`${blip.x},${blip.y - blip.blipSize * 1.2} ${blip.x + blip.blipSize},${blip.y + blip.blipSize * 0.6} ${blip.x - blip.blipSize},${blip.y + blip.blipSize * 0.6}`}
                fill={blip.color}
                stroke="white"
                strokeWidth={1}
              />
            ) : (
              <circle
                cx={blip.x}
                cy={blip.y}
                r={blip.blipSize}
                fill={blip.color}
                stroke="white"
                strokeWidth={1}
              />
            )}
          </g>
        ))}

        {/* Tooltip */}
        {tooltip && (() => {
          const hasMovement = !!tooltip.item.moved_in;
          const hasSignal = (tooltip.item.signal_strength || 0) > 0;
          const extraLines = (hasMovement ? 1 : 0) + (hasSignal ? 1 : 0);
          const tooltipHeight = 38 + extraLines * 14;
          const tooltipWidth = Math.max(
            tooltip.item.name.length * 7,
            tooltip.item.description.length * 4.5,
            hasMovement ? 200 : 160,
          );
          return (
            <g>
              <rect
                x={tooltip.x + 10}
                y={tooltip.y - 30}
                width={tooltipWidth}
                height={tooltipHeight}
                rx={4}
                fill="hsl(var(--popover))"
                stroke="hsl(var(--border))"
                strokeWidth={1}
                opacity={0.95}
              />
              <text
                x={tooltip.x + 16}
                y={tooltip.y - 16}
                fontSize={11}
                fontWeight="600"
                fill="hsl(var(--popover-foreground))"
              >
                {tooltip.item.name}
              </text>
              <text
                x={tooltip.x + 16}
                y={tooltip.y - 2}
                fontSize={9}
                fill="hsl(var(--muted-foreground))"
              >
                {tooltip.item.description.slice(0, 45)}{tooltip.item.description.length > 45 ? '...' : ''}
              </text>
              {hasMovement && (
                <text
                  x={tooltip.x + 16}
                  y={tooltip.y + 12}
                  fontSize={9}
                  fontWeight="600"
                  fill="#f59e0b"
                >
                  Moved from {tooltip.item.moved_in}
                </text>
              )}
              {hasSignal && (
                <text
                  x={tooltip.x + 16}
                  y={tooltip.y + 12 + (hasMovement ? 14 : 0)}
                  fontSize={9}
                  fill="hsl(var(--muted-foreground))"
                >
                  Signal: {Math.round((tooltip.item.signal_strength || 0) * 100)}%{tooltip.item.trl ? ` | TRL ${tooltip.item.trl}` : ''} | {tooltip.item.source_count || 0} sources{tooltip.item.patent_count ? ` | ${tooltip.item.patent_count} patents` : ''}
                </text>
              )}
            </g>
          );
        })()}
      </svg>
    </div>
  );
};

export default TechRadar;
