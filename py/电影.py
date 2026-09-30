# -*- coding: utf-8 -*-
"""
电影人生 (dyrshd.com) - TVBox 爬虫源
=====================================
接口：homeContent / categoryContent(含排序筛选) / detailContent(多线路) /
      playerContent(解析 m3u8 跨域 CDN) / searchContent

站点实测特性：
1. 移动端 UA 可正常访问（PC 未验证，统一用移动 UA）。
2. 分类：/dianying.html 等一级分类页（已移除二级子类型筛选，仅保留一级大类 + 排序）。
3. 翻页：?page=N 为 0 起始（第 1 页 page=0）。
4. 详情页列出多个「源/线路」(origin)，每个源对应一个播放页；播放页内嵌
   window.xg_video_player_doc.nexturl 数组，含每集 title 与播放 token。
5. 播放链路：
   dyrshd.com/api/m3u8?origin=源&url=token
     -> 302 跳转 box.dyrs.com.de/api/super?id=token&origin=源   (master m3u8)
     -> 变体 box.dyrs.com.de/api/m3u8?id=token                  (真实媒体列表，含 /api/ts 分片)
6. 防盗链：分片需 Referer: https://dyrshd.com/ 才能拿到真实视频流。
"""

import re
import json
import time
import threading
from urllib.parse import quote, unquote, urlencode

import requests
from requests.adapters import HTTPAdapter

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    ThreadPoolExecutor = None
    as_completed = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    import sys
    sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except ImportError:
    _BaseSpider = None


# ============================================================
# 常量
# ============================================================

HOST = "https://dyrshd.com"
# 真实视频 CDN（m3u8 跨域到这里）
MEDIA_HOST = "https://box.dyrs.com.de"
# 图片源（图床 CDN）。注意：图床在某些网络下会被限速/拦截导致整站海报全部
# 加载失败。因此 IMG_HOST 不再是写死常量，而是在 init 时通过 _select_img_host
# 用一张真实海报做探针，自动挑选「当前网络可达且最快」的图源；不可达时回退主站
# /img/ 路径（与主站同源同内容，实测可用）。
IMG_HOST = "https://pic2.tupian.click"

# 域名跟踪：站方可能的访问域名（含官方发布页 dyrs8.net、关联站 kingtv.vip 等）。
# 请求失败或主页打不开时自动向下探测，找到可用的更新 HOST 并记录变化。
DOMAIN_CANDIDATES = [
    "https://dyrshd.com",
    "https://dyrs8.net",      # 官方"最新网址"发布页
    "https://kingtv.vip",     # 关联站 kingtv
]
# 域名变化记录文件（与脚本同目录；只在有写权限时写入，无权限自动忽略）
DOMAIN_TRACK_FILE = "dyrshd_domain_track.log"

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

# 超时（秒）—— 整体收紧以快速失败，避免 UI 长时间卡在「加载中」
TIMEOUT_PAGE = 8      # 整页 HTML（首页/详情/分类/搜索）
TIMEOUT_API = 6      # 播放/线路解析（单线路探测，短超时快速失败）
TIMEOUT_PLAY = 6     # 播放解析（更短超时，快速失败）
TIMEOUT_IMG_PROBE = 5  # 图片源探测（init 时一次性）

# 缓存 TTL（秒）
TTL_HOME = 600       # 首页
TTL_CAT = 300        # 分类（含筛选组合）
TTL_DETAIL_OK = 1800 # 详情成功（多线路抓取较重，缓存久一点）
TTL_DETAIL_EMPTY = 30
TTL_SEARCH = 180     # 搜索
TTL_PLAY = 1800      # 播放地址

# 一级分类（已移除二级分类 / subs：分类页只保留一级大类，不再展开子类型筛选）
CATS = [
    {"id": "dianying", "name": "电影"},
    {"id": "dianshiju", "name": "电视剧"},
    {"id": "zongyi", "name": "综艺"},
    {"id": "dongman", "name": "动漫"},
    {"id": "duanju", "name": "短剧"},
]


# 全站真实播放线路（源）全集 —— 来自网站实测出现过的所有 origin 名称
# 用于详情解析时「补全」影片在各线路上的选集（多数线路为别名/代理，共用同一批流）
ORIGINS = [
    "超级线路", "王者TV加速", "王者TV蓝光", "lzm3u8", "1080zyk",
    "modum3u8", "bfzym3u8", "dyttm3u8", "ffm3u8", "jsm3u8",
    "mtm3u8", "wztv",
]
# 单影片并发探测线路数上限（必须 ≥ ORIGINS 数量，否则尾部线路永远探测不到；
# 12 条线路 + 动态线路，取 20 兼顾覆盖率与限流风险）
MAX_LINE_PROBE = 20


def _build_filters(cat):
    """构建筛选器：仅保留「排序」（二级分类/类型筛选已移除，避免空筛选项）"""
    filters = [{
        "key": "by", "name": "排序",
        "value": [
            {"n": "最新", "v": "time"},
            {"n": "最热", "v": "play_hot"},
            {"n": "评分", "v": "score"},
        ],
    }]
    return filters


