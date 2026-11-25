<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import MarkdownMessage from '$lib/components/MarkdownMessage.svelte';
	import {
		speakLunaText,
		startAudioRecording,
		stopSpeaking,
		type ActiveRecorder
	} from '$lib/utils/voice';
	import type {
		ChatMessage,
		ChatThread,
		FinancialHealthProfile,
		ProactiveInsight,
		UserMemoryItem
	} from '$lib/api/types';
	import {
		Sparkles,
		ArrowUp,
		Plus,
		Trash2,
		MessageSquare,
		Lightbulb,
		Brain,
		CheckCircle2,
		XCircle,
		ShieldAlert,
		AlertTriangle,
		Info,
		RefreshCw,
		Copy,
		Check,
		PanelLeft,
		X,
		ArrowDown,
		ShieldCheck,
		Globe,
		ExternalLink,
		Mic,
		Square,
		Volume2,
		VolumeX
	} from 'lucide-svelte';

	let sideTab = $state<'chats' | 'insights' | 'memory'>('chats');
	let drawerOpen = $state(false);
	let desktopPanelOpen = $state(true);

	let threads = $state<ChatThread[]>([]);
	let activeThreadId = $state<string | null>(null);
	let messages = $state<ChatMessage[]>([]);
	let insights = $state<ProactiveInsight[]>([]);
	let memories = $state<UserMemoryItem[]>([]);
	let healthProfile = $state<FinancialHealthProfile | null>(null);

	let inputText = $state('');
	let webSearchMode = $state<'auto' | 'on' | 'off'>('auto');
	let handsFreeVoice = $state(false);
	let recordingVoice = $state(false);
	let transcribingVoice = $state(false);
	let recordSec = $state(0);
	let speakingMsgId = $state<string | null>(null);
	let activeRecorder: ActiveRecorder | null = null;
	let recordTimer: ReturnType<typeof setInterval> | undefined;
	let streaming = $state(false);
	let statusLabel = $state<string | null>(null);
	let streamingText = $state('');
	let decidingId = $state<string | null>(null);
	let copiedMsgId = $state<string | null>(null);
	let generatingInsights = $state(false);
	let newMemoryFact = $state('');
	let error = $state<string | null>(null);

	let chatScrollEl = $state<HTMLDivElement | null>(null);
	let textareaEl = $state<HTMLTextAreaElement | null>(null);
	let showScrollDown = $state(false);

	const STARTER_PROMPTS = [
		{
			title: 'Search Apartments in My Budget',
			prompt: 'Search for 2-bedroom apartments to rent in Tbilisi (Saburtalo or Vake) that fit my real monthly budget and show affordability verdicts'
		},
		{
			title: 'Senior Financial Health Checkup',
			prompt: 'Run a full Senior Financial Advisor checkup on my finances and give me my top 3 priorities'
		},
		{
			title: 'Can I Afford This Purchase?',
			prompt: 'Can I afford a $1,200 purchase right now? Show my runway impact & 5-year opportunity cost'
		},
		{
			title: 'Find Spending Leaks',
			prompt: 'Where am I leaking money and how can I boost my savings rate?'
		}
	];

	function cycleWebSearchMode() {
		if (webSearchMode === 'auto') webSearchMode = 'on';
		else if (webSearchMode === 'on') webSearchMode = 'off';
		else webSearchMode = 'auto';
	}

	function toggleHandsFreeVoice() {
		handsFreeVoice = !handsFreeVoice;
		if (!handsFreeVoice) {
			stopSpeaking();
			speakingMsgId = null;
		}
	}

	async function playMessageAudio(msg: ChatMessage) {
		if (speakingMsgId === msg.id) {
			stopSpeaking();
			speakingMsgId = null;
			return;
		}
		speakingMsgId = msg.id;
		await speakLunaText(msg.content, () => {
			if (speakingMsgId === msg.id) speakingMsgId = null;
		});
	}

	function cleanupVoice() {
		if (recordTimer) {
			clearInterval(recordTimer);
			recordTimer = undefined;
		}
		if (activeRecorder) {
			activeRecorder.cancel();
			activeRecorder = null;
		}
		recordingVoice = false;
		recordSec = 0;
		stopSpeaking();
		speakingMsgId = null;
	}

	onDestroy(cleanupVoice);

	async function toggleComposerMic() {
		error = null;
		if (recordingVoice && activeRecorder) {
			if (recordTimer) {
				clearInterval(recordTimer);
				recordTimer = undefined;
			}
			recordingVoice = false;
			transcribingVoice = true;
			try {
				const blob = await activeRecorder.stop();
				activeRecorder = null;
				const tr = await api.voiceTranscribe(blob, 'auto');
				const spoken = tr.transcript.trim();
				if (spoken) {
					if (handsFreeVoice) {
						await sendMessage(spoken);
					} else {
						inputText = inputText ? `${inputText.trim()} ${spoken}` : spoken;
						await tick();
						autoResizeTextarea();
					}
				}
			} catch (e) {
				error = e instanceof Error ? e.message : 'Voice transcription failed.';
			} finally {
				transcribingVoice = false;
				recordSec = 0;
			}
			return;
		}

		try {
			stopSpeaking();
			speakingMsgId = null;
			recordSec = 0;
			activeRecorder = await startAudioRecording();
			recordingVoice = true;
			recordTimer = setInterval(() => {
				recordSec += 1;
				if (recordSec >= 45 && recordingVoice) {
					toggleComposerMic();
				}
			}, 1000);
		} catch (e) {
			error =
				e instanceof Error ? e.message : 'Microphone access was denied by your browser.';
		}
	}

	const QUICK_FOLLOWUPS = [
		'Give me a concrete 30-day action plan',
		'Show the trade-offs in a table',
		'Set up a budget to fix my biggest leak'
	];

	let activeThread = $derived(threads.find((t) => t.id === activeThreadId) ?? null);

	async function scrollToBottom(smooth = false) {
		await tick();
		if (chatScrollEl) {
			chatScrollEl.scrollTo({
				top: chatScrollEl.scrollHeight,
				behavior: smooth ? 'smooth' : 'auto'
			});
			showScrollDown = false;
		}
	}

	function handleScroll() {
		if (!chatScrollEl) return;
		const dist = chatScrollEl.scrollHeight - chatScrollEl.scrollTop - chatScrollEl.clientHeight;
		showScrollDown = dist > 160;
	}

	function autoResizeTextarea() {
		if (!textareaEl) return;
		textareaEl.style.height = 'auto';
		textareaEl.style.height = `${Math.min(textareaEl.scrollHeight, 160)}px`;
	}

	async function loadInitial() {
		try {
			const [ths, ins, mems, health] = await Promise.all([
				api.listThreads(),
				api.listInsights(),
				api.listMemories(),
				api.financialHealthScore().catch(() => null)
			]);
			threads = ths;
			insights = ins;
			memories = mems;
			healthProfile = health;

			if (page.url.searchParams.get('voice') === '1') {
				handsFreeVoice = true;
			}
			const initialQuery =
				page.url.searchParams.get('q') || page.url.searchParams.get('prompt');
			if (initialQuery && initialQuery.trim()) {
				await createNewThread();
				goto('/advisor', { replaceState: true });
				await sendMessage(initialQuery.trim());
			} else if (ths.length > 0) {
				await selectThread(ths[0].id);
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load Luna Advisor';
		}
	}

	onMount(loadInitial);

	async function selectThread(id: string) {
		activeThreadId = id;
		drawerOpen = false;
		error = null;
		const detail = await api.getThread(id);
		messages = detail.messages;
		await scrollToBottom();
	}

	async function createNewThread(): Promise<string> {
		const created = await api.createThread();
		threads = [created, ...threads];
		activeThreadId = created.id;
		messages = [];
		drawerOpen = false;
		return created.id;
	}

	async function deleteThread(id: string) {
		await api.deleteThread(id);
		threads = threads.filter((t) => t.id !== id);
		if (activeThreadId === id) {
			if (threads.length > 0) await selectThread(threads[0].id);
			else {
				activeThreadId = null;
				messages = [];
			}
		}
	}

	async function sendMessage(textOverride?: string) {
		const text = (textOverride ?? inputText).trim();
		if (!text || streaming) return;
		inputText = '';
		if (textareaEl) textareaEl.style.height = 'auto';
		error = null;
		streaming = true;
		streamingText = '';
		statusLabel = 'Luna is analyzing your request...';

		try {
			const tid = activeThreadId ?? (await createNewThread());

			const tempUserMsg: ChatMessage = {
				id: `temp-u-${Date.now()}`,
				thread_id: tid,
				role: 'user',
				content: text,
				active_agent: null,
				citations: [],
				pending_action: null,
				action_status: 'none',
				created_at: new Date().toISOString()
			};
			messages = [...messages, tempUserMsg];
			await scrollToBottom(true);

			await api.streamAdvisorMessage(
				tid,
				text,
				{
					onStatus: (label) => {
						statusLabel = label;
					},
					onToken: (chunk) => {
						streamingText += chunk;
						scrollToBottom();
					},
					onActionRequired: (msg) => {
						messages = [...messages, msg];
						streamingText = '';
						scrollToBottom(true);
					},
					onDone: (msg) => {
						if (!messages.some((m) => m.id === msg.id)) {
							messages = [...messages, msg];
						}
						streamingText = '';
						statusLabel = null;
						streaming = false;
						scrollToBottom(true);
						if (handsFreeVoice && msg.content) {
							playMessageAudio(msg);
						}
					},
					onError: (detail) => {
						error = detail;
					}
				},
				{ webSearchMode }
			);

			// Refresh thread titles, memories, and sidebar token meter silently in the background
			Promise.all([api.listThreads(), api.listMemories(), auth.refresh()])
				.then(([ths, mems]) => {
					threads = ths;
					memories = mems;
				})
				.catch(() => null);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Unable to reach Luna right now.';
		} finally {
			streaming = false;
			statusLabel = null;
		}
	}

	function handleComposerKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}

	async function handleActionDecision(msg: ChatMessage, approved: boolean) {
		if (!activeThreadId) return;
		decidingId = msg.id;
		error = null;
		try {
			const res = await api.decideAdvisorAction(activeThreadId, msg.id, approved);
			messages = messages.map((m) => (m.id === msg.id ? res.message : m));
			if (approved) {
				api.financialHealthScore().then((h) => (healthProfile = h)).catch(() => null);
			}
			await scrollToBottom(true);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Action decision failed';
		} finally {
			decidingId = null;
		}
	}

	async function copyMessage(msg: ChatMessage) {
		try {
			await navigator.clipboard.writeText(msg.content);
			copiedMsgId = msg.id;
			setTimeout(() => {
				if (copiedMsgId === msg.id) copiedMsgId = null;
			}, 1800);
		} catch {
			// ignore clipboard errors
		}
	}

	async function handleGenerateInsights() {
		generatingInsights = true;
		error = null;
		try {
			await api.generateInsights();
			insights = await api.listInsights();
			await auth.refresh();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Insight generation failed';
		} finally {
			generatingInsights = false;
		}
	}

	async function handleDismissInsight(id: string) {
		await api.dismissInsight(id);
		insights = insights.filter((i) => i.id !== id);
	}

	async function handleAddMemory(e: SubmitEvent) {
		e.preventDefault();
		if (!newMemoryFact.trim()) return;
		const added = await api.addMemory(newMemoryFact.trim(), 'preference');
		memories = [added, ...memories];
		newMemoryFact = '';
	}

	async function handleDeleteMemory(id: string) {
		await api.deleteMemory(id);
		memories = memories.filter((m) => m.id !== id);
	}

	function openPanelTab(tab: 'chats' | 'insights' | 'memory') {
		sideTab = tab;
		drawerOpen = true;
		desktopPanelOpen = true;
	}

	function agentLabel(agent: string | null): string {
		if (agent === 'decision_advisor') return 'Senior CFP Advisor';
		if (agent === 'ledger_analyst') return 'Ledger Analyst';
		if (agent === 'document_rag') return 'Document & Memory RAG';
		if (agent === 'wealth_strategist') return 'Wealth Strategist';
		if (agent === 'action_proposer') return 'Action Agent (HITL)';
		if (agent === 'web_researcher') return 'Live Web Researcher';
		if (agent === 'market_analyst') return 'AI Trader Bot & Quant';
		return 'Luna Personal CFO';
	}

	function healthBadgeTone(score: number): string {
		if (score >= 75) return 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300 hover:bg-emerald-500/25';
		if (score >= 50) return 'bg-amber-500/15 border-amber-500/35 text-amber-300 hover:bg-amber-500/25';
		return 'bg-rose-500/15 border-rose-500/35 text-rose-300 hover:bg-rose-500/25';
	}

	function humanizeKey(k: string): string {
		return k
			.replaceAll('_', ' ')
			.replace(/\b\w/g, (c) => c.toUpperCase());
	}
