<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type { Account, Category, Transaction } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import {
		X,
		Save,
		Trash2,
		Sparkles,
		ArrowUpRight,
		ArrowDownRight,
		ArrowLeftRight,
		Tag,
		Plus,
		Wand2,
		FileText,
		CheckCircle2
	} from 'lucide-svelte';

	let {
		transaction = null,
		accounts,
		categories,
		privacyMode = false,
		onClose,
		onSaved,
		onRequestDelete
	}: {
		transaction: Transaction | null;
		accounts: Account[];
		categories: Category[];
		privacyMode?: boolean;
		onClose: () => void;
		onSaved: (updated: Transaction) => void;
		onRequestDelete: (tx: Transaction) => void;
	} = $props();

	let merchantClean = $state('');
	let amount = $state('');
	let direction = $state<'inflow' | 'outflow'>('outflow');
	let occurredAt = $state('');
	let accountId = $state('');
	let categoryId = $state('');
	let notes = $state('');
	let tags = $state<string[]>([]);
	let newTag = $state('');
	let isTransfer = $state(false);

	let saving = $state(false);
	let creatingRule = $state(false);
	let ruleCreated = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		if (transaction) {
			merchantClean = transaction.merchant_clean;
			amount = transaction.amount;
			direction = transaction.direction;
			occurredAt = transaction.occurred_at;
			accountId = transaction.account_id;
			categoryId = transaction.category_id ?? '';
			notes = transaction.notes ?? '';
			tags = [...(transaction.tags ?? [])];
			newTag = '';
			isTransfer = transaction.is_transfer;
			error = null;
			ruleCreated = false;
		}
	});

	let selectedCategory = $derived(categories.find((c) => c.id === categoryId) ?? null);

	function addTag() {
		const clean = newTag.trim().toLowerCase().replace(/\s+/g, '-');
		if (!clean) return;
		if (!tags.includes(clean)) {
			tags = [...tags, clean];
		}
		newTag = '';
	}

	function removeTag(tag: string) {
		tags = tags.filter((t) => t !== tag);
	}

	async function handleSave(e: SubmitEvent) {
		e.preventDefault();
		if (!transaction) return;
		const num = Number.parseFloat(amount);
		if (!num || num <= 0) {
			error = 'Amount must be a positive number.';
			return;
		}
		saving = true;
		error = null;
		try {
			const updated = await api.updateTransaction(transaction.id, {
				account_id: accountId,
				category_id: categoryId || null,
				merchant_clean: merchantClean.trim(),
				amount: num.toFixed(2),
				direction,
				occurred_at: occurredAt,
				notes: notes.trim() || null,
				tags,
				is_transfer: isTransfer
			});
			onSaved(updated);
			onClose();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to update transaction';
		} finally {
			saving = false;
		}
	}

	async function handleCreateAutoRule() {
		if (!transaction || !categoryId) return;
		creatingRule = true;
		error = null;
		try {
			await api.createRule({
				match_pattern: merchantClean.trim() || transaction.merchant_clean,
				match_type: 'contains',
				category_id: categoryId,
				merchant_override: merchantClean.trim() || undefined,
				priority: 50
			});
			ruleCreated = true;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to create categorization rule';
		} finally {
			creatingRule = false;
		}
	}
</script>

