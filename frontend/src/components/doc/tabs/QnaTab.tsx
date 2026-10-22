"use client";

import { useState, useEffect } from "react";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { renderText } from "@/lib/renderText";
import type { Session } from "next-auth";
import type { ChatMessage } from "@/components/doc/types";
import { apiRequest, errorMessage } from "@/lib/api";

interface QnaTabProps {
  documentId: string;
  session: Session | null;
}



export default function QnaTab({ documentId, session }: QnaTabProps) {
  const [question, setQuestion] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const token = session?.backendToken;

  // Fetch existing chat history
  useEffect(() => {
    if (!documentId || !token) return;
    const controller = new AbortController();
    apiRequest<ChatMessage[]>(`/api/v1/qna/history/${documentId}`, token, { signal: controller.signal })
      .then((data) => {
        if (Array.isArray(data)) setChatHistory(data);
      })
      .catch((error) => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [documentId, token]);

  const handleAskQuestion = async () => {
    if (!question.trim() || asking || !token) return;

    const userQuestion = question;
    setError("");
    setAsking(true);

    try {
      const data = await apiRequest<{ answer: string }>("/api/v1/qna/", token, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ documentId, question: userQuestion }),
      });

      setQuestion("");
      setChatHistory((prev) => [...prev, { role: "user", content: userQuestion }, { role: "ai", content: data.answer }]);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setAsking(false);
    }
  };

  const handleClearChat = async () => {
    if (asking) return;
    if (!confirm("Clear chat history?")) return;
    try {
      await apiRequest(`/api/v1/qna/history/${documentId}`, token, {
        method: "DELETE",
      });
      setChatHistory([]);
      setError("");
    } catch (error) {
      setError(errorMessage(error));
    }
  };

  return (
    <div className="animate-in fade-in slide-in-from-right-4 flex flex-col h-full">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-2xl font-bold text-gray-800">Ask AI</h2>
        {chatHistory.length > 0 && (
          <button
            onClick={handleClearChat}
            disabled={asking}
            className="text-xs text-red-500 hover:text-red-600 font-medium px-3 py-1 rounded-lg hover:bg-red-50 transition-colors"
          >
            Clear Chat
          </button>
        )}
      </div>

      {error && <p role="alert" className="mb-4 text-red-600">{error}</p>}
      <div className="flex-1 min-h-0 neo-inset rounded-2xl mb-4 p-4 overflow-y-auto">
        {chatHistory.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <MessageSquare className="w-12 h-12 mb-2 opacity-20" />
            <p>Ask anything about the document...</p>
          </div>
        ) : (
          <div className="space-y-6">
            {chatHistory.map((msg, i) => (
              <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[85%] p-5 rounded-2xl shadow-sm text-sm leading-relaxed",
                    msg.role === "user"
                      ? "bg-[var(--primary)] text-white rounded-br-none"
                      : "bg-white text-gray-800 rounded-bl-none"
                  )}
                >
                  {renderText(msg.content)}
                </div>
              </div>
            ))}
            {asking && (
              <div className="flex justify-start">
                <div className="bg-white p-4 rounded-2xl rounded-bl-none shadow-sm flex items-center gap-1 w-fit">
                  <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAskQuestion()}
          placeholder="Type your question..."
          className="flex-1 neo-inset px-4 py-3 rounded-xl bg-transparent outline-none"
          disabled={asking || !token}
        />
        <button
          onClick={handleAskQuestion}
          disabled={asking || !question.trim() || !token}
          className="neo-btn px-6 py-3 rounded-xl font-bold text-primary disabled:opacity-50"
        >
          {asking ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}
