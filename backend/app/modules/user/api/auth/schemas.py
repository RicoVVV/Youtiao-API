"""认证 HTTP 请求契约，仅定义注册、登录和令牌刷新的输入模型。"""

from pydantic import BaseModel, Field


class UserRegistrationRequest(BaseModel):
    """用户公开注册请求。

    ``username`` 是用户用于密码登录的唯一账号名，注册不会自动创建 Token。
    """

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class UserRegisterRequest(BaseModel):
    """用户公开注册请求，邮箱和验证码在开启验证时必填（由应用服务校验）。"""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    email: str | None = Field(default=None, max_length=320)
    verification_code: str | None = Field(default=None, min_length=6, max_length=6)


class EmailVerificationCodeRequest(BaseModel):
    """发送注册邮箱验证码请求。"""

    email: str = Field(min_length=1, max_length=320)


class Credentials(BaseModel):
    """统一登录请求，用户名对应用户 username。"""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class SetupStatusResponse(BaseModel):
    """首次安装状态响应，供前端决定显示初始化或登录入口。"""

    setup_required: bool
