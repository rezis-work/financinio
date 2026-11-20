<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError, clearTokens } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import type { AuditLog, CategorizationRule, Category, SystemStatus } from '$lib/api/types';
	import { formatDate } from '$lib/utils/format';
	import {
		Plus,
		Trash2,
		CheckCircle2,
		Cpu,
		Database,
		Activity,
		Download,
		ShieldAlert,
		History
	} from 'lucide-svelte';

	let fullName = $state(auth.user?.full_name || '');
	let baseCurrency = $state(auth.user?.base_currency || 'USD');
	let fiscalStartDay = $state(auth.user?.fiscal_start_day || 1);
	let savingProfile = $state(false);
	let profileSaved = $state(false);

	let categories = $state<Category[]>([]);
	let rules = $state<CategorizationRule[]>([]);
	let statusInfo = $state<SystemStatus | null>(null);
	let auditLogs = $state<AuditLog[]>([]);
	let error = $state<string | null>(null);
	let exportSuccess = $state<string | null>(null);

	// New rule form
	let matchPattern = $state('');
	let matchType = $state<'contains' | 'exact' | 'regex'>('contains');
	let categoryId = $state('');
	let merchantOverride = $state('');

	// Danger zone delete account
	let deletePassword = $state('');
	let deletePhrase = $state('');
	let deletingAccount = $state(false);

	let catMap = $derived(new Map(categories.map((c) => [c.id, c])));

	onMount(async () => {
		try {
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
			if (cats.length > 0) categoryId = cats[0].id;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load settings';
		}
	});

	async function saveProfile(e: SubmitEvent) {
		e.preventDefault();
		savingProfile = true;
		profileSaved = false;
		try {
			const updated = await api.updateMe({
				full_name: fullName,
				base_currency: baseCurrency,
				fiscal_start_day: fiscalStartDay
			});
			auth.user = updated;
			profileSaved = true;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Profile update failed';
		} finally {
			savingProfile = false;
		}
	}

	async function addRule(e: SubmitEvent) {
		e.preventDefault();
		if (!matchPattern.trim() || !categoryId) return;
		error = null;
		try {
			await api.createRule({
				match_pattern: matchPattern,
				match_type: matchType,
				category_id: categoryId,
				merchant_override: merchantOverride || undefined
			});
			matchPattern = '';
			merchantOverride = '';
			rules = await api.listRules();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not add rule';
		}
	}

	async function removeRule(id: string) {
		await api.deleteRule(id);
		rules = rules.filter((r) => r.id !== id);
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
		error = null;
		exportSuccess = null;
		try {
			const blob = await api.downloadTransactionsCsv();
			triggerDownload(blob, `financinio_transactions_${new Date().toISOString().slice(0, 10)}.csv`);
			exportSuccess = 'Transactions CSV downloaded.';
			auditLogs = await api.listAuditLogs();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'CSV export failed';
		}
	}

	async function handleExportJson() {
		error = null;
		exportSuccess = null;
		try {
			const data = await api.exportFullBackupJson();
			const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
			triggerDownload(blob, `financinio_backup_${new Date().toISOString().slice(0, 10)}.json`);
			exportSuccess = 'Full workspace JSON backup downloaded.';
			auditLogs = await api.listAuditLogs();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'JSON backup failed';
		}
	}

	async function handleDeleteAccount(e: SubmitEvent) {
		e.preventDefault();
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
</script>

<div class="space-y-6 max-w-4xl">
	<div>
		<h1 class="text-2xl font-bold tracking-tight text-white">Settings, Privacy & AI Rules</h1>
		<p class="text-sm text-slate-400 mt-0.5">
			Manage workspace preferences, Tier-1 rules, data exports, audit logs, and infrastructure health.
		</p>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
	{/if}
	{#if exportSuccess}
		<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
			<CheckCircle2 class="w-4 h-4 shrink-0" /> {exportSuccess}
		</div>
	{/if}

	<!-- Profile -->
	<form onsubmit={saveProfile} class="card-surface rounded-2xl p-6 space-y-4">
		<div class="flex items-center justify-between">
			<h2 class="text-base font-semibold text-white">Profile & Preferences</h2>
			{#if profileSaved}
				<span class="inline-flex items-center gap-1.5 text-xs text-emerald-400">
					<CheckCircle2 class="w-4 h-4" /> Saved
				</span>
			{/if}
		</div>

		<div class="grid sm:grid-cols-3 gap-4">
			<div>
				<label for="prof-name" class="block text-xs font-medium text-slate-300 mb-1">Full Name</label>
				<input
					id="prof-name"
					type="text"
					required
					bind:value={fullName}
					class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
				/>
			</div>
			<div>
				<label for="prof-ccy" class="block text-xs font-medium text-slate-300 mb-1">Base Currency</label>
				<input
					id="prof-ccy"
					type="text"
					maxlength={3}
					required
					bind:value={baseCurrency}
					class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white uppercase focus:outline-none focus:border-emerald-500"
				/>
			</div>
			<div>
				<label for="prof-day" class="block text-xs font-medium text-slate-300 mb-1">Budget Cycle Start Day</label>
				<input
					id="prof-day"
					type="number"
					min={1}
					max={28}
					bind:value={fiscalStartDay}
					class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num focus:outline-none focus:border-emerald-500"
				/>
			</div>
		</div>

		<div class="flex justify-end">
			<button
				type="submit"
				disabled={savingProfile}
				class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50"
			>
				{savingProfile ? 'Saving...' : 'Save Preferences'}
			</button>
		</div>
	</form>

	<!-- Tier-1 Categorization Rules -->
	<div class="card-surface rounded-2xl p-6 space-y-4">
		<div>
			<h2 class="text-base font-semibold text-white">Tier-1 Categorization Rules</h2>
			<p class="text-xs text-slate-400 mt-0.5">
				Rules run instantly with 99% confidence before Upstash Vector memory or LLM calls (zero token cost).
			</p>
		</div>

		<form onsubmit={addRule} class="grid sm:grid-cols-5 gap-2.5 items-end">
			<div class="sm:col-span-2">
				<label for="rule-pat" class="block text-[11px] text-slate-400 mb-1">Match Pattern</label>
				<input
					id="rule-pat"
					type="text"
					required
					bind:value={matchPattern}
					placeholder="e.g., BLUE BOTTLE"
					class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
				/>
			</div>
			<div>
				<label for="rule-cat" class="block text-[11px] text-slate-400 mb-1">Category</label>
				<select
					id="rule-cat"
					bind:value={categoryId}
					class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white"
				>
					{#each categories as cat}
						<option value={cat.id}>{cat.name}</option>
					{/each}
				</select>
			</div>
			<div>
				<label for="rule-clean" class="block text-[11px] text-slate-400 mb-1">Clean Name (opt.)</label>
				<input
					id="rule-clean"
					type="text"
					bind:value={merchantOverride}
					placeholder="Blue Bottle"
					class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white"
				/>
			</div>
			<button
				type="submit"
				class="py-2 px-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs inline-flex items-center justify-center gap-1.5 cursor-pointer"
			>
				<Plus class="w-3.5 h-3.5" /> Add Rule
			</button>
		</form>

		{#if rules.length === 0}
			<p class="text-xs text-slate-500 py-3">No custom rules yet. Add patterns for merchants you want categorized deterministically.</p>
		{:else}
			<div class="divide-y divide-slate-800/70">
				{#each rules as r}
					<div class="py-2.5 flex items-center justify-between gap-4 text-xs">
						<div class="flex items-center gap-2.5 flex-wrap">
							<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono-num">{r.match_type}</span>
							<span class="font-medium text-white">"{r.match_pattern}"</span>
							<span class="text-slate-500">→</span>
							<span class="text-emerald-300 font-medium">{catMap.get(r.category_id)?.name ?? 'Category'}</span>
							{#if r.merchant_override}
								<span class="text-slate-400">(rename to "{r.merchant_override}")</span>
							{/if}
						</div>
						<button
							type="button"
							onclick={() => removeRule(r.id)}
							class="p-1 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
						>
							<Trash2 class="w-3.5 h-3.5" />
						</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- System & AI Stack Health -->
	{#if statusInfo}
		<div class="card-surface rounded-2xl p-6 space-y-4">
			<h2 class="text-base font-semibold text-white">AI & Infrastructure Status</h2>
			<div class="grid sm:grid-cols-3 gap-4 text-xs">
				<div class="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1">
					<div class="flex items-center gap-2 text-slate-400"><Database class="w-4 h-4 text-emerald-400" /> Database & Vector</div>
					<div class="font-semibold text-white">DB: {statusInfo.database}</div>
					<div class="{statusInfo.upstash_vector_connected ? 'text-emerald-400' : 'text-amber-400'}">
						Upstash Vector: {statusInfo.upstash_vector_connected ? 'Connected' : 'Not configured (.env)'}
					</div>
				</div>
				<div class="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1">
					<div class="flex items-center gap-2 text-slate-400"><Cpu class="w-4 h-4 text-cyan-400" /> LangChain LLM</div>
					<div class="font-semibold text-white">{statusInfo.llm_provider} ({statusInfo.llm_model_fast})</div>
					<div class="{statusInfo.llm_configured ? 'text-emerald-400' : 'text-amber-400'}">
						API Key: {statusInfo.llm_configured ? 'Configured' : 'Heuristic fallback active'}
					</div>
				</div>
				<div class="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1">
					<div class="flex items-center gap-2 text-slate-400"><Activity class="w-4 h-4 text-violet-400" /> LangSmith & Guardrails</div>
					<div class="font-semibold text-white">Project: {statusInfo.langsmith_project}</div>
					<div class="{statusInfo.langsmith_tracing ? 'text-emerald-400' : 'text-slate-400'}">
						Tracing: {statusInfo.langsmith_tracing ? 'Active (PII Redacted)' : 'Disabled (.env)'}
					</div>
				</div>
			</div>
		</div>
	{/if}

	<!-- Data Export & Backup -->
	<div class="card-surface rounded-2xl p-6 space-y-4">
		<div>
			<h2 class="text-base font-semibold text-white">Data Portability & Backups</h2>
			<p class="text-xs text-slate-400 mt-0.5">Export your entire financial ledger or download a portable JSON archive anytime.</p>
		</div>
		<div class="flex flex-wrap gap-3">
			<button
				type="button"
				onclick={handleExportCsv}
				class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-white cursor-pointer"
			>
				<Download class="w-4 h-4 text-emerald-400" /> Download Transactions (CSV)
			</button>
			<button
				type="button"
				onclick={handleExportJson}
				class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-white cursor-pointer"
			>
				<Download class="w-4 h-4 text-cyan-400" /> Download Full Backup (JSON)
			</button>
		</div>
	</div>

	<!-- Security Audit Log -->
	<div class="card-surface rounded-2xl p-6 space-y-3">
		<div class="flex items-center gap-2">
			<History class="w-4 h-4 text-slate-400" />
			<h2 class="text-base font-semibold text-white">Security & Data Audit Log</h2>
		</div>
		{#if auditLogs.length === 0}
			<p class="text-xs text-slate-500">No sensitive activity logged yet. Exports and security actions appear here.</p>
		{:else}
			<div class="divide-y divide-slate-800/70 text-xs">
				{#each auditLogs.slice(0, 12) as log}
					<div class="py-2 flex items-center justify-between gap-4">
						<div class="flex items-center gap-2.5">
							<span class="px-2 py-0.5 rounded bg-slate-800 text-emerald-300 font-mono-num">{log.action}</span>
							<span class="text-slate-300">{log.resource_type}</span>
						</div>
						<span class="text-slate-500 font-mono-num">{formatDate(log.created_at)}</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Danger Zone -->
	<form onsubmit={handleDeleteAccount} class="rounded-2xl p-6 space-y-4 bg-rose-950/20 border border-rose-500/30">
		<div class="flex items-center gap-2 text-rose-300">
			<ShieldAlert class="w-5 h-5" />
			<h2 class="text-base font-semibold">Danger Zone — Permanent Account Deletion</h2>
		</div>
		<p class="text-xs text-slate-400">
			Permanently deletes your account, cascades all Neon Postgres records (accounts, transactions, budgets, goals, chats), and purges all 3 Upstash Vector namespaces. This cannot be undone.
		</p>
		<div class="grid sm:grid-cols-2 gap-3">
			<input
				type="password"
				required
				bind:value={deletePassword}
				placeholder="Confirm your password"
				class="px-3.5 py-2 rounded-xl bg-slate-950 border border-rose-500/30 text-xs text-white"
			/>
			<input
				type="text"
				required
				bind:value={deletePhrase}
				placeholder='Type "DELETE MY ACCOUNT"'
				class="px-3.5 py-2 rounded-xl bg-slate-950 border border-rose-500/30 text-xs text-white"
			/>
		</div>
		<button
			type="submit"
			disabled={deletingAccount}
			class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs cursor-pointer disabled:opacity-50"
		>
			{deletingAccount ? 'Deleting...' : 'Permanently Delete My Account & Vector Memory'}
		</button>
	</form>
</div>
