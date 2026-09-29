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
- `integrations/gewechat/`
  - `client.py`: Gewechat API 客户端
  - `bootstrap.py`: Gewechat 登录初始化
  - `webhook.py`: Gewechat 回调接收器
- 根目录的 `gateway_server.py`、`gewechat_*.py` 现在是兼容包装层。

## 启动实现
- `launcher/`
  - `start_all.ps1`: 供根目录 `start_all.bat` 调用的 Windows 全量启动实现
  - `run_all.py`: 聚合 API 和机器人日志的内部运行器

## Windows 入口
- 根目录 `start_all.bat`: 唯一保留的 Windows 启动入口，双击后启动 NapCat、API 和机器人。

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
