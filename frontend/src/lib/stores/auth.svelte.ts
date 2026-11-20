import { api, clearTokens, getStoredAccessToken, saveTokens } from '$lib/api/client';
import type { User } from '$lib/api/types';

class AuthStore {
	user = $state<User | null>(null);
	loading = $state(true);

	async hydrate(): Promise<User | null> {
		if (!getStoredAccessToken()) {
			this.user = null;
			this.loading = false;
			return null;
		}
		this.loading = true;
		try {
			this.user = await api.me();
			return this.user;
		} catch {
			clearTokens();
			this.user = null;
			return null;
		} finally {
			this.loading = false;
		}
	}

	async login(email: string, password: string): Promise<void> {
		const res = await api.login({ email, password });
		saveTokens(res.access_token, res.refresh_token);
		this.user = res.user;
	}

	async register(
		email: string,
		password: string,
		fullName: string,
		baseCurrency: string
	): Promise<void> {
		const res = await api.register({
			email,
			password,
			full_name: fullName,
			base_currency: baseCurrency
		});
		saveTokens(res.access_token, res.refresh_token);
		this.user = res.user;
	}

	async logout(): Promise<void> {
		await api.logout();
		this.user = null;
	}
}

export const auth = new AuthStore();
