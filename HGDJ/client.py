# 仅供个人学习研究，不得用于商业用途
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
import random
import struct
import time
import urllib.parse
import urllib.request
from typing import Any

LOG = logging.getLogger(__name__)

# ── 设备模拟参数 ──
APP_BASE_URL = "https://api5-normal-sinfonlineb.fqnovel.com"
APP_USER_AGENT = (
    "com.phoenix.read/73532 (Linux; U; Android 16; zh_CN; 25053RT47C; "
    "Build/BP2A.250605.031.A3; Cronet/TTNetVersion:04657795 2026-01-23 "
    "QuicVersion:c67e9834 2025-09-08)"
)
WEB_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
WEB_BASE_URL = "https://hongguoduanju.com"


def _new_device_id() -> str:
    return str(random.randint(1_000_000_000_000_000_000, 9_000_000_000_000_000_000))


# ── 位操作工具 ──

def _rotate_left_8(val: int, shift: int) -> int:
    val &= 0xFF
    shift %= 8
    return ((val << shift) | (val >> (8 - shift))) & 0xFF


def _reverse_8(val: int) -> int:
    val &= 0xFF
    result = 0
    for _ in range(8):
        result = (result << 1) | (val & 1)
        val >>= 1
    return result


# ── X-Gorgon / X-Khronos 签名 ──

_SIGN_KEY = bytes([
    0x44, 0xb9, 0xb9, 0xd9, 0xa4, 0xae, 0xf9, 0xfc,
    0xa4, 0x93, 0xaa, 0x75, 0x7c, 0xa3, 0xc2, 0xc4,
    0xa4, 0x96, 0x93, 0x8f,
])


def _sign_request(query_string: str, body: bytes | None, timestamp: int) -> dict[str, str]:
    query_hash = hashlib.md5(query_string.encode()).digest()
    payload = bytearray(20)
    payload[0:4] = query_hash[0:4]
    headers: dict[str, str] = {}
    if body is not None:
        body_hash = hashlib.md5(body).digest()
        payload[4:8] = body_hash[0:4]
        headers['X-SS-STUB'] = body_hash.hex().upper()
    payload[12:16] = bytes([0, 6, 11, 28])
    struct.pack_into('>I', payload, 16, timestamp & 0xFFFFFFFF)
    for i in range(20):
        payload[i] ^= _SIGN_KEY[i]
    for i in range(20):
        mixed = _rotate_left_8(payload[i], 4) ^ payload[(i + 1) % 20]
        payload[i] = _reverse_8(mixed) ^ 0xFF ^ 20
    signature = bytes([0x84, 0x04, 0x40, 0x1c, 0x00, 0x00]) + bytes(payload)
    headers['X-Khronos'] = str(timestamp)
    headers['X-Gorgon'] = signature.hex()
    headers['X-SS-Req-Ticket'] = str(int(time.time() * 1000))
    return headers


# ── 红果 App API 客户端 ──

