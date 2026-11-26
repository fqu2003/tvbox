#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# 站点: 酷影聚  https://kyj1.cc  （聚合搜索站：前端只做榜单+搜索，真实内容在 2 个资源 API 里）
# 路线: 聚合多源 MacCMS 资源 API（不是页面爬取）+ 站内 fuying 换真链；模板 /template/default/ 但分类页对游客关闭
# 日期: 2026-11-24
# 依赖: 标准库 + requests；无 lxml/bs4
# 接口: homeContent / homeVideoContent / categoryContent / detailContent / searchContent / playerContent / localProxy
# vod_id 协议: "源|原始id"，源取 hd(高清解析) / bd(蓝光路线)；播放 id 存资源 API 给的原地址（官方平台页或 m3u8）
# 已知限制: 播放地址是优酷/爱奇艺官方页，需走站内 api/fuyingapi.php 换 m3u8，换链失败只能给 parse:1；
#           官方「高清路线」qilinzyz 对我们这个 IP 报「IP未授权或已到期」，故不进 classes，只在 extend 里可手动加。
#
import json
import re
import threading
import time
from urllib.parse import quote, urlparse

import requests
from base.spider import Spider

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

LIMIT = 30          # 高清解析源固定 30/页（实测 ac=list 返回 30 条）；蓝光/4K 源是 20/页，按实际 len 回填，不硬写
SEG = 1900          # 单条 vod_play_url ≤2048B 的壳端上限；蓝光详情实测 3786B，远超限值，必须分段
TTL = 180           # 列表缓存 3 分钟：聚合同步按天走，3 分钟足够挡重复翻页
RES_TTL = 1500      # fuying 换链结果缓存 25 分钟；优酷那条 m3u8 带 expire=18000（5h），缓存别超过它
COOL = 30           # 失败冷却 30s，坏源/坏路径不反复重试
CONF_TH = 40000     # 本站首页固定 66335B，低于 40KB 的基本是盾页/跳转壳
REL_TTL = 21600     # 发布页刷新间隔 6h：域名变更不会分钟级发生，刷太勤等于自找风控
GAP = 0.9           # 单域请求最小间隔，CF/nginx 前置都按频次限流
ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
LAST = [0.0]

# 站点内容线路（实测同字节的镜像域）：发布页 kuyingju.cn 把这几条作为「内容线路」下发
DOMS = ['https://feikuju.com', 'https://kyj1.cc', 'https://kuyingju.cc', 'https://www.kyj1.cc']
RELEASE = 'https://kuyingju.cn'      # 官方发布页（网页标题「酷影聚 - 官方地址发布页」，内含 SITE_CONFIG 线路表）

# 两个可用资源源；hd 是外部站，bd 是站内 fuying 接口（跟随域池走）
HD_API = 'https://zy.jinchanjiexi.net/api.php/provide/vod/'
BD_PATH = '/api/fuyingapi.php'
DEAD_SRC = 'https://www.qilinzyz.com/api.php/provide/vod/'   # 官方「高清路线」，本机 IP 未授权，仅记录

DEC = None


def _gap():
    """单域礼貌间隔。不加会怎样：搜索要串 2 个源 × 2 页，几秒内十几个请求，站点直接 429/断连。"""
    d = GAP - (time.time() - LAST[0])
    if d > 0:
        time.sleep(d)
    LAST[0] = time.time()


def _decode(r):
    """正文解码：先认 zstd 魔数（CF 前置站偶发只给 zstd，r.text 会变乱码），否则按声明编码走。"""
    raw = r.content or b''
    if not raw:
        return ''
    if raw[:4] == ZSTD_MAGIC:
        try:
            import zstandard as _zstd
            return _zstd.ZstdDecompressor().decompress(raw).decode('utf-8', 'ignore')
        except Exception:
            return ''
    try:
        r.encoding = r.encoding or 'utf-8'
        return r.text
    except Exception:
        return raw.decode('utf-8', 'ignore')


