<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { PaperPortfolio, PaperPosition, QuantSignal } from '$lib/api/types';
	import { X, TrendingUp, TrendingDown, ShieldCheck, AlertTriangle } from 'lucide-svelte';

	interface Props {
		symbol: string | null;
		displayName?: string;
		livePrice: number;
		currency?: string;
		signal?: QuantSignal | null;
		portfolio: PaperPortfolio | null;
		initialSide?: 'buy' | 'sell';
		onClose: () => void;
		onTraded: (updated: PaperPortfolio, message: string) => void;
	}

	let {
		symbol,
		displayName = '',
		livePrice,
		currency = 'USD',
		signal = null,
		portfolio,
		initialSide = 'buy',
		onClose,
		onTraded
	}: Props = $props();

	let side = $state<'buy' | 'sell'>('buy');
	let usdAmount = $state('500');
	let sellQty = $state('');
	let stopLoss = $state('');
	let takeProfit = $state('');
	let rationale = $state('');
	let submitting = $state(false);
	let error = $state<string | null>(null);

	let openPos = $derived<PaperPosition | null>(
		symbol && portfolio ? portfolio.positions.find((p) => p.symbol === symbol) ?? null : null
	);
	let cashAvailable = $derived(portfolio ? Number.parseFloat(portfolio.cash_balance) || 0 : 0);

	$effect(() => {
		if (!symbol) return;
		side = initialSide;
		error = null;
		if (signal) {
			stopLoss = String(signal.stop_loss);
			takeProfit = String(signal.take_profit);
			rationale = signal.reasons[0] ?? '';
		} else {
			stopLoss = '';
			takeProfit = '';
			rationale = '';
		}
		if (initialSide === 'sell' && openPos) {
			sellQty = openPos.quantity;
		} else {
			usdAmount = String(Math.min(500, Math.max(100, Math.floor(cashAvailable))));
		}
	});

	let estimatedQty = $derived.by(() => {
		const amt = Number.parseFloat(usdAmount) || 0;
		if (livePrice <= 0 || amt <= 0) return 0;
		return amt / livePrice;
	});

	let estimatedSellUsd = $derived.by(() => {
		const q = Number.parseFloat(sellQty) || 0;
		return q * livePrice;
	});

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!symbol) return;
		submitting = true;
		error = null;
		try {
			const updated = await api.executePaperTrade(
				side === 'buy'
					? {
							symbol,
							side: 'buy',
							usd_amount: Number.parseFloat(usdAmount).toFixed(2),
							stop_loss: stopLoss ? stopLoss : null,
							take_profit: takeProfit ? takeProfit : null,
							rationale: rationale.trim() || null
						}
					: {
							symbol,
							side: 'sell',
							quantity: Number.parseFloat(sellQty).toFixed(6),
							rationale: rationale.trim() || null
						}
			);
			const summary =
				side === 'buy'
					? `Paper bought $${Number.parseFloat(usdAmount).toFixed(2)} of ${symbol} at ${livePrice} ${currency}.`
					: `Paper sold ${Number.parseFloat(sellQty).toFixed(4)} ${symbol} at ${livePrice} ${currency}.`;
			onTraded(updated, summary);
			onClose();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Paper trade failed';
		} finally {
			submitting = false;
		}
	}
</script>

