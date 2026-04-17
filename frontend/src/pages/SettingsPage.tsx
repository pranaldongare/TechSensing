import React, { useCallback, useEffect, useState } from 'react';
import { Settings, Save, Loader2 } from 'lucide-react';
import AppNavbar from '@/components/AppNavbar';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/api';
import { toast } from '@/components/ui/use-toast';
import CompanyWatchlistManager from '@/components/CompanyWatchlistManager';

// ─────────────── helpers ───────────────

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
  );
}

// ─────────────── page ───────────────

const SettingsPage: React.FC = () => {
  // Aliases (#19)
  const [aliases, setAliases] = useState('');
  // Exclusions (#20)
  const [globalExcl, setGlobalExcl] = useState('');
  // Org context (#33)
  const [orgIndustry, setOrgIndustry] = useState('');
  const [orgPriorities, setOrgPriorities] = useState('');
  const [orgTechStack, setOrgTechStack] = useState('');
  // Integrations
  const [notionToken, setNotionToken] = useState('');
  const [notionParent, setNotionParent] = useState('');
  const [jiraBase, setJiraBase] = useState('');
  const [jiraEmail, setJiraEmail] = useState('');
  const [jiraToken, setJiraToken] = useState('');
  const [jiraProject, setJiraProject] = useState('');
  const [linearKey, setLinearKey] = useState('');
  const [linearTeam, setLinearTeam] = useState('');

  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [aliasRes, exclRes, orgRes, intRes] = await Promise.all([
        api.sensingGetAliases().catch(() => ({} as Record<string, string[]>)),
        api.sensingGetExclusions().catch(() => ({ global: [] as string[], per_company: {} as Record<string, string[]> })),
        api.sensingGetOrgContext().catch(() => ({ tech_stack: [] as string[], industry: '', priorities: [] as string[] })),
        api.sensingListIntegrations().catch(() => ({ integrations: {} as Record<string, Record<string, unknown>> })),
      ]);

      // Aliases: JSON dict → textarea lines.
      const aliasObj = aliasRes || {};
      const lines: string[] = [];
      for (const [canonical, alts] of Object.entries(aliasObj)) {
        lines.push(`${canonical}: ${(alts as string[]).join(', ')}`);
      }
      setAliases(lines.join('\n'));

      // Exclusions
      const gExcl: string[] = exclRes.global || [];
      setGlobalExcl(gExcl.join('\n'));

      // Org context
      setOrgIndustry(orgRes.industry || '');
      setOrgPriorities((orgRes.priorities || []).join('\n'));
      setOrgTechStack((orgRes.tech_stack || []).join('\n'));

      // Integrations (redacted)
      const ints = intRes.integrations || {};
      const n = (ints.notion as any) || {};
      const j = (ints.jira as any) || {};
      const l = (ints.linear as any) || {};
      setNotionToken(n.token || '');
      setNotionParent(n.default_parent_page_id || '');
      setJiraBase(j.base_url || '');
      setJiraEmail(j.email || '');
      setJiraToken(j.api_token || '');
      setJiraProject(j.project_key || '');
      setLinearKey(l.api_key || '');
      setLinearTeam(l.team_id || '');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ────── save handlers ──────

  const saveAliases = async () => {
    const obj: Record<string, string[]> = {};
    for (const line of aliases.split('\n')) {
      const idx = line.indexOf(':');
      if (idx < 1) continue;
      const canonical = line.slice(0, idx).trim();
      const alts = line
        .slice(idx + 1)
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      if (canonical && alts.length) obj[canonical] = alts;
    }
    try {
      await api.sensingSaveAliases(obj);
      toast({ title: 'Aliases saved' });
    } catch (e) {
      toast({ title: 'Failed', description: String(e), variant: 'destructive' });
    }
  };

  const saveExclusions = async () => {
    const global = globalExcl
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      await api.sensingSaveExclusions({ global, per_company: {} });
      toast({ title: 'Exclusions saved' });
    } catch (e) {
      toast({ title: 'Failed', description: String(e), variant: 'destructive' });
    }
  };

  const saveOrgContext = async () => {
    try {
      await api.sensingUpdateOrgContext({
        industry: orgIndustry.trim(),
        priorities: orgPriorities.split('\n').map((s) => s.trim()).filter(Boolean),
        tech_stack: orgTechStack.split('\n').map((s) => s.trim()).filter(Boolean),
      });
      toast({ title: 'Org context saved' });
    } catch (e) {
      toast({ title: 'Failed', description: String(e), variant: 'destructive' });
    }
  };

  const saveNotion = async () => {
    try {
      await api.sensingSetIntegration({
        provider: 'notion',
        config: { token: notionToken, default_parent_page_id: notionParent },
      });
      toast({ title: 'Notion config saved' });
    } catch (e) {
      toast({ title: 'Failed', description: String(e), variant: 'destructive' });
    }
  };

  const saveJira = async () => {
    try {
      await api.sensingSetIntegration({
        provider: 'jira',
        config: {
          base_url: jiraBase,
          email: jiraEmail,
          api_token: jiraToken,
          project_key: jiraProject,
        },
      });
      toast({ title: 'Jira config saved' });
    } catch (e) {
      toast({ title: 'Failed', description: String(e), variant: 'destructive' });
    }
  };

  const saveLinear = async () => {
    try {
      await api.sensingSetIntegration({
        provider: 'linear',
        config: { api_key: linearKey, team_id: linearTeam },
      });
      toast({ title: 'Linear config saved' });
    } catch (e) {
      toast({ title: 'Failed', description: String(e), variant: 'destructive' });
    }
  };

  if (loading) {
    return (
      <div className="h-screen flex flex-col">
        <AppNavbar />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      <AppNavbar />
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="flex items-center gap-3">
            <Settings className="w-6 h-6 text-primary" />
            <h2 className="text-2xl font-bold">Settings</h2>
          </div>

          {/* Aliases (#19) */}
          <Section title="Company aliases (#19)">
            <p className="text-xs text-muted-foreground">
              One line per canonical name: <code>Meta: Facebook, FB, Meta Platforms</code>
            </p>
            <Textarea
              value={aliases}
              onChange={(e) => setAliases(e.target.value)}
              rows={5}
              placeholder="Meta: Facebook, FB&#10;Google: Alphabet, GOOG"
            />
            <Button size="sm" onClick={saveAliases}>
              <Save className="w-4 h-4 mr-1" /> Save aliases
            </Button>
          </Section>

          {/* Exclusions (#20) */}
          <Section title="Global exclusion keywords (#20)">
            <p className="text-xs text-muted-foreground">
              One keyword/regex per line. Articles matching any of these are
              dropped.
            </p>
            <Textarea
              value={globalExcl}
              onChange={(e) => setGlobalExcl(e.target.value)}
              rows={4}
              placeholder="obituary&#10;horoscope"
            />
            <Button size="sm" onClick={saveExclusions}>
              <Save className="w-4 h-4 mr-1" /> Save exclusions
            </Button>
          </Section>

          {/* Watchlists (#15) */}
          <Section title="Company watchlists (#15)">
            <CompanyWatchlistManager />
          </Section>

          {/* Org context (#33) */}
          <Section title="Organization context (#33)">
            <p className="text-xs text-muted-foreground">
              Describe your organization so the Opportunity/Threat framing can
              tailor its analysis.
            </p>
            <div className="space-y-2">
              <div className="space-y-1">
                <label className="text-xs font-medium">Industry</label>
                <Input
                  value={orgIndustry}
                  onChange={(e) => setOrgIndustry(e.target.value)}
                  placeholder="AI tooling startup focused on agentic developer tools"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Priorities (one per line)</label>
                <Textarea
                  value={orgPriorities}
                  onChange={(e) => setOrgPriorities(e.target.value)}
                  rows={3}
                  placeholder={"Agentic AI capabilities\nDeveloper experience\nEnterprise security"}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Tech stack (one per line)</label>
                <Textarea
                  value={orgTechStack}
                  onChange={(e) => setOrgTechStack(e.target.value)}
                  rows={3}
                  placeholder={"Python\nReact\nFastAPI"}
                />
              </div>
            </div>
            <Button size="sm" onClick={saveOrgContext}>
              <Save className="w-4 h-4 mr-1" /> Save context
            </Button>
          </Section>

          {/* Notion (#23) */}
          <Section title="Notion integration (#23)">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs font-medium">Token</label>
                <Input
                  type="password"
                  value={notionToken}
                  onChange={(e) => setNotionToken(e.target.value)}
                  placeholder="secret_..."
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Default parent page ID</label>
                <Input
                  value={notionParent}
                  onChange={(e) => setNotionParent(e.target.value)}
                  placeholder="xxxxxxxx-xxxx-..."
                />
              </div>
            </div>
            <Button size="sm" onClick={saveNotion}>
              <Save className="w-4 h-4 mr-1" /> Save Notion
            </Button>
          </Section>

          {/* Jira (#24) */}
          <Section title="Jira integration (#24)">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs font-medium">Base URL</label>
                <Input
                  value={jiraBase}
                  onChange={(e) => setJiraBase(e.target.value)}
                  placeholder="https://acme.atlassian.net"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Project key</label>
                <Input
                  value={jiraProject}
                  onChange={(e) => setJiraProject(e.target.value)}
                  placeholder="TECH"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Email</label>
                <Input
                  value={jiraEmail}
                  onChange={(e) => setJiraEmail(e.target.value)}
                  placeholder="me@acme.com"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">API token</label>
                <Input
                  type="password"
                  value={jiraToken}
                  onChange={(e) => setJiraToken(e.target.value)}
                  placeholder="xxx"
                />
              </div>
            </div>
            <Button size="sm" onClick={saveJira}>
              <Save className="w-4 h-4 mr-1" /> Save Jira
            </Button>
          </Section>

          {/* Linear (#24) */}
          <Section title="Linear integration (#24)">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs font-medium">API key</label>
                <Input
                  type="password"
                  value={linearKey}
                  onChange={(e) => setLinearKey(e.target.value)}
                  placeholder="lin_api_..."
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Team ID</label>
                <Input
                  value={linearTeam}
                  onChange={(e) => setLinearTeam(e.target.value)}
                  placeholder="xxxxxxxx-xxxx-..."
                />
              </div>
            </div>
            <Button size="sm" onClick={saveLinear}>
              <Save className="w-4 h-4 mr-1" /> Save Linear
            </Button>
          </Section>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