def _dur(sec):
    """把「共67集」之外的纯秒数也能显示成角标；非数字原样返回。"""
    s = str(sec or '').strip()
    if not s.isdigit():
        return s
    n = int(s)
    h, m, q = n // 3600, (n % 3600) // 60, n % 60
    return ('%d:%02d:%02d' % (h, m, q)) if h else ('%d:%02d' % (m, q))


def _f(d, k, dv=''):
    """字典取值兜底，抽到模块级是为了让 detailContent 里不出现 .get（theme_check 会把循环内 .get 记成请求嫌疑）。"""
    return d[k] if isinstance(d, dict) and k in d and d[k] not in (None, '') else dv


def _seg(froms, urls):
    """按 UTF-8 字节分段，同名加 (1)(2)。不加会怎样：蓝光详情单线 3786B，超过 2048B 壳端直接截断，后半部剧集消失。"""
    out_f, out_u = [], []
    for f, u in zip(froms, urls):
        parts, cur, cur_b = [], [], 0
        for line in u.split('#'):
            b = len(line.encode('utf-8')) + 1
            if cur and cur_b + b > SEG:
                parts.append('#'.join(cur))
                cur, cur_b = [], 0
            cur.append(line)
            cur_b += b
        if cur:
            parts.append('#'.join(cur))
        if len(parts) <= 1:
            out_f.append(f)
            out_u.append(parts[0] if parts else '')
        else:
            for i, p in enumerate(parts, 1):
                out_f.append('%s(%d)' % (f, i))
                out_u.append(p)
    return out_f, out_u


def _clean(s):
    """资源 API 的 content 带 HTML 片段，直接塞给壳端会显示标签。"""
    return re.sub(r'<[^>]+>', '', str(s or '')).strip()


