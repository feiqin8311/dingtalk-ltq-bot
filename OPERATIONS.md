# 项目流程

## 总体入口
- 机器人入口: `main.py`
- 业务核心: `logistics_query.py`
- QQ 询问逻辑: `qq_query.py`
- 微信实验逻辑: `wechat_query.py`

## 单聊业务选择
- 单聊首次进入时，机器人不会直接查询，而是先返回业务菜单。
- 回复 `1` 后进入持续 `FBA查询` 模式，直到回复 `重置`。
- 回复 `2` 后进入持续 `跟踪号查询` 模式，直到回复 `重置`。
- 跟踪号查询不查钉钉表格，而是按前缀走平台官网，未命中特殊前缀时回退到 `17track`。
- `uniuni` 当前已接入直达 `tracking-detail` URL 的页面查询，并从 UniUni 页面轨迹区提取事件。
- `gofo` 当前已接入 `Export Summary` 导出流程，并从导出文件中读取 `Current status` 作为状态结果。
- `usps` 当前已接入详情页轨迹抓取，并读取全部 `tb-step` 状态块作为轨迹列表。
- `ups` 当前已接入详情页当前状态抓取，并读取激活中的进度步骤文本作为状态结果。
- `yuntrack` 当前已接入 `Export Summary` 导出流程，并从导出文件中读取 `Delivery Status` 作为状态结果。
- `swiship` 当前已接入页面摘要和 `TRACKING HISTORY` 表格抓取，并同时返回摘要状态与历史轨迹。
- `amazon_us` 当前已接入页面大标题抓取，并读取 `h1.css-alxyr3` 文本作为状态结果。
- `amazon_us` 若直达详情页出现 `We're sorry / We couldn't find the package you're looking for`，会自动回到首页重新输入跟踪号查询，并按设定次数重试。

## 当前主流程
1. 启动时加载 `.env`。
2. 启动钉钉 Stream 客户端，注册 `LogisticsBotHandler`。
3. 收到钉钉文本消息后，把消息内容当作 `FBA` 编号处理。
4. 如果文本中包含 `微信`，则直接走微信分支，不查询钉钉表格。
5. 如果未命中 `微信` 关键字，才调用 `find_order_by_fba` 查询钉钉表格记录。
6. 命中记录后，先整理基础字段并回复。
7. 再根据 `货代公司` 自动选择物流查询平台。
8. 查询结果会追加到钉钉回复中。

## 当前货代分支
- `龙舟` -> `AGL`
  - 使用钉钉表里的 `物流编号` 作为 `BookingID`
  - 通过 Playwright 查询 AGL 页面
- `平谊` -> `平谊系统`
  - 直接使用用户在钉钉中发送的单号查询
  - 不依赖钉钉表里的 `物流编号`
- `堡森` -> `堡森系统`
  - 使用钉钉表里的 `物流编号`
  - 通过 Playwright 查询堡森页面
- `金为` -> `QQ`
  - 使用钉钉表里的 `物流编号`
  - 去指定 QQ 群里 `@李美慧` 询问物流状态
  - 取对方第一条回复
- `大黄蜂` -> `17TRACK`
  - 使用钉钉表里的 `物流编号`
  - 打开 `https://www.17track.net/zh-cn` 查询轨迹
- 其他货代公司 -> `美通`
  - 使用钉钉表里的 `物流编号`
  - 走接口查询

## 已移除逻辑
- 原先 `大黄蜂 -> QQ群 63017易达工具-DHF -> @DHF-B组报价专员` 这条逻辑已经移除。
- 现在 `大黄蜂` 统一走 `17TRACK`，不再通过 QQ 群询问。

## 各平台说明

## 美通
1. 使用接口查询轨迹。
2. 输入值为钉钉表里的 `物流编号`。

## AGL
1. 打开 `https://www.agl.amazon.com/freight-puma`。
2. 代码会自动启动本地 CDP Chrome，并通过 `Playwright + CDP` 连接浏览器。
3. 根据品牌选择对应账号密码，账号密码来自 `.env`。
4. 使用 `物流编号` 作为 `BookingID` 打开追踪页。
5. 查询完成后尝试退出登录，再关闭当前浏览器。

## 平谊
1. 打开登录页 `http://hzpy.rtb56.com/login.aspx`。
2. 输入账号密码并处理验证码，账号密码来自 `.env`。
3. 登录后进入运单查询页面。
4. 直接用用户在钉钉中发送的单号查询。
5. 打开详情并提取轨迹。

