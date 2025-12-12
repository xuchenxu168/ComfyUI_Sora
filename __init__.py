# Definitive Manual Registration Scheme V6
# This uses the EXACT class name 'KenChenTopazVideoEnhancer' found in the file.
# Disables 'SoraMultiImage2Video' and 'TextEffects' to allow system boot.

# Sora Core
from .sora_text2video import SoraText2Video
from .sora_image2video import SoraImage2Video
from .storyboard_character import StoryboardCharacter
from .sora_batch_video import SoraBatchVideo
# from .sora_multi_image2video import MultiImage2Video # DISABLED

# Aabao Nodes
from .aabao_text2video import AabaoText2Video
from .aabao_image2video import AabaoImage2Video
from .aabao_character import AabaoCharacter
from .aabao_storyboard import AabaoStoryboard
from .aabao_image_gen import AabaoImageGen
from .aabao_image_edit import AabaoImageEdit
from .aabao_remix import AabaoRemix

# Auxiliary Nodes
from .video_watermark_node import VideoWatermark
from .video_watermark_advanced_node import VideoWatermarkAdvanced
from .frame_blender_node import FrameBlender
from .grok_imagine import GrokImagineNode
# from .text_effects import TextEffects # DISABLED

# Topaz Restore - EXPLICIT IMPORT
try:
    from .topaz_video_ai_node import KenChenTopazVideoEnhancer
    TopazAvailable = True
except ImportError as e:
    print(f"Failed to load Topaz Node: {e}")
    KenChenTopazVideoEnhancer = None
    TopazAvailable = False

# Attempt to load WriteNode safely
try:
    from .write_node import WriteNode
except ImportError:
    try:
         from .write_node import SoraWriteNode as WriteNode
    except:
         WriteNode = None

NODE_CLASS_MAPPINGS = {
    # Sora
    "SoraText2Video": SoraText2Video,
    "SoraImage2Video": SoraImage2Video,
    "StoryboardCharacter": StoryboardCharacter,
    "SoraBatchVideo": SoraBatchVideo,
    # "SoraMultiImage2Video": MultiImage2Video,
    
    # Aabao
    "AabaoText2Video": AabaoText2Video,
    "AabaoImage2Video": AabaoImage2Video,
    "AabaoCharacter": AabaoCharacter,
    "AabaoStoryboard": AabaoStoryboard,
    "AabaoImageGen": AabaoImageGen,
    "AabaoImageEdit": AabaoImageEdit,
    "AabaoVideoRemix": AabaoRemix,
    
    # Aux
    "VideoWatermark": VideoWatermark,
    "VideoWatermarkAdvanced": VideoWatermarkAdvanced,
    "FrameBlender": FrameBlender,
    "GrokImagineNode": GrokImagineNode,
    # "TextEffects": TextEffects,
}

if TopazAvailable and KenChenTopazVideoEnhancer:
    NODE_CLASS_MAPPINGS["KenChenTopazVideoEnhancer"] = KenChenTopazVideoEnhancer
    # Alias standard name too just in case
    NODE_CLASS_MAPPINGS["TopazVideoEnhancer"] = KenChenTopazVideoEnhancer

if WriteNode:
    NODE_CLASS_MAPPINGS["WriteNode"] = WriteNode


NODE_DISPLAY_NAME_MAPPINGS = {
    "SoraText2Video": "Sora 文生视频",
    "SoraImage2Video": "Sora 图生视频",
    "StoryboardCharacter": "Storyboard-Character",
    "SoraBatchVideo": "Sora Batch Video Generator",
    # "SoraMultiImage2Video": "Sora 多图生视频",
    
    "AabaoText2Video": "Aabao 文生视频",
    "AabaoImage2Video": "Aabao 图生视频",
    "AabaoCharacter": "Aabao 角色创建",
    "AabaoStoryboard": "Aabao 故事板",
    "AabaoImageGen": "Aabao 图像生成",
    "AabaoImageEdit": "Aabao 图像编辑",
    "AabaoVideoRemix": "Aabao 视频重绘",
    
    "VideoWatermark": "Video Watermark (视频水印)",
    "VideoWatermarkAdvanced": "Video Watermark Advanced (高级水印)",
    "FrameBlender": "Frame Blender",
    "GrokImagineNode": "Grok Imagine 视频生成",
    # "TextEffects": "Text Effects",
}

if TopazAvailable:
    NODE_DISPLAY_NAME_MAPPINGS["KenChenTopazVideoEnhancer"] = "Topaz Video Enhance AI"
    NODE_DISPLAY_NAME_MAPPINGS["TopazVideoEnhancer"] = "Topaz Video Enhance AI"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
