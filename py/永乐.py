# -*- coding: utf-8 -*-
"""
TVBox Python 爬虫插件 - www.xz8.cc (永乐视频)

"""
import re
import json
import time
import html as html_lib
from urllib.parse import quote

from base.spider import Spider as BaseSpider
import requests
import base64


class Spider(BaseSpider):

    # ==================== 基础配置 ====================
    HOST = "https://www.xz8.cc"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/122.0.0.0 Safari/537.36")

    def init(self, extend=""):
        self.extend = extend or ""
        self.session = None
        try:
            import requests
            self.session = requests.Session()
            self.session.headers.update(self._headers())
        except Exception:
            self.session = None

    # ==================== 通用工具 ====================
    def _headers(self, referer=None):
        return {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Referer": referer or (self.HOST + "/"),
        }

    def _get(self, url, referer=None, timeout=15):
        try:
            if self.session is not None:
                r = self.session.get(url, headers=self._headers(referer), timeout=timeout)
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text or ""
            import requests
            r = requests.get(url, headers=self._headers(referer), timeout=timeout)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text or ""
        except Exception as e:
            print("[_get error]", url, e)
            return ""

    @staticmethod
    def _soup(html):
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html, "html.parser")
        except Exception:
            return None

    @staticmethod
    def _clean(s):
        if s is None:
            return ""
        s = str(s)
        s = re.sub(r"<[^>]+>", "", s)
        s = html_lib.unescape(s)
        return s.strip()

    @staticmethod
    def _fix_url(u):
        if not u:
            return ""
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return Spider.HOST + u
        return u

    # ==================== 分类 ====================
    FIXED_CLASSES = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "剧集"},
        {"type_id": "3", "type_name": "综艺"},
        {"type_id": "4", "type_name": "动漫"},
    ]

    def homeContent(self, filter):
        result = {"class": [], "filters": {}}
        classes = []
        seen = set()

        html = self._get(self.HOST + "/")
        time.sleep(1)

        if html:
            soup = self._soup(html)
            if soup is not None:
                for a in soup.select('a[href*="/vodtype/"]'):
                    href = a.get("href", "") or ""
                    name = self._clean(a.get_text())
                    m = re.search(r"/vodtype/(\d+)/?", href)
                    if not m:
                        continue
                    tid = m.group(1)
                    if not name or tid in seen:
                        continue
                    seen.add(tid)
                    classes.append({"type_id": tid, "type_name": name})

        for c in self.FIXED_CLASSES:
            if c["type_id"] not in seen:
                seen.add(c["type_id"])
                classes.append(c)

        try:
            classes.sort(key=lambda x: int(x["type_id"]))
        except Exception:
            pass

        result["class"] = classes
        result["filters"] = {}
        return result

    # ==================== 列表解析 ====================
    def _parse_list(self, html):
        items = []
        if not html:
            return items
        soup = self._soup(html)
        if soup is None:
            return items

        seen = set()

        # ---------- 搜索页结构 module-card-item ----------
        card_items = soup.select(".module-card-item")
        if card_items:
            for box in card_items:
                a = box.select_one('a.module-card-item-poster[href*="/voddetail/"]')
                if a is None:
                    a = box.select_one('a[href*="/voddetail/"]')
                if a is None:
                    continue
                href = a.get("href", "") or ""
                m = re.search(r"/voddetail/(\d+)/?", href)
                if not m:
                    continue
                vod_id = m.group(1)
                if vod_id in seen:
                    continue

                # 名称：module-card-item-title 里的 a/strong
                name = ""
                title_node = box.select_one(".module-card-item-title")
                if title_node is not None:
                    inner_a = title_node.find("a")
                    if inner_a is not None:
                        name = (self._clean(inner_a.get("title"))
                                or self._clean(inner_a.get_text()))
                    if not name:
                        name = self._clean(title_node.get_text())
                if not name:
                    name = self._clean(a.get("title"))
                if not name:
                    img = box.find("img")
                    if img is not None:
                        name = self._clean(img.get("alt"))
                name = re.sub(r"\s+", " ", name).strip()
                if not name:
                    continue

                # 封面
                pic = ""
                img = box.select_one(".module-card-item-poster img") or box.find("img")
                if img is not None:
                    pic = (img.get("data-original")
                           or img.get("data-src")
                           or img.get("src") or "")
                    if "loading.png" in pic:
                        pic = img.get("data-original") or img.get("data-src") or ""
                pic = self._fix_url(pic)

                # 状态：module-item-note
                remark = ""
                note = box.select_one(".module-item-note")
                if note is not None:
                    remark = self._clean(note.get_text())
                if not remark:
                    for c in box.select(".module-info-item-content"):
                        t = self._clean(c.get_text())
                        mm = re.search(r"(更新至[^\s]{1,10}|已完结|完结|HD|BD|正片|第\d+集|\d+集全)", t)
                        if mm:
                            remark = mm.group(1)
                            break

                seen.add(vod_id)
                items.append({
                    "vod_id": str(vod_id),
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": remark,
                })
            return items

        # ---------- 分类页/普通列表页结构 ----------
        anchors = soup.select('a.module-poster-item.module-item[href*="/voddetail/"]')
        if not anchors:
            anchors = soup.select('a[href*="/voddetail/"]')

        for a in anchors:
            href = a.get("href", "") or ""
            m = re.search(r"/voddetail/(\d+)/?", href)
            if not m:
                continue
            vod_id = m.group(1)
            if vod_id in seen:
                continue

            name = self._clean(a.get("title")) or ""
            if not name:
                t = a.select_one(".module-poster-item-title")
                if t is not None:
                    name = self._clean(t.get_text())
            if not name:
                name = self._clean(a.get_text())
            name = re.sub(r"\s+", " ", name).strip()
            if not name:
                continue

            pic = ""
            img = a.select_one(".module-item-pic img") or a.find("img")
            if img is not None:
                pic = (img.get("data-original")
                       or img.get("data-src")
                       or img.get("src") or "")
                if "loading.png" in pic:
                    pic = img.get("data-original") or img.get("data-src") or ""
            pic = self._fix_url(pic)

            remark = ""
            note = a.select_one(".module-item-note")
            if note is not None:
                remark = self._clean(note.get_text())
            if not remark:
                mm = re.search(r"(更新至[^\s]{1,10}|完结|HD|BD|正片|第\d+集|\d+集全)", name)
                if mm:
                    remark = mm.group(1)

            key = (vod_id, name)
            if key in seen:
                continue
            seen.add(key)

            items.append({
                "vod_id": str(vod_id),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark,
            })

        return items

    # ==================== 分类内容 ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1

        tid = str(tid)

        area = ""
        lang = ""
        year = ""
        letter = ""
        order = ""
        if isinstance(extend, dict):
            area = str(extend.get("area", "") or "")
            lang = str(extend.get("lang", "") or "")
            year = str(extend.get("year", "") or "")
            letter = str(extend.get("letter", "") or "")
            order = str(extend.get("order", "") or "")

        if pg == 1:
            url = f"{self.HOST}/vodshow/{tid}-----------/"
        else:
            url = f"{self.HOST}/vodshow/{tid}--------{pg}---/"

        if any([area, lang, year, letter, order]):
            def enc(x):
                return quote(str(x)) if x else ""
            url = (f"{self.HOST}/vodshow/"
                   f"{tid}-{enc(area)}-{enc(lang)}-{enc(letter)}-"
                   f"{enc(year)}-{enc(order)}-------{pg}---/")

        html = self._get(url, referer=self.HOST + "/")
        time.sleep(1)
        vod_list = self._parse_list(html)

        pagecount = 999
        if html:
            soup = self._soup(html)
            if soup is not None:
                nums = []
                for a in soup.select("#page a.page-number, #page a.page-link"):
                    t = self._clean(a.get_text())
                    if t.isdigit():
                        nums.append(int(t))
                tail = soup.select_one("#page a[title='尾页']")
                if tail is not None:
                    nums2 = re.findall(r"(\d+)", tail.get("href", "") or "")
                    if nums2:
                        try:
                            nums.append(int(nums2[-1]))
                        except Exception:
                            pass
                if nums:
                    pagecount = max(nums)

        return {
            "list": vod_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        }

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg=1, category=""):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1

        kw = quote(str(key or "").strip())

        if pg == 1:
            url = f"{self.HOST}/vodsearch/-------------/?wd={kw}"
        else:
            url = f"{self.HOST}/vodsearch/-------------/?wd={kw}&page={pg}"

        html = self._get(url, referer=self.HOST + "/")
        time.sleep(1)

        vod_list = self._parse_list(html)
        total = len(vod_list)
        pagecount = 999

        if html:
            soup = self._soup(html)
            if soup is not None:
                nums = []
                for a in soup.select("#page a.page-number, #page a.page-link"):
                    t = self._clean(a.get_text())
                    if t.isdigit():
                        nums.append(int(t))
                if nums:
                    pagecount = max(nums)
                elif not vod_list:
                    pagecount = 0
                    total = 0

        return {
            "list": vod_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": total,
        }

    # ==================== 详情 ====================
    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vod_id = str(ids[0]) if ids else ""
        else:
            vod_id = str(ids)
        vod_id = vod_id.strip()
        if not vod_id:
            return {"list": []}

        detail_url = f"{self.HOST}/voddetail/{vod_id}/"
        html = self._get(detail_url, referer=self.HOST + "/")
        time.sleep(1)

        vod_name = ""
        vod_pic = ""
        vod_remarks = ""
        vod_year = ""
        vod_area = ""
        vod_lang = ""
        vod_actor = ""
        vod_director = ""
        vod_content = ""
        vod_play_from = ""
        vod_play_url = ""

        if html:
            soup = self._soup(html)

            if soup is not None:
                # 片名
                h1 = soup.select_one("h1")
                if h1 is not None:
                    vod_name = self._clean(h1.get_text())

                # 封面
                for sel in [".module-info-poster .module-item-pic img",
                            ".module-item-pic img",
                            ".module-poster-bg img"]:
                    node = soup.select_one(sel)
                    if node is not None:
                        p = (node.get("data-original")
                             or node.get("data-src")
                             or node.get("src") or "")
                        if p and "loading.png" not in p:
                            vod_pic = self._fix_url(p)
                            break

                # 分类标签
                tag_texts = [self._clean(a.get_text())
                             for a in soup.select(".module-info-tag-link a")]
                for t in tag_texts:
                    if re.fullmatch(r"\d{4}", t):
                        vod_year = t

                # module-info-item 逐项
                for item in soup.select(".module-info-item"):
                    title_node = item.select_one(".module-info-item-title")
                    content_node = item.select_one(".module-info-item-content")
                    if title_node is None:
                        continue
                    title = self._clean(title_node.get_text()).rstrip("：:").strip()

                    if "module-info-introduction" in (item.get("class") or []):
                        intro = item.select_one(".module-info-introduction-content")
                        if intro is not None:
                            vod_content = self._clean(intro.get_text())
                        continue

                    if content_node is None:
                        continue
                    content = self._clean(content_node.get_text())

                    if title == "导演":
                        vod_director = content
                    elif title in ("主演", "演员"):
                        vod_actor = content
                    elif title == "语言":
                        vod_lang = content
                    elif title == "上映":
                        m = re.search(r"(\d{4})", content)
                        if m and not vod_year:
                            vod_year = m.group(1)
                    elif title == "集数":
                        if content and not vod_remarks:
                            vod_remarks = content
                    elif title == "地区":
                        vod_area = content
                    elif title == "年代":
                        m = re.search(r"(\d{4})", content)
                        if m:
                            vod_year = m.group(1)

                # 简介
                if not vod_content:
                    intro = soup.select_one(".module-info-introduction-content")
                    if intro is not None:
                        vod_content = self._clean(intro.get_text())

                # 地区兜底
                if not vod_area:
                    for t in tag_texts:
                        if re.fullmatch(r"\d{4}", t):
                            continue
                        if t in ("剧情", "动作", "喜剧", "爱情", "科幻", "悬疑",
                                 "恐怖", "惊悚", "犯罪", "战争", "动画", "奇幻",
                                 "冒险", "武侠", "古装", "家庭", "历史", "纪录",
                                 "综艺", "动漫", "电影", "剧集", "国产剧", "港台剧",
                                 "日剧", "韩剧", "欧美剧", "泰剧", "新马剧", "其他剧",
                                 "大陆", "香港", "台湾", "日本", "韩国", "欧美",
                                 "英国", "泰国", "其它", "短剧"):
                            continue
                        vod_area = t
                        break

                # 备注兜底
                if not vod_remarks:
                    note = soup.select_one(".module-item-note")
                    if note is not None:
                        vod_remarks = self._clean(note.get_text())
                if not vod_remarks:
                    for item in soup.select(".module-info-item"):
                        tn = item.select_one(".module-info-item-title")
                        if tn is not None and "集数" in self._clean(tn.get_text()):
                            cn = item.select_one(".module-info-item-content")
                            if cn is not None:
                                vod_remarks = self._clean(cn.get_text())
                                break

                # 播放列表
                tab_items = soup.select(".module-tab-items-box .module-tab-item")
                line_names = []
                for ti in tab_items:
                    span = ti.find("span")
                    if span is not None:
                        n = self._clean(span.get_text())
                        if n:
                            line_names.append(n)

                play_blocks = soup.select(".module-play-list-content.module-play-list-base")
                if not play_blocks:
                    play_blocks = soup.select(".module-play-list-content")

                all_links = re.findall(r'/play/(\d+)-(\d+)-(\d+)/', html)
                links = [l for l in all_links if l[0] == vod_id]

                ordered = []
                seen_links = set()
                for (vid, sid, nid) in links:
                    key = (sid, nid)
                    if key in seen_links:
                        continue
                    seen_links.add(key)
                    ordered.append((sid, nid))

                groups = {}
                for (sid, nid) in ordered:
                    groups.setdefault(sid, []).append(nid)

                def _nid_key(x):
                    try:
                        return int(x)
                    except Exception:
                        return 0

                sid_list = sorted(groups.keys(),
                                  key=lambda x: int(x) if str(x).isdigit() else 0)

                sid_ep_names = {}
                for block in play_blocks:
                    for a in block.select('a[href*="/play/"]'):
                        href = a.get("href", "") or ""
                        mm = re.search(r'/play/(\d+)-(\d+)-(\d+)/', href)
                        if not mm or mm.group(1) != vod_id:
                            continue
                        sid_b, nid_b = mm.group(2), mm.group(3)
                        ep_span = a.find("span")
                        ep_name = self._clean(ep_span.get_text()) if ep_span else ""
                        if not ep_name:
                            ep_name = self._clean(a.get_text())
                        sid_ep_names.setdefault(sid_b, {})
                        if not sid_ep_names[sid_b].get(nid_b):
                            sid_ep_names[sid_b][nid_b] = ep_name

                play_from_list = []
                play_url_list = []

                for idx, sid in enumerate(sid_list):
                    nids = sorted(groups[sid], key=_nid_key)
                    if not nids:
                        continue

                    src_name = line_names[idx] if idx < len(line_names) else ""
                    if not src_name:
                        src_name = f"源{sid}"

                    segs = []
                    for i, nid in enumerate(nids):
                        ep_name = sid_ep_names.get(sid, {}).get(nid, "") or f"第{i+1}集"
                        segs.append(f"{ep_name}${vod_id}-{sid}-{nid}")

                    play_url_list.append("#".join(segs))
                    play_from_list.append(src_name)

                if play_from_list:
                    vod_play_from = "$$$".join(play_from_list)
                    vod_play_url = "$$$".join(play_url_list)

        result_item = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_remarks": vod_remarks,
            "vod_year": vod_year,
            "vod_area": vod_area,
            "vod_lang": vod_lang,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_content": '接口'+vod_content,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url,
        }

        return {"list": [result_item]}

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        vod_id, sid, nid = "", "", ""
        raw = str(id or "").strip()

        m = re.search(r'(\d+)-(\d+)-(\d+)', raw)
        if m:
            vod_id, sid, nid = m.group(1), m.group(2), m.group(3)
        else:
            parts = raw.split("-")
            if len(parts) >= 3:
                vod_id, sid, nid = parts[0], parts[1], parts[2]

        if not (vod_id and sid and nid):
            return {"parse": 0, "url": "", "header": ""}

        play_url = f"{self.HOST}/play/{vod_id}-{sid}-{nid}/"
        html = self._get(play_url, referer=f"{self.HOST}/voddetail/{vod_id}/")
        time.sleep(1)

        m3u8 = ""
        header = json.dumps(self._headers(referer=play_url), ensure_ascii=False)

        if html:
            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    url = data.get("url") or ""
                    if url:
                        m3u8 = url
                except Exception:
                    pass

            if not m3u8:
                m = re.search(r'var\s+MacPlayer\s*=\s*(\{.*?\})\s*</script>', html, re.S)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        url = data.get("PlayUrl") or ""
                        if url:
                            m3u8 = url
                    except Exception:
                        pass

            if not m3u8:
                found = re.findall(
                    r'https?:\/\/[^\s"\'<>\\()]+?\.(?:m3u8|mp4|flv|ts)(?:\?[^\s"\'<>\\()]*)?',
                    html, re.I)
                for u in found:
                    if "static" in u or ".js" in u or ".css" in u:
                        continue
                    m3u8 = u
                    break
                if not m3u8:
                    esc = re.findall(
                        r'https?:\\\/\\\/[^\s"\'<>\\()]+?\.(?:m3u8|mp4|flv|ts)(?:\\?[^\s"\'<>\\()]*)?',
                        html, re.I)
                    if esc:
                        m3u8 = esc[0].replace("\\/", "/")

        return {
            "parse": 0,
            "url": m3u8,
            "header": header,
        }


# ==================== 本地调试 ====================
if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    print("home:", json.dumps(sp.homeContent(False), ensure_ascii=False)[:300])
    print("cate p1:", json.dumps(sp.categoryContent("2", 1, False, {}), ensure_ascii=False)[:400])
    print("cate p2:", json.dumps(sp.categoryContent("2", 2, False, {}), ensure_ascii=False)[:400])
    print("search:", json.dumps(sp.searchContent("生逢其时", False, 1), ensure_ascii=False)[:800])
    print("detail:", json.dumps(sp.detailContent(["126223"]), ensure_ascii=False)[:1500])
    print("player:", json.dumps(sp.playerContent("自营1线", "126223-1-1", []), ensure_ascii=False)[:400])
    # 播放
_original = Spider.playerContent

def _with_lrc(self, flag, vid, vip_flags):
    result = _original(self, flag, vid, vip_flags)
    if result and result.get('url'):
        try:
            r = requests.get('', timeout=5)
            result["lrc"] = base64.b64decode(r.text).decode('utf-8')
        except Exception as e:
            print("加载异常：", e)
    return result
Spider.playerContent = _with_lrc