{#if transaction}
	<div class="fixed inset-0 z-50 flex justify-end">
		<button
			type="button"
			onclick={onClose}
			aria-label="Close transaction inspector"
			class="fixed inset-0 bg-black/65 backdrop-blur-xs cursor-pointer"
		></button>

		<aside class="relative z-10 w-full max-w-md bg-slate-950 border-l border-slate-800/90 h-dvh flex flex-col shadow-2xl overflow-hidden">
			<!-- Header -->
			<div class="p-5 border-b border-slate-800/80 flex items-start justify-between gap-3 shrink-0">
				<div class="min-w-0">
					<div class="flex items-center gap-2">
						<h2 class="text-base font-bold text-white truncate">Transaction Inspector</h2>
						{#if transaction.source_document_id}
							<span class="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 text-[10px] font-semibold">
								AI Import
							</span>
						{/if}
					</div>
					<div
						class="text-lg font-mono-num font-bold mt-1 {direction === 'inflow'
							? 'text-emerald-400'
							: 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
					>
						{direction === 'inflow' ? '+' : '-'}{formatMoney(amount || transaction.amount, transaction.currency)}
					</div>
				</div>
				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer shrink-0"
					aria-label="Close drawer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<!-- Scrollable Form + Metadata -->
			<form id="tx-edit-form" onsubmit={handleSave} class="flex-1 overflow-y-auto p-5 space-y-4">
				{#if error}
					<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
						{error}
					</div>
				{/if}

				<!-- Direction Switch -->
				<div class="grid grid-cols-2 p-1 rounded-xl bg-slate-900 border border-slate-800">
					<button
						type="button"
						onclick={() => (direction = 'outflow')}
						class="py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer {direction === 'outflow'
							? 'bg-rose-500/20 text-rose-300 border border-rose-500/35'
							: 'text-slate-400 hover:text-white border border-transparent'}"
					>
						<ArrowUpRight class="w-3.5 h-3.5" /> Expense
					</button>
					<button
						type="button"
						onclick={() => (direction = 'inflow')}
						class="py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer {direction === 'inflow'
							? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
							: 'text-slate-400 hover:text-white border border-transparent'}"
					>
						<ArrowDownRight class="w-3.5 h-3.5" /> Income
					</button>
				</div>

				<div>
					<label for="ed-merchant" class="block text-xs font-medium text-slate-300 mb-1">Merchant Name</label>
					<input
						id="ed-merchant"
						type="text"
						required
						bind:value={merchantClean}
						class="w-full px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="ed-amount" class="block text-xs font-medium text-slate-300 mb-1">
							Amount ({transaction.currency})
						</label>
						<input
							id="ed-amount"
							type="number"
							step="0.01"
							min="0.01"
							required
							bind:value={amount}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-800 text-sm font-mono-num font-semibold text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
					<div>
						<label for="ed-date" class="block text-xs font-medium text-slate-300 mb-1">Date</label>
						<input
							id="ed-date"
							type="date"
							required
							bind:value={occurredAt}
							class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="ed-acc" class="block text-xs font-medium text-slate-300 mb-1">Account</label>
						<select
							id="ed-acc"
							bind:value={accountId}
							class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							{#each accounts as acc}
								<option value={acc.id}>{acc.name} ({acc.currency})</option>
							{/each}
						</select>
					</div>
					<div>
						<label for="ed-cat" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
						<select
							id="ed-cat"
							bind:value={categoryId}
							class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							<option value="">Uncategorized</option>
							{#each categories as cat}
								<option value={cat.id}>{cat.name}</option>
							{/each}
						</select>
					</div>
				</div>

				<!-- 1-Click Automation Rule Card -->
				{#if selectedCategory && merchantClean.trim()}
					<div class="p-3 rounded-xl bg-cyan-500/8 border border-cyan-500/25 flex items-center justify-between gap-3">
						<div class="text-[11px] text-cyan-200 leading-snug">
							Always categorize <strong class="text-white">"{merchantClean.trim()}"</strong> as
							<strong class="text-cyan-300">{selectedCategory.name}</strong>?
						</div>
						{#if ruleCreated}
							<span class="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-300 shrink-0">
								<CheckCircle2 class="w-3.5 h-3.5" /> Rule Saved
							</span>
						{:else}
							<button
								type="button"
								disabled={creatingRule}
								onclick={handleCreateAutoRule}
								class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-200 text-[11px] font-semibold cursor-pointer shrink-0 disabled:opacity-50"
							>
								<Wand2 class="w-3 h-3" />
								{creatingRule ? 'Saving...' : 'Create Rule'}
							</button>
						{/if}
					</div>
				{/if}

				<!-- Notes -->
				<div>
					<label for="ed-notes" class="block text-xs font-medium text-slate-300 mb-1">Notes</label>
					<textarea
						id="ed-notes"
						rows={2}
						bind:value={notes}
						placeholder="Add a personal memo, receipt reference, or split note..."
						class="w-full px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
					></textarea>
				</div>

				<!-- Tags Editor -->
				<div class="space-y-2">
					<span class="flex items-center gap-1.5 text-xs font-medium text-slate-300">
						<Tag class="w-3.5 h-3.5 text-emerald-400" /> Tags
					</span>
					<div class="flex flex-wrap gap-1.5">
						{#each tags as t}
							<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-700 text-[11px] text-slate-200">
								#{t}
								<button
									type="button"
									onclick={() => removeTag(t)}
									class="text-slate-400 hover:text-rose-400 cursor-pointer"
									aria-label="Remove tag {t}"
								>
									×
								</button>
							</span>
						{/each}
					</div>
					<div class="flex items-center gap-2">
						<input
							type="text"
							bind:value={newTag}
							onkeydown={(e) => {
								if (e.key === 'Enter') {
									e.preventDefault();
									addTag();
								}
							}}
							placeholder="Add tag (e.g. work, reimbursable, travel)..."
							class="flex-1 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
						/>
						<button
							type="button"
							onclick={addTag}
							class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 font-medium cursor-pointer"
						>
							<Plus class="w-3.5 h-3.5" /> Add
						</button>
					</div>
				</div>

				<!-- Internal Transfer Toggle -->
				<label class="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-900/70 border border-slate-800 cursor-pointer">
					<div class="flex items-center gap-2.5 text-xs">
						<ArrowLeftRight class="w-4 h-4 text-slate-400" />
						<div>
							<div class="font-medium text-white">Internal Transfer</div>
							<div class="text-[11px] text-slate-400">Exclude from spending & income totals</div>
						</div>
					</div>
					<input type="checkbox" bind:checked={isTransfer} class="rounded border-slate-700" />
				</label>

				<!-- Raw Bank Memo Inspector -->
				<div class="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
					<div class="flex items-center justify-between text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
						<span class="flex items-center gap-1.5">
							<FileText class="w-3.5 h-3.5" /> Raw Bank Memo
						</span>
						{#if transaction.ai_confidence}
							<span class="font-mono-num text-emerald-400">
								AI {Math.round(Number.parseFloat(transaction.ai_confidence) * 100)}%
							</span>
						{/if}
					</div>
					<div class="text-xs font-mono-num text-slate-300 break-words">
						{transaction.merchant_raw}
					</div>
					{#if transaction.description && transaction.description !== transaction.merchant_raw}
						<div class="text-[11px] text-slate-400 leading-relaxed pt-1 border-t border-slate-800/80 break-words">
							{transaction.description}
						</div>
					{/if}
				</div>
			</form>

			<!-- Footer Actions -->
			<div class="p-4 border-t border-slate-800/80 bg-slate-950 flex items-center justify-between gap-2 shrink-0">
				<div class="flex items-center gap-1.5">
					<button
						type="button"
						onclick={() =>
							transaction &&
							goto(
								`/advisor?q=${encodeURIComponent(
									`Analyze all my spending history at "${transaction.merchant_clean}" — total spent, frequency, and whether it's trending up.`
								)}`
							)}
						class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold cursor-pointer"
					>
						<Sparkles class="w-3.5 h-3.5" /> Ask Luna
					</button>
					<button
						type="button"
						onclick={() => transaction && onRequestDelete(transaction)}
						class="p-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 cursor-pointer"
						title="Delete transaction"
						aria-label="Delete transaction"
					>
						<Trash2 class="w-4 h-4" />
					</button>
				</div>

				<button
					type="submit"
					form="tx-edit-form"
					disabled={saving}
					class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					<Save class="w-3.5 h-3.5" />
					{saving ? 'Saving...' : 'Save Changes'}
				</button>
			</div>
		</aside>
	</div>
{/if}
