"""
VideoWatermark节点 - 动态视频水印
支持文字、图片水印，多种动态效果
"""

import os
import cv2
import numpy as np
import torch
from typing import Tuple, Optional, List
from PIL import Image, ImageDraw, ImageFont
import tempfile
import subprocess


class VideoWatermark:
    """
    视频水印节点
    
    功能：
    - 文字水印（自定义内容、字体、颜色、大小）
    - 图片水印（Logo、PNG透明图）
    - 位置调整（9宫格 + 自定义坐标）
    - 透明度调整
    - 动态效果（移动、淡入淡出、旋转、缩放、闪烁）
    - 多个水印同时添加
    - 时间控制（水印出现/消失时间）
    """
    
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO", {
                    "tooltip": "输入视频"
                }),
                "watermark_type": (["text", "image", "both"], {
                    "default": "text",
                    "tooltip": "水印类型：text=文字, image=图片, both=文字+图片"
                }),
                "enable_watermark": ("BOOLEAN", {
                    "default": True,
                    "label_on": "启用",
                    "label_off": "禁用",
                    "tooltip": "是否添加水印"
                }),
            },
            "optional": {
                # 文字水印参数
                "text_content": ("STRING", {
                    "default": "© 2025 Your Brand",
                    "multiline": False,
                    "tooltip": "水印文字内容"
                }),
                "font_size": ("INT", {
                    "default": 48,
                    "min": 12,
                    "max": 200,
                    "tooltip": "字体大小"
                }),
                "font_color": (["white", "black", "red", "green", "blue", "yellow", "cyan", "magenta", "custom"], {
                    "default": "white",
                    "tooltip": "字体颜色"
                }),
                "custom_color_r": ("INT", {
                    "default": 255,
                    "min": 0,
                    "max": 255,
                    "tooltip": "自定义颜色R（font_color=custom时使用）"
                }),
                "custom_color_g": ("INT", {
                    "default": 255,
                    "min": 0,
                    "max": 255,
                    "tooltip": "自定义颜色G"
                }),
                "custom_color_b": ("INT", {
                    "default": 255,
                    "min": 0,
                    "max": 255,
                    "tooltip": "自定义颜色B"
                }),
                "text_position": (["top_left", "top_center", "top_right", 
                                   "center_left", "center", "center_right",
                                   "bottom_left", "bottom_center", "bottom_right", "custom"], {
                    "default": "bottom_right",
                    "tooltip": "文字位置"
                }),
                "text_opacity": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "文字透明度"
                }),
                
                # 图片水印参数
                "watermark_image": ("IMAGE", {
                    "tooltip": "水印图片（可连接Load Image）"
                }),
                "auto_remove_bg": ("BOOLEAN", {
                    "default": False,
                    "label_on": "自动抠图",
                    "label_off": "保持原样",
                    "tooltip": "自动移除纯色背景（白底、黑底等）"
                }),
                "bg_color_mode": (["white", "black", "auto"], {
                    "default": "white",
                    "tooltip": "背景颜色模式"
                }),
                "bg_threshold": ("INT", {
                    "default": 240,
                    "min": 0,
                    "max": 255,
                    "tooltip": "背景检测阈值（越高越严格）"
                }),
                "image_position": (["top_left", "top_center", "top_right",
                                    "center_left", "center", "center_right",
                                    "bottom_left", "bottom_center", "bottom_right", "custom"], {
                    "default": "top_right",
                    "tooltip": "图片位置"
                }),
                "image_scale": ("FLOAT", {
                    "default": 0.15,
                    "min": 0.01,
                    "max": 1.0,
                    "step": 0.01,
                    "tooltip": "图片缩放比例（相对视频宽度）"
                }),
                "image_opacity": ("FLOAT", {
                    "default": 0.8,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "图片透明度"
                }),
                "combined_layout": (["text_above_image", "text_below_image", "text_left_image", "text_right_image", "separate"], {
                    "default": "text_below_image",
                    "tooltip": "文字和图片组合布局（仅当watermark_type=both时生效）"
                }),
                "combined_spacing": ("INT", {
                    "default": 10,
                    "min": 0,
                    "max": 100,
                    "tooltip": "文字和图片之间的间距（像素）"
                }),

                # 位置微调
                "margin_x": ("INT", {
                    "default": 20,
                    "min": 0,
                    "max": 500,
                    "tooltip": "水平边距（像素）"
                }),
                "margin_y": ("INT", {
                    "default": 20,
                    "min": 0,
                    "max": 500,
                    "tooltip": "垂直边距（像素）"
                }),
                "custom_x": ("INT", {
                    "default": 100,
                    "min": 0,
                    "max": 3840,
                    "tooltip": "自定义X坐标（position=custom时使用）"
                }),
                "custom_y": ("INT", {
                    "default": 100,
                    "min": 0,
                    "max": 2160,
                    "tooltip": "自定义Y坐标"
                }),
                
                # 动态效果
                "animation": (["none", "fade_in", "fade_out", "fade_in_out",
                               "move_horizontal", "move_vertical", "move_diagonal",
                               "rotate", "scale", "blink", "slide_in", "slide_out",
                               "bounce", "pulse", "swing", "wave", "glint",
                               "breathe", "shake", "flip", "rainbow", "typewriter"], {
                    "default": "none",
                    "tooltip": "动画效果 - 新增10种吸引眼球的效果"
                }),
                "animation_duration": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.1,
                    "max": 10.0,
                    "step": 0.1,
                    "tooltip": "动画持续时间（秒）"
                }),
                "move_direction": (["left_to_right", "right_to_left", 
                                    "top_to_bottom", "bottom_to_top",
                                    "diagonal_tl_br", "diagonal_tr_bl"], {
                    "default": "left_to_right",
                    "tooltip": "移动方向"
                }),
                "rotation_speed": ("FLOAT", {
                    "default": 30.0,
                    "min": 1.0,
                    "max": 360.0,
                    "tooltip": "旋转速度（度/秒）"
                }),
                "scale_range_min": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "缩放最小值"
                }),
                "scale_range_max": ("FLOAT", {
                    "default": 1.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "缩放最大值"
                }),
                "blink_frequency": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.1,
                    "max": 10.0,
                    "step": 0.1,
                    "tooltip": "闪烁频率（次/秒）"
                }),
                
                # 时间控制
                "start_time": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 3600.0,
                    "step": 0.1,
                    "tooltip": "水印开始时间（秒）"
                }),
                "end_time": ("FLOAT", {
                    "default": -1.0,
                    "min": -1.0,
                    "max": 3600.0,
                    "step": 0.1,
                    "tooltip": "水印结束时间（秒，-1表示到视频结束）"
                }),
                
                # 高级选项
                "add_shadow": ("BOOLEAN", {
                    "default": True,
                    "label_on": "添加阴影",
                    "label_off": "无阴影",
                    "tooltip": "为文字添加阴影效果"
                }),
                "shadow_offset": ("INT", {
                    "default": 2,
                    "min": 0,
                    "max": 10,
                    "tooltip": "阴影偏移（像素）"
                }),
                "add_outline": ("BOOLEAN", {
                    "default": False,
                    "label_on": "添加描边",
                    "label_off": "无描边",
                    "tooltip": "为文字添加描边"
                }),

                # 多位置功能 ⭐ 新增
                "enable_multi_position": ("BOOLEAN", {
                    "default": False,
                    "label_on": "启用多位置",
                    "label_off": "单一位置",
                    "tooltip": "水印在多个位置之间切换"
                }),
                "multi_position_preset": (["custom", "four_corners", "top_bottom", "left_right", "all_edges", "all_nine", "diagonal", "horizontal_three", "vertical_three", "left_three", "right_three"], {
                    "default": "four_corners",
                    "tooltip": "多位置预设方案"
                }),
                "position_list": ("STRING", {
                    "default": "top_left,top_right,bottom_left,bottom_right",
                    "tooltip": "自定义位置列表（仅当preset=custom时使用）"
                }),
                "position_switch_interval": ("FLOAT", {
                    "default": 3.0,
                    "min": 0.5,
                    "max": 30.0,
                    "step": 0.5,
                    "tooltip": "位置切换间隔（秒）"
                }),
                "outline_width": ("INT", {
                    "default": 2,
                    "min": 1,
                    "max": 10,
                    "tooltip": "描边宽度"
                }),
            }
        }
    
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("video", "info")
    FUNCTION = "add_watermark"
    CATEGORY = "Ken-Chen/sora"
    
    def get_color(self, color_name: str, custom_r: int, custom_g: int, custom_b: int) -> Tuple[int, int, int]:
        """获取颜色RGB值"""
        colors = {
            "white": (255, 255, 255),
            "black": (0, 0, 0),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "yellow": (255, 255, 0),
            "cyan": (0, 255, 255),
            "magenta": (255, 0, 255),
            "custom": (custom_r, custom_g, custom_b)
        }
        return colors.get(color_name, (255, 255, 255))

    def remove_background(
        self,
        image: np.ndarray,
        bg_color_mode: str,
        threshold: int
    ) -> np.ndarray:
        """自动移除纯色背景，生成透明图片"""
        # 确保是RGB格式
        if image.shape[2] == 4:
            image = image[:, :, :3]

        h, w = image.shape[:2]

        # 确定背景颜色
        if bg_color_mode == "white":
            # 白色背景
            bg_color = np.array([255, 255, 255])
        elif bg_color_mode == "black":
            # 黑色背景
            bg_color = np.array([0, 0, 0])
        else:  # auto
            # 自动检测：使用四个角的平均颜色
            corners = [
                image[0, 0],
                image[0, w-1],
                image[h-1, 0],
                image[h-1, w-1]
            ]
            bg_color = np.mean(corners, axis=0).astype(np.uint8)
            print(f"[VideoWatermark] 自动检测背景颜色: RGB{tuple(bg_color)}")

        # 计算每个像素与背景颜色的差异
        diff = np.abs(image.astype(np.float32) - bg_color.astype(np.float32))
        diff_max = np.max(diff, axis=2)  # 取三个通道中的最大差异

        # 创建alpha通道：差异小的像素（接近背景色）设为透明
        # threshold越高，越容易判定为背景（更宽松）
        alpha = np.where(diff_max <= (255 - threshold), 0, 255).astype(np.uint8)

        # 边缘羽化（可选，使边缘更平滑）
        alpha = cv2.GaussianBlur(alpha, (3, 3), 0)

        # 合并RGB和Alpha
        rgba = np.dstack([image, alpha])

        # 统计透明像素
        transparent_pixels = np.sum(alpha == 0)
        total_pixels = h * w
        transparent_ratio = transparent_pixels / total_pixels * 100

        print(f"[VideoWatermark] 抠图完成:")
        print(f"  - 背景模式: {bg_color_mode}")
        print(f"  - 背景颜色: RGB{tuple(bg_color)}")
        print(f"  - 阈值: {threshold}")
        print(f"  - 透明像素: {transparent_pixels}/{total_pixels} ({transparent_ratio:.1f}%)")

        return rgba

    def get_multi_position_preset(self, preset: str) -> str:
        """获取多位置预设方案"""
        presets = {
            "four_corners": "top_left,top_right,bottom_left,bottom_right",
            "top_bottom": "top_center,bottom_center",
            "left_right": "center_left,center_right",
            "all_edges": "top_left,top_center,top_right,center_right,bottom_right,bottom_center,bottom_left,center_left",
            "all_nine": "top_left,top_center,top_right,center_left,center,center_right,bottom_left,bottom_center,bottom_right",
            "diagonal": "top_left,bottom_right,top_right,bottom_left",
            "horizontal_three": "top_left,top_center,top_right",
            "vertical_three": "top_center,center,bottom_center",
            "left_three": "top_left,center_right,bottom_left",  # Z字形：左上→右中→左下
            "right_three": "top_right,center_left,bottom_right",  # Z字形：右上→左中→右下
        }
        return presets.get(preset, "")

    def calculate_position(
        self,
        position: str,
        frame_width: int,
        frame_height: int,
        watermark_width: int,
        watermark_height: int,
        margin_x: int,
        margin_y: int,
        custom_x: int,
        custom_y: int
    ) -> Tuple[int, int]:
        """计算水印位置"""
        if position == "custom":
            return (custom_x, custom_y)
        
        positions = {
            "top_left": (margin_x, margin_y),
            "top_center": ((frame_width - watermark_width) // 2, margin_y),
            "top_right": (frame_width - watermark_width - margin_x, margin_y),
            "center_left": (margin_x, (frame_height - watermark_height) // 2),
            "center": ((frame_width - watermark_width) // 2, (frame_height - watermark_height) // 2),
            "center_right": (frame_width - watermark_width - margin_x, (frame_height - watermark_height) // 2),
            "bottom_left": (margin_x, frame_height - watermark_height - margin_y),
            "bottom_center": ((frame_width - watermark_width) // 2, frame_height - watermark_height - margin_y),
            "bottom_right": (frame_width - watermark_width - margin_x, frame_height - watermark_height - margin_y),
        }
        return positions.get(position, (margin_x, margin_y))

    def create_text_watermark(
        self,
        text: str,
        font_size: int,
        color: Tuple[int, int, int],
        add_shadow: bool,
        shadow_offset: int,
        add_outline: bool,
        outline_width: int
    ) -> np.ndarray:
        """创建文字水印图像"""
        # 使用PIL创建文字
        # 估算文字大小
        padding = 20
        img_width = len(text) * font_size + padding * 2
        img_height = font_size * 2 + padding * 2

        # 创建透明背景
        img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 尝试加载字体（如果失败使用默认字体）
        try:
            # Windows字体路径
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "C:/Windows/Fonts/arial.ttf",  # Arial
            ]
            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                    break
            if font is None:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        # 获取文字边界框
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # 调整图像大小
        img = Image.new('RGBA', (text_width + padding * 2, text_height + padding * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        text_x = padding
        text_y = padding

        # 添加阴影
        if add_shadow:
            shadow_color = (0, 0, 0, 128)
            draw.text((text_x + shadow_offset, text_y + shadow_offset), text, font=font, fill=shadow_color)

        # 添加描边
        if add_outline:
            outline_color = (0, 0, 0, 255)
            for offset_x in range(-outline_width, outline_width + 1):
                for offset_y in range(-outline_width, outline_width + 1):
                    if offset_x != 0 or offset_y != 0:
                        draw.text((text_x + offset_x, text_y + offset_y), text, font=font, fill=outline_color)

        # 绘制文字
        text_color = (*color, 255)
        draw.text((text_x, text_y), text, font=font, fill=text_color)

        # 转换为numpy数组
        return np.array(img)

    def combine_text_and_image(
        self,
        text_watermark: np.ndarray,
        image_watermark: np.ndarray,
        layout: str,
        spacing: int
    ) -> np.ndarray:
        """
        组合文字和图片水印

        Args:
            text_watermark: 文字水印（BGRA格式）
            image_watermark: 图片水印（BGRA格式）
            layout: 布局方式（text_above_image, text_below_image, text_left_image, text_right_image）
            spacing: 间距（像素）

        Returns:
            组合后的水印（BGRA格式）
        """
        text_h, text_w = text_watermark.shape[:2]
        img_h, img_w = image_watermark.shape[:2]

        if layout == "text_above_image":
            # 文字在图片上方
            combined_w = max(text_w, img_w)
            combined_h = text_h + spacing + img_h
            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 居中放置文字
            text_x = (combined_w - text_w) // 2
            combined[0:text_h, text_x:text_x+text_w] = text_watermark

            # 居中放置图片
            img_x = (combined_w - img_w) // 2
            combined[text_h+spacing:text_h+spacing+img_h, img_x:img_x+img_w] = image_watermark

        elif layout == "text_below_image":
            # 文字在图片下方
            combined_w = max(text_w, img_w)
            combined_h = img_h + spacing + text_h
            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 居中放置图片
            img_x = (combined_w - img_w) // 2
            combined[0:img_h, img_x:img_x+img_w] = image_watermark

            # 居中放置文字
            text_x = (combined_w - text_w) // 2
            combined[img_h+spacing:img_h+spacing+text_h, text_x:text_x+text_w] = text_watermark

        elif layout == "text_left_image":
            # 文字在图片左侧
            combined_w = text_w + spacing + img_w
            combined_h = max(text_h, img_h)
            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 居中放置文字
            text_y = (combined_h - text_h) // 2
            combined[text_y:text_y+text_h, 0:text_w] = text_watermark

            # 居中放置图片
            img_y = (combined_h - img_h) // 2
            combined[img_y:img_y+img_h, text_w+spacing:text_w+spacing+img_w] = image_watermark

        elif layout == "text_right_image":
            # 文字在图片右侧
            combined_w = img_w + spacing + text_w
            combined_h = max(text_h, img_h)
            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 居中放置图片
            img_y = (combined_h - img_h) // 2
            combined[img_y:img_y+img_h, 0:img_w] = image_watermark

            # 居中放置文字
            text_y = (combined_h - text_h) // 2
            combined[text_y:text_y+text_h, img_w+spacing:img_w+spacing+text_w] = text_watermark

        else:
            # 默认：文字在图片下方
            return self.combine_text_and_image(text_watermark, image_watermark, "text_below_image", spacing)

        return combined

    def _ease_out_bounce(self, t: float) -> float:
        """
        弹性缓动函数（Bounce效果）

        Args:
            t: 进度值 (0.0 - 1.0)

        Returns:
            缓动后的值 (0.0 - 1.0)
        """
        if t < 1 / 2.75:
            return 7.5625 * t * t
        elif t < 2 / 2.75:
            t -= 1.5 / 2.75
            return 7.5625 * t * t + 0.75
        elif t < 2.5 / 2.75:
            t -= 2.25 / 2.75
            return 7.5625 * t * t + 0.9375
        else:
            t -= 2.625 / 2.75
            return 7.5625 * t * t + 0.984375

    def apply_animation(
        self,
        frame_idx: int,
        total_frames: int,
        fps: float,
        animation: str,
        animation_duration: float,
        base_x: int,
        base_y: int,
        frame_width: int,
        frame_height: int,
        watermark_width: int,
        watermark_height: int,
        move_direction: str,
        rotation_speed: float,
        scale_range_min: float,
        scale_range_max: float,
        blink_frequency: float,
        base_opacity: float
    ) -> Tuple[int, int, float, float, float]:
        """
        应用动画效果

        Returns:
            (x, y, opacity, scale, rotation_angle)
        """
        current_time = frame_idx / fps
        animation_frames = int(animation_duration * fps)

        x, y = base_x, base_y
        opacity = base_opacity
        scale = 1.0
        rotation_angle = 0.0  # 旋转角度（度）

        if animation == "none":
            return (x, y, opacity, scale, rotation_angle)

        elif animation == "fade_in":
            if frame_idx < animation_frames:
                opacity = base_opacity * (frame_idx / animation_frames)

        elif animation == "fade_out":
            remaining_frames = total_frames - frame_idx
            if remaining_frames < animation_frames:
                opacity = base_opacity * (remaining_frames / animation_frames)

        elif animation == "fade_in_out":
            if frame_idx < animation_frames:
                opacity = base_opacity * (frame_idx / animation_frames)
            elif total_frames - frame_idx < animation_frames:
                remaining_frames = total_frames - frame_idx
                opacity = base_opacity * (remaining_frames / animation_frames)

        elif animation in ["move_horizontal", "move_vertical", "move_diagonal"]:
            progress = (frame_idx % animation_frames) / animation_frames

            if move_direction == "left_to_right":
                x = int(progress * (frame_width - watermark_width))
            elif move_direction == "right_to_left":
                x = int((1 - progress) * (frame_width - watermark_width))
            elif move_direction == "top_to_bottom":
                y = int(progress * (frame_height - watermark_height))
            elif move_direction == "bottom_to_top":
                y = int((1 - progress) * (frame_height - watermark_height))
            elif move_direction == "diagonal_tl_br":
                x = int(progress * (frame_width - watermark_width))
                y = int(progress * (frame_height - watermark_height))
            elif move_direction == "diagonal_tr_bl":
                x = int((1 - progress) * (frame_width - watermark_width))
                y = int(progress * (frame_height - watermark_height))

        elif animation == "slide_in":
            if frame_idx < animation_frames:
                progress = frame_idx / animation_frames
                if move_direction in ["left_to_right", "diagonal_tl_br", "diagonal_tr_bl"]:
                    x = int(base_x + (0 - base_x - watermark_width) * (1 - progress))
                elif move_direction in ["top_to_bottom"]:
                    y = int(base_y + (0 - base_y - watermark_height) * (1 - progress))

        elif animation == "slide_out":
            remaining_frames = total_frames - frame_idx
            if remaining_frames < animation_frames:
                progress = remaining_frames / animation_frames
                if move_direction in ["left_to_right", "diagonal_tl_br"]:
                    x = int(base_x + (frame_width - base_x) * (1 - progress))
                elif move_direction in ["top_to_bottom"]:
                    y = int(base_y + (frame_height - base_y) * (1 - progress))

        elif animation == "scale":
            progress = (frame_idx % animation_frames) / animation_frames
            scale = scale_range_min + (scale_range_max - scale_range_min) * abs(np.sin(progress * np.pi))

        elif animation == "blink":
            blink_cycle = int(fps / blink_frequency)
            if (frame_idx % blink_cycle) < (blink_cycle // 2):
                opacity = base_opacity
            else:
                opacity = 0.0

        elif animation == "rotate":
            # 持续旋转
            rotation_angle = (current_time * rotation_speed) % 360

        # ========== 新增10种动画效果 ==========

        elif animation == "bounce":
            # 🏀 弹跳效果：从上方弹跳进入
            if frame_idx < animation_frames:
                progress = frame_idx / animation_frames
                bounce_value = self._ease_out_bounce(progress)
                # 从上方 (-watermark_height) 弹跳到目标位置
                y = int(base_y - watermark_height * (1 - bounce_value))

        elif animation == "pulse":
            # 💓 脉冲效果：周期性放大缩小
            progress = (frame_idx % animation_frames) / animation_frames
            # 缩放范围：0.85 - 1.0（柔和的脉冲）
            pulse = 0.85 + 0.15 * np.sin(progress * 2 * np.pi)
            scale = pulse

        elif animation == "swing":
            # 🔔 摇摆效果：左右摇摆
            progress = (frame_idx % animation_frames) / animation_frames
            # 摇摆角度：±15度
            swing_angle = 15 * np.sin(progress * 2 * np.pi)
            rotation_angle = swing_angle

        elif animation == "wave":
            # 🌊 波浪效果：沿波浪路径移动
            progress = (frame_idx % animation_frames) / animation_frames
            # 水平移动
            x = int(progress * (frame_width - watermark_width))
            # 垂直波浪（幅度50px）
            amplitude = 50
            y = int(base_y + amplitude * np.sin(progress * 4 * np.pi))

        elif animation == "glint":
            # ✨ 闪光效果：周期性闪光
            progress = (frame_idx % animation_frames) / animation_frames
            # 在30%-50%时刻闪光
            if 0.3 <= progress <= 0.5:
                # 闪光时增加亮度和缩放
                scale = 1.1
                opacity = min(1.0, base_opacity * 1.5)
            else:
                scale = 1.0
                opacity = base_opacity

        elif animation == "breathe":
            # 🫁 呼吸效果：缓慢放大缩小 + 透明度变化
            progress = (frame_idx % animation_frames) / animation_frames
            # 缩放：0.9 - 1.1
            breathe_scale = 0.9 + 0.2 * np.sin(progress * 2 * np.pi)
            scale = breathe_scale
            # 透明度：0.85 - 1.0
            breathe_opacity = 0.85 + 0.15 * np.sin(progress * 2 * np.pi)
            opacity = base_opacity * breathe_opacity

        elif animation == "shake":
            # 📳 抖动效果：快速抖动
            if frame_idx < animation_frames:
                # 高频抖动（20Hz）
                shake_freq = 20
                shake_progress = (frame_idx / fps) * shake_freq
                # 抖动强度：±5px
                shake_x = int(5 * np.sin(shake_progress * 2 * np.pi))
                shake_y = int(5 * np.cos(shake_progress * 2 * np.pi))
                x = base_x + shake_x
                y = base_y + shake_y

        elif animation == "flip":
            # 🔄 翻转效果：3D翻转（水平翻转）
            progress = (frame_idx % animation_frames) / animation_frames
            # 使用余弦函数模拟3D翻转的缩放效果
            flip_scale = abs(np.cos(progress * 2 * np.pi))
            scale = max(0.1, flip_scale)  # 避免完全消失
            # 翻转时调整透明度
            if flip_scale < 0.3:
                opacity = base_opacity * (flip_scale / 0.3)

        elif animation == "rainbow":
            # 🌈 彩虹效果：颜色循环变化
            progress = (frame_idx % animation_frames) / animation_frames
            # 色相值：0-360度循环
            hue = progress * 360
            # 将色相值存储在 rotation_angle 中（后续在 overlay_watermark 中使用）
            rotation_angle = hue

        elif animation == "typewriter":
            # ⌨️ 打字机效果：逐渐出现
            if frame_idx < animation_frames:
                progress = frame_idx / animation_frames
                # 透明度渐变
                opacity = base_opacity * progress
                # 轻微滑入效果
                x = int(base_x - 20 * (1 - progress))

        return (x, y, opacity, scale, rotation_angle)

    def overlay_watermark(
        self,
        frame: np.ndarray,
        watermark: np.ndarray,
        x: int,
        y: int,
        opacity: float,
        scale: float = 1.0,
        rotation_angle: float = 0.0,
        animation: str = "none"
    ) -> np.ndarray:
        """
        将水印叠加到帧上

        注意：watermark已经通过image_scale缩放到目标大小
        这里的scale参数仅用于动画效果的额外缩放
        """
        # 记录原始尺寸（用于中心固定）
        original_h, original_w = watermark.shape[:2]
        original_center_x = x + original_w // 2
        original_center_y = y + original_h // 2

        # 应用动画缩放（基于当前水印大小）
        if scale != 1.0:
            old_width, old_height = watermark.shape[1], watermark.shape[0]
            new_width = int(watermark.shape[1] * scale)
            new_height = int(watermark.shape[0] * scale)
            if new_width > 0 and new_height > 0:
                watermark = cv2.resize(watermark, (new_width, new_height), interpolation=cv2.INTER_AREA)
                print(f"[VideoWatermark] 动画缩放: {old_width}x{old_height} -> {new_width}x{new_height} (scale={scale:.2f})")
                # 更新中心位置（缩放后）
                scaled_h, scaled_w = watermark.shape[:2]
                original_center_x = x + scaled_w // 2
                original_center_y = y + scaled_h // 2

        # 旋转水印
        if rotation_angle != 0.0:
            wm_h, wm_w = watermark.shape[:2]
            center = (wm_w // 2, wm_h // 2)

            # 计算旋转矩阵
            rotation_matrix = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)

            # 计算旋转后的边界框大小
            cos = np.abs(rotation_matrix[0, 0])
            sin = np.abs(rotation_matrix[0, 1])
            new_w = int((wm_h * sin) + (wm_w * cos))
            new_h = int((wm_h * cos) + (wm_w * sin))

            # 调整旋转矩阵以适应新的边界框
            rotation_matrix[0, 2] += (new_w / 2) - center[0]
            rotation_matrix[1, 2] += (new_h / 2) - center[1]

            # 执行旋转
            watermark = cv2.warpAffine(watermark, rotation_matrix, (new_w, new_h),
                                       flags=cv2.INTER_LINEAR,
                                       borderMode=cv2.BORDER_CONSTANT,
                                       borderValue=(0, 0, 0, 0))

            # ✅ 关键：调整位置使视觉中心保持固定
            rotated_h, rotated_w = watermark.shape[:2]
            x = original_center_x - rotated_w // 2
            y = original_center_y - rotated_h // 2

        wm_h, wm_w = watermark.shape[:2]
        frame_h, frame_w = frame.shape[:2]

        # 确保水印在帧内
        x = max(0, min(x, frame_w - wm_w))
        y = max(0, min(y, frame_h - wm_h))

        # 计算实际叠加区域
        x2 = min(x + wm_w, frame_w)
        y2 = min(y + wm_h, frame_h)
        wm_w_actual = x2 - x
        wm_h_actual = y2 - y

        if wm_w_actual <= 0 or wm_h_actual <= 0:
            return frame

        # 提取ROI
        roi = frame[y:y2, x:x2]
        watermark_crop = watermark[:wm_h_actual, :wm_w_actual]

        # 处理透明度
        if watermark_crop.shape[2] == 4:  # RGBA
            alpha = watermark_crop[:, :, 3:4] / 255.0 * opacity
            watermark_rgb = watermark_crop[:, :, :3]
        else:  # RGB
            alpha = np.ones((wm_h_actual, wm_w_actual, 1)) * opacity
            watermark_rgb = watermark_crop

        # 彩虹效果：根据 rotation_angle（实际存储的是色相值 0-360）调整颜色
        if animation == "rainbow":
            # 将 BGR 转换为 HSV
            watermark_hsv = cv2.cvtColor(watermark_rgb.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)

            # 计算当前色相值（0-180）
            hue_shift = rotation_angle / 2  # OpenCV 的色相范围是 0-180

            # 对于灰色/白色水印（饱和度低），添加颜色
            # 对于已有颜色的水印，调整色相
            saturation = watermark_hsv[:, :, 1]

            # 设置新的色相值
            watermark_hsv[:, :, 0] = hue_shift

            # 对于低饱和度的像素（灰色/白色），增加饱和度以显示彩虹颜色
            # 饱和度阈值：< 30 认为是灰色/白色
            low_saturation_mask = saturation < 30
            watermark_hsv[:, :, 1] = np.where(low_saturation_mask, 200, saturation)

            # 转换回 BGR
            watermark_rgb = cv2.cvtColor(watermark_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

        # 混合
        blended = roi * (1 - alpha) + watermark_rgb * alpha
        frame[y:y2, x:x2] = blended.astype(np.uint8)

        return frame

    def add_watermark(
        self,
        video: str,
        watermark_type: str,
        enable_watermark: bool,
        text_content: str = "© 2025 Your Brand",
        font_size: int = 48,
        font_color: str = "white",
        custom_color_r: int = 255,
        custom_color_g: int = 255,
        custom_color_b: int = 255,
        text_position: str = "bottom_right",
        text_opacity: float = 0.7,
        watermark_image: Optional[torch.Tensor] = None,
        auto_remove_bg: bool = False,
        bg_color_mode: str = "white",
        bg_threshold: int = 240,
        image_position: str = "top_right",
        image_scale: float = 0.15,
        image_opacity: float = 0.8,
        combined_layout: str = "text_below_image",
        combined_spacing: int = 10,
        margin_x: int = 20,
        margin_y: int = 20,
        custom_x: int = 100,
        custom_y: int = 100,
        animation: str = "none",
        animation_duration: float = 2.0,
        move_direction: str = "left_to_right",
        rotation_speed: float = 30.0,
        scale_range_min: float = 0.5,
        scale_range_max: float = 1.5,
        blink_frequency: float = 2.0,
        start_time: float = 0.0,
        end_time: float = -1.0,
        add_shadow: bool = True,
        shadow_offset: int = 2,
        add_outline: bool = False,
        outline_width: int = 2,
        enable_multi_position: bool = False,
        multi_position_preset: str = "four_corners",
        position_list: str = "top_left,top_right,bottom_left,bottom_right",
        position_switch_interval: float = 3.0
    ) -> Tuple[str, str]:
        """添加水印到视频"""

        if not enable_watermark:
            return (video, "水印已禁用，返回原视频")

        print("\n" + "="*70)
        print("🎨 VideoWatermark - 动态视频水印")
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

        print(f"[VideoWatermark] 视频信息:")
        print(f"  - 分辨率: {width}x{height}")
        print(f"  - 总帧数: {total_frames}")
        print(f"  - 帧率: {fps:.2f} fps")
        print(f"  - 时长: {total_frames/fps:.2f}秒")

        # 计算时间范围
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps) if end_time > 0 else total_frames

        print(f"[VideoWatermark] 水印时间范围: {start_time:.2f}s - {end_time if end_time > 0 else '结束'}s")
        print(f"[VideoWatermark] 水印帧范围: {start_frame} - {end_frame}")

        # 准备文字水印
        text_wm = None
        if watermark_type in ["text", "both"]:
            color = self.get_color(font_color, custom_color_r, custom_color_g, custom_color_b)
            text_wm = self.create_text_watermark(
                text_content, font_size, color, add_shadow, shadow_offset, add_outline, outline_width
            )
            print(f"[VideoWatermark] 文字水印: '{text_content}'")
            print(f"  - 字体大小: {font_size}")
            print(f"  - 颜色: {font_color}")
            print(f"  - 位置: {text_position}")
            print(f"  - 透明度: {text_opacity}")

        # 准备图片水印
        image_wm = None
        if watermark_type in ["image", "both"] and watermark_image is not None:
            # 转换ComfyUI IMAGE张量到numpy
            img_tensor = watermark_image[0]  # 取第一张图
            img_np = (img_tensor.cpu().numpy() * 255).astype(np.uint8)

            # ✅ 转换颜色格式：ComfyUI使用RGB，OpenCV使用BGR
            if img_np.shape[2] == 3:
                img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                print(f"[VideoWatermark] RGB转BGR")
            elif img_np.shape[2] == 4:
                img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGRA)
                print(f"[VideoWatermark] RGBA转BGRA")

            # 自动抠图（移除背景）
            if auto_remove_bg:
                print(f"[VideoWatermark] 开始自动抠图...")
                img_np = self.remove_background(img_np, bg_color_mode, bg_threshold)

            # 缩放图片
            original_img_width = img_np.shape[1]
            original_img_height = img_np.shape[0]
            target_width = int(width * image_scale)
            aspect_ratio = img_np.shape[0] / img_np.shape[1]
            target_height = int(target_width * aspect_ratio)

            print(f"[VideoWatermark] 图片缩放计算:")
            print(f"  - 视频宽度: {width}px")
            print(f"  - image_scale参数: {image_scale}")
            print(f"  - 原始图片: {original_img_width}x{original_img_height}")
            print(f"  - 目标宽度: {target_width}px ({width} * {image_scale})")
            print(f"  - 目标高度: {target_height}px")

            image_wm = cv2.resize(img_np, (target_width, target_height), interpolation=cv2.INTER_AREA)

            # 检查是否有alpha通道
            if image_wm.shape[2] == 4:
                # 已有alpha通道，保留
                print(f"[VideoWatermark] 检测到BGRA图片，保留透明度")
            elif image_wm.shape[2] == 3:
                # BGR图片，添加alpha通道（根据image_opacity）
                alpha = np.ones((image_wm.shape[0], image_wm.shape[1], 1), dtype=np.uint8) * int(255 * image_opacity)
                image_wm = np.concatenate([image_wm, alpha], axis=2)
                print(f"[VideoWatermark] BGR图片，添加alpha通道（透明度: {image_opacity}）")

            print(f"[VideoWatermark] 图片水印:")
            print(f"  - 原始尺寸: {img_np.shape[1]}x{img_np.shape[0]}")
            print(f"  - 缩放后: {target_width}x{target_height}")
            print(f"  - 通道数: {image_wm.shape[2]}")
            print(f"  - 自动抠图: {auto_remove_bg}")
            print(f"  - 位置: {image_position}")
            print(f"  - 透明度: {image_opacity}")

        # 组合水印
        text_watermark = None
        image_watermark = None

        if watermark_type == "both" and text_wm is not None and image_wm is not None:
            # 组合模式
            if combined_layout == "separate":
                # 分别显示
                text_watermark = cv2.cvtColor(text_wm, cv2.COLOR_RGBA2BGRA)
                image_watermark = image_wm
                print(f"[VideoWatermark] 组合模式: separate（分别显示）")
            else:
                # 组合显示
                text_wm_bgra = cv2.cvtColor(text_wm, cv2.COLOR_RGBA2BGRA)
                combined = self.combine_text_and_image(
                    text_wm_bgra, image_wm, combined_layout, combined_spacing
                )
                # 组合后的水印使用text_position和text_opacity
                text_watermark = combined
                print(f"[VideoWatermark] 组合模式: {combined_layout}, 间距: {combined_spacing}px")
                print(f"[VideoWatermark] 组合后尺寸: {combined.shape[:2]}")
        elif text_wm is not None:
            text_watermark = cv2.cvtColor(text_wm, cv2.COLOR_RGBA2BGRA)
        elif image_wm is not None:
            image_watermark = image_wm

        print(f"[VideoWatermark] 动画效果: {animation}")
        if animation != "none":
            print(f"  - 持续时间: {animation_duration}秒")
            if animation in ["move_horizontal", "move_vertical", "move_diagonal", "slide_in", "slide_out"]:
                print(f"  - 移动方向: {move_direction}")

        # 创建输出文件（保存到ComfyUI output目录）
        from folder_paths import get_output_directory
        output_dir = get_output_directory()

        # 生成唯一文件名
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(video))[0]
        output_filename = f"watermarked_{base_name}_{timestamp}.mp4"
        output_video = os.path.join(output_dir, output_filename)

        # 创建视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_video, fourcc, fps, (width, height))

        print(f"[VideoWatermark] 🎬 开始处理...")

        # 解析多位置列表
        positions = []
        if enable_multi_position:
            # 使用预设或自定义列表
            if multi_position_preset == "custom":
                position_str = position_list
            else:
                position_str = self.get_multi_position_preset(multi_position_preset)

            if position_str:
                positions = [p.strip() for p in position_str.split(',')]
                print(f"[VideoWatermark] 多位置模式: {multi_position_preset} ({len(positions)}个位置)")
                print(f"[VideoWatermark] 位置列表: {position_str}")

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_idx / fps

            # 检查是否在水印时间范围内
            if start_frame <= frame_idx < end_frame:
                # 添加文字水印
                if text_watermark is not None:
                    wm_h, wm_w = text_watermark.shape[:2]

                    # 确定位置（多位置或固定位置）
                    if enable_multi_position and positions:
                        position_index = int(current_time / position_switch_interval) % len(positions)
                        current_position = positions[position_index]
                        base_x, base_y = self.calculate_position(
                            current_position, width, height, wm_w, wm_h,
                            margin_x, margin_y, custom_x, custom_y
                        )
                    else:
                        base_x, base_y = self.calculate_position(
                            text_position, width, height, wm_w, wm_h,
                            margin_x, margin_y, custom_x, custom_y
                        )

                    x, y, opacity, scale, rotation_angle = self.apply_animation(
                        frame_idx - start_frame, end_frame - start_frame, fps,
                        animation, animation_duration, base_x, base_y,
                        width, height, wm_w, wm_h, move_direction,
                        rotation_speed, scale_range_min, scale_range_max,
                        blink_frequency, text_opacity
                    )

                    frame = self.overlay_watermark(frame, text_watermark, x, y, opacity, scale, rotation_angle, animation)

                # 添加图片水印
                if image_watermark is not None:
                    wm_h, wm_w = image_watermark.shape[:2]

                    # 确定位置（多位置或固定位置）
                    if enable_multi_position and positions:
                        position_index = int(current_time / position_switch_interval) % len(positions)
                        current_position = positions[position_index]
                        base_x, base_y = self.calculate_position(
                            current_position, width, height, wm_w, wm_h,
                            margin_x, margin_y, custom_x, custom_y
                        )
                    else:
                        base_x, base_y = self.calculate_position(
                            image_position, width, height, wm_w, wm_h,
                            margin_x, margin_y, custom_x, custom_y
                        )

                    x, y, opacity, scale, rotation_angle = self.apply_animation(
                        frame_idx - start_frame, end_frame - start_frame, fps,
                        animation, animation_duration, base_x, base_y,
                        width, height, wm_w, wm_h, move_direction,
                        rotation_speed, scale_range_min, scale_range_max,
                        blink_frequency, image_opacity
                    )

                    frame = self.overlay_watermark(frame, image_watermark, x, y, opacity, scale, rotation_angle, animation)

            out.write(frame)
            frame_idx += 1

            if frame_idx % 30 == 0:
                progress = (frame_idx / total_frames) * 100
                print(f"[VideoWatermark] 进度: {progress:.1f}% ({frame_idx}/{total_frames})")

        cap.release()
        out.release()

        print(f"[VideoWatermark] ✅ 处理完成！")
        print(f"[VideoWatermark] 输出: {output_video}")

        # 生成信息
        info = f"""
视频水印添加完成：
- 输入视频: {os.path.basename(video)}
- 分辨率: {width}x{height}
- 总帧数: {total_frames}
- 水印类型: {watermark_type}
- 动画效果: {animation}
- 水印时间: {start_time:.2f}s - {end_time if end_time > 0 else '结束'}s
- 输出视频: {os.path.basename(output_video)}
        """

        return (output_video, info.strip())


# 注册节点
NODE_CLASS_MAPPINGS = {
    "VideoWatermark": VideoWatermark
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VideoWatermark": "🎨 Video Watermark (视频水印)"
}

