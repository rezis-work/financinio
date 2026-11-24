<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type {
		Account,
		Category,
		FinancialHealthProfile,
		RecurringCadence,
		RecurringItem,
		RecurringOverview
	} from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import BillCalendar from '$lib/components/recurring/BillCalendar.svelte';
	import RecurringDetailDrawer from '$lib/components/recurring/RecurringDetailDrawer.svelte';
	import MarkPaidModal from '$lib/components/recurring/MarkPaidModal.svelte';
	import {
		Repeat,
		Radar,
		Plus,
		AlertTriangle,
		Calendar,
		Trash2,
		Sparkles,
		X,
		Eye,
		EyeOff,
		CheckCircle2,
		Search,
		Scissors,
		Pause,
		Play,
		LayoutList,
		Columns2,
		TrendingUp,
		Clock
	} from 'lucide-svelte';

	const PRIVACY_KEY = 'financinio_privacy_mode';

	const CURRENCIES = ['GEL', 'USD', 'EUR', 'GBP'];

	const PRESETS: Array<{
		label: string;
		merchant: string;
		amount: string;
		currency: string;
		cadence: RecurringCadence;
		direction: 'outflow' | 'inflow';
		isSubscription: boolean;
		categoryHint: string;
	}> = [
		{ label: 'Netflix', merchant: 'Netflix', amount: '12.99', currency: 'USD', cadence: 'monthly', direction: 'outflow', isSubscription: true, categoryHint: 'Subscriptions & Software' },
		{ label: 'Spotify', merchant: 'Spotify', amount: '5.99', currency: 'USD', cadence: 'monthly', direction: 'outflow', isSubscription: true, categoryHint: 'Subscriptions & Software' },
		{ label: 'YouTube Premium', merchant: 'YouTube Premium', amount: '7.99', currency: 'USD', cadence: 'monthly', direction: 'outflow', isSubscription: true, categoryHint: 'Subscriptions & Software' },
		{ label: 'iCloud+', merchant: 'Apple iCloud+', amount: '2.99', currency: 'USD', cadence: 'monthly', direction: 'outflow', isSubscription: true, categoryHint: 'Subscriptions & Software' },
		{ label: 'ChatGPT Plus', merchant: 'OpenAI ChatGPT Plus', amount: '20.00', currency: 'USD', cadence: 'monthly', direction: 'outflow', isSubscription: true, categoryHint: 'Subscriptions & Software' },
		{ label: 'Magti / Silknet', merchant: 'Magti Internet & Mobile', amount: '45.00', currency: 'GEL', cadence: 'monthly', direction: 'outflow', isSubscription: false, categoryHint: 'Utilities & Internet' },
		{ label: 'Gym Membership', merchant: 'Gym Membership', amount: '120.00', currency: 'GEL', cadence: 'monthly', direction: 'outflow', isSubscription: true, categoryHint: 'Entertainment & Leisure' },
		{ label: 'Apartment Rent', merchant: 'Apartment Rent', amount: '1200.00', currency: 'GEL', cadence: 'monthly', direction: 'outflow', isSubscription: false, categoryHint: 'Housing & Rent' },
		{ label: 'Monthly Salary', merchant: 'Monthly Salary', amount: '4000.00', currency: 'GEL', cadence: 'monthly', direction: 'inflow', isSubscription: false, categoryHint: 'Salary & Payroll' }
	];

	let overview = $state<RecurringOverview | null>(null);
	let categories = $state<Category[]>([]);
	let accounts = $state<Account[]>([]);
	let health = $state<FinancialHealthProfile | null>(null);

	let loading = $state(true);
	let scanning = $state(false);
	let privacyMode = $state(false);
	let viewMode = $state<'split' | 'list' | 'calendar'>('split');
	let error = $state<string | null>(null);
	let statusMsg = $state<string | null>(null);

	// Filters & Sort
	let filterTab = $state<'all' | 'subscriptions' | 'bills' | 'income' | 'paused'>('all');
	let search = $state('');
	let sortBy = $state<'due' | 'cost' | 'name'>('due');

	// "What If I Cut This?" Simulator
	let cutIds = $state<Set<string>>(new Set());
	let pausingSelected = $state(false);

	// Drawer & Modals
	let inspectedItemId = $state<string | null>(null);
	let inspectedItem = $derived(
		overview?.items.find((i) => i.id === inspectedItemId) ?? null
	);

	let markPaidOpen = $state(false);
	let markPaidItem = $state<RecurringItem | null>(null);

	let deleteTarget = $state<RecurringItem | null>(null);
	let deleting = $state(false);

	// Create Modal
	let showCreateModal = $state(false);
	let merchantName = $state('');
	let amount = $state('');
	let currency = $state(auth.user?.base_currency || 'GEL');
	let cadence = $state<RecurringCadence>('monthly');
	let direction = $state<'outflow' | 'inflow'>('outflow');
	let nextDueDate = $state(new Date().toISOString().slice(0, 10));
	let categoryId = $state('');
	let isSubscription = $state(true);
	let saving = $state(false);

	let baseCcy = $derived(auth.user?.base_currency || 'USD');
	let catMap = $derived(new Map(categories.map((c) => [c.id, c])));

	async function loadData(silent = false) {
		if (!silent) loading = true;
		error = null;
		try {
			const [ov, cats, accs, hlth] = await Promise.all([
				api.getRecurring(),
				api.listCategories(),
				api.listAccounts().catch(() => [] as Account[]),
				api.financialHealthScore().catch(() => null)
			]);
			overview = ov;
			categories = cats;
			accounts = accs;
			health = hlth;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load recurring bills';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if (typeof window !== 'undefined') {
			privacyMode = localStorage.getItem(PRIVACY_KEY) === '1';
		}
		loadData();
	});

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof window !== 'undefined') {
			localStorage.setItem(PRIVACY_KEY, privacyMode ? '1' : '0');
		}
	}

	function daysUntil(iso: string): number {
		const today = new Date();
		today.setHours(0, 0, 0, 0);
		const due = new Date(iso + 'T00:00:00');
		return Math.round((due.getTime() - today.getTime()) / 86_400_000);
	}

	function dueBadge(item: RecurringItem): { label: string; cls: string } {
		if (!item.is_active) {
			return { label: 'Paused', cls: 'bg-slate-800 text-slate-400 border-slate-700' };
		}
		const d = daysUntil(item.next_due_date);
		if (d < 0) {
			return {
				label: `Overdue ${Math.abs(d)}d`,
				cls: 'bg-rose-500/15 text-rose-300 border-rose-500/35'
			};
		}
		if (d === 0) {
			return { label: 'Due Today', cls: 'bg-amber-500/20 text-amber-200 border-amber-500/40' };
		}
		if (d <= 7) {
			return { label: `In ${d}d`, cls: 'bg-amber-500/12 text-amber-300 border-amber-500/30' };
		}
		return { label: `In ${d}d`, cls: 'bg-slate-900 text-slate-400 border-slate-800' };
	}

	function compound5Yr(monthly: number): number {
		const r = 0.07 / 12;
		return monthly * ((Math.pow(1 + r, 60) - 1) / r);
	}

	// Executive Hero Metrics
	let heroStats = $derived.by(() => {
		if (!overview) {
			return {
				monthlyOut: 0,
				annualOut: 0,
				due7dTotal: 0,
				due7dCount: 0,
				due30dTotal: 0,
				netFixed: 0,
				fixedRatioPct: 0,
				activeSubMonthly: 0,
				sub5YrOpp: 0
			};
		}
		const monthlyOut = Number.parseFloat(overview.monthly_recurring_expenses) || 0;
		const annualOut = Number.parseFloat(overview.annual_recurring_expenses) || 0;
		const monthlyIn = Number.parseFloat(overview.monthly_recurring_income) || 0;
		const due30dTotal = Number.parseFloat(overview.upcoming_30d_total) || 0;

		let due7dTotal = 0;
		let due7dCount = 0;
		let activeSubMonthly = 0;

		for (const item of overview.items) {
			if (!item.is_active || item.direction !== 'outflow') continue;
			const d = daysUntil(item.next_due_date);
			if (d <= 7) {
				due7dTotal += Number.parseFloat(item.amount) || 0;
				due7dCount += 1;
			}
			if (item.is_subscription) {
				activeSubMonthly += Number.parseFloat(item.monthly_equivalent) || 0;
			}
		}

		const denomIncome =
			health && Number.parseFloat(health.cash_flow_ratios.avg_monthly_income) > 0
				? Number.parseFloat(health.cash_flow_ratios.avg_monthly_income)
				: monthlyIn;
		const fixedRatioPct = denomIncome > 0 ? Math.round((monthlyOut / denomIncome) * 1000) / 10 : 0;

		return {
			monthlyOut,
			annualOut,
			due7dTotal,
			due7dCount,
			due30dTotal,
			netFixed: monthlyIn - monthlyOut,
			fixedRatioPct,
			activeSubMonthly,
			sub5YrOpp: compound5Yr(activeSubMonthly)
		};
	});

	// "What If I Cut This?" Simulator Stats
	let cutSavings = $derived.by(() => {
		if (!overview || cutIds.size === 0) return { count: 0, monthly: 0, annual: 0, fiveYr: 0 };
		let monthly = 0;
		let count = 0;
		for (const item of overview.items) {
			if (cutIds.has(item.id) && item.direction === 'outflow') {
				monthly += Number.parseFloat(item.monthly_equivalent) || 0;
				count += 1;
			}
		}
		return { count, monthly, annual: monthly * 12, fiveYr: compound5Yr(monthly) };
	});

	function toggleCut(id: string) {
		const next = new Set(cutIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		cutIds = next;
	}

	async function pauseSelectedCuts() {
		if (cutIds.size === 0 || pausingSelected) return;
		pausingSelected = true;
		error = null;
		try {
			const ids = Array.from(cutIds);
			for (const id of ids) {
				await api.updateRecurring(id, { is_active: false });
			}
			cutIds = new Set();
			overview = await api.getRecurring();
			statusMsg = `Paused ${ids.length} recurring ${ids.length === 1 ? 'item' : 'items'} — enjoy the savings!`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not pause selected items';
		} finally {
			pausingSelected = false;
		}
	}

	// Filtered & Sorted Items
	let filteredItems = $derived.by(() => {
		const list = overview?.items ?? [];
		const q = search.trim().toLowerCase();
		const filtered = list.filter((item) => {
			if (filterTab === 'paused') {
				if (item.is_active) return false;
			} else if (filterTab === 'subscriptions') {
				if (!item.is_active || !item.is_subscription || item.direction !== 'outflow') return false;
			} else if (filterTab === 'bills') {
				if (!item.is_active || item.is_subscription || item.direction !== 'outflow') return false;
			} else if (filterTab === 'income') {
				if (!item.is_active || item.direction !== 'inflow') return false;
			}
			if (q) {
				const catName = (item.category_id ? catMap.get(item.category_id)?.name : '') || '';
				if (
					!item.merchant_name.toLowerCase().includes(q) &&
					!catName.toLowerCase().includes(q)
				) {
					return false;
				}
			}
			return true;
		});

		return [...filtered].sort((a, b) => {
			if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
			if (sortBy === 'due') return a.next_due_date.localeCompare(b.next_due_date);
			if (sortBy === 'cost')
				return (
					(Number.parseFloat(b.monthly_equivalent) || 0) -
					(Number.parseFloat(a.monthly_equivalent) || 0)
				);
			return a.merchant_name.localeCompare(b.merchant_name);
		});
	});

	async function handleScan() {
		scanning = true;
		error = null;
		statusMsg = null;
		try {
			const res = await api.detectRecurring();
			overview = res.overview;
			statusMsg = `Scan complete: ${res.detected_new} new recurring items detected, ${res.updated_existing} updated, ${res.price_hikes_found} price hike alerts found.`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Detection scan failed';
		} finally {
			scanning = false;
		}
	}

	function applyPreset(p: (typeof PRESETS)[number]) {
		merchantName = p.merchant;
		amount = p.amount;
		currency = p.currency;
		cadence = p.cadence;
		direction = p.direction;
		isSubscription = p.isSubscription;
		const matchedCat = categories.find(
			(c) => c.name.toLowerCase() === p.categoryHint.toLowerCase()
		);
		categoryId = matchedCat?.id ?? '';
	}

	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = null;
		statusMsg = null;
		try {
			await api.createRecurring({
				merchant_name: merchantName.trim(),
				amount,
				currency: currency.toUpperCase(),
				direction,
				cadence,
				next_due_date: nextDueDate,
				category_id: categoryId || null,
				is_subscription: isSubscription
			});
			showCreateModal = false;
			merchantName = '';
			amount = '';
			overview = await api.getRecurring();
			statusMsg = 'Recurring bill / subscription added.';
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not save recurring item';
		} finally {
			saving = false;
		}
	}

	async function toggleActive(item: RecurringItem) {
		await api.updateRecurring(item.id, { is_active: !item.is_active });
		overview = await api.getRecurring();
	}

	async function confirmDelete() {
		if (!deleteTarget || deleting) return;
		const target = deleteTarget;
		deleting = true;
		error = null;
		try {
			await api.deleteRecurring(target.id);
			if (inspectedItemId === target.id) inspectedItemId = null;
			cutIds.delete(target.id);
			cutIds = new Set(cutIds);
			deleteTarget = null;
			overview = await api.getRecurring();
			statusMsg = `Deleted recurring item "${target.merchant_name}".`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to delete recurring item';
		} finally {
			deleting = false;
		}
	}
