"""平台响应文案的英文目录。

不变量（由 ``tests/test_i18n.py`` 强制校验）：
``backend/app`` 下所有可静态确定的响应文案——``raise XxxError("中文")``、
``HTTPException(detail="中文")``、``response_body(status, "中文", ...)``——
都必须以原文为 key 收录在 ``MESSAGES_EN`` 中。

因此修改任何一处中文文案时，必须同步修改本文件的 key；
新增中文文案时，必须同步补一条译文，否则测试失败。

``CODE_MESSAGES`` 承载**运行期拼接**的文案：这类文案无法以原文为 key，
改由业务层在 ``raise`` 时携带稳定的 ``code`` 与 ``params``，此处以英文模板渲染。
模板中的占位符名必须与业务层传入的 ``params`` 键完全一致（同样由测试强制）。
中文文案始终取自业务层原文，因此这里不需要中文模板，也就不存在双份模板漂移。
"""

from __future__ import annotations

MESSAGES_EN: dict[str, str] = {
    "SMTP 加密方式必须是 none、starttls 或 ssl": "SMTP security must be none, starttls, or ssl",
    "SMTP 密码密文无法解密": "The stored SMTP password cannot be decrypted",
    "SMTP 端口必须在 1 到 65535 之间": "SMTP port must be between 1 and 65535",
    "开启邮箱验证前必须配置 SMTP 服务器地址": "An SMTP host must be configured before enabling email verification",
    "开启邮箱验证前必须配置 SMTP 用户名": ("An SMTP username must be configured before enabling email verification"),
    "开启邮箱验证前必须配置 SMTP 密码": ("An SMTP password must be configured before enabling email verification"),
    "开启邮箱验证前必须配置有效的发件人邮箱": (
        "A valid sender email must be configured before enabling email verification"
    ),
    "邮件发送失败，请检查 SMTP 配置": "Failed to send email. Please check the SMTP configuration.",
    "验证码服务暂不可用": "The verification code service is temporarily unavailable",
    "验证码已过期或不存在，请重新获取": "The verification code has expired or does not exist. Please request a new one.",
    "验证码错误次数过多，请重新获取": "Too many incorrect verification code attempts. Please request a new one.",
    "验证码错误": "Incorrect verification code",
    "邮箱验证功能未开启": "Email verification is not enabled",
    "该邮箱已被注册": "This email is already registered",
    "邮箱格式不合法": "Invalid email format",
    "已开启邮箱验证，注册时必须提供邮箱和验证码": (
        "Email verification is enabled; an email and verification code are required to register"
    ),
    "Anthropic Messages Provider 不支持 OpenAI Responses API": "Anthropic Messages Provider does not support the OpenAI Responses API",
    "Anthropic Messages Provider 不支持图片生成": "Anthropic Messages Provider does not support image generation",
    "Anthropic Messages Provider 不支持图片编辑": "Anthropic Messages Provider does not support image editing",
    "Anthropic Messages 请求必须提供大于 0 的 max_tokens": (
        "Anthropic Messages requests must provide a max_tokens value greater than 0"
    ),
    "Anthropic Messages 请求必须提供非空 messages 列表": (
        "Anthropic Messages requests must provide a non-empty messages list"
    ),
    "DashScope Provider 不支持 OpenAI Responses API": "DashScope Provider does not support the OpenAI Responses API",
    "DashScope Provider 不支持 OpenAI 图片接口": "DashScope Provider does not support the OpenAI image API",
    "DashScope 端点类型不合法": "Invalid DashScope endpoint type",
    "DashScope 请求必须提供非空 input.messages": "DashScope requests must provide a non-empty input.messages",
    "DashScope 视频请求 aspect_ratio 不合法": "Invalid DashScope video request aspect_ratio",
    "DashScope 视频请求 model 不合法": "Invalid DashScope video request model",
    "DashScope 视频请求 prompt 不合法": "Invalid DashScope video request prompt",
    "DashScope 视频请求 resolution 不合法": "Invalid DashScope video request resolution",
    "DashScope 视频请求 seconds 不合法": "Invalid DashScope video request seconds",
    "DashScope 视频请求 seed 不合法": "Invalid DashScope video request seed",
    "DashScope 视频请求开关字段不合法": "Invalid DashScope video request switch field",
    "DashScope 视频请求必须提供 prompt 或媒体素材": (
        "DashScope video requests must provide a prompt or media material"
    ),
    "DashScope 视频请求素材地址不合法": "Invalid DashScope video request material URL",
    "DashScope 视频请求素材数量不合法": "Invalid DashScope video request material count",
    "DashScope 视频请求素材组合不合法": "Invalid DashScope video request material combination",
    "Gemini Provider 不支持 OpenAI Responses API": "Gemini Provider does not support the OpenAI Responses API",
    "Gemini Provider 不支持 multipart 图片编辑": "Gemini Provider does not support multipart image editing",
    "Gemini 图像请求必须提供非空 contents 列表": "Gemini image requests must provide a non-empty contents list",
    "Gemini 请求必须提供非空 contents 列表": "Gemini requests must provide a non-empty contents list",
    "H3 渠道 API Key 不合法": "Invalid H3 channel API key",
    "H3 渠道 API Key 未配置": "H3 channel API key is not configured",
    "H3 渠道 URL 必须使用 HTTP 或 HTTPS 协议": "H3 channel URL must use the HTTP or HTTPS protocol",
    "LOG_FORMAT 必须是 json 或 text": "LOG_FORMAT must be json or text",
    "LOG_LEVEL 必须是有效日志级别": "LOG_LEVEL must be a valid log level",
    "MiniMax 官方 V2 不支持取消任务": "MiniMax Official V2 does not support task cancellation",
    "MiniMax 官方 model 不合法": "Invalid MiniMax Official model",
    "MiniMax 官方参考素材请求 ratio 必须为 adaptive": (
        "MiniMax Official reference material requests must use ratio=adaptive"
    ),
    "MiniMax 官方渠道 API Key 不合法": "Invalid MiniMax Official channel API key",
    "MiniMax 官方渠道 URL 必须使用 HTTP 或 HTTPS 协议": (
        "MiniMax Official channel URL must use the HTTP or HTTPS protocol"
    ),
    "MiniMax 官方请求 aspect_ratio 不合法": "Invalid MiniMax Official aspect_ratio",
    "MiniMax 官方请求 resolution 不合法": "Invalid MiniMax Official resolution",
    "MiniMax 官方请求 seconds 不合法": "Invalid MiniMax Official seconds",
    "MiniMax 官方请求参考素材数量不合法": "Invalid MiniMax Official reference material count",
    "MiniMax 官方请求参考素材组合不合法": "Invalid MiniMax Official reference material combination",
    "MiniMax 官方请求必须提供非空 prompt": "MiniMax Official requests must provide a non-empty prompt",
    "Provider 模板不存在": "Provider template not found",
    "Redis 熔断中": "Redis circuit breaker is open",
    "Responses API 请求必须提供非空 input": "Responses API requests must provide a non-empty input",
    "Stripe 取消地址必须使用 HTTPS 地址": "Stripe cancel URL must be an HTTPS URL",
    "Stripe 回调币种不是 USD": "Stripe callback currency is not USD",
    "Stripe 回调缺少必要订单字段": "Stripe callback is missing required order fields",
    "Stripe 回调订单号不一致": "Stripe callback order ID mismatch",
    "Stripe 回调金额与订单快照不一致": "Stripe callback amount does not match the order snapshot",
    "Stripe 回调金额快照无效": "Invalid Stripe callback amount snapshot",
    "Stripe 必须配置 API Key、Webhook Secret、test/live 模式和 USD 币种": (
        "Stripe requires the API Key, Webhook Secret, test/live mode and USD currency to be configured"
    ),
    "Stripe 收银台暂时不可用，请稍后重试": "Stripe checkout is temporarily unavailable, please try again later",
    "Stripe 配置不可用": "Stripe configuration is unavailable",
    "Stripe 首版仅支持 card 支付方式": "The initial Stripe release only supports the card payment method",
    "Token 不存在": "Token not found",
    "Token 分组不存在": "Token group not found",
    "Token 分组主键生成失败": "Failed to generate the token group primary key",
    "USD/CNY 汇率服务暂时不可用": "The USD/CNY exchange rate service is temporarily unavailable",
    "USD/CNY 汇率服务返回无效汇率": "The USD/CNY exchange rate service returned an invalid rate",
    "Webhook 暂时无法处理": "The webhook cannot be processed right now",
    "Webhook 签名无效": "Invalid webhook signature",
    "Webhook 签名缺失": "Missing webhook signature",
    "loadavg 内容格式不正确": "The loadavg content is malformed",
    "Webhook 请求过大": "Webhook request is too large",
    "between 操作符必须使用两个边界值": "The between operator requires exactly two boundary values",
    "fal 任务 endpoint 未初始化": "The fal task endpoint is not initialized",
    "fal 冻结模板配置不合法": "Invalid fal frozen template configuration",
    "fal 渠道 API Key 不合法": "Invalid fal channel API key",
    "fal 渠道 URL 必须使用 HTTP 或 HTTPS 协议": "fal channel URL must use the HTTP or HTTPS protocol",
    "fal 请求 aspect_ratio 不合法": "Invalid fal request aspect_ratio",
    "fal 请求 end_image_url 不合法": "Invalid fal request end_image_url",
    "fal 请求 image_url 不合法": "Invalid fal request image_url",
    "fal 请求 prompt_expansion_mode 不合法": "Invalid fal request prompt_expansion_mode",
    "fal 请求 resolution 不合法": "Invalid fal request resolution",
    "fal 请求 seconds 不合法": "Invalid fal request seconds",
    "fal 请求 seed 不合法": "Invalid fal request seed",
    "fal 请求参考素材组合不合法": "Invalid fal request reference material combination",
    "fal 请求必须提供非空 prompt": "fal requests must provide a non-empty prompt",
    "in 操作符必须使用数组值": "The in operator requires an array value",
    "model 必须是字符串": "model must be a string",
    "return_url 必须是完整的 HTTPS 地址": "return_url must be a complete HTTPS URL",
    "上海时间条件不合法": "Invalid Shanghai time condition",
    "上海时间条件仅支持 between 操作符": "Shanghai time conditions only support the between operator",
    "上海时间条件必须使用 HH:MM:SS.ffffff 格式": ("Shanghai time conditions must use the HH:MM:SS.ffffff format"),
    "上海时间条件必须使用两个时间边界值": "Shanghai time conditions require exactly two time boundary values",
    "上游取消请求失败": "Failed to request cancellation upstream",
    "上游服务不可用": "Upstream service unavailable",
    "上游视频服务不支持取消任务": "The upstream video service does not support task cancellation",
    "上游视频服务渠道 API Key 不合法": "Invalid upstream video service channel API key",
    "上游视频服务渠道 URL 必须使用 HTTP 或 HTTPS 协议": (
        "The upstream video service channel URL must use the HTTP or HTTPS protocol"
    ),
    "上游视频服务渠道配置不合法": "Invalid upstream video service channel configuration",
    "上游视频服务素材不可用": "The upstream video service material is unavailable",
    "上游视频服务素材库模型族配置不合法": "Invalid upstream video service asset library model family configuration",
    "上游视频服务素材创建失败": "Failed to create the upstream video service material",
    "上游视频服务素材处理超时": "The upstream video service material processing timed out",
    "上游视频服务请求 aspect_ratio 不合法": "Invalid upstream video service request aspect_ratio",
    "上游视频服务请求 model 不合法": "Invalid upstream video service request model",
    "上游视频服务请求 resolution 不合法": "Invalid upstream video service request resolution",
    "上游视频服务请求 seconds 不合法": "Invalid upstream video service request seconds",
    "上游视频服务请求 seed 不合法": "Invalid upstream video service request seed",
    "上游视频服务请求开关字段不合法": "Invalid upstream video service request switch field",
    "上游视频服务请求参考素材数量不合法": "Invalid upstream video service reference material count",
    "上游视频服务请求参考素材组合不合法": "Invalid upstream video service reference material combination",
    "上游视频服务请求必须提供非空 prompt": "Upstream video service requests must provide a non-empty prompt",
    "上游视频服务请求素材地址不合法": "Invalid upstream video service request material URL",
    "上游未返回任务标识": "Upstream did not return a task ID",
    "上游未返回视频结果地址": "Upstream did not return a video result URL",
    "上游流式响应包含超长未完成事件": ("The upstream streaming response contains an oversized incomplete event"),
    "上游视频任务提交失败": "Failed to submit the video task upstream",
    "上游返回未知任务状态": "Upstream returned an unknown task status",
    "上游返回未知任务结构": "Upstream returned an unknown task structure",
    "上游返回未知响应结构": "Upstream returned an unknown response structure",
    "上游返回非 JSON 响应": "Upstream returned a non-JSON response",
    "不支持的支付服务商": "Unsupported payment provider",
    "不支持的支付服务商配置": "Unsupported payment provider configuration",
    "主分组与兜底分组均没有可匹配的计费方案": (
        "Neither the primary group nor the fallback group has a matching pricing plan"
    ),
    "仅图片 Token 计费项可以配置估算参数": "Only image token pricing items can have estimation parameters",
    "仅输入视频时长计费项可以引用其他计费项单价": (
        "Only input video duration pricing items can reference another pricing item's unit price"
    ),
    "令牌分组不存在": "Token group not found",
    "价格修正不存在": "Pricing modifier not found",
    "价格修正作用范围不受支持": "Unsupported pricing modifier scope",
    "价格修正作用范围不合法": "Invalid pricing modifier scope",
    "价格修正参数不合法": "Invalid pricing modifier parameters",
    "价格修正引用了不受支持的计费项类别": ("The pricing modifier references an unsupported pricing item category"),
    "价格修正引用了其他方案的计费项": "The pricing modifier references a pricing item from another plan",
    "价格修正必须属于同一批保存的计费方案": (
        "Pricing modifiers must belong to the pricing plan saved in the same batch"
    ),
    "价格修正必须指定有效的计费项": "The pricing modifier must reference a valid pricing item",
    "价格修正必须指定有效的计费项类别": "The pricing modifier must specify a valid pricing item category",
    "价格修正类型不受支持": "Unsupported pricing modifier type",
    "价格倍率不合法": "Invalid price multiplier",
    "价格字段白名单不合法": "Invalid pricing field allowlist",
    "价格字段白名单不能重复": "The pricing field allowlist cannot contain duplicates",
    "价格字段白名单只能引用模型请求契约或标准化投影字段": (
        "The pricing field allowlist may only reference model request contract or normalized projection fields"
    ),
    "价格字段白名单引用了未声明字段": "The pricing field allowlist references an undeclared field",
    "价格规则不存在": "Pricing rule not found",
    "价格规则引用了未授权字段": "The pricing rule references an unauthorized field",
    "价格规则操作符不受支持": "Unsupported pricing rule operator",
    "价格规则比较值类型与模型字段契约不一致": (
        "The pricing rule comparison value type does not match the model field contract"
    ),
    "任务终止只能进入 failed、cancelled 或 timed_out": (
        "A terminated task can only transition to failed, cancelled or timed_out"
    ),
    "会话已失效": "Session has expired",
    "作用于全部计费项时不能指定具体计费项": (
        "A specific pricing item cannot be specified when applying to all pricing items"
    ),
    "使用记录不存在": "Usage record not found",
    "使用记录不是已结算状态，不能冲正": "The usage record is not settled and cannot be reversed",
    "供应商图标不存在": "Provider logo not found",
    "充值倍率必须包含 default 分组": "Top-up multipliers must include the default group",
    "充值折扣和倍率必须为有限正数": "Top-up discounts and multipliers must be finite positive numbers",
    "充值金额不在允许范围内": "Top-up amount is outside the allowed range",
    "充值金额必须是最多两位小数的正数": ("Top-up amount must be a positive number with at most two decimal places"),
    "充值金额范围无效": "Invalid top-up amount range",
    "兑换码不存在": "Redemption code not found",
    "兑换码无效或已使用": "Redemption code is invalid or already used",
    "兑换金额必须为正": "Redemption amount must be positive",
    "入账金额必须为正数": "Credit amount must be positive",
    "公开分组不能配置授权用户": "Public groups cannot have authorized users configured",
    "公开模型不存在或未启用": "Public model not found or not enabled",
    "公开模型字段契约不合法": "Invalid public model field contract",
    "冻结 H3 请求不符合契约": "The frozen H3 request does not match the contract",
    "冻结 Provider 配置不可用": "Frozen Provider configuration is unavailable",
    "冻结模型协议不可用": "Frozen model protocol is unavailable",
    "冻结渠道 Provider 不可用": "The frozen channel Provider is unavailable",
    "冻结渠道实例快照不合法": "Invalid frozen channel instance snapshot",
    "冻结渠道引用不完整": "Incomplete frozen channel reference",
    "冻结渠道快照不合法": "Invalid frozen channel snapshot",
    "冻结渠道配置不可用": "Frozen channel configuration is unavailable",
    "分组不可重复": "Groups cannot contain duplicates",
    "分组告警规则不存在": "Group alert rule not found",
    "刷新令牌无效": "Invalid refresh token",
    "可用 Token 数量已达上限": "The maximum number of usable tokens has been reached",
    "告警记录不存在": "Alert record not found",
    "该告警已结束，无需处置": "The alert has already ended and needs no handling",
    "同一价格规则内价格修正规则 priority 不能重复": (
        "Pricing modifier priority must be unique within the same pricing rule"
    ),
    "同一模型和令牌组内价格规则 priority 不能重复": (
        "Pricing rule priority must be unique within the same model and token group"
    ),
    "固定价格修正参数不合法": "Invalid fixed pricing modifier parameters",
    "固定价格修正必须且只能作用于一个计费项": ("A fixed pricing modifier must apply to exactly one pricing item"),
    "图片 Token 估算配置不合法": "Invalid image token estimation configuration",
    "图片 Token 估算配置包含未授权字段": ("The image token estimation configuration contains unauthorized fields"),
    "图片 Token 估算配置必须为正数": "Image token estimation configuration must be a positive number",
    "图片 Token 计费必须同时配置图片输入与输出 Token 项": (
        "Image token pricing requires both image input and output token items"
    ),
    "图片 Token 计费缺少估算配置": "Image token pricing is missing the estimation configuration",
    "图片 Token 计费项缺少每张图片 Token 估算参数": (
        "The image token pricing item is missing the per-image token estimation parameter"
    ),
    "图片像素派生字段必须引用声明的字符串字段": ("Image pixel derived fields must reference a declared string field"),
    "图片响应为空": "Image response is empty",
    "图片编辑仅支持图片类型文件": "Image editing only supports image files",
    "图片编辑必须提供输入图片": "Image editing requires at least one input image",
    "图片编辑最多提供一个蒙版": "Image editing accepts at most one mask",
    "图片编辑输入图片数量超出限制": "Image editing input image count exceeds the limit",
    "图片编辑输入文件超出大小限制": "Image editing input file exceeds the size limit",
    "图片计费不能混用按次按张与图片 Token 计费项": (
        "Image pricing cannot mix per-request or per-image items with image token pricing items"
    ),
    "图片请求必须提供非空 prompt": "Image requests must provide a non-empty prompt",
    "图片输入 Token 计费项缺少 Gemini 未知尺寸图片 tile 数": (
        "The image input token pricing item is missing the Gemini unknown-size image tile count"
    ),
    "图片输入 Token 计费项缺少文本字符 Token 比率": (
        "The image input token pricing item is missing the text character token ratio"
    ),
    "存在不可用分组": "One or more groups are unavailable",
    "实际支付金额不能小于 0.01 元": "The actual payment amount cannot be less than CNY 0.01",
    "已认证用户不存在": "Authenticated user not found",
    "开始与结束时间必须同时提供": "The start and end times must be provided together",
    "当前分组不可用": "The current group is unavailable",
    "当前模型不支持流式生成": "The current model does not support streaming generation",
    "当前模型没有可用渠道": "The current model has no available channel",
    "当前渠道适配器不支持图片生成测试": ("The current channel adapter does not support image generation testing"),
    "当前渠道适配器不支持文本生成测试": ("The current channel adapter does not support text generation testing"),
    "当前视频不支持该成品类型": "The current video does not support this result type",
    "必须明确确认当前支付条款": "The current payment terms must be explicitly confirmed",
    "快捷充值金额必须在范围内且最多两位小数": (
        "The quick top-up amount must be within range and have at most two decimal places"
    ),
    "扣费金额必须为正数": "Debit amount must be positive",
    "报价时间不合法": "Invalid quote time",
    "按数量计费项必须引用数值类型字段": "Quantity-based pricing items must reference a numeric field",
    "授予金额必须为正数": "Grant amount must be positive",
    "授权用户不可重复": "Authorized users cannot contain duplicates",
    "授权用户不存在": "Authorized user not found",
    "操作成功": "Success",
    "支付功能暂未开启": "Payments are not enabled",
    "支付加密服务不可用": "The payment encryption service is unavailable",
    "支付合规确认保存失败": "Failed to save the payment compliance confirmation",
    "支付回调金额与订单不一致": "The payment callback amount does not match the order",
    "支付宝回调卖家不匹配": "Alipay callback seller mismatch",
    "支付宝回调应用不匹配": "Alipay callback app mismatch",
    "支付宝回调签名无效": "Invalid Alipay callback signature",
    "支付宝回调缺少订单字段": "Alipay callback is missing order fields",
    "支付宝回调金额无效": "Invalid Alipay callback amount",
    "支付宝回调金额格式无效": "Invalid Alipay callback amount format",
    "支付宝官方不支持该支付方式": "Alipay Official does not support this payment method",
    "支付宝官方必须配置 AppID、密钥和 page_pay 支付方式": (
        "Alipay Official requires the AppID, keys and the page_pay payment method to be configured"
    ),
    "支付方式不能为空且不能重复": "Payment methods cannot be empty or contain duplicates",
    "支付方式充值金额范围无效": "Invalid top-up amount range for the payment method",
    "支付方式图标必须使用 HTTPS 地址": "Payment method icons must use HTTPS URLs",
    "支付方式未启用": "The payment method is not enabled",
    "支付方式未在指定支付渠道中启用": ("The payment method is not enabled for the specified payment channel"),
    "支付方式未配置": "The payment method is not configured",
    "支付方式配置格式无效": "Invalid payment method configuration format",
    "支付服务商不能重复": "Payment providers cannot contain duplicates",
    "支付服务商配置格式无效": "Invalid payment provider configuration format",
    "支付渠道与支付方式组合不能重复": ("Payment channel and payment method combinations cannot contain duplicates"),
    "支付订单不存在或支付渠道不匹配": "Payment order not found or payment channel mismatch",
    "支付订单状态不允许结算": "The payment order status does not allow settlement",
    "支付配置不可用": "Payment configuration is unavailable",
    "支付配置密文无法解密": "The payment configuration ciphertext cannot be decrypted",
    "支付配置格式无效": "Invalid payment configuration format",
    "文本响应为空": "Text response is empty",
    "文本请求必须提供非空 messages 列表": "Text requests must provide a non-empty messages list",
    "无效 Token": "Invalid token",
    "无法识别输入素材的媒体格式": "Unable to recognize the media format of the input material",
    "时间必须包含时区": "The time must include a timezone",
    "时间范围不合法": "Invalid time range",
    "易支付 RSA 密钥不能为空": "The Epay RSA key cannot be empty",
    "易支付 RSA 密钥格式无效": "Invalid Epay RSA key format",
    "易支付商户私钥必须是 RSA 格式": "The Epay merchant private key must be in RSA format",
    "易支付回调商户或支付类型不匹配": "Epay callback merchant or payment type mismatch",
    "易支付回调已过期": "The Epay callback has expired",
    "易支付回调时间戳无效": "Invalid Epay callback timestamp",
    "易支付回调签名无效": "Invalid Epay callback signature",
    "易支付回调缺少订单字段": "Epay callback is missing order fields",
    "易支付回调金额无效": "Invalid Epay callback amount",
    "易支付回调金额格式无效": "Invalid Epay callback amount format",
    "易支付平台公钥必须是 RSA 格式": "The Epay platform public key must be in RSA format",
    "易支付必须配置商户 ID 和密钥": "Epay requires the merchant ID and key to be configured",
    "易支付配置不可用": "Epay configuration is unavailable",
    "服务暂时不可用": "Service temporarily unavailable",
    "服务端缺少媒体探测能力": "The server lacks media probing capability",
    "未匹配到模型模板，请显式指定 template_id": "No matching model template found, please specify template_id explicitly",
    "未配置当前公开模型": "The current public model is not configured",
    "未配置当前视频规格的有效计费方案": ("No valid pricing plan is configured for the current video specification"),
    "模型不存在": "Model not found",
    "模型不存在或已被删除": "Model not found or already deleted",
    "模型名称已存在": "Model name already exists",
    "模型广场模型不存在": "Model plaza model not found",
    "模型标准化投影不合法": "Invalid model normalized projection",
    "模型标准化投影字段类型不一致": "Inconsistent model normalized projection field types",
    "模型标准化投影引用了未声明字段": "The model normalized projection references an undeclared field",
    "模型标准化投影枚举映射不合法": "Invalid model normalized projection enum mapping",
    "模型模板不存在": "Model template not found",
    "模型模板不能为空": "Model template cannot be empty",
    "模型模板类型与模型类型不一致": "The model template type does not match the model type",
    "模型类型不支持": "Unsupported model type",
    "模型类型不支持计费校验": "The model type does not support pricing validation",
    "模型请求契约不合法": "Invalid model request contract",
    "派生计费字段只能引用模型请求契约": ("Derived pricing fields may only reference the model request contract"),
    "派生计费字段声明不合法": "Invalid derived pricing field declaration",
    "派生计费字段类型不受支持": "Unsupported derived pricing field type",
    "派生计费字段类型不能重复": "Derived pricing field types cannot contain duplicates",
    "渠道 Provider 未配置凭据": "The channel Provider has no credentials configured",
    "渠道 URL 必须使用 HTTP 或 HTTPS 协议": "Channel URL must use the HTTP or HTTPS protocol",
    "渠道不存在": "Channel not found",
    "渠道令牌分组不合法": "Invalid channel token group",
    "渠道已停用，无法测试": "The channel is disabled and cannot be tested",
    "渠道未配置可测试模型": "The channel has no testable model configured",
    "渠道权重必须为正整数": "Channel weight must be a positive integer",
    "渠道模型列表不合法": "Invalid channel model list",
    "渠道模型列表不能重复": "The channel model list cannot contain duplicates",
    "渠道模型映射包含未启用模型": "The channel model mapping contains a disabled model",
    "渠道模型映射必须为上游模型名": "Channel model mappings must be upstream model names",
    "渠道运行选项不允许包含地址或认证数据": ("Channel runtime options cannot contain URLs or authentication data"),
    "渠道随机源必须返回大于等于零且小于一的数值": (
        "The channel random source must return a value greater than or equal to zero and less than one"
    ),
    "用户不存在": "User not found",
    "用户名已存在": "Username already exists",
    "用户名或密码错误": "Incorrect username or password",
    "用户权限不足": "Insufficient user permissions",
    "用户钱包不存在": "User wallet not found",
    "第三方交易号已被其他订单使用": ("The third-party transaction ID is already used by another order"),
    "管理员权限不足": "Insufficient administrator permissions",
    "系统任务租约已失效": "The system task lease has expired",
    "系统已完成管理员初始化": "Administrator initialization has already been completed",
    "素材 Token 计费项必须引用素材字段": "Material token pricing items must reference a material field",
    "素材不存在": "Material not found",
    "素材资源标识不合法": "Invalid material resource identifier",
    "结束时间必须晚于开始时间": "The end time must be later than the start time",
    "统计维度不合法": "Invalid statistics dimension",
    "统计范围不能超过366天": "The statistics range cannot exceed 366 days",
    "缺少 Bearer Token": "Missing Bearer token",
    "缺少刷新令牌": "Missing refresh token",
    "缺少有效访问令牌": "Missing valid access token",
    "缺少用量": "Missing usage data",
    "至少绑定一个分组": "At least one group must be bound",
    "视频任务 ID 格式无效": "Invalid video task ID format",
    "视频任务不存在": "Video task not found",
    "视频任务缺少可结算的使用记录": "The video task is missing a settleable usage record",
    "视频成品尚不可下载": "The video result is not yet downloadable",
    "视频成品暂不可下载": "The video result is temporarily unavailable for download",
    "视频成品目录不可用": "The video result directory is unavailable",
    "视频模型素材契约不合法": "Invalid video model material contract",
    "视频模型缺少请求契约": "The video model is missing the request contract",
    "视频模型请求契约不合法": "Invalid video model request contract",
    "视频渠道不存在": "Video channel not found",
    "视频请求 seconds 不合法": "Invalid video request seconds",
    "计费方案未配置任何启用计费项": "The pricing plan has no enabled pricing items configured",
    "计费方案至少需要一个启用的计费主体项": ("The pricing plan requires at least one enabled primary pricing item"),
    "计费项免费数量必须为非负整数": "The pricing item free quantity must be a non-negative integer",
    "计费项单价不合法": "Invalid pricing item unit price",
    "计费项名称不合法": "Invalid pricing item name",
    "计费项基础单价不合法": "Invalid pricing item base unit price",
    "计费项必须声明计量来源字段": "Pricing items must declare a metering source field",
    "计费项必须属于同一批保存的计费方案": ("Pricing items must belong to the pricing plan saved in the same batch"),
    "计费项类型不受支持": "Unsupported pricing item type",
    "计费项计量来源字段不合法": "Invalid pricing item metering source field",
    "计费项计量来源字段不能重复": "Pricing item metering source fields cannot contain duplicates",
    "计费项计量来源字段未在价格字段白名单中声明": (
        "The pricing item metering source field is not declared in the pricing field allowlist"
    ),
    "订单不存在": "Order not found",
    "认证限流服务暂不可用": "The authentication rate limiting service is temporarily unavailable",
    "访问令牌无效": "Invalid access token",
    "该模型类型必须配置请求契约": "This model type requires a request contract to be configured",
    "该模型类型暂不支持同步测试": "This model type does not support synchronous testing yet",
    "该模型未配置定价": "The model has no pricing configured",
    "该渠道未配置此模型": "This model is not configured for the channel",
    "请求体不是合法 JSON": "The request body is not valid JSON",
    "请求体必须是 JSON 对象": "The request body must be a JSON object",
    "请求参数校验失败": "Request parameter validation failed",
    "请求超时": "Request timed out",
    "豆包 Seed Provider 不支持 OpenAI 图片接口": ("Doubao Seed Provider does not support the OpenAI image API"),
    "豆包 Seed Provider 仅支持 Responses 接口": "Doubao Seed Provider only supports the Responses API",
    "豆包 Seed 请求必须提供非空 input": "Doubao Seed requests must provide a non-empty input",
    "输入图片像素超出限制": "Input image pixels exceed the limit",
    "输入图片地址不合法": "Invalid input image URL",
    "输入素材下载失败": "Failed to download the input material",
    "输入素材下载重定向次数超出限制": ("Input material download exceeded the maximum number of redirects"),
    "输入素材下载重定向缺少目标地址": "Input material download redirect is missing a target URL",
    "输入素材为空": "Input material is empty",
    "输入素材地址不合法": "Invalid input material URL",
    "输入素材地址不被允许": "The input material URL is not allowed",
    "输入素材地址协议不受支持": "The input material URL protocol is not supported",
    "输入素材地址无法解析": "The input material URL cannot be resolved",
    "输入素材媒体解析失败": "Failed to parse the input material media",
    "输入素材媒体解析超时": "Parsing the input material media timed out",
    "输入素材时长无法确定": "Unable to determine the input material duration",
    "输入素材超出大小限制": "Input material exceeds the size limit",
    "输入视频时长计费项必须复用方案内唯一的输出视频时长计费项": (
        "The input video duration pricing item must reuse the single output video duration pricing item in the plan"
    ),
    "输入视频时长超出限制": "Input video duration exceeds the limit",
    "输入视频计费项不能引用已停用的输出视频时长计费项": (
        "Input video pricing items cannot reference a disabled output video duration pricing item"
    ),
    "输入视频计费项必须引用同方案唯一的输出视频时长计费项": (
        "Input video pricing items must reference the single output video duration pricing item in the same plan"
    ),
    "钱包余额不足": "Insufficient wallet balance",
    "非开发环境必须配置安全的 JWT 签名密钥和刷新令牌 Pepper": (
        "Non-development environments require a secure JWT signing key and refresh token pepper"
    ),
    "音频模型不能配置请求契约": "Audio models cannot have a request contract configured",
    "默认分组不可删除": "The default group cannot be deleted",
    "默认分组不可重命名": "The default group cannot be renamed",
    "默认分组必须公开": "The default group must be public",
    "默认分组必须启用": "The default group must be enabled",
    # Provider 模板展示文案与模型广场展示提示，按 X-Locale 切换；模板稳定标识不在此列
    "千问": "Qwen",
    "豆包": "Doubao",
    "通义千问": "Tongyi Qianwen",
    "通义万相": "Tongyi Wanxiang",
    "火山引擎": "Volcano Engine",
    "万相": "Wan",
    "万相 3.0 视频生成": "Wan 3.0 Video Generation",
    "通过百炼 DashScope 原生异步接口生成万相 3.0 视频，支持文生视频、图生视频与参考生视频。": (
        "Generate Wan 3.0 videos through the native asynchronous DashScope API, supporting text-to-video, "
        "image-to-video, and reference-to-video."
    ),
    "文生视频": "Text to video",
    "图生视频": "Image to video",
    "参考生视频": "Reference to video",
    "文生图": "Text to image",
    "图片编辑": "Image editing",
    "文本对话": "Text chat",
    "流式输出": "Streaming output",
    "视频任务": "Video tasks",
    "视频生成": "Video generation",
    "fal 同步": "fal synchronous",
    "多模态": "Multimodal",
    "方舟": "Ark",
    "MiniMax 官方": "MiniMax official",
    "fal MiniMax H3 Max 文生视频": "fal MiniMax H3 Max Text to Video",
    "fal MiniMax H3 Max 参考生视频": "fal MiniMax H3 Max Reference to Video",
    "fal MiniMax H3 Max 图生视频": "fal MiniMax H3 Max Image to Video",
    "根据文本提示词生成图片，并支持带输入图片的编辑。": (
        "Generate images from text prompts and edit them with input images."
    ),
    "OpenAI 兼容的文本对话补全，支持普通与流式响应。": (
        "OpenAI-compatible text chat completions with regular and streaming responses."
    ),
    "OpenAI 兼容的 Responses API，支持同步与流式响应。": (
        "The OpenAI-compatible Responses API with synchronous and streaming responses."
    ),
    "通过 OpenAI 兼容视频接口创建、查询和下载视频任务。": (
        "Create, query, and download video tasks through the OpenAI-compatible video API."
    ),
    "Gemini 原生 generateContent 与流式内容生成。": ("Native Gemini generateContent and streaming content generation."),
    "Gemini 原生图像生成与图像编辑，响应以 inlineData 返回图片。": (
        "Native Gemini image generation and editing, returning images as inlineData."
    ),
    "Anthropic 原生 Messages 接口，支持同步与流式响应。": (
        "Native Anthropic Messages API with synchronous and streaming responses."
    ),
    "DashScope 原生 Generation 接口，支持纯文本与多模态输入及增量流式输出。": (
        "Native DashScope Generation API supporting text and multimodal input with incremental streaming output."
    ),
    "火山方舟原生 Responses 接口，支持同步与流式事件。": (
        "Native Volcengine Ark Responses API with synchronous and streaming events."
    ),
    "通过 MiniMax 官方 Video Generation V2 异步接口生成视频。": (
        "Generate videos through the MiniMax official Video Generation V2 asynchronous API."
    ),
    "根据文本或参考素材生成短视频。": "Generate short videos from text or reference materials.",
    "通过 fal 同步接口根据文本提示词生成视频。": ("Generate videos from text prompts through the fal synchronous API."),
    "通过 fal 同步接口根据参考图片、视频或音频生成视频。": (
        "Generate videos from reference images, videos, or audio through the fal synchronous API."
    ),
    "通过 fal 同步接口根据首帧和尾帧图片生成视频。": (
        "Generate videos from start and end frame images through the fal synchronous API."
    ),
    "一只戴墨镜的橘猫，电影感光影": "An orange cat wearing sunglasses, cinematic lighting",
    "镜头缓慢推进，一只橘猫在窗边晒太阳": "The camera slowly pushes in on an orange cat sunning itself by the window",
    "你好，介绍一下你自己": "Hello, introduce yourself",
    "用一句话介绍你自己": "Introduce yourself in one sentence",
    "参考素材中的人物向镜头挥手": "The person in the reference material waves at the camera",
    "镜头慢慢拉远": "The camera slowly pulls back",
    "按实际用量计费": "Pay based on actual usage",
    # 接口文档展示文案：能力名、条目名、调用说明与错误场景说明
    "文本生成": "Text generation",
    "图片生成": "Image generation",
    "OpenAI 文本对话": "OpenAI text chat",
    "OpenAI 图片生成与编辑": "OpenAI image generation and editing",
    "Gemini 内容生成": "Gemini content generation",
    "Gemini 图片生成与编辑": "Gemini image generation and editing",
    "千问文本与多模态生成": "Qwen text and multimodal generation",
    "豆包 Responses": "Doubao Responses",
    "支持文生视频、图生视频与参考生视频。": "Supports text-to-video, image-to-video, and reference-to-video.",
    "接口文档条目不存在": "The API documentation entry does not exist",
    "令牌缺失、无效或已停用": "API key is missing, invalid, or disabled",
    "账户余额不足": "Insufficient account balance",
    "令牌无权访问该模型或模型分组": "The API key cannot access this model or token group",
    "请求的资源或任务不存在": "The requested resource or task does not exist",
    "请求与现有资源冲突": "The request conflicts with an existing resource",
    "请求参数或模型契约校验失败": "Request parameters or the model contract failed validation",
    "超出速率或并发限制": "Rate or concurrency limit exceeded",
    "服务内部错误": "Internal server error",
    "上游服务超时": "The upstream service timed out",
    "鉴权服务暂时不可用": "The authentication service is temporarily unavailable",
    "任务已受理，等待生成": "The task has been accepted and is waiting to be generated",
    "正在生成视频": "The video is being generated",
    "视频已生成完成，可通过结果地址下载": "The video is ready and can be downloaded from the result URL",
    "生成失败或任务被终止，失败原因见 error 字段": (
        "Generation failed or the task was terminated; see the error field for the reason"
    ),
    "任务状态由平台按上游处理进度推进；仅 completed 提供结果地址，failed 时由 error 字段给出原因。": (
        "The platform advances the task status as upstream processing progresses; only completed provides a result URL, "
        "and failed reports the reason in the error field."
    ),
    "素材字段既可直接传入公开可访问的 URL，也可随创建请求以 multipart/form-data 上传文件。": (
        "Material fields accept either a publicly reachable URL or a file uploaded with the create request as "
        "multipart/form-data."
    ),
    "请求体 stream 为 true 时以 SSE 返回增量内容。": (
        "When the request body sets stream to true, incremental content is returned as SSE."
    ),
    "该接口始终以 SSE 返回增量内容。": "This endpoint always returns incremental content as SSE.",
    # 接口文档的接口名、说明、参数与响应说明
    "创建视频任务": "Create a video task",
    "获取视频任务": "Retrieve a video task",
    "下载视频成品": "Download the video output",
    "查询视频成品": "Check the video output",
    "创建文本补全": "Create a chat completion",
    "创建响应": "Create a response",
    "创建图片生成": "Create an image generation",
    "创建图片编辑": "Create an image edit",
    "创建 Anthropic 消息": "Create an Anthropic message",
    "生成 Gemini 内容": "Generate Gemini content",
    "流式生成 Gemini 内容": "Stream Gemini content",
    "创建千问文本生成": "Create a Qwen text generation",
    "创建千问多模态生成": "Create a Qwen multimodal generation",
    "创建豆包响应": "Create a Doubao response",
    "提交一次生成请求并返回任务对象；异步渠道返回进行中状态，同步渠道可能在同一请求内返回成品。": (
        "Submit a generation request and return a task object; asynchronous channels return an in-progress status, "
        "while synchronous channels may return the finished video in the same request."
    ),
    "按任务 ID 查询任务状态、进度、结果地址与错误信息。": (
        "Query task status, progress, result URL, and error details by task ID."
    ),
    "按任务 ID 下载视频成品，返回二进制流。": "Download the video output by task ID as a binary stream.",
    "只返回响应头与空响应体，用于探测成品是否已就绪。": (
        "Returns response headers with an empty body, used to check whether the output is ready."
    ),
    "创建一次对话补全。": "Create a chat completion.",
    "创建一次 Responses 调用。": "Create a Responses call.",
    "根据文本提示词生成图片。": "Generate an image from a text prompt.",
    "以 multipart 提交输入图片并生成编辑结果。": ("Submit input images as multipart and generate an edited result."),
    "创建一次 Anthropic Messages 调用。": "Create an Anthropic Messages call.",
    "生成一次 Gemini 内容。": "Generate Gemini content once.",
    "以 SSE 增量返回 Gemini 内容。": "Stream Gemini content as SSE events.",
    "创建一次千问文本生成。": "Create a Qwen text generation.",
    "创建一次千问多模态生成。": "Create a Qwen multimodal generation.",
    "创建一次豆包 Responses 调用。": "Create a Doubao Responses call.",
    "任务 ID，取创建接口返回的 id（形如 task_<uuid>）。": (
        "Task ID, taken from the id returned by the create endpoint (formatted as task_<uuid>)."
    ),
    "模型名，取 GET /v1/models 返回的 id。": "Model name, taken from the id returned by GET /v1/models.",
    "成品变体，当前仅支持默认值 video。": "Output variant; currently only the default value video is supported.",
    "返回任务对象，含 id、status、progress 等字段。": (
        "Returns the task object with id, status, progress, and related fields."
    ),
    "返回任务对象，含状态、进度、结果地址与错误信息。": (
        "Returns the task object with status, progress, result URL, and error details."
    ),
    "返回视频二进制流。": "Returns the video as a binary stream.",
    "返回空响应体，不包含视频内容。": "Returns an empty body without video content.",
    "响应体保持该协议原生形状，不额外包装。": (
        "The response body keeps the native shape of the protocol and is not wrapped further."
    ),
}

