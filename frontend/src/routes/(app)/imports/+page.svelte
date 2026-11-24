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
	import StagedRowDrawer, {
		type StagedRowEdit
	} from '$lib/components/imports/StagedRowDrawer.svelte';
	import UploadProgressOverlay from '$lib/components/imports/UploadProgressOverlay.svelte';
	import FinancinioLoader from '$lib/components/FinancinioLoader.svelte';
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
		X,
		Eye,
		EyeOff,
		Search,
		SlidersHorizontal,
		Wand2,
		ArrowRight,
		ArrowUpRight,
		ArrowDownRight,
		ChevronDown,
		ChevronUp,
		Plus,
		Check,
		Layers,
		Receipt,
		Clock,
		RotateCcw,
		Wallet
	} from 'lucide-svelte';

	type RowFilter = 'all' | 'attention' | 'uncategorized' | 'duplicates' | 'approved' | 'skipped';
	type BatchFilter = 'all' | 'needs_review' | 'committed';

	let loading = $state(true);
	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let batches = $state<ImportBatch[]>([]);
	let activeBatch = $state<ImportBatchDetail | null>(null);
	let editedRows = $state<Record<string, StagedRowEdit>>({});

	// Upload studio state
	let importMode = $state<'general' | 'bog'>('bog');
	let selectedAccountId = $state('');
	let uploadStudioOpen = $state(true);
	let uploading = $state(false);
	let uploadingFilename = $state('');
	let dragOver = $state(false);

	// Commit & delete state
	let committing = $state(false);
	let justCommittedCount = $state<number | null>(null);
	let confirmDeleteBatch = $state<ImportBatch | null>(null);
	let deleteLedgerTxs = $state(true);
	let deletingBatch = $state(false);
	let skipDuplicates = $state(true);
	let learnFromEdits = $state(true);

	// Review filters & UX state
	let rowSearch = $state('');
	let rowFilter = $state<RowFilter>('all');
	let batchFilter = $state<BatchFilter>('all');
	let bulkCategoryId = $state('');
	let inspectingRowId = $state<string | null>(null);
	let propagateSuggestion = $state<{
		merchantKey: string;
		merchantLabel: string;
		categoryId: string;
		categoryName: string;
		otherIds: string[];
	} | null>(null);

	// Feedback & Privacy Mode
	let error = $state<string | null>(null);
	let successMsg = $state<string | null>(null);
	let privacyMode = $state(false);

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('financinio_privacy_mode', privacyMode ? '1' : '0');
		}
	}

	function normalizeMerchantKey(raw: string): string {
		return raw.trim().toLowerCase().replace(/\s+/g, ' ');
	}

	function hydrateEditedRows(detail: ImportBatchDetail) {
		const map: Record<string, StagedRowEdit> = {};
		for (const s of detail.staged_transactions) {
			map[s.id] = {
				user_approved: s.user_approved,
				merchant_clean: s.merchant_clean,
				category_id: s.suggested_category_id ?? '',
				direction: s.direction,
				amount: Number.parseFloat(s.amount).toFixed(2),
				occurred_at: s.occurred_at,
				description: s.description ?? ''
			};
		}
		editedRows = map;
		propagateSuggestion = null;
		rowSearch = '';
		rowFilter = 'all';
		bulkCategoryId = '';
	}

	async function loadInitial() {
		loading = true;
		try {
			if (typeof localStorage !== 'undefined') {
				privacyMode = localStorage.getItem('financinio_privacy_mode') === '1';
			}
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
				await selectBatch(pending.id, false);
				uploadStudioOpen = false;
			} else if (list.length > 0) {
				await selectBatch(list[0].id, false);
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load imports';
		} finally {
			loading = false;
		}
	}

	onMount(loadInitial);

	async function selectBatch(batchId: string, clearMessages = true) {
		if (clearMessages) {
			error = null;
			successMsg = null;
			justCommittedCount = null;
		}
		try {
			const detail = await api.getImportBatch(batchId);
			activeBatch = detail;
			hydrateEditedRows(detail);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load import batch';
		}
	}

	async function handleFileUpload(file: File | undefined) {
		if (!file) return;
		if (!selectedAccountId) {
			error = 'Please create an account first on the Accounts page before importing.';
			return;
		}
		uploading = true;
		uploadingFilename = file.name;
		error = null;
		successMsg = null;
		justCommittedCount = null;
		try {
			const detail =
				importMode === 'bog'
					? await api.uploadBogStatement(selectedAccountId, file)
					: await api.uploadDocument(selectedAccountId, file);
			activeBatch = detail;
			hydrateEditedRows(detail);
			batches = await api.listImportBatches();
			uploadStudioOpen = false;
			successMsg = `Extracted ${detail.total_rows} transactions from "${file.name}" — review below before committing to your ledger.`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Upload or AI parsing failed';
		} finally {
			uploading = false;
			uploadingFilename = '';
		}
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		const file = e.dataTransfer?.files?.[0];
		handleFileUpload(file);
	}

	function handleCategoryChange(row: StagedTransaction, newCatId: string) {
		if (!activeBatch) return;
		const key = normalizeMerchantKey(row.merchant_raw);
		const cleanKey = normalizeMerchantKey(editedRows[row.id]?.merchant_clean || row.merchant_clean);
		const otherIds = activeBatch.staged_transactions
			.filter((other) => {
				if (other.id === row.id) return false;
				const otherEd = editedRows[other.id];
				if (!otherEd) return false;
				if (otherEd.category_id === newCatId) return false;
				return (
					normalizeMerchantKey(other.merchant_raw) === key ||
					normalizeMerchantKey(otherEd.merchant_clean) === cleanKey
				);
			})
			.map((r) => r.id);

		if (otherIds.length > 0) {
			const catName = categories.find((c) => c.id === newCatId)?.name ?? 'Uncategorized';
			propagateSuggestion = {
				merchantKey: key,
				merchantLabel: editedRows[row.id]?.merchant_clean || row.merchant_clean,
				categoryId: newCatId,
				categoryName: catName,
				otherIds
			};
		} else {
			propagateSuggestion = null;
		}
	}

	function applyPropagateSuggestion() {
		if (!propagateSuggestion) return;
		for (const id of propagateSuggestion.otherIds) {
			if (editedRows[id]) {
				editedRows[id].category_id = propagateSuggestion.categoryId;
			}
		}
		successMsg = `Applied "${propagateSuggestion.categoryName}" to ${propagateSuggestion.otherIds.length} matching "${propagateSuggestion.merchantLabel}" rows.`;
		propagateSuggestion = null;
	}

	function applyToMatchingMerchant(merchantRaw: string, merchantClean: string, categoryId: string) {
		if (!activeBatch) return;
		const key = normalizeMerchantKey(merchantRaw);
		let updated = 0;
		for (const s of activeBatch.staged_transactions) {
			if (normalizeMerchantKey(s.merchant_raw) === key && editedRows[s.id]) {
				editedRows[s.id].merchant_clean = merchantClean;
				editedRows[s.id].category_id = categoryId;
				updated += 1;
			}
		}
		const catName = categories.find((c) => c.id === categoryId)?.name ?? 'Uncategorized';
		successMsg = `Updated ${updated} matching rows to "${merchantClean}" · ${catName}.`;
		propagateSuggestion = null;
	}

	function approveVisible(approved: boolean) {
		for (const row of filteredRows) {
			if (editedRows[row.id]) {
				editedRows[row.id].user_approved = approved;
			}
		}
	}

	function approveHighConfidence() {
		if (!activeBatch) return;
		let count = 0;
		for (const row of activeBatch.staged_transactions) {
			const ed = editedRows[row.id];
			if (!ed) continue;
			const conf = Number.parseFloat(row.confidence || '0');
			if (!row.is_duplicate && conf >= 0.8) {
				ed.user_approved = true;
				count += 1;
			}
		}
		successMsg = `Approved ${count} high-confidence (≥80%) non-duplicate rows.`;
	}

	function skipAllDuplicates() {
		if (!activeBatch) return;
		let count = 0;
		for (const row of activeBatch.staged_transactions) {
			const ed = editedRows[row.id];
			if (ed && row.is_duplicate) {
				ed.user_approved = false;
				count += 1;
			}
		}
		successMsg = `Unchecked ${count} duplicate rows.`;
	}

	function applyBulkCategoryToVisible() {
		if (!bulkCategoryId) return;
		const targetCat = bulkCategoryId === '__clear__' ? '' : bulkCategoryId;
		let count = 0;
		for (const row of filteredRows) {
			if (editedRows[row.id]) {
				editedRows[row.id].category_id = targetCat;
				count += 1;
			}
		}
		const catName = targetCat
			? categories.find((c) => c.id === targetCat)?.name ?? 'Category'
			: 'Uncategorized';
		successMsg = `Assigned "${catName}" to ${count} visible rows.`;
		bulkCategoryId = '';
	}

	async function handleCommit() {
		if (!activeBatch) return;
		committing = true;
		error = null;
		successMsg = null;
		try {
			const decisions = activeBatch.staged_transactions.map((s: StagedTransaction) => {
				const ed = editedRows[s.id];
				const parsedAmt = ed ? Number.parseFloat(ed.amount) : Number.parseFloat(s.amount);
				return {
					staged_id: s.id,
					user_approved: ed ? ed.user_approved : s.user_approved,
					merchant_clean: ed ? ed.merchant_clean : s.merchant_clean,
					category_id: ed?.category_id ? ed.category_id : null,
					direction: ed ? ed.direction : s.direction,
					amount: Number.isFinite(parsedAmt) && parsedAmt > 0 ? parsedAmt.toFixed(2) : s.amount,
					occurred_at: ed?.occurred_at || s.occurred_at,
					description: ed ? ed.description : s.description
				};
			});
			const committed = await api.commitImportBatch(activeBatch.id, {
				decisions,
				skip_duplicates: skipDuplicates,
				learn_from_edits: learnFromEdits
			});
			activeBatch = committed;
			hydrateEditedRows(committed);
			const [accs, list] = await Promise.all([api.listAccounts(), api.listImportBatches()]);
			accounts = accs;
			batches = list;
			justCommittedCount = committed.committed_rows;
			successMsg = `Committed ${committed.committed_rows} transactions to your ledger${learnFromEdits ? ' and trained Upstash Vector AI memory' : ''}!`;
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
					await selectBatch(list[0].id, false);
				} else {
					activeBatch = null;
					editedRows = {};
					uploadStudioOpen = true;
				}
			}
			const acc = accs.find((a) => a.id === res.recalculated_account_id);
			if (res.deleted_transactions > 0) {
				const balSuffix =
					res.new_account_balance !== null && acc
						? ` Account balance recalculated to ${formatMoney(res.new_account_balance, acc.currency)}.`
						: '';
				successMsg = `Removed "${target.filename}" and rolled back ${res.deleted_transactions} imported transactions.${balSuffix}`;
			} else {
				successMsg = `Removed import "${target.filename}".`;
			}
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to delete import batch';
		} finally {
			deletingBatch = false;
		}
	}

	function sourceBadgeMeta(source: string): { label: string; cls: string } {
		if (source === 'rule')
			return { label: 'Rule', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' };
		if (source === 'bog_mcc')
			return { label: 'BOG MCC', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/30' };
		if (source === 'bog_rule')
			return { label: 'BOG Rule', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/30' };
		if (source === 'vector')
			return { label: 'Vector', cls: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30' };
		if (source === 'llm')
			return { label: 'AI', cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30' };
		return {
			label: source.toUpperCase(),
			cls: 'bg-slate-800 text-slate-300 border-slate-700'
		};
	}

	function docTypeLabel(docType: string): string {
		if (docType === 'bog_pdf') return 'BOG PDF';
		if (docType === 'pdf_statement') return 'PDF';
		if (docType === 'receipt') return 'RECEIPT';
		return docType.toUpperCase();
	}

	function accountById(id: string): Account | undefined {
		return accounts.find((a) => a.id === id);
	}

	function isRowEdited(row: StagedTransaction): boolean {
		const ed = editedRows[row.id];
		if (!ed) return false;
		return (
			ed.merchant_clean !== row.merchant_clean ||
			ed.category_id !== (row.suggested_category_id ?? '') ||
			ed.direction !== row.direction ||
			ed.occurred_at !== row.occurred_at ||
			Number.parseFloat(ed.amount) !== Number.parseFloat(row.amount) ||
			ed.description !== (row.description ?? '')
		);
	}

	// Derived metrics & filters
	let selectedAccount = $derived(accountById(selectedAccountId));
	let activeBatchAccount = $derived(activeBatch ? accountById(activeBatch.account_id) : undefined);

	let pendingBatchesCount = $derived(batches.filter((b) => b.status === 'needs_review').length);
	let totalCommittedRows = $derived(batches.reduce((s, b) => s + (b.committed_rows || 0), 0));
	let bogBatchesCount = $derived(batches.filter((b) => b.doc_type === 'bog_pdf').length);

	let filteredBatches = $derived.by(() => {
		if (batchFilter === 'all') return batches;
		return batches.filter((b) => b.status === batchFilter);
	});

	let activeStep = $derived.by(() => {
		if (uploading) return 1;
		if (!activeBatch) return 1;
		if (activeBatch.status === 'needs_review') return 2;
		if (activeBatch.status === 'committed') return 3;
		return 1;
	});

	let batchLiveStats = $derived.by(() => {
		if (!activeBatch) {
			return {
				total: 0,
				approved: 0,
				skipped: 0,
				duplicates: 0,
				uncategorizedApproved: 0,
				attentionCount: 0,
				uncategorizedTotal: 0,
				inflow: 0,
				outflow: 0,
				net: 0,
				currency: activeBatchAccount?.currency ?? 'GEL'
			};
		}
		let approved = 0;
		let skipped = 0;
		let duplicates = 0;
		let uncategorizedApproved = 0;
		let attentionCount = 0;
		let uncategorizedTotal = 0;
		let inflow = 0;
		let outflow = 0;
		const currency =
			activeBatch.staged_transactions[0]?.currency ?? activeBatchAccount?.currency ?? 'GEL';

		for (const row of activeBatch.staged_transactions) {
			const ed = editedRows[row.id];
			const isApproved = ed ? ed.user_approved : row.user_approved;
			const effectiveApproved =
				activeBatch.status === 'needs_review' && skipDuplicates && row.is_duplicate
					? false
					: isApproved;
			const catId = ed ? ed.category_id : (row.suggested_category_id ?? '');
			const dir = ed ? ed.direction : row.direction;
			const amt = Number.parseFloat(ed ? ed.amount : row.amount) || 0;
			const conf = Number.parseFloat(row.confidence || '0');

			if (row.is_duplicate) duplicates += 1;
			if (!catId) uncategorizedTotal += 1;
			if (!catId || conf < 0.75) attentionCount += 1;

			if (effectiveApproved) {
				approved += 1;
				if (!catId) uncategorizedApproved += 1;
				if (dir === 'inflow') inflow += amt;
				else outflow += amt;
			} else {
				skipped += 1;
			}
		}

		return {
			total: activeBatch.staged_transactions.length,
			approved,
			skipped,
			duplicates,
			uncategorizedApproved,
			attentionCount,
			uncategorizedTotal,
			inflow,
			outflow,
			net: inflow - outflow,
			currency
		};
	});

	let projectedAccountBalance = $derived.by(() => {
		if (!activeBatchAccount || !activeBatch || activeBatch.status !== 'needs_review') return null;
		const current = Number.parseFloat(activeBatchAccount.current_balance) || 0;
		return current + batchLiveStats.net;
	});

	let filteredRows = $derived.by(() => {
		if (!activeBatch) return [];
		const q = rowSearch.trim().toLowerCase();
		return activeBatch.staged_transactions.filter((row) => {
			const ed = editedRows[row.id];
			const isApproved = ed ? ed.user_approved : row.user_approved;
			const catId = ed ? ed.category_id : (row.suggested_category_id ?? '');
			const conf = Number.parseFloat(row.confidence || '0');

			if (rowFilter === 'attention' && !(conf < 0.75 || !catId)) return false;
			if (rowFilter === 'uncategorized' && Boolean(catId)) return false;
			if (rowFilter === 'duplicates' && !row.is_duplicate) return false;
			if (rowFilter === 'approved' && !isApproved) return false;
			if (rowFilter === 'skipped' && isApproved) return false;

			if (q) {
				const catName = categories.find((c) => c.id === catId)?.name ?? '';
				const hay = `${ed?.merchant_clean ?? row.merchant_clean} ${row.merchant_raw} ${ed?.description ?? row.description ?? ''} ${catName} ${row.amount}`.toLowerCase();
				if (!hay.includes(q)) return false;
			}
			return true;
		});
	});

	let inspectingRow = $derived(
		inspectingRowId && activeBatch
			? activeBatch.staged_transactions.find((r) => r.id === inspectingRowId) ?? null
			: null
	);

	let inspectingMatchCount = $derived.by(() => {
		if (!inspectingRow || !activeBatch) return 0;
		const key = normalizeMerchantKey(inspectingRow.merchant_raw);
		return activeBatch.staged_transactions.filter(
			(r) => normalizeMerchantKey(r.merchant_raw) === key
		).length;
	});

	let lunaImportPrompt = $derived.by(() => {
		if (!activeBatch) return '';
		return encodeURIComponent(
			`Analyze my recently imported statement "${activeBatch.filename}" (${activeBatch.committed_rows || activeBatch.total_rows} transactions). Highlight my top merchants, any unusual charges or fees, and suggest 2 concrete savings wins.`
		);
	});
</script>

{#if loading}
	<FinancinioLoader
		fullscreen={false}
		label="Loading AI Imports Studio"
		subtitles={[
			'Syncing your accounts & categories...',
			'Loading ingestion history & HITL queue...'
		]}
	/>
{:else}
	<div class="space-y-6 pb-16">
		<!-- Executive Header -->
		<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
			<div>
				<div class="flex items-center gap-2.5 flex-wrap">
					<h1 class="text-2xl font-bold tracking-tight text-white">AI Statement & Receipt Imports</h1>
					{#if pendingBatchesCount > 0}
						<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
							<span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse"></span>
							{pendingBatchesCount} awaiting review
						</span>
					{/if}
				</div>
				<p class="text-sm text-slate-400 mt-0.5">
					Deterministic <span class="text-orange-300 font-medium">BOG PDF</span> math + <span class="text-emerald-400 font-medium">LangGraph</span> HITL Review + <span class="text-cyan-400 font-medium">Upstash Vector</span> self-learning memory.
				</p>
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<button
					type="button"
					onclick={togglePrivacy}
					title={privacyMode ? 'Show amounts' : 'Hide amounts'}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition cursor-pointer"
				>
					{#if privacyMode}
						<EyeOff class="w-3.5 h-3.5 text-amber-400" />
						<span class="hidden sm:inline">Private</span>
					{:else}
						<Eye class="w-3.5 h-3.5 text-slate-400" />
						<span class="hidden sm:inline">Privacy</span>
					{/if}
				</button>

				<button
					type="button"
					onclick={() => (uploadStudioOpen = !uploadStudioOpen)}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer {uploadStudioOpen
						? 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
						: 'bg-emerald-500 hover:bg-emerald-400 text-slate-950'}"
				>
					{#if uploadStudioOpen}
						<ChevronUp class="w-3.5 h-3.5" />
						Hide Uploader
					{:else}
						<Plus class="w-3.5 h-3.5" />
						New Import
					{/if}
				</button>
			</div>
		</div>

		<!-- 3-Step Guided Pipeline Stepper -->
		<div class="grid grid-cols-3 gap-2 sm:gap-3">
			{#each [
				{ num: 1, title: 'Upload Document', sub: 'BOG PDF, CSV, XLSX, Receipt' },
				{ num: 2, title: 'Review & Categorize', sub: 'Edit inline · Bulk assign' },
				{ num: 3, title: 'Commit & Train AI', sub: 'Update ledger & Vector memory' }
			] as step}
				{@const done = activeStep > step.num || (step.num === 3 && activeBatch?.status === 'committed')}
				{@const current = activeStep === step.num && !(step.num === 3 && activeBatch?.status === 'committed')}
				<div
					class="rounded-2xl border px-3.5 py-3 flex items-center gap-3 transition {current
						? 'bg-emerald-500/10 border-emerald-500/40'
						: done
							? 'bg-slate-900/70 border-emerald-500/20'
							: 'bg-slate-950/60 border-slate-800/70 opacity-65'}"
				>
					<div
						class="h-7 w-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 {done
							? 'bg-emerald-500 text-slate-950'
							: current
								? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50'
								: 'bg-slate-900 text-slate-400 border border-slate-800'}"
					>
						{#if done}
							<Check class="w-3.5 h-3.5" />
						{:else}
							{step.num}
						{/if}
					</div>
					<div class="min-w-0">
						<div class="text-xs font-semibold text-white truncate">{step.title}</div>
						<div class="text-[11px] text-slate-400 truncate hidden sm:block">{step.sub}</div>
					</div>
				</div>
			{/each}
		</div>

		<!-- Alerts / Toasts -->
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
		{#if successMsg}
			<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-sm flex items-start justify-between gap-3">
				<div class="flex items-start gap-2.5">
					<CheckCircle2 class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
					<span>{successMsg}</span>
				</div>
				<button type="button" onclick={() => (successMsg = null)} class="text-emerald-300 hover:text-white cursor-pointer">
					<X class="w-4 h-4" />
				</button>
			</div>
		{/if}

		<!-- Compact Import Overview Strip -->
		{#if batches.length > 0}
			<div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
				<div class="card-surface rounded-2xl p-4">
					<div class="text-[11px] uppercase tracking-wider text-slate-400 font-medium">Total Imports</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-1">{batches.length}</div>
					<div class="text-[11px] text-slate-400 mt-0.5">
						{bogBatchesCount} BOG PDF · {batches.length - bogBatchesCount} General
					</div>
				</div>
				<div class="card-surface rounded-2xl p-4 {pendingBatchesCount > 0 ? 'border-amber-500/35 bg-amber-500/[0.04]' : ''}">
					<div class="text-[11px] uppercase tracking-wider text-slate-400 font-medium">Awaiting Review</div>
					<div class="text-2xl font-bold font-mono-num mt-1 {pendingBatchesCount > 0 ? 'text-amber-300' : 'text-emerald-400'}">
						{pendingBatchesCount}
					</div>
					<div class="text-[11px] text-slate-400 mt-0.5">
						{pendingBatchesCount > 0 ? 'Ready for 1-click approval' : 'All caught up'}
					</div>
				</div>
				<div class="card-surface rounded-2xl p-4">
					<div class="text-[11px] uppercase tracking-wider text-slate-400 font-medium">Committed to Ledger</div>
					<div class="text-2xl font-bold font-mono-num text-emerald-400 mt-1">{totalCommittedRows}</div>
					<div class="text-[11px] text-slate-400 mt-0.5">Verified transactions in Neon</div>
				</div>
				<div class="card-surface rounded-2xl p-4">
					<div class="text-[11px] uppercase tracking-wider text-slate-400 font-medium">Target Accounts</div>
					<div class="text-2xl font-bold font-mono-num text-cyan-300 mt-1">{accounts.length}</div>
					<div class="text-[11px] text-slate-400 mt-0.5">
						{selectedAccount ? `Active: ${selectedAccount.name}` : 'Create an account to start'}
					</div>
				</div>
			</div>
		{/if}

		<!-- Upload Studio (Collapsible) -->
		{#if uploading}
			<UploadProgressOverlay mode={importMode} filename={uploadingFilename} />
		{:else if uploadStudioOpen}
			<div class="card-surface rounded-2xl p-5 sm:p-6 space-y-5">
				<!-- Source Mode Cards -->
				<div class="grid md:grid-cols-2 gap-3">
					<button
						type="button"
						onclick={() => {
							importMode = 'bog';
							error = null;
						}}
						class="text-left p-4 rounded-2xl border transition cursor-pointer relative overflow-hidden {importMode === 'bog'
							? 'bg-gradient-to-br from-orange-500/15 via-orange-500/5 to-slate-950 border-orange-500/50 shadow-lg shadow-orange-950/20'
							: 'bg-slate-950/60 border-slate-800 hover:border-slate-700'}"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="flex items-center gap-3">
								<div
									class="h-10 w-10 rounded-xl flex items-center justify-center border shrink-0 {importMode === 'bog'
										? 'bg-orange-500/20 border-orange-500/40 text-orange-300'
										: 'bg-slate-900 border-slate-800 text-slate-400'}"
								>
									<Landmark class="w-5 h-5" />
								</div>
								<div>
									<div class="text-sm font-bold text-white flex items-center gap-2">
										Bank of Georgia (BOG)
										<span class="px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300 text-[10px] font-mono-num font-semibold">
											GE PDF
										</span>
									</div>
									<p class="text-xs text-slate-400 mt-0.5">
										საქართველოს ბანკი · ანგარიშიდან ამონაწერი
									</p>
								</div>
							</div>
							<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-500/15 text-orange-300 border border-orange-500/30 shrink-0">
								0 AI Tokens
							</span>
						</div>
						<p class="text-[11px] text-slate-400 mt-3 leading-relaxed">
							Deterministic Georgian PDF parser with multi-currency math verification (<span class="font-mono-num text-slate-300">GEL/USD/EUR/GBP</span>), ISO MCC auto-categorization, and instant duplicate protection.
						</p>
					</button>

					<button
						type="button"
						onclick={() => {
							importMode = 'general';
							error = null;
						}}
						class="text-left p-4 rounded-2xl border transition cursor-pointer relative overflow-hidden {importMode === 'general'
							? 'bg-gradient-to-br from-emerald-500/15 via-cyan-500/5 to-slate-950 border-emerald-500/50 shadow-lg shadow-emerald-950/20'
							: 'bg-slate-950/60 border-slate-800 hover:border-slate-700'}"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="flex items-center gap-3">
								<div
									class="h-10 w-10 rounded-xl flex items-center justify-center border shrink-0 {importMode === 'general'
										? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
										: 'bg-slate-900 border-slate-800 text-slate-400'}"
								>
									<Receipt class="w-5 h-5" />
								</div>
								<div>
									<div class="text-sm font-bold text-white flex items-center gap-2">
										Universal Statement & Receipt
									</div>
									<p class="text-xs text-slate-400 mt-0.5">
										Any bank export or receipt photo
									</p>
								</div>
							</div>
							<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shrink-0">
								AI + Vision
							</span>
						</div>
						<div class="flex flex-wrap items-center gap-1.5 mt-3">
							{#each ['CSV', 'Excel .xlsx', 'Any Bank PDF', 'Receipt PNG/JPG'] as fmt}
								<span class="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-[10px] font-medium text-slate-300">
									{fmt}
								</span>
							{/each}
						</div>
					</button>
				</div>

				<!-- Target Account Bar -->
				<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-slate-950/75 border border-slate-800/90">
					<div class="flex items-center gap-2.5">
						<Wallet class="w-4 h-4 text-slate-400 shrink-0" />
						<label for="target-acc" class="text-xs font-medium text-slate-300">Import Destination Account</label>
					</div>
					<div class="flex flex-wrap items-center gap-3">
						{#if accounts.length === 0}
							<a
								href="/accounts"
								class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 text-slate-950 text-xs font-semibold"
							>
								<Plus class="w-3.5 h-3.5" /> Create an Account First
							</a>
						{:else}
							<select
								id="target-acc"
								bind:value={selectedAccountId}
								class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs font-medium text-white focus:outline-none focus:border-emerald-500"
							>
								{#each accounts as acc}
									<option value={acc.id}>{acc.name} ({acc.currency})</option>
								{/each}
							</select>
							{#if selectedAccount}
								<span class="text-xs font-mono-num text-slate-400 {privacyMode ? 'privacy-blur' : ''}">
									Bal: <strong class="text-slate-200">{formatMoney(selectedAccount.current_balance, selectedAccount.currency)}</strong>
								</span>
							{/if}
						{/if}
					</div>
				</div>

				{#if importMode === 'bog' && selectedAccount && selectedAccount.currency.toUpperCase() !== 'GEL'}
					<div class="px-3.5 py-2.5 rounded-xl bg-amber-500/8 border border-amber-500/25 text-xs text-amber-200 flex items-center gap-2">
						<AlertTriangle class="w-3.5 h-3.5 text-amber-400 shrink-0" />
						<span>
							Heads up: <strong>{selectedAccount.name}</strong> uses <strong>{selectedAccount.currency}</strong>. If your BOG PDF is primarily in GEL, consider selecting your GEL account for exact balance reconciliation.
						</span>
					</div>
				{/if}

				<!-- Drag & Drop Zone -->
				<label
					ondragover={(e) => {
						e.preventDefault();
						dragOver = true;
					}}
					ondragleave={() => (dragOver = false)}
					ondrop={onDrop}
					class="group relative block border-2 border-dashed rounded-2xl p-8 sm:p-10 text-center transition cursor-pointer {dragOver
						? importMode === 'bog'
							? 'border-orange-400 bg-orange-500/12 scale-[1.005]'
							: 'border-emerald-400 bg-emerald-500/12 scale-[1.005]'
						: importMode === 'bog'
							? 'border-orange-500/35 hover:border-orange-400/75 bg-slate-950/60 hover:bg-orange-500/[0.04]'
							: 'border-slate-700/80 hover:border-emerald-500/60 bg-slate-950/50 hover:bg-emerald-500/[0.03]'}"
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

					<div
						class="h-14 w-14 mx-auto mb-4 rounded-2xl flex items-center justify-center border transition-transform group-hover:-translate-y-0.5 {importMode === 'bog'
							? 'bg-orange-500/12 border-orange-500/35 text-orange-400'
							: 'bg-emerald-500/12 border-emerald-500/35 text-emerald-400'}"
					>
						<UploadCloud class="w-7 h-7" />
					</div>

					<div class="text-base font-semibold text-white">
						{#if dragOver}
							Release to start parsing immediately
						{:else if importMode === 'bog'}
							Drop your Bank of Georgia PDF here, or <span class="text-orange-300 underline decoration-orange-500/40 underline-offset-4">browse files</span>
						{:else}
							Drop any statement or receipt here, or <span class="text-emerald-300 underline decoration-emerald-500/40 underline-offset-4">browse files</span>
						{/if}
					</div>
					<p class="text-xs text-slate-400 mt-1.5 max-w-lg mx-auto">
						{#if importMode === 'bog'}
							Auto-extracts ობიექტი, MCC codes, transfers, commissions, and reconciles opening & closing balances. Max 15 MB.
						{:else}
							Deduplicated & categorized via Personal Rules → Upstash Vector → AI, then paused for your 1-click approval. Max 15 MB.
						{/if}
					</p>
				</label>
			</div>
		{/if}

		<!-- Main Split Workspace: Recent Imports + HITL Review Studio -->
		<div class="grid xl:grid-cols-12 gap-6 items-start">
			<!-- Left Sidebar: Recent Import Batches -->
			<div class="xl:col-span-3 card-surface rounded-2xl p-4 space-y-3">
				<div class="flex items-center justify-between gap-2 px-1">
					<h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400">
						Import History ({batches.length})
					</h3>
				</div>

				{#if batches.length > 0}
					<div class="grid grid-cols-3 gap-1 p-1 rounded-xl bg-slate-950/80 border border-slate-800/80 text-[11px]">
						{#each [
							{ id: 'all', label: 'All' },
							{ id: 'needs_review', label: 'Review' },
							{ id: 'committed', label: 'Done' }
						] as tab}
							<button
								type="button"
								onclick={() => (batchFilter = tab.id as BatchFilter)}
								class="py-1 rounded-lg font-medium transition cursor-pointer {batchFilter === tab.id
									? 'bg-slate-800 text-white'
									: 'text-slate-400 hover:text-slate-200'}"
							>
								{tab.label}
							</button>
						{/each}
					</div>
				{/if}

				{#if filteredBatches.length === 0}
					<div class="text-center py-8 px-2 space-y-1.5">
						<Layers class="w-6 h-6 text-slate-600 mx-auto" />
						<p class="text-xs text-slate-400">
							{batches.length === 0 ? 'No imports uploaded yet.' : 'No imports match this filter.'}
						</p>
					</div>
				{:else}
					<div class="space-y-2 max-h-[540px] overflow-y-auto pr-0.5">
						{#each filteredBatches as b}
							{@const acc = accountById(b.account_id)}
							{@const selected = activeBatch?.id === b.id}
							<div
								class="group relative flex items-stretch rounded-xl border transition {selected
									? 'bg-emerald-500/10 border-emerald-500/45 shadow-sm'
									: 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'}"
							>
								<button
									type="button"
									onclick={() => selectBatch(b.id)}
									class="flex-1 min-w-0 text-left p-3 cursor-pointer space-y-1.5"
								>
									<div class="flex items-center justify-between gap-2">
										<span class="text-xs font-semibold text-white truncate" title={b.filename}>
											{b.filename}
										</span>
										<span
											class="text-[10px] font-semibold px-1.5 py-0.5 rounded-md uppercase shrink-0 {b.status === 'committed'
												? 'bg-emerald-500/15 text-emerald-300'
												: b.status === 'needs_review'
													? 'bg-amber-500/15 text-amber-300'
													: 'bg-rose-500/15 text-rose-300'}"
										>
											{b.status === 'needs_review' ? 'Review' : b.status}
										</span>
									</div>
									<div class="flex items-center flex-wrap gap-1.5 text-[10px]">
										<span
											class="px-1.5 py-0.5 rounded font-semibold {b.doc_type === 'bog_pdf'
												? 'bg-orange-500/15 text-orange-300'
												: 'bg-slate-800 text-slate-300'}"
										>
											{docTypeLabel(b.doc_type)}
										</span>
										{#if acc}
											<span class="text-slate-400 truncate max-w-[110px]">{acc.name}</span>
										{/if}
									</div>
									<div class="text-[11px] text-slate-400 flex items-center justify-between gap-2 pt-0.5">
										<span class="inline-flex items-center gap-1">
											<FileSpreadsheet class="w-3 h-3 text-slate-500" />
											{b.status === 'committed' ? `${b.committed_rows} committed` : `${b.total_rows} rows`}
											{#if b.duplicate_rows > 0}
												<span class="text-amber-400">· {b.duplicate_rows} dup</span>
											{/if}
										</span>
										<span class="text-[10px] text-slate-500 inline-flex items-center gap-0.5">
											<Clock class="w-2.5 h-2.5" />
											{formatDate(b.created_at)}
										</span>
									</div>
								</button>
								<button
									type="button"
									onclick={() => openDeleteConfirm(b)}
									title={b.status === 'committed' ? 'Remove import & rollback transactions' : 'Discard import'}
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

			<!-- Right Main Area: HITL Review Studio -->
			<div class="xl:col-span-9 card-surface rounded-2xl overflow-hidden">
				{#if !activeBatch}
					<div class="p-12 sm:p-16 text-center space-y-3">
						<div class="h-14 w-14 mx-auto rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-emerald-400">
							<Sparkles class="w-7 h-7" />
						</div>
						<div class="text-base font-semibold text-white">Your AI Review Queue is Ready</div>
						<p class="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
							Upload a Bank of Georgia PDF, bank CSV/Excel export, or receipt photo above. Every parsed transaction will appear here for fast inline review before touching your Neon ledger.
						</p>
						{#if !uploadStudioOpen}
							<button
								type="button"
								onclick={() => (uploadStudioOpen = true)}
								class="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer"
							>
								<UploadCloud class="w-4 h-4" /> Upload Statement
							</button>
						{/if}
					</div>
				{:else}
					<!-- Batch Header -->
					<div class="p-5 border-b border-slate-800/80 space-y-4">
						<div class="flex flex-col md:flex-row md:items-start justify-between gap-4">
							<div class="space-y-1.5 min-w-0">
								<div class="flex items-center flex-wrap gap-2">
									<h2 class="text-lg font-bold text-white truncate max-w-full">
										{activeBatch.filename}
									</h2>
									<span
										class="text-[10px] px-2 py-0.5 rounded-full uppercase font-semibold {activeBatch.doc_type === 'bog_pdf'
											? 'bg-orange-500/15 text-orange-300 border border-orange-500/30'
											: 'bg-slate-800 text-slate-300 border border-slate-700'}"
									>
										{docTypeLabel(activeBatch.doc_type)}
									</span>
									{#if activeBatchAccount}
										<span class="text-[11px] px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-slate-300">
											{activeBatchAccount.name} ({activeBatchAccount.currency})
										</span>
									{/if}
								</div>

								{#if activeBatch.reconciliation_note}
									<div
										class="inline-flex items-start gap-2 px-3 py-2 rounded-xl text-xs border {activeBatch.balance_reconciled === false
											? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
											: 'bg-emerald-500/8 border-emerald-500/25 text-emerald-200'}"
									>
										{#if activeBatch.balance_reconciled === false}
											<AlertTriangle class="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
										{:else}
											<ShieldCheck class="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
										{/if}
										<span>{activeBatch.reconciliation_note}</span>
									</div>
								{/if}
							</div>

							<div class="flex flex-wrap items-center gap-2 shrink-0">
								{#if activeBatch.status === 'needs_review'}
									<button
										type="button"
										disabled={committing || batchLiveStats.approved === 0}
										onclick={handleCommit}
										class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs sm:text-sm transition cursor-pointer disabled:opacity-50"
									>
										<CheckCircle2 class="w-4 h-4" />
										{committing
											? 'Committing...'
											: `Commit ${batchLiveStats.approved} Rows`}
									</button>
								{:else if activeBatch.status === 'committed'}
									<span class="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-300 bg-emerald-500/15 px-3 py-2 rounded-xl border border-emerald-500/30">
										<CheckCircle2 class="w-4 h-4" /> Committed ({activeBatch.committed_rows} rows)
									</span>
								{/if}

								<button
									type="button"
									onclick={() => activeBatch && openDeleteConfirm(activeBatch)}
									class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-semibold transition cursor-pointer"
								>
									<Trash2 class="w-3.5 h-3.5" />
									{activeBatch.status === 'committed' ? 'Rollback Import' : 'Discard'}
								</button>
							</div>
						</div>

						<!-- Live Batch Financial Summary Strip -->
						<div class="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
							<div class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/80">
								<div class="text-[10px] uppercase tracking-wider text-slate-400">
									{activeBatch.status === 'committed' ? 'Committed Rows' : 'Selected to Commit'}
								</div>
								<div class="text-base font-bold font-mono-num text-white mt-0.5">
									{activeBatch.status === 'committed' ? activeBatch.committed_rows : batchLiveStats.approved}
									<span class="text-xs font-normal text-slate-500">/ {batchLiveStats.total}</span>
								</div>
								<div class="text-[10px] mt-0.5 {batchLiveStats.uncategorizedApproved > 0 ? 'text-amber-300' : 'text-emerald-400'}">
									{batchLiveStats.uncategorizedApproved > 0
										? `${batchLiveStats.uncategorizedApproved} uncategorized`
										: '100% categorized'}
								</div>
							</div>

							<div class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/80">
								<div class="text-[10px] uppercase tracking-wider text-slate-400">Total Inflow</div>
								<div class="text-base font-bold font-mono-num text-emerald-400 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
									+{formatMoney(batchLiveStats.inflow, batchLiveStats.currency)}
								</div>
								<div class="text-[10px] text-slate-500 mt-0.5">Incoming credits</div>
							</div>

							<div class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/80">
								<div class="text-[10px] uppercase tracking-wider text-slate-400">Total Outflow</div>
								<div class="text-base font-bold font-mono-num text-rose-300 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
									-{formatMoney(batchLiveStats.outflow, batchLiveStats.currency)}
								</div>
								<div class="text-[10px] text-slate-500 mt-0.5">Outgoing expenses</div>
							</div>

							<div class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/80">
								<div class="text-[10px] uppercase tracking-wider text-slate-400">
									{projectedAccountBalance !== null ? 'Projected Balance' : 'Net Batch Impact'}
								</div>
								<div
									class="text-base font-bold font-mono-num mt-0.5 {privacyMode ? 'privacy-blur' : ''} {projectedAccountBalance !== null
										? 'text-cyan-300'
										: batchLiveStats.net >= 0
											? 'text-emerald-400'
											: 'text-rose-300'}"
								>
									{#if projectedAccountBalance !== null && activeBatchAccount}
										{formatMoney(projectedAccountBalance, activeBatchAccount.currency)}
									{:else}
										{batchLiveStats.net >= 0 ? '+' : ''}{formatMoney(batchLiveStats.net, batchLiveStats.currency)}
									{/if}
								</div>
								<div class="text-[10px] text-slate-500 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
									{#if projectedAccountBalance !== null && activeBatchAccount}
										Net {batchLiveStats.net >= 0 ? '+' : ''}{formatMoney(batchLiveStats.net, activeBatchAccount.currency)}
									{:else}
										{batchLiveStats.duplicates} duplicates detected
									{/if}
								</div>
							</div>
						</div>

						<!-- Post-Commit Celebration & Next Actions -->
						{#if activeBatch.status === 'committed'}
							<div class="p-4 rounded-2xl bg-gradient-to-r from-emerald-500/12 via-cyan-500/8 to-slate-950 border border-emerald-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
								<div class="flex items-start gap-3">
									<div class="h-9 w-9 rounded-xl bg-emerald-500/20 border border-emerald-500/35 flex items-center justify-center text-emerald-300 shrink-0">
										<CheckCircle2 class="w-5 h-5" />
									</div>
									<div>
										<div class="text-sm font-semibold text-white">
											{justCommittedCount !== null
												? `${justCommittedCount} transactions committed & balance updated!`
												: `Batch committed (${activeBatch.committed_rows} rows in ledger)`}
										</div>
										<p class="text-xs text-slate-300 mt-0.5">
											Explore these entries in your ledger or ask Luna to audit your spending patterns.
										</p>
									</div>
								</div>
								<div class="flex flex-wrap items-center gap-2 shrink-0">
									<a
										href="/transactions?account={activeBatch.account_id}"
										class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold transition"
									>
										View in Ledger
										<ArrowRight class="w-3.5 h-3.5" />
									</a>
									<a
										href="/advisor?prompt={lunaImportPrompt}"
										class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-violet-500/15 hover:bg-violet-500/25 border border-violet-500/35 text-violet-200 text-xs font-semibold transition"
									>
										<Sparkles class="w-3.5 h-3.5" />
										Audit with Luna
									</a>
								</div>
							</div>
						{/if}
					</div>

					<!-- Review Filter, Search & Bulk Actions Toolbar -->
					<div class="px-5 py-3.5 bg-slate-900/55 border-b border-slate-800/80 space-y-3">
						<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
							<!-- Search -->
							<div class="relative flex-1 max-w-sm">
								<Search class="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
								<input
									type="text"
									bind:value={rowSearch}
									placeholder="Search merchant, category, raw text..."
									class="w-full pl-9 pr-8 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
								/>
								{#if rowSearch}
									<button
										type="button"
										onclick={() => (rowSearch = '')}
										class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white cursor-pointer"
									>
										<X class="w-3.5 h-3.5" />
									</button>
								{/if}
							</div>

							<!-- Smart Filter Chips -->
							<div class="flex flex-wrap items-center gap-1.5">
								{#each [
									{ id: 'all', label: 'All', count: batchLiveStats.total },
									{ id: 'attention', label: 'Needs Attention', count: batchLiveStats.attentionCount },
									{ id: 'uncategorized', label: 'Uncategorized', count: batchLiveStats.uncategorizedTotal },
									{ id: 'duplicates', label: 'Duplicates', count: batchLiveStats.duplicates },
									{ id: 'approved', label: 'Approved', count: batchLiveStats.approved },
									{ id: 'skipped', label: 'Skipped', count: batchLiveStats.skipped }
								] as chip}
									<button
										type="button"
										onclick={() => (rowFilter = chip.id as RowFilter)}
										class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border transition cursor-pointer {rowFilter === chip.id
											? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
											: 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-slate-200'}"
									>
										{chip.label}
										<span class="font-mono-num text-[10px] opacity-80">{chip.count}</span>
									</button>
								{/each}
							</div>
						</div>

						<!-- Bulk Quick Tools (only when needs_review) -->
						{#if activeBatch.status === 'needs_review'}
							<div class="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/70 text-xs">
								<div class="flex flex-wrap items-center gap-1.5">
									<button
										type="button"
										onclick={() => approveVisible(true)}
										class="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 text-[11px] font-medium cursor-pointer"
									>
										Approve Visible ({filteredRows.length})
									</button>
									<button
										type="button"
										onclick={() => approveVisible(false)}
										class="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-400 text-[11px] font-medium cursor-pointer"
									>
										Skip Visible
									</button>
									<button
										type="button"
										onclick={approveHighConfidence}
										class="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 text-[11px] font-medium cursor-pointer"
									>
										Approve ≥80% Conf
									</button>
									{#if batchLiveStats.duplicates > 0}
										<button
											type="button"
											onclick={skipAllDuplicates}
											class="px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 text-[11px] font-medium cursor-pointer"
										>
											Uncheck Duplicates
										</button>
									{/if}
								</div>

								<!-- Bulk Assign Category to Visible -->
								<div class="flex items-center gap-1.5">
									<select
										bind:value={bulkCategoryId}
										aria-label="Bulk assign category to visible rows"
										class="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-slate-200 focus:outline-none focus:border-cyan-500"
									>
										<option value="">Bulk set category ({filteredRows.length})...</option>
										<option value="__clear__">Set Uncategorized</option>
										{#each categories as cat}
											<option value={cat.id}>{cat.name}</option>
										{/each}
									</select>
									<button
										type="button"
										disabled={!bulkCategoryId || filteredRows.length === 0}
										onclick={applyBulkCategoryToVisible}
										class="px-2.5 py-1 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/35 text-cyan-200 text-[11px] font-semibold cursor-pointer disabled:opacity-40"
									>
										Apply
									</button>
								</div>
							</div>
						{/if}
					</div>

					<!-- Smart Auto-Propagate Merchant Banner -->
					{#if propagateSuggestion && activeBatch.status === 'needs_review'}
						<div class="px-5 py-3 bg-cyan-500/10 border-b border-cyan-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
							<div class="flex items-center gap-2 text-cyan-100">
								<Wand2 class="w-4 h-4 text-cyan-300 shrink-0" />
								<span>
									Found <strong>{propagateSuggestion.otherIds.length}</strong> other {propagateSuggestion.otherIds.length === 1 ? 'row' : 'rows'} matching <strong>"{propagateSuggestion.merchantLabel}"</strong>. Apply <strong>{propagateSuggestion.categoryName}</strong> to all of them?
								</span>
							</div>
							<div class="flex items-center gap-2 shrink-0">
								<button
									type="button"
									onclick={applyPropagateSuggestion}
									class="px-3 py-1.5 rounded-lg bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-semibold text-xs cursor-pointer"
								>
									Apply to {propagateSuggestion.otherIds.length} {propagateSuggestion.otherIds.length === 1 ? 'Row' : 'Rows'}
								</button>
								<button
									type="button"
									onclick={() => (propagateSuggestion = null)}
									class="p-1 text-cyan-200/70 hover:text-white cursor-pointer"
								>
									<X class="w-4 h-4" />
								</button>
							</div>
						</div>
					{/if}

					<!-- Staged Rows: Empty Filter State -->
					{#if filteredRows.length === 0}
						<div class="p-10 text-center space-y-2">
							<p class="text-sm font-medium text-slate-300">No rows match your current filter</p>
							<button
								type="button"
								onclick={() => {
									rowSearch = '';
									rowFilter = 'all';
								}}
								class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 cursor-pointer"
							>
								<RotateCcw class="w-3.5 h-3.5" /> Reset Filters
							</button>
						</div>
					{:else}
						<!-- Mobile Card View (< md) -->
						<div class="md:hidden divide-y divide-slate-800/70">
							{#each filteredRows as row}
								{@const ed = editedRows[row.id]}
								{@const confPct = Math.round(Number.parseFloat(row.confidence || '0') * 100)}
								{@const badge = sourceBadgeMeta(row.categorization_source)}
								{@const dir = ed ? ed.direction : row.direction}
								{@const amt = ed ? ed.amount : row.amount}
								<div class="p-4 space-y-3 {row.is_duplicate ? 'bg-amber-500/[0.04]' : ''}">
									<div class="flex items-start justify-between gap-3">
										<div class="flex items-start gap-2.5 min-w-0">
											{#if ed}
												<input
													type="checkbox"
													disabled={activeBatch.status === 'committed'}
													bind:checked={ed.user_approved}
													class="mt-1 rounded border-slate-700 accent-emerald-500"
												/>
											{/if}
											<div class="min-w-0">
												<div class="flex items-center gap-1.5 flex-wrap">
													<span class="text-[11px] font-mono-num text-slate-400">
														{formatDate(ed?.occurred_at || row.occurred_at)}
													</span>
													<span class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full border {badge.cls}">
														{badge.label} · {confPct}%
													</span>
													{#if row.is_duplicate}
														<span class="text-[10px] font-semibold text-amber-400">DUP</span>
													{/if}
												</div>
												<div class="text-xs text-slate-500 truncate mt-0.5">
													{row.description || row.merchant_raw}
												</div>
											</div>
										</div>
										<div class="text-right shrink-0">
											<div
												class="font-mono-num text-sm font-bold {privacyMode ? 'privacy-blur' : ''} {dir === 'inflow'
													? 'text-emerald-400'
													: 'text-white'}"
											>
												{dir === 'inflow' ? '+' : '-'}{formatMoney(amt, row.currency)}
											</div>
											<button
												type="button"
												onclick={() => (inspectingRowId = row.id)}
												class="mt-1 inline-flex items-center gap-1 text-[11px] text-cyan-300 hover:text-cyan-200 cursor-pointer"
											>
												<SlidersHorizontal class="w-3 h-3" /> Edit
											</button>
										</div>
									</div>

									{#if ed && activeBatch.status === 'needs_review'}
										<div class="grid grid-cols-1 gap-2">
											<input
												type="text"
												bind:value={ed.merchant_clean}
												class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
											/>
											<select
												bind:value={ed.category_id}
												onchange={() => handleCategoryChange(row, ed.category_id)}
												class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
											>
												<option value="">Uncategorized</option>
												{#each categories as cat}
													<option value={cat.id}>{cat.name}</option>
												{/each}
											</select>
										</div>
									{:else}
										<div class="flex items-center justify-between text-xs">
											<span class="font-medium text-white">{row.merchant_clean}</span>
											<span class="text-slate-400">
												{categories.find((c) => c.id === row.suggested_category_id)?.name ?? 'Uncategorized'}
											</span>
										</div>
									{/if}
								</div>
							{/each}
						</div>

						<!-- Desktop Review Table (>= md) -->
						<div class="hidden md:block overflow-x-auto">
							<table class="w-full text-left border-collapse text-sm">
								<thead>
									<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400 bg-slate-950/40">
										<th class="py-3 px-4 w-10">Use</th>
										<th class="py-3 px-3">Date</th>
										<th class="py-3 px-3">Merchant & Narrative</th>
										<th class="py-3 px-3">Category</th>
										<th class="py-3 px-3">AI Signal</th>
										<th class="py-3 px-3 text-right">Amount</th>
										<th class="py-3 px-3 w-12 text-right">Edit</th>
									</tr>
								</thead>
								<tbody class="divide-y divide-slate-800/60">
									{#each filteredRows as row}
										{@const ed = editedRows[row.id]}
										{@const confPct = Math.round(Number.parseFloat(row.confidence || '0') * 100)}
										{@const badge = sourceBadgeMeta(row.categorization_source)}
										{@const dir = ed ? ed.direction : row.direction}
										{@const amt = ed ? ed.amount : row.amount}
										{@const edited = isRowEdited(row)}
										<tr
											class="transition {row.is_duplicate
												? 'opacity-65 bg-amber-500/[0.04]'
												: ed && !ed.user_approved
													? 'opacity-50 bg-slate-950/30'
													: 'hover:bg-slate-900/45'}"
										>
											<td class="py-2.5 px-4">
												{#if ed}
													<input
														type="checkbox"
														disabled={activeBatch.status === 'committed'}
														bind:checked={ed.user_approved}
														class="rounded border-slate-700 accent-emerald-500 cursor-pointer disabled:cursor-not-allowed"
													/>
												{/if}
											</td>
											<td class="py-2.5 px-3 text-xs font-mono-num text-slate-400 whitespace-nowrap">
												{formatDate(ed?.occurred_at || row.occurred_at)}
											</td>
											<td class="py-2.5 px-3 min-w-[220px]">
												<div class="flex items-center gap-1.5">
													{#if ed && activeBatch.status === 'needs_review'}
														<input
															type="text"
															bind:value={ed.merchant_clean}
															class="w-full px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
														/>
													{:else}
														<div class="text-xs font-medium text-white">{row.merchant_clean}</div>
													{/if}
													{#if edited}
														<span
															title="Edited in review"
															class="h-2 w-2 rounded-full bg-cyan-400 shrink-0"
														></span>
													{/if}
												</div>
												<div
													class="text-[10px] text-slate-500 truncate max-w-[300px] mt-0.5 flex items-center gap-1.5"
													title={row.description || row.merchant_raw}
												>
													<span class="truncate">{ed?.description || row.description || row.merchant_raw}</span>
													{#if row.is_duplicate}
														<span class="px-1.5 py-0.2 rounded bg-amber-500/15 text-amber-300 font-semibold shrink-0">
															DUPLICATE
														</span>
													{/if}
												</div>
											</td>
											<td class="py-2.5 px-3">
												{#if ed && activeBatch.status === 'needs_review'}
													<select
														bind:value={ed.category_id}
														onchange={() => handleCategoryChange(row, ed.category_id)}
														class="w-full max-w-[190px] px-2.5 py-1.5 rounded-lg bg-slate-950 border text-xs focus:outline-none focus:border-emerald-500 {!ed.category_id
															? 'border-amber-500/40 text-amber-200'
															: 'border-slate-800 text-slate-200'}"
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
												<span class="inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full border {badge.cls}">
													<span
														class="h-1.5 w-1.5 rounded-full {confPct >= 80
															? 'bg-emerald-400'
															: confPct >= 60
																? 'bg-amber-400'
																: 'bg-rose-400'}"
													></span>
													{badge.label} · {confPct}%
												</span>
											</td>
											<td class="py-2.5 px-3 text-right whitespace-nowrap">
												<span
													class="inline-flex items-center justify-end gap-0.5 font-mono-num text-xs font-semibold {privacyMode ? 'privacy-blur' : ''} {dir === 'inflow'
														? 'text-emerald-400'
														: 'text-slate-100'}"
												>
													{#if dir === 'inflow'}
														<ArrowDownRight class="w-3 h-3 text-emerald-400" />
														+{formatMoney(amt, row.currency)}
													{:else}
														<ArrowUpRight class="w-3 h-3 text-rose-400/80" />
														-{formatMoney(amt, row.currency)}
													{/if}
												</span>
											</td>
											<td class="py-2.5 px-3 text-right">
												<button
													type="button"
													onclick={() => (inspectingRowId = row.id)}
													title="Inspect raw text & edit all fields"
													class="p-1.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-cyan-300 transition cursor-pointer"
												>
													<SlidersHorizontal class="w-3.5 h-3.5" />
												</button>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{/if}

					<!-- Sticky Bottom Review & Commit Action Bar -->
					{#if activeBatch.status === 'needs_review'}
						<div class="sticky bottom-0 z-20 px-5 py-4 bg-slate-950/95 backdrop-blur-md border-t border-slate-800 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
							<div class="flex flex-wrap items-center gap-4 text-xs text-slate-300">
								<label class="inline-flex items-center gap-2 cursor-pointer">
									<input
										type="checkbox"
										bind:checked={skipDuplicates}
										class="rounded border-slate-700 accent-emerald-500"
									/>
									<span>Skip duplicates ({batchLiveStats.duplicates})</span>
								</label>
								<label class="inline-flex items-center gap-2 cursor-pointer">
									<input
										type="checkbox"
										bind:checked={learnFromEdits}
										class="rounded border-slate-700 accent-cyan-400"
									/>
									<Brain class="w-3.5 h-3.5 text-cyan-400" />
									<span>Train Upstash Vector memory</span>
								</label>
							</div>

							<div class="flex flex-wrap items-center justify-between lg:justify-end gap-3">
								<div class="text-xs text-slate-400 font-mono-num {privacyMode ? 'privacy-blur' : ''}">
									<strong class="text-white">{batchLiveStats.approved}</strong> rows · Net
									<strong class="{batchLiveStats.net >= 0 ? 'text-emerald-400' : 'text-rose-300'}">
										{batchLiveStats.net >= 0 ? '+' : ''}{formatMoney(batchLiveStats.net, batchLiveStats.currency)}
									</strong>
								</div>
								<button
									type="button"
									disabled={committing || batchLiveStats.approved === 0}
									onclick={handleCommit}
									class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer disabled:opacity-50 shadow-lg shadow-emerald-500/20"
								>
									<CheckCircle2 class="w-4 h-4" />
									{committing
										? 'Committing to Ledger...'
										: `Approve & Commit ${batchLiveStats.approved} Rows`}
								</button>
							</div>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>
{/if}

<!-- Staged Row Inspector & Full Editor Drawer -->
{#if inspectingRow && editedRows[inspectingRow.id]}
	<StagedRowDrawer
		row={inspectingRow}
		bind:edit={editedRows[inspectingRow.id]}
		{categories}
		readonly={activeBatch?.status === 'committed'}
		matchingMerchantCount={inspectingMatchCount}
		{privacyMode}
		onClose={() => (inspectingRowId = null)}
		onApplyToMatching={applyToMatchingMerchant}
	/>
{/if}

<!-- Safe Delete / Rollback Modal -->
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
								? 'Rollback Imported Ledger?'
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
						This import added <strong class="text-white">{confirmDeleteBatch.committed_rows} transactions</strong> to your ledger. Removing it will also delete its stored file and AI search index.
					</p>
					<label class="flex items-start gap-2.5 p-3 rounded-xl bg-rose-500/8 border border-rose-500/25 cursor-pointer">
						<input
							type="checkbox"
							bind:checked={deleteLedgerTxs}
							class="mt-0.5 rounded border-slate-700 accent-rose-500"
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
						Rollback & Remove {confirmDeleteBatch.committed_rows} Transactions
					{:else}
						Delete Import
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
