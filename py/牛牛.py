# coding=utf-8
"""
目标站: 牛牛28短剧 (28dj01.com)
站点: https://28dj01.com/
自定义模板 - 短剧站 - 修复播放线路
"""
import re
import sys
import json
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://28dj01.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 动态获取分类（从首页导航解析）
        self.categories = self._fetch_categories()

    def _fetch_categories(self):
        """从首页导航栏解析分类"""
        try:
            resp = self.fetch(self.site_url, headers=self.headers)
            if not resp:
                return self._default_categories()
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 导航菜单：ul.nav-menu-items li a
            nav_links = soup.select('ul.nav-menu-items li a')
            categories = []
            seen = set()
            for a in nav_links:
                href = a.get('href', '')
                # 匹配 /vodtype/数字/
                match = re.search(r'/vodtype/(\d+)/', href)
                if not match:
                    continue
                tid = match.group(1)
                name = a.get_text(strip=True)
                if not name or tid in seen or name == '首页':
                    continue
                seen.add(tid)
                categories.append({"type_id": tid, "type_name": name})
            if categories:
                return categories
        except Exception as e:
            print(f"[牛牛短剧] 获取分类失败: {e}")
        return self._default_categories()

    def _default_categories(self):
        return [
            {"type_id": "1", "type_name": "穿越重生"},
            {"type_id": "2", "type_name": "都市情爱"},
            {"type_id": "3", "type_name": "复仇爽剧"},
            {"type_id": "4", "type_name": "玄幻武侠"},
            {"type_id": "5", "type_name": "奇幻恐怖"},
            {"type_id": "20", "type_name": "其它短剧"},
        ]

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return urllib.parse.urljoin(self.site_url + "/", url)
        return url

    def _parse_video_list(self, html):
        """从HTML中解析视频列表（首页/分类/搜索）"""
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        seen = set()
        # 卡片容器：.module-item（出现在首页和分类页）
        items = soup.select('div.module-item')
        for item in items:
            link = item.select_one('a')
            if not link:
                continue
            href = link.get('href', '')
            # 提取视频ID（从 /voddetail/数字/ 中提取）
            vod_id = re.search(r'/voddetail/(\d+)/', href)
            if not vod_id:
                continue
            vid = vod_id.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            # 标题（从 module-item-title 或 a 的 title 属性）
            title_elem = item.select_one('.module-item-title')
            title = title_elem.get_text(strip=True) if title_elem else ''
            if not title:
                title = link.get('title', '')
            if not title:
                continue
            # 封面图（从 img 的 data-src 或 src）
            img = item.select_one('img')
            pic = img.get('data-src') or img.get('src') if img else ''
            # 备注（集数等）
            remark_elem = item.select_one('.module-item-text')
            remark = remark_elem.get_text(strip=True) if remark_elem else ''
            results.append({
                "vod_id": vid,
                "vod_name": title.strip(),
                "vod_pic": self._fix_url(pic),
                "vod_remarks": remark
            })
        return results

    # ================= 首页推荐 =================
    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            video_list = self._parse_video_list(resp.text)
            video_list = video_list[:30]
        return {"class": self.categories, "list": video_list, "filters": {}}

    def homeVideoContent(self):
        return self.homeContent(False)

    # ================= 分类列表 =================
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        # 分类URL: /vodtype/数字/  (第1页) 和 /vodtype/数字/page/数字/ (第2页起)
        if page == 1:
            url = f"{self.site_url}/vodtype/{tid}/"
        else:
            url = f"{self.site_url}/vodtype/{tid}/page/{page}/"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        video_list = self._parse_video_list(resp.text)
        # 分页信息：从页面中提取页码（简单处理）
        pagecount = page
        soup = BeautifulSoup(resp.text, 'html.parser')
        pagination = soup.select('.page a, .pagination a')
        if pagination:
            nums = []
            for a in pagination:
                text = a.get_text(strip=True)
                if text.isdigit():
                    nums.append(int(text))
            if nums:
                pagecount = max(nums)
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": len(video_list) * pagecount
        }

    # ================= 详情页 =================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/voddetail/{vod_id}/"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}

        soup = BeautifulSoup(resp.text, 'html.parser')
        # 标题
        title_elem = soup.select_one('h1')
        vod_name = title_elem.get_text(strip=True) if title_elem else vod_id
        # 封面图
        img_elem = soup.select_one('.module-item-pic img')
        vod_pic = img_elem.get('data-src') or img_elem.get('src') if img_elem else ''
        vod_pic = self._fix_url(vod_pic)
        # 简介
        content_elem = soup.select_one('.video-text')
        vod_content = content_elem.get_text(' ', strip=True) if content_elem else ''
        # 主演/导演（可能没有，留空）
        vod_actor = ''
        vod_director = ''
        vod_year = ''

        # ===== 播放线路解析 =====
        play_from_list = []
        play_url_list = []

        # 查找剧集列表（.module-items 中的 .module-item 包含播放链接）
        ep_items = soup.select('.module-items .module-item')
        if ep_items:
            episodes = []
            for ep in ep_items:
                a = ep.select_one('a')
                if not a:
                    continue
                href = a.get('href', '')
                ep_name = a.get_text(strip=True) or f"第{len(episodes)+1}集"
                if href and '/vodplay/' in href:
                    full_url = self._fix_url(href)
                    episodes.append(f"{ep_name}${full_url}")
            if episodes:
                play_from_list.append('默认线路')
                play_url_list.append('#'.join(episodes))

        # 如果没有找到，尝试直接查找所有 /vodplay/ 链接
        if not play_url_list:
            all_links = soup.select('a[href*="/vodplay/"]')
            if all_links:
                episodes = []
                for a in all_links:
                    href = a.get('href', '')
                    ep_name = a.get_text(strip=True) or f"第{len(episodes)+1}集"
                    full_url = self._fix_url(href)
                    episodes.append(f"{ep_name}${full_url}")
                if episodes:
                    play_from_list.append('默认线路')
                    play_url_list.append('#'.join(episodes))

        vod_play_from = '$$$'.join(play_from_list) if play_from_list else '默认源'
        vod_play_url = '$$$'.join(play_url_list) if play_url_list else f"播放${vod_id}"

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_area": "",
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        # 搜索URL: /vodsearch/-------------/ 带 wd 参数
        url = f"{self.site_url}/vodsearch/-------------/?wd={encoded_key}"
        if page > 1:
            url += f"&page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}
        video_list = self._parse_video_list(resp.text)
        return {"list": video_list, "page": page, "pagecount": 1}

    # ================= 播放解析（修复版） =================
    def playerContent(self, flag, id, vipFlags):
        """解析播放地址，提取直链"""
        play_url = self._fix_url(id)

        # 如果已经是直链，直接返回
        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', play_url, re.I):
            return {"parse": 0, "url": play_url, "header": self.headers}

        # 请求播放页
        headers = dict(self.headers)
        headers['Referer'] = self.site_url + '/'
        resp = self.fetch(play_url, headers=headers)
        if not resp:
            return {"parse": 1, "url": play_url, "header": headers}

        html = resp.text

        # ---- 重点：提取 player_aaaa 变量 ----
        # 格式: var player_aaaa={"flag":"play",...,"url":"https://..."}
        match = re.search(r'var\s+player_aaaa\s*=\s*({[^;]+});', html, re.DOTALL)
        if match:
            try:
                # 替换 JSON 中的 \/ 为 / 以修复转义（也可以直接用 json.loads 处理，但有些字符会报错）
                json_str = match.group(1)
                # 标准 JSON 解析
                data = json.loads(json_str)
                if data.get('url'):
                    final_url = data['url']
                    # 如果地址是相对路径，补全；否则直接使用
                    if not final_url.startswith('http'):
                        final_url = self._fix_url(final_url)
                    # 判断是否为直链
                    if re.search(r'\.(m3u8|mp4|flv)', final_url, re.I):
                        return {
                            "parse": 0,
                            "url": final_url,
                            "header": {
                                "User-Agent": self.headers['User-Agent'],
                                "Referer": self.site_url + '/',
                            }
                        }
            except Exception as e:
                print(f"[牛牛短剧] 解析 player_aaaa 失败: {e}")

        # 备选：从页面中查找 iframe
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_url = self._fix_url(iframe.group(1))
            iframe_resp = self.fetch(iframe_url, headers=headers)
            if iframe_resp:
                iframe_html = iframe_resp.text
                # 在 iframe 中查找 video 或 m3u8
                video_src = re.search(r'<video[^>]+src="([^"]+)"', iframe_html)
                if video_src:
                    return {"parse": 0, "url": video_src.group(1), "header": headers}
                m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', iframe_html)
                if m3u8:
                    return {"parse": 0, "url": m3u8.group(1), "header": headers}
                # 嵌套 iframe
                nested = re.search(r'<iframe[^>]+src="([^"]+)"', iframe_html)
                if nested:
                    nested_url = self._fix_url(nested.group(1))
                    nested_resp = self.fetch(nested_url, headers=headers)
                    if nested_resp:
                        nested_html = nested_resp.text
                        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', nested_html)
                        if m3u8:
                            return {"parse": 0, "url": m3u8.group(1), "header": headers}

        # 直接查找 video 标签
        video_src = re.search(r'<video[^>]+src="([^"]+)"', html)
        if video_src:
            return {"parse": 0, "url": video_src.group(1), "header": headers}

        # 其他常见播放变量
        play_vars = re.findall(r'var\s+(?:playurl|url|video)\s*=\s*["\']([^"\']+)["\']', html, re.I)
        for p in play_vars:
            if re.search(r'\.(m3u8|mp4|flv)', p, re.I):
                return {"parse": 0, "url": p, "header": headers}

        # 最后兜底：交给客户端解析
        return {"parse": 1, "url": play_url, "header": headers}