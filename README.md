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
.github/workflows/scrape.yml   定时任务：cron "5,25,45 11-22 * * 1-5"（UTC，冗余是故意的，见下）
scraper/
  config.py    所有可调项（时区、时间窗、关注的 ramp、SMTP）都读环境变量
  schedule.py  归属档位（slot）：这次运行算作哪个整点的报告
  precheck.py  仅标准库；判断这次触发有没有活干，没有就秒退
  fetch.py     用无头 Chromium 渲染页面（原因见下）
  parse.py     解析 wpDataTable → LotRecord 列表
  storage.py   每天一个 CSV：data/YYYY-MM-DD.csv，运行完提交回仓库
  chart.py     matplotlib 画 Ramp 17 当日曲线 → PNG
  report.py    生成邮件正文（中文；车库名保留英文，跟路牌一致）
  mailer.py    Gmail SMTP 发信，图片内嵌 + 附件
  main.py      档位闸门 → 抓取 → 落盘 → (收官则画图) → 发信
tests/         对真实页面快照做的解析测试
```

### 为什么用无头浏览器而不是 requests

`transportation.wisc.edu` 整站挂在 **AWS WAF 的 challenge 模式**后面。用普通 HTTP 请求
（哪怕带全套浏览器 header）拿到的是 `HTTP 202` + 一段 JavaScript 工作量证明页面
（`x-amzn-waf-action: challenge`，页面里是 `window.gokuProps`），**永远拿不到真实内容**。
这个 challenge 是静默型的（不是需要人点的验证码），真实浏览器引擎执行完那段 JS 就会自动放行，
所以 `fetch.py` 用 Playwright 渲染页面。这也是本项目唯一的重量级依赖。

### 时区与夏令时

cron 只能用 UTC。芝加哥夏令时 UTC−5、冬令时 UTC−6，所以 cron 排在 `11-22 UTC`
（两种偏移都覆盖），再由 `schedule.py` 用 `America/Chicago` 判断这次运行的**归属档位**
是否落在 8–16，不在窗口内就直接退出。**换季不需要改任何配置。**

### 为什么 cron 一小时排三次（冗余是故意的）

因为 **GitHub 会大面积丢弃定时任务**。本仓库实测：

| 日期 | 应触发 | 实际触发 | 延迟 |
|---|---|---|---|
| 8/18–8/25（6 个工作日） | 10 | **10** 每天 | +15 ~ +57 分钟 |
| 8/26 | 10 | 6 | 最大 **+201 分钟** |
| 8/27、8/28 | 10 | **1** | +52、+55 |
| 8/31 | 10 | 2 | +32、+99 |
| 9/1 | 10 | 3 | +12、+27、+67 |

期间没有任何运行失败或被取消，workflow 状态一直是 `active`——**是平台侧在丢**。

所以不再指望某一次 cron 准时或一定会触发，改成**一小时排三次**（`:05 :25 :45`），
谁先跑成谁算数。配合下面的幂等机制，实际干活的仍然是每天 9 次。

**如实说明**：丢弃是整天性的（8/27、8/28 全天只触发 1 次），
所以冗余能提高命中率，但救不回"GitHub 一整天几乎不触发"的日子。
真要彻底解决只能改用外部调度器调 `workflow_dispatch` API
（手动触发分配 runner 只要 2–9 秒），代价是要把一个 GitHub PAT 放到第三方服务上。

### 每档幂等：重复触发不会重复发信

`precheck.py` 在**安装依赖之前**就判断这次触发有没有活干：

1. 这次运行的归属档位在 8–16 点的工作日窗口内吗？
2. 当天的 CSV 里这个档位已经有记录了吗？

任一条不满足就写 `proceed=false` 到 `$GITHUB_OUTPUT`，workflow 跳过后面所有步骤，
整个运行约 15 秒结束。它**只用标准库**（有测试专门在干净解释器里验证这一点），
所以能跑在 `pip install` 之前。

这带来两个好处：重复触发不会给你发第二封邮件，也不会对学校网站发出多余请求——
每天对方仍然只被访问 9 次，而不是 36 次。

### 归属档位（slot）

既然执行时刻会在整点前后浮动，"这次运行属于哪个小时"就不能看时钟了。
`schedule.slot_for()` 把实际时刻**四舍五入到最近整点**作为归属档位：
7:52 和 8:17 都算 **8 点档**。时间窗判断、是否收官、CSV 归档、曲线图 x 轴、
邮件标题全部按档位走；**邮件正文里显示的仍然是真实抓取时刻**，不会让你误以为
数据比实际更新。

### 数据

每次运行往 `data/YYYY-MM-DD.csv` 追加一轮读数（`timestamp_local, slot_local, lot_id,
name, available, total, region, raw_status`）并提交回仓库。
`timestamp_local` 是真实抓取时刻，`slot_local` 是归属档位（整点），两者相差几分钟到半小时。
早于 slot 机制的旧数据没有 `slot_local` 列，读取时会自动按时刻推算，不会读崩。

4pm 那次直接读当天 CSV 画图，所以图表数据和邮件数据永远一致，历史也留得下来。

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

- **GitHub 可能一整天几乎不触发**，冗余 cron 也救不回来（实测 8/27、8/28 全天只触发 1 次）。
  这种情况下当天的收官邮件会明确写出"今日只记录到 N/9 档，缺 X、Y"，
  让你一眼看出是调度没触发，而不是车位数据有问题。
- **触发时刻仍然不准**，延迟从十几分钟到三个多小时都出现过。每条记录存的是
  **真实抓取时刻**（`timestamp_local`）和**归属档位**（`slot_local`）两个值，
  邮件正文显示真实时刻，不会让你误以为数据比实际更新。
- 2026-08-17 至 08-19 的历史数据产生于 slot 机制之前，重新读取时按时刻推算档位，
  个别档可能与当初记录的小时不一致（例如 8:35 的那次会归到 9 点档）。只影响回看旧数据。
- **仓库连续 60 天没有人工活动**，GitHub 会自动停用定时任务，去 Actions 页面点一下恢复即可。
  （机器人自己的提交不算人工活动。）
- 网站自己声明空位数是**近似值且变化很快**，仅供参考。
- 抓取或解析失败时会照常发一封"本次抓取失败 + 错误原因"的邮件，并让这次 Actions 运行显示为红色失败，
  **绝不会编造数字**。