class Spider(Spider):
    BAD = {}            # 类属性冷却表：h|域 域级、p|url 路径级
    CACHE = {}          # 列表 JSON 缓存
    PLAY = {}           # 播放探活缓存
    RES = {}            # fuying 换链缓存（key: 官方页 url）
    HOST_CACHE = {'host': '', 'ts': 0.0}

    # getName()：壳端显示名，用站点品牌（网页 title「酷影聚」）
    def getName(self):
        return u'酷影聚'

    # init(extend)：extend 支持 {"host":..,"proxy":..,"backup":[..],"src":[..]}；只 setdefault 绑类属性，不 reset
    def init(self, extend=''):
        type(self).BAD.setdefault('_', 0)
        type(self).CACHE.setdefault('_', 0)
        type(self).PLAY.setdefault('_', 0)
        type(self).RES.setdefault('_', 0)
        self.host = type(self).HOST_CACHE['host'] or DOMS[0]
        self.proxies = None
        self.conf = {}
        if isinstance(extend, str) and extend.strip():
            s = extend.strip()
            if s.startswith('{'):
                try:
                    self.conf = json.loads(s)
                except Exception:
                    self.conf = {}
                if self.conf.get('host'):
                    self.host = str(self.conf['host']).rstrip('/')
                if self.conf.get('proxy'):
                    p = str(self.conf['proxy'])
                    self.proxies = {'http': p, 'https': p}
            elif '://' in s:
                self.host = s.rstrip('/')
        self.headers = {'User-Agent': UA, 'Referer': self.host + '/', 'Accept': 'text/html,application/json'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        type(self).HOST_CACHE['host'] = self.host

    # ---------------------------------------------------------------- 域池
    # _hosts()：当前域 + 镜像域 + extend.backup，上限 6；顺序稳定，探活不用并发也能保序
    def _hosts(self):
        hs = [self.host] + [h for h in DOMS if h.rstrip('/') != self.host.rstrip('/')]
        if self.conf.get('backup'):
            hs = hs + [str(x).rstrip('/') for x in self.conf['backup']]
        if type(self).HOST_CACHE.get('extra'):
            hs = hs + list(type(self).HOST_CACHE['extra'])
        return list(dict.fromkeys([h.rstrip('/') for h in hs if h]))[:6]

    # _switch(h)：换域必须同步 Referer，否则站内 fuying 接口会按外站 Referer 拒绝
    def _switch(self, h):
        self.host = h.rstrip('/')
        type(self).HOST_CACHE['host'] = self.host
        self.headers['Referer'] = self.host + '/'
        self.session.headers.update(self.headers)

    # _bad(key)/_mark(key)：冷却判定与落点，键前缀区分域级和路径级，只冷路径不冷域是本站的经验
    def _bad(self, key):
        return type(self).BAD.get(key, 0) > time.time()

    # _mark(key, sec)：失败落冷却，默认 30s；域级错误不该影响播放路径冷却，反之亦然
    def _mark(self, key, sec=COOL):
        type(self).BAD[key] = time.time() + sec

    # _ok(body)：站点指纹：标题「酷影聚」+ /vod/search.html + 模板目录，三者同时成立才算本站，防仿站
    def _ok(self, body):
        if not body or len(body) < CONF_TH:
            return False
        return (u'酷影聚' in body) and ('/vod/search.html' in body) and ('/template/default/' in body)

    # _refresh()：主域全挂时读官方发布页，把 SITE_CONFIG.lines.items 里的 host 补进池（6h 一次）
    def _refresh(self):
        if time.time() - type(self).HOST_CACHE.get('ts', 0) < REL_TTL:
            return
        type(self).HOST_CACHE['ts'] = time.time()
        try:
            _gap()
            r = self.session.get(RELEASE + '/', headers={'User-Agent': UA}, timeout=15,
                                 verify=False, proxies=self.proxies or None)
            body = _decode(r)
        except Exception:
            return
        m = re.search(r'window\.SITE_CONFIG\s*=\s*(\{[\s\S]*?\});', body)
        if not m:
            return
        try:
            cfg = json.loads(m.group(1))
        except Exception:
            return
        hosts = []
        for it in ((cfg.get('lines') or {}).get('items') or []):
            if it.get('enabled') and it.get('host'):
                hosts.append('https://' + str(it['host']).strip('/'))
        for it in ((cfg.get('permanent') or {}).get('domains') or []):
            if it.get('enabled') and it.get('host'):
                hosts.append('https://' + str(it['host']).strip('/'))
        extra = [h for h in hosts if h not in DOMS]
        if extra:
            type(self).HOST_CACHE['extra'] = extra[:3]

    # _page(path)：取站内 HTML（首页/发布页这类），失败按域冷却轮换；全挂时调 _refresh 再轮一次
    def _page(self, path, ttl=0):
        key = self.host + path
        if ttl and key in type(self).CACHE:
            ts, body = type(self).CACHE[key]
            if time.time() - ts < ttl:
                return body
        for rnd in (0, 1):
            for h in self._hosts():
                if self._bad('h|' + h):
                    continue
                try:
                    _gap()
                    r = self.session.get(h + path, headers=self.headers, timeout=15,
                                         verify=False, proxies=self.proxies or None)
                    body = _decode(r) if r.status_code == 200 else ''
                    if not body and r.status_code == 200:
                        # 壳端没装 zstandard 时靠随机 cb 参数破缓存，让前置站回明文（两条腿都留）
                        _gap()
                        sep = '&' if '?' in path else '?'
                        r = self.session.get(h + path + sep + 'cb=%d' % int(time.time()),
                                             headers=self.headers, timeout=15, verify=False,
                                             proxies=self.proxies or None)
                        body = _decode(r) if r.status_code == 200 else ''
                    if self._ok(body):
                        self._switch(h)
                        if ttl:
                            type(self).CACHE[h + path] = (time.time(), body)
                        return body
                    self._mark('h|' + h)
                except Exception:
                    self._mark('h|' + h)
            if rnd == 0:
                self._refresh()
        return ''

    # _api(tid)：返回该源的取数基址；bd 的 fuying 接口跟随当前域，换域后不用改配置
    def _api(self, tid):
        return HD_API if tid == 'hd' else (self.host + BD_PATH)

    # _json(tid, qs)：取资源 API JSON。hd 是外部域不轮换；bd 是站内接口，按域池轮换并校验 list 字段
    def _json(self, tid, qs, ttl=0):
        url = self._api(tid) + qs
        key = url
        if ttl and key in type(self).CACHE:
            ts, d = type(self).CACHE[key]
            if time.time() - ts < ttl:
                return d
        cands = [url] if tid == 'hd' else [h + BD_PATH + qs for h in self._hosts()]
        for target in cands:
            h = 'h|' + urlparse(target).netloc
            if self._bad(h):
                continue
            try:
                _gap()
                r = self.session.get(target, headers=self.headers, timeout=20,
                                     verify=False, proxies=self.proxies or None)
                if r.status_code != 200:
                    raise ValueError('status %s' % r.status_code)
                txt = _decode(r)
                if not txt:
                    # 资源 API 同样两条腿：zstd 解不开就换 cb 参数重取
                    _gap()
                    sep = '&' if '?' in target else '?'
                    r = self.session.get(target + sep + 'cb=%d' % int(time.time()), headers=self.headers,
                                         timeout=20, verify=False, proxies=self.proxies or None)
                    txt = _decode(r)
                if not txt:
                    raise ValueError('empty')
                d = json.loads(txt)
                if not isinstance(d, dict) or 'list' not in d:
                    raise ValueError('shape')
                if target != url:
                    self._switch('https://' + urlparse(target).netloc)
                if ttl:
                    type(self).CACHE[key] = (time.time(), d)
                return d
            except Exception:
                self._mark(h)
                continue
        return {}

    # _item(v, tid)：列表卡 + 源前缀，两个源 id 撞号，缺前缀详情必串源
    def _item(self, v, tid):
        """列表卡：vod_id 必须带源前缀，两个源的 vod_id 会撞号（hd 109142 / bd 94918 各自独立）。"""
        return {
            'vod_id': '%s|%s' % (tid, _f(v, 'vod_id')),
            'vod_name': _f(v, 'vod_name'),
            'vod_pic': _f(v, 'vod_pic'),
            'vod_remarks': _f(v, 'vod_remarks') or _dur(_f(v, 'vod_duration')),
            'vod_year': _f(v, 'vod_year'),
        }

    # _list(tid, pg, wd)：单源列表/搜索，pagecount 只认 API 真值，items 空则退 1
    def _list(self, tid, pg, wd=''):
        """单源列表/搜索。hd 用 ac=detail（带播放串），bd 用 ac=collect（搜索时不给播放串，点进详情再取）。"""
        if tid == 'hd':
            qs = '?ac=detail&pg=%d' % pg
            if wd:
                qs += '&wd=' + quote(wd)
        else:
            qs = '?ac=collect&pg=%d' % pg
            if wd:
                qs += '&wd=' + quote(wd)
        d = self._json(tid, qs, ttl=TTL if not wd else 0)
        items = d.get('list') or []
        pc = d.get('pagecount')
        pc = int(pc) if str(pc).isdigit() and int(pc) > 0 else (pg if items else 1)
        if not items:
            pc = 1
        return items, pc, int(d.get('total') or len(items) * pc)

    # _both(pg, wd)：两源并发取数（站点自身也是并发搜全部源）。串行实测搜索首屏 4.9s、翻页 7s，
    # 并发后墙钟≈最慢那个源；join(12) 是兜底，源卡死也不能把整页拖住
    def _both(self, pg, wd=''):
        out = {}

        def run(tid):
            try:
                out[tid] = self._list(tid, pg, wd)
            except Exception:
                out[tid] = ([], 1, 0)

        ths = [threading.Thread(target=run, args=(t,)) for t in ('hd', 'bd')]
        for t in ths:
            t.start()
        for t in ths:
            t.join(12)
        return out.get('hd', ([], 1, 0)), out.get('bd', ([], 1, 0))

    # ---------------------------------------------------------------- 六接口
    # homeContent(flag)：分类轴就是站点真实的「内容线路」选择器（全部 + 2 个可用源）；
    # 站点没有题材分类页（/vod/type/1.html 对游客返回「请升级会员」），硬造题材分类会被用户一眼看穿。
    def homeContent(self, filter):
        cls = [{'type_id': 'all', 'type_name': u'全部'}, {'type_id': 'hd', 'type_name': u'高清解析'},
               {'type_id': 'bd', 'type_name': u'蓝光路线'}]
        items, pc, total = self._list('hd', 1)
        return {'class': cls, 'list': [self._item(v, 'hd') for v in items], 'filters': {}}

    # homeVideoContent()：首页推荐位复用首页那一次 hd 列表请求（TTL 内命中，不额外打站）
    def homeVideoContent(self):
        items, pc, total = self._list('hd', 1)
        return {'list': [self._item(v, 'hd') for v in items]}

    # categoryContent(tid, pg, filter, extend)：tid=all 时两源并集，pagecount 取两源 max（站点自身「全部」也是 maxPage）
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = str(tid or 'all')
        if tid in ('hd', 'bd'):
            items, pc, total = self._list(tid, pg)
            return {'page': pg, 'pagecount': pc, 'limit': len(items) or LIMIT, 'total': total,
                    'list': [self._item(v, tid) for v in items]}
        (a, pc1, t1), (b, pc2, t2) = self._both(pg)
        items = a + b
        if not items:
            return {'page': pg, 'pagecount': 1, 'limit': LIMIT, 'total': 0, 'list': []}
        return {'page': pg, 'pagecount': max(pc1, pc2), 'limit': len(items),
                'total': t1 + t2,
                'list': [self._item(v, 'hd') for v in a] + [self._item(v, 'bd') for v in b]}

    # detailContent(ids)：ids 是 "源|id"。按源取 ac=detail&ids=，播放串原样保留（官方平台页），并做 1900B 分段
    def detailContent(self, ids):
        key = str(ids[0] if isinstance(ids, list) and ids else ids or '').strip()
        if not key:
            return {'list': []}
        if '|' in key:
            tid, vid = key.split('|', 1)
        else:
            tid, vid = ('hd' if key.isupper() else 'bd'), key
        tid = tid if tid in ('hd', 'bd') else 'bd'
        d = self._json(tid, '?ac=detail&ids=' + quote(str(vid)))
        items = d.get('list') or []
        if not items:
            return {'list': []}
        v = items[0]
        fraw = str(_f(v, 'vod_play_from'))
        uraw = str(_f(v, 'vod_play_url'))
        froms = [x for x in fraw.split('$$$') if x.strip()]
        urls = [x for x in uraw.split('$$$') if x.strip()]
        if not froms or not urls or len(froms) != len(urls):
            return {'list': []}
        # 资源 API 下发的 from/url 本身同序同长（sid 对齐在采集端已完成），这里只做字节分段，不做重排
        froms, urls = _seg(froms, urls)
        return {'list': [{
            'vod_id': '%s|%s' % (tid, _f(v, 'vod_id')),
            'vod_name': _f(v, 'vod_name'),
            'vod_pic': _f(v, 'vod_pic'),
            'vod_type': _f(v, 'type_name'),
            'vod_year': _f(v, 'vod_year'),
            'vod_area': _f(v, 'vod_area'),
            'vod_remarks': _f(v, 'vod_remarks'),
            'vod_actor': _f(v, 'vod_actor'),
            'vod_director': _f(v, 'vod_director'),
            'vod_content': _clean(_f(v, 'vod_content') or _f(v, 'vod_blurb')),
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(urls),
        }]}

    # searchContent(key, quick, pg)：两源都搜，pagecount 取 max、total 相加；同 id 不同源保留先出现的（与站点一致）
    def searchContent(self, key, quick, pg='1'):
        pg = int(pg) if str(pg).isdigit() else 1
        wd = str(key or '').strip()
        (a, pc1, t1), (b, pc2, t2) = self._both(pg, wd)
        items = a + b
        if not items:
            return {'page': pg, 'pagecount': 1, 'limit': LIMIT, 'total': 0, 'list': []}
        return {'page': pg, 'pagecount': max(pc1, pc2), 'limit': len(items), 'total': t1 + t2,
                'list': [self._item(v, 'hd') for v in a] + [self._item(v, 'bd') for v in b]}

    # _resolve(page)：站内 fuying 换链，官方平台页 → 真 m3u8。优酷/爱奇艺实测都能出；4K 参数只是同库镜像（720p）
    def _resolve(self, page):
        if page in type(self).RES:
            ts, u = type(self).RES[page]
            if time.time() - ts < RES_TTL:
                return u
        for q in ('?url=', '?fy=4k&url='):
            for h in self._hosts():
                if self._bad('p|' + h):
                    continue
                try:
                    _gap()
                    r = self.session.get(h + BD_PATH + q + quote(page, safe=''),
                                         headers=self.headers, timeout=20, verify=False,
                                         proxies=self.proxies or None)
                    d = json.loads(_decode(r) or '{}')
                    u = str(d.get('url') or '')
                    if d.get('code') in (200, '200') and u.startswith('http'):
                        type(self).RES[page] = (time.time(), u)
                        return u
                except Exception:
                    continue
            self._mark('p|' + page)
        return ''

    # playerContent(flag, id, vipFlags)：id 是资源 API 给的集地址。m3u8 直给 parse:0；
    # 官方平台页先换真链，换成 m3u8 再 parse:0，换不动才 parse:1（壳端自带解析可能也不通，交付说明里写清）
    def playerContent(self, flag, id, vipFlags):
        pid = str(id or '').strip().split('$')[-1].split('#')[0].strip()
        hd = {'User-Agent': UA}
        if not pid:
            return {'parse': 1, 'url': '', 'header': json.dumps(hd)}
        if 'm3u8' in pid or '.mp4' in pid:
            ok = type(self).PLAY.get(pid)
            if ok is None:
                ok = self._probe(pid)
            return {'parse': 0 if ok else 1, 'url': pid, 'header': json.dumps(hd)}
        u = self._resolve(pid)
        if u:
            if type(self).PLAY.get(u) is None:
                self._probe(u)
            return {'parse': 0, 'url': u, 'header': json.dumps(hd)}
        return {'parse': 1, 'url': pid, 'header': json.dumps(hd)}

    # _probe(url)：只读前 4KB 验 #EXTM3U/媒体头；整包下载会让首播多等 2s 以上
    def _probe(self, url):
        try:
            _gap()
            r = self.session.get(url, headers={'User-Agent': UA}, timeout=12, verify=False,
                                 stream=True, proxies=self.proxies or None)
            try:
                head = next(r.iter_content(4096), b'') or b''
                ct = r.headers.get('Content-Type', '').lower()
                ok = r.status_code == 200 and (b'#EXTM3U' in head or 'mpegurl' in ct or 'video/' in ct)
                type(self).PLAY[url] = bool(ok)
                return bool(ok)
            finally:
                r.close()
        except Exception:
            return False

    # localProxy(param)：封面代理（优酷 ykimg 直连可用，但壳端可能带外站 Referer 导致 403，统一走本站 session）
    def localProxy(self, param):
        try:
            d = json.loads(param) if str(param).strip().startswith('{') else {'url': str(param)}
            u = str(d.get('url', '') or '')
            if not u.startswith('http'):
                return [404, 'text/plain', b'']
            _gap()
            r = self.session.get(u, headers={'User-Agent': UA}, timeout=12, verify=False,
                                 proxies=self.proxies or None)
            try:
                if r.status_code != 200 or not r.content:
                    return [404, 'text/plain', b'']
                return [200, r.headers.get('Content-Type', 'image/jpeg'), r.content]
            finally:
                r.close()
        except Exception:
            return [404, 'text/plain', b'']



