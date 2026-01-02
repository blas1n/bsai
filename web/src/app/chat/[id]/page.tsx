'use client';

import { useParams } from 'next/navigation';
import { ChatContainer } from '@/components/chat';

export default function ChatSessionPage() {
  const params = useParams();
  const sessionId = params.id as string;

  return <ChatContainer sessionId={sessionId} />;
}
