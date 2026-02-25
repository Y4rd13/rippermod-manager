import { create } from "zustand";

export type ReasoningEffort = "none" | "minimal" | "low" | "medium" | "high";

export interface ToolCallInfo {
  name: string;
  status: "running" | "done";
}

export interface ChatMsg {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolCalls?: ToolCallInfo[];
  timestamp: number;
}

interface ChatState {
  messages: ChatMsg[];
  isStreaming: boolean;
  isThinking: boolean;
  reasoningEffort: ReasoningEffort;
  suggestedActions: string[];
  abortController: AbortController | null;
  addMessage: (msg: ChatMsg) => void;
  appendToLast: (content: string) => void;
  setStreaming: (streaming: boolean) => void;
  setThinking: (thinking: boolean) => void;
  setReasoningEffort: (effort: ReasoningEffort) => void;
  setSuggestedActions: (actions: string[]) => void;
  addToolCall: (name: string) => void;
  resolveToolCall: (name: string) => void;
  setAbortController: (ctrl: AbortController | null) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isStreaming: false,
  isThinking: false,
  reasoningEffort: "none",
  suggestedActions: [],
  abortController: null,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendToLast: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content: last.content + content };
      }
      return { messages: msgs };
    }),
  addToolCall: (name) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        const existing = last.toolCalls ?? [];
        msgs[msgs.length - 1] = {
          ...last,
          toolCalls: [...existing, { name, status: "running" }],
        };
      }
      return { messages: msgs };
    }),
  resolveToolCall: (name) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant" && last.toolCalls) {
        const calls = last.toolCalls.map((tc) =>
          tc.name === name && tc.status === "running"
            ? { ...tc, status: "done" as const }
            : tc,
        );
        msgs[msgs.length - 1] = { ...last, toolCalls: calls };
      }
      return { messages: msgs };
    }),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  setThinking: (thinking) => set({ isThinking: thinking }),
  setReasoningEffort: (effort) => set({ reasoningEffort: effort }),
  setSuggestedActions: (actions) => set({ suggestedActions: actions }),
  setAbortController: (ctrl) => set({ abortController: ctrl }),
  clearMessages: () => set({ messages: [], suggestedActions: [] }),
}));
