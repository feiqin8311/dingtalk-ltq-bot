# 项目结构

## 根目录保留的核心文件
- `main.py`: 钉钉机器人入口
- `api_server.py`: 本地查询 API
- `logistics_query.py`: 物流查询核心逻辑
- `qq_query.py`: QQ 查询逻辑
- `wechat_query.py`: 微信查询逻辑
- `requirements.txt`: Python 依赖
- `OPERATIONS.md`: 运行与操作说明

## Python 模块目录
- `services/`
  - `gateway_server.py`: 公网中转网关主实现
  - `host_bootstrap.py`: Linux 宿主机 CDP 引导主实现
- `integrations/gewechat/`
  - `client.py`: Gewechat API 客户端
  - `bootstrap.py`: Gewechat 登录初始化
  - `webhook.py`: Gewechat 回调接收器
- 根目录的 `gateway_server.py`、`host_bootstrap.py`、`gewechat_*.py` 现在是兼容包装层。

## 脚本目录
- `scripts/windows/`
  - `start_all.ps1`: Windows 一键启动 NapCat + API + 机器人
  - `start_bot.ps1`: Windows 启动机器人
  - `start_api.ps1`: Windows 启动本地 API
  - `start_remote_node.ps1`: Windows 启动 API 并拉起远程隧道
- `scripts/linux/`
  - `start_bot.sh`: Linux 直接启动机器人
  - `start_bot_linux.sh`: Linux 读取 `.env.linux` 后启动机器人
  - `start_api.sh`: Linux 读取 `.env.linux` 后启动 API
  - `start_host_cdp.sh`: Linux 启动本地 Chrome CDP
  - `stop_host_cdp.sh`: Linux 停止本地 Chrome CDP
- `scripts/`
  - `setup_qq_route.py`: 自动写入 QQ 群和用户路由
  - `start_reverse_tunnel.ps1`: Windows 反向隧道
  - `start_reverse_tunnel.sh`: Linux 反向隧道
  - `start-napcat.sh` / `stop-napcat.sh`: NapCat 辅助脚本

## 兼容入口
- 根目录的 `start_*.ps1` / `start_*.sh` 仍然保留，但现在只是转发到 `scripts/windows/` 或 `scripts/linux/`。
- 旧命令暂时还能继续使用，后续以 `scripts/` 下的新路径为准。

## 其他目录
- `deploy/`: Docker 与网关部署文件
- `docs/`: 文档
- `tests/`: 自动化测试
- `NapCat.Shell/`: NapCatQQ 程序目录
- `data/`, `runtime/`, `tmp/`: 运行时目录，不作为业务代码目录

## 当前整理原则
- 先收敛脚本入口，避免继续把启动逻辑堆在根目录
- Python 主业务模块暂不大搬家，先保证运行路径稳定
- 确认长期稳定后，再考虑把 `gateway_server.py`、`qq_query.py`、`wechat_query.py` 等拆入包目录
