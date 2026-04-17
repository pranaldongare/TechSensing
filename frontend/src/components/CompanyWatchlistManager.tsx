import React, { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Bookmark,
  Plus,
  Trash2,
  Edit3,
  Loader2,
  Save,
  X,
} from 'lucide-react';
import { api, type Watchlist } from '@/lib/api';
import { toast } from '@/components/ui/use-toast';

interface Props {
  /**
   * When the user picks a watchlist from the dropdown, fire the supplied
   * callback so the parent form can populate its companies / highlight
   * domain / period-days state.
   */
  onLoad?: (wl: Watchlist) => void;

  /** Optional initial companies to prefill the "create" form. */
  prefill?: {
    companies?: string[];
    highlight_domain?: string;
    period_days?: number;
  };

  /**
   * If true, render as a compact dropdown-only picker. If false, render
   * the full management card with edit/delete controls (used by
   * Settings page).
   */
  compact?: boolean;
}

const emptyDraft = (): {
  name: string;
  companies: string;
  highlight_domain: string;
  period_days: number;
} => ({
  name: '',
  companies: '',
  highlight_domain: '',
  period_days: 7,
});

/**
 * Per-user watchlist picker / manager (#15).
 *
 * Dropdown + create / edit / delete — backed by `/sensing/watchlists`.
 */
const CompanyWatchlistManager: React.FC<Props> = ({
  onLoad,
  prefill,
  compact = false,
}) => {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.sensingListWatchlists();
      setWatchlists(data);
    } catch (err) {
      toast({
        title: 'Could not load watchlists',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const openCreate = () => {
    setEditingId(null);
    setDraft({
      ...emptyDraft(),
      companies: (prefill?.companies || []).join(', '),
      highlight_domain: prefill?.highlight_domain || '',
      period_days: prefill?.period_days || 7,
    });
    setDialogOpen(true);
  };

  const openEdit = (wl: Watchlist) => {
    setEditingId(wl.id);
    setDraft({
      name: wl.name,
      companies: wl.companies.join(', '),
      highlight_domain: wl.highlight_domain,
      period_days: wl.period_days,
    });
    setDialogOpen(true);
  };

  const handleSelect = (id: string) => {
    setSelectedId(id);
    const wl = watchlists.find((w) => w.id === id);
    if (wl && onLoad) onLoad(wl);
  };

  const handleSave = async () => {
    const companies = draft.companies
      .split(/[,\n]/)
      .map((c) => c.trim())
      .filter(Boolean);
    if (!draft.name.trim() || companies.length === 0) {
      toast({
        title: 'Missing fields',
        description: 'Name and at least one company are required.',
        variant: 'destructive',
      });
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        await api.sensingUpdateWatchlist(editingId, {
          name: draft.name.trim(),
          companies,
          highlight_domain: draft.highlight_domain.trim(),
          period_days: draft.period_days,
        });
      } else {
        await api.sensingCreateWatchlist({
          name: draft.name.trim(),
          companies,
          highlight_domain: draft.highlight_domain.trim(),
          period_days: draft.period_days,
        });
      }
      setDialogOpen(false);
      await reload();
    } catch (err) {
      toast({
        title: 'Save failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this watchlist?')) return;
    try {
      await api.sensingDeleteWatchlist(id);
      if (selectedId === id) setSelectedId('');
      await reload();
    } catch (err) {
      toast({
        title: 'Delete failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const renderDialog = () => (
    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editingId ? 'Edit watchlist' : 'New watchlist'}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1">
            <label className="text-xs font-medium">Name</label>
            <Input
              value={draft.name}
              onChange={(e) =>
                setDraft({ ...draft, name: e.target.value })
              }
              placeholder="e.g. AI Frontier Labs"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">
              Companies (comma or newline-separated)
            </label>
            <textarea
              value={draft.companies}
              onChange={(e) =>
                setDraft({ ...draft, companies: e.target.value })
              }
              placeholder="OpenAI, Anthropic, Google DeepMind"
              rows={3}
              className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">
              Highlight domain (optional)
            </label>
            <Input
              value={draft.highlight_domain}
              onChange={(e) =>
                setDraft({ ...draft, highlight_domain: e.target.value })
              }
              placeholder="Generative AI"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Lookback window</label>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                value={draft.period_days}
                min={1}
                max={30}
                onChange={(e) => {
                  const n = parseInt(e.target.value, 10);
                  if (Number.isFinite(n))
                    setDraft({
                      ...draft,
                      period_days: Math.max(1, Math.min(30, n)),
                    });
                }}
                className="w-24"
              />
              <span className="text-xs text-muted-foreground">days</span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setDialogOpen(false)}
          >
            <X className="mr-1.5 h-4 w-4" />
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-4 w-4" />
            )}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  // ─────────────────── compact dropdown (for input form) ───────────
  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Select value={selectedId} onValueChange={handleSelect}>
          <SelectTrigger className="h-9 w-64">
            <SelectValue
              placeholder={
                loading
                  ? 'Loading watchlists...'
                  : watchlists.length === 0
                    ? 'No watchlists yet'
                    : 'Load watchlist...'
              }
            />
          </SelectTrigger>
          <SelectContent>
            {watchlists.map((w) => (
              <SelectItem key={w.id} value={w.id}>
                {w.name} ({w.companies.length})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={openCreate}
        >
          <Plus className="mr-1 h-4 w-4" />
          Save as watchlist
        </Button>
        {renderDialog()}
      </div>
    );
  }

  // ─────────────────── full management card (Settings) ────────────
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Bookmark className="h-4 w-4 text-primary" />
            Watchlists
          </CardTitle>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={openCreate}
          >
            <Plus className="mr-1 h-4 w-4" />
            New
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading...
          </div>
        )}
        {!loading && watchlists.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No watchlists yet. Create one to re-use company groupings.
          </p>
        )}
        {watchlists.map((wl) => (
          <div
            key={wl.id}
            className="flex items-start justify-between gap-2 rounded border border-border p-2"
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-medium">{wl.name}</span>
                {wl.highlight_domain && (
                  <Badge variant="outline" className="text-[10px]">
                    {wl.highlight_domain}
                  </Badge>
                )}
                <Badge variant="outline" className="text-[10px]">
                  {wl.period_days}d
                </Badge>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {wl.companies.slice(0, 8).join(', ')}
                {wl.companies.length > 8 &&
                  ` +${wl.companies.length - 8} more`}
              </div>
            </div>
            <div className="flex shrink-0 gap-1">
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => openEdit(wl)}
                aria-label="Edit"
              >
                <Edit3 className="h-3.5 w-3.5" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => handleDelete(wl.id)}
                aria-label="Delete"
              >
                <Trash2 className="h-3.5 w-3.5 text-destructive" />
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
      {renderDialog()}
    </Card>
  );
};

export default CompanyWatchlistManager;
