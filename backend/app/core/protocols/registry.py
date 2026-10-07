from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProtocolOperation:
    id: str
    methods: tuple[str, ...]
    path: str


@dataclass(frozen=True, slots=True)
class PublicProtocol:
    id: str
    version: int
    model_field: str
    operations: tuple[ProtocolOperation, ...]

    def operation(self, operation_id: str) -> ProtocolOperation:
        for operation in self.operations:
            if operation.id == operation_id:
                return operation
        raise KeyError(operation_id)

    def content_url(self, video_id: str) -> str:
        return self.operation("content").path.format(video_id=video_id)


OPENAI_VIDEO_PROTOCOL = PublicProtocol(
    id="openai_video",
    version=1,
    model_field="model",
    operations=(
        ProtocolOperation(id="create", methods=("POST",), path="/v1/videos"),
        ProtocolOperation(id="material", methods=("GET",), path="/v1/videos/materials/{resource_id}"),
        ProtocolOperation(id="retrieve", methods=("GET",), path="/v1/videos/{video_id}"),
        ProtocolOperation(id="public", methods=("GET",), path="/v1/videos/public/{task_id}"),
        ProtocolOperation(id="content", methods=("GET",), path="/v1/videos/{video_id}/content"),
    ),
)

OPENAI_IMAGE_PROTOCOL = PublicProtocol(
    id="openai_image",
    version=1,
    model_field="model",
    operations=(
        ProtocolOperation(id="create", methods=("POST",), path="/v1/images/generations"),
        ProtocolOperation(id="edit", methods=("POST",), path="/v1/images/edits"),
    ),
)

OPENAI_TEXT_PROTOCOL = PublicProtocol(
    id="openai_text",
    version=1,
    model_field="model",
    operations=(ProtocolOperation(id="create", methods=("POST",), path="/v1/chat/completions"),),
)

OPENAI_RESPONSE_PROTOCOL = PublicProtocol(
    id="openai_response",
    version=1,
    model_field="model",
    operations=(ProtocolOperation(id="create", methods=("POST",), path="/v1/responses"),),
)

OPENAI_MODELS_PROTOCOL = PublicProtocol(
    id="openai_models",
    version=1,
    model_field="model",
    operations=(ProtocolOperation(id="list", methods=("GET",), path="/v1/models"),),
)

GEMINI_TEXT_PROTOCOL = PublicProtocol(
    id="gemini_text",
    version=1,
    model_field="model",
    operations=(
        ProtocolOperation(id="list", methods=("GET",), path="/v1beta/models"),
        ProtocolOperation(id="generate", methods=("POST",), path="/v1beta/models/{model}:generateContent"),
        ProtocolOperation(id="stream", methods=("POST",), path="/v1beta/models/{model}:streamGenerateContent"),
    ),
)

ANTHROPIC_MESSAGES_PROTOCOL = PublicProtocol(
    id="anthropic_messages",
    version=1,
    model_field="model",
    operations=(ProtocolOperation(id="create", methods=("POST",), path="/v1/messages"),),
)

DASHSCOPE_TEXT_PROTOCOL = PublicProtocol(
    id="dashscope_text",
    version=1,
    model_field="model",
    operations=(
        ProtocolOperation(
            id="create",
            methods=("POST",),
            path="/api/v1/services/aigc/text-generation/generation",
        ),
    ),
)

DASHSCOPE_MULTIMODAL_PROTOCOL = PublicProtocol(
    id="dashscope_multimodal",
    version=1,
    model_field="model",
    operations=(
        ProtocolOperation(
            id="create",
            methods=("POST",),
            path="/api/v1/services/aigc/multimodal-generation/generation",
        ),
    ),
)

ARK_RESPONSES_PROTOCOL = PublicProtocol(
    id="ark_responses",
    version=1,
    model_field="model",
    operations=(ProtocolOperation(id="create", methods=("POST",), path="/api/v3/responses"),),
)

_PROTOCOLS = {
    OPENAI_VIDEO_PROTOCOL.id: OPENAI_VIDEO_PROTOCOL,
    OPENAI_IMAGE_PROTOCOL.id: OPENAI_IMAGE_PROTOCOL,
    OPENAI_TEXT_PROTOCOL.id: OPENAI_TEXT_PROTOCOL,
    OPENAI_RESPONSE_PROTOCOL.id: OPENAI_RESPONSE_PROTOCOL,
    OPENAI_MODELS_PROTOCOL.id: OPENAI_MODELS_PROTOCOL,
    GEMINI_TEXT_PROTOCOL.id: GEMINI_TEXT_PROTOCOL,
    ANTHROPIC_MESSAGES_PROTOCOL.id: ANTHROPIC_MESSAGES_PROTOCOL,
    DASHSCOPE_TEXT_PROTOCOL.id: DASHSCOPE_TEXT_PROTOCOL,
    DASHSCOPE_MULTIMODAL_PROTOCOL.id: DASHSCOPE_MULTIMODAL_PROTOCOL,
    ARK_RESPONSES_PROTOCOL.id: ARK_RESPONSES_PROTOCOL,
}


def get_protocol(protocol_id: str) -> PublicProtocol:
    return _PROTOCOLS[protocol_id]
