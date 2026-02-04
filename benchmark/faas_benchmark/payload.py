"""请求负载构建."""

import base64
import os
from typing import Any


class PayloadBuilder:
    """构建请求负载."""

    def __init__(self, mode: str, image_url: str | None, image_path: str | None):
        self.mode = mode
        self.image_url = image_url
        self.image_path = image_path

    def build(self) -> dict[str, Any]:
        """构建请求体."""
        match self.mode:
            case "url":
                return self._build_url_payload()
            case "image":
                return self._build_image_payload()
            case "health":
                return {}
            case _:
                return self._build_url_payload()

    def _build_url_payload(self) -> dict[str, str]:
        """构建 URL 模式负载."""
        url = self.image_url or "https://picsum.photos/400/300"
        return {"url": url}

    def _build_image_payload(self) -> dict[str, str]:
        """构建图片模式负载."""
        image_path = self.image_path or "test.jpg"

        if not os.path.exists(image_path):
            # 如果本地图片不存在，回退到 URL 模式
            return self._build_url_payload()

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        return {"image": image_data}
