<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import type { AdminOverview, AdminUserSummary } from '$lib/api/types';
	import { formatDate } from '$lib/utils/format';
	import FinancinioLoader from '$lib/components/FinancinioLoader.svelte';
	import AdminUserDrawer from '$lib/components/admin/AdminUserDrawer.svelte';
	import {
		ShieldCheck,
		Users,
		Infinity as InfinityIcon,
		Cpu,
		Database,
		Search,
		Sliders,
		CheckCircle2,
		AlertTriangle,
		RefreshCw,
		X,
		Activity,
		ArrowUpDown,
		ChevronRight
	} from 'lucide-svelte';

	type TierFilter = 'all' | 'standard' | 'unlimited' | 'admin' | 'suspended';
	type SortMode = 'newest' | 'tokens' | 'quota' | 'transactions';

	let overview = $state<AdminOverview | null>(null);
	let users = $state<AdminUserSummary[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);

	let search = $state('');
	let tierFilter = $state<TierFilter>('all');
	let sortMode = $state<SortMode>('newest');
	let busyUserId = $state<string | null>(null);
	let inspectingUser = $state<AdminUserSummary | null>(null);

	// AI usage feed filters
	let usageFeatureFilter = $state('all');
	let usageSearch = $state('');

	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	async function loadAll(silent = false) {
		if (auth.user?.role !== 'admin') {
			loading = false;
			return;
		}
		if (!silent) loading = true;
		else refreshing = true;
		error = null;
		try {
			const [ov, list] = await Promise.all([
				api.adminOverview(),
				api.adminListUsers({ search, tier: tierFilter })
			]);
			overview = ov;
			users = list;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load admin dashboard';
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function refreshUsers() {
		try {
			users = await api.adminListUsers({ search, tier: tierFilter });
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to filter users';
		}
	}

	function handleSearchInput() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(refreshUsers, 220);
	}

	onMount(() => {
		loadAll(false);
		return () => clearTimeout(searchTimer);
	});

	async function toggleUnlimited(u: AdminUserSummary) {
		busyUserId = u.id;
		error = null;
		notice = null;
		try {
			const nextVal = !u.has_unlimited_ai;
			const updated = await api.adminUpdateUserAccess(u.id, { has_unlimited_ai: nextVal });
			users = users.map((row) => (row.id === u.id ? updated : row));
			if (inspectingUser?.id === u.id) inspectingUser = updated;
			overview = await api.adminOverview();
			if (u.id === auth.user?.id) await auth.refresh();
			notice = nextVal
				? `Granted Unlimited Full AI Access to ${u.email}.`
				: `Reverted ${u.email} to fixed token limit (${u.ai_token_limit.toLocaleString()}).`;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Could not update access';
		} finally {
			busyUserId = null;
		}
	}

	async function handleDrawerUpdated(updated: AdminUserSummary, message: string) {
		users = users.map((row) => (row.id === updated.id ? updated : row));
		inspectingUser = updated;
		notice = message;
		try {
			overview = await api.adminOverview();
			if (updated.id === auth.user?.id) await auth.refresh();
		} catch {
			// non-fatal
		}
	}

	function pctUsed(u: AdminUserSummary): number {
		if (u.ai_token_limit <= 0) return 100;
		return Math.min(100, Math.round((u.ai_tokens_used / u.ai_token_limit) * 100));
	}

	function getInitials(u: AdminUserSummary): string {
		const parts = (u.full_name || u.email).trim().split(/\s+/);
		if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
		return parts[0].slice(0, 2).toUpperCase();
	}

	let sortedUsers = $derived.by(() => {
		const copy = [...users];
		if (sortMode === 'tokens') {
			copy.sort((a, b) => b.ai_tokens_used - a.ai_tokens_used);
		} else if (sortMode === 'quota') {
			copy.sort((a, b) => {
				const pa = a.has_unlimited_ai ? -1 : pctUsed(a);
				const pb = b.has_unlimited_ai ? -1 : pctUsed(b);
				return pb - pa;
			});
		} else if (sortMode === 'transactions') {
			copy.sort((a, b) => b.transactions_count - a.transactions_count);
		} else {
			copy.sort((a, b) => b.created_at.localeCompare(a.created_at));
		}
		return copy;
	});

	let featureBreakdown = $derived.by(() => {
		if (!overview) return [];
		const map = new Map<string, { tokens: number; count: number }>();
		let grandTotal = 0;
		for (const ev of overview.recent_ai_usage) {
			const prev = map.get(ev.feature) ?? { tokens: 0, count: 0 };
			prev.tokens += ev.total_tokens;
			prev.count += 1;
			grandTotal += ev.total_tokens;
			map.set(ev.feature, prev);
		}
		return [...map.entries()]
			.map(([feature, stats]) => ({
				feature,
				tokens: stats.tokens,
				count: stats.count,
				pct: grandTotal > 0 ? Math.round((stats.tokens / grandTotal) * 100) : 0
			}))
			.sort((a, b) => b.tokens - a.tokens);
	});

	let usageFeatures = $derived(['all', ...featureBreakdown.map((f) => f.feature)]);

	let filteredUsageEvents = $derived.by(() => {
		if (!overview) return [];
		const q = usageSearch.trim().toLowerCase();
		return overview.recent_ai_usage.filter((ev) => {
			if (usageFeatureFilter !== 'all' && ev.feature !== usageFeatureFilter) return false;
			if (q) {
				const hay = `${ev.user_email || ''} ${ev.feature} ${ev.model}`.toLowerCase();
				if (!hay.includes(q)) return false;
			}
			return true;
		});
	});

	let avgTxPerUser = $derived(
		overview && overview.total_users > 0
			? Math.round(overview.total_transactions / overview.total_users)
			: 0
	);
</script>

{#if auth.user?.role !== 'admin'}
	<div class="card-surface rounded-2xl p-12 text-center max-w-lg mx-auto mt-12 space-y-4">
		<div class="h-14 w-14 mx-auto rounded-2xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400">
			<ShieldCheck class="w-7 h-7" />
		</div>
		<h1 class="text-xl font-bold text-white">Administrator Access Required</h1>
		<p class="text-sm text-slate-400">
			This console is restricted to platform administrators.
		</p>
		<a
			href="/"
			class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white"
		>
			Return to Dashboard
		</a>
	</div>
{:else if loading}
	<FinancinioLoader
		fullscreen={false}
		label="Loading Admin Control Center"
		subtitles={[
			'Aggregating platform user & ledger metrics...',
			'Syncing AI token telemetry & quota states...'
		]}
	/>
{:else}
	<div class="space-y-6 pb-12">
		<!-- Executive Header -->
		<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
			<div>
				<div class="flex items-center gap-2.5 flex-wrap">
					<div class="h-9 w-9 rounded-xl bg-violet-500/15 border border-violet-500/35 flex items-center justify-center text-violet-300">
						<ShieldCheck class="w-5 h-5" />
					</div>
					<h1 class="text-2xl font-bold tracking-tight text-white">Admin Control Center</h1>
					<span class="px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-violet-500/15 border border-violet-500/30 text-violet-300">
						Platform Ops
					</span>
				</div>
				<p class="text-sm text-slate-400 mt-1">
					Monitor platform health, inspect per-user AI telemetry, adjust token caps, and manage roles.
				</p>
			</div>

			<button
				type="button"
				disabled={refreshing}
				onclick={() => loadAll(true)}
				class="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-200 transition cursor-pointer w-fit disabled:opacity-50"
			>
				<RefreshCw class="w-3.5 h-3.5 {refreshing ? 'animate-spin text-emerald-400' : 'text-slate-400'}" />
				{refreshing ? 'Refreshing...' : 'Refresh Telemetry'}
			</button>
		</div>

		<!-- Alerts -->
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
		{#if notice}
			<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-sm flex items-start justify-between gap-3">
				<div class="flex items-start gap-2.5">
					<CheckCircle2 class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
					<span>{notice}</span>
				</div>
				<button type="button" onclick={() => (notice = null)} class="text-emerald-300 hover:text-white cursor-pointer">
					<X class="w-4 h-4" />
				</button>
			</div>
		{/if}

		{#if overview}
			<!-- Platform KPI Hero Strip -->
			<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
				<div class="card-surface rounded-2xl p-5 space-y-2.5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Total Users</span>
						<Users class="w-4 h-4 text-emerald-400" />
					</div>
					<div class="text-3xl font-bold font-mono-num text-white">{overview.total_users}</div>
					<div class="flex items-center gap-2 text-[11px] text-slate-400">
						<span class="text-emerald-400 font-medium">{overview.active_users} active</span>
						<span>·</span>
						<span class="text-violet-300">{overview.admin_users} admin{overview.admin_users === 1 ? '' : 's'}</span>
						{#if overview.suspended_users > 0}
							<span>·</span>
							<span class="text-rose-300">{overview.suspended_users} suspended</span>
						{/if}
					</div>
				</div>

				<div class="card-surface rounded-2xl p-5 space-y-2.5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Unlimited AI Access</span>
						<InfinityIcon class="w-4 h-4 text-cyan-400" />
					</div>
					<div class="flex items-baseline gap-2">
						<span class="text-3xl font-bold font-mono-num text-cyan-300">{overview.unlimited_users}</span>
						<span class="text-xs font-mono-num text-slate-500">
							/ {overview.total_users} ({overview.total_users > 0 ? Math.round((overview.unlimited_users / overview.total_users) * 100) : 0}%)
						</span>
					</div>
					<div class="text-[11px] text-slate-400">
						Default standard cap: <span class="font-mono-num text-slate-200">{overview.default_token_limit.toLocaleString()}</span>
					</div>
				</div>

				<div class="card-surface rounded-2xl p-5 space-y-2.5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Platform AI Tokens</span>
						<Cpu class="w-4 h-4 text-violet-400" />
					</div>
					<div class="text-3xl font-bold font-mono-num text-white">
						{overview.total_ai_tokens_used.toLocaleString()}
					</div>
					<div class="text-[11px] text-slate-400 font-mono-num">
						Last 7d: <span class="text-violet-300 font-semibold">{overview.tokens_used_last_7d.toLocaleString()}</span> tokens
					</div>
				</div>

				<div class="card-surface rounded-2xl p-5 space-y-2.5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Platform Ledger Volume</span>
						<Database class="w-4 h-4 text-emerald-400" />
					</div>
					<div class="text-3xl font-bold font-mono-num text-white">
						{overview.total_transactions.toLocaleString()}
					</div>
					<div class="text-[11px] text-slate-400">
						{overview.total_accounts.toLocaleString()} accounts · ~{avgTxPerUser} tx/user
					</div>
				</div>
			</div>

			<!-- AI Feature Consumption Breakdown -->
			{#if featureBreakdown.length > 0}
				<div class="card-surface rounded-2xl p-5 space-y-3.5">
					<div class="flex items-center justify-between gap-2">
						<div class="flex items-center gap-2">
							<Activity class="w-4 h-4 text-cyan-400" />
							<h2 class="text-sm font-semibold text-white">Recent AI Consumption by Feature</h2>
						</div>
						<span class="text-[11px] text-slate-500">Last {overview.recent_ai_usage.length} events</span>
					</div>
					<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
						{#each featureBreakdown as item}
							<div class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/80 space-y-2">
								<div class="flex items-center justify-between gap-2 text-xs">
									<span class="font-medium text-cyan-300 truncate">{item.feature}</span>
									<span class="font-mono-num text-slate-400">{item.pct}%</span>
								</div>
								<div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
									<div class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400" style="width: {Math.max(4, item.pct)}%"></div>
								</div>
								<div class="flex items-center justify-between text-[11px] font-mono-num text-slate-400">
									<span class="text-white font-semibold">{item.tokens.toLocaleString()} tok</span>
									<span>{item.count} calls</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- User Directory & Quota Management -->
			<div class="card-surface rounded-2xl overflow-hidden">
				<div class="p-5 border-b border-slate-800/80 space-y-3">
					<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
						<div class="relative flex-1 max-w-md">
							<Search class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
							<input
								type="text"
								bind:value={search}
								oninput={handleSearchInput}
								placeholder="Search users by name or email..."
								class="w-full pl-9 pr-8 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs sm:text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
							/>
							{#if search}
								<button
									type="button"
									onclick={() => {
										search = '';
										refreshUsers();
									}}
									class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white cursor-pointer"
								>
									<X class="w-3.5 h-3.5" />
								</button>
							{/if}
						</div>

						<div class="flex flex-wrap items-center gap-2">
							<div class="flex flex-wrap items-center gap-1">
								{#each [
									{ id: 'all', label: 'All', count: overview.total_users },
									{ id: 'standard', label: 'Standard', count: overview.total_users - overview.unlimited_users },
									{ id: 'unlimited', label: 'Unlimited', count: overview.unlimited_users },
									{ id: 'admin', label: 'Admins', count: overview.admin_users },
									{ id: 'suspended', label: 'Suspended', count: overview.suspended_users }
								] as chip}
									<button
										type="button"
										onclick={() => {
											tierFilter = chip.id as TierFilter;
											refreshUsers();
										}}
										class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer {tierFilter === chip.id
											? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
											: 'bg-slate-950/70 text-slate-400 border-slate-800 hover:text-white'}"
									>
										{chip.label}
										<span class="font-mono-num text-[10px] opacity-80">{chip.count}</span>
									</button>
								{/each}
							</div>

							<div class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300">
								<ArrowUpDown class="w-3 h-3 text-slate-500" />
								<select
									bind:value={sortMode}
									aria-label="Sort users"
									class="bg-transparent text-xs text-slate-200 focus:outline-none cursor-pointer"
								>
									<option value="newest">Newest</option>
									<option value="tokens">Most AI Tokens</option>
									<option value="quota">Highest Quota %</option>
									<option value="transactions">Most Transactions</option>
								</select>
							</div>
						</div>
					</div>
				</div>

				{#if sortedUsers.length === 0}
					<div class="p-10 text-center text-xs text-slate-400">
						No users match your current search or filter.
					</div>
				{:else}
					<!-- Mobile User Cards (< md) -->
					<div class="md:hidden divide-y divide-slate-800/70">
						{#each sortedUsers as u}
							{@const pct = pctUsed(u)}
							<div class="p-4 space-y-3 {u.is_active ? '' : 'opacity-60 bg-rose-950/10'}">
								<div class="flex items-start justify-between gap-3">
									<button
										type="button"
										onclick={() => (inspectingUser = u)}
										class="flex items-center gap-3 min-w-0 text-left cursor-pointer"
									>
										<div class="h-9 w-9 rounded-xl bg-slate-900 border border-slate-800 text-emerald-300 font-bold text-xs flex items-center justify-center shrink-0">
											{getInitials(u)}
										</div>
										<div class="min-w-0">
											<div class="text-sm font-semibold text-white truncate flex items-center gap-1.5">
												{u.full_name}
												{#if u.role === 'admin'}
													<span class="text-[9px] uppercase px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300">Admin</span>
												{/if}
											</div>
											<div class="text-xs text-slate-400 truncate">{u.email}</div>
										</div>
									</button>
									<button
										type="button"
										onclick={() => (inspectingUser = u)}
										class="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 cursor-pointer"
									>
										<ChevronRight class="w-4 h-4" />
									</button>
								</div>

								<div class="flex items-center justify-between gap-3 text-xs">
									<div class="font-mono-num text-slate-300">
										{#if u.has_unlimited_ai}
											<span class="text-emerald-300 font-semibold">∞ Unlimited</span> · {u.ai_tokens_used.toLocaleString()} used
										{:else}
											{u.ai_tokens_used.toLocaleString()} / {u.ai_token_limit.toLocaleString()} ({pct}%)
										{/if}
									</div>
									<span class="text-slate-500 font-mono-num">{u.accounts_count} acc · {u.transactions_count} tx</span>
								</div>
							</div>
						{/each}
					</div>

					<!-- Desktop User Table (>= md) -->
					<div class="hidden md:block overflow-x-auto">
						<table class="w-full text-left border-collapse text-sm">
							<thead>
								<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400 bg-slate-950/40">
									<th class="py-3 px-4">User</th>
									<th class="py-3 px-4">Role / Status</th>
									<th class="py-3 px-4">AI Token Allowance</th>
									<th class="py-3 px-4">Ledger</th>
									<th class="py-3 px-4">Joined</th>
									<th class="py-3 px-4 text-right">Actions</th>
								</tr>
							</thead>
							<tbody class="divide-y divide-slate-800/60">
								{#each sortedUsers as u}
									{@const pct = pctUsed(u)}
									<tr class="transition {u.is_active ? 'hover:bg-slate-900/50' : 'opacity-60 bg-rose-950/10'}">
										<td class="py-3 px-4">
											<button
												type="button"
												onclick={() => (inspectingUser = u)}
												class="flex items-center gap-3 text-left group cursor-pointer"
											>
												<div class="h-9 w-9 rounded-xl bg-slate-900 border border-slate-800 group-hover:border-emerald-500/40 text-emerald-300 font-bold text-xs flex items-center justify-center shrink-0 transition">
													{getInitials(u)}
												</div>
												<div>
													<div class="font-semibold text-white group-hover:text-emerald-300 transition flex items-center gap-2">
														{u.full_name}
														{#if u.id === auth.user?.id}
															<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">You</span>
														{/if}
														<span class="text-[10px] font-mono-num text-slate-500">{u.base_currency}</span>
													</div>
													<div class="text-xs text-slate-400">{u.email}</div>
												</div>
											</button>
										</td>

										<td class="py-3 px-4 whitespace-nowrap">
											<div class="flex items-center gap-1.5">
												<span
													class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full {u.role === 'admin'
														? 'bg-violet-500/15 text-violet-300 border border-violet-500/30'
														: 'bg-slate-800 text-slate-300'}"
												>
													{u.role}
												</span>
												{#if !u.is_active}
													<span class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-300 border border-rose-500/30">
														Suspended
													</span>
												{/if}
											</div>
										</td>

										<td class="py-3 px-4 min-w-[210px]">
											{#if u.has_unlimited_ai}
												<span class="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-300 bg-emerald-500/15 px-2.5 py-1 rounded-full border border-emerald-500/30">
													<InfinityIcon class="w-3.5 h-3.5" /> Unlimited AI
												</span>
												<div class="text-[11px] text-slate-500 font-mono-num mt-1">
													{u.ai_tokens_used.toLocaleString()} tokens used
												</div>
											{:else}
												<div class="space-y-1">
													<div class="flex items-center justify-between text-xs font-mono-num">
														<span class="text-slate-200">{u.ai_tokens_used.toLocaleString()}</span>
														<span class="text-slate-400">/ {u.ai_token_limit.toLocaleString()} ({pct}%)</span>
													</div>
													<div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
														<div
															class="h-full rounded-full {pct >= 90 ? 'bg-rose-400' : pct >= 75 ? 'bg-amber-400' : 'bg-emerald-400'}"
															style="width: {pct}%"
														></div>
													</div>
												</div>
											{/if}
										</td>

										<td class="py-3 px-4 text-xs text-slate-400 font-mono-num whitespace-nowrap">
											{u.accounts_count} acc · {u.transactions_count} tx
										</td>

										<td class="py-3 px-4 text-xs text-slate-400 font-mono-num whitespace-nowrap">
											{formatDate(u.created_at)}
										</td>

										<td class="py-3 px-4 text-right whitespace-nowrap">
											<div class="inline-flex items-center gap-1.5">
												<button
													type="button"
													disabled={busyUserId === u.id}
													onclick={() => toggleUnlimited(u)}
													class="px-2.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer disabled:opacity-50 {u.has_unlimited_ai
														? 'bg-slate-800 hover:bg-slate-700 text-slate-200'
														: 'bg-emerald-500 hover:bg-emerald-400 text-slate-950'}"
												>
													{u.has_unlimited_ai ? 'Set Cap' : 'Grant Unlimited'}
												</button>

												<button
													type="button"
													onclick={() => (inspectingUser = u)}
													class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-medium text-slate-200 cursor-pointer"
													title="Inspect usage history & edit access"
												>
													<Sliders class="w-3.5 h-3.5 text-cyan-400" />
													Inspect
												</button>
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<!-- Recent Platform AI Token Usage Feed -->
			<div class="card-surface rounded-2xl p-6 space-y-4">
				<div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
					<div>
						<h2 class="text-base font-semibold text-white">Platform AI Token Telemetry</h2>
						<p class="text-xs text-slate-400 mt-0.5">Live stream of recent LLM calls across all users.</p>
					</div>

					<div class="flex flex-wrap items-center gap-2">
						<div class="relative w-full sm:w-52">
							<Search class="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
							<input
								type="text"
								bind:value={usageSearch}
								placeholder="Filter user or model..."
								class="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
							/>
						</div>
						<div class="flex flex-wrap items-center gap-1">
							{#each usageFeatures as feat}
								<button
									type="button"
									onclick={() => (usageFeatureFilter = feat)}
									class="px-2.5 py-1 rounded-lg text-[11px] font-medium border transition cursor-pointer {usageFeatureFilter === feat
										? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
										: 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'}"
								>
									{feat === 'all' ? 'All Features' : feat}
								</button>
							{/each}
						</div>
					</div>
				</div>

				{#if filteredUsageEvents.length === 0}
					<p class="text-xs text-slate-500 py-4 text-center">No AI usage events match this filter.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-left border-collapse text-xs">
							<thead>
								<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400">
									<th class="py-2.5 px-3">User</th>
									<th class="py-2.5 px-3">Feature</th>
									<th class="py-2.5 px-3">Model</th>
									<th class="py-2.5 px-3 text-right">Prompt</th>
									<th class="py-2.5 px-3 text-right">Completion</th>
									<th class="py-2.5 px-3 text-right">Total</th>
									<th class="py-2.5 px-3 text-right">Date</th>
								</tr>
							</thead>
							<tbody class="divide-y divide-slate-800/60 font-mono-num">
								{#each filteredUsageEvents as ev}
									<tr class="hover:bg-slate-900/40">
										<td class="py-2.5 px-3 font-sans text-slate-200">{ev.user_email || ev.user_id}</td>
										<td class="py-2.5 px-3">
											<span class="px-2 py-0.5 rounded bg-slate-800 text-cyan-300 font-sans font-medium">
												{ev.feature}
											</span>
										</td>
										<td class="py-2.5 px-3 text-slate-400">{ev.model}</td>
										<td class="py-2.5 px-3 text-right text-slate-400">{ev.prompt_tokens.toLocaleString()}</td>
										<td class="py-2.5 px-3 text-right text-slate-400">{ev.completion_tokens.toLocaleString()}</td>
										<td class="py-2.5 px-3 text-right font-semibold text-white">{ev.total_tokens.toLocaleString()}</td>
										<td class="py-2.5 px-3 text-right text-slate-500">{formatDate(ev.created_at)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}

<!-- Admin User Inspector & Access Drawer -->
<AdminUserDrawer
	user={inspectingUser}
	isSelf={inspectingUser?.id === auth.user?.id}
	onClose={() => (inspectingUser = null)}
	onUpdated={handleDrawerUpdated}
/>
