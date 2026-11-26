# 站点：https://cuptgr.com  （茶杯虎 · 热门影视在线观看；mzadycms + 自研 mizhiady 主题，非 MacCMS 官方模板）
# 路线：HTML 解析（主题卡片 = div.myui-vodbox-content），并辅以站内 JSON 接口 /index.php/ajax/data 取“最新”
#   实测 /index.php/ajax/data?mid=1&limit=30&page=1 → code=1 / total=11115 / 完整字段（含 vod_pic、vod_class）
#   但这套接口**只吃 page，不吃 tid / type_id / wd**（tid=1/2/3 首条恒为 1750《蜘蛛侠：崭新之日》），
#   所以分类/搜索一律走 HTML，JSON 只用于首页“最新入库”。
# 生成：2026-11-24   作者：Doubao
# 依赖：requests + base.spider；json / re / time / urllib 为标准库，无 lxml / bs4 / Crypto
# 接口：homeContent / homeVideoContent / categoryContent / detailContent / searchContent / playerContent / localProxy
# vod_id 协议：纯数字（"1100"）；播放 id 存站内相对路径 "/play/1100-1-1.html"（同站 sid 会变，不重拼）
# 分页来源：**分类页站点侧就没有第 2 页**（见下），所以 pagecount=1（站点真值，合法来源①的“1 页”结论），
#   不是满页推算；搜索页同理（?page=2 实测 0 卡片）。绝不填 99/999 骗壳端翻空页。
# 关键站点事实（全部实测）：
#   ① 分类页 /show/{tid}-----------.html 每类 24 张卡；/show/2-----------2.html、-----------3.html、
#      /type/2-2.html、/type/2.html?page=2、加 cb 破缓存 —— 五种写法返回的**主列表 id 完全一致**，
#      说明这个 CMS 的类型页只吐第一页 24 条，站内也没有“下一页”控件（页面里连分页 DOM 都没有）。
#   ② 因此详情里那 24 条之外的内容只能靠搜索；搜索 /search/{kw}-------------.html 单页有效（仙逆 → 3 条）。
#   ③ 详情页把多线路拆成 <div id="playlistN"> 面板，线路名是两字母代号（QY/YK/TX/BL/CZ），
#      必须先按 sid 分组再翻成人话，否则壳端线路栏就是一排字母。
#   ④ 播放地址不在详情页，必须点进 /play/{vid}-{sid}-{nid}.html 才能拿到 player_aaaa（含 url/from）。
#   ⑤ 本站**没有发布页/备用域名告示**（页脚只有统计脚本和 baidu 外链，maccms 变量里 url 就是 www.cuptgr.com），
#      换域走 TLD 变体候选 + 站点指纹双判，见 _sync_domains。

import json
import random
import re
import time
import urllib.parse

import requests

from base.spider import Spider