{#if symbol}
	<div
		class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-label="Execute paper trade"
	>
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-slate-800 shadow-2xl">
			<div class="flex items-start justify-between gap-3">
				<div>
					<div class="flex items-center gap-2">
						<span class="px-2 py-0.5 rounded-md bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-[10px] font-semibold uppercase">
							Virtual Paper Trade
						</span>
						<span class="text-xs font-mono-num text-slate-400">
							{livePrice} {currency}
						</span>
					</div>
					<h2 class="text-lg font-bold text-white mt-1">
						{symbol} <span class="text-sm font-normal text-slate-400">{displayName}</span>
					</h2>
				</div>
				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			{#if error}
				<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start gap-2">
					<AlertTriangle class="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
					<span>{error}</span>
				</div>
			{/if}

			<!-- Buy / Sell Toggle -->
			<div class="grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-slate-950 border border-slate-800">
				<button
					type="button"
					onclick={() => (side = 'buy')}
					class="py-2 rounded-lg text-xs font-semibold inline-flex items-center justify-center gap-1.5 transition cursor-pointer {side === 'buy'
						? 'bg-emerald-500 text-slate-950'
						: 'text-slate-400 hover:text-white'}"
				>
					<TrendingUp class="w-3.5 h-3.5" /> Paper Buy
				</button>
				<button
					type="button"
					disabled={!openPos}
					onclick={() => {
						side = 'sell';
						if (openPos) sellQty = openPos.quantity;
					}}
					class="py-2 rounded-lg text-xs font-semibold inline-flex items-center justify-center gap-1.5 transition cursor-pointer disabled:opacity-40 {side === 'sell'
						? 'bg-rose-500 text-white'
						: 'text-slate-400 hover:text-white'}"
				>
					<TrendingDown class="w-3.5 h-3.5" /> Paper Sell
				</button>
			</div>

			<form onsubmit={handleSubmit} class="space-y-4">
				{#if side === 'buy'}
					<div class="space-y-2">
						<div class="flex items-center justify-between text-xs">
							<label for="pt-usd" class="font-medium text-slate-300">Order Amount (USD)</label>
							<span class="text-slate-400 font-mono-num">
								Cash: <strong class="text-emerald-300">${cashAvailable.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
							</span>
						</div>
						<input
							id="pt-usd"
							type="number"
							step="1"
							min="10"
							max={cashAvailable}
							required
							bind:value={usdAmount}
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono-num text-white focus:outline-none focus:border-emerald-500"
						/>
						<div class="flex flex-wrap gap-1.5">
							{#each [250, 500, 1000, 2500] as preset}
								<button
									type="button"
									disabled={preset > cashAvailable}
									onclick={() => (usdAmount = String(preset))}
									class="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] font-mono-num text-slate-300 cursor-pointer disabled:opacity-35"
								>
									${preset}
								</button>
							{/each}
							<button
								type="button"
								onclick={() => (usdAmount = String(Math.floor(cashAvailable)))}
								class="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] font-semibold text-emerald-300 cursor-pointer"
							>
								Max
							</button>
						</div>
						<div class="text-[11px] text-slate-400 font-mono-num">
							Est. units: <strong class="text-white">{estimatedQty.toFixed(4)} {symbol}</strong>
						</div>
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="pt-sl" class="block text-[11px] text-slate-400 mb-1">Stop-Loss (Quant)</label>
							<input
								id="pt-sl"
								type="number"
								step="0.0001"
								bind:value={stopLoss}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-rose-300 focus:outline-none focus:border-rose-500"
							/>
						</div>
						<div>
							<label for="pt-tp" class="block text-[11px] text-slate-400 mb-1">Take-Profit (Quant)</label>
							<input
								id="pt-tp"
								type="number"
								step="0.0001"
								bind:value={takeProfit}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-emerald-300 focus:outline-none focus:border-emerald-500"
							/>
						</div>
					</div>
				{:else if openPos}
					<div class="space-y-2">
						<div class="flex items-center justify-between text-xs">
							<label for="pt-qty" class="font-medium text-slate-300">Quantity to Sell</label>
							<span class="text-slate-400 font-mono-num">
								Held: <strong class="text-white">{Number.parseFloat(openPos.quantity).toFixed(4)}</strong>
							</span>
						</div>
						<input
							id="pt-qty"
							type="number"
							step="0.0001"
							min="0.0001"
							max={Number.parseFloat(openPos.quantity)}
							required
							bind:value={sellQty}
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono-num text-white focus:outline-none focus:border-rose-500"
						/>
						<div class="flex gap-1.5">
							{#each [
								{ label: '25%', mult: 0.25 },
								{ label: '50%', mult: 0.5 },
								{ label: '100% Close', mult: 1 }
							] as frac}
								<button
									type="button"
									onclick={() =>
										(sellQty = (Number.parseFloat(openPos!.quantity) * frac.mult).toFixed(6))}
									class="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] font-semibold text-slate-300 cursor-pointer"
								>
									{frac.label}
								</button>
							{/each}
						</div>
						<div class="text-[11px] text-slate-400 font-mono-num">
							Est. proceeds: <strong class="text-emerald-300">${estimatedSellUsd.toFixed(2)}</strong>
						</div>
					</div>
				{/if}

				<div>
					<label for="pt-note" class="block text-[11px] text-slate-400 mb-1">Trade Journal Note</label>
					<input
						id="pt-note"
						type="text"
						bind:value={rationale}
						placeholder="Why are you taking this paper trade?"
						class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/80 text-[11px] text-slate-400 flex items-center gap-2">
					<ShieldCheck class="w-4 h-4 text-cyan-400 shrink-0" />
					<span>Simulated paper trade using virtual funds — zero real brokerage execution or risk.</span>
				</div>

				<div class="flex items-center justify-end gap-2 pt-1">
					<button
						type="button"
						onclick={onClose}
						class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={submitting}
						class="px-5 py-2.5 rounded-xl font-semibold text-xs cursor-pointer disabled:opacity-50 {side === 'buy'
							? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950'
							: 'bg-rose-500 hover:bg-rose-400 text-white'}"
					>
						{submitting
							? 'Executing...'
							: side === 'buy'
								? `Confirm Paper Buy`
								: `Confirm Paper Sell`}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
