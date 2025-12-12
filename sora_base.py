"""
ComfyUI_Sora - Sora API基础类
封装Sora API调用、流式响应处理、错误处理等核心功能
"""

import os
import re
import json
import time
import requests
import folder_paths
import hashlib
from typing import Optional, Tuple, Dict, Any
from .config import config_manager
import comfy.utils
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 尝试导入comfy_api_nodes的下载函数
try:
    from comfy_api_nodes.apinode_utils import download_url_to_video_output
    import asyncio
    HAS_COMFY_API_NODES = True
except ImportError:
    HAS_COMFY_API_NODES = False
    print("[Sora] 警告: 未找到comfy_api_nodes，将使用备用下载方法")

# 视频缓存字典：{url_hash: saved_path}
VIDEO_CACHE = {}


class SoraBaseNode:
    """Sora API基础节点类"""

    def __init__(self):
        self.api_key = config_manager.get_api_key()
        self.base_url = config_manager.get_base_url()
        self.api_provider = config_manager.get_api_provider()
        self.timeout = config_manager.get('timeout', 600)
        self.max_retries = config_manager.get('max_retries', 3)
        self.retry_delay = config_manager.get('retry_delay', 5)

        # 设置代理
        proxy_url = config_manager.get('proxy_url', '')
        self.proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None
    
    def _build_headers(self, api_key: Optional[str] = None) -> Dict[str, str]:
        """
        构建请求头
        
        Args:
            api_key: API密钥，如果为None则使用配置中的密钥
            
        Returns:
            Dict[str, str]: 请求头字典
        """
        key = api_key if api_key else self.api_key
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    def _parse_stream_response(self, response: requests.Response, pbar=None) -> Tuple[str, str]:
        """
        解析流式响应（SSE格式）

        SSE格式特点：
        - 每个事件以 "data: " 开头
        - 事件以双换行符分隔
        - 结束标记为 "data: [DONE]"

        Args:
            response: requests响应对象
            pbar: ComfyUI进度条实例（可选）

        Returns:
            Tuple[str, str]: (完整内容, token使用信息)
        """
        answer_parts = []
        tokens_usage = ""
        last_progress = -1
        chunk_count = 0
        printed_url = False

        try:
            # 读取原始文本，按SSE事件分割
            buffer = ""
            event_count = 0

            # 使用iter_content读取原始字节，避免iter_lines的分割问题
            for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    buffer += chunk

                    # 按双换行符分割事件
                    while "\n\n" in buffer:
                        event, buffer = buffer.split("\n\n", 1)

                        # 处理事件
                        for line in event.split("\n"):
                            line = line.strip()
                            if not line:
                                continue

                            # 处理SSE格式
                            if line.startswith("data: "):
                                data = line[6:]

                                # 检查结束标记
                                if data == "[DONE]":
                                    break

                                # 尝试解析JSON
                                try:
                                    payload = json.loads(data)
                                    event_count += 1
                                except json.JSONDecodeError as e:
                                    continue

                                # 提取内容
                                if "choices" in payload and isinstance(payload["choices"], list) and payload["choices"]:
                                    delta = payload["choices"][0].get("delta", {})
                                    if isinstance(delta, dict):
                                        piece = delta.get("content")
                                        if isinstance(piece, str) and piece:
                                            text = piece.strip()

                                            # 进度跟踪
                                            prog_candidates = []
                                            if "进度" in text or "progress" in text.lower():
                                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)
                                                if not prog_candidates:
                                                    prog_candidates = re.findall(r'进度[^0-9]*?(\d{1,3})', text)
                                            else:
                                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)

                                            curr_prog = None
                                            for p in prog_candidates:
                                                try:
                                                    v = int(p)
                                                    if 0 <= v <= 100:
                                                        curr_prog = v if (curr_prog is None or v > curr_prog) else curr_prog
                                                except Exception:
                                                    pass
                                            if curr_prog is not None and curr_prog > last_progress:
                                                last_progress = curr_prog
                                                print(f"[Sora][{time.strftime('%H:%M:%S')}] 任务进度: {last_progress}%")
                                                # 更新ComfyUI进度条（参考ComfyUI_SongBloom的实现）
                                                if pbar is not None:
                                                    try:
                                                        pbar.update_absolute(min(last_progress, 100), 100)
                                                    except Exception:
                                                        pass

                                            # URL检测
                                            if not printed_url and ("http://" in text or "https://" in text):
                                                urls = re.findall(r'https?://\S+', text)
                                                if urls:
                                                    print(f"[Sora] 可能的视频URL: {urls[0]}")
                                                    printed_url = True

                                            # 心跳日志
                                            chunk_count += 1
                                            if chunk_count % 20 == 0:
                                                total_len = sum(len(x) for x in answer_parts) + len(text)
                                                print(f"[Sora] 流式接收中... 已接收 {chunk_count} 块，累计字符 {total_len}")

                                            answer_parts.append(piece)

            # 合并并清理编码
            answer = self._normalize_text("".join(answer_parts).strip())
            print(f"[Sora] 流式解析完成，共接收 {chunk_count} 块，总长度 {len(answer)} 字符")
            return (answer, tokens_usage)

        except Exception as e:
            print(f"[Sora] 流式解析异常: {e}")
            import traceback
            traceback.print_exc()
            return (f"流式解析失败: {e}", tokens_usage)
    
    def _normalize_text(self, s: str) -> str:
        """
        修复编码问题（参考项目的实现）

        Args:
            s: 原始文本

        Returns:
            str: 修复后的文本
        """
        if not isinstance(s, str) or not s:
            return s or ""

        # 检查是否包含常见的UTF-8误编码字符
        # 这些字符通常表示中文被错误编码
        sample = s[:100]  # 检查前100个字符

        # 常见的UTF-8误编码字符（中文被当作latin-1编码后的结果）
        suspicious_patterns = [
            'å', 'ä', 'æ', 'ç', 'è', 'é',  # 中文常见误编码
            'Ã', 'Â', 'ð', 'þ',  # 其他误编码
            'ï¼', 'ï¿',  # 标点符号误编码
        ]

        # 检查是否包含这些模式
        has_encoding_issue = any(pattern in sample for pattern in suspicious_patterns)

        if has_encoding_issue:
            try:
                # 尝试修复 latin-1 误编码为 utf-8 的问题
                fixed = s.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
                # 验证修复是否成功（检查是否包含正常的中文字符）
                if fixed and len(fixed) > 0:
                    # 如果修复后包含中文字符，说明修复成功
                    if any('\u4e00' <= ch <= '\u9fff' for ch in fixed[:50]):
                        print(f"[Sora] 🔧 检测到编码问题并已修复")
                        return fixed
            except Exception as e:
                print(f"[Sora] ⚠️ 编码修复失败: {e}")
                pass

        return s

    def _extract_progress(self, text: str) -> Optional[int]:
        """
        从文本中提取进度百分比

        Args:
            text: 文本内容

        Returns:
            Optional[int]: 进度百分比(0-100)，如果未找到则返回None
        """
        # 优先匹配包含"进度"的片段
        prog_candidates = []
        if "进度" in text or "progress" in text.lower():
            prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)
            if not prog_candidates:
                prog_candidates = re.findall(r'进度[^0-9]*?(\d{1,3})', text)
        else:
            # 一般性匹配 "41.." 这类
            prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)

        # 过滤到 0-100 的最大值
        curr_prog = None
        for p in prog_candidates:
            try:
                v = int(p)
                if 0 <= v <= 100:
                    curr_prog = v if (curr_prog is None or v > curr_prog) else curr_prog
            except Exception:
                pass

        return curr_prog
    
    def _quick_check_url(self, url: str, timeout: int = 5) -> bool:
        """
        快速检查URL是否有效（不重试）

        Args:
            url: 要检查的URL
            timeout: 超时时间

        Returns:
            bool: URL是否有效
        """
        try:
            import requests
            head_response = requests.head(url, timeout=timeout, allow_redirects=True)
            if head_response.status_code == 200:
                return True
        except:
            pass
        return False

    def _extract_url_from_web_page(self, web_url: str) -> Optional[str]:
        """
        从asyncdata.net/web/页面提取真实的视频URL

        Args:
            web_url: web页面URL

        Returns:
            真实的视频URL，如果提取失败则返回None
        """
        try:
            import requests
            print(f"[Sora] 🔍 尝试从web页面提取视频URL: {web_url}")

            # 首先尝试直接调用API获取任务状态
            task_id_match = re.search(r'(task_[a-z0-9]+)', web_url)
            if task_id_match:
                task_id = task_id_match.group(1)

                # 尝试多个可能的API端点
                # 根据页面JavaScript代码，真正的API是 /api/share/
                api_endpoints = [
                    f"https://asyncdata.net/api/share/{task_id}",  # 这是页面实际使用的API
                    f"https://asyncdata.net/source/{task_id}",
                    f"https://asyncdata.net/api/task/{task_id}",
                    f"https://asyncdata.net/api/v1/task/{task_id}",
                ]

                for api_url in api_endpoints:
                    try:
                        print(f"[Sora] 🔍 尝试调用API: {api_url}")

                        # 调用API
                        api_response = requests.get(api_url, timeout=10, proxies=self.proxies, allow_redirects=True)

                        if api_response.status_code == 200:
                            content_type = api_response.headers.get('Content-Type', '')

                            # 如果是JSON，尝试解析
                            if 'json' in content_type:
                                try:
                                    api_data = api_response.json()
                                    print(f"[Sora] 📄 API响应keys: {list(api_data.keys())}")

                                    # 检查content.draft_info（视频完成后的数据结构）
                                    if 'content' in api_data and isinstance(api_data['content'], dict):
                                        content = api_data['content']
                                        print(f"[Sora DEBUG] content存在，keys: {list(content.keys())}")

                                        # 检查draft_info
                                        if 'draft_info' in content:
                                            print(f"[Sora DEBUG] draft_info存在")
                                            draft_info = content['draft_info']
                                            url = (draft_info.get('url') or
                                                  draft_info.get('downloadable_url') or
                                                  (draft_info.get('encodings', {}).get('source', {}).get('path')))
                                            print(f"[Sora DEBUG] 提取的URL: {url[:100] if url else 'None'}...")
                                            if url and isinstance(url, str) and url.startswith('http'):
                                                print(f"[Sora] ✅ 从draft_info提取视频URL: {url[:100]}...")
                                                return url
                                            else:
                                                print(f"[Sora DEBUG] URL验证失败: url={url}, type={type(url)}")
                                        else:
                                            print(f"[Sora DEBUG] draft_info不存在")

                                        # 检查items数组
                                        if 'items' in content and isinstance(content['items'], list):
                                            for item in content['items']:
                                                if isinstance(item, dict) and item.get('kind') == 'sora_draft':
                                                    url = (item.get('url') or
                                                          item.get('downloadable_url') or
                                                          (item.get('encodings', {}).get('source', {}).get('path')))
                                                    if url and isinstance(url, str) and url.startswith('http'):
                                                        print(f"[Sora] ✅ 从items数组提取视频URL: {url[:100]}...")
                                                        return url

                                        # 检查content.url
                                        if 'url' in content and isinstance(content['url'], str) and content['url'].startswith('http'):
                                            print(f"[Sora] ✅ 从content.url提取视频URL: {content['url'][:100]}...")
                                            return content['url']
                                except Exception as e:
                                    print(f"[Sora] ⚠️ 解析JSON失败: {e}")

                            # 检查是否重定向到了视频文件
                            final_url = api_response.url
                            if final_url != api_url and ('.mp4' in final_url or '.webm' in final_url or '.mov' in final_url):
                                print(f"[Sora] ✅ 重定向到视频URL: {final_url[:100]}...")
                                return final_url

                            # 检查Content-Type
                            if 'video' in content_type:
                                print(f"[Sora] ✅ 返回视频内容: {final_url[:100]}...")
                                return final_url
                    except Exception as e:
                        print(f"[Sora] ⚠️ API调用失败 ({api_url}): {e}")
                        continue

            # 如果API调用失败，尝试从页面提取
            response = requests.get(web_url, timeout=30, proxies=self.proxies)
            if response.status_code == 200:
                page_content = response.text

                # 保存页面HTML用于调试
                try:
                    import os
                    debug_dir = os.path.join(os.path.dirname(__file__), 'debug')
                    os.makedirs(debug_dir, exist_ok=True)
                    debug_file = os.path.join(debug_dir, 'last_page.html')
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(page_content)
                    print(f"[Sora] 💾 页面HTML已保存到: {debug_file}")
                except Exception as e:
                    print(f"[Sora] ⚠️ 保存页面HTML失败: {e}")

                # 首先尝试从页面的<script>标签中提取JSON数据
                # asyncdata.net通常会在页面中嵌入一个包含所有数据的JSON对象
                script_patterns = [
                    r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                    r'window\.__DATA__\s*=\s*({.+?});',
                    r'const\s+data\s*=\s*({.+?});',
                    r'var\s+data\s*=\s*({.+?});',
                ]

                for pattern in script_patterns:
                    script_match = re.search(pattern, page_content, re.DOTALL)
                    if script_match:
                        try:
                            import json
                            json_str = script_match.group(1)
                            data = json.loads(json_str)
                            print(f"[Sora] 📄 从页面脚本中提取到JSON数据")

                            # 递归查找视频URL
                            def find_url(obj, depth=0):
                                if depth > 10:
                                    return None
                                if isinstance(obj, dict):
                                    for key in ['url', 'video_url', 'videoUrl', 'video', 'file_url', 'fileUrl', 'mp4_url', 'downloadable_url', 'download_url', 'src']:
                                        if key in obj and isinstance(obj[key], str):
                                            url = obj[key]
                                            if url.startswith('http') and ('.mp4' in url or '.webm' in url or '.mov' in url):
                                                return url
                                    for value in obj.values():
                                        result = find_url(value, depth + 1)
                                        if result:
                                            return result
                                elif isinstance(obj, list):
                                    for item in obj:
                                        result = find_url(item, depth + 1)
                                        if result:
                                            return result
                                return None

                            video_url = find_url(data)
                            if video_url:
                                print(f"[Sora] ✅ 从页面脚本JSON提取视频URL: {video_url[:100]}...")
                                return video_url
                        except Exception as e:
                            print(f"[Sora] ⚠️ 解析页面脚本JSON失败: {e}")

                # 打印页面内容的前1000字符用于调试
                print(f"[Sora] 📄 Web页面内容（前500字符）: {page_content[:500]}")
                if len(page_content) > 500:
                    print(f"[Sora] 📄 Web页面内容（后500字符）: ...{page_content[-500:]}")

                # 尝试提取页面中的视频URL
                # 1. 查找video标签的src
                video_src = re.search(r'<video[^>]+src=["\']([^"\']+)["\']', page_content)
                if video_src:
                    url = video_src.group(1)
                    # 过滤掉JavaScript变量
                    if not url.startswith('$') and url.startswith('http'):
                        print(f"[Sora] ✅ 从video标签提取URL: {url[:100]}...")
                        return url

                # 2. 查找source标签的src（video标签内可能使用source）
                source_src = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', page_content)
                if source_src:
                    url = source_src.group(1)
                    # 过滤掉JavaScript变量
                    if not url.startswith('$') and url.startswith('http'):
                        print(f"[Sora] ✅ 从source标签提取URL: {url[:100]}...")
                        return url

                # 3. 查找JavaScript中的videoUrl变量赋值
                # 例如: const videoUrl = "https://...";
                js_patterns = [
                    r'(?:const|let|var)\s+videoUrl\s*=\s*["\']([^"\']+)["\']',
                    r'videoUrl\s*:\s*["\']([^"\']+)["\']',
                    r'video_url\s*:\s*["\']([^"\']+)["\']',
                    r'"url"\s*:\s*"([^"]+\.mp4[^"]*)"',
                    r'src\s*:\s*["\']([^"\']+\.mp4[^"\']*)["\']',
                ]

                for pattern in js_patterns:
                    js_match = re.search(pattern, page_content)
                    if js_match:
                        url = js_match.group(1)
                        if url.startswith('http'):
                            import urllib.parse
                            url = urllib.parse.unquote(url)
                            url = url.replace('\\u0026', '&')
                            url = url.replace('\\/', '/')
                            print(f"[Sora] ✅ 从JavaScript提取URL: {url[:100]}...")
                            return url

                # 4. 尝试从页面的fetch调用中提取API端点，然后调用API
                # 例如: fetch('/api/task/task_xxx')
                fetch_patterns = [
                    r'fetch\(["\']([^"\']+/api/[^"\']+)["\']',
                    r'fetch\(`([^`]+/api/[^`]+)`',
                    r'axios\.get\(["\']([^"\']+/api/[^"\']+)["\']',
                ]

                for pattern in fetch_patterns:
                    fetch_match = re.search(pattern, page_content)
                    if fetch_match:
                        api_path = fetch_match.group(1)
                        # 构造完整的API URL
                        if api_path.startswith('/'):
                            api_url = f"https://asyncdata.net{api_path}"
                        elif api_path.startswith('http'):
                            api_url = api_path
                        else:
                            continue

                        # 替换task_id占位符
                        if task_id_match:
                            task_id = task_id_match.group(0)
                            api_url = api_url.replace('${taskId}', task_id)
                            api_url = api_url.replace('{taskId}', task_id)
                            api_url = api_url.replace('${id}', task_id)
                            api_url = api_url.replace('{id}', task_id)

                        try:
                            print(f"[Sora] 🔍 从页面发现API端点，尝试调用: {api_url}")
                            api_response = requests.get(api_url, timeout=10, proxies=self.proxies)
                            if api_response.status_code == 200:
                                api_data = api_response.json()
                                print(f"[Sora] 📄 API响应: {str(api_data)[:300]}...")

                                # 递归查找所有可能的URL字段
                                def find_video_url(data, depth=0):
                                    if depth > 5:  # 防止无限递归
                                        return None
                                    if isinstance(data, dict):
                                        # 查找URL字段
                                        url_fields = ['video_url', 'videoUrl', 'url', 'video', 'file_url', 'fileUrl', 'mp4_url', 'mp4Url']
                                        for field in url_fields:
                                            if field in data and isinstance(data[field], str) and data[field].startswith('http'):
                                                return data[field]
                                        # 递归查找
                                        for value in data.values():
                                            result = find_video_url(value, depth + 1)
                                            if result:
                                                return result
                                    elif isinstance(data, list):
                                        for item in data:
                                            result = find_video_url(item, depth + 1)
                                            if result:
                                                return result
                                    return None

                                video_url = find_video_url(api_data)
                                if video_url:
                                    print(f"[Sora] ✅ 从动态API获取视频URL: {video_url[:100]}...")
                                    return video_url
                        except Exception as e:
                            print(f"[Sora] ⚠️ 动态API调用失败: {e}")

                # 5. 直接查找所有包含完整签名的视频URL（优先级最高）
                # 这些URL通常包含Azure存储的签名参数（st, se, sig等）
                full_url_patterns = [
                    r'(https://[^\s"\'<>]+\.mp4\?[^\s"\'<>]*sig=[^\s"\'<>&]+)',
                    r'(https://[^\s"\'<>]+/videos/[^\s"\'<>]+\.mp4\?[^\s"\'<>]+)',
                    r'"(https://[^"]+\.mp4\?[^"]+)"',
                    r"'(https://[^']+\.mp4\?[^']+)'",
                ]

                for pattern in full_url_patterns:
                    urls = re.findall(pattern, page_content)
                    if urls:
                        for url in urls:
                            # 清理URL
                            url = url.replace('\\/', '/')
                            url = url.replace('\\u0026', '&')
                            url = url.replace('&amp;', '&')
                            # 过滤掉明显的占位符
                            if 'example' not in url.lower() and 'placeholder' not in url.lower():
                                # 检查URL是否包含必要的签名参数
                                if 'sig=' in url or 'signature=' in url:
                                    print(f"[Sora] ✅ 从页面提取带签名的视频URL: {url[:100]}...")
                                    return url

                # 6. 查找所有可能的视频URL（.mp4结尾）
                all_urls = re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', page_content)
                if all_urls:
                    # 过滤掉明显的占位符
                    valid_urls = [u for u in all_urls if 'example' not in u.lower() and 'placeholder' not in u.lower()]
                    if valid_urls:
                        url = valid_urls[0]
                        import urllib.parse
                        url = urllib.parse.unquote(url)
                        url = url.replace('\\u0026', '&')
                        url = url.replace('\\/', '/')
                        # 清理可能的HTML标签残留
                        url = re.sub(r'[<>].*$', '', url)
                        print(f"[Sora] ✅ 从页面提取.mp4 URL: {url[:100]}...")
                        return url

                # 7. 查找任何.mp4/.webm/.mov链接
                video_match = re.search(r'(https?://[^\s"\'<>]+\.(?:mp4|webm|mov)(?:\?[^\s"\'<>]*)?)', page_content, flags=re.IGNORECASE)
                if video_match:
                    url = video_match.group(1)
                    # 清理可能的HTML实体编码
                    url = url.replace('&amp;', '&')
                    # 过滤掉JavaScript变量
                    if not url.startswith('$'):
                        print(f"[Sora] ✅ 从页面提取视频链接: {url[:100]}...")
                        return url

                # 6. 尝试查找data-video-url等属性
                data_url = re.search(r'data-video-url=["\']([^"\']+)["\']', page_content)
                if data_url:
                    url = data_url.group(1)
                    if not url.startswith('$') and url.startswith('http'):
                        print(f"[Sora] ✅ 从data属性提取URL: {url[:100]}...")
                        return url

                print(f"[Sora] ⚠️ 未能从web页面提取视频URL")
                print(f"[Sora] 💡 提示：页面可能使用JavaScript动态加载视频，尝试使用/source/链接")
            else:
                print(f"[Sora] ⚠️ web页面访问失败: HTTP {response.status_code}")
        except Exception as e:
            print(f"[Sora] ⚠️ web页面提取异常: {e}")
            import traceback
            traceback.print_exc()

        return None

    def _extract_video_urls(self, text: str) -> list:
        """
        从文本中提取所有可能的视频URL，按优先级排序

        优先级：
        1. JSON中的video_url字段
        2. .mp4/.webm/.mov 直链（包括blob storage）
        3. asyncdata.net/source/ 链接
        4. [原始数据](url) markdown链接
        5. 其他链接（但过滤掉 /web/ 预览页面）

        Args:
            text: 文本内容

        Returns:
            list: 按优先级排序的URL列表
        """
        if not isinstance(text, str) or not text:
            return []

        urls = []

        try:
            # 0. 尝试解析JSON格式的响应
            # 先解码Unicode转义字符
            import codecs
            try:
                decoded_text = codecs.decode(text, 'unicode_escape')
            except:
                decoded_text = text

            # 尝试提取JSON中的video_url
            try:
                # 查找 "video_url":"..." 模式
                video_url_match = re.search(r'"video_url"\s*:\s*"([^"]+)"', decoded_text)
                if video_url_match:
                    video_url = video_url_match.group(1)
                    # 解码URL编码
                    import urllib.parse
                    video_url = urllib.parse.unquote(video_url)
                    if video_url not in urls:
                        urls.append(video_url)
                        print(f"[Sora] 🎯 从JSON提取视频URL: {video_url[:100]}...")

                # 也尝试提取gif_url作为备选
                gif_url_match = re.search(r'"gif_url"\s*:\s*"([^"]+)"', decoded_text)
                if gif_url_match:
                    gif_url = gif_url_match.group(1)
                    gif_url = urllib.parse.unquote(gif_url)
                    if gif_url not in urls and gif_url.endswith('.gif'):
                        # GIF URL可以作为预览，但优先级较低
                        pass  # 暂时不添加GIF
            except Exception as e:
                print(f"[Sora] JSON解析警告: {e}")

            # 1. 最优先：视频直链（包括blob storage的.mp4链接）
            video_match = re.findall(r'(https?://[^\s)>\]"\\]+\.(?:mp4|webm|mov)(?:\?[^\s)>\]"\\]*)?)', decoded_text, flags=re.IGNORECASE)
            for url in video_match:
                # 清理URL中的转义字符
                url = url.replace('\\u0026', '&').replace('\\', '')
                if url not in urls:
                    urls.append(url)
                    print(f"[Sora] 🎯 找到视频直链: {url[:100]}...")

            # 2. asyncdata.net/web/ 链接（预览页面）
            web_match = re.findall(r'(https?://asyncdata\.net/web/[^\s)>\]"\\]+)', decoded_text, flags=re.IGNORECASE)
            for url in web_match:
                url = url.replace('\\u0026', '&').replace('\\', '')
                if url not in urls:
                    urls.append(url)
                    print(f"[Sora] 🔍 发现/web/链接: {url}")

            # 3. asyncdata.net/source/ 链接（可能是代理）
            # 注意：这些链接可能需要等待视频生成完成
            source_match = re.findall(r'(https?://asyncdata\.net/source/[^\s)>\]"\\]+)', decoded_text, flags=re.IGNORECASE)
            for url in source_match:
                url = url.replace('\\u0026', '&').replace('\\', '')
                if url not in urls:
                    urls.append(url)
                    print(f"[Sora] 🎯 找到 /source/ 链接: {url}")

            # 4. [原始数据](url) markdown链接
            markdown_match = re.findall(r'\[原始数据\]\((https?://[^\s)]+)\)', decoded_text, flags=re.IGNORECASE)
            for url in markdown_match:
                url = url.replace('\\u0026', '&').replace('\\', '')
                # 如果是/source/链接，跳过（优先级较低）
                if '/source/' in url:
                    continue
                if url not in urls:
                    urls.append(url)
                    print(f"[Sora] 🎯 找到markdown链接: {url[:100]}...")

            # 5. 匹配括号内的链接，但过滤掉 /web/ 和 /source/ 链接
            paren_match = re.findall(r'\((https?://[^\s)]+)\)', decoded_text, flags=re.IGNORECASE)
            for url in paren_match:
                url = url.replace('\\u0026', '&').replace('\\', '')
                if '/web/' not in url and '/source/' not in url and url not in urls:
                    urls.append(url)
                    print(f"[Sora] 🎯 找到括号链接: {url[:100]}...")

            # 6. 最后才匹配任意链接，但过滤掉 /web/ 和 /source/ 链接
            all_match = re.findall(r'(https?://[^\s)>\]"\\]+)', decoded_text, flags=re.IGNORECASE)
            for url in all_match:
                url = url.replace('\\u0026', '&').replace('\\', '')
                if '/web/' not in url and '/source/' not in url and url not in urls:
                    urls.append(url)

            # 如果没有找到任何URL，打印完整响应以便调试
            if not urls:
                print(f"[Sora] ⚠️ 未找到任何视频URL")
                print(f"[Sora] 📄 完整响应内容（前500字符）: {text[:500]}")
                print(f"[Sora] 📄 解码后内容（前500字符）: {decoded_text[:500]}")
            else:
                # 如果只找到/source/链接，尝试构造可能的直接视频URL
                if len(urls) == 1 and '/source/' in urls[0]:
                    task_id_match = re.search(r'task_([a-z0-9]+)', urls[0])
                    if task_id_match:
                        task_id = task_id_match.group(0)
                        # 尝试构造可能的视频URL格式
                        possible_urls = [
                            f"https://filesystem.site/gptimage/vg-assets/assets/{task_id}/videos/00000.mp4",
                            f"https://filesystem.site/gptimage/vg-assets/assets%2F{task_id}/videos/00000.mp4",
                        ]
                        print(f"[Sora] 💡 尝试构造可能的视频URL...")
                        for possible_url in possible_urls:
                            if possible_url not in urls:
                                urls.insert(0, possible_url)  # 插入到最前面，优先尝试
                                print(f"[Sora] 🎯 添加可能的视频URL: {possible_url[:100]}...")

            return urls

        except Exception as e:
            print(f"[Sora] URL提取异常: {e}")
            import traceback
            traceback.print_exc()
            return urls

    def _extract_video_url(self, text: str) -> Optional[str]:
        """
        从文本中提取视频URL（返回第一个可用的）

        为了向后兼容保留此方法

        Args:
            text: 文本内容

        Returns:
            Optional[str]: 视频URL，如果未找到则返回None
        """
        urls = self._extract_video_urls(text)
        if urls:
            print(f"[Sora] 📋 共找到 {len(urls)} 个候选URL")
            return urls[0]
        return None

    def _call_aabao_videos_api(self, prompt: str, model: str, size: str, seconds: str, api_key: str, base_url: str, pbar=None, input_reference: Optional[str] = None) -> Tuple[str, str, str, list]:
        """
        调用 Aabao (newapi.ai) OpenAI 视频格式 API (/v1/videos)

        Args:
            prompt: 视频描述提示词
            model: 模型名称
            size: 视频分辨率 (如 "720x1280")
            seconds: 视频时长 (如 "4")
            api_key: API密钥
            base_url: API基础URL
            pbar: ComfyUI进度条实例（可选）
            input_reference: 可选的图片参考（base64编码）

        Returns:
            Tuple[str, str, str, list]: (响应内容, 主视频URL, token使用信息, 所有候选URL列表)
        """

        # 根据模型和时长动态设置轮询超时时间
        # sora-2-pro 需要更长的生成时间（20-30分钟）
        if model == 'sora-2-pro':
            max_poll_time = 2400  # 40分钟
            print(f"[Sora] ⏰ sora-2-pro 模型，设置轮询超时: {max_poll_time//60} 分钟")
        elif seconds and int(seconds) >= 25:
            max_poll_time = 2400  # 40分钟（25秒视频）
            print(f"[Sora] ⏰ 25秒视频，设置轮询超时: {max_poll_time//60} 分钟")
        elif seconds and int(seconds) >= 15:
            max_poll_time = 1200  # 20分钟（15秒视频）
            print(f"[Sora] ⏰ 15秒视频，设置轮询超时: {max_poll_time//60} 分钟")
        else:
            max_poll_time = 600   # 10分钟（默认）
            print(f"[Sora] ⏰ 标准视频，设置轮询超时: {max_poll_time//60} 分钟")
        # 注意：根据 API 文档，应该使用 multipart/form-data 格式
        # 不需要手动设置 Content-Type，requests 会自动处理
        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        api_url = f"{base_url.rstrip('/')}/videos"

        # 去掉模型名称中的 [Aabao] 标识
        original_model = model
        if model.startswith('[Aabao] '):
            model = model.replace('[Aabao] ', '')
            print(f"[Sora] 🏷️ 使用 Aabao 专用模型: {model}")

        # 根据模型和分辨率调整参数
        # 某些模型不支持 size 参数，会使用内置的分辨率
        supports_size = True

        # 检查模型是否支持自定义分辨率
        # 基础模型和带方向/时长后缀的模型通常有固定分辨率
        if model in ['sora-2', 'sora-2-pro', 'sora-1.5', 'sora-1']:
            supports_size = False
            print(f"[Sora] ℹ️ 模型 {model} 使用默认分辨率")
        elif any(suffix in model for suffix in ['-landscape', '-portrait', '-15s']):
            # 带方向或时长后缀的模型有固定分辨率
            supports_size = False
            if '-landscape' in model:
                print(f"[Sora] ℹ️ 模型 {model} 使用横屏分辨率")
            elif '-portrait' in model:
                print(f"[Sora] ℹ️ 模型 {model} 使用竖屏分辨率")
            else:
                print(f"[Sora] ℹ️ 模型 {model} 使用内置分辨率")

        # 构建 multipart/form-data 请求数据
        # 文本字段放在 data 中
        data = {
            "model": model,
            "prompt": prompt,
        }

        # 添加可选参数
        # 只有支持的模型才添加 size 参数
        if size and supports_size:
            data["size"] = size
            print(f"[Sora] 📐 设置分辨率: {size}")
        elif size and not supports_size:
            print(f"[Sora] ⚠️ 跳过分辨率参数（模型使用内置分辨率）")

        if seconds:
            data["seconds"] = str(seconds)
            print(f"[Sora] ⏱️ 设置时长: {seconds}秒")

        # 文件字段放在 files 中
        files = None
        if input_reference:
            # input_reference 应该是 base64 编码的图片
            import base64
            import io
            try:
                # 去掉 data:image/xxx;base64, 前缀（如果有）
                if ',' in input_reference:
                    input_reference = input_reference.split(',', 1)[1]

                # 解码 base64 图片
                image_data = base64.b64decode(input_reference)
                files = {"input_reference": ("image.png", io.BytesIO(image_data), "image/png")}
                print(f"[Sora] 📷 包含图片参考 ({len(image_data)} bytes)")
            except Exception as e:
                print(f"[Sora] ⚠️ 图片参考处理失败: {e}")
                import traceback
                traceback.print_exc()

        print(f"[Sora] API提供商: aabao (OpenAI Videos)")
        print(f"[Sora] 请求API: {api_url}")
        print(f"[Sora] 模型: {model}")
        print(f"[Sora] 分辨率: {size}")
        print(f"[Sora] 时长: {seconds}秒")
        preview = (prompt[:120] + "...") if len(prompt) > 120 else prompt
        print(f"[Sora] 提示词: {preview}")

        # 检查必需参数
        if not prompt:
            print(f"[Sora] ⚠️ 警告：提示词为空！")
        if not model:
            print(f"[Sora] ⚠️ 警告：模型名称为空！")

        try:
            # 第一步：创建视频生成任务
            print(f"[Sora] 📤 发送视频生成请求 (multipart/form-data)...")
            print(f"[Sora] 🔍 调试信息:")
            print(f"[Sora]   - API URL: {api_url}")
            print(f"[Sora]   - Headers: {headers}")
            print(f"[Sora]   - Data: {data}")
            print(f"[Sora]   - Files: {list(files.keys()) if files else 'None'}")
            print(f"[Sora]   - Proxies: {self.proxies}")

            response = requests.post(
                api_url,
                headers=headers,
                data=data,  # 文本字段使用 data 参数
                files=files,  # 文件字段使用 files 参数（如果有）
                timeout=30,
                proxies=self.proxies,
                verify=False  # 禁用SSL验证以避免证书问题
            )

            print(f"[Sora] 响应状态码: {response.status_code}")
            print(f"[Sora] 响应内容: {response.text[:500]}")

            if response.status_code != 200:
                error_msg = f"API错误 (状态码: {response.status_code}): {response.text}"
                print(f"[Sora] {error_msg}")
                return (error_msg, "", "", [])

            # 解析响应获取视频ID
            task_data = response.json()
            print(f"[Sora] 📄 任务响应: {json.dumps(task_data, indent=2, ensure_ascii=False)}")

            video_id = task_data.get('id')
            if not video_id:
                error_msg = f"API响应中未找到视频ID: {task_data}"
                print(f"[Sora] {error_msg}")
                return (error_msg, "", "", [])

            print(f"[Sora] ✅ 视频任务已创建，ID: {video_id}")
            print(f"[Sora] 状态: {task_data.get('status', 'unknown')}")

            # 第二步：轮询视频状态直到完成
            # max_poll_time 已在函数开头根据模型和时长设置
            poll_interval = 5    # 每5秒轮询一次
            start_time = time.time()

            print(f"[Sora] ⏳ 开始轮询视频生成状态（最长等待 {max_poll_time//60} 分钟）...")

            while time.time() - start_time < max_poll_time:
                # 查询视频状态
                query_url = f"{base_url.rstrip('/')}/videos/{video_id}"
                query_response = requests.get(
                    query_url,
                    headers=headers,
                    timeout=30,
                    proxies=self.proxies,
                    verify=False  # 禁用SSL验证
                )

                if query_response.status_code != 200:
                    print(f"[Sora] ⚠️ 查询状态失败: HTTP {query_response.status_code}")
                    time.sleep(poll_interval)
                    continue

                status_data = query_response.json()
                status = status_data.get('status', 'unknown')
                progress = status_data.get('progress', 0)

                print(f"[Sora] 📊 状态: {status}, 进度: {progress}%")

                # 更新进度条
                if pbar is not None:
                    try:
                        pbar.update_absolute(min(progress, 99), 100)
                    except Exception:
                        pass

                # 检查是否完成
                if status == 'completed':
                    # 打印完整响应以便调试
                    print(f"[Sora] 📄 完整响应数据: {json.dumps(status_data, indent=2, ensure_ascii=False)}")

                    # 尝试多个可能的 URL 字段名
                    video_url = (
                        status_data.get('url') or
                        status_data.get('video_url') or
                        status_data.get('file_url') or
                        status_data.get('download_url') or
                        status_data.get('output_url') or
                        status_data.get('result_url')
                    )

                    # 也可能在嵌套的对象中
                    if not video_url and 'output' in status_data:
                        output = status_data['output']
                        if isinstance(output, dict):
                            video_url = output.get('url') or output.get('video_url')
                        elif isinstance(output, list) and len(output) > 0:
                            video_url = output[0] if isinstance(output[0], str) else output[0].get('url')

                    if video_url:
                        print(f"[Sora] ✅ 视频生成完成！")
                        print(f"[Sora] 视频URL: {video_url[:100]}...")

                        # 更新进度条到100%
                        if pbar is not None:
                            try:
                                pbar.update_absolute(100, 100)
                            except Exception:
                                pass

                        # 构建响应内容
                        response_content = json.dumps(status_data, indent=2, ensure_ascii=False)
                        return (response_content, video_url, "", [video_url])
                    else:
                        # 尝试多个可能的下载端点
                        download_endpoints = [
                            f"{base_url.rstrip('/')}/videos/{video_id}/content",  # OpenAI 标准端点
                            f"{base_url.rstrip('/')}/videos/{video_id}/download", # 备用端点
                            f"{base_url.rstrip('/')}/files/{video_id}/content",   # 文件端点
                        ]

                        for endpoint in download_endpoints:
                            print(f"[Sora] 🔍 尝试端点: {endpoint}")
                            try:
                                download_response = requests.get(
                                    endpoint,
                                    headers=headers,
                                    timeout=30,
                                    proxies=self.proxies,
                                    verify=False,
                                    allow_redirects=False  # 不自动跟随重定向
                                )

                                print(f"[Sora] 📊 端点响应状态: {download_response.status_code}")

                                # 检查是否是重定向到视频URL
                                if download_response.status_code in [301, 302, 303, 307, 308]:
                                    video_url = download_response.headers.get('Location')
                                    if video_url:
                                        print(f"[Sora] ✅ 从重定向获取到视频URL: {video_url[:100]}...")
                                        response_content = json.dumps(status_data, indent=2, ensure_ascii=False)

                                        # 更新进度条到100%
                                        if pbar is not None:
                                            try:
                                                pbar.update_absolute(100, 100)
                                            except Exception:
                                                pass

                                        return (response_content, video_url, "", [video_url])

                                # 检查响应体中是否有URL
                                if download_response.status_code == 200:
                                    # 尝试解析 JSON
                                    try:
                                        download_data = download_response.json()
                                        print(f"[Sora] 📄 下载端点响应: {json.dumps(download_data, indent=2, ensure_ascii=False)}")
                                        video_url = download_data.get('url') or download_data.get('download_url')
                                        if video_url:
                                            print(f"[Sora] ✅ 从下载端点获取到视频URL: {video_url[:100]}...")
                                            response_content = json.dumps(status_data, indent=2, ensure_ascii=False)

                                            # 更新进度条到100%
                                            if pbar is not None:
                                                try:
                                                    pbar.update_absolute(100, 100)
                                                except Exception:
                                                    pass

                                            return (response_content, video_url, "", [video_url])
                                    except:
                                        # 如果不是 JSON，可能直接返回视频内容
                                        # 这种情况下，端点本身就是下载 URL
                                        content_type = download_response.headers.get('Content-Type', '')
                                        if 'video' in content_type or 'octet-stream' in content_type:
                                            print(f"[Sora] ✅ 端点直接返回视频内容，使用端点作为URL")
                                            response_content = json.dumps(status_data, indent=2, ensure_ascii=False)

                                            # 更新进度条到100%
                                            if pbar is not None:
                                                try:
                                                    pbar.update_absolute(100, 100)
                                                except Exception:
                                                    pass

                                            return (response_content, endpoint, "", [endpoint])

                            except Exception as e:
                                print(f"[Sora] ⚠️ 端点 {endpoint} 调用失败: {e}")
                                continue

                        error_msg = f"视频已完成但未找到URL字段。完整响应: {status_data}"
                        print(f"[Sora] {error_msg}")
                        print(f"[Sora] 💡 提示：请检查 API 文档中视频 URL 的获取方式")
                        return (error_msg, "", "", [])

                elif status == 'failed':
                    error = status_data.get('error', {})
                    error_msg = f"视频生成失败: {error.get('message', str(error))}"
                    print(f"[Sora] {error_msg}")
                    return (error_msg, "", "", [])

                # 等待后继续轮询
                elapsed = int(time.time() - start_time)
                remaining = max_poll_time - elapsed
                elapsed_min = elapsed // 60
                remaining_min = remaining // 60
                print(f"[Sora] ⏳ 等待视频生成... (已等待 {elapsed_min}分{elapsed%60}秒 / 剩余 {remaining_min}分{remaining%60}秒)")
                time.sleep(poll_interval)

            # 超时
            error_msg = f"视频生成超时（{max_poll_time//60}分钟），任务ID: {video_id}"
            print(f"[Sora] {error_msg}")
            print(f"[Sora] 💡 提示：sora-2-pro 模型生成25秒视频可能需要20-30分钟，请耐心等待")
            return (error_msg, "", "", [])

        except requests.exceptions.Timeout as e:
            error_msg = f"请求超时: {e}"
            print(f"[Sora] {error_msg}")
            return (error_msg, "", "", [])
        except requests.exceptions.ConnectionError as e:
            error_msg = f"网络连接错误: {e}"
            print(f"[Sora] {error_msg}")
            return (error_msg, "", "", [])
        except Exception as e:
            error_msg = f"API调用失败: {e}"
            print(f"[Sora] {error_msg}")
            import traceback
            traceback.print_exc()
            return (error_msg, "", "", [])

    def _call_openai_videos_api(
        self,
        prompt: str,
        model: str,
        size: str,
        seconds: str,
        api_key: str,
        base_url: str,
        pbar=None,
        input_reference: Optional[str] = None,
        seed: Optional[int] = None,
        provider: str = 'comfly'
    ) -> Tuple[str, str, str, list]:
        """
        调用 OpenAI Videos API 格式（T8 和 Comfly 通用）

        参考 Comfly_sora2_openai 节点实现
        端点: /v1/videos 或 /videos
        """
        import requests
        import json
        import time

        # T8 和 Comfly 都使用 /videos 端点
        api_url = f"{base_url.rstrip('/')}/videos"
        # 注意：不要设置 Content-Type，让 requests 自动处理 multipart/form-data
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        print(f"[Sora] API提供商: {provider} (OpenAI Videos)")
        print(f"[Sora] 请求API: {api_url}")
        print(f"[Sora] 模型: {model}")
        print(f"[Sora] 分辨率: {size}")
        print(f"[Sora] 时长: {seconds}秒")

        # 构建请求数据
        data = {
            "model": model,
            "prompt": prompt,
            "seconds": seconds,
            "size": size
        }

        if seed and seed > 0:
            data["seed"] = str(seed)
            print(f"[Sora] 种子: {seed}")

        # 处理图片参考
        import base64
        import io

        files = []
        if input_reference:
            print(f"[Sora] 🔍 检测到 input_reference，类型: {type(input_reference)}, 长度: {len(input_reference) if isinstance(input_reference, str) else 'N/A'}")
            try:
                # 去掉 data:image/xxx;base64, 前缀（如果有）
                if isinstance(input_reference, str) and ',' in input_reference:
                    print(f"[Sora] 🔍 去除 data URI 前缀")
                    input_reference = input_reference.split(',', 1)[1]

                # 解码 base64 图片
                image_data = base64.b64decode(input_reference)
                buffered = io.BytesIO(image_data)
                files.append(('input_reference', ('image.png', buffered, 'image/png')))
                print(f"[Sora] 📷 包含图片参考 ({len(image_data)} bytes)")
            except Exception as e:
                print(f"[Sora] ⚠️ 图片参考处理失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[Sora] 🔍 input_reference 为空或 None")

        # 重要：如果没有图片，添加一个虚拟空文件来强制使用 multipart/form-data
        # 否则 requests 会使用 application/x-www-form-urlencoded，导致参数丢失
        if not files:
            files.append(('_dummy', ('', io.BytesIO(b''), 'application/octet-stream')))
            print(f"[Sora] 📝 文生视频模式（无图片参考）")

        try:
            # 第一步：创建视频生成任务
            print(f"[Sora] 📤 发送视频生成请求...")
            print(f"[Sora] 📋 请求参数: model={model}, prompt={prompt[:50]}..., seconds={seconds}, size={size}")

            if pbar:
                pbar.update_absolute(10)

            # 重要：即使 files 为空，也要传递空列表（而不是 None）
            # 这样 requests 会使用 multipart/form-data 格式
            response = requests.post(
                api_url,
                headers=headers,
                data=data,
                files=files,
                timeout=900,
                proxies=self.proxies,
                verify=False
            )

            print(f"[Sora] 📊 响应状态码: {response.status_code}")

            if response.status_code != 200:
                error_msg = f"API错误 (状态码: {response.status_code}): {response.text}"
                print(f"[Sora] {error_msg}")
                return (error_msg, "", "", [])

            # 解析响应
            result = response.json()
            print(f"[Sora] 📄 响应: {json.dumps(result, ensure_ascii=False, indent=2)}")

            # 获取任务ID
            if "id" not in result:
                error_msg = "No task ID in API response"
                print(f"[Sora] {error_msg}")
                return (error_msg, "", "", [])

            task_id = result["id"]
            print(f"[Sora] 📋 任务ID: {task_id}")

            if pbar:
                pbar.update_absolute(20)

            # 第二步：轮询任务状态
            max_attempts = 120  # 最多轮询 120 次
            poll_interval = 10  # 每 10 秒轮询一次
            attempts = 0
            video_url = None
            actual_seed = str(seed) if seed and seed > 0 else "0"

            print(f"[Sora] ⏳ 开始轮询任务状态...")

            while attempts < max_attempts:
                time.sleep(poll_interval)
                attempts += 1

                try:
                    status_url = f"{api_url}/{task_id}"
                    status_response = requests.get(
                        status_url,
                        headers=headers,
                        timeout=30,
                        proxies=self.proxies,
                        verify=False
                    )

                    if status_response.status_code != 200:
                        print(f"[Sora] ⚠️ 查询状态失败: HTTP {status_response.status_code}")
                        continue

                    status_data = status_response.json()
                    status = status_data.get("status", "")
                    progress = status_data.get("progress", 0)

                    # 更新进度条
                    if pbar:
                        try:
                            progress_int = int(progress)
                            pbar_value = min(90, 20 + int(progress_int * 0.7))
                            pbar.update_absolute(pbar_value)
                        except (ValueError, TypeError):
                            progress_value = min(80, 20 + (attempts * 60 // max_attempts))
                            pbar.update_absolute(progress_value)

                    print(f"[Sora] 📊 状态: {status}, 进度: {progress}%")

                    # 检查是否完成
                    if status == "completed":
                        video_url = status_data.get("video_url")
                        if not video_url and "url" in status_data:
                            video_url = status_data.get("url")

                        if "seed" in status_data:
                            actual_seed = str(status_data.get("seed", "0"))

                        if video_url:
                            print(f"[Sora] ✅ 视频生成完成！")
                            print(f"[Sora] 视频URL: {video_url}")

                            if pbar:
                                pbar.update_absolute(100)

                            response_content = json.dumps(status_data, indent=2, ensure_ascii=False)
                            return (response_content, video_url, "", [video_url])
                        else:
                            error_msg = "视频生成完成但未找到视频URL"
                            print(f"[Sora] {error_msg}")
                            return (json.dumps(status_data), "", "", [])

                    elif status == "failed":
                        fail_reason = status_data.get("fail_reason", "Unknown error")
                        error_msg = f"视频生成失败: {fail_reason}"
                        print(f"[Sora] {error_msg}")
                        return (error_msg, "", "", [])

                except Exception as e:
                    print(f"[Sora] ⚠️ 查询状态异常: {str(e)}")

            # 超时
            error_msg = f"视频生成超时（{max_attempts * poll_interval // 60}分钟），任务ID: {task_id}"
            print(f"[Sora] {error_msg}")
            return (error_msg, "", "", [])

        except Exception as e:
            error_msg = f"API调用失败: {e}"
            print(f"[Sora] {error_msg}")
            import traceback
            traceback.print_exc()
            return (error_msg, "", "", [])

    def _call_api(self, payload: Dict[str, Any], api_key: Optional[str] = None, api_provider: Optional[str] = None, base_url: Optional[str] = None, pbar=None) -> Tuple[str, str, str, list]:
        """
        调用Sora API

        Args:
            payload: 请求载荷
            api_key: API密钥，如果为None则使用配置中的密钥
            api_provider: API提供商，如果为None则使用配置中的提供商
            base_url: API基础URL，如果为None则根据提供商自动选择
            pbar: ComfyUI进度条实例（可选）

        Returns:
            Tuple[str, str, str, list]: (响应内容, 主视频URL, token使用信息, 所有候选URL列表)
        """
        # 确定使用的API提供商
        provider = api_provider if api_provider else self.api_provider

        # 获取对应提供商的配置
        if api_key is None or base_url is None:
            api_config = config_manager.get_current_api_config(provider)
            if api_key is None:
                api_key = api_config['api_key']
            if base_url is None:
                base_url = api_config['base_url']

        # T8 和 Comfly 提供商使用 OpenAI Videos API 格式
        if provider in ['t8', 'comfly']:
            # 从 payload 中提取参数
            messages = payload.get('messages', [])
            prompt = ""
            if messages:
                user_msg = messages[-1].get('content', '')
                # content 可能是字符串或数组
                if isinstance(user_msg, str):
                    prompt = user_msg
                elif isinstance(user_msg, list):
                    # 从数组中提取文本部分
                    for item in user_msg:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            prompt = item.get('text', '')
                            break

            # 从 payload 中提取视频参数
            model = payload.get('model', 'sora-2')
            size = payload.get('size', '720x1280')
            seconds = payload.get('seconds', '10')
            seed = payload.get('seed', None)

            # 提取图片参考（如果有）
            input_reference = payload.get('input_reference', None)

            # T8 和 Comfly 使用相同的 API 格式
            return self._call_openai_videos_api(
                prompt=prompt,
                model=model,
                size=size,
                seconds=seconds,
                api_key=api_key,
                base_url=base_url,
                pbar=pbar,
                input_reference=input_reference,
                seed=seed,
                provider=provider
            )

        # 如果是 aabao 提供商，检查模型类型
        if provider == 'aabao':
            model = payload.get('model', 'sora-2')

            # sora-2-pro 使用 Chat Completions API，其他模型使用 Videos API
            if model == 'sora-2-pro':
                print(f"[Sora] ℹ️ 模型 {model} 使用 Chat Completions API")
                # 继续使用下面的 Chat Completions API 逻辑
                pass
            else:
                # 使用 OpenAI 视频格式 API
                # 从 payload 中提取参数
                messages = payload.get('messages', [])
                prompt = ""
                if messages:
                    user_msg = messages[-1].get('content', '')
                    # content 可能是字符串或数组
                    if isinstance(user_msg, str):
                        prompt = user_msg
                    elif isinstance(user_msg, list):
                        # 从数组中提取文本部分
                        for item in user_msg:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                prompt = item.get('text', '')
                                break

                # 从 payload 中提取视频参数（如果有的话）
                # 这些参数可能在子类中设置
                size = payload.get('size', '720x1280')
                seconds = payload.get('seconds', '4')

                # 提取图片参考（如果有）
                input_reference = payload.get('input_reference', None)

                return self._call_aabao_videos_api(
                    prompt=prompt,
                    model=model,
                    size=size,
                    seconds=seconds,
                    api_key=api_key,
                    base_url=base_url,
                    pbar=pbar,
                    input_reference=input_reference
                )

        # 其他未知提供商报错
        error_msg = f"不支持的 API 提供商: {provider}。支持的提供商: t8, comfly, aabao"
        print(f"[Sora] ❌ {error_msg}")
        return (error_msg, "", "", [])
    
    def _parse_non_stream_response(self, response: requests.Response) -> Tuple[str, str]:
        """
        解析非流式响应
        
        Args:
            response: requests响应对象
            
        Returns:
            Tuple[str, str]: (内容, token使用信息)
        """
        try:
            data = response.json()
            
            # 检查错误
            if "error" in data:
                err = data["error"]
                msg = err.get("message", str(err))
                return (f"API错误: {msg}", "")
            
            # 提取内容
            if "choices" in data and data["choices"]:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                
                # 提取token使用信息
                usage = data.get("usage", {})
                tokens = self._format_tokens_usage(usage)
                
                return (content, tokens)
            
            return ("API未返回内容", "")
            
        except Exception as e:
            return (f"响应解析失败: {e}", "")
    
    def _format_tokens_usage(self, usage: Dict[str, Any]) -> str:
        """格式化token使用信息"""
        if not usage:
            return ""

        total = usage.get('total_tokens', '-')
        prompt = usage.get('prompt_tokens', usage.get('input_tokens', '-'))
        completion = usage.get('completion_tokens', usage.get('output_tokens', '-'))

        return f"total={total}, input={prompt}, output={completion}"

    def _check_url_validity(self, url: str, timeout: int = 10, retry_on_404: bool = True, max_retries: int = 3, retry_delay: int = 5) -> bool:
        """
        检查URL是否有效（返回200状态码），支持404重试

        Args:
            url: 要检查的URL
            timeout: 超时时间
            retry_on_404: 是否在404时重试
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            bool: URL是否有效
        """
        import requests

        for attempt in range(max_retries):
            try:
                head_response = requests.head(url, timeout=timeout, allow_redirects=True)
                print(f"[Sora] 🔍 URL检查 (尝试 {attempt + 1}/{max_retries}): {url[:80]}... -> HTTP {head_response.status_code}")

                if head_response.status_code == 200:
                    content_type = head_response.headers.get('content-type', 'unknown')
                    content_length = head_response.headers.get('content-length', 'unknown')
                    print(f"[Sora] ✅ URL有效 - Type: {content_type}, Size: {content_length}")
                    return True
                elif head_response.status_code == 404:
                    if retry_on_404 and attempt < max_retries - 1:
                        print(f"[Sora] ⏳ URL返回404，视频可能还在生成中，{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        print(f"[Sora] ❌ URL返回404，资源不存在")
                        return False
                else:
                    print(f"[Sora] ⚠️ URL返回状态码: {head_response.status_code}")
                    # 对于非200/404状态码，仍然尝试下载（可能是服务器不支持HEAD请求）
                    return True
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[Sora] ⚠️ URL检查失败: {e}，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"[Sora] ⚠️ URL检查失败: {e}，将尝试直接下载")
                    # 检查失败时仍然尝试下载
                    return True

        return False

    def _download_video(self, video_url: str, all_urls: Optional[list] = None, wait_for_generation: bool = True, output_dir: str = "sora_videos", metadata: Optional[dict] = None) -> Optional[Any]:
        """
        下载视频并返回VIDEO对象，支持多URL fallback和等待视频生成

        Args:
            video_url: 主要视频URL
            all_urls: 所有候选URL列表（用于fallback）
            wait_for_generation: 是否等待视频生成完成（对于404错误）
            output_dir: 自定义保存目录（相对于output目录）
            metadata: 视频元数据（提示词、参数等）

        Returns:
            VIDEO对象（VideoFromFile），或None
        """
        if not video_url or not isinstance(video_url, str):
            print(f"[Sora] 无效的视频URL: {video_url}")
            return None

        if not video_url.startswith(("http://", "https://")):
            print(f"[Sora] 不支持的URL格式: {video_url}")
            return None

        # 构建要尝试的URL列表
        urls_to_try = []
        if all_urls:
            urls_to_try = all_urls.copy()
        else:
            urls_to_try = [video_url]

        # 确保主URL在列表最前面
        if video_url in urls_to_try:
            urls_to_try.remove(video_url)
        urls_to_try.insert(0, video_url)

        print(f"[Sora] 🎬 准备下载视频，共 {len(urls_to_try)} 个候选URL")

        # 尝试每个URL
        for idx, url in enumerate(urls_to_try, 1):
            print(f"[Sora] 📥 尝试URL {idx}/{len(urls_to_try)}: {url[:80]}...")

            # 如果是 asyncdata.net/web/ 或 /source/ 链接，先尝试提取真实的视频URL
            if 'asyncdata.net' in url and ('/web/' in url or '/source/' in url):
                link_type = '/web/' if '/web/' in url else '/source/'
                print(f"[Sora] 🔍 检测到 {link_type} 链接，尝试提取真实视频URL...")

                # 对于 /source/ 链接，直接调用 GET 获取 JSON
                if '/source/' in url:
                    try:
                        # 根据模型和时长动态设置轮询超时时间
                        model = metadata.get('model', '') if metadata else ''
                        duration = metadata.get('duration', 0) if metadata else 0

                        if model == 'sora-2-pro':
                            max_poll_time = 2400  # 40分钟
                            print(f"[Sora] ⏰ sora-2-pro 模型，设置轮询超时: {max_poll_time//60} 分钟")
                        elif duration >= 25:
                            max_poll_time = 2400  # 40分钟
                            print(f"[Sora] ⏰ 25秒视频，设置轮询超时: {max_poll_time//60} 分钟")
                        elif duration >= 15:
                            max_poll_time = 1200  # 20分钟
                            print(f"[Sora] ⏰ 15秒视频，设置轮询超时: {max_poll_time//60} 分钟")
                        else:
                            max_poll_time = 600   # 10分钟
                            print(f"[Sora] ⏰ 标准视频，设置轮询超时: {max_poll_time//60} 分钟")

                        poll_interval = 10   # 每10秒轮询一次
                        start_time = time.time()
                        real_url = None

                        print(f"[Sora] ⏳ 开始轮询 /source/ 直到视频完成（最长等待 {max_poll_time//60} 分钟）...")

                        while time.time() - start_time < max_poll_time:
                            response = requests.get(url, timeout=30, proxies=self.proxies)
                            if response.status_code == 200:
                                try:
                                    data = response.json()

                                    # 检查状态和进度
                                    status = data.get('status', '')
                                    progress = data.get('progress', 0)

                                    print(f"[Sora] 📊 任务状态: {status}, 进度: {progress}%")

                                    # 尝试多个可能的字段
                                    for key in ['url', 'video_url', 'downloadable_url', 'draft_info.url', 'draft_info.downloadable_url']:
                                        if '.' in key:
                                            # 嵌套字段
                                            parts = key.split('.')
                                            value = data
                                            for part in parts:
                                                if isinstance(value, dict) and part in value:
                                                    value = value[part]
                                                else:
                                                    value = None
                                                    break
                                            if value and isinstance(value, str) and value.startswith('http'):
                                                real_url = value
                                                break
                                        else:
                                            # 顶层字段
                                            if key in data and isinstance(data[key], str) and data[key].startswith('http'):
                                                real_url = data[key]
                                                break

                                    if real_url:
                                        print(f"[Sora] ✅ 视频生成完成！成功从 /source/ 提取真实URL: {real_url[:100]}...")
                                        break
                                    else:
                                        # 检查是否失败
                                        if status in ['failed', 'error', 'cancelled']:
                                            print(f"[Sora] ❌ 任务失败: {status}")
                                            print(f"[Sora] 📄 响应数据: {data}")
                                            break

                                        # 视频还在生成中，继续等待
                                        elapsed = int(time.time() - start_time)
                                        remaining = max_poll_time - elapsed
                                        elapsed_min = elapsed // 60
                                        remaining_min = remaining // 60
                                        print(f"[Sora] ⏳ 视频还在生成中... (已等待 {elapsed_min}分{elapsed%60}秒 / 剩余 {remaining_min}分{remaining%60}秒)")
                                        time.sleep(poll_interval)

                                except json.JSONDecodeError:
                                    print(f"[Sora] ⚠️ /source/ 响应不是有效的JSON")
                                    break
                            else:
                                print(f"[Sora] ⚠️ /source/ 访问失败: HTTP {response.status_code}")
                                break

                        if real_url:
                            url = real_url
                        else:
                            elapsed = int(time.time() - start_time)
                            if elapsed >= max_poll_time:
                                print(f"[Sora] ⚠️ 轮询超时（{max_poll_time//60}分钟），视频仍未完成")
                                print(f"[Sora] 💡 提示：sora-2-pro 模型生成25秒视频可能需要20-30分钟")
                            print(f"[Sora] ⚠️ /source/ 响应中未找到视频URL")
                            if 'data' in locals():
                                print(f"[Sora] 📄 响应keys: {list(data.keys())}")
                            continue

                    except Exception as e:
                        print(f"[Sora] ⚠️ /source/ 提取异常: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                else:
                    # /web/ 链接，使用原来的提取方法
                    real_url = self._extract_url_from_web_page(url)
                    if real_url:
                        print(f"[Sora] ✅ 成功从 /web/ 页面提取真实URL: {real_url[:100]}...")
                        url = real_url
                    else:
                        print(f"[Sora] ⚠️ 无法从 /web/ 页面提取真实URL，跳过此链接")
                        continue

            # 检查缓存
            url_hash = hashlib.md5(url.encode()).hexdigest()
            if url_hash in VIDEO_CACHE:
                cached_path = VIDEO_CACHE[url_hash]
                if os.path.exists(cached_path):
                    print(f"[Sora] 💾 使用缓存视频: {cached_path}")
                    try:
                        # 从缓存路径创建VideoFromFile对象
                        if HAS_COMFY_API_NODES:
                            from comfy_api.latest._input_impl.video_types import VideoFromFile
                            video_output = VideoFromFile(cached_path)
                            video_output.saved_path = cached_path
                            return video_output
                        else:
                            return cached_path
                    except Exception as e:
                        print(f"[Sora] ⚠️ 缓存加载失败: {e}，重新下载")
                        del VIDEO_CACHE[url_hash]
                else:
                    # 缓存文件不存在，删除缓存记录
                    del VIDEO_CACHE[url_hash]

            # 检查URL有效性（对于asyncdata.net链接，启用404重试）
            is_asyncdata = 'asyncdata.net' in url
            retry_on_404 = wait_for_generation and is_asyncdata

            # 对于asyncdata.net链接，增加重试次数和等待时间
            # 因为视频生成可能需要较长时间
            max_retries = 15 if retry_on_404 else 1  # 增加到15次
            retry_delay = 20 if retry_on_404 else 5  # 增加到20秒
            # 总等待时间：最多300秒（5分钟）

            if not self._check_url_validity(url, retry_on_404=retry_on_404, max_retries=max_retries, retry_delay=retry_delay):
                print(f"[Sora] ⏭️ 跳过无效URL，尝试下一个...")
                continue

            try:
                if HAS_COMFY_API_NODES:
                    # 使用comfy_api_nodes的异步下载函数
                    print(f"[Sora] 📥 开始异步下载...")
                    print(f"[Sora] 💡 视频URL: {url}")
                    
                    # 增加超时时间到600秒（10分钟）
                    try:
                        video_output = asyncio.run(download_url_to_video_output(url, timeout=600))
                        print(f"[Sora] ✅ 视频下载完成")
                    except asyncio.TimeoutError:
                        print(f"[Sora] ⚠️ 异步下载超时，尝试使用备用方法...")
                        # 如果异步下载失败，尝试备用方法
                        raise Exception("Async download timeout, falling back to requests")

                    # 保存视频到output目录（参考ComfyUI的SaveVideo节点）
                    saved_path = None
                    try:
                        base_output_dir = folder_paths.get_output_directory()
                        sora_output_dir = os.path.join(base_output_dir, output_dir)
                        os.makedirs(sora_output_dir, exist_ok=True)

                        # 生成唯一文件名
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        random_suffix = os.urandom(4).hex()
                        filename = f"sora_{timestamp}_{random_suffix}.mp4"
                        dest_path = os.path.join(sora_output_dir, filename)

                        # 使用VideoInput的save_to方法保存视频
                        # 这是ComfyUI SaveVideo节点使用的方法
                        if hasattr(video_output, 'save_to'):
                            # 保存视频，带元数据
                            video_output.save_to(dest_path, format="auto", codec="auto", metadata=metadata)
                            print(f"[Sora] 📁 视频已保存到: {dest_path}")
                            if metadata:
                                print(f"[Sora] 📝 已添加元数据: {list(metadata.keys())}")
                            saved_path = dest_path

                            # 在video_output对象上添加自定义属性saved_path
                            # 这样在sora_image2video.py中可以优先使用这个路径
                            video_output.saved_path = dest_path
                            print(f"[Sora] 🔄 已设置video_output.saved_path为: {dest_path}")

                            # 添加到缓存
                            url_hash = hashlib.md5(url.encode()).hexdigest()
                            VIDEO_CACHE[url_hash] = dest_path
                            print(f"[Sora] 💾 已添加到缓存 (hash: {url_hash[:8]}...)")
                        else:
                            print(f"[Sora] ⚠️ VideoFromFile对象没有save_to方法")
                    except Exception as save_error:
                        print(f"[Sora] ⚠️ 保存视频失败: {save_error}")
                        import traceback
                        traceback.print_exc()

                    return video_output
                else:
                    # 备用方法：下载到output目录
                    output_dir = folder_paths.get_output_directory()
                    sora_output_dir = os.path.join(output_dir, "sora_videos")
                    os.makedirs(sora_output_dir, exist_ok=True)

                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"sora_{timestamp}_{os.urandom(4).hex()}.mp4"
                    output_path = os.path.join(sora_output_dir, filename)

                    print(f"[Sora] 下载到: {output_path}")
                    response = requests.get(url, timeout=self.timeout, stream=True, verify=False)
                    response.raise_for_status()

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)

                                if downloaded % (10 * 1024 * 1024) == 0 and total_size > 0:
                                    progress = (downloaded / total_size) * 100
                                    print(f"[Sora] 下载进度: {progress:.1f}%")

                    print(f"[Sora] ✅ 视频下载完成: {output_path}")
                    return output_path

            except Exception as e:
                print(f"[Sora] ❌ URL {idx} 下载失败: {e}")
                if idx < len(urls_to_try):
                    print(f"[Sora] 🔄 尝试下一个URL...")
                    continue
                else:
                    print(f"[Sora] ❌ 所有URL都下载失败")
                    import traceback
                    traceback.print_exc()
                    return None

        print(f"[Sora] ❌ 所有 {len(urls_to_try)} 个URL都无法下载")

        # 提供有用的建议
        if urls_to_try:
            first_url = urls_to_try[0]
            if 'asyncdata.net' in first_url:
                # 提取task ID
                task_id_match = re.search(r'task_([a-z0-9]+)', first_url)
                if task_id_match:
                    task_id = task_id_match.group(0)
                    web_url = f"https://asyncdata.net/web/{task_id}"
                    print(f"\n[Sora] 💡 建议：")
                    print(f"[Sora] 1. 在浏览器中打开: {web_url}")
                    print(f"[Sora] 2. 查看视频是否可以播放")
                    print(f"[Sora] 3. 如果可以播放，右键视频 → 复制视频地址")
                    print(f"[Sora] 4. 或使用提取工具: python extract_video_url.py {web_url}")
                    print(f"[Sora] 5. 或等待更长时间后重试（视频可能还在生成）\n")

        return None

    def _call_comfly_multi_image_api(self, payload: Dict[str, Any], api_key: str, pbar=None) -> Tuple[str, str, str, list]:
        """
        调用Comfly多图参考视频生成API

        使用 https://ai.comfly.chat/v2/videos/generations 端点

        Args:
            payload: 请求载荷，包含:
                - prompt: 提示词
                - model: 模型名称
                - images: base64图片数组
                - aspect_ratio: 宽高比
                - duration: 时长
                - hd: HD模式
                - seed: 随机种子（可选）
            api_key: API密钥
            pbar: 进度条实例（可选）

        Returns:
            Tuple[str, str, str, list]: (响应内容, 视频URL, token信息, 所有URL列表)
        """
        import requests
        import json
        import time

        api_url = "https://ai.comfly.chat/v2/videos/generations"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        print(f"[Sora MultiImage] 调用Comfly多图API: {api_url}")
        print(f"[Sora MultiImage] 模型: {payload.get('model')}")
        print(f"[Sora MultiImage] 图片数量: {len(payload.get('images', []))}")
        print(f"[Sora MultiImage] 宽高比: {payload.get('aspect_ratio')}")
        print(f"[Sora MultiImage] 时长: {payload.get('duration')}秒")
        print(f"[Sora MultiImage] HD模式: {payload.get('hd', False)}")

        try:
            # 发送请求
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=600  # 10分钟超时
            )

            print(f"[Sora MultiImage] 响应状态码: {response.status_code}")

            if response.status_code != 200:
                error_msg = f"API错误 (状态码: {response.status_code}): {response.text}"
                print(f"[Sora MultiImage] {error_msg}")
                return (error_msg, "", "", [])

            # 解析响应
            result = response.json()
            print(f"[Sora MultiImage] 响应: {json.dumps(result, ensure_ascii=False, indent=2)}")

            # 检查是否是任务ID响应
            if 'task_id' in result or 'id' in result:
                task_id = result.get('task_id') or result.get('id')
                print(f"[Sora MultiImage] 获得任务ID: {task_id}")

                # 轮询任务状态
                max_poll_time = 1200  # 20分钟
                poll_interval = 5  # 5秒轮询一次
                start_time = time.time()

                while time.time() - start_time < max_poll_time:
                    time.sleep(poll_interval)

                    # 查询任务状态
                    status_url = f"https://ai.comfly.chat/v2/videos/generations/{task_id}"
                    status_response = requests.get(status_url, headers=headers, timeout=30)

                    if status_response.status_code == 200:
                        status_result = status_response.json()
                        status = status_result.get('status', 'unknown')

                        print(f"[Sora MultiImage] 任务状态: {status}")

                        if pbar:
                            elapsed = time.time() - start_time
                            progress = min(int((elapsed / max_poll_time) * 100), 99)
                            pbar.update_absolute(progress, 100)

                        if status == 'completed' or status == 'succeeded':
                            # 提取视频URL
                            video_url = status_result.get('video_url') or status_result.get('url')
                            if video_url:
                                print(f"[Sora MultiImage] ✅ 视频生成成功: {video_url}")
                                if pbar:
                                    pbar.update_absolute(100, 100)
                                return (json.dumps(status_result), video_url, "", [video_url])

                        elif status == 'failed' or status == 'error':
                            error_msg = status_result.get('error', '未知错误')
                            print(f"[Sora MultiImage] ❌ 任务失败: {error_msg}")
                            return (error_msg, "", "", [])

                    else:
                        print(f"[Sora MultiImage] 查询状态失败: {status_response.status_code}")

                # 超时
                error_msg = f"任务超时（{max_poll_time}秒）"
                print(f"[Sora MultiImage] {error_msg}")
                return (error_msg, "", "", [])

            # 直接返回视频URL的情况
            elif 'video_url' in result or 'url' in result:
                video_url = result.get('video_url') or result.get('url')
                print(f"[Sora MultiImage] ✅ 直接获得视频URL: {video_url}")
                return (json.dumps(result), video_url, "", [video_url])

            else:
                error_msg = f"无法从响应中提取视频URL或任务ID: {result}"
                print(f"[Sora MultiImage] {error_msg}")
                return (error_msg, "", "", [])

        except Exception as e:
            error_msg = f"API调用异常: {e}"
            print(f"[Sora MultiImage] {error_msg}")
            import traceback
            traceback.print_exc()
            return (error_msg, "", "", [])

