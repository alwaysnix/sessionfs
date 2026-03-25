import { useState, useEffect, useRef } from 'react';
import { useMessages } from '../hooks/useMessages';
import MessageBlock from './MessageBlock';

interface Props {
  sessionId: string;
}

export default function ConversationView({ sessionId }: Props) {
  const [page, setPage] = useState(1);
  const [allMessages, setAllMessages] = useState<Record<string, unknown>[]>([]);
  const { data, isLoading, error } = useMessages(sessionId, page, 50);
  const prevSessionId = useRef(sessionId);

  // Reset when session changes
  useEffect(() => {
    if (sessionId !== prevSessionId.current) {
      setAllMessages([]);
      setPage(1);
      prevSessionId.current = sessionId;
    }
  }, [sessionId]);

  // Append new page data
  useEffect(() => {
    if (data?.messages) {
      setAllMessages(prev => {
        if (page === 1) return data.messages;
        // Avoid duplicates
        const existing = new Set(prev.map((_, i) => i));
        if (existing.size >= (page - 1) * 50 + data.messages.length) return prev;
        return [...prev, ...data.messages];
      });
    }
  }, [data, page]);

  if (error) {
    return (
      <div className="p-4 text-red-400 text-sm">
        Failed to load messages: {String(error)}
      </div>
    );
  }

  if (isLoading && allMessages.length === 0) {
    return <div className="p-4 text-text-muted">Loading messages...</div>;
  }

  const total = data?.total ?? allMessages.length;
  const hasMore = data?.has_more ?? false;

  return (
    <div className="flex flex-col gap-3 p-4">
      {allMessages.length === 0 && (
        <p className="text-text-muted text-sm">No messages in this session.</p>
      )}
      {allMessages.map((msg, i) => (
        <MessageBlock key={i} message={msg} />
      ))}
      {hasMore && (
        <button
          onClick={() => setPage((p) => p + 1)}
          disabled={isLoading}
          className="self-center px-4 py-1.5 text-sm bg-bg-secondary border border-border rounded hover:border-text-muted transition-colors text-text-secondary"
        >
          {isLoading ? 'Loading...' : `Load more (${total - allMessages.length} remaining)`}
        </button>
      )}
    </div>
  );
}
