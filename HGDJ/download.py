# 仅供个人学习研究，不得用于商业用途
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent
from io import BytesIO

from .client import HongguoClient, web_get_series_detail
from .crypto import decrypt_episode, hongguo_content_key
from .state import StateDB

LOG = logging.getLogger(__name__)


def _sanitize_filename(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]', '_', value)
    value = re.sub(r'\s+', ' ', value).strip().rstrip('.')
    encoded = value.encode('utf-8')
    if len(encoded) > 200:
        value = encoded[:200].decode('utf-8', errors='ignore').rstrip().rstrip('.')
    return value or 'Untitled'


def _write_nfo(path: Path, root: Element) -> None:
    indent(root, space='  ')
    buf = BytesIO()
    ElementTree(root).write(buf, encoding='utf-8', xml_declaration=True)
    data = buf.getvalue()
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _sub(root: Element, name: str, value: object) -> None:
    node = SubElement(root, name)
    node.text = str(value)


class DownloadManager:
    def __init__(self, client: HongguoClient, state: StateDB,
                 media_root: str, concurrent: int = 2, retries: int = 3):
        self.client = client
        self.state = state
        self.media_root = Path(media_root)
        self.retries = retries
        self._executor = ThreadPoolExecutor(max_workers=concurrent, thread_name_prefix='dl')
        self._running = False
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._running = True
        self._stop_event.clear()
        threading.Thread(target=self._loop, daemon=True, name='dl-loop').start()
        LOG.info('下载管理器已启动')

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
        LOG.info('下载管理器已停止')

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                queue = self.state.get_queue()
                for item in queue:
                    if self._stop_event.is_set():
                        break
                    series_id = item['series_id']
                    pending = self.state.get_pending_episodes(series_id)
                    if not pending:
                        # 所有集都已完成
                        self.state.remove_from_queue(series_id)
                        self.state.set_series_status(series_id, 'done')
                        LOG.info('《%s》全部下载完成', item.get('name', series_id))
                        continue
                    for ep in pending:
                        if self._stop_event.is_set():
                            break
                        self._download_episode(series_id, ep)
            except Exception as e:
                LOG.error('下载循环异常: %s', e)
            self._stop_event.wait(timeout=10)

    def enqueue_series(self, series_id: str) -> dict:
        """将剧集加入下载队列：获取详情 → 注册分集 → 入队"""
        # 从网页端获取详情
        sd = web_get_series_detail(series_id)
        name = sd.get('series_name', '')
        cover = sd.get('series_cover', '')
        intro = sd.get('series_intro', '')
        episode_count = sd.get('episode_cnt', 0)
        tags_list = sd.get('tags', [])
        tags_str = ','.join(tags_list) if isinstance(tags_list, list) else str(tags_list)

        self.state.upsert_series(
            series_id=series_id, name=name, cover_url=cover,
            intro=intro, tags=tags_str, episode_count=episode_count)

        # 注册所有分集 vid
        vid_list = sd.get('vid_list', [])
        for i, vid in enumerate(vid_list, 1):
            self.state.upsert_episode(series_id, i, vid)

        # 创建目录
        dir_name = f'{_sanitize_filename(name)} [hongguo-{series_id}]'
        series_dir = self.media_root / dir_name
        series_dir.mkdir(parents=True, exist_ok=True)
        self.state.set_series_directory(series_id, str(series_dir))

        # 写 tvshow.nfo
        self._write_tvshow_nfo(series_dir, sd)

        # 下载封面
        if cover:
            try:
                poster_data = self.client.download_bytes(cover, timeout=30)
                (series_dir / 'poster.jpg').write_bytes(poster_data)
            except Exception as e:
                LOG.warning('封面下载失败: %s', e)

        # 加入队列
        self.state.add_to_queue(series_id)
        self.state.set_series_status(series_id, 'downloading')

        return {
            'series_id': series_id, 'name': name,
            'episode_count': episode_count, 'vid_count': len(vid_list),
        }

    def _download_episode(self, series_id: str, ep: dict) -> None:
        ep_num = ep['episode_num']
        vid = ep['vid']
        if not vid:
            LOG.warning('第 %d 集缺少 vid，跳过', ep_num)
            return

        series = self.state.get_series(series_id)
        if not series:
            return
        series_name = series.get('name', '')
        series_dir = Path(series.get('directory', ''))

        self.state.set_episode_status(series_id, ep_num, 'downloading')
        LOG.info('开始下载《%s》第 %d 集 (vid=%s)', series_name, ep_num, vid)

        for attempt in range(self.retries):
            try:
                # 1. 获取播放地址
                vm = self.client.get_video_model(vid)
                media = self.client.select_best_media(vm)
                LOG.info('  画质: %dp, 编码: %s', media['quality'], media['codec'])

                # 2. 下载加密视频
                encrypted = self.client.download_bytes(media['url'], media['referer'], timeout=300)
                LOG.info('  已下载 %.1f MB 加密数据', len(encrypted) / 1048576)

                # 3. 解密
                if media['spade_a']:
                    decrypted = decrypt_episode(encrypted, media['spade_a'])
                    LOG.info('  CENC 解密完成')
                else:
                    decrypted = encrypted
                    LOG.info('  无加密，直接保存')

                # 4. 保存文件
                season_dir = series_dir / 'Season 01'
                season_dir.mkdir(parents=True, exist_ok=True)
                filename = f'{_sanitize_filename(series_name)}.S01E{ep_num:02d}.mp4'
                filepath = season_dir / filename
                filepath.write_bytes(decrypted)

                # 5. 写 episode NFO
                self._write_episode_nfo(season_dir, series_name, ep_num, filename)

                # 6. 更新状态
                self.state.set_episode_status(
                    series_id, ep_num, 'done',
                    file_path=str(filepath), file_size=len(decrypted))
                LOG.info('  ✅ 第 %d 集下载完成: %s (%.1f MB)',
                         ep_num, filename, len(decrypted) / 1048576)
                return

            except Exception as e:
                LOG.error('  ❌ 第 %d 集下载失败 (尝试 %d/%d): %s',
                          ep_num, attempt + 1, self.retries, e)
                if attempt < self.retries - 1:
                    time.sleep(3 * (attempt + 1))

        self.state.set_episode_status(series_id, ep_num, 'failed')

    def _write_tvshow_nfo(self, series_dir: Path, sd: dict) -> None:
        root = Element('tvshow')
        title = sd.get('series_name', '')
        _sub(root, 'title', title)
        _sub(root, 'originaltitle', title)
        _sub(root, 'plot', sd.get('series_intro', ''))
        _sub(root, 'studio', '红果短剧')
        tags = sd.get('tags', [])
        if isinstance(tags, list):
            for tag in tags:
                _sub(root, 'genre', tag)
        uid = SubElement(root, 'uniqueid', {'type': 'hongguo', 'default': 'true'})
        uid.text = str(sd.get('series_id', ''))
        _write_nfo(series_dir / 'tvshow.nfo', root)

    def _write_episode_nfo(self, season_dir: Path, series_name: str,
                           ep_num: int, video_filename: str) -> None:
        root = Element('episodedetails')
        _sub(root, 'title', f'第{ep_num}集')
        _sub(root, 'showtitle', series_name)
        _sub(root, 'season', 1)
        _sub(root, 'episode', ep_num)
        _sub(root, 'studio', '红果短剧')
        nfo_name = video_filename.rsplit('.', 1)[0] + '.nfo'
        _write_nfo(season_dir / nfo_name, root)
