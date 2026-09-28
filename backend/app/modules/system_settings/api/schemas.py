from pydantic import AnyHttpUrl, BaseModel, Field, TypeAdapter, field_validator


class SystemSettingsResponse(BaseModel):
    system_name: str
    server_url: str
    logo_url: str
    footer_text: str
    about_content: str
    homepage_content: str
    terms_of_service: str
    privacy_policy: str


class SystemSettingsUpdateRequest(BaseModel):
    system_name: str | None = Field(default=None, max_length=255)
    server_url: str | None = Field(default=None, max_length=2048)
    logo_url: str | None = Field(default=None, max_length=2048)
    footer_text: str | None = Field(default=None, max_length=2000)
    about_content: str | None = None
    homepage_content: str | None = None
    terms_of_service: str | None = None
    privacy_policy: str | None = None

    @field_validator("server_url", "logo_url", mode="before")
    @classmethod
    def normalize_url(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return ""
        return str(TypeAdapter(AnyHttpUrl).validate_python(value))
