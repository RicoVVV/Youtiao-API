"""SMTP 邮件发送基础设施，只负责发送纯文本邮件，不包含任何业务逻辑。"""

import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.errors import AuthenticationProviderUnavailableError

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT = 10


def send_email(
    *,
    host: str,
    port: int,
    security: str,
    username: str,
    password: str,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body: str,
) -> None:
    """发送纯文本邮件。security 取值：none、starttls、ssl。

    异常：连接、认证或发送失败时抛出 AuthenticationProviderUnavailableError（503）。
    安全：日志不记录密码与邮件正文。
    """

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8").encode()
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = to_email
    try:
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT) as smtp:
                if security == "starttls":
                    smtp.starttls()
                if username:
                    smtp.login(username, password)
                smtp.sendmail(from_email, [to_email], msg.as_string())
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("SMTP 发送失败 to=%s host=%s: %s", to_email, host, type(exc).__name__)
        raise AuthenticationProviderUnavailableError("邮件发送失败，请检查 SMTP 配置") from exc
