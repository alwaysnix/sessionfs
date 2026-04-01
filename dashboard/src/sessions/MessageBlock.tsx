import ContentBlock from './ContentBlock';
import RelativeDate from '../components/RelativeDate';

interface MessageProps {
  message: Record<string, unknown>;
}

const ROLE_BADGE_STYLES: Record<string, string> = {
  user: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  assistant: 'bg-green-500/10 text-green-400 border-green-500/20',
  tool: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
  system: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  developer: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
};

export default function MessageBlock({ message }: MessageProps) {
  const role = String(message.role || 'unknown');
  const content = message.content as Record<string, unknown>[] | string | undefined;
  const timestamp = message.timestamp as string | undefined;
  const model = message.model as string | undefined;
  const isSidechain = message.is_sidechain as boolean | undefined;

  if (isSidechain) return null; // Skip sidechain messages in main view

  const blocks: Record<string, unknown>[] = [];
  if (typeof content === 'string') {
    blocks.push({ type: 'text', text: content });
  } else if (Array.isArray(content)) {
    blocks.push(...content);
  }

  const isUser = role === 'user';
  const badgeStyle = ROLE_BADGE_STYLES[role] || 'bg-gray-500/10 text-gray-400 border-gray-500/20';
  const borderClass = isUser ? 'border-l-2 border-l-[var(--brand)]' : '';

  return (
    <div className={`${borderClass} pl-4 py-2`}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium px-1.5 py-0.5 rounded border ${badgeStyle}`}>
            {role === 'assistant' ? 'Assistant' : role === 'user' ? 'User' : role === 'system' ? 'System' : role.charAt(0).toUpperCase() + role.slice(1)}
          </span>
          {model && <span className="text-[var(--text-tertiary)] text-xs font-mono">{model}</span>}
        </div>
        {timestamp && (
          <span className="text-xs text-[var(--text-tertiary)]">
            <RelativeDate iso={timestamp} />
          </span>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {blocks.map((block, i) => (
          <ContentBlock key={i} block={block} />
        ))}
      </div>
    </div>
  );
}
