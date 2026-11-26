# -*- coding: utf-8 -*-
"""
TVBox / 海阔 py 源 —— 水獭音乐 (otter-music.pages.dev)
==================================================
站点本身是个纯前端播放器（React SPA，曲库/歌单/收藏都在浏览器 localStorage 里），
页面 HTML 里没有任何歌曲数据，抓不到东西。但它背后用的是公开聚合接口，
实测下来这两套都能直连、不需要登录 / cookie / 签名：

  一、GD Studio 聚合接口（站点的主接口）
    GET https://music-api.gdstudio.xyz/api.php?types=search&source=netease&name=&count=&pages=
        搜索，返回 [{"id","name","artist":[],"album","pic_id","url_id","lyric_id"}]，
        count 一次最多给 50 条（pages=2 会 503，所以一次取 50 本地翻页）
    GET ...?types=url&source=netease&id=&br=320|999|192
        播放地址 {"url","br","size"}，999 = flac 无损；
        VIP / 版权受限的歌 url 为空串，得换源（下面用 joox 兜底）
    GET ...?types=lyric&source=netease&id=      LRC（自带时间轴，不用再找 QQ 配轴）
    GET ...?types=playlist&source=netease&id=   整张歌单（tracks 带 ar/al/dt + privileges）
    source 支持 netease / joox / bilibili，kuwo、qq、migu 这个部署上已下线

  二、网易云公开老接口（不用 weapi 加密，仍在服务）
    GET https://music.163.com/api/toplist/detail                全部榜单（65 个，含封面/更新频率）
    GET https://music.163.com/api/personalized/playlist?limit=  推荐歌单（limit 可给 100）
    GET https://music.163.com/api/personalized/newsong?limit=   新歌速递（limit 可给 100）
    GET https://music.163.com/api/song/detail?ids=[1,2,3]       批量歌曲详情（封面/时长/歌手）
    GET https://music.163.com/api/playlist/detail?id=           单张歌单
    注：/api/search/pc、/api/playlist/catalogue 已被风控（-462 要求验证），不能用

实测下来的实情（2026-11）：
  * 网易直链（m701/m801.music.126.net）带 Range 就能拉，206 audio/mpeg，
    带不带 UA 都行；flac 也是 audio/mpeg，播放器照常认；
  * 网易 url 接口对 VIP 曲（fee=1 且 pl=0）一律给空串，所以点播做了换源链：
    网易 320 → 网易 flac → 网易 192 → joox 按「歌名 歌手」精确匹配再取 320；
  * 搜索走 GD 聚合（网易自己的搜索被风控），结果再用 /api/song/detail 批量补封面、
    时长、付费标记，20 首一次请求，不用一条条查；
  * GD 接口偶发 503（限流），请求里带 2 次重试，失败不阻塞整页。

播放 = 点播时才解析（歌单动辄 200 首，详情页不可能逐首取链）：
详情页只给曲目表，点哪首解析哪首，直链缓存 10 分钟；单曲详情顺手预热一下。
歌词照旧做时间轴校验：LRC 结尾和音频时长对不上的（Live / 版本差异）不给字幕，
宁可不显示也不让词跟唱的内容错位。
"""
import base64
import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

try:
    import requests
except Exception:
    requests = None


GD = "https://music-api.gdstudio.xyz/api.php"
NE = "https://music.163.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CATS = [
    ("top", "热歌榜单"),
    ("rec", "推荐歌单"),
    ("new", "新歌速递"),
]
PAGE_SIZE = 20
SEARCH_COUNT = 50         # GD 搜索一次最多 50 条，pages=2 会 503，本地翻页
MP3_BRS = (320, 999, 192)  # 取链顺序：先 320，再试无损，最后 192

Q_SEARCH = ("https://c.y.qq.com/soso/fcgi-bin/client_search_cp?p=1&n=10&format=json&w=")
Q_LYRIC = ("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?songmid="
           "%s&format=json&nobase64=1")


