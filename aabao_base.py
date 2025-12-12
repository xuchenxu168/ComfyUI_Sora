"""
ComfyUI_Sora - Aabao专用API基础类
专门为aabao API供应商设计
"""

import os
import re
import json
import time
import base64
import requests
import folder_paths
from io import BytesIO
from typing import Optional, Tuple, Any, Dict, List
from PIL import Image
import numpy as np
import torch

# API供应者列表 - 仅aabao
AABAO_API_PROVIDERS = ["aabao"]

# 可用的模型列表
AABAO_VIDEO_MODELS = [
    "sora-2", "sora-2-15s", "sora-2-landscape", "sora-2-landscape-15s",
    "sora-2-portrait", "sora-2-portrait-15s", "sora-2-characters",
]

AABAO_IMAGE_MODELS = ["sora-image", "sora-image-landscape", "sora-image-portrait"]
AABAO_STYLE_IDS = ["无", "festive", "retro", "news", "selfie", "handheld", "anime"]
AABAO_ORIENTATIONS = ["自动", "landscape", "portrait"]
AABAO_IMAGE_SIZES = ["360x360", "540x360", "360x540"]


class AabaoConfigManager:
    def __init__(self):
        self.config_file = os.path.join(os.path.dirname(__file__), "config.json")
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Aabao] 加载配置失败: {e}")
        return {}
    
    def get_api_key(self, custom_key: str = "") -> str:
        """获取API密钥，优先使用自定义密钥"""
        if custom_key and custom_key.strip():
            return custom_key.strip()
        return self.config.get("aabao_api_key", "")
    
    def get_base_url(self) -> str:
        return self.config.get("aabao_base_url", "https://api.aabao.top/v1")
    
    def get_timeout(self) -> int:
        return self.config.get("timeout", 600)


aabao_config = AabaoConfigManager()


class AabaoBaseNode:
    CATEGORY = "Ken-Chen/sora"
    
    def __init__(self):
        self.config = aabao_config
        self.output_dir = folder_paths.get_output_directory()
    
    def _get_headers(self, api_key: str = "") -> Dict[str, str]:
        key = self.config.get_api_key(api_key)
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
    
    def _image_to_base64(self, image: torch.Tensor) -> str:
        if len(image.shape) == 4:
            image = image[0]
        img_np = (image.cpu().numpy() * 255).astype(np.uint8)
        pil_image = Image.fromarray(img_np)
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=95)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{img_base64}"
    
    def _download_video(self, url: str, filename: str) -> str:
        try:
            response = requests.get(url, timeout=self.config.get_timeout())
            response.raise_for_status()
            os.makedirs(self.output_dir, exist_ok=True)
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(response.content)
            print(f"[Aabao] 视频已保存: {filepath}")
            return filepath
        except Exception as e:
            print(f"[Aabao] 下载视频失败: {e}")
            return ""
    
    def _download_image(self, url: str, filename: str) -> str:
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            os.makedirs(self.output_dir, exist_ok=True)
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(response.content)
            print(f"[Aabao] 图像已保存: {filepath}")
            return filepath
        except Exception as e:
            print(f"[Aabao] 下载图像失败: {e}")
            return ""
    
    def _load_image_from_url(self, url: str) -> Optional[torch.Tensor]:
        try:
            if url.startswith("data:"):
                header, data = url.split(",", 1)
                img_data = base64.b64decode(data)
                pil_image = Image.open(BytesIO(img_data)).convert("RGB")
            else:
                response = requests.get(url, timeout=60)
                pil_image = Image.open(BytesIO(response.content)).convert("RGB")
            img_np = np.array(pil_image).astype(np.float32) / 255.0
            return torch.from_numpy(img_np).unsqueeze(0)
        except Exception as e:
            print(f"[Aabao] 加载图像失败: {e}")
            return None
    
    def _call_videos_api(self, payload: Dict[str, Any], api_key: str = "", pbar=None) -> Tuple[str, str, str]:
        url = f"{self.config.get_base_url()}/videos"
        headers = self._get_headers(api_key)
        try:
            print(f"[Aabao] 发送视频生成请求...")
            response = requests.post(url, headers=headers, json=payload, timeout=self.config.get_timeout())
            if response.status_code != 200:
                return ("", "", f"API请求失败: {response.text}")
            result = response.json()
            video_id = result.get("id", "")
            status = result.get("status", "")
            if status == "completed":
                video_url = result.get("video_url", result.get("url", ""))
                return (video_url, video_id, result.get("share_id", ""))
            elif status in ["queued", "in_progress"]:
                return self._poll_video_status(video_id, api_key, pbar)
            elif result.get("object") == "character":
                return (result.get("username", ""), video_id, result.get("message", ""))
            return ("", video_id, f"未知状态: {result}")
        except Exception as e:
            return ("", "", f"API异常: {e}")
    
    def _poll_video_status(self, video_id: str, api_key: str = "", pbar=None) -> Tuple[str, str, str]:
        url = f"{self.config.get_base_url()}/videos/{video_id}"
        headers = self._get_headers(api_key)
        for _ in range(120):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code != 200:
                    time.sleep(5)
                    continue
                result = response.json()
                status = result.get("status", "")
                progress = result.get("progress", 0)
                if pbar:
                    pbar.update_absolute(progress)
                print(f"[Aabao] 进度: {progress}%")
                if status == "completed":
                    return (result.get("video_url", result.get("url", "")), video_id, result.get("share_id", ""))
                elif status == "failed":
                    return ("", video_id, result.get("error", {}).get("message", "失败"))
                time.sleep(5)
            except Exception as e:
                print(f"[Aabao] 查询异常: {e}")
                time.sleep(5)
        return ("", video_id, "超时")
    
    def _call_images_generations_api(self, payload: Dict[str, Any], api_key: str = "") -> List[str]:
        url = f"{self.config.get_base_url()}/images/generations"
        headers = self._get_headers(api_key)
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.config.get_timeout())
            if response.status_code != 200:
                return []
            result = response.json()
            urls = []
            for item in result.get("data", []):
                if "url" in item:
                    urls.append(item["url"])
                elif "b64_json" in item:
                    urls.append(f"data:image/png;base64,{item['b64_json']}")
            return urls
        except Exception as e:
            print(f"[Aabao] API异常: {e}")
            return []
    
    def _call_images_edits_api(self, payload: Dict[str, Any], api_key: str = "") -> str:
        url = f"{self.config.get_base_url()}/images/edits"
        headers = self._get_headers(api_key)
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.config.get_timeout())
            if response.status_code != 200:
                return ""
            result = response.json()
            data = result.get("data", [])
            if data:
                if "url" in data[0]:
                    return data[0]["url"]
                elif "b64_json" in data[0]:
                    return f"data:image/png;base64,{data[0]['b64_json']}"
            return ""
        except Exception as e:
            print(f"[Aabao] API异常: {e}")
            return ""
    
    def _generate_filename(self, prefix: str, ext: str = "mp4") -> str:
        import random
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        suffix = "".join([str(random.randint(0, 9)) for _ in range(4)])
        return f"{prefix}_{timestamp}_{suffix}.{ext}"
