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
  release_status: string;
  parameters: string;
  license: string;
  is_open_source: string;
  model_type: string;
  modality: string;
  notable_features: string;
  source_url: string;
  data_source: string;
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

export interface ContradictionFlag {
  topic: string;
  claim_a: string;
  claim_b: string;
  sources_a?: string[];
  sources_b?: string[];
  resolution?: 'unclear' | 'A' | 'B';
  note?: string;
  company?: string;
  technology?: string;
}

export interface UnsupportedClaim {
  claim: string;
  reason: string;
  suggested_action?: 'drop' | 'flag' | 'rewrite';
  company?: string;
}

export interface CompanyAnalysisReport {
  report_tracking_id: string;
  domain: string;
  companies_analyzed: string[];
  technologies_analyzed: string[];
  executive_summary: string;
  company_profiles: CompanyProfile[];
  comparative_matrix: ComparativeRow[];
  // Phase 3 optional fields
  overlap_matrix?: OverlapCell[];
  strategic_themes?: ThemeCluster[];
  investment_signals?: InvestmentEvent[];
  opportunity_threat?: {
    org_context_used: string;
    opportunities: string[];
    threats: string[];
    recommended_actions: string[];
  };
  // Phase 6 optional fields
  contradictions?: ContradictionFlag[];
  unsupported_claims?: UnsupportedClaim[];
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

// ---- Key Companies ----

export type SentimentLabel = 'positive' | 'neutral' | 'negative';

export interface ClaimEvidence {
  claim: string;
  source_urls: string[];
  confidence: number;
  is_single_source: boolean;
}

export interface DomainRollupEntry {
  domain: string;
  update_count: number;
  company_count: number;
}

export interface MomentumSnapshot {
  score: number;
  update_count: number;
  weighted_score: number;
  top_drivers: string[];
}

export type DiffStatus = 'NEW' | 'ONGOING' | 'RESOLVED';

export interface DiffTag {
  status: DiffStatus;
  previous_headline?: string;
}

export interface DiffSummary {
  previous_tracking_id: string;
  resolved_topics: { company: string; headline: string }[];
  new_count: number;
  ongoing_count: number;
}

export interface KeyCompanyUpdate {
  category: string;
  headline: string;
  summary: string;
  date: string;
  domain: string;
  source_url: string;
  sentiment?: SentimentLabel;
  evidence?: ClaimEvidence[];
  diff?: DiffTag;
}

export interface HiringSnapshot {
  total_postings: number;
  seniority_breakdown: string[];
  domains: string[];
  trend_vs_previous: 'up' | 'flat' | 'down' | 'unknown';
}

export interface KeyCompanyBriefing {
  company: string;
  overall_summary: string;
  domains_active: string[];
  updates: KeyCompanyUpdate[];
  key_themes: string[];
  sources_used: number;
  momentum?: MomentumSnapshot;
  hiring_signals?: HiringSnapshot;
}

export interface KeyCompaniesReport {
  companies_analyzed: string[];
  highlight_domain: string;
  period_days: number;
  period_start: string;
  period_end: string;
  cross_company_summary: string;
  briefings: KeyCompanyBriefing[];
  domain_rollup?: DomainRollupEntry[];
  watchlist_id?: string;
  diff_summary?: DiffSummary | null;
}

export interface TelemetryCall {
  label: string;
  model: string;
  port: number;
  elapsed_s: number;
  input_tokens_est: number;
  output_tokens_est: number;
  ok: boolean;
  error?: string;
  at: string;
}

export interface TelemetrySummary {
  tracking_id: string;
  kind: string;
  started_at: string;
  total_calls: number;
  successful_calls: number;
  total_elapsed_s: number;
  total_input_tokens_est: number;
  total_output_tokens_est: number;
  calls: TelemetryCall[];
}

export interface ExclusionsMap {
  global?: string[];
  per_company?: Record<string, string[]>;
}

export interface Watchlist {
  id: string;
  name: string;
  companies: string[];
  highlight_domain: string;
  period_days: number;
  created_at: string;
  updated_at: string;
}

// ──────────────────────────────────────────────────────────────
// Phase 3 — analytical output types
// ──────────────────────────────────────────────────────────────

export interface OverlapCell {
  technology_a: string;
  technology_b: string;
  overlap_count: number;
  overlap_companies: string[];
}

export interface ThemeCluster {
  theme: string;
  rationale: string;
  companies: string[];
  technologies: string[];
}

export type InvestmentEventType =
  | 'Funding'
  | 'Acquisition'
  | 'IPO'
  | 'Divestiture'
  | 'Partnership'
  | 'Hiring'
  | 'Other';

export interface InvestmentEvent {
  company: string;
  event_type: InvestmentEventType;
  amount_usd: number;
  amount_text: string;
  date: string;
  description: string;
  source_url: string;
}

export interface CompanyTimelineEvent {
  company: string;
  date: string;
  month_bucket: string;
  category: string;
  headline: string;
  summary: string;
  source: 'key_companies' | 'company_analysis';
  source_url: string;
  tracking_id: string;
}

export interface CompanyTimeline {
  company: string;
  events: CompanyTimelineEvent[];
  first_seen: string;
  last_seen: string;
}

export interface SimilarCompaniesResult {
  companies: string[];
  rationale: string;
}

export interface KeyCompaniesMeta {
  tracking_id: string;
  companies: string[];
  highlight_domain: string;
  period_days: number;
  period_start: string;
  period_end: string;
  generated_at: string;
}

export interface KeyCompaniesHistoryItem {
  tracking_id: string;
  companies: string[];
  highlight_domain: string;
  period_days: number;
  period_start: string;
  period_end: string;
  generated_at: string;
}

export interface KeyCompaniesFullLoad {
  report: KeyCompaniesReport;
  meta: KeyCompaniesMeta;
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

// ── Leading Indicator Radar (LIR) types ──

export interface LIRScoreSet {
  convergence: number;
  velocity: number;
  novelty: number;
  authority: number;
  pattern_match: number;
}

export interface LIREvidence {
  url: string;
  title: string;
  source: string;
  date: string;
}

export interface LIRCandidate {
  concept_id: string;
  canonical_name: string;
  description: string;
  ring: string;
  scores: LIRScoreSet;
  composite_score: number;
  signal_count: number;
  source_tiers: string[];
  domain_tags: string[];
  top_evidence: LIREvidence[];
  first_seen: string;
  last_seen: string;
  velocity_trend?: number[];
}

export interface LIRSignalEvidence {
  signal_id: string;
  source_id: string;
  tier: string;
  url: string;
  summary: string;
  evidence_quote: string;
  stated_novelty: number;
  relevance_score: number;
  published_date: string;
}

export interface LIRConceptDetail {
  concept_id: string;
  canonical_name: string;
  aliases: string[];
  description: string;
  domain_tags: string[];
  ring: string;
  scores: LIRScoreSet;
  composite_score: number;
  signal_count: number;
  source_tiers: string[];
  created_at: string;
  updated_at: string;
  evidence: LIRSignalEvidence[];
}

export interface LIRTimeseriesPoint {
  week: string;
  signal_count: number;
  composite_score: number;
}

export interface LIRSourceInfo {
  source_id: string;
  tier: string;
  lead_time_prior_days: number;
  authority_prior: number;
  enabled: boolean;
}

export interface LIRRefreshResult {
  candidates: LIRCandidate[];
  meta: {
    tracking_id: string;
    total_items_ingested: number;
    total_items_after_dedup: number;
    total_signals_extracted: number;
    total_concepts: number;
    new_concepts: number;
    execution_time_seconds: number;
    sources_polled: string[];
    errors: string[];
    generated_at: string;
  };
}

// Phase 3/4: Rationale
export interface LIRRationale {
  concept_id: string;
  summary: string;
  key_drivers: string[];
  risk_factors: string[];
  recommended_action: string;
  pattern_matches: LIRPatternMatch[];
  generated_at: string;
}

export interface LIRPatternMatch {
  pattern_id: string;
  name: string;
  description: string;
  score: number;
  expected_ring: string;
  consensus_week: number;
}

// Phase 3/4: Patterns
export interface LIRPattern {
  pattern_id: string;
  name: string;
  description: string;
  duration_weeks: number;
  expected_ring: string;
  consensus_week: number;
  tags: string[];
}

// Phase 3/4: Backtest
export interface LIRBacktestSnapshot {
  week_offset: number;
  date: string;
  signal_count: number;
  scores: Record<string, number>;
  composite: number;
  ring: string;
}

export interface LIRBacktestConceptResult {
  concept_id: string;
  canonical_name: string;
  first_assess_week: number | null;
  first_trial_week: number | null;
  first_adopt_week: number | null;
  snapshots: LIRBacktestSnapshot[];
}

export interface LIRBacktestResult {
  run_id: string;
  start_date: string;
  end_date: string;
  weights_used: Record<string, number>;
  total_concepts: number;
  execution_time_seconds: number;
  errors: string[];
  concept_results: LIRBacktestConceptResult[];
}

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

