# 本地资源管理.py - 增加同文件夹歌词识别

import sys
import re
import json
import os
import base64
import hashlib
import time
import urllib.parse
from pathlib import Path
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "本地资源管理"
    
    def init(self, extend=""):
        super().init(extend)
        # 根目录配置
        self.root_paths = [
            '/storage/emulated/0/Music/',
            '/storage/emulated/0/Download/',
            '/storage/emulated/0/Movies/',
            '/storage/emulated/0/DCIM/',
            '/storage/emulated/0/Pictures/',
            '/storage/emulated/0/'
        ]
        
        # 文件类型定义
        self.media_exts = ['mp4', 'mkv', 'avi', 'rmvb', 'mov', 'wmv', 'flv', 'm4v', 'ts', 'm3u8']
        self.audio_exts = ['mp3', 'm4a', 'aac', 'flac', 'wav', 'ogg', 'wma', 'ape']
        self.image_exts = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'ico', 'svg']
        self.list_exts = ['m3u', 'txt', 'json', 'm3u8']
        self.lrc_exts = ['lrc']  # 歌词文件扩展名
        
        # 前缀常量
        self.V_DIR_PREFIX = 'vdir://'
        self.V_ITEM_PREFIX = 'vitem://'
        self.I_ALBUM_PREFIX = 'ialbum://'
        self.URL_B64U_PREFIX = 'b64u://'
        self.V_ALL_PREFIX = 'vall://'      # 视频连播
        self.A_ALL_PREFIX = 'aall://'      # 音频连播
        self.FOLDER_PREFIX = 'folder://'
        self.LIST_PREFIX = 'list://'
        self.PICS_PREFIX = 'pics://'       # 图片查看器
        
        # 歌词缓存
        self.lrc_cache = {}
        
        # 添加请求会话
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    # ==================== 工具函数 ====================
    
    def b64u_encode(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        encoded = base64.b64encode(data).decode('ascii')
        return encoded.replace('+', '-').replace('/', '_').rstrip('=')
    
    def b64u_decode(self, data):
        data = data.replace('-', '+').replace('_', '/')
        pad = len(data) % 4
        if pad:
            data += '=' * (4 - pad)
        try:
            return base64.b64decode(data).decode('utf-8')
        except:
            return ''
    
    def get_file_ext(self, filename):
        idx = filename.rfind('.')
        if idx == -1:
            return ''
        return filename[idx + 1:].lower()
    
    def is_media_file(self, ext):
        return ext in self.media_exts
    
    def is_audio_file(self, ext):
        return ext in self.audio_exts
    
    def is_image_file(self, ext):
        return ext in self.image_exts
    
    def is_list_file(self, ext):
        return ext in self.list_exts
    
    def is_lrc_file(self, ext):
        return ext in self.lrc_exts
    
    def scan_directory(self, dir_path):
        """扫描目录"""
        try:
            if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
                return []
            
            files = []
            for name in os.listdir(dir_path):
                if name.startswith('.') or name in ['.', '..']:
                    continue
                
                full_path = os.path.join(dir_path, name)
                is_dir = os.path.isdir(full_path)
                ext = self.get_file_ext(name)
                
                files.append({
                    'name': name,
                    'path': full_path,
                    'is_dir': is_dir,
                    'ext': ext,
                    'mtime': os.path.getmtime(full_path) if not is_dir else 0,
                })
            
            # 排序：目录在前
            files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            return files
        except:
            return []
    
    def collect_videos_in_dir(self, dir_path):
        """收集目录内的所有视频文件"""
        files = self.scan_directory(dir_path)
        videos = []
        for f in files:
            if not f['is_dir'] and self.is_media_file(f['ext']):
                videos.append(f)
        videos.sort(key=lambda x: x['name'].lower())
        return videos
    
    def collect_audios_in_dir(self, dir_path):
        """收集目录内的所有音频文件"""
        files = self.scan_directory(dir_path)
        audios = []
        for f in files:
            if not f['is_dir'] and self.is_audio_file(f['ext']):
                audios.append(f)
        audios.sort(key=lambda x: x['name'].lower())
        return audios
    
    def collect_images_in_dir(self, dir_path):
        """收集目录内的所有图片文件"""
        files = self.scan_directory(dir_path)
        images = []
        for f in files:
            if not f['is_dir'] and self.is_image_file(f['ext']):
                images.append(f)
        images.sort(key=lambda x: x['name'].lower())
        return images
    
    def collect_lrc_in_dir(self, dir_path):
        """收集目录内的所有歌词文件"""
        files = self.scan_directory(dir_path)
        lrcs = []
        for f in files:
            if not f['is_dir'] and self.is_lrc_file(f['ext']):
                lrcs.append(f)
        return lrcs
    
    # ==================== 列表文件解析 ====================
    
    def parse_m3u_file(self, file_path):
        """解析M3U/M3U8文件"""
        items = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                if not line:
                    i += 1
                    continue
                
                if line.startswith('#EXTINF:'):
                    title_match = re.search(r',(.+)$', line)
                    title = title_match.group(1).strip() if title_match else f"剧集{len(items)+1}"
                    
                    i += 1
                    if i < len(lines):
                        url_line = lines[i].strip()
                        if url_line and not url_line.startswith('#'):
                            items.append({
                                'name': title,
                                'url': url_line
                            })
                elif not line.startswith('#'):
                    title = os.path.basename(line.split('?')[0]) or f"剧集{len(items)+1}"
                    items.append({
                        'name': title,
                        'url': line
                    })
                
                i += 1
        except Exception as e:
            print(f"解析M3U文件错误: {e}")
        return items
    
    def parse_txt_file(self, file_path):
        """解析TXT文件"""
        items = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if '#genre#' in line.lower():
                        continue
                    
                    if ',' in line:
                        parts = line.split(',', 1)
                        name = parts[0].strip()
                        url = parts[1].strip()
                        
                        if url.startswith(('http://', 'https://', 'file://', 'rtmp://', 'rtsp://')):
                            items.append({
                                'name': name,
                                'url': url
                            })
                    else:
                        if line.startswith(('http://', 'https://', 'file://', 'rtmp://', 'rtsp://')):
                            name = os.path.basename(line.split('?')[0]) or f"视频{len(items)+1}"
                            items.append({
                                'name': name,
                                'url': line
                            })
        except Exception as e:
            print(f"解析TXT文件错误: {e}")
        return items
    
    def get_file_icon(self, ext, is_dir=False):
        if is_dir:
            return '📁'
        if ext in self.media_exts:
            return '🎬'
        if ext in self.audio_exts:
            return '🎵'
        if ext in self.image_exts:
            return '🖼️'
        if ext in self.list_exts:
            return '📋'
        if ext in self.lrc_exts:
            return '📝'  # 歌词文件图标
        return '📄'
    
    # ==================== 歌词获取 ====================
    
    def find_local_lrc(self, audio_path):
        """查找同文件夹内的同名歌词文件"""
        audio_dir = os.path.dirname(audio_path)
        audio_name = os.path.splitext(os.path.basename(audio_path))[0]
        
        # 收集目录内所有歌词文件
        lrc_files = self.collect_lrc_in_dir(audio_dir)
        
        # 匹配规则
        for lrc in lrc_files:
            lrc_name = os.path.splitext(lrc['name'])[0]
            
            # 规则1: 完全匹配
            if lrc_name == audio_name:
                print(f"✅ 找到同名歌词: {lrc['path']}")
                return lrc['path']
            
            # 规则2: 忽略大小写匹配
            if lrc_name.lower() == audio_name.lower():
                print(f"✅ 找到忽略大小写匹配歌词: {lrc['path']}")
                return lrc['path']
            
            # 规则3: 音频文件名包含歌词文件名
            if audio_name.lower().find(lrc_name.lower()) != -1:
                print(f"✅ 找到包含匹配歌词: {lrc['path']}")
                return lrc['path']
            
            # 规则4: 歌词文件名包含音频文件名
            if lrc_name.lower().find(audio_name.lower()) != -1:
                print(f"✅ 找到被包含匹配歌词: {lrc['path']}")
                return lrc['path']
        
        return None
    
    def read_lrc_file(self, lrc_path):
        """读取歌词文件"""
        try:
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'big5', 'utf-16']
            for encoding in encodings:
                try:
                    with open(lrc_path, 'r', encoding=encoding, errors='ignore') as f:
                        content = f.read()
                        if content and len(content) > 10:
                            print(f"✅ 读取歌词文件成功: {lrc_path} (编码: {encoding})")
                            return content
                except:
                    continue
        except Exception as e:
            print(f"读取歌词文件失败: {e}")
        return None
    
    def clean_filename(self, filename):
        """清理文件名，移除常见干扰字符"""
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        
        # 常见干扰模式
        patterns = [
            r'【.*?】', r'\[.*?\]', r'\(.*?\)', r'\{.*?\}', r'（.*?）',
            r'\-? ?\d{3,4}kbps', r'\-? ?\d{3,4}Kbps', r'\-? ?\d{3,4}K',
            r'\-? ?\d{3,4}MB', r'\-? ?\d{3,4}Mb', r'\-? ?HQ', r'\-? ?SQ',
            r'\-? ?无损', r'\-? ?高品质', r'\-? ?高音质',
            r'\-? ?320k', r'\-? ?128k', r'\-? ?192k',
            r'\-? ?歌词版', r'\-? ?伴奏版', r'\-? ?纯音乐',
            r'\-? ?Live', r'\-? ?现场版', r'\-? ?演唱会',
            r'\-? ?官方版', r'\-? ?MV版', r'\-? ?电影原声',
            r'\-? ?电视剧原声', r'\-? ?主题曲', r'\-? ?片尾曲',
            r'\-? ?插曲', r'\-? ?背景音乐', r'\-? ?BGM'
        ]
        
        for pattern in patterns:
            name = re.sub(pattern, '', name)
        
        # 移除多余的空格
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def extract_song_info(self, filename):
        """从文件名提取歌手和歌曲名"""
        # 清理文件名
        name = self.clean_filename(filename)
        
        artist = ""
        song = name
        
        # 常见分隔符
        separators = [
            r'\s+-\s+', r'-\s+', r'\s+-', r'·', r'•', r'–', r'—', r'：', r':', r'、', r'／', r'/'
        ]
        
        for sep in separators:
            parts = re.split(sep, name, maxsplit=1)
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()
                
                # 判断哪边更可能是歌手
                left_is_artist = len(left) < 30 and len(left) > 1 and not re.search(r'[《》〈〉『』〔〕]', left)
                right_is_artist = len(right) < 30 and len(right) > 1 and not re.search(r'[《》〈〉『』〔〕]', right)
                
                if left_is_artist and not right_is_artist:
                    artist = left
                    song = right
                elif right_is_artist and not left_is_artist:
                    artist = right
                    song = left
                elif left_is_artist and right_is_artist:
                    # 两边都可能是歌手，取较短的
                    if len(left) < len(right):
                        artist = left
                        song = right
                    else:
                        artist = right
                        song = left
                else:
                    # 默认取左边
                    artist = left
                    song = right
                break
        
        # 清理歌曲名中的特殊符号
        song = re.sub(r'[《》〈〉『』〔〕]', '', song).strip()
        
        # 如果歌曲名太短，使用原文件名
        if len(song) < 2 or song.isdigit():
            song = filename
        
        return artist, song
    
    def get_lrc_for_audio(self, file_path):
        """为音频文件获取歌词 - 优先使用同文件夹歌词"""
        filename = os.path.basename(file_path)
        
        # 第一步：查找同文件夹内的同名歌词文件
        local_lrc_path = self.find_local_lrc(file_path)
        if local_lrc_path:
            lrc_content = self.read_lrc_file(local_lrc_path)
            if lrc_content:
                print(f"✅ 使用本地歌词: {local_lrc_path}")
                # 生成缓存键
                cache_key = hashlib.md5(f"local_{file_path}".encode()).hexdigest()
                self.lrc_cache[cache_key] = lrc_content
                return lrc_content
        
        # 第二步：检查是否存在同名的.lrc文件（兼容原逻辑）
        lrc_path = os.path.splitext(file_path)[0] + '.lrc'
        if os.path.exists(lrc_path):
            try:
                with open(lrc_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lrc_content = f.read()
                    if '[ti:' in lrc_content or '[ar:' in lrc_content or re.search(r'\[\d{2}:\d{2}', lrc_content):
                        print(f"✅ 找到标准同名歌词: {lrc_path}")
                        cache_key = hashlib.md5(f"local_{file_path}".encode()).hexdigest()
                        self.lrc_cache[cache_key] = lrc_content
                        return lrc_content
            except:
                pass
        
        # 第三步：提取歌曲信息，用于网络搜索
        artist, song = self.extract_song_info(filename)
        
        # 生成缓存键
        cache_key = hashlib.md5(f"{artist}_{song}".encode()).hexdigest()
        
        # 检查网络歌词缓存
        if cache_key in self.lrc_cache:
            print(f"📦 使用缓存网络歌词: {artist} - {song}")
            return self.lrc_cache[cache_key]
        
        print(f"🎵 搜索网络歌词: 歌手='{artist}', 歌曲='{song}'")
        
        # 获取网络歌词
        lrc_content = self._search_lrc(artist, song)
        
        if lrc_content:
            self.lrc_cache[cache_key] = lrc_content
            return lrc_content
        
        # 尝试只用歌曲名搜索
        if artist:
            print(f"🎵 尝试只用歌曲名搜索: {song}")
            lrc_content = self._search_lrc("", song)
            if lrc_content:
                self.lrc_cache[cache_key] = lrc_content
                return lrc_content
        
        print(f"❌ 未找到歌词: {filename}")
        return None
    
    def _search_lrc(self, artist, song):
        """搜索歌词"""
        # 构建搜索关键词
        keywords = []
        if artist:
            keywords.append(artist)
        if song:
            keywords.append(song)
        
        keyword = ' '.join(keywords)
        if not keyword:
            return None
        
        # 1. 尝试网易云音乐
        lrc = self._netease_search(keyword)
        if lrc:
            return lrc
        
        # 2. 尝试QQ音乐
        lrc = self._qq_search(keyword)
        if lrc:
            return lrc
        
        return None
    
    def _netease_search(self, keyword):
        """网易云音乐搜索"""
        try:
            # 搜索
            url = "https://music.163.com/api/search/get/web"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://music.163.com/"
            }
            data = {
                "s": keyword,
                "type": 1,
                "offset": 0,
                "limit": 3
            }
            
            resp = self.session.post(url, data=data, headers=headers, timeout=5)
            if resp.status_code == 200:
                result = resp.json()
                if result['code'] == 200 and result['result']['songs']:
                    # 取第一个结果
                    song = result['result']['songs'][0]
                    song_id = song['id']
                    
                    # 获取歌词
                    lrc_url = "https://music.163.com/api/song/lyric"
                    params = {
                        "id": song_id,
                        "lv": 1,
                        "kv": 1
                    }
                    
                    lrc_resp = self.session.get(lrc_url, params=params, headers=headers, timeout=5)
                    if lrc_resp.status_code == 200:
                        lrc_data = lrc_resp.json()
                        if 'lrc' in lrc_data and lrc_data['lrc']['lyric']:
                            lrc = lrc_data['lrc']['lyric']
                            if len(lrc) > 100:
                                print(f"✅ 网易云获取成功: {song['name']}")
                                return lrc
        except Exception as e:
            print(f"网易云搜索异常: {e}")
        return None
    
    def _qq_search(self, keyword):
        """QQ音乐搜索"""
        try:
            # 搜索
            url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
            params = {
                "w": keyword,
                "format": "json",
                "p": 1,
                "n": 3
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://y.qq.com/"
            }
            
            resp = self.session.get(url, params=params, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data['code'] == 0 and data['data']['song']['list']:
                    # 取第一个结果
                    song = data['data']['song']['list'][0]
                    song_mid = song['songmid']
                    
                    # 获取歌词
                    lrc_url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
                    params = {
                        "songmid": song_mid,
                        "format": "json"
                    }
                    
                    lrc_resp = self.session.get(lrc_url, params=params, headers=headers, timeout=5)
                    if lrc_resp.status_code == 200:
                        text = lrc_resp.text
                        match = re.search(r'({.*})', text)
                        if match:
                            lrc_data = json.loads(match.group(1))
                            if 'lyric' in lrc_data and lrc_data['lyric']:
                                lrc = base64.b64decode(lrc_data['lyric']).decode('utf-8')
                                if len(lrc) > 100:
                                    print(f"✅ QQ音乐获取成功: {song['name']}")
                                    return lrc
        except Exception as e:
            print(f"QQ音乐搜索异常: {e}")
        return None
    
    # ==================== 首页分类 ====================
    
    def homeContent(self, filter):
        classes = []
        
        for i, path in enumerate(self.root_paths):
            if os.path.exists(path):
                name = os.path.basename(path.rstrip('/')) or f'目录{i}'
                classes.append({
                    "type_id": f"root_{i}",
                    "type_name": name
                })
        
        classes.append({"type_id": "recent", "type_name": "最近添加"})
        classes.append({"type_id": "music", "type_name": "音乐专区"})
        classes.append({"type_id": "playlists", "type_name": "播放列表"})
        classes.append({"type_id": "galleries", "type_name": "图片画廊"})
        
        return {'class': classes}
    
    # ==================== 首页推荐 ====================
    
    def homeVideoContent(self):
        videos = []
        for path in self.root_paths[:2]:
            if not os.path.exists(path):
                continue
            files = self.scan_directory(path)[:10]
            for f in files:
                if not f['is_dir'] and (self.is_media_file(f['ext']) or self.is_audio_file(f['ext']) or self.is_list_file(f['ext']) or self.is_image_file(f['ext'])):
                    videos.append({
                        'vod_id': f['path'],
                        'vod_name': f['name'],
                        'vod_pic': f"file://{f['path']}" if self.is_image_file(f['ext']) else '',
                        'vod_remarks': f['ext'].upper()
                    })
        return {'list': videos[:20]}
    
    # ==================== 分类内容 ====================
    
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)
        
        # 处理最近添加
        if tid == 'recent':
            return self._recent_content(pg)
        
        # 处理音乐专区
        if tid == 'music':
            return self._music_content(pg)
        
        # 处理播放列表
        if tid == 'playlists':
            return self._playlists_content(pg)
        
        # 处理图片画廊
        if tid == 'galleries':
            return self._galleries_content(pg)
        
        # 处理图片画廊目录
        if tid.startswith(self.I_ALBUM_PREFIX):
            return self._gallery_content(tid, pg)
        
        # 解析真实路径
        path = tid
        if tid.startswith('root_'):
            idx = int(tid[5:])
            if idx >= len(self.root_paths):
                return {'list': [], 'page': pg, 'pagecount': 1}
            path = self.root_paths[idx]
        elif tid.startswith(self.FOLDER_PREFIX):
            path = self.b64u_decode(tid[len(self.FOLDER_PREFIX):])
        
        # 检查是否是目录
        if not os.path.exists(path) or not os.path.isdir(path):
            return {'list': [], 'page': pg, 'pagecount': 1}
        
        files = self.scan_directory(path)
        total = len(files)
        
        # 分页
        per_page = 50
        start = (pg - 1) * per_page
        end = min(start + per_page, total)
        page_files = files[start:end]
        
        vlist = []
        
        # 返回上一级
        parent = os.path.dirname(path)
        if parent and parent != path and os.path.exists(parent):
            is_root = False
            for root in self.root_paths:
                if parent == root.rstrip('/'):
                    is_root = True
                    break
            if not is_root:
                vlist.append({
                    'vod_id': self.FOLDER_PREFIX + self.b64u_encode(parent),
                    'vod_name': '⬅️ 返回上一级',
                    'vod_pic': '',
                    'vod_remarks': os.path.basename(parent),
                    'vod_tag': 'folder',
                    'style': {'type': 'list'}
                })
        
        # 第一页添加连播功能
        if pg == 1:
            videos = self.collect_videos_in_dir(path)
            if videos:
                vlist.append({
                    'vod_id': self.V_ALL_PREFIX + self.b64u_encode(path),
                    'vod_name': f'🎬 视频连播 ({len(videos)}个视频)',
                    'vod_pic': '',
                    'vod_remarks': '顺序播放',
                    'style': {'type': 'list'}
                })
            
            audios = self.collect_audios_in_dir(path)
            if audios:
                vlist.append({
                    'vod_id': self.A_ALL_PREFIX + self.b64u_encode(path),
                    'vod_name': f'🎵 音频连播 ({len(audios)}首歌曲)',
                    'vod_pic': '',
                    'vod_remarks': '顺序播放',
                    'style': {'type': 'list'}
                })
            
            images = self.collect_images_in_dir(path)
            if images:
                pic_urls = []
                for img in images:
                    pic_urls.append(f"file://{img['path']}")
                
                pics_data = '&&'.join(pic_urls)
                pics_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}{pics_data}")
                
                vlist.append({
                    'vod_id': pics_id,
                    'vod_name': f'🖼️ 图片连播 ({len(images)}张)',
                    'vod_pic': f"file://{images[0]['path']}",
                    'vod_remarks': '顺序浏览',
                    'vod_tag': 'slideshow',
                    'style': {'type': 'list'}
                })
        
        # 文件列表
        for f in page_files:
            icon = self.get_file_icon(f['ext'], f['is_dir'])
            
            if f['is_dir']:
                vod_id = self.FOLDER_PREFIX + self.b64u_encode(f['path'])
                remarks = '目录'
                style = {'type': 'list'}
                vod_tag = 'folder'
            elif self.is_audio_file(f['ext']):
                vod_id = f['path']
                remarks = f['ext'].upper()
                style = {'type': 'list'}
                vod_tag = 'audio'
            elif self.is_image_file(f['ext']):
                pics_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}file://{f['path']}")
                vod_id = pics_id
                remarks = f['ext'].upper()
                style = {'type': 'grid', 'ratio': 1}
                vod_tag = 'image'
            elif self.is_list_file(f['ext']):
                vod_id = self.LIST_PREFIX + self.b64u_encode(f['path'])
                remarks = f['ext'].upper() + ' 列表'
                style = {'type': 'list'}
                vod_tag = 'list'
            elif self.is_lrc_file(f['ext']):
                vod_id = f['path']
                remarks = '歌词文件'
                style = {'type': 'list'}
                vod_tag = 'lrc'
            else:
                vod_id = f['path']
                remarks = f['ext'].upper()
                style = {'type': 'list'}
                vod_tag = 'file'
            
            item = {
                'vod_id': vod_id,
                'vod_name': f"{icon} {f['name']}",
                'vod_pic': f"file://{f['path']}" if self.is_image_file(f['ext']) else '',
                'vod_remarks': remarks,
                'vod_tag': vod_tag,
                'style': style
            }
            
            vlist.append(item)
        
        return {
            'list': vlist,
            'page': pg,
            'pagecount': (total + per_page - 1) // per_page,
            'limit': per_page,
            'total': total
        }
    
    def _recent_content(self, pg):
        pg = int(pg)
        all_files = []
        
        for path in self.root_paths:
            if not os.path.exists(path):
                continue
            files = self.scan_directory(path)
            for f in files:
                if not f['is_dir'] and (self.is_media_file(f['ext']) or self.is_audio_file(f['ext']) or self.is_list_file(f['ext']) or self.is_image_file(f['ext'])):
                    all_files.append(f)
        
        all_files.sort(key=lambda x: x['mtime'], reverse=True)
        
        per_page = 50
        start = (pg - 1) * per_page
        end = min(start + per_page, len(all_files))
        page_files = all_files[start:end]
        
        import time
        vlist = []
        for f in page_files:
            if self.is_media_file(f['ext']):
                icon = '🎬'
            elif self.is_audio_file(f['ext']):
                icon = '🎵'
            elif self.is_image_file(f['ext']):
                icon = '🖼️'
            elif self.is_list_file(f['ext']):
                icon = '📋'
            else:
                icon = '📄'
            
            vod_id = f['path']
            if self.is_image_file(f['ext']):
                vod_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}file://{f['path']}")
            
            vlist.append({
                'vod_id': vod_id,
                'vod_name': f"{icon} {f['name']}",
                'vod_pic': f"file://{f['path']}" if self.is_image_file(f['ext']) else '',
                'vod_remarks': time.strftime('%m-%d', time.localtime(f['mtime'])),
                'vod_tag': 'file',
                'style': {'type': 'grid', 'ratio': 1} if self.is_image_file(f['ext']) else {'type': 'list'}
            })
        
        return {
            'list': vlist,
            'page': pg,
            'pagecount': (len(all_files) + per_page - 1) // per_page,
            'limit': per_page,
            'total': len(all_files)
        }
    
    def _music_content(self, pg):
        """音乐专区"""
        pg = int(pg)
        all_audios = []
        
        for path in self.root_paths:
            if not os.path.exists(path):
                continue
            files = self.scan_directory(path)
            for f in files:
                if not f['is_dir'] and self.is_audio_file(f['ext']):
                    all_audios.append(f)
        
        all_audios.sort(key=lambda x: x['name'].lower())
        
        per_page = 50
        start = (pg - 1) * per_page
        end = min(start + per_page, len(all_audios))
        page_audios = all_audios[start:end]
        
        vlist = []
        for f in page_audios:
            vlist.append({
                'vod_id': f['path'],
                'vod_name': f"🎵 {f['name']}",
                'vod_pic': '',
                'vod_remarks': f['ext'].upper(),
                'vod_tag': 'audio',
                'style': {'type': 'list'}
            })
        
        return {
            'list': vlist,
            'page': pg,
            'pagecount': (len(all_audios) + per_page - 1) // per_page,
            'limit': per_page,
            'total': len(all_audios)
        }
    
    def _playlists_content(self, pg):
        """播放列表"""
        pg = int(pg)
        all_lists = []
        
        for path in self.root_paths:
            if not os.path.exists(path):
                continue
            files = self.scan_directory(path)
            for f in files:
                if not f['is_dir'] and self.is_list_file(f['ext']):
                    all_lists.append(f)
        
        all_lists.sort(key=lambda x: x['name'].lower())
        
        per_page = 50
        start = (pg - 1) * per_page
        end = min(start + per_page, len(all_lists))
        page_lists = all_lists[start:end]
        
        vlist = []
        for f in page_lists:
            vlist.append({
                'vod_id': self.LIST_PREFIX + self.b64u_encode(f['path']),
                'vod_name': f"📋 {f['name']}",
                'vod_pic': '',
                'vod_remarks': f['ext'].upper() + ' 播放列表',
                'vod_tag': 'list',
                'style': {'type': 'list'}
            })
        
        return {
            'list': vlist,
            'page': pg,
            'pagecount': (len(all_lists) + per_page - 1) // per_page,
            'limit': per_page,
            'total': len(all_lists)
        }
    
    def _galleries_content(self, pg):
        """图片画廊"""
        pg = int(pg)
        galleries = []
        processed = set()
        
        for path in self.root_paths:
            if not os.path.exists(path):
                continue
            
            try:
                for name in os.listdir(path):
                    if name.startswith('.'):
                        continue
                    
                    dir_path = os.path.join(path, name)
                    if not os.path.isdir(dir_path):
                        continue
                    
                    if dir_path in processed:
                        continue
                    processed.add(dir_path)
                    
                    images = self.collect_images_in_dir(dir_path)
                    if images:
                        pic_urls = []
                        for img in images:
                            pic_urls.append(f"file://{img['path']}")
                        
                        pics_data = '&&'.join(pic_urls)
                        pics_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}{pics_data}")
                        
                        galleries.append({
                            'path': dir_path,
                            'name': name,
                            'count': len(images),
                            'cover': images[0]['path'],
                            'pics_id': pics_id
                        })
            except:
                pass
        
        galleries.sort(key=lambda x: x['name'].lower())
        
        per_page = 50
        start = (pg - 1) * per_page
        end = min(start + per_page, len(galleries))
        page_galleries = galleries[start:end]
        
        vlist = []
        for g in page_galleries:
            vlist.append({
                'vod_id': g['pics_id'],
                'vod_name': f"📁 {g['name']}",
                'vod_pic': f"file://{g['cover']}",
                'vod_remarks': f"{g['count']}张图片",
                'vod_tag': 'gallery',
                'style': {'type': 'grid', 'ratio': 1}
            })
        
        return {
            'list': vlist,
            'page': pg,
            'pagecount': (len(galleries) + per_page - 1) // per_page,
            'limit': per_page,
            'total': len(galleries)
        }
    
    def _gallery_content(self, tid, pg):
        """图片画廊内容"""
        if pg > 1:
            return {'list': [], 'page': pg, 'pagecount': 1}
        
        encoded = tid[len(self.I_ALBUM_PREFIX):]
        dir_path = self.b64u_decode(encoded)
        
        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return {'list': [], 'page': pg, 'pagecount': 1}
        
        images = self.collect_images_in_dir(dir_path)
        
        vlist = []
        
        vlist.append({
            'vod_id': self.FOLDER_PREFIX + self.b64u_encode(os.path.dirname(dir_path)),
            'vod_name': '⬅️ 返回上级目录',
            'vod_pic': '',
            'vod_remarks': '目录',
            'vod_tag': 'folder',
            'style': {'type': 'list'}
        })
        
        if images:
            pic_urls = []
            for img in images:
                pic_urls.append(f"file://{img['path']}")
            
            pics_data = '&&'.join(pic_urls)
            pics_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}{pics_data}")
            
            vlist.append({
                'vod_id': pics_id,
                'vod_name': f'🎞️ 图片连播 ({len(images)}张)',
                'vod_pic': f"file://{images[0]['path']}",
                'vod_remarks': '点击开始浏览',
                'vod_tag': 'slideshow',
                'style': {'type': 'list'}
            })
        
        for img in images:
            pics_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}file://{img['path']}")
            
            vlist.append({
                'vod_id': pics_id,
                'vod_name': f"🖼️ {img['name']}",
                'vod_pic': f"file://{img['path']}",
                'vod_remarks': img['ext'].upper(),
                'vod_tag': 'image',
                'style': {'type': 'grid', 'ratio': 1}
            })
        
        return {
            'list': vlist,
            'page': 1,
            'pagecount': 1,
            'limit': len(vlist),
            'total': len(vlist)
        }
    
    # ==================== 详情页 ====================
    
    def detailContent(self, ids):
        id_val = ids[0]
        
        # 处理图片查看器
        if id_val.startswith(self.URL_B64U_PREFIX):
            decoded = self.b64u_decode(id_val[len(self.URL_B64U_PREFIX):])
            if decoded and decoded.startswith(self.PICS_PREFIX):
                pics_data = decoded[len(self.PICS_PREFIX):]
                
                if '&&' in pics_data:
                    pic_urls = pics_data.split('&&')
                    play_urls = []
                    
                    for url in pic_urls:
                        if url.startswith('file://'):
                            file_path = url[7:]
                            file_name = os.path.basename(file_path)
                            play_urls.append(f"{file_name}${url}")
                        else:
                            file_name = os.path.basename(url.split('?')[0]) or "图片"
                            play_urls.append(f"{file_name}${url}")
                    
                    return {'list': [{
                        'vod_id': id_val,
                        'vod_name': f'图片相册 ({len(pic_urls)}张)',
                        'vod_pic': pic_urls[0],
                        'vod_play_from': '图片查看',
                        'vod_play_url': '#'.join(play_urls),
                        'style': {'type': 'list'}
                    }]}
                else:
                    file_name = os.path.basename(pics_data.split('?')[0])
                    if pics_data.startswith('file://'):
                        file_name = os.path.basename(pics_data[7:])
                    
                    return {'list': [{
                        'vod_id': id_val,
                        'vod_name': file_name,
                        'vod_pic': pics_data,
                        'vod_play_from': '图片查看',
                        'vod_play_url': f"查看${pics_data}",
                        'style': {'type': 'list'}
                    }]}
        
        # 处理文件夹
        if id_val.startswith(self.FOLDER_PREFIX):
            folder_path = self.b64u_decode(id_val[len(self.FOLDER_PREFIX):])
            return self.categoryContent(folder_path, 1, None, None)
        
        # 处理图片画廊
        if id_val.startswith(self.I_ALBUM_PREFIX):
            return self._gallery_content(id_val, 1)
        
        # 处理音频连播
        if id_val.startswith(self.A_ALL_PREFIX):
            encoded = id_val[len(self.A_ALL_PREFIX):]
            dir_path = self.b64u_decode(encoded)
            audios = self.collect_audios_in_dir(dir_path)
            
            if not audios:
                return {'list': []}
            
            play_urls = []
            for a in audios:
                play_urls.append(f"{a['name']}$file://{a['path']}")
            
            return {'list': [{
                'vod_id': id_val,
                'vod_name': f"🎵 音乐连播 - {os.path.basename(dir_path)} ({len(audios)}首)",
                'vod_pic': '',
                'vod_play_from': '本地音乐',
                'vod_play_url': '#'.join(play_urls),
                'style': {'type': 'list'}
            }]}
        
        # 处理视频连播
        if id_val.startswith(self.V_ALL_PREFIX):
            encoded = id_val[len(self.V_ALL_PREFIX):]
            dir_path = self.b64u_decode(encoded)
            videos = self.collect_videos_in_dir(dir_path)
            
            if not videos:
                return {'list': []}
            
            play_urls = []
            for v in videos:
                play_urls.append(f"{v['name']}$file://{v['path']}")
            
            return {'list': [{
                'vod_id': id_val,
                'vod_name': f"🎬 视频连播 - {os.path.basename(dir_path)} ({len(videos)}集)",
                'vod_pic': '',
                'vod_play_from': '本地视频',
                'vod_play_url': '#'.join(play_urls),
                'style': {'type': 'list'}
            }]}
        
        # 处理列表文件
        if id_val.startswith(self.LIST_PREFIX):
            encoded = id_val[len(self.LIST_PREFIX):]
            file_path = self.b64u_decode(encoded)
            
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                return {'list': []}
            
            ext = self.get_file_ext(file_path)
            items = []
            
            if ext in ['m3u', 'm3u8']:
                items = self.parse_m3u_file(file_path)
            elif ext == 'txt':
                items = self.parse_txt_file(file_path)
            
            if not items:
                return {'list': [{
                    'vod_id': id_val,
                    'vod_name': os.path.basename(file_path),
                    'vod_pic': '',
                    'vod_play_from': '播放列表',
                    'vod_play_url': f"播放$file://{file_path}",
                    'style': {'type': 'list'}
                }]}
            
            play_urls = []
            for item in items:
                safe_url = self.URL_B64U_PREFIX + self.b64u_encode(item['url'])
                play_urls.append(f"{item['name']}${safe_url}")
            
            return {'list': [{
                'vod_id': id_val,
                'vod_name': os.path.basename(file_path),
                'vod_pic': '',
                'vod_play_from': '播放列表',
                'vod_play_url': '#'.join(play_urls),
                'style': {'type': 'list'}
            }]}
        
        # 处理普通路径
        if not os.path.exists(id_val):
            return {'list': []}
        
        # 如果是目录，返回目录内容
        if os.path.isdir(id_val):
            return self.categoryContent(id_val, 1, None, None)
        
        # 处理文件
        name = os.path.basename(id_val)
        ext = self.get_file_ext(name)
        
        vod = {
            'vod_id': id_val,
            'vod_name': name,
            'vod_pic': f"file://{id_val}" if self.is_image_file(ext) else '',
            'vod_play_from': '本地播放',
            'vod_play_url': '',
            'style': {'type': 'list'}
        }
        
        if self.is_image_file(ext):
            pics_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}file://{id_val}")
            vod['vod_id'] = pics_id
            vod['vod_play_url'] = f"查看${pics_id}"
            vod['vod_pic'] = f"file://{id_val}"
            vod['vod_name'] = f"🖼️ {name}"
        elif self.is_audio_file(ext):
            vod['vod_play_url'] = f"播放$file://{id_val}"
            vod['vod_name'] = f"🎵 {name}"
        elif self.is_media_file(ext):
            vod['vod_play_url'] = f"播放$file://{id_val}"
        elif self.is_list_file(ext):
            vod_id = self.LIST_PREFIX + self.b64u_encode(id_val)
            return self.detailContent([vod_id])
        
        return {'list': [vod]}
    
    # ==================== 播放页 ====================
    
    def playerContent(self, flag, id, vipFlags):
        if id.startswith(self.URL_B64U_PREFIX):
            decoded = self.b64u_decode(id[len(self.URL_B64U_PREFIX):])
            if decoded:
                id = decoded
        
        result = {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": {}
        }
        
        # 如果是音频文件，添加歌词
        if id.startswith('file://'):
            file_path = id[7:]
            if os.path.exists(file_path) and self.is_audio_file(self.get_file_ext(file_path)):
                lrc = self.get_lrc_for_audio(file_path)
                if lrc:
                    result["lrc"] = lrc
                    print(f"✅ 歌词已添加: {os.path.basename(file_path)}")
        
        return result
    
    # ==================== 搜索 ====================
    
    def searchContent(self, key, quick, pg=1):
        pg = int(pg)
        results = []
        key = key.lower()
        
        for path in self.root_paths:
            if not os.path.exists(path):
                continue
            files = self.scan_directory(path)
            for f in files:
                if f['is_dir']:
                    continue
                if key in f['name'].lower():
                    if self.is_audio_file(f['ext']):
                        icon = '🎵'
                    elif self.is_media_file(f['ext']):
                        icon = '🎬'
                    elif self.is_image_file(f['ext']):
                        icon = '🖼️'
                    elif self.is_list_file(f['ext']):
                        icon = '📋'
                    elif self.is_lrc_file(f['ext']):
                        icon = '📝'
                    else:
                        icon = '📄'
                    
                    vod_id = f['path']
                    if self.is_image_file(f['ext']):
                        vod_id = self.URL_B64U_PREFIX + self.b64u_encode(f"{self.PICS_PREFIX}file://{f['path']}")
                    
                    results.append({
                        'vod_id': vod_id,
                        'vod_name': f"{icon} {f['name']}",
                        'vod_pic': f"file://{f['path']}" if self.is_image_file(f['ext']) else '',
                        'vod_remarks': f['ext'].upper(),
                        'style': {'type': 'grid', 'ratio': 1} if self.is_image_file(f['ext']) else {'type': 'list'}
                    })
        
        per_page = 50
        start = (pg - 1) * per_page
        end = min(start + per_page, len(results))
        page_results = results[start:end]
        
        return {
            'list': page_results,
            'page': pg,
            'pagecount': (len(results) + per_page - 1) // per_page,
            'limit': per_page,
            'total': len(results)
        }