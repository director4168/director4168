# tools

## farm_snake.py

回填提交，撑起 GitHub 贡献图（贡献蛇 / streak）。

GitHub 只统计落在**默认分支**（或 gh-pages 分支）上的提交，提交邮箱必须与账号关联，贡献时间戳按 UTC 计时。脚本按天生成空提交并把作者时间、提交时间一起回填，推到默认分支后，贡献格子和贡献蛇就会变长。

```bash
# 预览（不生成、不推送）
python3 tools/farm_snake.py --dry-run

# 回填最近一年，每天一条，推到 main
python3 tools/farm_snake.py --push

# 只补工作日、每天四条（贡献格子满格深色）
python3 tools/farm_snake.py --days 365 --per-day 4 --skip-weekends --push
```

常用参数：

- `--repo`：仓库地址，默认 `git@github.com:director4168/director4168.git`
- `--branch`：目标分支，必须是默认分支或 gh-pages，默认 `main`
- `--days` / `--start` / `--end`：回填区间，默认最近 365 天到今天
- `--per-day`：每天几条提交，默认 1
- `--skip-weekends`：跳过周六周日
- `--hour`：提交的小时（UTC），默认 12
- `--name` / `--email`：提交身份，默认 `director_Carter <director4168@163.com>`
- `--push`：真正推送，不加就只生成不推
- `--dry-run`：只打印计划

已有提交的日期会自动跳过，脚本可以重复执行。提交全部是空提交，不会改动任何文件。

想撤销：

```bash
git reset --hard <回填前的提交> && git push --force-with-lease origin main
```
