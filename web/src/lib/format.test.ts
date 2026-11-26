import { expect, it } from 'vitest';
import { probability } from './format';

it('never shows 0% or 100% for a probability', () => {
	expect([1 - 2 ** -21, 0.995, 0.87, 0.004, 0].map(probability)).toEqual([
		'>99%',
		'>99%',
		'87%',
		'<1%',
		'<1%'
	]);
});
