# 仅供个人学习研究，不得用于商业用途
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from pathlib import Path

LOG = logging.getLogger('HGDJ')


def setup_logging(log_dir: str | None = None) -> None:
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(
            str(Path(log_dir) / 'hgdj.log'), when='midnight', backupCount=7,
            encoding='utf-8')
        handlers.append(fh)
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        LOG.error('配置文件不存在: %s', path)
        sys.exit(1)
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def main() -> None:
    import logging.handlers

    parser = argparse.ArgumentParser(description='HGDJ 红果短剧下载与在线播放')
    parser.add_argument('--config', default='/config/config.json', help='配置文件路径')
    parser.add_argument('--daemon', action='store_true', help='常驻后台运行')
    parser.add_argument('--port', type=int, default=None, help='WebUI 端口')
    args = parser.parse_args()

    cfg = load_config(args.config)

    log_dir = cfg.get('log', {}).get('directory')
    setup_logging(log_dir)

    LOG.info('🍎 HGDJ 红果短剧 启动中...')

    from .client import HongguoClient
    from .state import StateDB
    from .download import DownloadManager
    from .web.app import create_app, set_shared

    # 初始化组件
    dl_cfg = cfg.get('download', {})
    state = StateDB(cfg.get('state', {}).get('database', '/data/state.sqlite3'))
    client = HongguoClient(request_interval=dl_cfg.get('request_interval', 2.0))
    download_mgr = DownloadManager(
        client=client, state=state,
        media_root=dl_cfg.get('root', '/media'),
        concurrent=dl_cfg.get('concurrent', 2),
        retries=dl_cfg.get('retries', 3),
    )
    set_shared(state, client, download_mgr)

    # 启动下载管理器
    download_mgr.start()

    # 启动 WebUI
    port = args.port or cfg.get('web', {}).get('port', 8098)
    app = create_app()

    import uvicorn
    LOG.info('🌐 WebUI 启动: http://0.0.0.0:%d', port)
    uvicorn.run(app, host='0.0.0.0', port=port, log_level='warning')


if __name__ == '__main__':
    main()
