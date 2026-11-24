<script lang="ts">
	import type { Category, StagedTransaction } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import {
		X,
		CheckCircle2,
		AlertTriangle,
		ArrowDownRight,
		ArrowUpRight,
		Sparkles,
		Copy,
		Check,
		Wand2,
		FileCode2
	} from 'lucide-svelte';

	export interface StagedRowEdit {
		user_approved: boolean;
		merchant_clean: string;
		category_id: string;
		direction: 'inflow' | 'outflow';
		amount: string;
		occurred_at: string;
		description: string;
	}

	interface Props {
		row: StagedTransaction | null;
		edit: StagedRowEdit | null;
		categories: Category[];
		readonly?: boolean;
		matchingMerchantCount?: number;
		privacyMode?: boolean;
		onClose: () => void;
		onApplyToMatching?: (merchantRaw: string, merchantClean: string, categoryId: string) => void;
	}

	let {
		row,
		edit = $bindable(),
		categories,
		readonly = false,
		matchingMerchantCount = 0,
		privacyMode = false,
		onClose,
		onApplyToMatching
	}: Props = $props();

	let copiedRaw = $state(false);

	function copyRaw() {
		if (!row) return;
		navigator.clipboard?.writeText(row.merchant_raw);
		copiedRaw = true;
		setTimeout(() => (copiedRaw = false), 1500);
	}

	function sourceLabel(src: string): { label: string; desc: string; tone: string } {
		if (src === 'bog_mcc')
			return {
				label: 'BOG ISO MCC',
				desc: 'Matched deterministically via Bank of Georgia merchant category code (0 AI tokens).',
				tone: 'bg-orange-500/15 text-orange-300 border-orange-500/30'
			};
		if (src === 'bog_rule')
			return {
				label: 'BOG Georgian Rule',
				desc: 'Matched via Bank of Georgia transfer, fee, or Georgian merchant rule (0 AI tokens).',
				tone: 'bg-orange-500/15 text-orange-300 border-orange-500/30'
			};
		if (src === 'rule')
			return {
				label: 'Personal Rule',
				desc: 'Matched one of your saved deterministic categorization rules.',
				tone: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
			};
		if (src === 'vector')
			return {
				label: 'Upstash Vector Memory',
				desc: 'Recalled from a merchant category you previously confirmed.',
				tone: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'
			};
		if (src === 'llm')
			return {
				label: 'AI Classifier',
				desc: 'Categorized by Financinio AI from merchant & description context.',
				tone: 'bg-violet-500/15 text-violet-300 border-violet-500/30'
			};
		return {
			label: src.toUpperCase(),
			desc: 'Heuristic classification — verify before committing.',
			tone: 'bg-slate-800 text-slate-300 border-slate-700'
		};
	}

	let confPct = $derived(row ? Math.round(Number.parseFloat(row.confidence || '0') * 100) : 0);
	let srcMeta = $derived(row ? sourceLabel(row.categorization_source) : null);
	let selectedCategoryName = $derived(
		edit?.category_id ? categories.find((c) => c.id === edit?.category_id)?.name ?? '' : ''
	);
</script>

