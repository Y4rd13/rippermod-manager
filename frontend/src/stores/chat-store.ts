import { create } from "zustand";

export interface ChatMsg {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolCalls?: string;
  timestamp: number;
}

interface ChatState {
  messages: ChatMsg[];
  isStreaming: boolean;
  suggestedActions: string[];
  abortController: AbortController | null;
  addMessage: (msg: ChatMsg) => void;
  appendToLast: (content: string) => void;
  setStreaming: (streaming: boolean) => void;
  setSuggestedActions: (actions: string[]) => void;
  setAbortController: (ctrl: AbortController | null) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isStreaming: false,
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
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  setSuggestedActions: (actions) => set({ suggestedActions: actions }),
  setAbortController: (ctrl) => set({ abortController: ctrl }),
  clearMessages: () => set({ messages: [], suggestedActions: [] }),
}));
