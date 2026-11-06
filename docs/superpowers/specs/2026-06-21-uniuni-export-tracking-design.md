# UNIUNI Export Tracking Design

## Goal

把 `UNIUNI` 查询从“页面 HTML 时间线解析”切换为“详情页导出 Excel 后读取 `Latest Track` 列”，与人工操作路径保持一致。

## Scope

- 保留现有 `UUS -> uniuni` 的平台路由。
- 保留现有 CDP 共享浏览器接入方式。
- 修改 `query_uniuni_tracking()` 的主路径为 `More -> Download -> 解析 Excel`。
- 如果第一次点击 `More` 后没有看到 `Download`，允许再点一次 `More` 后重试一次。
- 返回结果只基于导出文件中的 `Latest Track` 列，不再以页面时间线为主数据源。
- 下载文件统一放到 `tmp/tracking-downloads/<date>/uniuni/`。

## Non-Goals

- 不改 `query_tracking_number()` 的分流逻辑。
- 不引入新的三方依赖。
- 不尝试从 UNIUNI 导出文件中重建完整历史轨迹。

## Design

### Query Flow

1. 打开 `https://www.uniuni.com//tracking#tracking-detail?no=<tracking_no>`。
2. 等待并点击包含跟踪号的结果项，进入详情区域。
3. 定位 `More` 按钮并点击。
4. 查找 `Download` 菜单项。
5. 若未找到 `Download`，再次点击 `More` 并重试一次。
6. 用 `page.expect_download()` 等待导出文件。
7. 把导出文件保存到 `tmp/tracking-downloads/<date>/uniuni/`。
8. 解析 Excel 的首行和数据行，读取 `Latest Track` 列。
9. 返回单条轨迹：
   - `时间`: `''`
   - `内容`: `Latest Track`
   - `地点`: `''`

### Error Handling

- 详情结果项不存在：返回 `未找到 UNIUNI 跟踪号结果`
- `More` 不存在：返回 `UNIUNI 页面未找到 More 导出入口`
- `Download` 仍不存在：返回 `UNIUNI 页面未找到 Download 菜单`
- 下载超时：返回 `UNIUNI 导出文件下载失败`
- Excel 缺少 `Latest Track`：返回 `UNIUNI 导出文件缺少 Latest Track 字段`
- 解析异常：返回 `UNIUNI 导出文件解析失败: ...`

失败时继续保留现有调试信息：
- `当前页面标题`
- `当前URL`
- `调试HTML`

### Testing

- helper 测试：
  - 下载目录和文件名
  - `Latest Track` 读取
  - 缺少 `Latest Track` 时抛错
- 执行测试：
  - `More` 第一次未展开 `Download`，第二次成功
  - 下载成功后返回单条 `Latest Track`
