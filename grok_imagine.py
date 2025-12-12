"""
ComfyUI_Sora - Grok Imagine 视频生成节点
通过 Aabao API 调用 xAI 的 Grok Imagine 0.9 模型生成视频
仅支持图像生成视频（Image-to-Video）模式
"""

import json
import base64
import os
import shutil
import time
import requests
from io import BytesIO
from typing import Tuple, Optional, Any
import torch
import folder_paths
from .grok_config import grok_config_manager
from .utils import tensor2pil, download_video
import comfy.utils


class GrokImagineNode:
    """Grok Imagine 视频生成节点 - 仅支持图像生成视频（Image-to-Video）"""

    def __init__(self):
        """初始化 Grok Imagine 节点 - 使用独立的 grok-config.json"""
        # 从 grok-config.json 读取配置
        self.api_key = grok_config_manager.get_api_key()
        self.base_url = grok_config_manager.get_base_url()
        self.timeout = grok_config_manager.get_timeout()

        # 设置代理
        proxy_url = grok_config_manager.get_proxy_url()
        self.proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None

        # 打印配置信息（首次加载时）
        if not hasattr(GrokImagineNode, '_config_printed'):
            grok_config_manager.print_config()
            GrokImagineNode._config_printed = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),  # 图像是必需的（仅支持图生视频）
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "camera slowly pulls back to reveal context, studio lighting with soft shadows",
                    "placeholder": "描述动作、镜头运动、视觉风格等（遵循六组分公式）..."
                }),
                "duration": (["6", "7", "8", "9", "10", "11", "12", "13", "14", "15"], {
                    "default": "10",
                    "tooltip": "视频时长（秒），支持 6-15 秒"
                }),
                "model": (["grok-imagine-0.9"], {
                    "default": "grok-imagine-0.9",
                    "tooltip": "Grok Imagine 模型（仅支持图生视频）"
                }),
                "quality": (["standard", "high"], {
                    "default": "high",
                    "tooltip": "视频质量"
                }),
                "style": (["normal", "fun", "spicy", "custom"], {
                    "default": "normal",
                    "tooltip": "视频风格"
                }),
            },
            "optional": {
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "留空则使用配置文件中的API Key"
                }),
                "seed": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 2147483647,
                    "tooltip": "随机种子，-1为随机"
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
        image: torch.Tensor,
        prompt: str,
        duration: str,
        model: str,
        quality: str,
        style: str,
        api_key: str = "",
        seed: int = -1
    ) -> Tuple[Any, str, str, str, str]:
        """
        生成视频（仅支持图生视频）

        Args:
            image: 输入图像（必需）
            prompt: 视频动作描述提示词
            duration: 视频时长（5/10/15秒）
            model: 模型名称
            quality: 视频质量（standard/high）
            style: 视频风格（normal/fun/spicy/custom）
            api_key: API密钥
            seed: 随机种子

        Returns:
            Tuple[Any, str, str, str, str]: (视频路径, Filenames, 视频URL, 响应信息, 提示词)
        """
        # Grok Imagine 仅支持图生视频
        mode = "image-to-video"

        print(f"[Grok Imagine] 开始生成视频")
        print(f"[Grok Imagine] 模式: {mode} (仅支持图生视频)")
        print(f"[Grok Imagine] 模型: {model}")
        print(f"[Grok Imagine] 提示词: {prompt}")
        print(f"[Grok Imagine] 时长: {duration}秒, 质量: {quality}, 风格: {style}")

        # 使用传入的 API Key 或配置文件中的 api_key
        use_api_key = api_key if api_key else self.api_key
        if not use_api_key:
            error_msg = "❌ 错误：未提供 API Key，请在节点参数或 grok-config.json 中配置"
            print(f"[Grok Imagine] {error_msg}")
            print(f"[Grok Imagine] 💡 提示：编辑 grok-config.json 文件，设置 api_key 字段")
            return ("", "", "", error_msg, prompt)

        # 使用 aabao 的 base_url
        use_base_url = self.base_url
        print(f"[Grok Imagine] API Base URL: {use_base_url}")
        print(f"[Grok Imagine] API Key: {use_api_key[:20]}...")

        # 构建请求
        try:
            # 构建增强的提示词
            # 根据 Grok Imagine 六组分公式：
            # [Subject] + [Action/Motion] + [Camera Movement] + [Visual Style] + [Duration] + [Audio Direction]
            # 注意：Duration 作为独立的 API 参数传递，不需要添加到提示词中

            enhanced_prompt = prompt

            # 如果有额外的风格要求，添加到提示词中（符合 Visual Style 部分）
            if style == "fun":
                enhanced_prompt += ", playful and energetic style"
            elif style == "spicy":
                enhanced_prompt += ", dramatic and intense style"
            elif style == "custom":
                enhanced_prompt += ", artistic and creative style"

            # quality 和 duration 参数通过 API 参数传递，不需要显式添加到提示词中

            # 构建用户消息内容（多模态格式）
            user_content = []

            # 添加图像（图像在前）
            # 2K 及以下保持原始质量，超过 2K 才压缩
            image_base64 = self._image_to_base64(image, max_size=2048)

            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}"
                }
            })

            # 添加文本提示词
            user_content.append({
                "type": "text",
                "text": enhanced_prompt
            })

            # 构建请求体（使用 Chat Completions API 格式）
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                # 添加 duration 作为独立参数
                "duration": int(duration)
            }

            # 添加种子（如果指定）
            if seed >= 0:
                payload["seed"] = seed

            # 构建 API 端点（使用 Chat Completions API）
            api_endpoint = f"{use_base_url}/chat/completions"

            print(f"[Grok Imagine] 发送请求到 Aabao API...")
            print(f"[Grok Imagine] 完整端点: {api_endpoint}")
            print(f"[Grok Imagine] 模型: {model}")
            print(f"[Grok Imagine] 提示词: {enhanced_prompt}")
            print(f"[Grok Imagine] Duration 参数: {duration} 秒")
            if seed >= 0:
                print(f"[Grok Imagine] 种子: {seed}")

            # 创建进度条
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            # 构建请求头（使用传入的 API Key）
            headers = {
                "Authorization": f"Bearer {use_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # 发送请求
            response = requests.post(
                api_endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout,
                proxies=self.proxies,
                verify=False
            )

            pbar.update_absolute(30)

            if response.status_code != 200:
                error_text = response.text
                print(f"[Grok Imagine] ❌ API 错误: {response.status_code}")
                print(f"[Grok Imagine] 响应内容: {error_text}")

                # 尝试解析错误信息
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        error_detail = error_json["error"]
                        error_msg = f"❌ API 错误 ({response.status_code})\n"
                        error_msg += f"类型: {error_detail.get('type', 'unknown')}\n"
                        error_msg += f"代码: {error_detail.get('code', 'unknown')}\n"
                        error_msg += f"消息: {error_detail.get('message', error_text)}"
                    else:
                        error_msg = f"❌ API 错误: {response.status_code} - {error_text}"
                except:
                    error_msg = f"❌ API 错误: {response.status_code} - {error_text}"

                print(f"[Grok Imagine] {error_msg}")
                return ("", "", "", error_msg, prompt)

            # 解析响应
            result = response.json()
            print(f"[Grok Imagine] 收到响应")
            print(f"[Grok Imagine] 响应结构: {json.dumps({k: type(v).__name__ for k, v in result.items()}, ensure_ascii=False)}")

            # 打印完整的消息内容用于调试
            if "choices" in result and len(result["choices"]) > 0:
                full_content = result["choices"][0].get("message", {}).get("content", "")
                print(f"[Grok Imagine] 完整消息内容:\n{full_content}")

            # 从 Chat Completions API 响应中提取视频 URL
            video_url = self._extract_video_url_from_chat_response(result)

            if not video_url:
                error_msg = f"❌ 错误：无法从响应中提取视频 URL\n完整响应: {json.dumps(result, indent=2, ensure_ascii=False)}"
                print(f"[Grok Imagine] {error_msg}")
                return ("", "", "", error_msg, prompt)

            print(f"[Grok Imagine] 媒体 URL: {video_url}")

            # 检查 URL 类型（图片还是视频）
            url_lower = video_url.lower()
            is_image = any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])
            is_video = any(ext in url_lower for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv'])

            if is_image:
                print(f"[Grok Imagine] ⚠️ 警告：API 返回的是图片 URL，不是视频")
                print(f"[Grok Imagine] 💡 提示：grok-imagine-0.9 可能只支持图片生成")
                print(f"[Grok Imagine] 💡 建议：检查 Aabao API 文档，确认是否有专门的视频生成模型")
                error_msg = f"⚠️ API 返回图片而非视频\n图片 URL: {video_url}\n\n可能原因：\n1. grok-imagine-0.9 是图片生成模型\n2. 需要使用不同的模型名称（如 grok-video）\n3. 需要特殊参数启用视频生成\n\n请检查 Aabao API 文档"
                return ("", "", video_url, error_msg, prompt)

            pbar.update_absolute(50)

            # 步骤1：先下载到临时目录
            print(f"[Grok Imagine] 开始下载视频...")
            temp_video_path = download_video(video_url)

            if not temp_video_path:
                error_msg = f"❌ 错误：视频下载失败"
                print(f"[Grok Imagine] {error_msg}")
                return ("", "", video_url, error_msg, prompt)

            print(f"[Grok Imagine] ✅ 视频下载成功: {temp_video_path}")

            pbar.update_absolute(70)

            # 步骤2：复制到 output 目录
            try:
                base_output_dir = folder_paths.get_output_directory()
                grok_output_dir = os.path.join(base_output_dir, "grok_videos")
                os.makedirs(grok_output_dir, exist_ok=True)

                # 生成唯一文件名
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                random_suffix = os.urandom(4).hex()
                filename = f"grok_{timestamp}_{random_suffix}.mp4"
                final_path = os.path.join(grok_output_dir, filename)

                print(f"[Grok Imagine] 复制视频到 output 目录...")
                shutil.copy2(temp_video_path, final_path)
                print(f"[Grok Imagine] ✅ 视频已保存: {final_path}")

                video_path = final_path
            except Exception as e:
                print(f"[Grok Imagine] ⚠️ 复制到 output 目录失败: {e}")
                print(f"[Grok Imagine] 使用临时路径: {temp_video_path}")
                video_path = temp_video_path

            pbar.update_absolute(100)

            # 构建响应信息
            response_info = self._build_response_info(result, video_url, duration, quality, style, mode, model)

            print(f"[Grok Imagine] ✅ 视频生成成功")
            print(f"[Grok Imagine] 视频路径: {video_path}")

            # 返回格式与 Sora 节点一致
            return (video_path, [video_path], video_url, response_info, prompt)

        except requests.exceptions.Timeout:
            error_msg = f"❌ 错误：请求超时（{self.timeout}秒）"
            print(f"[Grok Imagine] {error_msg}")
            return ("", "", "", error_msg, prompt)
        except Exception as e:
            error_msg = f"❌ 错误：{str(e)}"
            print(f"[Grok Imagine] {error_msg}")
            import traceback
            traceback.print_exc()
            return ("", "", "", error_msg, prompt)

    def _image_to_base64(self, image_tensor: torch.Tensor, max_size: int = 2048) -> str:
        """
        将 ComfyUI 图像张量转换为 base64 字符串

        Args:
            image_tensor: 输入图像张量
            max_size: 最大边长（像素），默认 2048（2K）

        Returns:
            base64 编码的图像字符串
        """
        from PIL import Image

        pil_image = tensor2pil(image_tensor)[0]

        # 获取原始尺寸
        original_width, original_height = pil_image.size
        max_edge = max(original_width, original_height)
        print(f"[Grok Imagine] 原始图像尺寸: {original_width}x{original_height}")

        # 只对超过 2K 的图像进行缩放
        if max_edge > max_size:
            # 计算缩放比例
            scale = max_size / max_edge
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)

            print(f"[Grok Imagine] ⚠️ 图像超过 2K，缩放到: {new_width}x{new_height} (缩放比例: {scale:.2f})")
            pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        else:
            print(f"[Grok Imagine] ✅ 图像在 2K 以内，保持原始尺寸")

        # 转换为 PNG 格式（保持最佳质量）
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 打印 base64 大小
        base64_size = len(base64_str)
        print(f"[Grok Imagine] Base64 大小: {base64_size:,} 字符 ({base64_size/1024:.1f} KB)")

        return base64_str

    def _extract_video_url_from_chat_response(self, result: dict) -> str:
        """从 Chat Completions API 响应中提取视频 URL"""
        try:
            # Chat API 响应格式:
            # {
            #   "choices": [
            #     {
            #       "message": {
            #         "content": "视频URL或包含URL的文本"
            #       }
            #     }
            #   ]
            # }

            # 尝试从 choices[0].message.content 中提取
            if "choices" in result and len(result["choices"]) > 0:
                message = result["choices"][0].get("message", {})
                content = message.get("content", "")

                # 尝试解析 JSON 格式的内容
                if content.strip().startswith("{"):
                    try:
                        content_json = json.loads(content)
                        # 尝试多种可能的字段名
                        for key in ["video_url", "url", "video", "output_url", "result_url"]:
                            if key in content_json:
                                return self._clean_url(content_json[key])
                    except json.JSONDecodeError:
                        pass

                # 尝试从文本中提取 URL（使用正则表达式）
                import re
                # 更精确的 URL 匹配模式，排除末尾的括号等字符
                url_pattern = r'https?://[^\s<>"{}|\\^`\[\]\(\)]+'
                urls = re.findall(url_pattern, content)

                if urls:
                    print(f"[Grok Imagine] 找到 {len(urls)} 个 URL:")
                    for i, url in enumerate(urls):
                        print(f"  [{i+1}] {url}")

                    # 优先查找视频文件 URL
                    video_extensions = ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv']
                    for url in urls:
                        url_lower = url.lower()
                        if any(ext in url_lower for ext in video_extensions):
                            cleaned_url = self._clean_url(url)
                            print(f"[Grok Imagine] ✅ 找到视频文件: {cleaned_url}")
                            return cleaned_url

                    # 查找包含 video 关键词的 URL
                    for url in urls:
                        if 'video' in url.lower():
                            cleaned_url = self._clean_url(url)
                            print(f"[Grok Imagine] ✅ 找到视频 URL (关键词): {cleaned_url}")
                            return cleaned_url

                    # 如果都不是视频，返回第一个 URL（可能是图片或其他）
                    cleaned_url = self._clean_url(urls[0])
                    print(f"[Grok Imagine] ⚠️ 未找到明确的视频 URL，使用第一个 URL: {cleaned_url}")
                    return cleaned_url

                # 如果内容本身就是一个 URL
                if content.startswith("http://") or content.startswith("https://"):
                    return self._clean_url(content.strip())

            # 尝试直接从响应中获取（某些 API 可能直接返回）
            for key in ["video_url", "url", "video", "output_url", "result_url"]:
                if key in result:
                    return self._clean_url(result[key])

            return ""

        except Exception as e:
            print(f"[Grok Imagine] 提取视频 URL 时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return ""

    def _clean_url(self, url: str) -> str:
        """清理 URL，移除末尾的括号、引号等无效字符"""
        url = url.strip()
        # 移除末尾的括号、引号、逗号等
        while url and url[-1] in ')\'",.;:':
            url = url[:-1]
        return url

    def _build_response_info(self, result: dict, video_url: str, duration: str, quality: str, style: str, mode: str, model: str) -> str:
        """构建响应信息"""
        info_parts = [
            "=== Grok Imagine 视频生成结果 ===",
            f"模型: {model}",
            f"模式: {mode} (仅支持图生视频)",
            f"时长: {duration}秒",
            f"质量: {quality}",
            f"风格: {style}",
            f"视频 URL: {video_url}",
            ""
        ]

        # 添加其他响应信息
        if "id" in result:
            info_parts.append(f"任务 ID: {result['id']}")

        if "created" in result:
            info_parts.append(f"创建时间: {result['created']}")

        return "\n".join(info_parts)


# 节点映射
NODE_CLASS_MAPPINGS = {
    "GrokImagineNode": GrokImagineNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokImagineNode": "🎬 Grok Imagine 视频生成"
}

