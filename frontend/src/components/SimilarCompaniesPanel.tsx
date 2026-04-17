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
import { Loader2, Plus, Sparkles } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from '@/components/ui/use-toast';

interface Props {
  /** Seed company to find peers for. */
  seed: string;
  /** Optional domain to bias suggestions. */
  domain?: string;
  /** Existing companies in the current watchlist (not suggested again). */
  existing: string[];
  /** Callback when user picks one or more companies to add. */
  onAdd: (names: string[]) => void;
  /** Disable button when no seed or at capacity. */
  disabled?: boolean;
}

/** "Suggest peers for {company}" dialog (#32). */
const SimilarCompaniesPanel: React.FC<Props> = ({
  seed,
  domain,
  existing,
  onAdd,
  disabled,
}) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [rationale, setRationale] = useState<string>('');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const runSuggestion = async () => {
    setLoading(true);
    setSuggestions([]);
    setRationale('');
    setSelected(new Set());
    try {
      const res = await api.sensingSimilarCompanies({
        company: seed,
        domain: domain || '',
        existing,
        max_suggestions: 6,
      });
      const list = (res.companies || []).filter(
        (c) =>
          !existing.some((e) => e.toLowerCase() === c.toLowerCase()),
      );
      setSuggestions(list);
      setRationale(res.rationale || '');
      if (list.length === 0) {
        toast({
          title: 'No suggestions',
          description: 'Model returned no peers for this seed.',
        });
      }
    } catch (err) {
      toast({
        title: 'Suggestion failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleAdd = () => {
    const picks = Array.from(selected);
    if (picks.length === 0) return;
    onAdd(picks);
    setOpen(false);
  };

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => {
          setOpen(true);
          runSuggestion();
        }}
        disabled={disabled || !seed.trim()}
        title={`Suggest peers for ${seed || '...'}`}
      >
        <Sparkles className="mr-1 h-4 w-4 text-primary" />
        Suggest peers
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Similar companies to {seed}</DialogTitle>
            <DialogDescription>
              {domain
                ? `Biased toward "${domain}".`
                : 'Select peers to add to your watchlist.'}
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-[200px] space-y-2 py-2">
            {loading && (
              <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Finding peers...
              </div>
            )}

            {!loading && suggestions.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No suggestions yet. Click "Try again" to re-query.
              </p>
            )}

            {rationale && (
              <p className="rounded bg-muted/40 p-2 text-xs text-muted-foreground">
                {rationale}
              </p>
            )}

            {suggestions.map((name) => {
              const active = selected.has(name);
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() => toggle(name)}
                  className={`w-full rounded border p-2 text-left transition-colors ${
                    active
                      ? 'border-primary bg-primary/10'
                      : 'border-border hover:bg-muted'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={active}
                      readOnly
                      className="accent-primary"
                    />
                    <span className="text-sm font-medium">{name}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={runSuggestion}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-1 h-4 w-4" />
              )}
              Try again
            </Button>
            <Button
              type="button"
              onClick={handleAdd}
              disabled={selected.size === 0}
            >
              <Plus className="mr-1 h-4 w-4" />
              Add {selected.size > 0 ? `${selected.size} ` : ''}to watchlist
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default SimilarCompaniesPanel;
