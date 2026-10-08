# 仅供个人学习研究，不得用于商业用途
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles

from ..client import HongguoClient, web_get_series_detail, web_get_homepage, web_get_category, web_search
from ..crypto import decrypt_episode, hongguo_content_key, decrypt_cenc_mp4
from ..state import StateDB

LOG = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / 'static'

_state_db: StateDB | None = None
_client: HongguoClient | None = None
_download_mgr: Any = None
_play_cache: dict[str, bytes] = {}  # vid -> decrypted mp4 bytes
_play_cache_lock = threading.Lock()
_MAX_CACHE = 15  # 最多缓存 15 集

# 并发防重入锁：同一集的多个并发 Range 请求共享一把锁，防止重复下载和重复解密
_inflight_locks: dict[str, threading.Lock] = {}
_inflight_master_lock = threading.Lock()

# 剧集详情缓存，避免每次切集都爬取外部网页
_series_cache: dict[str, dict] = {}
_series_cache_lock = threading.Lock()


def _get_inflight_lock(key: str) -> threading.Lock:
    with _inflight_master_lock:
        if key not in _inflight_locks:
            _inflight_locks[key] = threading.Lock()
        return _inflight_locks[key]


def _cleanup_inflight_lock(key: str) -> None:
    with _inflight_master_lock:
        _inflight_locks.pop(key, None)


def _fetch_and_decrypt_sync(cache_key: str, vid: str, series_name: str, episode_num: int) -> bytes:
    """在后台工作线程中执行下载与解密（带双重检查互斥锁，避免雪崩）"""
    with _play_cache_lock:
        if cache_key in _play_cache:
            return _play_cache[cache_key]

    lock = _get_inflight_lock(cache_key)
    with lock:
        # 双重检查：如果并发的另一个请求刚解密完成，直接返回缓存结果
        with _play_cache_lock:
            if cache_key in _play_cache:
                return _play_cache[cache_key]

        if not _client:
            raise RuntimeError('客户端未就绪')

        # 1. 获取播放地址与密钥
        vm = _client.get_video_model(vid)
        media = _client.select_best_media(vm)
        LOG.info('播放《%s》第%d集: %dp %s', series_name, episode_num,
                 media['quality'], media['codec'])

        # 2. 下载加密视频
        encrypted = _client.download_bytes(media['url'], media['referer'], timeout=120)

        # 3. 解密
        if media['spade_a']:
            decrypted = decrypt_episode(encrypted, media['spade_a'])
        else:
            decrypted = encrypted

        # 4. 存入内存缓存（淘汰最旧缓存）
        with _play_cache_lock:
            if len(_play_cache) >= _MAX_CACHE:
                oldest = next(iter(_play_cache))
                del _play_cache[oldest]
            _play_cache[cache_key] = decrypted

        _cleanup_inflight_lock(cache_key)
        return decrypted


def set_shared(state: StateDB, client: HongguoClient, download_mgr: Any) -> None:
    global _state_db, _client, _download_mgr
    _state_db = state
    _client = client
    _download_mgr = download_mgr


