"""OpenAI Chat Completions / Responses 与 Anthropic Messages 的双向协议转换。

平台允许 Claude 模型同时通过三个公开端点调用：``/v1/messages`` 保持 Anthropic 原生请求与响应，
``/v1/chat/completions`` 与 ``/v1/responses`` 则复用 OpenAI 协议形状。本模块把后两者的请求翻译为
Anthropic Messages 上游请求，并把 Anthropic 的同步响应与 SSE 事件翻译回 OpenAI 形状，使路由与
应用层无需感知上游协议差异。

翻译保留计费所需的用量明细：OpenAI 用量统一把 Anthropic 的缓存读取、缓存写入并入总输入，并写入
``prompt_tokens_details`` / ``input_tokens_details``，使后付费统计口径与原生调用一致。
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

DEFAULT_MAX_TOKENS = 4096
"""OpenAI 请求未给出输出上限时使用的默认 ``max_tokens``；Anthropic 要求该字段必填。"""

_STOP_REASON_TO_FINISH = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}
_FINISH_TO_RESPONSES_STATUS = {"length": "incomplete"}

_DONE_CHUNK = b"data: [DONE]\n\n"


def _dump(obj: dict[str, Any]) -> bytes:
    return ("data: " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode("utf-8")


def _dump_event(event_type: str, obj: dict[str, Any]) -> bytes:
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {payload}\n\n".encode()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _content_text(content: Any) -> str:
    """把 OpenAI 字符串或内容块列表折叠为纯文本。"""

    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(part, str):
            parts.append(part)
    return "".join(parts)


def _image_block(value: Any) -> dict[str, Any] | None:
    """把 OpenAI ``image_url`` 值转换为 Anthropic 图片内容块。"""

    url = value.get("url") if isinstance(value, dict) else value
    if not isinstance(url, str) or not url:
        return None
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        meta = header[len("data:") :]
        media_type = meta.split(";", 1)[0] or "image/png"
        if ";base64" not in meta or not data:
            return None
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def _chat_content_blocks(content: Any) -> list[dict[str, Any]]:
    """把 OpenAI 消息内容转换为 Anthropic 内容块列表。"""

    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    blocks: list[dict[str, Any]] = []
    for part in _as_list(content):
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text" and isinstance(part.get("text"), str):
            blocks.append({"type": "text", "text": part["text"]})
        elif part_type == "image_url":
            block = _image_block(part.get("image_url"))
            if block is not None:
                blocks.append(block)
    return blocks


def _tool_use_blocks(tool_calls: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for call in _as_list(tool_calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                parsed = {}
        else:
            parsed = arguments
        blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id"),
                "name": function.get("name"),
                "input": parsed if isinstance(parsed, dict) else {},
            }
        )
    return blocks


def _tool_result_block(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": message.get("tool_call_id"),
        "content": _content_text(message.get("content")),
    }


def _append_message(messages: list[dict[str, Any]], role: str, blocks: list[dict[str, Any]]) -> None:
    """追加一条 Anthropic 消息；相同角色连续出现时合并，避免上游拒绝角色未交替。"""

    if not blocks:
        return
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"].extend(blocks)
        return
    messages.append({"role": role, "content": blocks})


def _max_tokens(body: dict[str, Any], *fields: str) -> int:
    for field in fields:
        value = body.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return DEFAULT_MAX_TOKENS


def _stop_sequences(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _chat_tools(tools: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tool in _as_list(tools):
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else None
        if not function or not isinstance(function.get("name"), str):
            continue
        result.append(
            {
                "name": function["name"],
                "description": function.get("description"),
                "input_schema": function.get("parameters") or {"type": "object"},
            }
        )
    return result


def _responses_tools(tools: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tool in _as_list(tools):
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        if not isinstance(tool.get("name"), str):
            continue
        result.append(
            {
                "name": tool["name"],
                "description": tool.get("description"),
                "input_schema": tool.get("parameters") or {"type": "object"},
            }
        )
    return result


def _chat_tool_choice(choice: Any) -> dict[str, Any] | None:
    if choice == "auto":
        return {"type": "auto"}
    if choice == "required":
        return {"type": "any"}
    if choice == "none":
        return {"type": "none"}
    if isinstance(choice, dict) and choice.get("type") == "function":
        function = choice.get("function") if isinstance(choice.get("function"), dict) else {}
        name = function.get("name")
        if isinstance(name, str) and name:
            return {"type": "tool", "name": name}
    return None


def _responses_tool_choice(choice: Any) -> dict[str, Any] | None:
    if choice == "auto":
        return {"type": "auto"}
    if choice == "required":
        return {"type": "any"}
    if choice == "none":
        return {"type": "none"}
    if isinstance(choice, dict) and choice.get("type") == "function":
        name = choice.get("name")
        if isinstance(name, str) and name:
            return {"type": "tool", "name": name}
    return None


def _copy_reasoning_params(body: dict[str, Any], result: dict[str, Any]) -> None:
    """透传两家共有的采样参数，忽略仅 OpenAI 使用的字段。"""

    for field in ("temperature", "top_p"):
        value = body.get(field)
        if isinstance(value, int | float) and not isinstance(value, bool):
            result[field] = value


def chat_request_to_messages(body: dict[str, Any]) -> dict[str, Any]:
    """把 OpenAI Chat Completions 请求翻译为 Anthropic Messages 请求。"""

    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []
    for message in _as_list(body.get("messages")):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role in {"system", "developer"}:
            text = _content_text(message.get("content"))
            if text:
                system_parts.append(text)
            continue
        if role == "tool":
            _append_message(messages, "user", [_tool_result_block(message)])
            continue
        blocks = _chat_content_blocks(message.get("content"))
        if role == "assistant":
            blocks.extend(_tool_use_blocks(message.get("tool_calls")))
            _append_message(messages, "assistant", blocks)
        else:
            _append_message(messages, "user", blocks)
    result: dict[str, Any] = {
        "model": body.get("model"),
        "messages": messages,
        "max_tokens": _max_tokens(body, "max_tokens", "max_completion_tokens"),
    }
    if system_parts:
        result["system"] = "\n\n".join(system_parts)
    _copy_reasoning_params(body, result)
    stop = _stop_sequences(body.get("stop"))
    if stop:
        result["stop_sequences"] = stop
    tools = _chat_tools(body.get("tools"))
    if tools:
        result["tools"] = tools
        tool_choice = _chat_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            result["tool_choice"] = tool_choice
    if body.get("stream") is True:
        result["stream"] = True
    return result


def _responses_message_items(items: Any) -> list[dict[str, Any]]:
    """把 Responses ``input`` 归一为可迭代的消息项列表。"""

    if isinstance(items, str):
        return [{"type": "message", "role": "user", "content": items}]
    return [item for item in _as_list(items) if isinstance(item, dict)]


def _responses_content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    blocks: list[dict[str, Any]] = []
    for part in _as_list(content):
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"} and isinstance(part.get("text"), str):
            blocks.append({"type": "text", "text": part["text"]})
        elif part_type == "input_image":
            block = _image_block(part.get("image_url"))
            if block is not None:
                blocks.append(block)
    return blocks


def responses_request_to_messages(body: dict[str, Any]) -> dict[str, Any]:
    """把 OpenAI Responses 请求翻译为 Anthropic Messages 请求。"""

    messages: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for item in _responses_message_items(body.get("input")):
        item_type = item.get("type")
        if item_type == "function_call":
            arguments = item.get("arguments")
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError:
                    parsed = {}
            else:
                parsed = arguments
            _append_message(
                messages,
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": item.get("call_id") or item.get("id"),
                        "name": item.get("name"),
                        "input": parsed if isinstance(parsed, dict) else {},
                    }
                ],
            )
            continue
        if item_type == "function_call_output":
            output = item.get("output")
            _append_message(
                messages,
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": item.get("call_id"),
                        "content": output if isinstance(output, str) else _content_text(output),
                    }
                ],
            )
            continue
        role = item.get("role")
        blocks = _responses_content_blocks(item.get("content"))
        if role == "system":
            text = _content_text(item.get("content"))
            if text:
                system_parts.append(text)
        elif role == "assistant":
            _append_message(messages, "assistant", blocks)
        else:
            _append_message(messages, "user", blocks)
    result: dict[str, Any] = {
        "model": body.get("model"),
        "messages": messages,
        "max_tokens": _max_tokens(body, "max_output_tokens", "max_tokens"),
    }
    instructions = _content_text(body.get("instructions"))
    if instructions:
        system_parts.insert(0, instructions)
    if system_parts:
        result["system"] = "\n\n".join(system_parts)
    _copy_reasoning_params(body, result)
    tools = _responses_tools(body.get("tools"))
    if tools:
        result["tools"] = tools
        tool_choice = _responses_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            result["tool_choice"] = tool_choice
    if body.get("stream") is True:
        result["stream"] = True
    return result


def _openai_usage(usage: Any) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    if input_tokens is None and output_tokens is None:
        return None
    cache_read = _int(usage.get("cache_read_input_tokens")) or 0
    cache_write = _int(usage.get("cache_creation_input_tokens")) or 0
    prompt_tokens = (input_tokens or 0) + cache_read + cache_write
    completion_tokens = output_tokens or 0
    result: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    details: dict[str, int] = {}
    if cache_read:
        details["cached_tokens"] = cache_read
    if cache_write:
        details["cache_write_tokens"] = cache_write
    if details:
        result["prompt_tokens_details"] = details
    return result


def _responses_usage(usage: Any) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    if input_tokens is None and output_tokens is None:
        return None
    cache_read = _int(usage.get("cache_read_input_tokens")) or 0
    cache_write = _int(usage.get("cache_creation_input_tokens")) or 0
    total_input = (input_tokens or 0) + cache_read + cache_write
    completion = output_tokens or 0
    result: dict[str, Any] = {
        "input_tokens": total_input,
        "output_tokens": completion,
        "total_tokens": total_input + completion,
    }
    details: dict[str, int] = {}
    if cache_read:
        details["cached_tokens"] = cache_read
    if cache_write:
        details["cache_write_tokens"] = cache_write
    if details:
        result["input_tokens_details"] = details
    return result


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _text_blocks(payload: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for block in _as_list(payload.get("content")):
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
    return texts


def _tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for block in _as_list(payload.get("content")):
        if isinstance(block, dict) and block.get("type") == "tool_use":
            calls.append(
                {
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    },
                }
            )
    return calls


def _finish_reason(payload: dict[str, Any]) -> str:
    stop_reason = payload.get("stop_reason")
    if isinstance(stop_reason, str):
        return _STOP_REASON_TO_FINISH.get(stop_reason, "stop")
    return "stop"


def messages_response_to_chat(payload: dict[str, Any]) -> dict[str, Any]:
    """把 Anthropic Messages 响应翻译为 OpenAI Chat Completion 响应。"""

    text = "".join(_text_blocks(payload))
    tool_calls = _tool_calls(payload)
    message: dict[str, Any] = {"role": "assistant", "content": text if text else None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    result: dict[str, Any] = {
        "id": _chat_id(payload),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model"),
        "choices": [{"index": 0, "message": message, "finish_reason": _finish_reason(payload)}],
    }
    usage = _openai_usage(payload.get("usage"))
    if usage is not None:
        result["usage"] = usage
    return result


def messages_response_to_responses(payload: dict[str, Any]) -> dict[str, Any]:
    """把 Anthropic Messages 响应翻译为 OpenAI Responses 响应。"""

    output = _responses_output(payload)
    status = _FINISH_TO_RESPONSES_STATUS.get(_finish_reason(payload), "completed")
    result: dict[str, Any] = {
        "id": _response_id(payload),
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "model": payload.get("model"),
        "output": output,
    }
    usage = _responses_usage(payload.get("usage"))
    if usage is not None:
        result["usage"] = usage
    return result


def _responses_output(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    texts = _text_blocks(payload)
    if texts:
        output.append(
            {
                "type": "message",
                "id": f"msg_{uuid4().hex}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "".join(texts), "annotations": []}],
            }
        )
    for block in _as_list(payload.get("content")):
        if isinstance(block, dict) and block.get("type") == "tool_use":
            output.append(
                {
                    "type": "function_call",
                    "id": f"fc_{uuid4().hex}",
                    "call_id": block.get("id"),
                    "name": block.get("name"),
                    "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    "status": "completed",
                }
            )
    return output


def _chat_id(payload: dict[str, Any]) -> str:
    identifier = payload.get("id")
    return identifier if isinstance(identifier, str) and identifier else f"chatcmpl-{uuid4().hex}"


def _response_id(payload: dict[str, Any]) -> str:
    identifier = payload.get("id")
    if isinstance(identifier, str) and identifier:
        return identifier if identifier.startswith("resp_") else f"resp_{identifier}"
    return f"resp_{uuid4().hex}"


def _parse_data_line(line: str) -> dict[str, Any] | None:
    """解析一条 SSE ``data:`` 行为 JSON 对象，非数据行、空数据或非法 JSON 返回空。"""

    text = line.strip()
    if not text.startswith("data:"):
        return None
    data = text[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


class ChatStreamTranslator:
    """把 Anthropic Messages SSE 事件逐行翻译为 OpenAI Chat Completion chunk。"""

    def __init__(self) -> None:
        self._id = f"chatcmpl-{uuid4().hex}"
        self._created = int(time.time())
        self._model: str | None = None
        self._tool_index = -1
        self._block_tools: dict[Any, int] = {}
        self._finish_reason: str | None = None
        self._usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        self._done = False

    def feed_line(self, line: str) -> list[bytes]:
        event = _parse_data_line(line)
        if event is None:
            return []
        return self._handle(event)

    def finish(self) -> list[bytes]:
        if self._done:
            return []
        self._done = True
        chunks = [self._chunk({}, finish_reason=self._finish_reason or "stop")]
        usage = _openai_usage(self._usage)
        if usage is not None:
            chunks.append(self._chunk(None, usage=usage))
        chunks.append(_DONE_CHUNK)
        return chunks

    def _handle(self, event: dict[str, Any]) -> list[bytes]:
        event_type = event.get("type")
        if event_type == "message_start":
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            self._model = message.get("model") or self._model
            self._id = message.get("id") or self._id
            self._record(message.get("usage"))
            return [self._chunk({"role": "assistant", "content": ""})]
        if event_type == "content_block_start":
            block = event.get("content_block") if isinstance(event.get("content_block"), dict) else {}
            if block.get("type") == "tool_use":
                self._tool_index += 1
                self._block_tools[event.get("index")] = self._tool_index
                return [
                    self._chunk(
                        {
                            "tool_calls": [
                                {
                                    "index": self._tool_index,
                                    "id": block.get("id"),
                                    "type": "function",
                                    "function": {"name": block.get("name"), "arguments": ""},
                                }
                            ]
                        }
                    )
                ]
            return []
        if event_type == "content_block_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            if delta.get("type") == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    return [self._chunk({"content": text})]
            elif delta.get("type") == "input_json_delta":
                tool_index = self._block_tools.get(event.get("index"))
                if tool_index is not None:
                    return [
                        self._chunk(
                            {
                                "tool_calls": [
                                    {"index": tool_index, "function": {"arguments": delta.get("partial_json", "")}}
                                ]
                            }
                        )
                    ]
            return []
        if event_type == "message_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            stop_reason = delta.get("stop_reason")
            if isinstance(stop_reason, str):
                self._finish_reason = _STOP_REASON_TO_FINISH.get(stop_reason, "stop")
            self._record(event.get("usage"))
            return []
        if event_type == "message_stop":
            return self.finish()
        return []

    def _record(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        for field in self._usage:
            value = _int(usage.get(field))
            if value is not None:
                self._usage[field] = value

    def _chunk(
        self, delta: dict[str, Any] | None, *, finish_reason: str | None = None, usage: dict[str, Any] | None = None
    ) -> bytes:
        payload: dict[str, Any] = {
            "id": self._id,
            "object": "chat.completion.chunk",
            "created": self._created,
            "model": self._model,
            "choices": [],
        }
        if delta is not None:
            payload["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
        if usage is not None:
            payload["usage"] = usage
        return _dump(payload)


class ResponsesStreamTranslator:
    """把 Anthropic Messages SSE 事件逐行翻译为 OpenAI Responses 事件。"""

    def __init__(self) -> None:
        self._response_id = f"resp_{uuid4().hex}"
        self._created = int(time.time())
        self._model: str | None = None
        self._output_index = -1
        self._blocks: dict[Any, dict[str, Any]] = {}
        self._output: list[dict[str, Any]] = []
        self._finish_reason: str | None = None
        self._usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        self._done = False

    def feed_line(self, line: str) -> list[bytes]:
        event = _parse_data_line(line)
        if event is None:
            return []
        return self._handle(event)

    def finish(self) -> list[bytes]:
        if self._done:
            return []
        self._done = True
        return [
            self._event("response.completed", {"type": "response.completed", "response": self._response("completed")}),
            _DONE_CHUNK,
        ]

    def _handle(self, event: dict[str, Any]) -> list[bytes]:
        event_type = event.get("type")
        if event_type == "message_start":
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            self._model = message.get("model") or self._model
            self._response_id = _response_id(message) if message.get("id") else self._response_id
            self._record(message.get("usage"))
            return [
                self._event(
                    "response.created", {"type": "response.created", "response": self._response("in_progress")}
                ),
                self._event(
                    "response.in_progress", {"type": "response.in_progress", "response": self._response("in_progress")}
                ),
            ]
        if event_type == "content_block_start":
            return self._start_block(event)
        if event_type == "content_block_delta":
            return self._delta_block(event)
        if event_type == "content_block_stop":
            return self._stop_block(event)
        if event_type == "message_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            stop_reason = delta.get("stop_reason")
            if isinstance(stop_reason, str):
                self._finish_reason = _STOP_REASON_TO_FINISH.get(stop_reason, "stop")
            self._record(event.get("usage"))
            return []
        if event_type == "message_stop":
            return self.finish()
        return []

    def _start_block(self, event: dict[str, Any]) -> list[bytes]:
        block = event.get("content_block") if isinstance(event.get("content_block"), dict) else {}
        index = event.get("index")
        self._output_index += 1
        item_id = f"msg_{uuid4().hex}" if block.get("type") != "tool_use" else f"fc_{uuid4().hex}"
        self._blocks[index] = {
            "item_id": item_id,
            "type": block.get("type"),
            "text": "",
            "arguments": "",
            "meta": block,
        }
        if block.get("type") == "tool_use":
            item = {
                "type": "function_call",
                "id": item_id,
                "call_id": block.get("id"),
                "name": block.get("name"),
                "arguments": "",
                "status": "in_progress",
            }
            return [
                self._event(
                    "response.output_item.added",
                    {"type": "response.output_item.added", "output_index": self._output_index, "item": item},
                )
            ]
        item = {"type": "message", "id": item_id, "role": "assistant", "status": "in_progress", "content": []}
        return [
            self._event(
                "response.output_item.added",
                {"type": "response.output_item.added", "output_index": self._output_index, "item": item},
            ),
            self._event(
                "response.content_part.added",
                {
                    "type": "response.content_part.added",
                    "item_id": item_id,
                    "output_index": self._output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                },
            ),
        ]

    def _delta_block(self, event: dict[str, Any]) -> list[bytes]:
        state = self._blocks.get(event.get("index"))
        if state is None:
            return []
        delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
        if delta.get("type") == "text_delta":
            text = delta.get("text")
            if not isinstance(text, str) or not text:
                return []
            state["text"] += text
            return [
                self._event(
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "item_id": state["item_id"],
                        "output_index": self._output_index,
                        "content_index": 0,
                        "delta": text,
                    },
                )
            ]
        if delta.get("type") == "input_json_delta":
            partial = delta.get("partial_json", "")
            state["arguments"] += partial
            return [
                self._event(
                    "response.function_call_arguments.delta",
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": state["item_id"],
                        "output_index": self._output_index,
                        "delta": partial,
                    },
                )
            ]
        return []

    def _stop_block(self, event: dict[str, Any]) -> list[bytes]:
        state = self._blocks.pop(event.get("index"), None)
        if state is None:
            return []
        if state["type"] == "tool_use":
            item = {
                "type": "function_call",
                "id": state["item_id"],
                "call_id": state["meta"].get("id"),
                "name": state["meta"].get("name"),
                "arguments": state["arguments"],
                "status": "completed",
            }
            self._output.append(item)
            return [
                self._event(
                    "response.function_call_arguments.done",
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": state["item_id"],
                        "output_index": self._output_index,
                        "arguments": state["arguments"],
                    },
                ),
                self._event(
                    "response.output_item.done",
                    {"type": "response.output_item.done", "output_index": self._output_index, "item": item},
                ),
            ]
        item = {
            "type": "message",
            "id": state["item_id"],
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": state["text"], "annotations": []}],
        }
        self._output.append(item)
        return [
            self._event(
                "response.output_text.done",
                {
                    "type": "response.output_text.done",
                    "item_id": state["item_id"],
                    "output_index": self._output_index,
                    "content_index": 0,
                    "text": state["text"],
                },
            ),
            self._event(
                "response.content_part.done",
                {
                    "type": "response.content_part.done",
                    "item_id": state["item_id"],
                    "output_index": self._output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": state["text"], "annotations": []},
                },
            ),
            self._event(
                "response.output_item.done",
                {"type": "response.output_item.done", "output_index": self._output_index, "item": item},
            ),
        ]

    def _record(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        for field in self._usage:
            value = _int(usage.get(field))
            if value is not None:
                self._usage[field] = value

    def _response(self, status: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self._response_id,
            "object": "response",
            "created_at": self._created,
            "status": status,
            "model": self._model,
            "output": list(self._output),
        }
        usage = _responses_usage(self._usage)
        if usage is not None:
            result["usage"] = usage
        return result

    def _event(self, event_type: str, payload: dict[str, Any]) -> bytes:
        return _dump_event(event_type, payload)
