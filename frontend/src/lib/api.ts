import { API_URL } from '../../config';

// Types
export interface User {
  userId: string;
  name: string;
  email: string;
}

export interface LoginResponse {
  status: string;
  message: string;
  user: User;
  token: string;
}

// ── Tech Sensing types ──

export interface SensingRadarItem {
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
  lifecycle_stage?: string;
  funding_signal?: string;
}

export interface SensingTrendItem {
  trend_name: string;
  description: string;
  evidence: string[];
  impact_level: string;
  time_horizon: string;
  source_urls?: string[];
}

export interface SensingReportSection {
  section_title: string;
  content: string;
  source_urls?: string[];
}

export interface SensingRecommendation {
  title: string;
  description: string;
  priority: string;
  related_trends: string[];
}

export interface SensingClassifiedArticle {
  title: string;
  source: string;
  url: string;
  published_date: string;
  summary: string;
  relevance_score: number;
  quadrant: string;
  ring: string;
  technology_name: string;
  reasoning: string;
  topic_category?: string;
  industry_segment?: string;
}

export interface SensingRadarItemDetail {
  technology_name: string;
  what_it_is: string;
  why_it_matters: string;
  current_state: string;
  key_players: string[];
  practical_applications: string[];
  source_urls?: string[];
}

export interface SensingHeadlineMove {
  headline: string;
  actor: string;
  segment: string;
  source_urls?: string[];
}

export interface SensingMarketSignal {
  company_or_player: string;
  signal: string;
  strategic_intent: string;
  industry_impact: string;
  segment?: string;
  related_technologies: string[];
  source_urls?: string[];
}

export interface SensingTrendingVideo {
  technology_name: string;
  title: string;
  url: string;
  description: string;
  uploader: string;
  duration: string;
  published: string;
  view_count: number;
  thumbnail_url: string;
}

export interface WeakSignalTrajectoryPoint {
  run_date: string;
  article_count: number;
  source_count: number;
  avg_relevance: number;
  signal_strength: number;
}

export interface WeakSignal {
  technology_name: string;
  current_strength: number;
  acceleration_rate: number;
  first_seen: string;
  run_count: number;
  trajectory: WeakSignalTrajectoryPoint[];
  dvi_score: number;
}

export interface ModelRelease {
  model_name: string;
  organization: string;
  release_date: string;
  parameters: string;
  license: string;
  model_type: string;
  modality: string;
  notable_features: string;
  source_url: string;
}

export interface SensingReport {
  report_title: string;
  executive_summary: string;
  domain: string;
  date_range: string;
  total_articles_analyzed: number;
  headline_moves?: SensingHeadlineMove[];
  key_trends: SensingTrendItem[];
  report_sections: SensingReportSection[];
  radar_items: SensingRadarItem[];
  radar_item_details: SensingRadarItemDetail[];
  market_signals: SensingMarketSignal[];
  recommendations: SensingRecommendation[];
  notable_articles: SensingClassifiedArticle[];
  trending_videos?: SensingTrendingVideo[];
  weak_signals?: WeakSignal[];
  model_releases?: ModelRelease[];
  relationships?: TechRelationshipMap | null;
  report_confidence?: string;
  confidence_factors?: Record<string, any>;
}

export interface TechRelationship {
  source_tech: string;
  target_tech: string;
  relationship_type: string;
  strength: number;
  evidence: string;
}

export interface TechCluster {
  cluster_name: string;
  technologies: string[];
  theme: string;
}

export interface TechRelationshipMap {
  relationships: TechRelationship[];
  clusters: TechCluster[];
}

export interface TopicPreferences {
  domain: string;
  interested: string[];
  not_interested: string[];
  updated_at: string;
}

export interface DomainSummaryItem {
  domain: string;
  report_id: string;
  report_date: string;
  report_title: string;
  total_radar_items: number;
  new_items_count: number;
  moved_items_count: number;
  adopt_ring_items: string[];
  top_trends: string[];
  alert_count: number;
  weak_signal_count: number;
}

export interface CrossDomainDashboard {
  user_id: string;
  generated_at: string;
  domains: DomainSummaryItem[];
  total_domains: number;
  total_radar_items: number;
  total_new_items: number;
  total_alerts: number;
  recent_adopt_items: { name: string; domain: string; date: string }[];
  recent_movements: { name: string; domain: string; from_ring: string; to_ring: string; date: string }[];
}

export interface QueryAnswer {
  answer: string;
  sources: string[];
  technologies_mentioned: string[];
  confidence: string;
}

export interface SensingReportData {
  report: SensingReport;
  meta: {
    tracking_id: string;
    domain: string;
    raw_article_count: number;
    deduped_article_count: number;
    classified_article_count: number;
    execution_time_seconds: number;
    generated_at: string;
    custom_requirements?: string;
    must_include?: string[] | null;
    dont_include?: string[] | null;
    lookback_days?: number;
  };
}

