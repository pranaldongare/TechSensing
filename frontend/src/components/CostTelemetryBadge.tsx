import React, { useEffect, useState } from 'react';
import { Activity, Clock, Cpu } from 'lucide-react';
import { api, type TelemetrySummary } from '@/lib/api';

interface Props {
  trackingId: string | null;
  /** When set, poll every N ms for running jobs. Omit for finished runs. */
  pollIntervalMs?: number;
}

const formatTokens = (n: number): string => {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return `${n}`;
};

/** Compact inline badge showing LLM call count, elapsed, and ~token usage (#28). */
const CostTelemetryBadge: React.FC<Props> = ({ trackingId, pollIntervalMs }) => {
  const [tel, setTel] = useState<TelemetrySummary | null>(null);

  useEffect(() => {
    let active = true;
    let timer: number | null = null;

    const load = async () => {
      if (!trackingId) return;
      try {
        const data = await api.sensingTelemetry(trackingId);
        if (active && data) setTel(data);
      } catch {
        // Telemetry is best-effort; ignore.
      }
    };

    load();
    if (pollIntervalMs && pollIntervalMs > 0) {
      timer = window.setInterval(load, pollIntervalMs);
    }
    return () => {
      active = false;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [trackingId, pollIntervalMs]);

  if (!trackingId || !tel) return null;

  const totalTokens = tel.total_input_tokens_est + tel.total_output_tokens_est;
  return (
    <span
      className="inline-flex items-center gap-2 rounded border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground"
      title={`${tel.total_calls} LLM call(s), ${tel.successful_calls} ok; ~${tel.total_input_tokens_est} in / ${tel.total_output_tokens_est} out tokens`}
    >
      <span className="inline-flex items-center gap-1">
        <Activity className="h-3 w-3" />
        {tel.total_calls}
      </span>
      <span className="inline-flex items-center gap-1">
        <Clock className="h-3 w-3" />
        {tel.total_elapsed_s.toFixed(1)}s
      </span>
      <span className="inline-flex items-center gap-1">
        <Cpu className="h-3 w-3" />~{formatTokens(totalTokens)} tok
      </span>
    </span>
  );
};

export default CostTelemetryBadge;
