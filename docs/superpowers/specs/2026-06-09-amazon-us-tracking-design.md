# Amazon US 跟踪号查询接入设计

## 背景

当前跟踪号查询模式已经具备前缀分流能力，`TBA` 会路由到 `amazon_us`。

但 `amazon_us` 仍是占位实现，尚未接入真实查询流程。

用户给出的目标很明确：优先打开

`https://track.amazon.com/tracking/<tracking_no>?trackingId=<tracking_no>`

等待页面加载完成后，抓取页面主标题 `h1.css-alxyr3` 的文本，例如：

- `Arriving tomorrow`
- `Delivered Tuesday, June 9, 5:23 AM`

## 目标

- 对 `TBA` 开头的跟踪号执行真实 Amazon US 页面查询。
- 仅提取页面大标题文本作为当前物流状态。
- 保持现有单聊持续模式和平台分流规则不变。

## 非目标

- 不解析 Amazon US 完整历史轨迹。
- 不实现额外点击展开逻辑。
- 不改动 FBA 查询逻辑。

## 查询流程

查询地址：

`https://track.amazon.com/tracking/<tracking_no>?trackingId=<tracking_no>`

流程：

1. 规范化跟踪号。
2. 打开直达查询页。
3. 由于页面加载较慢，优先等待 `domcontentloaded` 后，再等待页面主标题或错误提示出现。
4. 如果拿到 `h1.css-alxyr3`，直接返回标题文本。
5. 如果页面出现 `div.css-1jlcqid[role="alert"]`，且提示为 `We're sorry / We couldn't find the package you're looking for`，则跳转 `https://track.amazon.com/`。
6. 在首页输入框 `input.search-input` 输入跟踪号，点击 `Track` 按钮提交。
7. 等待结果页加载后再次抓取标题。
8. 若仍然出现同样错误，则重复首页查询，直到达到重试上限。
9. 达到重试上限后，返回错误。

## 返回结构

成功时：

```json
{
  "平台": "AMAZON_US",
  "查询值": "TBA331751755675",
  "物流轨迹": [
    {
      "时间": "",
      "内容": "Arriving tomorrow",
      "地点": ""
    }
  ],
  "最新轨迹": {
    "时间": "",
    "内容": "Arriving tomorrow",
    "地点": ""
  }
}
```

失败时：

```json
{
  "平台": "AMAZON_US",
  "查询值": "TBA331751755675",
  "物流轨迹": [],
  "最新轨迹": {},
  "错误": "Amazon US 页面未返回状态标题"
}
```

## 实现边界

- 在 `logistics_query.py` 中新增 HTML 解析函数，用于提取 `h1.css-alxyr3` 与错误提示块。
- 在 `query_amazon_us_tracking` 中使用本地 CDP 浏览器执行“直达页 + 首页回查 + 重试”。
- `query_tracking_number` 的 `TBA` 分流保持不变。

## 测试

- 新增解析测试，覆盖：
  - `Arriving tomorrow`
  - `Delivered Tuesday, June 9, 5:23 AM`
  - `We're sorry / We couldn't find the package you're looking for`
- 新增路由测试，确认 `TBA...` 调用 `query_amazon_us_tracking`
