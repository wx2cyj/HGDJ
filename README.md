# 🍎 HGDJ - 红果短剧下载与在线播放

自动下载红果短剧视频到指定目录，带 WebUI 在线播放与选剧下载管理界面。

基于红果短剧 App 端原生接口逆向工程，**彻底突破网页端 3 集试看限制**获取全集资源。支持**按需选剧下载**（绝不自动全量塞满 NAS 硬盘）与**网页端在线解密即点即播**，自动生成 Emby / Jellyfin 兼容的媒体库目录与 NFO 刮削元数据。

---

## 🌟 功能特点

- **突破 3 集限制** — 逆向官方 App 移动端双重签名算法（`X-Gorgon` / `X-Khronos` / `X-SS-Req-Ticket`），直连 App 端视频后端，全部分集均可直接获取 1080P/720P 媒体源（网页端 `hongguoduanju.com` 第 4 集起 404）。
- **原生 CENC 解密** — 纯 Python 还原 `spade_a` 密钥派生算法与 AES-128 CTR MP4 容器解密，服务端直接吐出标准可播放的 MP4 文件。
- **Web 端即点即播** — 内置 HTML5 视频播放器，服务端实时解密推流，支持 `HTTP 206 Partial Content` (Range 请求)，进度条秒开、随意拖拽寻道、播完自动连播下一集。
- **拒绝无脑全量，按需选择下载** — WebUI 界面支持热门推荐、分类浏览与关键字检索。只有点击【下载全集】才会入队下载，绝不打满 NAS 硬盘。
- **Emby / Jellyfin 兼容** — 自动生成标准影视目录规范，包含 `tvshow.nfo`、`episodedetails.nfo` 和 `poster.jpg`，视频按 `S01E01.mp4` 规范命名，智能跳过无变化重写。
- **Unraid 专属支持** — 提供现成的 Unraid Docker 图形化安装模板，支持一键部署。

---

## 📊 HGDJ 与 HGXZ 对比

| 对比维度 | HGXZ（黄果下载） | HGDJ（红果短剧） |
| :--- | :--- | :--- |
| **视频数据源** | 黄果短剧站（采集站聚合） | **红果短剧官方 App 端原生源** |
| **下载策略** | 定时全量遍历所有分类并全部下载（易塞满硬盘） | **WebUI 按需选剧下载，点哪部下哪部** |
| **在线播放** | 仅管理下载进度，无网页在线播放功能 | **内置播放器，实时解密推流即点即播** |
| **突破限制** | 无（依赖采集站上架速度） | **逆向设备签名，绕过官方网页 3 集试看限制** |
| **默认 WebUI 端口** | `8099` | **`8098`**（紧挨黄果，好记且避开 CookieCloud 的 8088） |
| **Emby 刮削结构** | 支持 | 支持 |

---

## 📁 目录与路径规划

| 用途 | 容器内路径 | Unraid / NAS 宿主机路径 | 说明 |
| :--- | :--- | :--- | :--- |
| **配置文件** | `/config` | `/mnt/user/appdata/HGDJ/config` | 存放 `config.json` |
| **状态库** | `/data` | `/mnt/user/appdata/HGDJ/data` | 存放 SQLite 状态数据库 `state.sqlite3` |
| **运行日志** | `/logs` | `/mnt/user/appdata/HGDJ/logs` | 存放每日轮转日志 `hgdj.log` |
| **视频媒体库** | `/media` | `/mnt/user/QTZL/红果` | 下载好的短剧视频与 NFO 元数据 |

---

## 一、Docker 镜像信息

- **镜像地址**：`ghcr.io/wx2cyj/hgdj:latest`
- **平台架构**：`linux/amd64`
- **镜像构建**：基于 GitHub Actions 自动化构建，源码推送即自动更新镜像。

---

## 二、Unraid 图形化配置部署指南

### 第一步：准备配置文件目录

在 Unraid 终端中执行以下命令创建所需目录：

