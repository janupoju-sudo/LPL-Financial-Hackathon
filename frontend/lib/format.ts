export const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
export const percent = (ratio: number | null) => ratio === null ? '—' : `${(ratio * 100).toFixed(1)}%`;
