---
title: "Bilibili配信のギフト目標バーをElectron + WebSocketで作った"
emoji: "🎯"
type: "tech"
topics: ["electron", "websocket", "streaming", "nodejs"]
published: true
---

## TL;DR

**Bilibili Goal Bar** は、Bilibili ライブ配信のギフト目標を OBS のブラウザソースとして表示するツールです。Electron + WebSocket で実装しました。

## 機能

- ギフト受信をリアルタイム検知（WebSocket）
- プログレスバーで目標達成率を表示
- OBS ブラウザソースとして組み込み可能
- 効果音演出
- Electron デスクトップアプリ

## 技術スタック

- **Electron 40.6** - デスクトップアプリ
- **WebSocket (ws 8.18)** - Bilibili との双方向通信
- **Node.js** - サーバーサイド処理
- **Playwright** - ブラウザ自動操作（認証）

## アーキテクチャ

```
Bilibili WebSocket API ──> Node.js Server ──> OBS Browser Source
         │                       │
         └── ギフトイベント       └── プログレスバー HTML
```

## まとめ

配信ツール開発は、WebSocket のリアルタイム通信を学ぶ絶好の題材です。OBS との連携もブラウザソースを使えば簡単に実現できます。
