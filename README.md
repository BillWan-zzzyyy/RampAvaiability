# RampAvaiability

自动盯 UW–Madison 校园停车位：工作日 **8am–4pm 每小时**抓取一次
[Visitor Parking Availability](https://transportation.wisc.edu/parking-lots/lot-occupancy-count/)
上 14 个车库 / ramp 的实时空位数，邮件发到你的邮箱；当天最后一次（下午 4 点）那封
额外附带一张 **Ramp 17（017 Engineering Drive Ramp）当日逐小时余位曲线图**。

全程跑在 GitHub Actions 上，不需要本地开机，public 仓库额度免费。

---

## 你需要做的两件事

### 1. 配置 3 个 Secret

仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名 | 填什么 |
|---|---|
| `GMAIL_USER` | 发件用的 Gmail 地址，例如 `yourname@gmail.com` |
| `GMAIL_APP_PASSWORD` | Google 账号 → 安全性 → 两步验证 → **应用专用密码**（16 位），**不是**登录密码 |
| `MAIL_TO` | 收件邮箱 |

> 收件地址放在 Secret 里而不是写进代码，因为**这个仓库是公开的**，邮箱写进文件等于公开挂网上被爬虫收走。

拿 App Password 的前提是 Google 账号已开启两步验证；入口在
<https://myaccount.google.com/apppasswords>。

### 2. 把功能分支合并到 `main`

GitHub 的 `schedule` 定时触发器**只读取默认分支上的 workflow 文件**。
代码停在功能分支上，定时任务永远不会触发（手动触发不受此限）。

---

## 它是怎么跑的

```
.github/workflows/scrape.yml   定时任务：cron "0 13-22 * * 1-5"（UTC）
scraper/
  config.py    所有可调项（时区、时间窗、关注的 ramp、SMTP）都读环境变量
  fetch.py     用无头 Chromium 渲染页面（原因见下）
  parse.py     解析 wpDataTable → LotRecord 列表
  storage.py   每天一个 CSV：data/YYYY-MM-DD.csv，运行完提交回仓库
  chart.py     matplotlib 画 Ramp 17 当日曲线 → PNG
  report.py    生成邮件正文（中文；车库名保留英文，跟路牌一致）
  mailer.py    Gmail SMTP 发信，图片内嵌 + 附件
  main.py      时间闸门 → 抓取 → 落盘 → (收官则画图) → 发信
tests/         对真实页面快照做的解析测试
```

### 为什么用无头浏览器而不是 requests

`transportation.wisc.edu` 整站挂在 **AWS WAF 的 challenge 模式**后面。用普通 HTTP 请求
（哪怕带全套浏览器 header）拿到的是 `HTTP 202` + 一段 JavaScript 工作量证明页面
（`x-amzn-waf-action: challenge`，页面里是 `window.gokuProps`），**永远拿不到真实内容**。
这个 challenge 是静默型的（不是需要人点的验证码），真实浏览器引擎执行完那段 JS 就会自动放行，
所以 `fetch.py` 用 Playwright 渲染页面。这也是本项目唯一的重量级依赖。

### 时区与夏令时

cron 只能用 UTC。芝加哥夏令时 UTC−5、冬令时 UTC−6，所以 cron 排在 `13-22 UTC`
（两种偏移都覆盖），再由 `main.py` 用 `America/Chicago` 判断本地小时是否落在 8–16，
不在窗口内就直接退出。**换季不需要改任何配置。**

### 数据

每次运行往 `data/YYYY-MM-DD.csv` 追加一轮读数（`timestamp_local, lot_id, name,
available, total, region, raw_status`）并提交回仓库。4pm 那次直接读当天 CSV 画图，
所以图表数据和邮件数据永远一致，历史也留得下来。

网站有时不给数字而给文字（已实测到 `006U H.C. White Garage upper` 显示 **FULL**）：

- `FULL` → 记为 **0**，状态显示"已满"。这是最该让你知道的情况，绝不能当成"未知"糊弄过去。
- `CLOSED` / 其他无法识别的文字 → 记为**未知**，邮件里原样显示网站的用词，不进曲线图，
  也绝不猜一个数字。

---

## 本地开发

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m pytest tests/ -q          # 解析/存储/画图测试，不需要联网
python -m scraper.main --dry-run --force   # 真抓一次但不发邮件（需要能访问该网站）
```

可调环境变量：`FOCUS_LOT`（默认 `17`）、`FIRST_HOUR`/`LAST_HOUR`（默认 8/16）、
`TIMEZONE`、`SOURCE_URL`、`DATA_DIR`。

手动触发：Actions → *Parking availability report* → **Run workflow**，
可勾选 `dry_run`（不发信）、`force`（无视时间窗）、`force_chart`（强制带曲线图）。

---

## 已知限制

- **定时任务可能延迟**。GitHub Actions 的 cron 在高峰期常延迟几分钟到十几分钟，偶尔跳过某次。
  这是平台行为，不是本项目的 bug；脚本记录的是**实际抓取时间**，图表按小时归档。
- **仓库连续 60 天没有人工活动**，GitHub 会自动停用定时任务，去 Actions 页面点一下恢复即可。
  （机器人自己的提交不算人工活动。）
- 网站自己声明空位数是**近似值且变化很快**，仅供参考。
- 抓取或解析失败时会照常发一封"本次抓取失败 + 错误原因"的邮件，并让这次 Actions 运行显示为红色失败，
  **绝不会编造数字**。
