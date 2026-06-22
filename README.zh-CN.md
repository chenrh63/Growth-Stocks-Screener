# A 股成长股筛选与季报验证系统

本仓库包含一个面向 A 股研究的成长股筛选系统，同时提供两种使用形态：

- `python-program/`：可直接运行的 Python 程序。
- `a-share-growth-screener/`：可安装或调用的 Codex skill，内置同一套程序模板和使用说明。

项目目标是把“低位、低估、财务仍有成长性、并且定期报告文本能验证成长延续”的公司筛出来，形成可继续跟踪的研究候选池。它不是自动交易系统，不输出买卖点、仓位建议或投资建议。

## 这个项目解决什么问题

很多 A 股公司会因为市场风格、行业 beta、短期情绪或非核心题材被一起下杀。这个系统尝试从中筛出一类研究对象：

- 所属行业不是 AI/TMT 等高拥挤热门方向。
- 当前价格位置相对较低，有低位错杀特征。
- 估值处在相对可接受区域。
- 财务数据仍体现收入、扣非利润、ROE、现金流等成长或质量信号。
- 季报、半年报、三季报或年报文本中能进一步验证成长是否延续、预期是否更清晰、风险是否恶化。

系统输出的是研究候选池，用于辅助后续人工研究，而不是直接给投资结论。

## 仓库结构

```text
.
├─ README.md                         英文简要说明
├─ README.zh-CN.md                   中文详细说明
├─ python-program/                   可直接运行的 Python 程序
│  ├─ app.py                         Streamlit Dashboard
│  ├─ requirements.txt               Python 依赖
│  ├─ .env.example                   环境变量模板，不含真实密钥
│  ├─ config/
│  │  └─ rules.yaml                  筛选、评分、文本验证规则
│  ├─ stock_screener/                核心程序包
│  ├─ tests/                         单元测试
│  ├─ data/
│  │  └─ outputs/.gitkeep            输出目录占位文件
│  ├─ screen_candidates.ps1          初筛候选池脚本
│  ├─ refresh_reports.ps1            下载和解析报告脚本
│  ├─ analyze_reports.ps1            文本分析脚本
│  └─ run_dashboard.ps1              Dashboard 启动脚本
└─ a-share-growth-screener/          Codex skill
   ├─ SKILL.md                       skill 主说明
   ├─ agents/openai.yaml             skill UI 元数据
   ├─ scripts/materialize_project.py 复制内置项目模板
   ├─ references/program-usage.md    命令和配置参考
   └─ assets/a-share-growth-screener-project/
                                      skill 内置的 Python 项目模板
```

## 两种使用方式

### 方式一：直接运行 Python 程序

进入程序目录：

```powershell
cd python-program
```

创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

复制配置模板：

```powershell
copy .env.example .env
```

然后在本地 `.env` 或 `.env.txt` 中填写：

```env
TUSHARE_TOKEN=你的_tushare_token
LLM_API_KEY=可选_OpenAI_兼容接口_key
LLM_BASE_URL=可选_OpenAI_兼容接口地址
LLM_MODEL=可选_模型名称
```

`TUSHARE_TOKEN` 是量化初筛和行情/财务数据获取的核心配置。`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 是可选配置，如果不填写，系统仍可完成候选池筛选、公告抓取、PDF 解析和章节截取，但文本验证会标记为待处理或跳过 LLM 分析。

### 方式二：作为 Codex skill 使用

skill 入口文件：

```text
a-share-growth-screener/SKILL.md
```

如果你在 Codex 环境中使用这个 skill，可以让它把内置项目模板复制到当前工作区：

```powershell
python a-share-growth-screener\scripts\materialize_project.py .\a-share-growth-screener-project
```

复制完成后，进入生成的项目目录，按上面的 Python 程序方式配置和运行。

## 主流程

### 1. 量化初筛

运行：

```powershell
.\.venv\Scripts\python.exe -m stock_screener.screen_market --period 20260331 --target-count 30
```

常用参数：

- `--period YYYYMMDD`：目标报告期，例如 `20260331`、`20260630`、`20260930`、`20261231`。
- `--target-count N`：输出候选股数量。
- `--financial-period YYYYMMDD`：用于初筛的财报期。
- `--trade-date YYYYMMDD`：指定 Tushare 交易日。
- `--refresh-stock-list`：刷新股票基础列表。
- `--no-price-history`：跳过日线历史价格调用。
- `--flat-output`：直接写入 `data/outputs/`，不创建单独 run 目录。
- `--all-boards`：关闭默认的沪深主板过滤。

初筛会综合使用股票基础信息、估值、行情、财务指标和规则配置，生成候选池。

### 2. 下载和解析定期报告

运行：

```powershell
.\.venv\Scripts\python.exe -m stock_screener.refresh_reports --period 20260331
```

这一步会尝试：

- 根据候选池查找对应报告公告。
- 下载正式报告 PDF。
- 解析 PDF 文本。
- 截取经营、展望、风险等相关章节。
- 生成报告处理状态清单。

Tushare 公告接口权限会影响公告抓取效果。如果没有相关权限，程序会尝试使用备用公告来源，但备用来源可能受网页结构变化影响。

### 3. 文本验证分析

运行：

```powershell
.\.venv\Scripts\python.exe -m stock_screener.analyze_reports --period 20260331
```

如果配置了 LLM，系统会把截取出的报告文本片段送入 OpenAI 兼容接口，判断：

- 成长是否延续。
- 预期是否更明朗。
- 成长质量是否健康。
- 风险是否恶化。
- 是否继续跟踪、观察或剔除。

如果没有配置 LLM，程序不会强制失败，会保留财务和报告处理结果，并把文本分析状态标记为待处理。

### 4. 启动 Dashboard

运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

或使用 PowerShell 包装脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard.ps1
```

