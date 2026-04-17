import React from 'react';

interface Props {
  confidence: number;
  size?: number;
  label?: boolean;
  className?: string;
}

// Green >= 0.7, amber >= 0.4, red otherwise. Matches the single-source
// downgrade ceiling of 0.4 enforced server-side (#13).
const bucket = (c: number): { color: string; label: string } => {
  if (c >= 0.7) return { color: 'bg-emerald-500', label: 'high' };
  if (c >= 0.4) return { color: 'bg-amber-500', label: 'medium' };
  return { color: 'bg-rose-500', label: 'low' };
};

const ConfidenceDot: React.FC<Props> = ({
  confidence,
  size = 10,
  label = false,
  className = '',
}) => {
  const { color, label: lbl } = bucket(confidence || 0);
  const tooltip = `Confidence: ${(confidence * 100).toFixed(0)}% (${lbl})`;
  return (
    <span
      className={`inline-flex items-center gap-1 ${className}`}
      title={tooltip}
    >
      <span
        className={`inline-block rounded-full ${color}`}
        style={{ width: size, height: size }}
        aria-label={tooltip}
      />
      {label && (
        <span className="text-xs text-muted-foreground">
          {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
};

export default ConfidenceDot;
