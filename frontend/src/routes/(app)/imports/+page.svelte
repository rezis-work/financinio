<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
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
		ShieldCheck,
		Landmark,
		FileText,
		Trash2,
		X
	} from 'lucide-svelte';

	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let batches = $state<ImportBatch[]>([]);
	let activeBatch = $state<ImportBatchDetail | null>(null);
	let editedRows = $state<Record<string, { user_approved: boolean; merchant_clean: string; category_id: string }>>({});

	let importMode = $state<'general' | 'bog'>('bog');
	let selectedAccountId = $state('');
	let uploading = $state(false);
	let committing = $state(false);
	let confirmDeleteBatch = $state<ImportBatch | null>(null);
	let deleteLedgerTxs = $state(true);
	let deletingBatch = $state(false);
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
			const paramAccId = page.url.searchParams.get('account');
			if (paramAccId && accs.some((a) => a.id === paramAccId)) {
				selectedAccountId = paramAccId;
			} else if (!selectedAccountId && accs.length > 0) {
				const gelOrBog = accs.find(
					(a) =>
						a.currency.toUpperCase() === 'GEL' ||
						a.name.toLowerCase().includes('bog') ||
						(a.institution || '').toLowerCase().includes('georgia')
				);
				selectedAccountId = (gelOrBog ?? accs[0]).id;
			}
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
			const detail =
				importMode === 'bog'
					? await api.uploadBogStatement(selectedAccountId, file)
					: await api.uploadDocument(selectedAccountId, file);
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

	function openDeleteConfirm(batch: ImportBatch) {
		confirmDeleteBatch = batch;
		deleteLedgerTxs = true;
	}

	async function handleConfirmDelete() {
		if (!confirmDeleteBatch || deletingBatch) return;
		const target = confirmDeleteBatch;
		deletingBatch = true;
		error = null;
		successMsg = null;
		try {
			const res = await api.deleteImportBatch(target.id, deleteLedgerTxs);
			confirmDeleteBatch = null;
			const [accs, list] = await Promise.all([api.listAccounts(), api.listImportBatches()]);
			accounts = accs;
			batches = list;
			if (activeBatch?.id === target.id) {
				if (list.length > 0) {
					await selectBatch(list[0].id);
				} else {
					activeBatch = null;
					editedRows = {};
				}
			}
			const acc = accs.find((a) => a.id === res.recalculated_account_id);
			if (res.deleted_transactions > 0) {
				const balSuffix =
					res.new_account_balance !== null && acc
						? ` Account balance recalculated to ${formatMoney(res.new_account_balance, acc.currency)}.`
						: '';
				successMsg = `Removed "${target.filename}" and deleted ${res.deleted_transactions} imported transactions from your ledger.${balSuffix}`;
			} else {
				successMsg = `Removed import "${target.filename}".`;
			}
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to delete import batch';
		} finally {
			deletingBatch = false;
		}
	}

	function sourceBadgeClass(source: string): string {
		if (source === 'rule') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
		if (source === 'bog_mcc' || source === 'bog_rule')
			return 'bg-orange-500/15 text-orange-300 border-orange-500/30';
		if (source === 'vector') return 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30';
		if (source === 'llm') return 'bg-violet-500/15 text-violet-300 border-violet-500/30';
		return 'bg-slate-800 text-slate-300 border-slate-700';
	}

	function docTypeLabel(docType: string): string {
		if (docType === 'bog_pdf') return 'BOG PDF';
		if (docType === 'pdf_statement') return 'PDF';
		return docType.toUpperCase();
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
	<div class="card-surface rounded-2xl p-6 space-y-5">
		<!-- Source Switcher: Dedicated Bank of Georgia (BOG) vs General Import -->
		<div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
			<div class="inline-flex p-1 rounded-xl bg-slate-950/90 border border-slate-800 w-fit">
				<button
					type="button"
					onclick={() => {
						importMode = 'bog';
						error = null;
					}}
					class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition cursor-pointer {importMode === 'bog'
						? 'bg-orange-500/20 text-orange-300 border border-orange-500/35'
						: 'text-slate-400 hover:text-white border border-transparent'}"
				>
					<Landmark class="w-3.5 h-3.5" />
					Bank of Georgia (BOG)
					<span class="px-1.5 py-0.5 rounded bg-orange-500/20 text-[10px] font-mono-num">GE PDF</span>
				</button>
				<button
					type="button"
					onclick={() => {
						importMode = 'general';
						error = null;
					}}
					class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition cursor-pointer {importMode === 'general'
						? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
						: 'text-slate-400 hover:text-white border border-transparent'}"
				>
					<FileText class="w-3.5 h-3.5" />
					General Statement / Receipt
				</button>
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

		{#if importMode === 'bog'}
			<div class="p-3.5 rounded-xl bg-orange-500/8 border border-orange-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
				<div class="space-y-0.5">
					<div class="font-semibold text-orange-200">
						საქართველოს ბანკი · Dedicated Bank of Georgia PDF Importer
					</div>
					<p class="text-slate-400">
						Upload your Internet Bank PDF export (<span class="text-slate-200">ანგარიშიდან ამონაწერი</span>). Deterministically parses Georgian text, multi-currency balances (<span class="font-mono-num text-slate-200">GEL / USD / EUR / GBP</span>), merchants, and ISO MCC codes with zero AI token cost.
					</p>
				</div>
				<span class="shrink-0 px-2.5 py-1 rounded-full bg-orange-500/15 border border-orange-500/30 text-orange-300 text-[10px] font-semibold uppercase tracking-wide w-fit">
					0 AI Tokens · Verified Math
				</span>
			</div>
		{:else}
			<div>
				<h2 class="text-sm font-semibold text-white">Upload General Financial Document</h2>
				<p class="text-xs text-slate-400">Supports CSV, Excel (.xlsx), any bank PDF statement, and receipt photos (PNG/JPG).</p>
			</div>
		{/if}

		<label
			ondragover={(e) => { e.preventDefault(); dragOver = true; }}
			ondragleave={() => (dragOver = false)}
			ondrop={onDrop}
			class="block border-2 border-dashed rounded-2xl p-8 text-center transition cursor-pointer {dragOver
				? importMode === 'bog'
					? 'border-orange-400 bg-orange-500/10'
					: 'border-emerald-400 bg-emerald-500/10'
				: importMode === 'bog'
					? 'border-orange-500/35 hover:border-orange-400/70 bg-slate-950/60'
					: 'border-slate-700/80 hover:border-slate-500 bg-slate-950/50'}"
		>
			<input
				type="file"
				accept={importMode === 'bog' ? '.pdf,application/pdf' : '.csv,.xlsx,.xls,.pdf,image/*'}
				class="hidden"
				disabled={uploading}
				onchange={(e) => {
					const input = e.currentTarget as HTMLInputElement;
					handleFileUpload(input.files?.[0]);
					input.value = '';
				}}
			/>
			<UploadCloud class="w-10 h-10 mx-auto mb-3 {importMode === 'bog' ? 'text-orange-400' : 'text-emerald-400'}" />
			<div class="text-sm font-semibold text-white">
				{#if uploading}
					{importMode === 'bog'
						? 'Parsing Bank of Georgia Georgian PDF & reconciling balances...'
						: 'Running LangGraph extraction & categorization pipeline...'}
				{:else if importMode === 'bog'}
					Drop your Bank of Georgia PDF (ანგარიშიდან ამონაწერი) here, or click to browse
				{:else}
					Drop statement or receipt here, or click to browse
				{/if}
			</div>
			<p class="text-xs text-slate-400 mt-1">
				{importMode === 'bog'
					? 'Auto-extracts ობიექტი, MCC codes, transfers, commissions, and reconciles opening & closing balances.'
					: 'Files are deduplicated, categorized via Rules → Upstash Vector → LLM, and paused for your approval.'}
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
						<div
							class="group relative flex items-stretch rounded-xl border transition {activeBatch?.id === b.id
								? 'bg-emerald-500/10 border-emerald-500/35'
								: 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'}"
						>
							<button
								type="button"
								onclick={() => selectBatch(b.id)}
								class="flex-1 min-w-0 text-left p-3 cursor-pointer"
							>
								<div class="flex items-center justify-between gap-2">
									<span class="text-xs font-medium text-white truncate">{b.filename}</span>
									<span
										class="text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase shrink-0 {b.status === 'committed'
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
							<button
								type="button"
								onclick={() => openDeleteConfirm(b)}
								title={b.status === 'committed' ? 'Remove import & imported transactions' : 'Discard import'}
								aria-label="Delete import batch"
								class="px-2.5 flex items-center justify-center text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-r-xl transition cursor-pointer border-l border-slate-800/60"
							>
								<Trash2 class="w-3.5 h-3.5" />
							</button>
						</div>
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
							<span
								class="text-[11px] px-2 py-0.5 rounded-full uppercase font-semibold {activeBatch.doc_type === 'bog_pdf'
									? 'bg-orange-500/15 text-orange-300 border border-orange-500/30'
									: 'bg-slate-800 text-slate-300'}"
							>
								{docTypeLabel(activeBatch.doc_type)}
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

					<div class="flex flex-wrap items-center gap-2 shrink-0">
						{#if activeBatch.status === 'needs_review'}
							<button
								type="button"
								disabled={committing}
								onclick={handleCommit}
								class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer disabled:opacity-50"
							>
								<CheckCircle2 class="w-4 h-4" />
								{committing ? 'Committing...' : 'Approve & Commit to Ledger'}
							</button>
						{:else if activeBatch.status === 'committed'}
							<span class="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-300 bg-emerald-500/15 px-3 py-1.5 rounded-xl border border-emerald-500/30">
								<CheckCircle2 class="w-4 h-4" /> Committed ({activeBatch.committed_rows} rows)
							</span>
						{/if}
						<button
							type="button"
							onclick={() => activeBatch && openDeleteConfirm(activeBatch)}
							class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-semibold transition cursor-pointer"
						>
							<Trash2 class="w-3.5 h-3.5" />
							{activeBatch.status === 'committed' ? 'Remove Imported Ledger' : 'Discard Import'}
						</button>
					</div>
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
										<div class="text-[10px] text-slate-500 truncate max-w-[280px] mt-0.5" title={row.description || row.merchant_raw}>
											{row.description || row.merchant_raw}
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

<!-- Confirm Delete Imported Batch Modal -->
{#if confirmDeleteBatch}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-rose-500/30">
			<div class="flex items-start justify-between gap-3">
				<div class="flex items-center gap-2.5">
					<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
						<Trash2 class="w-5 h-5" />
					</div>
					<div>
						<h2 class="text-base font-semibold text-white">
							{confirmDeleteBatch.status === 'committed'
								? 'Remove Imported Ledger?'
								: 'Discard Import Batch?'}
						</h2>
						<p class="text-xs text-slate-400 truncate max-w-[260px]">
							{confirmDeleteBatch.filename}
						</p>
					</div>
				</div>
				<button
					type="button"
					disabled={deletingBatch}
					onclick={() => (confirmDeleteBatch = null)}
					class="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			{#if confirmDeleteBatch.status === 'committed'}
				<div class="space-y-3 text-xs text-slate-300 leading-relaxed">
					<p>
						This import added <strong class="text-white">{confirmDeleteBatch.committed_rows} transactions</strong> to your ledger. Removing it will also delete its uploaded file and AI search index.
					</p>
					<label class="flex items-start gap-2.5 p-3 rounded-xl bg-rose-500/8 border border-rose-500/25 cursor-pointer">
						<input
							type="checkbox"
							bind:checked={deleteLedgerTxs}
							class="mt-0.5 rounded border-slate-700"
						/>
						<span class="text-rose-200">
							Also delete all <strong>{confirmDeleteBatch.committed_rows}</strong> imported transactions from my ledger and automatically recalculate the account balance.
						</span>
					</label>
				</div>
			{:else}
				<p class="text-xs text-slate-300 leading-relaxed">
					This will discard the pending import batch (<strong class="text-white">{confirmDeleteBatch.total_rows} staged rows</strong>) and remove the uploaded document. No committed ledger transactions exist for this batch.
				</p>
			{/if}

			<div class="flex items-center justify-end gap-2.5 pt-1">
				<button
					type="button"
					disabled={deletingBatch}
					onclick={() => (confirmDeleteBatch = null)}
					class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer disabled:opacity-50"
				>
					Cancel
				</button>
				<button
					type="button"
					disabled={deletingBatch}
					onclick={handleConfirmDelete}
					class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					<Trash2 class="w-3.5 h-3.5" />
					{#if deletingBatch}
						Removing...
					{:else if confirmDeleteBatch.status === 'committed' && deleteLedgerTxs}
						Remove Import & {confirmDeleteBatch.committed_rows} Transactions
					{:else}
						Delete Import
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
