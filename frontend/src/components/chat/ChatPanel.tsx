import {
  Bot,
  Brain,
  Check,
  CircleUser,
  Download,
  FileText,
  Gamepad2,
  Globe,
  MessageSquare,
  RefreshCw,
  Search,
  ChevronsLeft,
  ChevronsRight,
  Send,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { type LucideIcon } from "lucide-react";
import { memo, useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useShallow } from "zustand/react/shallow";

import { Button } from "@/components/ui/Button";
import { useHasOpenaiKey } from "@/hooks/queries";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse-parser";
import { cn } from "@/lib/utils";
import {
  type ChatMsg,
  type ReasoningEffort,
  type ToolCallInfo,
  useChatStore,
} from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";

const remarkPlugins = [remarkGfm];

const markdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-2 last:mb-0">{children}</p>
  ),
  code: ({ children, className }: { children?: React.ReactNode; className?: string }) =>
    className ? (
      <code className="block bg-surface-3 rounded p-2 text-xs font-mono overflow-x-auto my-2">
        {children}
      </code>
    ) : (
      <code className="bg-surface-3 rounded px-1 py-0.5 text-xs font-mono">
        {children}
      </code>
    ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>
  ),
  li: ({ children }: { children?: React.ReactNode }) => <li>{children}</li>,
};

const EFFORT_CYCLE: ReasoningEffort[] = ["none", "minimal", "low", "medium", "high"];
const EFFORT_LABELS: Record<ReasoningEffort, string> = {
  none: "Off",
  minimal: "Min",
  low: "Low",
  medium: "Med",
  high: "High",
};

interface ToolConfig {
  icon: LucideIcon;
  color: string;
  label: string;
  spin: boolean;
}

const TOOL_CONFIG: Record<string, ToolConfig> = {
  search_local_mods: { icon: Search, color: "text-accent", label: "Searching local mods", spin: true },
  get_mod_details: { icon: FileText, color: "text-text-secondary", label: "Getting mod details", spin: false },
  get_nexus_mod_info: { icon: Globe, color: "text-accent-hover", label: "Fetching Nexus info", spin: false },
  list_all_games: { icon: Gamepad2, color: "text-success", label: "Listing games", spin: false },
  list_nexus_downloads: { icon: Download, color: "text-warning", label: "Listing downloads", spin: false },
  semantic_mod_search: { icon: Sparkles, color: "text-accent", label: "Semantic search", spin: true },
  reindex_vector_store: { icon: RefreshCw, color: "text-danger", label: "Rebuilding index", spin: true },
};

const DEFAULT_TOOL_CONFIG: ToolConfig = {
  icon: Search,
  color: "text-text-secondary",
  label: "Running tool",
  spin: false,
};

interface GroupedToolCall {
  name: string;
  count: number;
  running: number;
  done: number;
}

function groupToolCalls(calls: ToolCallInfo[]): GroupedToolCall[] {
  const map = new Map<string, GroupedToolCall>();
  for (const tc of calls) {
    const existing = map.get(tc.name);
    if (existing) {
      existing.count++;
      if (tc.status === "running") existing.running++;
      else existing.done++;
    } else {
      map.set(tc.name, {
        name: tc.name,
        count: 1,
        running: tc.status === "running" ? 1 : 0,
        done: tc.status === "done" ? 1 : 0,
      });
    }
  }
  return Array.from(map.values());
}

