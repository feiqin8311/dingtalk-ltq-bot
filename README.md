# DingTalk AI Table Example

这个目录包含一个最小可运行的 Python 示例，用钉钉开放平台接口访问 AI 表格。

代码基于官方 Python SDK：

- `oauth2_1_0`：获取企业内部应用 `accessToken`
- `notable_2_0`：访问 AI 表格的表、记录等接口

## 1. 安装依赖

```bash
conda activate dingtalk-ltq-bot
pip install -r requirements.txt
```

## 2. 配置环境变量

先复制一份环境变量模板：

```bash
cp .env.example .env
```

然后填写这些值：

- `DINGTALK_APP_KEY`
- `DINGTALK_APP_SECRET`
- `DINGTALK_BASE_ID`
- `DINGTALK_SHEET_ID`

## 3. 常用命令

列出 AI 表格下的所有数据表：

```bash
python main.py list-sheets
```

创建数据表：

```bash
python main.py create-sheet --name "测试表"
```

查看某个表：

```bash
python main.py get-sheet --sheet-id sheet_xxx
```

列出记录：

```bash
python main.py list-records --sheet-id sheet_xxx --max-results 20
```

插入记录：

```bash
python main.py insert-records --sheet-id sheet_xxx --records-json '[{"姓名":"张三","分数":95}]'
```

更新记录：

```bash
python main.py update-records --sheet-id sheet_xxx --records-json '[{"id":"rec_xxx","fields":{"分数":100}}]'
```

删除记录：

```bash
python main.py delete-records --sheet-id sheet_xxx --record-ids-json '["rec_xxx"]'
```

## 4. 说明

- `base_id` 是 AI 表格底座 ID，不是应用的 `appKey`
- `sheet_id` 是数据表 ID，也可以按接口要求传名称，但用 ID 更稳
- 字段名必须和 AI 表格里的字段一致
- 如果接口权限不足，通常需要先确认应用是否开通了对应 AI 表格权限
