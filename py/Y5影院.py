# coding=utf-8
import sys
import json
import time
import uuid
import hashlib
import re
import base64
import urllib.parse

import urllib.request

try:
    import html as _html
except Exception:
    _html = None

try:
    import requests
except Exception:
    requests = None

from base.spider import Spider


class Spider(Spider):

    def getName(self):
        return "Y5影院"

    def init(self, extend=""):
        self.host = "https://m.jysct15.com"
        self.api = self.host + "/mw-movie"
        self.sign_key = "cb808529bae6b6be45ecfab29a4889bc"
        self.ua = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
        self.pagesize = 30
        self.extend = extend or ""
        cfg = {}
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
            except Exception:
                cfg = {}
        self.device_id = str(cfg.get("deviceId") or uuid.uuid4())
        self.quality = int(cfg.get("quality") or 1080)
        self.use_proxy = int(cfg.get("proxy") or 0)
        self.headers = {
            "User-Agent": self.ua,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": self.host + "/",
            "Origin": self.host,
            "client-type": "3",
            "deviceId": self.device_id,
        }

    def _sign(self, params):
        clean = {}
        for k, v in params.items():
            if v is None or v == "" or v == "null" or v == "undefined":
                continue
            clean[k] = v
        t = int(time.time() * 1000)
        p = "&".join("%s=%s" % (k, clean[k]) for k in sorted(clean))
        s = "key=%s&t=%d" % (self.sign_key, t)
        if p:
            s = p + "&" + s
        sign = hashlib.sha1(hashlib.md5(s.encode("utf-8")).hexdigest().encode("utf-8")).hexdigest()
        return clean, t, sign

    def _api(self, path, params=None):
        params = params or {}
        clean, t, sign = self._sign(params)
        h = dict(self.headers)
        h["sign"] = sign
        h["t"] = str(t)
        url = self.api + path
        if requests is not None:
            try:
                r = requests.get(url, params=clean, headers=h, timeout=20, verify=False)
                return r.json()
            except Exception:
                return None
        try:
            q = urllib.parse.urlencode(clean)
            if q:
                url = url + "?" + q
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception:
            return None

    def _get_bytes(self, url, headers=None, maxbytes=None):
        h = {"User-Agent": self.ua, "Referer": self.host + "/"}
        if headers:
            h.update(headers)
        if requests is not None:
            try:
                r = requests.get(url, headers=h, timeout=25, verify=False, stream=bool(maxbytes))
                ctype = r.headers.get("Content-Type", "")
                if maxbytes:
                    data = b""
                    for chunk in r.iter_content(2048):
                        data += chunk
                        if len(data) >= maxbytes:
                            break
                    return r.status_code, ctype, data
                return r.status_code, ctype, r.content
            except Exception:
                return 0, "", b""
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=25) as resp:
                body = resp.read(maxbytes) if maxbytes else resp.read()
                return resp.getcode(), resp.headers.get("Content-Type", ""), body
        except Exception as e:
            code = 0
            try:
                code = int(getattr(e, "code", 0) or 0)
            except Exception:
                code = 0
            return code, "", b""

    def _probe(self, url):
        st, _, _ = self._get_bytes(url, {"Range": "bytes=0-511", "Accept": "*/*"}, maxbytes=512)
        return st

    def _proxy_url(self, url, mode="ts", extra=None):
        d = {
            "do": "py", "type": mode,
            "u": base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8"),
        }
        if extra:
            for k, v in extra.items():
                if v:
                    d[k] = v
        return "http://127.0.0.1:9978/proxy?" + urllib.parse.urlencode(d)

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.split("?")[0].lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".ts", ".mkv", ".avi", ".mov"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return "destroy"

    def _clean(self, s):
        if not s:
            return ""
        s = str(s)
        s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", s)
        s = re.sub(r"(?i)<br\s*/?>", "\n", s)
        s = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)\s*>", "\n", s)
        s = re.sub(r"(?i)<(p|div|li|h[1-6]|tr)[^>]*>", "\n", s)
        s = re.sub(r"<[^>]+>", "", s)
        s = s.replace("\r", "")
        if _html is not None:
            try:
                s = _html.unescape(s)
            except Exception:
                pass
        s = s.replace("\u00a0", " ").replace("\u3000", " ")
        lines = []
        for ln in s.split("\n"):
            ln = re.sub(r"[ \t]+", " ", ln).strip()
            lines.append(ln)
        s = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", s).strip()

    def _vod(self, it):
        vod_id = str(it.get("vodId") or "")
        name = it.get("vodName") or ""
        pic = it.get("vodPic") or it.get("vodPicSlide") or it.get("bgImage") or ""
        remarks = it.get("vodRemarks") or ""
        if not remarks:
            total = it.get("vodTotal") or 0
            serial = it.get("vodSerial") or ""
            if total and serial:
                remarks = "%s/%s" % (serial, total)
        if not remarks:
            remarks = it.get("vodVersion") or ""
        year = str(it.get("vodYear") or "")
        if not year:
            year = str(it.get("vodPubdate") or "")[:4]
        score = it.get("vodScore")
        if score in (None, ""):
            score = it.get("vodDoubanScore")
        return {
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_year": year,
            "vod_area": it.get("vodArea") or "",
            "vod_actor": it.get("vodActor") or "",
            "vod_director": it.get("vodDirector") or "",
            "vod_score": str(score if score is not None else ""),
            "vod_lang": it.get("vodLang") or "",
            "vod_content": self._clean(it.get("vodContent") or it.get("vodBlurb") or ""),
            "type_name": it.get("vodClass") or it.get("typeName") or it.get("type") or "",
        }

    def _list_of(self, data):
        if isinstance(data, dict):
            return data.get("list") or []
        if isinstance(data, list):
            return data
        return []

    def homeContent(self, filter=False):
        classes = []
        filters = {}
        r = self._api("/anonymous/get/filer/type", {"clientType": 3})
        if r and r.get("data"):
            for it in r["data"]:
                if it.get("typeJumpurl"):
                    continue
                tid = str(it.get("typeId"))
                classes.append({"type_id": tid, "type_name": it.get("typeName") or tid})
                f = []
                g = self._api("/anonymous/get/filer/getClassByType", {"type1": it.get("typeId")})
                if g and g.get("data"):
                    items = [{"n": "全部", "v": ""}]
                    for c in g["data"]:
                        if c.get("dictCode") == "FILTER_PLOT" and c.get("itemText"):
                            items.append({"n": c["itemText"], "v": c["itemText"]})
                    if len(items) > 1:
                        f.append({"key": "class", "name": "剧情", "value": items})
                if f:
                    filters[tid] = f

        videos = []
        r2 = self._api("/anonymous/rank/all", {"clientType": 3, "pageNum": 1})
        if r2 and isinstance(r2.get("data"), dict):
            seen = set()
            for k in ("movieRank", "tvRank", "varietyRank", "cartoonRank", "shortTvRank"):
                for it in (r2["data"].get(k) or []):
                    vid = str(it.get("vodId"))
                    if vid in seen:
                        continue
                    seen.add(vid)
                    v = self._vod(it)
                    if v["vod_pic"]:
                        videos.append(v)
                    if len(videos) >= 24:
                        break
                if len(videos) >= 24:
                    break
        if not videos:
            r3 = self._api("/anonymous/video/list", {"type1": 1, "pageNum": 1, "pageSize": 12})
            videos = [self._vod(x) for x in self._list_of((r3 or {}).get("data"))]

        out = {"class": classes, "list": videos}
        if filters:
            out["filters"] = filters
        return out

    def homeVideoContent(self):
        videos = []
        r = self._api("/anonymous/home/banner", {"clientType": 3, "typeId": 1})
        if r and isinstance(r.get("data"), list):
            for it in r["data"]:
                vd = it.get("videoData") or {}
                if vd.get("vodId"):
                    videos.append(self._vod(vd))
        if not videos:
            r2 = self._api("/anonymous/rank/all", {"clientType": 3, "pageNum": 1})
            d = (r2 or {}).get("data") or {}
            if isinstance(d, dict):
                for it in (d.get("movieRank") or [])[:20]:
                    videos.append(self._vod(it))
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "1")
        page = int(pg or 1)
        params = {"pageNum": page, "pageSize": self.pagesize}
        if "_" in tid:
            t1, cls = tid.split("_", 1)
            params["type1"] = t1
            if cls:
                params["v_class"] = cls
        else:
            params["type1"] = tid
        ext = {}
        if isinstance(extend, dict):
            ext = extend
        elif isinstance(extend, str) and extend:
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        if ext.get("class"):
            params["v_class"] = ext["class"]
        if ext.get("area"):
            params["area"] = ext["area"]
        if ext.get("year"):
            params["year"] = ext["year"]
        if ext.get("lang"):
            params["lang"] = ext["lang"]

        r = self._api("/anonymous/video/list", params)
        data = (r or {}).get("data") or {}
        lst = [self._vod(x) for x in self._list_of(data)]
        return {
            "list": lst,
            "page": page,
            "pagecount": int(data.get("totalPage") or 0),
            "limit": int(data.get("pageSize") or self.pagesize),
            "total": int(data.get("totalCount") or 0),
        }

    def detailContent(self, ids):
        vod_id = str(ids[0] if isinstance(ids, (list, tuple)) else ids).split("/")[0].strip()
        r = self._api("/anonymous/video/detail", {"id": vod_id})
        d = (r or {}).get("data")
        if not d:
            return {"list": []}
        v = self._vod(d)
        v["vod_id"] = str(d.get("vodId") or vod_id)
        v["vod_content"] = self._clean(d.get("vodContent") or d.get("vodBlurb") or "")
        v["type_name"] = d.get("typeName") or d.get("vodClass") or ""
        v["vod_content"] = self._clean(d.get("vodContent") or d.get("vodBlurb") or "")
        v["vod_year"] = str(d.get("vodYear") or v.get("vod_year") or "")
        v["vod_area"] = d.get("vodArea") or v.get("vod_area") or ""
        v["vod_lang"] = d.get("vodLang") or v.get("vod_lang") or ""
        v["vod_actor"] = d.get("vodActor") or v.get("vod_actor") or ""
        v["vod_director"] = d.get("vodDirector") or v.get("vod_director") or ""
        remark = str(d.get("vodRemarks") or "").strip()
        total = int(d.get("vodTotal") or 0)
        serial = int(d.get("vodSerial") or 0)
        m = re.match(r"^[（(]?\s*(\d+)\s*/\s*(\d+)\s*[)）]?$", remark)
        if m:
            serial, total = int(m.group(1)), int(m.group(2))
            remark = ""
        if not remark and total:
            if serial and serial < total:
                remark = "更新至%d集/共%d集" % (serial, total)
            elif serial and serial >= total:
                remark = "全%d集" % total
            else:
                remark = "共%d集" % total
        if remark:
            v["vod_remarks"] = remark
        if not v["vod_remarks"] and d.get("vodVersion"):
            v["vod_remarks"] = str(d.get("vodVersion"))

        eps = d.get("episodeList") or []
        names = []
        flags = []
        for i, ep in enumerate(eps):
            nid = ep.get("nid")
            if not nid:
                continue
            raw = (ep.get("name") or "").strip()
            if len(eps) == 1:
                nm = "正片"
            elif not raw:
                nm = "第%d集" % (i + 1)
            elif raw.isdigit():
                nm = "第%s集" % raw
            else:
                nm = raw
            names.append(nm)
            flags.append("jys://%s/%s" % (v["vod_id"], nid))
        if not names:
            return {"list": []}
        v["vod_play_from"] = "Y5影院"
        v["vod_play_url"] = "#".join("%s$%s" % (n, f) for n, f in zip(names, flags))
        return {"list": [v]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        params = {"keyword": key, "pageNum": page, "pageSize": self.pagesize}
        r = self._api("/anonymous/video/searchByWordPageable", params)
        data = (r or {}).get("data") or {}
        lst = [self._vod(x) for x in self._list_of(data)]
        return {"list": lst, "page": page}

    def _resolve_episode(self, vid, nid):
        r = self._api("/anonymous/v2/video/episode/url",
                      {"clientType": 3, "id": vid, "nid": nid})
        data = (r or {}).get("data") or {}
        lst = data.get("list") or []
        cands = [it for it in lst if it.get("url")]
        if not cands:
            return None, []
        best = None
        for it in cands:
            try:
                res = int(it.get("resolution") or 0)
            except Exception:
                res = 0
            if res <= self.quality:
                if best is None or res > int(best.get("resolution") or 0):
                    best = it
        if best is None:
            best = min(cands, key=lambda x: int(x.get("resolution") or 0))
        return best, lst

    def playerContent(self, flag, id, vipFlags=None):
        play_url = ""
        vid, nid = None, None
        cands = []
        for x in (id, flag):
            if x is None:
                continue
            s = str(x).strip()
            if s:
                cands.append(s)
        for s in cands:
            if s.startswith("jys://"):
                body = s[len("jys://"):]
                parts = body.split("/")
                if len(parts) >= 2:
                    vid, nid = parts[0].strip(), parts[1].strip()
                if vid and nid:
                    break
        if not vid or not nid:
            for s in cands:
                if s.startswith("http://") or s.startswith("https://"):
                    play_url = s
                    break
        if not play_url and vid and nid:
            best, _ = self._resolve_episode(vid, nid)
            if best:
                play_url = best.get("url") or ""
        if not play_url:
            return {"parse": 0, "playUrl": "", "url": "", "header": "", "jx": 0}

        header = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Accept": "*/*",
            "Origin": self.host,
        }
        result = {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": header,
            "jx": 0,
        }
        if not self.use_proxy:
            st = self._probe(play_url)
            if st in (401, 403, 410):
                self.use_proxy = 1
        if self.use_proxy:
            extra = {"pn": "%s/%s" % (vid, nid)} if (vid and nid) else None
            result["url"] = self._proxy_url(play_url, "m3u8", extra)
        return result

    def localProxy(self, param):
        p = {}
        if isinstance(param, dict):
            p = dict(param)
        elif isinstance(param, str):
            p = {k: v[0] for k, v in urllib.parse.parse_qs(param).items()}
        mode = (p.get("type") or p.get("mode") or "m3u8").lower()
        u = p.get("u") or p.get("url") or ""
        if u and not u.startswith("http"):
            try:
                u = base64.urlsafe_b64decode(u.encode("utf-8") + b"=" * (-len(u) % 4)).decode("utf-8")
            except Exception:
                pass
        if not u and p.get("play"):
            try:
                vid, nid = str(p["play"]).split("/")[:2]
            except Exception:
                vid, nid = "", ""
            best, _ = self._resolve_episode(vid, nid)
            if best:
                u = best.get("url") or ""
        if not u:
            return [404, "text/plain", "no url"]

        status, ctype, body = self._get_bytes(u)
        if (status != 200 or not body) and p.get("pn"):
            pn = str(p.get("pn")).split("/")
            if len(pn) >= 2:
                best, _ = self._resolve_episode(pn[0], pn[1])
                if best and best.get("url"):
                    u2 = best["url"]
                    st2, ct2, bd2 = self._get_bytes(u2)
                    if st2 == 200 and bd2:
                        u, status, ctype, body = u2, st2, ct2, bd2
        if status != 200 or not body:
            return [502, "text/plain", "upstream %s" % status]

        if mode in ("img",):
            return [200, ctype or "image/webp", body]
        if mode in ("ts", "seg", "key", "segkey"):
            return [200, ctype or "application/octet-stream", body]

        text = body.decode("utf-8", "ignore")
        if "#EXTM3U" not in text:
            return [200, ctype or "application/octet-stream", body]

        wrap = bool(getattr(self, "use_proxy", 0))

        def _wrap_seg(target):
            if not wrap:
                return target
            m2 = "m3u8" if target.split("?")[0].lower().endswith(".m3u8") else "ts"
            return self._proxy_url(target, m2)

        lines = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                lines.append(line)
                continue
            if s.startswith("#"):
                def _abs(m):
                    val = m.group(1)
                    if not val.startswith("http"):
                        val = urllib.parse.urljoin(u, val)
                    return 'URI="%s"' % _wrap_seg(val)
                s = re.sub(r'URI="([^"]+)"', _abs, s)
                lines.append(s)
            elif s.startswith("http"):
                lines.append(_wrap_seg(s))
            else:
                lines.append(_wrap_seg(urllib.parse.urljoin(u, s)))
        return [200, "application/vnd.apple.mpegurl", "\n".join(lines)]