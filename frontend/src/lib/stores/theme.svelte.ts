class ThemeStore {
	mode = $state<'dark' | 'light'>('dark');

	hydrate() {
		if (typeof window === 'undefined') return;
		const saved = localStorage.getItem('financinio_theme');
		this.mode = saved === 'light' ? 'light' : 'dark';
		this.apply();
	}

	toggle() {
		this.mode = this.mode === 'dark' ? 'light' : 'dark';
		if (typeof window !== 'undefined') {
			localStorage.setItem('financinio_theme', this.mode);
		}
		this.apply();
	}

	private apply() {
		if (typeof document === 'undefined') return;
		document.documentElement.classList.toggle('light', this.mode === 'light');
		document.documentElement.classList.toggle('dark', this.mode === 'dark');
	}
}

export const theme = new ThemeStore();
