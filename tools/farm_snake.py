#!/usr/bin/env python3
"""回填提交，撑起 GitHub 贡献图（贡献蛇 / streak）。

GitHub 只统计落在默认分支（或 gh-pages 分支）上的提交，且提交邮箱必须与账号
关联；贡献时间戳按 UTC 计时。所以这里的做法是：按天生成空提交，并把作者时间
和提交时间都回填成指定日期（UTC 正午），最后推送到默认分支。

用法：
    # 在当前仓库内预览将要生成的提交（不动任何东西）
    python3 tools/farm_snake.py --dry-run

    # 回填最近一年，每天一条，推到 main
    python3 tools/farm_snake.py --push

    # 只在工作日补，四条/天（贡献格子满格深色）
    python3 tools/farm_snake.py --days 365 --per-day 4 --skip-weekends --push

    # 指定仓库和分支
    python3 tools/farm_snake.py --repo git@github.com:director4168/director4168.git \\
        --branch main --days 365 --push

说明：
    - 已存在提交的日期会被跳过，可以重复执行，不会刷重
    - 提交是空提交（--allow-empty 效果），不会改动任何文件
    - 想撤销：git reset --hard <回填前的提交> && git push --force-with-lease origin <分支>
"""

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile

DEFAULT_REPO = "git@github.com:director4168/director4168.git"


def run(args, cwd=None, env=None, check=True):
    proc = subprocess.run(
        args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    if check and proc.returncode != 0:
        sys.exit(f"命令失败：{' '.join(args)}\n{proc.stdout}")
    return proc.stdout.strip()


def parse_iso_date(text):
    return dt.datetime.fromisoformat(text).astimezone(dt.timezone.utc).date()


def existing_dates(repo, branch):
    """分支上已有的提交日期（按 UTC 归一），用于跳过重复回填。"""
    out = run(["git", "log", "--format=%aI", branch], cwd=repo)
    return {parse_iso_date(line) for line in out.splitlines() if line.strip()}


def date_range(start, end):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def build_chain(repo, branch, days, name, email, message, hour):
    """用 git commit-tree 串一条空提交链，不碰工作区。"""
    head = run(["git", "rev-parse", branch], cwd=repo)
    tree = run(["git", "rev-parse", f"{head}^{{tree}}"], cwd=repo)
    parent = head
    for day in days:
        stamp = f"{day.isoformat()}T{hour:02d}:00:00+00:00"
        env = dict(os.environ)
        env.update(
            {
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_AUTHOR_DATE": stamp,
                "GIT_COMMITTER_NAME": name,
                "GIT_COMMITTER_EMAIL": email,
                "GIT_COMMITTER_DATE": stamp,
            }
        )
        parent = run(
            ["git", "commit-tree", tree, "-p", parent, "-m", message],
            cwd=repo,
            env=env,
        )
    return head, parent


def main():
    parser = argparse.ArgumentParser(description="回填提交，撑起 GitHub 贡献图")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="仓库地址，默认当前仓库")
    parser.add_argument("--branch", default="main", help="目标分支，必须是默认分支或 gh-pages")
    parser.add_argument("--days", type=int, default=365, help="回填最近多少天，默认 365")
    parser.add_argument("--start", default="", help="起始日期 YYYY-MM-DD，优先于 --days")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--per-day", type=int, default=1, help="每天几条提交，默认 1")
    parser.add_argument("--skip-weekends", action="store_true", help="跳过周六周日")
    parser.add_argument("--hour", type=int, default=12, help="提交时间的小时（UTC），默认 12")
    parser.add_argument("--name", default="director_Carter", help="提交作者名")
    parser.add_argument("--email", default="director4168@163.com", help="提交作者邮箱，须与账号关联")
    parser.add_argument("--message", default="chore: keep the contribution snake alive", help="提交信息")
    parser.add_argument("--push", action="store_true", help="真正推送，否则只打印计划")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不生成提交")
    args = parser.parse_args()

    today = dt.datetime.now(dt.timezone.utc).date()
    end = dt.datetime.fromisoformat(args.end).date() if args.end else today
    start = (
        dt.datetime.fromisoformat(args.start).date()
        if args.start
        else end - dt.timedelta(days=max(args.days - 1, 0))
    )

    tmp = None
    repo = os.getcwd()
    if not os.path.isdir(os.path.join(repo, ".git")):
        tmp = tempfile.mkdtemp(prefix="farm-snake-")
        repo = tmp
        print(f"克隆 {args.repo} 到临时目录 …")
        run(["git", "clone", "--quiet", args.repo, repo])
    try:
        run(["git", "fetch", "--quiet", "origin", args.branch], cwd=repo)
        if run(["git", "rev-parse", "--verify", args.branch], cwd=repo, check=False) == "":
            run(["git", "checkout", "-q", "-B", args.branch, f"origin/{args.branch}"], cwd=repo)
        else:
            run(["git", "checkout", "-q", args.branch], cwd=repo)
            run(["git", "reset", "--quiet", "--hard", f"origin/{args.branch}"], cwd=repo)

        have = existing_dates(repo, args.branch)
        todo = []
        for day in date_range(start, end):
            if args.skip_weekends and day.weekday() >= 5:
                continue
            if day in have:
                continue
            todo.append(day)

        total = len(todo) * max(args.per_day, 1)
        print(f"仓库      : {args.repo}")
        print(f"分支      : {args.branch}")
        print(f"区间      : {start} → {end}")
        print(f"待补日期  : {len(todo)} 天，每天 {args.per_day} 条，合计 {total} 条提交")
        print(f"已有日期  : {len(have)} 天（跳过）")
        if not todo:
            print("没有需要补的日期，结束。")
            return

        if args.dry_run:
            preview = ", ".join(d.isoformat() for d in todo[:10])
            print(f"预览前 10 天：{preview} …")
            print("（dry-run，未生成任何提交）")
            return

        head, tip = build_chain(
            repo, args.branch, todo, args.name, args.email, args.message, args.hour
        )
        run(["git", "update-ref", f"refs/heads/{args.branch}", tip], cwd=repo)
        count = int(run(["git", "rev-list", "--count", f"{head}..{tip}"], cwd=repo))
        print(f"已生成 {count} 条回填提交（{head[:8]} → {tip[:8]}）")

        if not args.push:
            print("未指定 --push，停止在这里。")
            return

        run(["git", "push", "origin", f"{args.branch}:{args.branch}"], cwd=repo)
        print(f"已推送到 origin/{args.branch}")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
