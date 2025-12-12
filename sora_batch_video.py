# coding: utf-8
import os
import time
import json
import torch
import requests
import numpy as np
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from typing import List, Tuple, Any, Optional

try:
    from .config import config_manager
    from .utils import image_to_base64, tensor2pil, resize_image, get_aspect_ratio_size
    from .sora_base import SoraBaseNode, HAS_COMFY_API_NODES
except ImportError:
    config_manager = None
    SoraBaseNode = None
    HAS_COMFY_API_NODES = False
    def image_to_base64(img, fmt): return ""
    def tensor2pil(t): return [Image.fromarray(np.clip(255. * t.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))]
    def get_aspect_ratio_size(ar, q): return 1280, 720
    def resize_image(img, size, mode): return img

class BatchVideoWrapper:
    def __init__(self, tensor):
        self.tensor = tensor
        # Ensure tensor is 4D (BT, H, W, C) or 5D (B, T, H, W, C)
        # ComfyUI often expects [B, H, W, C] for images or custom wrappers for video.
        # If tensor is [B, H, W, C], dimensions are H, W.
        
    def get_dimensions(self):
        # Assuming tensor is (B, H, W, C) or (B, C, H, W)
        # Standard ComfyUI image tensor is (B, H, W, C)
        if len(self.tensor.shape) >= 4:
            # Check channels position. Usually last in ComfyUI.
            # (1, 720, 1280, 3) -> height=720, width=1280
            return self.tensor.shape[-2], self.tensor.shape[-3]
        return 0, 0
    
    # Allow acts like a tensor?
    # Some nodes might check isinstance(obj, torch.Tensor)
    # If so, this wrapper fails.
    # But get_dimensions check implies object.
    
    def __getattr__(self, name):
         return getattr(self.tensor, name)
         
    def __getitem__(self, idx):
         return self.tensor[idx]

    def size(self, *args):
         return self.tensor.size(*args)

    @property
    def shape(self):
         return self.tensor.shape


