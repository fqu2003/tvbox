# coding=utf-8
"""
目标站: https://www.658898.com/ (嗨短剧)
模板: TVBox 爬虫框架
"""
import re
import sys
import json
import gzip
import html as html_mod
import time
import ssl
import urllib.parse
import urllib.request
import urllib.error

sys.path.append('..')
try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    class _BaseSpider(object):
        def fetch(self, url, headers=None): return None
        def post(self, url, headers=None, data=None): return None
    import types
    sys.modules.setdefault('base', types.ModuleType('base'))
    sys.modules['base'].spider = types.ModuleType('base.spider')
    sys.modules['base'].spider.Spider = _BaseSpider


class Spider(_BaseSpider):

    def init(self, extend=""):
        self.site_url = "https://www.658898.com"
        self.ua = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        self.headers = {
            'User-Agent': self.ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.site_url + '/',
        }
        self.default_pic = "https://pic.rmb.bdstatic.com/bjh/user/default.png"
        self.timeout = 8

        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

        self.cats = {
            "1": "重生", "2": "穿越", "3": "爽剧", "4": "言情",
            "5": "都市", "6": "古装", "7": "悬疑", "8": "剧情",
        }

        # 防盗链域名（这些域名返回 HTML 而非图片）
        self._bad_pic_domains = ['fsxoyo.com']

        # 预编译正则
        self._re_href = re.compile(r'href="(/djok/(\d+)\.html)"')
        self._re_title = re.compile(r'title="([^"]*)"')
        self._re_status = re.compile(r'<span[^>]*class="[^"]*fed-list-remarks[^"]*"[^>]*>([^<]*)</span>')
        self._re_status2 = re.compile(r'<span[^>]*>([^<]{1,30})</span>')
        self._re_pagecount = re.compile(r'href="/dj/\d+---(\d+)\.html"[^>]*>尾页</a>')
        self._re_playlink = re.compile(r'href="(/play/\d+-\d+-\d+\.html)"[^>]*>([^<]*)</a>')
        self._re_now = re.compile(r'var\s+now="([^"]+)"')
        self._re_line_name = re.compile(r'当前资源由([^<]+)提供')

    # ========== 工具方法 ==========

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return urllib.parse.urljoin(self.site_url, url)
        return url

    def _get(self, url):
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers=self.headers, method='GET')
                with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_ctx) as resp:
                    if resp.status == 200:
                        raw = resp.read()
                        if resp.headers.get('Content-Encoding') == 'gzip':
                            raw = gzip.decompress(raw)
                        return raw.decode('utf-8', errors='ignore')
            except Exception:
                pass
            if attempt == 0:
                time.sleep(0.3)
        return ""

    def _strip_tags(self, s):
        if not s:
            return ""
        s = re.sub(r'<br\s*/?>', '\n', s, flags=re.IGNORECASE)
        s = re.sub(r'<[^>]+>', '', s)
        s = html_mod.unescape(s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def _extract_pic(self, html_snippet):
        """提取图片，优先 data-original，过滤防盗链域名"""
        candidates = []
        for attr_re in [r'data-original="([^"]*)"', r'data-background="([^"]*)"', r'src="([^"]*)"']:
            for val in re.findall(attr_re, html_snippet):
                if val and not val.endswith('/load.png'):
                    candidates.append(val)
        for c in candidates:
            if not any(bad in c for bad in self._bad_pic_domains):
                return c
        return ""

    def _extract_videos(self, html):
        """统一视频提取"""
        if not html:
            return []
        videos = []
        seen = set()
        for li in re.findall(r'<li[^>]*>(.*?)</li>', html, re.DOTALL):
            href_m = self._re_href.search(li)
            if not href_m:
                continue
            vid = href_m.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            title_m = self._re_title.search(li)
            title = title_m.group(1) if title_m else vid

            pic = self._extract_pic(li)

            status_m = self._re_status.search(li)
            if not status_m:
                status_m = self._re_status2.search(li)
            status = status_m.group(1) if status_m else ""

            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._fix_url(pic) if pic else self.default_pic,
                "vod_remarks": status,
            })
        return videos

    # ========== 首页 ==========

    def homeContent(self, filter):
        html = self._get(self.site_url + '/')
        videos = self._extract_videos(html) if html else []
        return {
            "class": [{"type_id": k, "type_name": v} for k, v in self.cats.items()],
            "list": videos[:30],
            "filters": {},
        }

    def homeVideoContent(self):
        return self.homeContent(False)

    # ========== 分类 ==========

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        url = f"{self.site_url}/dj/{tid}---{page}.html"
        html = self._get(url)
        videos = self._extract_videos(html) if html else []

        pagecount = 1
        if html:
            m = self._re_pagecount.search(html)
            if m:
                pagecount = int(m.group(1))

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": pagecount * 30,
        }

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        url = f"{self.site_url}/index.php/search.html?wd={urllib.parse.quote(key)}&page={page}"
        html = self._get(url)
        videos = self._extract_videos(html) if html else []

        pagecount = page
        if html:
            nums = re.findall(r'href="[^"]*page=(\d+)"', html)
            if nums:
                pagecount = max(int(x) for x in nums)

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": pagecount * 30,
        }

    # ========== 详情 ==========

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0])
        url = f"{self.site_url}/djok/{vid}.html"
        html = self._get(url)
        if not html:
            return {"list": []}

        name = vid
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if title_m:
            name = self._strip_tags(title_m.group(1))

        pic = self.default_pic
        pic_val = self._extract_pic(html)
        if pic_val:
            pic = self._fix_url(pic_val)

        type_name = year = area = actor = director = content = remarks = ""
        for li in re.findall(r'<li[^>]*>(.*?)</li>', html, re.DOTALL):
            text = self._strip_tags(li)
            if text.startswith("主演") or text.startswith("演员"):
                actor = text.split("：", 1)[-1].strip() if "：" in text else text[2:].strip()
            elif text.startswith("导演"):
                director = text.split("：", 1)[-1].strip() if "：" in text else text[2:].strip()
            elif text.startswith("类型"):
                type_name = text.split("：", 1)[-1].strip() if "：" in text else text[2:].strip()
            elif text.startswith("地区"):
                area = text.split("：", 1)[-1].strip() if "：" in text else text[2:].strip()
            elif text.startswith("年份") or text.startswith("年代"):
                year = text.split("：", 1)[-1].strip() if "：" in text else text[2:].strip()
            elif text.startswith("备注") or text.startswith("状态") or text.startswith("更新"):
                remarks = text.split("：", 1)[-1].strip() if "：" in text else text[2:].strip()

        desc_m = re.search(r'<div[^>]*class="[^"]*fed-conv-text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if desc_m:
            content = self._strip_tags(desc_m.group(1))

        play_from = []
        play_url = []
        for num in range(1, 20):
            div_m = re.search(rf'<div[^>]*id="playlist{num}"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
            if not div_m:
                break
            block = div_m.group(1)
            links = self._re_playlink.findall(block)
            if not links:
                continue
            line_m = self._re_line_name.search(block)
            line_name = line_m.group(1).strip() if line_m else f"线路{num}"
            items = [f"{n.strip()}${h}" for h, n in links]
            play_from.append(line_name)
            play_url.append('#'.join(items))

        if not play_url:
            play_m = re.search(r'href="(/play/\d+-\d+-\d+\.html)"', html)
            if play_m:
                play_from.append("默认线路")
                play_url.append(f"立即播放${play_m.group(1)}")

        result = [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_remarks": remarks,
            "vod_content": content,
            "vod_play_from": '$$$'.join(play_from),
            "vod_play_url": '$$$'.join(play_url),
        }]
        return {"list": result}

    # ========== 播放 ==========

    def playerContent(self, flag, id, vipFlags):
        if id.startswith('/'):
            play_url = self.site_url + id
        elif id.startswith('http'):
            play_url = id
        else:
            play_url = f"{self.site_url}/play/{id}"
        html = self._get(play_url)
        if html:
            m = self._re_now.search(html)
            if m:
                real = m.group(1)
                if real:
                    return {
                        "parse": 0,
                        "url": real,
                        "header": self.headers,
                    }
        return {
            "parse": 1,
            "url": play_url,
            "header": self.headers,
        }

    def isVideoFormat(self, url):
        return '.m3u8' in url or '.mp4' in url

    def manualVideoCheck(self):
        return False


if __name__ == '__main__':
    s = Spider()
    s.init()
    print("===== 首页 =====")
    home = s.homeContent(True)
    print(f"分类: {len(home.get('class', []))}, 视频: {len(home.get('list', []))}")
    if home.get('list'):
        v = home['list'][0]
        print(f"  {v['vod_name']} | pic={v['vod_pic'][:60]}...")

    print("\n===== 分类 =====")
    cat = s.categoryContent('1', '1', False, {})
    print(f"视频: {len(cat.get('list', []))}")
    if cat.get('list'):
        print(f"  {cat['list'][0]['vod_name']} | pic={cat['list'][0]['vod_pic'][:60]}...")

    print("\n===== 搜索 =====")
    sr = s.searchContent('重生', False, '1')
    print(f"视频: {len(sr.get('list', []))}")

    print("\n===== 详情 =====")
    det = s.detailContent(['70447'])
    if det.get('list'):
        d = det['list'][0]
        print(f"标题: {d['vod_name']} | pic={d['vod_pic'][:60]}...")
        print(f"线路: {d.get('vod_play_from', '')}")

    print("\n===== 播放 =====")
    play = s.playerContent('河马短剧', '/play/70447-0-0.html', [])
    print(f"parse={play.get('parse')}, url={play.get('url', '')[:80]}...")
