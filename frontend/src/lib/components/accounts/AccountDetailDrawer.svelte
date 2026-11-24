<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import type { Account, Category, Transaction } from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import {
		X,
		UploadCloud,
		ArrowLeftRight,
		Scale,
		Sparkles,
		Pencil,
		Archive,
		RotateCcw,
		Trash2,
		ArrowUpRight,
		ArrowDownRight,
		Wallet,
		CreditCard,
		Landmark
	} from 'lucide-svelte';

	let {
		account = null,
		categoriesMap,
		privacyMode = false,
		onClose,
		onEdit,
		onTransfer,
		onReconcile,
		onToggleArchive,
		onRequestDelete
	}: {
		account: Account | null;
		categoriesMap: Map<string, Category>;
		privacyMode?: boolean;
		onClose: () => void;
		onEdit: (acc: Account) => void;
		onTransfer: (acc: Account) => void;
		onReconcile: (acc: Account) => void;
		onToggleArchive: (acc: Account) => void;
		onRequestDelete: (acc: Account) => void;
	} = $props();

	let txs = $state<Transaction[]>([]);
	let totalCount = $state(0);
	let loadingTxs = $state(false);

	$effect(() => {
		if (!account) {
			txs = [];
			totalCount = 0;
			return;
		}
		const accId = account.id;
		loadingTxs = true;
		api
			.listTransactions({ account_id: accId, limit: 30 })
			.then((res) => {
				if (account?.id === accId) {
					txs = res.items;
					totalCount = res.total;
				}
			})
			.catch(() => {
				txs = [];
				totalCount = 0;
			})
			.finally(() => {
				loadingTxs = false;
			});
	});

	let metrics = $derived.by(() => {
		if (!account) return { delta: 0, in30: 0, out30: 0 };
		const cur = Number.parseFloat(account.current_balance) || 0;
		const init = Number.parseFloat(account.initial_balance) || 0;
		const cutoff = new Date();
		cutoff.setDate(cutoff.getDate() - 30);
		let in30 = 0;
		let out30 = 0;
		for (const tx of txs) {
			if (tx.is_transfer) continue;
			const d = new Date(tx.occurred_at + 'T00:00:00');
			if (d >= cutoff) {
				const a = Number.parseFloat(tx.amount) || 0;
				if (tx.direction === 'inflow') in30 += a;
				else out30 += a;
			}
		}
		return { delta: cur - init, in30, out30 };
	});
</script>

