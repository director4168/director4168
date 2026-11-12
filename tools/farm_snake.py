#!/usr/bin/env python3
"""回填提交，撑起 GitHub 贡献图（贡献蛇 / streak）。

规则要点：
  - GitHub 只统计落在默认分支（或 gh-pages 分支）上的提交，邮箱必须与账号关联
  - 贡献时间戳按 UTC 计时
  - 格子颜色取自「自己每日提交量的四分位」，所以每天补同样多会变成一整片同色，
    想有深浅渐变就得让每天的提交量有高有低

保护真实贡献：真实活跃日从账号各仓库的「作者提交记录」里取（比贡献日历准，
贡献日历有缓存，撤销回填后短时间内仍显示旧数据，会把脏数据当成真实贡献）。
这些日期一律跳过，你的真实提交一条都不动。

用法：
    python3 tools/farm_snake.py --dry-run                      # 预览
    python3 tools/farm_snake.py --per-day-range 1 25 --push     # 随机量回填
    python3 tools/farm_snake.py --reset-to <sha> --per-day-range 1 25 --push --force-push
"""

import argparse
import datetime as dt
import os
import random
import shutil
import subprocess
import sys
import tempfile

DEFAULT_REPO = "git@github.com:director4168/director4168.git"
DEFAULT_REAL_REPOS = [
    "git@github.com:director4168/MiniiChat-Next.git",
    "git@github.com:director4168/director4168.github.io.git",
    "git@github.com:director4168/CarterToolbox.git",
    "git@github.com:director4168/MT-DeepseekPlugin.git",
    "git@github.com:director4168/HEX-offset.git",
]


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
    out = run(["git", "log", "--format=%aI", branch], cwd=repo)
    return {parse_iso_date(line) for line in out.splitlines() if line.strip()}


def repo_commit_days(repo, branch, base):
    """BASE 之后新增的提交日期，也就是我们自己回填出去的那些天。"""
    spec = f"{base}..{branch}" if base else branch
    out = run(["git", "log", "--format=%aI", spec], cwd=repo, check=False)
    return {parse_iso_date(line) for line in out.splitlines() if line.strip()}


def fetch_real_days(specs, author):
    """扫描各仓库里属于该作者的提交日期，这些就是「真实贡献日」。"""
    days = set()
    for spec in specs:
        tmp = None
        repo = spec
        if not os.path.isdir(os.path.join(spec, ".git")):
            tmp = tempfile.mkdtemp(prefix="real-days-")
            repo = tmp
            try:
                run(
                    [
                        "git",
                        "clone",
                        "--quiet",
                        "--filter=blob:none",
                        "--no-checkout",
                        spec,
                        repo,
                    ]
                )
            except SystemExit:
                shutil.rmtree(tmp, ignore_errors=True)
                continue
        try:
            out = run(
                ["git", "log", "--all", "--format=%aI", f"--author={author}"],
                cwd=repo,
                check=False,
            )
            got = {parse_iso_date(line) for line in out.splitlines() if line.strip()}
            days |= got
            print(f"  {spec}: {len(got)} 天真实提交")
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
    return days


def date_range(start, end):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def counts_for(day, args, rng):
    """某一天的提交条数。

    默认对数均匀分布：低值段密、高值段稀疏，像真人「偶尔肝一天」。
    均匀分布会让 GitHub 的四分位挤在同一档，贡献图就是一整片同色。
    """
    if args.per_day_range:
        low, high = args.per_day_range
        if low >= high:
            return low
        if args.dist == "log":
            count = int(round(low * (high / low) ** rng.random()))
        else:
            # 三角分布（两个均匀数相加再折半）：中间多、两头少，
            # 这样 GitHub 的四分位会均匀散到四档，格子颜色不会全挤在一档
            count = int(round(low + (high - low) * (rng.random() + rng.random()) / 2))
        if day.weekday() >= 5:
            count = int(count * args.weekend_scale)
        return max(low, count)
    if args.per_day_max > args.per_day_min:
        return rng.randint(args.per_day_min, args.per_day_max)
    return max(args.per_day, 1)


def build_chain(repo, branch, plan, name, email, message, hour):
    """用 git commit-tree 串一条空提交链，不碰工作区。plan 是 [(日期, 条数)]。"""
    head = run(["git", "rev-parse", branch], cwd=repo)
    tree = run(["git", "rev-parse", f"{head}^{{tree}}"], cwd=repo)
    parent = head
    made = 0
    for day, count in plan:
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
        for _ in range(count):
            parent = run(
                ["git", "commit-tree", tree, "-p", parent, "-m", message],
                cwd=repo,
                env=env,
            )
            made += 1
    return head, parent, made


