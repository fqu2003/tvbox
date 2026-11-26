# -*- coding: utf-8 -*-
# 站点：https://m.7ighz2.com       金牌影院 / 爱电影（同一套后端，两个皮肤：seoId 33 / 115）
# 路线：签名 API 站 —— Next.js SSR 前端 + /mw-movie REST
#       签名 = sha1( md5( "排序后的参数&key=<signKey>&t=<毫秒>" ) )，header 带 sign / t / deviceId / client-type
# 生成：2026-11-23   维护：Doubao
# 依赖：requests（壳端自带）+ base.spider
# 接口：homeContent / homeVideoContent / categoryContent / detailContent / searchContent
#       playerContent / localProxy
# vod_id：147455（纯数字 vodId）
# 播放 id：147455|1323435（vodId|episodeNid），播放时再换成 m3u8 直链
# 域池：/mw-movie/anonymous/website/get/domain?websiteSeoId=33 动态返回备用域，失效自动换下一个
# 已知：ppvod01.kqgfbs.com 是反 Referer CDN，媒体请求必须"不带 Referer"才 200
#       m.x8kb9k8.com 已在池里但已死（证明域池会轮换，探活必须逐域实测）

import hashlib
import json
import re
import time
import uuid
from urllib.parse import unquote, urlsplit

import requests
from base.spider import Spider


