"""
ComfyUI_Sora - Aabao 文生视频节点
"""

import os
import comfy.utils
import folder_paths
from typing import Tuple, List, Any
from .aabao_base import (
    AabaoBaseNode, AABAO_VIDEO_MODELS, AABAO_STYLE_IDS, 
    AABAO_ORIENTATIONS, AABAO_API_PROVIDERS
)


class AabaoText2Video(AabaoBaseNode):
    """Aabao 文生视频节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (AABAO_API_PROVIDERS, {"default": "aabao"}),
                "api_key": ("STRING", {"default": "", "placeholder": "留空使用config.json配置"}),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "一只可爱的橘猫在阳光下的草地上追逐蝴蝶",
                }),
                "model": (AABAO_VIDEO_MODELS, {"default": "sora-2-landscape-15s"}),
                "style_id": (AABAO_STYLE_IDS, {"default": "无"}),
                "orientation": (AABAO_ORIENTATIONS, {"default": "自动"}),
            },
            "optional": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 999999999}),
                "output_dir": ("STRING", {"default": ""}),
            }
        }
    
    RETURN_TYPES = ("VIDEO", "VHS_FILENAMES", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "Filenames", "video_url", "response_info", "prompt_used")
    FUNCTION = "generate"
    OUTPUT_NODE = True
    CATEGORY = "Ken-Chen/sora"
    
    def generate(self, api_provider: str, api_key: str, prompt: str, model: str, 
                 style_id: str, orientation: str, seed: int = 0, output_dir: str = "") -> Tuple[Any, List[str], str, str, str]:
        
        payload = {"model": model, "prompt": prompt}
        
        if style_id != "无":
            payload["style_id"] = style_id
        if orientation != "自动":
            payload["orientation"] = orientation
        if seed > 0:
            payload["seed"] = seed
        
        pbar = comfy.utils.ProgressBar(100)
        video_url, video_id, message = self._call_videos_api(payload, api_key, pbar)
        
        if not video_url:
            return (None, [], "", f"生成失败: {message}", prompt)
        
        # 下载视频
        filename = self._generate_filename("aabao_t2v", "mp4")
        save_dir = output_dir if output_dir else self.output_dir
        video_path = self._download_video(video_url, filename)
        
        # 构建VHS兼容的文件名列表
        vhs_filenames = [video_path] if video_path else []
        
        response_info = f"生成成功! ID: {video_id}, Share: {message}"
        
        return (video_path, vhs_filenames, video_url, response_info, prompt)


NODE_CLASS_MAPPINGS = {"AabaoText2Video": AabaoText2Video}
NODE_DISPLAY_NAME_MAPPINGS = {"AabaoText2Video": "Aabao 文生视频"}
