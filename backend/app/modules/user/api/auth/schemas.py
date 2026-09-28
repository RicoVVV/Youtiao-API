"""认证 HTTP 请求契约，仅定义注册、登录和令牌刷新的输入模型。"""

from pydantic import BaseModel, Field


class UserRegistrationRequest(BaseModel):
    """用户公开注册请求。

    ``username`` 是用户用于密码登录的唯一账号名，注册不会自动创建 Token。
    """

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class Credentials(BaseModel):
    """统一登录请求，用户名对应用户 username。"""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class SetupStatusResponse(BaseModel):
    """首次安装状态响应，供前端决定显示初始化或登录入口。"""

    setup_required: bool
