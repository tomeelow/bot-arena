<script lang="ts">
	import { python } from '@codemirror/lang-python';
	import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
	import { tags as t } from '@lezer/highlight';
	import { basicSetup, EditorView } from 'codemirror';
	import { untrack } from 'svelte';

	let { value = $bindable(''), label }: { value: string; label: string } = $props();
	let parent: HTMLElement;
	let view: EditorView | null = null;

	const theme = EditorView.theme({
		'&': {
			blockSize: '100%',
			backgroundColor: 'var(--surface)',
			color: 'var(--ink)',
			fontSize: '0.875rem'
		},
		'.cm-content': { fontFamily: 'var(--mono)', caretColor: 'var(--ink)' },
		'.cm-gutters': { backgroundColor: 'var(--surface)', color: 'var(--muted)', border: 'none' },
		'.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'var(--highlight)' },
		'&.cm-focused': { outline: '2px solid var(--accent)' },
		'.cm-scroller': { overflow: 'auto' }
	});

	// Site colours, so code stays readable in light and dark mode alike.
	const highlight = HighlightStyle.define([
		{ tag: [t.keyword, t.controlKeyword, t.definitionKeyword], color: 'var(--seat-0)' },
		{ tag: [t.string, t.docString], color: 'var(--board-crystal)' },
		{ tag: [t.comment, t.lineComment], color: 'var(--muted)', fontStyle: 'italic' },
		{ tag: [t.number, t.bool, t.null], color: 'var(--seat-1)' },
		{ tag: [t.function(t.variableName), t.function(t.propertyName)], color: 'var(--accent)' },
		{ tag: t.className, color: 'var(--accent)', fontWeight: '600' }
	]);

	$effect(() => {
		// In a shadow root, CodeMirror's styles go in a constructed stylesheet, which the CSP
		// allows; in the document they'd need an inline <style> element, which it blocks.
		const root = parent.shadowRoot ?? parent.attachShadow({ mode: 'open' });
		const editor = new EditorView({
			doc: untrack(() => value),
			root,
			parent: root,
			extensions: [
				basicSetup,
				python(),
				syntaxHighlighting(highlight),
				theme,
				EditorView.contentAttributes.of({ 'aria-label': label }),
				EditorView.updateListener.of((update) => {
					if (update.docChanged) value = update.state.doc.toString();
				})
			]
		});
		view = editor;
		return () => editor.destroy();
	});

	// A file opened or dropped elsewhere replaces the whole document.
	$effect(() => {
		const text = value;
		if (view && text !== view.state.doc.toString()) {
			view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
		}
	});
</script>

<div class="editor" bind:this={parent}></div>

<style>
	.editor {
		block-size: 32rem;
		border: 1px solid var(--line);
		border-radius: 4px;
		overflow: hidden;
	}
</style>
