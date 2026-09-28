/** 画布 API 错误代码（对应 canvas.json 中 errors.* 的 key） */
export const CANVAS_ERROR = {
    MISSING_CHANNEL: 'missingChannel',
    PROMPT_REQUIRED: 'promptRequired',
    NO_IMAGE_RETURNED: 'noImageReturned',
    NO_TEXT_RETURNED: 'noTextReturned',
    NO_AUDIO_RETURNED: 'noAudioReturned',
    NO_TASK_ID_RETURNED: 'noTaskIdReturned',
    VIDEO_TIMEOUT: 'videoTimeout',
    VIDEO_FAILED: 'videoFailed',
    VIDEO_NO_CONTENT: 'videoNoContent',
    API_KEY_INVALID: 'apiKeyInvalid',
    NETWORK_ERROR: 'networkError',
    HTTP_ERROR: 'httpError',
    REQUEST_FAILED: 'requestFailed',
    READ_RESULT_FAILED: 'readResultFailed',
    REFERENCE_IMAGE_FAILED: 'referenceImageFailed',
    SCRIPT_NO_TEXT: 'scriptNoText',
    SCRIPT_NO_RESULT: 'scriptNoResult',
    SCRIPT_EXEC_FAILED: 'scriptExecFailed',
    POLL_TIMEOUT: 'pollTimeout',
} as const;

export type CanvasErrorCode = (typeof CANVAS_ERROR)[keyof typeof CANVAS_ERROR];

/** 携带错误代码的 API 错误，供组件层用 t() 映射显示 */
export class CanvasApiError extends Error {
    readonly code: CanvasErrorCode;
    readonly params?: Record<string, unknown>;

    constructor(code: CanvasErrorCode, params?: Record<string, unknown>) {
        super(code);
        this.name = 'CanvasApiError';
        this.code = code;
        this.params = params;
    }
}

/** 类型守卫 */
export function isCanvasApiError(error: unknown): error is CanvasApiError {
    return error instanceof CanvasApiError;
}

/** 将未知错误解析为可显示的结构 */
export function resolveErrorDisplay(error: unknown): { code: CanvasErrorCode; params?: Record<string, unknown> } | { message: string } {
    if (isCanvasApiError(error)) {
        return { code: error.code, params: error.params };
    }
    if (error instanceof Error) {
        return { message: error.message };
    }
    return { message: String(error) };
}