class Spider(_BaseSpider):

    def getName(self):
        return "水獭音乐"

    def init(self, extend=""):
        self.timeout = 12
        self._list_cache = {}      # 列表 key -> (列表, 时间)
        self._pl_cache = {}        # 歌单 id -> (信息, 时间)
        self._url_cache = {}       # 歌曲 id -> (url, br, 时间)
        self._lrc_cache = {}       # 歌曲 id -> (lrc, 时间)
        self._joox_ids = {}        # 网易 id -> joox id（换源成功时记下，配同源歌词）
        self._sess = None
        if requests is not None:
            try:
                self._sess = requests.Session()
                self._sess.headers.update({"User-Agent": UA})
            except Exception:
                self._sess = None

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ------------------------------------------------------------------ 基础

    def _get(self, url, referer=None, timeout=None, retry=2):
        h = {"User-Agent": UA, "Accept": "*/*"}
        if referer:
            h["Referer"] = referer
        last = None
        for i in range(retry + 1):
            try:
                if self._sess is not None:
                    r = self._sess.get(url, headers=h, timeout=timeout or self.timeout)
                    if r.status_code == 200:
                        return r.text or ""
                    last = "HTTP %s" % r.status_code
                else:
                    req = urllib.request.Request(url, headers=h)
                    return urllib.request.urlopen(
                        req, timeout=timeout or self.timeout).read().decode("utf-8", "ignore")
            except Exception as e:
                last = e
            time.sleep(0.3 * (i + 1))          # 503 限流时退避，别硬怼
        print("水獭音乐 请求失败 %s: %s" % (url[:80], last))
        return ""

    def _json(self, url, referer=None, retry=2):
        txt = self._get(url, referer=referer, retry=retry)
        if not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None

    def _gd(self, params, retry=2):
        """GD Studio 聚合接口，偶发 503 靠重试扛。"""
        q = "&".join("%s=%s" % (k, urllib.parse.quote(str(v)))
                     for k, v in params.items())
        return self._json(GD + "?" + q, referer="https://music.gdstudio.xyz/", retry=retry)

    def _ne(self, path, retry=2):
        return self._json(NE + path, referer="https://music.163.com/", retry=retry)

    def _probe(self, url):
        """一次请求同时干两件事：确认音频能拉 + 拿总字节数。
        Range: bytes=0-1000，返回 (是否可用, 总字节)。"""
        if not url:
            return False, 0
        try:
            h = {"User-Agent": UA, "Range": "bytes=0-1000"}
            if self._sess is not None:
                r = self._sess.get(url, headers=h, timeout=8, allow_redirects=True, stream=True)
                code = r.status_code
                ctype = str(r.headers.get("Content-Type") or "").lower()
                cr = str(r.headers.get("Content-Range") or "")
                cl = str(r.headers.get("Content-Length") or "")
                r.close()
            else:
                resp = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=8)
                code = resp.getcode()
                ctype = str(resp.headers.get("Content-Type") or "").lower()
                cr = str(resp.headers.get("Content-Range") or "")
                cl = str(resp.headers.get("Content-Length") or "")
            ok = code in (200, 206) and ("audio" in ctype or "octet-stream" in ctype)
            total = cr.rsplit("/", 1)[-1] if "/" in cr else cl
            return ok, (int(total) if total.isdigit() else 0)
        except Exception:
            return False, 0

    @staticmethod
    def _clean(s):
        s = str(s or "").replace("&nbsp;", " ")
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    @staticmethod
    def _norm(s):
        return re.sub(r"[\s\-_·、,，.。!！?？'\"“”‘’()（）\[\]【】]", "", str(s or "")).lower()

    @staticmethod
    def _sim(a, b):
        """字符重合度：joox 是繁体库（說/说、倫/伦 写法不同），不能死比相等。"""
        a, b = str(a or ""), str(b or "")
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if len(a) >= 4 and (a in b or b in a):
            return 0.9
        return len(set(a) & set(b)) / float(max(len(set(a)), len(set(b))))

    @staticmethod
    def _pic(u, size=300):
        u = str(u or "").strip()
        if not u:
            return ""
        u = u.replace("http://", "https://", 1) if u.startswith("http://") else u
        if u.startswith("//"):
            u = "https:" + u
        if "music.126.net" in u and "?" not in u:
            u += "?param=%dy%d" % (size, size)
        return u if u.startswith("http") and len(u) > 18 else ""

    @staticmethod
    def _mmss(ms):
        sec = int(ms or 0) // 1000
        return "%02d:%02d" % (sec // 60, sec % 60) if sec > 0 else ""

    # ------------------------------------------------------------------ 编码

    @staticmethod
    def _b64(o):
        raw = json.dumps(o, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _unb64(s):
        s = str(s or "")
        try:
            return json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8"))
        except Exception:
            return {}

    # ------------------------------------------------------------------ 榜单 / 歌单 / 新歌

    def _toplists(self):
        """全部榜单（65 个），首页和「热歌榜单」分类共用。"""
        hit = self._list_cache.get("top")
        if hit and time.time() - hit[1] < 1800:
            return hit[0]
        j = self._ne("/api/toplist/detail")
        items = []
        for x in ((j or {}).get("list") or []):
            items.append({
                "pl": str(x.get("id") or ""),
                "n": self._clean(x.get("name")),
                "p": self._pic(x.get("coverImgUrl")),
                "d": " · ".join(z for z in (self._clean(x.get("updateFrequency")),
                                            "%d 首" % (x.get("trackCount") or 0)) if z),
            })
        if items:
            self._list_cache["top"] = (items, time.time())
        return items

    def _recommend(self):
        hit = self._list_cache.get("rec")
        if hit and time.time() - hit[1] < 1800:
            return hit[0]
        j = self._ne("/api/personalized/playlist?limit=100")
        items = []
        for x in ((j or {}).get("result") or []):
            items.append({
                "pl": str(x.get("id") or ""),
                "n": self._clean(x.get("name")),
                "p": self._pic(x.get("picUrl")),
                "d": "%d 首 · %s 次播放" % (x.get("trackCount") or 0,
                                          self._wan(x.get("playCount"))),
            })
        if items:
            self._list_cache["rec"] = (items, time.time())
        return items

    def _newsongs(self):
        hit = self._list_cache.get("new")
        if hit and time.time() - hit[1] < 900:
            return hit[0]
        j = self._ne("/api/personalized/newsong?limit=100&type=recommend")
        items = []
        for x in ((j or {}).get("result") or []):
            s = x.get("song") or {}
            if not s.get("id"):
                continue
            items.append({
                "sid": str(s.get("id")),
                "n": self._clean(s.get("name")),
                "a": "/".join(self._clean(z.get("name")) for z in (s.get("artists") or [])),
                "p": self._pic((s.get("album") or {}).get("picUrl")),
                "d": self._mmss(s.get("duration")),
                "fee": s.get("fee") or 0,
            })
        if items:
            self._list_cache["new"] = (items, time.time())
        return items

    @staticmethod
    def _wan(n):
        try:
            n = int(n or 0)
        except Exception:
            return "0"
        return ("%.1f 万" % (n / 10000.0)) if n >= 10000 else str(n)

    def _enrich(self, songs):
        """搜索结果补封面 / 时长 / 付费标记：一条 /api/song/detail 批量拿，不逐首查。"""
        ids = [s["sid"] for s in songs if s.get("sid") and not s.get("p")]
        if not ids:
            return songs
        j = self._ne("/api/song/detail?ids=[%s]" % ",".join(ids[:100]))
        meta = {}
        for s in ((j or {}).get("songs") or []):
            meta[str(s.get("id"))] = s
        for s in songs:
            m = meta.get(s["sid"])
            if not m:
                continue
            s["p"] = s["p"] or self._pic((m.get("album") or {}).get("picUrl"))
            s["d"] = s["d"] or self._mmss(m.get("duration"))
            s["fee"] = s.get("fee") or m.get("fee") or 0
        return songs

    # ------------------------------------------------------------------ 首页 / 分类 / 搜索

    def homeContent(self, filter=False):
        classes = [{"type_id": k, "type_name": n} for k, n in CATS]
        items = self._toplists()[:PAGE_SIZE]
        return {"class": classes, "filters": {}, "list": self._vods(items)}

    def homeVideoContent(self):
        return self.homeContent()

    def categoryContent(self, tid, pg, filter=False, extend=""):
        result = {"list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        tid = str(tid or "").strip()
        try:
            page = max(1, int(pg) if pg else 1)
        except (TypeError, ValueError):
            page = 1

        if tid == "rec":
            items = self._recommend()
        elif tid == "new":
            items = self._newsongs()
        else:
            items = self._toplists()
        total = len(items)
        pagecount = max(1, int(math.ceil(total / float(PAGE_SIZE)))) if total else 1
        page = min(page, pagecount)
        chunk = items[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

        result.update({
            "page": page,
            "pagecount": pagecount,
            "total": total,
            "limit": PAGE_SIZE,
            "list": self._vods(chunk),
        })
        return result

    def _vods(self, items):
        """榜单 / 歌单进详情展开成整张曲目，新歌直接当单曲。"""
        out = []
        for it in items:
            if it.get("pl"):
                tag = self._b64({"pl": it["pl"], "n": it["n"], "p": it.get("p") or ""})
                out.append({
                    "vod_id": tag,
                    "vod_name": it["n"],
                    "vod_pic": it.get("p") or "",
                    "vod_remarks": it.get("d") or "歌单",
                    "vod_content": "%s\n%s\n\n数据来自 网易云音乐（水獭音乐 otter-music 同源接口），"
                                   "进详情可整张连播。" % (it["n"], it.get("d") or ""),
                    "vod_play_from": "水獭音乐",
                    "vod_play_url": "%s$%s" % (it["n"], tag),
                })
            else:
                tag = self._b64({"sid": it["sid"], "n": it["n"],
                                 "a": it.get("a") or "", "p": it.get("p") or "",
                                 "vip": 1 if it.get("fee") in (1, 4) else 0})
                out.append({
                    "vod_id": tag,
                    "vod_name": it["n"],
                    "vod_pic": it.get("p") or "",
                    "vod_remarks": " · ".join(x for x in (it.get("d"), it.get("a")) if x),
                    "vod_actor": it.get("a") or "",
                    "vod_content": "%s\n%s\n\n数据来自 网易云音乐（水獭音乐 otter-music 同源接口），"
                                   "本页可直接播放。" % (it["n"], it.get("a") or "未知歌手"),
                    "vod_play_from": "水獭音乐",
                    "vod_play_url": "%s$%s" % (it["n"], tag),
                })
        return out

    def searchContent(self, key, quick=False, pg=1):
        result = {"list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        key = (key or "").strip()
        if not key:
            return result
        try:
            page = max(1, int(pg) if pg else 1)
        except (TypeError, ValueError):
            page = 1

        # GD 搜索一次取 50 条（pages=2 会 503），本地按 20 条翻页
        ck = "s:" + key
        hit = self._list_cache.get(ck)
        if hit and time.time() - hit[1] < 600:
            songs = hit[0]
        else:
            j = self._gd({"types": "search", "source": "netease", "name": key,
                          "count": SEARCH_COUNT, "pages": 1})
            songs = []
            for x in (j if isinstance(j, list) else []):
                songs.append({
                    "sid": str(x.get("id") or ""),
                    "n": self._clean(x.get("name")),
                    "a": "/".join(self._clean(z) for z in (x.get("artist") or [])),
                    "p": "",
                    "d": "",
                    "fee": 0,
                })
            songs = [s for s in songs if s["sid"]]
            if songs:
                self._enrich(songs)
                self._list_cache[ck] = (songs, time.time())
        total = len(songs)
        pagecount = max(1, int(math.ceil(total / float(PAGE_SIZE)))) if total else 1
        page = min(page, pagecount)
        chunk = songs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

        result.update({
            "page": page,
            "pagecount": pagecount,
            "total": total,
            "limit": PAGE_SIZE,
            "list": self._vods(chunk),
        })
        return result

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ------------------------------------------------------------------ 取链

    def _song_url(self, sid, name="", artist="", vip=0):
        """普通曲网易 320 → 无损 → 192；VIP 曲网易只试一次 320（必给空串），
        拿不到就换 joox。返回 (url, 码率标签)。点播时才调，歌单不为它等。"""
        sid = str(sid or "")
        hit = self._url_cache.get(sid)
        if hit and time.time() - hit[2] < 600:
            return hit[0], hit[1], hit[3]

        if vip:
            # VIP 曲网易大概率给空串，先快速试一次 320，再换 joox
            brs = (320,)
        else:
            brs = MP3_BRS
        for br in brs:
            j = self._gd({"types": "url", "source": "netease", "id": sid, "br": br})
            u = str((j or {}).get("url") or "")
            if not u.startswith("http"):
                continue
            ok, _size = self._probe(u)
            if not ok:
                continue
            got = int((j or {}).get("br") or br)
            label = "无损 FLAC" if got >= 700 else "%dK" % (got // 1000 if got > 1000 else got)
            self._url_cache[sid] = (u, label, time.time(), _size)
            return u, label, _size

        u, label, jid = self._joox_url(name, artist)
        if u:
            size = self._probe(u)[1]
            self._url_cache[sid] = (u, label, time.time(), size)
            if jid:
                self._joox_ids[sid] = jid
            return u, label, size
        return "", "", 0

    def _joox_url(self, name, artist):
        """网易拿不到（VIP / 无版权）时按「歌名 歌手」去 joox 找同一首。
        joox 是繁体库，名字按字符重合度匹配；伴奏 / 纯音乐 / 翻唱版本跳过。
        返回 (url, 标签, joox 歌曲 id)。"""
        if not name:
            return "", "", ""
        want = self._norm(name)
        wa = self._norm((artist or "").split("/")[0])
        j = self._gd({"types": "search", "source": "joox",
                      "name": ("%s %s" % (name, artist)).strip(),
                      "count": 10, "pages": 1})
        bad = ("伴奏", "純音樂", "纯音乐", "cover", "翻唱", "remix", "dj版")
        want_bad = any(b in want.lower() for b in bad)

        picks = []
        for idx, x in enumerate(j if isinstance(j, list) else []):
            nm = self._norm(x.get("name"))
            ar = "/".join(self._clean(a) for a in (x.get("artist") or []))
            s_name = self._sim(nm, want)
            if s_name < 0.75:
                continue
            if wa and self._sim(self._norm(ar), wa) < 0.5:
                continue
            if not want_bad and any(b in nm.lower() for b in bad):
                continue
            # 同名同歌手优先，其次按相似度、原始顺序
            picks.append((0 if s_name == 1.0 else 1, -s_name, idx, x))
        picks.sort()
        for _a, _b, _i, x in picks[:2]:
            g = self._gd({"types": "url", "source": "joox",
                          "id": x.get("url_id") or x.get("id"), "br": 320})
            u = str((g or {}).get("url") or "")
            if u.startswith("http") and self._probe(u)[0]:
                return u, "joox 320K", str(x.get("url_id") or x.get("id") or "")
        return "", "", ""

    # ------------------------------------------------------------------ 歌词

    def _lrc_of(self, sid, name="", artist=""):
        """歌词：网易（同 id，版本最稳）→ QQ 按歌名歌手兜底。
        joox 换源的曲子另有用 _lrc_gd("joox") 取同源歌词，在详情里覆盖。"""
        sid = str(sid or "")
        hit = self._lrc_cache.get(sid)
        if hit and time.time() - hit[1] < 604800:
            return hit[0]
        lrc = self._lrc_gd("netease", sid)
        if lrc is None:
            lrc = ""                      # 接口抽风，这次先不给词，别拖慢详情
        elif not lrc and name:
            lrc = self._lrc_qq(name, artist)
        if lrc:
            self._lrc_cache[sid] = (lrc, time.time())
        return lrc

    def _lrc_gd(self, source, sid):
        """返回 None = 请求本身失败（限流 / 超时），"" = 接口说没词。
        两者分开，失败时不要再去叠 QQ 的慢链路。"""
        j = self._gd({"types": "lyric", "source": source, "id": str(sid or "")})
        if j is None:
            return None
        return self._tidy_lrc(str((j or {}).get("lyric") or ""))

    def _lrc_qq(self, name, artist):
        """网易没词时按「歌名 歌手」去 QQ 匹配，别让字幕整首空着。"""
        want, wa = self._norm(name), self._norm(str(artist or "").split("/")[0])
        j = self._json(Q_SEARCH + urllib.parse.quote(("%s %s" % (name, artist)).strip()),
                       referer="https://y.qq.com/")
        cands = []
        for x in ((((j or {}).get("data") or {}).get("song") or {}).get("list") or []):
            ar = "/".join((z or {}).get("name") or "" for z in (x.get("singer") or []))
            score = 2 if self._norm(x.get("songname")) == want else 0
            if wa and wa in self._norm(ar):
                score += 4
            cands.append((score, str(x.get("songmid") or "")))
        cands.sort(reverse=True)
        for _sc, mid in cands[:2]:
            if not mid:
                continue
            j2 = self._json(Q_LYRIC % mid, referer="https://y.qq.com/")
            lrc = self._tidy_lrc(str((j2 or {}).get("lyric") or ""))
            if lrc:
                return lrc
        return ""

    @staticmethod
    def _tidy_lrc(txt):
        """去元信息行；[offset:±毫秒] 不能直接扔，整段平移时间轴再去标签。"""
        offset = 0
        om = re.search(r"^\[offset:\s*([+-]?\d+)\s*\]", txt or "", re.I | re.M)
        if om:
            try:
                offset = int(om.group(1))
            except Exception:
                offset = 0
        keep = []
        for line in (txt or "").splitlines():
            if not line.strip():
                continue
            if re.match(r"^\[(offset|ti|ar|al|by|length|re|ve|kana)\s*:", line, re.I):
                continue
            if Spider._is_meta(line):
                continue
            keep.append(Spider._shift_ts(line, offset) if offset else line)
        return "\n".join(Spider._dedup(keep))

    # 制作信息关键词（含「商务统筹」「制作统筹」这种组合词，用包含判断而不是前缀）
    META_KW = ("演唱", "歌手", "作词", "作曲", "词曲", "编曲", "填词", "谱曲", "制作", "监制",
               "出品", "录音", "混音", "母带", "吉他", "贝斯", "鼓", "键盘", "和声",
               "弦乐", "统筹", "企划", "策划", "发行", "录音棚", "音频编辑", "项目总监",
               "商务", "宣推", "OP", "SP")

    @classmethod
    def _is_meta(cls, line):
        """「演唱 : 赵本山」「商务统筹 : xxx」这种制作信息不是歌词，别占字幕时间。"""
        body = re.sub(r"^(\[[^\]]*\])+", "", line).strip()
        if not body:
            return True
        # 「【本音乐作品已获得正版授权】」这类声明行也不是歌词
        if re.match(r"^【[^】]{0,24}】$", body) and re.search(r"授权|正版|版权", body):
            return True
        # 平台占位文案（纯音乐 / 无歌词）也别当字幕
        if len(body) <= 60 and re.search(r"没有填词|纯音乐|请您欣赏|暂无歌词|该歌曲|"
                                         r"instrumental|no lyrics|please enjoy", body, re.I):
            return True
        m = re.match(r"^([^:：]{1,8})\s*[:：]", body)
        if not m:
            return False
        head = m.group(1).strip()
        return any(kw.lower() in head.lower() for kw in cls.META_KW)

    @staticmethod
    def _dedup(lines):
        """同一时间点同一句重复出现的去重；不同时间的副歌重复要保留。"""
        seen, out = set(), []
        for line in lines:
            ts = (re.match(r"^\[([^\]]*)\]", line) or [None, ""])[1]
            body = re.sub(r"^(\[[^\]]*\])+", "", line).strip()
            key = (ts, body)
            if body and key in seen:
                continue
            if body:
                seen.add(key)
            out.append(line)
        return out

    @staticmethod
    def _shift_ts(line, offset):
        """给一行里所有时间戳加 offset 毫秒（负值截到 0）。"""
        def rep(m):
            total = (int(m.group(1)) * 60 + int(m.group(2))) * 1000
            frac = m.group(3)
            if frac:
                total += int(frac) * (10 if len(frac) == 2 else (1 if len(frac) == 3 else 100))
            total = max(0, total + int(offset))
            return "[%02d:%02d.%03d]" % (total // 60000, total // 1000 % 60, total % 1000)
        return re.sub(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]", rep, line)

    @staticmethod
    def _lrc_ok(lrc, dur):
        """时间轴校验：整首词比音频长出来一截、或者唱完太早收尾的，都当版本不符。"""
        first = last = 0
        for m in re.finditer(r"\[(\d{1,2}):(\d{2})(?:[.:]\d{1,3})?\]", lrc or ""):
            t = int(m.group(1)) * 60 + int(m.group(2))
            if not first:
                first = t
            last = t
        dur = int(dur or 0)
        if not last:
            return False
        if not dur:
            return True
        return first <= dur * 0.55 and dur * 0.45 <= last <= dur + 8

    # ------------------------------------------------------------------ 详情 / 播放

    def detailContent(self, ids):
        result = {"list": []}
        tag = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        t = self._unb64(tag)

        # ---- 榜单 / 歌单：展开成整张曲目 ----
        if t.get("pl"):
            pid = str(t["pl"])
            hit = self._pl_cache.get(pid)
            if hit and time.time() - hit[1] < 1800:
                info = hit[0]
            else:
                # 网易老接口 0.3s 就回来，GD 聚合要 4s，先用快的
                j = self._ne("/api/playlist/detail?id=%s" % urllib.parse.quote(pid))
                pl = ((j or {}).get("result") or {})
                info = {"name": self._clean(pl.get("name")),
                        "cover": self._pic(pl.get("coverImgUrl")),
                        "desc": self._clean(pl.get("description"))[:200],
                        "songs": []}
                for s in (pl.get("tracks") or []):
                    sid = str(s.get("id") or "")
                    if not sid:
                        continue
                    fee = s.get("fee")
                    info["songs"].append({
                        "sid": sid,
                        "n": self._clean(s.get("name")),
                        "a": "/".join(self._clean(z.get("name"))
                                      for z in (s.get("artists") or [])),
                        "p": self._pic((s.get("album") or {}).get("picUrl")),
                        "d": self._mmss(s.get("duration")),
                        # fee 1/4 = VIP 或付费专辑，网易必不给链，直接走换源
                        "vip": 1 if (fee in (1, 4) or s.get("noCopyrightRcmd")) else 0,
                    })
                if info["songs"]:
                    self._pl_cache[pid] = (info, time.time())
            name = info.get("name") or t.get("n") or "歌单"
            eps = []
            for idx, s in enumerate(info["songs"], 1):
                sub = self._b64({"sid": s["sid"], "n": s["n"], "a": s["a"],
                                 "p": s["p"], "vip": s.get("vip") or 0})
                eps.append("%02d %s%s$%s" % (idx, s["n"], " [VIP]" if s.get("vip") else "", sub))
            n_vip = len([x for x in info["songs"] if x.get("vip")])
            vod = {
                "vod_id": tag,
                "vod_name": name,
                "vod_pic": info.get("cover") or t.get("p") or "",
                "vod_remarks": "%d 首%s" % (len(info["songs"]),
                                           "（%d 首需换源）" % n_vip if n_vip else ""),
                "vod_content": "%s\n共 %d 首，数据来自 网易云音乐（水獭音乐同源接口）。\n"
                               "选集即播，VIP 曲会自动去 joox 找同款。"
                               % (name, len(info["songs"])),
                "vod_play_from": "水獭音乐",
                "vod_play_url": "#".join(eps) if eps else "%s$%s" % (name, tag),
            }
            result["list"].append(vod)
            return result

        # ---- 单曲 ----
        sid = str(t.get("sid") or "")
        if not sid:
            return result
        name0 = t.get("n") or ("歌曲 %s" % sid)
        artist0 = t.get("a") or ""

        # 直链 / 歌词两路并发：列表里就带着歌名歌手，不用先查详情页
        box = {}

        def do_url():
            try:
                box["url"] = self._song_url(sid, name0, artist0, t.get("vip") or 0)
            except Exception:
                box["url"] = ("", "", 0)

        def do_lrc():
            try:
                box["lrc"] = self._lrc_of(sid, name0, artist0)
            except Exception:
                box["lrc"] = ""

        threads = []
        for fn in (do_url, do_lrc):
            th = threading.Thread(target=fn)
            th.daemon = True
            th.start()
            threads.append(th)
        for th in threads:
            th.join(12)

        u, label, size = box.get("url") or ("", "", 0)
        lrc = box.get("lrc") or ""
        # 换源到 joox 的曲子，歌词也用 joox 同源的（版本才对得上）
        jid = self._joox_ids.get(sid)
        if jid and "joox" in label:
            j_lrc = self._lrc_gd("joox", jid)
            if j_lrc:
                lrc = j_lrc
        dur = size * 8 // (797000 if "FLAC" in label else 320000) if size else 0
        lrc_ok = self._lrc_ok(lrc, dur)

        lines = [name0, artist0 or "未知歌手", ""]
        if u:
            lines.append("音质：%s　%s" % (label or "未知", self._mmss(dur * 1000) if dur else ""))
            lines.append("点播放即可；直链有时效，过期会自动重取，VIP 曲自动换源。")
        else:
            lines.append("这首网易 / joox 都没拿到可播地址（多为独家版权），换一首试试。")
        if lrc_ok:
            lines.append("")
            lines.append("歌词：已匹配滚动歌词，播放时同步显示。")
        elif lrc:
            lines.append("")
            lines.append("有歌词文本，但时间轴和音频对不上（版本差异），没有启用同步字幕。")

        eps = []
        if u:
            sub = self._b64({"sid": sid, "n": name0, "a": artist0, "vip": t.get("vip") or 0,
                             "u": u, "t": int(time.time())})
            eps.append("%s$%s" % (name0, sub))
        else:
            eps.append("%s$%s" % (name0, tag))

        vod = {
            "vod_id": tag,
            "vod_name": name0,
            "vod_pic": t.get("p") or "",
            "vod_remarks": " · ".join(x for x in (artist0, label,
                                                 self._mmss(dur * 1000) if dur else "") if x),
            "vod_actor": artist0,
            "vod_content": "\n".join(lines),
            "vod_play_from": "水獭音乐",
            "vod_play_url": "#".join(eps),
        }
        if lrc and lrc_ok:
            try:
                vod["vod_sub"] = "data:text/plain;charset=utf-8;base64," + base64.b64encode(
                    self._lrc_to_ssa(lrc).encode("utf-8")).decode()
            except Exception:
                pass
        result["list"].append(vod)
        return result

    def playerContent(self, flag, id, vipFlags=None):
        result = {"parse": 0, "playUrl": "", "url": "", "header": "", "title": "水獭音乐"}
        t = self._unb64(id)
        if not t.get("sid"):
            result["parse"] = 1
            return result

        header = json.dumps({"User-Agent": UA})    # 网易直链不需要 Referer

        # 详情页已取好的直链，15 分钟内直接给（签名有时效，过期重取）
        u = str(t.get("u") or "")
        if u and time.time() - (t.get("t") or 0) < 900:
            result.update({"url": u, "header": header})
            return result
        u2, _label, _size = self._song_url(str(t["sid"]), str(t.get("n") or ""),
                                           str(t.get("a") or ""), t.get("vip") or 0)
        if u2:
            result.update({"url": u2, "header": header})
            return result
        result["parse"] = 1
        return result

    # ------------------------------------------------------------------ 歌词 LRC -> SSA

    @staticmethod
    def _lrc_to_ssa(lrc):
        rows = []
        for line in (lrc or "").splitlines():
            m = re.match(r"^\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\](.*)$", line.strip())
            if not m:
                continue
            ms = (int(m.group(1)) * 60 + int(m.group(2))) * 1000
            frac = m.group(3) or "0"
            ms += int(frac) * (10 if len(frac) == 2 else (1 if len(frac) == 3 else 100))
            txt = m.group(4).strip()
            if txt:
                rows.append((ms, txt))
        if not rows:
            return ""
        head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n"
                "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
                "[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                "Style: Default,微软雅黑,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
                "0,0,0,0,100,100,0,0,1,2,1,2,30,30,50,1\n\n"
                "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        out = []
        for i, (ms, txt) in enumerate(rows):
            end = rows[i + 1][0] if i + 1 < len(rows) else ms + 5000
            if end <= ms:
                end = ms + 3000
            out.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s" % (
                Spider._ass_t(ms), Spider._ass_t(end), txt.replace("\n", "\\N")))
        return head + "\n".join(out) + "\n"

    @staticmethod
    def _ass_t(ms):
        ms = max(0, int(ms))
        return "%d:%02d:%02d.%02d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000 // 10)
