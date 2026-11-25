<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type {
		EmailDigestPreview,
		EmailDigestType,
		EmailPreferences
	} from '$lib/api/types';
	import { formatDate } from '$lib/utils/format';
	import {
		Mail,
		Send,
		Calendar,
		Sparkles,
		CheckCircle2,
		AlertTriangle,
		RefreshCw
	} from 'lucide-svelte';

	interface Props {
		onNotice: (msg: string) => void;
		onError: (msg: string) => void;
	}

	let { onNotice, onError }: Props = $props();

	let prefs = $state<EmailPreferences | null>(null);
	let loadingPrefs = $state(true);
	let savingPref = $state(false);
	let sendingType = $state<EmailDigestType | null>(null);

	let previewType = $state<EmailDigestType>('weekly');
	let preview = $state<EmailDigestPreview | null>(null);
	let loadingPreview = $state(false);

	async function loadPreview(type: EmailDigestType) {
		previewType = type;
		loadingPreview = true;
		try {
			preview = await api.previewEmailDigest(type);
		} catch (e) {
			onError(e instanceof ApiError ? e.message : 'Failed to load email preview');
		} finally {
			loadingPreview = false;
		}
	}

	onMount(async () => {
		loadingPrefs = true;
		try {
			const [p, prev] = await Promise.all([
				api.getEmailPreferences(),
				api.previewEmailDigest('weekly')
			]);
			prefs = p;
			preview = prev;
		} catch (e) {
			onError(e instanceof ApiError ? e.message : 'Failed to load email digest settings');
		} finally {
			loadingPrefs = false;
		}
	});

	async function togglePreference(field: 'email_weekly_briefing' | 'email_monthly_wrapped') {
		if (!prefs || savingPref) return;
		savingPref = true;
		try {
			const nextVal = !prefs[field];
			prefs = await api.updateEmailPreferences({ [field]: nextVal });
			onNotice(
				field === 'email_weekly_briefing'
					? `Monday Weekly Briefing ${nextVal ? 'enabled' : 'paused'}.`
					: `Monthly CFO Wrapped ${nextVal ? 'enabled' : 'paused'}.`
			);
		} catch (e) {
			onError(e instanceof ApiError ? e.message : 'Could not update email preference');
		} finally {
			savingPref = false;
		}
	}

	async function sendDigestNow(type: EmailDigestType) {
		sendingType = type;
		try {
			const res = await api.sendEmailDigestNow(type);
			prefs = await api.getEmailPreferences();
			onNotice(`Sent "${res.subject}" to ${res.recipient}!`);
		} catch (e) {
			onError(e instanceof ApiError ? e.message : 'Failed to send email via Resend');
		} finally {
			sendingType = null;
		}
	}
</script>

