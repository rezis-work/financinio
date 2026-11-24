<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { AdminUserSummary, AIUsageEvent } from '$lib/api/types';
	import { formatDate } from '$lib/utils/format';
	import {
		X,
		Infinity as InfinityIcon,
		ShieldCheck,
		Ban,
		CheckCircle2,
		Cpu,
		Database,
		RotateCcw,
		AlertTriangle,
		Activity
	} from 'lucide-svelte';

	interface Props {
		user: AdminUserSummary | null;
		isSelf: boolean;
		onClose: () => void;
		onUpdated: (updated: AdminUserSummary, message: string) => void;
	}

	let { user, isSelf, onClose, onUpdated }: Props = $props();

	const QUOTA_PRESETS = [25000, 50000, 100000, 250000, 1000000];

	let editLimit = $state(50000);
	let editUnlimited = $state(false);
	let editResetUsed = $state(false);
	let editRole = $state<'user' | 'admin'>('user');
	let saving = $state(false);
	let togglingStatus = $state(false);
	let confirmSuspend = $state(false);
	let drawerError = $state<string | null>(null);

	let usageLoading = $state(false);
	let usageEvents = $state<AIUsageEvent[]>([]);

	$effect(() => {
		if (!user) return;
		const target = user;
		editLimit = target.ai_token_limit;
		editUnlimited = target.has_unlimited_ai;
		editResetUsed = false;
		editRole = target.role;
		confirmSuspend = false;
		drawerError = null;
		usageLoading = true;
		usageEvents = [];

		api
			.adminUserUsage(target.id)
			.then((events) => {
				if (user?.id === target.id) usageEvents = events;
			})
			.catch(() => {
				if (user?.id === target.id) usageEvents = [];
			})
			.finally(() => {
				if (user?.id === target.id) usageLoading = false;
			});
	});

	let initials = $derived.by(() => {
		if (!user) return 'U';
		const parts = (user.full_name || user.email).trim().split(/\s+/);
		if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
		return parts[0].slice(0, 2).toUpperCase();
	});

	let pctUsed = $derived.by(() => {
		if (!user || user.ai_token_limit <= 0) return 100;
		return Math.min(100, Math.round((user.ai_tokens_used / user.ai_token_limit) * 100));
	});

	let featureBreakdown = $derived.by(() => {
		const map = new Map<string, number>();
		for (const ev of usageEvents) {
			map.set(ev.feature, (map.get(ev.feature) ?? 0) + ev.total_tokens);
		}
		return [...map.entries()].sort((a, b) => b[1] - a[1]);
	});

	async function handleSave(e: SubmitEvent) {
		e.preventDefault();
		if (!user) return;
		saving = true;
		drawerError = null;
		try {
			const updated = await api.adminUpdateUserAccess(user.id, {
				ai_token_limit: Number(editLimit),
				has_unlimited_ai: editUnlimited,
				reset_tokens_used: editResetUsed,
				role: isSelf ? undefined : editRole
			});
			editResetUsed = false;
			onUpdated(updated, `Updated access & AI quota for ${updated.email}.`);
		} catch (err) {
			drawerError = err instanceof ApiError ? err.message : 'Failed to update user access';
		} finally {
			saving = false;
		}
	}

	async function handleToggleActive() {
		if (!user || isSelf) return;
		togglingStatus = true;
		drawerError = null;
		try {
			const nextActive = !user.is_active;
			const updated = await api.adminUpdateUserAccess(user.id, { is_active: nextActive });
			confirmSuspend = false;
			onUpdated(
				updated,
				nextActive ? `Reactivated ${updated.email}.` : `Suspended ${updated.email} and revoked active sessions.`
			);
		} catch (err) {
			drawerError = err instanceof ApiError ? err.message : 'Failed to update user status';
		} finally {
			togglingStatus = false;
		}
	}
</script>

