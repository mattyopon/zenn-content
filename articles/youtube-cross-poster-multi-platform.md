---
title: "YouTube動画をX/ニコニコ/Bilibiliに自動投稿するCLIツール"
emoji: "📺"
type: "tech"
topics: ["python", "youtube", "automation", "cli"]
published: true
---

## TL;DR

YouTube チャンネルの新着動画を検知し、X（Twitter）、ニコニコ動画、Bilibili に自動でクロスポストする Python CLI ツールを作りました。

## なぜ作ったか

動画クリエイターにとって、マルチプラットフォーム展開は視聴者拡大の鍵です。しかし、YouTube に動画を上げるたびに各プラットフォームに手動で投稿するのは非常に面倒。

「RSSフィードを監視して自動投稿できないか？」というシンプルなアイデアから開発しました。

## 機能

- **RSS ポーリング** - YouTube チャンネルの RSS フィードを定期監視
- **マルチプラットフォーム投稿** - X / ニコニコ動画 / Bilibili に対応
- **重複防止** - SQLite で投稿履歴を管理、同じ動画は2度投稿しない
- **テンプレート** - プラットフォームごとの投稿テンプレートをカスタマイズ可能
- **翻訳** - deep-translator による多言語対応（Bilibili向けの中国語翻訳等）

## 技術スタック

| 用途 | ライブラリ |
|------|----------|
| RSS解析 | feedparser |
| HTTP | httpx |
| 動画DL | yt-dlp |
| X投稿 | tweepy |
| 設定 | pyyaml |
| 表示 | rich |
| スケジュール | schedule |
| 翻訳 | deep-translator |
| ブラウザ操作 | Playwright (オプション) |

## 使い方

```bash
pip install -e .
youtube-cross-poster config  # 初期設定
youtube-cross-poster watch   # 監視開始
```

設定ファイル（YAML）でチャンネルURL、投稿先、テンプレートを指定するだけで動きます。

## まとめ

コンテンツクリエイターの「面倒な作業」を自動化する実用的なツールです。RSS + CLI という枯れた技術の組み合わせで、安定した自動投稿を実現しています。