<div class="space-y-6">
	<!-- Resend Delivery Status & Toggles -->
	<div class="card-surface rounded-2xl p-6 space-y-5">
		<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
			<div>
				<h2 class="text-base font-semibold text-white flex items-center gap-2">
					<Mail class="w-4 h-4 text-emerald-400" />
					Automated Luna CFO Email Digests
				</h2>
				<p class="text-xs text-slate-400 mt-0.5">
					Delivered to <strong class="text-slate-200">{prefs?.email || 'your account email'}</strong> via Resend.
				</p>
			</div>

			{#if prefs}
				<span
					class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold border w-fit {prefs.resend_configured
						? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300'
						: 'bg-amber-500/15 border-amber-500/35 text-amber-300'}"
				>
					<span
						class="h-1.5 w-1.5 rounded-full {prefs.resend_configured
							? 'bg-emerald-400 animate-pulse'
							: 'bg-amber-400'}"
					></span>
					{prefs.resend_configured ? 'Resend Live' : 'Resend API Key Needed'}
				</span>
			{/if}
		</div>

		{#if loadingPrefs}
			<div class="p-6 text-center text-xs text-slate-500">Loading email preferences...</div>
		{:else if prefs}
			{#if !prefs.resend_configured}
				<div class="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 flex items-start gap-2.5">
					<AlertTriangle class="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
					<span>
						Preview works right now! Once you add <code class="px-1 py-0.5 rounded bg-slate-950 text-amber-300">RESEND_API_KEY</code> on Fly.io, clicking <strong>Send Now</strong> and the Monday / 1st-of-month schedules will deliver straight to your inbox.
					</span>
				</div>
			{/if}

			<div class="grid md:grid-cols-2 gap-4">
				<!-- Card 1: Monday Weekly Briefing -->
				<div class="p-4 rounded-2xl bg-slate-950/80 border border-slate-800/90 flex flex-col justify-between gap-4">
					<div class="space-y-2.5">
						<div class="flex items-start justify-between gap-3">
							<div class="flex items-center gap-2.5">
								<div class="h-9 w-9 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center shrink-0">
									<Sparkles class="w-4 h-4" />
								</div>
								<div>
									<div class="text-sm font-semibold text-white">Monday Weekly Briefing</div>
									<div class="text-[11px] text-emerald-300 font-medium">Every Monday · 9:00 AM</div>
								</div>
							</div>

							<button
								type="button"
								disabled={savingPref}
								onclick={() => togglePreference('email_weekly_briefing')}
								aria-label="Toggle Monday Weekly Briefing"
								class="relative inline-flex h-6 w-11 shrink-0 rounded-full border transition cursor-pointer {prefs.email_weekly_briefing
									? 'bg-emerald-500 border-emerald-400'
									: 'bg-slate-800 border-slate-700'}"
							>
								<span
									class="inline-block h-5 w-5 rounded-full bg-white shadow transform transition {prefs.email_weekly_briefing
										? 'translate-x-5'
										: 'translate-x-0'}"
								></span>
							</button>
						</div>

						<p class="text-xs text-slate-400 leading-relaxed">
							Last 7-day Net Cash Flow, Financial Health Score, Remaining Safe-to-Spend, Bills Due This Week, and Luna's #1 move.
						</p>

						{#if prefs.last_weekly_briefing_sent_at}
							<div class="text-[10px] text-slate-500 inline-flex items-center gap-1">
								<CheckCircle2 class="w-3 h-3 text-emerald-400" />
								Last sent {formatDate(prefs.last_weekly_briefing_sent_at)}
							</div>
						{/if}
					</div>

					<div class="flex items-center gap-2">
						<button
							type="button"
							disabled={sendingType !== null}
							onclick={() => sendDigestNow('weekly')}
							class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer transition disabled:opacity-50"
						>
							<Send class="w-3.5 h-3.5" />
							{sendingType === 'weekly' ? 'Sending...' : 'Send Now'}
						</button>
						<button
							type="button"
							onclick={() => loadPreview('weekly')}
							class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 cursor-pointer"
						>
							Preview
						</button>
					</div>
				</div>

				<!-- Card 2: Monthly CFO Wrapped -->
				<div class="p-4 rounded-2xl bg-slate-950/80 border border-slate-800/90 flex flex-col justify-between gap-4">
					<div class="space-y-2.5">
						<div class="flex items-start justify-between gap-3">
							<div class="flex items-center gap-2.5">
								<div class="h-9 w-9 rounded-xl bg-orange-500/15 border border-orange-500/30 text-orange-400 flex items-center justify-center shrink-0">
									<Calendar class="w-4 h-4" />
								</div>
								<div>
									<div class="text-sm font-semibold text-white">Monthly "CFO Wrapped"</div>
									<div class="text-[11px] text-orange-300 font-medium">1st of Every Month · 9:00 AM</div>
								</div>
							</div>

							<button
								type="button"
								disabled={savingPref}
								onclick={() => togglePreference('email_monthly_wrapped')}
								aria-label="Toggle Monthly CFO Wrapped"
								class="relative inline-flex h-6 w-11 shrink-0 rounded-full border transition cursor-pointer {prefs.email_monthly_wrapped
									? 'bg-emerald-500 border-emerald-400'
									: 'bg-slate-800 border-slate-700'}"
							>
								<span
									class="inline-block h-5 w-5 rounded-full bg-white shadow transform transition {prefs.email_monthly_wrapped
										? 'translate-x-5'
										: 'translate-x-0'}"
								></span>
							</button>
						</div>

						<p class="text-xs text-slate-400 leading-relaxed">
							Net Worth change, Savings Rate %, Top 3 Categories, Goal Milestones Hit, Biggest Win, and BOG PDF upload reminder.
						</p>

						{#if prefs.last_monthly_wrapped_sent_at}
							<div class="text-[10px] text-slate-500 inline-flex items-center gap-1">
								<CheckCircle2 class="w-3 h-3 text-emerald-400" />
								Last sent {formatDate(prefs.last_monthly_wrapped_sent_at)}
							</div>
						{/if}
					</div>

					<div class="flex items-center gap-2">
						<button
							type="button"
							disabled={sendingType !== null}
							onclick={() => sendDigestNow('monthly')}
							class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-orange-500 hover:bg-orange-400 text-white text-xs font-semibold cursor-pointer transition disabled:opacity-50"
						>
							<Send class="w-3.5 h-3.5" />
							{sendingType === 'monthly' ? 'Sending...' : 'Send Now'}
						</button>
						<button
							type="button"
							onclick={() => loadPreview('monthly')}
							class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 cursor-pointer"
						>
							Preview
						</button>
					</div>
				</div>
			</div>
		{/if}
	</div>

	<!-- Live Dark-Mode HTML Email Preview -->
	<div class="card-surface rounded-2xl overflow-hidden">
		<div class="px-5 py-4 border-b border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
			<div class="min-w-0">
				<div class="text-xs font-semibold uppercase tracking-wider text-slate-400">
					Live Email Preview (Real Ledger Data)
				</div>
				{#if preview}
					<div class="text-xs text-white font-medium truncate mt-0.5">
						Subject: <span class="text-emerald-300">{preview.subject}</span>
					</div>
				{/if}
			</div>

			<div class="flex items-center gap-1.5 shrink-0">
				<div class="inline-flex p-0.5 rounded-xl bg-slate-950 border border-slate-800 text-xs">
					<button
						type="button"
						onclick={() => loadPreview('weekly')}
						class="px-3 py-1.5 rounded-lg font-semibold cursor-pointer transition {previewType === 'weekly'
							? 'bg-emerald-500/20 text-emerald-300'
							: 'text-slate-400 hover:text-white'}"
					>
						Weekly Briefing
					</button>
					<button
						type="button"
						onclick={() => loadPreview('monthly')}
						class="px-3 py-1.5 rounded-lg font-semibold cursor-pointer transition {previewType === 'monthly'
							? 'bg-orange-500/20 text-orange-300'
							: 'text-slate-400 hover:text-white'}"
					>
						Monthly Wrapped
					</button>
				</div>
				<button
					type="button"
					disabled={loadingPreview}
					onclick={() => loadPreview(previewType)}
					class="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 cursor-pointer"
					title="Refresh preview"
				>
					<RefreshCw class="w-3.5 h-3.5 {loadingPreview ? 'animate-spin text-emerald-400' : ''}" />
				</button>
			</div>
		</div>

		{#if loadingPreview && !preview}
			<div class="p-12 text-center text-xs text-slate-400">Rendering dark-mode email preview...</div>
		{:else if preview}
			<div class="bg-slate-950 p-3 sm:p-4">
				<iframe
					title="Financinio Email Digest Preview"
					srcdoc={preview.html}
					class="w-full h-[680px] rounded-xl border border-slate-800 bg-slate-950"
				></iframe>
			</div>
		{/if}
	</div>
</div>
