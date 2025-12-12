"""
ComfyUI_Sora - 工具函数模块
提供图像/视频转换、下载、格式处理等核心功能
"""

import os
import io
import json
import base64
import tempfile
import requests
import numpy as np
import torch
from PIL import Image
from typing import List, Union, Optional, Tuple, Any
import cv2
import folder_paths


def pil2tensor(image: Union[Image.Image, List[Image.Image]]) -> torch.Tensor:
    """
    将PIL图像转换为ComfyUI张量格式
    
    Args:
        image: 单个PIL图像或PIL图像列表
        
    Returns:
        torch.Tensor: 形状为[B, H, W, 3]的张量，值范围[0, 1]
    """
    if isinstance(image, list):
        if len(image) == 0:
            return torch.empty(0)
        return torch.cat([pil2tensor(img) for img in image], dim=0)
    
    # 转换为RGB模式
    if image.mode == 'RGBA':
        # 创建白色背景
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # 转换为numpy数组并归一化到[0, 1]
    img_array = np.array(image).astype(np.float32) / 255.0
    
    # 返回形状为[1, H, W, 3]的张量
    return torch.from_numpy(img_array)[None,]


def tensor2pil(image: torch.Tensor) -> List[Image.Image]:
    """
    将ComfyUI张量转换为PIL图像列表
    
    Args:
        image: 形状为[B, H, W, 3]或[H, W, 3]的张量，值范围[0, 1]
        
    Returns:
        List[Image.Image]: PIL图像列表
    """
    batch_count = image.size(0) if len(image.shape) > 3 else 1
    if batch_count > 1:
        out = []
        for i in range(batch_count):
            out.extend(tensor2pil(image[i]))
        return out
    
    # 转换为numpy数组，缩放到[0, 255]并裁剪
    numpy_image = np.clip(255.0 * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8)
    
    # 转换为PIL图像
    return [Image.fromarray(numpy_image)]


def image_to_base64(image: Union[Image.Image, torch.Tensor], format: str = "PNG") -> str:
    """
    将图像转换为base64编码字符串
    
    Args:
        image: PIL图像或ComfyUI张量
        format: 图像格式，默认PNG
        
    Returns:
        str: base64编码的图像字符串（包含data URI前缀）
    """
    if isinstance(image, torch.Tensor):
        image = tensor2pil(image)[0]
    
    buffered = io.BytesIO()
    image.save(buffered, format=format)
    image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    return f"data:image/{format.lower()};base64,{image_base64}"


def download_image(url: str, timeout: int = 60) -> Image.Image:
    """
    从URL下载图像
    
    Args:
        url: 图像URL
        timeout: 超时时间（秒）
        
    Returns:
        Image.Image: PIL图像
    """
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    
    image = Image.open(io.BytesIO(response.content))
    
    # 转换为RGB
    if image.mode == 'RGBA':
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    return image


def download_video(url: str, output_path: Optional[str] = None, timeout: int = 300) -> str:
    """
    从URL下载视频
    
    Args:
        url: 视频URL
        output_path: 输出路径，如果为None则创建临时文件
        timeout: 超时时间（秒）
        
    Returns:
        str: 下载的视频文件路径
    """
    if output_path is None:
        # 从URL获取文件扩展名
        ext = url.split('?')[0].split('.')[-1]
        if ext not in ['mp4', 'webm', 'mov', 'avi']:
            ext = 'mp4'
        
        # 创建临时文件
        temp_dir = folder_paths.get_temp_directory()
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(temp_dir, f"sora_video_{os.urandom(8).hex()}.{ext}")
    
    # 下载视频
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    
    return output_path


def get_video_info(video_path: str) -> dict:
    """
    获取视频信息
    
    Args:
        video_path: 视频文件路径
        
    Returns:
        dict: 包含width, height, fps, frame_count等信息
    """
    cap = cv2.VideoCapture(video_path)
    
    info = {
        'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        'fps': cap.get(cv2.CAP_PROP_FPS),
        'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    
    cap.release()
    
    return info


def resize_image(image: Image.Image, target_size: Tuple[int, int], mode: str = "contain") -> Image.Image:
    """
    调整图像大小
    
    Args:
        image: PIL图像
        target_size: 目标尺寸(width, height)
        mode: 调整模式，"contain"保持比例填充，"cover"保持比例裁剪，"stretch"拉伸
        
    Returns:
        Image.Image: 调整后的图像
    """
    target_w, target_h = target_size
    
    if mode == "stretch":
        return image.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    # 计算缩放比例
    img_w, img_h = image.size
    scale_w = target_w / img_w
    scale_h = target_h / img_h
    
    if mode == "contain":
        # 保持比例，完整显示图像
        scale = min(scale_w, scale_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        
        # 调整大小
        resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 创建目标尺寸的画布并居中粘贴
        result = Image.new('RGB', (target_w, target_h), (0, 0, 0))
        paste_x = (target_w - new_w) // 2
        paste_y = (target_h - new_h) // 2
        result.paste(resized, (paste_x, paste_y))
        
        return result
    
    elif mode == "cover":
        # 保持比例，填满画布
        scale = max(scale_w, scale_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        
        # 调整大小
        resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 居中裁剪
        crop_x = (new_w - target_w) // 2
        crop_y = (new_h - target_h) // 2
        result = resized.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))
        
        return result
    
    else:
        raise ValueError(f"Unknown resize mode: {mode}")


def get_aspect_ratio_size(aspect_ratio: str, quality: str = "1080p") -> Tuple[int, int]:
    """
    根据宽高比和质量获取视频尺寸

    Args:
        aspect_ratio: 宽高比，如"16:9", "9:16", "1:1", "4:3"等
        quality: 质量级别，"720p", "1080p", "2k", "4k"

    Returns:
        Tuple[int, int]: (width, height)
    """
    # 解析宽高比
    parts = aspect_ratio.split(':')
    if len(parts) != 2:
        raise ValueError(f"Invalid aspect ratio: {aspect_ratio}")

    ratio_w = float(parts[0])
    ratio_h = float(parts[1])

    # 根据质量确定基准分辨率
    quality_resolutions = {
        "720p": 720,
        "1080p": 1080,
    }

    base_resolution = quality_resolutions.get(quality, 1080)

    # 判断是横屏还是竖屏
    if ratio_w > ratio_h:
        # 横屏 (如 16:9)：宽度较大，高度为基准
        height = base_resolution
        width = int(height * ratio_w / ratio_h)
    else:
        # 竖屏 (如 9:16)：高度较大，宽度为基准
        width = base_resolution
        height = int(width * ratio_h / ratio_w)

    # 确保是8的倍数（视频编码要求）
    width = (width // 8) * 8
    height = (height // 8) * 8

    return (width, height)


def format_duration(seconds: float) -> str:
    """
    格式化时长为可读字符串
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化的时长字符串
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}分{secs}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}小时{minutes}分"

