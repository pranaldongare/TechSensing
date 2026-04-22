import React from 'react';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import type { LIRScoreSet } from '@/lib/api';

interface Props {
  scores: LIRScoreSet;
  size?: number;
}

const SCORE_LABELS: Record<string, string> = {
  convergence: 'Convergence',
  velocity: 'Velocity',
  novelty: 'Novelty',
  authority: 'Authority',
  pattern_match: 'Pattern',
  persistence: 'Persistence',
  cross_platform: 'Cross-Platform',
};

const LIRScoreRadar: React.FC<Props> = ({ scores, size = 180 }) => {
  const data = Object.entries(SCORE_LABELS).map(([key, label]) => ({
    axis: label,
    value: Math.round((scores[key as keyof LIRScoreSet] || 0) * 100),
  }));

  return (
    <div style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="hsl(var(--border))" />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={false}
            axisLine={false}
          />
          <Radar
            dataKey="value"
            stroke="hsl(var(--primary))"
            fill="hsl(var(--primary))"
            fillOpacity={0.25}
            strokeWidth={1.5}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 6,
              fontSize: 11,
            }}
            formatter={(value: number) => [`${value}%`, 'Score']}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default LIRScoreRadar;