Dashboard 用于查看候选池、报告状态、文本分析结果和重点跟踪名单。

## PowerShell 快捷脚本

Windows 下可以直接使用这些脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\screen_candidates.ps1 -Period 20260331 -TargetCount 30
powershell -NoProfile -ExecutionPolicy Bypass -File .\refresh_reports.ps1 -Period 20260331
powershell -NoProfile -ExecutionPolicy Bypass -File .\analyze_reports.ps1 -Period 20260331
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard.ps1
```

如果 PowerShell 执行策略限制脚本运行，使用上面的 `-ExecutionPolicy Bypass` 即可临时绕过本次命令限制。

## 主要输出

输出默认位于：

```text
python-program/data/outputs/
```

主要文件：

```text
candidates_<period>.xlsx
candidates_<period>.csv
```

第一阶段量化初筛候选池。

```text
report_manifest_<period>.xlsx
report_manifest_<period>.csv
```

报告公告、PDF 下载、文本解析、章节截取的状态清单。

```text
report_analysis_<period>.xlsx
report_analysis_<period>.csv
```

最终验证结果，包含财务分、文本分、LLM 结论、证据摘录、错误信息和候选状态。

当不使用 `--flat-output` 时，部分运行结果会写入：

```text
data/outputs/runs/
```

## 结果字段说明

常见字段包括：

| 字段 | 含义 |
|---|---|
| `ts_code` | Tushare 股票代码 |
| `name` | 股票名称 |
| `industry` | 行业 |
| `total_score` | 第一阶段综合分 |
| `growth_score` | 财务成长分 |
| `valuation_score` | 估值分 |
| `mispricing_score` | 低位错杀分 |
| `quality_score` | 质量与风险分 |
| `financial_continuation_score` | 财务延续性分 |
| `text_confirmation_score` | 文本确认分 |
| `verification_total_score` | 财务和文本综合验证分 |
| `candidate_status` | 最终候选状态 |
| `text_verdict` | LLM 文本结论 |
| `reasoning` | 简短分析逻辑 |
| `evidence_quotes` | 报告原文证据摘录 |
| `llm_error` | LLM 调用错误信息 |
| `section_path` | 被送入分析的文本片段路径 |

候选状态含义：

| 状态 | 含义 |
|---|---|
| `A_confirmed` | 财务和文本证据都较强，优先继续跟踪 |
| `B_watch` | 有成长证据，但仍有质量、现金流、订单、费用或风险问题，需要观察 |
| `C_reject` | 成长证据不足、文本不支持或风险恶化，暂时剔除 |
| `D_pending` | 报告未披露、PDF 解析失败、章节缺失或 LLM 未配置 |

## 规则配置

核心规则文件：

```text
python-program/config/rules.yaml
```

可以在这里调整：

- 目标候选数量。
- 排除行业和主题关键词。
- ST、退市、北交所、上市年限等过滤规则。
- 成长、估值、低位错杀、质量风险评分权重。
- 文本验证评分权重。
- `A_confirmed`、`B_watch`、`C_reject` 的状态阈值。

修改规则后重新运行初筛和分析流程即可。

## 测试

在 `python-program/` 下运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

测试覆盖内容包括：

- 筛选逻辑。
- 评分逻辑。
- 报告期识别。
- 报告来源处理。
- 文本章节截取。
- LLM 响应解析。
- 回测辅助逻辑。

## 隐私与安全

本仓库刻意不上传以下内容：

- `.env`
- `.env.txt`
- 真实 Tushare token
- 真实 LLM API key
- 下载的公告 PDF
- 解析后的报告全文
- 截取后的报告片段
- Tushare 或行情缓存
- 生成的 Excel/CSV 输出
- Python `__pycache__` 和 `.pyc`

仓库中保留的 `.env.example` 只包含占位值，方便本地配置。

如果你 fork 或二次发布本项目，请确认 `.gitignore` 仍然生效，并在提交前检查：

```powershell
git status --ignored --short
```

也建议搜索敏感字段：

```powershell
rg -n "TUSHARE_TOKEN|LLM_API_KEY|OPENAI_API_KEY|sk-" .
```

## 适合的使用场景

适合：

- 用作个人 A 股研究辅助工具。
- 定期生成成长股候选池。
- 跟踪季报、半年报、三季报、年报披露后的验证结果。
- 把财务数据和报告文本结合起来做二阶段筛选。
- 在 Codex 中作为 skill 复用或改造。

不适合：

- 自动交易。
- 短线择时。
- 直接生成买卖建议。
- 替代人工阅读公告、财报和行业资料。

## 免责声明

本项目仅用于研究流程、数据整理和候选池构建，不构成任何投资建议。股票市场存在风险，任何投资判断都需要结合最新公告、财报、行业数据、估值水平、流动性和个人风险承受能力独立完成。