{#if account}
	<div class="fixed inset-0 z-50 flex justify-end">
		<!-- Backdrop -->
		<button
			type="button"
			onclick={onClose}
			aria-label="Close account details"
			class="fixed inset-0 bg-black/65 backdrop-blur-xs cursor-pointer"
		></button>

		<!-- Right Slide-Over Panel -->
		<aside class="relative z-10 w-full max-w-md bg-slate-950 border-l border-slate-800/90 h-dvh flex flex-col shadow-2xl overflow-hidden">
			<!-- Branded Accent Bar -->
			<div class="h-1.5 w-full shrink-0" style="background-color: {account.color || '#10b981'}"></div>

			<!-- Header -->
			<div class="p-5 border-b border-slate-800/80 flex items-start justify-between gap-3 shrink-0">
				<div class="flex items-center gap-3 min-w-0">
					<div
						class="h-11 w-11 rounded-xl flex items-center justify-center border border-white/10 shrink-0"
						style="background-color: {account.color}22; color: {account.color}"
					>
						{#if account.type === 'credit'}
							<CreditCard class="w-5 h-5" />
						{:else if account.type === 'loan' || account.type === 'investment'}
							<Landmark class="w-5 h-5" />
						{:else}
							<Wallet class="w-5 h-5" />
						{/if}
					</div>
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<h2 class="text-base font-bold text-white truncate">{account.name}</h2>
							<span class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] font-mono-num text-slate-300">
								{account.currency}
							</span>
						</div>
						<div class="text-xs text-slate-400 capitalize mt-0.5 truncate">
							{account.type}{account.institution ? ` · ${account.institution}` : ''}
							{#if account.is_archived}
								<span class="ml-1.5 text-amber-400 font-semibold">· Archived</span>
							{/if}
						</div>
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

			<!-- Scrollable Body -->
			<div class="flex-1 overflow-y-auto p-5 space-y-5">
				<!-- Balance Hero -->
				<div class="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
					<div class="flex items-baseline justify-between gap-2">
						<div>
							<div class="text-[11px] text-slate-400">Live Balance</div>
							<div
								class="text-3xl font-bold font-mono-num mt-0.5 {Number.parseFloat(account.current_balance) < 0
									? 'text-rose-400'
									: 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
							>
								{formatMoney(account.current_balance, account.currency)}
							</div>
						</div>
						<div class="text-right">
							<div class="text-[10px] text-slate-500">Since Opening</div>
							<div
								class="text-xs font-mono-num font-semibold {metrics.delta >= 0
									? 'text-emerald-400'
									: 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
							>
								{metrics.delta >= 0 ? '+' : ''}{formatMoney(metrics.delta, account.currency)}
							</div>
						</div>
					</div>

					<div class="grid grid-cols-3 gap-2 pt-3 border-t border-slate-800/80 text-xs">
						<div>
							<div class="text-[10px] text-slate-500">Starting</div>
							<div class="font-mono-num text-slate-300 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(account.initial_balance, account.currency)}
							</div>
						</div>
						<div>
							<div class="text-[10px] text-slate-500">30d Inflow</div>
							<div class="font-mono-num text-emerald-400 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
								+{formatMoney(metrics.in30, account.currency)}
							</div>
						</div>
						<div>
							<div class="text-[10px] text-slate-500">30d Outflow</div>
							<div class="font-mono-num text-rose-400 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
								-{formatMoney(metrics.out30, account.currency)}
							</div>
						</div>
					</div>
				</div>

				<!-- 4 Quick Action Buttons -->
				<div class="grid grid-cols-2 gap-2">
					<a
						href="/imports?account={account.id}"
						class="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-orange-500/15 hover:bg-orange-500/25 border border-orange-500/30 text-orange-200 text-xs font-semibold transition"
					>
						<UploadCloud class="w-3.5 h-3.5 text-orange-400" />
						Import Statement
					</a>
					<button
						type="button"
						onclick={() => account && onTransfer(account)}
						class="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-200 text-xs font-semibold transition cursor-pointer"
					>
						<ArrowLeftRight class="w-3.5 h-3.5 text-cyan-400" />
						Transfer Money
					</button>
					<button
						type="button"
						onclick={() => account && onReconcile(account)}
						class="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition cursor-pointer"
					>
						<Scale class="w-3.5 h-3.5 text-emerald-400" />
						Reconcile Balance
					</button>
					<button
						type="button"
						onclick={() =>
							account &&
							goto(
								`/advisor?q=${encodeURIComponent(
									`Audit my "${account.name}" (${account.currency}) account activity, cash flow velocity, and top spending merchants.`
								)}`
							)}
						class="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-200 text-xs font-semibold transition cursor-pointer"
					>
						<Sparkles class="w-3.5 h-3.5 text-emerald-400" />
						Ask Luna
					</button>
				</div>

				<!-- Latest Transactions for this Account -->
				<div class="space-y-2.5">
					<div class="flex items-center justify-between">
						<h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400">
							Latest Activity ({totalCount})
						</h3>
						<a
							href="/transactions?account={account.id}"
							class="text-xs font-medium text-emerald-400 hover:text-emerald-300"
						>
							Open Full Ledger →
						</a>
					</div>

					{#if loadingTxs}
						<div class="space-y-2">
							{#each Array(4) as _}
								<div class="h-12 rounded-xl bg-slate-900/70 animate-pulse"></div>
							{/each}
						</div>
					{:else if txs.length === 0}
						<div class="p-6 rounded-xl bg-slate-900/50 border border-slate-800/80 text-center text-xs text-slate-500">
							No transactions posted on this account yet.
						</div>
					{:else}
						<div class="divide-y divide-slate-800/70 rounded-xl bg-slate-900/50 border border-slate-800/80 px-3.5">
							{#each txs.slice(0, 10) as tx}
								{@const cat = tx.category_id ? categoriesMap.get(tx.category_id) : null}
								<div class="py-2.5 flex items-center justify-between gap-2.5">
									<div class="flex items-center gap-2.5 min-w-0">
										<div
											class="h-7 w-7 rounded-lg flex items-center justify-center shrink-0 {tx.direction === 'inflow'
												? 'bg-emerald-500/15 text-emerald-400'
												: 'bg-slate-800 text-slate-300'}"
										>
											{#if tx.direction === 'inflow'}
												<ArrowDownRight class="w-3.5 h-3.5" />
											{:else}
												<ArrowUpRight class="w-3.5 h-3.5" />
											{/if}
										</div>
										<div class="min-w-0">
											<div class="text-xs font-medium text-white truncate">{tx.merchant_clean}</div>
											<div class="text-[10px] text-slate-400 flex items-center gap-1.5">
												<span>{formatDate(tx.occurred_at)}</span>
												{#if cat}
													<span style="color: {cat.color}">· {cat.name}</span>
												{/if}
											</div>
										</div>
									</div>
									<span
										class="text-xs font-mono-num font-semibold shrink-0 {tx.direction === 'inflow'
											? 'text-emerald-400'
											: 'text-slate-200'} {privacyMode ? 'privacy-blur' : ''}"
									>
										{tx.direction === 'inflow' ? '+' : '-'}{formatMoney(tx.amount, tx.currency)}
									</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Footer Lifecycle Actions -->
			<div class="p-4 border-t border-slate-800/80 bg-slate-950 flex items-center justify-between gap-2 shrink-0">
				<div class="flex items-center gap-2">
					<button
						type="button"
						onclick={() => account && onEdit(account)}
						class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 cursor-pointer"
					>
						<Pencil class="w-3.5 h-3.5" /> Edit
					</button>
					<button
						type="button"
						onclick={() => account && onToggleArchive(account)}
						class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 cursor-pointer"
					>
						{#if account.is_archived}
							<RotateCcw class="w-3.5 h-3.5 text-emerald-400" /> Restore
						{:else}
							<Archive class="w-3.5 h-3.5 text-amber-400" /> Archive
						{/if}
					</button>
				</div>
				<button
					type="button"
					onclick={() => account && onRequestDelete(account)}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-xs font-semibold text-rose-300 cursor-pointer"
				>
					<Trash2 class="w-3.5 h-3.5" /> Delete
				</button>
			</div>
		</aside>
	</div>
{/if}
