# coding: utf-8
import os, json, requests, torch, numpy as np
import time
import tempfile
import shutil
import mimetypes
from PIL import Image
from io import BytesIO
import comfy.utils
from comfy.comfy_types import IO
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

try:
    from .config import config_manager
except ImportError:
    config_manager = None

class StoryboardCharacter:
    @classmethod
    def _load_config_file(cls):
        cfg = {}
        # Try manager first
        if config_manager:
            try:
                cfg = config_manager.get_config()
            except: pass
        
        # Fallback to local file
        if not cfg:
            try:
                cp = os.path.join(os.path.dirname(__file__), 'config.json')
                if os.path.exists(cp):
                    with open(cp, 'r', encoding='utf-8') as f: cfg = json.load(f)
            except: pass
        return cfg

    @classmethod
    def INPUT_TYPES(cls):
        providers = ['t8', 't8-us', 't8-hk', 'comfly', 'comfly-us', 'comfly-hk', 'aabao']
        return {
            'required': {
                'api_provider': (providers, {'default': 't8'}),
                'api_key': ('STRING', {'default': ''}),
                'timestamps': ('STRING', {'default': '1,3'}),
            },
            'optional': {
                'video': (IO.VIDEO,),
                'video_url': ('STRING', {'default': ''}),
                'character_name': ('STRING', {'default': ''}),
                'seed': ('INT', {'default': 0, 'min': 0, 'max': 2147483647}),
                'timeout': ('INT', {'default': 300, 'min': 60, 'max': 600}),
                'download_profile_image': ('BOOLEAN', {'default': True}),
            }
        }
    RETURN_TYPES = ('STRING', 'STRING', 'STRING', 'STRING', 'IMAGE', 'STRING')
    RETURN_NAMES = ('character_id', 'username', 'permalink', 'profile_picture_url', 'profile_image', 'response')
    FUNCTION = 'create_character'
    CATEGORY = "Ken-Chen/sora"
    def __init__(self): self.timeout = 300

    def _get_config_value(self, cfg, base_name, suffix):
        val = cfg.get(f'{base_name}_{suffix}') or cfg.get(f'{base_name} {suffix}')
        if not val and base_name == 't8':
             val = cfg.get(f'zhenzhen_{suffix}') or cfg.get(f'zhenzhen {suffix}')
        return val

    def _get_api_key(self, cfg, api_key_input, api_provider):
        if api_key_input and api_key_input.strip(): return api_key_input.strip()
        key = ''
        if api_provider == 'aabao':
            key = self._get_config_value(cfg, 'aabao', 'api_key')
        elif api_provider == 'comfly':
            key = self._get_config_value(cfg, 'comfly', 'api_key')
        elif api_provider == 't8':
            key = self._get_config_value(cfg, 't8', 'api_key')
            if not key:
                def_prov = cfg.get('api_provider') or ''
                if def_prov.lower() in ['t8', 'zhenzhen']:
                    key = cfg.get('api_key') or cfg.get('api key')
        elif api_provider == 't8-us':
            key = self._get_config_value(cfg, 't8-us', 'api_key')
        elif api_provider == 't8-hk':
            key = self._get_config_value(cfg, 't8-hk', 'api_key')
        elif api_provider == 'comfly-us':
            key = self._get_config_value(cfg, 'comfly-us', 'api_key')
        elif api_provider == 'comfly-hk':
            key = self._get_config_value(cfg, 'comfly-hk', 'api_key')
        return key if key else ''

    def _get_api_url(self, cfg, prov):
        # Aabao Special Handling
        if prov == 'aabao':
            base_url = self._get_config_value(cfg, 'aabao', 'base_url')
            if not base_url: base_url = 'https://api.aabao.top/v1'
            base_url = base_url.rstrip('/')
            if base_url.endswith('/v1'):
                 return f"{base_url}/videos"
            else:
                 return f"{base_url}/v1/videos"

        # T8/Comfly Logic
        char_base_url = self._get_config_value(cfg, prov, 'character_base_url')
        if char_base_url:
            if 'characters' in char_base_url or 'sora-2' in char_base_url:
                 return char_base_url
            base_url = char_base_url.rstrip('/')
        else:
            base_url = ''
            if prov == 'comfly':
                base_url = self._get_config_value(cfg, 'comfly', 'base_url')
                if not base_url: base_url = 'https://ai.comfly.chat/v1'
            elif prov == 't8':
                base_url = self._get_config_value(cfg, 't8', 'base_url')
                if not base_url: base_url = cfg.get('base_url')
                if not base_url: base_url = 'https://ai.t8star.cn/v1'
            elif prov == 't8-us' or prov == 'comfly-us':
                base_url = self._get_config_value(cfg, prov, 'base_url')
                if not base_url: base_url = 'https://api.gptbest.vip/v1'
            elif prov == 't8-hk' or prov == 'comfly-hk':
                base_url = self._get_config_value(cfg, prov, 'base_url')
                if not base_url: base_url = 'https://hk-api.gptbest.vip/v1'
            
            base_url = base_url.rstrip('/')
        
        # Default suffix for T8/Comfly
        if base_url.endswith('/v1'):
            host_url = base_url[:-3]
        else:
            host_url = base_url
        return f"{host_url}/sora/v1/characters"

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
    
    def _create_session(self, ignore_proxy=False):
        s = requests.Session()
        if ignore_proxy:
            s.trust_env = False  
            
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        s.mount('http://', HTTPAdapter(max_retries=retries))
        s.mount('https://', HTTPAdapter(max_retries=retries))
        return s
    
    def _upload_file_to_api(self, url, key, file_path):
        if url.endswith('/videos'):
            base = url[:-7] 
        elif url.endswith('/v1'):
            base = url
        else:
            base = url 
            
        files_url = f"{base}/files"
        print(f"[Storyboard] Uploading file to {files_url}")
        
        session = self._create_session(ignore_proxy=True)
        hdrs = {'Authorization': f'Bearer {key}'}
        
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type: mime_type = 'application/octet-stream'
        
        model_to_use = 'gpt-4' 
        
        try:
            with open(file_path, 'rb') as f:
                # Use list of tuples for ordered multipart
                multipart_data = [
                    ('model', (None, model_to_use)),
                    ('purpose', (None, 'assistants')),
                    ('file', (os.path.basename(file_path), f, mime_type))
                ]
                
                r = session.post(files_url, headers=hdrs, files=multipart_data, timeout=300, verify=False)
                
                if r.status_code == 200:
                    rj = r.json()
                    fid = rj.get('id')
                    if fid: 
                        print(f"[Storyboard] File uploaded: {fid}")
                        return fid
                print(f"[Storyboard] File upload failed: {r.status_code} {r.text}")
        except Exception as e:
            print(f"[Storyboard] File upload error: {e}")
            
        return None

    def _download_image(self, url, to=30):
        if not url: return None
        try:
            s = self._create_session(ignore_proxy=True) 
            r = s.get(url, timeout=to, verify=False)
            r.raise_for_status()
            im = Image.open(BytesIO(r.content))
            im = im.convert('RGB') if im.mode != 'RGB' else im
            return torch.from_numpy(np.array(im).astype(np.float32) / 255.0).unsqueeze(0)
        except: return None
    def _create_blank_image(self): return torch.from_numpy(np.array(Image.new('RGB', (256, 256), (200, 200, 200))).astype(np.float32) / 255.0).unsqueeze(0)
    
    def _call_api(self, prov, key, url, vurl, ts, seed, name, video_path=None):
        print(f'[Storyboard] Calling {prov} API at {url}')

        uploaded_file_id = None
        # V25/V26 LOGIC: Skip upload if URL is present for Aabao
        if prov == 'aabao' and video_path and os.path.exists(video_path) and not vurl:
             uploaded_file_id = self._upload_file_to_api(url, key, video_path)
        
        if uploaded_file_id:
             vurl = uploaded_file_id
             use_file_upload_in_call = False 
        else:
             # Fallback to direct upload ONLY if: Aabao + Local File + No URL
             if prov == 'aabao' and video_path and os.path.exists(video_path) and not vurl:
                 use_file_upload_in_call = True
             else:
                 use_file_upload_in_call = False # Just pass vurl (which might be external URL)
        
        if use_file_upload_in_call:
            hdrs = {'Authorization': f'Bearer {key}', 'Connection': 'close'}
        else:
            hdrs = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}', 'Connection': 'close'}
            
        pl = {'timestamps': ts}
        
        if prov == 'aabao':
            pl['name'] = name if name else ''
            pl['model'] = 'sora-2-characters'
            pl['prompt'] = '角色创建'
            
            if not use_file_upload_in_call:
                 pl['video'] = vurl 
        else:
            pl['url'] = vurl
            
        if seed > 0: pl['seed'] = seed
        
        print(f'[Storyboard] Payload (partial): {pl}, Uploading File in Call: {use_file_upload_in_call}')
        
        ignore_proxy = (prov == 'aabao')
        session = self._create_session(ignore_proxy=ignore_proxy)
        
        try:
            if use_file_upload_in_call:
                mime_type, _ = mimetypes.guess_type(video_path)
                if not mime_type: mime_type = 'application/octet-stream'
                
                with open(video_path, 'rb') as f:
                    f.seek(0)
                    files = {'video': (os.path.basename(video_path), f, mime_type)}
                    resp = session.post(url, headers=hdrs, data=pl, files=files, timeout=self.timeout, verify=False)
                    
                    if resp.status_code != 200:
                         print(f"[Storyboard] Fallback 'video' key failed: {resp.status_code}. Trying 'file' key...")
                         f.seek(0)
                         files = {'file': (os.path.basename(video_path), f, mime_type)}
                         resp = session.post(url, headers=hdrs, data=pl, files=files, timeout=self.timeout, verify=False)
            else:
                resp = session.post(url, headers=hdrs, json=pl, timeout=self.timeout, verify=False)
                
            if resp.status_code != 200: return {'error': f'API error {resp.status_code}: {resp.text[:200]}'}
            return resp.json()
        except requests.exceptions.SSLError as ssl_err:
             print(f"[Storyboard] SSL Error: {ssl_err}")
             if url.startswith('https://'):
                 print("[Storyboard] Retrying with HTTP...")
                 new_url = url.replace('https://', 'http://')
                 try:
                     if use_file_upload_in_call:
                         mime_type, _ = mimetypes.guess_type(video_path)
                         if not mime_type: mime_type = 'application/octet-stream'
                         with open(video_path, 'rb') as f:
                             files = {'video': (os.path.basename(video_path), f, mime_type)}
                             resp = session.post(new_url, headers=hdrs, data=pl, files=files, timeout=self.timeout, verify=False)
                     else:
                        resp = session.post(new_url, headers=hdrs, json=pl, timeout=self.timeout, verify=False)
                     
                     if resp.status_code != 200: return {'error': f'API error {resp.status_code}: {resp.text[:200]}'}
                     return resp.json()
                 except Exception as e2: return {'error': f"HTTPS failed ({ssl_err}) and HTTP failed ({e2})"}
             return {'error': str(ssl_err)}
        except Exception as e: return {'error': str(e)}

    def _poll_api(self, url, cid, key, timeout=300):
        print(f"[Storyboard] Polling for task {cid}...")
        start_time = time.time()
        hdrs = {'Authorization': f'Bearer {key}', 'Connection': 'close'}
        
        session = self._create_session(ignore_proxy=True)
        
        while time.time() - start_time < timeout:
            try:
                if '/sora/v1/characters' in url:
                     status_url = f"{url}/{cid}"
                else:
                    status_url = f"{url}/{cid}"
                    
                resp = session.get(status_url, headers=hdrs, timeout=30, verify=False)
                
                # Enhanced Logging
                print(f"[Storyboard] Poll {status_url} -> {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"[Storyboard] Poll Data: {str(data)[:200]}") # Log first 200 chars
                    
                    status = data.get('status')
                    if not status:
                         # Try nested
                         status = data.get('data', {}).get('status')
                    
                    print(f"[Storyboard] Status Found: {status}")
                    
                    success_statuses = ['completed', 'success', 'succeeded', 'finished']
                    
                    if status in success_statuses: 
                         return data
                    elif status == 'failed':
                         return {'error': f"Task failed: {data.get('fail_reason') or data.get('error')}"}
                    
                    # Also check for success evidence even if status matches none
                    usr = data.get('username') or data.get('data', {}).get('username')
                    plink = data.get('permalink') or data.get('data', {}).get('permalink')
                    if usr and plink:
                         print("[Storyboard] Username/Permalink found! Treating as success.")
                         # Normalize data structure if needed? 
                         # Ensure returned data has top-level keys if possible, or reliance on data getter in create_character will handle it
                         if not data.get('username') and usr: data['username'] = usr
                         if not data.get('permalink') and plink: data['permalink'] = plink
                         return data
                else:
                    print(f"[Storyboard] Poll non-200: {resp.text}")
                
            except Exception as e:
                print(f"[Storyboard] Polling error: {e}")
            
            time.sleep(3)
        
        return {'error': 'Polling timed out'}
    
    def _download_video_temp(self, url):
         try:
             import tempfile
             session = self._create_session(ignore_proxy=True)
             r = session.get(url, stream=True, timeout=120, verify=False)
             if r.status_code == 200:
                 fd, path = tempfile.mkstemp(suffix='.mp4')
                 with os.fdopen(fd, 'wb') as f:
                     for chunk in r.iter_content(chunk_size=8192):
                         f.write(chunk)
                 return path
         except Exception as e:
             print(f"[Storyboard] Download failed: {e}")
         return None

    def create_character(self, api_provider, timestamps, api_key='', video=None, video_url='', character_name='', seed=0, timeout=300, download_profile_image=True):
        self.timeout = timeout; blank = self._create_blank_image(); pbar = comfy.utils.ProgressBar(100); pbar.update_absolute(5)
        
        cfg = self._load_config_file()
        
        key = self._get_api_key(cfg, api_key, api_provider)
        if not key: 
            print(f'[Storyboard] Error: No API key found for provider {api_provider}.')
            return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': f'No key found for {api_provider}. Check config.json.'}))
            
        api_url = self._get_api_url(cfg, api_provider)
            
        pbar.update_absolute(10); ok, err, st, et = self._validate_timestamps(timestamps)
        if not ok: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': err}))
        
        video_path = None
        if video:
             video_path = getattr(video, 'saved_path', None) or getattr(video, 'path', None)
             if not video_path and isinstance(video, dict):
                 video_path = video.get('saved_path') or video.get('path')
        
        pbar.update_absolute(15); vurl, err = self._get_video_url(video, video_url)
        if err: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': err}))
        
        pbar.update_absolute(25)
        res = self._call_api(api_provider, key, api_url, vurl, timestamps, seed, character_name, video_path)
        
        if video_path and 'tmp' in video_path and os.path.exists(video_path):
             try: os.remove(video_path)
             except: pass
             
        if 'error' in res: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': res['error']}))
        
        cid = res.get('id', '') or res.get('character_id', '')
        if not cid: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': 'No character ID', 'raw': res}))

        usr = res.get('username', '') or (res.get('character', {}).get('username') if res.get('character') else '')
        status = res.get('status', '')
        
        need_poll = (status in ['queued', 'processing', 'pending']) or (cid and not usr and api_provider == 'aabao')
        
        if need_poll:
             pbar.update_absolute(30)
             print(f"[Storyboard] Response indicates async task. Polling...")
             poll_res = self._poll_api(api_url, cid, key, timeout)
             if 'error' in poll_res:
                 return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': poll_res['error']}))
             res = poll_res
             usr = res.get('username', '') or (res.get('character', {}).get('username') if res.get('character') else '') or res.get('data', {}).get('username')

        pbar.update_absolute(70)
        
        cid = res.get('id', '') or res.get('character_id', '')
        usr = res.get('username', '') or (res.get('character', {}).get('username') if res.get('character') else '') or res.get('data', {}).get('username')
        plink = res.get('permalink', '') or res.get('data', {}).get('permalink')
        ppurl = res.get('profile_picture_url', '') or res.get('avatar_url', '') or (res.get('character', {}).get('avatar_url') if res.get('character') else '') or res.get('data', {}).get('avatar_url')

        if not cid: return ('', '', '', '', blank, json.dumps({'status': 'error', 'message': 'No character ID after poll', 'raw': res}))
        
        pbar.update_absolute(80); img = self._download_image(ppurl) if download_profile_image and ppurl else None; pbar.update_absolute(100)
        resp = {'status': 'success', 'character_id': cid, 'username': usr, 'permalink': plink, 'profile_picture_url': ppurl}
        print(f'[Storyboard] OK: {cid}')
        return (cid, usr, plink, ppurl, img if img is not None else blank, json.dumps(resp, ensure_ascii=False))
NODE_CLASS_MAPPINGS = {'StoryboardCharacter': StoryboardCharacter}
NODE_DISPLAY_NAME_MAPPINGS = {'StoryboardCharacter': 'Storyboard-Character'}
