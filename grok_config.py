"""
ComfyUI_Sora - Grok Imagine 配置管理模块
管理 Grok Imagine API 的配置
"""

import os
import json
from typing import Dict, Any


class GrokConfigManager:
    """Grok Imagine 配置管理器"""
    
    def __init__(self):
        self.config_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            'grok-config.json'
        )
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print(f"[Grok Config] 成功加载配置文件: {self.config_file}")
                    return config
            except Exception as e:
                print(f"[Grok Config] 加载配置文件失败: {e}")
                return self._get_default_config()
        else:
            print(f"[Grok Config] 配置文件不存在，使用默认配置")
            default_config = self._get_default_config()
            self._save_default_config(default_config)
            return default_config
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'api_key': '',
            'base_url': 'https://api.aabao.top/v1',
            'timeout': 600,
            'default_model': 'grok-imagine-0.9',
            'default_duration': '10',
            'default_quality': 'high',
            'default_style': 'normal',
            'max_retries': 3,
            'retry_delay': 5,
            'proxy_url': ''
        }
    
    def _save_default_config(self, config: Dict[str, Any]) -> None:
        """保存默认配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            print(f"[Grok Config] 已创建默认配置文件: {self.config_file}")
        except Exception as e:
            print(f"[Grok Config] 创建配置文件失败: {e}")
    
    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            print(f"[Grok Config] 配置已保存")
            return True
        except Exception as e:
            print(f"[Grok Config] 保存配置文件失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        value = self.config.get(key, default)
        return value
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        self.config[key] = value
        self.save_config()
    
    def get_api_key(self) -> str:
        """获取 API 密钥"""
        return self.config.get('api_key', '')
    
    def set_api_key(self, api_key: str) -> None:
        """设置 API 密钥"""
        self.set('api_key', api_key)
    
    def get_base_url(self) -> str:
        """获取 API 基础 URL"""
        return self.config.get('base_url', 'https://api.aabao.top/v1')
    
    def set_base_url(self, base_url: str) -> None:
        """设置 API 基础 URL"""
        self.set('base_url', base_url)
    
    def get_timeout(self) -> int:
        """获取超时时间"""
        return self.config.get('timeout', 600)
    
    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.config.get('default_model', 'grok-imagine-0.9')

    def get_default_duration(self) -> str:
        """获取默认时长"""
        return self.config.get('default_duration', '10')

    def get_default_quality(self) -> str:
        """获取默认质量"""
        return self.config.get('default_quality', 'high')

    def get_default_style(self) -> str:
        """获取默认风格"""
        return self.config.get('default_style', 'normal')
    
    def get_proxy_url(self) -> str:
        """获取代理 URL"""
        return self.config.get('proxy_url', '')
    
    def reload(self) -> None:
        """重新加载配置"""
        self.config = self._load_config()
        print(f"[Grok Config] 配置已重新加载")
    
    def print_config(self) -> None:
        """打印当前配置（隐藏敏感信息）"""
        safe_config = self.config.copy()
        if safe_config.get('api_key'):
            safe_config['api_key'] = safe_config['api_key'][:20] + '...'
        print(f"[Grok Config] 当前配置:")
        print(json.dumps(safe_config, indent=2, ensure_ascii=False))


# 创建全局配置管理器实例
grok_config_manager = GrokConfigManager()