def main():
    parser = argparse.ArgumentParser(description="回填提交，撑起 GitHub 贡献图")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="仓库地址，默认当前仓库")
    parser.add_argument("--branch", default="main", help="目标分支，必须是默认分支或 gh-pages")
    parser.add_argument("--days", type=int, default=365, help="回填最近多少天，默认 365")
    parser.add_argument("--start", default="", help="起始日期 YYYY-MM-DD，优先于 --days")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--per-day", type=int, default=1, help="每天几条提交，默认 1")
    parser.add_argument(
        "--per-day-range",
        nargs=2,
        type=int,
        metavar=("MIN", "MAX"),
        help="每天提交量在 MIN~MAX 之间按对数均匀分布取，优先于 --per-day",
    )
    parser.add_argument("--per-day-min", type=int, default=0, help="每天提交量下限")
    parser.add_argument("--per-day-max", type=int, default=0, help="每天提交量上限")
    parser.add_argument(
        "--dist",
        choices=("tri", "log"),
        default="tri",
        help="每天提交量的分布：tri=三角（默认，四档更均匀）/ log=对数均匀（多数日子少）",
    )
    parser.add_argument("--weekend-scale", type=float, default=0.5, help="周末提交量折扣，默认 0.5")
    parser.add_argument("--skip-weekends", action="store_true", help="跳过周六周日")
    parser.add_argument("--hour", type=int, default=12, help="提交时间的小时（UTC），默认 12")
    parser.add_argument("--name", default="director_Carter", help="提交作者名")
    parser.add_argument("--email", default="director4168@163.com", help="提交作者邮箱，须与账号关联")
    parser.add_argument("--message", default="chore: keep the contribution snake alive", help="提交信息")
    parser.add_argument("--seed", type=int, default=0, help="随机种子，填 0 表示不固定")
    parser.add_argument(
        "--real-from-repo",
        action="append",
        default=None,
        metavar="REPO",
        help="统计真实贡献用的仓库（可重复，本地路径或 git 地址），默认用账号下的公开仓库",
    )
    parser.add_argument(
        "--author",
        default=r"director4168\|director_Carter",
        help="作者匹配正则，默认匹配自己的两个身份",
    )
    parser.add_argument("--no-protect-real", action="store_true", help="不去保护真实贡献日期（默认保护）")
    parser.add_argument(
        "--reset-to",
        default="",
        help="生成前把分支重置到这个提交（用来重做之前回填过的日期）",
    )
    parser.add_argument("--force-push", action="store_true", help="配合 --reset-to 用强推覆盖远端")
    parser.add_argument("--push", action="store_true", help="真正推送，否则只打印计划")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不生成提交")
    args = parser.parse_args()

    rng = random.Random(args.seed or None)
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

        farm_days = repo_commit_days(repo, args.branch, args.reset_to)
        protected = set()
        if not args.no_protect_real:
            specs = args.real_from_repo or DEFAULT_REAL_REPOS
            print("统计真实贡献日期 …")
            real_days = fetch_real_days(specs, args.author)
            protected = real_days - farm_days
            print(
                f"真实提交 {len(real_days)} 天，扣掉上次回填的 {len(farm_days)} 天，"
                f"本次保护 {len(protected)} 天不动"
            )

        if args.reset_to:
            run(["git", "reset", "--quiet", "--hard", args.reset_to], cwd=repo)
            print(f"分支已重置到 {args.reset_to[:8]}（之前的回填会被重建）")

        have = existing_dates(repo, args.branch)
        todo = []
        skipped_real = 0
        for day in date_range(start, end):
            if args.skip_weekends and day.weekday() >= 5:
                continue
            if day in protected:
                skipped_real += 1
                continue
            if day in have:
                continue
            todo.append(day)

        plan = [(day, counts_for(day, args, rng)) for day in todo]
        total = sum(c for _, c in plan)
        print(f"仓库      : {args.repo}")
        print(f"分支      : {args.branch}")
        print(f"区间      : {start} → {end}")
        print(f"待补日期  : {len(todo)} 天，合计 {total} 条提交")
        if plan:
            counts = [c for _, c in plan]
            print(
                f"每天条数  : 最小 {min(counts)}，最大 {max(counts)}，"
                f"平均 {sum(counts) / len(counts):.1f}"
            )
        print(f"已有日期  : {len(have)} 天（跳过）")
        if skipped_real:
            print(f"真实贡献  : {skipped_real} 天（保护，不动）")
        if not todo:
            print("没有需要补的日期，结束。")
            return

        if args.dry_run:
            preview = ", ".join(f"{d.isoformat()}x{c}" for d, c in plan[:10])
            print(f"预览前 10 天：{preview} …")
            print("（dry-run，未生成任何提交）")
            return

        head, tip, made = build_chain(
            repo, args.branch, plan, args.name, args.email, args.message, args.hour
        )
        run(["git", "update-ref", f"refs/heads/{args.branch}", tip], cwd=repo)
        print(f"已生成 {made} 条回填提交（{head[:8]} → {tip[:8]}）")

        if not args.push:
            print("未指定 --push，停止在这里。")
            return

        if args.force_push:
            run(
                ["git", "push", "--force-with-lease", "origin", f"{args.branch}:{args.branch}"],
                cwd=repo,
            )
        else:
            run(["git", "push", "origin", f"{args.branch}:{args.branch}"], cwd=repo)
        print(f"已推送到 origin/{args.branch}")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
