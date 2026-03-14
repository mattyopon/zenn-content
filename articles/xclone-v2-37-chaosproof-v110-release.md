---
title: "ChaosProof v1.1.0リリース — 3層可用性モデル・ベースライン回帰検出・1070テスト"
emoji: "🚀"
type: "tech"
topics: ["python", "sre", "chaosengineering", "oss", "pypi"]
published: false
---

## はじめに

InfraSim を ChaosProof にリネームし、v1.1.0 をリリースしました。PyPI・GitHub・Fly.io・Docker 全てを更新。主要な新機能と品質改善をまとめます。

## v1.0.0 → v1.1.0 の変更点

### 新機能

| 機能 | 説明 |
|------|------|
| **3層可用性モデル** | MTBF×冗長×failover の数学的計算（旧: lookup table） |
| **JSON エクスポート** | `--json` フラグで simulate/dynamic/ops-sim の結果をJSON出力 |
| **ベースライン回帰検出** | `--baseline` / `--save-baseline` でCI/CDに組み込み可能 |
| **NetworkProfile** | パケットロス・RTT・ジッターの可用性への影響モデル |
| **RuntimeJitter** | GCパーズ・カーネルスケジューリング遅延のモデル |
| **インスタンスレベル障害** | replicas>=2 のコンポーネントは1インスタンスDOWNでもDEGRADED |
| **サービスティア可用性** | ティア内1台DOWNでもティアは可用 |
| **相関障害** | AZアウテージシミュレーション |
| **sub-second failover** | 0.1秒単位のフェイルオーバー対応 |

### 品質強制の仕組み

| 仕組み | 効果 |
|--------|------|
| **Pre-commit hook** | コミット前に全テスト実行、FAIL→commit拒否 |
| **GitHub Actions CI** | push/PRで自動テスト、FAIL→マージ拒否 |
| **テスト数** | 89件 → **1070件**（12倍） |

### バグ修正

- 動的シミュレーション表示が常に0件（float vs string比較）
- ローリングリスタートで全サーバーダウン
- YAMLローダーがNetworkProfile/RuntimeJitterを無視
- レジリエンススコアがdependency typeを無視
- 3層モデルがlookup table（嘘）→ 数学的実装に修正

## CI/CD でのベースライン回帰検出

```bash
# 初回: ベースラインを保存
chaosproof simulate --model infra.yaml --save-baseline baseline.json

# CI/CD: ベースラインと比較（回帰したらexit 1）
chaosproof simulate --model infra.yaml --baseline baseline.json || exit 1
```

## インストール

```bash
pip install chaosproof==1.1.0
```

## 公開先

| プラットフォーム | URL |
|----------------|-----|
| PyPI | `pip install chaosproof` |
| GitHub | github.com/mattyopon/chaosproof |
| Fly.io | デモダッシュボード |
| Docker | `docker compose up web` |
