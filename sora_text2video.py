"""
ComfyUI_Sora - Sora文生视频节点
支持多种分辨率、横竖版、质量参数等
"""

import os
import folder_paths
from typing import Optional, Tuple, Any
from .sora_base import SoraBaseNode
from .utils import download_video, get_aspect_ratio_size
from .config import config_manager


class SoraText2Video(SoraBaseNode):
    """
    Sora文生视频节点
    
    功能：
    - 支持文本生成视频
    - 支持多种宽高比（16:9横版、9:16竖版、1:1方形等）
    - 支持多种质量级别（720p、1080p、2K、4K）
    - 支持时长控制
    - 支持风格参数
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "一只可爱的小猫在阳光下玩耍",
                    "placeholder": "描述您想要生成的视频内容..."
                }),
                "aspect_ratio": ([
                    "16:9",   # 横屏
                    "9:16",   # 竖屏
                ], {
                    "default": "16:9",
                    "tooltip": "横屏(16:9)适合YouTube/B站，竖屏(9:16)适合抖音/快手"
                }),
                "quality": ([
                    "720p",   # 高清
                    "1080p",  # 全高清
                    "2k",     # 2K
                    "4k",     # 4K超高清
                ], {
                    "default": "1080p"
                }),
                "duration": (["5s", "10s", "15s", "25s (Pro)"], {
                    "default": "5s",
                    "tooltip": "视频时长，15s需要使用15s模型，25s仅支持sora-2-pro模型"
                }),
            },
            "optional": {
                "api_provider": (["t8", "comfly", "aabao"], {
                    "default": "t8",
                    "tooltip": "选择API提供商：T8、Comfly 或 Aabao (newapi.ai)"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "留空则使用配置文件中的API Key"
                }),
                "model": ([
                    "sora_video2",
                    "sora_video2-portrait-hd",
                    "sora_video2-landscape-hd",
                    "sora-2-pro",
                    "sora-2",
                    "sora-1.5",
                    "sora-1",
                    "[Aabao] sora-2-landscape",
                    "[Aabao] sora-2-landscape-15s",
                    "[Aabao] sora-2-portrait",
                    "[Aabao] sora-2-portrait-15s",
                    "[Aabao] sora-2-15s",
                ], {
                    "default": "sora_video2"
                }),
                "style": ([
                    "auto",           # 自动
                    "cinematic",      # 电影感
                    "realistic",      # 写实
                    "anime",          # 动漫
                    "3d",             # 3D渲染
                    "oil_painting",   # 油画
                    "watercolor",     # 水彩
                ], {
                    "default": "auto"
                }),
                "motion_intensity": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1
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
    
    def generate_video(
        self,
        prompt: str,
        aspect_ratio: str,
        quality: str,
        duration: str,
        api_provider: str = "t8",
        api_key: str = "",
        model: str = "sora-2",
        style: str = "auto",
        motion_intensity: float = 0.5,
        seed: int = -1,
        output_dir: str = "sora_videos",
    ) -> Tuple[Any, str, str, str]:
        """
        生成视频

        Args:
            prompt: 视频描述提示词
            aspect_ratio: 宽高比
            quality: 质量级别
            duration: 视频时长（"5s", "10s", "15s"）
            api_provider: API提供商
            api_key: API密钥
            model: 模型名称
            style: 风格
            motion_intensity: 运动强度
            seed: 随机种子

        Returns:
            Tuple: (视频对象, 视频URL, 响应信息, 使用的提示词)
        """
        # 将duration字符串转换为整数（"5s" -> 5, "25s (Pro)" -> 25）
        import re
        duration_match = re.match(r'(\d+)s', duration)
        duration_int = int(duration_match.group(1)) if duration_match else 5

        # 获取API配置
        api_config = config_manager.get_current_api_config(api_provider)

        # 更新API密钥（如果用户提供了）
        if api_key.strip():
            api_config['api_key'] = api_key
            # 保存到配置
            if api_provider == 'comfly':
                config_manager.set_comfly_api_key(api_key)
            elif api_provider == 'aabao':
                config_manager.set_aabao_api_key(api_key)
            else:
                config_manager.set_api_key(api_key)

        # 验证API密钥
        if not api_config['api_key']:
            error_msg = f"错误：未配置{api_provider.upper()} API Key，请在节点参数中设置或在配置文件中配置"
            print(f"[Sora Text2Video] {error_msg}")
            # 返回空字符串作为VIDEO路径（ComfyUI的VIDEO类型就是字符串路径）
            return ("", "", error_msg, prompt)

        # 验证25s时长只能用于sora-2-pro模型
        if duration_int == 25 and model != "sora-2-pro":
            warning_msg = f"⚠️ 警告：25秒时长仅支持 sora-2-pro 模型，当前模型: {model}"
            print(f"[Sora Text2Video] {warning_msg}")
            print(f"[Sora Text2Video] 💡 建议：请将模型切换为 sora-2-pro 或选择其他时长")

        # 构建完整提示词
        full_prompt = self._build_full_prompt(
            prompt, aspect_ratio, quality, duration_int, style, motion_intensity
        )

        print(f"[Sora Text2Video] 开始生成视频")
        print(f"[Sora Text2Video] API提供商: {api_provider}")
        print(f"[Sora Text2Video] 宽高比: {aspect_ratio}, 质量: {quality}, 时长: {duration_int}秒")
        print(f"[Sora Text2Video] 风格: {style}, 运动强度: {motion_intensity}")
        print(f"[Sora Text2Video] 🔍 完整提示词: {full_prompt}")

        # 创建进度条实例（参考ComfyUI_SongBloom的实现）
        try:
            from comfy.utils import ProgressBar
            pbar = ProgressBar(100)  # 总进度100%
        except Exception:
            pbar = None

        # 构建API请求
        messages = [{"role": "user", "content": full_prompt}]

        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }

        # 添加种子（如果指定）
        if seed >= 0:
            payload["seed"] = seed

        # 为 aabao 提供商添加视频参数
        if api_provider == 'aabao':
            # 获取分辨率
            width, height = get_aspect_ratio_size(aspect_ratio, quality)
            payload["size"] = f"{width}x{height}"
            payload["seconds"] = str(duration_int)

        # 调用API（传递进度条实例）
        content, video_url, tokens, all_urls = self._call_api(
            payload,
            api_key=api_config['api_key'],
            api_provider=api_provider,
            base_url=api_config['base_url'],
            pbar=pbar
        )

        # 检查是否成功
        if not video_url:
            error_msg = f"生成失败: {content}"
            print(f"[Sora Text2Video] {error_msg}")
            raise RuntimeError(error_msg)

        # 下载视频（传入所有候选URL以支持fallback）
        try:
            # 构建元数据
            metadata = {
                "prompt": prompt,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "quality": quality,
                "duration": duration_int,
                "style": style,
                "motion_intensity": motion_intensity,
                "seed": seed,
            }

            video_output = self._download_video(video_url, all_urls, output_dir=output_dir, metadata=metadata)
            if not video_output:
                error_msg = "视频下载失败"
                print(f"[Sora Text2Video] {error_msg}")
                raise RuntimeError(error_msg)

            # 提取视频路径
            if isinstance(video_output, str):
                # 如果返回的是字符串路径
                video_path = video_output
            elif hasattr(video_output, 'saved_path'):
                # 优先使用saved_path属性（这是我们在sora_base.py中设置的）
                video_path = video_output.saved_path
            elif hasattr(video_output, 'path'):
                # 如果是VideoFromFile对象
                video_path = video_output.path
            else:
                # 其他情况，尝试转换为字符串
                video_path = str(video_output)

            # 构建VHS_FILENAMES格式输出
            # VHS_FILENAMES = (save_output: bool, file_paths: list)
            # save_output=True表示文件已保存到output目录
            vhs_filenames = (True, [video_path])

            # 构建响应信息
            response_info = {
                "status": "success",
                "model": model,
                "aspect_ratio": aspect_ratio,
                "quality": quality,
                "duration": duration_int,
                "style": style,
                "motion_intensity": motion_intensity,
                "seed": seed if seed >= 0 else "auto",
                "video_url": video_url,
                "video_path": video_path,
                "tokens": tokens
            }

            import json
            response_str = json.dumps(response_info, ensure_ascii=False, indent=2)

            # 返回：VIDEO对象, VHS_FILENAMES, video_url, response_info, prompt_used
            return (video_output, vhs_filenames, video_url, response_str, full_prompt)

        except Exception as e:
            error_msg = f"视频处理失败: {e}"
            print(f"[Sora Text2Video] {error_msg}")
            import traceback
            traceback.print_exc()
            raise
    
    def _build_full_prompt(
        self,
        prompt: str,
        aspect_ratio: str,
        quality: str,
        duration: int,
        style: str,
        motion_intensity: float
    ) -> str:
        """
        构建完整的提示词

        Sora API不接受单独的参数，所有设置都需要写在提示词中

        Args:
            prompt: 基础提示词
            aspect_ratio: 宽高比
            quality: 质量
            duration: 时长
            style: 风格
            motion_intensity: 运动强度

        Returns:
            str: 完整提示词
        """
        # 清理用户输入的末尾标点符号
        cleaned_prompt = prompt.strip().rstrip('，,。.！!？?')
        parts = [cleaned_prompt]

        # 添加宽高比描述（严格按照文档格式）
        aspect_ratio_desc = {
            "16:9": "横屏16:9",
            "9:16": "竖屏9:16",
            "1:1": "方形1:1",
            "4:3": "横屏4:3",
            "21:9": "超宽屏21:9"
        }
        if aspect_ratio in aspect_ratio_desc:
            parts.append(aspect_ratio_desc[aspect_ratio])

        # 添加质量描述（严格按照文档格式）
        quality_desc = {
            "720p": "高清720p",
            "1080p": "全高清1080p",
            "2k": "2K分辨率",
            "4k": "4K超高清"
        }
        if quality in quality_desc:
            parts.append(quality_desc[quality])

        # 添加时长
        parts.append(f"{duration}秒视频")

        return "，".join(parts)


# 节点显示名称
NODE_DISPLAY_NAME = "Sora 文生视频"

