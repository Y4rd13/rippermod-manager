export interface SSEEvent {
  event: string;
  data: string;
}

export async function* parseSSE(
  response: Response,
): AsyncGenerator<SSEEvent, void, undefined> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      let currentEvent = "message";
      let currentData = "";

      for (const line of lines) {
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          currentData = line.slice(5).trim();
        } else if (line === "") {
          if (currentData) {
            yield { event: currentEvent, data: currentData };
          }
          currentEvent = "message";
          currentData = "";
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
