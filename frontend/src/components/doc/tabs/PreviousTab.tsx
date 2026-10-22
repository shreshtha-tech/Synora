"use client";

import { useEffect, useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import { renderText } from "@/lib/renderText";
import type { ChatMessage } from "@/components/doc/types";

export default function PreviousTab({ documentId, token }: { documentId: string; token: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    apiRequest<ChatMessage[]>(`/api/v1/qna/history/${documentId}`, token, { signal: controller.signal })
      .then(data => { setMessages(data); setError(""); })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [documentId, token, refresh]);
  return <div className="space-y-5">
    <h2 className="text-2xl font-bold text-gray-800">Your previous questions</h2>
    <p className="text-sm text-gray-500">Questions and answers from your AI Q&amp;A for this document.</p>
    {loading && <p role="status">Loading your questions...</p>}
    {error && <div role="alert"><p>{error}</p><button className="neo-btn px-4 py-2 mt-2" onClick={() => { setLoading(true); setRefresh(value => value + 1); }}>Retry</button></div>}
    {!loading && !error && messages.length === 0 && <p className="text-gray-500">You have not asked a question yet. Use AI Q&amp;A to start.</p>}
    {messages.map((message, index) => <div key={message.id || index} className="neo-shadow p-5 rounded-2xl"><h3 className="font-bold text-primary mb-2">{message.role === "user" ? "Your question" : "Answer"}</h3><div className="text-gray-700 whitespace-pre-wrap">{renderText(message.content)}</div></div>)}
  </div>;
}