## 堡森
1. 打开堡森官网页面。
2. 通过 Playwright 自动启动本地 CDP Chrome 并连接。
3. 如果检测到未登录，则使用 `.env` 中的账号密码登录。
4. 在页面中输入 `物流编号` 查询。
5. 获取最新轨迹后关闭浏览器。

## QQ
1. 当前只配置了 `金为`。
2. 群名: `璧久FBA海运-杭州金为`
3. 提问对象: `李美慧`
4. 提问内容格式: `@李美慧 <物流编号> 物流状态`
5. 通过 NapCat OneBot HTTP API 发消息并轮询群消息。
6. 命中对方第一条新回复后返回。
7. 本机需要先启动 NapCat，并暴露 HTTP API 到 `QQ_API_BASE_URL`。
8. 启动后可执行 `python scripts/setup_qq_route.py --write-env` 自动写入 `QQ_JINWEI_GROUP_ID` 和 `QQ_JINWEI_USER_ID`。

## Windows + NapCatQQ 运行
1. 在 Windows 上运行本项目时，建议直接使用 Windows Python，不通过 WSL 启动浏览器。
2. 安装依赖:
   - `py -3.11 -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
   - `pip install -r requirements.txt`
   - `python -m playwright install chromium`
3. 启动 NapCatQQ:
   - 下载 `NapCat.Shell.zip`
   - 解压到本项目 `NapCat.Shell`
   - Windows 11 默认使用 `NapCat.Shell\launcher.bat`
   - Windows 10 在 `.env` 中设置 `NAPCAT_LAUNCHER_PATH=NapCat.Shell\launcher-win10.bat`
   - 打开控制台输出的 WebUI 地址并扫码登录 QQ
4. 在 NapCat WebUI 的网络配置中新建并启用 `HTTP 服务端`:
   - `host`: `127.0.0.1`
   - `port`: `6702`
   - `messagePostFormat`: `array`
   - `token`: 留空或自定义；如果自定义，需要同步写入本项目 `QQ_API_TOKEN`
5. 本项目 `.env` 中保持:
   - `QQ_API_BASE_URL=http://127.0.0.1:6702`
   - `QQ_API_TOKEN=`
   - `NAPCAT_LAUNCHER_PATH=NapCat.Shell\launcher.bat`
   - `NAPCAT_WAIT_SECONDS=90`
   - `LOCAL_CDP_USER_DATA_DIR=./data/chrome-cdp-windows`
6. NapCat HTTP 服务启动后执行:
   - `python scripts\setup_qq_route.py --write-env`
7. 只启动机器人:
   - `.\start_bot.ps1`
8. 启动 NapCatQQ 并启动机器人:
   - `.\start_all.ps1`

## 17TRACK
1. 当前只配置了 `大黄蜂`。
2. 打开 `https://www.17track.net/zh-cn`。
3. 当前跟踪号查询模式会直接打开新版英文直达页：
   - `https://t.17track.net/en#nums=<物流编号>`
4. 页面加载后直接提取轨迹时间线。
5. 如果出现引导弹窗，只关闭右上角 `×`，不点“下一页”。
6. 如果遇到验证码或人工验证，程序会暂停等待人工处理，再继续抓取结果。
7. 当前运行方式为本机直接启动浏览器。

## 本机运行现状
- 应用直接在本机 Python 环境中运行。
- Playwright 浏览器和本地 Chrome CDP 都在本机启动。
- 当前 17TRACK、堡森等网页自动化使用本机浏览器能力。
- 当前策略是“按需启动浏览器，单次查询结束后自动关闭项目专用 CDP 浏览器”。

## 微信现状
- `wechat_query.py` 已接入关键字分流。
- 只要钉钉消息中包含 `微信`，就不查钉钉表格，直接走微信分支。
- 当前支持两个 provider:
  - `WECHAT_PROVIDER=gui`
    - 使用 Linux 桌面微信 + `xdotool/wmctrl/xclip` 自动化
    - 支持两种打开会话策略:
      - `WECHAT_GUI_OPEN_MODE=search`
        - 默认值，始终通过微信搜索打开目标群，稳定但略慢
      - `WECHAT_GUI_OPEN_MODE=sidebar_recent`
        - 适合目标群已置顶或稳定出现在左侧最近会话列表
        - 可配 `WECHAT_GUI_RECENT_CHAT_POINTS=群名=x,y;另一个群=x,y`
        - 如果 OCR 没找到群名，会回退到这里配置的固定坐标
  - `WECHAT_PROVIDER=gewechat`
    - 通过 Gewechat HTTP API 发消息，不依赖桌面微信
    - 需要配置 `GEWECHAT_BASE_URL / GEWECHAT_TOKEN / GEWECHAT_APP_ID / GEWECHAT_CHAT_WXID`