# 全部分类 + 筛选器
ALL_CLASSES = [{"type_id": c["id"], "type_name": c["name"], "filter": 1} for c in CATS]
ALL_FILTERS = {c["id"]: _build_filters(c) for c in CATS}


# ============================================================
# Spider 主类
# ============================================================

_Base = _BaseSpider if _BaseSpider is not None else object


class Spider(_Base):
    siteUrl = HOST

    headers = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': HOST + '/',
    }

    # ===== 初始化 =====
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.headers['Connection'] = 'keep-alive'
        self.session.verify = False
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=40,
            max_retries=0,
            pool_block=False,
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self._lock = threading.Lock()
        self._home_cache = []
        self._home_cache_time = 0
        self._cat_cache = {}
        self._detail_cache = {}
        self._search_cache = {}
        self._play_cache = {}
        self._domain_checked = False

    def init(self, extend=""):
        self.extend = extend or ""
        # 每次任务开始前做一次域名跟踪（缓存探测结果，避免反复请求）
        self._track_domain()

    # ===== 域名跟踪 =====
    @staticmethod
    def _log_domain(old, new, source):
        """把域名变化写入跟踪日志（脚本同目录；无写权限时自动忽略）"""
        try:
            line = "{0} | {1} -> {2} | source={3}\n".format(
                time.strftime('%Y-%m-%d %H:%M:%S'), old, new, source)
            with open(DOMAIN_TRACK_FILE, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception:
            pass

    @staticmethod
    def _mark_track_ok(host):
        """记录当日主站可用（含日期 + host，供下次任务复用）"""
        try:
            with open(DOMAIN_TRACK_FILE, 'a', encoding='utf-8') as f:
                f.write("CHECK_OK | {0} | {1}\n".format(
                    host, time.strftime('%Y-%m-%d')))
        except Exception:
            pass

    @staticmethod
    def _is_track_ok(host):
        """当日已确认过该主站可用 -> True（避免每次任务重复探测）"""
        try:
            with open(DOMAIN_TRACK_FILE, 'r', encoding='utf-8') as f:
                last = None
                for line in f:
                    last = line
                if last and last.startswith('CHECK_OK'):
                    parts = last.strip().split(' | ')
                    return (len(parts) >= 3 and parts[1] == host
                            and parts[2] == time.strftime('%Y-%m-%d'))
        except Exception:
            pass
        return False

    def _probe_url(self, base, timeout=6):
        """GET 一个域名主页；返回 (status, text)，异常返回 (None, '')"""
        try:
            r = self.session.get(base, timeout=timeout)
            return r.status_code, r.text
        except Exception:
            return None, ''

    def _sync_live_domains(self, html):
        """从主页 JS 提取实时媒体域/图床域，变化时写日志并更新全局常量"""
        global MEDIA_HOST, IMG_HOST
        try:
            m2 = re.search(r'box\.([a-z0-9.-]+)/api/super', html)
            if m2:
                new_media = 'https://box.{0}'.format(m2.group(1))
                if new_media != MEDIA_HOST:
                    self._log_domain(MEDIA_HOST, new_media, 'home-js')
                    MEDIA_HOST = new_media
            m3 = re.search(r'var\s+dyrs_api_origin\s*=\s*"https?://([^"/]+)"', html)
            if m3:
                new_img = 'https://{0}'.format(m3.group(1))
                if new_img != IMG_HOST:
                    self._log_domain(IMG_HOST, new_img, 'home-js')
                    IMG_HOST = new_img
        except Exception:
            pass

    def _select_img_host(self, html):
        """选最快可达的图片源，解决「海报全部加载不出来」。

        站点海报同时存在于：图床 CDN(pic2.tupian.click 等，由 dyrs_api_origin
        指定) 与主站 /img/ 路径（同源同内容）。部分网络会限速/拦截图床，导致
        整站海报裂图。本函数在 init 时用【一张真实海报】对候选图源逐个 GET 探针，
        选首个返回 200 图片的图源写入全局 IMG_HOST；图床不可达则回退主站。

        探针仅一次（随 _track_domain 在 init 执行），开销 < 1s。
        """
        global IMG_HOST
        # 候选顺序：JS 指定的图床优先，主站 /img 兜底（永远可达同源）。
        # 注：dyrs_api_origin 在 HTML 里以转义形式出现（https:\/\/pic2.tupian.click），
        # 所以正则需兼容正反斜杠两种写法。
        candidates = []
        m = re.search(r'dyrs_api_origin\s*=\s*"https?:\\?/\\?/([^"/\\]+)"', html or '')
        if m:
            candidates.append('https://{0}'.format(m.group(1)))
        candidates.append(HOST)  # 主站兜底
        seen, cands = set(), []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                cands.append(c)

        # 从首页/详情 HTML 抽取一张真实海报（图床或 /img/ 皆可）作为探针样本
        probe = ''
        urls = re.findall(
            r'(?:https://[^"\'\s]*?pic2\.tupian\.click|/img/)[^"\'\s]+\.'
            r'(?:jpg|jpeg|png|webp)', html or '')
        if urls:
            probe = urls[0]
        if not probe:
            return  # 无样本，沿用当前 IMG_HOST

        for c in cands:
            if probe.startswith('/img/'):
                target = c + probe
            elif 'pic2.tupian.click' in probe:
                # 样本是图床全 URL：候选为主站时改写成主站路径，避免同域重复探测
                if 'tupian.click' in c:
                    target = probe  # 候选即图床，直接验证原样本
                else:
                    target = c + re.sub(r'https?://[^/]+', '', probe)
            else:
                continue
            try:
                r = self.session.get(
                    target, timeout=TIMEOUT_IMG_PROBE,
                    headers={'Referer': HOST + '/', 'Connection': 'keep-alive'})
                ctype = (r.headers.get('Content-Type') or '').lower()
                if r.status_code == 200 and 'image' in ctype:
                    if c != IMG_HOST:
                        self._log_domain(IMG_HOST, c, 'img-probe')
                    IMG_HOST = c
                    return
            except Exception:
                continue
        # 全部探针失败：保留 IMG_HOST 原值（默认图床），不阻断主流程

    def _track_domain(self):
        """域名跟踪：单次轻量请求检测当前 HOST（顺带提取实时媒体/图床域），
        失效时并行探测候选域名切换，变化写入 DOMAIN_TRACK_FILE。
        返回当前生效的 HOST。
        """
        global HOST, MEDIA_HOST
        if self._domain_checked:
            return HOST
        self._domain_checked = True

        # 0) 当日已确认主站可用 -> 跳过域名切换探测，但仍必须确认图片源可达
        #    （图床常被网络单独限速/拦截，因此每次任务都做一次轻量图片源探针）
        if self._is_track_ok(HOST):
            status, text = self._probe_url(HOST, timeout=TIMEOUT_IMG_PROBE)
            if status == 200 and text:
                self._sync_live_domains(text or '')
                self._select_img_host(text or '')
            return HOST

        # 1) 单次主页请求：既探测可达性，又提取实时媒体/图床域名 + 图片源探针。
        #    200 正常；429 是 SHA1 校验页（站点在线，PoW 由业务请求自行处理），
        #    也算可达，不能判失效。
        status, text = self._probe_url(HOST)
        if status == 200:
            self._sync_live_domains(text or '')
            self._select_img_host(text or '')
            self._mark_track_ok(HOST)
            return HOST
        if status == 429:
            self._mark_track_ok(HOST)
            return HOST
        # 主页请求失败（超时/重置）不一定是站挂了：用带 PoW 处理的业务
        # 链路再确认一次分类页，能出数据就仍视为主站可用。
        r = self._get(HOST + '/dianying.html?page=0',
                      referer=HOST + '/', timeout=TIMEOUT_API)
        if r is not None and r.status_code == 200:
            self._sync_live_domains(r.text or '')
            self._select_img_host(r.text or '')
            self._mark_track_ok(HOST)
            return HOST

        # 2) 主站不可用（超时/非200/429）-> 并行探测候选域名，取最先可达者
        import queue as _q
        q = _q.Queue()

        def _worker(c):
            s, t = self._probe_url(c)
            if s == 200:
                q.put((c, t))

        threads = []
        for cand in DOMAIN_CANDIDATES:
            if cand == HOST:
                continue
            th = threading.Thread(target=_worker, args=(cand,))
            th.daemon = True
            th.start()
            threads.append(th)
        for th in threads:
            th.join(timeout=8)

        found = None
        text = ''
        while not q.empty():
            found, text = q.get()
            break
        if found:
            old = HOST
            HOST = found
            self.siteUrl = HOST
            self.headers['Referer'] = HOST + '/'
            self._log_domain(old, HOST, 'candidate')
            self._sync_live_domains(text or '')
            self._select_img_host(text or '')
            self._mark_track_ok(HOST)
            return HOST

        # 3) 全部失败：记录一次失败日志（不阻塞，维持原 HOST）
        try:
            with open(DOMAIN_TRACK_FILE, 'a', encoding='utf-8') as f:
                f.write("{0} | ALL_DOMAINS_DOWN\n".format(
                    time.strftime('%Y-%m-%d %H:%M:%S')))
        except Exception:
            pass
        return HOST

    # ===== 网络工具 =====
    def _get(self, url, referer='', timeout=TIMEOUT_PAGE, _depth=0):
        """带超时与连接复用的 GET；自动处理 SHA1 工作量证明(429 校验页)"""
        headers = {'Connection': 'keep-alive'}
        if referer:
            headers['Referer'] = referer
        try:
            r = self.session.get(url, timeout=timeout, headers=headers)
        except Exception:
            return None

        # 站点反爬：参数化分类页会返回 HTTP 429 + JS 校验页（SHA1 工作量证明）。
        # 校验页内嵌 hash/target，需暴力求出 i 使 sha1(hash+i)==target，
        # 再把 ?attack_key=i 拼回 URL 重新请求即可放行。
        if r.status_code == 429 and _depth < 2 and self._is_pow_challenge(r.text):
            i = self._solve_pow(r.text)
            if i is not None:
                sep = '&' if '?' in url else '?'
                surl = "{0}{1}attack_key={2}".format(url, sep, i)
                return self._get(surl, referer, timeout, _depth + 1)
            return None
        if r.status_code == 429:
            # 无挑战页的 429：快速失败，不做无意义等待
            return None

        try:
            r.raise_for_status()
        except Exception:
            return None
        r.encoding = (r.apparent_encoding
                      if r.encoding in (None, 'ISO-8859-1') else r.encoding)
        return r

    @staticmethod
    def _is_pow_challenge(text):
        """判断是否命中站点的 SHA1 工作量证明校验页"""
        return 'passChallenge' in text and 'attack_key' in text

    @staticmethod
    def _solve_pow(text):
        """从校验页提取 hash/target，暴力求 i 使 sha1(hash+str(i))==target

        该站难度极低（i 通常 < 1000），可在毫秒级解出。
        """
        import hashlib
        mh = re.search(r"hash\s*=\s*'([0-9a-f]+)'", text)
        mt = re.search(r"target\s*=\s*'([0-9a-f]+)'", text)
        if not mh or not mt:
            return None
        h, t = mh.group(1), mt.group(1)
        for i in range(0, 5_000_000):
            if hashlib.sha1((h + str(i)).encode()).hexdigest() == t:
                return i
        return None

    def _get_text(self, url, referer='', timeout=TIMEOUT_PAGE):
        r = self._get(url, referer, timeout)
        return r.text if r is not None else ""

    # ===== 缓存 =====
    @staticmethod
    def _cache_get(cache, key, ttl=None):
        item = cache.get(key)
        if item and time.time() - item[0] < (ttl if ttl is not None else item[2]):
            return item[1]
        return None

    @staticmethod
    def _cache_set(cache, key, value, ttl=TTL_CAT):
        if len(cache) > 512:
            cache.clear()
        cache[key] = (time.time(), value, ttl)

    # ===== HTML 解析 =====
    @staticmethod
    def _soup(html):
        if not html or BeautifulSoup is None:
            return None
        try:
            return BeautifulSoup(html, 'lxml')
        except Exception:
            try:
                return BeautifulSoup(html, 'html.parser')
            except Exception:
                return None

    @staticmethod
    def _abs(u):
        """相对路径补全为全站 HTTPS 地址"""
        u = (u or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return HOST + u
        if not u.startswith('http'):
            return HOST + '/' + u
        return u

    @staticmethod
    def _abs_pic(u):
        """图片地址补全：走当前生效图源 IMG_HOST（init 时经 _select_img_host
        探测选出的可达图源；图床被网络拦截时自动回退主站 /img）。

        处理三种来源：
        1) /img/...           -> IMG_HOST + 路径（图床与主站同结构）
        2) 写死的 pic2.tupian.click 全 URL -> 图床可用时原样返回；不可达时整体
           改写为当前生效图源（如主站），避免海报全部裂图。
        3) 其他相对/全 URL    -> 走 _abs 补全。
        """
        u = (u or '').strip()
        if not u:
            return ''
        # 写死图床全 URL：当前图源若不是该图床（说明已回退），整体改写前缀
        if 'pic2.tupian.click' in u and 'tupian.click' not in IMG_HOST:
            path = re.sub(r'https?://[^/]+', '', u)
            return IMG_HOST + path
        if u.startswith('/img/'):
            return IMG_HOST + u
        return Spider._abs(u)

    @staticmethod
    def _extract_vid(href):
        """从 /tv/{id}.html 或 /movie/{id}.html 提取 vid（保留 tv/ 前缀）"""
        m = re.search(r'/(?:tv|movie)/([0-9a-f]+(?:-[0-9a-f]+)?)\.html', href.strip())
        return ('tv/' + m.group(1)) if m else None

    # ===== 卡片解析（分类 / 搜索共用）=====
    def _parse_cards(self, html, limit=36):
        """解析卡片列表 -> TVBox vod 字段。

        注意：站点同一影片常出现两类链接——「文字列表 <a>」（无封面，仅标题）
        与「海报网格 <a>」（含 <img> 封面，标题在 <h2>/<img alt>）。两者 vid 相同，
        若文字链接触达在先会被先登记为无封面卡片，导致海报被后续重复项跳过而丢失。
        故采用「合并去重」：同一 vid 再次遇到带封面的链接时补全封面，确保海报不丢。
        """
        if not html:
            return []
        soup = self._soup(html)
        if soup is None:
            return []
        items = {}
        order = []
        for a in soup.select('a[href*="/tv/"], a[href*="/movie/"]'):
            href = str(a.get('href') or '')
            vid = self._extract_vid(href)
            if not vid:
                continue
            # 封面：img 的 data-src / data-original / data-lazy-src / src
            # （/img/ 走当前生效图源；覆盖主流懒加载写法，避免封面为空）
            pic = ''
            img = a.find('img')
            if img:
                for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
                    val = str(img.get(attr) or '').strip()
                    if val:
                        pic = self._abs_pic(val)
                        break
            # 标题：a.title / <h2>,<h3> / <img alt> / 纯文本兜底
            title = str(a.get('title') or '').strip()
            if not title:
                h = a.find(['h2', 'h3'])
                title = h.get_text(strip=True) if h else ''
            if not title and img:
                title = str(img.get('alt') or '').strip()
            if not title:
                title = a.get_text(strip=True)
            if not title:
                continue
            if vid in items:
                # 已存在：补全封面/标题（优先带图、带标题者），不新增重复项
                if pic and not items[vid]['vod_pic']:
                    items[vid]['vod_pic'] = pic
                if not items[vid]['vod_name'] and title:
                    items[vid]['vod_name'] = title
                continue
            # 备注角标（HD国语 / 1080p 等）
            remarks = ''
            badge = a.select_one('div.absolute')
            if badge:
                remarks = badge.get_text(strip=True)
            if not remarks:
                info = a.find_parent('div')
                if info:
                    txt = info.get_text(' ', strip=True)
                    m = re.search(r'(更新至[^\s]{0,12}|全\d+集|全集|已完结|正片|HD\w*|TC\w*|1080p)', txt)
                    if m:
                        remarks = m.group(1)
            items[vid] = {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks,
            }
            order.append(vid)
        return [items[v] for v in order][:limit]

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter=False):
        vod_list = []
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                vod_list = self._home_cache[:60]

        if not vod_list:
            try:
                html = self._get_text(HOST)
                vod_list = self._parse_cards(html, limit=60)
                if vod_list:
                    with self._lock:
                        self._home_cache = vod_list
                        self._home_cache_time = int(time.time())
            except Exception:
                pass

        return {
            "class": ALL_CLASSES,
            "filters": ALL_FILTERS,
            "list": vod_list,
        }

    def homeVideoContent(self):
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                return {"list": self._home_cache[:60]}
        try:
            html = self._get_text(HOST)
            vod_list = self._parse_cards(html, limit=60)
            if vod_list:
                with self._lock:
                    self._home_cache = vod_list
                    self._home_cache_time = int(time.time())
            return {"list": vod_list[:60]}
        except Exception:
            return {"list": []}

    # ============================================================
    # 分类列表（一级分类 + 排序）
    # ============================================================
    def _empty_category(self, page=1):
        return {"list": [], "page": page, "pagecount": 1, "limit": 36, "total": 0}

    def categoryContent(self, tid, pg, filter, extend):
        """分类列表：支持排序(by)（二级分类/类型筛选已移除）

        注：参数 filter 为 TVBox 框架传入的布尔开关（是否启用筛选 UI），
        本源通过 extend 字典携带实际筛选条件，故该形参未直接使用。
        """
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1

        # 解析 extend 筛选参数
        ext = {}
        if extend:
            if isinstance(extend, dict):
                ext = extend
            elif isinstance(extend, str):
                try:
                    ext = json.loads(extend)
                except Exception:
                    ext = {}

        # 组合缓存
        ckey = "{0}|{1}|{2}".format(tid, page,
                                    json.dumps(ext, ensure_ascii=False, sort_keys=True))
        cached = self._cache_get(self._cat_cache, ckey, TTL_CAT)
        if cached is not None:
            return cached

        # 构造分类 URL：?page={n-1}（0 起始）+ class + by
        params = {'page': page - 1}
        cls = (ext.get('class') or '').strip()
        if cls:
            params['class'] = cls
        by = (ext.get('by') or ext.get('sort_field') or '').strip()
        if by:
            params['sort_field'] = by
        url = "{0}/{1}.html?{2}".format(HOST, tid, urlencode(params))

        html = self._get_text(url)
        if not html:
            return self._empty_category(page)

        # 解析分页（链接形如 ?page=N）
        pagecount = 1
        nums = [int(x) for x in re.findall(r'[?&]page=(\d+)', html)]
        if nums:
            pagecount = max(nums) + 1  # page 从 0 起始

        vod_list = self._parse_cards(html, limit=36)
        result = {
            "list": vod_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 36,
            "total": pagecount * 36,
        }
        self._cache_set(self._cat_cache, ckey, result, TTL_CAT)
        return result

    # ============================================================
    # 详情页（多线路：抓取各源播放页，提取选集）
    # ============================================================
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vid = str(ids[0]).split(',')[0].strip()
        if not vid:
            return {"list": []}

        cached = self._cache_get(self._detail_cache, vid, None)
        if cached is not None:
            return cached

        result = self._fetch_detail(vid)
        ttl = TTL_DETAIL_OK if result.get("list") else TTL_DETAIL_EMPTY
        self._cache_set(self._detail_cache, vid, result, ttl)
        return result

    def _fetch_detail(self, vid):
        """抓取并解析详情页 + 各线路选集

        站点有两套播放模板（实测）：
        【模板A / 旧】详情页内嵌 currentUrl 数组（整季 token），形如：
              currentUrl = "\\/api\\/m3u8?origin=线路名\\u0026url=TOKEN";
          直接解析即可，无需额外请求。
        【模板B / 新】详情页不内嵌 token，每集 m3u8 直链（vodcnd*.uvjtih.cn 等
          CDN）嵌在「选集子页」 /movie/{hex}/{num}.html?origin=X&p=0 的
          window.xg_video_player_doc.aa（JSON 数组）里。该子页一次性返回当前
          线路的整季直链，故每线路仅 1 次请求。
        """
        html = self._get_text("{0}/{1}.html".format(HOST, vid))
        if not html:
            return {"list": []}

        soup = self._soup(html)
        if soup is None:
            return {"list": []}

        # --- 基本信息 ---
        name = ''
        h1 = soup.find('h1')
        if h1:
            name = h1.get_text(strip=True)
        if not name:
            t = soup.select_one('.myui-content__detail h1') or soup.title
            if t:
                name = t.get_text(strip=True)

        # 封面（走当前生效图源；覆盖懒加载写法，避免封面为空）
        pic = ''
        img = (soup.select_one('img[data-src]')
               or soup.select_one('img[data-original]')
               or soup.select_one('img[src]'))
        if img:
            for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
                val = str(img.get(attr) or '').strip()
                if val:
                    pic = self._abs_pic(val)
                    break

        # 简介
        content = ''
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta:
            content = str(meta.get('content') or '').strip()

        # --- 线路与选集（覆盖网站全部真实线路）---
        play_groups = self._collect_lines(vid, html)

        if not play_groups:
            return {"list": [{
                "vod_id": vid,
                "vod_name": name or "视频{0}".format(vid),
                "vod_pic": pic or HOST,
                "vod_remarks": '',
                "vod_content": content,
                "vod_play_from": '默认',
                "vod_play_url": '',
            }]}

        # 构造 play_from / play_url
        play_from, play_url = '', ''
        for line_name, eps in play_groups:
            if not eps:
                continue
            ep_parts = ["{0}${1}".format(t, u) for t, u in eps]
            play_from = (play_from + '$$$' + line_name) if play_from else line_name
            play_url = (play_url + '$$$' + '#'.join(ep_parts)) if play_url else '#'.join(ep_parts)

        detail = {
            "vod_id": vid,
            "vod_name": name or "视频{0}".format(vid),
            "vod_pic": pic or HOST,
            "vod_remarks": '',
            "vod_content": content,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [detail]}

    @staticmethod
    def _build_group_from_tokens(origin, tokens):
        """模板A：token 列表 -> (线路名, [(标题, master_url), ...])"""
        eps = []
        for idx, tok in enumerate(tokens):
            title = "第{0:02d}集".format(idx + 1)
            master = "{0}/api/m3u8?origin={1}&url={2}".format(HOST, quote(origin), tok)
            eps.append((title, master))
        return (origin, eps)

    def _collect_lines(self, vid, html):
        """收集该影片【全部真实线路】的整季选集

        策略：
        1) 从详情页 episodeContent 按钮提取「该影片实际拥有的动态线路」
        2) 合并全站已知真实线路 ORIGINS（兜底补全，覆盖网站全部源）
        3) 并发探测每个线路，模板自适应解析（A: currentUrl token / B: 子页直链），
           最终按播放 url 去重合并，避免别名线路重复。
        返回 [(line_name, [(title, url), ...]), ...]
        """
        # 1) 动态线路（该影片详情页实际渲染的源）
        dyn = []
        i = html.find('id="episodeContent"')
        blk = html[i:] if i > 0 else html
        for h in re.findall(r'href="(/(?:tv|movie)/[^"]+)"', blk):
            mo = re.search(r'origin=([^&]+)', h)
            if mo:
                o = unquote(mo.group(1))
                if o and o not in dyn:
                    dyn.append(o)

        # 2) 合并全站真实线路（去重保序）
        seen = set()
        all_o = []
        for o in dyn + list(ORIGINS):
            if o and o not in seen:
                seen.add(o)
                all_o.append(o)
        if not all_o:
            all_o = ['']
        all_o = all_o[:MAX_LINE_PROBE]

        # 3) 并发探测：提高并发度（8 线程）加速整季选集抓取，缩短详情/起播耗时。
        #    配合 TIMEOUT_API=6s 短超时，单线路失败可快速跳过，不会拖垮整体。
        groups = {}
        order = []
        if ThreadPoolExecutor is not None:
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(self._probe_line, vid, o, html): o for o in all_o}
                for f in as_completed(futs):
                    o = futs[f]
                    try:
                        data = f.result()
                    except Exception:
                        data = None
                    if data and data[1]:
                        key = o or '默认线路'
                        groups[key] = data[1]
                        order.append(key)
        else:
            for o in all_o:
                data = self._probe_line(vid, o, html)
                if data and data[1]:
                    key = o or '默认线路'
                    groups[key] = data[1]
                    order.append(key)
        return [(o, groups[o]) for o in order]

    def _probe_line(self, vid, origin, base_html):
        """探测单个线路(origin)的整季选集，模板自适应

        返回 (line_name, [(title, url), ...])；无数据返回 ('', [])。
        origin 为空串时直接复用主详情页(base_html)。
        """
        if origin:
            line_html = self._get_text(
                "{0}/{1}.html?origin={2}".format(HOST, vid, quote(origin)),
                timeout=TIMEOUT_API)
        else:
            line_html = base_html
        if not line_html:
            return ('', [])

        # 模板A：内嵌 currentUrl token 整季
        pl = self._parse_playlist(line_html)
        if pl and pl[1]:
            return self._build_group_from_tokens(pl[0] or origin or '默认线路', pl[1])

        # 模板B：直链在 /movie 子页
        tb = self._parse_template_b_line(line_html, origin)
        if tb and tb[1]:
            return tb

        return ('', [])

    def _parse_template_b_line(self, html, origin):
        """模板B：抓取指定线路 origin 的选集子页，提取整季直链 m3u8

        返回 (line_name, [(title, url), ...])，失败返回 None。
        """
        i = html.find('id="episodeContent"')
        blk = html[i:] if i > 0 else html
        hrefs = re.findall(r'href="(/(?:tv|movie)/[^"]+)"', blk)
        if not hrefs:
            return None
        base_href = hrefs[0].replace('&amp;', '&')

        page = re.sub(r'[?&]p=\d+', '', base_href)
        sep = '&' if '?' in page else '?'
        page = page + sep + 'p=0'
        if origin:
            page = re.sub(r'[?&]origin=[^&]+', '', page)
            psep = '&' if '?' in page else '?'
            page = page + psep + 'origin=' + quote(origin)

        eh = self._get_text(HOST + page, timeout=TIMEOUT_API)
        if not eh:
            return None
        items = self._parse_xg_all(eh)
        if not items:
            return None
        eps = [((t or "第{0:02d}集".format(idx + 1)), u)
               for idx, (t, u, _) in enumerate(items)]
        return (origin or '默认线路', eps)

    @staticmethod
    def _parse_xg_all(html):
        """提取页面里所有 JSON.parse('...') 中的 {origin,url,title} 播放记录

        模板B 的直链 m3u8 以 \\u0022 转义引号、\\/ 转义斜杠包裹在 JSON 字符串里。
        返回 [(title, url, origin), ...]（按 url 去重）。
        """
        out = []
        if not html:
            return out
        for mm in re.finditer(r'JSON\.parse\(\'(.*?)\'\)', html, re.S):
            raw = mm.group(1).replace('\\u0022', '"').replace('\\/', '/')
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            items = obj if isinstance(obj, list) else [obj]
            for it in items:
                if isinstance(it, dict) and it.get('url'):
                    out.append((it.get('title', ''), it.get('url'), it.get('origin', '')))
        seen = set()
        uniq = []
        for t, u, o in out:
            if u in seen:
                continue
            seen.add(u)
            uniq.append((t, u, o))
        return uniq

    @staticmethod
    def _parse_playlist(html):
        """从详情/线路页提取「当前渲染线路」的整季选集 token

        页面每个选集按钮附带 currentUrl = "\\/api\\/m3u8?origin=线路名\\u0026url=TOKEN";
        返回 (line_name, [token, ...])，失败返回 None。
        注：正则全程不使用反斜杠（用字符类替代），避免转义翻倍导致的匹配失效。
        """
        if not html:
            return None
        # 提取每个 currentUrl = "..." 的值串（含转义反斜杠）
        vals = re.findall(r'currentUrl[ ]*=[ ]*"([^"]*)"', html)
        if not vals:
            return None
        line_name = ''
        tokens = []
        for v in vals:
            # 归一化：\/ -> /，\u0026 -> &（字符串替换对反斜杠翻倍免疫）
            norm = v.replace('\\/', '/').replace('\\u0026', '&')
            mo = re.search(r'[?&]origin=([^&]+)[&]url=([0-9a-f]{20,32})', norm)
            if not mo:
                continue
            if not line_name:
                line_name = unquote(mo.group(1))
            tokens.append(mo.group(2))
        if not tokens:
            return None
        return (line_name, tokens)

    # ============================================================
    # 播放解析（跨域 CDN m3u8）
    # ============================================================
    def _resolve_play(self, master_url):
        """将 dyrshd master 入口解析为 box.dyrs.com.de 真实媒体 m3u8 直链

        速度优化：master 入口经 dyrshd 302 中转实测 10~20s（超时即失败），
        而直连 box.dyrs.com.de/api/super 仅约 1s。因此先解析入口里的
        token 直连媒体域；失败再走原 302 链路兜底。
        """
        cached = self._cache_get(self._play_cache, master_url, TTL_PLAY)
        if cached:
            return cached

        real = ''
        # 快速路径：从入口 URL 提取 token/origin，直连 box super 接口
        try:
            mtok = re.search(r'[?&]url=([0-9a-f]{20,32})', master_url)
            morg = re.search(r'[?&]origin=([^&]+)', master_url)
            if mtok:
                tok = mtok.group(1)
                origin = unquote(morg.group(1)) if morg else ''
                super_url = "{0}/api/super?id={1}&origin={2}".format(
                    MEDIA_HOST, tok, quote(origin))
                r = self._get(super_url, referer=HOST + '/', timeout=TIMEOUT_PLAY)
                if r:
                    txt = r.text
                    m = re.search(r'/api/m3u8\?id=([0-9a-f]{20,32})', txt)
                    if m:
                        real = "{0}/api/m3u8?id={1}".format(MEDIA_HOST, m.group(1))
                    elif '#EXTINF' in txt:
                        # 已经是媒体列表
                        real = super_url
        except Exception:
            real = ''

        # 兜底路径：原 dyrshd 302 链路
        if not real:
            try:
                r = self._get(master_url, referer=HOST + '/', timeout=TIMEOUT_PLAY)
                if not r:
                    return None
                txt = r.text
                m = re.search(r'/api/m3u8\?id=([0-9a-f]{20,32})', txt)
                if m:
                    real = "{0}/api/m3u8?id={1}".format(MEDIA_HOST, m.group(1))
                elif '#EXTINF' in txt:
                    # 已经是媒体列表
                    real = master_url
            except Exception:
                real = ''

        if real:
            self._cache_set(self._play_cache, master_url, real, TTL_PLAY)
        return real

    def _play_payload(self, playurl):
        """组装直连播放结果（parse=0 秒开）"""
        is_m3u8 = '.m3u8' in playurl.lower()
        return {
            "parse": 0,
            "playUrl": "",
            "url": playurl,
            "header": {
                "User-Agent": UA,
                "Referer": HOST + "/",
                "Origin": HOST,
            },
            "format": "application/x-mpegURL" if is_m3u8 else "",
            "contentType": "application/x-mpegURL" if is_m3u8 else "",
        }

    def playerContent(self, flag, id, vipFlags):
        """解析播放页 -> 真实 m3u8 直链（跨域 CDN，带防盗链 Referer）

        - 模板A：id 为 dyrshd.com/api/m3u8?origin=&url= 入口，需 _resolve_play
          跟随 302 到 box.dyrs.com.de 真实媒体直链。
        - 模板B：id 为直链 CDN m3u8（vodcnd*.uvjtih.cn 等），直接返回，
          由 _play_payload 带上 Referer: dyrshd.com/ 满足防盗链。
        """
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}

        playurl = self._abs(str(id))

        # 模板A：站方 /api/m3u8?origin=&url= 入口 -> 解析到真实 CDN 媒体直链。
        # 判断用入口路径结构（origin/url 参数）而非写死域名，兼容域名跟踪切换。
        if '/api/m3u8' in playurl and 'origin=' in playurl and 'url=' in playurl:
            cached = self._cache_get(self._play_cache, playurl, TTL_PLAY)
            if cached:
                return self._play_payload(cached)
            m3u8 = self._resolve_play(playurl)
            if m3u8:
                return self._play_payload(m3u8)

        # 模板B：直链 CDN m3u8，直接返回（带 Referer 防盗链）
        return self._play_payload(playurl)

    # ============================================================
    # 搜索
    # ============================================================
    def searchContent(self, keyword, quick=False, pg=1):
        kw = (keyword or '').strip()
        if not kw:
            return {"list": [], "msg": "请输入搜索关键词"}

        page = int(pg or 1)
        ckey = "{0}|{1}".format(page, kw)
        cached = self._cache_get(self._search_cache, ckey, TTL_SEARCH)
        if cached is not None:
            return cached

        # 搜索接口：/s.html?name=关键词（真实接口；/search.html?wd= 只返回推荐，
        # 不会返回搜索结果）。该接口带 SHA1 工作量证明反爬，_get 已自动处理。
        url = "{0}/s.html?name={1}".format(HOST, quote(kw))
        if page > 1:
            url += "&page={0}".format(page - 1)

        try:
            html = self._get_text(url)
            vod_list = self._parse_cards(html, limit=36)
            # 无结果时页面 image-grid 会塞「推荐内容」而非搜索结果：
            # 若没有一个卡片标题命中关键词，判定为无结果，返回空列表。
            if vod_list:
                kwl = kw.lower()
                hit = any(kwl in (str(v.get('vod_name') or '').lower())
                          for v in vod_list)
                if not hit:
                    vod_list = []
        except Exception:
            vod_list = []

        result = {"list": vod_list}
        self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
        return result

    # ============================================================
    # 本地代理 & 清理
    # ============================================================
    def localProxy(self, param):
        # 本源所有播放均走 parse=0 直链（playerContent 已返回真实 m3u8 直链，
        # 且已带 Referer 头满足 box.dyrs.com.de 防盗链），TVBox 不会回调此处。
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def close(self):
        self.destroy()


