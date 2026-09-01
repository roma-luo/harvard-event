# harvard-events

每天自动抓取 Harvard 和 MIT 多个来源的活动，分类打分，生成两个 iCalendar 订阅文件，每周日发一封邮件摘要。订阅一次日历链接之后零日常操作。

## 输出

- `docs/priority.ics` — 日历 A「Events - Priority」，最多 8 条高分活动
- `docs/all.ics` — 日历 B「Events - All」，其余全部
- 周报邮件 — 周日晚发，含必看、报名截止、在展展览、来源健康状态

在 Outlook 里用「从 Web 订阅」添加这两个 URL（GitHub Pages 地址）；不要「导入」，导入不会自动刷新。展览不进 ICS（跨月展览会毁掉周视图），只在周报里出现。

## 常用命令

```bash
uv sync                                # 安装
uv run pytest                          # 测试
uv run harvard-events run              # 完整管道：抓取→去重→打分→写 ICS（周日自动发邮件）
uv run harvard-events run --mail       # 立刻发本周邮件（调试用）
uv run harvard-events preview --source harvard_seas --days 7   # 看某来源会贡献什么，不写任何文件
uv run harvard-events discover calendar.mit.edu                # 拉下一个 Localist 实例的完整词表
uv run harvard-events probe hls.harvard.edu                    # 探测一个新域名是什么平台
uv run harvard-events busy-json        # 把 busy.yml 转成 JSON，用于 BUSY_SCHEDULE_JSON secret
```

## 配置（都在 `config/`）

- `sources.yml` — 唯一的来源清单；加一个 Localist 日历 = 复制一段配置改域名
- `subscriptions.yml` — 直接订阅的 Series / 院系名，精度最高的一层，**主要维护这个文件**
- `keywords.yml` — 关键词打分（词边界、缩写区分大小写、同义词组），只用于主题细分
- `taxonomy/<source>.yml` — 每个来源的原始分类到统一字段的映射
- `scoring.yml` / `campus.yml` — 权重、阈值、通勤扣分
- `busy.yml` — 你的固定日程。**不进仓库**（.gitignore），CI 用 `BUSY_SCHEDULE_JSON` secret 注入
- `registry.yml` — 已知来源的登记表（全部默认关闭），加来源前先翻它

## 加一个新来源

1. `uv run harvard-events probe <domain>` — 是什么平台
2. 是 Localist：`discover <domain>` 拉词表，把一段配置粘进 `sources.yml`
3. 不是：登记表里查成本，可能要在 `src/harvard_events/adapters/` 写一个适配器
4. 启用前 `preview --source <id>` 看实际内容

## 部署

GitHub Actions（`.github/workflows/build.yml`）每天 UTC 10:00 跑一次，抓取、生成 ICS 到 `docs/`、更新 `state/seen.json` 并 commit 回去；周日那次发邮件。GitHub Pages 从 main 的 `docs/` 发布，仓库必须 public。

需要的 Secrets：`SMTP_HOST`、`SMTP_USER`、`SMTP_PASS`、`MAIL_TO`、`BUSY_SCHEDULE_JSON`。

## 排查

- 某条活动不该出现 → 查 `logs/scoring.jsonl`，每项得分都有记录
- 某来源的新分类没生效 → 查 `logs/unmapped.log`，把值补进 `config/taxonomy/<source>.yml`
- 抓取连续失败 → 周报第 5 节会报，`state/health.json` 有连续失败计数
