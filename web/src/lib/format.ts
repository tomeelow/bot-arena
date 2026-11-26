/** A probability as a percentage that never claims certainty the data can't give. */
export function probability(p: number): string {
	if (p > 0.99) return '>99%';
	if (p < 0.01) return '<1%';
	return `${Math.round(p * 100)}%`;
}
