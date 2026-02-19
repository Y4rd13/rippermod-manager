import { MessageSquare, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse-parser";
import { cn } from "@/lib/utils";
import { type ChatMsg, useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";

function ChatMessage({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div
      className={cn(
        "flex gap-3 py-3",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      <div
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold shrink-0",
          isUser
            ? "bg-accent text-white"
            : "bg-surface-3 text-text-secondary",
        )}
      >
        {isUser ? "U" : "AI"}
      </div>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-2.5 text-sm",
          isUser
            ? "bg-accent/10 text-text-primary"
            : "bg-surface-2 text-text-primary",
        )}
      >
        {msg.role === "tool" ? (
          <pre className="text-xs text-text-muted whitespace-pre-wrap font-mono">
            {msg.content}
          </pre>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              code: ({ children, className }) =>
                className ? (
                  <code className="block bg-surface-3 rounded p-2 text-xs font-mono overflow-x-auto my-2">
                    {children}
                  </code>
                ) : (
                  <code className="bg-surface-3 rounded px-1 py-0.5 text-xs font-mono">
                    {children}
                  </code>
                ),
              ul: ({ children }) => (
                <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>
              ),
              li: ({ children }) => <li>{children}</li>,
            }}
          >
            {msg.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}

export function ChatPanel() {
  const { chatPanelOpen, setChatPanelOpen } = useUIStore();
  const {
    messages,
    isStreaming,
    suggestedActions,
    addMessage,
    appendToLast,
    setStreaming,
    setSuggestedActions,
  } = useChatStore();

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (text?: string) => {
    const msg = text ?? input.trim();
    if (!msg || isStreaming) return;

    setInput("");
    addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: msg,
      timestamp: Date.now(),
    });

    setStreaming(true);
    setSuggestedActions([]);

    addMessage({
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
    });

    try {
      const response = await api.stream("/api/v1/chat", { message: msg });
      if (!response.ok) {
        appendToLast("Failed to connect to chat service.");
        setStreaming(false);
        return;
      }

      for await (const event of parseSSE(response)) {
        try {
          const data = JSON.parse(event.data);
          switch (event.event) {
            case "token":
              appendToLast(data.content ?? "");
              break;
            case "tool_call":
              appendToLast(`\n\n*Using tool: ${data.name}...*\n\n`);
              break;
            case "tool_result":
              break;
            case "suggested_actions":
              setSuggestedActions(data.actions ?? []);
              break;
            case "done":
              break;
          }
        } catch {
          // skip malformed events
        }
      }
    } catch (e) {
      appendToLast(
        `\n\nError: ${e instanceof Error ? e.message : "Connection failed"}`,
      );
    } finally {
      setStreaming(false);
    }
  };

  if (!chatPanelOpen) return null;

  return (
    <div className="fixed right-0 top-9 bottom-0 w-96 flex flex-col border-l border-border bg-surface-1 z-40 shadow-xl">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-accent" />
          <span className="text-sm font-semibold text-text-primary">
            Chat Assistant
          </span>
        </div>
        <button
          onClick={() => setChatPanelOpen(false)}
          className="rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-2">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <MessageSquare size={32} className="text-text-muted mb-3" />
            <p className="text-sm text-text-muted mb-4">
              Ask about your mods, troubleshoot issues, or check for updates.
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} msg={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {suggestedActions.length > 0 && !isStreaming && (
        <div className="flex flex-wrap gap-2 px-4 py-2 border-t border-border/50">
          {suggestedActions.map((action) => (
            <button
              key={action}
              onClick={() => handleSend(action)}
              className="rounded-full border border-border px-3 py-1 text-xs text-text-secondary hover:bg-surface-2 hover:text-text-primary transition-colors"
            >
              {action}
            </button>
          ))}
        </div>
      )}

      <div className="border-t border-border p-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your mods..."
            className="flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent"
            disabled={isStreaming}
          />
          <Button
            type="submit"
            size="sm"
            disabled={!input.trim() || isStreaming}
          >
            <Send size={14} />
          </Button>
        </form>
      </div>
    </div>
  );
}
