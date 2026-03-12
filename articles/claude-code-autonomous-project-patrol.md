---
title: "Claude Codeに18プロジェクトを自律巡回させたら、放置されたgitの闇が全部片付いた"
emoji: "🔄"
type: "tech"
topics: ["claudecode", "ai", "git", "automation", "devops"]
published: true
---

## はじめに

個人開発をしていると、プロジェクトが増えるにつれてgit管理がどんどん雑になっていきます。

- 「あとでコミットしよう」と思ったまま放置された変更
- `.gitignore`が整備されていないプロジェクト
- ローカルにしか存在しない非git化プロジェクト
- `git push`を忘れて、ローカルだけにコミットが残っている状態

心当たりがある人は多いのではないでしょうか。

今回、**Claude Code**のAgent Team機能を使って、ホームディレクトリ配下の全18プロジェクトを自律的に巡回させ、これらの問題を一気に片付けました。

## やったこと

### 1. 全プロジェクトのgit整理

まず既存の5プロジェクトについて、未コミットファイルの整理と`.gitignore`の追加・修正を実行しました。

- `node_modules/`や`__pycache__/`、`.env`などが追跡対象になっていたプロジェクトの`.gitignore`を修正
- 未コミットの変更を意味のある単位でコミット
- ローカルにしかないコミットをリモートにpush

### 2. 7プロジェクトの新規リポジトリ化+GitHub公開

gitで管理されていなかった7つのプロジェクトを、一括でGitHubリポジトリ化しました。

```
新規リポジトリ化されたプロジェクト:
- openclaw-auto-projects  （プロジェクト自動巡回ツール）
- claude-glass            （Claude搭載スマートグラス実験）
- line-claude-bot         （LINE × Claude Bot）
- task-bridge             （統合タスク管理CLI）
- bilibili-goal-bar       （Bilibili配信ギフト目標バー）
- youtube-cross-poster    （YouTube動画クロスポスター）
- stock-analyzer          （株式分析ダッシュボード）
```

それぞれに`README.md`（バイリンガル EN/JP）、`LICENSE`（MIT）、`.gitignore`を整備した上でpublicリポジトリとして公開しました。

### 3. Zenn下書き記事5本の公開

`published: false`のまま溜まっていた下書き記事5本を確認し、内容に問題がないことを検証した上で`published: true`に変更してpushしました。

### 4. cron未実行問題の発見とanacron互換スクリプトの導入

巡回中に、WSL2環境で`cron`ジョブが実行されていない問題を発見しました。原因はWSL2ではホストPCがスリープ・シャットダウンしている間にcronのスケジュール時刻を通過してしまい、ジョブがスキップされることでした。

これを解決するため、**anacron互換のユーザーランドスクリプト**を導入しました。

```bash
#!/usr/bin/env bash
# user-anacron.sh - anacron-compatible job scheduler for unprivileged users
#
# Emulates anacron behavior:
#   - Reads jobs from ~/.anacrontab
#   - Tracks last-run date per job in ~/.anacron/<job-id>
#   - Runs overdue jobs with specified delay (minutes)
#
# Usage:
#   user-anacron.sh            # Normal mode: run overdue jobs
#   user-anacron.sh -f         # Force mode: run all jobs
#   user-anacron.sh -t         # Test mode: show what would run

set -euo pipefail

ANACRONTAB="${HOME}/.anacrontab"
SPOOLDIR="${HOME}/.anacron"
today=$(date '+%Y%m%d')
today_epoch=$(date -d "$today" '+%s')

while IFS=$'\t' read -r period delay jobid command; do
    [[ -z "$period" || "$period" =~ ^# ]] && continue
    timestamp_file="${SPOOLDIR}/${jobid}"

    if [[ ! -f "$timestamp_file" ]]; then
        should_run=true
    else
        last_run=$(cat "$timestamp_file" | head -1)
        last_epoch=$(date -d "$last_run" '+%s' 2>/dev/null || echo 0)
        days_elapsed=$(( (today_epoch - last_epoch) / 86400 ))
        [[ "$days_elapsed" -ge "$period" ]] && should_run=true
    fi

    if [[ "$should_run" == "true" ]]; then
        sleep "$((delay * 60))" && eval "$command" && echo "$today" > "$timestamp_file"
    fi
done < "$ANACRONTAB"
```

`~/.anacrontab`にジョブを登録するだけで、PCが起動した時に未実行ジョブを検出して自動実行してくれます。

```bash
# ~/.anacrontab
# period(days)  delay(minutes)  job-identifier       command
1               0               bookmark-organizer   /home/user/scripts/run_bookmark_organizer.sh
1               5               agent-team-research  /home/user/scripts/agent-team-daily-research.sh
1               10              daily-summary        /home/user/scripts/daily-summary.sh
```

### 5. Slack Webhook URLの不整合修正

CLAUDE.mdの各所に記載されていたSlack Webhook URLに不整合があることを検出し、正しいURLに統一しました。通知先が分散していると、通知が一部しか届かないという地味だけど厄介な問題でした。