```bash
mkdir -p /mnt/user/appdata/HGDJ/config /mnt/user/appdata/HGDJ/data /mnt/user/appdata/HGDJ/logs /mnt/user/QTZL/红果
```

将项目中的 `config.example.json` 复制到 `/mnt/user/appdata/HGDJ/config/config.json`：

```bash
curl -sSL https://raw.githubusercontent.com/wx2cyj/HGDJ/main/config.example.json -o /mnt/user/appdata/HGDJ/config/config.json
```

### 第二步：添加 Unraid 容器模板

1. 在 Unraid 终端中下载专属 XML 模板文件：
   ```bash
   curl -sSL https://raw.githubusercontent.com/wx2cyj/HGDJ/main/unraid/hgdj.xml -o /boot/config/plugins/dockerMan/templates-user/my-hgdj.xml
   ```
2. 进入 Unraid 网页端 **【Docker】** → 滑动到底部点击 **【添加容器】（Add Container）**。
3. 在顶部的 **【模板】（Template）** 下拉菜单中选择 **`HGDJ`**（系统会自动填充所有配置项与路径映射）。
4. 确认参数设置无误：

| 设置项 | 字段名 | 填写内容 | 说明 |
| :--- | :--- | :--- | :--- |
| **名称** | Name | `HGDJ` | 容器名称 |
| **存储库** | Repository | `ghcr.io/wx2cyj/hgdj:latest` | 镜像地址 |
| **WebUI 端口** | Port: 8098 | `8098` | Web 界面访问端口（避开 8088 冲突） |
| **配置文件目录** | Path: /config | `/mnt/user/appdata/HGDJ/config` | 存放 `config.json` |
| **状态库目录** | Path: /data | `/mnt/user/appdata/HGDJ/data` | SQLite 数据库文件 |
| **日志目录** | Path: /logs | `/mnt/user/appdata/HGDJ/logs` | 运行日志 |
| **媒体目录** | Path: /media | `/mnt/user/QTZL/红果` | 视频下载保存目录 |
| **时区** | Variable: TZ | `Asia/Shanghai` | 确保容器时间准确 |
| **文件权限掩码** | Variable: UMASK | `000` | 赋予生成文件 777 权限，避免 Unraid SMB 权限问题 |
| **运行参数** | Post Arguments | `--daemon` | 常驻后台运行 |

5. 点击最下方的 **【应用】（Apply）** 按钮即可启动容器。

---

## 三、Docker CLI 命令行运行（飞牛 NAS / 普通 Linux 备用）

如果不使用 Unraid 模板，也可以在终端直接执行命令运行：

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

## 四、配置文件详细说明

配置文件路径：`/config/config.json`（完整模板见 `config.example.json`）

```json
{
  "web": {
    "port": 8098
  },
  "download": {
    "root": "/media",
    "concurrent": 2,
    "retries": 3,
    "request_interval": 2
  },
  "state": {
    "database": "/data/state.sqlite3"
  },
  "log": {
    "directory": "/logs"
  }
}
```

| 参数项 | 类型 | 默认推荐值 | 说明 |
| :--- | :--- | :--- | :--- |
| `web.port` | 整数 | `8098` | 容器内 WebUI 服务监听端口 |
| `download.root` | 字符串 | `/media` | 视频下载与 NFO 生成保存的根目录 |
| `download.concurrent` | 整数 | `2` | 下载并发工作线程数（建议 1~3，避免频繁请求） |
| `download.retries` | 整数 | `3` | 单集视频下载与解密失败最大重试次数 |
| `download.request_interval` | 浮点数 | `2.0` | API 请求节流间隔（秒），模拟正常客户端行为 |
| `state.database` | 字符串 | `/data/state.sqlite3` | SQLite 任务状态与下载进度库路径 |
| `log.directory` | 字符串 | `/logs` | 运行日志存放路径（自动每日轮转） |

---

## 五、WebUI 界面与功能操作

部署完成后，在浏览器访问：`http://[你的NAS主机IP]:8098`：

