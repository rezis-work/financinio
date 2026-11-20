export interface User {
	id: string;
	email: string;
	full_name: string;
	base_currency: string;
	fiscal_start_day: number;
	created_at: string;
}

export interface AuthTokenResponse {
	access_token: string;
	refresh_token: string;
	token_type: string;
	expires_in: number;
	user: User;
}

export type AccountType = 'checking' | 'savings' | 'credit' | 'cash' | 'investment' | 'loan';

export interface Account {
	id: string;
	name: string;
	type: AccountType;
	currency: string;
	initial_balance: string;
	current_balance: string;
	institution: string | null;
	color: string;
	is_archived: boolean;
	created_at: string;
	updated_at: string;
}

export type CategoryKind = 'income' | 'expense' | 'transfer';

export interface Category {
	id: string;
	name: string;
	kind: CategoryKind;
	icon: string;
	color: string;
	parent_id: string | null;
	is_system: boolean;
}

export interface CategorizationRule {
	id: string;
	match_pattern: string;
	match_type: 'contains' | 'exact' | 'regex';
	category_id: string;
	merchant_override: string | null;
	priority: number;
	is_active: boolean;
}

export type TransactionDirection = 'inflow' | 'outflow';

export interface Transaction {
	id: string;
	account_id: string;
	category_id: string | null;
	amount: string;
	currency: string;
	base_amount: string;
	fx_rate: string;
	direction: TransactionDirection;
	occurred_at: string;
	merchant_raw: string;
	merchant_clean: string;
	description: string | null;
	notes: string | null;
	tags: string[];
	is_transfer: boolean;
	transfer_peer_id: string | null;
	source_document_id: string | null;
	ai_confidence: string | null;
	created_at: string;
}

export interface TransactionListResponse {
	items: Transaction[];
	total: number;
	limit: number;
	offset: number;
}

export interface MonthlyCashFlowPoint {
	month: string;
	income: string;
	expenses: string;
	net: string;
}

export interface CategorySpendItem {
	category_id: string | null;
	category_name: string;
	color: string;
	total: string;
	percentage: number;
	transaction_count: number;
}

export interface DashboardSummary {
	base_currency: string;
	total_assets: string;
	total_liabilities: string;
	net_worth: string;
	period_income: string;
	period_expenses: string;
	period_net: string;
	savings_rate: number;
	monthly_cash_flow: MonthlyCashFlowPoint[];
	category_breakdown: CategorySpendItem[];
	recent_transactions: Transaction[];
	pending_review_batches: number;
}

export interface StagedTransaction {
	id: string;
	batch_id: string;
	occurred_at: string;
	amount: string;
	currency: string;
	direction: TransactionDirection;
	merchant_raw: string;
	merchant_clean: string;
	description: string | null;
	suggested_category_id: string | null;
	confidence: string;
	categorization_source: string;
	is_duplicate: boolean;
	needs_review: boolean;
	user_approved: boolean;
}

export interface ImportBatch {
	id: string;
	document_id: string;
	account_id: string;
	langgraph_thread_id: string;
	filename: string;
	doc_type: string;
	status: 'processing' | 'needs_review' | 'committed' | 'failed';
	total_rows: number;
	duplicate_rows: number;
	needs_review_rows: number;
	committed_rows: number;
	balance_reconciled: boolean | null;
	reconciliation_note: string | null;
	error_message: string | null;
	created_at: string;
}

export interface ImportBatchDetail extends ImportBatch {
	staged_transactions: StagedTransaction[];
}

export interface SystemStatus {
	database: string;
	storage_backend: string;
	upstash_vector_connected: boolean;
	llm_provider: string;
	llm_model_fast: string;
	llm_model_vision: string;
	llm_configured: boolean;
	langsmith_tracing: boolean;
	langsmith_project: string;
}

// --- Phase 3: Budgets, Recurring, Net Worth, Goals & Simulators ---

export type BudgetPeriod = 'monthly' | 'quarterly' | 'yearly';

export interface BudgetStatus {
	id: string;
	category_id: string;
	category_name: string;
	category_color: string;
	period: BudgetPeriod;
	amount: string;
	rollover: boolean;
	rollover_carry: string;
	effective_limit: string;
	spent: string;
	remaining: string;
	percent_used: number;
	pace_pct: number;
	alert_threshold_pct: number;
	status: 'on_track' | 'pacing_fast' | 'warning' | 'over_budget';
	is_active: boolean;
}

export interface BudgetOverview {
	month: string;
	days_elapsed: number;
	days_in_month: number;
	pace_pct: number;
	total_budgeted: string;
	total_spent: string;
	total_remaining: string;
	budgets: BudgetStatus[];
}

export type RecurringCadence = 'weekly' | 'biweekly' | 'monthly' | 'quarterly' | 'yearly';

