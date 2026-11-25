<script lang="ts">
	import { onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type {
		Account,
		Category,
		ParsedVoiceTransaction,
		VoiceLanguage
	} from '$lib/api/types';
	import { startAudioRecording, type ActiveRecorder } from '$lib/utils/voice';
	import {
		Mic,
		Square,
		X,
		Sparkles,
		CheckCircle2,
		AlertTriangle,
		ArrowDownRight,
		ArrowUpRight,
		ArrowRight,
		Wand2
	} from 'lucide-svelte';

	interface Props {
		open: boolean;
		onClose: () => void;
		onSaved?: () => void;
	}

	let { open, onClose, onSaved }: Props = $props();

	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let loadedMeta = $state(false);

	let language = $state<VoiceLanguage>('auto');
	let recording = $state(false);
	let recordSeconds = $state(0);
	let processing = $state(false);
	let saving = $state(false);

	let transcript = $state('');
	let parsed = $state<ParsedVoiceTransaction | null>(null);

	// Editable confirmation fields
	let editAmount = $state('');
	let editDirection = $state<'inflow' | 'outflow'>('outflow');
	let editMerchant = $state('');
	let editAccountId = $state('');
	let editCategoryId = $state('');
	let editDate = $state('');
	let editNotes = $state('');

	let error = $state<string | null>(null);
	let savedBanner = $state<string | null>(null);

	let activeRecorder: ActiveRecorder | null = null;
	let timerHandle: ReturnType<typeof setInterval> | undefined;

	const QUICK_EXAMPLES = [
		'Spent 18 lari at Entree on coffee from BOG',
		'დავხარჯე 45 ლარი კარფურში BOG ბარათით',
		"Hey Luna, what's NVDA doing today and how much safe-to-spend do I have left?"
	];

	async function ensureMetaLoaded() {
		if (loadedMeta) return;
		try {
			const [accs, cats] = await Promise.all([api.listAccounts(), api.listCategories()]);
			accounts = accs;
			categories = cats;
			loadedMeta = true;
		} catch {
			// non-fatal
		}
	}

	$effect(() => {
		if (open) {
			error = null;
			savedBanner = null;
			ensureMetaLoaded();
		} else {
			cleanupRecording();
		}
	});

	function cleanupRecording() {
		if (timerHandle) {
			clearInterval(timerHandle);
			timerHandle = undefined;
		}
		if (activeRecorder) {
			activeRecorder.cancel();
			activeRecorder = null;
		}
		recording = false;
		recordSeconds = 0;
	}

	onDestroy(cleanupRecording);

	function hydrateParsed(res: ParsedVoiceTransaction) {
		parsed = res;
		editAmount = res.amount ?? '';
		editDirection = res.direction;
		editMerchant = res.merchant;
		editAccountId = res.account_id ?? accounts[0]?.id ?? '';
		editCategoryId = res.category_id ?? '';
		editDate = res.occurred_at;
		editNotes = res.notes ?? '';
	}

	async function runParse(text: string) {
		const clean = text.trim();
		if (!clean) return;
		processing = true;
		error = null;
		savedBanner = null;
		try {
			await ensureMetaLoaded();
			const res = await api.voiceParseTransaction(clean, language);
			hydrateParsed(res);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Could not parse voice command';
		} finally {
			processing = false;
		}
	}

	async function toggleRecording() {
		error = null;
		savedBanner = null;

		if (recording && activeRecorder) {
			if (timerHandle) {
				clearInterval(timerHandle);
				timerHandle = undefined;
			}
			recording = false;
			processing = true;
			try {
				const blob = await activeRecorder.stop();
				activeRecorder = null;
				const tr = await api.voiceTranscribe(blob, language);
				transcript = tr.transcript;
				await runParse(tr.transcript);
			} catch (e) {
				error = e instanceof Error ? e.message : 'Voice transcription failed';
				processing = false;
			}
			return;
		}

		try {
			parsed = null;
			recordSeconds = 0;
			activeRecorder = await startAudioRecording();
			recording = true;
			timerHandle = setInterval(() => {
				recordSeconds += 1;
				if (recordSeconds >= 45 && recording) {
					toggleRecording();
				}
			}, 1000);
		} catch (e) {
			error =
				e instanceof Error
					? e.message
					: 'Microphone permission denied. You can also type or paste below.';
		}
	}

	async function handleSaveTransaction(e: SubmitEvent) {
		e.preventDefault();
		if (!editAccountId || !editAmount || !editMerchant.trim()) return;
		saving = true;
		error = null;
		try {
			await api.createTransaction({
				account_id: editAccountId,
				category_id: editCategoryId || null,
				amount: Number.parseFloat(editAmount).toFixed(2),
				direction: editDirection,
				occurred_at: editDate,
				merchant: editMerchant.trim(),
				notes: editNotes.trim() || undefined,
				tags: ['voice']
			});
			const acc = accounts.find((a) => a.id === editAccountId);
			savedBanner = `Saved ${editDirection === 'inflow' ? '+' : '-'}${editAmount} ${acc?.currency ?? parsed?.currency ?? ''} at ${editMerchant}!`;
			parsed = null;
			transcript = '';
			onSaved?.();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to save transaction';
		} finally {
			saving = false;
		}
	}

	function openInLunaHandsFree() {
		const q = (parsed?.transcript || transcript).trim();
		if (!q) return;
		onClose();
		goto(`/advisor?q=${encodeURIComponent(q)}&voice=1`);
	}

	function formatTimer(sec: number): string {
		const m = Math.floor(sec / 60);
		const s = sec % 60;
		return `${m}:${s < 10 ? '0' : ''}${s}`;
	}
</script>

{#if open}
	<div
		class="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-label="Voice-to-Ledger and Talk to Luna"
	>
		<div class="card-surface rounded-3xl w-full max-w-lg max-h-[92dvh] overflow-y-auto p-6 space-y-5 border border-emerald-500/30 shadow-2xl">
			<!-- Header -->
			<div class="flex items-start justify-between gap-3">
				<div>
					<div class="flex items-center gap-2">
						<span class="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/35 text-emerald-300 text-[10px] font-semibold uppercase">
							EN + ქართული Voice AI
						</span>
					</div>
					<h2 class="text-lg font-bold text-white mt-1">Voice-to-Ledger & Talk to Luna</h2>
					<p class="text-xs text-slate-400">
						Speak an expense to log it instantly, or ask Luna anything hands-free.
					</p>
				</div>
				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-4 h-4" />
				</button>
			</div>

			<!-- Language Selector -->
			<div class="grid grid-cols-3 gap-1.5 p-1 rounded-xl bg-slate-950 border border-slate-800 text-xs">
				{#each [
					{ id: 'auto', label: 'Auto (EN + KA)' },
					{ id: 'en', label: 'English' },
					{ id: 'ka', label: 'ქართული' }
				] as opt}
					<button
						type="button"
						onclick={() => (language = opt.id as VoiceLanguage)}
						class="py-1.5 rounded-lg font-semibold transition cursor-pointer {language === opt.id
							? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
							: 'text-slate-400 hover:text-white border border-transparent'}"
					>
						{opt.label}
					</button>
				{/each}
			</div>

			{#if error}
				<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start gap-2">
					<AlertTriangle class="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
					<span>{error}</span>
				</div>
			{/if}

			{#if savedBanner}
				<div class="p-3.5 rounded-xl bg-emerald-500/12 border border-emerald-500/35 text-emerald-200 text-xs flex items-center justify-between gap-2">
					<div class="flex items-center gap-2">
						<CheckCircle2 class="w-4 h-4 text-emerald-400 shrink-0" />
						<span class="font-medium">{savedBanner}</span>
					</div>
					<a href="/transactions" onclick={onClose} class="text-emerald-300 underline font-semibold shrink-0">
						View Ledger
					</a>
				</div>
			{/if}

			<!-- Animated Mic Orb -->
			<div class="py-3 flex flex-col items-center text-center space-y-3">
				<div class="relative flex items-center justify-center">
					{#if recording}
						<span class="absolute h-28 w-28 rounded-full bg-rose-500/20 animate-ping"></span>
						<span class="absolute h-24 w-24 rounded-full bg-rose-500/15 animate-pulse"></span>
					{:else if processing}
						<span class="absolute h-24 w-24 rounded-full border-2 border-cyan-400/50 border-t-transparent animate-spin"></span>
					{/if}
					<button
						type="button"
						disabled={processing}
						onclick={toggleRecording}
						aria-label={recording ? 'Stop recording' : 'Start voice recording'}
						class="relative z-10 h-20 w-20 rounded-full flex items-center justify-center transition-all cursor-pointer shadow-xl disabled:opacity-60 {recording
							? 'bg-rose-500 hover:bg-rose-400 text-white scale-105 shadow-rose-500/35'
							: 'bg-gradient-to-br from-emerald-400 to-cyan-500 hover:from-emerald-300 hover:to-cyan-400 text-slate-950 shadow-emerald-500/25'}"
					>
						{#if recording}
							<Square class="w-7 h-7 fill-current" />
						{:else}
							<Mic class="w-8 h-8" />
						{/if}
					</button>
				</div>

				<div class="text-xs font-semibold {recording ? 'text-rose-300' : processing ? 'text-cyan-300' : 'text-slate-300'}">
					{#if recording}
						Listening... <span class="font-mono-num">{formatTimer(recordSeconds)}</span> · Tap to stop
					{:else if processing}
						Transcribing & understanding your voice...
					{:else}
						Tap the microphone and speak naturally
					{/if}
				</div>
			</div>

			<!-- Transcript Input + Quick Examples -->
			<form
				onsubmit={(e) => {
					e.preventDefault();
					runParse(transcript);
				}}
				class="space-y-2.5"
			>
				<div class="flex gap-2">
					<input
						type="text"
						bind:value={transcript}
						placeholder='Or type: "Spent 18 lari at Entree on coffee from BOG"'
						class="flex-1 px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
					/>
					<button
						type="submit"
						disabled={processing || !transcript.trim()}
						class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-40"
					>
						<Wand2 class="w-3.5 h-3.5 text-cyan-400" /> Parse
					</button>
				</div>

				{#if !parsed}
					<div class="space-y-1.5">
						<div class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
							Try saying or tap an example:
						</div>
						<div class="flex flex-wrap gap-1.5">
							{#each QUICK_EXAMPLES as ex}
								<button
									type="button"
									onclick={() => {
										transcript = ex;
										runParse(ex);
									}}
									class="text-left px-2.5 py-1.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-300 transition cursor-pointer"
								>
									"{ex}"
								</button>
							{/each}
						</div>
					</div>
				{/if}
			</form>

			<!-- Instant Structured Confirmation Card -->
			{#if parsed}
				{#if parsed.intent === 'ask_luna'}
					<div class="p-4 rounded-2xl bg-gradient-to-br from-violet-950/50 via-slate-900 to-cyan-950/30 border border-violet-500/35 space-y-3">
						<div class="flex items-center gap-2 text-xs font-semibold text-violet-300">
							<Sparkles class="w-4 h-4" />
							Detected Question for Luna Personal CFO
						</div>
						<p class="text-sm text-white leading-relaxed">"{parsed.transcript}"</p>
						<button
							type="button"
							onclick={openInLunaHandsFree}
							class="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold inline-flex items-center justify-center gap-2 cursor-pointer transition"
						>
							Ask Luna (Hands-Free Spoken Reply)
							<ArrowRight class="w-4 h-4" />
						</button>
					</div>
				{:else}
					<form onsubmit={handleSaveTransaction} class="p-4 rounded-2xl bg-slate-900/75 border border-emerald-500/35 space-y-3.5">
						<div class="flex items-center justify-between gap-2">
							<span class="text-xs font-bold text-emerald-300 inline-flex items-center gap-1.5">
								<CheckCircle2 class="w-4 h-4" /> Ready to Save to Ledger
							</span>
							<div class="inline-flex p-0.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px]">
								<button
									type="button"
									onclick={() => (editDirection = 'outflow')}
									class="px-2 py-0.5 rounded-md font-semibold inline-flex items-center gap-1 cursor-pointer {editDirection === 'outflow'
										? 'bg-rose-500/20 text-rose-300'
										: 'text-slate-400'}"
								>
									<ArrowUpRight class="w-3 h-3" /> Expense
								</button>
								<button
									type="button"
									onclick={() => (editDirection = 'inflow')}
									class="px-2 py-0.5 rounded-md font-semibold inline-flex items-center gap-1 cursor-pointer {editDirection === 'inflow'
										? 'bg-emerald-500/20 text-emerald-300'
										: 'text-slate-400'}"
								>
									<ArrowDownRight class="w-3 h-3" /> Income
								</button>
							</div>
						</div>

						<div class="grid grid-cols-2 gap-2.5">
							<div>
								<label for="vl-amt" class="block text-[10px] text-slate-400 mb-1">
									Amount ({parsed.currency})
								</label>
								<input
									id="vl-amt"
									type="number"
									step="0.01"
									min="0.01"
									required
									bind:value={editAmount}
									class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono-num text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>
							<div>
								<label for="vl-date" class="block text-[10px] text-slate-400 mb-1">Date</label>
								<input
									id="vl-date"
									type="date"
									required
									bind:value={editDate}
									class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>
						</div>

						<div>
							<label for="vl-merch" class="block text-[10px] text-slate-400 mb-1">Merchant</label>
							<input
								id="vl-merch"
								type="text"
								required
								bind:value={editMerchant}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
							/>
						</div>

						<div class="grid grid-cols-2 gap-2.5">
							<div>
								<label for="vl-acc" class="block text-[10px] text-slate-400 mb-1">Account</label>
								<select
									id="vl-acc"
									required
									bind:value={editAccountId}
									class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								>
									{#each accounts as acc}
										<option value={acc.id}>{acc.name} ({acc.currency})</option>
									{/each}
								</select>
							</div>
							<div>
								<label for="vl-cat" class="block text-[10px] text-slate-400 mb-1">Category</label>
								<select
									id="vl-cat"
									bind:value={editCategoryId}
									class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
								>
									<option value="">Uncategorized</option>
									{#each categories as cat}
										<option value={cat.id}>{cat.name}</option>
									{/each}
								</select>
							</div>
						</div>

						<div class="flex items-center justify-between gap-2 pt-1">
							<button
								type="button"
								onclick={openInLunaHandsFree}
								class="text-[11px] text-violet-300 hover:text-violet-200 font-medium cursor-pointer"
							>
								Ask Luna instead →
							</button>
							<button
								type="submit"
								disabled={saving || !editAccountId}
								class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
							>
								<CheckCircle2 class="w-3.5 h-3.5" />
								{saving ? 'Saving...' : 'Confirm & Save to Ledger'}
							</button>
						</div>
					</form>
				{/if}
			{/if}
		</div>
	</div>
{/if}
