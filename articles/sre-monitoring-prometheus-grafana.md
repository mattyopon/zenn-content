---
title: "Prometheus + Grafana + Flask でSRE監視基盤デモを構築した"
emoji: "📊"
type: "tech"
topics: ["sre", "prometheus", "grafana", "docker"]
published: true
---

## TL;DR

SRE の監視基盤を学習するために、Prometheus + Grafana + Node Exporter + Flask のフルスタック監視デモ環境を Docker Compose で構築しました。

## 構成

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ Flask App   │────>│ Prometheus   │────>│   Grafana    │
│ (カスタム    │     │ (メトリクス   │     │ (ダッシュ     │
│  メトリクス) │     │  収集)        │     │  ボード)      │
└─────────────┘     └──────────────┘     └──────────────┘
                           │
                    ┌──────────────┐
                    │Node Exporter │
                    │ (ホストメトリ │
                    │  クス)        │
                    └──────────────┘
```

## 技術要素

### Flask カスタムメトリクス
- リクエスト数、レスポンスタイム、エラー率
- Prometheus クライアントライブラリでメトリクス公開

### Prometheus
- スクレイプ設定
- アラートルール定義
- PromQL によるクエリ

### Grafana ダッシュボード
- プリセットダッシュボード
- アラート設定

### Docker Compose
- `docker compose up` 一発で全環境起動
- 開発者が手軽にSRE体験可能

## まとめ

SRE の監視基盤は複雑に見えますが、Docker Compose でローカルに構築すれば手軽に学べます。Prometheus + Grafana は事実上の業界標準であり、この知識は実務で直接活かせます。