</script>

<!-- Full-viewport Edge-to-Edge Chat Workspace -->
<div class="h-[calc(100dvh-3.5rem)] md:h-dvh flex overflow-hidden bg-slate-950 relative">
	<!-- Mobile Slide-Over Backdrop -->
	{#if drawerOpen}
		<button
			type="button"
			onclick={() => (drawerOpen = false)}
			aria-label="Close panel"
			class="lg:hidden fixed inset-0 z-40 bg-black/65 backdrop-blur-xs"
		></button>
	{/if}

	<!-- Side Panel: Chats / Insights / Memory (Slide-over on mobile, Collapsible rail on desktop) -->
	<aside
		class="fixed lg:static inset-y-0 left-0 z-50 w-80 max-w-[85vw] lg:w-72 xl:w-80 bg-slate-950 border-r border-slate-800/80 flex flex-col transition-transform duration-200 {drawerOpen
			? 'translate-x-0'
			: '-translate-x-full lg:translate-x-0'} {desktopPanelOpen ? 'lg:flex' : 'lg:hidden'}"
	>
		<div class="flex items-center justify-between px-3.5 py-3 border-b border-slate-800/80">
			<div class="grid grid-cols-3 flex-1 p-1 rounded-xl bg-slate-900/90 border border-slate-800/80">
				<button
					type="button"
					onclick={() => (sideTab = 'chats')}
					class="py-1.5 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1 cursor-pointer {sideTab === 'chats'
						? 'bg-emerald-500/20 text-emerald-300'
						: 'text-slate-400 hover:text-white'}"
				>
					<MessageSquare class="w-3.5 h-3.5" /> Chats
				</button>
				<button
					type="button"
					onclick={() => (sideTab = 'insights')}
					class="py-1.5 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1 cursor-pointer relative {sideTab === 'insights'
						? 'bg-emerald-500/20 text-emerald-300'
						: 'text-slate-400 hover:text-white'}"
				>
					<Lightbulb class="w-3.5 h-3.5" /> Insights
					{#if insights.length > 0}
						<span class="ml-0.5 px-1 rounded-full bg-emerald-500/25 text-emerald-300 text-[9px] font-mono-num">
							{insights.length}
						</span>
					{/if}
				</button>
				<button
					type="button"
					onclick={() => (sideTab = 'memory')}
					class="py-1.5 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1 cursor-pointer {sideTab === 'memory'
						? 'bg-emerald-500/20 text-emerald-300'
						: 'text-slate-400 hover:text-white'}"
				>
					<Brain class="w-3.5 h-3.5" /> Memory
				</button>
			</div>
			<button
				type="button"
				onclick={() => (drawerOpen = false)}
				class="lg:hidden ml-2 p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
				aria-label="Close drawer"
			>
				<X class="w-4 h-4" />
			</button>
		</div>

		{#if sideTab === 'chats'}
			<div class="p-3 border-b border-slate-800/70">
				<button
					type="button"
					onclick={createNewThread}
					class="w-full py-2.5 px-3 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition"
				>
					<Plus class="w-4 h-4" /> New Conversation
				</button>
			</div>
			<div class="flex-1 overflow-y-auto p-2.5 space-y-1">
				{#if threads.length === 0}
					<p class="text-xs text-slate-500 text-center py-10 px-4">
						Your conversations with Luna will appear here.
					</p>
				{:else}
					{#each threads as th}
						<div
							class="group flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl border transition {activeThreadId === th.id
								? 'bg-slate-900 border-emerald-500/35 text-white'
								: 'bg-transparent border-transparent hover:bg-slate-900/60 text-slate-300'}"
						>
							<button
								type="button"
								onclick={() => selectThread(th.id)}
								class="flex-1 text-left text-xs font-medium truncate cursor-pointer"
							>
								{th.title}
							</button>
							<button
								type="button"
								onclick={() => deleteThread(th.id)}
								class="lg:opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400 cursor-pointer p-1"
								title="Delete chat"
							>
								<Trash2 class="w-3.5 h-3.5" />
							</button>
						</div>
					{/each}
				{/if}
			</div>
		{:else if sideTab === 'insights'}
			<div class="p-3 border-b border-slate-800/70">
				<button
					type="button"
					disabled={generatingInsights}
					onclick={handleGenerateInsights}
					class="w-full py-2.5 px-3 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
				>
					<RefreshCw class="w-3.5 h-3.5 {generatingInsights ? 'animate-spin' : ''}" />
					{generatingInsights ? 'Scanning Ledger...' : 'Generate Fresh Digest'}
				</button>
			</div>
			<div class="flex-1 overflow-y-auto p-3 space-y-3">
				{#if insights.length === 0}
					<p class="text-xs text-slate-500 text-center py-8 px-3">
						Run a ledger scan for spending anomalies, budget overruns, and Luna's weekly digest.
					</p>
				{:else}
					{#each insights as ins}
						<div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
							<div class="flex items-start justify-between gap-2">
								<div class="flex items-center gap-1.5 text-xs font-semibold {ins.severity === 'alert' ? 'text-rose-300' : ins.severity === 'warning' ? 'text-amber-300' : 'text-emerald-300'}">
									{#if ins.severity === 'alert'}
										<ShieldAlert class="w-3.5 h-3.5 shrink-0" />
									{:else if ins.severity === 'warning'}
										<AlertTriangle class="w-3.5 h-3.5 shrink-0" />
									{:else}
										<Info class="w-3.5 h-3.5 shrink-0" />
									{/if}
									<span>{ins.title}</span>
								</div>
								<button
									type="button"
									onclick={() => handleDismissInsight(ins.id)}
									class="text-slate-500 hover:text-slate-300 text-xs cursor-pointer"
									aria-label="Dismiss insight"
								>
									✕
								</button>
							</div>
							<MarkdownMessage content={ins.summary} compact />
						</div>
					{/each}
				{/if}
			</div>
		{:else}
			<form onsubmit={handleAddMemory} class="p-3 border-b border-slate-800/70 space-y-2">
				<input
					type="text"
					bind:value={newMemoryFact}
					placeholder="Add a financial goal or preference..."
					class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
				/>
				<button
					type="submit"
					class="w-full py-2 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 text-xs font-semibold cursor-pointer"
				>
					+ Save to Upstash Memory
				</button>
			</form>
			<div class="flex-1 overflow-y-auto p-3 space-y-2">
				{#if memories.length === 0}
					<p class="text-xs text-slate-500 text-center py-8 px-3">
						No long-term memories yet. Tell Luna "Remember that..." in chat or save one above.
					</p>
				{:else}
					{#each memories as mem}
						<div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex items-start justify-between gap-2 text-xs">
							<span class="text-slate-200 leading-relaxed">{mem.fact}</span>
							<button
								type="button"
								onclick={() => handleDeleteMemory(mem.id)}
								class="text-slate-500 hover:text-rose-400 shrink-0 cursor-pointer p-0.5"
								aria-label="Delete memory"
							>
								<Trash2 class="w-3.5 h-3.5" />
							</button>
						</div>
					{/each}
				{/if}
			</div>
		{/if}
	</aside>

	<!-- Main Full-Height Chat Column -->
	<div class="flex-1 flex flex-col min-w-0 min-h-0 relative">
		<!-- Compact Top Toolbar -->
		<header class="shrink-0 h-14 px-3 sm:px-5 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md flex items-center justify-between gap-3">
			<div class="flex items-center gap-2.5 min-w-0">
				<!-- Toggle Drawer (mobile) / Toggle Rail (desktop) -->
				<button
					type="button"
					onclick={() => (drawerOpen = !drawerOpen)}
					class="lg:hidden p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 hover:text-white cursor-pointer"
					aria-label="Open chats and insights"
				>
					<PanelLeft class="w-4 h-4" />
				</button>
				<button
					type="button"
					onclick={() => (desktopPanelOpen = !desktopPanelOpen)}
					class="hidden lg:inline-flex p-2 rounded-xl bg-slate-900/70 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white cursor-pointer"
					title="Toggle side panel"
					aria-label="Toggle side panel"
				>
					<PanelLeft class="w-4 h-4" />
				</button>

				<div class="h-8 w-8 rounded-xl bg-gradient-to-br from-emerald-500/25 to-cyan-500/25 border border-emerald-500/35 flex items-center justify-center text-emerald-300 shrink-0">
					<Sparkles class="w-4 h-4" />
				</div>
				<div class="min-w-0">
					<div class="text-sm font-semibold text-white truncate">
						{activeThread ? activeThread.title : 'Luna · Senior Personal CFO'}
					</div>
					<div class="text-[11px] text-slate-400 hidden sm:block">
						CFP Decision Engine · Live Web Search · Verified Neon Ledger
					</div>
				</div>
			</div>

			<div class="flex items-center gap-1.5 shrink-0">
				{#if speakingMsgId}
					<button
						type="button"
						onclick={() => {
							stopSpeaking();
							speakingMsgId = null;
						}}
						class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-semibold cursor-pointer transition"
					>
						<Square class="w-3 h-3 fill-current" />
						<span class="hidden sm:inline">Stop</span>
					</button>
				{/if}
				<button
					type="button"
					onclick={toggleHandsFreeVoice}
					title={handsFreeVoice
						? 'Hands-Free Talk to Luna: ON (auto-sends voice & speaks replies aloud)'
						: 'Hands-Free Talk to Luna: OFF (click to enable spoken replies)'}
					class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer transition {handsFreeVoice
						? 'bg-cyan-500/20 border-cyan-400/50 text-cyan-200'
						: 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'}"
				>
					{#if handsFreeVoice}
						<Volume2 class="w-3.5 h-3.5 text-cyan-300" />
						<span class="hidden sm:inline">Voice On</span>
					{:else}
						<VolumeX class="w-3.5 h-3.5" />
						<span class="hidden sm:inline">Voice</span>
					{/if}
				</button>
				{#if healthProfile}
					<button
						type="button"
						disabled={streaming}
						onclick={() =>
							sendMessage(
								'Run a full Senior Financial Advisor checkup on my Financial Health Score and give me my top 3 priorities.'
							)}
						title={`${healthProfile.health_score.grade} — ${healthProfile.health_score.top_priority}`}
						class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer transition disabled:opacity-50 {healthBadgeTone(healthProfile.health_score.overall)}"
					>
						<ShieldCheck class="w-3.5 h-3.5 shrink-0" />
						<span class="hidden sm:inline">Health</span>
						<span class="font-mono-num">{healthProfile.health_score.overall}/100</span>
					</button>
				{/if}
				<button
					type="button"
					onclick={() => openPanelTab('insights')}
					class="lg:hidden inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300"
				>
					<Lightbulb class="w-3.5 h-3.5 text-amber-400" />
					{#if insights.length > 0}<span class="font-mono-num">{insights.length}</span>{/if}
				</button>
				<button
					type="button"
					onclick={createNewThread}
					class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold cursor-pointer transition"
				>
					<Plus class="w-3.5 h-3.5" />
					<span class="hidden sm:inline">New Chat</span>
				</button>
			</div>
		</header>

		{#if error}
			<div class="shrink-0 mx-auto max-w-3xl w-full px-4 pt-3">
				<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-3">
					<span>{error}</span>
					<button type="button" onclick={() => (error = null)} class="text-rose-200 hover:text-white cursor-pointer">✕</button>
				</div>
			</div>
		{/if}

		<!-- Scrollable Message Canvas -->
		<div
			bind:this={chatScrollEl}
			onscroll={handleScroll}
			class="flex-1 overflow-y-auto px-4 sm:px-6 py-6 scroll-smooth"
		>
			<div class="max-w-3xl mx-auto space-y-6">
				{#if messages.length === 0 && !streaming}
					<!-- Spacious Welcome Hero -->
					<div class="py-8 sm:py-14 flex flex-col items-center text-center space-y-6">
						<div class="h-16 w-16 rounded-2xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shadow-lg shadow-emerald-950/50">
							<Sparkles class="w-8 h-8" />
						</div>
						<div class="space-y-2 max-w-lg">
							<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">
								Hi, I'm Luna — your Personal CFO.
							</h1>
							<p class="text-sm text-slate-400 leading-relaxed">
								Ask before you spend ("Can I afford this?"), run a CFP Financial Health Checkup, spot spending leaks, compare debt strategies, or let me create budgets & goals with one-click approval.
							</p>
						</div>

						<div class="grid sm:grid-cols-2 gap-3 w-full pt-2">
							{#each STARTER_PROMPTS as item}
								<button
									type="button"
									onclick={() => sendMessage(item.prompt)}
									class="text-left p-4 rounded-2xl bg-slate-900/75 hover:bg-slate-900 border border-slate-800 hover:border-emerald-500/40 transition cursor-pointer space-y-1 group"
								>
									<div class="text-xs font-semibold text-emerald-400 group-hover:text-emerald-300">
										{item.title}
									</div>
									<div class="text-xs text-slate-300 leading-relaxed">
										{item.prompt}
									</div>
								</button>
							{/each}
						</div>
					</div>
				{:else}
					{#each messages as msg}
						{#if msg.role === 'user'}
							<div class="flex justify-end">
								<div class="max-w-[88%] sm:max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-3 bg-emerald-500 text-slate-950 font-medium text-[15px] leading-relaxed shadow-sm">
									<div class="whitespace-pre-wrap">{msg.content}</div>
								</div>
							</div>
						{:else}
							<div class="flex items-start gap-3 sm:gap-4 group">
								<div class="h-8 w-8 rounded-xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0 mt-0.5">
									<Sparkles class="w-4 h-4" />
								</div>

								<div class="flex-1 min-w-0 space-y-3">
									<!-- Agent header & copy button -->
									<div class="flex items-center justify-between gap-2">
										<div class="flex items-center gap-2 flex-wrap">
											<span class="text-xs font-semibold text-white">Luna</span>
											{#if msg.active_agent}
												<span class="px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-cyan-300 text-[10px] font-medium">
													{agentLabel(msg.active_agent)}
												</span>
											{/if}
										</div>
										<div class="flex items-center gap-1">
											<button
												type="button"
												onclick={() => playMessageAudio(msg)}
												class="opacity-80 sm:opacity-0 group-hover:opacity-100 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] transition cursor-pointer {speakingMsgId === msg.id
													? 'text-cyan-300 bg-cyan-500/15 opacity-100'
													: 'text-slate-400 hover:text-cyan-300 hover:bg-slate-900'}"
												title={speakingMsgId === msg.id ? 'Stop speaking' : 'Listen to Luna'}
											>
												{#if speakingMsgId === msg.id}
													<Square class="w-3 h-3 fill-current" />
													<span class="hidden sm:inline">Stop</span>
												{:else}
													<Volume2 class="w-3.5 h-3.5" />
													<span class="hidden sm:inline">Listen</span>
												{/if}
											</button>
											<button
												type="button"
												onclick={() => copyMessage(msg)}
												class="opacity-70 sm:opacity-0 group-hover:opacity-100 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] text-slate-400 hover:text-white hover:bg-slate-900 transition cursor-pointer"
												title="Copy response"
											>
												{#if copiedMsgId === msg.id}
													<Check class="w-3.5 h-3.5 text-emerald-400" />
													<span class="text-emerald-400">Copied</span>
												{:else}
													<Copy class="w-3.5 h-3.5" />
													<span class="hidden sm:inline">Copy</span>
												{/if}
											</button>
										</div>
									</div>

									<!-- Rich Formatted Markdown Body -->
									<div class="rounded-2xl bg-slate-900/55 border border-slate-800/80 px-4 sm:px-5 py-3.5 sm:py-4">
										<MarkdownMessage content={msg.content} />
									</div>

									<!-- Interactive HITL Action Approval Card -->
									{#if msg.pending_action}
										<div
											class="p-4 rounded-2xl bg-slate-900/90 border {msg.action_status === 'pending'
												? 'border-amber-500/45'
												: msg.action_status === 'executed'
													? 'border-emerald-500/45'
													: 'border-slate-700'} space-y-3.5"
										>
											<div class="flex items-center justify-between gap-2">
												<span class="text-sm font-semibold text-white">
													{String(msg.pending_action.title || 'Proposed Financial Action')}
												</span>
												<span
													class="text-[10px] font-semibold uppercase px-2.5 py-0.5 rounded-full {msg.action_status === 'pending'
														? 'bg-amber-500/15 text-amber-300'
														: msg.action_status === 'executed'
															? 'bg-emerald-500/15 text-emerald-300'
															: 'bg-rose-500/15 text-rose-300'}"
												>
													{msg.action_status}
												</span>
											</div>

											<div class="grid sm:grid-cols-2 gap-2 text-xs">
												{#each Object.entries(msg.pending_action).filter(([k, v]) => v !== null && !['title', 'summary'].includes(k)) as [k, v]}
													<div class="bg-slate-950/90 border border-slate-800/80 px-3 py-2 rounded-xl flex items-center justify-between gap-2">
														<span class="text-slate-400">{humanizeKey(k)}</span>
														<span class="font-mono-num font-medium text-white">{String(v)}</span>
													</div>
												{/each}
											</div>

											{#if msg.action_status === 'pending'}
												<div class="flex flex-wrap items-center gap-2 pt-1">
													<button
														type="button"
														disabled={decidingId === msg.id}
														onclick={() => handleActionDecision(msg, true)}
														class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
													>
														<CheckCircle2 class="w-4 h-4" />
														{decidingId === msg.id ? 'Executing...' : 'Approve & Save'}
													</button>
													<button
														type="button"
														disabled={decidingId === msg.id}
														onclick={() => handleActionDecision(msg, false)}
														class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-800 hover:bg-rose-500/20 text-slate-300 hover:text-rose-300 text-xs font-medium cursor-pointer disabled:opacity-50"
													>
														<XCircle class="w-4 h-4" />
														Reject
													</button>
												</div>
											{/if}
										</div>
									{/if}

									<!-- Citations & Clickable Web Sources -->
									{#if msg.citations && msg.citations.length > 0}
										{@const webSources = msg.citations.filter((c) => Boolean(c.url))}
										{@const metaCitations = msg.citations.filter((c) => !c.url)}

										{#if webSources.length > 0}
											<div class="space-y-1.5">
												<div class="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-400">
													<Globe class="w-3 h-3" />
													Live Web Sources ({webSources.length})
												</div>
												<div class="grid sm:grid-cols-2 gap-2">
													{#each webSources as src}
														<a
															href={src.url}
															target="_blank"
															rel="noopener noreferrer"
															class="group/link flex items-center justify-between gap-2.5 p-2.5 rounded-xl bg-slate-900/90 hover:bg-slate-900 border border-slate-800 hover:border-cyan-500/45 transition"
														>
															<div class="min-w-0">
																<div class="text-xs font-medium text-slate-200 group-hover/link:text-cyan-300 truncate">
																	{src.label}
																</div>
																{#if src.domain}
																	<div class="text-[10px] text-slate-500 truncate mt-0.5">
																		{src.domain}
																	</div>
																{/if}
															</div>
															<ExternalLink class="w-3.5 h-3.5 text-slate-500 group-hover/link:text-cyan-400 shrink-0" />
														</a>
													{/each}
												</div>
											</div>
										{/if}

										{#if metaCitations.length > 0}
											<div class="flex flex-wrap gap-1.5">
												{#each metaCitations as cit}
													<span class="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900/90 border border-slate-800 text-slate-400">
														<strong class="text-slate-300">{cit.source}:</strong> {cit.label}
													</span>
												{/each}
											</div>
										{/if}
									{/if}
								</div>
							</div>
						{/if}
					{/each}

					<!-- Live Streaming Bubble (with live Markdown rendering!) -->
					{#if streaming}
						<div class="flex items-start gap-3 sm:gap-4">
							<div class="h-8 w-8 rounded-xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0 mt-0.5">
								<Sparkles class="w-4 h-4 animate-pulse" />
							</div>
							<div class="flex-1 min-w-0 space-y-2.5">
								<div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-xs text-emerald-300">
									<span class="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span>
									<span>{statusLabel || 'Luna is writing...'}</span>
								</div>
								{#if streamingText}
									<div class="rounded-2xl bg-slate-900/55 border border-emerald-500/25 px-4 sm:px-5 py-3.5 sm:py-4">
										<MarkdownMessage content={streamingText} />
									</div>
								{/if}
							</div>
						</div>
					{:else if messages.length > 0 && messages[messages.length - 1].role === 'assistant'}
						<!-- One-tap Follow-up Suggestions -->
						<div class="flex flex-wrap gap-2 pl-0 sm:pl-12 pt-1">
							{#each QUICK_FOLLOWUPS as chip}
								<button
									type="button"
									onclick={() => sendMessage(chip)}
									class="px-3 py-1.5 rounded-full bg-slate-900/80 hover:bg-slate-800 border border-slate-800 hover:border-emerald-500/35 text-xs text-slate-300 hover:text-white transition cursor-pointer"
								>
									{chip}
								</button>
							{/each}
						</div>
					{/if}
				{/if}
			</div>
		</div>

		<!-- Scroll to bottom floating pill -->
		{#if showScrollDown}
			<button
				type="button"
				onclick={() => scrollToBottom(true)}
				class="absolute bottom-28 left-1/2 -translate-x-1/2 z-20 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900/95 border border-slate-700 text-xs text-slate-200 shadow-lg hover:border-emerald-500/50 cursor-pointer"
			>
				<ArrowDown class="w-3.5 h-3.5" /> Latest
			</button>
		{/if}

		<!-- Modern Multiline Auto-Growing Composer -->
		<div class="shrink-0 border-t border-slate-800/80 bg-slate-950/95 backdrop-blur-md px-3 sm:px-6 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
			<form
				onsubmit={(e) => {
					e.preventDefault();
					sendMessage();
				}}
				class="max-w-3xl mx-auto"
			>
				<div class="flex items-end gap-2 p-2 rounded-2xl bg-slate-900/90 border border-slate-800 focus-within:border-emerald-500/60 transition shadow-inner">
					<button
						type="button"
						onclick={cycleWebSearchMode}
						disabled={streaming}
						title={webSearchMode === 'auto'
							? 'Web Search: Auto (Luna searches Google automatically when you ask for apartments, prices, or live rates)'
							: webSearchMode === 'on'
								? 'Web Search: Always On (Forces live Google Search + your budget check)'
								: 'Web Search: Off (100% local Neon ledger & Upstash memory only)'}
						class="h-10 px-2.5 sm:px-3 rounded-xl border text-xs font-semibold inline-flex items-center gap-1.5 shrink-0 cursor-pointer transition disabled:opacity-45 {webSearchMode === 'on'
							? 'bg-cyan-500/20 border-cyan-400/50 text-cyan-200'
							: webSearchMode === 'auto'
								? 'bg-slate-950/90 border-slate-700/80 text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300'
								: 'bg-slate-950/60 border-slate-800 text-slate-500 hover:text-slate-300'}"
					>
						<Globe class="w-3.5 h-3.5 {webSearchMode === 'on' ? 'text-cyan-300' : webSearchMode === 'auto' ? 'text-emerald-400' : 'text-slate-500'}" />
						<span class="hidden sm:inline">
							{webSearchMode === 'on' ? 'Web On' : webSearchMode === 'auto' ? 'Web Auto' : 'Web Off'}
						</span>
					</button>
					<button
						type="button"
						onclick={toggleComposerMic}
						disabled={streaming || transcribingVoice}
						title={recordingVoice
							? 'Tap to stop recording'
							: 'Speak to Luna in English or Georgian'}
						aria-label={recordingVoice ? 'Stop voice recording' : 'Speak to Luna'}
						class="h-10 px-2.5 rounded-xl border text-xs font-semibold inline-flex items-center gap-1.5 shrink-0 cursor-pointer transition disabled:opacity-45 {recordingVoice
							? 'bg-rose-500 border-rose-400 text-white animate-pulse'
							: transcribingVoice
								? 'bg-cyan-500/20 border-cyan-400/50 text-cyan-200'
								: 'bg-slate-950/90 border-slate-700/80 text-slate-300 hover:border-emerald-500/50 hover:text-emerald-300'}"
					>
						{#if recordingVoice}
							<Square class="w-3.5 h-3.5 fill-current" />
							<span class="font-mono-num text-[11px]">{recordSec}s</span>
						{:else if transcribingVoice}
							<span class="h-3.5 w-3.5 rounded-full border-2 border-cyan-300 border-t-transparent animate-spin"></span>
						{:else}
							<Mic class="w-4 h-4" />
						{/if}
					</button>
					<textarea
						bind:this={textareaEl}
						bind:value={inputText}
						oninput={autoResizeTextarea}
						onkeydown={handleComposerKeydown}
						disabled={streaming}
						rows={1}
						placeholder={recordingVoice
							? 'Listening (English or Georgian)... tap Stop when finished'
							: webSearchMode === 'on'
								? "Search live web + budget: 'Find 2-bed apartments in Vake under my rent cap'"
								: "Ask or speak to Luna: 'What's NVDA doing today?' or 'Can I afford a $1,200 trip?'"}
						class="flex-1 bg-transparent px-2 py-2 text-[15px] text-white placeholder:text-slate-500 focus:outline-none resize-none max-h-40 leading-relaxed"
					></textarea>
					<button
						type="submit"
						disabled={streaming || !inputText.trim()}
						aria-label="Send message"
						class="h-10 w-10 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-35 text-slate-950 flex items-center justify-center shrink-0 cursor-pointer transition"
					>
						<ArrowUp class="w-5 h-5 stroke-[2.5]" />
					</button>
				</div>
				<div class="flex items-center justify-between text-[10px] text-slate-500 px-1.5 pt-1.5">
					<span>Luna provides educational financial planning, not licensed tax or investment advice.</span>
					<span class="hidden sm:inline font-mono-num">Enter to send · Shift+Enter newline</span>
				</div>
			</form>
		</div>
	</div>
</div>