class Spider(Spider):
    # 主域：实测 200 / 299707B，title=茶杯虎 - 热门影视在线观看，Server: nginx（无 CF、无盾、无 cookie 关卡）
    HOST = 'https://cuptgr.com'
    # 域池：裸域与 www 都是同一站（裸域 301 到 www），两条都留着当兜底
    DOMS = ['https://cuptgr.com', 'https://www.cuptgr.com']
    # 候选域：同 TLD 变体猜测清单。本站没有公布备用域，所以一律不直接入池，
    # 必须过 _ok_site 指纹双判（标题含“茶杯虎” + 有 /detail/ 卡片），否则 parked 页会被当成镜像。
    # 2026-11-24 实测：net/cc/vip/top 四个全部 TCP/TLS 连接失败（没有同站镜像），
    # 也就是说此刻“换域”唯一可用的手段是用户自己塞新域，这份清单只在站点换 TLD 时才有用
    CAND = ['https://cuptgr.net', 'https://cuptgr.cc', 'https://cuptgr.vip', 'https://cuptgr.top',
            'https://cuptgr.xyz', 'https://cuptgr.io', 'https://cuptgr.site', 'https://cuptgr.club']
    # 分类：导航 tab_item 实测四项 —— 电影(/type/1) 连续剧(/type/2) 综艺(/type/3) 动漫(/type/4)，
    # 与详情页 tag 的 /show/1---动作--------.html 前缀对得上，所以 type_id 就是 1~4
    CLASSES = [('1', '电影'), ('2', '连续剧'), ('3', '综艺'), ('4', '动漫')]
    # 线路代号 → 中文：详情页 tab 里是两字母（QY/YK/TX/BL/CZ…），不翻就是给用户看字母；
    # 未收录的原样保留，不丢线路
    LINE_NAME = {
        'QY': '爱奇艺官采', 'YK': '优酷官采', 'TX': '腾讯官采', 'BL': '哔哩哔哩官采',
        'MG': '芒果官采', 'IQ': '爱奇艺官采', 'CQ': 'CQ资源', 'CZ': 'CZ资源',
        'HQ': 'HQ资源', 'PP': 'PP资源', 'WJ': '无极资源', 'ZX': '自建线路',
    }
    # 官方平台域：这些地址是平台网页，只能 parse:1；采集 CDN 的 m3u8/mp4 才允许 parse:0
    OFFICIAL = ('iqiyi.com', 'v.qq.com', 'youku.com', 'mgtv.com', 'bilibili.com',
                'le.com', 'sohu.com', 'miguvideo.com')
    # 每页 24：站点主列表容器 div.myui-vodbox-content 实测每页 24 个（type1/type2/show p2 三份样本都是 24）
    PAGE = 24
    # 单条播放串上限：壳端 2048B 截断，留 148B 给线路名与 (1)(2) 后缀 → 1900。
    # 26 集 × 5 线路时单线约 1.6KB 不该切，但 100 集以上的剧集必爆，所以统一按字节切段
    SEG = 1900
    # HTML 缓存 180s：分类页 24 条会被壳端反复取（首屏+换页），站点对连击没有限流但也有统计脚本，
    # 缓存能省一半请求；详情页只缓存短时，避免用户点进点出重复打站
    TTL = 180
    # 域级冷却 30s：整域拿不到合法 HTML 才写；单条 404/500 不冷整域
    COOL = 30
    # 换域探测上限：一次同步最多验 3 个候选域，池上限 8（门禁要求）
    MAXB = 3
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    # 直链门禁：只有确实返回 #EXTM3U 的地址才允许标 parse:0。
    # 本站 p1.czzyplay.com 是站长自建图床、svip.czzyplay.com 是采集 CDN，两者都靠后缀判不够稳，
    # 所以遇到“没写明 .m3u8 但路径里带 m3u8”的地址时真去取 512 字节验一遍（不认头就不给 parse:0）
    MEDIA_SIG = '#EXTM3U'
    # 类属性缓存：壳端每次调用新建实例，写 self._x 会让每次进首页重打一次；必须类属性 + init 只 setdefault
    _POOL = []
    _BAD = {}
    _CACHE = {}
    _SYNC = 0.0
    _PLAY = {}

    # 源名：壳端源列表显示用
    def getName(self):
        return '茶杯虎'

    # 初始化：建 session 绑类缓存；不重置任何缓存（重置=每集重打详情/播放页）
    def init(self, extend=''):
        self.extend = extend or ''
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        type(self)._POOL = type(self)._POOL or list(self.DOMS)
        for t in ('_BAD', '_CACHE', '_PLAY'):
            getattr(type(self), t).setdefault('_t', 0)
        # 站点无发布页，唯一人工自救入口是让用户把新域塞进来：
        # extend 支持 {"domain": "https://xxx"} 或直接传 URL 字符串
        manual = ''
        if isinstance(self.extend, dict):
            manual = str(self.extend.get('domain') or self.extend.get('host') or '')
        if not manual and str(self.extend or '').startswith('http'):
            manual = str(self.extend)
        if manual.startswith('http'):
            h = manual.rstrip('/')
            if h not in type(self)._POOL:
                type(self)._POOL.insert(0, h)
        self.base = type(self)._POOL[0]

    # ── 基础工具 ────────────────────────────────────────────────

    # 请求间隔：站方挂了访问统计（aizhantj）且分类页无缓存，1.0~1.4s 抖动既稳又不触发风控
    def _gap(self):
        time.sleep(random.uniform(1.0, 1.4))

    # 站点请求头：Referer 必须指向当前域；换域后仍用主域 Referer 会被判盗链（部分 nginx 规则直接 403）
    def _bh(self, referer=None):
        return {
            'User-Agent': self.UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': referer or (self.base + '/'),
        }

    # 域级冷却
    def _mark(self, host):
        type(self)._BAD[host] = time.time() + self.COOL

    # 选可用域：先给未冷却的池成员，全冷却就同步候选，再不行清冷却重来
    def _pick_host(self):
        pool = type(self)._POOL or list(self.DOMS)
        now = time.time()
        for h in pool:
            if float(type(self)._BAD.get(h, 0) or 0) < now:
                return h
        self._sync_domains()
        for h in (type(self)._POOL or list(self.DOMS)):
            if float(type(self)._BAD.get(h, 0) or 0) < now:
                return h
        type(self)._BAD.clear()
        return pool[0]

    # 站点指纹双判：标题必须含“茶杯虎”，页面必须有 /detail/ 卡片，且字符量 > 30KB。
    # 只判 200 会把同 TLD 的停放页/推广页当镜像（yunbo.top 那类坑），指纹是唯一便宜又靠谱的判别手段
    def _ok_site(self, host):
        try:
            r = self.session.get(host + '/', headers=self._bh(host + '/'), timeout=(8, 18),
                                 proxies=self.session.proxies or None)
            if r.status_code != 200 or len(r.content) < 30000:
                return False
            txt = r.content.decode('utf-8', 'replace')
            return '茶杯虎' in txt and len(re.findall(r'/detail/\d+\.html', txt)) >= 10
        except Exception:
            return False

    # 域同步：本站无发布页，只能 TLD 变体 + 指纹。30 分钟一次、最多验 MAXB 个、池上限 8
    def _sync_domains(self):
        if time.time() - float(type(self)._SYNC or 0) < 1800:
            return
        type(self)._SYNC = time.time()
        tried = 0
        for h in self.CAND:
            if tried >= self.MAXB or len(type(self)._POOL) >= 8:
                break
            if h in type(self)._POOL:
                continue
            tried += 1
            if self._ok_site(h):
                type(self)._POOL.append(h)

    # 取页：带冷却跳域 + 失败换域重试一次；返回 HTML 文本，失败返回 ''
    def _get(self, path, ttl=None, referer=None):
        key = 'h|' + path
        hit = type(self)._CACHE.get(key)
        if hit and time.time() < hit[0]:
            return hit[1]
        html = ''
        for _ in range(2):
            host = urllib.parse.urlparse(self.base).scheme + '://' + \
                (urllib.parse.urlparse(self.base).hostname or '')
            if float(type(self)._BAD.get(host, 0) or 0) > time.time():
                nb = self._pick_host()
                if nb != self.base:
                    self.base = nb
                continue
            try:
                self._gap()
                r = self.session.get(self.base + path,
                                     headers=self._bh(referer), timeout=(8, 22),
                                     proxies=self.session.proxies or None)
                if r.status_code == 200 and len(r.content) > 2000:
                    html = r.content.decode('utf-8', 'replace')
                    break
                # 200 但内容过小（跳转壳页/错误页）也按失败处理，避免把空壳交给解析器
                if r.status_code >= 500 or r.status_code == 403:
                    self._mark(host)
            except Exception:
                self._mark(host)
            nb = self._pick_host()
            if nb and nb != self.base:
                self.base = nb
        if html:
            ttl = self.TTL if ttl is None else ttl
            if ttl:
                type(self)._CACHE[key] = (time.time() + ttl, html)
        return html

    # 站内 JSON 接口（只用于“最新入库”，它不认 tid/type_id/wd，别拿它做分类和搜索）
    def _feed(self, pg=1, limit=30):
        key = 'j|%s|%s' % (pg, limit)
        hit = type(self)._CACHE.get(key)
        if hit and time.time() < hit[0]:
            return hit[1]
        data = {}
        for _ in range(2):
            try:
                self._gap()
                r = self.session.get(self.base + '/index.php/ajax/data',
                                     params={'mid': 1, 'page': pg, 'limit': limit},
                                     headers=self._bh(), timeout=(8, 20),
                                     proxies=self.session.proxies or None)
                data = json.loads(r.content.decode('utf-8', 'replace'))
            except Exception:
                data = {}
            if isinstance(data, dict) and data.get('list'):
                break
            host = urllib.parse.urlparse(self.base).hostname or ''
            self._mark('https://' + host)
            nb = self._pick_host()
            if nb and nb != self.base:
                self.base = nb
        if isinstance(data, dict) and data.get('list'):
            type(self)._CACHE[key] = (time.time() + self.TTL, data)
            return data
        return {}

    # 去标签 + 实体：站内简介是富文本，直接给壳端会显示 <p>&nbsp; 拼接
    def _clean(self, s):
        s = re.sub(r'(?is)<[^>]+>', ' ', s or '')
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
        s = s.replace('&lt;', '<').replace('&gt;', '>').replace('&#39;', "'")
        return re.sub(r'\s+', ' ', s).strip()

    # ── 卡片解析（主题自研，按 class 前缀切，三种兜底都留着）────────

    # 列表卡片：div.myui-vodbox-content 为一卡一块（type1/type2/search/home 四份样本均为同一结构）。
    # 兜底链：class 前缀切块 → aria/alt 文本 → 详情链接正则，避免主题改版后整页 0 条
    def _cards(self, html):
        out, seen = [], set()
        blocks = re.split(r'<div class="myui-vodbox-content">', html)[1:]
        if not blocks:
            # 兜底：主题换 class，就按 /detail/ 链接周围取标题与封面
            blocks = re.findall(r'(?is)(<a href="/detail/\d+\.html">.{0,1200}?</div>\s*</div>)', html)
        for b in blocks:
            mid = re.search(r'/detail/(\d+)\.html', b)
            if not mid:
                continue
            vid = mid.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            name = ''
            for pat in (r'<div class="title">([^<]+)</div>', r'alt="([^"]+)"',
                        r'<div class="info-title-box">\s*<div class="title">([^<]+)'):
                m = re.search(pat, b)
                if m and m.group(1).strip():
                    name = self._clean(m.group(1))
                    break
            pic = ''
            for pat in (r'<img[^>]+src="(https?://[^"]+)"', r'data-original="(https?://[^"]+)"'):
                m = re.search(pat, b)
                if m:
                    pic = m.group(1)
                    break
            remark = ''
            m = re.search(r'<div class="tag text-overflow">([^<]+)</div>', b)
            if m:
                remark = self._clean(m.group(1))
            year = ''
            m = re.search(r'(?:更新|上映)[^<]{0,6}[:：]?\s*(\d{4})', b)
            if m:
                year = m.group(1)
            out.append({
                'vod_id': vid,
                'vod_name': name or ('影片%s' % vid),
                'vod_pic': pic,
                'vod_remarks': remark,
                'vod_year': year,
                'vod_area': '',
                'vod_type': '',
            })
        return out

    # JSON feed 条目 → 卡片：字段比 HTML 全（有 vod_pic/vod_class/vod_year/vod_area），
    # 首页“最新”用它，一次请求 30 条完整卡片，比解 54 个 HTML 卡片块还便宜
    def _row(self, it):
        return {
            'vod_id': str(it.get('vod_id') or ''),
            'vod_name': self._clean(it.get('vod_name') or ''),
            'vod_pic': it.get('vod_pic') or '',
            'vod_remarks': self._clean(it.get('vod_remarks') or ''),
            'vod_year': str(it.get('vod_year') or '')[:4],
            'vod_area': self._clean(it.get('vod_area') or ''),
            'vod_type': self._clean(it.get('vod_class') or it.get('type') or ''),
        }

    # ── 六接口 ─────────────────────────────────────────────────

    # 首页：4 个真实分类 + 首屏卡片（解首页 HTML 的 54 张卡，按出现顺序去重取 30 条）。
    # 分页来源：无（首页固定 1 页）。解析失败时回退到 JSON feed，保证 class/list 永不为空
    def homeContent(self, filter):
        html = self._get('/', ttl=self.TTL)
        cards = self._cards(html) if html else []
        if not cards:
            feed = self._feed(1, 30)
            cards = [self._row(i) for i in (feed.get('list') or [])]
        cls = [{'type_id': t, 'type_name': n} for t, n in self.CLASSES]
        return {'class': cls, 'filters': {}, 'list': cards[:30]}

    # 推荐位：走 JSON feed 第一页（total=11115 / limit 30，字段齐全），
    # 与 homeContent 不共用缓存 key，所以壳端首屏会打两次站 —— 首页 HTML 必解、feed 又必须调，
    # 这里刻意只用 feed 30 条，避免再解一遍 300KB HTML
    def homeVideoContent(self):
        feed = self._feed(1, 30)
        return {'list': [self._row(i) for i in (feed.get('list') or [])][:30]}

    # 分类：/show/{tid}-----------.html 只有 24 条且**没有第 2 页**（五种页码写法实测 id 一致）。
    # 所以 pagecount=1（站点真值结论），pg>1 直接返空 —— 不 duplicates 第一页，也不编造更大页数
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '').strip() or self.CLASSES[0][0]
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        if pg > 1:
            # 站点第 2 页与第 1 页同内容，返空比返重复更诚实（壳端 pagecount=1 时也不会真翻到第 2 页）
            return {'page': pg, 'pagecount': 1, 'limit': self.PAGE, 'total': 0, 'list': []}
        html = self._get('/show/%s-----------.html' % tid)
        cards = self._cards(html)
        return {'page': 1, 'pagecount': 1, 'limit': self.PAGE,
                'total': len(cards), 'list': cards[:self.PAGE]}

    # 详情：/detail/{id}.html。多线路在 <div id="playlistN"> 面板里，线路名在 <a href="#playlistN"> 上。
    # 播放地址不在详情页，必须点进 /play/... 由 playerContent 现取（见 _play）
    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        mid = re.search(r'(\d+)', str(raw) or '')
        if not mid:
            return {'list': []}
        vid = mid.group(1)
        html = self._get('/detail/%s.html' % vid)
        if not html:
            return {'list': []}
        name = ''
        m = re.search(r'<h1 class="title">([^<]+)</h1>', html)
        if m:
            name = self._clean(m.group(1))
        pic = ''
        m = re.search(r'data-original="(https?://[^"]+)"', html) or \
            re.search(r'<div class="mask-img"[^>]*style="[^"]*url\((https?://[^)]+)\)', html)
        if m:
            pic = m.group(1)
        # 类型标签：详情页 tag 链接指向 /show/{tid}---{题材}---，全抓下来当题材
        tags = re.findall(r'<a class="tag" href="/show/[^"]*">([^<]+)</a>', html)
        tipos = ' / '.join([self._clean(t) for t in tags if self._clean(t)][:3])
        remark = ''
        m = re.search(r'<div class="tag text-overflow">([^<]+)</div>', html)
        if m:
            remark = self._clean(m.group(1))
        year = ''
        m = re.search(r'上映时间[^0-9]{0,80}?(\d{4})(?:-\d{2}-\d{2})?', html, re.S) or \
            re.search(r'(\d{4})-\d{2}-\d{2}', html)
        if m:
            year = m.group(1)
        area, lang = '', ''
        m = re.search(r'([\u4e00-\u9fa5]{2,10})\s*</div>\s*<div class="name">地区</div>', html)
        if m:
            area = self._clean(m.group(1))
        m = re.search(r'([\u4e00-\u9fa5]{2,10})\s*</div>\s*<div class="name">语言</div>', html)
        if m:
            lang = self._clean(m.group(1))
        content = ''
        m = re.search(r'(?is)<div class="intro">(.*?)</div>\s*</div>', html)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = re.search(r'(?is)<div class="wrapper_more[^>]*>(.*?)</div>\s*</div>', html)
            if m:
                content = self._clean(m.group(1))
        # 线路分组：id="playlistN" 每个面板一条线路，面板内的 /play/vid-sid-nid.html 才是该线集数
        sids, eps_of = [], {}
        for m in re.finditer(r'(?is)id="playlist(\d+)"[^>]*>(.*?)(?=id="playlist\d+"|</div>\s*</div>\s*</div>\s*</div>)',
                             html):
            sid = m.group(1)
            body = m.group(2)
            eps = []
            for a in re.finditer(r'<a href="/play/%s-%s-(\d+)\.html"[^>]*>([^<]*)</a>'
                                 % (re.escape(vid), re.escape(sid)), body):
                nid = a.group(1)
                label = self._clean(a.group(2)) or ('第%d集' % (len(eps) + 1))
                eps.append((label, '/play/%s-%s-%s.html' % (vid, sid, nid)))
            if eps:
                sids.append(sid)
                eps_of[sid] = eps
        if not sids:
            # 兜底：整页抓 /play/vid-*-*，至少不让详情空着（电影只有 1 条时也能出线）
            allp = re.findall(r'href="(/play/%s-(\d+)-(\d+)\.html)"' % re.escape(vid), html)
            for path, sid, nid in allp:
                eps_of.setdefault(sid, []).append(('第%d集' % (len(eps_of.get(sid, [])) + 1), path))
                if sid not in sids:
                    sids.append(sid)
        # 线路名：tab 头 <a href="#playlistN">QY</a>，代号翻中文；同名去重加序号
        names, used = [], set()
        for sid in sids:
            code = ''
            m = re.search(r'<a href="#playlist%s"[^>]*>([^<]+)</a>' % re.escape(sid), html)
            if m:
                code = self._clean(m.group(1)).upper()
            nm = self.LINE_NAME[code] if code in self.LINE_NAME else (code or ('线路%s' % sid))
            if nm in used:
                k = 2
                while '%s%d' % (nm, k) in used:
                    k += 1
                nm = '%s%d' % (nm, k)
            used.add(nm)
            names.append(nm)
        # 分段：按字节切，段名「线路名(1)(2)」；froms 与 urls 段数必须相等，所以同一循环里成对 append
        seg_froms, seg_urls = [], []
        for idx, sid in enumerate(sids):
            base_nm = names[idx]
            part, seg, cur = 0, [], 0
            for label, path in (eps_of[sid] if sid in eps_of else []):
                if len(label) > 16:
                    label = label[:16]
                need = len(('%s$%s' % (label, path)).encode('utf-8')) + 1
                if seg and cur + need > self.SEG:
                    part += 1
                    seg_froms.append(base_nm if part == 1 else '%s(%d)' % (base_nm, part))
                    seg_urls.append('#'.join('%s$%s' % (a, b) for a, b in seg))
                    seg, cur = [], 0
                seg.append((label, path))
                cur += need
            if seg:
                part += 1
                seg_froms.append(base_nm if part == 1 else '%s(%d)' % (base_nm, part))
                seg_urls.append('#'.join('%s$%s' % (a, b) for a, b in seg))
        vod = {
            'vod_id': vid,
            'vod_name': name or ('影片%s' % vid),
            'vod_pic': pic,
            'vod_remarks': remark,
            'vod_year': year,
            'vod_area': area,
            'vod_type': tipos,
            'vod_lang': lang,
            'vod_content': content,
            'vod_play_from': '$$$'.join(seg_froms),
            'vod_play_url': '$$$'.join(seg_urls),
        }
        return {'list': [vod]}

    # 搜索：/search/{kw}-------------.html（MacCMS 风路径，但本站搜索只有 1 页，?page=2 实测 0 卡）。
    # 分页来源：站点真值 1 页；total 取本页卡片数
    def searchContent(self, key, quick, pg='1'):
        kw = (key or '').strip()
        if not kw:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': self.PAGE, 'total': 0}
        try:
            p = max(1, int(pg))
        except Exception:
            p = 1
        if p > 1:
            # 站点搜索第 2 页就是空页（实测 0 卡），照实返空；pagecount 仍报 1，壳端不会白翻
            return {'list': [], 'page': p, 'pagecount': 1, 'limit': self.PAGE, 'total': 0}
        html = self._get('/search/%s-------------.html' % urllib.parse.quote(kw, safe=''))
        cards = self._cards(html)
        if str(quick) in ('1', 'True', 'true') and len(cards) > 12:
            cards = cards[:12]
        return {'list': cards[:self.PAGE], 'page': 1, 'pagecount': 1,
                'limit': self.PAGE, 'total': len(cards)}

    # 播放取址：pid 是站内相对路径 /play/{vid}-{sid}-{nid}.html，必须现取页面里的 player_aaaa：
    #   {"url":"https://svip.czzyplay.com/…/index.m3u8","from":"changzhangm3u8","sid":1,"nid":1}
    # 直链 m3u8/mp4 → parse:0（只给 UA，带站点 Referer 会被采集 CDN 判盗链）；
    # 官方平台页 → parse:1 + 平台 Referer。取不到 url 时降级为 parse:1 交壳端打开播放页，绝不假装直链
    def _play(self, pid):
        hit = type(self)._PLAY.get(pid)
        if hit and time.time() < hit[0]:
            return hit[1]
        html = self._get(pid, ttl=0, referer=self.base + '/')
        if not html:
            return {}
        m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        data = {}
        if m:
            try:
                data = json.loads(m.group(1))
            except Exception:
                data = {}
        if data:
            type(self)._PLAY[pid] = (time.time() + 600, data)
        return data

    # 播放接口：入参可能是 /play/xxx.html 或整条 "集名$/play/xxx.html"，统一剥掉集名
    def playerContent(self, flag, id, vipFlags):
        pid = str(id or '').split('#')[0].rsplit('$', 1)[-1].strip()
        if not pid:
            return {'parse': 1, 'url': ''}
        if not pid.startswith('/'):
            if pid.startswith('http'):
                # 已经是绝对地址：按媒体/官方页二分
                return self._route(pid)
            pid = '/' + pid
        data = self._play(pid)
        url = str(data.get('url') or '').strip()
        if url.startswith('http'):
            return self._route(url)
        # 站点给了多段地址（url 为空但 url_next 有值）：走第一段有效地址
        alt = str(data.get('url_next') or '').strip()
        if alt.startswith('http'):
            return self._route(alt)
        # 兜底：把播放页交给壳端（parse:1 + 站内 Referer），比返回空 url 强
        return {'parse': 1, 'url': self.base + pid,
                'header': {'User-Agent': self.UA, 'Referer': self.base + '/'}}

    # 直链抽验：只读前 512B 看有没有 #EXTM3U。带站点 Referer 会被采集 CDN 判盗链，所以只给 UA
    def _is_media(self, url):
        try:
            r = self.session.get(url, headers={'User-Agent': self.UA}, timeout=(6, 12),
                                 proxies=self.session.proxies or None)
            head = (r.content or b'')[:512].decode('utf-8', 'replace')
            return r.status_code == 200 and self.MEDIA_SIG in head
        except Exception:
            return False

    # 地址分流：直链媒体 parse:0（只带 UA），官方平台页 parse:1（带平台 Referer）
    def _route(self, url):
        low = url.split('?')[0].lower()
        host = urllib.parse.urlparse(url).hostname or ''
        if low.endswith('.m3u8') or low.endswith('.mp4') or low.endswith('.flv'):
            return {'parse': 0, 'url': url, 'header': {'User-Agent': self.UA}}
        # 后缀缺失但路径/参数里带 m3u8（如 /play/xx/main/index）→ 先用 MEDIA_SIG 验一把，
        # 验过才是直链，验不过一律按页面交给壳端解析，绝不拿 HTML 播放页冒充直链
        if 'm3u8' in low and self._is_media(url):
            return {'parse': 0, 'url': url, 'header': {'User-Agent': self.UA}}
        if any(d in host for d in self.OFFICIAL):
            root = '.'.join(host.split('.')[-2:]) if host else ''
            return {'parse': 1, 'url': url,
                    'header': {'User-Agent': self.UA, 'Referer': 'https://%s/' % root}}
        return {'parse': 1, 'url': url,
                'header': {'User-Agent': self.UA, 'Referer': self.base + '/'}}

    # 图片代理：本站封面集中在 p1.czzyplay.com（站长自建图床）+ iqiyipic/hitv/ali 等第三方。
    # 铁律：不带站点 Referer（第三方图床会 403）；空 body 返 404，避免壳端显示 200 灰块
    def localProxy(self, param):
        u = urllib.parse.unquote(str(param or ''))
        if not u.startswith('http'):
            return [404, 'text/plain', b'']
        try:
            r = self.session.get(u, headers={'User-Agent': self.UA,
                                             'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8'},
                                 timeout=(6, 15), proxies=self.session.proxies or None)
            body = r.content or b''
            if not body:
                return [404, 'text/plain', b'']
            ctype = (r.headers.get('Content-Type') or 'image/jpeg').split(';')[0]
            # 图床常把 webp 写成 jpeg，按魔数纠正，壳端解码不报格式错
            if body[:4] == b'\x89PNG':
                ctype = 'image/png'
            elif body[:3] == b'\xff\xd8\xff':
                ctype = 'image/jpeg'
            elif body[:4] == b'RIFF' and body[8:12] == b'WEBP':
                ctype = 'image/webp'
            return [200, ctype, body]
        except Exception:
            return [404, 'text/plain', b'']
