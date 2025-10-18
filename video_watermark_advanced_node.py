"""
VideoWatermarkAdvanced节点 - 高级视频水印（专业级）
支持目标跟踪、防遮挡、批量处理
"""

import os
import cv2
import numpy as np
import torch
from typing import Tuple, Optional, List, Dict
from PIL import Image, ImageDraw, ImageFont
import tempfile
import subprocess
import glob


class VideoWatermarkAdvanced:
    """
    高级视频水印节点（专业级）
    
    功能：
    - 🎯 目标跟踪：水印跟随人脸、物体移动
    - 🛡️ 防遮挡：自动调整位置避开重要内容
    - 📦 批量处理：一次处理多个视频
    - 🎨 所有基础功能（文字、图片、动画等）
    """
    
    def __init__(self):
        self.face_cascade = None
        self.body_cascade = None
        
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO", {
                    "tooltip": "输入视频（单个或批量）"
                }),
                "watermark_type": (["text", "image", "both"], {
                    "default": "text",
                    "tooltip": "水印类型"
                }),
                "enable_watermark": ("BOOLEAN", {
                    "default": True,
                    "label_on": "启用",
                    "label_off": "禁用",
                }),
            },
            "optional": {
                # 高级功能 ⭐
                "tracking_mode": (["none", "face", "body", "object"], {
                    "default": "none",
                    "tooltip": "目标跟踪模式：none=固定位置, face=跟随人脸, body=跟随人体, object=跟随物体"
                }),
                "tracking_position": (["above", "below", "left", "right", "on_target"], {
                    "default": "above",
                    "tooltip": "水印相对目标的位置"
                }),
                "tracking_offset_x": ("INT", {
                    "default": 0,
                    "min": -500,
                    "max": 500,
                    "tooltip": "跟踪时的X偏移"
                }),
                "tracking_offset_y": ("INT", {
                    "default": -50,
                    "min": -500,
                    "max": 500,
                    "tooltip": "跟踪时的Y偏移"
                }),
                "enable_anti_occlusion": ("BOOLEAN", {
                    "default": False,
                    "label_on": "启用防遮挡",
                    "label_off": "禁用",
                    "tooltip": "自动调整位置避开重要内容"
                }),
                "occlusion_detection_method": (["brightness", "edge", "saliency"], {
                    "default": "brightness",
                    "tooltip": "遮挡检测方法：brightness=亮度, edge=边缘, saliency=显著性"
                }),
                "min_target_confidence": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.1,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "目标检测最小置信度"
                }),
                "smooth_tracking": ("BOOLEAN", {
                    "default": True,
                    "label_on": "平滑跟踪",
                    "label_off": "直接跟踪",
                    "tooltip": "使用平滑算法减少抖动"
                }),
                "smoothing_factor": ("FLOAT", {
                    "default": 0.3,
                    "min": 0.1,
                    "max": 0.9,
                    "step": 0.05,
                    "tooltip": "平滑系数（越小越平滑）"
                }),
                
                # 批量处理
                "batch_mode": ("BOOLEAN", {
                    "default": False,
                    "label_on": "批量模式",
                    "label_off": "单个视频",
                    "tooltip": "是否批量处理多个视频"
                }),
                "batch_video_folder": ("STRING", {
                    "default": "",
                    "tooltip": "批量处理的视频文件夹路径"
                }),
                "batch_output_folder": ("STRING", {
                    "default": "",
                    "tooltip": "批量输出文件夹路径"
                }),
                
                # 基础水印参数（继承自基础版）
                "text_content": ("STRING", {
                    "default": "© 2025 Your Brand",
                    "multiline": False,
                }),
                "font_size": ("INT", {
                    "default": 48,
                    "min": 12,
                    "max": 200,
                }),
                "font_color": (["white", "black", "red", "green", "blue", "yellow", "cyan", "magenta", "custom"], {
                    "default": "white",
                }),
                "text_position": (["top_left", "top_center", "top_right", 
                                   "center_left", "center", "center_right",
                                   "bottom_left", "bottom_center", "bottom_right", "custom"], {
                    "default": "bottom_right",
                }),
                "text_opacity": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                }),
                "watermark_image": ("IMAGE", {
                    "tooltip": "水印图片"
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
                }),
                "image_scale": ("FLOAT", {
                    "default": 0.15,
                    "min": 0.01,
                    "max": 1.0,
                    "step": 0.01,
                }),
                "image_opacity": ("FLOAT", {
                    "default": 0.8,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
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
                "text_effect": (["none", "curved"], {
                    "default": "none",
                    "tooltip": "文字特效（curved=弧形文字）"
                }),
                "margin_x": ("INT", {
                    "default": 20,
                    "min": 0,
                    "max": 500,
                }),
                "margin_y": ("INT", {
                    "default": 20,
                    "min": 0,
                    "max": 500,
                }),
                "animation": (["none", "fade_in", "fade_out", "fade_in_out",
                               "move_horizontal", "move_vertical", "move_diagonal",
                               "slide_in", "slide_out", "rotate", "scale", "blink",
                               "bounce", "pulse", "swing", "wave", "glint",
                               "breathe", "shake", "flip", "rainbow", "typewriter"], {
                    "default": "none",
                    "tooltip": "动画效果类型 - 新增10种吸引眼球的效果"
                }),
                "animation_duration": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.1,
                    "max": 30.0,
                    "step": 0.1,
                    "tooltip": "动画持续时间（秒）- 数值越大动画越慢"
                }),
                "move_direction": (["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"], {
                    "default": "left_to_right",
                }),
                "rotation_speed": ("FLOAT", {
                    "default": 30.0,
                    "min": 1.0,
                    "max": 360.0,
                    "step": 1.0,
                    "tooltip": "旋转速度（度/秒）- 数值越小旋转越慢"
                }),
                "scale_range_min": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                }),
                "scale_range_max": ("FLOAT", {
                    "default": 1.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                }),
                "blink_frequency": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.5,
                    "max": 10.0,
                    "step": 0.5,
                }),

                # 多位置功能 ⭐ 新增
                "enable_multi_position": ("BOOLEAN", {
                    "default": False,
                    "label_on": "启用多位置",
                    "label_off": "单一位置",
                    "tooltip": "水印在多个位置之间切换（与跟踪模式冲突）"
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
                "add_shadow": ("BOOLEAN", {
                    "default": True,
                }),
                "shadow_offset": ("INT", {
                    "default": 2,
                    "min": 0,
                    "max": 10,
                }),
            }
        }
    
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("video", "info")
    FUNCTION = "add_watermark_advanced"
    CATEGORY = "Ken-Chen/sora"
    
    def load_face_detector(self):
        """加载人脸检测器"""
        if self.face_cascade is None:
            # 尝试加载OpenCV自带的Haar Cascade
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            if os.path.exists(cascade_path):
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
                print("[VideoWatermarkAdvanced] ✅ 人脸检测器加载成功")
            else:
                print("[VideoWatermarkAdvanced] ⚠️ 人脸检测器未找到")
        return self.face_cascade
    
    def load_body_detector(self):
        """加载人体检测器"""
        if self.body_cascade is None:
            cascade_path = cv2.data.haarcascades + 'haarcascade_fullbody.xml'
            if os.path.exists(cascade_path):
                self.body_cascade = cv2.CascadeClassifier(cascade_path)
                print("[VideoWatermarkAdvanced] ✅ 人体检测器加载成功")
            else:
                print("[VideoWatermarkAdvanced] ⚠️ 人体检测器未找到")
        return self.body_cascade
    
    def detect_targets(
        self,
        frame: np.ndarray,
        tracking_mode: str,
        min_confidence: float
    ) -> List[Tuple[int, int, int, int]]:
        """
        检测目标
        
        Returns:
            List of (x, y, w, h) bounding boxes
        """
        targets = []
        
        if tracking_mode == "face":
            detector = self.load_face_detector()
            if detector is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(30, 30)
                )
                targets = [(x, y, w, h) for (x, y, w, h) in faces]
        
        elif tracking_mode == "body":
            detector = self.load_body_detector()
            if detector is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                bodies = detector.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(50, 50)
                )
                targets = [(x, y, w, h) for (x, y, w, h) in bodies]
        
        elif tracking_mode == "object":
            # TODO: 实现YOLO物体检测
            pass
        
        return targets

    def calculate_tracking_position(
        self,
        target_bbox: Tuple[int, int, int, int],
        tracking_position: str,
        watermark_width: int,
        watermark_height: int,
        offset_x: int,
        offset_y: int,
        frame_width: int,
        frame_height: int
    ) -> Tuple[int, int]:
        """
        计算跟踪时的水印位置

        Args:
            target_bbox: (x, y, w, h) 目标边界框
            tracking_position: 相对位置
            watermark_width: 水印宽度
            watermark_height: 水印高度
            offset_x: X偏移
            offset_y: Y偏移

        Returns:
            (x, y) 水印位置
        """
        tx, ty, tw, th = target_bbox

        if tracking_position == "above":
            # 目标上方
            x = tx + (tw - watermark_width) // 2 + offset_x
            y = ty - watermark_height + offset_y
        elif tracking_position == "below":
            # 目标下方
            x = tx + (tw - watermark_width) // 2 + offset_x
            y = ty + th + offset_y
        elif tracking_position == "left":
            # 目标左侧
            x = tx - watermark_width + offset_x
            y = ty + (th - watermark_height) // 2 + offset_y
        elif tracking_position == "right":
            # 目标右侧
            x = tx + tw + offset_x
            y = ty + (th - watermark_height) // 2 + offset_y
        elif tracking_position == "on_target":
            # 目标上（中心）
            x = tx + (tw - watermark_width) // 2 + offset_x
            y = ty + (th - watermark_height) // 2 + offset_y
        else:
            x = tx + offset_x
            y = ty + offset_y

        # 确保在帧内
        x = max(0, min(x, frame_width - watermark_width))
        y = max(0, min(y, frame_height - watermark_height))

        return (x, y)

    def smooth_position(
        self,
        current_pos: Tuple[int, int],
        previous_pos: Optional[Tuple[int, int]],
        smoothing_factor: float
    ) -> Tuple[int, int]:
        """
        平滑位置变化（减少抖动）

        Args:
            current_pos: 当前位置
            previous_pos: 上一帧位置
            smoothing_factor: 平滑系数（0-1，越小越平滑）

        Returns:
            平滑后的位置
        """
        if previous_pos is None:
            return current_pos

        x = int(previous_pos[0] * (1 - smoothing_factor) + current_pos[0] * smoothing_factor)
        y = int(previous_pos[1] * (1 - smoothing_factor) + current_pos[1] * smoothing_factor)

        return (x, y)

    def check_occlusion(
        self,
        frame: np.ndarray,
        watermark_bbox: Tuple[int, int, int, int],
        method: str = "brightness"
    ) -> float:
        """
        检测水印区域是否遮挡重要内容

        Args:
            frame: 视频帧
            watermark_bbox: (x, y, w, h) 水印边界框
            method: 检测方法

        Returns:
            遮挡分数（0-1，越高越可能遮挡重要内容）
        """
        x, y, w, h = watermark_bbox

        # 确保在帧内
        x = max(0, x)
        y = max(0, y)
        w = min(w, frame.shape[1] - x)
        h = min(h, frame.shape[0] - y)

        if w <= 0 or h <= 0:
            return 0.0

        roi = frame[y:y+h, x:x+w]

        if method == "brightness":
            # 亮度检测：亮度高的区域可能是重要内容
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray) / 255.0
            return brightness

        elif method == "edge":
            # 边缘检测：边缘多的区域可能是重要内容
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / (w * h)
            return edge_density

        elif method == "saliency":
            # 显著性检测（简化版）
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            saliency = cv2.GaussianBlur(gray, (5, 5), 0)
            saliency_score = np.std(saliency) / 255.0
            return saliency_score

        return 0.0

    def find_best_position(
        self,
        frame: np.ndarray,
        watermark_width: int,
        watermark_height: int,
        candidate_positions: List[Tuple[int, int]],
        occlusion_method: str
    ) -> Tuple[int, int]:
        """
        在候选位置中找到最佳位置（遮挡最少）

        Args:
            frame: 视频帧
            watermark_width: 水印宽度
            watermark_height: 水印高度
            candidate_positions: 候选位置列表
            occlusion_method: 遮挡检测方法

        Returns:
            最佳位置 (x, y)
        """
        best_pos = candidate_positions[0]
        min_occlusion = float('inf')

        for pos in candidate_positions:
            x, y = pos
            bbox = (x, y, watermark_width, watermark_height)
            occlusion_score = self.check_occlusion(frame, bbox, occlusion_method)

            if occlusion_score < min_occlusion:
                min_occlusion = occlusion_score
                best_pos = pos

        return best_pos

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
            print(f"[VideoWatermarkAdvanced] 自动检测背景颜色: RGB{tuple(bg_color)}")

        # 计算每个像素与背景颜色的差异
        diff = np.abs(image.astype(np.float32) - bg_color.astype(np.float32))
        diff_sum = np.sum(diff, axis=2)  # 三个通道的差异总和

        # 创建alpha通道：差异小的像素（接近背景色）设为透明
        alpha = np.where(diff_sum < (255 - threshold) * 3, 0, 255).astype(np.uint8)

        # 边缘羽化（可选，使边缘更平滑）
        alpha = cv2.GaussianBlur(alpha, (3, 3), 0)

        # 合并RGB和Alpha
        rgba = np.dstack([image, alpha])

        # 统计透明像素
        transparent_pixels = np.sum(alpha == 0)
        total_pixels = h * w
        transparent_ratio = transparent_pixels / total_pixels * 100

        print(f"[VideoWatermarkAdvanced] 抠图完成:")
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
        margin_y: int
    ) -> Tuple[int, int]:
        """计算水印位置（9宫格）"""
        if position == "top_left":
            return (margin_x, margin_y)
        elif position == "top_center":
            return ((frame_width - watermark_width) // 2, margin_y)
        elif position == "top_right":
            return (frame_width - watermark_width - margin_x, margin_y)
        elif position == "center_left":
            return (margin_x, (frame_height - watermark_height) // 2)
        elif position == "center":
            return ((frame_width - watermark_width) // 2, (frame_height - watermark_height) // 2)
        elif position == "center_right":
            return (frame_width - watermark_width - margin_x, (frame_height - watermark_height) // 2)
        elif position == "bottom_left":
            return (margin_x, frame_height - watermark_height - margin_y)
        elif position == "bottom_center":
            return ((frame_width - watermark_width) // 2, frame_height - watermark_height - margin_y)
        elif position == "bottom_right":
            return (frame_width - watermark_width - margin_x, frame_height - watermark_height - margin_y)
        else:
            return (margin_x, frame_height - watermark_height - margin_y)

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
        # 计算有效持续时间
        effective_duration = animation_duration
        current_time = frame_idx / fps
        animation_frames = int(effective_duration * fps)

        x, y = base_x, base_y
        opacity = base_opacity
        scale = 1.0
        rotation_angle = 0.0

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
            # 移动动画
            progress = (frame_idx % animation_frames) / animation_frames

            if move_direction == "left_to_right":
                x = int(progress * (frame_width - watermark_width))
            elif move_direction == "right_to_left":
                x = int((1 - progress) * (frame_width - watermark_width))
            elif move_direction == "top_to_bottom":
                y = int(progress * (frame_height - watermark_height))
            elif move_direction == "bottom_to_top":
                y = int((1 - progress) * (frame_height - watermark_height))

        elif animation == "slide_in":
            if frame_idx < animation_frames:
                progress = frame_idx / animation_frames
                if move_direction in ["left_to_right"]:
                    x = int(base_x + (0 - base_x - watermark_width) * (1 - progress))
                elif move_direction in ["top_to_bottom"]:
                    y = int(base_y + (0 - base_y - watermark_height) * (1 - progress))

        elif animation == "slide_out":
            remaining_frames = total_frames - frame_idx
            if remaining_frames < animation_frames:
                progress = remaining_frames / animation_frames
                if move_direction in ["left_to_right"]:
                    x = int(base_x + (frame_width - base_x) * (1 - progress))
                elif move_direction in ["top_to_bottom"]:
                    y = int(base_y + (frame_height - base_y) * (1 - progress))

        elif animation == "scale":
            # 缩放动画
            progress = (frame_idx % animation_frames) / animation_frames
            scale = scale_range_min + (scale_range_max - scale_range_min) * abs(np.sin(progress * np.pi))

        elif animation == "blink":
            # 闪烁动画
            blink_cycle = int(fps / blink_frequency)
            if blink_cycle > 0 and (frame_idx % blink_cycle) < (blink_cycle // 2):
                opacity = base_opacity
            else:
                opacity = 0.0

        elif animation == "rotate":
            # 旋转动画
            rotation_angle = (current_time * rotation_speed) % 360

        # ========== 新增动画效果 ==========

        elif animation == "bounce":
            # 弹跳效果 - 从上方弹跳进入，像球一样有弹性
            if frame_idx < animation_frames:
                progress = frame_idx / animation_frames
                # 使用弹性缓动函数
                bounce_progress = self._ease_out_bounce(progress)
                # 从顶部弹跳到目标位置
                y = int(base_y - (frame_height - base_y) * (1 - bounce_progress))

        elif animation == "pulse":
            # 脉冲效果 - 周期性放大缩小，像心跳一样
            progress = (frame_idx % animation_frames) / animation_frames
            # 使用正弦波创建脉冲效果
            pulse = 0.85 + 0.15 * np.sin(progress * 2 * np.pi)
            scale = pulse

        elif animation == "swing":
            # 摇摆效果 - 左右摇摆，像钟摆一样
            progress = (frame_idx % animation_frames) / animation_frames
            # 使用正弦波创建摇摆效果
            swing_angle = 15 * np.sin(progress * 2 * np.pi)  # ±15度摇摆
            rotation_angle = swing_angle

        elif animation == "wave":
            # 波浪效果 - 沿着波浪路径移动
            progress = (frame_idx % animation_frames) / animation_frames
            # 水平移动
            x = int(base_x + (frame_width - watermark_width - base_x) * progress)
            # 垂直波浪
            wave_amplitude = 50  # 波浪幅度
            y = int(base_y + wave_amplitude * np.sin(progress * 4 * np.pi))

        elif animation == "glint":
            # 闪光效果 - 光线从水印上扫过，像钻石闪光
            progress = (frame_idx % animation_frames) / animation_frames
            # 创建闪光效果：快速增亮然后恢复
            if 0.3 < progress < 0.5:
                # 闪光时刻
                glint_progress = (progress - 0.3) / 0.2
                opacity = base_opacity * (1.0 + 0.5 * np.sin(glint_progress * np.pi))
            else:
                opacity = base_opacity
            # 同时添加轻微缩放
            if 0.3 < progress < 0.5:
                scale = 1.0 + 0.1 * np.sin((progress - 0.3) / 0.2 * np.pi)

        elif animation == "breathe":
            # 呼吸效果 - 缓慢放大缩小 + 透明度变化
            progress = (frame_idx % animation_frames) / animation_frames
            # 使用正弦波创建呼吸效果
            breathe = np.sin(progress * 2 * np.pi)
            # 缩放变化 (0.9 - 1.1)
            scale = 1.0 + 0.1 * breathe
            # 透明度变化
            opacity = base_opacity * (0.85 + 0.15 * breathe)

        elif animation == "shake":
            # 抖动效果 - 快速抖动，吸引注意
            progress = (frame_idx % animation_frames) / animation_frames
            # 高频抖动
            shake_intensity = 5  # 抖动强度（像素）
            shake_freq = 20  # 抖动频率
            x = int(base_x + shake_intensity * np.sin(progress * shake_freq * 2 * np.pi))
            y = int(base_y + shake_intensity * np.cos(progress * shake_freq * 2 * np.pi))

        elif animation == "flip":
            # 翻转效果 - 3D翻转（水平翻转）
            progress = (frame_idx % animation_frames) / animation_frames
            # 使用余弦函数模拟3D翻转的缩放效果
            flip_scale = abs(np.cos(progress * 2 * np.pi))
            scale = max(0.1, flip_scale)  # 避免完全消失
            # 翻转时调整透明度
            if flip_scale < 0.3:
                opacity = base_opacity * (flip_scale / 0.3)

        elif animation == "rainbow":
            # 彩虹效果 - 颜色循环变化
            # 注意：这个效果需要在应用水印时处理颜色变化
            # 这里只设置一个标记，实际颜色变化在 apply_watermark 中处理
            progress = (frame_idx % animation_frames) / animation_frames
            # 存储彩虹进度（将通过 rotation_angle 传递，因为我们没有其他返回值）
            rotation_angle = progress * 360  # 0-360度表示色相

        elif animation == "typewriter":
            # 打字机效果 - 文字逐个出现
            # 注意：这个效果主要用于文字水印
            if frame_idx < animation_frames:
                progress = frame_idx / animation_frames
                # 通过透明度渐变模拟打字效果
                opacity = base_opacity * min(1.0, progress * 2)
                # 同时添加轻微的滑入效果
                x = int(base_x - 20 * (1 - min(1.0, progress * 2)))

        return (x, y, opacity, scale, rotation_angle)

    def _ease_out_bounce(self, t: float) -> float:
        """
        弹性缓动函数 - 用于弹跳效果

        Args:
            t: 进度 (0-1)

        Returns:
            缓动后的进度
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

        return (x, y, opacity, scale, rotation_angle)

    def create_text_watermark(
        self,
        text: str,
        font_size: int,
        color: Tuple[int, int, int],
        add_shadow: bool,
        shadow_offset: int
    ) -> np.ndarray:
        """创建文字水印（简化版）"""
        padding = 20
        img_width = len(text) * font_size + padding * 2
        img_height = font_size * 2 + padding * 2

        img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/arial.ttf",
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

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        img = Image.new('RGBA', (text_width + padding * 2, text_height + padding * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        text_x = padding
        text_y = padding

        if add_shadow:
            shadow_color = (0, 0, 0, 128)
            draw.text((text_x + shadow_offset, text_y + shadow_offset), text, font=font, fill=shadow_color)

        text_color = (*color, 255)
        draw.text((text_x, text_y), text, font=font, fill=text_color)

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
        """叠加水印到帧上（支持缩放、旋转和彩虹效果）"""
        # 记录原始尺寸（用于中心固定）
        original_h, original_w = watermark.shape[:2]
        original_center_x = x + original_w // 2
        original_center_y = y + original_h // 2

        # 缩放水印
        if scale != 1.0:
            new_width = int(watermark.shape[1] * scale)
            new_height = int(watermark.shape[0] * scale)
            if new_width > 0 and new_height > 0:
                watermark = cv2.resize(watermark, (new_width, new_height), interpolation=cv2.INTER_AREA)
                # 更新中心位置（缩放后）
                scaled_h, scaled_w = watermark.shape[:2]
                original_center_x = x + scaled_w // 2
                original_center_y = y + scaled_h // 2

        # 旋转水印
        if rotation_angle != 0.0:
            wm_h, wm_w = watermark.shape[:2]
            center = (wm_w // 2, wm_h // 2)

            rotation_matrix = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)

            cos = np.abs(rotation_matrix[0, 0])
            sin = np.abs(rotation_matrix[0, 1])
            new_w = int((wm_h * sin) + (wm_w * cos))
            new_h = int((wm_h * cos) + (wm_w * sin))

            rotation_matrix[0, 2] += (new_w / 2) - center[0]
            rotation_matrix[1, 2] += (new_h / 2) - center[1]

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

        x = max(0, min(x, frame_w - wm_w))
        y = max(0, min(y, frame_h - wm_h))

        x2 = min(x + wm_w, frame_w)
        y2 = min(y + wm_h, frame_h)
        wm_w_actual = x2 - x
        wm_h_actual = y2 - y

        if wm_w_actual <= 0 or wm_h_actual <= 0:
            return frame

        roi = frame[y:y2, x:x2]
        watermark_crop = watermark[:wm_h_actual, :wm_w_actual]

        if watermark_crop.shape[2] == 4:
            alpha = watermark_crop[:, :, 3:4] / 255.0 * opacity
            watermark_rgb = watermark_crop[:, :, :3]
        else:
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

        blended = roi * (1 - alpha) + watermark_rgb * alpha
        frame[y:y2, x:x2] = blended.astype(np.uint8)

        return frame

    def process_single_video(
        self,
        video_path: str,
        output_path: str,
        watermark: np.ndarray,
        tracking_mode: str,
        tracking_position: str,
        tracking_offset_x: int,
        tracking_offset_y: int,
        enable_anti_occlusion: bool,
        occlusion_detection_method: str,
        min_target_confidence: float,
        smooth_tracking: bool,
        smoothing_factor: float,
        text_opacity: float,
        text_position: str,
        margin_x: int,
        margin_y: int,
        animation: str,
        animation_duration: float,
        move_direction: str,
        rotation_speed: float,
        scale_range_min: float,
        scale_range_max: float,
        blink_frequency: float,
        enable_multi_position: bool,
        multi_position_preset: str,
        position_list: str,
        position_switch_interval: float,
        watermark_type: str = "text",
        image_scale: float = 0.15
    ) -> str:
        """
        处理单个视频
        """
        print(f"\n[VideoWatermarkAdvanced] 处理视频: {os.path.basename(video_path)}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception(f"无法打开视频: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"  - 分辨率: {width}x{height}")
        print(f"  - 总帧数: {total_frames}")
        print(f"  - 帧率: {fps:.2f} fps")

        # ✅ 缩放图片水印（如果是图片类型）
        if watermark_type in ["image", "both"]:
            original_wm_width = watermark.shape[1]
            original_wm_height = watermark.shape[0]
            target_width = int(width * image_scale)
            aspect_ratio = watermark.shape[0] / watermark.shape[1]
            target_height = int(target_width * aspect_ratio)

            print(f"[VideoWatermarkAdvanced] 图片缩放计算:")
            print(f"  - 视频宽度: {width}px")
            print(f"  - image_scale参数: {image_scale}")
            print(f"  - 原始图片: {original_wm_width}x{original_wm_height}")
            print(f"  - 目标宽度: {target_width}px ({width} * {image_scale})")
            print(f"  - 目标高度: {target_height}px")

            watermark = cv2.resize(watermark, (target_width, target_height), interpolation=cv2.INTER_AREA)
            print(f"  - 缩放后: {watermark.shape[1]}x{watermark.shape[0]}")

        # 创建输出视频
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        wm_h, wm_w = watermark.shape[:2]
        previous_pos = None
        frame_idx = 0

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

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_idx / fps

            # 确定基础位置
            if enable_multi_position and positions:
                # 多位置模式：根据时间切换位置
                position_index = int(current_time / position_switch_interval) % len(positions)
                current_position = positions[position_index]
                base_x, base_y = self.calculate_position(
                    current_position, width, height, wm_w, wm_h, margin_x, margin_y
                )
            elif tracking_mode != "none":
                # 跟踪模式
                targets = self.detect_targets(frame, tracking_mode, min_target_confidence)

                if targets:
                    target = targets[0]
                    current_pos = self.calculate_tracking_position(
                        target, tracking_position, wm_w, wm_h,
                        tracking_offset_x, tracking_offset_y, width, height
                    )

                    # 平滑跟踪（降低抖动）
                    if smooth_tracking and previous_pos is not None:
                        # 使用更强的平滑
                        smooth_factor = max(0.1, smoothing_factor * 0.5)  # 减半平滑系数
                        current_pos = self.smooth_position(current_pos, previous_pos, smooth_factor)

                    # 防遮挡
                    if enable_anti_occlusion:
                        candidate_positions = [
                            current_pos,
                            (current_pos[0], current_pos[1] - 50),
                            (current_pos[0], current_pos[1] + 50),
                            (current_pos[0] - 50, current_pos[1]),
                            (current_pos[0] + 50, current_pos[1]),
                        ]
                        current_pos = self.find_best_position(
                            frame, wm_w, wm_h, candidate_positions, occlusion_detection_method
                        )

                    base_x, base_y = current_pos
                    previous_pos = current_pos
                else:
                    # 没有检测到目标，使用默认位置
                    base_x, base_y = self.calculate_position(
                        text_position, width, height, wm_w, wm_h, margin_x, margin_y
                    )
            else:
                # 固定位置
                base_x, base_y = self.calculate_position(
                    text_position, width, height, wm_w, wm_h, margin_x, margin_y
                )

            # 应用动画效果
            x, y, opacity, scale, rotation_angle = self.apply_animation(
                frame_idx, total_frames, fps,
                animation, animation_duration,
                base_x, base_y, width, height, wm_w, wm_h,
                move_direction, rotation_speed,
                scale_range_min, scale_range_max,
                blink_frequency, text_opacity
            )

            # 叠加水印
            frame = self.overlay_watermark(frame, watermark, x, y, opacity, scale, rotation_angle, animation)

            out.write(frame)
            frame_idx += 1

            if frame_idx % 30 == 0:
                progress = (frame_idx / total_frames) * 100
                print(f"  进度: {progress:.1f}% ({frame_idx}/{total_frames})")

        cap.release()
        out.release()

        print(f"  ✅ 完成: {os.path.basename(output_path)}")
        return output_path

    def add_watermark_advanced(
        self,
        video: str,
        watermark_type: str,
        enable_watermark: bool,
        tracking_mode: str = "none",
        tracking_position: str = "above",
        tracking_offset_x: int = 0,
        tracking_offset_y: int = -50,
        enable_anti_occlusion: bool = False,
        occlusion_detection_method: str = "brightness",
        min_target_confidence: float = 0.5,
        smooth_tracking: bool = True,
        smoothing_factor: float = 0.3,
        batch_mode: bool = False,
        batch_video_folder: str = "",
        batch_output_folder: str = "",
        text_content: str = "© 2025 Your Brand",
        font_size: int = 48,
        font_color: str = "white",
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
        text_effect: str = "none",
        margin_x: int = 20,
        margin_y: int = 20,
        animation: str = "none",
        animation_duration: float = 2.0,
        move_direction: str = "left_to_right",
        rotation_speed: float = 30.0,
        scale_range_min: float = 0.5,
        scale_range_max: float = 1.5,
        blink_frequency: float = 2.0,
        enable_multi_position: bool = False,
        multi_position_preset: str = "four_corners",
        position_list: str = "top_left,top_right,bottom_left,bottom_right",
        position_switch_interval: float = 3.0,
        add_shadow: bool = True,
        shadow_offset: int = 2
    ) -> Tuple[str, str]:
        """
        高级水印处理主函数
        """
        if not enable_watermark:
            return (video, "水印已禁用")

        print("\n" + "="*70)
        print("🎨 VideoWatermarkAdvanced - 高级视频水印（专业级）")
        print("="*70)

        # 准备水印
        text_watermark = None
        image_watermark = None

        # 准备文字水印
        if watermark_type in ["text", "both"]:
            color = (255, 255, 255) if font_color == "white" else (0, 0, 0)
            text_wm = self.create_text_watermark(
                text_content, font_size, color, add_shadow, shadow_offset
            )
            # 转换为BGRA格式
            text_watermark = cv2.cvtColor(text_wm, cv2.COLOR_RGBA2BGRA)
            print(f"[VideoWatermarkAdvanced] 文字水印: '{text_content}', 尺寸: {text_watermark.shape[:2]}")

        # 准备图片水印
        if watermark_type in ["image", "both"] and watermark_image is not None:
            img_tensor = watermark_image[0]
            img_np = (img_tensor.cpu().numpy() * 255).astype(np.uint8)

            # ✅ 转换颜色格式：ComfyUI使用RGB，OpenCV使用BGR
            if img_np.shape[2] == 3:
                img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                print(f"[VideoWatermarkAdvanced] RGB转BGR")
            elif img_np.shape[2] == 4:
                img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGRA)
                print(f"[VideoWatermarkAdvanced] RGBA转BGRA")

            # 自动抠图（移除背景）
            if auto_remove_bg:
                print(f"[VideoWatermarkAdvanced] 开始自动抠图...")
                img_np = self.remove_background(img_np, bg_color_mode, bg_threshold)

            # 检查是否有alpha通道
            if img_np.shape[2] == 4:
                print(f"[VideoWatermarkAdvanced] 检测到BGRA图片，保留透明度")
            elif img_np.shape[2] == 3:
                # BGR图片，添加alpha通道
                alpha = np.ones((img_np.shape[0], img_np.shape[1], 1), dtype=np.uint8) * 255
                img_np = np.concatenate([img_np, alpha], axis=2)
                print(f"[VideoWatermarkAdvanced] BGR图片，添加alpha通道")

            image_watermark = img_np
            print(f"[VideoWatermarkAdvanced] 图片水印（原始尺寸）: {image_watermark.shape[:2]}, 自动抠图: {auto_remove_bg}")

        # 组合水印
        watermark = None
        if watermark_type == "both" and text_watermark is not None and image_watermark is not None:
            # 组合模式
            if combined_layout == "separate":
                # 分别显示（使用图片水印，文字水印被忽略）
                watermark = image_watermark
                print(f"[VideoWatermarkAdvanced] 组合模式: separate（分别显示，仅使用图片）")
            else:
                # 普通组合显示
                watermark = self.combine_text_and_image(
                    text_watermark, image_watermark, combined_layout, combined_spacing
                )
                print(f"[VideoWatermarkAdvanced] 组合模式: {combined_layout}, 间距: {combined_spacing}px")
                print(f"[VideoWatermarkAdvanced] 组合后尺寸: {watermark.shape[:2]}")
        elif text_watermark is not None:
            watermark = text_watermark
        elif image_watermark is not None:
            watermark = image_watermark

        if watermark is None:
            return (video, "未提供水印内容")

        # 显示高级功能状态
        print(f"[VideoWatermarkAdvanced] 高级功能:")
        print(f"  - 目标跟踪: {tracking_mode}")
        if tracking_mode != "none":
            print(f"  - 跟踪位置: {tracking_position}")
            print(f"  - 偏移: ({tracking_offset_x}, {tracking_offset_y})")
            print(f"  - 平滑跟踪: {smooth_tracking}")
        print(f"  - 防遮挡: {enable_anti_occlusion}")
        if enable_anti_occlusion:
            print(f"  - 检测方法: {occlusion_detection_method}")
        print(f"  - 动画效果: {animation}")
        print(f"  - 多位置模式: {enable_multi_position}")
        if enable_multi_position:
            print(f"  - 位置列表: {position_list}")
            print(f"  - 切换间隔: {position_switch_interval}秒")
        print(f"  - 批量模式: {batch_mode}")

        # 批量处理
        if batch_mode and batch_video_folder:
            print(f"\n[VideoWatermarkAdvanced] 📦 批量处理模式")
            print(f"  - 输入文件夹: {batch_video_folder}")
            print(f"  - 输出文件夹: {batch_output_folder}")

            # 查找所有视频文件
            video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv']
            video_files = []
            for ext in video_extensions:
                video_files.extend(glob.glob(os.path.join(batch_video_folder, ext)))

            if not video_files:
                return (video, f"未在 {batch_video_folder} 中找到视频文件")

            print(f"  - 找到 {len(video_files)} 个视频文件")

            # 创建输出文件夹
            if not batch_output_folder:
                batch_output_folder = os.path.join(batch_video_folder, "watermarked")
            os.makedirs(batch_output_folder, exist_ok=True)

            # 处理每个视频
            processed_videos = []
            for i, video_file in enumerate(video_files):
                print(f"\n[{i+1}/{len(video_files)}] 处理: {os.path.basename(video_file)}")

                output_filename = f"watermarked_{os.path.basename(video_file)}"
                output_path = os.path.join(batch_output_folder, output_filename)

                try:
                    result = self.process_single_video(
                        video_file, output_path, watermark,
                        tracking_mode, tracking_position,
                        tracking_offset_x, tracking_offset_y,
                        enable_anti_occlusion, occlusion_detection_method,
                        min_target_confidence, smooth_tracking, smoothing_factor,
                        text_opacity, text_position, margin_x, margin_y,
                        animation, animation_duration, move_direction,
                        rotation_speed, scale_range_min, scale_range_max,
                        blink_frequency, enable_multi_position,
                        multi_position_preset, position_list, position_switch_interval,
                        watermark_type, image_scale
                    )
                    processed_videos.append(result)
                except Exception as e:
                    print(f"  ❌ 处理失败: {str(e)}")

            info = f"""
批量处理完成：
- 输入文件夹: {batch_video_folder}
- 输出文件夹: {batch_output_folder}
- 处理视频数: {len(processed_videos)}/{len(video_files)}
- 跟踪模式: {tracking_mode}
- 防遮挡: {enable_anti_occlusion}
            """

            # 返回第一个处理的视频
            return (processed_videos[0] if processed_videos else video, info.strip())

        # 单个视频处理
        else:
            # 创建输出文件（保存到ComfyUI output目录）
            from folder_paths import get_output_directory
            output_dir = get_output_directory()

            # 生成唯一文件名
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(video))[0]
            output_filename = f"watermarked_advanced_{base_name}_{timestamp}.mp4"
            output_video = os.path.join(output_dir, output_filename)

            result = self.process_single_video(
                video, output_video, watermark,
                tracking_mode, tracking_position,
                tracking_offset_x, tracking_offset_y,
                enable_anti_occlusion, occlusion_detection_method,
                min_target_confidence, smooth_tracking, smoothing_factor,
                text_opacity, text_position, margin_x, margin_y,
                animation, animation_duration, move_direction,
                rotation_speed, scale_range_min, scale_range_max,
                blink_frequency, enable_multi_position,
                multi_position_preset, position_list, position_switch_interval,
                watermark_type, image_scale
            )

            info = f"""
高级水印处理完成：
- 输入视频: {os.path.basename(video)}
- 跟踪模式: {tracking_mode}
- 防遮挡: {enable_anti_occlusion}
- 动画效果: {animation}
- 多位置模式: {enable_multi_position}
- 输出视频: {os.path.basename(output_video)}
            """

            return (result, info.strip())


# 注册节点
NODE_CLASS_MAPPINGS = {
    "VideoWatermarkAdvanced": VideoWatermarkAdvanced
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VideoWatermarkAdvanced": "🎨 Video Watermark Advanced (高级水印)"
}

