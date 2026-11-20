<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type { Category, RecurringCadence, RecurringItem, RecurringOverview } from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import {
		Repeat,
		Radar,
		Plus,
		AlertTriangle,
		Calendar,
		Trash2,
		Sparkles,
		X
	} from 'lucide-svelte';

	let overview = $state<RecurringOverview | null>(null);
	let categories = $state<Category[]>([]);
	let loading = $state(true);
	let scanning = $state(false);
	let scanResultMsg = $state<string | null>(null);
	let error = $state<string | null>(null);

	// Create modal
	let showModal = $state(false);
	let merchantName = $state('');
	let amount = $state('');
	let cadence = $state<RecurringCadence>('monthly');
	let direction = $state<'outflow' | 'inflow'>('outflow');
	let nextDueDate = $state(new Date().toISOString().slice(0, 10));
	let categoryId = $state('');
	let isSubscription = $state(true);
	let saving = $state(false);

	let baseCcy = $derived(auth.user?.base_currency || 'USD');
	let catMap = $derived(new Map(categories.map((c) => [c.id, c])));

	async function loadData() {
		loading = true;
		error = null;
		try {
			const [ov, cats] = await Promise.all([api.getRecurring(), api.listCategories()]);
			overview = ov;
			categories = cats;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load recurring bills';
		} finally {
			loading = false;
		}
	}

	onMount(loadData);

	async function handleScan() {
		scanning = true;
		error = null;
		scanResultMsg = null;
		try {
			const res = await api.detectRecurring();
			overview = res.overview;
			scanResultMsg = `Scan complete: ${res.detected_new} new recurring items detected, ${res.updated_existing} updated, ${res.price_hikes_found} price hike alerts found.`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Detection scan failed';
		} finally {
			scanning = false;
		}
	}

	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = null;
		try {
			await api.createRecurring({
				merchant_name: merchantName,
				amount,
				currency: baseCcy,
				direction,
				cadence,
				next_due_date: nextDueDate,
				category_id: categoryId || null,
				is_subscription: isSubscription
			});
			showModal = false;
			merchantName = '';
			amount = '';
			overview = await api.getRecurring();
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

	async function handleDelete(item: RecurringItem) {
		if (!confirm(`Delete recurring item "${item.merchant_name}"?`)) return;
		await api.deleteRecurring(item.id);
		overview = await api.getRecurring();
	}
</script>

<div class="space-y-6">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl font-bold tracking-tight text-white">Recurring Bills & Subscriptions</h1>
			<p class="text-sm text-slate-400 mt-0.5">
				Automatically detect subscriptions from your ledger, track upcoming bills, and catch price hikes early.
			</p>
		</div>
		<div class="flex items-center gap-2.5">
			<button
				type="button"
				disabled={scanning}
				onclick={handleScan}
				class="inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-sm font-medium text-slate-200 transition cursor-pointer disabled:opacity-50"
			>
				<Radar class="w-4 h-4 text-cyan-400" />
				{scanning ? 'Scanning Ledger...' : 'Auto-Detect from Ledger'}
			</button>
			<button
				type="button"
				onclick={() => (showModal = true)}
				class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer"
			>
				<Plus class="w-4 h-4" />
				Add Bill
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
	{/if}
	{#if scanResultMsg}
		<div class="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-200 text-sm flex items-center gap-2">
			<Sparkles class="w-4 h-4 shrink-0 text-cyan-400" />
			{scanResultMsg}
		</div>
	{/if}

	{#if loading}
		<div class="grid sm:grid-cols-3 gap-4">
			{#each Array(3) as _}
				<div class="card-surface rounded-2xl h-28 animate-pulse"></div>
			{/each}
		</div>
	{:else if overview}
		<!-- Price Hike Alert Banner -->
		{#if overview.price_hike_alerts.length > 0}
			<div class="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 space-y-2">
				<div class="flex items-center gap-2 text-amber-300 text-sm font-semibold">
					<AlertTriangle class="w-4 h-4" />
					Subscription Price Creep Detected ({overview.price_hike_alerts.length})
				</div>
				<div class="grid sm:grid-cols-2 gap-2">
					{#each overview.price_hike_alerts as alert}
						<div class="flex items-center justify-between px-3 py-2 rounded-xl bg-slate-950/60 text-xs">
							<span class="font-medium text-white">{alert.merchant_name}</span>
							<span class="font-mono-num text-amber-300">
								{formatMoney(alert.previous_amount || '0', alert.currency)} → {formatMoney(alert.amount, alert.currency)}
								(+{alert.price_change_pct}%)
							</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- KPI Summary -->
		<div class="grid sm:grid-cols-3 gap-4">
			<div class="card-surface rounded-2xl p-5">
				<div class="text-xs text-slate-400">Monthly Recurring Burn</div>
				<div class="text-2xl font-bold font-mono-num text-rose-400 mt-1.5">
					{formatMoney(overview.monthly_recurring_expenses, baseCcy)}
				</div>
				<div class="text-xs text-slate-400 mt-1 font-mono-num">
					Annualized: {formatMoney(overview.annual_recurring_expenses, baseCcy)}/yr
				</div>
			</div>

			<div class="card-surface rounded-2xl p-5">
				<div class="text-xs text-slate-400">Due in Next 30 Days</div>
				<div class="text-2xl font-bold font-mono-num text-white mt-1.5">
					{formatMoney(overview.upcoming_30d_total, baseCcy)}
				</div>
				<div class="text-xs text-slate-400 mt-1">Upcoming scheduled outflows</div>
			</div>

			<div class="card-surface rounded-2xl p-5">
				<div class="text-xs text-slate-400">Recurring Income (Monthly Eq.)</div>
				<div class="text-2xl font-bold font-mono-num text-emerald-400 mt-1.5">
					{formatMoney(overview.monthly_recurring_income, baseCcy)}
				</div>
				<div class="text-xs text-slate-400 mt-1">Detected payroll & retainers</div>
			</div>
		</div>

		<!-- Recurring Items Table -->
		<div class="card-surface rounded-2xl overflow-hidden">
			{#if overview.items.length === 0}
				<div class="p-12 text-center space-y-3">
					<Repeat class="w-9 h-9 text-slate-500 mx-auto" />
					<h2 class="text-base font-semibold text-white">No recurring bills tracked yet</h2>
					<p class="text-xs text-slate-400 max-w-md mx-auto">
						Click <strong>Auto-Detect from Ledger</strong> after importing 2+ months of statements, or add bills manually.
					</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<table class="w-full text-left border-collapse text-sm">
						<thead>
							<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400">
								<th class="py-3 px-4">Merchant</th>
								<th class="py-3 px-4">Cadence</th>
								<th class="py-3 px-4">Next Due</th>
								<th class="py-3 px-4 text-right">Amount</th>
								<th class="py-3 px-4 text-right">Monthly Eq.</th>
								<th class="py-3 px-4 text-right">Actions</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-slate-800/60">
							{#each overview.items as item}
								<tr class="{item.is_active ? 'hover:bg-slate-900/50' : 'opacity-45'}">
									<td class="py-3 px-4">
										<div class="flex items-center gap-2">
											<span class="font-medium text-white">{item.merchant_name}</span>
											{#if item.auto_detected}
												<span class="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300">Auto</span>
											{/if}
											{#if item.price_change_pct && Number.parseFloat(item.price_change_pct) > 1}
												<span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 font-semibold">
													+{item.price_change_pct}%
												</span>
											{/if}
										</div>
										{#if item.category_id && catMap.get(item.category_id)}
											<div class="text-[11px] text-slate-400 mt-0.5">{catMap.get(item.category_id)?.name}</div>
										{/if}
									</td>
									<td class="py-3 px-4 text-xs text-slate-300 capitalize">{item.cadence}</td>
									<td class="py-3 px-4 text-xs text-slate-300 font-mono-num whitespace-nowrap">
										<span class="inline-flex items-center gap-1.5">
											<Calendar class="w-3.5 h-3.5 text-slate-500" />
											{formatDate(item.next_due_date)}
										</span>
									</td>
									<td class="py-3 px-4 text-right font-mono-num font-semibold {item.direction === 'inflow' ? 'text-emerald-400' : 'text-white'}">
										{item.direction === 'inflow' ? '+' : '-'}{formatMoney(item.amount, item.currency)}
									</td>
									<td class="py-3 px-4 text-right font-mono-num text-xs text-slate-400">
										{formatMoney(item.monthly_equivalent, item.currency)}/mo
									</td>
									<td class="py-3 px-4 text-right whitespace-nowrap">
										<button
											type="button"
											onclick={() => toggleActive(item)}
											class="text-xs px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 mr-1.5 cursor-pointer"
										>
											{item.is_active ? 'Pause' : 'Resume'}
										</button>
										<button
											type="button"
											onclick={() => handleDelete(item)}
											class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
										>
											<Trash2 class="w-3.5 h-3.5" />
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</div>

{#if showModal}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Add Recurring Bill / Income</h2>
				<button type="button" onclick={() => (showModal = false)} class="text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={handleCreate} class="space-y-4">
				<div>
					<label for="rec-name" class="block text-xs font-medium text-slate-300 mb-1">Merchant / Name</label>
					<input
						id="rec-name"
						type="text"
						required
						bind:value={merchantName}
						placeholder="e.g., Spotify, Rent, Salary"
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="rec-amt" class="block text-xs font-medium text-slate-300 mb-1">Amount ({baseCcy})</label>
						<input
							id="rec-amt"
							type="number"
							step="0.01"
							min="0.01"
							required
							bind:value={amount}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num"
						/>
					</div>
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
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="rec-dir" class="block text-xs font-medium text-slate-300 mb-1">Type</label>
						<select id="rec-dir" bind:value={direction} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white">
							<option value="outflow">Expense / Bill</option>
							<option value="inflow">Recurring Income</option>
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

				<div>
					<label for="rec-cat" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
					<select id="rec-cat" bind:value={categoryId} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white">
						<option value="">Uncategorized</option>
						{#each categories as cat}
							<option value={cat.id}>{cat.name}</option>
						{/each}
					</select>
				</div>

				<div class="flex justify-end gap-2.5 pt-2">
					<button type="button" onclick={() => (showModal = false)} class="px-4 py-2 rounded-xl text-sm text-slate-300 hover:bg-slate-800 cursor-pointer">
						Cancel
					</button>
					<button type="submit" disabled={saving} class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50">
						{saving ? 'Saving...' : 'Add Recurring'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