## Agent Teamの構成

今回使ったのは、Claude CodeのAgent Team機能で構築した**PM + 5並行エージェント**構成です。

```
╔══════════════════════════════════════════════════════════╗
║  AGENT TEAM: Project Patrol                              ║
║  Scale: M  |  Members: 6名  |  Mode: ops                ║
╠══════════════════════════════════════════════════════════╣
║  TEAM ROSTER                                             ║
║  ┌──────────────────┬───────────────────────────────┐   ║
║  │ Role             │ Mission                       │   ║
║  ├──────────────────┼───────────────────────────────┤   ║
║  │ project-manager  │ 全体統括・進捗管理            │   ║
║  │ tech-lead        │ 技術判断・git操作方針決定     │   ║
║  │ ops-engineer     │ git整理・リポジトリ化実行     │   ║
║  │ sre-engineer     │ cron/anacron問題の調査・修正  │   ║
║  │ qa-engineer      │ 各プロジェクトの動作検証      │   ║
║  │ docs-engineer    │ README・.gitignore整備        │   ║
║  └──────────────────┴───────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════╝
```

PMがタスクを分解し、各エージェントが`SendMessage`で直接やり取りしながら自律的に作業を進めます。人間（私）は最初に「全プロジェクトを巡回して整理して」と指示を出しただけです。

### 自律的に動いたポイント

1. **PMが自動でプロジェクト一覧をスキャン**し、gitの状態を分類（未コミットあり / 非git / クリーン）
2. **ops-engineerがgit操作を実行**し、完了したらqa-engineerに検証依頼を`SendMessage`で送信
3. **sre-engineerがcronの実行ログを調査**し、未実行問題を自主的に発見・修正
4. **docs-engineerがREADMEのバイリンガル化**を並行で進行
5. 全作業完了後、**PMが最終レポートをSlackに通知**

## 結果

| 指標 | Before | After |
|------|--------|-------|
| GitHubリポジトリ数 | 11 | **18** |
| 未コミットファイルがあるプロジェクト | 5 | **0** |
| `.gitignore`未整備のプロジェクト | 7 | **0** |
| Zenn下書き記事 | 5 | **0**（全て公開済み） |
| cronジョブの実行状態 | 未実行 | **anacron互換で確実に実行** |

全18リポジトリがGitHub上でクリーンな状態になりました。

## 学び

### AIエージェントによる「プロジェクト巡回パトロール」は個人開発の運用負担を劇的に減らす

個人開発では、プロジェクトが増えるほど「管理のための管理」にかかる時間が増えていきます。git statusを確認する、.gitignoreを書く、READMEを整備する、リモートにpushする——どれも1つ1つは小さな作業ですが、18プロジェクト分となるとまとまった時間が必要です。

Claude CodeのAgent Teamにこれを任せることで、以下のメリットがありました。

- **網羅性**: 人間だと「あとでやろう」で抜け漏れるが、エージェントは全プロジェクトを機械的にチェックする
- **一貫性**: `.gitignore`のルールやREADMEのフォーマットが全プロジェクトで統一される
- **発見力**: cron未実行やSlack Webhook URLの不整合など、人間が気づきにくい問題を検出してくれた
- **並行処理**: 5エージェントが同時に作業するので、直列作業より大幅に高速

### 定期巡回のすすめ

今回のanacron互換スクリプトと日次リサーチの仕組みを組み合わせれば、**毎日自動でプロジェクトの健全性をチェック**することも可能です。「放置されたgitの闇」が溜まる前に、定期的にエージェントに巡回させることで、常にクリーンな状態を維持できます。

## GitHubリポジトリ一覧

今回整理した全18リポジトリは以下から確認できます。

https://github.com/mattyopon?tab=repositories

主なリポジトリ:

| リポジトリ | 概要 |
|-----------|------|
| [claude-crew](https://github.com/mattyopon/claude-crew) | Claude Codeを24ロールAI開発チームに変える |
| [ai-game-translator](https://github.com/mattyopon/ai-game-translator) | AI日英ゲーム翻訳ツール |
| [task-bridge](https://github.com/mattyopon/task-bridge) | 統合タスク管理CLI |
| [infrasim](https://github.com/mattyopon/infrasim) | 仮想カオスエンジニアリング |
| [line-claude-bot](https://github.com/mattyopon/line-claude-bot) | LINE × Claude Bot |
| [stock-analyzer](https://github.com/mattyopon/stock-analyzer) | 株式分析ダッシュボード |
| [bilibili-goal-bar](https://github.com/mattyopon/bilibili-goal-bar) | Bilibili配信ギフト目標バー |

## おわりに

「プロジェクトの管理がめんどくさい」は、個人開発者の永遠の悩みです。でもAIエージェントに巡回させれば、その面倒な部分を丸ごと委任できます。

Claude CodeのAgent Teamは「コードを書く」だけでなく、こういった**運用・メンテナンス系のタスク**にも威力を発揮します。プロジェクトが増えてきたら、ぜひ一度エージェントに巡回パトロールを任せてみてください。