function ToolCallCard({ group }: { group: GroupedToolCall }) {
  const config = TOOL_CONFIG[group.name] ?? DEFAULT_TOOL_CONFIG;
  const Icon = config.icon;
  const isRunning = group.running > 0;

  return (
    <div className="flex items-center gap-2 rounded-md border border-border/50 bg-surface-3/50 px-2.5 py-1.5 text-xs animate-fade-in">
      <Icon
        size={14}
        className={cn(
          config.color,
          isRunning && (config.spin ? "animate-spin" : "animate-pulse"),
        )}
      />
      <span className="flex-1 text-text-secondary">{config.label}</span>
      {group.count > 1 && (
        <span className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
          {isRunning ? `${group.done}/${group.count}` : `×${group.count}`}
        </span>
      )}
      {isRunning ? (
        <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
      ) : (
        <Check size={14} className="text-success animate-fade-in" />
      )}
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex gap-3 py-3 flex-row">
      <div className="relative flex h-7 w-7 items-center justify-center rounded-full shrink-0 bg-accent/10 text-accent">
        <Bot size={16} />
        <span className="absolute inset-0 rounded-full border-2 border-accent/40 animate-pulse-ring" />
      </div>
      <div className="rounded-xl px-4 py-2.5 bg-surface-2">
        <div className="flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 16 16" className="animate-orbit-spin">
            <path
              d="M 8 2 A 6 6 0 0 1 14 8"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              className="text-accent"
            />
          </svg>
          <span className="text-xs text-text-muted">Thinking...</span>
        </div>
      </div>
    </div>
  );
}

const ChatMessage = memo(function ChatMessage({ msg }: { msg: ChatMsg }) {
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
          "flex h-7 w-7 items-center justify-center rounded-full shrink-0",
          isUser
            ? "bg-accent text-white"
            : "bg-accent/10 text-accent",
        )}
      >
        {isUser ? <CircleUser size={16} /> : <Bot size={16} />}
      </div>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-2.5 text-sm",
          isUser
            ? "bg-accent/10 text-text-primary"
            : "bg-surface-2 text-text-primary",
        )}
      >
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="flex flex-col gap-1.5 mb-2">
            {groupToolCalls(msg.toolCalls).map((group) => (
              <ToolCallCard key={group.name} group={group} />
            ))}
          </div>
        )}
        {msg.role === "tool" ? (
          <pre className="text-xs text-text-muted whitespace-pre-wrap font-mono">
            {msg.content}
          </pre>
        ) : (
          msg.content && (
            <ReactMarkdown
              remarkPlugins={remarkPlugins}
              components={markdownComponents}
            >
              {msg.content}
            </ReactMarkdown>
          )
        )}
      </div>
    </div>
  );
});

