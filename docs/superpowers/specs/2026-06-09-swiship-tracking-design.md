# Swiship 跟踪号查询接入设计

## 背景

当前跟踪号查询模式已经具备前缀分流能力，`TBC`、`INTL`、`BNI` 会路由到 `swiship_ca`。

但 `swiship_ca` 仍是占位实现，尚未接入真实查询流程。

与 `amazon_uk` 类似，Swiship 页面默认已经展开摘要状态和 `TRACKING HISTORY` 表格，不需要额外交互。

## 目标

- 对 `TBC` / `INTL` / `BNI` 跟踪号执行真实页面查询。
- 直接访问带参数的详情页。
- 同时抓取摘要状态和历史轨迹表。
- 把摘要状态和历史轨迹转换成统一结果结构。

## 非目标

- 不改造单聊业务选择状态机。
- 不新增下载文件或导出逻辑。
- 不为 Swiship 单独设计新的回复格式。

## 页面访问策略

直接访问：

`https://www.swiship.com/track?loc=en-US&id=<tracking_no>`

原因：

- 已知该链接可直达详情页。
- 页面默认展开，不需要点击 `Details`。
- 历史表格结构清晰，适合直接解析。

## 查询流程

1. 规范化输入跟踪号。
2. 打开：
   - `https://www.swiship.com/track?loc=en-US&id=<tracking_no>`
3. 等待页面加载完成。
4. 读取摘要区域：
   - 标题，例如 `1 item arrives`
   - 摘要状态，例如 `In-Transit. Delivery June 11`
5. 读取 `TRACKING HISTORY` 表格。
6. 按日期分组和行项目提取轨迹。
7. 组装为统一结果结构并返回。

## 页面识别规则

### 摘要区域

当前页面摘要区至少包含：

- 标题：
  - 示例：`1 item arrives`
- 摘要状态：
  - 示例：`In-Transit. Delivery June 11`

### 历史轨迹表

`TRACKING HISTORY` 表格结构包含：

- 日期分组标题：
  - 示例：`June 9`
- 每条事件行：
  - 时间：`10:14 am CST`
  - 状态：`Package left an Amazon facility.`
  - 地点：`Hamilton, ON, CA`

有些事件地点可能为空，应允许空字符串。

## 字段映射

### 摘要信息

建议保存在结果附加字段中：

- `摘要标题`
- `摘要状态`

例如：

- `摘要标题 = 1 item arrives`
- `摘要状态 = In-Transit. Delivery June 11`

### 历史轨迹

每条历史轨迹映射为：

- `时间`
  - 组装为 `<日期> <时间>`
  - 示例：`June 9 10:14 am CST`
- `内容`
  - 直接取状态文本
  - 示例：`Package left an Amazon facility.`
- `地点`
  - 直接取地点文本
  - 若为空则保留空字符串

## 轨迹顺序

从页面结构看，历史表按最新在前排列。

因此：

- `物流轨迹` 保持页面顺序
- `最新轨迹` 取历史表第一条

如果页面没有历史表，但摘要状态存在：

- `物流轨迹 = []`
- `最新轨迹 = {}`
- 摘要字段仍应返回

## 返回结构

沿用当前统一结构：

- `平台: SWISHIP_CA`
- `查询值`
- `物流轨迹`
- `最新轨迹`

并附加：

- `摘要标题`
- `摘要状态`

示例：

```json
{
  "平台": "SWISHIP_CA",
  "查询值": "TBC906468472009",
  "摘要标题": "1 item arrives",
  "摘要状态": "In-Transit. Delivery June 11",
  "物流轨迹": [
    {
      "时间": "June 9 10:14 am CST",
      "内容": "Package left an Amazon facility.",
      "地点": "Hamilton, ON, CA"
    },
    {
      "时间": "June 9 5:31 am CST",
      "内容": "Package arrived at an Amazon facility.",
      "地点": "Hamilton, ON, CA"
    },
    {
      "时间": "June 9 2:26 am CST",
      "内容": "Carrier picked up the package.",
      "地点": ""
    }
  ],
  "最新轨迹": {
    "时间": "June 9 10:14 am CST",
    "内容": "Package left an Amazon facility.",
    "地点": "Hamilton, ON, CA"
  }
}
```

## 数据清洗

- 去首尾空白
- 去掉空 HTML 标签残留
- 若事件行完全为空则跳过
- 地点缺失时保留空字符串

## 错误处理

### 页面无历史表

若没有解析到历史表，且也没有摘要状态，返回：

- `错误: Swiship 页面未返回轨迹信息`

### 页面结构变化

若关键节点缺失或提取失败，返回结构化错误，不抛出未处理异常。

## 测试策略

### 单元测试

新增纯 HTML 解析测试，至少覆盖：

- 能读取摘要标题和摘要状态
- 能提取 3 条历史轨迹
- 第一条为最新轨迹
- 第三条地点为空时不报错

### 路由测试

保留或新增分发测试：

- `TBC...` 路由到 `query_swiship_tracking`
- `INTL...` 路由到 `query_swiship_tracking`
- `BNI...` 路由到 `query_swiship_tracking`

## 代码落点

- `logistics_query.py`
  - 实现 `extract_swiship_tracking_summary_from_html`
  - 实现 `extract_swiship_tracking_items_from_html`
  - 实现 `query_swiship_tracking`
- 新增测试文件：
  - `tests/test_swiship_query.py`
- `tests/test_tracking_mode.py`
  - 保留/补充分发测试

## 风险

- 页面 class 可能变化。
- 历史表的日期分组和事件行结构可能存在轻微变体。

## 风险应对

- 解析时同时依赖表头文本和行列结构。
- 保持摘要解析和历史解析分离，便于单独修复。