{#if user}
	<div
		class="fixed inset-0 z-50 bg-black/65 backdrop-blur-xs flex justify-end"
		role="dialog"
		aria-modal="true"
		aria-label="Inspect user access and usage"
	>
		<button type="button" class="flex-1 cursor-default" aria-label="Close drawer" onclick={onClose}></button>

		<div class="w-full max-w-xl bg-slate-950 border-l border-slate-800/90 h-full overflow-y-auto flex flex-col shadow-2xl">
			<!-- Header -->
			<div class="sticky top-0 z-10 bg-slate-950/95 backdrop-blur-md px-5 py-4 border-b border-slate-800/80 flex items-center justify-between gap-3">
				<div class="flex items-center gap-3 min-w-0">
					<div class="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-400/20 to-cyan-500/20 border border-emerald-500/30 text-emerald-300 font-bold text-sm flex items-center justify-center shrink-0">
						{initials}
					</div>
					<div class="min-w-0">
						<div class="flex items-center gap-2 flex-wrap">
							<h3 class="text-sm font-bold text-white truncate">{user.full_name}</h3>
							{#if isSelf}
								<span class="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] font-semibold text-slate-300">You</span>
							{/if}
							{#if !user.is_active}
								<span class="px-1.5 py-0.5 rounded bg-rose-500/15 border border-rose-500/30 text-[10px] font-semibold text-rose-300 uppercase">
									Suspended
								</span>
							{/if}
						</div>
						<p class="text-xs text-slate-400 truncate">{user.email}</p>
					</div>
				</div>

				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-4 h-4" />
				</button>
			</div>

			<div class="p-5 space-y-5 flex-1">
				{#if drawerError}
					<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start gap-2">
						<AlertTriangle class="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
						<span>{drawerError}</span>
					</div>
				{/if}

				<!-- Quick User Snapshot Stats -->
				<div class="grid grid-cols-3 gap-2.5">
					<div class="p-3 rounded-xl bg-slate-900/70 border border-slate-800/80">
						<div class="text-[10px] uppercase tracking-wider text-slate-400">Ledger</div>
						<div class="text-sm font-bold font-mono-num text-white mt-0.5 flex items-center gap-1">
							<Database class="w-3.5 h-3.5 text-emerald-400" />
							{user.transactions_count} tx
						</div>
						<div class="text-[10px] text-slate-500 mt-0.5">{user.accounts_count} accounts</div>
					</div>
					<div class="p-3 rounded-xl bg-slate-900/70 border border-slate-800/80">
						<div class="text-[10px] uppercase tracking-wider text-slate-400">Tokens Used</div>
						<div class="text-sm font-bold font-mono-num text-cyan-300 mt-0.5 flex items-center gap-1">
							<Cpu class="w-3.5 h-3.5 text-cyan-400" />
							{user.ai_tokens_used.toLocaleString()}
						</div>
						<div class="text-[10px] text-slate-500 mt-0.5">
							{user.has_unlimited_ai ? 'Unlimited' : `${pctUsed}% of cap`}
						</div>
					</div>
					<div class="p-3 rounded-xl bg-slate-900/70 border border-slate-800/80">
						<div class="text-[10px] uppercase tracking-wider text-slate-400">Workspace</div>
						<div class="text-sm font-bold font-mono-num text-white mt-0.5">{user.base_currency}</div>
						<div class="text-[10px] text-slate-500 mt-0.5">Joined {formatDate(user.created_at)}</div>
					</div>
				</div>

				<!-- Quota & Role Form -->
				<form onsubmit={handleSave} class="p-4 rounded-2xl bg-slate-900/55 border border-slate-800/80 space-y-4">
					<div class="text-xs font-semibold uppercase tracking-wider text-slate-400">
						AI Allowance & Role Controls
					</div>

					<label class="flex items-center justify-between p-3.5 rounded-xl bg-slate-950 border cursor-pointer transition {editUnlimited ? 'border-emerald-500/45 bg-emerald-500/[0.06]' : 'border-slate-800'}">
						<div class="flex items-center gap-2.5">
							<InfinityIcon class="w-4 h-4 {editUnlimited ? 'text-emerald-400' : 'text-slate-500'}" />
							<div>
								<div class="text-xs font-semibold text-white">Unlimited Full AI Access</div>
								<div class="text-[11px] text-slate-400">Uncapped Luna CFO, Imports & Insights</div>
							</div>
						</div>
						<input type="checkbox" bind:checked={editUnlimited} class="h-4 w-4 accent-emerald-500" />
					</label>

					<div class="space-y-2">
						<label for="drawer-limit" class="block text-xs font-medium text-slate-300">
							Fixed AI Token Limit
						</label>
						<input
							id="drawer-limit"
							type="number"
							min={0}
							step={5000}
							bind:value={editLimit}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono-num text-white focus:outline-none focus:border-emerald-500"
						/>
						<div class="flex flex-wrap items-center gap-1.5">
							{#each QUOTA_PRESETS as preset}
								<button
									type="button"
									onclick={() => (editLimit = preset)}
									class="px-2.5 py-1 rounded-lg text-[11px] font-mono-num border transition cursor-pointer {Number(editLimit) === preset
										? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
										: 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'}"
								>
									{preset >= 1000000 ? `${preset / 1000000}M` : `${preset / 1000}k`}
								</button>
							{/each}
						</div>
					</div>

					<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
						<input type="checkbox" bind:checked={editResetUsed} class="rounded border-slate-700 accent-cyan-400" />
						<RotateCcw class="w-3.5 h-3.5 text-cyan-400" />
						Reset consumed tokens counter back to 0
					</label>

					{#if !isSelf}
						<div>
							<label for="drawer-role" class="block text-xs font-medium text-slate-300 mb-1">
								Platform Role
							</label>
							<select
								id="drawer-role"
								bind:value={editRole}
								class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
							>
								<option value="user">Standard User</option>
								<option value="admin">Administrator</option>
							</select>
						</div>
					{/if}

					<div class="flex items-center justify-between gap-3 pt-1">
						{#if !isSelf}
							{#if confirmSuspend}
								<div class="flex items-center gap-1.5">
									<button
										type="button"
										disabled={togglingStatus}
										onclick={handleToggleActive}
										class="px-3 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
									>
										{togglingStatus ? 'Working...' : user.is_active ? 'Confirm Suspend' : 'Confirm Reactivate'}
									</button>
									<button
										type="button"
										onclick={() => (confirmSuspend = false)}
										class="px-2.5 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs cursor-pointer"
									>
										Cancel
									</button>
								</div>
							{:else}
								<button
									type="button"
									onclick={() => (confirmSuspend = true)}
									class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-semibold transition cursor-pointer {user.is_active
										? 'bg-rose-500/10 hover:bg-rose-500/20 border-rose-500/30 text-rose-300'
										: 'bg-emerald-500/15 hover:bg-emerald-500/25 border-emerald-500/35 text-emerald-300'}"
								>
									{#if user.is_active}
										<Ban class="w-3.5 h-3.5" /> Suspend User
									{:else}
										<ShieldCheck class="w-3.5 h-3.5" /> Reactivate User
									{/if}
								</button>
							{/if}
						{:else}
							<span class="text-[11px] text-slate-500">Self-lockout protection active</span>
						{/if}

						<button
							type="submit"
							disabled={saving}
							class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
						>
							<CheckCircle2 class="w-3.5 h-3.5" />
							{saving ? 'Saving...' : 'Save Access'}
						</button>
					</div>
				</form>

				<!-- Per-User AI Usage History (GET /admin/users/{id}/usage) -->
				<div class="space-y-3">
					<div class="flex items-center justify-between">
						<div class="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
							<Activity class="w-3.5 h-3.5 text-violet-400" />
							User AI Usage History ({usageEvents.length})
						</div>
					</div>

					{#if featureBreakdown.length > 0}
						<div class="flex flex-wrap gap-1.5">
							{#each featureBreakdown as [feat, total]}
								<span class="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-mono-num">
									<span class="text-cyan-300 font-sans font-medium">{feat}</span> · {total.toLocaleString()} tok
								</span>
							{/each}
						</div>
					{/if}

					{#if usageLoading}
						<div class="p-6 text-center text-xs text-slate-500">Loading user AI usage log...</div>
					{:else if usageEvents.length === 0}
						<div class="p-6 rounded-xl bg-slate-900/40 border border-slate-800/70 text-center text-xs text-slate-500">
							No AI token events recorded for this user yet.
						</div>
					{:else}
						<div class="rounded-xl border border-slate-800/80 divide-y divide-slate-800/70 overflow-hidden bg-slate-900/40">
							{#each usageEvents.slice(0, 20) as ev}
								<div class="px-3.5 py-2.5 flex items-center justify-between gap-3 text-xs">
									<div class="min-w-0">
										<div class="flex items-center gap-2 flex-wrap">
											<span class="px-2 py-0.5 rounded bg-slate-800 text-cyan-300 font-medium text-[10px]">
												{ev.feature}
											</span>
											<span class="text-slate-400 font-mono-num text-[11px] truncate">{ev.model}</span>
										</div>
										<div class="text-[10px] text-slate-500 font-mono-num mt-0.5">
											{ev.prompt_tokens.toLocaleString()} in · {ev.completion_tokens.toLocaleString()} out · {formatDate(ev.created_at)}
										</div>
									</div>
									<div class="font-mono-num font-bold text-white shrink-0">
										{ev.total_tokens.toLocaleString()}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>
{/if}
