"""渠道模型名称映射。

渠道按公开模型名声明请求要转交的上游模型名；未声明时沿用公开模型名，其余已校验字段原样透传。
"""

from typing import Any


def apply_upstream_model_name(provider_request: dict[str, Any], upstream_model: Any) -> None:
    """公开模型已声明上游模型名时覆盖请求的 ``model``，否则保留公开模型名。"""

    if isinstance(upstream_model, str) and upstream_model:
        provider_request["model"] = upstream_model
