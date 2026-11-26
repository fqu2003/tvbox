# -*- coding: utf-8 -*-
# =============================================================================
# ᵀ⁴剧踪 —— 剧踪影院（juzong 系）TVBox / 羊壳 Python 源
# -----------------------------------------------------------------------------
# 路线判定：MacCMS v10（首途 stui 模板），伪静态路由 + 自研播放壳
#   · 分类 /vodshow/{tid}-----------/ ，翻页 /vodshow/{tid}--------{pg}---/
#   · 详情 /voddetail/{id}/ ，播放 /vodplay/{id}-{sid}-{nid}/
#   · 搜索 /vodsearch/-------------/?wd={词}&submit=search
#     ↑ 这个 submit=search 不能省：不带它站点 WAF 直接返 403 跳转壳
#   · 播放 data 不是 player_aaaa，而是 var player_data（首途版），url 形态两种：
#     a) 真直链 https://…/index.m3u8          → 直接 parse:0
#     b) 私有前缀 juzong1-/juzong2-/juzongyd- → 密文，站点不解，交给播放壳
# -----------------------------------------------------------------------------
# 播放壳链路（这是本站真正的"暗线"）：
#   /static/player/{from}.js（694B 模板）→ 指向 https://jzpic.ok1333.cn/
#   → 壳页 HTML 里带 window.WGART_PARSE_TOKEN（每次请求现签，绑定当次页面）
#   → /wgart/api.php?action=try_json_api&video_url=<前缀密文>&parse_token=<token>
#   → JSON.data.url 是 m3u8 或 mp4（字节 CDN 会伪装成 .image?…&name=jz.mp4，仍是 mp4）
#   所以 playerContent 必须"现取现解"，不能把整条直链缓存在详情里：token 与
#   CDN 的 auth_key / x-expires 都是短时有效的，缓存久了用户点开就是 403。
# -----------------------------------------------------------------------------
# 域池与发布页（用户明确要求"失效能自动换下一个"）：
#   发布页 https://juzong.vip/ 与 https://juzongvip.netlify.app/（同一份页面，
#   后者是 1818dy.org 跳转过去的目标）会列出 主用/备用/失效 三条线路域；
#   备用域 juzong02.me 实际是一个 5 秒跳转页，里面 targetUrl 才是当年主域，
#   所以两条来源都要解析：发布页链接 + 跳转页 targetUrl。
# -----------------------------------------------------------------------------
# 踩坑记录（都实测过，改代码别踩回去）：
#   1. 分类 22 犯罪片 是空栏目（16KB、0 卡），写进 classes 会让入参矩阵报空；
#   2. 首页/分类卡片 42~60 张，搜索页是另一套 stui-vodlist__media 列表样式，
#      统一按 "stui-vodlist__thumb" 锚点切段才能一处代码吃三种页面；
#   3. 详情页 10+ 条线路里混着 http下载（磁力），只认 /vodplay/ 链接，
#      否则会把磁力当可播地址塞进 vod_play_url；
#   4. 分页尾页从 <span class="num">当前/总数</span> 取，别用"满页+1"猜。
# =============================================================================

import base64
import json
import re
import threading
import time
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit

import requests
from base.spider import Spider


