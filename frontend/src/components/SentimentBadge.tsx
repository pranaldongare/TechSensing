import React from 'react';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import type { SentimentLabel } from '@/lib/api';

interface Props {
  sentiment?: SentimentLabel;
  compact?: boolean;
}

const tone = (s: SentimentLabel) => {
  switch (s) {
    case 'positive':
      return {
        cls: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200',
        Icon: ArrowUp,
        label: 'Positive',
      };
    case 'negative':
      return {
        cls: 'bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-900/40 dark:text-rose-200',
        Icon: ArrowDown,
        label: 'Negative',
      };
    default:
      return {
        cls: 'bg-muted text-muted-foreground border-border',
        Icon: Minus,
        label: 'Neutral',
      };
  }
};

const SentimentBadge: React.FC<Props> = ({ sentiment, compact }) => {
  if (!sentiment) return null;
  const { cls, Icon, label } = tone(sentiment);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] ${cls}`}
      title={`Sentiment: ${label}`}
    >
      <Icon className="h-3 w-3" />
      {!compact && label}
    </span>
  );
};

export default SentimentBadge;
