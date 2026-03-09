---
title: "複数AIを統合管理するOSSを作った - Claw Empire"
emoji: "🦞"
type: "tech"
topics: ["ai", "cli", "typescript", "oss"]
published: false
---

## TL;DR

**Claw Empire** は、Claude Code / Codex CLI / Gemini CLI / OpenCode など複数のAIエージェントを統合的にオーケストレーションするローカルファーストのCLIツールです。

## なぜ作ったか

2025年以降、AIコーディングエージェントが爆発的に増えました。Claude Code、OpenAI Codex CLI、Gemini CLI、GitHub Copilot...どれも優秀ですが、プロジェクトごとに最適なエージェントは異なります。

「全部のAIを1つの司令塔から指揮できたら？」というアイデアから Claw Empire を作りました。

## 特徴

- **マルチAIプロバイダー対応** - Claude Code, Codex CLI, Gemini CLI, OpenCode, Copilot, Antigravity
- **ローカルファースト** - データはローカルに保持、プライバシー重視
- **タスクルーティング** - タスク内容に応じて最適なAIを自動選択
- **OAuth/API認証** - 各プロバイダーの認証を統合管理

## 技術スタック

- Node.js 22+ / TypeScript
- CLI ベースのインターフェース
- Apache 2.0 ライセンス

## 使い方

```bash
npm install -g claw-empire
claw-empire init
```

各AIプロバイダーのCLIがインストールされていれば、Claw Empire から統合的に操作できます。

## ユースケース

1. **コードレビュー** - Claude に設計レビュー、Codex にバグ検出を並行依頼
2. **リファクタリング** - Gemini に提案させ、Claude Code に実装させる
3. **ドキュメント生成** - 複数AIの出力を比較して最良のものを採用

## まとめ

AI時代の開発は「どのAIを使うか」ではなく「どうAIを組み合わせるか」が鍵。Claw Empire はその答えの一つです。

