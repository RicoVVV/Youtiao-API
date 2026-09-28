/**
 * 文本对话 SSE 流式客户端：调用 /v1/chat/completions（stream: true），
 * 逐块解析 Server-Sent Events 并把增量回调给 UI，实现逐字渲染。
 * 经 app/v1/[...path]/route.ts 手动代理转发，响应体不缓冲、逐块透传。
 */

export type StreamDelta = {
  /** 正文增量 */
  content?: string;
  /** 思考过程增量（reasoning_content） */
  reasoning?: string;
  /** 实际出参模型（任一 chunk 返回） */
  model?: string;
  /** 终止原因（最后一个带 finish_reason 的 chunk） */
  finishReason?: string;
  /** token 用量（stream_options.include_usage 时末尾 chunk 返回） */
  usage?: { prompt: number; completion: number; total: number };
};

type ChatCompletionChunk = {
  model?: string;
  choices?: Array<{
    delta?: { content?: string; reasoning_content?: string };
    finish_reason?: string | null;
  }>;
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
};

type StreamOptions = {
  /** 用户长期 API Token（/v1 仅接受 sk-，登录 JWT 会 401） */
  bearerToken: string;
  /** 每个增量回调一次；累计内容交由 UI 维护 */
  onDelta: (delta: StreamDelta) => void;
  signal?: AbortSignal;
};

/**
 * 流式请求文本对话。
 * 返回最终聚合结果（正文/思考/模型/用量），onDelta 期间已逐块回调。
 * 出错（HTTP 非 2xx / 流内 error）抛异常。
 */
export async function streamChatCompletion(
  payload: {
    model: string;
    messages: Array<{ role: "user" | "assistant"; content: string }>;
    /** 推理强度（可选，透传给上游模型） */
    reasoning_effort?: string;
    /** 模型模板声明的其余标量参数（temperature、top_p 等），按契约透传 */
    [key: string]: unknown;
  },
  { bearerToken, onDelta, signal }: StreamOptions
): Promise<Omit<StreamDelta, "content" | "reasoning">> {
  const res = await fetch("/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${bearerToken}`,
    },
    body: JSON.stringify({
      ...payload,
      stream: true,
      stream_options: { include_usage: true },
    }),
    signal,
  });

  if (!res.ok) {
    // 错误体可能是信封或 OpenAI error 结构
    let message = `请求失败（${res.status}）`;
    try {
      const data = (await res.json()) as Record<string, unknown>;
      const err = data.error as Record<string, unknown> | undefined;
      if (typeof data.message === "string") message = data.message;
      else if (typeof err?.message === "string") message = err.message;
    } catch {
      /* 非 JSON 错误体，沿用状态码提示 */
    }
    throw new Error(message);
  }
  if (!res.body) throw new Error("接口未返回流式内容");

  const result: Omit<StreamDelta, "content" | "reasoning"> = {};
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handleData = (json: string) => {
    let chunk: ChatCompletionChunk;
    try {
      chunk = JSON.parse(json) as ChatCompletionChunk;
    } catch {
      return; // 忽略不完整/非 JSON 行
    }
    if (chunk.model) result.model = chunk.model;
    const choice = chunk.choices?.[0];
    const content = choice?.delta?.content;
    const reasoning = choice?.delta?.reasoning_content;
    if (content) onDelta({ content });
    if (reasoning) onDelta({ reasoning });
    if (choice?.finish_reason) {
      result.finishReason = choice.finish_reason;
      onDelta({ finishReason: choice.finish_reason });
    }
    if (chunk.usage) {
      result.usage = {
        prompt: chunk.usage.prompt_tokens,
        completion: chunk.usage.completion_tokens,
        total: chunk.usage.total_tokens,
      };
      onDelta({ usage: result.usage });
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE 事件以空行分隔；同一 read 可能含多个事件，也可能一个事件跨多次 read
    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() ?? "";
    for (const event of events) {
      for (const line of event.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const data = trimmed.slice(5).trim();
        if (data === "[DONE]") continue;
        handleData(data);
      }
    }
  }
  return result;
}
