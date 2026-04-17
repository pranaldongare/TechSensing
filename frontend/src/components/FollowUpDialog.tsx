import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Loader2, Search } from 'lucide-react';
import { api } from '@/lib/api';
import type { DeepDiveReport } from '@/lib/api';
import { toast } from '@/components/ui/use-toast';
import SensingDeepDive from '@/components/SensingDeepDive';

interface Props {
  /** Pre-filled technology name / headline for the deep dive. */
  technologyName: string;
  /** Domain context. */
  domain?: string;
  /** Seed question to bias the search. */
  seedQuestion?: string;
  /** Source URLs to include as seed evidence. */
  seedUrls?: string[];
  /** Optional trigger button label override. */
  label?: string;
}

/**
 * "Deep dive" dialog triggered from an update/finding row (#17).
 *
 * Kicks off the existing deep-dive pipeline pre-seeded with the
 * update's headline and source URLs, then shows the results inline.
 */
const FollowUpDialog: React.FC<Props> = ({
  technologyName,
  domain,
  seedQuestion,
  seedUrls,
  label,
}) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [trackingId, setTrackingId] = useState<string | null>(null);
  const [report, setReport] = useState<DeepDiveReport | null>(null);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>(
    'idle',
  );

  const handleStart = async () => {
    setLoading(true);
    setStatus('running');
    setReport(null);
    try {
      const res = await api.sensingDeepDive(
        technologyName,
        domain || 'Technology',
        {
          seed_question: seedQuestion || technologyName,
          seed_urls: seedUrls || [],
        },
      );
      setTrackingId(res.tracking_id);
      pollForResult(res.tracking_id);
    } catch (err) {
      setStatus('error');
      setLoading(false);
      toast({
        title: 'Failed to start deep dive',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const pollForResult = (tid: string) => {
    let count = 0;
    const interval = window.setInterval(async () => {
      count += 1;
      if (count > 120) {
        window.clearInterval(interval);
        setStatus('error');
        setLoading(false);
        return;
      }
      try {
        const res = await api.sensingDeepDiveStatus(tid);
        if (res.status === 'completed') {
          window.clearInterval(interval);
          setStatus('done');
          setLoading(false);
          if (res.data) {
            setReport(res.data);
          }
          toast({
            title: 'Deep dive complete',
            description: `Analysis of "${technologyName}" is ready.`,
          });
        } else if (res.status === 'failed') {
          window.clearInterval(interval);
          setStatus('error');
          setLoading(false);
          toast({
            title: 'Deep dive failed',
            description: res.error || 'Unknown error',
            variant: 'destructive',
          });
        }
      } catch {
        // transient — keep polling
      }
    }, 4_000);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          if (status === 'idle') handleStart();
        }}
        className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        title={`Deep dive into "${technologyName}"`}
      >
        <Search className="w-3 h-3" />
        {label || 'Deep dive'}
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className={report ? 'max-w-3xl max-h-[85vh]' : undefined}>
          <DialogHeader>
            <DialogTitle>Deep Dive: {technologyName}</DialogTitle>
            <DialogDescription>
              {seedQuestion
                ? `Seeded with: "${seedQuestion}"`
                : 'Running a focused analysis using the existing deep-dive pipeline.'}
            </DialogDescription>
          </DialogHeader>

          {loading && (
            <div className="min-h-[120px] flex flex-col items-center justify-center py-8 gap-3">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">
                Researching and analyzing...
              </p>
              <p className="text-xs text-muted-foreground">
                This may take a few minutes.
              </p>
            </div>
          )}

          {status === 'done' && report && (
            <SensingDeepDive
              report={report}
              trackingId={trackingId || undefined}
              domain={domain}
            />
          )}

          {status === 'error' && (
            <div className="min-h-[120px] flex flex-col items-center justify-center py-4">
              <p className="text-sm text-destructive">
                The deep dive encountered an error. Try again later.
              </p>
            </div>
          )}

          <DialogFooter>
            {status === 'error' && (
              <Button
                variant="outline"
                onClick={() => {
                  setStatus('idle');
                  handleStart();
                }}
              >
                Retry
              </Button>
            )}
            <Button variant="outline" onClick={() => setOpen(false)}>
              {status === 'done' ? 'Close' : 'Dismiss'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default FollowUpDialog;