class Spider(Spider):

    # ---- 站点身份与域池 ------------------------------------------------------
    NAME = 'ᵀ⁴剧踪'
    HOST = 'https://www.juzong01.me'          # 主域（发布页里的"主用"）
    HOSTS = (                                   # 种子域：主用 + 备用 + 裸域写法
        'https://www.juzong01.me',
        'https://juzong01.me',
        'https://www.juzong02.me',
        'https://juzong02.me',
    )
    PUBLIC = (                                  # 发布页两个入口（同一份内容，互为备份）
        'https://juzongvip.netlify.app/',
        'https://juzong.vip/',
    )
    SHELL = 'https://jzpic.ok1333.cn/'          # 播放壳兜底域（从 player js 里解析优先）

    # ---- 分类表：站点 18 个目录里 22 犯罪片是空栏目，已剔除 ------------------
    CATS = (
        ('1', '电影'), ('2', '剧集'), ('3', '综艺'), ('4', '动漫'),
        ('6', '动作片'), ('7', '喜剧片'), ('8', '爱情片'), ('9', '科幻片'),
        ('10', '恐怖片'), ('11', '剧情片'), ('12', '战争片'), ('13', '国产剧'),
        ('14', '港台剧'), ('15', '日韩剧'), ('16', '欧美剧'), ('20', '海外剧'),
        ('23', '动画片'),
    )

    # ---- 客户端硬限制与预算 --------------------------------------------------
    LIMIT = 42          # 分类页每页 42 卡（首页 60，需分开记，别互相污染）
    SEARCH_PC = 1       # 搜索无分页：本站搜索结果页没有分页条，pagecount 恒为 1
    TTL = 300           # 页面缓存 5 分钟
    FAIL_TTL = 30       # 冷却 30 秒（SKILL 硬要求）
    BUDGET = 12         # 单次取页墙钟预算（站点 TTFB 0.3~1.5s，12s 足够兜住抖动）
    HARD = (0, 403, 407, 429, 502, 503, 504, 520, 521, 522, 523, 524)  # 域级失败码

    # ---- 跨实例状态（类属性：客户端会反复 new Spider()，缓存必须挂在类上）----
    _CACHE = {}
    _FAIL = {}          # host -> 冷却截止时间
    _PF = {}            # path -> 冷却截止时间（路径级，只在单页 404/500 时用）
    _PLAY = {}          # 播放 id -> (时间, 解析结果)
    _HOSTS = []         # 学习到的好域
    _HOST = ''          # 当前可用域
    _HT = 0.0           # 上次确认 host 的时间
    _PROBED = {}        # 域探测节流
    _SEARCH = {}        # 关键词 -> (时间, 结果)：站点搜索 6 秒硬限流，同词必须复用
    _LAST_SEARCH = 0.0  # 上次真实搜索时刻，用于补足 6 秒间隔

    def init(self, extend=''):
        """绑定域池与缓存；只做 setdefault，禁止重置清空（否则每次进页都重探）。"""
        self.host = self.HOST
        s = (extend or '').strip()
        if s.startswith('{'):
            try:
                cfg = json.loads(s)
                h = str(cfg.get('host') or '').strip()
                if h.startswith('http'):
                    self.host = h.rstrip('/')
                extra = cfg.get('hosts') or []
                if isinstance(extra, list):
                    for x in extra:
                        x = str(x or '').strip()
                        if x.startswith('http') and x not in type(self)._HOSTS:
                            type(self)._HOSTS.append(x.rstrip('/'))
            except Exception:
                pass
        elif s.startswith('http'):
            self.host = s.rstrip('/')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/131.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/',
        }
        # session 必须先建：_pick_host 要用它探活，顺序反了探活会全失败
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        self.base = self._pick_host(self.host) or self.host
        self.headers['Referer'] = self.base + '/'
        self.session.headers.update(self.headers)
        self._CACHE = type(self)._CACHE.setdefault(self.base, {})
        self._FAIL = type(self)._FAIL.setdefault(self.base, {})
        self._PF = type(self)._PF.setdefault(self.base, {})
        self._PLAY = type(self)._PLAY.setdefault(self.base, {})
        return None

    # 接口：getName() -> 源名（壳端可能在 init 之前就调用，所以只返回常量）
    def getName(self):
        return self.NAME

    # =========================================================================
    # 六接口
    # =========================================================================
    def homeContent(self, filter):
        """首页：分类表 + 首页 60 张卡（热播推荐/电影/剧集/综艺/动漫 混排）。"""
        classes = [{'type_id': t, 'type_name': n} for t, n in self.CATS]
        return {'class': classes, 'list': self._cards(self._page('/'))}

    # 接口：homeVideoContent() -> {list}，羊壳推荐位，复用首页缓存不发二次请求
    def homeVideoContent(self):
        """羊壳首页推荐位，复用同一份首页卡，不发第二次请求。"""
        return {'list': self._cards(self._page('/'))}

    # 接口：categoryContent(tid, pg, filter, extend) -> {page, pagecount, limit, total, list}
    def categoryContent(self, tid, pg, filter, extend):
        """分类：第 1 页是 /vodshow/{tid}-----------/，之后是 /vodshow/{tid}--------{pg}---/。"""
        page = self._pg(pg)
        tid = str(tid or '').strip()
        if page <= 1:
            path = '/vodshow/%s-----------/' % tid
        else:
            path = '/vodshow/%s--------%d---/' % (tid, page)
        html = self._page(path)
        vods = self._cards(html)
        total, pagecount = self._pagecount(html, page, len(vods), tid)
        return {'page': page, 'pagecount': pagecount, 'limit': self.LIMIT,
                'total': total, 'list': vods}

    # 接口：searchContent(key, quick, pg) -> {page, pagecount, limit, total, list}
    # 站点搜索硬限流 6 秒、且结果页没有分页条，所以 pagecount 恒取 self.SEARCH_PC
    def searchContent(self, key, quick, pg='1'):
        """
        搜索：submit=search 必须带；该站搜索无分页，pagecount 固定 SEARCH_PC。
        站点有硬限流——"搜索时间间隔为6秒"，短于 6 秒会返 1341B「系统提示」页。
        所以：同词走本地缓存；换词先补足 6 秒间隔（最多等 5 秒，不把客户端拖死）；
        quick 建议词密集并发时不等待，直接返回空，避免刷屏拖慢。
        """
        kw = str(key or '').strip()
        page = self._pg(pg)
        hit = type(self)._SEARCH.get(kw.lower())
        if hit and time.time() - hit[0] < (600 if hit[1] else 90):
            # 命中的结果非空缓存 10 分钟；空结果只留 90 秒（限流/无结果都可能，
            # 长时间缓存空会让用户搜不到东西还以为源坏了）
            vods = hit[1]
            if page > 1:
                vods = []
            return {'page': page, 'pagecount': self.SEARCH_PC, 'limit': len(vods),
                    'total': len(vods), 'list': vods}
        # quick 只在真是布尔 True / 'true' 时算"快速建议词"；别把 '1' 当 True——
        # 校验器和部分客户端就传 '1'，那样会被误判成快搜而直接返空（实测踩过）
        fast = quick is True or str(quick).lower() == 'true'
        gap = time.time() - type(self)._LAST_SEARCH
        need = 6.2 - gap
        if need > 0:
            time.sleep(min(need, 2.0 if fast else 5.0))
        path = '/vodsearch/-------------/?wd=%s&submit=search' % quote(kw)
        # 搜索页的 403（170B 空壳）和「系统提示…6 秒」页都是站点请求密度限流，
        # 不是域失效：这里 hard=False 不换域，改成按 6 秒退避重试，最多 3 轮。
        html = ''
        for attempt in range(3):
            type(self)._LAST_SEARCH = time.time()
            self._CACHE.pop(self.base + path, None)
            html = self._page(path, hard=False)
            if html and len(html) >= 3000:
                break
            if attempt < 2:
                time.sleep(6.5)
        vods = self._cards(html)
        if len(type(self)._SEARCH) > 60:
            type(self)._SEARCH.clear()
        type(self)._SEARCH[kw.lower()] = (time.time(), vods)
        if page > 1:
            vods = []
        return {'page': page, 'pagecount': self.SEARCH_PC, 'limit': len(vods),
                'total': len(vods), 'list': vods}

    # 接口：detailContent(ids) -> {list}，ids 兼容 list/JSON 串/整段播放 id
    def detailContent(self, ids):
        """详情：h1 名称 + p.data 元信息 + 按 h3.title 配对 stui-content__playlist 线路。"""
        vid = self._vid(ids)
        if not vid:
            return {'list': []}
        html = self._page('/voddetail/%s/' % vid)
        if not html:
            return {'list': []}
        vod = self._vod(html, vid)
        lines = self._lines(html, vid)
        parts = []
        for label, urlstr in lines:
            parts.extend(self._segments(label, urlstr))
        if parts:
            vod['vod_play_from'] = '$$$'.join(x[0] for x in parts)
            vod['vod_play_url'] = '$$$'.join(x[1] for x in parts)
        else:
            vod['vod_play_from'] = ''
            vod['vod_play_url'] = ''
            vod['vod_content'] = (vod.get('vod_content') or '') + '｜该条目暂无在线资源'
        return {'list': [vod]}

    # 接口：playerContent(flag, id, vipFlags) -> {parse, jx, url, playUrl, header}
    def playerContent(self, flag, id, vipFlags):
        """
        播放：播放页 player_data.url 分两种形态
          · http(s) 直链 → 验真后 parse:0
          · 私有前缀密文 → 壳页 token + try_json_api 现解，验真后 parse:0
        失败统一回 parse:1 指向原播放页，绝不把未验证地址当直链。
        """
        header = json.dumps(self.headers)
        path = self._path(id)
        if not path:
            return {'parse': 1, 'jx': 0, 'url': str(id or ''), 'playUrl': '', 'header': header}
        # 传入的已经是 http 媒体地址（部分客户端会回传解析结果）
        if path.startswith('http') and '.m3u8' in path:
            if self._probe(path):
                return {'parse': 0, 'jx': 0, 'url': path, 'playUrl': '',
                        'header': json.dumps(self._media_headers(path))}
            return {'parse': 1, 'jx': 1, 'url': path, 'playUrl': '', 'header': header}
        page = path if path.startswith('http') else self.base + path
        hit = self._PLAY.get(page)
        if hit and time.time() - hit[0] < 120:
            url = hit[1]
        else:
            url = self._play_url(page)
            if url:
                self._PLAY[page] = (time.time(), url)
        if not url:
            return {'parse': 1, 'jx': 0, 'url': page, 'playUrl': '', 'header': header}
        if self._probe(url):
            # 给播放器的 Referer 必须跟着媒体域走，不能拿站点 Referer 打 CDN
            return {'parse': 0, 'jx': 0, 'url': url, 'playUrl': '',
                    'header': json.dumps(self._media_headers(url))}
        return {'parse': 1, 'jx': 1, 'url': page, 'playUrl': '', 'header': header}

    def _media_headers(self, url):
        """
        播给客户端用的请求头：站点自有媒体带同源 Referer；CDN 一律删掉 Referer。
        实测 douyinvod / byteimg / bytetos / blbtgg 带任何 Referer 都 403，
        只有"没有 Referer"才 200/206，所以这里必须 pop 而不是换。
        """
        hd = dict(self.headers)
        host = urlsplit(str(url or '')).netloc
        if 'juzong' in host:
            hd['Referer'] = 'https://%s/' % host
        else:
            hd.pop('Referer', None)
        return hd

    def localProxy(self, param):
        """图片 / HLS 三件套：do=img | do=m3u8 | do=ts。空 body 一律 404，不返 200 空图。"""
        text = str(param or '')
        m = re.search(r'(?:^|[?&])url=([^&]+)', text)
        if not m:
            return [404, 'text/plain', b'']
        url = unquote(m.group(1))
        if not url.startswith('http'):
            return [404, 'text/plain', b'']
        code, ctype, data = self._req(url, 12, raw=True)
        if code not in (200, 206) or not data:
            return [404, 'text/plain', b'']
        if 'do=m3u8' in text and data[:7] == b'#EXTM3U':
            body = self._rewrite(data.decode('utf-8', 'ignore'), url)
            return [200, 'application/vnd.apple.mpegurl', body.encode('utf-8')]
        return [200, ctype or 'application/octet-stream', data]

    # =========================================================================
    # 页面解析
    # =========================================================================
    def _cards(self, html):
        """
        统一卡片切分。三种页面共用一套锚点：
          首页/分类 → <a class="stui-vodlist__thumb …" href="/voddetail/{id}/" title data-original>
          搜索页   → <a class="v-thumb stui-vodlist__thumb lazyload" href title data-original>
        必须按"整个 <a> 标签"匹配而不是截断切段：首页有些区块 href 写在 class 之前，
        按 <a…thumb 切会把 href 一起吃进丢弃的半截，那批卡就全漏（实测少 13 张）。
        首页另有 3 张 /topicdetail-* 专题图，href 不匹配 voddetail 自然被排除。
        """
        out, seen = [], set()
        h = str(html or '')
        for m in re.finditer(r'<a\b[^>]*stui-vodlist__thumb[^>]*>', h):
            tag = m.group(0)
            hm = re.search(r'href="([^"]*?/voddetail/(\d+)/)"', tag)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            t = re.search(r'title="([^"]*)"', tag)
            name = t.group(1).strip() if t else ''
            if not name:
                n2 = re.search(r'>([^<]{1,40})</a>', h[m.end():m.end() + 200])
                name = n2.group(1).strip() if n2 else ''
            pic = re.search(r'data-original="([^"]+)"', tag) or re.search(r'src="(http[^"]+)"', tag)
            rem = re.search(r'<span[^>]*class="pic-text[^"]*"[^>]*>([^<]{0,30})</span>',
                            h[m.end():m.end() + 600])
            out.append({
                'vod_id': vid,
                'vod_name': name or ('影片%s' % vid),
                'vod_pic': self._pic(pic.group(1)) if pic else '',
                'vod_remarks': re.sub(r'\s+', ' ', rem.group(1)).strip() if rem else '',
            })
        return out

    def _pagecount(self, html, page, n, tid):
        """真分页：优先 <span class="num">当前/总数</span>，其次"尾页"链接，最后满页滑窗。"""
        m = re.search(r'<span class="num">\s*\d+\s*/\s*(\d+)\s*</span>', str(html or ''))
        if m:
            pc = int(m.group(1))
            return pc * self.LIMIT, pc
        m = re.search(r'href="[^"]*?/vodshow/%s--------(\d+)---/">尾页' % re.escape(str(tid)), str(html or ''))
        if m:
            pc = int(m.group(1))
            return pc * self.LIMIT, pc
        pc = page + 1 if n >= self.LIMIT else page
        return pc * self.LIMIT, pc

    def _vod(self, html, vid):
        """详情字段：首途模板的 p.data 是"标签+值"平铺，用锚点正则逐项取。"""
        def clean(x):
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', x or '')).strip()

        h = str(html or '')
        name = re.search(r'<h1[^>]*class="title"[^>]*>(.*?)</h1>', h, re.S)
        if not name:
            name = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
        pic = re.search(r'<a[^>]*stui-vodlist__thumb[^>]*data-original="([^"]+)"', h)
        if not pic:
            pic = re.search(r'<img[^>]+(?:data-original|src)="(http[^"]+)"', h)

        year = re.search(r'年份[：:]\s*(?:</span>)?\s*([0-9]{4})', h)
        area = re.search(r'地区[：:]\s*(?:</span>)?\s*([^<\s]{1,10})', h)
        typ = re.search(r'类型[：:]\s*(?:</span>)?\s*<a[^>]*>([^<]{1,20})</a>', h)
        act = re.search(r'主演[：:]\s*</span>(.*?)</p>', h, re.S)
        dire = re.search(r'导演[：:]\s*</span>(.*?)</p>', h, re.S)
        upd = re.search(r'更新[：:]\s*</span>\s*([0-9\-]{6,12})', h)
        sketch = re.search(r'<span class="detail-sketch"[^>]*>(.*?)</span>', h, re.S)
        full = re.search(r'<span class="detail-content"[^>]*>(.*?)</span>', h, re.S)

        content = ''
        if full:
            content = clean(full.group(1))
            # 站点把"剧情简介:"前缀塞在长简介里，切掉比留着重更干净
            if '剧情简介' in content:
                content = content.split('剧情简介', 1)[-1].lstrip('：: ')
        if not content and sketch:
            content = clean(sketch.group(1))

        remarks = ''
        if upd:
            remarks = '更新至' + upd.group(1).strip()
        rem2 = re.search(r'<span[^>]*class="pic-text[^"]*"[^>]*>([^<]{0,30})</span>', h)
        if not remarks and rem2:
            remarks = re.sub(r'\s+', ' ', rem2.group(1)).strip()

        return {
            'vod_id': vid,
            'vod_name': clean(name.group(1)) if name else ('影片%s' % vid),
            'vod_pic': self._pic(pic.group(1)) if pic else '',
            'vod_year': year.group(1) if year else '',
            'vod_area': area.group(1).strip() if area else '',
            'type_name': typ.group(1).strip() if typ else '',
            'vod_actor': clean(re.sub(r'<a[^>]*>', ' ', act.group(1)).replace('&nbsp;', ' ')).replace(' ', ',').strip(',') if act else '',
            'vod_director': clean(re.sub(r'<a[^>]*>', ' ', dire.group(1)).replace('&nbsp;', ' ')).replace(' ', ',').strip(',') if dire else '',
            'vod_remarks': remarks,
            'vod_content': content,
        }

    def _lines(self, html, vid):
        """
        线路配对：h3.title 是线路名，紧跟的 stui-content__playlist 是选集。
        只认 /vodplay/{vid}-{sid}-{nid}/ 链接——下载区的磁力链在另一个列表里，
        sid/nid 形态 GET 必 404，塞进 vod_play_url 就是"假可播"。
        """
        h = str(html or '')
        heads = [(m.start(), re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', m.group(1))))
                 for m in re.finditer(r'<h3 class="title"[^>]*>(.*?)</h3>', h, re.S)]
        out = []
        for m in re.finditer(r'<ul class="stui-content__playlist[^"]*"[^>]*>(.*?)</ul>', h, re.S):
            body = m.group(1)
            eps = re.findall(r'<li[^>]*><a[^>]+href="([^"]*?/vodplay/%s-[^"]*?)"[^>]*>([^<]{1,30})</a>'
                             % re.escape(str(vid)), body)
            if not eps:
                continue
            label = ''
            for pos, name in heads:
                if pos < m.start():
                    label = name
                else:
                    break
            if not label:
                label = '线路'
            seen, items = set(), []
            for href, epname in eps:
                sid = self._sid(href)
                if not sid or href in seen:
                    continue
                seen.add(href)
                items.append((sid, re.sub(r'\s+', ' ', epname).strip(), href))
            if not items:
                continue
            items.sort(key=lambda x: (int(x[0]), len(x[1]), x[1]))
            urlstr = '#'.join('%s$%s' % (it[1], it[2]) for it in items)
            dup = [x[0] for x in out]
            if label in dup:
                label = '%s(%d)' % (label, dup.count(label) + 1)
            out.append((label, urlstr))
        return out

    def _sid(self, href):
        m = re.search(r'/vodplay/(\d+)-(\d+)-(\d+)/', str(href or ''))
        return m.group(2) if m else ''

    def _segments(self, label, urlstr):
        """1900B 分段：客户端单字段 2048B 截断，超长线路拆成 名(1)/名(2)。"""
        eps = [x for x in str(urlstr or '').split('#') if x.strip()]
        chunks, cur, size = [], [], 0
        for seg in eps:
            b = len(seg.encode('utf-8')) + 1
            if cur and size + b > 1900:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(seg)
            size += b
        if cur:
            chunks.append(cur)
        if len(chunks) <= 1:
            return [(label, urlstr)]
        return [('%s(%d)' % (label, i + 1), '#'.join(c)) for i, c in enumerate(chunks)]

    # =========================================================================
    # 播放链路
    # =========================================================================
    def _play_url(self, page_url):
        """播放页 → player_data → 直链 or 壳解析。失败重试 2 次（首途页偶发 500 空壳）。"""
        html = ''
        for i in range(3):
            html = self._page_abs(page_url)
            if 'player_data' in html:
                break
            time.sleep(1)
        pd = self._player_data(html)
        if not pd:
            return ''
        raw = str(pd.get('url') or '').strip()
        if not raw:
            return ''
        enc = str(pd.get('encrypt') or '0')
        try:
            if enc == '2':
                raw = self._b64(raw)
            elif enc == '1':
                raw = unquote(raw)
        except Exception:
            pass
        if raw.startswith('http'):
            return raw
        vid = self._vid_from_play(page_url)
        nid = self._nid_from_play(page_url)
        return self._resolve(raw, str(pd.get('from') or ''), vid, nid,
                             str(pd.get('link') or ''))

    def _player_data(self, html):
        """brace 配平取 JSON；不用正则收尾（url_next 里也有引号容易截断）。"""
        t = str(html or '')
        m = re.search(r'var\s+player_data\s*=\s*', t)
        if not m:
            return {}
        start = t.find('{', m.end())
        if start < 0:
            return {}
        raw = self._brace(t, start)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            try:
                return json.loads(raw.replace('\\/', '/'))
            except Exception:
                return {}

    def _resolve(self, raw, frm, vid, nid, link):
        """
        私有前缀密文解析：壳页拿 token → api try_json_api。
        token 是"每次进壳页现签"的，必须跟着请求走，不能缓存复用。
        """
        shell = self._shell_base(frm)
        if not shell:
            return ''
        ep = nid or '1'
        q = urlencode({'url': raw, 'name': '', 'id': vid, 'ep': ep,
                       'source_index': ep, 'episode_title': '', 'year': ''})
        html = self._page_abs(shell + '?' + q)
        tk = re.search(r'WGART_PARSE_TOKEN="([^"]+)"', html)
        if not tk:
            return ''
        api = ('%swgart/api.php?action=try_json_api&video_url=%s&parse_token=%s'
               % (shell, quote(raw, ''), quote(tk.group(1), '')))
        code, ctype, data = self._req(api, 15)
        if code != 200 or not data:
            return ''
        try:
            j = json.loads(data.decode('utf-8', 'ignore'))
        except Exception:
            return ''
        u = ''
        if isinstance(j, dict):
            d = j.get('data') or {}
            if isinstance(d, dict):
                u = str(d.get('url') or d.get('video_url') or '')
        return u if u.startswith('http') else ''

    def _shell_base(self, frm):
        """从 /static/player/{from}.js 里取 base= 参数；取不到用兜底壳域。"""
        frm = re.sub(r'[^a-z0-9_\-]', '', str(frm or '').lower())
        if frm:
            js = self._page('/static/player/%s.js' % frm)
            m = re.search(r'base=([^&"\'\s]+)', js)
            if m:
                b = unquote(m.group(1)).rstrip('/')
                if b.startswith('http'):
                    return b + '/'
        return self.SHELL

    def _vid_from_play(self, page_url):
        m = re.search(r'/vodplay/(\d+)-', str(page_url or ''))
        return m.group(1) if m else ''

    def _nid_from_play(self, page_url):
        m = re.search(r'/vodplay/\d+-\d+-(\d+)/', str(page_url or ''))
        return m.group(1) if m else '1'

    def _b64(self, s):
        s = str(s or '').strip().replace('-', '+').replace('_', '/')
        return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', 'ignore')

    # =========================================================================
    # 请求与域池
    # =========================================================================
    def _page(self, path, hard=True):
        """
        相对路径取页：带路径级冷却，命中就直接空返回（不触发换域）。
        hard=False 用于搜索页：搜索的 403 是站点"请求太密"的限流（实测 170B 空壳），
        不是域失效；这时候换域只会把好域也换掉，必须由 searchContent 自己退避重试。
        """
        key = path if path.startswith('http') else self.base + path
        hit = self._CACHE.get(key)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[3]
        pf = self._PF.get(key)
        if pf and time.time() < pf:
            return ''
        code, ctype, data = self._req(key, self.BUDGET)
        if code not in (200, 206) or not data:
            if code in (404, 500):
                self._PF[key] = time.time() + self.FAIL_TTL
            if hard and code in self.HARD:
                self._mark_host(code)
            return ''
        text = self._decode(data, ctype)
        # 域被劫持/换皮最常见的就是"200 但返回一堆垃圾页"：首页与分类页
        # 只要既不认识 voddetail 也不认识 stui，就当这个域废了，立刻换下一个。
        # 限流页（"系统提示…6 秒"）是正常的 200 短页，必须排除，别误杀。
        if (path == '/' or path.startswith('/vodshow/')) \
                and '系统提示' not in text and 'voddetail' not in text and 'stui' not in text:
            self._mark_host(0)
            return ''
        if len(self._CACHE) > 200:
            self._CACHE.clear()
        self._CACHE[key] = (time.time(), code, ctype, text)
        return text

    def _page_abs(self, url):
        """绝对地址取页（壳页/发布页/播放页用，不走相对路径冷却）。"""
        hit = self._CACHE.get(url)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[3]
        code, ctype, data = self._req(url, self.BUDGET)
        if code not in (200, 206) or not data:
            return ''
        text = self._decode(data, ctype)
        if len(self._CACHE) > 200:
            self._CACHE.clear()
        self._CACHE[url] = (time.time(), code, ctype, text)
        return text

    def _req(self, url, budget, raw=False):
        """唯一的网络出口：线程加墙钟预算，超时即放弃，避免整页卡死。"""
        box = {}

        def run():
            try:
                r = self.session.get(url, timeout=25, verify=False,
                                     proxies=self.session.proxies or None)
                data = r.content or b''
                # 少数情况下前置代理会给 gzip，浏览器能解，requests 已自动解；再兜一层
                if data[:2] == b'\x1f\x8b':
                    try:
                        import gzip
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                box['code'] = r.status_code
                box['ctype'] = str(r.headers.get('Content-Type') or '')
                box['data'] = data
            except Exception as e:
                box['err'] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(budget)
        if 'data' not in box:
            return 0, '', b''
        if raw:
            return box['code'], box['ctype'], box['data']
        return box['code'], box['ctype'], box['data']

    def _decode(self, data, ctype):
        if 'gbk' in (ctype or '').lower() or 'gb2312' in (ctype or '').lower():
            try:
                return data.decode('gbk')
            except Exception:
                pass
        for enc in ('utf-8', 'gbk'):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('utf-8', 'ignore')

    def _probe(self, url):
        """
        媒体验真：Range 只取前 2KB，绝不整文件下载。
        字节 CDN 那条 .image?…&name=jz.mp4 实测 502MB，整量读会把 12s 预算烧穿、
        结果 probe 超时 → 明明可播却被判死；改 Range 后 200/206 + ftyp 秒回。
        """
        code, ctype, head = self._head(url)
        if code not in (200, 206) or not head:
            return False
        return (b'#EXTM3U' in head or b'ftyp' in head[:64]
                or 'mpegurl' in (ctype or '').lower() or 'video/' in (ctype or '').lower())

    def _head(self, url, n=2048):
        """
        流式取前 n 字节：Range + iter_content + 立即 close，大文件也不会被拖死。
        Referer 必须按媒体域处理：抖音/字节系（douyinvod / byteimg / bytetos）
        和 ppvod 系（blbtgg）都是"带任何 Referer 一律 403，不带才 200/206"，
        所以非站点自有域一律把 session 默认 Referer 置 None 删掉。
        （这是 direct_play 从 3/8 掉到 7/8 的第二个真凶，别改回去）
        """
        box = {}
        host = urlsplit(url).netloc
        hd = {'Range': 'bytes=0-%d' % (n - 1)}
        hd['Referer'] = ('https://%s/' % host) if 'juzong' in host else None

        def run():
            try:
                r = self.session.get(url, timeout=20, verify=False, stream=True, headers=hd)
                buf = b''
                for chunk in r.iter_content(1024):
                    buf += chunk
                    if len(buf) >= n:
                        break
                box['code'] = r.status_code
                box['ctype'] = str(r.headers.get('Content-Type') or '')
                box['data'] = buf[:n]
                try:
                    r.close()
                except Exception:
                    pass
            except Exception as e:
                box['err'] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(12)
        if 'data' not in box:
            return 0, '', b''
        return box['code'], box['ctype'], box['data']

    # ---- 域池 ---------------------------------------------------------------
    def _mark_host(self, code):
        """域级冷却 + 立刻换域重绑 base；否则后续请求还会打在坏域上。"""
        if code not in self.HARD:
            return
        bad = self.base
        if bad:
            type(self)._FAIL[bad] = time.time() + self.FAIL_TTL
        type(self)._HOST = ''
        type(self)._HT = 0.0
        new = self._pick_host(self.HOST, full=True)
        if new and new != bad:
            self.base = new
            self.headers['Referer'] = new + '/'
            self._CACHE = type(self)._CACHE.setdefault(new, {})
            self._FAIL = type(self)._FAIL.setdefault(new, {})
            self._PF = type(self)._PF.setdefault(new, {})
            self._PLAY = type(self)._PLAY.setdefault(new, {})

    def _pick_host(self, seed='', full=False):
        """
        选域顺序：种子 → 学习池 → 跳转页 targetUrl →（全挂才）发布页。
        full=False 是启动路径：只验前两个种子，失败也先认种子当 base，
        别把 init 拖成十几秒；真失效由 _page 的内容判定抓出来再走 full=True。
        full=True 是换域路径：上限 6 个候选、每个探 1 次、间隔 1s、总预算 15s。
        """
        now = time.time()
        cached = type(self)._HOST
        if cached and now - type(self)._HT < 600:
            return cached
        cands = []
        for h in (seed, self.HOST) + tuple(self.HOSTS) + tuple(type(self)._HOSTS):
            h = str(h or '').strip().rstrip('/')
            if h.startswith('http') and h not in cands:
                cands.append(h)
        if not full:
            for h in cands[:2]:
                ok, _ = self._alive(h, fast=True)
                if ok:
                    type(self)._HOST = h
                    type(self)._HT = time.time()
                    return h
            fallback = seed or self.HOST
            type(self)._HOST = fallback
            type(self)._HT = time.time()
            return fallback
        deadline = now + 15
        for h in cands[:6]:
            if time.time() > deadline:
                break
            if type(self)._FAIL.get(h) and time.time() < type(self)._FAIL[h]:
                continue
            ok, jump = self._alive(h)
            if ok:
                type(self)._HOST = h
                type(self)._HT = time.time()
                if h not in type(self)._HOSTS:
                    type(self)._HOSTS.append(h)
                return h
            if jump:
                # 备用域常是 5 秒跳转页，targetUrl 才是当年主域
                t = jump.rstrip('/')
                if t.startswith('http') and t not in cands:
                    cands.insert(0, t)
        # 种子和跳转页全没活，才去打发布页（省请求；发布页有 CF，可能被拦）
        if time.time() < deadline:
            for h in self._from_public():
                if h in cands:
                    continue
                if type(self)._FAIL.get(h) and time.time() < type(self)._FAIL[h]:
                    continue
                ok, _ = self._alive(h)
                if ok:
                    type(self)._HOST = h
                    type(self)._HT = time.time()
                    if h not in type(self)._HOSTS:
                        type(self)._HOSTS.append(h)
                    return h
        # 全失败：如实退回种子（站点可能只是一时限流，硬切空域反而整源不可用）
        fallback = seed or self.HOST
        type(self)._HOST = fallback
        type(self)._HT = time.time()
        return fallback

    def _alive(self, host, fast=False):
        """双判：200 + 含 voddetail/ 与 stui-vodlist；只有跳转页的域返回 targetUrl。"""
        key = 'alive:' + host
        ts = type(self)._PROBED.get(key + ':t')
        ttl = 300 if type(self)._PROBED.get(key + ':r') else 30
        if ts and time.time() - ts < ttl:
            return type(self)._PROBED.get(key + ':r', False), type(self)._PROBED.get(key + ':j', '')
        code, ctype, data = self._req(host + '/', 8, raw=True)
        jump = ''
        ok = False
        if code == 200 and data:
            text = self._decode(data, ctype)
            if 'voddetail/' in text and 'stui-vodlist' in text:
                ok = True
            else:
                m = re.search(r'targetUrl\s*=\s*["\']([^"\']+)["\']', text)
                if m:
                    jump = m.group(1)
        time.sleep(0.2 if fast else 1.0)  # 探测间隔：启动时轻量，换域时 ≥1s 别变压测
        type(self)._PROBED[key + ':t'] = time.time()
        type(self)._PROBED[key + ':r'] = ok
        type(self)._PROBED[key + ':j'] = jump
        return ok, jump

    def _from_public(self):
        """发布页解析：页面里列着 主用/备用/失效 三个域，取 juzong 系域名逐个验。"""
        out = []
        for u in self.PUBLIC:
            html = self._page_abs(u)
            if not html:
                continue
            for d in re.findall(r'https?://([a-z0-9][a-z0-9\.\-]{2,30})', html):
                if 'juzong' not in d:
                    continue
                base = 'https://' + d
                if base not in out:
                    out.append(base)
            if len(out) >= 4:
                break
        return out[:6]

    # ---- 小工具 -------------------------------------------------------------
    def _brace(self, text, start):
        depth, quote_ch, esc = 0, '', False
        for i in range(start, len(text)):
            ch = text[i]
            if quote_ch:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == quote_ch:
                    quote_ch = ''
                continue
            if ch in '"\'':
                quote_ch = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return ''

    def _rewrite(self, text, base_url):
        prefix = self._proxy_base()
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith('#'):
                if s.startswith('#EXT-X-KEY') and 'URI="' in s:
                    a = s.split('URI="', 1)[1].split('"', 1)[0]
                    s = s.replace(a, prefix + '?do=key&url=' + quote(urljoin(base_url, a), ''))
                out.append(s)
                continue
            absu = urljoin(base_url, s)
            if absu.split('?', 1)[0].lower().endswith('.m3u8'):
                out.append(prefix + '?do=m3u8&url=' + quote(absu, '') + '&ext=.m3u8')
            else:
                out.append(prefix + '?do=ts&url=' + quote(absu, '') + '&ext=.ts')
        return '\n'.join(out)

    def _proxy_base(self):
        try:
            from com.github.catvod import Proxy as JProxy
            u = JProxy.getUrl(True)
            if u:
                return str(u)
        except Exception:
            pass
        return 'http://127.0.0.1:9978/proxy'

    def _pic(self, p):
        p = str(p or '').strip()
        if p.startswith('//'):
            return 'https:' + p
        if p.startswith('http://'):
            return 'https://' + p[7:]
        if p.startswith('/'):
            return self.base + p
        return p

    def _pg(self, pg):
        try:
            page = int(pg)
        except Exception:
            page = 1
        return page if page > 0 else 1

    def _vid(self, ids):
        """ids 兼容 list / JSON 串 / 第01集$/路径 整段 / 纯数字。"""
        raw = ids
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ''
        s = str(raw or '').strip()
        if s.startswith('['):
            try:
                arr = json.loads(s.replace("'", '"'))
                s = str(arr[0]) if arr else ''
            except Exception:
                s = s.strip('[]\'" ')
        if '$' in s:
            s = s.split('$')[-1]
        m = re.search(r'voddetail/(\d+)', s) or re.search(r'(\d+)', s)
        return m.group(1) if m else ''

    def _path(self, pid):
        """播放 id 兜底：可能传 /vodplay/…、绝对 URL、或 第01集$/vodplay/… 整段。"""
        raw = pid
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ''
        s = str(raw or '').strip()
        if s.startswith('['):
            try:
                arr = json.loads(s.replace("'", '"'))
                s = str(arr[0]) if arr else ''
            except Exception:
                s = s.strip('[]\'" ')
        if '$' in s:
            s = s.split('$')[-1]
        s = s.strip()
        if s.startswith('http'):
            return s
        m = re.search(r'/vodplay/[^\s"\'<>]+', s)
        if m:
            return m.group(0)
        if s.isdigit():
            return '/vodplay/%s-1-1/' % s
        return ''
