#coding=utf-8
#!/usr/bin/python
import re
import sys
import json
import requests
import time
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "36DJ舞曲网"

    def init(self, extend):
        try:
            self.extendDict = json.loads(extend)
        except:
            self.extendDict = {}
        
        # Konfigurasi proxy
        self.proxies = {}
        self.proxy_str = None
        if 'proxy' in self.extendDict:
            proxy_val = self.extendDict['proxy']
            if proxy_val:
                if isinstance(proxy_val, dict):
                    self.proxies = proxy_val
                elif isinstance(proxy_val, str):
                    self.proxy_str = proxy_val
                    self.proxies = {
                        'http': f'http://{proxy_val}',
                        'https': f'http://{proxy_val}'
                    }
        
        # Buat session dengan koneksi terbatas
        self.session = requests.Session()
        
        # Batasi jumlah koneksi simultan untuk mencegah kebuntuan
        adapter = HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=Retry(total=2, backoff_factor=0.5)
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.36dj.com",
            "Connection": "close",
            "Cache-Control": "no-cache"
        }
        
        # Header khusus untuk streaming audio
        self.audio_header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
            "Referer": "https://www.36dj.com",
            "Origin": "https://www.36dj.com",
            "Connection": "close",
            "Range": "bytes=0-",
            "Cache-Control": "no-cache"
        }
        
        self.base_url = "https://www.36dj.com"
        self.cdn_domain = "https://tn1.72djapp.cn"
        self.items_per_page = 20
        
        # Track stream yang sedang aktif
        self.active_stream = None
        
        # ==================== KATEGORI UTAMA ====================
        self.categories = [
            {'type_id': 'index', 'type_name': '首页'},
            {'type_id': 'xc', 'type_name': '串烧舞曲'},
            {'type_id': 'myxc', 'type_name': '慢摇串烧'},
            {'type_id': 'zw', 'type_name': '中文舞曲'},
            {'type_id': 'my', 'type_name': '慢摇舞曲'},
            {'type_id': 'yw', 'type_name': '英文舞曲'},
            {'type_id': 'new', 'type_name': '最新舞曲'},
            {'type_id': 'good', 'type_name': '推荐舞曲'},
            {'type_id': 'top', 'type_name': 'DJ舞曲榜'},
            {'type_id': 'search', 'type_name': '搜索DJ'}
        ]
        
        # ==================== SUB KATEGORI ====================
        self.sub_categories = {
            'xc': [
                {'n': '电音', 'v': '/top/dianyin/'},
                {'n': '女声dj', 'v': '/top/nvsheng/'},
                {'n': '英文', 'v': '/top/yingwendj/'},
                {'n': '轻音乐', 'v': '/top/xuanv/'},
                {'n': '全中文', 'v': '/top/zwdjcs/'},
                {'n': '车载dj', 'v': '/top/chezaidj/'},
                {'n': '伤感dj', 'v': '/top/tag/shanggan.html'},
                {'n': '越南鼓', 'v': '/top/yuenangudj/'},
                {'n': '重低音', 'v': '/top/zhongdiyindj/'},
                {'n': '经典老歌', 'v': '/top/tag/jingdian.html'},
                {'n': '狂嗨', 'v': '/top/tag/kuang.html'},
                {'n': '热门', 'v': '/top/tag/remen.html'},
                {'n': '抒情', 'v': '/top/tag/shuqing.html'},
                {'n': '国会鼓', 'v': '/top/tag/guohuigudj.html'},
                {'n': '派对', 'v': '/top/tag/paidui.html'},
                {'n': '粤语', 'v': '/top/tag/yueyu.html'},
                {'n': '旋律', 'v': '/top/tag/xuanlv.html'},
                {'n': '档次', 'v': '/top/tag/dangci.html'},
                {'n': '重鼓', 'v': '/top/tag/zhonggu.html'},
                {'n': '男声', 'v': '/top/tag/nansheng.html'},
                {'n': '酒吧暖场', 'v': '/top/tag/nuanchang.html'},
                {'n': '发烧车载', 'v': '/top/tag/fashao.html'},
                {'n': 'Proghouse', 'v': '/top/tag/prog.html'},
                {'n': '百听不厌', 'v': '/top/tag/baitingbuyan.html'}
            ],
            'myxc': [
                {'n': '慢摇', 'v': '/top/tag/manyao.html'},
                {'n': '夜店', 'v': '/top/tag/yedian.html'},
                {'n': '包房', 'v': '/top/tag/baofang.html'},
                {'n': '苏荷', 'v': '/top/tag/suhe.html'},
                {'n': '气氛', 'v': '/top/tag/qifen.html'},
                {'n': '极品', 'v': '/top/tag/jipin.html'},
                {'n': '汽车dj慢摇', 'v': '/top/qichemanyao/'},
                {'n': '包厢慢摇', 'v': '/top/tag/baoxiang.html'},
                {'n': '劲爆dj舞曲', 'v': '/top/jinbaodj/'}
            ],
            'zw': [
                {'n': '全中文', 'v': '/top/zwdjcs/'},
                {'n': '情歌', 'v': '/top/tag/qingge.html'},
                {'n': '伤感dj', 'v': '/top/tag/shanggan.html'},
                {'n': '经典老歌', 'v': '/top/tag/jingdian.html'},
                {'n': '粤语', 'v': '/top/tag/yueyu.html'},
                {'n': '男声', 'v': '/top/tag/nansheng.html'},
                {'n': '女声dj', 'v': '/top/nvsheng/'},
                {'n': '加快舞曲', 'v': '/top/tag/jiakuai.html'},
                {'n': '老歌DJ', 'v': '/top/laogedj/'}
            ],
            'my': [
                {'n': '慢摇', 'v': '/top/tag/manyao.html'},
                {'n': '车载dj', 'v': '/top/chezaidj/'},
                {'n': '重低音', 'v': '/top/zhongdiyindj/'},
                {'n': '重鼓', 'v': '/top/tag/zhonggu.html'},
                {'n': '旋律', 'v': '/top/tag/xuanlv.html'},
                {'n': '档次', 'v': '/top/tag/dangci.html'}
            ],
            'yw': [
                {'n': '英文', 'v': '/top/yingwendj/'},
                {'n': '电音', 'v': '/top/dianyin/'},
                {'n': '越南鼓', 'v': '/top/yuenangudj/'},
                {'n': 'DeepHouse', 'v': '/top/tag/deep.html'},
                {'n': 'Proghouse', 'v': '/top/tag/prog.html'},
                {'n': 'Trance/Club', 'v': '/top/tag/club.html'},
                {'n': 'Break/House', 'v': '/top/tag/house.html'},
                {'n': 'Rnb/Hip-Hop', 'v': '/top/tag/rnb.html'}
            ],
            'new': [
                {'n': '热门', 'v': '/top/tag/remen.html'},
                {'n': '车载dj', 'v': '/top/chezaidj/'},
                {'n': '抖音最火DJ', 'v': '/top/douyindj/'},
                {'n': '好听的dj', 'v': '/top/haotingdj/'}
            ],
            'good': [
                {'n': '热门', 'v': '/top/tag/remen.html'},
                {'n': '精品', 'v': '/top/tag/jipin.html'},
                {'n': '百听不厌', 'v': '/top/tag/baitingbuyan.html'},
                {'n': '好听的dj', 'v': '/top/haotingdj/'}
            ],
            'top': [
                {'n': '热门', 'v': '/top/tag/remen.html'},
                {'n': '经典老歌', 'v': '/top/tag/jingdian.html'},
                {'n': '车载dj', 'v': '/top/chezaidj/'},
                {'n': '伤感dj', 'v': '/top/tag/shanggan.html'},
                {'n': '劲爆dj舞曲', 'v': '/top/jinbaodj/'}
            ]
        }

    def _close_active_stream(self):
        """Tutup koneksi streaming yang masih aktif"""
        if self.active_stream:
            try:
                self.active_stream.close()
            except:
                pass
            self.active_stream = None

    def _get_session(self):
        """Dapatkan session baru untuk setiap request"""
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _get_url(self, cid, page=1, keyword=''):
        """Membangun URL"""
        if cid == 'index':
            return f"{self.base_url}/"
        
        if cid == 'search' or keyword:
            if page == 1:
                return f"{self.base_url}/e/search/index.php?classid=1&show=title&tempid=1&keyboard={quote(keyword)}"
            else:
                offset = (page - 1) * self.items_per_page
                return f"{self.base_url}/e/search/index.php?classid=1&show=title&tempid=1&keyboard={quote(keyword)}&offset={offset}"
        
        if cid in ['xc', 'myxc', 'zw', 'my', 'yw']:
            if page == 1:
                return f"{self.base_url}/{cid}/"
            else:
                return f"{self.base_url}/{cid}/index_{page}.html"
        
        if cid == 'new':
            if page == 1:
                return f"{self.base_url}/html/new/"
            else:
                return f"{self.base_url}/html/new/index_{page}.html"
        
        if cid == 'good':
            if page == 1:
                return f"{self.base_url}/html/good/"
            else:
                return f"{self.base_url}/html/good/index_{page}.html"
        
        if cid == 'top':
            if page == 1:
                return f"{self.base_url}/top/"
            else:
                return f"{self.base_url}/top/index_{page}.html"
        
        return f"{self.base_url}/"

    def _extract_videos_from_list(self, html, category_name=""):
        """Ekstrak video dari halaman list"""
        videos = []
        seen = set()
        
        pattern = r'<a[^>]+href="/(play/(\d+)\.html)"[^>]*(?:title="([^"]*)")?[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.DOTALL)
        
        for url_path, sid, title, content in matches:
            if sid not in seen:
                seen.add(sid)
                song_title = title if title else re.sub(r'<[^>]+>', '', content).strip()
                song_title = re.sub(r'^[\d]+\.\s*', '', song_title)
                song_title = song_title[:100] if song_title else f"DJ歌曲 {sid}"
                
                videos.append({
                    "vod_id": sid,
                    "vod_name": song_title,
                    "vod_pic": f"{self.base_url}/e/data/images/notimg.gif",
                    "vod_remarks": category_name
                })
        
        return videos

    def _has_next_page(self, html):
        """Cek apakah ada halaman berikutnya"""
        patterns = [
            r'<a[^>]+href="[^"]*index_(\d+)\.html"[^>]*>下一页</a>',
            r'<a[^>]+class="next"[^>]*>',
            r'<a[^>]*>下一页</a>',
            r'<li class="next">',
            r'<link rel="next"'
        ]
        for pattern in patterns:
            if re.search(pattern, html, re.IGNORECASE):
                return True
        return False

    def _get_page_name(self, cid):
        """Dapatkan nama halaman"""
        for cat in self.categories:
            if cat['type_id'] == cid:
                return cat['type_name']
        return "DJ舞曲"

    def _extract_audio_url(self, html, song_id):
        """Ekstrak URL audio"""
        # Metode 1: Variabel info
        info_match = re.search(r'var\s+info\s*=\s*\{\s*"playurl"\s*:\s*"([^"]+)"', html)
        if info_match:
            playurl = info_match.group(1)
            return f"{self.cdn_domain}/{playurl}"
        
        # Metode 2: CDN pattern
        cdn_match = re.search(r'(?:https?:)?//tn\d+\.72djapp\.cn/([^\s"\']+\.m4a)', html, re.IGNORECASE)
        if cdn_match:
            playurl = cdn_match.group(1)
            return f"{self.cdn_domain}/{playurl}"
        
        # Metode 3: Langsung .m4a URL
        m4a_match = re.search(r'https?://tn\d+\.72djapp\.cn/[^\s"\']+\.m4a', html, re.IGNORECASE)
        if m4a_match:
            return m4a_match.group(0)
        
        # Metode 4: Audio tag
        audio_match = re.search(r'<audio[^>]+src="([^"]+)"', html)
        if audio_match:
            return audio_match.group(1)
        
        return None

    def _extract_cover_url(self, html, song_id):
        """Ekstrak URL cover"""
        patterns = [
            r'<meta property="og:image" content="([^"]+)"',
            r'<img[^>]+class="[^"]*cover[^"]*"[^>]+src="([^"]+)"',
            r'<img[^>]+src="([^"]+)"[^>]+class="[^"]*cover[^"]*"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                cover = match.group(1)
                if cover.startswith('//'):
                    cover = 'https:' + cover
                return cover
        return f"{self.base_url}/e/data/images/notimg.gif"

    def _extract_duration(self, html):
        """Ekstrak durasi"""
        match = re.search(r'时长[：:]\s*([0-9:]+)', html)
        if match:
            return match.group(1)
        return ""

    def _extract_description(self, html):
        """Ekstrak deskripsi"""
        match = re.search(r'<meta name="description" content="([^"]+)"', html)
        if match:
            return match.group(1)[:500]
        return ""

    # ==================== METHOD UNTUK OK影视 ====================
    
    def homeContent(self, filter):
        """Menu utama dengan kategori dan sub kategori"""
        result = {
            'class': self.categories,
            'filters': {}
        }
        
        if filter:
            filters = {}
            for cat_id, sub_list in self.sub_categories.items():
                filters[cat_id] = [
                    {
                        'key': 'sub',
                        'name': '分类筛选',
                        'value': sub_list
                    }
                ]
            result['filters'] = filters
        
        return result

    def homeVideoContent(self):
        """Konten beranda"""
        return self.categoryContent('index', 1, False, {})

    def categoryContent(self, cid, page, filter, ext):
        """Konten per kategori dengan pagination"""
        page = int(page)
        result = {'list': [], 'page': page, 'pagecount': page, 'limit': 0}
        
        # Tutup stream sebelumnya
        self._close_active_stream()
        time.sleep(0.5)  # Jeda sebentar
        
        # Gunakan session baru
        session = self._get_session()
        
        try:
            # Cek sub kategori
            if ext and 'sub' in ext:
                sub_value = ext['sub']
                path_suffix = None
                
                for cat_id, sub_list in self.sub_categories.items():
                    for sub in sub_list:
                        if sub['n'] == sub_value or sub['v'] == sub_value:
                            path_suffix = sub['v']
                            break
                    if path_suffix:
                        break
                
                if path_suffix:
                    if page == 1:
                        url = f"{self.base_url}{path_suffix}"
                    else:
                        if path_suffix.endswith('.html'):
                            base_path = path_suffix.replace('.html', '')
                            url = f"{self.base_url}{base_path}_{page}.html"
                        else:
                            if not path_suffix.endswith('/'):
                                path_suffix = path_suffix + '/'
                            url = f"{self.base_url}{path_suffix}index_{page}.html"
                    
                    print(f"Sub kategori URL: {url}")
                    r = session.get(url, headers=self.header, timeout=15, proxies=self.proxies)
                    r.encoding = 'utf-8'
                    html = r.text
                    
                    videos = self._extract_videos_from_list(html, sub_value if isinstance(sub_value, str) and not sub_value.startswith('/') else '筛选')
                    has_next = self._has_next_page(html)
                    
                    result['list'] = videos[:self.items_per_page]
                    result['limit'] = len(result['list'])
                    result['pagecount'] = page + 1 if has_next and videos else page
                    
                    return result
            
            # Cek pencarian
            if ext and 'tid' in ext and ext['tid']:
                keyword = ext['tid']
                return self._search_page(keyword, page, session)
            
            # Kategori biasa
            url = self._get_url(cid, page)
            page_name = self._get_page_name(cid)
            
            print(f"Kategori URL: {url}")
            r = session.get(url, headers=self.header, timeout=15, proxies=self.proxies)
            r.encoding = 'utf-8'
            html = r.text
            
            videos = self._extract_videos_from_list(html, page_name)
            has_next = self._has_next_page(html)
            
            result['list'] = videos[:self.items_per_page]
            result['limit'] = len(result['list'])
            result['pagecount'] = page + 1 if has_next and videos else page
            
        except Exception as e:
            print(f"Error categoryContent: {e}")
        finally:
            session.close()
        
        return result

    def detailContent(self, did):
        """Ambil detail lagu"""
        song_id = did[0] if isinstance(did, list) else did
        result = {'list': []}
        
        # Tutup stream sebelumnya
        self._close_active_stream()
        time.sleep(0.5)
        
        session = self._get_session()
        
        try:
            url = f"{self.base_url}/play/{song_id}.html"
            print(f"Detail URL: {url}")
            
            r = session.get(url, headers=self.header, timeout=15, proxies=self.proxies)
            r.encoding = 'utf-8'
            html = r.text
            
            # Judul
            title_match = re.search(r'<title>([^<]+)</title>', html)
            title = title_match.group(1).strip() if title_match else f"DJ {song_id}"
            title = re.sub(r'试听,mp3下载\s*-\s*36DJ舞曲.*$', '', title)
            title = title.strip()
            
            # Audio URL
            audio_url = self._extract_audio_url(html, song_id)
            
            if not audio_url:
                print(f"GAGAL: Tidak menemukan URL audio untuk ID {song_id}")
                return result
            
            # Cover
            cover_url = self._extract_cover_url(html, song_id)
            
            # Durasi
            duration = self._extract_duration(html)
            
            # Deskripsi
            content = self._extract_description(html)
            
            vod = {
                "vod_id": song_id,
                "vod_name": title[:100],
                "vod_pic": cover_url,
                "vod_content": content or f"{title}",
                "vod_play_from": "36DJ舞曲网",
                "vod_play_url": f"{title}${audio_url}",
                "vod_remarks": duration or "DJ舞曲"
            }
            
            result['list'] = [vod]
            print(f"Berhasil: {title[:50]}... | Audio: {audio_url[:80]}...")
            
        except Exception as e:
            print(f"Detail error: {e}")
        finally:
            session.close()
        
        return result

    def searchContent(self, key, quick, pg=1):
        """Pencarian"""
        if quick:
            return {'list': []}
        
        # Tutup stream sebelumnya
        self._close_active_stream()
        time.sleep(0.5)
        
        session = self._get_session()
        
        try:
            return self._search_page(key, int(pg), session)
        finally:
            session.close()

    def _search_page(self, keyword, page, session=None):
        """Pencarian dengan pagination"""
        result = {'list': [], 'page': page, 'pagecount': page, 'limit': 0}
        
        close_session = False
        if session is None:
            session = self._get_session()
            close_session = True
        
        try:
            if page == 1:
                url = f"{self.base_url}/e/search/index.php?classid=1&show=title&tempid=1&keyboard={quote(keyword)}"
            else:
                offset = (page - 1) * self.items_per_page
                url = f"{self.base_url}/e/search/index.php?classid=1&show=title&tempid=1&keyboard={quote(keyword)}&offset={offset}"
            
            print(f"Mencari: {url}")
            
            r = session.get(url, headers=self.header, timeout=15, proxies=self.proxies)
            r.encoding = 'utf-8'
            html = r.text
            
            videos = self._extract_videos_from_list(html, "搜索结果")
            has_next = self._has_next_page(html)
            
            for v in videos:
                v['vod_remarks'] = "搜索结果"
            
            result['list'] = videos[:self.items_per_page]
            result['limit'] = len(result['list'])
            result['pagecount'] = page + 1 if has_next and videos else page
            
        except Exception as e:
            print(f"Pencarian gagal: {e}")
        finally:
            if close_session:
                session.close()
        
        return result

    def playerContent(self, flag, pid, vipFlags):
        """URL untuk diputar"""
        # Tutup stream sebelumnya jika ada
        self._close_active_stream()
        time.sleep(0.5)
        
        # Buat header dengan Connection close
        headers = self.audio_header.copy()
        headers["Referer"] = f"{self.base_url}/play/"
        headers["Connection"] = "close"
        
        result = {
            "parse": 0,
            "url": pid,
            "header": headers
        }
        
        if self.proxy_str:
            result["proxy"] = self.proxy_str
        
        print(f"Player Content - URL: {pid[:100]}...")
        
        return result

    def removeHtmlTags(self, src):
        from re import sub, compile
        clean = compile('<.*?>')
        return sub(clean, '', src)

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        """Bersihkan resource saat spider dihancurkan"""
        self._close_active_stream()
        if hasattr(self, 'session'):
            try:
                self.session.close()
            except:
                pass