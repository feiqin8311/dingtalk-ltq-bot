# 公网 API 网关部署

## 目标

- 阿里云服务器只暴露一个公网 API 网关。
- 本机继续运行真实查询服务和浏览器自动化。
- 服务器通过 Tailscale 或反向 SSH 隧道访问本机 API，不把本机服务直接暴露到公网。

## 端口规划

- 公网网关端口: `18743`
- 云主机本地隧道端口: `18781`
- 本机 API 端口: `18081`

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
UPSTREAM_API_BASE_URL=http://100.99.40.87:18081
UPSTREAM_API_TOKEN=本机API使用的令牌
GATEWAY_REQUEST_TIMEOUT=240
```

推荐优先把 `UPSTREAM_API_BASE_URL` 指向执行节点的 Tailscale 地址；只有在 Tailscale 不可用时，才回退到反向 SSH 隧道的 `127.0.0.1:18781`。

4. 启动网关:

```bash
docker compose --env-file deploy/gateway/.env -f deploy/docker-compose.gateway.yml up -d --build
```

如果只修改了 `deploy/gateway/.env`，要强制重建容器让新环境变量生效:

```bash
docker compose --env-file deploy/gateway/.env -f deploy/docker-compose.gateway.yml up -d --force-recreate --no-build logistics-query-gateway
```

5. 健康检查:

```bash
curl http://127.0.0.1:18743/api/health
```

## 二、本机启动真实查询 API

本机 `.env` 中建议增加:

```env
API_HOST=0.0.0.0
API_PORT=18081
API_AUTH_TOKEN=本机API使用的令牌
```

启动本机 API:

```powershell
.\scripts\windows\start_api.ps1
```

Linux / WSL:

```bash
bash ./scripts/linux/start_api.sh
```

Windows 建议使用 `.env.windows.example` 作为起始模板；Linux / WSL 建议使用 `.env.linux.example`。

## 三、优先方案: Tailscale 直连上游

推荐架构:

- Windows 执行节点 Tailscale IP: `100.99.40.87`
- 服务器 Tailscale IP: `100.124.246.13`
- 服务器网关上游直接指向 `http://100.99.40.87:18081`

服务器验证执行节点 API:

```bash
curl http://100.99.40.87:18081/api/health
```

## 四、备用方案: 本机建立反向 SSH 隧道

Windows PowerShell:

```powershell
$env:SERVER_HOST="121.41.4.126"
$env:SERVER_USER="root"
$env:REMOTE_BIND_PORT="18781"
$env:LOCAL_API_PORT="18081"
.\scripts\start_reverse_tunnel.ps1
```

Linux / WSL:

```bash
SERVER_HOST=121.41.4.126 \
SERVER_USER=root \
REMOTE_BIND_PORT=18781 \
LOCAL_API_PORT=18081 \
bash scripts/start_reverse_tunnel.sh
```

这个隧道会把服务器上的 `127.0.0.1:18781` 转发到本机 `127.0.0.1:18081`。

## 五、外部调用方式

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

## 六、建议

- 云服务器安全组只放行 `18743`。
- `22` 端口限制为你自己的管理 IP。
- Windows 执行节点建议使用 `.env.windows.example`。
- Linux / WSL 执行节点建议使用 `.env.linux.example`。
- 长期优先使用 Tailscale 直连上游，反向 SSH 隧道仅作为备用链路。
