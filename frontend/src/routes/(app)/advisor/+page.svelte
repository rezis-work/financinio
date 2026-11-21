<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type {
		ChatMessage,
		ChatThread,
		ProactiveInsight,
		UserMemoryItem
	} from '$lib/api/types';
	import {
		Sparkles,
		Send,
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
		RefreshCw
	} from 'lucide-svelte';

	let sideTab = $state<'chats' | 'insights' | 'memory'>('chats');
	let threads = $state<ChatThread[]>([]);
	let activeThreadId = $state<string | null>(null);
	let messages = $state<ChatMessage[]>([]);
	let insights = $state<ProactiveInsight[]>([]);
	let memories = $state<UserMemoryItem[]>([]);

	let inputText = $state('');
	let streaming = $state(false);
	let statusLabel = $state<string | null>(null);
	let streamingText = $state('');
	let decidingId = $state<string | null>(null);
	let generatingInsights = $state(false);
	let newMemoryFact = $state('');
	let error = $state<string | null>(null);
	let chatScrollEl = $state<HTMLDivElement | null>(null);

	const STARTER_PROMPTS = [
		'How much did I spend this month and what are my top categories?',
		'Compare Snowball vs Avalanche payoff on my debts',
		'Create a monthly Dining & Coffee budget of $350',
		'What if I cut expenses by $250/mo for the next 12 months?',
		'Remember that I am saving for a house down payment in 2027'
	];

	async function scrollToBottom() {
		await tick();
		if (chatScrollEl) {
			chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
		}
	}

	async function loadInitial() {
		try {
			const [ths, ins, mems] = await Promise.all([
				api.listThreads(),
				api.listInsights(),
				api.listMemories()
			]);
			threads = ths;
			insights = ins;
			memories = mems;

			const initialQuery = page.url.searchParams.get('q');
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
		error = null;
		streaming = true;
		streamingText = '';
		statusLabel = 'Luna is analyzing your request...';

		try {
			const tid = activeThreadId ?? (await createNewThread());

			// Optimistically render user bubble
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
			await scrollToBottom();

			await api.streamAdvisorMessage(tid, text, {
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
					scrollToBottom();
				},
				onDone: (msg) => {
					if (!messages.some((m) => m.id === msg.id)) {
						messages = [...messages, msg];
					}
					streamingText = '';
					statusLabel = null;
					scrollToBottom();
				},
				onError: (detail) => {
					error = detail;
				}
			});

			// Refresh threads & memories in case title updated or memory saved
			const [ths, mems] = await Promise.all([api.listThreads(), api.listMemories()]);
			threads = ths;
			memories = mems;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Unable to reach Luna right now.';
		} finally {
			streaming = false;
			statusLabel = null;
		}
	}

	async function handleActionDecision(msg: ChatMessage, approved: boolean) {
		if (!activeThreadId) return;
		decidingId = msg.id;
		error = null;
		try {
			const res = await api.decideAdvisorAction(activeThreadId, msg.id, approved);
			messages = messages.map((m) => (m.id === msg.id ? res.message : m));
			await scrollToBottom();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Action decision failed';
		} finally {
			decidingId = null;
		}
	}

	async function handleGenerateInsights() {
		generatingInsights = true;
		error = null;
		try {
			await api.generateInsights();
			insights = await api.listInsights();
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

	function agentLabel(agent: string | null): string {
		if (agent === 'ledger_analyst') return 'Ledger Analyst';
		if (agent === 'document_rag') return 'Document & Memory RAG';
		if (agent === 'wealth_strategist') return 'Wealth Strategist';
		if (agent === 'action_proposer') return 'Action Agent (HITL)';
		return 'Luna Advisor';
	}
</script>

<div class="h-[calc(100vh-5.5rem)] flex flex-col gap-4">
	<!-- Header -->
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 shrink-0">
		<div class="flex items-center gap-3">
			<div class="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-500/25 to-cyan-500/25 border border-emerald-500/35 flex items-center justify-center text-emerald-300">
				<Sparkles class="w-5 h-5" />
			</div>
			<div>
				<h1 class="text-xl font-bold tracking-tight text-white">Luna — AI Financial Advisor</h1>
				<p class="text-xs text-slate-400">
					Multi-Agent LangGraph Copilot · Neon Ledger Tools · Upstash Vector RAG · HITL Action Approvals
				</p>
			</div>
		</div>
	</div>

	{#if error}
		<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs shrink-0">
			{error}
		</div>
	{/if}

	<!-- Main Grid -->
	<div class="flex-1 min-h-0 grid lg:grid-cols-4 gap-4">
		<!-- Left Panel: Chats / Insights / Memory -->
		<div class="card-surface rounded-2xl flex flex-col min-h-0 overflow-hidden">
			<div class="grid grid-cols-3 p-1.5 border-b border-slate-800/80 bg-slate-950/60">
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
					class="py-1.5 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1 cursor-pointer {sideTab === 'insights'
						? 'bg-emerald-500/20 text-emerald-300'
						: 'text-slate-400 hover:text-white'}"
				>
					<Lightbulb class="w-3.5 h-3.5" /> Insights
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

			{#if sideTab === 'chats'}
				<div class="p-3 border-b border-slate-800/70">
					<button
						type="button"
						onclick={createNewThread}
						class="w-full py-2 px-3 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition"
					>
						<Plus class="w-3.5 h-3.5" /> New Conversation
					</button>
				</div>
				<div class="flex-1 overflow-y-auto p-2 space-y-1">
					{#if threads.length === 0}
						<p class="text-xs text-slate-500 text-center py-8 px-3">Start a conversation with Luna.</p>
					{:else}
						{#each threads as th}
							<div
								class="group flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl border transition {activeThreadId === th.id
									? 'bg-slate-800/80 border-emerald-500/35 text-white'
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
									class="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400 cursor-pointer"
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
						class="w-full py-2 px-3 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
					>
						<RefreshCw class="w-3.5 h-3.5 {generatingInsights ? 'animate-spin' : ''}" />
						{generatingInsights ? 'Scanning Ledger...' : 'Generate Digest & Anomalies'}
					</button>
				</div>
				<div class="flex-1 overflow-y-auto p-3 space-y-2.5">
					{#if insights.length === 0}
						<p class="text-xs text-slate-500 text-center py-6">
							Click above to scan for spending anomalies, budget overruns, and generate Luna's digest.
						</p>
					{:else}
						{#each insights as ins}
							<div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1.5">
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
										class="text-slate-500 hover:text-slate-300 text-[10px] cursor-pointer"
									>
										✕
									</button>
								</div>
								<p class="text-[11px] text-slate-300 whitespace-pre-line leading-relaxed">{ins.summary}</p>
							</div>
						{/each}
					{/if}
				</div>
			{:else}
				<!-- Long-term Upstash Vector Memory -->
				<form onsubmit={handleAddMemory} class="p-3 border-b border-slate-800/70 space-y-2">
					<input
						type="text"
						bind:value={newMemoryFact}
						placeholder="Add a financial preference or goal..."
						class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
					/>
					<button
						type="submit"
						class="w-full py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 text-[11px] font-semibold cursor-pointer"
					>
						+ Save to Upstash Memory
					</button>
				</form>
				<div class="flex-1 overflow-y-auto p-3 space-y-2">
					{#if memories.length === 0}
						<p class="text-xs text-slate-500 text-center py-6">
							No memories stored yet. Tell Luna "Remember that..." in chat or add one above.
						</p>
					{:else}
						{#each memories as mem}
							<div class="p-2.5 rounded-xl bg-slate-950/70 border border-slate-800 flex items-start justify-between gap-2 text-xs">
								<span class="text-slate-200 leading-snug">{mem.fact}</span>
								<button
									type="button"
									onclick={() => handleDeleteMemory(mem.id)}
									class="text-slate-500 hover:text-rose-400 shrink-0 cursor-pointer"
								>
									<Trash2 class="w-3.5 h-3.5" />
								</button>
							</div>
						{/each}
					{/if}
				</div>
			{/if}
		</div>

		<!-- Center/Right Chat Stream -->
		<div class="lg:col-span-3 card-surface rounded-2xl flex flex-col min-h-0 overflow-hidden">
			<div bind:this={chatScrollEl} class="flex-1 overflow-y-auto p-5 space-y-4">
				{#if messages.length === 0 && !streaming}
					<div class="h-full flex flex-col items-center justify-center text-center max-w-xl mx-auto space-y-5 py-8">
						<div class="h-14 w-14 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
							<Sparkles class="w-7 h-7" />
						</div>
						<div>
							<h2 class="text-lg font-semibold text-white">Ask Luna anything about your finances</h2>
							<p class="text-xs text-slate-400 mt-1">
								Luna routes your question to specialized agents backed by your live Neon ledger, deterministic Python simulators, and Upstash Vector receipt & memory search.
							</p>
						</div>
						<div class="grid sm:grid-cols-2 gap-2.5 w-full">
							{#each STARTER_PROMPTS as prompt}
								<button
									type="button"
									onclick={() => sendMessage(prompt)}
									class="text-left p-3 rounded-xl bg-slate-950/80 hover:bg-slate-900 border border-slate-800 hover:border-emerald-500/40 text-xs text-slate-300 transition cursor-pointer"
								>
									"{prompt}"
								</button>
							{/each}
						</div>
					</div>
				{:else}
					{#each messages as msg}
						<div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
							<div
								class="max-w-[85%] rounded-2xl px-4 py-3 space-y-2.5 {msg.role === 'user'
									? 'bg-emerald-500 text-slate-950 font-medium text-sm'
									: 'bg-slate-900/90 border border-slate-800 text-slate-100 text-sm'}"
							>
								{#if msg.role === 'assistant'}
									<div class="flex items-center gap-2 text-[11px]">
										<span class="font-semibold text-emerald-400">Luna</span>
										{#if msg.active_agent}
											<span class="px-2 py-0.5 rounded-full bg-slate-800 text-cyan-300 text-[10px] font-medium">
												{agentLabel(msg.active_agent)}
											</span>
										{/if}
									</div>
								{/if}

								<div class="whitespace-pre-wrap leading-relaxed">{msg.content}</div>

								<!-- Interactive HITL Action Approval Card -->
								{#if msg.pending_action}
									<div class="p-3.5 rounded-xl bg-slate-950/90 border {msg.action_status === 'pending' ? 'border-amber-500/40' : msg.action_status === 'executed' ? 'border-emerald-500/40' : 'border-slate-700'} space-y-3">
										<div class="flex items-center justify-between gap-2">
											<span class="text-xs font-semibold text-white">
												{String(msg.pending_action.title || 'Proposed Action')}
											</span>
											<span
												class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full {msg.action_status === 'pending'
													? 'bg-amber-500/15 text-amber-300'
													: msg.action_status === 'executed'
														? 'bg-emerald-500/15 text-emerald-300'
														: 'bg-rose-500/15 text-rose-300'}"
											>
												{msg.action_status}
											</span>
										</div>

										<div class="grid grid-cols-2 gap-1.5 text-[11px] font-mono-num text-slate-300">
											{#each Object.entries(msg.pending_action).filter(([k, v]) => v !== null && !['title', 'summary'].includes(k)) as [k, v]}
												<div class="bg-slate-900/80 px-2 py-1 rounded">
													<span class="text-slate-500">{k}:</span> {String(v)}
												</div>
											{/each}
										</div>

										{#if msg.action_status === 'pending'}
											<div class="flex items-center gap-2 pt-1">
												<button
													type="button"
													disabled={decidingId === msg.id}
													onclick={() => handleActionDecision(msg, true)}
													class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
												>
													<CheckCircle2 class="w-3.5 h-3.5" />
													{decidingId === msg.id ? 'Executing...' : 'Approve & Execute'}
												</button>
												<button
													type="button"
													disabled={decidingId === msg.id}
													onclick={() => handleActionDecision(msg, false)}
													class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-rose-500/20 text-slate-300 hover:text-rose-300 text-xs font-medium cursor-pointer disabled:opacity-50"
												>
													<XCircle class="w-3.5 h-3.5" />
													Reject
												</button>
											</div>
										{/if}
									</div>
								{/if}

								<!-- Citations -->
								{#if msg.citations && msg.citations.length > 0}
									<div class="flex flex-wrap gap-1.5 pt-1">
										{#each msg.citations as cit}
											<span class="text-[10px] px-2 py-0.5 rounded-md bg-slate-950 border border-slate-800 text-slate-400">
												<strong class="text-slate-300">{cit.source}:</strong> {cit.label}
											</span>
										{/each}
									</div>
								{/if}
							</div>
						</div>
					{/each}

					{#if streaming}
						<div class="flex justify-start">
							<div class="max-w-[85%] rounded-2xl px-4 py-3 bg-slate-900/90 border border-emerald-500/30 text-sm text-slate-100 space-y-2">
								<div class="flex items-center gap-2 text-xs text-emerald-400">
									<Sparkles class="w-3.5 h-3.5 animate-pulse" />
									<span>{statusLabel || 'Luna is responding...'}</span>
								</div>
								{#if streamingText}
									<div class="whitespace-pre-wrap leading-relaxed">{streamingText}</div>
								{/if}
							</div>
						</div>
					{/if}
				{/if}
			</div>

			<!-- Composer -->
			<form
				onsubmit={(e) => {
					e.preventDefault();
					sendMessage();
				}}
				class="p-3.5 border-t border-slate-800/80 bg-slate-950/70 flex items-center gap-2.5"
			>
				<input
					type="text"
					disabled={streaming}
					bind:value={inputText}
					placeholder="Ask Luna about spending, debts, receipts, or say 'Create a $400 Dining budget'..."
					class="flex-1 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
				/>
				<button
					type="submit"
					disabled={streaming || !inputText.trim()}
					class="px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-slate-950 font-semibold text-sm inline-flex items-center gap-1.5 cursor-pointer transition"
				>
					<Send class="w-4 h-4" />
					Send
				</button>
			</form>
		</div>
	</div>
</div>
