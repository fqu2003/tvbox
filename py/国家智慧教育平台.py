#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国家智慧教育平台 —— 影视TV 适配版（免登录探测增强版）
特性：
1. 教材列表稳定获取（多重降级）
2. 视频解析并发加速
3. 多资源类型：national_lesson / elite_lesson / singing / teaching_lesson
4. 四级联动筛选
5. 支持 ext 覆盖 cookie/ua/referer/origin/basic/cdn1/cdn2
6. URL 解码解决 TV 端编码问题
7. 去重
8. 所有筛选下拉框首位增加"全部"
9. 【新增】免登录探测真实播放地址：尝试公开接口 + 去 -private 变体
10. 【新增】全链路缓存：URL/m3u8/密钥/重写结果
11. 【2026-10-16 播放修复】playerContent 不再返回本地临时文件路径（TVBox 播放器读不到
    / 无 file:// 协议导致黑屏），改返 localProxy type=m3u8 地址；localProxy 内实时
    调 _rewrite_m3u8 重写（密钥嵌 data: URI、分片转绝对地址），重写失败则直返原始 m3u8；
    _rewrite_m3u8 缓存改存重写后文本（不再存本地文件路径，避免重复拉取）
"""

import sys, os, json, re, hashlib, base64, time, urllib.parse, urllib.request, hmac, tempfile, threading
from typing import List, Dict, Optional, Tuple, Any
from base.spider import Spider

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _HAS_CONCURRENT = True
except ImportError:
    _HAS_CONCURRENT = False

# ========== 配置常量 ==========
BASIC = "https://basic.smartedu.cn"
CDN1 = "https://s-file-1.ykt.cbern.com.cn"
CDN2 = "https://s-file-2.ykt.cbern.com.cn"
CDN3 = "https://s-file-3.ykt.cbern.com.cn"
R2 = "https://r2-ndr.ykt.cbern.com.cn"
R3 = "https://r3-ndr.ykt.cbern.com.cn"

DEFAULT_COOKIE = ""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://basic.smartedu.cn/",
    "Origin": "https://basic.smartedu.cn",
}

XD_LIST = ["小学", "初中", "高中", "小学（五•四学制）", "初中（五•四学制）"]

GRADE_ORDER = {
    "一年级": 1, "二年级": 2, "三年级": 3, "四年级": 4, "五年级": 5, "六年级": 6,
    "七年级": 7, "八年级": 8, "九年级": 9,
    "高一": 10, "高一年级": 10, "高二": 11, "高二年级": 11, "高三": 12,
    "一至二年级": 1.5, "三至四年级": 3.5, "五至六年级": 5.5,
    "学生读本": 0, "中国历史": 0, "世界历史": 0,
}

RES_TYPE_FETCHERS = {
    "national_lesson": "_fetch_national_lesson",
    "elite_lesson": "_fetch_elite_lesson",
    "singing": "_fetch_singing_resource",
    "teaching_lesson": "_fetch_detail_json",
}

# ========== 纯 Python AES-128-ECB ==========
class _AES128:
    _sbox = bytes([
        0x63,0x7C,0x77,0x7B,0xF2,0x6B,0x6F,0xC5,0x30,0x01,0x67,0x2B,0xFE,0xD7,0xAB,0x76,
        0xCA,0x82,0xC9,0x7D,0xFA,0x59,0x47,0xF0,0xAD,0xD4,0xA2,0xAF,0x9C,0xA4,0x72,0xC0,
        0xB7,0xFD,0x93,0x26,0x36,0x3F,0xF7,0xCC,0x34,0xA5,0xE5,0xF1,0x71,0xD8,0x31,0x15,
        0x04,0xC7,0x23,0xC3,0x18,0x96,0x05,0x9A,0x07,0x12,0x80,0xE2,0xEB,0x27,0xB2,0x75,
        0x09,0x83,0x2C,0x1A,0x1B,0x6E,0x5A,0xA0,0x52,0x3B,0xD6,0xB3,0x29,0xE3,0x2F,0x84,
        0x53,0xD1,0x00,0xED,0x20,0xFC,0xB1,0x5B,0x6A,0xCB,0xBE,0x39,0x4A,0x4C,0x58,0xCF,
        0xD0,0xEF,0xAA,0xFB,0x43,0x4D,0x33,0x85,0x45,0xF9,0x02,0x7F,0x50,0x3C,0x9F,0xA8,
        0x51,0xA3,0x40,0x8F,0x92,0x9D,0x38,0xF5,0xBC,0xB6,0xDA,0x21,0x10,0xFF,0xF3,0xD2,
        0xCD,0x0C,0x13,0xEC,0x5F,0x97,0x44,0x17,0xC4,0xA7,0x7E,0x3D,0x64,0x5D,0x19,0x73,
        0x60,0x81,0x4F,0xDC,0x22,0x2A,0x90,0x88,0x46,0xEE,0xB8,0x14,0xDE,0x5E,0x0B,0xDB,
        0xE0,0x32,0x3A,0x0A,0x49,0x06,0x24,0x5C,0xC2,0xD3,0xAC,0x62,0x91,0x95,0xE4,0x79,
        0xE7,0xC8,0x37,0x6D,0x8D,0xD5,0x4E,0xA9,0x6C,0x56,0xF4,0xEA,0x65,0x7A,0xAE,0x08,
        0xBA,0x78,0x25,0x2E,0x1C,0xA6,0xB4,0xC6,0xE8,0xDD,0x74,0x1F,0x4B,0xBD,0x8B,0x8A,
        0x70,0x3E,0xB5,0x66,0x48,0x03,0xF6,0x0E,0x61,0x35,0x57,0xB9,0x86,0xC1,0x1D,0x9E,
        0xE1,0xF8,0x98,0x11,0x69,0xD9,0x8E,0x94,0x9B,0x1E,0x87,0xE9,0xCE,0x55,0x28,0xDF,
        0x8C,0xA1,0x89,0x0D,0xBF,0xE6,0x42,0x68,0x41,0x99,0x2D,0x0F,0xB0,0x54,0xBB,0x16,
    ])
    _inv_sbox = bytes([
        0x52,0x09,0x6A,0xD5,0x30,0x36,0xA5,0x38,0xBF,0x40,0xA3,0x9E,0x81,0xF3,0xD7,0xFB,
        0x7C,0xE3,0x39,0x82,0x9B,0x2F,0xFF,0x87,0x34,0x8E,0x43,0x44,0xC4,0xDE,0xE9,0xCB,
        0x54,0x7B,0x94,0x32,0xA6,0xC2,0x23,0x3D,0xEE,0x4C,0x95,0x0B,0x42,0xFA,0xC3,0x4E,
        0x08,0x2E,0xA1,0x66,0x28,0xD9,0x24,0xB2,0x76,0x5B,0xA2,0x49,0x6D,0x8B,0xD1,0x25,
        0x72,0xF8,0xF6,0x64,0x86,0x68,0x98,0x16,0xD4,0xA4,0x5C,0xCC,0x5D,0x65,0xB6,0x92,
        0x6C,0x70,0x48,0x50,0xFD,0xED,0xB9,0xDA,0x5E,0x15,0x46,0x57,0xA7,0x8D,0x9D,0x84,
        0x90,0xD8,0xAB,0x00,0x8C,0xBC,0xD3,0x0A,0xF7,0xE4,0x58,0x05,0xB8,0xB3,0x45,0x06,
        0xD0,0x2C,0x1E,0x8F,0xCA,0x3F,0x0F,0x02,0xC1,0xAF,0xBD,0x03,0x01,0x13,0x8A,0x6B,
        0x3A,0x91,0x11,0x41,0x4F,0x67,0xDC,0xEA,0x97,0xF2,0xCF,0xCE,0xF0,0xB4,0xE6,0x73,
        0x96,0xAC,0x74,0x22,0xE7,0xAD,0x35,0x85,0xE2,0xF9,0x37,0xE8,0x1C,0x75,0xDF,0x6E,
        0x47,0xF1,0x1A,0x71,0x1D,0x29,0xC5,0x89,0x6F,0xB7,0x62,0x0E,0xAA,0x18,0xBE,0x1B,
        0xFC,0x56,0x3E,0x4B,0xC6,0xD2,0x79,0x20,0x9A,0xDB,0xC0,0xFE,0x78,0xCD,0x5A,0xF4,
        0x1F,0xDD,0xA8,0x33,0x88,0x07,0xC7,0x31,0xB1,0x12,0x10,0x59,0x27,0x80,0xEC,0x5F,
        0x60,0x51,0x7F,0xA9,0x19,0xB5,0x4A,0x0D,0x2D,0xE5,0x7A,0x9F,0x93,0xC9,0x9C,0xEF,
        0xA0,0xE0,0x3B,0x4D,0xAE,0x2A,0xF5,0xB0,0xC8,0xEB,0xBB,0x3C,0x83,0x53,0x99,0x61,
        0x17,0x2B,0x04,0x7E,0xBA,0x77,0xD6,0x26,0xE1,0x69,0x14,0x63,0x55,0x21,0x0C,0x7D,
    ])

    @classmethod
    def _gf_mul(cls, a: int, b: int) -> int:
        p = 0
        for _ in range(8):
            if b & 1: p ^= a
            hi = a & 0x80
            a = (a << 1) & 0xFF
            if hi: a ^= 0x1B
            b >>= 1
        return p

    @classmethod
    def _expand_key(cls, key: bytes) -> List[bytes]:
        Nk, Nr = 4, 10
        Rcon = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36]
        w = bytearray(key)
        for i in range(Nk, 4 * (Nr + 1)):
            temp = w[(i-1)*4 : i*4]
            if i % Nk == 0:
                temp = temp[1:] + temp[:1]
                temp = bytearray([cls._sbox[b] for b in temp])
                temp[0] ^= Rcon[i // Nk - 1]
            prev = w[(i - Nk)*4 : (i - Nk + 1)*4]
            w.extend([temp[j] ^ prev[j] for j in range(4)])
        return [bytes(w[i*16:(i+1)*16]) for i in range(Nr + 1)]

    @classmethod
    def _sub_bytes(cls, s, inv=False):
        box = cls._inv_sbox if inv else cls._sbox
        for i in range(16): s[i] = box[s[i]]

    @classmethod
    def _shift_rows(cls, s, inv=False):
        t = s[:]
        if inv:
            s[1],s[5],s[9],s[13] = t[13],t[1],t[5],t[9]
            s[2],s[6],s[10],s[14] = t[10],t[14],t[2],t[6]
            s[3],s[7],s[11],s[15] = t[7],t[11],t[15],t[3]
        else:
            s[1],s[5],s[9],s[13] = t[5],t[9],t[13],t[1]
            s[2],s[6],s[10],s[14] = t[10],t[14],t[2],t[6]
            s[3],s[7],s[11],s[15] = t[15],t[3],t[7],t[11]

    @classmethod
    def _mix_columns(cls, s, inv=False):
        for c in range(4):
            i = c * 4
            a,b,c_,d = s[i],s[i+1],s[i+2],s[i+3]
            if not inv:
                s[i]   = cls._gf_mul(a,2)^cls._gf_mul(b,3)^c_^d
                s[i+1] = a^cls._gf_mul(b,2)^cls._gf_mul(c_,3)^d
                s[i+2] = a^b^cls._gf_mul(c_,2)^cls._gf_mul(d,3)
                s[i+3] = cls._gf_mul(a,3)^b^c_^cls._gf_mul(d,2)
            else:
                s[i]   = cls._gf_mul(a,0x0E)^cls._gf_mul(b,0x0B)^cls._gf_mul(c_,0x0D)^cls._gf_mul(d,0x09)
                s[i+1] = cls._gf_mul(a,0x09)^cls._gf_mul(b,0x0E)^cls._gf_mul(c_,0x0B)^cls._gf_mul(d,0x0D)
                s[i+2] = cls._gf_mul(a,0x0D)^cls._gf_mul(b,0x09)^cls._gf_mul(c_,0x0E)^cls._gf_mul(d,0x0B)
                s[i+3] = cls._gf_mul(a,0x0B)^cls._gf_mul(b,0x0D)^cls._gf_mul(c_,0x09)^cls._gf_mul(d,0x0E)

    @classmethod
    def _add_round_key(cls, s, rk):
        for i in range(16): s[i] ^= rk[i]

    @classmethod
    def decrypt_block(cls, ct, key):
        rk = cls._expand_key(key)
        s = bytearray(ct)
        cls._add_round_key(s, rk[10])
        for r in range(9, 0, -1):
            cls._shift_rows(s, True)
            cls._sub_bytes(s, True)
            cls._add_round_key(s, rk[r])
            cls._mix_columns(s, True)
        cls._shift_rows(s, True)
        cls._sub_bytes(s, True)
        cls._add_round_key(s, rk[0])
        return bytes(s)

    @classmethod
    def decrypt(cls, ct, key):
        key = (key.ljust(16, b'\x00') if len(key) < 16 else key[:16])
        pt = bytearray()
        for i in range(0, len(ct), 16):
            blk = ct[i:i+16]
            if len(blk) < 16: blk = blk + b'\x00' * (16 - len(blk))
            pt.extend(cls.decrypt_block(blk, key))
        if not pt: return b''
        pad = pt[-1]
        if 1 <= pad <= 16 and all(b == pad for b in pt[-pad:]):
            return bytes(pt[:-pad])
        return bytes(pt)


# ========== 线程安全缓存 ==========
class _Cache:
    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()
    def get(self, key):
        with self._lock: return self._store.get(key)
    def set(self, key, val):
        with self._lock: self._store[key] = val


class _TTLCache:
    def __init__(self, ttl=600):
        self._store = {}
        self._lock = threading.Lock()
        self._ttl = ttl
    def get(self, key):
        with self._lock:
            item = self._store.get(key)
            if not item: return None
            val, ts = item
            if time.time() - ts > self._ttl:
                self._store.pop(key, None); return None
            return val
    def set(self, key, val):
        with self._lock:
            self._store[key] = (val, time.time())


# ========== Spider 类 ==========
class Spider(Spider):
    def getName(self):
        return "国家智慧教育平台"

    def init(self, extend=""):
        ext = {}
        if isinstance(extend, str) and extend.strip():
            try: ext = json.loads(extend)
            except (json.JSONDecodeError, TypeError): ext = {}
        elif isinstance(extend, dict): ext = extend

        self.basic = ext.get("basic") or BASIC
        self.cdn1 = ext.get("cdn1") or CDN1
        self.cdn2 = ext.get("cdn2") or CDN2

        self.headers = dict(HEADERS)
        if ext.get("ua"):       self.headers["User-Agent"] = ext["ua"]
        if ext.get("referer"):  self.headers["Referer"] = ext["referer"]
        if ext.get("origin"):   self.headers["Origin"] = ext["origin"]

        cookie_from_ext = ext.get("cookie", "")
        self.cookie = cookie_from_ext if cookie_from_ext else DEFAULT_COOKIE

        self.access_token = ""
        self.mac_key = ""
        if self.cookie:
            parsed = self._parse_cookie(self.cookie)
            self.access_token = parsed.get("access_token", "")
            self.mac_key = parsed.get("mac_key", "")
            if not self.access_token:
                m = re.search(r'accessToken=([^;]+)', self.cookie)
                if m: self.access_token = m.group(1)
            if self.access_token: self.headers["accessToken"] = self.access_token
            self.headers["Cookie"] = self.cookie

        self._recommend_config = ext.get("recommend") or [
            {"name": "九年级·语文·统编版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "语文", "zxxbb": "统编版", "zxxcc": "上册"}},
            {"name": "九年级·数学·苏科版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "数学", "zxxbb": "苏科版", "zxxcc": "上册"}},
            {"name": "八年级·语文·统编版·上册", "tags": {"zxxxd": "初中", "zxxnj": "八年级", "zxxxk": "语文", "zxxbb": "统编版", "zxxcc": "上册"}},
            {"name": "七年级·数学·人教版·上册", "tags": {"zxxxd": "初中", "zxxnj": "七年级", "zxxxk": "数学", "zxxbb": "人教版", "zxxcc": "上册"}},
        ]

        # 缓存
        self._http_cache = _TTLCache(ttl=600)
        self._m3u8_rewrite_cache = _TTLCache(ttl=900)
        self._key_cache = _TTLCache(ttl=900)
        self._m3u8_text_cache = _TTLCache(ttl=600)
        self._local_m3u8_dir = tempfile.gettempdir()

        self._tree_cache = _Cache()
        self._resource_cache = _Cache()
        self._res_map_cache = _Cache()
        self._node_index_cache = _Cache()
        self._tm_pic_cache = _Cache()
        self._play_probe_cache = _TTLCache(ttl=1800)   # 免登录探测缓存

        self._tm_list_cache = None
        self._tm_list_lock = threading.Lock()
        self._tm_id_map = {}
        self._xd_tm_map = {}
        self._act_cache = _Cache()
        self._resolve_lock = threading.Lock()
        self._detail_json_cache = _Cache()

        threading.Thread(target=self._ensure_tm_loaded, daemon=True).start()

    # ==================== 教材列表 ====================
    def _ensure_tm_loaded(self, retry=2):
        if self._tm_id_map: return
        for attempt in range(retry + 1):
            try:
                tm_list = self._fetch_tm_list()
                if tm_list:
                    self._build_tm_maps(tm_list)
                    print(f"[init] 教材索引构建完成: {len(self._tm_id_map)} 套")
                    return
            except Exception as e:
                print(f"[init] 教材列表加载异常: {e}")
            time.sleep(1.2 ** attempt)

    # ==================== HTTP ====================
    def _http_get(self, url, timeout=12, use_mac=False, use_cookie=True,
                  json_resp=True, retry=3, use_cache=True):
        if use_cache:
            cached = self._http_cache.get(url)
            if cached is not None:
                if json_resp and isinstance(cached, str):
                    try: return json.loads(cached)
                    except Exception: return cached
                return cached

        for attempt in range(retry):
            try:
                h = dict(self.headers)
                if use_cookie and self.cookie: h["Cookie"] = self.cookie
                if use_mac and self.access_token and self.mac_key:
                    h["Authorization"] = self._mac_header(url)
                    h["accessToken"] = self.access_token
                    h["sdp-app-id"] = "e5649925-441d-4a53-b525-51a2f1c4e0a8"
                elif self.access_token:
                    h["accessToken"] = self.access_token
                req = urllib.request.Request(url, headers=h, method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read().decode("utf-8", errors="ignore")
                    if use_cache: self._http_cache.set(url, data)
                    if json_resp:
                        try: return json.loads(data)
                        except Exception: return data
                    return data
            except Exception as e:
                if attempt == retry - 1:
                    raise Exception(f"请求失败（重试{retry}次）: {e}")
                time.sleep(0.6 * (attempt + 1))
        return None

    def _with_token(self, url):
        if not url: return url
        url = str(url)
        if self.access_token and "accessToken=" not in url:
            url += ("?" if "?" not in url else "&") + f"accessToken={urllib.parse.quote(self.access_token)}"
        return url

    def _parse_cookie(self, cookie_str):
        if not cookie_str: return {}
        m = re.search(r'UC_TOKEN-[^=]+=([^;]+)', cookie_str)
        if not m: return {"cookie": cookie_str}
        try:
            b64 = m.group(1).replace("-", "+").replace("_", "/")
            while len(b64) % 4: b64 += "="
            obj = json.loads(base64.b64decode(b64).decode("utf-8"))
            return {"access_token": obj.get("access_token", ""),
                    "mac_key": obj.get("mac_key", ""),
                    "user_id": obj.get("user_id", ""),
                    "cookie": cookie_str}
        except Exception:
            return {"cookie": cookie_str}

    def _hmac_sha256_base64(self, key, msg):
        return base64.b64encode(hmac.new(key.encode(), msg.encode(), hashlib.sha256).digest()).decode()

    def _mac_header(self, url, method="GET"):
        if not self.access_token or not self.mac_key: return ""
        p = urllib.parse.urlparse(url)
        nonce = f"{int(time.time()*1000)}:{os.urandom(4).hex()}"
        raw = f"{nonce}\n{method.upper()}\n{p.path}\n{p.hostname}\n"
        mac = self._hmac_sha256_base64(self.mac_key, raw)
        return f'MAC id="{self.access_token}",nonce="{nonce}",mac="{mac}"'

    def _concurrent_fetch(self, tasks, max_workers=6, timeout_per_task=8):
        if not _HAS_CONCURRENT:
            results = []
            for task in tasks:
                name = task[0]
                cfg = task[1] if isinstance(task[1], dict) else {"url": task[1]}
                try:
                    res = self._http_get(cfg["url"], timeout=timeout_per_task,
                                         use_mac=cfg.get("use_mac", False),
                                         use_cookie=cfg.get("use_cookie", True))
                    results.append((name, res))
                except Exception:
                    results.append((name, None))
            return results
        results = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tasks)))) as ex:
            future_map = {}
            for task in tasks:
                name = task[0]
                cfg = task[1] if isinstance(task[1], dict) else {"url": task[1]}
                fut = ex.submit(self._http_get, cfg["url"], timeout_per_task,
                                cfg.get("use_mac", False), cfg.get("use_cookie", True), True, 2)
                future_map[fut] = name
            try:
                for fut in as_completed(future_map, timeout=timeout_per_task * 2):
                    try: results.append((future_map[fut], fut.result()))
                    except Exception: results.append((future_map[fut], None))
            except Exception:
                pass
        return results

    # ==================== 教材列表 ====================
    def _fetch_tm_list(self):
        if self._tm_list_cache is not None: return self._tm_list_cache
        with self._tm_list_lock:
            if self._tm_list_cache is not None: return self._tm_list_cache
            hosts = [self.cdn1, self.cdn2, CDN3]
            part_urls = []
            for host in hosts:
                try:
                    data = self._http_get(f"{host}/zxx/ndrs/national_lesson/teachingmaterials/version/data_version.json",
                                          timeout=15, use_cookie=False, use_mac=False)
                    if data and isinstance(data, dict) and "urls" in data:
                        urls = data["urls"]
                        if isinstance(urls, str):
                            part_urls = [u.strip() for u in urls.split(",") if u.strip()]
                        elif isinstance(urls, list):
                            part_urls = [u.strip() for u in urls if u.strip()]
                        if part_urls: break
                except Exception:
                    pass
            if not part_urls:
                part_urls = [f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/part_{i}.json"
                             for i in range(100, 106)]
            all_items = []
            for url in part_urls:
                try:
                    data = self._http_get(url, timeout=30, use_cookie=False, use_mac=False)
                    if isinstance(data, list): all_items.extend(data)
                except Exception:
                    continue
            valid = self._filter_tm_items(all_items)
            self._tm_list_cache = valid if valid else []
            print(f"[教材列表] {len(self._tm_list_cache)} 套")
            return self._tm_list_cache

    def _filter_tm_items(self, items):
        valid, seen = [], set()
        for item in items:
            if not isinstance(item, dict): continue
            if not item.get("id"): continue
            if item["id"] in seen: continue
            title = item.get("title") or (item.get("global_title") or {}).get("zh-CN", "")
            if not title or len(title) < 2: continue
            rtype = item.get("resource_type_code", "")
            if rtype and rtype not in ("teachingmaterials", "teachingmaterial", "", None):
                tags = item.get("tag_list", [])
                has_tm_tag = any(t.get("tag_dimension_id") == "zxxxd" for t in tags if isinstance(t, dict))
                if not has_tm_tag and "教材" not in title and "教学" not in title:
                    continue
            valid.append(item)
            seen.add(item["id"])
        return valid

    # ---------- 教材封面 ----------
    def _build_cover_url(self, tm_id, title=""):
        if not tm_id: return ""
        cached = self._tm_pic_cache.get(tm_id)
        if cached is not None: return cached
        candidates = []
        if title:
            safe_title = title.replace(" ", "%20")
            candidates.append(f"{R2}/edu_product/esp/teachingmaterials/{tm_id}.pkg/{safe_title}.png?x-eos-process=image/format,webp")
            candidates.append(f"{R2}/edu_product/esp/teachingmaterials/{tm_id}.pkg/{safe_title}.jpg")
        candidates.append(f"{R2}/edu_product/esp/teachingmaterials/{tm_id}.pkg/cover.png")
        candidates.append(f"{R2}/edu_product/esp/teachingmaterials/{tm_id}.pkg/cover.jpg")
        result = candidates[0] if candidates else ""
        self._tm_pic_cache.set(tm_id, result)
        return result

    def _extract_tm_pic(self, item):
        if not item: return ""
        try:
            thumbs = (item.get("custom_properties") or {}).get("thumbnails", [])
            if thumbs and isinstance(thumbs, list): return thumbs[0]
        except Exception: pass
        try:
            prev = (item.get("custom_properties") or {}).get("preview", {})
            if prev.get("frame1"): return prev["frame1"]
        except Exception: pass
        tm_id = item.get("id", "")
        title = item.get("title") or (item.get("global_title") or {}).get("zh-CN", "")
        if tm_id: return self._build_cover_url(tm_id, title)
        return ""

    def _build_tm_maps(self, tm_list):
        self._tm_id_map = {}
        self._xd_tm_map = {}
        seen_keys = set()
        KNOWN_VERSIONS = ["统编版", "人教版", "北师大版", "苏教版", "沪教版", "鲁教版",
                          "青岛版", "牛津上海版", "沪音版", "沪书画版", "沪科技版",
                          "沪少版", "冀教版", "教科版", "西南大学版", "外研社版",
                          "译林版", "苏科版", "华东师大版", "浙教版", "湘教版",
                          "粤教版", "沪科教版", "沪外教版", "北京版", "辽海版",
                          "湘美版", "人美版", "冀美版", "岭南美版", "人音版",
                          "苏少版", "湘文艺版", "粤教花城版", "鲁科版", "中华中图版",
                          "中图版", "晋教版", "商务星球版", "科普版", "地质社版",
                          "华中师大版", "科学社版", "川教版", "陕旅版", "闽教版",
                          "辽宁师大版", "鲁教湘教版", "人教大同版", "人教鄂教版",
                          "冀人版", "大象社版", "粤教科技版", "湘科版"]
        for item in tm_list:
            tags = item.get("tag_list", [])
            tag_map = {}
            for t in tags:
                if isinstance(t, dict) and "tag_dimension_id" in t:
                    tag_map[t["tag_dimension_id"]] = t.get("tag_name", "")
            xd = tag_map.get("zxxxd", "")
            nj = tag_map.get("zxxnj", "")
            xk = tag_map.get("zxxxk", "")
            bb = tag_map.get("zxxbb", "")
            cc = tag_map.get("zxxcc", "")
            if not xd or not nj or not xk: continue
            title = item.get("title") or (item.get("global_title") or {}).get("zh-CN", "")
            if not bb and title:
                for ver in KNOWN_VERSIONS:
                    if ver in title: bb = ver; break
                bb = bb or "未知版本"
            elif not bb: bb = "未知版本"
            if not cc and title:
                if "上册" in title: cc = "上册"
                elif "下册" in title: cc = "下册"
                elif "全一册" in title: cc = "全一册"
                elif "必修" in title:
                    idx = title.find("必修")
                    cc = title[idx:idx+6]
                else: cc = "未知册次"
            elif not cc: cc = "未知册次"
            key = f"{xd}·{nj}·{xk}·{bb}·{cc}"
            if key in seen_keys: continue
            seen_keys.add(key)
            tm_id = item.get("id", "")
            if not tm_id: continue
            self._tm_id_map[key] = tm_id
            pic_url = self._extract_tm_pic(item)
            if pic_url:
                self._tm_pic_cache.set(tm_id, pic_url)
                self._tm_pic_cache.set(key, pic_url)
            if xd not in self._xd_tm_map: self._xd_tm_map[xd] = []
            self._xd_tm_map[xd].append({
                "id": tm_id, "key": key, "xd": xd, "nj": nj, "xk": xk,
                "bb": bb, "cc": cc, "pic": pic_url,
            })

    # ==================== 教材树/资源 ====================
    def _fetch_tm_tree(self, tm_id):
        cached = self._tree_cache.get(tm_id)
        if cached: return cached
        for host in (self.cdn1, self.cdn2):
            try:
                data = self._http_get(f"{host}/zxx/ndrv2/national_lesson/trees/{tm_id}.json",
                                      timeout=20, use_cookie=True)
                if data and isinstance(data, list) and len(data) > 0:
                    self._tree_cache.set(tm_id, data)
                    self._build_node_index(tm_id, data)
                    return data
            except Exception: pass
        return []

    def _fetch_tm_resources(self, tm_id):
        cached = self._resource_cache.get(tm_id)
        if cached: return cached
        part_urls = []
        for host in (self.cdn1, self.cdn2):
            try:
                data = self._http_get(f"{host}/zxx/ndrs/national_lesson/teachingmaterials/{tm_id}/resources/parts.json",
                                      timeout=15, use_cookie=True)
                if isinstance(data, list):
                    part_urls = [u for u in data if isinstance(u, str) and re.search(r"part_\d+\.json", u)]
                    if part_urls: break
            except Exception: pass
        if not part_urls:
            part_urls = [f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/{tm_id}/resources/part_100.json"]
        tasks = [("res_part", url) for url in part_urls]
        fetch_results = self._concurrent_fetch(tasks, max_workers=min(6, len(part_urls)), timeout_per_task=30)
        all_list = []
        for _, data in fetch_results:
            if isinstance(data, list): all_list.extend(data)
        valid_res, seen = [], set()
        for r in all_list:
            rtype = r.get("resource_type_code", "")
            if rtype not in ("national_lesson", "elite_lesson", "singing", "teaching_lesson"): continue
            aid = r.get("id", "")
            if not aid or aid in seen: continue
            seen.add(aid); valid_res.append(r)
        self._resource_cache.set(tm_id, valid_res)
        self._build_res_map(tm_id, valid_res)
        return valid_res

    def _build_node_index(self, tm_id, tree):
        index = {}
        def walk(nodes):
            for node in nodes:
                if not node: continue
                nid = node.get("id")
                if nid: index[nid] = node
                children = node.get("child_nodes") or node.get("children") or []
                if children: walk(children)
        walk(tree)
        self._node_index_cache.set(tm_id, index)

    def _build_res_map(self, tm_id, resources):
        res_map = {}
        for r in resources:
            ch_ids = r.get("chapter_ids", [])
            if not ch_ids: continue
            target_cid = ch_ids[-1]
            res_map.setdefault(target_cid, []).append(r)
        self._res_map_cache.set(tm_id, res_map)

    # ==================== 视频源提取 ====================
    def _pick_best_video(self, ti_items):
        if not ti_items: return None
        prefer = ["1920x1080", "1280x720", "852x480", "640x360"]
        candidates = []
        for it in ti_items:
            fmt = str(it.get("ti_format", "")).lower()
            stor = str(it.get("ti_storage", ""))
            stors = it.get("ti_storages", [])
            if fmt != "m3u8" and ".m3u8" not in stor: continue
            first_url = str(stors[0]) if stors else (stor or None)
            if not first_url: continue
            if first_url.startswith("cs_path:${ref-path}/"):
                first_url = "https://r1-ndr-private.ykt.cbern.com.cn/" + first_url.replace("cs_path:${ref-path}/", "")
            elif first_url.startswith("cs_path:"):
                first_url = "https://r1-ndr-private.ykt.cbern.com.cn/" + re.sub(r"^cs_path:\$\{ref-path\}/?", "", first_url)
            if first_url.startswith("//"): first_url = "https:" + first_url
            if re.search(r"\.m3u8(\?|$)", first_url, re.I): candidates.append(first_url)
        if not candidates: return None
        for p in prefer:
            for c in candidates:
                if p in c: return c
        return candidates[0]

    # ==================== 【新增】免登录探测真实播放地址 ====================
    def _probe_public_play_url(self, activity_id):
        """
        免登录探测真实播放地址：
        1. 尝试 resources/details 公开接口
        2. 提取 m3u8 地址
        3. 生成去 -private 变体
        """
        if not activity_id: return None
        cache_key = f"probe_{activity_id}"
        cached = self._play_probe_cache.get(cache_key)
        if cached is not None: return cached

        result = {"m3u8": [], "public_ok": False}
        # 公开接口列表
        public_paths = [
            f"/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/elite_lesson/resources/details/{activity_id}.json",
        ]
        hosts = [self.cdn1, self.cdn2, CDN3]
        tasks = [("detail", h + p) for h in hosts for p in public_paths]
        # 关键：不使用 cookie/mac，纯匿名探测
        fetch_results = []
        if _HAS_CONCURRENT:
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(self._http_get, url, 6, False, False, True, 1): url
                        for _, url in tasks}
                try:
                    for fut in as_completed(futs, timeout=10):
                        try:
                            d = fut.result()
                            if d and isinstance(d, dict):
                                fetch_results.append(d)
                        except Exception: pass
                except Exception: pass
        else:
            for _, url in tasks:
                try:
                    d = self._http_get(url, timeout=6, use_mac=False, use_cookie=False)
                    if d and isinstance(d, dict): fetch_results.append(d)
                except Exception: pass

        m3u8_list = []
        for data in fetch_results:
            # 方式 1：直接 relations
            for rk in ["national_course_resource", "course_resource", "elite_course_resource", "resources"]:
                arr = (data.get("relations") or {}).get(rk, [])
                for item in arr:
                    u = self._pick_best_video(item.get("ti_items", []))
                    if u: m3u8_list.append(u)
            # 方式 2：顶层 ti_items
            for it in data.get("ti_items", []):
                for u in (it.get("ti_storages") or []):
                    if re.search(r"\.m3u8", str(u), re.I): m3u8_list.append(str(u))
                if it.get("ti_storage") and re.search(r"\.m3u8", str(it["ti_storage"]), re.I):
                    m3u8_list.append(str(it["ti_storage"]))

        # 去重
        seen = set()
        uniq = []
        for u in m3u8_list:
            if u and u not in seen:
                seen.add(u); uniq.append(u)

        # 生成去 -private 变体
        result["m3u8"] = uniq
        result["public_ok"] = len(uniq) > 0
        self._play_probe_cache.set(cache_key, result)
        return result

    # ==================== 详情获取 ====================
    def _fetch_national_lesson(self, activity_id):
        hosts = [self.cdn2, self.cdn1]
        paths = [
            f"/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/national_lesson/resources/details/{activity_id}.json",
        ]
        tasks = [("nl", h + p) for h in hosts for p in paths]
        results = self._concurrent_fetch(tasks, max_workers=4, timeout_per_task=6)
        for _, data in results:
            if data and isinstance(data, dict) and (data.get("id") or data.get("title") or data.get("relations")):
                return data
        return None

    def _fetch_elite_lesson(self, activity_id):
        hosts = [self.cdn1, self.cdn2]
        paths = [
            f"/zxx/ndrv2/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/elite_lesson/resources/details/{activity_id}.json",
        ]
        tasks = [("elite", h + p) for h in hosts for p in paths]
        results = self._concurrent_fetch(tasks, max_workers=4, timeout_per_task=6)
        for _, data in results:
            if data and isinstance(data, dict) and (
                data.get("title") or data.get("global_title") or data.get("relations") or data.get("resource_type_code")
            ):
                return data
        rel_tasks = []
        for host in hosts:
            rel_tasks.append(("elite_rel", host + f"/zxx/ndrv2/elite_lesson/resources/{activity_id}/relation_resource.json"))
            rel_tasks.append(("elite_rel", host + f"/zxx/ndrs/elite_lesson/resources/{activity_id}/relation_resource.json"))
        rel_results = self._concurrent_fetch(rel_tasks, max_workers=4, timeout_per_task=6)
        for _, data in rel_results:
            if data and isinstance(data, dict):
                if data.get("id") == activity_id: return data
                try:
                    dump = json.dumps(data, ensure_ascii=False)
                    if len(dump) < 50000 and activity_id in dump: return data
                except Exception: pass
        return None

    def _fetch_singing_resource(self, activity_id):
        hosts = [self.cdn2, self.cdn1, CDN3]
        paths = [
            f"/zxx/ndrs/singing/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrv2/singing/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/national_lesson/resources/details/{activity_id}.json",
        ]
        tasks = [("sing", h + p) for h in hosts for p in paths]
        results = self._concurrent_fetch(tasks, max_workers=4, timeout_per_task=10)
        for _, data in results:
            if data and isinstance(data, dict): return data
        return None

    def _fetch_detail_json(self, activity_id):
        if not activity_id: return None
        cached = self._detail_json_cache.get(activity_id)
        if cached is not None: return cached

        hosts = [self.cdn1, self.cdn2, CDN3]
        core_paths = [
            f"/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/resources/{activity_id}.json",
            f"/zxx/ndrs/resources/{activity_id}.json",
            f"/zxx/ndrv2/resources/details/{activity_id}.json",
            f"/zxx/ndrs/resources/details/{activity_id}.json",
        ]
        tasks = [("core", h + p) for h in hosts for p in core_paths]
        results = self._concurrent_fetch(tasks, max_workers=8, timeout_per_task=6)
        for _, data in results:
            if data and isinstance(data, dict) and (
                data.get("title") or data.get("global_title") or data.get("relations") or data.get("resource_type_code")
            ):
                self._detail_json_cache.set(activity_id, data)
                return data

        edge_paths = [
            f"/zxx/ndrv2/prepare_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/prepare_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/resources/tch_material/details/{activity_id}.json",
            f"/zxx/ndrs/resources/tch_material/details/{activity_id}.json",
            f"/zxx/ndrv2/special_edu/resources/details/{activity_id}.json",
        ]
        tasks2 = [("edge", h + p) for h in hosts for p in edge_paths]
        results2 = self._concurrent_fetch(tasks2, max_workers=4, timeout_per_task=6)
        for _, data in results2:
            if data and isinstance(data, dict) and (
                data.get("title") or data.get("global_title") or data.get("relations") or data.get("resource_type_code")
            ):
                self._detail_json_cache.set(activity_id, data)
                return data

        loose_paths = [
            f"/zxx/ndrv2/elite_lesson/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrs/elite_lesson/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrv2/singing/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrs/singing/resources/{activity_id}/relation_resource.json",
        ]
        tasks3 = [("loose", h + p) for h in hosts for p in loose_paths]
        results3 = self._concurrent_fetch(tasks3, max_workers=4, timeout_per_task=6)
        for _, data in results3:
            if data and isinstance(data, dict):
                if data.get("id") == activity_id:
                    self._detail_json_cache.set(activity_id, data)
                    return data
                try:
                    dump = json.dumps(data, ensure_ascii=False)
                    if len(dump) < 50000 and activity_id in dump:
                        self._detail_json_cache.set(activity_id, data)
                        return data
                except Exception: pass
        self._detail_json_cache.set(activity_id, None)
        return None

    # ==================== 播放解析 ====================
    def _rank_media(self, media):
        """播放候选排序：优先公开未加密流。
        加密流（文件名含 -true-）与 -private 域地址匿名拉不到（401/403），
        必须排在公开流（无 -private、文件名含 .false）之后，否则并发抢跑时
        拿到加密地址就播不了。"""
        def score(it):
            u = str(it.get("url") or "")
            s = 0
            if "-private" in u:
                s -= 2
            if "-true-" in u:
                s -= 2
            if ".false" in u:
                s += 1
            return s
        return sorted(media, key=score, reverse=True)

    def _resolve_activity(self, activity_id, hint_type=""):
        if not activity_id: raise Exception("activityId 为空")
        cache_key = f"act_{activity_id}_{hint_type}"
        cached = self._act_cache.get(cache_key)
        if cached: return cached

        with self._resolve_lock:
            cached2 = self._act_cache.get(cache_key)
            if cached2: return cached2

            media = []
            fetcher_names = list(RES_TYPE_FETCHERS.values())
            if hint_type and hint_type in RES_TYPE_FETCHERS:
                preferred = RES_TYPE_FETCHERS[hint_type]
                fetcher_names = [preferred] + [f for f in fetcher_names if f != preferred]

            if _HAS_CONCURRENT and len(fetcher_names) > 1:
                with ThreadPoolExecutor(max_workers=len(fetcher_names)) as ex:
                    future_map = {}
                    for fname in fetcher_names:
                        method = getattr(self, fname, None)
                        if method is None: continue
                        future_map[ex.submit(method, activity_id)] = fname
                    all_media = []
                    try:
                        for fut in as_completed(future_map, timeout=30):
                            try:
                                d = fut.result(timeout=25)
                                if not d or not isinstance(d, dict): continue
                                m = self._extract_media(d)
                                m = [mm for mm in m if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                                if m: all_media.extend(m)
                                sub = self._resolve_video_sub_items(d)
                                sub = [mm for mm in sub if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                                if sub: all_media.extend(sub)
                            except Exception: continue
                    except Exception: pass
                    media = self._rank_media(all_media)
            else:
                all_media = []
                for fname in fetcher_names:
                    method = getattr(self, fname, None)
                    if method is None: continue
                    try:
                        d = method(activity_id)
                        if not d or not isinstance(d, dict): continue
                        m = self._extract_media(d)
                        m = [mm for mm in m if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                        if m: all_media.extend(m)
                        sub = self._resolve_video_sub_items(d)
                        sub = [mm for mm in sub if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                        if sub: all_media.extend(sub)
                    except Exception: continue
                media = self._rank_media(all_media)

            if not media:
                try:
                    by_id = self._resolve_by_id(activity_id)
                    if by_id: media = self._rank_media(by_id)
                except Exception: pass

            if not media:
                raise Exception(f"课包无视频流: {activity_id}")
            self._act_cache.set(cache_key, media)
            return media

    def _resolve_by_id(self, content_id):
        data = self._fetch_detail_json(content_id)
        if not data: raise Exception(f"未找到资源 JSON: {content_id}")
        media = self._extract_media(data)
        if media: return media
        for it in data.get("ti_items", []):
            u = it.get("ti_storage", "")
            if it.get("ti_storages"): u = it["ti_storages"][0]
            if re.search(r"\.pdf(\?|$)", str(u), re.I):
                if u.startswith("cs_path:"):
                    u = "https://r1-ndr-private.ykt.cbern.com.cn/" + re.sub(r"^cs_path:\$\{ref-path\}/?", "", u)
                return [{"kind": "file",
                         "title": data.get("title") or (data.get("global_title") or {}).get("zh-CN") or content_id,
                         "sub": "PDF", "url": u, "badge": "PDF"}]
        raise Exception("资源内没有可播放的视频地址")

    def _resolve_video_sub_items(self, data):
        if not data or not isinstance(data, dict): return []
        candidates, seen_ids = [], set()
        MAX_DEPTH, MAX_CANDS, VISIT_LIMIT = 5, 6, 120
        visit_count = [0]
        def _walk(node, depth=0):
            if not node or depth > MAX_DEPTH or visit_count[0] > VISIT_LIMIT: return
            if isinstance(node, list):
                for item in node:
                    _walk(item, depth + 1)
                    if visit_count[0] > VISIT_LIMIT: return
                return
            if not isinstance(node, dict): return
            visit_count[0] += 1
            rtype = str(node.get("resource_type_code", ""))
            prom = (node.get("custom_properties") or {}).get("prom_resouce_type", "")
            fmt = (node.get("custom_properties") or {}).get("format", "")
            is_doc = re.match(r"^(lesson_plandesign|learning_task|after_class_exercise|coursewares|assets_document|tch_material)$", rtype, re.I)
            has_media = bool(node.get("ti_items") and len(node.get("ti_items")) > 0)
            if not has_media and not is_doc and node.get("id") and node.get("id") not in seen_ids:
                if (re.search(r"video", rtype, re.I) or re.search(r"lesson", rtype, re.I) or
                        prom == "assets_video" or re.match(r"^(mp4|m3u8)$", str(fmt), re.I)):
                    seen_ids.add(node["id"]); candidates.append(node)
                    if len(candidates) >= MAX_CANDS: return
            for k, v in node.items():
                if k == "ti_items": continue
                if isinstance(v, (dict, list)):
                    _walk(v, depth + 1)
                    if len(candidates) >= MAX_CANDS or visit_count[0] > VISIT_LIMIT: return
        _walk(data)
        if not candidates: return []

        top_cands = candidates[:4]
        all_media = []
        if _HAS_CONCURRENT:
            with ThreadPoolExecutor(max_workers=min(4, len(top_cands))) as ex:
                future_map = {ex.submit(self._fetch_detail_json, c.get("id")): c for c in top_cands}
                try:
                    for fut in as_completed(future_map, timeout=10):
                        cand = future_map[fut]
                        try:
                            d2 = fut.result(timeout=6)
                            if not d2: continue
                            m2 = self._extract_media(d2)
                            m2 = [mm for mm in m2 if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                            if m2:
                                title_fix = (cand.get("global_title") or {}).get("zh-CN") or cand.get("title", "")
                                for mm in m2:
                                    if title_fix: mm["title"] = title_fix
                                all_media.extend(m2)
                        except Exception: pass
                except Exception: pass
        else:
            for cand in top_cands:
                try:
                    d2 = self._fetch_detail_json(cand.get("id"))
                    if not d2: continue
                    m2 = self._extract_media(d2)
                    m2 = [mm for mm in m2 if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                    if m2:
                        title_fix = (cand.get("global_title") or {}).get("zh-CN") or cand.get("title", "")
                        for mm in m2:
                            if title_fix: mm["title"] = title_fix
                        all_media.extend(m2)
                except Exception: pass
        return all_media

    def _extract_media(self, data):
        out = []
        if not data: return out
        title = (data.get("global_title") or {}).get("zh-CN") or data.get("title") or data.get("name", "资源")
        pic = ""
        try:
            thumbs = (data.get("custom_properties") or {}).get("thumbnails", [])
            if thumbs: pic = thumbs[0]
        except Exception: pass
        def _norm_url(u):
            if not u: return ""
            u = str(u)
            if u.startswith("cs_path:${ref-path}/"):
                u = "https://r1-ndr-private.ykt.cbern.com.cn/" + u.replace("cs_path:${ref-path}/", "")
            if u.startswith("//"): u = "https:" + u
            return u
        def _push(u, t2="", p2="", badge=""):
            if not u: return
            u = _norm_url(u)
            out.append({
                "title": t2 or title,
                "sub": (data.get("provider_list") or [{}])[0].get("name", "智慧教育"),
                "pic": p2 or pic,
                "url": u,
                "badge": badge or ("HLS" if re.search(r"\.m3u8(\?|$)", u, re.I) else ("MP4" if re.search(r"\.mp4(\?|$)", u, re.I) else ""))
            })
        rel_keys = ["national_course_resource", "course_resource", "elite_course_resource", "resources"]
        seen_vid = set()
        for rk in rel_keys:
            arr = (data.get("relations") or {}).get(rk, [])
            if not isinstance(arr, list): continue
            for item in arr:
                vurl = self._pick_best_video(item.get("ti_items", []))
                if not vurl or vurl in seen_vid: continue
                seen_vid.add(vurl)
                t2 = (item.get("global_title") or {}).get("zh-CN") or item.get("title", title)
                if not t2 or t2 in ("视频课程", "微课视频", "精品课视频", "视频") or re.match(r"^(视频|微课|精品课)", t2) or re.search(r"\.(mp4|m3u8)$", t2, re.I):
                    t2 = title
                p2 = ""
                try:
                    p2 = ((item.get("custom_properties") or {}).get("preview") or {}).get("frame1", "")
                except Exception: pass
                _push(vurl, t2, p2, "课程视频")
        for rk, arr in (data.get("relations") or {}).items():
            if rk in rel_keys or not isinstance(arr, list): continue
            for item in arr:
                vurl = self._pick_best_video(item.get("ti_items", []))
                if vurl and vurl not in seen_vid:
                    seen_vid.add(vurl)
                    t2 = (item.get("global_title") or {}).get("zh-CN") or item.get("title", title)
                    _push(vurl, t2, pic, rk)
        for it in data.get("ti_items", []):
            stors = it.get("ti_storages", [])
            stor = it.get("ti_storage", "")
            if stors:
                for u in stors:
                    if re.search(r"\.(m3u8|mp4)(\?|$)", str(u), re.I):
                        _push(u, it.get("ti_title", title))
            elif stor and re.search(r"\.(m3u8|mp4|pdf)(\?|$)", str(stor), re.I):
                _push(stor, it.get("ti_title", title))
        if data.get("video_url"): _push(data["video_url"], title)
        if data.get("media_url"): _push(data["media_url"], title)
        if not out:
            seen_urls = set()
            DEEP_MAX_DEPTH, DEEP_MAX_NODES = 6, 150
            deep_count = [0]
            def _deep_scan(node, ctx_title="", depth=0):
                if not node or depth > DEEP_MAX_DEPTH: return
                if deep_count[0] > DEEP_MAX_NODES: return
                if isinstance(node, list):
                    for item in node:
                        _deep_scan(item, ctx_title, depth + 1)
                        if deep_count[0] > DEEP_MAX_NODES: return
                    return
                if not isinstance(node, dict): return
                deep_count[0] += 1
                local_title = node.get("ti_title") or (node.get("global_title") or {}).get("zh-CN") or node.get("title") or ctx_title
                cand = []
                if node.get("ti_storages"): cand.extend(node["ti_storages"])
                if node.get("ti_storage"): cand.append(node["ti_storage"])
                if node.get("video_url"): cand.append(node["video_url"])
                if node.get("play_url"): cand.append(node["play_url"])
                if isinstance(node.get("src"), str): cand.append(node["src"])
                for cu in cand:
                    cu = str(cu)
                    if re.search(r"\.(m3u8|mp4)(\?|$)", cu, re.I) and cu not in seen_urls:
                        seen_urls.add(cu)
                        _push(cu, local_title, "", "深度解析")
                for k, v in node.items():
                    if k in ("ti_storages", "ti_storage"): continue
                    if isinstance(v, (dict, list)):
                        _deep_scan(v, local_title, depth + 1)
                        if deep_count[0] > DEEP_MAX_NODES: return
            _deep_scan(data, title)
        return out

    # ==================== m3u8 重写 ====================
    def _md5_hex(self, s): return hashlib.md5(s.encode("utf-8")).hexdigest()

    def _aes128_ecb_decrypt(self, key_bytes, cipher_b64):
        raw = base64.b64decode(cipher_b64)
        return _AES128.decrypt(raw, key_bytes)

    def _fetch_video_key_bytes(self, key_url):
        cached = self._key_cache.get(key_url)
        if cached is not None: return cached
        m = re.search(r"resource_keys/([a-fA-F0-9]+)", key_url)
        if not m: raise Exception("无法解析 keyId")
        key_id = m.group(1)
        base_key = key_url.split("?")[0]
        signs_url = base_key + "/signs"
        modes = [{"use_mac": False, "use_cookie": True},
                 {"use_mac": True, "use_cookie": True},
                 {"use_mac": False, "use_cookie": False}]
        signs_body = None
        for mode in modes:
            try:
                res = self._http_get(signs_url, timeout=8, use_mac=mode["use_mac"],
                                     use_cookie=mode["use_cookie"], json_resp=True)
                if res and res.get("nonce"): signs_body = res; break
            except Exception: pass
        if not signs_body or not signs_body.get("nonce"):
            raise Exception("signs 请求失败")
        nonce = signs_body["nonce"]
        sign = self._md5_hex(nonce + key_id)[:16]
        key_get = base_key + f"?nonce={urllib.parse.quote(nonce)}&sign={urllib.parse.quote(sign)}"
        key_body = None
        for mode in modes:
            try:
                res = self._http_get(key_get, timeout=8, use_mac=mode["use_mac"],
                                     use_cookie=mode["use_cookie"], json_resp=True)
                if res and res.get("key"): key_body = res; break
            except Exception: pass
        if not key_body or not key_body.get("key"):
            raise Exception("key 请求失败")
        result = self._aes128_ecb_decrypt(sign.encode("utf-8")[:16], key_body["key"])
        self._key_cache.set(key_url, result)
        return result

    def _rewrite_m3u8(self, m3u8_url):
        raw = str(m3u8_url)
        cache_key = f"m3u8_{self._md5_hex(raw)}"
        cached_text = self._m3u8_rewrite_cache.get(cache_key)
        if cached_text and "#EXTM3U" in cached_text:
            return cached_text
        base = raw.split("?")[0].rsplit("/", 1)[0] + "/"
        alts = [raw]
        if self.access_token:
            alts.append(raw + ("?" if "?" not in raw else "&") + f"accessToken={urllib.parse.quote(self.access_token)}")
        # 【新增】去 -private 变体
        for key in ("r1-ndr-private", "r2-ndr-private", "r3-ndr-private"):
            if key in raw:
                alt = raw.replace(key, key.replace("-private", ""))
                alts.append(alt)
                if self.access_token:
                    alts.append(alt + ("?" if "?" not in alt else "&") + f"accessToken={urllib.parse.quote(self.access_token)}")
        seen = set()
        alts = [u for u in alts if not (u in seen or seen.add(u))]

        text_body = ""
        for u in alts:
            cached_text = self._m3u8_text_cache.get(u)
            if cached_text and "#EXTM3U" in cached_text:
                text_body = cached_text; break

        if not text_body:
            modes = [{"use_cookie": True}, {"use_cookie": False}]
            def _try_fetch(url, mode):
                try:
                    h = {"User-Agent": self.headers["User-Agent"],
                         "Referer": "https://basic.smartedu.cn/",
                         "Origin": "https://basic.smartedu.cn"}
                    if self.access_token: h["accessToken"] = self.access_token
                    if mode["use_cookie"] and self.cookie: h["Cookie"] = self.cookie
                    req = urllib.request.Request(url, headers=h, method="GET")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return resp.read().decode("utf-8", errors="ignore")
                except Exception: return None
            for mode in modes:
                for u in alts:
                    body = _try_fetch(u, mode)
                    if body and "#EXTM3U" in body:
                        text_body = body
                        self._m3u8_text_cache.set(u, body)
                        break
                if text_body: break

        if not text_body or "#EXTM3U" not in text_body:
            raise Exception("m3u8 拉取失败")

        lines = text_body.splitlines()
        out_lines = []
        key_uri = None
        for line in lines:
            if "EXT-X-KEY" in line and 'URI="' in line:
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    key_uri = m.group(1)
                    if not key_uri.startswith("http"):
                        key_uri = urllib.parse.urljoin(base, key_uri)
                    break

        key_data_uri = ""
        if key_uri:
            try:
                key_bytes = self._fetch_video_key_bytes(key_uri)
                key_b64 = base64.b64encode(key_bytes).decode()
                key_data_uri = f"data:application/octet-stream;base64,{key_b64}"
            except Exception as e:
                print(f"[KEY] 获取失败: {e}，保留原始 URI")
                key_data_uri = self._with_token(key_uri)

        for line in lines:
            if not line:
                out_lines.append(line); continue
            if line.startswith("#"):
                if "EXT-X-KEY" in line and 'URI="' in line and key_data_uri:
                    line = re.sub(r'URI="[^"]+"', f'URI="{key_data_uri}"', line)
                out_lines.append(line)
            else:
                seg = line.strip()
                if not seg.startswith("http"):
                    seg = urllib.parse.urljoin(base, seg)
                # 段地址也去 -private
                for key in ("r1-ndr-private", "r2-ndr-private", "r3-ndr-private"):
                    if key in seg:
                        seg = seg.replace(key, key.replace("-private", ""))
                        break
                seg = self._with_token(seg)
                out_lines.append(seg)
        result = "\n".join(out_lines)
        self._m3u8_rewrite_cache.set(cache_key, result)
        return result

    def _save_m3u8_local(self, activity_id, content, suffix=""):
        safe_id = activity_id.replace("-", "_").replace("|", "_")
        if suffix:
            safe_suffix = re.sub(r'[^\w\u4e00-\u9fff]', '_', suffix)[:20]
            filename = os.path.join(self._local_m3u8_dir, f"smartedu_{safe_id}_{safe_suffix}.m3u8")
        else:
            filename = os.path.join(self._local_m3u8_dir, f"smartedu_{safe_id}.m3u8")
        try:
            with open(filename, "w", encoding="utf-8") as f: f.write(content)
            return filename
        except Exception as e:
            print(f"[FILE] 写入失败: {e}")
            return None

    def _paginate(self, items, pg, per_page=20):
        total = len(items)
        pagecount = (total + per_page - 1) // per_page if total > 0 else 1
        start = (pg - 1) * per_page
        return {"page": pg, "pagecount": pagecount,
                "list": items[start:start + per_page], "total": total}

    # ==================== T4 接口 ====================
    def homeContent(self, filter=False):
        self._ensure_tm_loaded()
        class_list = [{"type_id": xd, "type_name": xd} for xd in XD_LIST]
        filters = {}
        if filter:
            for xd in XD_LIST:
                items = self._xd_tm_map.get(xd, [])
                if not items: continue
                grades, subjects, publishers, volumes = set(), set(), set(), set()
                for it in items:
                    if it["nj"]: grades.add(it["nj"])
                    if it["xk"]: subjects.add(it["xk"])
                    if it["bb"]: publishers.add(it["bb"])
                    if it["cc"]: volumes.add(it["cc"])
                grade_list = sorted(grades, key=lambda x: GRADE_ORDER.get(x, 999))
                def _mk(keys, name, values):
                    return {"key": keys, "name": name,
                            "value": [{"n": "全部", "v": ""}] + [{"n": v, "v": v} for v in values]}
                defs = []
                if grade_list: defs.append(_mk("grade", "年级", grade_list))
                if subjects: defs.append(_mk("subject", "学科", sorted(subjects)))
                if publishers: defs.append(_mk("publisher", "版本", sorted(publishers)))
                if volumes: defs.append(_mk("volume", "册次", sorted(volumes)))
                if defs: filters[xd] = defs
        result = {"class": class_list}
        if filters: result["filters"] = filters
        return result

    def homeVideoContent(self):
        result = []
        for rec in self._recommend_config:
            key = f"{rec['tags']['zxxxd']}·{rec['tags']['zxxnj']}·{rec['tags']['zxxxk']}·{rec['tags']['zxxbb']}·{rec['tags']['zxxcc']}"
            tm_id = self._tm_id_map.get(key)
            if tm_id:
                pic = self._tm_pic_cache.get(tm_id) or self._tm_pic_cache.get(key) or self._build_cover_url(tm_id, rec['name'])
                result.append({"vod_id": key, "vod_name": rec["name"],
                               "vod_pic": pic, "vod_remarks": rec["tags"]["zxxxk"]})
        return {"list": result}

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        tid = urllib.parse.unquote(tid)
        try: pg = int(pg)
        except (ValueError, TypeError): pg = 1
        if tid not in self._xd_tm_map:
            return {"page": pg, "pagecount": 1, "list": [], "total": 0}
        all_items = self._xd_tm_map[tid]
        sel = {"grade": [], "subject": [], "publisher": [], "volume": []}
        if extend:
            obj = extend
            if isinstance(extend, str) and extend.strip():
                try: obj = json.loads(extend)
                except (json.JSONDecodeError, TypeError): obj = {}
            if isinstance(obj, dict):
                def _split(v):
                    if v is None: return []
                    if isinstance(v, list): return [str(x).strip() for x in v if x]
                    if isinstance(v, str): return [x.strip() for x in v.split(',') if x.strip()]
                    return []
                sel["grade"] = _split(obj.get("grade"))
                sel["subject"] = _split(obj.get("subject"))
                sel["publisher"] = _split(obj.get("publisher"))
                sel["volume"] = _split(obj.get("volume"))
        def _filter(items):
            res = []
            for it in items:
                if sel["grade"] and it["nj"] not in sel["grade"]: continue
                if sel["subject"] and it["xk"] not in sel["subject"]: continue
                if sel["publisher"] and it["bb"] not in sel["publisher"]:
                    if not ("" in sel["publisher"] and it["bb"] in ("未知版本", "")): continue
                if sel["volume"] and it["cc"] not in sel["volume"]:
                    if not ("" in sel["volume"] and it["cc"] in ("未知册次", "")): continue
                res.append(it)
            return res
        filtered = sorted(_filter(all_items), key=lambda x: GRADE_ORDER.get(x["nj"], 999))
        result = []
        for it in filtered:
            name = f"{it['nj']}·{it['xk']}·{it['bb']}·{it['cc']}"
            pic = it.get("pic") or self._tm_pic_cache.get(it["id"]) or self._tm_pic_cache.get(it["key"]) or ""
            result.append({
                "vod_id": urllib.parse.quote(it["key"], safe=""),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": it["xk"]
            })
        return self._paginate(result, pg, 20)

    def detailContent(self, ids):
        if isinstance(ids, list): ids = ids[0] if ids else ""
        if not ids: return {"list": []}
        ids = urllib.parse.unquote(ids)
        tm_id = self._tm_id_map.get(ids)
        if not tm_id:
            parts = re.split(r"[·|]", ids)
            if len(parts) >= 5:
                tm_id = self._tm_id_map.get(f"{parts[0]}·{parts[1]}·{parts[2]}·{parts[3]}·{parts[4]}")
        if not tm_id: return {"list": []}
        tree = self._fetch_tm_tree(tm_id)
        if not tree: return {"list": []}
        resources = self._fetch_tm_resources(tm_id)
        res_map = {}
        for r in resources:
            ch_ids = r.get("chapter_ids", [])
            if not ch_ids: continue
            target_cid = ch_ids[-1]
            res_map.setdefault(target_cid, []).append(r)
        cover = self._tm_pic_cache.get(tm_id) or self._tm_pic_cache.get(ids) or self._build_cover_url(tm_id, ids)
        play_from_list, play_url_list = [], []
        for unit in tree:
            unit_title = unit.get("title", "")
            if not unit_title: continue
            unit_title_safe = unit_title.replace("$", "＄").replace("#", "＃")
            seen_ids = set()
            episodes = []
            def walk(node):
                nid = node.get("id", "")
                if nid in res_map:
                    for r in res_map[nid]:
                        rid = r.get("id", "")
                        if rid in seen_ids: continue
                        seen_ids.add(rid)
                        title = r.get("title") or (r.get("global_title") or {}).get("zh-CN", "") or "视频"
                        title = title.replace("$", "＄").replace("#", "＃")
                        rtype = r.get("resource_type_code", "") or "unknown"
                        episodes.append({"name": title, "activity_id": rid, "rtype": rtype})
                    return
                for child in (node.get("child_nodes") or node.get("children") or []):
                    walk(child)
            walk(unit)
            if not episodes: continue
            name_count = {}
            for ep in episodes:
                n = ep["name"]
                if n in name_count:
                    name_count[n] += 1
                    ep["name"] = f"{n}-{name_count[n]}"
                else: name_count[n] = 0
            play_from_list.append(unit_title_safe)
            play_url_list.append("#".join(f"{ep['name']}${ep['rtype']}|{ep['activity_id']}" for ep in episodes))
        if not play_from_list: return {"list": []}
        return {"list": [{
            "vod_id": ids, "vod_name": ids, "vod_pic": cover, "vod_content": "",
            "vod_play_from": "$$$".join(play_from_list),
            "vod_play_url": "$$$".join(play_url_list),
            "vod_remarks": f"{len(play_from_list)}个单元"
        }]}

    def searchContent(self, key, quick=False, pg="1"):
        try: pg = int(pg)
        except (ValueError, TypeError): pg = 1
        return {"page": pg, "pagecount": 0, "list": [], "total": 0}

    # ==================== 播放（含免登录探测） ====================
    def _proxy_base(self):
        """localProxy 基础地址（与已验证可用的 nubwfp 同款写法）。"""
        try:
            u = super().getProxyUrl()
            if u:
                return u
        except Exception:
            pass
        try:
            from base.localProxy import get_port
            return "http://127.0.0.1:%d/proxy?do=py" % get_port()
        except Exception:
            pass
        return "http://127.0.0.1:9978/proxy?do=py"

    def _proxy_m3u8_url(self, m3u8_url):
        """把原始 m3u8 地址包成 localProxy 地址，播放器经壳内代理取重写后的 m3u8。"""
        b64 = base64.urlsafe_b64encode(m3u8_url.encode("utf-8")).decode().rstrip("=")
        base = self._proxy_base()
        sep = "&" if "?" in base else "?"
        return base + sep + "type=m3u8&u=" + b64

    def localProxy(self, param):
        t = param.get("type")
        if t == "m3u8":
            u = param.get("u", "")
            try:
                pad = "=" * (-len(u) % 4)
                orig = base64.urlsafe_b64decode(u + pad).decode("utf-8", errors="ignore")
            except Exception:
                return [404, "text/plain", b"bad url"]
            if not orig:
                return [404, "text/plain", b"bad url"]
            try:
                text = self._rewrite_m3u8(orig)
                if text and "#EXTM3U" in text:
                    return [200, "application/vnd.apple.mpegurl", text.encode("utf-8")]
            except Exception:
                pass
            # 重写失败：直接返回原始 m3u8（本站流未加密、分片无需头，可直接播）
            try:
                req = urllib.request.Request(orig, headers={
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": "https://basic.smartedu.cn/",
                    "Origin": "https://basic.smartedu.cn"}, method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                if raw and "#EXTM3U" in raw:
                    return [200, "application/vnd.apple.mpegurl", raw.encode("utf-8")]
            except Exception:
                pass
            return [404, "text/plain", b"m3u8 fetch fail"]
        return [404, "text/plain", b"unknown type"]

    def playerContent(self, flag, id, vipFlags=None):
        if not id: return {"parse": 0, "url": ""}
        id = urllib.parse.unquote(id)

        hint_type, activity_id = "", id
        if "|" in id and re.match(r'^[a-zA-Z_]+[a-zA-Z0-9_]*\|[0-9a-fA-F-]{36}$', id):
            hint_type, activity_id = id.split("|", 1)
        elif not re.match(r'^[0-9a-fA-F-]{36}$', id):
            if "|" in id:
                parts = id.rsplit("|", 1)
                if re.match(r'^[0-9a-fA-F-]{36}$', parts[-1]):
                    hint_type = parts[0] if parts[0] else ""
                    activity_id = parts[-1]

        if re.match(r'^[0-9a-fA-F-]{36}$', activity_id):
            # 【新增】先尝试免登录探测
            try:
                probe = self._probe_public_play_url(activity_id)
                if probe and probe.get("public_ok") and probe.get("m3u8"):
                    # 尝试去 -private 变体
                    for orig in probe["m3u8"]:
                        candidates = [orig]
                        for key in ("r1-ndr-private", "r2-ndr-private", "r3-ndr-private"):
                            if key in orig:
                                candidates.append(orig.replace(key, key.replace("-private", "")))
                        for u in candidates:
                            try:
                                new_m3u8 = self._rewrite_m3u8(u)
                                if new_m3u8 and "#EXTM3U" in new_m3u8:
                                    print(f"[PLAYER] 免登录探测成功: {u}")
                                    return {
                                        "parse": 0, "url": self._proxy_m3u8_url(u),
                                        "header": self.headers, "playUrl": "",
                                        "flag": flag, "js": "", "extra": {}
                                    }
                            except Exception as e:
                                continue
            except Exception as e:
                print(f"[PLAYER] 免登录探测失败: {e}")

            # 标准解析流程：逐个尝试全部候选（已按公开流优先排过序），
            # 第一个能重写成功的才用，避免并发抢跑拿到加密地址就播不了。
            try:
                media_list = self._resolve_activity(activity_id, hint_type=hint_type)
                play_url = ""
                for first in media_list:
                    url = first["url"]
                    try:
                        new_m3u8 = self._rewrite_m3u8(url)
                        if new_m3u8 and "#EXTM3U" in new_m3u8:
                            play_url = self._proxy_m3u8_url(url)
                            break
                    except Exception as e:
                        print(f"[PLAYER] 候选重写失败，试下一个: {url[:80]}: {e}")
                        continue
                if not play_url and media_list:
                    play_url = self._proxy_m3u8_url(media_list[0]["url"])
                if play_url:
                    return {
                        "parse": 0, "url": play_url,
                        "header": self.headers, "playUrl": "",
                        "flag": flag, "js": "", "extra": {}
                    }
            except Exception as e:
                print(f"[PLAYER] 播放解析失败: {e}")
                return {"parse": 0, "url": ""}

        if id.startswith("http"):
            return {"parse": 0, "url": self._with_token(id), "header": self.headers}
        return {"parse": 1, "url": id, "header": self.headers}