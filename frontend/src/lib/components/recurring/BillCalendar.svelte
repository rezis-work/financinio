<script lang="ts">
	import type { RecurringItem } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import { ChevronLeft, ChevronRight, Calendar as CalendarIcon } from 'lucide-svelte';

	let {
		items,
		currency = 'USD',
		privacyMode = false,
		onSelectItem
	}: {
		items: RecurringItem[];
		currency: string;
		privacyMode?: boolean;
		onSelectItem: (item: RecurringItem) => void;
	} = $props();

	let viewDate = $state(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
	let selectedDayIso = $state<string | null>(null);

	function toIso(d: Date): string {
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}

	const todayIso = toIso(new Date());

	let year = $derived(viewDate.getFullYear());
	let month = $derived(viewDate.getMonth());
	let monthLabel = $derived(
		viewDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
	);

	function shiftMonth(delta: number) {
		viewDate = new Date(year, month + delta, 1);
		selectedDayIso = null;
	}

	function advanceByCadence(d: Date, cadence: RecurringItem['cadence'], step = 1): Date {
		const next = new Date(d.getFullYear(), d.getMonth(), d.getDate());
		if (cadence === 'weekly') next.setDate(next.getDate() + 7 * step);
		else if (cadence === 'biweekly') next.setDate(next.getDate() + 14 * step);
		else if (cadence === 'monthly') next.setMonth(next.getMonth() + step);
		else if (cadence === 'quarterly') next.setMonth(next.getMonth() + 3 * step);
		else if (cadence === 'yearly') next.setFullYear(next.getFullYear() + step);
		return next;
	}

	// Project active recurring occurrences into the visible month
	let eventsByDate = $derived.by(() => {
		const map = new Map<string, RecurringItem[]>();
		const monthStart = new Date(year, month, 1);
		const monthEnd = new Date(year, month + 1, 0);

		for (const item of items) {
			if (!item.is_active || !item.next_due_date) continue;
			const [iy, im, id] = item.next_due_date.split('-').map(Number);
			if (!iy || !im || !id) continue;
			let cur = new Date(iy, im - 1, id);

			// Step backward if anchor is after visible month
			let guard = 0;
			while (cur > monthEnd && guard < 40) {
				cur = advanceByCadence(cur, item.cadence, -1);
				guard++;
			}
			// Step forward into visible month
			guard = 0;
			while (cur < monthStart && guard < 120) {
				cur = advanceByCadence(cur, item.cadence, 1);
				guard++;
			}
			// Collect all occurrences inside visible month
			guard = 0;
			while (cur >= monthStart && cur <= monthEnd && guard < 10) {
				const key = toIso(cur);
				const list = map.get(key) ?? [];
				list.push(item);
				map.set(key, list);
				cur = advanceByCadence(cur, item.cadence, 1);
				guard++;
			}
		}
		return map;
	});

	let calendarCells = $derived.by(() => {
		const firstDayOfWeek = (new Date(year, month, 1).getDay() + 6) % 7; // Mon=0 .. Sun=6
		const daysInMonth = new Date(year, month + 1, 0).getDate();
		const cells: Array<{ day: number | null; iso: string | null; events: RecurringItem[]; outTotal: number; inTotal: number }> = [];

		for (let i = 0; i < firstDayOfWeek; i++) {
			cells.push({ day: null, iso: null, events: [], outTotal: 0, inTotal: 0 });
		}
		for (let d = 1; d <= daysInMonth; d++) {
			const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
			const events = eventsByDate.get(iso) ?? [];
			let outTotal = 0;
			let inTotal = 0;
			for (const ev of events) {
				const a = Number.parseFloat(ev.amount) || 0;
				if (ev.direction === 'inflow') inTotal += a;
				else outTotal += a;
			}
			cells.push({ day: d, iso, events, outTotal, inTotal });
		}
		return cells;
	});

	let selectedEvents = $derived(selectedDayIso ? eventsByDate.get(selectedDayIso) ?? [] : []);
</script>

<div class="card-surface rounded-2xl p-5 space-y-4">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div class="flex items-center gap-2">
			<CalendarIcon class="w-4 h-4 text-cyan-400" />
			<h2 class="text-sm font-semibold text-white">Monthly Bill Calendar</h2>
		</div>
		<div class="flex items-center gap-2">
			<div class="hidden sm:flex items-center gap-3 text-[10px] text-slate-400 mr-2">
				<span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-rose-400"></span>Bill</span>
				<span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-emerald-400"></span>Income</span>
			</div>
			<div class="inline-flex items-center rounded-xl bg-slate-950 border border-slate-800 p-0.5 text-xs">
				<button
					type="button"
					onclick={() => shiftMonth(-1)}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
					aria-label="Previous month"
				>
					<ChevronLeft class="w-3.5 h-3.5" />
				</button>
				<span class="px-2.5 font-semibold text-white min-w-[112px] text-center">{monthLabel}</span>
				<button
					type="button"
					onclick={() => shiftMonth(1)}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
					aria-label="Next month"
				>
					<ChevronRight class="w-3.5 h-3.5" />
				</button>
			</div>
		</div>
	</div>

	<!-- Weekday Headers -->
	<div class="grid grid-cols-7 gap-1 text-center text-[10px] font-semibold uppercase tracking-wider text-slate-500">
		{#each ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as wd}
			<div class="py-1">{wd}</div>
		{/each}
	</div>

	<!-- Days Grid -->
	<div class="grid grid-cols-7 gap-1">
		{#each calendarCells as cell}
			{#if cell.day === null}
				<div class="h-14 sm:h-16 rounded-xl bg-slate-950/25"></div>
			{:else}
				{@const isToday = cell.iso === todayIso}
				{@const isSelected = cell.iso === selectedDayIso}
				{@const hasEvents = cell.events.length > 0}
				<button
					type="button"
					onclick={() => (selectedDayIso = isSelected ? null : cell.iso)}
					class="h-14 sm:h-16 p-1.5 rounded-xl border text-left flex flex-col justify-between transition cursor-pointer {isSelected
						? 'bg-emerald-500/15 border-emerald-400/60'
						: isToday
							? 'bg-cyan-500/10 border-cyan-500/40'
							: hasEvents
								? 'bg-slate-900/90 border-slate-700/80 hover:border-slate-500'
								: 'bg-slate-950/50 border-slate-800/60 hover:border-slate-700'}"
				>
					<div class="flex items-center justify-between w-full">
						<span
							class="text-[11px] font-mono-num font-semibold {isToday
								? 'text-cyan-300'
								: hasEvents
									? 'text-white'
									: 'text-slate-500'}"
						>
							{cell.day}
						</span>
						{#if hasEvents}
							<div class="flex items-center gap-0.5">
								{#if cell.outTotal > 0}
									<span class="w-1.5 h-1.5 rounded-full {isToday ? 'bg-amber-400' : 'bg-rose-400'}"></span>
								{/if}
								{#if cell.inTotal > 0}
									<span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
								{/if}
							</div>
						{/if}
					</div>

					{#if hasEvents}
						<div class="space-y-0.5 overflow-hidden">
							{#if cell.outTotal > 0}
								<div class="text-[9px] sm:text-[10px] font-mono-num font-semibold text-rose-300 truncate {privacyMode ? 'privacy-blur' : ''}">
									-{Math.round(cell.outTotal)}
								</div>
							{/if}
							{#if cell.inTotal > 0}
								<div class="text-[9px] sm:text-[10px] font-mono-num font-semibold text-emerald-300 truncate {privacyMode ? 'privacy-blur' : ''}">
									+{Math.round(cell.inTotal)}
								</div>
							{/if}
						</div>
					{/if}
				</button>
			{/if}
		{/each}
	</div>

	<!-- Selected Day Detail Strip -->
	{#if selectedDayIso}
		<div class="p-3.5 rounded-xl bg-slate-950/85 border border-slate-800 space-y-2">
			<div class="flex items-center justify-between text-xs">
				<span class="font-semibold text-white">Scheduled on {selectedDayIso}</span>
				<button
					type="button"
					onclick={() => (selectedDayIso = null)}
					class="text-slate-400 hover:text-white text-[11px] cursor-pointer"
				>
					Clear
				</button>
			</div>
			{#if selectedEvents.length === 0}
				<p class="text-xs text-slate-500">No bills or recurring income scheduled on this date.</p>
			{:else}
				<div class="space-y-1.5">
					{#each selectedEvents as ev}
						<button
							type="button"
							onclick={() => onSelectItem(ev)}
							class="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-xs transition cursor-pointer"
						>
							<div class="flex items-center gap-2 min-w-0">
								<span class="w-2 h-2 rounded-full {ev.direction === 'inflow' ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
								<span class="font-medium text-white truncate">{ev.merchant_name}</span>
								<span class="text-[10px] text-slate-400 capitalize">({ev.cadence})</span>
							</div>
							<span
								class="font-mono-num font-semibold shrink-0 {ev.direction === 'inflow'
									? 'text-emerald-400'
									: 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
							>
								{ev.direction === 'inflow' ? '+' : '-'}{formatMoney(ev.amount, ev.currency || currency)}
							</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>