1. **首页推荐 & 分类浏览**：
   - 顶部提供「真人剧 / 漫剧 / AI剧 / 漫画」分类切换。
   - 自动展示短剧高清海报封面、总集数、题材标签与简介。
2. **搜索短剧**：
   - 顶部搜索框直接输入短剧名字（如《反派亲妈》、《今天有朵云爱我》等），实时检索匹配。
3. **在线解密播放（核心功能）**：
   - 点击短剧卡片打开详情弹窗，选集列表中点击任意一集（例如第 1 集、第 4 集、第 50 集）；
   - 顶部播放器立即自动加载推流播放；
   - 支持全屏、倍速、进度条任意拖拽跳转（基于 HTTP 206 Range 支持）；
   - 播完当前集后自动无缝切到下一集。
4. **按需选剧下载**：
   - 在短剧详情弹窗中点击右上角 **【下载全集】**，该剧才会加入后台下载队列；
   - 页面实时高亮已下载（绿）、下载中（黄动效）、失败（红）的分集状态；
   - 只有你手动点选的剧才会下载，不点击绝不下，保护 NAS 硬盘容量。
5. **下载管理**：
   - 切换到导航栏 **【下载管理】** 页面，可实时查看当前正在下载的队列、下载进度百分比、已完成集数与历史任务，支持随时取消下载。

---

## 六、Emby / Jellyfin 刮削结构

下载完成后的媒体库结构直接兼容 Emby 和 Jellyfin，无需额外安装任何刮削插件：

```
/mnt/user/QTZL/红果/
└── 家有五女，穿越来的他连夜搞事业啦 [hongguo-7688646466708966462]/
    ├── tvshow.nfo           # 剧集元数据（标题/简介/分类标签/红果唯一ID）
    ├── poster.jpg           # 自动抓取的海报封面
    └── Season 01/
        ├── 家有五女，穿越来的他连夜搞事业啦.S01E01.mp4 # 标准 MP4 视频
        ├── 家有五女，穿越来的他连夜搞事业啦.S01E01.nfo # 单集元数据
        ├── 家有五女，穿越来的他连夜搞事业啦.S01E02.mp4
        └── 家有五女，穿越来的他连夜搞事业啦.S01E02.nfo
```

在 Emby 中添加媒体库时：
- 内容类型选择：**节目（电视节目）**
- 文件夹路径选择：`/mnt/user/QTZL/红果`
- Emby 将直接通过本地 NFO 与图片秒级识别，呈现精美短剧海报墙。

---

## 七、常见问题与排查

| 常见问题 | 原因与处理方案 |
| :--- | :--- |
| **为什么网页端只有 3 集，这里能看全集？** | 网页版 `hongguoduanju.com` 是字节跳动的引流站，第 4 集服务端写死 404；本工具逆向了红果 App 原生客户端 API 与请求签名，直连移动端视频流与密钥解密，不受 3 集试看限制。 |
| **端口 8088 冲突怎么办？** | 项目已将默认端口调整为 `8098`，若仍需更改，只需在 Unraid 模板中修改端口映射，或在 `config.json` 中修改 `web.port`。 |
| **Unraid 拉取镜像提示权限拒绝 (403/unauthorized)** | GitHub Package 首次推送默认为 Private。请访问 https://github.com/users/wx2cyj/packages/container/package/hgdj → 右下角 **Package settings** → 底部 **Danger Zone** → 将可见性改为 **Public** 即可免密直接拉取。 |
| **播放器拖动进度条卡顿吗？** | 后端完整实现了 `HTTP 206 Partial Content` 分段传输支持，主流浏览器（Chrome、Edge、Safari、移动端浏览器）均可直接拖拽快进快退。 |
| **短剧下架或失效导致某集报错？** | 单集若因网络瞬时波动失败，系统会自动重试 3 次；若该剧集源已被官方下架，该集会标记为失败状态并跳过，不会中断后续正常集数的下载。 |

---

## 许可证

本项目仅供个人学习、技术研究、逆向协议分析与离线归档使用，请勿用于商业用途或分发传播。
