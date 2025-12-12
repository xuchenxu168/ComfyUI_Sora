# coding: utf-8
import os, json, requests, torch, numpy as np
from PIL import Image
from io import BytesIO
from typing import Optional, Tuple, Dict, Any
import comfy.utils
from comfy.comfy_types import IO

try:
    from .config import config_manager
except ImportError:
    config_manager = None

class StoryboardCharacter:
    API_ENDPOINTS = {
        'aabao': {'node_url': 'https://api.aabao.top', 'endpoint': '/v1/sora-2-characters'},
        'comfly': {'base_url': 'https://ai.t8star.cn', 'endpoint': '/sora/v1/characters'},
        'zhenzhen': {'base_url': 'https://ai.t8star.cn', 'endpoint': '/sora/v1/characters'}
    }
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            'required': {
                'api_provider': (['aabao', 'comfly', 'zhenzhen'], {'default': 'aabao'}),
                'timestamps': ('STRING', {'default': '1,3', 'multiline': False}),
            },
            'optional': {
                'api_key': ('STRING', {'default': '', 'multiline': False}),
                'video': (IO.VIDEO,),
                'video_url': ('STRING', {'default': '', 'multiline': False}),
                'character_name': ('STRING', {'default': '', 'multiline': False}),
                'seed': ('INT', {'default': 0, 'min': 0, 'max': 2147483647}),
                'timeout': ('INT', {'default': 300, 'min': 60, 'max': 600, 'step': 30}),
                'download_profile_image': ('BOOLEAN', {'default': True}),
            }
        }
    
    RETURN_TYPES = ('STRING', 'STRING', 'STRING', 'STRING', 'IMAGE', 'STRING')
    RETURN_NAMES = ('character_id', 'username', 'permalink', 'profile_picture_url', 'profile_image', 'response')
    FUNCTION = 'create_character'
    CATEGORY = "Ken-Chen/sora"

NODE_CLASS_MAPPINGS = {'StoryboardCharacter': StoryboardCharacter}
NODE_DISPLAY_NAME_MAPPINGS = {'StoryboardCharacter': 'Storyboard-Character'}
