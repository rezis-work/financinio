export function formatMoney(amount: string | number, currency = 'USD'): string {
	const num = typeof amount === 'string' ? Number.parseFloat(amount) : amount;
	if (Number.isNaN(num)) return '$0.00';
	try {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency,
			minimumFractionDigits: 2,
			maximumFractionDigits: 2
		}).format(num);
	} catch {
		return `${currency} ${num.toFixed(2)}`;
	}
}

export function formatShortMonth(yyyyMm: string): string {
	const [year, month] = yyyyMm.split('-').map(Number);
	if (!year || !month) return yyyyMm;
	return new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short' });
}

export function formatDate(isoDate: string): string {
	const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
	if (!y || !m || !d) return isoDate;
	return new Date(y, m - 1, d).toLocaleDateString('en-US', {
		month: 'short',
		day: 'numeric',
		year: 'numeric'
	});
}