class HongguoClient:
    def __init__(self, request_interval: float = 2.0):
        self.device_id = _new_device_id()
        self.install_id = _new_device_id()
        self.request_interval = request_interval
        self._last_request = 0.0
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _throttle(self) -> None:
        wait = self.request_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.25))

    def _base_query(self) -> dict[str, str]:
        return {
            'aid': '8662', 'app_name': 'novelread',
            'version_code': '73532', 'version_name': '7.3.5.32',
            'manifest_version_code': '73532', 'update_version_code': '73532',
            'channel': 'update_64', 'device_platform': 'android',
            'os': 'android', 'ssmix': 'a', 'device_type': '25053RT47C',
            'device_brand': 'Redmi', 'language': 'zh',
            'os_api': '36', 'os_version': '16',
            'resolution': '1280*2772', 'dpi': '520', 'ac': 'wifi',
            'device_id': self.device_id, 'iid': self.install_id,
        }

    def app_request(self, path: str, payload: dict | None = None,
                    timeout: int = 30) -> dict[str, Any]:
        """向红果 App 后端发起签名请求"""
        self._throttle()
        query = self._base_query()
        query['_rticket'] = str(int(time.time() * 1000))
        body = json.dumps(payload, ensure_ascii=False).encode() if payload else None
        query_string = urllib.parse.urlencode(query)
        now = int(time.time())
        sign_headers = _sign_request(query_string, body, now)
        url = APP_BASE_URL.rstrip('/') + path + '?' + query_string
        req = urllib.request.Request(url, method='POST', data=body)
        req.add_header('User-Agent', APP_USER_AGENT)
        req.add_header('Accept', 'application/json')
        req.add_header('Accept-Encoding', 'gzip')
        req.add_header('X-XS-From-Web', '0')
        req.add_header('Sdk-Version', '2')
        if body:
            req.add_header('Content-Type', 'application/json; charset=utf-8')
        for k, v in sign_headers.items():
            req.add_header(k, v)
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                self._last_request = time.monotonic()
                return json.loads(raw) if raw else {}
        except Exception as e:
            self._last_request = time.monotonic()
            raise RuntimeError(f'红果 API 请求失败: {e}') from e

    # ── 业务方法 ──

    def get_video_model(self, video_id: str) -> dict:
        """获取单集的播放信息（CDN URL + 加密密钥）"""
        result = self.app_request('/novel/player/video_model/v1/', {
            'video_id': video_id,
            'content_type': 1,
            'biz_param': {'need_all_video_definition': True, 'video_platform': 3},
        })
        if result.get('code') != 0:
            raise RuntimeError(f"video_model 失败: {result.get('message', '未知错误')}")
        vm_raw = result.get('data', {}).get('video_model', '')
        if isinstance(vm_raw, str):
            return json.loads(vm_raw)
        return vm_raw

    def select_best_media(self, video_model: dict) -> dict:
        """从 video_model 中选择最佳画质"""
        video_list = video_model.get('video_list', {})
        if isinstance(video_list, dict):
            items = list(video_list.values())
        elif isinstance(video_list, list):
            items = video_list
        else:
            items = []
        best = None
        best_score = -1
        for item in items:
            meta = item.get('video_meta', {})
            codec = meta.get('codec_type', '').lower()
            if codec == 'bytevc2':
                continue
            # 解析 URL
            raw_url = item.get('main_url', '')
            try:
                media_url = base64.b64decode(raw_url).decode()
            except Exception:
                media_url = raw_url
            if not media_url.startswith('http'):
                continue
            # 画质评分
            height = 0
            try:
                height = int(meta.get('vheight', 0) or 0)
            except (ValueError, TypeError):
                pass
            score = height * 10
            if codec in ('h264', 'avc1'):
                score += 1
            # 密钥
            spade_a = item.get('encrypt_info', {}).get('spade_a', '')
            if score > best_score:
                best_score = score
                best = {
                    'url': media_url,
                    'quality': height,
                    'codec': codec,
                    'spade_a': spade_a,
                    'referer': 'https://novel.snssdk.com/',
                }
        if not best:
            raise RuntimeError('未找到可用的媒体变体')
        return best

    def download_bytes(self, url: str, referer: str = 'https://novel.snssdk.com/',
                       timeout: int = 120, max_retries: int = 3) -> bytes:
        """下载 URL 对应的完整文件，带重试机制"""
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url)
                req.add_header('User-Agent', WEB_USER_AGENT)
                req.add_header('Referer', referer)
                req.add_header('Connection', 'close')
                with self._opener.open(req, timeout=timeout) as resp:
                    return resp.read()
            except Exception as e:
                last_err = e
                LOG.warning('下载 CDN 分片异常 (第 %d/%d 次重试): %s', attempt + 1, max_retries, e)
                time.sleep(0.5 * (attempt + 1))
        raise last_err or RuntimeError('下载 CDN 文件失败')

    def download_range(self, url: str, start: int, end: int,
                       referer: str = 'https://novel.snssdk.com/',
                       timeout: int = 30) -> bytes:
        """Range 下载"""
        req = urllib.request.Request(url)
        req.add_header('User-Agent', WEB_USER_AGENT)
        req.add_header('Referer', referer)
        req.add_header('Range', f'bytes={start}-{end}')
        with self._opener.open(req, timeout=timeout) as resp:
            return resp.read()


