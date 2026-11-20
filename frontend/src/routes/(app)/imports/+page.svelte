<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type {
		Account,
		Category,
		ImportBatch,
		ImportBatchDetail,
		StagedTransaction
	} from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import {
		UploadCloud,
		FileSpreadsheet,
		CheckCircle2,
		AlertTriangle,
		Sparkles,
		Brain,
		ShieldCheck
	} from 'lucide-svelte';

	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let batches = $state<ImportBatch[]>([]);
	let activeBatch = $state<ImportBatchDetail | null>(null);
	let editedRows = $state<Record<string, { user_approved: boolean; merchant_clean: string; category_id: string }>>({});

	let selectedAccountId = $state('');
	let uploading = $state(false);
	let committing = $state(false);
	let skipDuplicates = $state(true);
	let learnFromEdits = $state(true);
	let dragOver = $state(false);
	let error = $state<string | null>(null);
	let successMsg = $state<string | null>(null);

	async function loadInitial() {
		try {
			const [accs, cats, list] = await Promise.all([
				api.listAccounts(),
				api.listCategories(),
				api.listImportBatches()
			]);
			accounts = accs;
			categories = cats;
			batches = list;
			if (!selectedAccountId && accs.length > 0) selectedAccountId = accs[0].id;
			const pending = list.find((b) => b.status === 'needs_review');
			if (pending) {
				await selectBatch(pending.id);
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load imports';
		}
	}

	onMount(loadInitial);

	function hydrateEditedRows(detail: ImportBatchDetail) {
		const map: Record<string, { user_approved: boolean; merchant_clean: string; category_id: string }> = {};
		for (const s of detail.staged_transactions) {
			map[s.id] = {
				user_approved: s.user_approved,
				merchant_clean: s.merchant_clean,
				category_id: s.suggested_category_id ?? ''
			};
		}
		editedRows = map;
	}

	async function selectBatch(batchId: string) {
		error = null;
		successMsg = null;
		const detail = await api.getImportBatch(batchId);
		activeBatch = detail;
		hydrateEditedRows(detail);
	}

	async function handleFileUpload(file: File | undefined) {
		if (!file) return;
		if (!selectedAccountId) {
			error = 'Please create an account first on the Accounts page before importing.';
			return;
		}
		uploading = true;
		error = null;
		successMsg = null;
		try {
			const detail = await api.uploadDocument(selectedAccountId, file);
			activeBatch = detail;
			hydrateEditedRows(detail);
			batches = await api.listImportBatches();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Upload or AI parsing failed';
		} finally {
			uploading = false;
		}
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		const file = e.dataTransfer?.files?.[0];
		handleFileUpload(file);
	}

	async function handleCommit() {
		if (!activeBatch) return;
		committing = true;
		error = null;
		successMsg = null;
		try {
			const decisions = activeBatch.staged_transactions.map((s: StagedTransaction) => {
				const ed = editedRows[s.id];
				return {
					staged_id: s.id,
					user_approved: ed ? ed.user_approved : s.user_approved,
					merchant_clean: ed ? ed.merchant_clean : s.merchant_clean,
					category_id: ed?.category_id ? ed.category_id : null
				};
			});
			const committed = await api.commitImportBatch(activeBatch.id, {
				decisions,
				skip_duplicates: skipDuplicates,
				learn_from_edits: learnFromEdits
			});
			activeBatch = committed;
			batches = await api.listImportBatches();
			successMsg = `Committed ${committed.committed_rows} transactions to your ledger and updated AI merchant memory!`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Commit failed';
		} finally {
			committing = false;
		}
	}

	function sourceBadgeClass(source: string): string {
		if (source === 'rule') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
		if (source === 'vector') return 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30';
		if (source === 'llm') return 'bg-violet-500/15 text-violet-300 border-violet-500/30';
		return 'bg-slate-800 text-slate-300 border-slate-700';
	}
</script>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-bold tracking-tight text-white">AI Statement & Receipt Imports</h1>
		<p class="text-sm text-slate-400 mt-0.5">
			Powered by <span class="text-emerald-400 font-medium">LangGraph</span> HITL Review, <span class="text-cyan-400 font-medium">Upstash Vector</span> self-learning memory, and <span class="text-violet-400 font-medium">LangSmith</span> tracing.
		</p>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
	{/if}
	{#if successMsg}
		<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
			<CheckCircle2 class="w-4 h-4 shrink-0" />
			{successMsg}
		</div>
	{/if}

	<!-- Upload Card -->
	<div class="card-surface rounded-2xl p-6 space-y-4">
		<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
			<div>
				<h2 class="text-base font-semibold text-white">Upload Financial Document</h2>
				<p class="text-xs text-slate-400">Supports CSV, Excel (.xlsx), PDF bank statements, and receipt photos (PNG/JPG).</p>
			</div>
			<div class="flex items-center gap-2">
				<label for="target-acc" class="text-xs text-slate-400">Target Account:</label>
				<select
					id="target-acc"
					bind:value={selectedAccountId}
					class="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
				>
					{#if accounts.length === 0}
						<option value="">No accounts — create one first</option>
					{:else}
						{#each accounts as acc}
							<option value={acc.id}>{acc.name} ({acc.currency})</option>
						{/each}
					{/if}
				</select>
			</div>
		</div>

		<label
			ondragover={(e) => { e.preventDefault(); dragOver = true; }}
			ondragleave={() => (dragOver = false)}
			ondrop={onDrop}
			class="block border-2 border-dashed rounded-2xl p-8 text-center transition cursor-pointer {dragOver
				? 'border-emerald-400 bg-emerald-500/10'
				: 'border-slate-700/80 hover:border-slate-500 bg-slate-950/50'}"
		>
			<input
				type="file"
				accept=".csv,.xlsx,.xls,.pdf,image/*"
				class="hidden"
				disabled={uploading}
				onchange={(e) => handleFileUpload((e.currentTarget as HTMLInputElement).files?.[0])}
			/>
			<UploadCloud class="w-10 h-10 text-emerald-400 mx-auto mb-3" />
			<div class="text-sm font-semibold text-white">
				{uploading ? 'Running LangGraph extraction & categorization pipeline...' : 'Drop statement or receipt here, or click to browse'}
			</div>
			<p class="text-xs text-slate-400 mt-1">
				Files are deduplicated, categorized via Rules → Upstash Vector → LLM, and paused for your approval.
			</p>
		</label>
	</div>

	<div class="grid lg:grid-cols-4 gap-6">
		<!-- Recent Batches -->
		<div class="card-surface rounded-2xl p-4 space-y-3 h-fit">
			<h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 px-1">Recent Imports</h3>
			{#if batches.length === 0}
				<p class="text-xs text-slate-500 px-1 py-4">No imports yet.</p>
			{:else}
				<div class="space-y-1.5">
					{#each batches as b}
						<button
							type="button"
							onclick={() => selectBatch(b.id)}
							class="w-full text-left p-3 rounded-xl border transition cursor-pointer {activeBatch?.id === b.id
								? 'bg-emerald-500/10 border-emerald-500/35'
								: 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'}"
						>
							<div class="flex items-center justify-between gap-2">
								<span class="text-xs font-medium text-white truncate">{b.filename}</span>
								<span
									class="text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase {b.status === 'committed'
										? 'bg-emerald-500/15 text-emerald-300'
										: b.status === 'needs_review'
											? 'bg-amber-500/15 text-amber-300'
											: 'bg-rose-500/15 text-rose-300'}"
								>
									{b.status.replace('_', ' ')}
								</span>
							</div>
							<div class="text-[11px] text-slate-400 mt-1 flex items-center gap-2">
								<FileSpreadsheet class="w-3 h-3" />
								<span>{b.total_rows} rows</span>
								{#if b.duplicate_rows > 0}
									<span class="text-amber-400">· {b.duplicate_rows} dup</span>
								{/if}
							</div>
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- HITL Review Queue -->
		<div class="lg:col-span-3 card-surface rounded-2xl overflow-hidden">
			{#if !activeBatch}
				<div class="p-12 text-center space-y-2">
					<Sparkles class="w-8 h-8 text-slate-500 mx-auto" />
					<div class="text-sm font-medium text-slate-300">Select an import batch or upload a new file</div>
					<p class="text-xs text-slate-500">Every AI-parsed row appears here for one-click review before touching your Neon ledger.</p>
				</div>
			{:else}
				<div class="p-5 border-b border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
					<div>
						<div class="flex items-center gap-2.5">
							<h2 class="text-base font-semibold text-white">{activeBatch.filename}</h2>
							<span class="text-[11px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 uppercase">
								{activeBatch.doc_type}
							</span>
						</div>
						{#if activeBatch.reconciliation_note}
							<p class="text-xs mt-1 flex items-center gap-1.5 {activeBatch.balance_reconciled === false ? 'text-amber-300' : 'text-slate-400'}">
								{#if activeBatch.balance_reconciled === false}
									<AlertTriangle class="w-3.5 h-3.5 shrink-0" />
								{:else}
									<ShieldCheck class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
								{/if}
								{activeBatch.reconciliation_note}
							</p>
						{/if}
					</div>

					{#if activeBatch.status === 'needs_review'}
						<button
							type="button"
							disabled={committing}
							onclick={handleCommit}
							class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer disabled:opacity-50 shrink-0"
						>
							<CheckCircle2 class="w-4 h-4" />
							{committing ? 'Committing...' : 'Approve & Commit to Ledger'}
						</button>
					{:else if activeBatch.status === 'committed'}
						<span class="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-300 bg-emerald-500/15 px-3 py-1.5 rounded-xl border border-emerald-500/30">
							<CheckCircle2 class="w-4 h-4" /> Committed ({activeBatch.committed_rows} rows)
						</span>
					{/if}
				</div>

				{#if activeBatch.status === 'needs_review'}
					<div class="px-5 py-3 bg-slate-900/60 border-b border-slate-800/80 flex flex-wrap items-center gap-5 text-xs text-slate-300">
						<label class="flex items-center gap-2 cursor-pointer">
							<input type="checkbox" bind:checked={skipDuplicates} />
							Skip detected duplicates ({activeBatch.duplicate_rows})
						</label>
						<label class="flex items-center gap-2 cursor-pointer">
							<input type="checkbox" bind:checked={learnFromEdits} />
							<Brain class="w-3.5 h-3.5 text-cyan-400" />
							Save confirmations to Upstash Vector memory
						</label>
					</div>
				{/if}

				<div class="overflow-x-auto">
					<table class="w-full text-left border-collapse text-sm">
						<thead>
							<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400">
								<th class="py-3 px-4 w-10">Use</th>
								<th class="py-3 px-3">Date</th>
								<th class="py-3 px-3">Merchant</th>
								<th class="py-3 px-3">Category</th>
								<th class="py-3 px-3">AI Source</th>
								<th class="py-3 px-4 text-right">Amount</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-slate-800/60">
							{#each activeBatch.staged_transactions as row}
								{@const ed = editedRows[row.id]}
								<tr class="{row.is_duplicate ? 'opacity-55 bg-amber-500/5' : 'hover:bg-slate-900/40'}">
									<td class="py-2.5 px-4">
										{#if ed}
											<input
												type="checkbox"
												disabled={activeBatch.status === 'committed'}
												bind:checked={ed.user_approved}
												class="rounded border-slate-700"
											/>
										{/if}
									</td>
									<td class="py-2.5 px-3 text-xs font-mono-num text-slate-400 whitespace-nowrap">
										{formatDate(row.occurred_at)}
									</td>
									<td class="py-2.5 px-3 min-w-[200px]">
										{#if ed && activeBatch.status === 'needs_review'}
											<input
												type="text"
												bind:value={ed.merchant_clean}
												class="w-full px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
											/>
										{:else}
											<div class="text-xs font-medium text-white">{row.merchant_clean}</div>
										{/if}
										<div class="text-[10px] text-slate-500 truncate max-w-[240px] mt-0.5">
											{row.merchant_raw}
											{#if row.is_duplicate}
												<span class="ml-1.5 text-amber-400 font-semibold">DUPLICATE</span>
											{/if}
										</div>
									</td>
									<td class="py-2.5 px-3">
										{#if ed && activeBatch.status === 'needs_review'}
											<select
												bind:value={ed.category_id}
												class="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
											>
												<option value="">Uncategorized</option>
												{#each categories as cat}
													<option value={cat.id}>{cat.name}</option>
												{/each}
											</select>
										{:else}
											<span class="text-xs text-slate-300">
												{categories.find((c) => c.id === row.suggested_category_id)?.name ?? 'Uncategorized'}
											</span>
										{/if}
									</td>
									<td class="py-2.5 px-3 whitespace-nowrap">
										<span class="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border uppercase {sourceBadgeClass(row.categorization_source)}">
											{row.categorization_source} · {Math.round(Number.parseFloat(row.confidence) * 100)}%
										</span>
									</td>
									<td
										class="py-2.5 px-4 text-right font-mono-num text-xs font-semibold whitespace-nowrap {row.direction === 'inflow'
											? 'text-emerald-400'
											: 'text-slate-100'}"
									>
										{row.direction === 'inflow' ? '+' : '-'}{formatMoney(row.amount, row.currency)}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	</div>
</div>
