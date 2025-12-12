"""
ComfyUI_Sora - Aabao 图像生成节点
"""

from typing import Tuple
import torch
from .aabao_base import AabaoBaseNode, AABAO_IMAGE_MODELS, AABAO_IMAGE_SIZES, AABAO_API_PROVIDERS


class AabaoImageGen(AabaoBaseNode):
    """Aabao 图像生成节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (AABAO_API_PROVIDERS, {"default": "aabao"}),
                "api_key": ("STRING", {"default": "", "placeholder": "留空使用config.json配置"}),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "一只可爱的小猫",
                }),
                "model": (AABAO_IMAGE_MODELS, {"default": "sora-image"}),
                "size": (AABAO_IMAGE_SIZES, {"default": "360x360"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 4}),
            },
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "status")
    FUNCTION = "generate"
    OUTPUT_NODE = True
    
    def generate(self, api_provider: str, api_key: str, prompt: str, 
                 model: str, size: str, n: int) -> Tuple[torch.Tensor, str]:
        
        payload = {"model": model, "prompt": prompt, "size": size, "n": n, "response_format": "url"}
        
        urls = self._call_images_generations_api(payload, api_key)
        
        if not urls:
            empty = torch.zeros((1, 64, 64, 3))
            return (empty, "图像生成失败")
        
        images = []
        for i, url in enumerate(urls):
            img_tensor = self._load_image_from_url(url)
            if img_tensor is not None:
                images.append(img_tensor)
                filename = self._generate_filename(f"aabao_img_{i}", "png")
                self._download_image(url, filename)
        
        if not images:
            empty = torch.zeros((1, 64, 64, 3))
            return (empty, "图像加载失败")
        
        result = torch.cat(images, dim=0)
        return (result, f"成功生成 {len(images)} 张图像")


NODE_CLASS_MAPPINGS = {"AabaoImageGen": AabaoImageGen}
NODE_DISPLAY_NAME_MAPPINGS = {"AabaoImageGen": "Aabao 图像生成"}