def create_app() -> FastAPI:
    app = FastAPI(title='HGDJ 红果短剧')

    if STATIC_DIR.is_dir():
        app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')

    @app.get('/', response_class=HTMLResponse)
    async def index():
        return FileResponse(STATIC_DIR / 'index.html')

    # ── 仪表盘 ──
    @app.get('/api/dashboard')
    async def dashboard():
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        return _state_db.dashboard_stats()

    # ── 首页推荐 ──
    @app.get('/api/recommend')
    async def recommend():
        try:
            items = web_get_homepage()
            return {'items': items[:30]}
        except Exception as e:
            return JSONResponse({'error': str(e)}, 500)

    # ── 分类浏览 ──
    @app.get('/api/categories')
    async def categories():
        return {'categories': [
            {'key': 'real-drama', 'name': '真人剧'},
            {'key': 'comic-drama', 'name': '漫剧'},
            {'key': 'ai-drama', 'name': 'AI剧'},
            {'key': 'comic', 'name': '漫画'},
        ]}

    @app.get('/api/browse')
    async def browse(category: str = 'real-drama', page: int = 1):
        try:
            data = web_get_category(category, max(1, page))
            return {
                'items': data.get('items', []),
                'pagination': data.get('pagination', {}),
                'category': category,
                'page': page,
            }
        except Exception as e:
            return JSONResponse({'error': str(e)}, 500)

    # ── 搜索 ──
    @app.get('/api/search')
    async def search(q: str = ''):
        keyword = q.strip()
        if not keyword:
            return {'items': []}
        try:
            items = web_search(keyword)
            return {'items': items[:30], 'query': keyword}
        except Exception as e:
            LOG.error('搜索异常: %s', e)
            return JSONResponse({'error': str(e)}, 500)

    def _get_cached_series_detail(series_id: str) -> dict:
        with _series_cache_lock:
            if series_id in _series_cache:
                return _series_cache[series_id]
        sd = web_get_series_detail(series_id)
        with _series_cache_lock:
            _series_cache[series_id] = sd
        # 预注册剧集及各分集 vid 到数据库，后续播放无需重复网络爬取
        if _state_db:
            try:
                _state_db.upsert_series(
                    series_id=series_id,
                    name=sd.get('series_name', ''),
                    cover_url=sd.get('series_cover', ''),
                    intro=sd.get('series_intro', ''),
                    episode_count=sd.get('episode_cnt', 0),
                    tags=','.join(sd.get('tags', [])) if isinstance(sd.get('tags'), list) else '',
                )
                vid_list = sd.get('vid_list', [])
                for i, vid in enumerate(vid_list, 1):
                    _state_db.upsert_episode(series_id, i, vid)
            except Exception as e:
                LOG.warning('预注册分集异常: %s', e)
        return sd

    # ── 剧集详情 ──
    @app.get('/api/series/{series_id}')
    async def series_detail(series_id: str):
        try:
            sd = await anyio.to_thread.run_sync(_get_cached_series_detail, series_id)
            # 获取下载状态
            episodes = _state_db.get_episodes(series_id) if _state_db else []
            in_queue = _state_db.is_in_queue(series_id) if _state_db else False
            ep_stats = _state_db.episode_stats(series_id) if _state_db else {}
            history = _state_db.get_series_history(series_id) if _state_db else None
            return {
                'detail': sd,
                'episodes': episodes,
                'in_queue': in_queue,
                'stats': ep_stats,
                'history': history,
            }
        except Exception as e:
            return JSONResponse({'error': str(e)}, 500)

    # ── 封面代理 ──
    @app.get('/api/poster/{series_id}')
    async def poster(series_id: str):
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        s = _state_db.get_series(series_id)
        if s and s.get('directory'):
            p = Path(s['directory']) / 'poster.jpg'
            if p.is_file():
                return FileResponse(str(p), media_type='image/jpeg',
                                    headers={'Cache-Control': 'max-age=3600'})
        # 代理远程封面
        if s and s.get('cover_url') and _client:
            try:
                data = await anyio.to_thread.run_sync(
                    _client.download_bytes, s['cover_url'], 'https://novel.snssdk.com/', 15, 2
                )
                return Response(data, media_type='image/jpeg',
                                headers={'Cache-Control': 'max-age=3600'})
            except Exception:
                pass
        return JSONResponse({'error': 'not found'}, 404)

    # ── 在线播放 ──
    @app.get('/api/play/{series_id}/{episode_num}')
    async def play(series_id: str, episode_num: int, request: Request):
        if not _client:
            return JSONResponse({'error': 'not ready'}, 503)
        try:
            # 优先从已下载的文件读取
            if _state_db:
                ep_row = _state_db.get_episode(series_id, episode_num)
                if ep_row and ep_row.get('status') == 'done' and ep_row.get('file_path'):
                    local_p = Path(ep_row['file_path'])
                    if local_p.is_file():
                        return FileResponse(str(local_p), media_type='video/mp4')

            # 优先从数据库缓存获取 vid
            vid = ''
            series_name = ''
            if _state_db:
                ep_row = _state_db.get_episode(series_id, episode_num)
                if ep_row and ep_row.get('vid'):
                    vid = ep_row['vid']
                s_row = _state_db.get_series(series_id)
                if s_row:
                    series_name = s_row.get('name', '')

            # 若数据库未缓存 vid，异步抓取剧集详情
            if not vid:
                sd = await anyio.to_thread.run_sync(_get_cached_series_detail, series_id)
                vid_list = sd.get('vid_list', [])
                if episode_num < 1 or episode_num > len(vid_list):
                    return JSONResponse({'error': f'集数超出范围 (1-{len(vid_list)})'}, 404)
                vid = vid_list[episode_num - 1]
                series_name = sd.get('series_name', '')

            cache_key = f'{series_id}_{episode_num}_{vid}'

            # 在后台线程池执行下载与解密（带防重入锁，绝不阻塞主事件循环）
            decrypted = await anyio.to_thread.run_sync(
                _fetch_and_decrypt_sync, cache_key, vid, series_name, episode_num
            )

            file_size = len(decrypted)
            range_header = request.headers.get('Range')

            if range_header:
                # 兼容 Safari、Chrome 和移动端浏览器必须的 HTTP 206 Partial Content
                try:
                    range_val = range_header.strip().replace('bytes=', '')
                    parts = range_val.split('-')
                    start = int(parts[0]) if parts[0] else 0
                    end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
                    start = max(0, start)
                    end = min(file_size - 1, end)
                    length = end - start + 1

                    return Response(
                        content=decrypted[start:end + 1],
                        status_code=206,
                        media_type='video/mp4',
                        headers={
                            'Content-Range': f'bytes {start}-{end}/{file_size}',
                            'Accept-Ranges': 'bytes',
                            'Content-Length': str(length),
                            'Cache-Control': 'private, max-age=300',
                        },
                    )
                except Exception as e:
                    LOG.warning('Range 解析失败: %s', e)

            return Response(
                content=decrypted,
                status_code=200,
                media_type='video/mp4',
                headers={
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(file_size),
                    'Cache-Control': 'private, max-age=300',
                },
            )
        except Exception as e:
            LOG.error('播放失败: %s', e)
            return JSONResponse({'error': str(e)}, 500)

    # ── 下载管理 ──
    @app.post('/api/download/{series_id}')
    async def add_download(series_id: str):
        if not _download_mgr:
            return JSONResponse({'error': 'not ready'}, 503)
        try:
            result = _download_mgr.enqueue_series(series_id)
            return result
        except Exception as e:
            return JSONResponse({'error': str(e)}, 500)

    @app.delete('/api/download/{series_id}')
    async def cancel_download(series_id: str):
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        _state_db.remove_from_queue(series_id)
        _state_db.set_series_status(series_id, 'cancelled')
        return {'ok': True}

    @app.get('/api/downloads')
    async def downloads():
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        queue = _state_db.get_queue()
        all_series = _state_db.list_series()
        downloading = [s for s in all_series if s['status'] in ('downloading', 'done', 'cancelled')]
        return {'queue': queue, 'history': downloading[:50]}

    # ── 观看历史 ──
    @app.get('/api/history')
    async def get_history():
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        return {'items': _state_db.get_history(limit=60)}

    @app.post('/api/history')
    async def save_history(request: Request):
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        try:
            body = await request.json()
            series_id = str(body.get('series_id', '')).strip()
            if not series_id:
                return JSONResponse({'error': '缺少 series_id'}, 400)
            _state_db.upsert_history(
                series_id=series_id,
                series_name=str(body.get('series_name', '')),
                series_cover=str(body.get('series_cover', '')),
                episode_num=int(body.get('episode_num', 1)),
                total_episodes=int(body.get('total_episodes', 1)),
                current_time=float(body.get('current_time', 0.0)),
                duration=float(body.get('duration', 0.0)),
            )
            return {'ok': True}
        except Exception as e:
            return JSONResponse({'error': str(e)}, 500)

    @app.delete('/api/history/{series_id}')
    async def delete_history_item(series_id: str):
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        _state_db.delete_history(series_id)
        return {'ok': True}

    @app.delete('/api/history')
    async def clear_all_history():
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        _state_db.delete_history()
        return {'ok': True}

    return app
