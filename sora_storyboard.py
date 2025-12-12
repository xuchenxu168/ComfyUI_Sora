"""
ComfyUI_Sora - Sora 2 Pro Storyboard 节点
支持多场景故事板视频生成
"""

import json
from typing import Optional, Tuple, Any
import torch
from .sora_base import SoraBaseNode
from .config import config_manager


class SoraStoryboard(SoraBaseNode):
    """
    Sora 2 Pro Storyboard 节点
    
    功能：
    - 支持多场景故事板生成
    - 每个场景独立描述
    - 支持图像参考
    - 支持多种时长（10s、15s、25s）
    - 支持竖屏和横屏格式
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (["kie"], {
                    "default": "kie",
                    "tooltip": "选择API提供商"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "留空则使用配置文件中的API Key"
                }),
                "n_frames": (["10", "15", "25"], {
                    "default": "15",
                    "tooltip": "视频总时长（秒）"
                }),
                "aspect_ratio": (["portrait", "landscape"], {
                    "default": "landscape",
                    "tooltip": "视频宽高比"
                }),
                "scene_count": (["1", "2", "3", "4", "5"], {
                    "default": "2",
                    "tooltip": "场景数量（1-5个）"
                }),
                "scene_1_prompt": ("STRING", {
                    "multiline": True,
                    "default": "A beautiful landscape with mountains and sunset",
                    "placeholder": "描述第一个场景..."
                }),
                "scene_1_duration": ("FLOAT", {
                    "default": 5.0,
                    "min": 0.1,
                    "max": 25.0,
                    "step": 0.01,
                    "tooltip": "第一个场景的时长（秒）"
                }),
                "scene_2_prompt": ("STRING", {
                    "multiline": True,
                    "default": "A serene lake reflecting the sky",
                    "placeholder": "描述第二个场景..."
                }),
                "scene_2_duration": ("FLOAT", {
                    "default": 5.0,
                    "min": 0.1,
                    "max": 25.0,
                    "step": 0.01,
                    "tooltip": "第二个场景的时长（秒）"
                }),
            },
            "optional": {
                "scene_3_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "描述第三个场景..."
                }),
                "scene_3_duration": ("FLOAT", {
                    "default": 5.0,
                    "min": 0.1,
                    "max": 25.0,
                    "step": 0.01,
                    "tooltip": "第三个场景的时长（秒）"
                }),
                "scene_4_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "描述第四个场景..."
                }),
                "scene_4_duration": ("FLOAT", {
                    "default": 5.0,
                    "min": 0.1,
                    "max": 25.0,
                    "step": 0.01,
                    "tooltip": "第四个场景的时长（秒）"
                }),
                "scene_5_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "描述第五个场景..."
                }),
                "scene_5_duration": ("FLOAT", {
                    "default": 5.0,
                    "min": 0.1,
                    "max": 25.0,
                    "step": 0.01,
                    "tooltip": "第五个场景的时长（秒）"
                }),
                "image": ("IMAGE", {
                    "tooltip": "可选的参考图像"
                }),
                "output_dir": ("STRING", {
                    "default": "sora_videos",
                    "placeholder": "自定义保存目录"
                }),
                "seed": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 2147483647,
                    "tooltip": "-1 为随机种子"
                }),
            }
        }
    
    RETURN_TYPES = ("VIDEO", "VHS_FILENAMES", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "Filenames", "video_url", "response_info", "scenes_used")
    OUTPUT_NODE = True
    FUNCTION = "generate_storyboard"
    CATEGORY = "Ken-Chen/sora"
    DESCRIPTION = """
    ⚠️ Sora 2 Pro Storyboard 节点
    • 仅支持 720P 质量
    • 支持 10s、15s、25s 时长
    • 支持多场景故事板生成
    • 每个场景可独立描述
    """

    def generate_storyboard(
        self,
        n_frames: str,
        aspect_ratio: str,
        scene_count: str,
        scene_1_prompt: str,
        scene_2_prompt: str,
        scene_1_duration: float,
        scene_2_duration: float,
        image: Optional[torch.Tensor] = None,
        scene_3_prompt: str = "",
        scene_3_duration: float = 5.0,
        scene_4_prompt: str = "",
        scene_4_duration: float = 5.0,
        scene_5_prompt: str = "",
        scene_5_duration: float = 5.0,
        api_provider: str = "kie",
        api_key: str = "",
        output_dir: str = "sora_videos",
        seed: int = -1,
    ) -> Tuple[Any, str, str, str]:
        """
        生成故事板视频

        参数：
        - n_frames: 视频时长 (10/15/25 秒)
        - aspect_ratio: 宽高比 (portrait/landscape)
        - scene_count: 场景数量 (1-5)
        - scene_*_prompt: 各场景描述
        - image: 可选的参考图像
        - api_provider: API提供商 (kie/t8/comfly/aabao)
        - api_key: API密钥
        - output_dir: 输出目录
        """
        try:
            print("[Sora Storyboard] ========== 开始生成故事板视频 ==========")

            # 获取API配置
            api_config = config_manager.get_current_api_config(api_provider)
            
            # 更新API密钥（如果用户提供了）
            if api_key.strip():
                api_config['api_key'] = api_key
                self.api_key = api_key
            else:
                self.api_key = api_config['api_key']
            
            if api_provider:
                self.api_provider = api_provider
            
            # 验证API密钥
            if not self.api_key:
                error_msg = f"错误：未配置{api_provider.upper()} API Key，请在节点参数中设置或在配置文件中配置"
                print(f"[Sora Storyboard] {error_msg}")
                return ("", "", "", error_msg)

            # 验证参数
            if n_frames not in ["10", "15", "25"]:
                raise ValueError(f"无效的时长: {n_frames}，必须是 10、15 或 25")

            if aspect_ratio not in ["portrait", "landscape"]:
                raise ValueError(f"无效的宽高比: {aspect_ratio}")

            # 构建场景列表
            scenes = []
            scene_prompts = [scene_1_prompt, scene_2_prompt, scene_3_prompt, scene_4_prompt, scene_5_prompt]
            scene_durations = [scene_1_duration, scene_2_duration, scene_3_duration, scene_4_duration, scene_5_duration]

            scene_count_int = int(scene_count)
            total_duration = int(n_frames)

            # 收集用户输入的时长
            user_durations = []
            for i in range(scene_count_int):
                if i < len(scene_prompts) and scene_prompts[i].strip():
                    user_durations.append(scene_durations[i])

            # 验证用户输入的时长总和是否等于选定的总时长
            total_user_duration = sum(user_durations)
            total_user_duration = round(total_user_duration, 2)

            print(f"[Sora Storyboard] 用户输入的时长总和: {total_user_duration}s (期望: {total_duration}s)")

            if abs(total_user_duration - total_duration) > 0.01:
                print(f"[Sora Storyboard] ⚠️ 警告: 用户输入的时长总和 ({total_user_duration}s) 与选定的总时长 ({total_duration}s) 不匹配")
                print(f"[Sora Storyboard] 将自动调整最后一个场景的时长")

                # 自动调整最后一个场景的时长
                if len(user_durations) > 0:
                    adjustment = total_duration - sum(user_durations[:-1])
                    user_durations[-1] = round(adjustment, 2)
                    print(f"[Sora Storyboard] 最后一个场景时长已调整为: {user_durations[-1]}s")

            # 构建场景对象
            for i in range(scene_count_int):
                if i < len(scene_prompts) and scene_prompts[i].strip():
                    # duration 必须是整数或浮点数，不能有过多小数位
                    scene_duration = user_durations[i]

                    scenes.append({
                        "Scene": scene_prompts[i].strip(),
                        "duration": scene_duration
                    })

            if not scenes:
                raise ValueError("至少需要一个场景描述")

            print(f"[Sora Storyboard] 场景数: {len(scenes)}")
            for i, scene in enumerate(scenes, 1):
                print(f"[Sora Storyboard] 场景 {i}: {scene['Scene'][:50]}... (时长: {scene['duration']}s)")

            # 构建请求数据
            payload = {
                "n_frames": n_frames,
                "aspect_ratio": aspect_ratio,
                "shots": scenes,
            }

            # 验证总时长
            print(f"[Sora Storyboard] 验证参数:")
            print(f"[Sora Storyboard]   n_frames: {n_frames} (类型: {type(n_frames).__name__})")
            print(f"[Sora Storyboard]   场景数: {len(scenes)}")
            # 计算实际总时长
            actual_total_duration = sum(scene['duration'] for scene in scenes)
            print(f"[Sora Storyboard]   所有场景总时长: {actual_total_duration}s")

            # 添加 seed 参数
            if seed >= 0:
                payload["seed"] = seed
                print(f"[Sora Storyboard] 使用种子: {seed}")

            # 如果有参考图像，转换为base64
            # 注意：API 需要真实的 URL，而不是 base64
            # 如果需要支持本地图像，需要先上传到服务器
            if image is not None:
                print("[Sora Storyboard] ⚠️ 参考图像功能需要真实 URL，暂不支持本地图像")
                # from .utils import image_to_base64
                # image_pil = tensor2pil(image)
                # image_base64 = image_to_base64(image_pil)
                # payload["image_urls"] = [image_base64]
                # print("[Sora Storyboard] 参考图像已添加")

            # 调用API
            print("[Sora Storyboard] 调用 API...")
            response_info = self._call_storyboard_api(payload)

            # 处理响应
            if isinstance(response_info, dict):
                status = response_info.get("status", "unknown")

                if status == "success":
                    task_id = response_info.get("task_id", "")
                    print(f"[Sora Storyboard] 任务已创建，Task ID: {task_id}")

                    # 轮询任务状态
                    print("[Sora Storyboard] 开始轮询任务状态...")
                    video_url = self._poll_task_status(task_id)

                    if video_url:
                        print(f"[Sora Storyboard] 生成成功，下载视频: {video_url}")

                        # 构建元数据
                        metadata = {
                            "prompt": "Sora Storyboard",
                            "n_frames": n_frames,
                            "aspect_ratio": aspect_ratio,
                            "scene_count": scene_count,
                        }

                        # 使用 _download_video 方法下载视频（与其他节点一致）
                        video_output = self._download_video(
                            video_url,
                            all_urls=[video_url],
                            output_dir=output_dir,
                            metadata=metadata
                        )

                        if not video_output:
                            error_msg = "视频下载失败"
                            print(f"[Sora Storyboard] ❌ {error_msg}")
                            raise RuntimeError(error_msg)

                        # 提取视频路径用于 VHS_FILENAMES
                        print(f"[Sora Storyboard] video_output 类型: {type(video_output)}")
                        print(f"[Sora Storyboard] video_output 内容: {video_output}")

                        # 调试：打印 video_output 的所有属性
                        if hasattr(video_output, '__dict__'):
                            print(f"[Sora Storyboard] video_output 属性: {video_output.__dict__}")
                        if hasattr(video_output, 'saved_path'):
                            print(f"[Sora Storyboard] video_output.saved_path: {video_output.saved_path}")
                        if hasattr(video_output, 'path'):
                            print(f"[Sora Storyboard] video_output.path: {video_output.path}")

                        if isinstance(video_output, str):
                            # 如果返回的是字符串路径
                            video_path = video_output
                            print(f"[Sora Storyboard] 情况1: 字符串路径")
                        elif hasattr(video_output, 'saved_path'):
                            # 优先使用 saved_path 属性
                            video_path = video_output.saved_path
                            print(f"[Sora Storyboard] 情况2: 使用 saved_path 属性，path={video_path}")
                        elif hasattr(video_output, 'path'):
                            # 如果是 VideoFromFile 对象
                            video_path = video_output.path
                            print(f"[Sora Storyboard] 情况3: VideoFromFile 对象，path={video_path}")
                        else:
                            # 其他情况，尝试转换为字符串
                            video_path = str(video_output)
                            print(f"[Sora Storyboard] 情况4: 转换为字符串")

                        print(f"[Sora Storyboard] 最终 video_path: {video_path}")

                        # 构建 VHS_FILENAMES 格式输出
                        # VHS_FILENAMES = (save_output: bool, file_paths: list)
                        # save_output=True 表示文件已保存到 output 目录
                        vhs_filenames = (True, [video_path])

                        # 构建场景信息字符串（与 sora_image2video 的 prompt_used 对应）
                        scenes_info = json.dumps({
                            "n_frames": n_frames,
                            "aspect_ratio": aspect_ratio,
                            "scene_count": scene_count,
                            "scenes": scenes
                        }, ensure_ascii=False, indent=2)

                        return (
                            video_output,
                            vhs_filenames,
                            video_url,
                            json.dumps(response_info, ensure_ascii=False, indent=2),
                            scenes_info
                        )
                    else:
                        print("[Sora Storyboard] ❌ 任务超时或失败")
                        return (
                            "",
                            ("", []),
                            "",
                            json.dumps({"status": "timeout", "task_id": task_id}, ensure_ascii=False),
                            ""
                        )
                else:
                    error = response_info.get("error", "未知错误")
                    raise RuntimeError(f"API 返回错误: {error}")
            else:
                raise RuntimeError(f"API 返回错误: {response_info}")

        except Exception as e:
            error_msg = f"故事板生成失败: {str(e)}"
            print(f"[Sora Storyboard] ❌ {error_msg}")
            return ("", ("", []), "", error_msg, "")
    
    def _poll_task_status(self, task_id: str, max_wait_seconds: int = 3000) -> Optional[str]:
        """
        轮询任务状态，获取视频 URL

        Args:
            task_id: 任务 ID
            max_wait_seconds: 最大等待时间（秒）

        Returns:
            视频 URL 或 None
        """
        import requests
        import time

        # 使用有效的 KIE API 格式 (其他端点返回404)
        url_formats = [
            f"https://api.kie.ai/api/v1/jobs/recordInfo?taskId={task_id}",
        ]

        url = url_formats[0]  # 默认使用第一个格式
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        start_time = time.time()
        poll_interval = 5  # 每 5 秒轮询一次
        poll_count = 0

        print(f"[Sora Storyboard] 🔄 开始轮询任务状态...")
        print(f"[Sora Storyboard] 轮询 URL: {url}")
        print(f"[Sora Storyboard] 备用 URL 格式:")
        for i, fmt in enumerate(url_formats[1:], 1):
            print(f"[Sora Storyboard]   {i}. {fmt}")
        print(f"[Sora Storyboard] 最大等待时间: {max_wait_seconds}s")

        while time.time() - start_time < max_wait_seconds:
            poll_count += 1
            elapsed = int(time.time() - start_time)
            print(f"[Sora Storyboard] 📡 第 {poll_count} 次轮询 (已等待 {elapsed}s)...")

            # 依次尝试所有URL格式
            success = False
            for i, current_url in enumerate(url_formats):
                print(f"[Sora Storyboard] 尝试URL {i+1}/{len(url_formats)}: {current_url}")

                try:
                    response = requests.get(
                        current_url,
                        headers=headers,
                        timeout=30,
                        proxies=self.proxies,
                        verify=False
                    )

                    print(f"[Sora Storyboard] URL {i+1} 响应状态: {response.status_code}")

                    if response.status_code == 200:
                        try:
                            data = response.json()
                            print(f"[Sora Storyboard] 成功响应: {data}")

                            task_data = data.get('data', {})
                            # 支持两种状态字段格式：state (KIE API) 和 status
                            task_status = task_data.get('state', task_data.get('status', ''))

                            print(f"[Sora Storyboard] 任务状态: {task_status}")

                            if task_status == 'success':
                                # 尝试多种视频URL获取方式
                                video_url = None
                                
                                # 方式1: KIE API格式 - resultJson中的resultUrls
                                result_json = task_data.get('resultJson', '')
                                if result_json:
                                    try:
                                        import json
                                        result_data = json.loads(result_json)
                                        result_urls = result_data.get('resultUrls', [])
                                        if result_urls and len(result_urls) > 0:
                                            video_url = result_urls[0]
                                    except Exception as e:
                                        print(f"[Sora Storyboard] ⚠️ 解析resultJson失败: {e}")
                                
                                # 方式2: 标准格式 - output.video_url
                                if not video_url:
                                    video_url = task_data.get('output', {}).get('video_url', '')
                                
                                # 方式3: 直接从data中获取video_url
                                if not video_url:
                                    video_url = task_data.get('video_url', '')
                                
                                if video_url:
                                    print(f"[Sora Storyboard] ✅ 任务完成，视频 URL: {video_url}")
                                    return video_url
                                else:
                                    print(f"[Sora Storyboard] ⚠️ 任务成功但未找到视频 URL")
                                    print(f"[Sora Storyboard] 完整响应: {data}")
                            elif task_status == 'failed':
                                error_msg = task_data.get('failMsg', task_data.get('error', '未知错误'))
                                print(f"[Sora Storyboard] ❌ 任务失败: {error_msg}")
                                return None
                            elif task_status in ['pending', 'processing', 'running', 'waiting', 'generating']:
                                print(f"[Sora Storyboard] ⏳ 任务处理中，{poll_interval}s 后重试...")
                                success = True
                                break
                            else:
                                print(f"[Sora Storyboard] ⚠️ 未知状态: {task_status}")
                                print(f"[Sora Storyboard] 完整响应: {data}")

                        except Exception as json_e:
                            print(f"[Sora Storyboard] ⚠️ JSON解析失败: {json_e}")
                            print(f"[Sora Storyboard] 原始响应: {response.text[:200]}...")
                            continue

                    elif response.status_code == 404:
                        print(f"[Sora Storyboard] ⚠️ URL {i+1} 返回404，继续尝试下一个")
                        continue
                    else:
                        print(f"[Sora Storyboard] ⚠️ URL {i+1} 返回状态码: {response.status_code}")
                        print(f"[Sora Storyboard] 响应内容: {response.text[:200]}...")
                        continue

                except Exception as e:
                    print(f"[Sora Storyboard] ⚠️ URL {i+1} 请求异常: {e}")
                    continue

            if not success:
                print(f"[Sora Storyboard] ⚠️ 所有URL都失败，{poll_interval}秒后重试")
            
            time.sleep(poll_interval)

        print(f"[Sora Storyboard] ❌ 任务超时 (超过 {max_wait_seconds} 秒，共轮询 {poll_count} 次)")
        return None

    def _call_storyboard_api(self, payload: dict) -> dict:
        """
        调用 Sora 2 Pro Storyboard API
        支持 KIE、T8、Comfly 等多个提供商
        """
        if self.api_provider == "kie":
            return self._call_kie_storyboard_api(payload)
        else:
            # 其他提供商暂不支持
            return {
                "status": "error",
                "error": f"Storyboard 暂不支持 {self.api_provider} 提供商"
            }

    def _call_kie_storyboard_api(self, payload: dict) -> dict:
        """
        调用 KIE Sora 2 Pro Storyboard API
        使用异步任务模式
        """
        import requests

        url = "https://api.kie.ai/api/v1/jobs/createTask"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # 构建 KIE 格式的请求
        # 注意：根据 API 文档，n_frames 应该是字符串类型
        kie_payload = {
            "model": "sora-2-pro-storyboard",
            "input": {
                "n_frames": str(payload.get("n_frames", "15")),
                "aspect_ratio": payload.get("aspect_ratio", "landscape"),
                "shots": payload.get("shots", []),
            }
        }

        # 添加参考图像（如果有）
        # 注意：image_urls 应该是 URL 数组，不是 base64
        if "image_urls" in payload:
            kie_payload["input"]["image_urls"] = payload["image_urls"]

        # 添加种子（如果有）
        if "seed" in payload:
            kie_payload["input"]["seed"] = payload["seed"]

        print(f"[Sora Storyboard] 调用 KIE API: {url}")
        print(f"[Sora Storyboard] 场景数: {len(kie_payload['input'].get('shots', []))}")
        print(f"[Sora Storyboard] 时长: {kie_payload['input'].get('n_frames')}s")
        print(f"[Sora Storyboard] 宽高比: {kie_payload['input'].get('aspect_ratio')}")
        print(f"[Sora Storyboard] 请求载荷: {kie_payload}")

        try:
            response = requests.post(
                url,
                json=kie_payload,
                headers=headers,
                timeout=self.timeout,
                proxies=self.proxies,
                verify=False
            )

            if response.status_code in [200, 201]:
                print(f"[Sora Storyboard] API 响应成功")
                print(f"[Sora Storyboard] 响应状态码: {response.status_code}")
                print(f"[Sora Storyboard] 响应头: {response.headers}")
                print(f"[Sora Storyboard] 响应文本: {response.text}")

                try:
                    data = response.json()
                except Exception as e:
                    print(f"[Sora Storyboard] ⚠️ JSON 解析失败: {e}")
                    print(f"[Sora Storyboard] 原始响应: {response.text}")
                    return {
                        "status": "error",
                        "error": f"JSON 解析失败: {e}"
                    }

                print(f"[Sora Storyboard] 完整响应: {data}")

                # 调试：打印响应结构
                if data is None:
                    print(f"[Sora Storyboard] ⚠️ 响应为 None")
                    return {
                        "status": "error",
                        "error": "API 返回空响应"
                    }

                # 检查响应中的错误码
                # 根据 API 文档：成功时 code=200，失败时返回其他错误码
                if isinstance(data, dict):
                    response_code = data.get('code')
                    
                    # 检查是否成功
                    if response_code == 200:
                        # 成功响应，继续提取 taskId
                        pass
                    elif response_code == 401:
                        error_msg = "错误：API Key 无效或权限不足，请检查API Key配置"
                        print(f"[Sora Storyboard] {error_msg}")
                        return {
                            "status": "error",
                            "error": error_msg
                        }
                    elif response_code == 422:
                        error_msg = data.get('msg', 'Internal error')
                        print(f"[Sora Storyboard] ❌ API返回错误 (422): {error_msg}")
                        print(f"[Sora Storyboard] 💡 可能的原因:")
                        print(f"[Sora Storyboard]   - API Key 配额不足")
                        print(f"[Sora Storyboard]   - 请求参数不符合要求")
                        print(f"[Sora Storyboard]   - 服务暂时不可用")
                        return {
                            "status": "error",
                            "error": f"API错误 (422): {error_msg}"
                        }
                    elif response_code and response_code != 200:
                        error_msg = data.get('msg', f'Unknown error (code: {response_code})')
                        print(f"[Sora Storyboard] ❌ API返回错误 ({response_code}): {error_msg}")
                        return {
                            "status": "error",
                            "error": f"API错误 ({response_code}): {error_msg}"
                        }

                # 提取 taskId
                # 根据 API 文档：成功响应格式为 {"code": 200, "message": "success", "data": {"taskId": "xxx"}}
                task_id = None
                if isinstance(data, dict):
                    # 标准格式: {"data": {"taskId": "xxx"}}
                    if 'data' in data and isinstance(data['data'], dict):
                        task_id = data['data'].get('taskId', '')
                    # 备用格式: {"taskId": "xxx"}
                    elif 'taskId' in data:
                        task_id = data.get('taskId', '')
                    # 备用格式: {"id": "xxx"}
                    elif 'id' in data:
                        task_id = data.get('id', '')

                print(f"[Sora Storyboard] 任务 ID: {task_id}")
                
                # 如果没有获取到task_id，返回错误
                if not task_id:
                    error_msg = "API响应中未找到任务ID"
                    print(f"[Sora Storyboard] ❌ {error_msg}")
                    print(f"[Sora Storyboard] 完整响应: {data}")
                    return {
                        "status": "error",
                        "error": error_msg,
                        "response": data
                    }

                return {
                    "status": "success",
                    "task_id": task_id,
                    "response": data
                }
            else:
                error_msg = f"API 返回状态码 {response.status_code}: {response.text}"
                print(f"[Sora Storyboard] ❌ {error_msg}")
                return {
                    "status": "error",
                    "error": error_msg,
                    "status_code": response.status_code
                }
        except Exception as e:
            error_msg = f"API 调用异常: {str(e)}"
            print(f"[Sora Storyboard] ❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": error_msg
            }


# 节点类映射
NODE_CLASS_MAPPINGS = {
    "SoraStoryboard": SoraStoryboard,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SoraStoryboard": "🎬 Sora 2 Pro Storyboard ⚠️ 仅支持720P",
}

