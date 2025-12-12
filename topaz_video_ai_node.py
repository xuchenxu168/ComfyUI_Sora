"""
Topaz Video AI节点 - 用于视频高清修复和放大

支持功能：
- 视频超分辨率（2x, 4x）
- 视频降噪
- 视频去隔行
- 视频帧率插值
- 多种AI模型选择
"""

import os
import sys
import subprocess
import torch
import folder_paths
from typing import Tuple
from comfy.utils import ProgressBar


class KenChenTopazVideoEnhancer:
    """
    Ken-Chen Topaz Video Enhancer - 高清视频修复和放大
    """

    def __init__(self):
        self.type = "KenChenTopazVideoEnhancer"
        self.output_dir = folder_paths.get_output_directory()
    
    @classmethod
    def INPUT_TYPES(cls):
        # Topaz Video AI Beta 模型列表（31个）
        # 使用前缀模拟Topaz GUI的分类方式

        upscale_models = [
            # === Frame Interpolation 分类（6个）===
            "Frame Interpolation | Themis",
            "Frame Interpolation | Aion",
            "Frame Interpolation | Apollo",
            "Frame Interpolation | Apollo Fast",
            "Frame Interpolation | Chronos",
            "Frame Interpolation | Chronos Fast",

            # === Enhancement 分类（25个）===
            "Enhancement | Artemis - Aliasing or Moire",
            "Enhancement | Artemis - High Quality",
            "Enhancement | Artemis - Low Quality",
            "Enhancement | Artemis - Medium Quality",
            "Enhancement | Artemis - Medium Quality Strong Halo",
            "Enhancement | Artemis - Low Quality Strong Halo",
            "Enhancement | Computer Generated",
            "Enhancement | Dione - DV",
            "Enhancement | Dione - Robust",
            "Enhancement | Dione - Robust Dehalo",
            "Enhancement | Dione - TV",
            "Enhancement | Dione - TV Dehalo",
            "Enhancement | Gaia - High Quality",
            "Enhancement | Hyperion HDR",
            "Enhancement | Iris",
            "Enhancement | Iris LQ",
            "Enhancement | Nyx",
            "Enhancement | Nyx Fast",
            "Enhancement | Proteus",
            "Enhancement | Proteus Fine Tune",
            "Enhancement | Rhea",
            "Enhancement | Rhea XL",
            "Enhancement | Theia - Fine Tune Detail",
            "Enhancement | Theia - Fine Tune Fidelity",
            "Enhancement | Themis",
        ]

        # 模型ID映射表（显示名称 -> 实际模型ID）
        cls.model_id_map = {
            # Frame Interpolation 分类
            "Frame Interpolation | Themis": "thm-2",
            "Frame Interpolation | Aion": "aion-1",
            "Frame Interpolation | Apollo": "apo-8",
            "Frame Interpolation | Apollo Fast": "apf-2",
            "Frame Interpolation | Chronos": "chr-2",
            "Frame Interpolation | Chronos Fast": "chf-3",

            # Enhancement 分类
            "Enhancement | Artemis - Aliasing or Moire": "aaa-10",
            "Enhancement | Artemis - High Quality": "ahq-12",
            "Enhancement | Artemis - Low Quality": "alq-13",
            "Enhancement | Artemis - Medium Quality": "amq-13",
            "Enhancement | Artemis - Medium Quality Strong Halo": "amqs-2",
            "Enhancement | Artemis - Low Quality Strong Halo": "alqs-2",
            "Enhancement | Computer Generated": "gcg-5",
            "Enhancement | Dione - DV": "ddv-3",
            "Enhancement | Dione - Robust": "dtd-4",
            "Enhancement | Dione - Robust Dehalo": "dtds-2",
            "Enhancement | Dione - TV": "dtv-4",
            "Enhancement | Dione - TV Dehalo": "dtvs-2",
            "Enhancement | Gaia - High Quality": "ghq-5",
            "Enhancement | Hyperion HDR": "hyp-1",
            "Enhancement | Iris": "iris-3",
            "Enhancement | Iris LQ": "iris-2",
            "Enhancement | Nyx": "nyx-3",
            "Enhancement | Nyx Fast": "nxf-1",
            "Enhancement | Proteus": "prob-4",
            "Enhancement | Proteus Fine Tune": "prob-3",
            "Enhancement | Rhea": "rhea-1",
            "Enhancement | Rhea XL": "rxl-1",
            "Enhancement | Theia - Fine Tune Detail": "thd-3",
            "Enhancement | Theia - Fine Tune Fidelity": "thf-4",
            "Enhancement | Themis": "thm-2",
        }
        return {
            "required": {
                "video": ("VIDEO", {
                    "tooltip": "输入视频文件"
                }),
                "model": (upscale_models, {
                    "default": "prob-4"
                }),
                "scale_factor": ([
                    "2x",
                    "4x",
                    "Auto",
                ], {
                    "default": "2x"
                }),
                "output_resolution": ([
                    "Auto",
                    "720p",
                    "1080p",
                    "2K",
                    "4K",
                    "8K",
                ], {
                    "default": "Auto"
                }),
                "denoise": ([
                    "Off",
                    "Low",
                    "Medium",
                    "High",
                ], {
                    "default": "Off"
                }),
                "sharpen": ([
                    "Off",
                    "Low",
                    "Medium",
                    "High",
                ], {
                    "default": "Off"
                }),
                "deinterlace": ("BOOLEAN", {
                    "default": False,
                    "label_on": "启用",
                    "label_off": "禁用"
                }),
                "frame_interpolation": ([
                    "Off",
                    "2x (60fps)",
                    "4x (120fps)",
                    "8x (240fps)",
                ], {
                    "default": "Off"
                }),
                "output_format": ([
                    "mp4",
                    "mov",
                    "avi",
                    "mkv",
                ], {
                    "default": "mp4"
                }),
                "quality": ([
                    "Low",
                    "Medium",
                    "High",
                    "Very High",
                ], {
                    "default": "High"
                }),
            },
            "optional": {
                "topaz_path": ("STRING", {
                    "default": "C:\\Program Files\\Topaz Labs LLC\\Topaz Video AI\\ffmpeg.exe",
                    "multiline": False,
                    "placeholder": "Topaz Video AI ffmpeg路径"
                }),
            }
        }
    
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("output_video", "info")
    FUNCTION = "enhance_video"
    CATEGORY = "Ken-Chen/Video-post-processing"
    OUTPUT_NODE = False
    
    def find_topaz_ffmpeg(self) -> str:
        """
        查找Topaz Video AI的ffmpeg可执行文件
        支持正式版和Beta版
        """
        possible_paths = [
            "C:\\Program Files\\Topaz Labs LLC\\Topaz Video AI BETA\\ffmpeg.exe",  # Beta版（优先）
            "C:\\Program Files\\Topaz Labs LLC\\Topaz Video AI\\ffmpeg.exe",  # 正式版
            "C:\\Program Files (x86)\\Topaz Labs LLC\\Topaz Video AI BETA\\ffmpeg.exe",
            "C:\\Program Files (x86)\\Topaz Labs LLC\\Topaz Video AI\\ffmpeg.exe",
            "/Applications/Topaz Video AI.app/Contents/MacOS/ffmpeg",
            "/usr/local/bin/ffmpeg",  # 如果安装了Topaz的ffmpeg
        ]

        for path in possible_paths:
            if os.path.exists(path):
                print(f"[Topaz] 找到ffmpeg: {path}")
                return path

        return None
    

    def get_resolution(self, resolution: str) -> Tuple[int, int]:
        """
        获取分辨率
        """
        resolution_map = {
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "2K": (2560, 1440),
            "4K": (3840, 2160),
            "8K": (7680, 4320),
        }
        return resolution_map.get(resolution, None)
    
    def enhance_video(
        self,
        video: str,
        model: str,
        scale_factor: str,
        output_resolution: str,
        denoise: str,
        sharpen: str,
        deinterlace: bool,
        frame_interpolation: str,
        output_format: str,
        quality: str,
        topaz_path: str = None,
    ) -> Tuple[str, str]:
        """
        使用Topaz Video AI增强视频
        """
        # 将显示名称转换为实际模型ID
        actual_model_id = self.model_id_map.get(model, model)
        print(f"[Topaz] 模型选择: {model} -> {actual_model_id}")

        # 验证输入
        if not video or not os.path.exists(video):
            error_msg = f"视频文件不存在: {video}"
            print(f"[Topaz] {error_msg}")
            return ("", error_msg)
        
        # 查找Topaz ffmpeg
        if not topaz_path or not os.path.exists(topaz_path):
            topaz_path = self.find_topaz_ffmpeg()
        
        if not topaz_path:
            error_msg = "未找到Topaz Video AI，请确保已安装并指定正确的路径"
            print(f"[Topaz] {error_msg}")
            return ("", error_msg)
        
        print(f"[Topaz] 使用Topaz ffmpeg: {topaz_path}")
        
        # 准备输出路径
        video_name = os.path.splitext(os.path.basename(video))[0]
        import time
        timestamp = int(time.time())
        output_path = os.path.join(self.output_dir, f"{video_name}_topaz_{timestamp}.{output_format}")
        
        # 构建Topaz Video AI命令
        # 使用ffmpeg的tvai_up滤镜
        # 使用转换后的实际模型ID

        # 构建滤镜参数
        # 参考ComfyUI-TopazVideoAI插件的参数格式
        tvai_params = [f"model={actual_model_id}"]

        # 缩放因子
        if scale_factor != "Auto":
            scale = int(scale_factor.replace("x", ""))
            tvai_params.append(f"scale={scale}")
        else:
            tvai_params.append("scale=2")  # 默认2x

        # download参数 - 允许自动下载模型
        tvai_params.append("download=1")

        # estimate参数 - 重要！参考TopazVideoAI插件
        tvai_params.append("estimate=8")

        # compression参数 - 重要！参考TopazVideoAI插件
        denoise_map = {"Off": 0.0, "Low": 0.3, "Medium": 0.5, "High": 0.7}
        compression_value = denoise_map.get(denoise, 1.0)
        tvai_params.append(f"compression={compression_value}")

        # blend参数 - 重要！参考TopazVideoAI插件
        tvai_params.append("blend=0.0")

        filter_str = f"tvai_up={':'.join(tvai_params)}"
        
        # 帧率插值
        if frame_interpolation != "Off":
            fps_map = {
                "2x (60fps)": 60,
                "4x (120fps)": 120,
                "8x (240fps)": 240,
            }
            target_fps = fps_map[frame_interpolation]
            filter_str += f",tvai_fi=fps={target_fps}"
        
        # 构建完整命令
        # 参考ComfyUI-TopazVideoAI插件，使用mpeg4编码器
        # 注意：必须使用mpeg4，hevc_nvenc会导致模型无法加载！
        cmd = [
            topaz_path,
            "-y",  # 覆盖输出文件
            "-hwaccel", "auto",  # 硬件加速
            "-i", video,
            "-vf", filter_str,
            "-c:v", "mpeg4",  # 必须使用mpeg4！
            "-q:v", "2",  # 质量参数
            "-pix_fmt", "yuv420p",  # 像素格式，提高兼容性
            "-c:a", "copy",  # 复制音频
            output_path
        ]
        
        print(f"[Topaz] 🎬 开始处理视频: {video}")
        print(f"[Topaz] 📊 模型: {model}")
        print(f"[Topaz] 📐 缩放: {scale_factor}")
        print(f"[Topaz] 🎨 分辨率: {output_resolution}")
        print(f"[Topaz] 🔧 降噪: {denoise}, 锐化: {sharpen}")
        print(f"[Topaz] 🎞️ 帧率插值: {frame_interpolation}")
        print(f"[Topaz] 💻 命令: {' '.join(cmd)}")
        print(f"[Topaz] ⏱️ Topaz Video AI处理可能需要较长时间，请耐心等待...")
        
        # 创建进度条
        pbar = ProgressBar(100)
        pbar.update_absolute(0, 100)

        # 设置环境变量（Beta版本需要）
        env = os.environ.copy()

        # 检测Beta版本并设置模型目录
        if "BETA" in topaz_path.upper():
            beta_model_dir = r"C:\ProgramData\Topaz Labs LLC\Topaz Video AI Beta\models"
            if os.path.exists(beta_model_dir):
                env["TVAI_MODEL_DIR"] = beta_model_dir
                print(f"[Topaz] 🔧 设置Beta版本模型目录: {beta_model_dir}")

        try:
            # 执行Topaz Video AI
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',  # 明确指定 UTF-8 编码
                errors='replace',  # 遇到无法解码的字符时替换为 �
                env=env  # 传递环境变量
            )

            # 实时打印输出并更新进度
            print(f"[Topaz] 📺 实时输出:")
            print("-" * 60)

            progress = 0
            try:
                for line in process.stdout:
                    # 安全地打印输出（处理可能的编码问题）
                    try:
                        print(line.rstrip())
                    except UnicodeEncodeError:
                        # 如果打印失败，使用 ASCII 安全模式
                        print(line.encode('ascii', errors='replace').decode('ascii').rstrip())

                    # 根据输出更新进度条
                    if "frame=" in line:
                        progress = min(progress + 1, 90)
                        pbar.update_absolute(progress, 100)
            except UnicodeDecodeError as e:
                print(f"[Topaz] ⚠️ 输出解码错误: {e}")
                print(f"[Topaz] 💡 继续处理，但部分输出可能无法显示")
            
            process.wait()
            print("-" * 60)
            
            pbar.update_absolute(100, 100)
            
            if process.returncode != 0:
                error_msg = f"Topaz Video AI处理失败，返回码: {process.returncode}"
                print(f"[Topaz] {error_msg}")
                return ("", error_msg)
            
            if not os.path.exists(output_path):
                error_msg = "输出文件未生成"
                print(f"[Topaz] {error_msg}")
                return ("", error_msg)
            
            # 构建信息字符串
            info_parts = ["✅ Topaz Video AI处理成功！"]
            info_parts.append(f"模型: {model}")
            info_parts.append(f"缩放: {scale_factor}")
            if output_resolution != "Auto":
                info_parts.append(f"分辨率: {output_resolution}")
            if denoise != "Off":
                info_parts.append(f"降噪: {denoise}")
            if sharpen != "Off":
                info_parts.append(f"锐化: {sharpen}")
            if frame_interpolation != "Off":
                info_parts.append(f"帧率插值: {frame_interpolation}")
            info_parts.append(f"输出: {output_path}")
            info = "\n".join(info_parts)
            
            print(f"[Topaz] {info}")
            return (output_path, info)
            
        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            print(f"[Topaz] {error_msg}")
            import traceback
            traceback.print_exc()
            return ("", error_msg)