- 当前微信分支默认只负责发送。
- `gewechat_webhook.py` 已提供最小 webhook 接收器，会把回调原始事件落到 `tmp/gewechat-callback-events.jsonl`。
- 因此微信能力当前状态是“已完成 provider 抽象，GUI 可发，Gewechat 可接入发送，回读链路待按真实回调格式联调”。

## Gewechat 接入说明
1. 部署 Gewechat 服务，拿到本地 API 地址。
   - 例如 `http://127.0.0.1:2531/v2/api`
2. 拿到登录后的 `token` 和 `appId`。
3. 找到目标群的 `wxid`，以及被 @ 对象的 `wxid`。
4. 启动本项目 webhook 接收器。
   - `python3 gewechat_webhook.py --host 0.0.0.0 --port 8788`
5. 在 `.env` 中配置：
   - `WECHAT_PROVIDER=gewechat`
   - `GEWECHAT_BASE_URL=...`
   - `GEWECHAT_TOKEN=...`
   - `GEWECHAT_APP_ID=...`
   - `GEWECHAT_REGION_ID=...`
   - `GEWECHAT_PROXY_IP=...`
   - `GEWECHAT_USERNAME=...`
   - `GEWECHAT_CHAT_WXID=...`
   - `GEWECHAT_AT_WXID=...`
   - `GEWECHAT_CALLBACK_URL=http://<本机内网地址>:8788`
     - 优先用 Gewechat 服务可直连的内网地址，不要先用公网地址
6. 之后钉钉消息里只要包含 `微信 <单号>`，就会走 Gewechat 发送分支。

## Gewechat 首次登录
1. 启动 Gewechat 服务和本项目 webhook。
2. 执行：
   - `python3 gewechat_bootstrap.py`
3. 脚本会自动：
   - 调 `getTokenId`
   - 调 `getLoginQrCode`
   - 输出 `app_id / uuid / qr_url`
   - 轮询 `checkLogin`
   - 登录成功后把 `GEWECHAT_TOKEN / GEWECHAT_APP_ID` 写回 `.env`
   - 自动调用 `setCallback`
4. 如果 `getLoginQrCode` 返回“创建设备失败”：
   - 先补 `GEWECHAT_REGION_ID`
   - 如需走指定代理，再补 `GEWECHAT_PROXY_IP`
   - 如果当前网络无法连设备节点，优先切换到稳定的中国大陆网络，最好与手机同省

## 本机启动建议
1. 安装项目依赖:
   - `conda create -y -n dingtalk-ltq-bot python=3.11`
   - `conda run -n dingtalk-ltq-bot python -m pip install -r requirements.txt`
2. 准备 Chrome:
   - 默认读取 `CHROME_BIN=/usr/bin/google-chrome`
3. 如需网页自动化浏览器:
   - `conda run -n dingtalk-ltq-bot python -m playwright install chromium`
4. 如需 QQ 查询:
   - 本机启动 NapCat / OneBot HTTP 服务
   - 确认 `.env` 中 `QQ_API_BASE_URL` 和 `QQ_API_TOKEN`
   - 执行 `conda run -n dingtalk-ltq-bot python scripts/setup_qq_route.py --write-env`
5. 启动机器人:
   - `conda run -n dingtalk-ltq-bot bash start_bot.sh`
6. 如果只想单独测试本地 CDP Chrome:
   - `bash start_host_cdp.sh 19444 visible`

## 公网 API 网关方案
- 推荐架构:
  - 阿里云服务器只部署 Docker 网关
  - 本机继续运行 `api_server.py` 和浏览器自动化查询
  - 本机通过反向 SSH 隧道把 `127.0.0.1:8000` 转发到云主机 `127.0.0.1:18781`
  - Docker 网关再把公网请求转发到这个云主机本地隧道端口
- 参考文档:
  - `docs/deployment-public-api-gateway.md`
- 关键端口:
  - 公网网关: `18743`
  - 云主机本地隧道: `18781`
  - 本机 API: `8000`

## 当前代码里的真实平台枚举
- `auto`
- `agl`
- `meitong`
- `pingyi`
- `baosen`
- `qq`
- `17track`
- `none`
