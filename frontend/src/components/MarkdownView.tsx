import { useRef, useState, type CSSProperties } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Rich Markdown viewer for artifact files.
 *
 * Behaviors on top of plain react-markdown:
 *
 *   - GFM task-list checkboxes (``- [ ]`` / ``- [x]``) are INTERACTIVE.
 *     User clicks toggle state; optionally persisted to localStorage so
 *     the checklist survives refreshes.
 *   - Headings, code blocks, tables, and lists use the app's design
 *     tokens instead of browser defaults.
 *   - Links open in a new tab with a rel-noopener guard.
 *
 * Prop contract:
 *   - ``content``       — the raw markdown string
 *   - ``storageKey``    — (optional) unique key for persisting checkbox
 *                         state across sessions. Omit for in-memory only.
 */

const ph = {
  color: 'var(--color-text)',
  fontFamily: 'var(--font-sans)',
  fontSize: '0.875rem',
  lineHeight: 1.7,
} as const;

const headingBase: CSSProperties = { color: 'var(--color-text-bright)', fontWeight: 700, marginTop: '1.2em', marginBottom: '0.5em' };

export default function MarkdownView({
  content,
  storageKey,
}: {
  content: string;
  storageKey?: string;
}) {
  const [checked, setChecked] = useState<Record<number, boolean>>(() => {
    if (!storageKey) return {};
    try {
      return JSON.parse(localStorage.getItem(`md-checks:${storageKey}`) || '{}');
    } catch {
      return {};
    }
  });

  // Simple depth-first index for each task-list checkbox. Resets on every
  // render; react-markdown walks the tree in source order so the index
  // stays stable as long as the underlying markdown content doesn't change.
  const taskIndexRef = useRef(0);
  taskIndexRef.current = 0;

  const toggle = (idx: number) => {
    setChecked((prev) => {
      const next = { ...prev, [idx]: !prev[idx] };
      if (storageKey) {
        try {
          localStorage.setItem(`md-checks:${storageKey}`, JSON.stringify(next));
        } catch { /* quota / private mode — ignore */ }
      }
      return next;
    });
  };

  return (
    <div style={ph} className="md-view">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 style={{ ...headingBase, fontSize: '1.5rem', paddingBottom: '0.35em', borderBottom: '1px solid var(--color-rule)' }}>{children}</h1>,
          h2: ({ children }) => <h2 style={{ ...headingBase, fontSize: '1.2rem', paddingBottom: '0.3em', borderBottom: '1px solid var(--color-fence)' }}>{children}</h2>,
          h3: ({ children }) => <h3 style={{ ...headingBase, fontSize: '1.05rem' }}>{children}</h3>,
          h4: ({ children }) => <h4 style={{ ...headingBase, fontSize: '0.95rem' }}>{children}</h4>,
          h5: ({ children }) => <h5 style={{ ...headingBase, fontSize: '0.875rem' }}>{children}</h5>,
          h6: ({ children }) => <h6 style={{ ...headingBase, fontSize: '0.8125rem', color: 'var(--color-text-dim)' }}>{children}</h6>,
          p:  ({ children }) => <p style={{ margin: '0.8em 0' }}>{children}</p>,
          strong: ({ children }) => <strong style={{ color: 'var(--color-text-bright)' }}>{children}</strong>,
          em: ({ children }) => <em style={{ color: 'var(--color-text-bright)' }}>{children}</em>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer"
               style={{ color: 'var(--color-ember)', textDecoration: 'underline' }}>
              {children}
            </a>
          ),
          code: ({ children, className }) => {
            // Inline vs block distinguishable by className presence (``language-*``).
            if (className) {
              return (
                <code style={{ fontFamily: 'var(--font-mono)' }}>{children}</code>
              );
            }
            return (
              <code style={{
                background: 'var(--color-well)',
                border: '1px solid var(--color-fence)',
                borderRadius: '4px',
                padding: '1px 5px',
                fontSize: '0.85em',
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-ember)',
              }}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre style={{
              background: '#0d1221',
              border: '1px solid var(--color-fence)',
              borderRadius: '8px',
              padding: '12px 14px',
              margin: '0.9em 0',
              overflowX: 'auto',
              fontSize: '0.75rem',
              fontFamily: 'var(--font-mono)',
              color: '#e2e8f0',
              lineHeight: 1.55,
            }}>
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote style={{
              borderLeft: '3px solid var(--color-ember)',
              paddingLeft: '1em',
              margin: '0.9em 0',
              color: 'var(--color-text-dim)',
              fontStyle: 'italic',
            }}>
              {children}
            </blockquote>
          ),
          ul: ({ children }) => <ul style={{ margin: '0.8em 0', paddingLeft: '1.5em', listStyle: 'disc' }}>{children}</ul>,
          ol: ({ children }) => <ol style={{ margin: '0.8em 0', paddingLeft: '1.5em', listStyle: 'decimal' }}>{children}</ol>,
          li: ({ children, className }) => {
            // GFM renders task-list <li>s with className="task-list-item".
            // Inline-list them (no bullet) so our interactive checkbox lines up.
            const isTask = className?.includes('task-list-item');
            return (
              <li style={{
                margin: '0.3em 0',
                listStyle: isTask ? 'none' : undefined,
                marginLeft: isTask ? '-1.5em' : undefined,
              }}>
                {children}
              </li>
            );
          },
          input: (props) => {
            if (props.type !== 'checkbox') return <input {...props} />;
            const idx = taskIndexRef.current++;
            const isChecked = checked[idx] ?? Boolean(props.checked);
            return (
              <input
                type="checkbox"
                checked={isChecked}
                onChange={() => toggle(idx)}
                style={{ marginRight: '0.6em', cursor: 'pointer', verticalAlign: 'middle' }}
              />
            );
          },
          table: ({ children }) => (
            <div style={{ overflowX: 'auto', margin: '0.9em 0' }}>
              <table style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '0.8125rem',
                border: '1px solid var(--color-rule)',
              }}>
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th style={{
              background: 'var(--color-well)',
              border: '1px solid var(--color-rule)',
              padding: '0.45em 0.7em',
              textAlign: 'left',
              color: 'var(--color-text-bright)',
              fontWeight: 600,
              fontSize: '0.75rem',
              textTransform: 'uppercase',
              letterSpacing: '0.03em',
            }}>
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td style={{
              border: '1px solid var(--color-rule)',
              padding: '0.45em 0.7em',
              verticalAlign: 'top',
            }}>
              {children}
            </td>
          ),
          hr: () => <hr style={{ border: 0, borderTop: '1px solid var(--color-fence)', margin: '1.5em 0' }} />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
