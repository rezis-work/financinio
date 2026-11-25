import { env } from '$env/dynamic/public';
import type {
	Account,
	ActionDecisionResponse,
	AdminOverview,
	AdminUserSummary,
	AIUsageEvent,
	AuditLog,
	AuthTokenResponse,
	BudgetOverview,
	BudgetPeriod,
	CategorizationRule,
	Category,
	ChatMessage,
	ChatThread,
	ChatThreadDetail,
	DashboardSummary,
	DebtInput,
	DebtPayoffComparison,
	DeleteImportBatchResponse,
	DetectRecurringResponse,
	EmailDigestPreview,
	EmailDigestType,
	EmailPreferences,
	FinancialGoal,
	FinancialHealthProfile,
	GoalType,
	ImportBatch,
	ImportBatchDetail,
	MarketRiskProfile,
	MarketScannerResponse,
	MarketsOverview,
	NetWorthOverview,
	NetWorthSnapshot,
	NewsBriefingResponse,
	NewsCategory,
	NewsFeedResponse,
	PaperPortfolio,
	ParsedVoiceTransaction,
	ProactiveInsight,
	QuoteDetail,
	RecurringCadence,
	RecurringItem,
	RecurringOverview,
	SendEmailDigestResult,
	SymbolSearchHit,
	SystemStatus,
	Transaction,
	TransactionListResponse,
	User,
	UserMemoryItem,
	VoiceLanguage,
	VoiceTranscribeResult,
	WatchlistItem,
	WhatIfResponse
} from './types';

const API_BASE = env.PUBLIC_API_URL || 'http://localhost:8000/api/v1';

const ACCESS_KEY = 'financinio_access_token';
const REFRESH_KEY = 'financinio_refresh_token';

export function getStoredAccessToken(): string | null {
	if (typeof window === 'undefined') return null;
	return localStorage.getItem(ACCESS_KEY);
}

export function getStoredRefreshToken(): string | null {
	if (typeof window === 'undefined') return null;
	return localStorage.getItem(REFRESH_KEY);
}

export function saveTokens(access: string, refresh: string): void {
	if (typeof window === 'undefined') return;
	localStorage.setItem(ACCESS_KEY, access);
	localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
	if (typeof window === 'undefined') return;
	localStorage.removeItem(ACCESS_KEY);
	localStorage.removeItem(REFRESH_KEY);
}

export class ApiError extends Error {
	status: number;
	constructor(status: number, message: string) {
		super(message);
		this.status = status;
	}
}

async function tryRefreshToken(): Promise<string | null> {
	const refresh = getStoredRefreshToken();
	if (!refresh) return null;
	const res = await fetch(`${API_BASE}/auth/refresh`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		credentials: 'include',
		body: JSON.stringify({ refresh_token: refresh })
	});
	if (!res.ok) {
		clearTokens();
		return null;
	}
	const data: AuthTokenResponse = await res.json();
	saveTokens(data.access_token, data.refresh_token);
	return data.access_token;
}

async function request<T>(
	path: string,
	options: RequestInit = {},
	retryOn401 = true
): Promise<T> {
	const headers = new Headers(options.headers || {});
	const token = getStoredAccessToken();
	if (token) {
		headers.set('Authorization', `Bearer ${token}`);
	}
	if (!(options.body instanceof FormData) && !headers.has('Content-Type') && options.body) {
		headers.set('Content-Type', 'application/json');
	}

	const res = await fetch(`${API_BASE}${path}`, {
		...options,
		headers,
		credentials: 'include'
	});

	if (res.status === 401 && retryOn401) {
		const newToken = await tryRefreshToken();
		if (newToken) {
			return request<T>(path, options, false);
		}
	}

	if (!res.ok) {
		let detail = `Request failed (${res.status})`;
		try {
			const body = await res.json();
			if (typeof body.detail === 'string') detail = body.detail;
			else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
		} catch {
			// ignore non-json error body
		}
		throw new ApiError(res.status, detail);
	}

	if (res.status === 204) {
		return undefined as T;
	}
	return res.json();
}

