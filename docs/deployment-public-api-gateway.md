# 公网 API 网关部署

## 目标

- 阿里云服务器只暴露一个公网 API 网关。
- 本机继续运行真实查询服务和浏览器自动化。
- 服务器通过反向 SSH 隧道访问本机 API，不把本机服务直接暴露到公网。

## 端口规划

- 公网网关端口: `18743`
- 云主机本地隧道端口: `18781`
- 本机 API 端口: `8000`

这三个端口都故意避开常用默认端口。

## 一、服务器部署 Docker 网关

1. 进入项目目录。
2. 复制环境变量模板:

```bash
cp deploy/gateway/.env.example deploy/gateway/.env
```

3. 修改 `deploy/gateway/.env`:

```env
GATEWAY_PORT=18743
GATEWAY_AUTH_TOKEN=对外调用网关时使用的令牌
UPSTREAM_API_BASE_URL=http://host.docker.internal:18781
UPSTREAM_API_TOKEN=本机API使用的令牌
GATEWAY_REQUEST_TIMEOUT=240
```

4. 启动网关:

```bash
docker compose --env-file deploy/gateway/.env -f deploy/docker-compose.gateway.yml up -d --build
```

5. 健康检查:

```bash
curl http://127.0.0.1:18743/api/health
```

## 二、本机启动真实查询 API

本机 `.env` 中建议增加:

```env
API_HOST=127.0.0.1
API_PORT=8000
API_AUTH_TOKEN=本机API使用的令牌
```

启动本机 API:

```powershell
.\start_api.ps1
```

## 三、本机建立反向 SSH 隧道

Windows PowerShell:

```powershell
$env:SERVER_HOST="121.41.4.126"
$env:SERVER_USER="root"
$env:REMOTE_BIND_PORT="18781"
$env:LOCAL_API_PORT="8000"
.\scripts\start_reverse_tunnel.ps1
```

Linux / WSL:

```bash
SERVER_HOST=121.41.4.126 \
SERVER_USER=root \
REMOTE_BIND_PORT=18781 \
LOCAL_API_PORT=8000 \
bash scripts/start_reverse_tunnel.sh
```

这个隧道会把服务器上的 `127.0.0.1:18781` 转发到本机 `127.0.0.1:8000`。

## 四、外部调用方式

查询跟踪号:

```bash
curl -X POST "http://121.41.4.126:18743/api/tracking/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 对外调用网关时使用的令牌" \
  -d '{"tracking_no":"UUS6685590859556771"}'
```

查询 FBA:

```bash
curl -X POST "http://121.41.4.126:18743/api/fba/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 对外调用网关时使用的令牌" \
  -d '{"fba_code":"FBA123456","platform":"auto","include_order":true,"include_tracking":true}'
```

## 五、建议

- 云服务器安全组只放行 `18743`。
- `22` 端口限制为你自己的管理 IP。
- 如果你要长期运行隧道，建议后续把反向 SSH 隧道做成 Windows 计划任务或 `autossh` 常驻进程。
