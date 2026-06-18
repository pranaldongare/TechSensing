import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Moon, Sun, Radar, Building2, Briefcase, Cpu, BarChart3, Settings,
  Plus, X, Trash2, Pencil, User,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { useTheme } from '@/lib/theme-context';
import { useProfile } from '@/lib/profile-context';
import { api } from '@/lib/api';
import type { UserProfile } from '@/lib/api';
import { PROJECT_NAME } from '../../config';

const ROLES = [
  ['general', 'General'],
  ['cto', 'CTO / Strategy'],
  ['engineering_lead', 'Engineering Lead'],
  ['developer', 'Developer'],
  ['product_manager', 'Product Manager'],
  ['analyst', 'Analyst'],
  ['exec', 'Executive'],
];

function ChipInput({
  label, values, onChange, placeholder,
}: { label: string; values: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [input, setInput] = useState('');
  const add = () => {
    const t = input.trim();
    if (t && !values.includes(t)) onChange([...values, t]);
    setInput('');
  };
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <div className="flex gap-2 mt-1">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          className="text-sm h-8"
        />
        <Button type="button" variant="outline" size="icon" className="h-8 w-8 shrink-0" onClick={add} disabled={!input.trim()}>
          <Plus className="w-3.5 h-3.5" />
        </Button>
      </div>
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {values.map((v) => (
            <Badge key={v} variant="secondary" className="gap-1 text-xs">
              {v}
              <button type="button" onClick={() => onChange(values.filter((x) => x !== v))}><X className="w-3 h-3" /></button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

const emptyProfile = (): UserProfile => ({
  id: '', name: 'New Profile', role: 'general',
  tech_stack: [], priorities: [], competitors: [], interests: [], avoid: [],
  personalization: 80,
});

const AppNavbar: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { profiles, activeProfileId, setActiveProfileId, refresh } = useProfile();

  // Company Analysis is temporarily hidden from the nav (route/page retained).
  const SHOW_COMPANY_ANALYSIS = false;

  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState<UserProfile>(emptyProfile());
  const [saving, setSaving] = useState(false);

  const openEditor = (profile?: UserProfile) => {
    setDraft(profile ? { ...profile } : emptyProfile());
    setEditorOpen(true);
  };

  const handleSave = async () => {
    if (!draft.name.trim()) return;
    setSaving(true);
    try {
      const saved = await api.sensingSaveProfile(draft);
      await refresh();
      setActiveProfileId(saved.id);
      setEditorOpen(false);
    } catch (e) {
      console.error('Save profile failed', e);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!draft.id || draft.id === 'default') return;
    setSaving(true);
    try {
      await api.sensingDeleteProfile(draft.id);
      await refresh();
      setActiveProfileId('default');
      setEditorOpen(false);
    } catch (e) {
      console.error('Delete profile failed', e);
    } finally {
      setSaving(false);
    }
  };

  const linkClass = ({ isActive }: { isActive: boolean }): string =>
    `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
      isActive ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
    }`;

  const activeProfile = profiles.find((p) => p.id === activeProfileId);

  return (
    <header className="border-b bg-background sticky top-0 z-10">
      <div className="px-4 py-3 flex justify-between items-center gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <img src="/tile-intelligent-augmenter.svg" alt="Tech Sensing" className="w-6 h-6 object-contain" draggable={false} />
          <h1 className="text-lg font-semibold">{PROJECT_NAME}</h1>
        </div>
        <nav className="flex items-center gap-1 flex-1 justify-center">
          <NavLink to="/" end className={linkClass}><Radar className="w-4 h-4" />Tech Sensing</NavLink>
          {SHOW_COMPANY_ANALYSIS && (
            <NavLink to="/company-analysis" className={linkClass}><Building2 className="w-4 h-4" />Company Analysis</NavLink>
          )}
          <NavLink to="/key-companies" className={linkClass}><Briefcase className="w-4 h-4" />Key Companies</NavLink>
          <NavLink to="/model-releases" className={linkClass}><Cpu className="w-4 h-4" />Model Releases</NavLink>
          <NavLink to="/ai-leaderboard" className={linkClass}><BarChart3 className="w-4 h-4" />AI Leaderboard</NavLink>
          <NavLink to="/settings" className={linkClass}><Settings className="w-4 h-4" />Settings</NavLink>
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          {/* Profile selector */}
          <div className="flex items-center gap-1">
            <User className="w-4 h-4 text-muted-foreground" />
            <Select
              value={activeProfileId}
              onValueChange={(v) => {
                if (v === '__new__') { openEditor(); return; }
                setActiveProfileId(v);
              }}
            >
              <SelectTrigger className="h-8 w-44 text-sm"><SelectValue placeholder="Profile" /></SelectTrigger>
              <SelectContent>
                {profiles.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
                <SelectItem value="__new__">+ New profile…</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="ghost" size="icon" className="h-8 w-8" title="Edit profile" onClick={() => openEditor(activeProfile)}>
              <Pencil className="w-4 h-4" />
            </Button>
          </div>

          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
            {theme === 'light' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
          </Button>
        </div>
      </div>

      {/* Profile editor */}
      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{draft.id ? 'Edit Profile' : 'New Profile'}</DialogTitle>
            <DialogDescription>
              Reports for the active profile are tailored to these interests. Personalization
              ranks and frames — it never hides major developments.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Profile name</Label>
                <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <Label className="text-xs">Role</Label>
                <Select value={draft.role || 'general'} onValueChange={(v) => setDraft({ ...draft, role: v })}>
                  <SelectTrigger className="h-8 mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROLES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <ChipInput label="Interest areas (topics/tech to follow)" values={draft.interests || []} onChange={(v) => setDraft({ ...draft, interests: v })} placeholder="e.g., Agentic AI, On-device inference" />
            <ChipInput label="Tech stack" values={draft.tech_stack || []} onChange={(v) => setDraft({ ...draft, tech_stack: v })} placeholder="e.g., Postgres, React" />
            <ChipInput label="Strategic priorities" values={draft.priorities || []} onChange={(v) => setDraft({ ...draft, priorities: v })} placeholder="e.g., Cost reduction" />
            <ChipInput label="Competitors / watchlist" values={draft.competitors || []} onChange={(v) => setDraft({ ...draft, competitors: v })} placeholder="e.g., OpenAI" />
            <ChipInput label="De-prioritize (avoid)" values={draft.avoid || []} onChange={(v) => setDraft({ ...draft, avoid: v })} placeholder="e.g., Crypto" />

            <div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">Personalization strength</Label>
                <span className="text-xs font-medium text-muted-foreground">{draft.personalization ?? 80}%</span>
              </div>
              <Slider
                className="mt-2"
                value={[draft.personalization ?? 80]}
                min={0} max={100} step={5}
                onValueChange={([v]) => setDraft({ ...draft, personalization: v })}
              />
            </div>
          </div>
          <DialogFooter className="flex items-center gap-2 pt-3 border-t">
            {draft.id && draft.id !== 'default' && (
              <Button variant="ghost" className="mr-auto text-destructive" onClick={handleDelete} disabled={saving}>
                <Trash2 className="w-4 h-4 mr-1.5" />Delete
              </Button>
            )}
            <Button variant="ghost" onClick={() => setEditorOpen(false)} disabled={saving}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving || !draft.name.trim()}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </header>
  );
};

export default AppNavbar;