{#if row && edit}
	<!-- Backdrop -->
	<div
		class="fixed inset-0 z-50 bg-black/65 backdrop-blur-xs flex justify-end"
		role="dialog"
		aria-modal="true"
		aria-label="Inspect staged transaction"
	>
		<button
			type="button"
			class="flex-1 cursor-default"
			aria-label="Close drawer"
			onclick={onClose}
		></button>

		<div
			class="w-full max-w-lg bg-slate-950 border-l border-slate-800/90 h-full overflow-y-auto flex flex-col shadow-2xl"
		>
			<!-- Header -->
			<div class="sticky top-0 z-10 bg-slate-950/95 backdrop-blur-md px-5 py-4 border-b border-slate-800/80 flex items-center justify-between gap-3">
				<div class="min-w-0">
					<div class="flex items-center gap-2">
						<span class="text-xs font-semibold uppercase tracking-wider text-slate-400">
							Staged Row Inspector
						</span>
						{#if row.is_duplicate}
							<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
								DUPLICATE
							</span>
						{/if}
					</div>
					<h3 class="text-base font-semibold text-white truncate mt-0.5">
						{edit.merchant_clean || row.merchant_clean}
					</h3>
				</div>
				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition cursor-pointer"
				>
					<X class="w-4 h-4" />
				</button>
			</div>

			<!-- Body -->
			<div class="p-5 space-y-5 flex-1">
				<!-- Amount & Status Hero -->
				<div class="p-4 rounded-2xl bg-slate-900/70 border border-slate-800/80 flex items-center justify-between gap-4">
					<div class="flex items-center gap-3">
						<div
							class="h-11 w-11 rounded-xl flex items-center justify-center border {edit.direction === 'inflow'
								? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
								: 'bg-rose-500/15 border-rose-500/30 text-rose-400'}"
						>
							{#if edit.direction === 'inflow'}
								<ArrowDownRight class="w-5 h-5" />
							{:else}
								<ArrowUpRight class="w-5 h-5" />
							{/if}
						</div>
						<div>
							<div class="text-[11px] uppercase tracking-wider text-slate-400">
								{edit.direction === 'inflow' ? 'Incoming Credit' : 'Outgoing Charge'}
							</div>
							<div
								class="text-xl font-bold font-mono-num {privacyMode ? 'privacy-blur' : ''} {edit.direction === 'inflow'
									? 'text-emerald-400'
									: 'text-white'}"
							>
								{edit.direction === 'inflow' ? '+' : '-'}{formatMoney(edit.amount || row.amount, row.currency)}
							</div>
						</div>
					</div>

					<label
						class="inline-flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-semibold transition {readonly
							? 'opacity-70 cursor-not-allowed'
							: 'cursor-pointer'} {edit.user_approved
							? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300'
							: 'bg-slate-950 border-slate-800 text-slate-400'}"
					>
						<input
							type="checkbox"
							disabled={readonly}
							bind:checked={edit.user_approved}
							class="rounded border-slate-700 accent-emerald-500"
						/>
						{edit.user_approved ? 'Approved' : 'Skipped'}
					</label>
				</div>

				<!-- AI Classification Card -->
				{#if srcMeta}
					<div class="p-4 rounded-2xl bg-slate-900/50 border border-slate-800/80 space-y-2.5">
						<div class="flex items-center justify-between gap-2">
							<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border {srcMeta.tone}">
								<Sparkles class="w-3 h-3" />
								{srcMeta.label}
							</span>
							<span
								class="text-xs font-mono-num font-semibold {confPct >= 80
									? 'text-emerald-400'
									: confPct >= 60
										? 'text-amber-300'
										: 'text-rose-300'}"
							>
								{confPct}% confidence
							</span>
						</div>
						<div class="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
							<div
								class="h-full rounded-full transition-all {confPct >= 80
									? 'bg-emerald-400'
									: confPct >= 60
										? 'bg-amber-400'
										: 'bg-rose-400'}"
								style="width: {Math.min(100, Math.max(5, confPct))}%"
							></div>
						</div>
						<p class="text-xs text-slate-400 leading-relaxed">{srcMeta.desc}</p>
					</div>
				{/if}

				{#if row.is_duplicate}
					<div class="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-2.5 text-xs text-amber-200">
						<AlertTriangle class="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
						<div>
							<div class="font-semibold text-amber-100">Duplicate Fingerprint Detected</div>
							<p class="text-amber-200/80 mt-0.5">
								A transaction with the same date, amount, direction, and raw merchant already exists in this account. Leave skipped unless this is genuinely a second identical charge.
							</p>
						</div>
					</div>
				{/if}

				<!-- Editable Fields -->
				<div class="space-y-4">
					<div>
						<label for="drawer-merchant" class="block text-xs font-medium text-slate-300 mb-1.5">
							Clean Merchant Name
						</label>
						<input
							id="drawer-merchant"
							type="text"
							disabled={readonly}
							bind:value={edit.merchant_clean}
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500 disabled:opacity-60"
						/>
					</div>

					<div>
						<label for="drawer-cat" class="block text-xs font-medium text-slate-300 mb-1.5">
							Category
						</label>
						<select
							id="drawer-cat"
							disabled={readonly}
							bind:value={edit.category_id}
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500 disabled:opacity-60"
						>
							<option value="">Uncategorized</option>
							{#each categories as cat}
								<option value={cat.id}>{cat.name} ({cat.kind})</option>
							{/each}
						</select>

						{#if !readonly && matchingMerchantCount > 1 && onApplyToMatching}
							<button
								type="button"
								onclick={() => onApplyToMatching(row.merchant_raw, edit!.merchant_clean, edit!.category_id)}
								class="mt-2 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-cyan-500/12 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-200 text-xs font-semibold transition cursor-pointer"
							>
								<Wand2 class="w-3.5 h-3.5" />
								Apply "{selectedCategoryName || 'Uncategorized'}" & clean name to all {matchingMerchantCount} matching rows
							</button>
						{/if}
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="drawer-amount" class="block text-xs font-medium text-slate-300 mb-1.5">
								Amount ({row.currency})
							</label>
							<input
								id="drawer-amount"
								type="number"
								step="0.01"
								min="0.01"
								disabled={readonly}
								bind:value={edit.amount}
								class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-sm font-mono-num text-white focus:outline-none focus:border-emerald-500 disabled:opacity-60"
							/>
						</div>
						<div>
							<label for="drawer-date" class="block text-xs font-medium text-slate-300 mb-1.5">
								Date
							</label>
							<input
								id="drawer-date"
								type="date"
								disabled={readonly}
								bind:value={edit.occurred_at}
								class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-sm font-mono-num text-white focus:outline-none focus:border-emerald-500 disabled:opacity-60"
							/>
						</div>
					</div>

					<div>
						<span class="block text-xs font-medium text-slate-300 mb-1.5">Direction</span>
						<div class="grid grid-cols-2 gap-2">
							<button
								type="button"
								disabled={readonly}
								onclick={() => {
									if (edit) edit.direction = 'outflow';
								}}
								class="flex items-center justify-center gap-1.5 py-2.5 rounded-xl border text-xs font-semibold transition cursor-pointer disabled:opacity-60 {edit.direction === 'outflow'
									? 'bg-rose-500/15 border-rose-500/40 text-rose-300'
									: 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'}"
							>
								<ArrowUpRight class="w-3.5 h-3.5" />
								Outflow (Expense)
							</button>
							<button
								type="button"
								disabled={readonly}
								onclick={() => {
									if (edit) edit.direction = 'inflow';
								}}
								class="flex items-center justify-center gap-1.5 py-2.5 rounded-xl border text-xs font-semibold transition cursor-pointer disabled:opacity-60 {edit.direction === 'inflow'
									? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
									: 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'}"
							>
								<ArrowDownRight class="w-3.5 h-3.5" />
								Inflow (Income)
							</button>
						</div>
					</div>

					<div>
						<label for="drawer-desc" class="block text-xs font-medium text-slate-300 mb-1.5">
							Description / Memo
						</label>
						<textarea
							id="drawer-desc"
							rows="3"
							disabled={readonly}
							bind:value={edit.description}
							placeholder="Optional note or bank narrative..."
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-60 resize-none"
						></textarea>
					</div>

					<!-- Raw Bank Text Audit Box -->
					<div class="p-3.5 rounded-xl bg-slate-900/70 border border-slate-800/80 space-y-1.5">
						<div class="flex items-center justify-between">
							<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
								<FileCode2 class="w-3.5 h-3.5" />
								Raw Bank Statement Text
							</span>
							<button
								type="button"
								onclick={copyRaw}
								class="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-white cursor-pointer"
							>
								{#if copiedRaw}
									<Check class="w-3 h-3 text-emerald-400" />
									Copied
								{:else}
									<Copy class="w-3 h-3" />
									Copy
								{/if}
							</button>
						</div>
						<p class="text-xs font-mono text-slate-300 break-words leading-relaxed">
							{row.merchant_raw}
						</p>
					</div>
				</div>
			</div>

			<!-- Footer -->
			<div class="sticky bottom-0 bg-slate-950/95 backdrop-blur-md px-5 py-4 border-t border-slate-800/80 flex items-center justify-between gap-3">
				<span class="text-xs text-slate-400">
					{readonly ? 'Already committed to ledger' : 'Changes apply when you commit batch'}
				</span>
				<button
					type="button"
					onclick={onClose}
					class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold transition cursor-pointer"
				>
					<CheckCircle2 class="w-3.5 h-3.5" />
					Done
				</button>
			</div>
		</div>
	</div>
{/if}
