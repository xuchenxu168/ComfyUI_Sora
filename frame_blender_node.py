"""
FrameBlender节点 - 多帧混合/时间平均
用于生成水印mask、背景提取、艺术效果等
"""

import os
import cv2
import numpy as np
import torch
from typing import Tuple, List, Optional
import folder_paths


class FrameBlender:
    """
    帧混合器节点
    
    功能：
    - 从视频中提取指定帧
    - 以可调透明度混合多帧
    - 支持多种混合模式
    - 输出ComfyUI IMAGE张量和可选MASK
    """
    
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO", {
                    "tooltip": "视频文件路径"
                }),
                "frame_selection_mode": (["manual", "range", "interval", "all"], {
                    "default": "interval",
                    "tooltip": "帧选择模式：manual=手动指定, range=范围, interval=间隔采样, all=全部帧"
                }),
                "blend_mode": (["average", "max", "min", "median", "weighted"], {
                    "default": "average",
                    "tooltip": "混合模式：average=平均, max=最大值(检测水印), min=最小值, median=中位数(背景提取), weighted=加权平均"
                }),
                "opacity": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "tooltip": "每帧的透明度/混合强度（仅average模式使用）"
                }),
                "normalize": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否归一化到0-255范围"
                }),
                "output_mask": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否输出二值化mask（用于ProPainter）"
                }),
            },
            "optional": {
                "frame_indices": ("STRING", {
                    "default": "1,10,20,30",
                    "tooltip": "手动指定帧号（逗号分隔），如：1,10,20,30（manual模式使用）"
                }),
                "frame_range_start": ("INT", {
                    "default": 1,
                    "min": 1,
                    "tooltip": "起始帧号（range模式使用）"
                }),
                "frame_range_end": ("INT", {
                    "default": 100,
                    "min": 1,
                    "tooltip": "结束帧号（range模式使用）"
                }),
                "frame_interval": ("INT", {
                    "default": 10,
                    "min": 1,
                    "tooltip": "帧间隔（interval模式：每N帧取1帧）"
                }),
                "mask_threshold": ("INT", {
                    "default": 128,
                    "min": 0,
                    "max": 255,
                    "tooltip": "mask二值化阈值（output_mask=True时使用）"
                }),
                "weight_mode": (["linear", "exponential", "gaussian"], {
                    "default": "linear",
                    "tooltip": "加权模式（weighted混合模式使用）：linear=线性, exponential=指数, gaussian=高斯"
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "info")
    FUNCTION = "blend_frames"
    CATEGORY = "Ken-Chen/sora"
    
    def parse_frame_indices(
        self,
        mode: str,
        total_frames: int,
        manual_indices: str = "",
        range_start: int = 1,
        range_end: int = 100,
        interval: int = 10
    ) -> List[int]:
        """
        解析帧索引
        
        Returns:
            帧索引列表（0-based）
        """
        if mode == "manual":
            # 手动指定：1,10,20,30
            indices = []
            for idx_str in manual_indices.split(","):
                idx_str = idx_str.strip()
                if idx_str:
                    idx = int(idx_str) - 1  # 转换为0-based
                    if 0 <= idx < total_frames:
                        indices.append(idx)
            return sorted(set(indices))
        
        elif mode == "range":
            # 范围：1-100
            start = max(0, range_start - 1)  # 转换为0-based
            end = min(total_frames, range_end)
            return list(range(start, end))
        
        elif mode == "interval":
            # 间隔：每10帧取1帧
            return list(range(0, total_frames, interval))
        
        else:  # all
            # 全部帧
            return list(range(total_frames))
    
    def generate_weights(self, num_frames: int, mode: str) -> np.ndarray:
        """
        生成加权系数
        
        Args:
            num_frames: 帧数量
            mode: 加权模式
        
        Returns:
            归一化的权重数组
        """
        if mode == "linear":
            # 线性增长：后面的帧权重更高
            weights = np.linspace(1, num_frames, num_frames)
        elif mode == "exponential":
            # 指数增长
            weights = np.exp(np.linspace(0, 2, num_frames))
        elif mode == "gaussian":
            # 高斯分布：中间帧权重最高
            center = num_frames / 2
            sigma = num_frames / 4
            x = np.arange(num_frames)
            weights = np.exp(-((x - center) ** 2) / (2 * sigma ** 2))
        else:
            # 默认均匀权重
            weights = np.ones(num_frames)
        
        # 归一化
        return weights / weights.sum()
    
    def blend_frames(
        self,
        video: str,
        frame_selection_mode: str,
        blend_mode: str,
        opacity: float,
        normalize: bool,
        output_mask: bool,
        frame_indices: str = "1,10,20,30",
        frame_range_start: int = 1,
        frame_range_end: int = 100,
        frame_interval: int = 10,
        mask_threshold: int = 128,
        weight_mode: str = "linear"
    ) -> Tuple[torch.Tensor, torch.Tensor, str]:
        """
        混合视频帧
        """
        print("\n" + "="*70)
        print("🎨 FrameBlender - 多帧混合")
        print("="*70)
        
        # 检查视频文件
        if not os.path.exists(video):
            raise FileNotFoundError(f"视频文件不存在: {video}")
        
        # 打开视频
        cap = cv2.VideoCapture(video)
        if not cap.isOpened():
            raise Exception(f"无法打开视频: {video}")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        print(f"[FrameBlender] 视频信息:")
        print(f"  - 分辨率: {width}x{height}")
        print(f"  - 总帧数: {total_frames}")
        print(f"  - 帧率: {fps:.2f} fps")
        
        # 解析要提取的帧
        selected_indices = self.parse_frame_indices(
            frame_selection_mode,
            total_frames,
            frame_indices,
            frame_range_start,
            frame_range_end,
            frame_interval
        )
        
        if not selected_indices:
            cap.release()
            raise Exception("没有选择任何帧！")
        
        print(f"[FrameBlender] 帧选择模式: {frame_selection_mode}")
        print(f"[FrameBlender] 选中帧数: {len(selected_indices)}")
        print(f"[FrameBlender] 帧索引: {selected_indices[:10]}{'...' if len(selected_indices) > 10 else ''}")
        
        # 提取选中的帧
        frames = []
        for idx in selected_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                # BGR转RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame.astype(np.float32))
            else:
                print(f"[FrameBlender] ⚠️ 无法读取帧 {idx}")
        
        cap.release()
        
        if not frames:
            raise Exception("没有成功读取任何帧！")
        
        print(f"[FrameBlender] ✅ 成功读取 {len(frames)} 帧")
        
        # 转换为numpy数组
        frames_array = np.array(frames)  # shape: (N, H, W, 3)
        
        # 混合帧
        print(f"[FrameBlender] 混合模式: {blend_mode}")
        
        if blend_mode == "average":
            # 平均混合（考虑透明度）
            result = frames_array[0] * opacity
            for i in range(1, len(frames_array)):
                result = result * (1 - opacity) + frames_array[i] * opacity
            
        elif blend_mode == "max":
            # 最大值投影（适合检测水印）
            result = np.max(frames_array, axis=0)
            
        elif blend_mode == "min":
            # 最小值投影
            result = np.min(frames_array, axis=0)
            
        elif blend_mode == "median":
            # 中位数（适合背景提取）
            result = np.median(frames_array, axis=0)
            
        elif blend_mode == "weighted":
            # 加权平均
            weights = self.generate_weights(len(frames_array), weight_mode)
            print(f"[FrameBlender] 加权模式: {weight_mode}")
            print(f"[FrameBlender] 权重: {weights[:5]}{'...' if len(weights) > 5 else ''}")
            result = np.average(frames_array, axis=0, weights=weights)
        
        else:
            # 默认简单平均
            result = np.mean(frames_array, axis=0)
        
        # 归一化
        if normalize:
            result = np.clip(result, 0, 255)
        
        result = result.astype(np.uint8)
        
        print(f"[FrameBlender] ✅ 混合完成")
        print(f"[FrameBlender] 输出形状: {result.shape}")
        
        # 转换为ComfyUI IMAGE张量 (1, H, W, 3)，范围0-1
        image_tensor = torch.from_numpy(result).float() / 255.0
        image_tensor = image_tensor.unsqueeze(0)  # 添加batch维度
        
        # 生成mask（如果需要）
        if output_mask:
            # 转换为灰度
            gray = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
            # 二值化
            _, mask_binary = cv2.threshold(gray, mask_threshold, 255, cv2.THRESH_BINARY)
            # 转换为ComfyUI MASK张量 (1, H, W)，范围0-1
            mask_tensor = torch.from_numpy(mask_binary).float() / 255.0
            mask_tensor = mask_tensor.unsqueeze(0)
            print(f"[FrameBlender] ✅ 生成mask (阈值: {mask_threshold})")
        else:
            # 空mask
            mask_tensor = torch.zeros((1, height, width), dtype=torch.float32)
        
        # 生成信息
        info = f"""
帧混合完成：
- 视频: {os.path.basename(video)}
- 分辨率: {width}x{height}
- 总帧数: {total_frames}
- 选择模式: {frame_selection_mode}
- 选中帧数: {len(selected_indices)}
- 混合模式: {blend_mode}
- 透明度: {opacity:.2f}
- 归一化: {normalize}
- 输出mask: {output_mask}
        """
        
        if blend_mode == "weighted":
            info += f"- 加权模式: {weight_mode}\n"
        
        print("[FrameBlender] ✅ 处理完成！")
        
        return (image_tensor, mask_tensor, info.strip())


# 注册节点
NODE_CLASS_MAPPINGS = {
    "FrameBlender": FrameBlender
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrameBlender": "🎨 Frame Blender"
}