  async sensingDeepDive(
    technologyName: string,
    domain: string,
    opts?: { seed_question?: string; seed_urls?: string[] },
  ): Promise<{ status: string; tracking_id: string }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/deep-dive`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          technology_name: technologyName,
          domain,
          seed_question: opts?.seed_question || '',
          seed_urls: opts?.seed_urls || [],
        }),
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
    report_tracking_id?: string;
    company_names: string[];
    technology_names?: string[];
    domain?: string;
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

  async sensingModelReleases(lookbackDays: number = 30): Promise<{
    status: string;
    lookback_days: number;
    count: number;
    model_releases: ModelRelease[];
  }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/model-releases`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ lookback_days: lookbackDays }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to fetch model releases');
    return data;
  },

  async sensingKeyCompaniesStart(body: {
    company_names: string[];
    highlight_domain?: string;
    period_days?: number;
  }): Promise<{ status: string; tracking_id: string }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/key-companies`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to start Key Companies briefing');
    return data;
  },

  async sensingKeyCompaniesStatus(
    trackingId: string,
  ): Promise<{ status: string; data?: { report: KeyCompaniesReport; meta: KeyCompaniesMeta }; error?: string }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/key-companies/status/${trackingId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to get Key Companies status');
    return data;
  },

  async sensingKeyCompaniesHistory(): Promise<{ briefings: KeyCompaniesHistoryItem[] }> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/key-companies/history`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load Key Companies history');
    return data;
  },

  async sensingKeyCompaniesLoad(trackingId: string): Promise<KeyCompaniesFullLoad> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/key-companies/${trackingId}/full`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load Key Companies briefing');
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

  // ── Phase 1: telemetry / aliases / exclusions / BYO URLs / watchlists ──

  async sensingTelemetry(trackingId: string): Promise<TelemetrySummary | null> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/telemetry/${trackingId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (response.status === 404) return null;
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load telemetry');
    return data as TelemetrySummary;
  },

  async sensingGetAliases(): Promise<Record<string, string[]>> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/config/aliases`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load aliases');
    return (data.aliases || {}) as Record<string, string[]>;
  },

  async sensingSaveAliases(aliases: Record<string, string[]>): Promise<void> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/config/aliases`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ aliases }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to save aliases');
    }
  },

  async sensingGetExclusions(): Promise<ExclusionsMap> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/config/exclusions`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load exclusions');
    return (data.exclusions || {}) as ExclusionsMap;
  },

  async sensingSaveExclusions(exclusions: ExclusionsMap): Promise<void> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/config/exclusions`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ exclusions }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to save exclusions');
    }
  },

  async sensingGetByoUrls(): Promise<Record<string, string[]>> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/config/byo-urls`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load BYO URLs');
    return (data.byo_urls || {}) as Record<string, string[]>;
  },

  async sensingSaveByoUrls(byoUrls: Record<string, string[]>): Promise<void> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/config/byo-urls`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ byo_urls: byoUrls }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to save BYO URLs');
    }
  },

  async sensingListWatchlists(): Promise<Watchlist[]> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/watchlists`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to load watchlists');
    return (data.watchlists || []) as Watchlist[];
  },

  async sensingCreateWatchlist(body: {
    name: string;
    companies: string[];
    highlight_domain?: string;
    period_days?: number;
  }): Promise<Watchlist> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/watchlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to create watchlist');
    return data as Watchlist;
  },

  async sensingUpdateWatchlist(
    id: string,
    patch: Partial<Omit<Watchlist, 'id' | 'created_at' | 'updated_at'>>,
  ): Promise<Watchlist> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/watchlists/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(patch),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to update watchlist');
    return data as Watchlist;
  },

  async sensingDeleteWatchlist(id: string): Promise<void> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/watchlists/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to delete watchlist');
    }
  },

  // ──────────────────────────────────────────────────────────
  // Phase 3 — timeline + similar-companies
  // ──────────────────────────────────────────────────────────

  async sensingCompanyTimeline(
    companies: string[] = [],
  ): Promise<CompanyTimeline[]> {
    const token = getAuthToken();
    const q = companies.length
      ? `?companies=${encodeURIComponent(companies.join(','))}`
      : '';
    const response = await fetch(
      `${API_URL}/sensing/company-timeline${q}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.detail || 'Failed to load company timeline');
    return (data.timelines || []) as CompanyTimeline[];
  },

  async sensingSimilarCompanies(body: {
    company: string;
    domain?: string;
    existing?: string[];
    max_suggestions?: number;
  }): Promise<SimilarCompaniesResult> {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}/sensing/similar-companies`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.detail || 'Failed to suggest similar companies');
    return data as SimilarCompaniesResult;
  },

  // ──────────────────────────────────────────────────────────
  // Phase 4.2 — Scheduled Key Companies digests (#16)
  // ──────────────────────────────────────────────────────────

  async sensingScheduleKeyCompanies(body: {
    frequency: 'daily' | 'weekly' | 'biweekly' | 'monthly';
    email?: string;
    watchlist_id?: string;
    companies?: string[];
    highlight_domain?: string;
    period_days?: number;
  }): Promise<SensingSchedule> {
    const token = getAuthToken();
    const response = await fetch(
      `${API_URL}/sensing/key-companies/schedule`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      },
    );
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        data.detail || 'Failed to schedule Key Companies briefing',
      );
    return data as SensingSchedule;
  },

  // ──────────────────────────────────────────────────────────
  // Integrations + Notion export (#23)
  // ──────────────────────────────────────────────────────────

  async sensingListIntegrations(): Promise<{
    integrations: Record<string, Record<string, unknown>>;
  }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/sensing/integrations`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to list integrations');
    return data;
  },

  async sensingSetIntegration(body: {
    provider: 'notion' | 'jira' | 'linear';
    config: Record<string, unknown>;
  }): Promise<void> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/sensing/integrations`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to set integration');
    }
  },

  async sensingDeleteIntegration(
    provider: 'notion' | 'jira' | 'linear',
  ): Promise<void> {
    const token = getAuthToken();
    const res = await fetch(
      `${API_URL}/sensing/integrations/${provider}`,
      {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    if (!res.ok && res.status !== 404) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to delete integration');
    }
  },

  async sensingVerifyNotion(): Promise<{ status: string; bot: unknown }> {
    const token = getAuthToken();
    const res = await fetch(
      `${API_URL}/sensing/integrations/notion/verify`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Notion verification failed');
    return data;
  },

  async sensingExportKeyCompaniesToNotion(body: {
    tracking_id: string;
    parent_page_id?: string;
  }): Promise<{ status: string; page: { id: string; url: string } }> {
    const token = getAuthToken();
    const res = await fetch(
      `${API_URL}/sensing/export/notion/key-companies`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Notion export failed');
    return data;
  },

  async sensingExportCompanyAnalysisToNotion(body: {
    tracking_id: string;
    parent_page_id?: string;
  }): Promise<{ status: string; page: { id: string; url: string } }> {
    const token = getAuthToken();
    const res = await fetch(
      `${API_URL}/sensing/export/notion/company-analysis`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Notion export failed');
    return data;
  },

  // ──────────────────────────────────────────────────────────
  // Jira / Linear export (#24)
  // ──────────────────────────────────────────────────────────

  async sensingExportToJira(body: {
    items: Array<{
      company?: string;
      headline: string;
      category?: string;
      date?: string;
      summary?: string;
      source_url?: string;
      domain?: string;
    }>;
    issue_type?: string;
  }): Promise<{ created: Array<{ key: string; id: string }>; errors: string[] }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/sensing/export/jira`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok && res.status !== 207)
      throw new Error(data.detail || 'Jira export failed');
    return data;
  },

  async sensingExportToLinear(body: {
    items: Array<{
      company?: string;
      headline: string;
      category?: string;
      date?: string;
      summary?: string;
      source_url?: string;
      domain?: string;
    }>;
    priority?: number;
  }): Promise<{
    created: Array<{ identifier: string; url: string }>;
    errors: string[];
  }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/sensing/export/linear`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok && res.status !== 207)
      throw new Error(data.detail || 'Linear export failed');
    return data;
  },

  // ── Leading Indicator Radar (LIR) ──

  async lirRefresh(body?: {
    lookback_days?: number;
    max_per_source?: number;
  }): Promise<{ status: string; tracking_id: string; message: string }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR refresh failed');
    return data;
  },

  async lirStatus(trackingId: string): Promise<{
    status: string;
    data?: LIRRefreshResult;
    error?: string;
  }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/status/${trackingId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR status check failed');
    return data;
  },

  async lirCandidates(params?: {
    ring?: string;
    limit?: number;
    min_score?: number;
  }): Promise<{ candidates: LIRCandidate[]; total: number }> {
    const token = getAuthToken();
    const query = new URLSearchParams();
    if (params?.ring) query.set('ring', params.ring);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.min_score) query.set('min_score', String(params.min_score));
    const qs = query.toString();
    const res = await fetch(`${API_URL}/lir/candidates${qs ? `?${qs}` : ''}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR candidates fetch failed');
    return data;
  },

  async lirConceptDetail(conceptId: string): Promise<LIRConceptDetail> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/concepts/${encodeURIComponent(conceptId)}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR concept detail failed');
    return data;
  },

  async lirConceptTimeseries(
    conceptId: string,
    weeks?: number,
  ): Promise<{ concept_id: string; timeseries: LIRTimeseriesPoint[]; weeks: number }> {
    const token = getAuthToken();
    const qs = weeks ? `?weeks=${weeks}` : '';
    const res = await fetch(
      `${API_URL}/lir/concepts/${encodeURIComponent(conceptId)}/timeseries${qs}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR timeseries failed');
    return data;
  },

  async lirSources(): Promise<{ sources: LIRSourceInfo[]; total: number }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/sources`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR sources failed');
    return data;
  },

  async lirConceptRationale(conceptId: string): Promise<LIRRationale> {
    const token = getAuthToken();
    const res = await fetch(
      `${API_URL}/lir/concepts/${encodeURIComponent(conceptId)}/rationale`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR rationale failed');
    return data;
  },

  async lirPatterns(): Promise<{ patterns: LIRPattern[]; total: number }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/patterns`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR patterns failed');
    return data;
  },

  async lirBacktestRun(body?: {
    start_date?: string;
    end_date?: string;
    step_weeks?: number;
    concept_ids?: string[];
  }): Promise<{ status: string; tracking_id: string; run_id: string; message: string }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/backtest/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR backtest failed');
    return data;
  },

  async lirBacktestStatus(trackingId: string): Promise<{
    status: string;
    data?: LIRBacktestResult;
    error?: string;
  }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/backtest/${trackingId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'LIR backtest status failed');
    return data;
  },

  async lirSourceRefresh(sourceId: string): Promise<{ source_id: string; items_fetched: number }> {
    const token = getAuthToken();
    const res = await fetch(`${API_URL}/lir/sources/${encodeURIComponent(sourceId)}/refresh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Source refresh failed');
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