class SoraBatchVideo(SoraBaseNode if SoraBaseNode else object):
    @classmethod
    def INPUT_TYPES(cls):
        inputs = {
            "required": {
                "api_provider": (["t8", "t8-us", "t8-hk", "comfly", "comfly-us", "comfly-hk", "aabao"], {"default": "t8"}),
                "api_key": ("STRING", {"default": ""}), 
                "model": ([
                    "sora_video2", "sora-2-pro", "sora-2",
                    "[Aabao] sora-2-landscape", "[Aabao] sora-2-portrait", "[Aabao] sora-2-15s"
                ], {"default": "sora_video2"}),
                "prompt": ("STRING", {"multiline": True, "default": "Animate this image", "placeholder": "Global prompt..."}),
                "max_concurrent": ("INT", {"default": 3, "min": 1, "max": 10, "step": 1}),
                "aspect_ratio": (["16:9", "9:16", "1:1", "4:3"], {"default": "16:9"}),
                "duration": (["5s", "10s", "15s"], {"default": "5s"}),
            },
            "optional": {
                "image_batch": ("IMAGE",),
                "prompt_list": ("STRING", {"forceInput": True}),
                "motion_direction": (["auto", "forward", "backward", "left", "right", "zoom_in", "zoom_out"], {"default": "auto"}),
                "motion_intensity": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0}),
                "seed": ("INT", {"default": -1}),
                "output_dir": ("STRING", {"default": "sora_batch_output"}),
            }
        }
        
        # Add 10 image + prompt pairs
        for i in range(1, 11):
            inputs["optional"][f"image_{i}"] = ("IMAGE",)
            # Use forceInput=True to create a socket instead of a text widget
            inputs["optional"][f"prompt_{i}"] = ("STRING", {"forceInput": True})
            
        return inputs

    # Outputs: merged, merged_name, video_1, name_1 ... video_10, name_10, report
    RETURN_TYPES = ("VIDEO", "STRING") + tuple(["VIDEO", "STRING"] * 10) + ("STRING",)
    RETURN_NAMES = ("merged_video", "merged_filename") + tuple([n for i in range(1, 11) for n in (f"video_{i}", f"filename_{i}")]) + ("report",)
    
    FUNCTION = "generate_batch"
    CATEGORY = "Sora/Video"

    def _get_api_config(self, provider, key_input):
        if config_manager:
            cfg = config_manager.get_current_api_config(provider)
            if key_input.strip():
                cfg['api_key'] = key_input.strip()
            return cfg
        return {'api_key': key_input, 'base_url': ''}
    
    def _merge_videos(self, video_paths: List[str], output_dir: str) -> Optional[Any]:
        """
        使用ffmpeg合并多个视频文件
        
        Args:
            video_paths: 视频文件路径列表
            output_dir: 输出目录
            
        Returns:
            合并后的VideoFromFile对象，或None
        """
        if not video_paths or len(video_paths) == 0:
            print(f"[SoraBatch] ⚠️ 没有视频可合并")
            return None
        
        if len(video_paths) == 1:
            print(f"[SoraBatch] ℹ️ 只有一个视频，无需合并")
            # 返回第一个视频的VideoFromFile对象
            try:
                if HAS_COMFY_API_NODES:
                    from comfy_api.latest._input_impl.video_types import VideoFromFile
                    video_output = VideoFromFile(video_paths[0])
                    video_output.saved_path = video_paths[0]
                    return video_output
                else:
                    return video_paths[0]
            except Exception as e:
                print(f"[SoraBatch] ⚠️ 加载单个视频失败: {e}")
                return None
        
        import subprocess
        import folder_paths
        
        try:
            # 创建输出目录
            base_output_dir = folder_paths.get_output_directory()
            sora_output_dir = os.path.join(base_output_dir, output_dir)
            os.makedirs(sora_output_dir, exist_ok=True)
            
            # 生成合并后的文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            merged_filename = f"merged_{timestamp}_{os.urandom(4).hex()}.mp4"
            merged_path = os.path.join(sora_output_dir, merged_filename)
            
            # 创建ffmpeg输入文件列表
            concat_file = os.path.join(sora_output_dir, f"concat_{timestamp}.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for video_path in video_paths:
                    # 转换为绝对路径并使用正斜杠（ffmpeg要求）
                    abs_path = os.path.abspath(video_path).replace('\\', '/')
                    f.write(f"file '{abs_path}'\n")
            
            print(f"[SoraBatch] 🎬 开始合并 {len(video_paths)} 个视频...")
            print(f"[SoraBatch] 📋 合并列表文件: {concat_file}")
            print(f"[SoraBatch] 📁 输出文件: {merged_path}")
            
            # 使用ffmpeg concat demuxer合并视频
            # -f concat: 使用concat demuxer
            # -safe 0: 允许使用绝对路径
            # -i: 输入文件列表
            # -c copy: 直接复制流，不重新编码（快速）
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',
                '-y',  # 覆盖已存在的文件
                merged_path
            ]
            
            print(f"[SoraBatch] 💻 执行命令: {' '.join(cmd)}")
            
            # 执行ffmpeg命令
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                print(f"[SoraBatch] ✅ 视频合并成功: {merged_path}")
                
                # 清理临时文件
                try:
                    os.remove(concat_file)
                except:
                    pass
                
                # 返回VideoFromFile对象
                try:
                    if HAS_COMFY_API_NODES:
                        from comfy_api.latest._input_impl.video_types import VideoFromFile
                        video_output = VideoFromFile(merged_path)
                        video_output.saved_path = merged_path
                        return video_output
                    else:
                        return merged_path
                except Exception as e:
                    print(f"[SoraBatch] ⚠️ 创建VideoFromFile对象失败: {e}")
                    return merged_path
            else:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                print(f"[SoraBatch] ❌ 视频合并失败:")
                print(f"[SoraBatch] {error_msg[:500]}")
                return None
                
        except FileNotFoundError:
            print(f"[SoraBatch] ❌ 未找到ffmpeg，无法合并视频")
            print(f"[SoraBatch] 💡 请安装ffmpeg: https://ffmpeg.org/download.html")
            # Fallback: 返回第一个视频
            return video_paths[0] if video_paths else None
        except subprocess.TimeoutExpired:
            print(f"[SoraBatch] ❌ 视频合并超时（5分钟）")
            return None
        except Exception as e:
            print(f"[SoraBatch] ❌ 视频合并异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _process_single_task(self, task_idx, image_tensor, prompt, args, api_config):
        try:
            pil_img = tensor2pil(image_tensor)[0]
            w, h = get_aspect_ratio_size(args['aspect_ratio'], '1080p' if 'pro' in args['model'] else '720p')
            resized = resize_image(pil_img, (w, h), 'cover')
            img_b64 = image_to_base64(resized, "PNG")
            
            if not img_b64:
                print(f"[SoraBatch] Task {task_idx} Error: Image base64 conversion failed (empty).")
            
            full_prompt = f"{prompt}, {args['aspect_ratio']}, {args['duration']}"
            if args['motion_direction'] != 'auto': full_prompt += f", {args['motion_direction']}"
            
            # 修复：使用multipart/form-data格式（不设置Content-Type，让requests自动处理）
            headers = {
                "Authorization": f"Bearer {api_config['api_key']}"
            }
            
            base_url = api_config['base_url'].rstrip('/')
            if not base_url:
                if 't8' in args['provider']: base_url = "https://ai.t8star.cn/v1"
                elif 'aabao' in args['provider']: base_url = "https://api.aabao.top/v1"
                elif 'comfly' in args['provider']: base_url = "https://ai.comfly.chat/v1"
            
            if base_url.endswith('/v1'): url = f"{base_url}/videos"
            else: url = f"{base_url}/v1/videos"
            
            # 处理模型名称 - 去掉 [Aabao] 前缀
            model_name = args['model']
            if model_name.startswith('[Aabao] '):
                model_name = model_name.replace('[Aabao] ', '')
                print(f"[SoraBatch] Task {task_idx} 使用 Aabao 特定模型: {model_name}")
            
            print(f"[SoraBatch] Task {task_idx} posting to {url} (multipart/form-data)")
            print(f"[SoraBatch] Task {task_idx} Model: {model_name}, Size: {w}x{h}, Duration: {args['duration']}")
            
            # 构建multipart/form-data请求
            data = {
                "model": model_name,
                "prompt": full_prompt,
                "size": f"{w}x{h}",
                "seconds": args['duration'].replace('s', '')
            }
            
            if args['seed'] >= 0:
                data['seed'] = str(args['seed'])
            
            # 处理图片参考
            import base64
            import io
            files = []
            try:
                # 去掉data URI前缀（如果有）
                if ',' in img_b64:
                    img_b64 = img_b64.split(',', 1)[1]
                
                # 解码base64图片
                image_data = base64.b64decode(img_b64)
                buffered = io.BytesIO(image_data)
                files.append(('input_reference', ('image.png', buffered, 'image/png')))
                print(f"[SoraBatch] Task {task_idx} 包含图片参考 ({len(image_data)} bytes)")
            except Exception as e:
                print(f"[SoraBatch] Task {task_idx} 图片处理失败: {e}")
                return {'error': f"Image processing failed: {e}", 'idx': task_idx}
            
            # 如果没有图片，添加虚拟文件强制使用multipart/form-data
            if not files:
                files.append(('_dummy', ('', io.BytesIO(b''), 'application/octet-stream')))
            
            try:
                # 修复：不使用stream=True，直接解析JSON响应
                resp = requests.post(url, headers=headers, data=data, files=files, timeout=60)
            except Exception as req_e:
                print(f"[SoraBatch] Task {task_idx} Request EXCEPTION: {req_e}")
                return {'error': f"Request Failed: {req_e}", 'idx': task_idx}

            if resp.status_code != 200:
                print(f"[SoraBatch] Task {task_idx} API FAIL {resp.status_code}: {resp.text[:200]}")
                return {'error': f"HTTP {resp.status_code}: {resp.text[:50]}", 'idx': task_idx}
            
            # 修复：直接解析JSON响应（不是流式响应）
            task_id = None
            video_url = None
            
            try:
                result = resp.json()
                print(f"[SoraBatch] Task {task_idx} Response: {json.dumps(result, ensure_ascii=False)[:200]}...")
                
                # 从响应中提取任务ID
                task_id = result.get('id') or result.get('task_id')
                
                # 检查是否直接返回了视频URL（某些情况下）
                video_url = result.get('video_url') or result.get('url')
                
                if task_id:
                    print(f"[SoraBatch] Task {task_idx} 任务已创建，ID: {task_id}")
                elif video_url:
                    print(f"[SoraBatch] Task {task_idx} 直接获得视频URL: {video_url[:80]}...")
                else:
                    print(f"[SoraBatch] Task {task_idx} 响应中未找到任务ID或视频URL")
                    return {'error': "No task ID or video URL in response", 'idx': task_idx}
                    
            except json.JSONDecodeError as je:
                print(f"[SoraBatch] Task {task_idx} JSON解析失败: {je}")
                return {'error': f"JSON decode failed: {je}", 'idx': task_idx}
                
            if video_url:
                 # If we got URL directly, skip polling
                 pass
            elif task_id:
                print(f"[SoraBatch] Task {task_idx} Submited. ID: {task_id}. Polling...")
                start_t = time.time()
                poll_count = 0
                max_poll_time = 600  # 10分钟
                poll_interval = 5  # 5秒轮询一次
                
                while time.time() - start_t < max_poll_time:
                    time.sleep(poll_interval)
                    poll_count += 1
                    elapsed = int(time.time() - start_t)
                    
                    poll_url = f"{url}/{task_id}"
                    try:
                        r_poll = requests.get(poll_url, headers=headers, timeout=30)
                    except Exception as poll_e:
                        print(f"[SoraBatch] Task {task_idx} Poll #{poll_count} Error: {poll_e}")
                        continue
    
                    if r_poll.status_code == 200:
                        d = r_poll.json()
                        
                        # 获取状态和进度
                        st = d.get('status', '')
                        progress = d.get('progress', 0)
                        
                        # 打印详细状态
                        print(f"[SoraBatch] Task {task_idx} Poll #{poll_count} ({elapsed}s): status={st}, progress={progress}%")
                        
                        # 如果状态为空，尝试从data字段获取
                        if not st:
                            st = d.get('data', {}).get('status', '')
                            print(f"[SoraBatch] Task {task_idx} 从data字段获取状态: {st}")
                        
                        # 转换为小写用于比较
                        st_lower = st.lower() if st else ''
                        
                        # 检查是否完成
                        if st_lower in ['succeeded', 'success', 'finished', 'completed']:
                            print(f"[SoraBatch] Task {task_idx} ✅ 任务完成！状态: {st}")
                            
                            # 提取视频URL - 支持多种字段名
                            video_url = (
                                d.get('video_url') or
                                d.get('url') or
                                d.get('data', {}).get('video_url') or
                                d.get('data', {}).get('url')
                            )
                            
                            if video_url:
                                print(f"[SoraBatch] Task {task_idx} 视频URL: {video_url[:80]}...")
                                break
                            else:
                                print(f"[SoraBatch] Task {task_idx} ⚠️ 任务完成但未找到视频URL")
                                print(f"[SoraBatch] Task {task_idx} 响应数据: {json.dumps(d, ensure_ascii=False)[:300]}...")
                                # 继续轮询，可能URL稍后才会出现
                                
                        elif st_lower in ['failed', 'error']:
                            err_info = d.get('error') or d.get('fail_reason') or d.get('message') or str(d)
                            print(f"[SoraBatch] Task {task_idx} ❌ 任务失败: {err_info}")
                            return {'error': f"Failed: {err_info}", 'idx': task_idx}
                        
                        elif st_lower in ['queued', 'processing', 'pending', 'running', 'in_progress']:
                            # 正常进行中，每10次轮询打印一次详细信息
                            if poll_count % 10 == 0:
                                print(f"[SoraBatch] Task {task_idx} ⏳ 持续轮询中... (已轮询{poll_count}次，耗时{elapsed}秒)")
                        else:
                            # 未知状态
                            print(f"[SoraBatch] Task {task_idx} ❓ 未知状态: {st}")
                            print(f"[SoraBatch] Task {task_idx} 响应: {json.dumps(d, ensure_ascii=False)[:200]}...")
                    else:
                        print(f"[SoraBatch] Task {task_idx} Poll #{poll_count} HTTP {r_poll.status_code}: {r_poll.text[:100]}")
            
            if not video_url: return {'error': "Timeout", 'idx': task_idx}
            
            # 下载视频 - 使用基类的_download_video方法
            meta = {'prompt': prompt, 'model': args['model'], 'duration': args['duration']}
            try:
                # 使用基类的_download_video方法，它会返回VideoFromFile对象
                saved_obj = self._download_video(
                    video_url=video_url,
                    all_urls=[video_url],
                    wait_for_generation=False,
                    output_dir=args['output_dir'],
                    metadata=meta
                )
                
                if saved_obj is None:
                    print(f"[SoraBatch] Task {task_idx} ❌ 视频下载失败：返回None")
                    return {'error': "Video download returned None", 'idx': task_idx}
                
                # 获取保存路径
                if hasattr(saved_obj, 'path'):
                    saved_path = saved_obj.path
                elif hasattr(saved_obj, 'saved_path'):
                    saved_path = saved_obj.saved_path
                else:
                    saved_path = str(saved_obj)
                
                print(f"[SoraBatch] Task {task_idx} ✅ 视频下载完成: {saved_path}")
                return {'result': saved_obj, 'url': video_url, 'idx': task_idx, 'path': saved_path}
            except Exception as dl_e:
                print(f"[SoraBatch] Task {task_idx} ❌ 视频下载失败: {dl_e}")
                import traceback
                traceback.print_exc()
                return {'error': f"Download failed: {dl_e}", 'idx': task_idx}
            
        except Exception as e:
            print(f"[SoraBatch] Task {task_idx} General Exception: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e), 'idx': task_idx}

    def generate_batch(self, api_provider, model, prompt, max_concurrent, aspect_ratio, duration, 
                       image_batch=None, prompt_list=None, motion_direction="auto", motion_intensity=0.5, seed=-1, api_key="", output_dir="sora_batch_output",
                       **kwargs):
        
        tasks = []
        
        # 1. Collect Batch Images
        if image_batch is not None:
            # Prepare prompts for batch
            batch_prompts = []
            if prompt_list is not None:
                if isinstance(prompt_list, list):
                    batch_prompts = prompt_list
                elif isinstance(prompt_list, str):
                    # Try to parse if it looks like a list or just use it? 
                    # Usually "forceInput" STRING receives the raw object from upstream.
                    # If upstream sends a list [ "a", "b" ], prompt_list will be that list.
                    # If upstream sends a single string, we use it as a list of 1.
                    batch_prompts = [prompt_list]
            
            for i in range(image_batch.shape[0]):
                # Determine prompt for this image
                this_prompt = prompt # Default to global
                
                if batch_prompts:
                    # Cycle through available prompts
                    # If 10 images and 3 prompts: 0->0, 1->1, 2->2, 3->0 ...
                    this_prompt = batch_prompts[i % len(batch_prompts)]
                    
                    # If the item in the list is not a string (e.g. None), fallback
                    if not this_prompt or not isinstance(this_prompt, str):
                         this_prompt = prompt

                tasks.append({
                    'image': image_batch[i].unsqueeze(0),
                    'prompt': this_prompt,
                    'type': 'batch',
                    'slot': -1
                })
        
        # 2. Collect Individual Images
        for i in range(1, 11):
            img_key, pm_key = f"image_{i}", f"prompt_{i}"
            if kwargs.get(img_key) is not None:
                p_val = kwargs.get(pm_key)
                if not p_val or not p_val.strip(): p_val = prompt # Fallback
                tasks.append({
                    'image': kwargs[img_key],
                    'prompt': p_val,
                    'type': 'slot',
                    'slot': i
                })
                
        if not tasks: return (None,) * 23 # Return empty tuples
        
        print(f"[SoraBatch] {len(tasks)} tasks. Concurrent: {max_concurrent}")
        api_config = self._get_api_config(api_provider, api_key)
        
        args = {
            'provider': api_provider, 'model': model,
            'aspect_ratio': aspect_ratio, 'duration': duration,
            'motion_direction': motion_direction, 'motion_intensity': motion_intensity,
            'seed': seed, 'output_dir': output_dir
        }
        
        results_map = {} # Map original index to result
        
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(self._process_single_task, i, t['image'], t['prompt'], args, api_config): i 
                for i, t in enumerate(tasks)
            }
            for fut in concurrent.futures.as_completed(futures):
                idx = futures[fut]
                results_map[idx] = fut.result()
        
        # Assemble Outputs
        # 20 slots: 10 x (Video, Name)
        # Merged: (Video, Name)
        
        slot_results = [None] * 11 # 1-based
        all_frames = []
        all_paths = []
        report_lines = []
        
        for i, t in enumerate(tasks):
            print(f"Task {i} processing result...")
            res = results_map.get(i, {'error': 'Unknown'})
            
            if 'error' not in res and res.get('result'):
                # Success
                vid_obj = res['result']
                path = res['path']
                print(f"[SoraBatch Debug] Task {i} returned type: {type(vid_obj)}")
                
                # Get Frames for Merging
                frames = None
                if isinstance(vid_obj, torch.Tensor): 
                    frames = vid_obj
                elif isinstance(vid_obj, (list, tuple)) and len(vid_obj) > 0 and isinstance(vid_obj[0], torch.Tensor):
                    frames = vid_obj[0]
                elif hasattr(vid_obj, 'get_batch_images'): # helper object?
                     pass # complex
                     
                if frames is not None:
                    # Dimensions check?
                    # If sizes differ, concat fails. But we resize inputs to same AR/size.
                    # Generated videos should be same resolution.
                    all_frames.append(frames)
                    print(f"[SoraBatch Debug] Task {i} frames captured. Shape: {frames.shape}")
                else:
                    print(f"[SoraBatch Debug] Task {i} NO FRAMES extracted. vid_obj: {vid_obj}")
                    
                all_paths.append(path)
                
                if t['type'] == 'slot':
                    slot_results[t['slot']] = (vid_obj, path)
                
                report_lines.append(f"Task {i} ({t['type']} {t['slot'] if t['slot']>0 else ''}): OK")
            else:
                 err = res.get('error', 'Failed')
                 report_lines.append(f"Task {i}: Failed - {err}")

        # Prepare Return Tuple
        # 对于空结果，返回None而不是tensor
        # 这样下游节点可以正确处理空值
        empty_video = None
        empty_name = ""

        # 1. Merged - 真正合并所有成功的视频
        merged_video = None
        merged_name = ""
        
        if all_paths and len(all_paths) > 0:
            print(f"[SoraBatch] 🎬 开始合并 {len(all_paths)} 个视频...")
            
            # 使用ffmpeg合并视频
            merged_video = self._merge_videos(all_paths, output_dir)
            
            if merged_video:
                # 获取合并后的完整路径
                merged_path = None
                if hasattr(merged_video, 'path'):
                    merged_path = merged_video.path
                elif hasattr(merged_video, 'saved_path'):
                    merged_path = merged_video.saved_path
                elif isinstance(merged_video, str):
                    merged_path = merged_video
                
                # 构建详细的文件名信息
                # 格式：merged_xxx.mp4 | 合并了N个视频 | 总时长：XX秒 | 源文件：[file1, file2, ...]
                if merged_path:
                    filename = os.path.basename(merged_path)
                    duration_total = len(all_paths) * int(duration.replace('s', ''))
                    
                    # 构建源文件列表
                    source_files = [os.path.basename(p) for p in all_paths]
                    source_list = ", ".join(source_files[:3])  # 最多显示前3个
                    if len(source_files) > 3:
                        source_list += f", ... (+{len(source_files)-3}个)"
                    
                    merged_name = f"{filename} | 合并{len(all_paths)}个视频 | 总时长:{duration_total}秒 | 源文件:[{source_list}]"
                else:
                    merged_name = f"merged_{len(all_paths)}_videos.mp4 | {len(all_paths)}个视频"
                
                print(f"[SoraBatch] ✅ 视频合并完成: {merged_name}")
            else:
                # 如果合并失败，fallback到第一个视频
                print(f"[SoraBatch] ⚠️ 视频合并失败，使用第一个视频")
                first_result = None
                for i, t in enumerate(tasks):
                    res = results_map.get(i, {})
                    if 'error' not in res and res.get('result'):
                        first_result = res['result']
                        break
                
                if first_result:
                    merged_video = first_result
                    first_filename = os.path.basename(all_paths[0]) if all_paths else "fallback.mp4"
                    merged_name = f"{first_filename} | 合并失败，仅第一个视频"
                else:
                    merged_video = empty_video
                    merged_name = "no_videos.mp4 | 无视频生成"
        else:
            merged_video = empty_video
            merged_name = "no_videos.mp4 | 无视频生成"

        ret = [merged_video, merged_name]
        
        # 2. Slots 1-10
        for i in range(1, 11):
            if slot_results[i]:
                # 直接返回VideoFromFile对象，不包装
                # 这样与其他Sora节点的输出类型一致
                vid_res = slot_results[i][0]
                ret.append(vid_res) # Video (VideoFromFile对象)
                ret.append(slot_results[i][1]) # Name
            else:
                ret.append(empty_video)
                ret.append("empty.mp4")
                
        ret.append("\n".join(report_lines))
        return tuple(ret)

NODE_CLASS_MAPPINGS = {"SoraBatchVideo": SoraBatchVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"SoraBatchVideo": "Sora Batch Video Generator"}
