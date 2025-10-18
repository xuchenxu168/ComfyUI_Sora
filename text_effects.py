"""
文字特效模块
支持各种创意文字效果
"""

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import math
import os
from typing import Tuple, Optional


class TextEffects:
    """文字特效类"""
    
    @staticmethod
    def create_curved_text(
        text: str,
        font_size: int,
        color: Tuple[int, int, int],
        radius: int,
        start_angle: float = -90,
        end_angle: float = 90,
        font_path: Optional[str] = None
    ) -> np.ndarray:
        """
        创建弧形文字
        
        Args:
            text: 文字内容
            font_size: 字体大小
            color: 文字颜色 (R, G, B)
            radius: 弧形半径
            start_angle: 起始角度（度）
            end_angle: 结束角度（度）
            font_path: 字体文件路径
        
        Returns:
            RGBA格式的numpy数组
        """
        # 加载字体
        try:
            if font_path and os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
            else:
                # 尝试常见字体
                font_paths = [
                    "C:/Windows/Fonts/msyh.ttc",
                    "C:/Windows/Fonts/arial.ttf",
                ]
                font = None
                for fp in font_paths:
                    try:
                        font = ImageFont.truetype(fp, font_size)
                        break
                    except:
                        continue
                if font is None:
                    font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # 计算画布大小
        canvas_size = int(radius * 2.5)
        center_x = canvas_size // 2
        center_y = canvas_size // 2
        
        # 创建透明画布
        img = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 计算每个字符的角度间隔
        angle_range = end_angle - start_angle
        char_count = len(text)
        
        if char_count > 1:
            angle_step = angle_range / (char_count - 1)
        else:
            angle_step = 0
        
        # 绘制每个字符
        for i, char in enumerate(text):
            # 计算当前字符的角度
            angle = start_angle + (i * angle_step)
            angle_rad = math.radians(angle)
            
            # 计算字符位置
            x = center_x + radius * math.cos(angle_rad)
            y = center_y + radius * math.sin(angle_rad)
            
            # 创建单个字符的图像
            bbox = draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            char_height = bbox[3] - bbox[1]
            
            char_img = Image.new('RGBA', (char_width + 20, char_height + 20), (0, 0, 0, 0))
            char_draw = ImageDraw.Draw(char_img)
            char_draw.text((10, 10), char, font=font, fill=(*color, 255))
            
            # 旋转字符（使其沿着弧线方向）
            rotation_angle = angle + 90  # 调整方向
            char_img_rotated = char_img.rotate(-rotation_angle, expand=True, fillcolor=(0, 0, 0, 0))
            
            # 粘贴到主画布
            paste_x = int(x - char_img_rotated.width // 2)
            paste_y = int(y - char_img_rotated.height // 2)
            img.paste(char_img_rotated, (paste_x, paste_y), char_img_rotated)
        
        return np.array(img)
    
    @staticmethod
    def create_arc_text_around_image(
        text: str,
        image: np.ndarray,
        font_size: int,
        color: Tuple[int, int, int],
        position: str = "top",
        spacing: int = 20,
        font_path: Optional[str] = None
    ) -> np.ndarray:
        """
        创建环绕图片的弧形文字
        
        Args:
            text: 文字内容
            image: 图片（BGRA格式）
            font_size: 字体大小
            color: 文字颜色 (R, G, B)
            position: 位置 ("top", "bottom", "left", "right", "top_bottom", "full")
            spacing: 文字与图片的间距
            font_path: 字体文件路径
        
        Returns:
            组合后的BGRA格式numpy数组
        """
        img_h, img_w = image.shape[:2]

        # 计算弧形半径（增大以确保文字完整显示）
        radius = max(img_w, img_h) // 2 + spacing + font_size

        if position == "top":
            # 上方半圆
            curved_text = TextEffects.create_curved_text(
                text, font_size, color, radius,
                start_angle=-180, end_angle=0
            )
            # 转换为BGRA
            curved_text_bgra = cv2.cvtColor(curved_text, cv2.COLOR_RGBA2BGRA)

            # 计算组合尺寸
            text_h, text_w = curved_text_bgra.shape[:2]
            combined_w = max(text_w, img_w)
            # 计算文字实际占用的高度（从中心到顶部）
            text_actual_h = radius + font_size * 2
            combined_h = text_actual_h + spacing + img_h

            # 创建画布
            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 放置文字（上方，完整显示）
            text_x = (combined_w - text_w) // 2
            text_y = 0
            # 找到文字的实际边界
            text_alpha = curved_text_bgra[:, :, 3]
            text_rows = np.where(text_alpha.sum(axis=1) > 0)[0]
            if len(text_rows) > 0:
                text_start = text_rows[0]
                text_end = text_rows[-1] + 1
                text_content = curved_text_bgra[text_start:text_end, :]
                combined[text_y:text_y+text_content.shape[0], text_x:text_x+text_w] = text_content
                img_y = text_y + text_content.shape[0] + spacing
            else:
                img_y = text_actual_h + spacing

            # 放置图片（下方）
            img_x = (combined_w - img_w) // 2
            combined[img_y:img_y+img_h, img_x:img_x+img_w] = image
            
        elif position == "bottom":
            # 下方半圆
            curved_text = TextEffects.create_curved_text(
                text, font_size, color, radius,
                start_angle=0, end_angle=180
            )
            curved_text_bgra = cv2.cvtColor(curved_text, cv2.COLOR_RGBA2BGRA)

            text_h, text_w = curved_text_bgra.shape[:2]
            combined_w = max(text_w, img_w)

            # 找到文字的实际边界
            text_alpha = curved_text_bgra[:, :, 3]
            text_rows = np.where(text_alpha.sum(axis=1) > 0)[0]
            if len(text_rows) > 0:
                text_start = text_rows[0]
                text_end = text_rows[-1] + 1
                text_content = curved_text_bgra[text_start:text_end, :]
                text_actual_h = text_content.shape[0]
            else:
                text_content = curved_text_bgra
                text_actual_h = text_h

            combined_h = img_h + spacing + text_actual_h
            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 放置图片（上方）
            img_x = (combined_w - img_w) // 2
            combined[0:img_h, img_x:img_x+img_w] = image

            # 放置文字（下方，完整显示）
            text_x = (combined_w - text_w) // 2
            text_y = img_h + spacing
            combined[text_y:text_y+text_actual_h, text_x:text_x+text_w] = text_content
            
        elif position == "top_bottom":
            # 上下都有弧形文字
            # 分割文字
            mid = len(text) // 2
            text_top = text[:mid]
            text_bottom = text[mid:]

            # 上方半圆
            curved_top = TextEffects.create_curved_text(
                text_top, font_size, color, radius,
                start_angle=-180, end_angle=0
            )
            curved_top_bgra = cv2.cvtColor(curved_top, cv2.COLOR_RGBA2BGRA)

            # 下方半圆
            curved_bottom = TextEffects.create_curved_text(
                text_bottom, font_size, color, radius,
                start_angle=0, end_angle=180
            )
            curved_bottom_bgra = cv2.cvtColor(curved_bottom, cv2.COLOR_RGBA2BGRA)

            top_h, top_w = curved_top_bgra.shape[:2]
            bottom_h, bottom_w = curved_bottom_bgra.shape[:2]

            # 找到上方文字的实际边界
            top_alpha = curved_top_bgra[:, :, 3]
            top_rows = np.where(top_alpha.sum(axis=1) > 0)[0]
            if len(top_rows) > 0:
                top_content = curved_top_bgra[top_rows[0]:top_rows[-1]+1, :]
                top_actual_h = top_content.shape[0]
            else:
                top_content = curved_top_bgra
                top_actual_h = top_h

            # 找到下方文字的实际边界
            bottom_alpha = curved_bottom_bgra[:, :, 3]
            bottom_rows = np.where(bottom_alpha.sum(axis=1) > 0)[0]
            if len(bottom_rows) > 0:
                bottom_content = curved_bottom_bgra[bottom_rows[0]:bottom_rows[-1]+1, :]
                bottom_actual_h = bottom_content.shape[0]
            else:
                bottom_content = curved_bottom_bgra
                bottom_actual_h = bottom_h

            combined_w = max(top_w, bottom_w, img_w)
            combined_h = top_actual_h + spacing + img_h + spacing + bottom_actual_h

            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 放置上方文字（完整显示）
            top_x = (combined_w - top_w) // 2
            combined[0:top_actual_h, top_x:top_x+top_w] = top_content

            # 放置图片（中间）
            img_x = (combined_w - img_w) // 2
            img_y = top_actual_h + spacing
            combined[img_y:img_y+img_h, img_x:img_x+img_w] = image

            # 放置下方文字（完整显示）
            bottom_x = (combined_w - bottom_w) // 2
            bottom_y = img_y + img_h + spacing
            combined[bottom_y:bottom_y+bottom_actual_h, bottom_x:bottom_x+bottom_w] = bottom_content
            
        elif position == "full":
            # 完整圆形环绕
            curved_text = TextEffects.create_curved_text(
                text, font_size, color, radius,
                start_angle=0, end_angle=360
            )
            curved_text_bgra = cv2.cvtColor(curved_text, cv2.COLOR_RGBA2BGRA)

            text_h, text_w = curved_text_bgra.shape[:2]
            combined_w = max(text_w, img_w)
            combined_h = max(text_h, img_h)

            combined = np.zeros((combined_h, combined_w, 4), dtype=np.uint8)

            # 先放置文字（底层）
            text_x = (combined_w - text_w) // 2
            text_y = (combined_h - text_h) // 2
            combined[text_y:text_y+text_h, text_x:text_x+text_w] = curved_text_bgra

            # 再放置图片（顶层，使用alpha混合）
            img_x = (combined_w - img_w) // 2
            img_y = (combined_h - img_h) // 2

            # Alpha混合：图片覆盖在文字上方
            img_alpha = image[:, :, 3:4].astype(float) / 255.0
            bg_alpha = combined[img_y:img_y+img_h, img_x:img_x+img_w, 3:4].astype(float) / 255.0

            # 计算混合后的颜色
            for c in range(3):
                combined[img_y:img_y+img_h, img_x:img_x+img_w, c] = (
                    image[:, :, c] * img_alpha[:, :, 0] +
                    combined[img_y:img_y+img_h, img_x:img_x+img_w, c] * bg_alpha[:, :, 0] * (1 - img_alpha[:, :, 0])
                ).astype(np.uint8)

            # 计算混合后的alpha
            combined[img_y:img_y+img_h, img_x:img_x+img_w, 3] = (
                (img_alpha[:, :, 0] + bg_alpha[:, :, 0] * (1 - img_alpha[:, :, 0])) * 255
            ).astype(np.uint8)
        
        else:
            # 默认：上方
            return TextEffects.create_arc_text_around_image(
                text, image, font_size, color, "top", spacing, font_path
            )
        
        return combined


import os

