"""
ComfyUI_Sora - Sora图生视频节点
支持图像输入、运动控制、风格参数等
"""

import json
from typing import Optional, Tuple, Any
import torch
from .sora_base import SoraBaseNode
from .utils import image_to_base64, download_video, tensor2pil, resize_image, get_aspect_ratio_size
from .config import config_manager


class SoraImage2Video(SoraBaseNode):
    """
    Sora图生视频节点
    
    功能：
    - 支持图像生成视频
    - 支持运动方向控制
    - 支持运动强度控制
    - 支持多种宽高比和质量
    - 支持风格迁移
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "让图像动起来",
                    "placeholder": "描述图像中的运动和变化..."
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
                    "default": "5s",
                    "tooltip": "视频时长，15s需要使用15s模型，25s仅支持sora-2-pro模型"
                }),
                "hd": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "⚠️ HD高清模式仅 sora-2-pro 模型支持，不能与25s同时使用"
                }),
            },
            "optional": {
                "api_provider": (["t8", "t8-us", "t8-hk", "comfly", "comfly-us", "comfly-hk", "aabao"], {
                    "default": "t8",
                    "tooltip": "选择API提供商：T8、T8-US、T8-HK、Comfly、Comfly-US、Comfly-HK 或 Aabao (newapi.ai)"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "留空则使用配置文件中的API Key"
                }),
                "model": ([
                    "sora_video2",
                    "sora-2-pro",
                    "sora-2",
                    "[Aabao] sora-2-landscape",
                    "[Aabao] sora-2-landscape-15s",
                    "[Aabao] sora-2-portrait",
                    "[Aabao] sora-2-portrait-15s",
                    "[Aabao] sora-2-15s",
                ], {
                    "default": "sora_video2"
                }),
                "motion_direction": ([
                    "auto",       # 自动
                    "forward",    # 向前
                    "backward",   # 向后
                    "left",       # 向左
                    "right",      # 向右
                    "up",         # 向上
                    "down",       # 向下
                    "zoom_in",    # 放大
                    "zoom_out",   # 缩小
                    "rotate_cw",  # 顺时针旋转
                    "rotate_ccw", # 逆时针旋转
                ], {
                    "default": "auto"
                }),
                "motion_intensity": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1
                }),
                "style": ([
                    "keep_original",  # 保持原样
                    "cinematic",      # 电影感
                    "realistic",      # 写实
                    "anime",          # 动漫
                    "3d",             # 3D
                    "oil_painting",   # 油画
                    "watercolor",     # 水彩
                ], {
                    "default": "keep_original"
                }),
                "resize_mode": ([
                    "cover",    # 裁剪填充
                    "contain",  # 完整显示
                    "stretch",  # 拉伸
                ], {
                    "default": "cover"
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
    """

    def generate_video(
        self,
        image: torch.Tensor,
        prompt: str,
        aspect_ratio: str,
        quality: str,
        duration: str,
        hd: bool = False,
        api_provider: str = "t8",
        api_key: str = "",
        model: str = "sora-2",
        motion_direction: str = "auto",
        motion_intensity: float = 0.5,
        style: str = "keep_original",
        resize_mode: str = "cover",
        seed: int = -1,
        output_dir: str = "sora_videos",
    ) -> Tuple[Any, str, str, str]:
        """
        从图像生成视频

        Args:
            image: 输入图像（ComfyUI张量）
            prompt: 运动描述提示词
            aspect_ratio: 宽高比
            quality: 质量级别
            duration: 视频时长（"5s", "10s", "15s", "25s (Pro)"）
            hd: HD高清模式（仅sora-2-pro支持，不能与25s同时使用）
            api_provider: API提供商
            api_key: API密钥
            model: 模型名称
            motion_direction: 运动方向
            motion_intensity: 运动强度
            style: 风格
            resize_mode: 调整模式
            seed: 随机种子
            output_dir: 输出目录

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
            elif api_provider == 't8-us':
                config_manager.set_t8_us_api_key(api_key)
            elif api_provider == 't8-hk':
                config_manager.set_t8_hk_api_key(api_key)
            elif api_provider == 'comfly-us':
                config_manager.set_comfly_us_api_key(api_key)
            elif api_provider == 'comfly-hk':
                config_manager.set_comfly_hk_api_key(api_key)
            else:
                config_manager.set_api_key(api_key)

        # 验证API密钥
        if not api_config['api_key']:
            error_msg = f"错误：未配置{api_provider.upper()} API Key，请在节点参数中设置或在配置文件中配置"
            print(f"[Sora Image2Video] {error_msg}")
            # 返回空字符串作为VIDEO路径（ComfyUI的VIDEO类型就是字符串路径）
            return ("", "", error_msg, prompt)

        # 验证HD和25s不能同时使用
        if hd and duration_int == 25:
            error_msg = "❌ 错误：HD模式和25秒时长不能同时使用，请选择其中一个"
            print(f"[Sora Image2Video] {error_msg}")
            return ("", "", error_msg, prompt)

        # 验证HD模式只支持特定模型
        if hd and model not in ["sora-2-pro", "sora-2"]:
            warning_msg = f"⚠️ 警告：HD模式仅支持 sora-2-pro 和 sora-2 模型，当前模型: {model}"
            print(f"[Sora Image2Video] {warning_msg}")
            print(f"[Sora Image2Video] 💡 建议：请将模型切换为 sora-2-pro 或 sora-2")

        # 验证25s时长只能用于sora-2-pro模型
        if duration_int == 25 and model != "sora-2-pro":
            warning_msg = f"⚠️ 警告：25秒时长仅支持 sora-2-pro 模型，当前模型: {model}"
            print(f"[Sora Image2Video] {warning_msg}")
            print(f"[Sora Image2Video] 💡 建议：请将模型切换为 sora-2-pro 或选择其他时长")

        # 处理图像
        try:
            # 转换为PIL图像
            pil_image = tensor2pil(image)[0]
            
            # 调整图像尺寸
            target_size = get_aspect_ratio_size(aspect_ratio, quality)
            resized_image = resize_image(pil_image, target_size, resize_mode)
            
            # 转换为base64
            image_base64 = image_to_base64(resized_image, "PNG")
            
            print(f"[Sora Image2Video] 图像处理完成: {resized_image.size}")
            
        except Exception as e:
            error_msg = f"图像处理失败: {e}"
            print(f"[Sora Image2Video] {error_msg}")
            return (None, "", error_msg, prompt)
        
        # 构建完整提示词
        full_prompt = self._build_full_prompt(
            prompt, aspect_ratio, quality, motion_direction, motion_intensity, style, duration_int
        )

        print(f"[Sora Image2Video] 开始生成视频")
        print(f"[Sora Image2Video] API提供商: {api_provider}")
        print(f"[Sora Image2Video] 模型: {model}")
        print(f"[Sora Image2Video] 宽高比: {aspect_ratio}, 质量: {quality}, 时长: {duration_int}秒")
        print(f"[Sora Image2Video] HD模式: {'✅ 开启' if hd else '❌ 关闭'}")
        print(f"[Sora Image2Video] 运动: {motion_direction}, 强度: {motion_intensity}")
        print(f"[Sora Image2Video] 🔍 完整提示词: {full_prompt}")

        # 创建进度条实例（参考ComfyUI_SongBloom的实现）
        try:
            from comfy.utils import ProgressBar
            pbar = ProgressBar(100)  # 总进度100%
        except Exception:
            pbar = None

        # 构建API请求（多模态格式）
        content = [
            {"type": "text", "text": full_prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": image_base64,
                    "detail": "high"
                }
            }
        ]

        messages = [{"role": "user", "content": content}]

        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }

        # 添加种子
        if seed >= 0:
            payload["seed"] = seed

        # 添加HD参数（所有支持的模型都使用 hd 参数，由API自己判定）
        if hd:
            payload["hd"] = True

        # 为所有提供商添加视频参数（T8、Comfly、Aabao 都需要）
        # 获取分辨率
        width, height = get_aspect_ratio_size(aspect_ratio, quality)
        payload["size"] = f"{width}x{height}"
        payload["seconds"] = str(duration_int)
        # 添加图片参考（base64编码）
        payload["input_reference"] = image_base64

        # 调用API（传递进度条实例）
        response_content, video_url, tokens, all_urls = self._call_api(
            payload,
            api_key=api_config['api_key'],
            api_provider=api_provider,
            base_url=api_config['base_url'],
            pbar=pbar
        )

        # 检查是否成功
        if not video_url:
            error_msg = f"生成失败: {response_content}"
            print(f"[Sora Image2Video] {error_msg}")
            raise RuntimeError(error_msg)

        # 下载视频（传入所有候选URL以支持fallback）
        try:
            # 构建元数据
            metadata = {
                "prompt": full_prompt,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "quality": quality,
                "duration": duration_int,
                "motion_direction": motion_direction,
                "motion_intensity": motion_intensity,
                "style": style,
                "seed": seed,
            }

            video_output = self._download_video(video_url, all_urls, output_dir=output_dir, metadata=metadata)
            if not video_output:
                error_msg = "视频下载失败"
                print(f"[Sora Image2Video] {error_msg}")
                raise RuntimeError(error_msg)

            # 提取视频路径
            print(f"[Sora DEBUG] video_output类型: {type(video_output)}")
            print(f"[Sora DEBUG] video_output内容: {video_output}")

            if isinstance(video_output, str):
                # 如果返回的是字符串路径
                video_path = video_output
                print(f"[Sora DEBUG] 情况1: 字符串路径")
            elif hasattr(video_output, 'saved_path'):
                # 优先使用saved_path属性（这是我们在sora_base.py中设置的）
                video_path = video_output.saved_path
                print(f"[Sora DEBUG] 情况2: 使用saved_path属性，path={video_path}")
            elif hasattr(video_output, 'path'):
                # 如果是VideoFromFile对象
                video_path = video_output.path
                print(f"[Sora DEBUG] 情况3: VideoFromFile对象，path={video_path}")
            else:
                # 其他情况，尝试转换为字符串
                video_path = str(video_output)
                print(f"[Sora DEBUG] 情况4: 转换为字符串")

            print(f"[Sora DEBUG] 最终video_path: {video_path}")
            print(f"[Sora DEBUG] video_path类型: {type(video_path)}")

            # 构建VHS_FILENAMES格式输出
            # VHS_FILENAMES = (save_output: bool, file_paths: list)
            # save_output=True表示文件已保存到output目录
            vhs_filenames = (True, [video_path])
            print(f"[Sora DEBUG] vhs_filenames: {vhs_filenames}")

            # 构建响应信息
            response_info = {
                "status": "success",
                "model": model,
                "aspect_ratio": aspect_ratio,
                "quality": quality,
                "duration": duration_int,
                "motion_direction": motion_direction,
                "motion_intensity": motion_intensity,
                "style": style,
                "seed": seed if seed >= 0 else "auto",
                "video_url": video_url,
                "video_path": video_path,
                "tokens": tokens
            }

            response_str = json.dumps(response_info, ensure_ascii=False, indent=2)

            # 返回：VIDEO对象, VHS_FILENAMES, video_url, response_info, prompt_used
            return (video_output, vhs_filenames, video_url, response_str, full_prompt)
            
        except Exception as e:
            error_msg = f"视频处理失败: {e}"
            print(f"[Sora Image2Video] {error_msg}")
            import traceback
            traceback.print_exc()
            raise
    
    def _build_full_prompt(
        self,
        prompt: str,
        aspect_ratio: str,
        quality: str,
        motion_direction: str,
        motion_intensity: float,
        style: str,
        duration: int
    ) -> str:
        """
        构建完整提示词

        Sora API不接受单独的参数，所有设置都需要写在提示词中
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
            "1080p": "全高清1080p"
        }
        if quality in quality_desc:
            parts.append(quality_desc[quality])

        # 添加运动方向描述
        if motion_direction != "auto":
            motion_descriptions = {
                "forward": "镜头向前推进",
                "backward": "镜头向后拉远",
                "left": "镜头向左平移",
                "right": "镜头向右平移",
                "up": "镜头向上移动",
                "down": "镜头向下移动",
                "zoom_in": "镜头逐渐放大",
                "zoom_out": "镜头逐渐缩小",
                "rotate_cw": "镜头顺时针旋转",
                "rotate_ccw": "镜头逆时针旋转",
            }
            if motion_direction in motion_descriptions:
                parts.append(motion_descriptions[motion_direction])

        # 添加运动强度
        if motion_intensity < 0.3:
            parts.append("缓慢平稳")
        elif motion_intensity > 0.7:
            parts.append("快速动态")

        # 添加时长
        parts.append(f"{duration}秒视频")

        return "，".join(parts)


# 节点显示名称
NODE_DISPLAY_NAME = "Sora 图生视频"
