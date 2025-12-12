code = '''# coding: utf-8
import os, json, requests, torch, numpy as np
from PIL import Image
from io import BytesIO
import comfy.utils
from comfy.comfy_types import IO
try:
    from .config import config_manager
except ImportError:
    config_manager = None

class StoryboardCharacter:
    API_ENDPOINTS = {
        'aabao': {'base_url': 'https://api.aabao.top', 'endpoint': '/v1/sora-2-characters'},
        'comfly': {'base_url': 'https://ai.t8star.cn', 'endpoint': '/sora/v1/characters'},
        'zhenzhen': {'base_url': 'https://ai.t8star.cn', 'endpoint': '/sora/v1/characters'}
    }
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'api_provider': (['aabao', 'comfly', 'zhenzhen'], {'default': 'aabao'}), 'timestamps': ('STRING', {'default': '1,3'})}, 'optional': {'api_key': ('STRING', {'default': ''}), 'video': (IO.VIDEO,), 'video_url': ('STRING', {'default': ''}), 'character_name': ('STRING', {'default': ''}), 'seed': ('INT', {'default': 0, 'min': 0, 'max': 2147483647}), 'timeout': ('INT', {'default': 300, 'min': 60, 'max': 600}), 'download_profile_image': ('BOOLEAN', {'default': True})}}
    RETURN_TYPES = ('STRING', 'STRING', 'STRING', 'STRING', 'IMAGE', 'STRING')
    RETURN_NAMES = ('character_id', 'username', 'permalink', 'profile_picture_url', 'profile_image', 'response')
    FUNCTION = 'create_character'
    CATEGORY = "Ken-Chen/sora"
    def __init__(self): self.timeout = 300
    def _get_api_key(self, api_key, api_provider):
        if api_key and api_key.strip(): return api_key.strip()
        if config_manager:
            try:
                cfg = config_manager.get_config()
                return cfg.get('aabao_api_key', '') or cfg.get('api_key', '') if api_provider == 'aabao' else cfg.get('api_key', '')
            except: pass
        try:
            cp = os.path.join(os.path.dirname(__file__), 'config.json')
            if os.path.exists(cp):
                with open(cp, 'r', encoding='utf-8') as f: cfg = json.load(f)
                return cfg.get('aabao_api_key', '') or cfg.get('api_key', '') if api_provider == 'aabao' else cfg.get('api_key', '')
        except: pass
        return ''
    def _validate_timestamps(self, ts):
        if not ts or ',' not in ts: return False, 'Bad timestamp', 0, 0
        try:
            p = ts.split(','); st, et = float(p[0].strip()), float(p[1].strip())
            if st < 0: return False, 'Negative start', 0, 0
            if et <= st: return False, 'End <= start', 0, 0
            d = et - st
            if d < 1: return False, f'Duration < 1s ({d:.1f}s)', 0, 0
            if d > 3: return False, f'Duration > 3s ({d:.1f}s)', 0, 0
            return True, '', st, et
        except: return False, 'Invalid timestamp', 0, 0
    def _get_video_url(self, video, video_url):
        if video_url and video_url.strip():
            u = video_url.strip()
            return (u, '') if u.startswith(('http://', 'https://')) else ('', 'Bad URL scheme')
        if video: return (getattr(video, 'url', None) or (video.get('url') if isinstance(video, dict) else None) or '', '') if hasattr(video, 'url') or isinstance(video, dict) else ('', 'Need video_url')
        return '', 'No video provided'
    def _download_image(self, url, to=30):
        if not url: return None
        try:
            r = requests.get(url, timeout=to); r.raise_for_status()
            im = Image.open(BytesIO(r.content))
            im = im.convert('RGB') if im.mode != 'RGB' else im
            return torch.from_numpy(np.array(im).astype(np.float32) / 255.0).unsqueeze(0)
        except: return None
    def _create_blank_image(self): return torch.from_numpy(np.array(Image.new('RGB', (256, 256), (200, 200, 200))).astype(np.float32) / 255.0).unsqueeze(0)
    def _call_api(self, prov, key, vurl, ts, seed, name):
        cfg = self.API_ENDPOINTS.get(prov)
        if not cfg: return {'error': f'Unknown provider: {prov}'}
        url = f"{cfg['base_url']}{cfg['endpoint']}"
        hdrs = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
        pl = {'video_url' if prov == 'aabao' else 'url': vurl, 'timestamps': ts}
        if name and prov == 'aabao': pl['name'] = name
        if seed > 0: pl['seed'] = seed
        try:
            print(f'[Storyboard] Calling {prov} API'); resp = requests.post(url, headers=hdrs, json=pl, timeout=self.timeout)
            if resp.status_code != 200: return {'error': f'API error {resp.status_code}: {resp.text[:200]}'}
            return resp.json()
        except Exception as e: return {'error': str(e)}
    def create_character(self, api_provider, timestamps, api_key='', video=None, video_url='', character_name='', seed=0, timeout=300, download_profile_image=True):
        self.timeout = timeout; blank = self._create_blank_image(); pbar = comfy.utils.ProgressBar(100); pbar.update_absolute(5)
        key = self._get_api_key(api_key, api_provider)
        if not key: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': f'No key for {api_provider}'}))
        pbar.update_absolute(10); ok, err, st, et = self._validate_timestamps(timestamps)
        if not ok: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': err}))
        pbar.update_absolute(15); vurl, err = self._get_video_url(video, video_url)
        if err: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': err}))
        pbar.update_absolute(25); res = self._call_api(api_provider, key, vurl, timestamps, seed, character_name); pbar.update_absolute(70)
        if 'error' in res: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': res['error']}))
        cid = res.get('id', '') or res.get('character_id', ''); usr = res.get('username', ''); plink = res.get('permalink', ''); ppurl = res.get('profile_picture_url', '') or res.get('avatar_url', '')
        if not cid: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': 'No character ID', 'raw': res}))
        pbar.update_absolute(80); img = self._download_image(ppurl) if download_profile_image and ppurl else None; pbar.update_absolute(100)
        resp = {'status': 'success', 'character_id': cid, 'username': usr, 'permalink': plink, 'profile_picture_url': ppurl}
        print(f'[Storyboard] OK: {cid}')
        return (cid, usr, plink, ppurl, img if img is not None else blank, json.dumps(resp, ensure_ascii=False))
NODE_CLASS_MAPPINGS = {'StoryboardCharacter': StoryboardCharacter}
NODE_DISPLAY_NAME_MAPPINGS = {'StoryboardCharacter': 'Storyboard-Character'}
'''
with open('storyboard_character.py', 'w', encoding='utf-8') as f: f.write(code)
print('Created!')
