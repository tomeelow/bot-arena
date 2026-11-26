/** A probability as a percentage that never claims certainty the data can't give. */
export function probability(p: number): string {
	if (p > 0.99) return '>99%';
	if (p < 0.01) return '<1%';
	return `${Math.round(p * 100)}%`;
}

/** A length of time in the largest unit that keeps it readable. */
export function duration(seconds: number | null): string {
	if (seconds === null) return '–';
	if (seconds < 90) return `${Math.round(seconds)} s`;
	if (seconds < 90 * 60) return `${Math.round(seconds / 60)} min`;
	if (seconds < 48 * 3600) return `${(seconds / 3600).toFixed(1)} h`;
	return `${(seconds / 86400).toFixed(1)} days`;
}

/** A share as a whole percentage. Unlike `probability`, 0% and 100% are real counts here. */
export function share(fraction: number): string {
	return `${Math.round(fraction * 100)}%`;
}
