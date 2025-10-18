"""
ComfyUI_Sora - Sora视频生成节点集合
支持文生视频和图生视频，提供高质量的横版和竖版视频生成能力
"""

from .sora_text2video import SoraText2Video
from .sora_image2video import SoraImage2Video
from .topaz_video_ai_node import KenChenTopazVideoEnhancer
from .frame_blender_node import FrameBlender
from .video_watermark_node import VideoWatermark
from .video_watermark_advanced_node import VideoWatermarkAdvanced


# 节点类映射
NODE_CLASS_MAPPINGS = {
    "SoraText2Video": SoraText2Video,
    "SoraImage2Video": SoraImage2Video,
    "KenChenTopazVideoEnhancer": KenChenTopazVideoEnhancer,
    "FrameBlender": FrameBlender,
    "VideoWatermark": VideoWatermark,
    "VideoWatermarkAdvanced": VideoWatermarkAdvanced,
}

# 节点显示名称映射
NODE_DISPLAY_NAME_MAPPINGS = {
    "SoraText2Video": "🎬 Sora 文生视频",
    "SoraImage2Video": "🖼️ Sora 图生视频",
    "KenChenTopazVideoEnhancer": "🎨 Topaz 视频增强",
    "FrameBlender": "🎨 Frame Blender (帧混合器)",
    "VideoWatermark": "🎨 Video Watermark (视频水印)",
    "VideoWatermarkAdvanced": "🎯 Video Watermark Advanced (高级水印)",
}

# 导出
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']


# 打印加载信息
print("=" * 80)
print("ComfyUI_Sora Nodes Loaded Successfully!")
print("=" * 80)
print("Available Nodes:")
print("  * Sora Text2Video - Generate high-quality videos from text")
print("  * Sora Image2Video - Generate dynamic videos from images")
print("  * Topaz Video Enhancer - Professional video upscaling and enhancement")
print("  * Frame Blender - Multi-frame blending and temporal averaging")
print("  * Video Watermark - Add dynamic watermarks to videos")
print("  * Video Watermark Advanced - Target tracking, anti-occlusion, batch processing")
print("")
print("Features:")
print("  + Multiple aspect ratios (16:9 landscape, 9:16 portrait)")
print("  + Multiple qualities (720p, 1080p, 2K, 4K)")
print("  + Duration control (5s, 10s, 15s)")
print("  + Style control (cinematic, realistic, anime, 3D, etc.)")
print("  + Motion control (direction, intensity)")
print("  + Seed control (reproducible)")
print("  + Professional video upscaling (Topaz Video Enhancer)")
print("  + Dynamic watermarks with animations and effects")
print("=" * 80)
print("")