export interface SensingHistoryItem {
  tracking_id: string;
  domain: string;
  generated_at: string;
  report_title: string;
  total_articles: number;
  custom_requirements?: string;
  must_include?: string[] | null;
  dont_include?: string[] | null;
  lookback_days?: number;
}

export interface SensingSchedule {
  id: string;
  user_id: string;
  domain: string;
  frequency: string;
  custom_requirements: string;
  must_include?: string[] | null;
  dont_include?: string[] | null;
  lookback_days: number;
  enabled: boolean;
  created_at: string;
  next_run: string;
  last_run?: string | null;
}

export interface RadarDiffItem {
  name: string;
  status: 'added' | 'removed' | 'moved' | 'unchanged';
  quadrant: string;
  current_ring?: string | null;
  previous_ring?: string | null;
  description: string;
}

export interface TrendDiff {
  name: string;
  status: 'new' | 'removed' | 'continuing';
}

export interface ReportComparison {
  report_a_id: string;
  report_b_id: string;
  report_a_title: string;
  report_b_title: string;
  report_a_date: string;
  report_b_date: string;
  radar_diff: RadarDiffItem[];
  trend_diff: TrendDiff[];
  new_signals: string[];
  removed_signals: string[];
  summary: string;
}

export interface TechnologyTimelineEntry {
  report_date: string;
  report_id: string;
  ring: string;
  quadrant: string;
}

export interface TechnologyTimeline {
  technology_name: string;
  quadrant: string;
  entries: TechnologyTimelineEntry[];
}

export interface TimelineData {
  domain: string;
  technologies: TechnologyTimeline[];
}

export interface RadarQuadrantConfig {
  name: string;
  color: string;
}

export interface RadarCustomization {
  quadrants: RadarQuadrantConfig[];
}

export interface OrgTechContext {
  tech_stack: string[];
  industry: string;
  priorities: string[];
  radar_customization?: RadarCustomization | null;
}

export interface CompetitorEntry {
  name: string;
  approach: string;
  strengths: string;
  weaknesses: string;
}

export interface KeyResource {
  title: string;
  url: string;
  type: string;
}

export interface DeepDiveReport {
  technology_name: string;
  comprehensive_analysis: string;
  technical_architecture: string;
  competitive_landscape: CompetitorEntry[];
  adoption_roadmap: string;
  risk_assessment: string;
  key_resources: KeyResource[];
  recommendations: string[];
}

export interface DeepDiveHistoryItem {
  tracking_id: string;
  technology_name: string;
  domain: string;
  generated_at: string;
  message_count: number;
}

export interface DeepDiveFullLoad {
  report: DeepDiveReport;
  conversation_history: { role: string; content: string }[];
  meta: { tracking_id: string; technology_name: string; domain: string; generated_at: string };
}

// --- Company Analysis ---

export interface CompanyTechFinding {
  technology: string;
  summary: string;
  specific_products: string[];
  recent_developments: string[];
  partnerships: string[];
  investment_signal: string;
  stance: string;
  confidence: number;
  source_urls: string[];
}

export interface CompanyProfile {
  company: string;
  overall_summary: string;
  technology_findings: CompanyTechFinding[];
  strengths: string[];
  gaps: string[];
  sources_used: number;
}

export interface ComparativeRow {
  technology: string;
  leader: string;
  rationale: string;
}

export interface CompanyAnalysisReport {
  report_tracking_id: string;
  domain: string;
  companies_analyzed: string[];
  technologies_analyzed: string[];
  executive_summary: string;
  company_profiles: CompanyProfile[];
  comparative_matrix: ComparativeRow[];
}

export interface CompanyAnalysisMeta {
  tracking_id: string;
  report_tracking_id: string;
  domain: string;
  companies: string[];
  technologies: string[];
  generated_at: string;
}

export interface CompanyAnalysisHistoryItem {
  tracking_id: string;
  report_tracking_id: string;
  domain: string;
  companies: string[];
  technologies: string[];
  generated_at: string;
}

export interface CompanyAnalysisFullLoad {
  report: CompanyAnalysisReport;
  meta: CompanyAnalysisMeta;
}

export interface RadarVote {
  vote_id: string;
  user_id: string;
  user_name: string;
  radar_item_name: string;
  suggested_ring: string;
  reasoning: string;
  created_at: string;
}

export interface RadarComment {
  comment_id: string;
  user_id: string;
  user_name: string;
  radar_item_name: string;
  text: string;
  created_at: string;
}

export interface SharedReport {
  share_id: string;
  report_tracking_id: string;
  owner_user_id: string;
  votes: RadarVote[];
  comments: RadarComment[];
  created_at: string;
}

