import { expect, it } from 'vitest';
import { duration, probability, share } from './format';

it('never shows 0% or 100% for a probability', () => {
	expect([1 - 2 ** -21, 0.995, 0.87, 0.004, 0].map(probability)).toEqual([
		'>99%',
		'>99%',
		'87%',
		'<1%',
		'<1%'
	]);
});

it('shows a counted share as it is, 0% and 100% included', () => {
	expect([0, 0.25, 1].map(share)).toEqual(['0%', '25%', '100%']);
});

it('shows durations in a readable unit', () => {
	expect([null, 42, 600, 3 * 3600, 3 * 86400].map(duration)).toEqual([
		'–',
		'42 s',
		'10 min',
		'3.0 h',
		'3.0 days'
	]);
});