export const api = {
	// Auth
	register: (payload: {
		email: string;
		password: string;
		full_name: string;
		base_currency: string;
	}) =>
		request<AuthTokenResponse>(
			'/auth/register',
			{ method: 'POST', body: JSON.stringify(payload) },
			false
		),

	login: (payload: { email: string; password: string }) =>
		request<AuthTokenResponse>(
			'/auth/login',
			{ method: 'POST', body: JSON.stringify(payload) },
			false
		),

	logout: async () => {
		const refresh = getStoredRefreshToken();
		try {
			await request<void>(
				'/auth/logout',
				{ method: 'POST', body: JSON.stringify({ refresh_token: refresh }) },
				false
			);
		} finally {
			clearTokens();
		}
	},

	me: () => request<User>('/auth/me'),

	updateMe: (payload: { full_name?: string; base_currency?: string; fiscal_start_day?: number }) =>
		request<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(payload) }),

	// Dashboard
	dashboardSummary: (months = 6) => request<DashboardSummary>(`/dashboard/summary?months=${months}`),
	systemStatus: () => request<SystemStatus>('/dashboard/system-status'),

	// Accounts
	listAccounts: (includeArchived = false) =>
		request<Account[]>(`/accounts?include_archived=${includeArchived}`),

	createAccount: (payload: {
		name: string;
		type: string;
		currency: string;
		initial_balance: string;
		institution?: string;
		color?: string;
	}) => request<Account>('/accounts', { method: 'POST', body: JSON.stringify(payload) }),

	updateAccount: (id: string, payload: Partial<Account>) =>
		request<Account>(`/accounts/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

	deleteAccount: (id: string) => request<void>(`/accounts/${id}`, { method: 'DELETE' }),

	// Categories & Rules
	listCategories: () => request<Category[]>('/categories'),
	createCategory: (payload: { name: string; kind: string; color: string; icon?: string }) =>
		request<Category>('/categories', { method: 'POST', body: JSON.stringify(payload) }),
	updateCategory: (
		id: string,
		payload: Partial<{ name: string; kind: string; color: string; icon: string }>
	) => request<Category>(`/categories/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
	deleteCategory: (id: string) => request<void>(`/categories/${id}`, { method: 'DELETE' }),

	listRules: () => request<CategorizationRule[]>('/categories/rules'),
	createRule: (payload: {
		match_pattern: string;
		match_type: 'contains' | 'exact' | 'regex';
		category_id: string;
		merchant_override?: string;
		priority?: number;
	}) => request<CategorizationRule>('/categories/rules', { method: 'POST', body: JSON.stringify(payload) }),

	deleteRule: (id: string) => request<void>(`/categories/rules/${id}`, { method: 'DELETE' }),

	// Transactions
	listTransactions: (params: Record<string, string | number | undefined> = {}) => {
		const qs = new URLSearchParams();
		for (const [k, v] of Object.entries(params)) {
			if (v !== undefined && v !== '') qs.set(k, String(v));
		}
		const query = qs.toString();
		return request<TransactionListResponse>(`/transactions${query ? `?${query}` : ''}`);
	},

	createTransaction: (payload: {
		account_id: string;
		category_id?: string | null;
		amount: string;
		direction: 'inflow' | 'outflow';
		occurred_at: string;
		merchant: string;
		description?: string;
		notes?: string;
		tags?: string[];
		is_transfer?: boolean;
		transfer_account_id?: string | null;
	}) => request<Transaction>('/transactions', { method: 'POST', body: JSON.stringify(payload) }),

	updateTransaction: (
		id: string,
		payload: Partial<{
			account_id: string;
			category_id: string | null;
			merchant_clean: string;
			description: string | null;
			notes: string | null;
			tags: string[];
			is_transfer: boolean;
			occurred_at: string;
			amount: string;
			direction: 'inflow' | 'outflow';
		}>
	) => request<Transaction>(`/transactions/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

	bulkCategorizeTransactions: (
		transactionIds: string[],
		categoryId: string | null,
		learnMemory = true
	) =>
		request<{ updated: number }>('/transactions/bulk-categorize', {
			method: 'POST',
			body: JSON.stringify({
				transaction_ids: transactionIds,
				category_id: categoryId,
				learn_memory: learnMemory
			})
		}),

	deleteTransaction: (id: string) => request<void>(`/transactions/${id}`, { method: 'DELETE' }),

	// AI Ingestion & HITL Review
	listImportBatches: () => request<ImportBatch[]>('/imports'),
	getImportBatch: (id: string) => request<ImportBatchDetail>(`/imports/${id}`),

	uploadDocument: (
		accountId: string,
		file: File,
		docTypeOverride?: 'csv' | 'xlsx' | 'pdf_statement' | 'bog_pdf' | 'receipt'
	) => {
		const form = new FormData();
		form.append('account_id', accountId);
		if (docTypeOverride) form.append('doc_type_override', docTypeOverride);
		form.append('file', file);
		return request<ImportBatchDetail>('/imports/upload', {
			method: 'POST',
			body: form
		});
	},

	uploadBogStatement: (accountId: string, file: File) => {
		const form = new FormData();
		form.append('account_id', accountId);
		form.append('file', file);
		return request<ImportBatchDetail>('/imports/bog', {
			method: 'POST',
			body: form
		});
	},

	commitImportBatch: (
		batchId: string,
		payload: {
			decisions: Array<{
				staged_id: string;
				user_approved: boolean;
				merchant_clean?: string;
				category_id?: string | null;
				direction?: 'inflow' | 'outflow';
				amount?: string;
				occurred_at?: string;
				description?: string | null;
			}>;
			skip_duplicates: boolean;
			learn_from_edits: boolean;
		}
	) =>
		request<ImportBatchDetail>(`/imports/${batchId}/commit`, {
			method: 'POST',
			body: JSON.stringify(payload)
		}),

	deleteImportBatch: (batchId: string, deleteTransactions = true) =>
		request<DeleteImportBatchResponse>(
			`/imports/${batchId}?delete_transactions=${deleteTransactions}`,
			{ method: 'DELETE' }
		),

	// Phase 3: Budgets
	getBudgets: (month?: string) =>
		request<BudgetOverview>(`/budgets${month ? `?month=${month}` : ''}`),

	upsertBudget: (payload: {
		category_id: string;
		amount: string;
		period?: BudgetPeriod;
		rollover?: boolean;
		alert_threshold_pct?: number;
	}) => request<BudgetOverview>('/budgets', { method: 'POST', body: JSON.stringify(payload) }),

	updateBudget: (
		id: string,
		payload: Partial<{
			amount: string;
			rollover: boolean;
			alert_threshold_pct: number;
			is_active: boolean;
		}>
	) => request<BudgetOverview>(`/budgets/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

	apply503020Template: (monthlyIncome: string) =>
		request<BudgetOverview>('/budgets/apply-50-30-20', {
			method: 'POST',
			body: JSON.stringify({ monthly_income: monthlyIncome })
		}),

	deleteBudget: (id: string) => request<void>(`/budgets/${id}`, { method: 'DELETE' }),

	// Phase 3: Recurring & Subscriptions
	getRecurring: () => request<RecurringOverview>('/recurring'),
	detectRecurring: () => request<DetectRecurringResponse>('/recurring/detect', { method: 'POST' }),

	createRecurring: (payload: {
		merchant_name: string;
		amount: string;
		currency?: string;
		direction?: 'outflow' | 'inflow';
		cadence: RecurringCadence;
		next_due_date: string;
		category_id?: string | null;
		is_subscription?: boolean;
	}) => request<RecurringItem>('/recurring', { method: 'POST', body: JSON.stringify(payload) }),

	updateRecurring: (id: string, payload: Partial<RecurringItem>) =>
		request<RecurringItem>(`/recurring/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

	deleteRecurring: (id: string) => request<void>(`/recurring/${id}`, { method: 'DELETE' }),

	// Phase 3: Net Worth, Goals & Simulators
	getNetWorth: () => request<NetWorthOverview>('/wealth/net-worth'),
	captureNetWorthSnapshot: () =>
		request<NetWorthSnapshot>('/wealth/net-worth/snapshot', { method: 'POST' }),

	listGoals: () => request<FinancialGoal[]>('/wealth/goals'),
	createGoal: (payload: {
		name: string;
		goal_type: GoalType;
		target_amount: string;
		current_amount?: string;
		monthly_contribution?: string;
		target_date?: string | null;
		color?: string;
	}) => request<FinancialGoal>('/wealth/goals', { method: 'POST', body: JSON.stringify(payload) }),

	updateGoal: (
		id: string,
		payload: Partial<{
			name: string;
			goal_type: GoalType;
			target_amount: string;
			current_amount: string;
			monthly_contribution: string;
			target_date: string | null;
			color: string;
			is_completed: boolean;
		}>
	) => request<FinancialGoal>(`/wealth/goals/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

	contributeGoal: (id: string, amount: string) =>
		request<FinancialGoal>(`/wealth/goals/${id}/contribute`, {
			method: 'POST',
			body: JSON.stringify({ amount })
		}),

	deleteGoal: (id: string) => request<void>(`/wealth/goals/${id}`, { method: 'DELETE' }),

	simulateDebtPayoff: (debts: DebtInput[], extraMonthlyPayment: string) =>
		request<DebtPayoffComparison>('/wealth/simulate/debt-payoff', {
			method: 'POST',
			body: JSON.stringify({ debts, extra_monthly_payment: extraMonthlyPayment })
		}),

	simulateWhatIf: (payload: {
		starting_savings: string;
		monthly_income: string;
		monthly_expenses: string;
		income_delta_monthly: string;
		expense_delta_monthly: string;
		one_time_impact: string;
		annual_return_pct: string;
		horizon_months: number;
	}) =>
		request<WhatIfResponse>('/wealth/simulate/what-if', {
			method: 'POST',
			body: JSON.stringify(payload)
		}),

	// Phase 4: Luna Multi-Agent AI Advisor & Insights
	listThreads: () => request<ChatThread[]>('/advisor/threads'),
	createThread: (title?: string) =>
		request<ChatThread>('/advisor/threads', {
			method: 'POST',
			body: JSON.stringify(title ? { title } : {})
		}),
	getThread: (threadId: string) => request<ChatThreadDetail>(`/advisor/threads/${threadId}`),
	deleteThread: (threadId: string) =>
		request<void>(`/advisor/threads/${threadId}`, { method: 'DELETE' }),

	decideAdvisorAction: (
		threadId: string,
		messageId: string,
		approved: boolean,
		overrideParams?: Record<string, unknown>
	) =>
		request<ActionDecisionResponse>(`/advisor/threads/${threadId}/actions/${messageId}`, {
			method: 'POST',
			body: JSON.stringify({ approved, override_params: overrideParams })
		}),

	listMemories: () => request<UserMemoryItem[]>('/advisor/memories'),
	addMemory: (fact: string, category = 'preference') =>
		request<UserMemoryItem>('/advisor/memories', {
			method: 'POST',
			body: JSON.stringify({ fact, category })
		}),
	deleteMemory: (memoryId: string) =>
		request<void>(`/advisor/memories/${memoryId}`, { method: 'DELETE' }),

	listInsights: () => request<ProactiveInsight[]>('/advisor/insights'),
	generateInsights: () =>
		request<ProactiveInsight[]>('/advisor/insights/generate', { method: 'POST' }),
	dismissInsight: (insightId: string) =>
		request<void>(`/advisor/insights/${insightId}/dismiss`, { method: 'PATCH' }),
	financialHealthScore: () => request<FinancialHealthProfile>('/advisor/health-score'),

	streamAdvisorMessage: async (
		threadId: string,
		message: string,
		handlers: {
			onStatus?: (label: string, node: string) => void;
			onToken?: (chunk: string) => void;
			onActionRequired?: (msg: ChatMessage) => void;
			onDone?: (msg: ChatMessage) => void;
			onError?: (detail: string) => void;
		},
		options: { webSearchMode?: 'auto' | 'on' | 'off' } = {}
	): Promise<void> => {
		let token = getStoredAccessToken();
		const doFetch = (authTok: string | null) =>
			fetch(`${API_BASE}/advisor/threads/${threadId}/stream`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					...(authTok ? { Authorization: `Bearer ${authTok}` } : {})
				},
				credentials: 'include',
				body: JSON.stringify({
					message,
					web_search_mode: options.webSearchMode ?? 'auto'
				})
			});

		let res = await doFetch(token);
		if (res.status === 401) {
			token = await tryRefreshToken();
			if (token) res = await doFetch(token);
		}
		if (!res.ok || !res.body) {
			let detail = `Stream failed (${res.status})`;
			try {
				const errBody = await res.json();
				if (typeof errBody.detail === 'string') detail = errBody.detail;
			} catch {
				// ignore
			}
			throw new ApiError(res.status, detail);
		}

		const reader = res.body.getReader();
		const decoder = new TextDecoder();
		let buffer = '';

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });

			const parts = buffer.split('\n\n');
			buffer = parts.pop() || '';

			for (const block of parts) {
				if (!block.trim()) continue;
				let evName = 'message';
				let dataRaw = '{}';
				for (const line of block.split('\n')) {
					if (line.startsWith('event:')) evName = line.slice(6).trim();
					else if (line.startsWith('data:')) dataRaw = line.slice(5).trim();
				}
				try {
					const parsed = JSON.parse(dataRaw);
					if (evName === 'status') handlers.onStatus?.(parsed.label || '', parsed.node || '');
					else if (evName === 'token') handlers.onToken?.(parsed.content || '');
					else if (evName === 'action_required') handlers.onActionRequired?.(parsed.message);
					else if (evName === 'done') handlers.onDone?.(parsed.message);
					else if (evName === 'error') handlers.onError?.(parsed.detail || 'Stream error');
				} catch {
					// ignore partial JSON
				}
			}
		}
	},

	// Phase 5: Data Export, Audit Logs & Account Deletion
	listAuditLogs: () => request<AuditLog[]>('/data/audit-logs'),

	downloadTransactionsCsv: async () => {
		const token = getStoredAccessToken();
		const res = await fetch(`${API_BASE}/data/export/csv`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
			credentials: 'include'
		});
		if (!res.ok) throw new ApiError(res.status, 'CSV export failed');
		return res.blob();
	},

	exportFullBackupJson: () => request<Record<string, unknown>>('/data/export/json'),

	deleteMyAccount: (password: string, confirmPhrase: string) =>
		request<void>('/data/account', {
			method: 'DELETE',
			body: JSON.stringify({ password, confirm_phrase: confirmPhrase })
		}),

	// Admin Dashboard & User AI Quotas
	adminOverview: () => request<AdminOverview>('/admin/overview'),

	adminListUsers: (params: { search?: string; tier?: string } = {}) => {
		const qs = new URLSearchParams();
		if (params.search) qs.set('search', params.search);
		if (params.tier && params.tier !== 'all') qs.set('tier', params.tier);
		const q = qs.toString();
		return request<AdminUserSummary[]>(`/admin/users${q ? `?${q}` : ''}`);
	},

	adminUpdateUserAccess: (
		userId: string,
		payload: {
			has_unlimited_ai?: boolean;
			ai_token_limit?: number;
			reset_tokens_used?: boolean;
			role?: 'user' | 'admin';
			is_active?: boolean;
		}
	) =>
		request<AdminUserSummary>(`/admin/users/${userId}/access`, {
			method: 'PATCH',
			body: JSON.stringify(payload)
		}),

	adminUserUsage: (userId: string) => request<AIUsageEvent[]>(`/admin/users/${userId}/usage`),

	// Markets, Forex & AI Trader Bot
	marketsOverview: (forceRefresh = false) =>
		request<MarketsOverview>(`/markets/overview${forceRefresh ? '?force_refresh=true' : ''}`),

	marketsScanner: (
		category: 'all' | 'stock' | 'etf' | 'forex' | 'crypto' | 'commodity' = 'all',
		riskProfile?: MarketRiskProfile
	) => {
		const qs = new URLSearchParams({ category });
		if (riskProfile) qs.set('risk_profile', riskProfile);
		return request<MarketScannerResponse>(`/markets/scanner?${qs.toString()}`);
	},

	marketsQuoteDetail: (symbol: string, rangeStr: '1mo' | '3mo' | '6mo' | '1y' = '6mo') =>
		request<QuoteDetail>(
			`/markets/quote/${encodeURIComponent(symbol)}?range_str=${rangeStr}`
		),

	marketsSearch: (q: string) =>
		request<SymbolSearchHit[]>(`/markets/search?q=${encodeURIComponent(q)}`),

	listWatchlist: () => request<WatchlistItem[]>('/markets/watchlist'),

	addWatchlistItem: (payload: {
		symbol: string;
		display_name?: string;
		asset_type?: string;
		target_buy_price?: string | null;
		target_sell_price?: string | null;
		alert_enabled?: boolean;
		notes?: string | null;
	}) => request<WatchlistItem>('/markets/watchlist', { method: 'POST', body: JSON.stringify(payload) }),

	updateWatchlistItem: (
		id: string,
		payload: Partial<{
			target_buy_price: string | null;
			target_sell_price: string | null;
			alert_enabled: boolean;
			notes: string | null;
		}>
	) =>
		request<WatchlistItem>(`/markets/watchlist/${id}`, {
			method: 'PATCH',
			body: JSON.stringify(payload)
		}),

	deleteWatchlistItem: (id: string) =>
		request<void>(`/markets/watchlist/${id}`, { method: 'DELETE' }),

	getPaperPortfolio: () => request<PaperPortfolio>('/markets/paper/portfolio'),

	executePaperTrade: (payload: {
		symbol: string;
		side: 'buy' | 'sell';
		usd_amount?: string;
		quantity?: string;
		stop_loss?: string | null;
		take_profit?: string | null;
		rationale?: string | null;
	}) =>
		request<PaperPortfolio>('/markets/paper/trade', {
			method: 'POST',
			body: JSON.stringify(payload)
		}),

	updatePaperSettings: (riskProfile: MarketRiskProfile) =>
		request<PaperPortfolio>('/markets/paper/settings', {
			method: 'PATCH',
			body: JSON.stringify({ risk_profile: riskProfile })
		}),

	resetPaperPortfolio: () =>
		request<PaperPortfolio>('/markets/paper/reset', { method: 'POST' }),

	// Voice-to-Ledger & Talk to Luna
	voiceTranscribe: (audioBlob: Blob, language: VoiceLanguage = 'auto') => {
		const ext = audioBlob.type.includes('mp4')
			? 'm4a'
			: audioBlob.type.includes('ogg')
				? 'ogg'
				: 'webm';
		const form = new FormData();
		form.append('file', audioBlob, `voice.${ext}`);
		form.append('language', language);
		return request<VoiceTranscribeResult>('/voice/transcribe', {
			method: 'POST',
			body: form
		});
	},

	voiceParseTransaction: (transcript: string, language: VoiceLanguage = 'auto') =>
		request<ParsedVoiceTransaction>('/voice/parse-transaction', {
			method: 'POST',
			body: JSON.stringify({ transcript, language })
		}),

	voiceSpeak: async (text: string, voice: 'nova' | 'alloy' | 'shimmer' = 'nova'): Promise<Blob> => {
		let token = getStoredAccessToken();
		const doFetch = (authTok: string | null) =>
			fetch(`${API_BASE}/voice/speak`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					...(authTok ? { Authorization: `Bearer ${authTok}` } : {})
				},
				credentials: 'include',
				body: JSON.stringify({ text, voice })
			});

		let res = await doFetch(token);
		if (res.status === 401) {
			token = await tryRefreshToken();
			if (token) res = await doFetch(token);
		}
		if (!res.ok) {
			throw new ApiError(res.status, 'Speech synthesis unavailable');
		}
		return res.blob();
	},

	// Scheduled Email Digests (Resend)
	getEmailPreferences: () => request<EmailPreferences>('/emails/preferences'),

	updateEmailPreferences: (payload: {
		email_weekly_briefing?: boolean;
		email_monthly_wrapped?: boolean;
	}) =>
		request<EmailPreferences>('/emails/preferences', {
			method: 'PATCH',
			body: JSON.stringify(payload)
		}),

	previewEmailDigest: (digestType: EmailDigestType) =>
		request<EmailDigestPreview>(`/emails/preview?digest_type=${digestType}`),

	sendEmailDigestNow: (digestType: EmailDigestType) =>
		request<SendEmailDigestResult>('/emails/send-test', {
			method: 'POST',
			body: JSON.stringify({ digest_type: digestType })
		}),

	// Global Finance Newsroom
	newsFeed: (
		params: { category?: NewsCategory; q?: string; forceRefresh?: boolean } = {}
	) => {
		const qs = new URLSearchParams();
		if (params.category) qs.set('category', params.category);
		if (params.q) qs.set('q', params.q);
		if (params.forceRefresh) qs.set('force_refresh', 'true');
		const qStr = qs.toString();
		return request<NewsFeedResponse>(`/news/feed${qStr ? `?${qStr}` : ''}`);
	},

	newsAiBriefing: (category: NewsCategory = 'all') =>
		request<NewsBriefingResponse>('/news/ai-briefing', {
			method: 'POST',
			body: JSON.stringify({ category })
		})
};