class Spider(Spider):
    # ---------------------------------------------------------------- 基本常量
    # 用户给的入口域；init 只在这个域上探活，不做全量域池解析（否则启动要 10s+）
    HOST = 'https://m.7ighz2.com'
    NAME = 'ᵀ⁴爱电影'
    # 站点 API 前缀：前端 chunk 里写死 let u="/mw-movie"，不是 /api
    PRE = '/mw-movie'
    # 应用签名密钥：从播放页 chunk 的 requestUseSign 里取到，改版时按同一位置找
    SIGN_KEY = 'cb808529bae6b6be45ecfab29a4889bc'
    # 单页条数：站点 pageSize 默认 30，改大会和 totalPage 换算错位
    LIMIT = 30
    # 接口结果缓存 TTL：列表/详情/搜索都走它，翻页时同页重复请求直接命中
    TTL = 300
    # 失败冷却：失败后 30s 内直接返回空，避免整页卡死重试
    FAIL_TTL = 30
    # 单条 vod_play_url 上限：客户端按 2048B 截断，留 150B 余量后按集切段
    SEG = 1900
    # 搜索无结果时站点给 totalPage=0，这里补 1 页而不是 0，避免壳端把结果页判成空源
    SEARCH_PC = 1
    # 换域解析总预算：6 个候选 × 1s 间隔 + 远程域池，超时直接回落种子
    BUDGET = 15
    # 单请求超时：接口 12s（Next 站接口常在 0.5s 内回，留足余量）
    TIMEOUT = 12
    # 静态种子域：前两个是实测同站的（金牌影院），后一个已死留着占位（探活会跳过）
    SEEDS = ['https://m.7ighz2.com', 'https://m.jpyy.com',
             'https://jpyy.com', 'https://m.sxbfxk.com']
    # 动态域池的 seoId：33=金牌影院（m.7ighz2.com 实际解析到它），115=爱电影01
    SEO_IDS = [33, 115]
    # 反 Referer CDN 特征：这些域带任何 Referer 都 403，只有删掉 header 才 200/206
    NO_REF_HOSTS = ('kqgfbs', 'blbtgg', 'douyinvod', 'byteimg', 'bytetos')
    UA = ('Mozilla/5.0 (Linux; Android 13; PGT-AN20) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36')

    # ---------------------------------------------------------------- 类级共享
    # 缓存/冷却按域分组：换域后新域不能命中旧域的缓存，否则看着"新域也没数据"
    _CACHE = {}
    _FAIL = {}
    _TYPES = {}
    # 探活结果必须跨域共享（key 就是候选域本身），不能按 base 分组
    _PROBED = {}

    def init(self, extend=''):
        # 启动：只验前两个种子（0.2s 间隔），探活失败也先认种子，不把启动拖死
        s = (extend or '').strip()
        seed = self.HOST
        if s.startswith('{'):
            try:
                cfg = json.loads(s)
                if cfg.get('host'):
                    seed = str(cfg['host']).strip().rstrip('/')
                if cfg.get('seo'):
                    seo = int(cfg['seo'])
                    self.SEO_IDS = [seo] + [x for x in type(self).SEO_IDS if x != seo]
            except Exception:
                seed = self.HOST
        elif s.startswith('http'):
            seed = s.rstrip('/')
        if not seed.startswith('http'):
            seed = self.HOST

        self.session = requests.Session()
        self.session.trust_env = False
        self.session.verify = False
        self.UA = type(self).UA
        # 设备号固定：签名里要带，每次换 UUID 会被后端当新设备，反而多一套风控记录
        self.device = uuid.uuid4().hex
        self.headers = {'User-Agent': self.UA,
                        'Accept': 'application/json',
                        'Referer': seed + '/',
                        'Origin': seed}
        self.session.headers.update(self.headers)
        self.base = seed
        self._HOST = ''
        self._HT = 0.0
        self._SEQ = 0
        self._rebind(seed)
        self.base = self._pick_host(seed)
        self._rebind(self.base)
        return None

    # 源名：与文件名一致，壳端列表里显示的就是它
    def getName(self):
        return self.NAME

    # ================================================================= 六个接口
    def homeContent(self, filter):
        # 首页：分类取站点真实一级目录（filer/type），体育直播跳 /sports 外站所以剔除
        # filters 故意留空：站点的年份/类型筛选值未逐个实测，不放假选项误导壳端
        classes = [{'type_id': str(t['typeId']), 'type_name': t['typeName']}
                   for t in self._types()]
        return {'class': classes, 'filters': {}, 'list': self.homeVideoContent()['list']}

    # 首页列表：按大类各取一页拼首页（无 type1 的混合列表站点会报错，别用）
    def homeVideoContent(self):
        items, seen = [], set()
        for tid in ('1', '2'):
            d = self._get('/anonymous/video/list',
                          {'type1': tid, 'pageNum': '1', 'pageSize': str(self.LIMIT)}) or {}
            for x in (d.get('list') or []):
                c = self._card(x)
                if c.get('vod_name') and c['vod_id'] not in seen:
                    seen.add(c['vod_id'])
                    items.append(c)
            if len(items) >= self.LIMIT:
                break
        return {'list': items[:self.LIMIT]}

    # 分类：tid 就是站点 typeId1（1 电影 / 2 电视剧 / 3 综艺 / 4 动漫 / 88 短剧）
    # 分页用站点真值 totalPage（库里有 334 页），不是本地切片
    def categoryContent(self, tid, pg, filter, extend):
        page = self._pg(pg)
        ext = self._ext(extend)
        q = {'type1': str(tid or '1'), 'pageNum': str(page), 'pageSize': str(self.LIMIT)}
        # 二级筛选：type=具体 typeId，year=年份，v_class=类型词，都可选
        for k, name in (('type', 'type'), ('year', 'year'), ('v_class', 'v_class')):
            val = str(ext.get(name) or '').strip()
            if val:
                q[k] = val
        d = self._get('/anonymous/video/list', q) or {}
        items = [self._card(x) for x in (d.get('list') or [])]
        items = [x for x in items if x.get('vod_name')]
        total_page = self._int(d.get('totalPage'), page)
        return {'page': page, 'pagecount': max(page, total_page),
                'limit': self.LIMIT, 'total': total_page * self.LIMIT, 'list': items}

    # 详情：video/detail 一次给全字段 + episodeList(nid/name)
    # 站点只有一条播放线路（取流只认 id+nid，没有 sid 概念），所以 from/url 都是一段
    def detailContent(self, ids):
        key = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(key or '').split('|')[0].strip()
        if not vid:
            return {'list': []}
        d = self._get('/anonymous/video/detail', {'id': vid}) or {}
        if not d:
            return {'list': []}
        eps = [e for e in (d.get('episodeList') or []) if e.get('nid')]
        if not eps:
            return {'list': []}
        pairs = [(str(e.get('name') or '').strip() or '第%d集' % (i + 1),
                  '%s|%s' % (vid, e.get('nid'))) for i, e in enumerate(eps)]
        lines = self._segments('蓝光', pairs)
        vod = {'vod_id': vid,
               'vod_name': str(d.get('vodName') or '').replace('|', ' ').strip(),
               'vod_pic': self._pic(d.get('vodPic')),
               'vod_remarks': str(d.get('vodRemarks') or ''),
               'vod_year': str(d.get('vodYear') or ''),
               'vod_area': str(d.get('vodArea') or ''),
               'vod_lang': str(d.get('vodLang') or ''),
               'vod_actor': str(d.get('vodActor') or ''),
               'vod_director': str(d.get('vodDirector') or ''),
               'vod_content': self._txt(d.get('vodContent')),
               'type_name': str(d.get('typeName') or '')}
        vod['vod_play_from'] = '$$$'.join(x[0] for x in lines)
        vod['vod_play_url'] = '$$$'.join(x[1] for x in lines)
        return {'list': [vod]}

    # 搜索：searchByWord 直接返 {result:{list,totalPage}}，另有 typeResult 是分类联想，忽略
    # quick='1' 不代表站点有快搜接口，统一走分页搜索，避免壳端拿到假快搜结果
    def searchContent(self, key, quick, pg='1'):
        page = self._pg(pg)
        kw = str(key or '').strip()
        if not kw:
            return {'page': page, 'pagecount': self.SEARCH_PC,
                    'limit': self.LIMIT, 'total': 0, 'list': []}
        d = self._get('/anonymous/video/searchByWord',
                      {'keyword': kw, 'pageNum': str(page), 'pageSize': str(self.LIMIT)}) or {}
        res = d.get('result') or {}
        items = [self._card(x) for x in (res.get('list') or [])]
        items = [x for x in items if x.get('vod_name')]
        total_page = self._int(res.get('totalPage'), self.SEARCH_PC)
        return {'page': page, 'pagecount': max(self.SEARCH_PC, total_page),
                'limit': self.LIMIT, 'total': total_page * self.LIMIT, 'list': items}

    # 播放：episode/url 给 3 档 m3u8（1080 蓝光 / 720 高清 / 480 标清）
    # 优先 needLogin=false 那档（1080/720 标了 needLogin=true，实测 480 一定可播）
    def playerContent(self, flag, id, vipFlags):
        # 入参兼容两种：'147455|1323435' 与 '第1集$147455|1323435'
        # 云盘壳与部分校验器会把整段 vod_play_url 第一段原样传进来，不剥 '$' 就取流全失败
        raw = str(id or '').strip()
        if '$' in raw:
            raw = raw.rsplit('$', 1)[1]
        parts = raw.split('|', 1)
        vid, nid = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else '')
        if not vid or not nid:
            return {'parse': 1, 'jx': 1, 'url': '', 'playUrl': '', 'header': ''}
        d = self._get('/anonymous/v2/video/episode/url',
                      {'clientType': '3', 'id': vid, 'nid': nid}) or {}
        lst = [x for x in (d.get('list') or []) if x.get('url')]
        if not lst:
            return {'parse': 1, 'jx': 1, 'url': '', 'playUrl': '', 'header': ''}
        # 排序：免登录优先 → 分辨率降序（蓝光>高清>标清）
        lst.sort(key=lambda x: (1 if x.get('needLogin') else 0,
                                -self._int(x.get('resolution'), 0)))
        url = str(lst[0]['url'])
        header = json.dumps(self._media_headers(url))
        if self._probe(url):
            return {'parse': 0, 'jx': 0, 'url': url, 'playUrl': '', 'header': header}
        return {'parse': 1, 'jx': 1, 'url': url, 'playUrl': '', 'header': header}

    def localProxy(self, param):
        # 图片 / HLS 代理：真实 MIME + 二进制；空 body 一律 404，绝不返 200 空图
        text = str(param or '')
        m = re.search(r'(?:^|[?&])url=([^&]+)', text)
        if not m:
            return [404, 'text/plain', b'']
        url = unquote(m.group(1))
        if not url.startswith('http'):
            return [404, 'text/plain', b'']
        code, ctype, data = self._req(url, raw=True)
        if code not in (200, 206) or not data:
            return [404, 'text/plain', b'']
        if 'do=m3u8' in text and data[:7] == b'#EXTM3U':
            return [200, 'application/vnd.apple.mpegurl', data]
        return [200, ctype or 'application/octet-stream', data]

    # ================================================================= 域池
    def _pick_host(self, seed='', full=False):
        # 选域分两条路径：启动只验 2 个种子；判定域失效（full=True）才跑全量 + 远程域池
        now = time.time()
        if self._HOST and now - self._HT < 600:
            return self._HOST
        seed = str(seed or self.HOST).rstrip('/')
        cands = [seed]
        for h in self.SEEDS:
            h = h.rstrip('/')
            if h and h not in cands:
                cands.append(h)
        if not full:
            for i, h in enumerate(cands[:2]):
                if i:
                    time.sleep(0.2)
                if self._alive(h, fast=True):
                    self._HOST, self._HT = h, now
                    return h
            # 探活失败也先认种子：站点可能只是瞬时限流，硬切空域会让整源不可用
            self._HOST, self._HT = seed, now
            return seed
        deadline = now + self.BUDGET
        seen = list(cands[:6])
        for i, h in enumerate(seen):
            if time.time() > deadline:
                break
            if i:
                time.sleep(1)
            if self._alive(h):
                self._HOST, self._HT = h, time.time()
                return h
        # 静态种子全挂才问远程域池：接口本身要签名，所以走当前 base
        for h in self._remote_pool():
            if h in seen or time.time() > deadline:
                continue
            seen.append(h)
            time.sleep(1)
            if self._alive(h):
                self._HOST, self._HT = h, time.time()
                return h
        self._HOST, self._HT = seed, time.time()
        return seed

    def _remote_pool(self):
        # 远程域池：website/get/domain 按 seoId 返回该皮肤的全部域（33 → jpyy/sxbfxk/x8kb9k8）
        # 返回的是裸域，真实站点还提供 m. 移动端子域，两种都当候选
        out = []
        for seo in self.SEO_IDS[:2]:
            lst = self._api('/anonymous/website/get/domain',
                            {'websiteSeoId': str(seo)}, hard=False)
            if not isinstance(lst, list):
                continue
            for dom in lst:
                dom = str(dom or '').strip()
                if not dom or '.' not in dom:
                    continue
                for h in ('https://m.' + dom, 'https://' + dom):
                    if h not in out:
                        out.append(h)
        return out

    def _alive(self, host, fast=False):
        # 探活只打 website/conf（35B JSON），不拉首页：首页 396KB，探 6 个域就是 2.4MB
        host = str(host or '').rstrip('/')
        if not host.startswith('http'):
            return False
        key = host + ':t'
        hit = self._PROBED.get(key)
        if hit:
            # 成功缓存 300s、失败只缓存 30s：失败也缓存 5 分钟会让一次瞬时限流把好域判死
            ttl = 300 if self._PROBED.get(host + ':r') else 30
            if time.time() - hit < ttl:
                return bool(self._PROBED.get(host + ':r'))
        ok = False
        try:
            url = host + self.PRE + '/anonymous/website/conf'
            r = self.session.get(url, headers=self._sign_headers({}, host),
                                 timeout=4 if fast else 8, verify=False, stream=True,
                                 proxies=self.session.proxies or None)
            buf = next(r.iter_content(2048), b'')
            r.close()
            ok = b'"code":200' in buf or b'"code": 200' in buf
        except Exception:
            ok = False
        self._PROBED[key] = time.time()
        self._PROBED[host + ':r'] = ok
        return ok

    def _mark_host(self, code):
        # 换域三件套：主域、请求头、三张表按新域分组——只清 _HOST 不改 base 等于假换域
        bad = self.base
        self._HOST = ''
        self._HT = 0.0
        new = self._pick_host(self.HOST, full=True)
        if new and new != bad:
            self._rebind(new)
        return new

    def _rebind(self, host):
        # 绑定当前域：base / 请求头 / 缓存表分组。探活表不重绑（跨域共享）
        host = str(host or self.HOST).rstrip('/')
        self.base = host
        self.headers = {'User-Agent': self.UA, 'Accept': 'application/json',
                        'Referer': host + '/', 'Origin': host}
        self.session.headers.update(self.headers)
        self._CACHE = type(self)._CACHE.setdefault(host, {})
        self._FAIL = type(self)._FAIL.setdefault(host, {})
        self._TYPES = type(self)._TYPES.setdefault(host, {})

    # ================================================================= 接口层
    def _sign_headers(self, params, host=None):
        # 站点签名：GET 参数按 key 字典序拼 k=v&k=v，再接 key=<signKey>&t=<毫秒>，再 sha1(md5(整串))
        # 参数值不做 URL 编码（和前端一致），空值/None 直接剔除，否则哈希对不上
        base = str(host or self.base).rstrip('/')
        t = str(int(time.time() * 1000))
        body = self._qstr(params)
        raw = (body + '&' if body else '') + 'key=%s&t=%s' % (self.SIGN_KEY, t)
        sg = hashlib.sha1(hashlib.md5(raw.encode('utf-8')).hexdigest()
                          .encode('utf-8')).hexdigest()
        return {'client-type': '3', 'sign': sg, 't': t, 'deviceId': self.device,
                'authorization': '', 'Accept': 'application/json',
                'User-Agent': self.UA, 'Referer': base + '/', 'Origin': base}

    def _qstr(self, params):
        # 签名串与 query 必须同源同序：排序键、跳过空值，返回不带前导 '?'
        if not params:
            return ''
        parts = []
        for k in sorted(params.keys()):
            v = params[k]
            if v is None:
                continue
            v = str(v)
            if v in ('', 'undefined', 'null'):
                continue
            parts.append('%s=%s' % (k, v))
        return '&'.join(parts)

    def _get(self, path, params=None, hard=True):
        # 单次接口调用的语义包装：命中缓存直接回，冷却期内回 None，失败计数到 2 换域
        return self._api(path, params, hard=hard)

    def _api(self, path, params=None, host=None, hard=True, retry=True):
        # 所有接口的统一入口：拼 URL → 签名 → 解析 JSON 的 data
        # code!=200 只当"本次失败"写冷却，不换域（122012 缺签名、99500 参数错都不是域问题）
        base = str(host or self.base).rstrip('/')
        params = dict(params or {})
        ck = path + '?' + self._qstr(params)
        hit = self._CACHE.get(ck)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[1]
        exp = self._FAIL.get(ck)
        if exp and time.time() < exp:
            return None
        try:
            r = self.session.get(base + self.PRE + path, params=params or None,
                                 headers=self._sign_headers(params, base),
                                 timeout=self.TIMEOUT, verify=False,
                                 proxies=self.session.proxies or None)
            if r.status_code != 200:
                self._FAIL[ck] = time.time() + self.FAIL_TTL
                if hard and r.status_code >= 500:
                    self._seq_fail()
                return None
            j = r.json()
        except Exception:
            self._FAIL[ck] = time.time() + self.FAIL_TTL
            # 连接级异常基本等于"这个域不通"：立刻换域并重试一次，
            # 不换域的话第一次请求必然空手而归（实测死域首请求 0 条、第二次才恢复）
            if hard and retry:
                new = self._mark_host(0)
                if new and new != base:
                    return self._api(path, params, retry=False)
            elif hard:
                self._seq_fail()
            return None
        if not isinstance(j, dict) or j.get('code') != 200:
            self._FAIL[ck] = time.time() + self.FAIL_TTL
            return None
        data = j.get('data')
        if len(self._CACHE) > 300:
            self._CACHE.clear()
        self._CACHE[ck] = (time.time(), data)
        self._SEQ = 0
        return data

    def _seq_fail(self):
        # 连续两次网络级失败才换域：单次抖动就换域会把好域换掉（实测首页偶发 5xx 一次）
        self._SEQ = self._SEQ + 1
        if self._SEQ >= 2:
            self._SEQ = 0
            self._mark_host(0)

    # ================================================================= 数据整形
    def _types(self):
        # 分类目录：filer/type 是站点真实一级目录，体育直播指向 /sports 外战，剔除
        cached = self._TYPES.get('list')
        if cached and time.time() - cached[0] < self.TTL * 4:
            return cached[1]
        data = self._api('/anonymous/get/filer/type')
        out = []
        for t in (data or []):
            if not isinstance(t, dict) or not t.get('typeId'):
                continue
            if '/sports' in str(t.get('typeJumpurl') or ''):
                continue
            name = str(t.get('typeName') or '').strip()
            if not name:
                continue
            out.append({'typeId': int(t['typeId']), 'typeName': name})
        if not out:
            # 兜底只在接口失败时用，正常路径永远是站点真目录
            out = [{'typeId': 1, 'typeName': '电影'}, {'typeId': 2, 'typeName': '电视剧'},
                   {'typeId': 3, 'typeName': '综艺'}, {'typeId': 4, 'typeName': '动漫'},
                   {'typeId': 88, 'typeName': '短剧'}]
        self._TYPES['list'] = (time.time(), out)
        return out

    def _card(self, x):
        # 列表/搜索共用卡片映射：字段名与 MacCMS 那套基本一致，但 id 是 vodId
        x = x or {}
        vid = x.get('vodId') or x.get('id')
        name = str(x.get('vodName') or '').replace('|', ' ').strip()
        if not vid or not name:
            return {}
        remarks = str(x.get('vodRemarks') or '')
        if not remarks and x.get('vodSerial'):
            remarks = str(x.get('vodSerial')) + '集'
        return {'vod_id': str(vid), 'vod_name': name,
                'vod_pic': self._pic(x.get('vodPic')),
                'vod_remarks': remarks,
                'vod_year': str(x.get('vodYear') or ''),
                'type_name': str(x.get('typeName') or '')}

    def _segments(self, label, pairs):
        # 1900B 分段：客户端按 2048B 截断 vod_play_url，长剧必须拆段否则后半段集数丢失
        chunks, cur, size = [], [], 0
        for n, u in pairs:
            seg = '%s$%s' % (n, u)
            b = len(seg.encode('utf-8')) + 1
            if cur and size + b > self.SEG:
                chunks.append(cur)
                cur, size = [], 0
            cur.append((n, u))
            size += b
        if cur:
            chunks.append(cur)
        if len(chunks) <= 1:
            return [(label, self._join(chunks[0] if chunks else []))]
        # 同名线路加 (1)(2)：壳端同名会互相覆盖
        return [('%s(%d)' % (label, i + 1), self._join(c)) for i, c in enumerate(chunks)]

    def _join(self, eps):
        # 集数与地址用 # 分、NAME$URL 用 $ 分，这是壳端 vod_play_url 的固定语法
        out = []
        for i, (n, u) in enumerate(eps):
            out.append('%s$%s' % (n or '第%d集' % (i + 1), u))
        return '#'.join(out)

    def _txt(self, html):
        # 简介是 HTML 片段（<p>…</p>），壳端只认纯文本
        s = str(html or '')
        s = re.sub(r'<[^>]+>', '', s)
        s = s.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&')
        return s.strip()

    def _pic(self, p):
        # 封面统一 https：站点图床 obs.3688baihuo.com 本身就支持 https
        p = str(p or '').strip()
        if p.startswith('//'):
            return 'https:' + p
        if p.startswith('http://'):
            return 'https://' + p[7:]
        if p.startswith('/'):
            return self.base + p
        return p

    # ================================================================= 媒体
    def _media_headers(self, url):
        # ppvod 系（kqgfbs / blbtgg）和字节系带任何 Referer 都是 403，必须彻底不给
        # 返回给壳端的 header 里不能有 Referer: null，所以这里直接不带这个键
        host = urlsplit(str(url or '')).netloc
        for k in self.NO_REF_HOSTS:
            if k in host:
                return {'User-Agent': self.UA}
        return {'User-Agent': self.UA, 'Referer': self.base + '/', 'Origin': self.base}

    def _probe(self, url):
        # 媒体验真：Range 只读前 2KB 就判，绝不整文件下载（长视频会把预算烧穿）
        code, ctype, head = self._head(url)
        if code not in (200, 206) or not head:
            return False
        low = (ctype or '').lower()
        return (b'#EXTM3U' in head or b'ftyp' in head[:64]
                or 'mpegurl' in low or 'video/' in low)

    def _head(self, url, n=2048):
        # 流式取前 n 字节：Referer 传 None 让 requests 删掉 session 里的站点 Referer，
        # 否则 session 默认 Referer 会打到 CDN 上，实测直接 403
        hd = {'Range': 'bytes=0-%d' % (n - 1), 'Referer': None}
        try:
            r = self.session.get(url, headers=hd, timeout=20, verify=False, stream=True,
                                 proxies=self.session.proxies or None)
            buf = b''
            try:
                for ch in r.iter_content(1024):
                    buf += ch
                    if len(buf) >= n:
                        break
            finally:
                r.close()
            return r.status_code, r.headers.get('Content-Type') or '', buf
        except Exception:
            return 0, '', b''

    def _req(self, url, raw=False):
        # 代理取流：图片要完整字节，所以不设 Range；CDN 同样要删 Referer
        try:
            r = self.session.get(url, headers={'Referer': None, 'User-Agent': self.UA},
                                 timeout=20, verify=False, stream=raw,
                                 proxies=self.session.proxies or None)
            if raw:
                data = r.content
                r.close()
                return r.status_code, r.headers.get('Content-Type') or '', data
            return r.status_code, r.headers.get('Content-Type') or '', b''
        except Exception:
            return 0, '', b''

    # ================================================================= 工具
    def _pg(self, pg):
        # 页码规范化：壳端可能传 '1' / 1 / '' / 'abc'
        try:
            page = int(str(pg).strip())
        except Exception:
            page = 1
        return page if page > 0 else 1

    def _int(self, v, default=0):
        # 站点有些计数字段是字符串，统一转 int，失败给默认值
        try:
            return int(str(v).strip())
        except Exception:
            return default

    def _ext(self, extend):
        # extend 可能是 dict 也可能是 JSON 串，解析失败当空
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str) and extend.strip().startswith('{'):
            try:
                return json.loads(extend)
            except Exception:
                return {}
        return {}
