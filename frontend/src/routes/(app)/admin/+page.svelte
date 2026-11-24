<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import type { AdminOverview, AdminUserSummary } from '$lib/api/types';
	import { formatDate } from '$lib/utils/format';
	import {
		ShieldCheck,
		Users,
		Infinity as InfinityIcon,
		Cpu,
		Database,
		Search,
		Sliders,
		Ban,
		CheckCircle2,
		X
	} from 'lucide-svelte';

	let overview = $state<AdminOverview | null>(null);
	let users = $state<AdminUserSummary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);

	let search = $state('');
	let tierFilter = $state<'all' | 'standard' | 'unlimited' | 'admin' | 'suspended'>('all');
	let busyUserId = $state<string | null>(null);

	// Edit Quota Modal
	let editingUser = $state<AdminUserSummary | null>(null);
	let editLimit = $state(50000);
	let editUnlimited = $state(false);
	let editResetUsed = $state(false);
	let editRole = $state<'user' | 'admin'>('user');
	let savingEdit = $state(false);

	async function loadAll() {
		if (auth.user?.role !== 'admin') {
			loading = false;
			return;
		}
		loading = true;
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
		}
	}

	async function refreshUsers() {
		try {
			users = await api.adminListUsers({ search, tier: tierFilter });
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to filter users';
		}
	}

	onMount(loadAll);

	async function toggleUnlimited(u: AdminUserSummary) {
		busyUserId = u.id;
		error = null;
		notice = null;
		try {
			const nextVal = !u.has_unlimited_ai;
			const updated = await api.adminUpdateUserAccess(u.id, { has_unlimited_ai: nextVal });
			users = users.map((row) => (row.id === u.id ? updated : row));
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

	async function toggleSuspend(u: AdminUserSummary) {
		busyUserId = u.id;
		error = null;
		notice = null;
		try {
			const updated = await api.adminUpdateUserAccess(u.id, { is_active: !u.is_active });
			users = users.map((row) => (row.id === u.id ? updated : row));
			overview = await api.adminOverview();
			notice = updated.is_active ? `Reactivated ${u.email}.` : `Suspended ${u.email}.`;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Status update failed';
		} finally {
			busyUserId = null;
		}
	}

	function openEditModal(u: AdminUserSummary) {
		editingUser = u;
		editLimit = u.ai_token_limit;
		editUnlimited = u.has_unlimited_ai;
		editResetUsed = false;
		editRole = u.role;
	}

	async function saveEditModal(e: SubmitEvent) {
		e.preventDefault();
		if (!editingUser) return;
		savingEdit = true;
		error = null;
		notice = null;
		try {
			const updated = await api.adminUpdateUserAccess(editingUser.id, {
				ai_token_limit: Number(editLimit),
				has_unlimited_ai: editUnlimited,
				reset_tokens_used: editResetUsed,
				role: editingUser.id === auth.user?.id ? undefined : editRole
			});
			users = users.map((row) => (row.id === updated.id ? updated : row));
			overview = await api.adminOverview();
			if (updated.id === auth.user?.id) await auth.refresh();
			notice = `Updated access & quota for ${updated.email}.`;
			editingUser = null;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not save user access';
		} finally {
			savingEdit = false;
		}
	}

	function pctUsed(u: AdminUserSummary): number {
		if (u.ai_token_limit <= 0) return 100;
		return Math.min(100, Math.round((u.ai_tokens_used / u.ai_token_limit) * 100));
	}
</script>

{#if auth.user?.role !== 'admin'}
	<div class="card-surface rounded-2xl p-12 text-center max-w-lg mx-auto mt-12 space-y-3">
		<ShieldCheck class="w-10 h-10 text-rose-400 mx-auto" />
		<h1 class="text-xl font-bold text-white">Administrator Access Required</h1>
		<p class="text-sm text-slate-400">
			This area is restricted to platform administrators.
		</p>
	</div>
{:else}
	<div class="space-y-6">
		<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
			<div>
				<div class="flex items-center gap-2">
					<ShieldCheck class="w-6 h-6 text-emerald-400" />
					<h1 class="text-2xl font-bold tracking-tight text-white">Admin Control Center</h1>
				</div>
				<p class="text-sm text-slate-400 mt-0.5">
					Manage users, monitor AI token consumption, adjust fixed allowances, or grant Unlimited Full Access.
				</p>
			</div>
		</div>

		{#if error}
			<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
		{/if}
		{#if notice}
			<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
				<CheckCircle2 class="w-4 h-4 shrink-0" /> {notice}
			</div>
		{/if}

		{#if loading}
			<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
				{#each Array(4) as _}
					<div class="card-surface rounded-2xl h-28 animate-pulse"></div>
				{/each}
			</div>
		{:else if overview}
			<!-- Platform KPIs -->
			<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
				<div class="card-surface rounded-2xl p-5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Total Users</span>
						<Users class="w-4 h-4 text-emerald-400" />
					</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-2">{overview.total_users}</div>
					<div class="text-xs text-slate-400 mt-1">
						{overview.active_users} active · {overview.admin_users} admin{overview.admin_users === 1 ? '' : 's'}
					</div>
				</div>

				<div class="card-surface rounded-2xl p-5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Unlimited Full Access</span>
						<InfinityIcon class="w-4 h-4 text-cyan-400" />
					</div>
					<div class="text-2xl font-bold font-mono-num text-cyan-300 mt-2">{overview.unlimited_users}</div>
					<div class="text-xs text-slate-400 mt-1">
						Default cap: {overview.default_token_limit.toLocaleString()} tokens
					</div>
				</div>

				<div class="card-surface rounded-2xl p-5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Platform AI Tokens</span>
						<Cpu class="w-4 h-4 text-violet-400" />
					</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-2">
						{overview.total_ai_tokens_used.toLocaleString()}
					</div>
					<div class="text-xs text-slate-400 mt-1 font-mono-num">
						Last 7d: {overview.tokens_used_last_7d.toLocaleString()} tokens
					</div>
				</div>

				<div class="card-surface rounded-2xl p-5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Platform Ledger Volume</span>
						<Database class="w-4 h-4 text-emerald-400" />
					</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-2">
						{overview.total_transactions.toLocaleString()}
					</div>
					<div class="text-xs text-slate-400 mt-1">
						Across {overview.total_accounts.toLocaleString()} accounts
					</div>
				</div>
			</div>

			<!-- User Directory & Quota Management -->
			<div class="card-surface rounded-2xl overflow-hidden">
				<div class="p-5 border-b border-slate-800/80 flex flex-col md:flex-row md:items-center justify-between gap-3">
					<div class="relative flex-1 max-w-md">
						<Search class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
						<input
							type="text"
							bind:value={search}
							oninput={refreshUsers}
							placeholder="Search user by name or email..."
							class="w-full pl-9 pr-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
						/>
					</div>

					<div class="flex flex-wrap items-center gap-1.5">
						{#each (['all', 'standard', 'unlimited', 'admin', 'suspended'] as const) as f}
							<button
								type="button"
								onclick={() => { tierFilter = f; refreshUsers(); }}
								class="px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition cursor-pointer {tierFilter === f
									? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
									: 'bg-slate-950/70 text-slate-400 border border-slate-800 hover:text-white'}"
							>
								{f}
							</button>
						{/each}
					</div>
				</div>

				<div class="overflow-x-auto">
					<table class="w-full text-left border-collapse text-sm">
						<thead>
							<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400">
								<th class="py-3 px-4">User</th>
								<th class="py-3 px-4">Role / Status</th>
								<th class="py-3 px-4">AI Token Allowance</th>
								<th class="py-3 px-4">Ledger</th>
								<th class="py-3 px-4">Joined</th>
								<th class="py-3 px-4 text-right">Admin Actions</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-slate-800/60">
							{#each users as u}
								{@const pct = pctUsed(u)}
								<tr class="{u.is_active ? 'hover:bg-slate-900/50' : 'opacity-55 bg-rose-950/10'}">
									<td class="py-3 px-4">
										<div class="font-medium text-white flex items-center gap-2">
											{u.full_name}
											{#if u.id === auth.user?.id}
												<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">You</span>
											{/if}
										</div>
										<div class="text-xs text-slate-400">{u.email}</div>
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

									<td class="py-3 px-4 min-w-[200px]">
										{#if u.has_unlimited_ai}
											<span class="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-300 bg-emerald-500/15 px-2.5 py-1 rounded-full border border-emerald-500/30">
												<InfinityIcon class="w-3.5 h-3.5" /> Unlimited Full Access
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
												{u.has_unlimited_ai ? 'Set Fixed Cap' : 'Grant Unlimited'}
											</button>

											<button
												type="button"
												onclick={() => openEditModal(u)}
												class="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 cursor-pointer"
												title="Edit token limit, reset usage, or change role"
											>
												<Sliders class="w-3.5 h-3.5" />
											</button>

											{#if u.id !== auth.user?.id}
												<button
													type="button"
													disabled={busyUserId === u.id}
													onclick={() => toggleSuspend(u)}
													class="p-1.5 rounded-lg border cursor-pointer disabled:opacity-50 {u.is_active
														? 'bg-slate-900 hover:bg-rose-500/20 border-slate-700 text-slate-400 hover:text-rose-300'
														: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'}"
													title={u.is_active ? 'Suspend user' : 'Reactivate user'}
												>
													<Ban class="w-3.5 h-3.5" />
												</button>
											{/if}
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			<!-- Recent Platform AI Token Usage Feed -->
			<div class="card-surface rounded-2xl p-6 space-y-4">
				<h2 class="text-base font-semibold text-white">Recent AI Token Usage Events</h2>
				{#if overview.recent_ai_usage.length === 0}
					<p class="text-xs text-slate-500">No AI usage events recorded yet.</p>
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
									<th class="py-2.5 px-3 text-right">Total Tokens</th>
									<th class="py-2.5 px-3 text-right">Date</th>
								</tr>
							</thead>
							<tbody class="divide-y divide-slate-800/60 font-mono-num">
								{#each overview.recent_ai_usage as ev}
									<tr class="hover:bg-slate-900/40">
										<td class="py-2.5 px-3 font-sans text-slate-200">{ev.user_email || ev.user_id}</td>
										<td class="py-2.5 px-3">
											<span class="px-2 py-0.5 rounded bg-slate-800 text-cyan-300">{ev.feature}</span>
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

<!-- Edit Quota & Role Modal -->
{#if editingUser}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5">
			<div class="flex items-center justify-between">
				<div>
					<h2 class="text-lg font-semibold text-white">Manage User Access</h2>
					<p class="text-xs text-slate-400">{editingUser.email}</p>
				</div>
				<button type="button" onclick={() => (editingUser = null)} class="text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={saveEditModal} class="space-y-4">
				<label class="flex items-center justify-between p-3.5 rounded-xl bg-slate-950 border border-slate-800 cursor-pointer">
					<div>
						<div class="text-sm font-semibold text-emerald-300">Unlimited Full AI Access</div>
						<div class="text-[11px] text-slate-400">Bypass fixed token cap for Luna, Imports & Insights</div>
					</div>
					<input type="checkbox" bind:checked={editUnlimited} class="h-4 w-4" />
				</label>

				<div>
					<label for="ed-limit" class="block text-xs font-medium text-slate-300 mb-1">
						Fixed AI Token Allowance
					</label>
					<input
						id="ed-limit"
						type="number"
						min={0}
						step={5000}
						bind:value={editLimit}
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num"
					/>
					<p class="text-[11px] text-slate-500 mt-1">
						Currently used: {editingUser.ai_tokens_used.toLocaleString()} tokens
					</p>
				</div>

				<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
					<input type="checkbox" bind:checked={editResetUsed} />
					Reset consumed tokens counter back to 0
				</label>

				{#if editingUser.id !== auth.user?.id}
					<div>
						<label for="ed-role" class="block text-xs font-medium text-slate-300 mb-1">Role</label>
						<select
							id="ed-role"
							bind:value={editRole}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white"
						>
							<option value="user">Standard User</option>
							<option value="admin">Administrator</option>
						</select>
					</div>
				{/if}

				<div class="flex justify-end gap-2.5 pt-2">
					<button
						type="button"
						onclick={() => (editingUser = null)}
						class="px-4 py-2 rounded-xl text-sm text-slate-300 hover:bg-slate-800 cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={savingEdit}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50"
					>
						{savingEdit ? 'Saving...' : 'Save Access'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
