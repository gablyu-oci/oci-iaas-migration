export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014';
  return new Date(dateStr).toLocaleString();
}

export function formatCost(cost: number | null): string {
  if (cost === null || cost === undefined) return '$0.00';
  return `$${cost.toFixed(4)}`;
}