export interface SharedReportFeedback {
  share_id: string;
  votes: RadarVote[];
  comments: RadarComment[];
  vote_summary: Record<string, { votes: RadarVote[]; ring_counts: Record<string, number> }>;
  total_votes: number;
  total_comments: number;
}

// Auth helpers
export const getAuthToken = () => localStorage.getItem('auth_token');
export const setAuthToken = (token: string) => localStorage.setItem('auth_token', token);
export const removeAuthToken = () => localStorage.removeItem('auth_token');
export const getCurrentUser = (): User | null => {
  const userStr = localStorage.getItem('current_user');
  return userStr ? JSON.parse(userStr) : null;
};
export const setCurrentUser = (user: User) => localStorage.setItem('current_user', JSON.stringify(user));
export const removeCurrentUser = () => localStorage.removeItem('current_user');

// API functions
export const api = {
  async register(name: string, email: string, password: string) {
    const response = await fetch(`${API_URL}/user/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    return response;
  },

  async login(email: string, password: string): Promise<LoginResponse> {
    const response = await fetch(`${API_URL}/user/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      const errorMessage = errorData.detail || 'Invalid email or password';
      throw new Error(errorMessage);
    }

    return response.json();
  },

  async getUser(userId: string): Promise<User> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/user/${userId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    return data.user;
  },

  // --- Tech Sensing ---

  async sensingGenerate(
    domain: string = 'Generative AI',
    customRequirements: string = '',
    mustInclude?: string[],
    dontInclude?: string[],
    lookbackDays: number = 7,
    feedUrls?: string[],
    searchQueries?: string[],
    includeVideos: boolean = false,
  ): Promise<{ status: string; tracking_id: string; message: string }> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        domain,
        custom_requirements: customRequirements,
        must_include: mustInclude?.length ? mustInclude : null,
        dont_include: dontInclude?.length ? dontInclude : null,
        lookback_days: lookbackDays,
        feed_urls: feedUrls || null,
        search_queries: searchQueries || null,
        include_videos: includeVideos,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Failed to start sensing report generation');
    }
    return data;
  },

  async sensingGenerateFromDocument(
    file: File,
    domain: string = 'Generative AI',
    customRequirements: string = '',
    mustInclude?: string[],
    dontInclude?: string[],
    lookbackDays: number = 7,
    includeVideos: boolean = false,
  ): Promise<{ status: string; tracking_id: string; message: string }> {
    const token = getAuthToken();
    const formData = new FormData();
    formData.append('file', file);
    formData.append('domain', domain);
    formData.append('custom_requirements', customRequirements);
    if (mustInclude?.length) formData.append('must_include', mustInclude.join(','));
    if (dontInclude?.length) formData.append('dont_include', dontInclude.join(','));
    formData.append('lookback_days', String(lookbackDays));
    formData.append('include_videos', String(includeVideos));

    const response = await fetch(`${API_URL}/sensing/generate-from-document`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Failed to start document sensing');
    }
    return data;
  },

  async sensingStatus(
    trackingId: string,
  ): Promise<{ status: string; data?: SensingReportData; error?: string }> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/status/${trackingId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Failed to check sensing status');
    }
    return data;
  },

  async sensingHistory(): Promise<{ reports: SensingHistoryItem[] }> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/history`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Failed to load sensing history');
    }
    return data;
  },

  async sensingDelete(reportId: string): Promise<void> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/report/${reportId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || 'Failed to delete sensing report');
    }
  },

  async sensingCompare(tidA: string, tidB: string): Promise<ReportComparison> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/compare?a=${encodeURIComponent(tidA)}&b=${encodeURIComponent(tidB)}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Failed to compare reports');
    }
    return data;
  },

  async sensingCreateSchedule(params: {
    domain: string; frequency: string; custom_requirements?: string;
    must_include?: string[] | null; dont_include?: string[] | null; lookback_days?: number;
  }): Promise<SensingSchedule> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/schedule`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to create schedule');
    return data;
  },

  async sensingGetSchedules(): Promise<{ schedules: SensingSchedule[] }> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/schedules`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load schedules');
    return data;
  },

  async sensingUpdateSchedule(id: string, updates: Record<string, unknown>): Promise<SensingSchedule> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/schedule/${id}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to update schedule');
    return data;
  },

  async sensingDeleteSchedule(id: string): Promise<void> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/schedule/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || 'Failed to delete schedule');
    }
  },

  async sensingGetFeeds(domain: string): Promise<{ feeds: string[]; queries: string[] }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/feeds?domain=${encodeURIComponent(domain)}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load feeds');
    return data;
  },

  async sensingTimeline(domain?: string): Promise<TimelineData> {
    const token = getAuthToken();
    const params = domain ? `?domain=${encodeURIComponent(domain)}` : '';
    const response = await fetch(
      `${API_URL}/sensing/timeline${params}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load timeline');
    return data;
  },

  async sensingGetOrgContext(): Promise<OrgTechContext> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/org-context`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load org context');
    return data;
  },

  async sensingUpdateOrgContext(context: OrgTechContext): Promise<OrgTechContext> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/org-context`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(context),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to update org context');
    return data;
  },

  async sensingDeepDive(technologyName: string, domain: string): Promise<{ status: string; tracking_id: string }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/deep-dive`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ technology_name: technologyName, domain }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to start deep dive');
    return data;
  },

  async sensingDeepDiveStatus(trackingId: string): Promise<{ status: string; data?: DeepDiveReport; error?: string }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/deep-dive/status/${trackingId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to get deep dive status');
    return data;
  },

  async sensingDeepDiveHistory(): Promise<{ deep_dives: DeepDiveHistoryItem[] }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/deep-dive/history`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load deep dive history');
    return data;
  },

  async sensingDeepDiveLoad(trackingId: string): Promise<DeepDiveFullLoad> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/deep-dive/${trackingId}/full`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load deep dive');
    return data;
  },

  async sensingCompanyAnalysisStart(body: {
    report_tracking_id: string;
    company_names: string[];
    technology_names?: string[];
  }): Promise<{ status: string; tracking_id: string }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/company-analysis`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to start company analysis');
    return data;
  },

  async sensingCompanyAnalysisStatus(
    trackingId: string,
  ): Promise<{ status: string; data?: { report: CompanyAnalysisReport; meta: CompanyAnalysisMeta }; error?: string }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/company-analysis/status/${trackingId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to get company analysis status');
    return data;
  },

  async sensingCompanyAnalysisHistory(
    reportTrackingId?: string,
  ): Promise<{ analyses: CompanyAnalysisHistoryItem[] }> {
    const token = getAuthToken();
    const qs = reportTrackingId
      ? `?report_tracking_id=${encodeURIComponent(reportTrackingId)}`
      : '';
    const response = await fetch(
      `${API_URL}/sensing/company-analysis/history${qs}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load company analysis history');
    return data;
  },

  async sensingCompanyAnalysisLoad(
    trackingId: string,
  ): Promise<CompanyAnalysisFullLoad> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/company-analysis/${trackingId}/full`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load company analysis');
    return data;
  },

  async sensingGetTopicPrefs(domain: string): Promise<TopicPreferences> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/topic-prefs?domain=${encodeURIComponent(domain)}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load topic preferences');
    return data;
  },

  async sensingUpdateTopicPref(
    domain: string,
    technologyName: string,
    interest: 'interested' | 'not_interested' | 'neutral',
  ): Promise<TopicPreferences> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/topic-prefs`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ domain, technology_name: technologyName, interest }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to update topic preference');
    return data;
  },

  async sensingShare(reportId: string): Promise<SharedReport> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/share/${reportId}`,
      { method: 'POST', headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to share report');
    return data;
  },

  async sensingGetShared(shareId: string): Promise<{ shared: SharedReport; report: SensingReportData | null }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/shared/${shareId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load shared report');
    return data;
  },

  async sensingVote(shareId: string, radarItemName: string, suggestedRing: string, reasoning?: string): Promise<RadarVote> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/shared/${shareId}/vote`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ radar_item_name: radarItemName, suggested_ring: suggestedRing, reasoning: reasoning || '' }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to submit vote');
    return data;
  },

  async sensingComment(shareId: string, text: string, radarItemName?: string): Promise<RadarComment> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/shared/${shareId}/comment`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text, radar_item_name: radarItemName || '' }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to add comment');
    return data;
  },

  async sensingGetFeedback(shareId: string): Promise<SharedReportFeedback> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/shared/${shareId}/feedback`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load feedback');
    return data;
  },

  async sensingSubmitSourceFeedback(sourceName: string, vote: 'up' | 'down'): Promise<{ status: string; feedback: Record<string, any> }> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/source-feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ source_name: sourceName, vote }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to submit feedback');
    return data;
  },

  async sensingGetSourceFeedback(): Promise<Record<string, any>> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/source-feedback`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load source feedback');
    return data;
  },

  async sensingDashboard(): Promise<CrossDomainDashboard> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/dashboard`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load dashboard');
    return data;
  },

  async sensingQuery(question: string, domain?: string): Promise<QueryAnswer> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ question, domain: domain || null }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to query reports');
    return data;
  },
};

// WebSocket helper
export const getWebSocketUrl = (path: string) => {
  const base = (import.meta.env.VITE_WS_URL as string | undefined) || API_URL;
  const url = new URL(base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const joined = `${url.origin}${path.startsWith('/') ? '' : '/'}${path}`;
  return joined;
};
