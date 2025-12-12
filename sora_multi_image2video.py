"""
ComfyUI_Sora - Sora多图参考视频生成节点
支持最多4张图片输入，用于生成视频
"""

import json
import base64
from io import BytesIO
from typing import Optional, Tuple, Any
import torch
from .sora_base import SoraBaseNode
from .utils import download_video, tensor2pil, resize_image, get_aspect_ratio_size
from .config import config_manager


class SoraMultiImage2Video(SoraBaseNode):
    """
    Sora多图参考视频生成节点
    
    功能：
    - 支持最多4张图片作为参考
    - 支持多种宽高比和质量
    - 支持HD高清模式
    - 支持时长控制
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "根据参考图片生成视频",
                    "placeholder": "描述视频内容和运动..."
                }),
                "aspect_ratio": ([
                    "16:9",   # 横屏
                    "9:16",   # 竖屏
                ], {
                    "default": "16:9",
                    "tooltip": "横屏(16:9)适合YouTube/B站，竖屏(9:16)适合抖音/快手"
                }),
                "quality": ([
                    "720p",
                    "1080p",
                ], {
                    "default": "1080p",
                    "tooltip": "⚠️ 1080p 仅支持 sora-2-pro 模型，其他模型仅支持 720p"
                }),
                "duration": (["5s", "10s", "15s", "25s (Pro)"], {
                    "default": "10s",
                    "tooltip": "视频时长，15s需要使用15s模型，25s仅支持sora-2-pro模型"
                }),
                "hd": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "⚠️ HD高清模式仅 sora-2-pro 模型支持，不能与25s同时使用"
                }),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "api_provider": (["comfly"], {
                    "default": "comfly",
                    "tooltip": "多图参考功能仅Comfly API支持"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "留空则使用配置文件中的API Key"
                }),
                "model": ([
                    "sora-2-pro",
                    "sora-2",
                ], {
                    "default": "sora-2"
                }),
                "seed": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 2147483647
                }),
                "output_dir": ("STRING", {
                    "default": "sora_videos",
                    "placeholder": "自定义保存目录（相对于output目录）"
                }),
            }
        }
    
    RETURN_TYPES = ("VIDEO", "VHS_FILENAMES", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "Filenames", "video_url", "response_info", "prompt_used")
    OUTPUT_NODE = True
    FUNCTION = "generate_video"
    CATEGORY = "Ken-Chen/sora"
    DESCRIPTION = """
    ⚠️ 重要提示：
    • 1080p 质量仅支持 sora-2-pro 模型
    • HD 高清模式仅支持 sora-2-pro 模型
    • 其他模型仅支持 720p 质量
    • 多图参考功能仅 Comfly API 支持
    """

    def image_to_base64(self, image_tensor: torch.Tensor) -> str:
        """
        将ComfyUI图像张量转换为base64字符串（带data URI前缀）
        
        Args:
            image_tensor: ComfyUI图像张量
            
        Returns:
            str: data:image/png;base64,{base64_str} 格式的字符串
        """
        if image_tensor is None:
            return None
        
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{base64_str}"
    
    def generate_video(
        self,
        prompt: str,
        aspect_ratio: str,
        quality: str,
        duration: str,
        hd: bool = False,
        image1: Optional[torch.Tensor] = None,
        image2: Optional[torch.Tensor] = None,
        image3: Optional[torch.Tensor] = None,
        image4: Optional[torch.Tensor] = None,
        api_provider: str = "comfly",
        api_key: str = "",
        model: str = "sora-2",
        seed: int = -1,
        output_dir: str = "sora_videos",
    ) -> Tuple[Any, str, str, str]:
        """
        从多张图片生成视频
        
        Args:
            prompt: 视频描述提示词
            aspect_ratio: 宽高比
            quality: 质量级别
            duration: 视频时长
            hd: HD高清模式
            image1-4: 输入图像（最多4张）
            api_provider: API提供商（仅支持comfly）
            api_key: API密钥
            model: 模型名称
            seed: 随机种子
            output_dir: 输出目录
            
        Returns:
            Tuple: (视频对象, 视频URL, 响应信息, 使用的提示词)
        """
        # 将duration字符串转换为整数
        import re
        duration_match = re.match(r'(\d+)s', duration)
        duration_int = int(duration_match.group(1)) if duration_match else 10
        
        # 验证至少有一张图片
        images = [image1, image2, image3, image4]
        valid_images = [img for img in images if img is not None]
        
        if not valid_images:
            error_msg = "❌ 错误：至少需要提供一张参考图片"
            print(f"[Sora MultiImage2Video] {error_msg}")
            return ("", "", error_msg, prompt)
        
        print(f"[Sora MultiImage2Video] 收到 {len(valid_images)} 张参考图片")
        
        # 强制使用comfly API
        if api_provider != "comfly":
            warning_msg = "⚠️ 警告：多图参考功能仅Comfly API支持，已自动切换到Comfly"
            print(f"[Sora MultiImage2Video] {warning_msg}")
            api_provider = "comfly"
        
        # 获取API配置
        api_config = config_manager.get_current_api_config(api_provider)
        
        # 更新API密钥（如果用户提供了）
        if api_key.strip():
            api_config['api_key'] = api_key
            config_manager.set_comfly_api_key(api_key)
        
        # 验证API密钥
        if not api_config['api_key']:
            error_msg = f"错误：未配置Comfly API Key，请在节点参数中设置或在配置文件中配置"
            print(f"[Sora MultiImage2Video] {error_msg}")
            return ("", "", error_msg, prompt)
        
        # 验证HD和25s不能同时使用
        if hd and duration_int == 25:
            error_msg = "❌ 错误：HD模式和25秒时长不能同时使用，请选择其中一个"
            print(f"[Sora MultiImage2Video] {error_msg}")
            return ("", "", error_msg, prompt)

        # Comfly API 使用 hd 参数，不需要切换模型名称
        # 但仍需验证模型兼容性
        if hd and model not in ["sora-2-pro", "sora-2"]:
            warning_msg = f"⚠️ 警告：HD模式仅支持 sora-2-pro 和 sora-2 模型，当前模型: {model}"
            print(f"[Sora MultiImage2Video] {warning_msg}")
            print(f"[Sora MultiImage2Video] 💡 建议：请将模型切换为 sora-2-pro 或 sora-2")

        # 验证25s时长只能用于sora-2-pro模型
        if duration_int == 25 and model != "sora-2-pro":
            warning_msg = f"⚠️ 警告：25秒时长仅支持 sora-2-pro 模型，当前模型: {model}"
            print(f"[Sora MultiImage2Video] {warning_msg}")
            print(f"[Sora MultiImage2Video] 💡 建议：请将模型切换为 sora-2-pro 或选择其他时长")
        
        # 处理图像 - 转换为base64
        try:
            images_base64 = []
            for idx, img in enumerate(valid_images, 1):
                base64_str = self.image_to_base64(img)
                if base64_str:
                    images_base64.append(base64_str)
                    print(f"[Sora MultiImage2Video] 图片 {idx} 转换完成")
            
            print(f"[Sora MultiImage2Video] 共处理 {len(images_base64)} 张图片")
            
        except Exception as e:
            error_msg = f"图像处理失败: {e}"
            print(f"[Sora MultiImage2Video] {error_msg}")
            return ("", "", error_msg, prompt)
        
        print(f"[Sora MultiImage2Video] 开始生成视频")
        print(f"[Sora MultiImage2Video] API提供商: {api_provider}")
        print(f"[Sora MultiImage2Video] 模型: {model}")
        print(f"[Sora MultiImage2Video] 宽高比: {aspect_ratio}, 质量: {quality}, 时长: {duration_int}秒")
        print(f"[Sora MultiImage2Video] HD模式: {'✅ 开启' if hd else '❌ 关闭'}")
        print(f"[Sora MultiImage2Video] 参考图片数量: {len(images_base64)}")
        print(f"[Sora MultiImage2Video] 🔍 提示词: {prompt}")
        
        # 创建进度条实例
        try:
            from comfy.utils import ProgressBar
            pbar = ProgressBar(100)
        except Exception:
            pbar = None
        
        # 构建Comfly API特定的payload
        # 使用 /v2/videos/generations 端点
        payload = {
            "prompt": prompt,
            "model": model,
            "images": images_base64,  # 图片数组
            "aspect_ratio": aspect_ratio,
            "duration": str(duration_int),
            "hd": hd
        }
        
        # 添加种子
        if seed >= 0:
            payload["seed"] = seed
        
        print(f"[Sora MultiImage2Video] 调用Comfly多图API...")
        
        # 调用API（使用特殊的多图端点）
        response_content, video_url, tokens, all_urls = self._call_comfly_multi_image_api(
            payload,
            api_key=api_config['api_key'],
            pbar=pbar
        )
        
        # 检查是否成功
        if not video_url:
            error_msg = f"生成失败: {response_content}"
            print(f"[Sora MultiImage2Video] {error_msg}")
            raise RuntimeError(error_msg)
        
        print(f"[Sora MultiImage2Video] ✅ 视频生成成功")
        print(f"[Sora MultiImage2Video] 视频URL: {video_url}")
        
        # 下载视频
        try:
            video_path = download_video(video_url, output_dir)
            print(f"[Sora MultiImage2Video] 视频已保存: {video_path}")
        except Exception as e:
            error_msg = f"视频下载失败: {e}"
            print(f"[Sora MultiImage2Video] {error_msg}")
            raise RuntimeError(error_msg)
        
        # 返回结果
        return (video_path, video_path, video_url, response_content, prompt)

