# YunTrack 跟踪号查询接入设计

## 背景

当前跟踪号查询模式已经具备前缀分流能力，`H00RVA` 与 `GV` 会路由到 `yuntrack`。

但 `yuntrack` 仍是占位实现，尚未接入真实查询流程。

与 `gofo` 类似，YunTrack 需要通过页面导出 Excel，再读取导出表中的目标状态字段。

## 目标

- 对 `H00RVA` / `GV` 跟踪号执行真实 YunTrack 查询。
- 直接访问带跟踪号参数的详情页。
- 通过 `Copy & Export -> Export Summary` 触发 Excel 导出。
- 等待 Excel 下载完成并保存到规范目录。
- 从 Excel 中读取 `Delivery Status` 字段。
- 把 `Delivery Status` 转换成当前机器人统一的查询结果结构。

## 非目标

- 不解析整份 Excel 的所有字段作为默认回复内容。
- 不恢复完整历史轨迹时间线。
- 不改造单聊业务状态机。

## 页面访问策略

直接访问：

`https://www.yuntrack.com/parcelTracking?id=<tracking_no>`

原因：

- 已知该链接可直接打开对应查询页。
- 不需要额外搜索交互。
- 与当前自动化链路兼容。

## 查询流程

1. 规范化输入跟踪号。
2. 打开：
   - `https://www.yuntrack.com/parcelTracking?id=<tracking_no>`
3. 等待页面加载完成。
4. 点击 `Copy & Export` 按钮。
5. 点击 `Export Summary` 菜单项。
6. 等待 Excel 下载完成。
7. 将下载文件保存到规范目录并重命名。
8. 读取 Excel 首行数据。
9. 提取 `Delivery Status` 字段。
10. 组装统一查询结果并返回。

## 下载目录规范

目录：

`tmp/tracking-downloads/<YYYY-MM-DD>/yuntrack/`

文件名：

`<tracking_no>-yuntrack-summary.xlsx`

示例：

`tmp/tracking-downloads/2026-06-09/yuntrack/H00RVA0498916385-yuntrack-summary.xlsx`

## Excel 读取规则

默认只读取并展示：

- `Delivery Status`

其余字段可以保留作解析失败排查，但不作为默认回复内容。

## 返回结构

沿用当前统一结构：

- `平台: YUNTRACK`
- `查询值`
- `物流轨迹`
- `最新轨迹`

由于当前只读取 `Delivery Status`，返回 1 条标准化结果：

- `时间 = ""`
- `内容 = Delivery Status`
- `地点 = ""`

## 页面交互规则

先点击：

- 文本：`Copy & Export`

再点击：

- 文本：`Export Summary`

实现时优先依赖可见文本，不依赖随机实例 ID。

## 错误处理

- 页面未找到导出按钮：
  - `YunTrack 页面未找到导出入口`
- 页面未找到导出菜单：
  - `YunTrack 页面未找到 Export Summary 菜单`
- 下载失败：
  - `YunTrack 导出文件下载失败`
- 导出文件解析失败：
  - `YunTrack 导出文件解析失败`
- 缺少 `Delivery Status`：
  - `YunTrack 导出文件缺少 Delivery Status 字段`

## 测试策略

### 单元测试

新增纯解析函数测试，至少覆盖：

- 能读取 `Delivery Status`
- 缺少 `Delivery Status` 时返回预期错误
- 下载路径格式正确

### 路由测试

保留或新增分发测试：

- `H00RVA...` 路由到 `query_yuntrack_tracking`
- `GV...` 路由到 `query_yuntrack_tracking`

## 代码落点

- `logistics_query.py`
  - 实现 `query_yuntrack_tracking`
  - 新增下载目录辅助函数
  - 新增 Excel 解析辅助函数
- 新增测试文件：
  - `tests/test_yuntrack_query.py`
- `tests/test_tracking_mode.py`
  - 保留/补充分发测试

## 风险

- 页面菜单可能异步出现，点击时序不稳定。
- 导出文件字段名可能有大小写或空格差异。

## 风险应对

- 对导出按钮和菜单项使用明确等待。
- 解析表头时统一做 `clean_text`。
