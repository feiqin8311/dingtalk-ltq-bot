# UPS 跟踪号查询接入设计

## 背景

当前跟踪号查询模式已经具备前缀分流能力，`1Z0` 开头会路由到 `ups`。

但 `ups` 仍是占位实现，尚未接入真实页面抓取。

从当前页面结构看，UPS 详情页已经提供一组稳定的进度步骤节点，可以直接判断当前物流所处阶段，而不需要登录或导出文件。

## 目标

- 对 `1Z0` 开头的 UPS 跟踪号执行真实页面查询。
- 直接访问带跟踪号参数的详情页。
- 解析 UPS 进度条中的当前激活步骤。
- 返回当前物流阶段作为统一结果结构中的最新轨迹。

## 非目标

- 本次不恢复完整 UPS 历史轨迹时间线。
- 不扩展除当前阶段以外的更多页面字段。
- 不改造单聊业务选择状态机。

## 页面访问策略

直接访问：

`https://www.ups.com/track?tracknum=<tracking_no>`

原因：

- 已知该链接可直达详情页。
- 当前页面已经包含可直接读取的状态进度条。
- 不需要额外搜索交互。

## 查询流程

1. 规范化输入跟踪号。
2. 打开：
   - `https://www.ups.com/track?tracknum=<tracking_no>`
3. 等待页面加载完成。
4. 定位进度条中的所有 `progress-step` 节点。
5. 找到 `active` 且 `aria-current="true"` 的步骤。
6. 提取该步骤中的可见文本。
7. 组装为统一结果结构并返回。

## 页面识别规则

当前页面中的阶段节点结构大致为：

- `progress-step completed`
- `progress-step active`
- `progress-step inactive`

当前状态判断依据：

- 节点 class 中包含 `active`
- 且 `aria-current="true"`

当前节点中可见文本示例：

- `We Have Your Package`

同一页面还可见完整阶段顺序：

1. `Label Created`
2. `We Have Your Package`
3. `On the Way`
4. `Out for Delivery`
5. `Delivery`

## 字段映射

### 内容

直接取当前激活步骤文本，例如：

- `We Have Your Package`

### 时间

本次默认留空。

### 地点

本次默认留空。

## 返回结构

沿用当前统一结构：

- `平台: UPS`
- `查询值`
- `物流轨迹`
- `最新轨迹`

示例：

```json
{
  "平台": "UPS",
  "查询值": "1Z0VV9660319941066",
  "物流轨迹": [
    {
      "时间": "",
      "内容": "We Have Your Package",
      "地点": ""
    }
  ],
  "最新轨迹": {
    "时间": "",
    "内容": "We Have Your Package",
    "地点": ""
  }
}
```

## 数据清洗

- 去首尾空白
- 忽略 `completed` 和 `inactive` 节点内容
- 只保留当前 `active` 节点文本

## 错误处理

### 页面无激活步骤

返回：

- `错误: UPS 页面未返回当前物流状态`

### 页面结构变化

若关键节点缺失或提取失败，返回结构化错误，不抛出未处理异常。

## 测试策略

### 单元测试

新增一个纯 HTML 解析测试，至少覆盖：

- 能识别 `active` + `aria-current="true"` 节点
- 返回 `We Have Your Package`
- 不误取 `completed` 或 `inactive` 节点

### 路由测试

保留或新增分发测试：

- `1Z0...` 路由到 `query_ups_tracking`

## 代码落点

- `logistics_query.py`
  - 实现 `extract_ups_current_status_from_html`
  - 实现 `query_ups_tracking`
- 新增测试文件：
  - `tests/test_ups_query.py`
- `tests/test_tracking_mode.py`
  - 保留/补充分发测试

## 风险

- 页面 class 结构可能调整。
- 当前状态文本可能存在多处重复渲染。

## 风险应对

- 优先依赖 `active` + `aria-current="true"` 双重条件。
- 解析时只取当前步骤节点内部的可见标签文本。
