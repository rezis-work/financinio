<script lang="ts">
	import { browser } from '$app/environment';
	import { Marked } from 'marked';
	import DOMPurify from 'dompurify';

	let {
		content,
		compact = false
	}: {
		content: string;
		compact?: boolean;
	} = $props();

	const md = new Marked({
		gfm: true,
		breaks: true
	});

	function escapeHtml(text: string): string {
		return text
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;');
	}

	let renderedHtml = $derived.by(() => {
		const raw = content || '';
		if (!raw.trim()) return '';
		if (!browser) {
			return `<p>${escapeHtml(raw)}</p>`;
		}
		const parsed = md.parse(raw) as string;
		// Wrap tables in a horizontally scrollable container for mobile responsiveness
		const withResponsiveTables = parsed
			.replaceAll('<table>', '<div class="luna-table-wrap"><table>')
			.replaceAll('</table>', '</table></div>');

		return DOMPurify.sanitize(withResponsiveTables, {
			USE_PROFILES: { html: true },
			ADD_ATTR: ['target', 'rel']
		});
	});
</script>

<div class="luna-prose {compact ? 'luna-prose-compact' : ''}">
	{@html renderedHtml}
</div>
