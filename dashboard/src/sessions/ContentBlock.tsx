import { useState } from 'react';
import Markdown from 'react-markdown';

interface BlockProps {
  block: Record<string, unknown>;
}

export default function ContentBlock({ block }: BlockProps) {
  const type = block.type as string;

  if (type === 'text') {
    return (
      <div className="prose prose-invert prose-sm max-w-none [&_pre]:bg-code-bg [&_pre]:border [&_pre]:border-border [&_pre]:rounded [&_code]:text-sm">
        <Markdown>{String(block.text || '')}</Markdown>
      </div>
    );
  }

  if (type === 'tool_use') {
    return <ToolUseBlock block={block} />;
  }

  if (type === 'tool_result') {
    return <ToolResultBlock block={block} />;
  }

  if (type === 'thinking') {
    return <ThinkingBlock text={String(block.thinking || block.text || '')} />;
  }

  if (type === 'image') {
    const src = block.source as Record<string, unknown> | undefined;
    if (src?.type === 'base64') {
      return (
        <img
          src={`data:${src.media_type};base64,${src.data}`}
          alt="Session image"
          className="max-w-md rounded border border-border"
        />
      );
    }
    return <span className="text-[var(--text-tertiary)] italic text-sm">[image reference]</span>;
  }

  if (type === 'summary') {
    return (
      <div className="text-[var(--text-tertiary)] italic text-sm border-l-2 border-[var(--border)] pl-3">
        {String(block.text || '')}
      </div>
    );
  }

  return (
    <pre className="text-sm text-[var(--text-tertiary)] bg-[var(--bg-secondary)] p-2 rounded overflow-x-auto">
      {JSON.stringify(block, null, 2)}
    </pre>
  );
}

function ToolUseBlock({ block }: BlockProps) {
  const [open, setOpen] = useState(false);
  const name = String(block.name || 'tool');
  const input = block.input as Record<string, unknown> | undefined;
  const inputStr = input ? JSON.stringify(input, null, 2) : '';
  const isLong = inputStr.length > 200;

  return (
    <div className="ml-2 border border-[var(--border)] rounded-lg bg-[var(--bg-secondary)] text-sm">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--surface-hover)] transition-colors rounded-t-lg"
      >
        <svg className="w-3.5 h-3.5 text-[var(--text-tertiary)] shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
        <span className="text-[var(--text-secondary)] font-mono font-medium">{name}</span>
        {typeof block.tool_use_id === 'string' && (
          <span className="text-[var(--text-tertiary)] font-mono text-xs">{block.tool_use_id.slice(0, 8)}</span>
        )}
        <span className="ml-auto text-[var(--text-tertiary)] text-xs">{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {(open || !isLong) && inputStr && (
        <pre className="px-3 py-2 border-t border-[var(--border)] overflow-x-auto text-[var(--text-secondary)] whitespace-pre-wrap font-mono text-xs">
          {inputStr}
        </pre>
      )}
    </div>
  );
}

function ToolResultBlock({ block }: BlockProps) {
  const [open, setOpen] = useState(false);
  const content = String(block.content || block.output || '');
  const lines = content.split('\n');

  return (
    <div className="ml-4 border border-[var(--border)] rounded-lg bg-[var(--bg-secondary)] text-sm opacity-70">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--surface-hover)] transition-colors rounded-t-lg"
      >
        <span className="text-[var(--text-tertiary)] text-xs">result</span>
        <span className="text-[var(--text-tertiary)] text-xs">({String(lines.length)} lines)</span>
        <span className="ml-auto text-[var(--text-tertiary)] text-xs">{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {open && (
        <pre className="px-3 py-2 border-t border-[var(--border)] overflow-x-auto text-[var(--text-tertiary)] whitespace-pre-wrap max-h-96 overflow-y-auto font-mono text-xs">
          {content}
        </pre>
      )}
    </div>
  );
}

function ThinkingBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg bg-thinking-bg border border-[var(--border)]">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-3 py-1.5 text-left text-sm text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors flex items-center gap-2"
      >
        <span>Thinking</span>
        <span>{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {open && (
        <pre className="px-3 py-2 border-t border-[var(--border)] text-sm text-[var(--text-tertiary)] whitespace-pre-wrap max-h-80 overflow-y-auto">
          {text}
        </pre>
      )}
    </div>
  );
}
