"""
ComfyUI_Sora - 配置管理模块
管理API密钥、默认参数等配置
"""

import os
import json
from typing import Dict, Any, Optional


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.config_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            'config.json'
        )
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ComfyUI_Sora] 加载配置文件失败: {e}")
                return self._get_default_config()
        else:
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'api_key': '',
            'api_provider': 't8',  # 't8', 'comfly', 或 'aabao'
            'base_url': 'https://ai.t8star.cn/v1',
            'comfly_api_key': '',  # Comfly API密钥
            'comfly_base_url': 'https://ai.comfly.chat/v1',
            'aabao_api_key': '',  # Aabao (newapi.ai) API密钥
            'aabao_base_url': 'https://api.aabao.top/v1',  # Aabao API基础URL
            'timeout': 600,
            'default_model': 'sora-2',
            'default_quality': '1080p',
            'default_aspect_ratio': '16:9',
            'default_duration': 5,
            'max_retries': 3,
            'retry_delay': 5,
        }
    
    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ComfyUI_Sora] 保存配置文件失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        self.config[key] = value
        self.save_config()
    
    def get_api_key(self) -> str:
        """获取API密钥"""
        return self.config.get('api_key', '')
    
    def set_api_key(self, api_key: str) -> None:
        """设置API密钥"""
        self.set('api_key', api_key)
    
    def get_base_url(self) -> str:
        """获取API基础URL"""
        return self.config.get('base_url', 'https://ai.t8star.cn/v1')

    def set_base_url(self, base_url: str) -> None:
        """设置API基础URL"""
        self.set('base_url', base_url)

    def get_api_provider(self) -> str:
        """获取API提供商"""
        return self.config.get('api_provider', 't8')

    def set_api_provider(self, provider: str) -> None:
        """设置API提供商"""
        self.set('api_provider', provider)

    def get_comfly_api_key(self) -> str:
        """获取Comfly API密钥"""
        return self.config.get('comfly_api_key', '')

    def set_comfly_api_key(self, api_key: str) -> None:
        """设置Comfly API密钥"""
        self.set('comfly_api_key', api_key)

    def get_comfly_base_url(self) -> str:
        """获取Comfly API基础URL"""
        return self.config.get('comfly_base_url', 'https://ai.comfly.chat/v1')

    def set_comfly_base_url(self, base_url: str) -> None:
        """设置Comfly API基础URL"""
        self.set('comfly_base_url', base_url)

    def get_aabao_api_key(self) -> str:
        """获取Aabao API密钥"""
        return self.config.get('aabao_api_key', '')

    def set_aabao_api_key(self, api_key: str) -> None:
        """设置Aabao API密钥"""
        self.set('aabao_api_key', api_key)

    def get_aabao_base_url(self) -> str:
        """获取Aabao API基础URL"""
        return self.config.get('aabao_base_url', 'https://api.aabao.top/v1')

    def set_aabao_base_url(self, base_url: str) -> None:
        """设置Aabao API基础URL"""
        self.set('aabao_base_url', base_url)

    def get_current_api_config(self, provider: Optional[str] = None) -> Dict[str, str]:
        """
        获取当前API配置（根据提供商）

        Args:
            provider: API提供商，如果为None则使用配置中的默认提供商

        Returns:
            Dict[str, str]: 包含api_key和base_url的字典
        """
        if provider is None:
            provider = self.get_api_provider()

        if provider == 'comfly':
            return {
                'api_key': self.get_comfly_api_key(),
                'base_url': self.get_comfly_base_url()
            }
        elif provider == 'aabao':
            return {
                'api_key': self.get_aabao_api_key(),
                'base_url': self.get_aabao_base_url()
            }
        else:  # 't8' 或其他
            return {
                'api_key': self.get_api_key(),
                'base_url': self.get_base_url()
            }


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config() -> Dict[str, Any]:
    """获取配置字典（兼容旧代码）"""
    return config_manager.config


def save_config(config: Dict[str, Any]) -> None:
    """保存配置字典（兼容旧代码）"""
    config_manager.config = config
    config_manager.save_config()

