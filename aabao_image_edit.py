"""
ComfyUI_Sora - Aabao 图像编辑节点
"""

from typing import Tuple
import torch
from .aabao_base import AabaoBaseNode, AABAO_IMAGE_MODELS, AABAO_IMAGE_SIZES, AABAO_API_PROVIDERS


class AabaoImageEdit(AabaoBaseNode):
    """Aabao 图像编辑节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (AABAO_API_PROVIDERS, {"default": "aabao"}),
                "api_key": ("STRING", {"default": "", "placeholder": "留空使用config.json配置"}),
                "image": ("IMAGE",),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "将这张图片变成油画风格",
                }),
                "model": (AABAO_IMAGE_MODELS, {"default": "sora-image"}),
                "size": (AABAO_IMAGE_SIZES, {"default": "360x360"}),
            },
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")
    FUNCTION = "edit"
    OUTPUT_NODE = True
    
    def edit(self, api_provider: str, api_key: str, image: torch.Tensor, 
             prompt: str, model: str, size: str) -> Tuple[torch.Tensor, str]:
        
        image_base64 = self._image_to_base64(image)
        payload = {"model": model, "image": image_base64, "prompt": prompt, "size": size, "response_format": "url"}
        
        result_url = self._call_images_edits_api(payload, api_key)
        
        if not result_url:
            return (image, "图像编辑失败")
        
        result_tensor = self._load_image_from_url(result_url)
        
        if result_tensor is None:
            return (image, "图像加载失败")
        
        filename = self._generate_filename("aabao_edit", "png")
        self._download_image(result_url, filename)
        
        return (result_tensor, "图像编辑成功")


NODE_CLASS_MAPPINGS = {"AabaoImageEdit": AabaoImageEdit}
NODE_DISPLAY_NAME_MAPPINGS = {"AabaoImageEdit": "Aabao 图像编辑"}
