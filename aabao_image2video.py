"""
ComfyUI_Sora - Aabao 图生视频节点
"""

import comfy.utils
from typing import Tuple, List, Any
import torch
from .aabao_base import (
    AabaoBaseNode, AABAO_VIDEO_MODELS, AABAO_STYLE_IDS, AABAO_API_PROVIDERS
)


class AabaoImage2Video(AabaoBaseNode):
    """Aabao 图生视频节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (AABAO_API_PROVIDERS, {"default": "aabao"}),
                "api_key": ("STRING", {"default": "", "placeholder": "留空使用config.json配置"}),
                "image": ("IMAGE",),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "让画面动起来",
                }),
                "model": (AABAO_VIDEO_MODELS, {"default": "sora-2-landscape-15s"}),
                "style_id": (AABAO_STYLE_IDS, {"default": "无"}),
            },
            "optional": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 999999999}),
            }
        }
    
    RETURN_TYPES = ("VIDEO", "VHS_FILENAMES", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "Filenames", "video_url", "response_info", "prompt_used")
    FUNCTION = "generate"
    OUTPUT_NODE = True
    CATEGORY = "Ken-Chen/sora"
    
    def generate(self, api_provider: str, api_key: str, image: torch.Tensor, 
                 prompt: str, model: str, style_id: str, seed: int = 0) -> Tuple[Any, List[str], str, str, str]:
        
        image_base64 = self._image_to_base64(image)
        payload = {"model": model, "prompt": prompt, "image": image_base64}
        
        if style_id != "无":
            payload["style_id"] = style_id
        if seed > 0:
            payload["seed"] = seed
        
        pbar = comfy.utils.ProgressBar(100)
        video_url, video_id, message = self._call_videos_api(payload, api_key, pbar)
        
        if not video_url:
            return (None, [], "", f"生成失败: {message}", prompt)
        
        filename = self._generate_filename("aabao_i2v", "mp4")
        video_path = self._download_video(video_url, filename)
        vhs_filenames = [video_path] if video_path else []
        response_info = f"生成成功! ID: {video_id}"
        
        return (video_path, vhs_filenames, video_url, response_info, prompt)


NODE_CLASS_MAPPINGS = {"AabaoImage2Video": AabaoImage2Video}
NODE_DISPLAY_NAME_MAPPINGS = {"AabaoImage2Video": "Aabao 图生视频"}
