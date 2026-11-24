<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError, clearTokens } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import type {
		AuditLog,
		CategorizationRule,
		Category,
		CategoryKind,
		SystemStatus
	} from '$lib/api/types';
	import { formatDate } from '$lib/utils/format';
	import FinancinioLoader from '$lib/components/FinancinioLoader.svelte';
	import {
		User as UserIcon,
		Tag,
		Wand2,
		Shield,
		Cpu,
		Plus,
		Trash2,
		CheckCircle2,
		AlertTriangle,
		Database,
		Activity,
		Download,
		ShieldAlert,
		History,
		Eye,
		EyeOff,
		Search,
		Pencil,
		Check,
		X,
		Sparkles,
		HardDrive,
		RefreshCw,
		FlaskConical,
		FileJson,
		FileSpreadsheet,
		Lock,
		ChevronRight
	} from 'lucide-svelte';

	type SettingsTab = 'profile' | 'categories' | 'rules' | 'security' | 'system';

	const COLOR_SWATCHES = [
		'#10b981',
		'#06b6d4',
		'#3b82f6',
		'#8b5cf6',
		'#ec4899',
		'#f43f5e',
		'#f97316',
		'#eab308',
		'#84cc16',
		'#64748b'
	];

	const QUICK_CURRENCIES = [
		{ code: 'GEL', label: '₾ GEL' },
		{ code: 'USD', label: '$ USD' },
		{ code: 'EUR', label: '€ EUR' },
		{ code: 'GBP', label: '£ GBP' }
	];

	let activeTab = $state<SettingsTab>('profile');
	let loading = $state(true);

	// Profile state
	let fullName = $state(auth.user?.full_name || '');
	let baseCurrency = $state(auth.user?.base_currency || 'USD');
	let fiscalStartDay = $state(auth.user?.fiscal_start_day || 1);
	let savingProfile = $state(false);
	let privacyMode = $state(false);

	// Data state
	let categories = $state<Category[]>([]);
	let rules = $state<CategorizationRule[]>([]);
	let statusInfo = $state<SystemStatus | null>(null);
	let auditLogs = $state<AuditLog[]>([]);
	let refreshingSystem = $state(false);

	// Banners
	let error = $state<string | null>(null);
	let toast = $state<string | null>(null);

	// Categories Studio state
	let catFilter = $state<'all' | CategoryKind>('all');
	let catSearch = $state('');
	let newCatName = $state('');
	let newCatKind = $state<CategoryKind>('expense');
	let newCatColor = $state('#10b981');
	let creatingCat = $state(false);
	let editingCatId = $state<string | null>(null);
	let editCatName = $state('');
	let editCatColor = $state('#10b981');
	let savingCat = $state(false);
	let confirmDeleteCat = $state<Category | null>(null);
	let deletingCat = $state(false);

	// Rules Studio state
	let ruleSearch = $state('');
	let matchPattern = $state('');
	let matchType = $state<'contains' | 'exact' | 'regex'>('contains');
	let categoryId = $state('');
	let merchantOverride = $state('');
	let rulePriority = $state(50);
	let creatingRule = $state(false);
	let testMerchantInput = $state('');

	// Exports & Security state
	let exportingCsv = $state(false);
	let exportingJson = $state(false);
	let auditSearch = $state('');
	let showAllAudit = $state(false);
	let dangerZoneOpen = $state(false);
	let deletePassword = $state('');
	let deletePhrase = $state('');
	let deletingAccount = $state(false);

	function showToast(msg: string) {
		toast = msg;
		error = null;
	}

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('financinio_privacy_mode', privacyMode ? '1' : '0');
		}
		showToast(
			privacyMode
				? 'Privacy Mode enabled across all pages.'
				: 'Privacy Mode disabled — amounts visible.'
		);
	}

	onMount(async () => {
		loading = true;
		try {
			if (typeof localStorage !== 'undefined') {
				privacyMode = localStorage.getItem('financinio_privacy_mode') === '1';
			}
			const [cats, rls, sys, logs] = await Promise.all([
				api.listCategories(),
				api.listRules(),
				api.systemStatus(),
				api.listAuditLogs()
			]);
			categories = cats;
			rules = rls;
			statusInfo = sys;
			auditLogs = logs;
			if (cats.length > 0 && !categoryId) categoryId = cats[0].id;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load settings';
		} finally {
			loading = false;
		}
	});

	// Derived helpers
	let catMap = $derived(new Map(categories.map((c) => [c.id, c])));

	let initials = $derived.by(() => {
		const name = (auth.user?.full_name || auth.user?.email || 'U').trim();
		const parts = name.split(/\s+/);
		if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
		return name.slice(0, 2).toUpperCase();
	});

	let profileDirty = $derived(
		fullName.trim() !== (auth.user?.full_name || '').trim() ||
			baseCurrency.toUpperCase() !== (auth.user?.base_currency || 'USD').toUpperCase() ||
			Number(fiscalStartDay) !== Number(auth.user?.fiscal_start_day || 1)
	);

	let aiQuotaPct = $derived.by(() => {
		if (!auth.user || auth.user.has_unlimited_ai) return 0;
		const limit = Math.max(1, auth.user.ai_token_limit || 1);
		return Math.min(100, Math.round((auth.user.ai_tokens_used / limit) * 100));
	});

	let filteredCategories = $derived.by(() => {
		const q = catSearch.trim().toLowerCase();
		return categories.filter((c) => {
			if (catFilter !== 'all' && c.kind !== catFilter) return false;
			if (q && !c.name.toLowerCase().includes(q)) return false;
			return true;
		});
	});

	let filteredRules = $derived.by(() => {
		const q = ruleSearch.trim().toLowerCase();
		return rules.filter((r) => {
			if (!q) return true;
			const catName = catMap.get(r.category_id)?.name ?? '';
			return `${r.match_pattern} ${r.merchant_override ?? ''} ${catName} ${r.match_type}`
				.toLowerCase()
				.includes(q);
		});
	});

	function testSingleRule(
		sample: string,
		pattern: string,
		type: 'contains' | 'exact' | 'regex'
	): boolean {
		const s = sample.trim();
		const p = pattern.trim();
		if (!s || !p) return false;
		if (type === 'exact') return s.toLowerCase() === p.toLowerCase();
		if (type === 'contains') return s.toLowerCase().includes(p.toLowerCase());
		try {
			return new RegExp(p, 'i').test(s);
		} catch {
			return false;
		}
	}

	let liveRuleTestResult = $derived.by(() => {
		const sample = testMerchantInput.trim();
		if (!sample) return null;

		const draftMatches = matchPattern.trim()
			? testSingleRule(sample, matchPattern, matchType)
			: false;

		const matchedSaved = rules.find((r) => testSingleRule(sample, r.match_pattern, r.match_type));
		return { draftMatches, matchedSaved };
	});

	let filteredAuditLogs = $derived.by(() => {
		const q = auditSearch.trim().toLowerCase();
		const list = q
			? auditLogs.filter((l) =>
					`${l.action} ${l.resource_type} ${l.ip_address ?? ''}`.toLowerCase().includes(q)
				)
			: auditLogs;
		return showAllAudit ? list : list.slice(0, 10);
	});

	let canDeleteAccount = $derived(
		deletePassword.trim().length > 0 && deletePhrase.trim() === 'DELETE MY ACCOUNT'
	);

	// Actions
	async function saveProfile(e: SubmitEvent) {
		e.preventDefault();
		savingProfile = true;
		error = null;
		try {
			const updated = await api.updateMe({
				full_name: fullName.trim(),
				base_currency: baseCurrency.trim().toUpperCase(),
				fiscal_start_day: Number(fiscalStartDay)
			});
			auth.user = updated;
			fullName = updated.full_name;
			baseCurrency = updated.base_currency;
			fiscalStartDay = updated.fiscal_start_day;
			showToast('Workspace preferences saved.');
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Profile update failed';
		} finally {
			savingProfile = false;
		}
	}

	async function handleCreateCategory(e: SubmitEvent) {
		e.preventDefault();
		if (!newCatName.trim()) return;
		creatingCat = true;
		error = null;
		try {
			const created = await api.createCategory({
				name: newCatName.trim(),
				kind: newCatKind,
				color: newCatColor
			});
			categories = [...categories, created].sort((a, b) => a.name.localeCompare(b.name));
			newCatName = '';
			showToast(`Created category "${created.name}".`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to create category';
		} finally {
			creatingCat = false;
		}
	}

	function startEditCategory(cat: Category) {
		editingCatId = cat.id;
		editCatName = cat.name;
		editCatColor = cat.color || '#10b981';
	}

	async function saveEditCategory(catId: string) {
		if (!editCatName.trim()) return;
		savingCat = true;
		error = null;
		try {
			const updated = await api.updateCategory(catId, {
				name: editCatName.trim(),
				color: editCatColor
			});
			categories = categories.map((c) => (c.id === catId ? updated : c));
			editingCatId = null;
			showToast(`Updated category "${updated.name}".`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to update category';
		} finally {
			savingCat = false;
		}
	}

	async function handleConfirmDeleteCategory() {
		if (!confirmDeleteCat || deletingCat) return;
		const target = confirmDeleteCat;
		deletingCat = true;
		error = null;
		try {
			await api.deleteCategory(target.id);
			categories = categories.filter((c) => c.id !== target.id);
			confirmDeleteCat = null;
			showToast(`Deleted category "${target.name}".`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not delete category';
		} finally {
			deletingCat = false;
		}
	}

	function applyRulePreset(pattern: string, cleanName: string, hints: string[]) {
		matchPattern = pattern;
		matchType = 'contains';
		merchantOverride = cleanName;
		const found = categories.find((c) =>
			hints.some((h) => c.name.toLowerCase().includes(h.toLowerCase()))
		);
		if (found) categoryId = found.id;
	}

	async function addRule(e: SubmitEvent) {
		e.preventDefault();
		if (!matchPattern.trim() || !categoryId) return;
		creatingRule = true;
		error = null;
		try {
			await api.createRule({
				match_pattern: matchPattern.trim(),
				match_type: matchType,
				category_id: categoryId,
				merchant_override: merchantOverride.trim() || undefined,
				priority: Number(rulePriority)
			});
			const savedPat = matchPattern.trim();
			matchPattern = '';
			merchantOverride = '';
			rules = await api.listRules();
			showToast(`Added Tier-1 rule for "${savedPat}".`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not add rule';
		} finally {
			creatingRule = false;
		}
	}

	async function removeRule(r: CategorizationRule) {
		error = null;
		try {
			await api.deleteRule(r.id);
			rules = rules.filter((item) => item.id !== r.id);
			showToast(`Removed rule "${r.match_pattern}".`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to remove rule';
		}
	}

	async function refreshSystemStatus() {
		refreshingSystem = true;
		try {
			statusInfo = await api.systemStatus();
			showToast('Infrastructure health refreshed.');
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to check system status';
		} finally {
			refreshingSystem = false;
		}
	}

	function triggerDownload(blob: Blob, filename: string) {
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		a.click();
		URL.revokeObjectURL(url);
	}

	async function handleExportCsv() {
		exportingCsv = true;
		error = null;
		try {
			const blob = await api.downloadTransactionsCsv();
			triggerDownload(blob, `financinio_transactions_${new Date().toISOString().slice(0, 10)}.csv`);
			showToast('Transactions CSV downloaded.');
			auditLogs = await api.listAuditLogs();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'CSV export failed';
		} finally {
			exportingCsv = false;
		}
	}

	async function handleExportJson() {
		exportingJson = true;
		error = null;
		try {
			const data = await api.exportFullBackupJson();
			const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
			triggerDownload(blob, `financinio_backup_${new Date().toISOString().slice(0, 10)}.json`);
			showToast('Full workspace JSON backup downloaded.');
			auditLogs = await api.listAuditLogs();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'JSON backup failed';
		} finally {
			exportingJson = false;
		}
	}

	async function handleDeleteAccount(e: SubmitEvent) {
		e.preventDefault();
		if (!canDeleteAccount) return;
		deletingAccount = true;
		error = null;
		try {
			await api.deleteMyAccount(deletePassword, deletePhrase);
			clearTokens();
			auth.user = null;
			goto('/login');
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Account deletion failed';
		} finally {
			deletingAccount = false;
		}
	}

	const NAV_ITEMS: Array<{
		id: SettingsTab;
		label: string;
		desc: string;
	}> = [
		{ id: 'profile', label: 'Profile & Workspace', desc: 'Currency, cycle & privacy' },
		{ id: 'categories', label: 'Categories Studio', desc: 'Custom colors & types' },
		{ id: 'rules', label: 'AI Rules & Tester', desc: 'Zero-token Tier-1 rules' },
		{ id: 'security', label: 'Data & Security', desc: 'Exports, audit log & danger' },
		{ id: 'system', label: 'AI & System Health', desc: 'DB, Vector, LLM & tracing' }
	];
</script>

{#if loading}
	<FinancinioLoader
		fullscreen={false}
		label="Loading Settings Control Center"
		subtitles={[
			'Loading workspace preferences & categories...',
			'Checking AI stack & security audit logs...'
		]}
	/>
{:else}
	<div class="space-y-6 pb-12">
		<!-- Header -->
		<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
			<div>
				<h1 class="text-2xl font-bold tracking-tight text-white">Settings & Control Center</h1>
				<p class="text-sm text-slate-400 mt-0.5">
					Configure your workspace, manage custom categories, automate Tier-1 AI rules, and export your data.
				</p>
			</div>

			<button
				type="button"
				onclick={togglePrivacy}
				class="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl border text-xs font-semibold transition cursor-pointer w-fit {privacyMode
					? 'bg-amber-500/15 border-amber-500/35 text-amber-300'
					: 'bg-slate-900/90 border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white'}"
			>
				{#if privacyMode}
					<EyeOff class="w-3.5 h-3.5" />
					Privacy Mode: ON
				{:else}
					<Eye class="w-3.5 h-3.5" />
					Privacy Mode: OFF
				{/if}
			</button>
		</div>

		<!-- Feedback Alerts -->
		{#if error}
			<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-200 text-sm flex items-start justify-between gap-3">
				<div class="flex items-start gap-2.5">
					<AlertTriangle class="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
					<span>{error}</span>
				</div>
				<button type="button" onclick={() => (error = null)} class="text-rose-300 hover:text-white cursor-pointer">
					<X class="w-4 h-4" />
				</button>
			</div>
		{/if}
		{#if toast}
			<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-sm flex items-start justify-between gap-3">
				<div class="flex items-start gap-2.5">
					<CheckCircle2 class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
					<span>{toast}</span>
				</div>
				<button type="button" onclick={() => (toast = null)} class="text-emerald-300 hover:text-white cursor-pointer">
					<X class="w-4 h-4" />
				</button>
			</div>
		{/if}

		<!-- Mobile Horizontal Pill Nav -->
		<div class="lg:hidden flex items-center gap-1.5 overflow-x-auto pb-1">
			{#each NAV_ITEMS as item}
				<button
					type="button"
					onclick={() => (activeTab = item.id)}
					class="shrink-0 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer {activeTab === item.id
						? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
						: 'bg-slate-900/70 border-slate-800 text-slate-400 hover:text-white'}"
				>
					{#if item.id === 'profile'}
						<UserIcon class="w-3.5 h-3.5" />
					{:else if item.id === 'categories'}
						<Tag class="w-3.5 h-3.5" />
					{:else if item.id === 'rules'}
						<Wand2 class="w-3.5 h-3.5" />
					{:else if item.id === 'security'}
						<Shield class="w-3.5 h-3.5" />
					{:else}
						<Cpu class="w-3.5 h-3.5" />
					{/if}
					{item.label}
				</button>
			{/each}
		</div>

		<!-- Split Settings Layout -->
		<div class="grid lg:grid-cols-12 gap-6 items-start">
			<!-- Desktop Left Settings Rail -->
			<aside class="hidden lg:block lg:col-span-3 card-surface rounded-2xl p-2.5 space-y-1 sticky top-6">
				{#each NAV_ITEMS as item}
					{@const active = activeTab === item.id}
					<button
						type="button"
						onclick={() => (activeTab = item.id)}
						class="w-full text-left px-3.5 py-3 rounded-xl flex items-center justify-between gap-3 transition cursor-pointer border {active
							? 'bg-emerald-500/12 border-emerald-500/35 text-white'
							: 'bg-transparent border-transparent text-slate-400 hover:bg-slate-900/70 hover:text-slate-200'}"
					>
						<div class="flex items-center gap-3 min-w-0">
							<div
								class="h-8 w-8 rounded-lg flex items-center justify-center shrink-0 {active
									? 'bg-emerald-500/20 text-emerald-300'
									: 'bg-slate-900 text-slate-400'}"
							>
								{#if item.id === 'profile'}
									<UserIcon class="w-4 h-4" />
								{:else if item.id === 'categories'}
									<Tag class="w-4 h-4" />
								{:else if item.id === 'rules'}
									<Wand2 class="w-4 h-4" />
								{:else if item.id === 'security'}
									<Shield class="w-4 h-4" />
								{:else}
									<Cpu class="w-4 h-4" />
								{/if}
							</div>
							<div class="min-w-0">
								<div class="text-xs font-semibold truncate">{item.label}</div>
								<div class="text-[10px] text-slate-500 truncate">{item.desc}</div>
							</div>
						</div>
						{#if item.id === 'categories'}
							<span class="text-[10px] font-mono-num px-1.5 py-0.5 rounded bg-slate-900 text-slate-400">
								{categories.length}
							</span>
						{:else if item.id === 'rules'}
							<span class="text-[10px] font-mono-num px-1.5 py-0.5 rounded bg-slate-900 text-slate-400">
								{rules.length}
							</span>
						{:else if active}
							<ChevronRight class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
						{/if}
					</button>
				{/each}
			</aside>

			<!-- Right Active Settings Panel -->
			<div class="lg:col-span-9 space-y-6">
				<!-- ==================== TAB 1: PROFILE & WORKSPACE ==================== -->
				{#if activeTab === 'profile'}
					<!-- Identity & AI Quota Hero -->
					<div class="card-surface rounded-2xl p-6 bg-gradient-to-br from-emerald-950/25 via-slate-950/80 to-cyan-950/20 border-emerald-500/20">
						<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-5">
							<div class="flex items-center gap-4 min-w-0">
								<div class="h-14 w-14 rounded-2xl bg-gradient-to-br from-emerald-400 to-cyan-500 text-slate-950 font-bold text-lg flex items-center justify-center shrink-0 shadow-lg shadow-emerald-500/20">
									{initials}
								</div>
								<div class="min-w-0">
									<div class="flex items-center gap-2 flex-wrap">
										<h2 class="text-lg font-bold text-white truncate">
											{auth.user?.full_name || 'Financinio Member'}
										</h2>
										<span
											class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border {auth.user?.role === 'admin'
												? 'bg-violet-500/15 border-violet-500/35 text-violet-300'
												: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'}"
										>
											{auth.user?.role || 'user'}
										</span>
									</div>
									<p class="text-xs text-slate-400 truncate mt-0.5">{auth.user?.email}</p>
									{#if auth.user?.created_at}
										<p class="text-[11px] text-slate-500 mt-1">
											Member since {formatDate(auth.user.created_at)}
										</p>
									{/if}
								</div>
							</div>

							<!-- AI Token Quota Pill / Meter -->
							{#if auth.user}
								<div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800/90 min-w-[220px] space-y-1.5">
									<div class="flex items-center justify-between gap-2 text-[11px]">
										<span class="inline-flex items-center gap-1.5 text-slate-300 font-medium">
											<Sparkles class="w-3.5 h-3.5 text-cyan-400" />
											AI Token Quota
										</span>
										{#if auth.user.has_unlimited_ai}
											<span class="text-emerald-400 font-semibold">Unlimited</span>
										{:else}
											<span class="font-mono-num text-slate-300">{aiQuotaPct}%</span>
										{/if}
									</div>
									{#if auth.user.has_unlimited_ai}
										<div class="text-[11px] text-slate-400 font-mono-num">
											{auth.user.ai_tokens_used.toLocaleString()} tokens used · Uncapped
										</div>
									{:else}
										<div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
											<div
												class="h-full rounded-full transition-all {aiQuotaPct >= 90
													? 'bg-rose-500'
													: aiQuotaPct >= 70
														? 'bg-amber-400'
														: 'bg-emerald-400'}"
												style="width: {aiQuotaPct}%"
											></div>
										</div>
										<div class="text-[10px] text-slate-400 font-mono-num">
											{auth.user.ai_tokens_used.toLocaleString()} / {auth.user.ai_token_limit.toLocaleString()} tokens
										</div>
									{/if}
								</div>
							{/if}
						</div>
					</div>

					<!-- Workspace Preferences Form -->
					<form onsubmit={saveProfile} class="card-surface rounded-2xl p-6 space-y-6">
						<div class="flex items-center justify-between gap-3">
							<div>
								<h3 class="text-base font-semibold text-white">Workspace Preferences</h3>
								<p class="text-xs text-slate-400 mt-0.5">
									Controls your reporting currency and monthly budget reset date across all dashboards.
								</p>
							</div>
							{#if profileDirty}
								<span class="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-500/15 border border-amber-500/30 text-amber-300 shrink-0">
									Unsaved changes
								</span>
							{/if}
						</div>

						<div class="grid md:grid-cols-2 gap-5">
							<div>
								<label for="prof-name" class="block text-xs font-medium text-slate-300 mb-1.5">
									Full Name
								</label>
								<input
									id="prof-name"
									type="text"
									required
									bind:value={fullName}
									class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>

							<div>
								<label for="prof-day" class="block text-xs font-medium text-slate-300 mb-1.5">
									Budget Cycle Start Day (1–28)
								</label>
								<input
									id="prof-day"
									type="number"
									min={1}
									max={28}
									bind:value={fiscalStartDay}
									class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num focus:outline-none focus:border-emerald-500"
								/>
								<p class="text-[11px] text-slate-500 mt-1">
									Your monthly budgets and cash-flow pacing align to day {fiscalStartDay} of each month.
								</p>
							</div>
						</div>

						<div>
							<label for="prof-ccy" class="block text-xs font-medium text-slate-300 mb-1.5">
								Base Reporting Currency
							</label>
							<div class="flex flex-wrap items-center gap-2">
								{#each QUICK_CURRENCIES as cur}
									<button
										type="button"
										onclick={() => (baseCurrency = cur.code)}
										class="px-3.5 py-2 rounded-xl border text-xs font-semibold transition cursor-pointer {baseCurrency.toUpperCase() === cur.code
											? 'bg-emerald-500/15 border-emerald-500/45 text-emerald-300'
											: 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'}"
									>
										{cur.label}
									</button>
								{/each}
								<input
									id="prof-ccy"
									type="text"
									maxlength={3}
									required
									bind:value={baseCurrency}
									placeholder="ISO"
									class="w-24 px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-white uppercase focus:outline-none focus:border-emerald-500"
								/>
							</div>
						</div>

						<!-- Synced Privacy Toggle Card -->
						<div class="p-4 rounded-xl bg-slate-950/75 border border-slate-800/90 flex items-center justify-between gap-4">
							<div>
								<div class="text-xs font-semibold text-white flex items-center gap-2">
									{#if privacyMode}
										<EyeOff class="w-4 h-4 text-amber-400" />
									{:else}
										<Eye class="w-4 h-4 text-emerald-400" />
									{/if}
									Global Privacy Mode (Blur Amounts)
								</div>
								<p class="text-[11px] text-slate-400 mt-0.5">
									Blurs balances and transaction figures across Dashboard, Accounts, Transactions, Budgets, Recurring, Wealth, and Imports.
								</p>
							</div>
							<button
								type="button"
								onclick={togglePrivacy}
								aria-label="Toggle Privacy Mode"
								class="relative inline-flex h-6 w-11 shrink-0 rounded-full border transition cursor-pointer {privacyMode
									? 'bg-amber-500 border-amber-400'
									: 'bg-slate-800 border-slate-700'}"
							>
								<span
									class="inline-block h-5 w-5 rounded-full bg-white shadow transform transition {privacyMode
										? 'translate-x-5'
										: 'translate-x-0'}"
								></span>
							</button>
						</div>

						<div class="flex justify-end pt-1">
							<button
								type="submit"
								disabled={savingProfile || !profileDirty}
								class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer disabled:opacity-45"
							>
								<Check class="w-4 h-4" />
								{savingProfile ? 'Saving...' : 'Save Workspace Preferences'}
							</button>
						</div>
					</form>

				<!-- ==================== TAB 2: CATEGORIES STUDIO ==================== -->
				{:else if activeTab === 'categories'}
					<!-- Add Category Form -->
					<form onsubmit={handleCreateCategory} class="card-surface rounded-2xl p-6 space-y-4">
						<div>
							<h2 class="text-base font-semibold text-white">Create Custom Category</h2>
							<p class="text-xs text-slate-400 mt-0.5">
								Custom categories automatically appear in Budgets, Transactions, AI Imports, and Luna's advice.
							</p>
						</div>

						<div class="grid sm:grid-cols-12 gap-3 items-end">
							<div class="sm:col-span-5">
								<label for="cat-name" class="block text-[11px] text-slate-400 mb-1">Category Name</label>
								<input
									id="cat-name"
									type="text"
									required
									bind:value={newCatName}
									placeholder="e.g., Coffee & Cafes, Pet Care, Freelance"
									class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>
							<div class="sm:col-span-3">
								<label for="cat-kind" class="block text-[11px] text-slate-400 mb-1">Type</label>
								<select
									id="cat-kind"
									bind:value={newCatKind}
									class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								>
									<option value="expense">Expense</option>
									<option value="income">Income</option>
									<option value="transfer">Transfer</option>
								</select>
							</div>
							<div class="sm:col-span-4 flex items-center justify-between gap-2">
								<button
									type="submit"
									disabled={creatingCat || !newCatName.trim()}
									class="w-full py-2 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs inline-flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
								>
									<Plus class="w-3.5 h-3.5" />
									{creatingCat ? 'Creating...' : 'Add Category'}
								</button>
							</div>
						</div>

						<!-- Color Swatches -->
						<div class="flex items-center flex-wrap gap-2 pt-1">
							<span class="text-[11px] text-slate-400 mr-1">Badge Color:</span>
							{#each COLOR_SWATCHES as hex}
								<button
									type="button"
									aria-label="Choose color {hex}"
									onclick={() => (newCatColor = hex)}
									class="h-6 w-6 rounded-full transition cursor-pointer {newCatColor === hex
										? 'ring-2 ring-white ring-offset-2 ring-offset-slate-950 scale-110'
										: 'opacity-75 hover:opacity-100'}"
									style="background-color: {hex}"
								></button>
							{/each}
						</div>
					</form>

					<!-- Category List & Inline Editor -->
					<div class="card-surface rounded-2xl p-6 space-y-4">
						<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
							<div class="flex items-center gap-1.5 flex-wrap">
								{#each [
									{ id: 'all', label: 'All' },
									{ id: 'expense', label: 'Expense' },
									{ id: 'income', label: 'Income' },
									{ id: 'transfer', label: 'Transfer' }
								] as f}
									<button
										type="button"
										onclick={() => (catFilter = f.id as 'all' | CategoryKind)}
										class="px-3 py-1.5 rounded-lg text-xs font-medium border transition cursor-pointer {catFilter === f.id
											? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
											: 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'}"
									>
										{f.label}
									</button>
								{/each}
							</div>

							<div class="relative w-full sm:w-56">
								<Search class="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
								<input
									type="text"
									bind:value={catSearch}
									placeholder="Filter categories..."
									class="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>
						</div>

						<div class="grid sm:grid-cols-2 gap-2.5">
							{#each filteredCategories as cat}
								{#if editingCatId === cat.id}
									<div class="p-3.5 rounded-xl bg-slate-900 border border-emerald-500/40 space-y-2.5">
										<input
											type="text"
											bind:value={editCatName}
											class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
										/>
										<div class="flex items-center justify-between gap-2">
											<div class="flex items-center gap-1.5 flex-wrap">
												{#each COLOR_SWATCHES.slice(0, 7) as hex}
													<button
														type="button"
														aria-label="Select color {hex}"
														onclick={() => (editCatColor = hex)}
														class="h-4 w-4 rounded-full cursor-pointer {editCatColor === hex
															? 'ring-2 ring-white ring-offset-1 ring-offset-slate-900'
															: 'opacity-70'}"
														style="background-color: {hex}"
													></button>
												{/each}
											</div>
											<div class="flex items-center gap-1.5">
												<button
													type="button"
													onclick={() => (editingCatId = null)}
													class="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white cursor-pointer"
												>
													<X class="w-3.5 h-3.5" />
												</button>
												<button
													type="button"
													disabled={savingCat}
													onclick={() => saveEditCategory(cat.id)}
													class="p-1.5 rounded-lg bg-emerald-500 text-slate-950 hover:bg-emerald-400 cursor-pointer disabled:opacity-50"
												>
													<Check class="w-3.5 h-3.5" />
												</button>
											</div>
										</div>
									</div>
								{:else}
									<div class="p-3.5 rounded-xl bg-slate-950/75 border border-slate-800/80 hover:border-slate-700 transition flex items-center justify-between gap-3">
										<div class="flex items-center gap-3 min-w-0">
											<span
												class="h-3.5 w-3.5 rounded-full shrink-0 ring-2 ring-slate-900"
												style="background-color: {cat.color || '#10b981'}"
											></span>
											<div class="min-w-0">
												<div class="text-xs font-semibold text-white truncate">{cat.name}</div>
												<div class="flex items-center gap-1.5 mt-0.5 text-[10px]">
													<span class="uppercase text-slate-400">{cat.kind}</span>
													{#if cat.is_system}
														<span class="px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">System</span>
													{:else}
														<span class="px-1.5 py-0.2 rounded bg-cyan-500/15 text-cyan-300">Custom</span>
													{/if}
												</div>
											</div>
										</div>
										<div class="flex items-center gap-1 shrink-0">
											<button
												type="button"
												onclick={() => startEditCategory(cat)}
												title="Rename or recolor"
												class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
											>
												<Pencil class="w-3.5 h-3.5" />
											</button>
											{#if !cat.is_system}
												<button
													type="button"
													onclick={() => (confirmDeleteCat = cat)}
													title="Delete custom category"
													class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
												>
													<Trash2 class="w-3.5 h-3.5" />
												</button>
											{/if}
										</div>
									</div>
								{/if}
							{/each}
						</div>
					</div>

				<!-- ==================== TAB 3: AI RULES & TESTER ==================== -->
				{:else if activeTab === 'rules'}
					<!-- 3-Tier Explanation Strip -->
					<div class="grid sm:grid-cols-3 gap-3">
						<div class="p-4 rounded-2xl bg-emerald-500/8 border border-emerald-500/30">
							<div class="text-[10px] font-bold uppercase tracking-wider text-emerald-300">Tier 1 · Instant</div>
							<div class="text-sm font-semibold text-white mt-0.5">Your Rules (0 Tokens)</div>
							<p class="text-[11px] text-slate-400 mt-1">Runs first with 99% confidence before any vector search or LLM call.</p>
						</div>
						<div class="p-4 rounded-2xl bg-cyan-500/8 border border-cyan-500/25">
							<div class="text-[10px] font-bold uppercase tracking-wider text-cyan-300">Tier 2 · Learned</div>
							<div class="text-sm font-semibold text-white mt-0.5">Upstash Vector Memory</div>
							<p class="text-[11px] text-slate-400 mt-1">Automatically remembers every category you confirm during imports.</p>
						</div>
						<div class="p-4 rounded-2xl bg-violet-500/8 border border-violet-500/25">
							<div class="text-[10px] font-bold uppercase tracking-wider text-violet-300">Tier 3 · Fallback</div>
							<div class="text-sm font-semibold text-white mt-0.5">BOG MCC & AI Classifier</div>
							<p class="text-[11px] text-slate-400 mt-1">Handles brand-new merchants using ISO codes and AI reasoning.</p>
						</div>
					</div>

					<!-- Rule Builder -->
					<div class="card-surface rounded-2xl p-6 space-y-4">
						<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
							<div>
								<h2 class="text-base font-semibold text-white">Add Tier-1 Categorization Rule</h2>
								<p class="text-xs text-slate-400 mt-0.5">Match bank narratives by substring, exact text, or regex.</p>
							</div>
							<div class="flex flex-wrap items-center gap-1.5">
								<span class="text-[10px] text-slate-500">Quick Presets:</span>
								{#each [
									{ pat: 'WOLT', clean: 'Wolt', hints: ['dining', 'food', 'restaurant'] },
									{ pat: 'CARREFOUR', clean: 'Carrefour', hints: ['grocer', 'food'] },
									{ pat: 'BOLT', clean: 'Bolt', hints: ['transport', 'taxi'] },
									{ pat: 'MAGTI', clean: 'MagtiCom', hints: ['utilit', 'telecom', 'internet'] }
								] as preset}
									<button
										type="button"
										onclick={() => applyRulePreset(preset.pat, preset.clean, preset.hints)}
										class="px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[10px] font-medium text-slate-300 cursor-pointer"
									>
										+ {preset.clean}
									</button>
								{/each}
							</div>
						</div>

						<form onsubmit={addRule} class="grid sm:grid-cols-12 gap-3 items-end">
							<div class="sm:col-span-2">
								<label for="rule-type" class="block text-[11px] text-slate-400 mb-1">Match Type</label>
								<select
									id="rule-type"
									bind:value={matchType}
									class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								>
									<option value="contains">Contains</option>
									<option value="exact">Exact</option>
									<option value="regex">Regex</option>
								</select>
							</div>
							<div class="sm:col-span-3">
								<label for="rule-pat" class="block text-[11px] text-slate-400 mb-1">Match Pattern</label>
								<input
									id="rule-pat"
									type="text"
									required
									bind:value={matchPattern}
									placeholder="e.g., CARREFOUR"
									class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>
							<div class="sm:col-span-3">
								<label for="rule-cat" class="block text-[11px] text-slate-400 mb-1">Category</label>
								<select
									id="rule-cat"
									bind:value={categoryId}
									class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								>
									{#each categories as cat}
										<option value={cat.id}>{cat.name}</option>
									{/each}
								</select>
							</div>
							<div class="sm:col-span-2">
								<label for="rule-clean" class="block text-[11px] text-slate-400 mb-1">Clean Name</label>
								<input
									id="rule-clean"
									type="text"
									bind:value={merchantOverride}
									placeholder="Optional"
									class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>
							<div class="sm:col-span-2">
								<button
									type="submit"
									disabled={creatingRule || !matchPattern.trim()}
									class="w-full py-2 px-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs inline-flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
								>
									<Plus class="w-3.5 h-3.5" /> Add Rule
								</button>
							</div>
						</form>

						<!-- Live Rule Tester -->
						<div class="p-4 rounded-xl bg-slate-950/80 border border-slate-800/90 space-y-2.5">
							<div class="flex items-center gap-2 text-xs font-semibold text-cyan-300">
								<FlaskConical class="w-3.5 h-3.5" />
								Live Rule Sandbox Tester
							</div>
							<input
								type="text"
								bind:value={testMerchantInput}
								placeholder='Paste a bank string to test (e.g. "POS CARREFOUR TBILISI 0921")...'
								class="w-full px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-cyan-500"
							/>
							{#if liveRuleTestResult}
								<div class="text-xs flex flex-wrap items-center gap-2">
									{#if liveRuleTestResult.draftMatches}
										<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-cyan-500/15 border border-cyan-500/35 text-cyan-200">
											<CheckCircle2 class="w-3.5 h-3.5" />
											Draft rule "{matchPattern}" matches! → {catMap.get(categoryId)?.name ?? 'Selected Category'}
										</span>
									{/if}
									{#if liveRuleTestResult.matchedSaved}
										<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/15 border border-emerald-500/35 text-emerald-200">
											<CheckCircle2 class="w-3.5 h-3.5" />
											Active rule "{liveRuleTestResult.matchedSaved.match_pattern}" matches → {catMap.get(liveRuleTestResult.matchedSaved.category_id)?.name ?? 'Category'}
										</span>
									{:else if !liveRuleTestResult.draftMatches}
										<span class="text-slate-400">
											No Tier-1 rule matched — this merchant will fall through to Upstash Vector Memory / AI.
										</span>
									{/if}
								</div>
							{/if}
						</div>
					</div>

					<!-- Saved Rules List -->
					<div class="card-surface rounded-2xl p-6 space-y-4">
						<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
							<h3 class="text-sm font-semibold text-white">Active Rules ({rules.length})</h3>
							{#if rules.length > 0}
								<div class="relative w-full sm:w-56">
									<Search class="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
									<input
										type="text"
										bind:value={ruleSearch}
										placeholder="Search rules..."
										class="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
									/>
								</div>
							{/if}
						</div>

						{#if filteredRules.length === 0}
							<p class="text-xs text-slate-500 py-4 text-center">
								{rules.length === 0
									? 'No custom rules yet. Use a preset above or create your first deterministic rule.'
									: 'No rules match your search.'}
							</p>
						{:else}
							<div class="divide-y divide-slate-800/70">
								{#each filteredRules as r}
									{@const cat = catMap.get(r.category_id)}
									<div class="py-3 flex items-center justify-between gap-4 text-xs">
										<div class="flex items-center gap-2.5 flex-wrap">
											<span class="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-slate-300 font-mono-num uppercase text-[10px]">
												{r.match_type}
											</span>
											<span class="font-semibold text-white">"{r.match_pattern}"</span>
											<span class="text-slate-500">→</span>
											<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-emerald-300 font-medium">
												<span
													class="h-2 w-2 rounded-full"
													style="background-color: {cat?.color || '#10b981'}"
												></span>
												{cat?.name ?? 'Category'}
											</span>
											{#if r.merchant_override}
												<span class="text-slate-400">rename → <strong class="text-slate-200">{r.merchant_override}</strong></span>
											{/if}
										</div>
										<button
											type="button"
											onclick={() => removeRule(r)}
											title="Delete rule"
											class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer shrink-0"
										>
											<Trash2 class="w-3.5 h-3.5" />
										</button>
									</div>
								{/each}
							</div>
						{/if}
					</div>

				<!-- ==================== TAB 4: DATA & SECURITY ==================== -->
				{:else if activeTab === 'security'}
					<!-- Data Portability -->
					<div class="card-surface rounded-2xl p-6 space-y-4">
						<div>
							<h2 class="text-base font-semibold text-white">Data Portability & Backups</h2>
							<p class="text-xs text-slate-400 mt-0.5">
								Your data belongs to you. Export your full ledger or download a complete JSON archive anytime.
							</p>
						</div>
						<div class="grid sm:grid-cols-2 gap-3.5">
							<button
								type="button"
								disabled={exportingCsv}
								onclick={handleExportCsv}
								class="text-left p-4 rounded-2xl bg-slate-950/75 hover:bg-slate-900 border border-slate-800 hover:border-emerald-500/40 transition cursor-pointer flex items-start justify-between gap-3 disabled:opacity-50"
							>
								<div class="flex items-start gap-3">
									<div class="h-10 w-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center shrink-0">
										<FileSpreadsheet class="w-5 h-5" />
									</div>
									<div>
										<div class="text-sm font-semibold text-white">Transactions Ledger (CSV)</div>
										<p class="text-[11px] text-slate-400 mt-0.5">Spreadsheet-ready export for Excel, Numbers, or Sheets.</p>
									</div>
								</div>
								<Download class="w-4 h-4 text-emerald-400 shrink-0 mt-1 {exportingCsv ? 'animate-bounce' : ''}" />
							</button>

							<button
								type="button"
								disabled={exportingJson}
								onclick={handleExportJson}
								class="text-left p-4 rounded-2xl bg-slate-950/75 hover:bg-slate-900 border border-slate-800 hover:border-cyan-500/40 transition cursor-pointer flex items-start justify-between gap-3 disabled:opacity-50"
							>
								<div class="flex items-start gap-3">
									<div class="h-10 w-10 rounded-xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 flex items-center justify-center shrink-0">
										<FileJson class="w-5 h-5" />
									</div>
									<div>
										<div class="text-sm font-semibold text-white">Full Workspace Backup (JSON)</div>
										<p class="text-[11px] text-slate-400 mt-0.5">Complete archive of accounts, transactions, budgets, goals & rules.</p>
									</div>
								</div>
								<Download class="w-4 h-4 text-cyan-400 shrink-0 mt-1 {exportingJson ? 'animate-bounce' : ''}" />
							</button>
						</div>
					</div>

					<!-- Security Audit Log -->
					<div class="card-surface rounded-2xl p-6 space-y-4">
						<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
							<div class="flex items-center gap-2">
								<History class="w-4 h-4 text-emerald-400" />
								<h2 class="text-base font-semibold text-white">Security & Data Audit Log</h2>
							</div>
							{#if auditLogs.length > 0}
								<div class="relative w-full sm:w-56">
									<Search class="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
									<input
										type="text"
										bind:value={auditSearch}
										placeholder="Filter activity..."
										class="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
									/>
								</div>
							{/if}
						</div>

						{#if auditLogs.length === 0}
							<p class="text-xs text-slate-500 py-4 text-center">
								No sensitive activity logged yet. Exports and security actions appear here automatically.
							</p>
						{:else}
							<div class="divide-y divide-slate-800/70 text-xs">
								{#each filteredAuditLogs as log}
									<div class="py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
										<div class="flex items-center gap-2.5 flex-wrap">
											<span class="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 font-mono-num text-[11px]">
												{log.action}
											</span>
											<span class="text-slate-200 font-medium">{log.resource_type}</span>
											{#if log.ip_address}
												<span class="text-[11px] font-mono-num text-slate-500">IP {log.ip_address}</span>
											{/if}
										</div>
										<span class="text-slate-500 font-mono-num text-[11px]">{formatDate(log.created_at)}</span>
									</div>
								{/each}
							</div>
							{#if auditLogs.length > 10}
								<button
									type="button"
									onclick={() => (showAllAudit = !showAllAudit)}
									class="text-xs font-medium text-cyan-300 hover:text-cyan-200 cursor-pointer"
								>
									{showAllAudit ? 'Show less' : `Show all ${auditLogs.length} events`}
								</button>
							{/if}
						{/if}
					</div>

					<!-- Expandable Danger Zone -->
					<div class="rounded-2xl bg-rose-950/20 border border-rose-500/30 overflow-hidden">
						<button
							type="button"
							onclick={() => (dangerZoneOpen = !dangerZoneOpen)}
							class="w-full p-5 flex items-center justify-between gap-4 text-left cursor-pointer hover:bg-rose-500/[0.04] transition"
						>
							<div class="flex items-center gap-3">
								<div class="h-9 w-9 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-400 flex items-center justify-center shrink-0">
									<ShieldAlert class="w-5 h-5" />
								</div>
								<div>
									<h2 class="text-sm font-semibold text-rose-200">Danger Zone — Permanent Account Deletion</h2>
									<p class="text-xs text-slate-400 mt-0.5">
										Irreversibly delete your Neon records and purge all Upstash Vector memory namespaces.
									</p>
								</div>
							</div>
							<span class="text-xs font-semibold text-rose-300 shrink-0">
								{dangerZoneOpen ? 'Close' : 'Manage'}
							</span>
						</button>

						{#if dangerZoneOpen}
							<form onsubmit={handleDeleteAccount} class="px-5 pb-5 pt-2 border-t border-rose-500/20 space-y-4">
								<p class="text-xs text-slate-300 leading-relaxed">
									This cascades deletion across all accounts, transactions, budgets, recurring bills, goals, chats, uploaded files, and AI vector memory. We recommend downloading a JSON backup first.
								</p>
								<div class="grid sm:grid-cols-2 gap-3">
									<div>
										<label for="del-pw" class="block text-[11px] text-rose-200/80 mb-1">Confirm Password</label>
										<input
											id="del-pw"
											type="password"
											required
											bind:value={deletePassword}
											placeholder="Enter your password"
											class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-rose-500/30 text-xs text-white focus:outline-none focus:border-rose-400"
										/>
									</div>
									<div>
										<label for="del-phrase" class="block text-[11px] text-rose-200/80 mb-1">
											Type <span class="font-mono font-bold text-rose-200">DELETE MY ACCOUNT</span>
										</label>
										<input
											id="del-phrase"
											type="text"
											required
											bind:value={deletePhrase}
											placeholder="DELETE MY ACCOUNT"
											class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-rose-500/30 text-xs text-white font-mono focus:outline-none focus:border-rose-400"
										/>
									</div>
								</div>

								<div class="flex flex-wrap items-center justify-between gap-3">
									<div class="flex items-center gap-3 text-[11px]">
										<span class="inline-flex items-center gap-1 {deletePassword.trim() ? 'text-emerald-400' : 'text-slate-500'}">
											<Lock class="w-3 h-3" /> Password entered
										</span>
										<span class="inline-flex items-center gap-1 {deletePhrase.trim() === 'DELETE MY ACCOUNT' ? 'text-emerald-400' : 'text-slate-500'}">
											<CheckCircle2 class="w-3 h-3" /> Phrase matched
										</span>
									</div>
									<button
										type="submit"
										disabled={deletingAccount || !canDeleteAccount}
										class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs cursor-pointer disabled:opacity-40"
									>
										{deletingAccount ? 'Deleting Forever...' : 'Permanently Delete Account'}
									</button>
								</div>
							</form>
						{/if}
					</div>

				<!-- ==================== TAB 5: AI & SYSTEM HEALTH ==================== -->
				{:else if activeTab === 'system'}
					<div class="card-surface rounded-2xl p-6 space-y-5">
						<div class="flex items-center justify-between gap-3">
							<div>
								<h2 class="text-base font-semibold text-white">AI & Cloud Infrastructure Health</h2>
								<p class="text-xs text-slate-400 mt-0.5">
									Live diagnostics for your Neon database, Upstash Vector memory, object storage, and LangGraph runtime.
								</p>
							</div>
							<button
								type="button"
								disabled={refreshingSystem}
								onclick={refreshSystemStatus}
								class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-200 cursor-pointer disabled:opacity-50"
							>
								<RefreshCw class="w-3.5 h-3.5 {refreshingSystem ? 'animate-spin' : ''}" />
								Refresh
							</button>
						</div>

						{#if statusInfo}
							<div class="grid sm:grid-cols-2 gap-3.5 text-xs">
								<div class="p-4 rounded-2xl bg-slate-950/80 border border-slate-800/90 space-y-2">
									<div class="flex items-center justify-between">
										<span class="inline-flex items-center gap-2 text-slate-300 font-medium">
											<Database class="w-4 h-4 text-emerald-400" /> Primary Database
										</span>
										<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-emerald-400">
											<span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span> Online
										</span>
									</div>
									<div class="font-mono-num text-sm font-bold text-white">{statusInfo.database}</div>
									<div class="text-slate-400">Encrypted financial ledger & LangGraph checkpoints.</div>
								</div>

								<div class="p-4 rounded-2xl bg-slate-950/80 border border-slate-800/90 space-y-2">
									<div class="flex items-center justify-between">
										<span class="inline-flex items-center gap-2 text-slate-300 font-medium">
											<Sparkles class="w-4 h-4 text-cyan-400" /> Upstash Vector Memory
										</span>
										<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold {statusInfo.upstash_vector_connected ? 'text-emerald-400' : 'text-amber-400'}">
											<span class="h-2 w-2 rounded-full {statusInfo.upstash_vector_connected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}"></span>
											{statusInfo.upstash_vector_connected ? 'Connected' : 'Fallback'}
										</span>
									</div>
									<div class="font-mono-num text-sm font-bold text-white">
										{statusInfo.upstash_vector_connected ? 'Self-Learning Active' : 'Not Configured'}
									</div>
									<div class="text-slate-400">Powers merchant recall, statement RAG, and Luna episodic memory.</div>
								</div>

								<div class="p-4 rounded-2xl bg-slate-950/80 border border-slate-800/90 space-y-2">
									<div class="flex items-center justify-between">
										<span class="inline-flex items-center gap-2 text-slate-300 font-medium">
											<Cpu class="w-4 h-4 text-violet-400" /> LangChain LLM Engine
										</span>
										<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold {statusInfo.llm_configured ? 'text-emerald-400' : 'text-amber-400'}">
											<span class="h-2 w-2 rounded-full {statusInfo.llm_configured ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}"></span>
											{statusInfo.llm_configured ? 'Configured' : 'Heuristic'}
										</span>
									</div>
									<div class="font-mono-num text-sm font-bold text-white">
										{statusInfo.llm_provider} · {statusInfo.llm_model_fast}
									</div>
									<div class="text-slate-400">Vision model: <span class="font-mono-num text-slate-300">{statusInfo.llm_model_vision}</span></div>
								</div>

								<div class="p-4 rounded-2xl bg-slate-950/80 border border-slate-800/90 space-y-2">
									<div class="flex items-center justify-between">
										<span class="inline-flex items-center gap-2 text-slate-300 font-medium">
											<Activity class="w-4 h-4 text-amber-400" /> LangSmith & Storage
										</span>
										<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold {statusInfo.langsmith_tracing ? 'text-emerald-400' : 'text-slate-400'}">
											<span class="h-2 w-2 rounded-full {statusInfo.langsmith_tracing ? 'bg-emerald-400' : 'bg-slate-600'}"></span>
											{statusInfo.langsmith_tracing ? 'Tracing On' : 'Off'}
										</span>
									</div>
									<div class="font-mono-num text-sm font-bold text-white flex items-center gap-2">
										<HardDrive class="w-3.5 h-3.5 text-slate-400" />
										Storage: {statusInfo.storage_backend}
									</div>
									<div class="text-slate-400">
										Project: <span class="text-slate-300">{statusInfo.langsmith_project}</span> (PII redacted)
									</div>
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<!-- Safe Delete Category Modal -->
{#if confirmDeleteCat}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-4 border border-rose-500/30">
			<div class="flex items-start justify-between gap-3">
				<div class="flex items-center gap-3">
					<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
						<Trash2 class="w-5 h-5" />
					</div>
					<div>
						<h3 class="text-base font-semibold text-white">Delete Category?</h3>
						<p class="text-xs text-slate-400">"{confirmDeleteCat.name}"</p>
					</div>
				</div>
				<button
					type="button"
					disabled={deletingCat}
					onclick={() => (confirmDeleteCat = null)}
					class="p-1 text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>
			<p class="text-xs text-slate-300 leading-relaxed">
				Deleting this custom category will remove it from your workspace. Existing transactions assigned to it will remain safely in your ledger as uncategorized.
			</p>
			<div class="flex items-center justify-end gap-2">
				<button
					type="button"
					disabled={deletingCat}
					onclick={() => (confirmDeleteCat = null)}
					class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
				<button
					type="button"
					disabled={deletingCat}
					onclick={handleConfirmDeleteCategory}
					class="px-4 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					{deletingCat ? 'Deleting...' : 'Delete Category'}
				</button>
			</div>
		</div>
	</div>
{/if}
