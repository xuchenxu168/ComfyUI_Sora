"""
ComfyUI_Sora - Aabao 分镜模式节点
"""

import comfy.utils
from typing import Tuple, List, Any
from .aabao_base import AabaoBaseNode, AABAO_VIDEO_MODELS, AABAO_STYLE_IDS, AABAO_API_PROVIDERS


class AabaoStoryboard(AabaoBaseNode):
    """Aabao 分镜模式节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (AABAO_API_PROVIDERS, {"default": "aabao"}),
                "api_key": ("STRING", {"default": "", "placeholder": "留空使用config.json配置"}),
                "scenes": ("STRING", {
                    "multiline": True,
                    "default": "[5.0s]开场：城市全景\n[4.0s]转场：街道人群\n[6.0s]特写：主角微笑",
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
    
    def generate(self, api_provider: str, api_key: str, scenes: str, model: str, 
                 style_id: str, seed: int = 0) -> Tuple[Any, List[str], str, str, str]:
        
        if not scenes.strip():
            return (None, [], "", "请输入分镜场景", scenes)
        
        payload = {"model": model, "prompt": scenes}
        
        if style_id != "无":
            payload["style_id"] = style_id
        if seed > 0:
            payload["seed"] = seed
        
        pbar = comfy.utils.ProgressBar(100)
        video_url, video_id, message = self._call_videos_api(payload, api_key, pbar)
        
        if not video_url:
            return (None, [], "", f"生成失败: {message}", scenes)
        
        filename = self._generate_filename("aabao_story", "mp4")
        video_path = self._download_video(video_url, filename)
        vhs_filenames = [video_path] if video_path else []
        scene_count = scenes.count("[")
        response_info = f"分镜视频生成成功! {scene_count}个场景, ID: {video_id}"
        
        return (video_path, vhs_filenames, video_url, response_info, scenes)


NODE_CLASS_MAPPINGS = {"AabaoStoryboard": AabaoStoryboard}
NODE_DISPLAY_NAME_MAPPINGS = {"AabaoStoryboard": "Aabao 分镜模式"}
