# 陈半仙中间层（Chenbanxian Middleware）

这是给“陈半仙 Agent ↔ Open Notebook”做的**最小编排中间层**：
- 紫微斗数问题走知识库检索
- 非紫微问题直连你自己的大模型（不走搜索引擎）
- 触发规则可控（私聊/群聊）
- 紫微问题知识库未命中时，自动走 LLM 补答，并明确“师门未授、需查证”语义
- 支持一键安装 / 一键卸载

> 设计原则：只做编排，不重复造检索引擎。检索能力交给 Open Notebook。

---

## 你能得到什么

- 一个 FastAPI 服务：`POST /ask`、`POST /chart`、`GET /health`、`GET /preflight`
- 双路由能力：
  - 紫微斗数 → Open Notebook 检索优先；未命中则 LLM 补答（带“师门未授、需查证”语义）
  - 非紫微 → 直连 LLM（无搜索）
- 双输出模式：
  - 默认 Human Mode（自然人类口语，不暴露 AI 身份）
  - 显式触发 Report Mode（来源分级/报告格式）
- 一键安装脚本：`scripts/install.sh`
- 一键卸载脚本：`scripts/uninstall.sh`（支持 dry-run / purge）
- 批量导入脚本：`scripts/batch_import_from_dir.sh`（把本地目录文件批量导入 notebook）

---

## 目录结构

```text
.
├── app.py
├── requirements.txt
├── .env.example
├── README.md
└── scripts/
    ├── install.sh
    ├── uninstall.sh
    └── batch_import_from_dir.sh
```

---

## 快速开始

### 1) 配置环境

```bash
cp .env.example .env
# 按需修改 OPEN_NOTEBOOK_BASE_URL 等参数
```

### 2) 一键安装

```bash
bash scripts/install.sh
```

安装脚本会：
- 创建 `.venv`
- 安装依赖
- 生成 `.env`（如果你还没建）
- 若当前是 root + systemd 环境：自动注册并启动 `chenbanxian-middleware.service`

> Debian/Ubuntu 如果报 `ensurepip is not available`，先安装：
> `apt install -y python3-venv`

### 3) 健康检查

```bash
curl http://127.0.0.1:8787/health
```

---

## Docker 部署（可选）

如果你不想装本机 Python 依赖，可以直接 Docker 跑：

```bash
docker compose up -d --build
curl http://127.0.0.1:8787/health
```

停止：

```bash
docker compose down
```

---

## 一键卸载

### 先预览（推荐）

```bash
bash scripts/uninstall.sh --dry-run
```

### 执行卸载

```bash
bash scripts/uninstall.sh --yes
```

### 彻底清理（危险）

```bash
bash scripts/uninstall.sh --yes --purge
```

说明：
- 默认卸载会保留 `.env`（避免误删配置）
- `--purge` 才会连 `.env` 一起删

---

## 批量导入来源（给 Open Notebook）

> 重点：Open Notebook 不会因为你“挂载目录”就自动索引，必须创建 Source。

```bash
bash scripts/batch_import_from_dir.sh \
  --api http://127.0.0.1:5055/api \
  --dir "/vol3/1000/KaitOP/修养/斗数学习" \
  --notebook-id "notebook:xxxx"
```

如果不传 `--notebook-id`，脚本会自动取第一个 notebook。

支持文件类型：`pdf epub txt md doc docx pptx xlsx`

---

## API

### 路由规则

- `is_ziweidoushu_intent(question) == true`：走知识库（Open Notebook）优先；未命中转 LLM 补答
- 否则：走直连 LLM

### 输出模式规则

- 默认：Human Mode（自然对话，不显式展示分级与技术术语）
- 当问题文本包含以下触发词之一时切 Report Mode：
  - `来源分级` / `报告模式` / `报告格式` / `证据分层` / `分级来源`

### `POST /chart`（排盘）

> 约束：排盘引擎固定为 `iztro`，用于保证计算口径一致。

请求示例：

```json
{
  "birth_date": "1990-8-15",
  "birth_hour": 14,
  "gender": "男",
  "lang": "zh-CN",
  "fix_leap": true
}
```

返回重点：
- `engine`: 固定 `iztro`
- `chart.basic`: 基础盘面信息（命主、身主、五行局等）
- `chart.palaces`: 十二宫结构化数据（可直接用于前端可视化渲染）

### `POST /ask`

请求示例：

```json
{
  "question": "今年事业运势怎么看？",
  "chat_type": "private",
  "addressed": true,
  "teaching_preferred": false,
  "force": false
}
```

返回字段说明：
- `should_answer`: 是否应该回答
- `uncertain`: 是否低置信
- `mode`: `ziweidoushu-kb` / `direct-llm` / `reject`
- `retrieval_params`: 本次实际检索参数（仅知识库路由有）
- `answer`: 最终答复
- `citations`: 引用列表（仅知识库路由有）

---

## 关键配置（.env）

- `OPEN_NOTEBOOK_BASE_URL`：Open Notebook API 地址
- `OPEN_NOTEBOOK_SEARCH_PATH`：默认 `/api/search`
- `GROUP_REQUIRE_ADDRESSED`：群聊是否要求被@或回复
- `ENABLE_INTENT_GATE`：是否启用命理意图闸门
- `BASELINE_*`：检索基线参数（limit/min_score 等）

---

## 常见问题

### Q1: 为什么挂载了目录还是检索不到？
A: 因为“看得见文件”≠“已建立 source + embedding”。请执行批量导入脚本。

### Q2: 卸载会不会把我知识库数据删掉？
A: 默认不会。只有 `--purge` 才会清理更彻底。

### Q3: 我不用 systemd 可以吗？
A: 可以。`install.sh` 检测到无 systemd 时会给你前台启动命令。

---

## 版本与定位

当前版本：`v0.4`（MVP+）

定位：
- ✅ 做消息编排、路由、策略
- ✅ 提供安装/卸载与导入工具
- ✅ 支持紫微 KB 未命中时的 LLM 补答（含“需查证”语义）
- ❌ 不替代 Open Notebook 检索/索引内核