export function ChatPanel() {
  const { chatPanelOpen, setChatPanelOpen } = useUIStore(
    useShallow((s) => ({ chatPanelOpen: s.chatPanelOpen, setChatPanelOpen: s.setChatPanelOpen })),
  );
  const { messages, isStreaming, isThinking, reasoningEffort, suggestedActions } = useChatStore(
    useShallow((s) => ({
      messages: s.messages,
      isStreaming: s.isStreaming,
      isThinking: s.isThinking,
      reasoningEffort: s.reasoningEffort,
      suggestedActions: s.suggestedActions,
    })),
  );
  const addMessage = useChatStore((s) => s.addMessage);
  const appendToLast = useChatStore((s) => s.appendToLast);
  const addToolCall = useChatStore((s) => s.addToolCall);
  const resolveToolCall = useChatStore((s) => s.resolveToolCall);
  const setStreaming = useChatStore((s) => s.setStreaming);
  const setThinking = useChatStore((s) => s.setThinking);
  const setReasoningEffort = useChatStore((s) => s.setReasoningEffort);
  const setSuggestedActions = useChatStore((s) => s.setSuggestedActions);
  const clearMessages = useChatStore((s) => s.clearMessages);

  const hasOpenaiKey = useHasOpenaiKey();

  const [input, setInput] = useState("");
  const [panelWidth, setPanelWidth] = useState(384);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isResizing = useRef(false);
  const widthBeforeCollapse = useRef(384);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    const startX = e.clientX;
    const startW = panelWidth;

    const onMouseMove = (ev: MouseEvent) => {
      const delta = startX - ev.clientX;
      const clamped = Math.min(Math.max(startW + delta, 320), 800);
      setPanelWidth(clamped);
    };

    const onMouseUp = () => {
      isResizing.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, [panelWidth]);

  const toggleCollapse = useCallback(() => {
    setIsCollapsed((prev) => {
      if (!prev) widthBeforeCollapse.current = panelWidth;
      else setPanelWidth(widthBeforeCollapse.current);
      return !prev;
    });
  }, [panelWidth]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const handleSend = useCallback(async (text?: string) => {
    const msg = text ?? input.trim();
    if (!msg || useChatStore.getState().isStreaming) return;

    const currentEffort = useChatStore.getState().reasoningEffort;

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

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await api.stream(
        "/api/v1/chat/",
        { message: msg, reasoning_effort: currentEffort },
        controller.signal,
      );

      for await (const event of parseSSE(response)) {
        try {
          const data = JSON.parse(event.data);
          switch (event.event) {
            case "token":
              appendToLast(data.content ?? "");
              break;
            case "thinking_start":
              setThinking(true);
              break;
            case "thinking_end":
              setThinking(false);
              break;
            case "tool_call":
              addToolCall(data.name);
              break;
            case "tool_result":
              resolveToolCall(data.name);
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
      if (e instanceof DOMException && e.name === "AbortError") return;
      appendToLast(
        `\n\nError: ${e instanceof Error ? e.message : "Connection failed"}`,
      );
    } finally {
      abortRef.current = null;
      setStreaming(false);
      setThinking(false);
    }
  }, [input, addMessage, appendToLast, addToolCall, resolveToolCall, setStreaming, setThinking, setSuggestedActions]);

  if (!chatPanelOpen || !hasOpenaiKey) return null;

  if (isCollapsed) {
    return (
      <div className="fixed right-0 top-9 bottom-0 w-10 flex flex-col items-center border-l border-border bg-surface-1 z-40 shadow-xl py-3 gap-2">
        <button
          onClick={toggleCollapse}
          aria-label="Expand chat"
          className="rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
        >
          <ChevronsLeft size={16} />
        </button>
        <MessageSquare size={16} className="text-accent" />
      </div>
    );
  }

  return (
    <div
      className="fixed right-0 top-9 bottom-0 flex flex-col border-l border-border bg-surface-1 z-40 shadow-xl transition-[width] duration-150"
      style={{ width: `min(100vw, ${panelWidth}px)` }}
    >
      {/* Drag resize handle */}
      <div
        onMouseDown={handleResizeStart}
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-accent/30 active:bg-accent/50 transition-colors z-10"
      />

      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-accent" />
          <span className="text-sm font-semibold text-text-primary">
            Chat Assistant
          </span>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              onClick={clearMessages}
              disabled={isStreaming}
              aria-label="Clear messages"
              className="rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors disabled:opacity-50"
            >
              <Trash2 size={16} />
            </button>
          )}
          <button
            onClick={toggleCollapse}
            aria-label="Collapse chat"
            className="rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
          >
            <ChevronsRight size={16} />
          </button>
          <button
            onClick={() => setChatPanelOpen(false)}
            aria-label="Close chat"
            className="rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </div>
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
        {isThinking && <ThinkingIndicator />}
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
          <div
            className={cn(
              "flex items-center gap-1 rounded-lg border px-2 py-1.5 text-xs font-medium transition-colors",
              reasoningEffort !== "none"
                ? "border-accent bg-accent/10 text-accent"
                : "border-border bg-surface-2 text-text-muted",
            )}
          >
            <Brain size={14} />
            <select
              value={reasoningEffort}
              onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
              className="bg-transparent text-inherit text-xs focus:outline-none cursor-pointer"
            >
              {EFFORT_CYCLE.map((e) => (
                <option key={e} value={e}>{EFFORT_LABELS[e]}</option>
              ))}
            </select>
          </div>
          {isStreaming ? (
            <Button
              type="button"
              size="sm"
              variant="danger"
              onClick={handleStop}
              aria-label="Stop generation"
            >
              <Square size={14} />
            </Button>
          ) : (
            <Button
              type="submit"
              size="sm"
              disabled={!input.trim()}
              aria-label="Send message"
            >
              <Send size={14} />
            </Button>
          )}
        </form>
      </div>
    </div>
  );
}