</script>

<div class="space-y-6">
	<!-- HEADER -->
	<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">Recurring Bills & Subscriptions</h1>
			<p class="text-xs sm:text-sm text-slate-400 mt-0.5">
				Interactive bill calendar, price-hike radar, 1-click Mark Paid, and subscription cut simulator.
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<button
				type="button"
				onclick={togglePrivacy}
				title={privacyMode ? 'Show amounts' : 'Hide amounts (Privacy Mode)'}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-medium transition cursor-pointer {privacyMode
					? 'bg-cyan-500/15 border-cyan-500/35 text-cyan-300'
					: 'bg-slate-900/90 hover:bg-slate-800 border-slate-800 text-slate-300'}"
			>
				{#if privacyMode}
					<EyeOff class="w-3.5 h-3.5" />
				{:else}
					<Eye class="w-3.5 h-3.5" />
				{/if}
			</button>

			<button
				type="button"
				disabled={scanning}
				onclick={handleScan}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-cyan-200 transition cursor-pointer disabled:opacity-50"
			>
				<Radar class="w-3.5 h-3.5 text-cyan-400 {scanning ? 'animate-spin' : ''}" />
				<span>{scanning ? 'Scanning...' : 'Auto-Detect'}</span>
			</button>

			<button
				type="button"
				onclick={() =>
					goto(
						`/advisor?q=${encodeURIComponent(
							'Audit all my recurring bills and subscriptions — highlight any price hikes, redundancies, or easy cuts to boost my monthly savings.'
						)}`
					)}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-emerald-300 transition cursor-pointer"
			>
				<Sparkles class="w-3.5 h-3.5" />
				<span class="hidden sm:inline">Audit with Luna</span>
			</button>

			<button
				type="button"
				onclick={() => {
					currency = baseCcy;
					showCreateModal = true;
				}}
				class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs transition cursor-pointer shadow-sm"
			>
				<Plus class="w-4 h-4" />
				<span>Add Bill</span>
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-3">
			<span>{error}</span>
			<button type="button" onclick={() => (error = null)} class="text-rose-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}
	{#if statusMsg}
		<div class="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-200 text-xs flex items-center justify-between gap-3">
			<span class="flex items-center gap-2">
				<Sparkles class="w-4 h-4 shrink-0 text-cyan-400" />
				{statusMsg}
			</span>
			<button type="button" onclick={() => (statusMsg = null)} class="text-cyan-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}

	{#if loading}
		<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
			{#each Array(4) as _}
				<div class="card-surface rounded-2xl h-28 animate-pulse"></div>
			{/each}
		</div>
	{:else if overview}
		<!-- 1. PRICE HIKE ALERT BANNER WITH LUNA ACTION -->
		{#if overview.price_hike_alerts.length > 0}
			<div class="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/35 space-y-2.5">
				<div class="flex items-center gap-2 text-amber-300 text-xs font-semibold">
					<AlertTriangle class="w-4 h-4" />
					Subscription Price Creep Detected ({overview.price_hike_alerts.length})
				</div>
				<div class="grid md:grid-cols-2 gap-2.5">
					{#each overview.price_hike_alerts as alert}
						<div class="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl bg-slate-950/75 border border-amber-500/20 text-xs">
							<div class="min-w-0">
								<div class="font-semibold text-white truncate">{alert.merchant_name}</div>
								<div class="font-mono-num text-[11px] text-amber-300 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
									{formatMoney(alert.previous_amount || '0', alert.currency)} → {formatMoney(alert.amount, alert.currency)}
									<span class="font-bold">(+{alert.price_change_pct}%)</span>
								</div>
							</div>
							<button
								type="button"
								onclick={() =>
									goto(
										`/advisor?q=${encodeURIComponent(
											`My "${alert.merchant_name}" subscription jumped by +${alert.price_change_pct}% (from ${alert.previous_amount} to ${alert.amount} ${alert.currency}). Should I negotiate, downgrade, or cancel it?`
										)}`
									)}
								class="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 text-[11px] font-semibold cursor-pointer"
							>
								<Sparkles class="w-3 h-3" /> Cut / Negotiate
							</button>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- EXECUTIVE 4-CARD FIXED-BURN HERO -->
		<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
			<div class="card-surface rounded-2xl p-4 sm:p-5">
				<div class="text-xs text-slate-400">Monthly Fixed Burn</div>
				<div class="text-2xl font-bold font-mono-num text-rose-400 mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
					{formatMoney(heroStats.monthlyOut, baseCcy)}
				</div>
				<div class="text-[11px] text-slate-400 mt-1 font-mono-num {privacyMode ? 'privacy-blur' : ''}">
					Annualized: {formatMoney(heroStats.annualOut, baseCcy)}/yr
				</div>
			</div>

			<div class="card-surface rounded-2xl p-4 sm:p-5">
				<div class="flex items-center justify-between text-xs text-slate-400">
					<span>Due Next 7d / 30d</span>
					<Clock class="w-3.5 h-3.5 text-amber-400" />
				</div>
				<div class="text-2xl font-bold font-mono-num text-white mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
					{formatMoney(heroStats.due30dTotal, baseCcy)}
				</div>
				<div class="text-[11px] text-slate-400 mt-1 font-mono-num">
					<span class="text-amber-300 font-semibold">{heroStats.due7dCount} urgent</span>
					(<span class={privacyMode ? 'privacy-blur' : ''}>{formatMoney(heroStats.due7dTotal, baseCcy)}</span> in 7d)
				</div>
			</div>

			<div class="card-surface rounded-2xl p-4 sm:p-5">
				<div class="flex items-center justify-between text-xs text-slate-400">
					<span>Fixed Bills Ratio</span>
					<span
						class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full {heroStats.fixedRatioPct <= 50
							? 'bg-emerald-500/15 text-emerald-300'
							: 'bg-rose-500/15 text-rose-300'}"
					>
						{heroStats.fixedRatioPct <= 50 ? 'Healthy' : 'High (>50%)'}
					</span>
				</div>
				<div class="text-2xl font-bold font-mono-num text-cyan-300 mt-1.5">
					{heroStats.fixedRatioPct}%
				</div>
				<div class="text-[11px] text-slate-400 mt-1 font-mono-num">
					Net fixed:
					<span class="{heroStats.netFixed >= 0 ? 'text-emerald-400' : 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}">
						{heroStats.netFixed >= 0 ? '+' : ''}{formatMoney(heroStats.netFixed, baseCcy)}
					</span>
				</div>
			</div>

			<div class="card-surface rounded-2xl p-4 sm:p-5 border-amber-500/20">
				<div class="flex items-center justify-between text-xs text-slate-400">
					<span>5-Yr Subscription Cost</span>
					<TrendingUp class="w-3.5 h-3.5 text-amber-400" />
				</div>
				<div class="text-2xl font-bold font-mono-num text-amber-300 mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
					{formatMoney(heroStats.sub5YrOpp, baseCcy)}
				</div>
				<div class="text-[11px] text-slate-400 mt-1 font-mono-num">
					Compounded @ 7% (<span class={privacyMode ? 'privacy-blur' : ''}>{formatMoney(heroStats.activeSubMonthly, baseCcy)}/mo</span>)
				</div>
			</div>
		</div>

		<!-- "WHAT IF I CUT THIS?" SAVINGS SIMULATOR BANNER -->
		{#if cutSavings.count > 0}
			<div class="p-4 rounded-2xl bg-emerald-500/12 border border-emerald-500/35 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
				<div class="flex items-start sm:items-center gap-3">
					<div class="h-9 w-9 rounded-xl bg-emerald-500/20 border border-emerald-500/35 flex items-center justify-center text-emerald-300 shrink-0">
						<Scissors class="w-4 h-4" />
					</div>
					<div class="text-xs space-y-0.5">
						<div class="font-semibold text-emerald-200">
							Cutting {cutSavings.count} selected {cutSavings.count === 1 ? 'item' : 'items'} saves:
						</div>
						<div class="font-mono-num text-slate-200 {privacyMode ? 'privacy-blur' : ''}">
							<strong class="text-emerald-300">+{formatMoney(cutSavings.monthly, baseCcy)}/mo</strong> ·
							<strong>+{formatMoney(cutSavings.annual, baseCcy)}/yr</strong> ·
							<strong class="text-cyan-300">+{formatMoney(cutSavings.fiveYr, baseCcy)} in 5 yrs</strong> @ 7%
						</div>
					</div>
				</div>
				<div class="flex items-center gap-2 shrink-0">
					<button
						type="button"
						disabled={pausingSelected}
						onclick={pauseSelectedCuts}
						class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
					>
						<Pause class="w-3.5 h-3.5" />
						{pausingSelected ? 'Pausing...' : 'Pause Selected'}
					</button>
					<button
						type="button"
						onclick={() => (cutIds = new Set())}
						class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-xs text-slate-300 cursor-pointer"
					>
						Clear
					</button>
				</div>
			</div>
		{/if}

		<!-- FILTER / SEARCH / VIEW-MODE STRIP -->
		<div class="card-surface rounded-2xl p-3.5 flex flex-col xl:flex-row xl:items-center justify-between gap-3">
			<div class="inline-flex flex-wrap p-1 rounded-xl bg-slate-950 border border-slate-800 text-xs gap-0.5">
				{#each [
					['all', `All (${overview.items.length})`],
					['subscriptions', 'Subscriptions'],
					['bills', 'Fixed Bills'],
					['income', 'Income'],
					['paused', 'Paused']
				] as [tab, label]}
					<button
						type="button"
						onclick={() =>
							(filterTab = tab as 'all' | 'subscriptions' | 'bills' | 'income' | 'paused')}
						class="px-2.5 py-1.5 rounded-lg font-semibold transition cursor-pointer {filterTab === tab
							? 'bg-emerald-500/20 text-emerald-300'
							: 'text-slate-400 hover:text-white'}"
					>
						{label}
					</button>
				{/each}
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<div class="relative flex-1 sm:flex-none">
					<Search class="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
					<input
						type="text"
						bind:value={search}
						placeholder="Search bills..."
						class="pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 w-full sm:w-44"
					/>
				</div>

				<select
					bind:value={sortBy}
					class="px-2.5 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
				>
					<option value="due">Sort: Next Due</option>
					<option value="cost">Sort: Highest /mo</option>
					<option value="name">Sort: A–Z</option>
				</select>

				<div class="inline-flex p-0.5 rounded-xl bg-slate-950 border border-slate-800 text-xs">
					<button
						type="button"
						onclick={() => (viewMode = 'split')}
						class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium cursor-pointer {viewMode === 'split'
							? 'bg-slate-800 text-white'
							: 'text-slate-400 hover:text-white'}"
						title="Calendar + List"
					>
						<Columns2 class="w-3.5 h-3.5" />
						<span class="hidden sm:inline">Split</span>
					</button>
					<button
						type="button"
						onclick={() => (viewMode = 'list')}
						class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium cursor-pointer {viewMode === 'list'
							? 'bg-slate-800 text-white'
							: 'text-slate-400 hover:text-white'}"
						title="List only"
					>
						<LayoutList class="w-3.5 h-3.5" />
						<span class="hidden sm:inline">List</span>
					</button>
					<button
						type="button"
						onclick={() => (viewMode = 'calendar')}
						class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium cursor-pointer {viewMode === 'calendar'
							? 'bg-slate-800 text-white'
							: 'text-slate-400 hover:text-white'}"
						title="Calendar only"
					>
						<Calendar class="w-3.5 h-3.5" />
						<span class="hidden sm:inline">Calendar</span>
					</button>
				</div>
			</div>
		</div>

		<!-- 2. MAIN CONTENT: CALENDAR + UPGRADED BILL LIST -->
		<div class="grid {viewMode === 'split' ? 'lg:grid-cols-12' : ''} gap-5 items-start">
			{#if viewMode === 'calendar' || viewMode === 'split'}
				<div class={viewMode === 'split' ? 'lg:col-span-5' : ''}>
					<BillCalendar
						items={overview.items}
						currency={baseCcy}
						{privacyMode}
						onSelectItem={(item) => (inspectedItemId = item.id)}
					/>
				</div>
			{/if}

			{#if viewMode === 'list' || viewMode === 'split'}
				<div class="{viewMode === 'split' ? 'lg:col-span-7' : ''} card-surface rounded-2xl overflow-hidden">
					{#if filteredItems.length === 0}
						<div class="p-12 text-center space-y-3">
							<Repeat class="w-9 h-9 text-slate-500 mx-auto" />
							<h2 class="text-base font-semibold text-white">No recurring items found</h2>
							<p class="text-xs text-slate-400 max-w-md mx-auto">
								Click <strong>Auto-Detect</strong> to scan your ledger for subscriptions, or add one with our 1-click presets.
							</p>
						</div>
					{:else}
						<div class="px-4 py-2.5 bg-slate-900/70 border-b border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
							<span>Click any bill to inspect payment history & edit · Check boxes to simulate cuts</span>
							<span class="font-mono-num">{filteredItems.length} shown</span>
						</div>

						<div class="divide-y divide-slate-800/60">
							{#each filteredItems as item}
								{@const badge = dueBadge(item)}
								{@const cat = item.category_id ? catMap.get(item.category_id) : null}
								{@const isCut = cutIds.has(item.id)}
								<div
									role="button"
									tabindex="0"
									onclick={() => (inspectedItemId = item.id)}
									onkeydown={(e) => {
										if (e.key === 'Enter' || e.key === ' ') {
											e.preventDefault();
											inspectedItemId = item.id;
										}
									}}
									class="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition cursor-pointer outline-none {isCut
										? 'bg-emerald-500/8'
										: item.is_active
											? 'hover:bg-slate-900/55'
											: 'opacity-50 hover:opacity-80'}"
								>
									<div class="flex items-start sm:items-center gap-3 min-w-0 flex-1">
										{#if item.is_active && item.direction === 'outflow'}
											<input
												type="checkbox"
												checked={isCut}
												onclick={(e) => e.stopPropagation()}
												onchange={() => toggleCut(item.id)}
												title="Include in 'What If I Cut This?' savings simulator"
												aria-label="Simulate cutting {item.merchant_name}"
												class="mt-1 sm:mt-0 rounded border-slate-700 cursor-pointer shrink-0"
											/>
										{/if}

										<div class="min-w-0 flex-1">
											<div class="flex items-center gap-1.5 flex-wrap">
												<span class="text-sm font-semibold text-white truncate">
													{item.merchant_name}
												</span>
												<span class="px-2 py-0.5 rounded-full border text-[10px] font-semibold {badge.cls}">
													{badge.label}
												</span>
												{#if item.is_subscription && item.direction === 'outflow'}
													<span class="px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-300 text-[10px] font-medium">
														Sub
													</span>
												{/if}
												{#if item.auto_detected}
													<span class="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300 text-[10px]">
														Auto
													</span>
												{/if}
												{#if item.price_change_pct && Number.parseFloat(item.price_change_pct) > 1}
													<span class="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 text-[10px] font-semibold">
														+{item.price_change_pct}%
													</span>
												{/if}
											</div>

											<div class="text-[11px] text-slate-400 flex items-center gap-2 flex-wrap mt-1">
												<span class="capitalize">{item.cadence}</span>
												<span>·</span>
												<span class="font-mono-num">Next: {formatDate(item.next_due_date)}</span>
												{#if cat}
													<span>·</span>
													<span style="color: {cat.color}">{cat.name}</span>
												{/if}
											</div>
										</div>
									</div>

									<div class="flex items-center justify-between sm:justify-end gap-3 pl-6 sm:pl-0 shrink-0">
										<div class="text-right">
											<div
												class="text-sm font-bold font-mono-num {item.direction === 'inflow'
													? 'text-emerald-400'
													: 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
											>
												{item.direction === 'inflow' ? '+' : '-'}{formatMoney(item.amount, item.currency)}
											</div>
											<div class="text-[10px] font-mono-num text-slate-500 {privacyMode ? 'privacy-blur' : ''}">
												{formatMoney(item.monthly_equivalent, item.currency)}/mo
											</div>
										</div>

										<div class="flex items-center gap-1">
											{#if item.is_active}
												<button
													type="button"
													onclick={(e) => {
														e.stopPropagation();
														markPaidItem = item;
														markPaidOpen = true;
													}}
													class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-[11px] font-semibold cursor-pointer"
													title="Mark paid and advance due date"
												>
													<CheckCircle2 class="w-3 h-3" /> Paid
												</button>
											{/if}
											<button
												type="button"
												onclick={(e) => {
													e.stopPropagation();
													toggleActive(item);
												}}
												class="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 cursor-pointer"
												title={item.is_active ? 'Pause' : 'Resume'}
											>
												{#if item.is_active}
													<Pause class="w-3.5 h-3.5" />
												{:else}
													<Play class="w-3.5 h-3.5 text-emerald-400" />
												{/if}
											</button>
											<button
												type="button"
												onclick={(e) => {
													e.stopPropagation();
													deleteTarget = item;
												}}
												class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
												title="Delete recurring item"
											>
												<Trash2 class="w-3.5 h-3.5" />
											</button>
										</div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>

<!-- 4. SUBSCRIPTION INSPECTOR SLIDE-OVER DRAWER -->
<RecurringDetailDrawer
	item={inspectedItem}
	{categories}
	{privacyMode}
	onClose={() => (inspectedItemId = null)}
	onSaved={async () => {
		overview = await api.getRecurring();
		statusMsg = 'Recurring schedule updated.';
	}}
	onMarkPaid={(it) => {
		markPaidItem = it;
		markPaidOpen = true;
	}}
	onRequestDelete={(it) => (deleteTarget = it)}
/>

<!-- 3. MARK PAID MODAL -->
<MarkPaidModal
	bind:open={markPaidOpen}
	item={markPaidItem}
	{accounts}
	onDone={async (msg) => {
		overview = await api.getRecurring();
		statusMsg = msg;
	}}
/>

<!-- 5. UPGRADED ADD BILL / SUBSCRIPTION MODAL WITH QUICK PRESETS -->
{#if showCreateModal}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
		<div class="card-surface rounded-2xl w-full max-w-lg p-6 space-y-5 border border-slate-700/80 my-auto">
			<div class="flex items-center justify-between">
				<div>
					<h2 class="text-base font-semibold text-white">Add Recurring Bill or Subscription</h2>
					<p class="text-[11px] text-slate-400">Use a 1-click preset or enter a custom recurring schedule.</p>
				</div>
				<button type="button" onclick={() => (showCreateModal = false)} class="text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>

			<!-- Quick Presets -->
			<div class="space-y-2">
				<div class="text-[11px] font-medium text-slate-400 flex items-center gap-1.5">
					<Sparkles class="w-3 h-3 text-emerald-400" /> Quick Presets
				</div>
				<div class="flex flex-wrap gap-1.5">
					{#each PRESETS as p}
						<button
							type="button"
							onclick={() => applyPreset(p)}
							class="px-2.5 py-1 rounded-xl bg-slate-950/85 hover:bg-slate-900 border border-slate-800 hover:border-slate-600 text-[11px] text-slate-200 transition cursor-pointer"
						>
							{p.label}
						</button>
					{/each}
				</div>
			</div>

			<form onsubmit={handleCreate} class="space-y-4">
				<div>
					<label for="rec-name" class="block text-xs font-medium text-slate-300 mb-1">Merchant / Name</label>
					<input
						id="rec-name"
						type="text"
						required
						bind:value={merchantName}
						placeholder="e.g., Spotify, Magti Internet, Rent, Salary"
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white"
					/>
				</div>

				<div class="grid grid-cols-3 gap-3">
					<div class="col-span-2">
						<label for="rec-amt" class="block text-xs font-medium text-slate-300 mb-1">Amount</label>
						<input
							id="rec-amt"
							type="number"
							step="0.01"
							min="0.01"
							required
							bind:value={amount}
							placeholder="0.00"
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num"
						/>
					</div>
					<div>
						<label for="rec-ccy" class="block text-xs font-medium text-slate-300 mb-1">Currency</label>
						<select
							id="rec-ccy"
							bind:value={currency}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num"
						>
							{#each CURRENCIES as c}
								<option value={c}>{c}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="rec-cad" class="block text-xs font-medium text-slate-300 mb-1">Cadence</label>
						<select id="rec-cad" bind:value={cadence} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white">
							<option value="weekly">Weekly</option>
							<option value="biweekly">Bi-Weekly</option>
							<option value="monthly">Monthly</option>
							<option value="quarterly">Quarterly</option>
							<option value="yearly">Yearly</option>
						</select>
					</div>
					<div>
						<label for="rec-due" class="block text-xs font-medium text-slate-300 mb-1">Next Due Date</label>
						<input
							id="rec-due"
							type="date"
							required
							bind:value={nextDueDate}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white"
						/>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="rec-dir" class="block text-xs font-medium text-slate-300 mb-1">Direction</label>
						<select id="rec-dir" bind:value={direction} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white">
							<option value="outflow">Expense / Bill</option>
							<option value="inflow">Recurring Income</option>
						</select>
					</div>
					<div>
						<label for="rec-cat" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
						<select id="rec-cat" bind:value={categoryId} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white">
							<option value="">Uncategorized</option>
							{#each categories as cat}
								<option value={cat.id}>{cat.name}</option>
							{/each}
						</select>
					</div>
				</div>

				{#if direction === 'outflow'}
					<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
						<input type="checkbox" bind:checked={isSubscription} class="rounded border-slate-700" />
						Classify as a digital/lifestyle subscription (included in 5-Year Subscription Audit)
					</label>
				{/if}

				<div class="flex justify-end gap-2.5 pt-2">
					<button type="button" onclick={() => (showCreateModal = false)} class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 cursor-pointer">
						Cancel
					</button>
					<button type="submit" disabled={saving} class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50">
						{saving ? 'Saving...' : 'Add Recurring'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- SAFE DELETE MODAL -->
{#if deleteTarget}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-sm p-6 space-y-4 border border-rose-500/35">
			<div class="flex items-start gap-3">
				<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
					<AlertTriangle class="w-5 h-5" />
				</div>
				<div>
					<h2 class="text-base font-semibold text-white">Delete "{deleteTarget.merchant_name}"?</h2>
					<p class="text-xs text-slate-400 mt-0.5">
						Removes this {deleteTarget.cadence} recurring schedule ({formatMoney(deleteTarget.amount, deleteTarget.currency)}). Past ledger transactions remain untouched.
					</p>
				</div>
			</div>
			<div class="flex items-center justify-end gap-2 pt-1">
				<button
					type="button"
					disabled={deleting}
					onclick={() => (deleteTarget = null)}
					class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
				<button
					type="button"
					disabled={deleting}
					onclick={confirmDelete}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					<Trash2 class="w-3.5 h-3.5" />
					{deleting ? 'Deleting...' : 'Delete Permanently'}
				</button>
			</div>
		</div>
	</div>
{/if}