export interface RecurringItem {
	id: string;
	account_id: string | null;
	category_id: string | null;
	merchant_name: string;
	amount: string;
	previous_amount: string | null;
	currency: string;
	direction: TransactionDirection;
	cadence: RecurringCadence;
	next_due_date: string;
	last_seen_date: string | null;
	is_subscription: boolean;
	is_active: boolean;
	auto_detected: boolean;
	price_change_pct: string | null;
	monthly_equivalent: string;
}

export interface RecurringOverview {
	monthly_recurring_expenses: string;
	annual_recurring_expenses: string;
	monthly_recurring_income: string;
	upcoming_30d_total: string;
	price_hike_alerts: RecurringItem[];
	items: RecurringItem[];
}

export interface DetectRecurringResponse {
	detected_new: number;
	updated_existing: number;
	price_hikes_found: number;
	overview: RecurringOverview;
}

export interface NetWorthSnapshot {
	id: string;
	snapshot_date: string;
	total_assets: string;
	total_liabilities: string;
	net_worth: string;
	breakdown: Record<string, { name: string; type: string; balance: string; classification: string }>;
	created_at: string;
}

export interface NetWorthAccountBreakdown {
	account_id: string;
	name: string;
	type: string;
	currency: string;
	balance: string;
	classification: 'asset' | 'liability';
}

export interface NetWorthOverview {
	base_currency: string;
	current_assets: string;
	current_liabilities: string;
	current_net_worth: string;
	change_amount: string | null;
	change_pct: number | null;
	accounts: NetWorthAccountBreakdown[];
	snapshots: NetWorthSnapshot[];
}

export type GoalType =
	| 'emergency_fund'
	| 'savings'
	| 'debt_payoff'
	| 'investment'
	| 'purchase'
	| 'retirement';

export interface FinancialGoal {
	id: string;
	linked_account_id: string | null;
	name: string;
	goal_type: GoalType;
	target_amount: string;
	current_amount: string;
	monthly_contribution: string;
	target_date: string | null;
	color: string;
	is_completed: boolean;
	progress_pct: number;
	remaining_amount: string;
	required_monthly: string | null;
	projected_completion_date: string | null;
}

export interface DebtInput {
	name: string;
	balance: string;
	apr: string;
	min_payment: string;
}

export interface DebtStrategyResult {
	strategy: 'snowball' | 'avalanche';
	months_to_payoff: number;
	total_interest_paid: string;
	total_paid: string;
	payoff_order: string[];
	monthly_balance_curve: Array<{ month: number; total_balance: number }>;
}

export interface DebtPayoffComparison {
	snowball: DebtStrategyResult;
	avalanche: DebtStrategyResult;
	recommended_strategy: 'snowball' | 'avalanche';
	interest_saved_by_avalanche: string;
	months_saved_by_avalanche: number;
}

export interface WhatIfPoint {
	month_index: number;
	label: string;
	baseline_balance: string;
	scenario_balance: string;
	difference: string;
}

export interface WhatIfResponse {
	baseline_monthly_net: string;
	scenario_monthly_net: string;
	baseline_end_balance: string;
	scenario_end_balance: string;
	net_impact: string;
	scenario_runway_months: number | null;
	points: WhatIfPoint[];
}

// --- Phase 4: Luna Multi-Agent AI Advisor & Proactive Insights ---

export interface ChatCitation {
	source: string;
	label: string;
}

export interface ChatMessage {
	id: string;
	thread_id: string;
	role: 'user' | 'assistant';
	content: string;
	active_agent: string | null;
	citations: ChatCitation[];
	pending_action: Record<string, unknown> | null;
	action_status: 'none' | 'pending' | 'executed' | 'rejected';
	created_at: string;
}

export interface ChatThread {
	id: string;
	langgraph_thread_id: string;
	title: string;
	last_message_at: string;
	created_at: string;
}

export interface ChatThreadDetail extends ChatThread {
	messages: ChatMessage[];
}

export interface ActionDecisionResponse {
	message: ChatMessage;
	executed_result: Record<string, unknown> | null;
}

export interface UserMemoryItem {
	id: string;
	fact: string;
	category: string;
	score: number | null;
}

export interface ProactiveInsight {
	id: string;
	insight_type: string;
	severity: 'info' | 'warning' | 'alert';
	title: string;
	summary: string;
	data: Record<string, unknown>;
	is_read: boolean;
	is_dismissed: boolean;
	created_at: string;
}

// --- Phase 5: Audit Logs & Privacy ---

export interface AuditLog {
	id: string;
	action: string;
	resource_type: string;
	resource_id: string | null;
	ip_address: string | null;
	details: Record<string, unknown>;
	created_at: string;
}