# ============================================================
# 本地测试
# ============================================================
if __name__ == '__main__':
    import sys

    s = Spider()
    action = sys.argv[1] if len(sys.argv) > 1 else 'home'
    if action == 'home':
        print(json.dumps(s.homeContent(), ensure_ascii=False)[:800])
    elif action == 'category':
        tid = sys.argv[2] if len(sys.argv) > 2 else 'dianying'
        pg = sys.argv[3] if len(sys.argv) > 3 else '1'
        cl = sys.argv[4] if len(sys.argv) > 4 else ''
        ext = {'class': cl} if cl else {}
        print(json.dumps(
            s.categoryContent(tid, pg, False, ext), ensure_ascii=False)[:800])
    elif action == 'detail':
        vid = sys.argv[2] if len(sys.argv) > 2 else 'tv/6aa3fe769d8e33c8f1ce0ea8-65211'
        r = s.detailContent(vid)
        d = r['list'][0] if r.get('list') else {}
        print(json.dumps(d, ensure_ascii=False)[:800])
    elif action == 'play':
        pid = sys.argv[2] if len(sys.argv) > 2 else ''
        print(json.dumps(s.playerContent('', pid, []), ensure_ascii=False)[:500])
    elif action == 'search':
        kw = sys.argv[2] if len(sys.argv) > 2 else '古原'
        print(json.dumps(s.searchContent(kw), ensure_ascii=False)[:500])