# ── 网页端数据获取 ──

def web_fetch(path: str, timeout: int = 15) -> str:
    """从红果网页端获取 HTML"""
    url = WEB_BASE_URL + path
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={'User-Agent': WEB_USER_AGENT})
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
        encoding = resp.headers.get_content_charset() or 'utf-8'
        return raw.decode(encoding, errors='replace')


def web_get_series_detail(series_id: str) -> dict:
    """从网页端获取剧集详情（含 vid_list）"""
    import re
    html = web_fetch(f'/detail?series_id={series_id}')
    m = re.search(r'_ROUTER_DATA\s*=\s*(\{.*?\});', html, re.DOTALL)
    if not m:
        raise RuntimeError('无法解析网页数据')
    data = json.loads(m.group(1))
    detail_page = data.get('loaderData', {}).get('detail_page', {})
    sd = detail_page.get('seriesDetail', {})
    if not sd:
        raise RuntimeError('未获取到剧集详情')
    return sd


def web_get_homepage() -> list[dict]:
    """从网页端获取首页推荐"""
    import re
    import html as htmlmod
    raw_html = web_fetch('/')
    results = []
    # 从 mergeLoaderData 提取推荐数据
    m = re.search(r'data-fn-args="(.*?)"', raw_html)
    if m:
        args = htmlmod.unescape(m.group(1))
        try:
            parsed = json.loads(args)
            if isinstance(parsed, list) and len(parsed) > 1:
                for item in parsed[1]:
                    fn_args = item.get('routerDataFnArgs', [])
                    for fa in fn_args:
                        try:
                            sub = json.loads(fa)
                            video_list = sub.get('videoList', [])
                            for v in video_list:
                                if isinstance(v, dict) and v.get('series_id'):
                                    results.append(v)
                        except (json.JSONDecodeError, KeyError):
                            pass
        except (json.JSONDecodeError, KeyError):
            pass
    # 从链接提取 series_id
    if not results:
        ids = re.findall(r'/detail\?series_id=(\d+)', raw_html)
        for sid in dict.fromkeys(ids):
            results.append({'series_id': sid})
    return results


def web_get_category(category: str, page: int = 1) -> list[dict]:
    """从网页端获取分类列表"""
    import re
    import html as htmlmod
    path_map = {
        'real-drama': '/category/real-drama',
        'comic-drama': '/category/comic-drama',
        'ai-drama': '/category/ai-drama',
        'comic': '/category/comic',
    }
    path = path_map.get(category, f'/category/{category}')
    raw_html = web_fetch(path)
    results = []
    m = re.search(r'data-fn-args="(.*?)"', raw_html)
    if m:
        args = htmlmod.unescape(m.group(1))
        try:
            parsed = json.loads(args)
            if isinstance(parsed, list) and len(parsed) > 1:
                for item in parsed[1]:
                    fn_args = item.get('routerDataFnArgs', [])
                    for fa in fn_args:
                        try:
                            sub = json.loads(fa)
                            for key in ('videoList', 'data', 'series_list'):
                                vl = sub.get(key, [])
                                if isinstance(vl, list):
                                    for v in vl:
                                        if isinstance(v, dict) and v.get('series_id'):
                                            results.append(v)
                        except (json.JSONDecodeError, KeyError):
                            pass
        except (json.JSONDecodeError, KeyError):
            pass
    return results
