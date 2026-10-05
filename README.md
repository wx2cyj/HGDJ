# 🍎 HGDJ - 红果短剧下载与在线播放

自动下载红果短剧视频到指定目录，带 WebUI 管理界面。

基于红果 App 接口逆向，**突破网页端 3 集限制**获取全集，支持**按需选剧下载**与**网页端在线解密即点即播**，自动生成 Emby / Jellyfin 兼容目录与 NFO 刮削元数据。

---

## 功能特点

- **突破 3 集限制** — 逆向官方 App 双重签名算法（`X-Gorgon` / `X-Khronos`），直连 App 端视频源，获取全部集数数据。
- **原生 CENC 解密** — 纯 Python 还原 `spade_a` 密钥与 AES-128 CTR MP4 容器解密，生成标准 MP4。
- **Web 端即点即播** — 内置 HTML5 播放器，服务端实时解密推流，支持 `HTTP 206 Partial Content` 分段传输与拖拽寻道。
- **拒绝无脑全量，按需选择下载** — WebUI 界面支持分类浏览与剧名搜索，只有点击【下载全集】才会入队下载，绝不打满 NAS 硬盘。
- **Emby / Jellyfin 兼容** — 自动生成 `tvshow.nfo`、`episodedetails.nfo` 和 `poster.jpg`，智能跳过无变化重写。
- **Unraid 专属支持** — 提供现成的 Unraid Docker 图形化安装模板。

---

## 目录与路径规划

| 用途 | 容器内路径 | Unraid 宿主机路径 | 说明 |
|------|------------|-------------------|------|
| **配置文件** | `/config` | `/mnt/user/appdata/HGDJ/config` | 存放 `config.json` |
| **状态库** | `/data` | `/mnt/user/appdata/HGDJ/data` | 存放 SQLite 状态数据库 `state.sqlite3` |
| **运行日志** | `/logs` | `/mnt/user/appdata/HGDJ/logs` | 存放每日轮转日志 `hgdj.log` |
| **视频媒体库** | `/media` | `/mnt/user/QTZL/红果` | 下载好的短剧视频与 NFO 元数据 |

---

## 一、Docker 镜像信息

- **镜像地址**：`ghcr.io/wx2cyj/hgdj:latest`
- **平台架构**：`linux/amd64`

---

## 二、Unraid 图形化配置部署指南

### 第一步：准备配置文件目录

在 Unraid 终端中执行以下命令，创建所需目录：

```bash
mkdir -p /mnt/user/appdata/HGDJ/config /mnt/user/appdata/HGDJ/data /mnt/user/appdata/HGDJ/logs /mnt/user/QTZL/红果
```

将项目中的 `config.example.json` 复制到 `/mnt/user/appdata/HGDJ/config/config.json`：

```bash
curl -sSL https://raw.githubusercontent.com/wx2cyj/HGDJ/main/config.example.json -o /mnt/user/appdata/HGDJ/config/config.json
```

### 第二步：添加 Unraid 容器模板

1. 在 Unraid 终端中下载模板文件：
   ```bash
   curl -sSL https://raw.githubusercontent.com/wx2cyj/HGDJ/main/unraid/hgdj.xml -o /boot/config/plugins/dockerMan/templates-user/my-hgdj.xml
   ```
2. 进入 Unraid 网页端 **【Docker】** → 点击底部的 **【添加容器】（Add Container）**。
3. 在 **【模板】（Template）** 下拉菜单中选择 **`HGDJ`**（系统会自动填充所有配置项）。
4. 确认参数设置无误：

| 设置项 | 字段名 | 填写内容 | 说明 |
|--------|--------|----------|------|
| **名称** | Name | `HGDJ` | 容器名称 |
| **存储库** | Repository | `ghcr.io/wx2cyj/hgdj:latest` | 镜像地址 |
| **WebUI 端口** | Port: 8098 | `8098` | Web 界面访问端口，可按需修改 |
| **配置文件目录** | Path: /config | `/mnt/user/appdata/HGDJ/config` | 存放 config.json |
| **状态库目录** | Path: /data | `/mnt/user/appdata/HGDJ/data` | SQLite 数据库文件 |
| **日志目录** | Path: /logs | `/mnt/user/appdata/HGDJ/logs` | 运行日志 |
| **媒体目录** | Path: /media | `/mnt/user/QTZL/红果` | 视频下载保存目录 |
| **时区** | Variable: TZ | `Asia/Shanghai` | 确保时间准确 |
| **文件权限掩码** | Variable: UMASK | `000` | 赋予生成文件完全读写权限 |
| **运行参数** | Post Arguments | `--daemon` | 常驻后台运行 |

5. 点击最下方的 **【应用】（Apply）** 按钮即可。

---

## 三、Docker CLI 命令行运行（备用）

如果不使用 Unraid 模板，也可以直接在终端运行以下命令：

```bash
docker run -d --name HGDJ \
  --restart unless-stopped \
  -p 8098:8098 \
  -v /mnt/user/appdata/HGDJ/config:/config \
  -v /mnt/user/appdata/HGDJ/data:/data \
  -v /mnt/user/appdata/HGDJ/logs:/logs \
  -v /mnt/user/QTZL/红果:/media \
  -e TZ=Asia/Shanghai \
  -e UMASK=000 \
  ghcr.io/wx2cyj/hgdj:latest
```

---

## 四、WebUI 界面说明

访问 `http://[你的Unraid主机IP]:8098`：

1. **首页推荐 & 分类浏览**：展示最新、最热短剧海报与总集数，支持真人剧、漫剧、AI剧切换。
2. **搜索短剧**：顶部搜索框直接输入短剧名称快速检索。
3. **在线解密播放**：点击任意短剧打开详情弹窗，点击任意一集，顶部播放器立即解密开播，支持全屏、快进、左右切集。
4. **选剧下载**：点击右上角 **【下载全集】**，该剧才会加入后台下载队列；未点选的剧绝不会自动下载。
5. **下载管理**：点击导航栏 **【下载管理】** 查看实时下载进度与任务列表。

---

## 五、Emby / Jellyfin 刮削结构

下载完成后的媒体库结构直接兼容 Emby 和 Jellyfin，无需额外刮削插件：

```
/mnt/user/QTZL/红果/
└── 剧名A [hongguo-7688646466708966462]/
    ├── tvshow.nfo           # 剧集元数据（标题/简介/分类/标签）
    ├── poster.jpg           # 剧集封面
    └── Season 01/
        ├── 剧名A.S01E01.mp4 # 视频文件（已解密）
        ├── 剧名A.S01E01.nfo # 单集元数据
        ├── 剧名A.S01E02.mp4
        └── 剧名A.S01E02.nfo
```

---

## 许可证

仅供个人学习、技术研究与离线归档使用。
