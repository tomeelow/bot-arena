/** Cloudflare Pages' `_headers` format (static/_headers): an unindented path pattern, where
 * `*` matches anything, then indented `Name: value` lines. A header set by several matching
 * rules is joined with commas, as Pages does. */
export interface HeaderRule {
	pattern: RegExp;
	headers: [string, string][];
}

export function parseHeaders(text: string): HeaderRule[] {
	const rules: HeaderRule[] = [];
	for (const line of text.split('\n')) {
		const trimmed = line.trim();
		if (!trimmed || trimmed.startsWith('#')) continue;
		if (!/^\s/.test(line)) {
			const source = trimmed
				.split('*')
				.map((part) => part.replace(/[.+?^${}()|[\]\\]/g, '\\$&'))
				.join('.*');
			rules.push({ pattern: new RegExp(`^${source}$`), headers: [] });
			continue;
		}
		const rule = rules.at(-1);
		const colon = trimmed.indexOf(':');
		if (!rule || colon < 1) throw new Error(`_headers: unexpected line ${JSON.stringify(line)}`);
		rule.headers.push([trimmed.slice(0, colon).trim(), trimmed.slice(colon + 1).trim()]);
	}
	return rules;
}

export function headersFor(rules: HeaderRule[], path: string): Map<string, string> {
	const out = new Map<string, string>();
	for (const rule of rules.filter((r) => r.pattern.test(path))) {
		for (const [name, value] of rule.headers) {
			const before = out.get(name);
			out.set(name, before === undefined ? value : `${before}, ${value}`);
		}
	}
	return out;
}
