"""
ComfyUI_Sora - Aabao 角色创建节点
修复 v3 - 最终版：
1. 服务器只接受真实的 HTTP/HTTPS URL
2. 不支持文件上传（multipart/form-data）
3. 不支持 Base64 data URI（服务器会尝试 curl 下载导致失败）
4. 用户必须使用外部图床或云存储服务
"""

import os
import requests
import comfy.utils
from typing import Tuple, List, Any, Optional
from .aabao_base import AabaoBaseNode, AABAO_VIDEO_MODELS, AABAO_API_PROVIDERS

class AabaoCharacter(AabaoBaseNode):
    """Aabao 角色创建节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_provider": (AABAO_API_PROVIDERS, {"default": "aabao"}),
                "api_key": ("STRING", {"default": "", "placeholder": "留空使用config.json配置"}),
                "video_url": ("STRING", {"default": "", "placeholder": "⚠️ 必填：视频直链URL（推荐：阿里云OSS/腾讯云COS/七牛云）", "multiline": False}),
                "create_only": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "prompt": ("STRING", {"multiline": True, "default": "", "placeholder": "角色动作描述（create_only=False时需要）"}),
                "model": (AABAO_VIDEO_MODELS, {"default": "sora-2-characters"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "VIDEO", "VHS_FILENAMES", "STRING")
    RETURN_NAMES = ("username", "character_id", "video", "Filenames", "status")
    FUNCTION = "create_character"
    OUTPUT_NODE = True
    CATEGORY = "Ken-Chen/sora"

    def create_character(self, api_provider: str, api_key: str,
                        video_url: str, create_only: bool,
                        prompt: str = "",
                        model: str = "sora-2-characters") -> Tuple[str, str, Any, List[str], str]:
        """创建角色"""

        if not api_key:
            api_key = self.config.get_api_key()
        
        base_url = self.config.get_base_url().strip()
        if base_url.endswith('/v1'):
            url = f"{base_url}/videos"
        else:
            url = f"{base_url}/v1/videos"
        
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }
        
        # 验证 video_url
        if not video_url or not video_url.strip():
            return ("", "", None, [],
                f"❌ 必须提供 video_url\n\n"
                f"💡 使用步骤:\n"
                f"1. 将视频上传到图床或云存储\n"
                f"   推荐服务: 阿里云OSS、腾讯云COS、七牛云\n"
                f"2. 获取视频的公开访问 URL\n"
                f"3. 填入 video_url 参数\n\n"
                f"⚠️ 服务器限制:\n"
                f"• 不支持文件上传（multipart/form-data）\n"
                f"• 不支持 Base64 data URI\n"
                f"• 只接受真实的 HTTP/HTTPS URL"
            )
        
        # 验证 URL 格式
        video_url = video_url.strip()
        if not (video_url.startswith('http://') or video_url.startswith('https://')):
            return ("", "", None, [],
                f"❌ 无效的 URL 格式\n\n"
                f"URL 必须以 http:// 或 https:// 开头\n"
                f"当前输入: {video_url[:100]}"
            )
        
        # 构造请求数据
        payload = {
            'model': model,
            'video': video_url
        }
        
        # 非仅创建模式，必须发送 prompt
        if not create_only:
            payload['prompt'] = prompt or ""
            
        print(f"[Aabao 角色创建] 模式: {'仅创建角色' if create_only else '创建+生成'}")
        print(f"[Aabao 角色创建] URL: {video_url}")
        
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(5)
            
            response = requests.post(url, headers=headers, json=payload, timeout=self.config.get_timeout())
            
            return self._handle_response(response, create_only, headers, url, pbar_start=10)
            
        except requests.exceptions.Timeout:
            return ("", "", None, [], "❌ 请求超时\n请检查网络连接和 API 服务状态")
        except requests.exceptions.ConnectionError:
            return ("", "", None, [], "❌ 连接失败\n请检查网络连接和 API 地址")
        except Exception as e:
            return ("", "", None, [], f"❌ 请求失败: {str(e)}")

    def _handle_response(self, response, create_only, headers, base_params_url, pbar_start=0):
        if response.status_code != 200:
            err_text = response.text
            print(f"[Aabao Error] {response.status_code} - {err_text}")
            
            # 错误诊断与建议
            if "curl" in err_text.lower() or "download" in err_text.lower() or "port number" in err_text.lower():
                return ("", "", None, [],
                    f"❌ 服务器无法下载视频\n\n"
                    f"错误详情: {err_text[:200]}\n\n"
                    f"可能原因:\n"
                    f"1. video_url 不可公开访问\n"
                    f"2. URL 有防盗链保护\n"
                    f"3. URL 需要认证或 Cookie\n"
                    f"4. 服务器网络无法访问该域名\n\n"
                    f"💡 解决方案:\n"
                    f"• 确保 URL 是完全公开的直链\n"
                    f"• 在浏览器无痕模式测试 URL 可访问性\n"
                    f"• 使用稳定的商业云存储（推荐）:\n"
                    f"  - 阿里云 OSS\n"
                    f"  - 腾讯云 COS\n"
                    f"  - 七牛云"
                )
                 
            if "too large" in err_text.lower() or response.status_code == 413:
                return ("", "", None, [],
                    f"❌ 视频过大被拒绝\n\n"
                    f"服务器限制视频大小\n"
                    f"建议: 压缩视频或使用更短的片段"
                )
                 
            if response.status_code == 500:
                return ("", "", None, [],
                    f"❌ 服务器错误 (500)\n\n"
                    f"可能原因:\n"
                    f"• 视频格式不支持\n"
                    f"• 视频内容有问题\n"
                    f"• 服务器临时故障\n\n"
                    f"建议: 检查视频格式或稍后重试"
                )
            
            return ("", "", None, [], f"❌ API请求失败: {response.status_code}\n{err_text[:200]}")
        
        result = response.json()
        video_id = result.get("id", "")
        if not video_id:
            return ("", "", None, [], f"❌ 未获取到任务ID: {result}")

        print(f"[Aabao 角色创建] ✅ 任务已提交，ID: {video_id}")
        print(f"[Aabao 角色创建] 🔄 开始轮询状态...")

        import time
        pbar = comfy.utils.ProgressBar(100)
        max_attempts = 60  # 最多轮询2分钟
        attempt = 0
        username = ""
        last_status = ""
        status_result = None  # 初始化，避免作用域问题
        
        while attempt < max_attempts:
            try:
                status_response = requests.get(f"{base_params_url}/{video_id}", headers=headers, timeout=30)
                
                if status_response.status_code == 200:
                    status_result = status_response.json()
                    status = status_result.get("status", "unknown")
                    progress_value = status_result.get("progress", 0)
                    
                    # 只在状态变化时打印
                    if status != last_status:
                        print(f"[Aabao 角色创建] 状态: {status} (进度: {progress_value}%)")
                        last_status = status
                    
                    if status == "completed":
                        username = status_result.get("username", "")
                        display_name = status_result.get("display_name", "")
                        print(f"[Aabao 角色创建] ✅ 完成! 角色名: {username}")
                        if display_name:
                            print(f"[Aabao 角色创建] 显示名: {display_name}")
                        pbar.update_absolute(100)
                        break
                        
                    elif status == "failed":
                        error_msg = status_result.get("message", "未知错误")
                        if status_result.get("error"):
                            error_msg += f" - {status_result['error']}"
                        
                        print(f"[Aabao 角色创建] ❌ 失败: {error_msg}")
                        
                        # 有时失败也会返回username
                        if status_result.get("username"):
                            username = status_result.get("username")
                            print(f"[Aabao 角色创建] 但已获取到角色名: {username}")
                            pbar.update_absolute(100)
                            break
                        return ("", "", None, [], f"❌ 创建失败: {error_msg}")
                    
                    # 更新进度条（使用实际进度或估算进度）
                    if progress_value > 0:
                        pbar.update_absolute(min(99, progress_value))
                    else:
                        estimated_progress = pbar_start + int((attempt/max_attempts) * (100-pbar_start))
                        pbar.update_absolute(min(99, estimated_progress))
                        
                elif status_response.status_code == 404:
                    print(f"[Aabao 角色创建] ⚠️ 任务未找到，可能还在初始化...")
                else:
                    print(f"[Aabao 角色创建] ⚠️ 查询失败: {status_response.status_code}")
                    
            except requests.exceptions.Timeout:
                print(f"[Aabao 角色创建] ⚠️ 查询超时，继续重试... (尝试 {attempt+1}/{max_attempts})")
            except Exception as e:
                print(f"[Aabao 角色创建] ⚠️ 查询异常: {str(e)}")
            
            time.sleep(2)
            attempt += 1
        
        # 轮询结束后的处理
        if username:
            if create_only:
                return (username, video_id, None, [], f"✅ 角色创建成功!\n角色名: {username}")
            else:
                # create_only=False 模式，需要下载生成的视频
                if status_result:
                    video_url_result = status_result.get("video_url", "")
                    if video_url_result:
                        print(f"[Aabao 角色创建] 📥 下载视频: {video_url_result}")
                        filename = self._generate_filename("aabao_char", "mp4")
                        video_out_path = self._download_video(video_url_result, filename)
                        vhs_filenames = [video_out_path] if video_out_path else []
                        return (username, video_id, video_out_path, vhs_filenames, f"✅ 角色视频生成成功!\n角色名: {username}")
                return (username, video_id, None, [], f"✅ 角色创建成功但无视频\n角色名: {username}")

        # 超时
        print(f"[Aabao 角色创建] ❌ 轮询超时 (已尝试 {max_attempts} 次)")
        return ("", video_id, None, [],
            f"❌ 任务超时\n\n"
            f"任务ID: {video_id}\n"
            f"已轮询: {attempt} 次 ({attempt*2} 秒)\n\n"
            f"可能原因:\n"
            f"• 服务器处理时间过长\n"
            f"• 视频过大或复杂\n"
            f"• 服务器繁忙\n\n"
            f"建议: 稍后使用任务ID查询状态"
        )

NODE_CLASS_MAPPINGS = {"AabaoCharacter": AabaoCharacter}
NODE_DISPLAY_NAME_MAPPINGS = {"AabaoCharacter": "Aabao 角色创建"}
