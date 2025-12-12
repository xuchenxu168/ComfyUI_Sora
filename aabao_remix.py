"""
ComfyUI_Sora - Aabao 视频Remix节点
"""

import comfy.utils
from typing import Tuple, List, Any
from .aabao_base import AabaoBaseNode, AABAO_VIDEO_MODELS, AABAO_API_PROVIDERS


class AabaoRemix(AabaoBaseNode):
    """Aabao 视频Remix节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (AABAO_API_PROVIDERS, {"default": "aabao"}),
                "api_key": ("STRING", {"default": "", "placeholder": "留空使用config.json配置"}),
                "remix_target_id": ("STRING", {
                    "default": "",
                    "placeholder": "Sora分享链接或ID",
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "改成水墨画风格",
                }),
                "model": (AABAO_VIDEO_MODELS, {"default": "sora-2-landscape-15s"}),
            },
        }
    
    RETURN_TYPES = ("VIDEO", "VHS_FILENAMES", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "Filenames", "video_url", "response_info", "prompt_used")
    FUNCTION = "remix"
    OUTPUT_NODE = True
    CATEGORY = "Ken-Chen/sora"
    
    def remix(self, api_provider: str, api_key: str, remix_target_id: str, 
              prompt: str, model: str) -> Tuple[Any, List[str], str, str, str]:
        
        if not remix_target_id:
            return (None, [], "", "请输入Sora视频ID或链接", prompt)
        
        payload = {"model": model, "prompt": prompt, "remix_target_id": remix_target_id}
        
        pbar = comfy.utils.ProgressBar(100)
        video_url, video_id, message = self._call_videos_api(payload, api_key, pbar)
        
        if not video_url:
            return (None, [], "", f"Remix失败: {message}", prompt)
        
        filename = self._generate_filename("aabao_remix", "mp4")
        video_path = self._download_video(video_url, filename)
        vhs_filenames = [video_path] if video_path else []
        response_info = f"Remix成功! ID: {video_id}"
        
        return (video_path, vhs_filenames, video_url, response_info, prompt)


NODE_CLASS_MAPPINGS = {"AabaoRemix": AabaoRemix}
NODE_DISPLAY_NAME_MAPPINGS = {"AabaoRemix": "Aabao 视频Remix"}