CODE_MESSAGES: dict[str, str] = {
    # 模型请求契约校验（channels 与 generation 共用同一批帧）
    "contract.field_type_mismatch": "Field {name} must be of type {expected}",
    "contract.field_not_in_enum": "Field {name} is not among the allowed enum values",
    "contract.field_length_too_short": "Field {name} is too short",
    "contract.field_length_too_long": "Field {name} exceeds the length limit",
    "contract.field_items_too_few": "Field {name} has too few items",
    "contract.field_items_too_many": "Field {name} exceeds the item count limit",
    "contract.field_below_minimum": "Field {name} is below the minimum",
    "contract.field_above_maximum": "Field {name} is above the maximum",
    "contract.field_derived_by_system": "Field {name} is derived by the system and cannot be submitted",
    "contract.field_single_material_only": "Field {name} accepts only one material",
    "contract.unsupported_fields": "The request contains a field the model does not support: {name}",
    "contract.unsupported_upload_fields": (
        "The request contains an upload material field the model does not support: {name}"
    ),
    "contract.missing_required_fields": "Missing required model field: {name}",
    "contract.invalid_field_contract": "Invalid model field contract: {name}",
    "contract.non_empty_field_required": "The request must provide a non-empty {name}",
    "contract.model_reference_deleted": (
        "The model referenced by the channel does not exist or has been deleted: {name}"
    ),
    # 计费方案与报价
    "pricing_plan.duplicate_position": "Duplicate {label} position",
    "pricing_plan.material_field_unsupported_kind": (
        "The pricing item metering source field does not support {category} materials"
    ),
    "pricing.missing_quantity_field": "The pricing item is missing a valid {name} quantity field",
    # 计费与视频素材
    "billing.redemption_code_locked": "A redeemed redemption code cannot be {action}",
    "generation.image_edit_unsupported_field": "Image editing does not support the field: {name}",
    "video.material_category_unsupported": "Unsupported input material category: {category}",
    # 令牌分组
    "token_group.disabled": "Token group is disabled: {name}",
    # 支付
    "payment.gateway_url_https_required": "The {provider} gateway address must use an HTTPS URL",
    "payment.callback_url_https_required": "The {provider} callback address must use an HTTPS URL",
    "payment.return_url_https_required": "The {provider} return URL must use an HTTPS URL",
    "payment.rsa_key_format_invalid": "Invalid {provider} RSA key format",
}
