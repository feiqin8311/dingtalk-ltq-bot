# GOFO 跟踪号查询接入设计

## 背景

当前跟踪号查询模式已经具备前缀分流能力，`GFUS` 会路由到 `gofo`。

但 `gofo` 仍是占位实现，尚未接入真实查询流程。

与 `uniuni` 不同，`gofo` 的核心数据不是直接从页面时间线抓取，而是通过页面的导出能力下载 Excel，再读取导出表中的状态字段。

## 目标

- 对 `GFUS` 跟踪号执行真实 `gofo` 查询。
- 直接访问带跟踪号参数的详情页。
- 通过页面上的 `COPY & EXPORT -> Export Summary` 触发 Excel 导出。
- 等待 Excel 下载完成并保存到规范目录。
- 从 Excel 中读取 `Current status` 字段。
- 把 `Current status` 转换成当前机器人统一的查询结果结构。

## 非目标

- 不解析整份 Excel 的所有字段作为默认回复内容。
- 不实现完整历史轨迹时间线还原。
- 不改造单聊业务状态机。
- 不实现 `gofo` 以外平台的 Excel 下载能力。

## 页面访问策略

直接访问：

`https://www.gofo.com/us/track?searchID=<tracking_no>`

原因：

- 已知该链接可直接打开对应运单查询页。
- 不需要额外输入框或首页跳转。
- 更适合自动化。

## 查询流程

1. 规范化输入跟踪号。
2. 打开：
   - `https://www.gofo.com/us/track?searchID=<tracking_no>`
3. 等待页面加载完成。
4. 点击 `COPY & EXPORT` 按钮。
5. 点击 `Export Summary` 菜单项。
6. 等待 Excel 下载完成。
7. 将下载文件保存到规范目录并重命名。
8. 读取 Excel 首行数据。
9. 提取 `Current status` 字段。
10. 组装统一查询结果并返回。

## 下载目录规范

推荐目录：

`tmp/tracking-downloads/<YYYY-MM-DD>/gofo/`

例如：

`tmp/tracking-downloads/2026-06-09/gofo/`

理由：

- 不同日期分目录，避免长期堆在一个目录中。
- 不同平台分目录，后续如果 `ups`、`usps` 等也需要导出文件，不会混乱。
- 便于问题排查和手工核验。

### 文件命名

下载完成后，重命名为：

`<tracking_no>-gofo-summary.xlsx`

例如：

`GFUS01055496346945-gofo-summary.xlsx`

这样文件名稳定、易追溯，不依赖浏览器默认下载名。

## Excel 读取规则

当前已知表头至少包括：

- `Tracking Number`
- `Waybill No`
- `Current status`
- `Last Event`

### 默认业务字段

默认只读取并展示：

- `Current status`

### 备用调试字段

保留读取但不默认展示：

- `Last Event`
- `Tracking Number`
- `Waybill No`

这些字段仅用于：

- 下载内容核对
- 解析失败排查
- 后续如果要扩展回复内容时复用

## 返回结构

沿用当前统一结构：

- `平台: GOFO`
- `查询值: <tracking_no>`
- `物流轨迹`
- `最新轨迹`

由于当前只读取 `Current status`，建议返回 1 条标准化结果：

- `时间`
  - 默认为空
  - 若后续确认 `Last Event` 可稳定拆出时间，再扩展
- `内容`
  - 直接使用 `Current status`
- `地点`
  - 默认留空

示例：

```json
{
  "平台": "GOFO",
  "查询值": "GFUS01055496346945",
  "物流轨迹": [
    {
      "时间": "",
      "内容": "Transit",
      "地点": ""
    }
  ],
  "最新轨迹": {
    "时间": "",
    "内容": "Transit",
    "地点": ""
  }
}
```

## 页面交互规则

### 导出按钮

先点击按钮：

- 文本：`COPY & EXPORT`

再点击菜单项：

- 文本：`Export Summary`

实现时应优先依赖：

- 可见文本
- 较稳定的 role / button / menu item 结构

不要依赖随机生成的前端实例 ID。

## 文件下载策略

建议使用 Playwright 的下载事件能力：

- 监听下载事件
- 等待导出完成
- 将文件保存到目标目录

这样比依赖浏览器默认下载目录更稳定。

## Excel 解析策略

实现时建议：

- 优先尝试系统已有 Python Excel 读取库
- 如果当前仓库没有该依赖，则新增一个轻量 Excel 解析依赖
- 只读取第一张表和首行有效数据

解析要求：

- 表头必须存在 `Current status`
- 若没有该列，返回结构化错误
- 若没有数据行，返回结构化错误

## 错误处理

### 页面未找到导出按钮

返回：

- `错误: GOFO 页面未找到导出入口`

### 导出菜单未找到

返回：

- `错误: GOFO 页面未找到 Export Summary 菜单`

### 下载失败

返回：

- `错误: GOFO 导出文件下载失败`

### Excel 解析失败

返回：

- `错误: GOFO 导出文件解析失败`

### 缺少 Current status

返回：

- `错误: GOFO 导出文件缺少 Current status 字段`

## 测试策略

### 单元测试

新增一个纯解析函数测试，至少覆盖：

- 能从示例表头中读取 `Current status`
- 缺少 `Current status` 时返回预期错误
- 数据行为空时返回预期错误

### 路由测试

保留已有分发测试：

- `GFUS...` 路由到 `query_gofo_tracking`

### 下载目录测试

新增一个纯路径函数或轻量辅助函数测试：

- 目录格式为 `tmp/tracking-downloads/<YYYY-MM-DD>/gofo/`
- 文件名格式为 `<tracking_no>-gofo-summary.xlsx`

## 代码落点

- `logistics_query.py`
  - 实现 `query_gofo_tracking`
  - 新增下载目录辅助函数
  - 新增 Excel 解析辅助函数
- 新增测试文件：
  - `tests/test_gofo_query.py`
- `tests/test_tracking_mode.py`
  - 保留/补充分发测试

## 风险

- 页面菜单可能异步出现，点击时序不稳定。
- 浏览器下载事件可能受页面脚本时延影响。
- Excel 文件格式可能不是简单的 CSV，需要额外依赖读取。

## 风险应对

- 对导出按钮和菜单项使用明确等待。
- 下载采用 Playwright 原生下载等待机制。
- 把 Excel 解析提炼成独立函数，先用单测固定输入输出。
