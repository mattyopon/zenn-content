---
title: "Xクローン v2.35 — InfiniBand+GC-freeランタイムで6 Nines到達：ハードウェアが可用性を決める"
emoji: "🔧"
type: "tech"
topics: ["infrastructure", "sre", "network", "infiniband", "rust"]
published: true
---

## はじめに

v2.34 でパケットロスとGCパーズが 4 nines のボトルネックだと判明。今回は InfiniBand クラスのネットワーク + GC-free ランタイム（Rust 想定）でシミュレーションし、**6 nines (99.9999%)** に到達しました。

## InfraSim バグ修正: YAML ローダーが network フィールドを無視していた

v5.13 で `NetworkProfile` と `RuntimeJitter` を追加したが、**YAML ローダー (`loader.py`) がこれらのフィールドをパースしていなかった**ため、常にデフォルト値（パケットロス 0.01%）が使われていました。

```python
# ❌ Before: network/runtime_jitter フィールドなし
component = Component(
    id=comp_id, name=comp_name, type=comp_type,
    metrics=metrics, capacity=capacity, ...
    # network と runtime_jitter が欠落
)

# ✅ After: 明示的にパース
network = NetworkProfile(**entry["network"]) if "network" in entry else NetworkProfile()
runtime_jitter = RuntimeJitter(**entry["runtime_jitter"]) if "runtime_jitter" in entry else RuntimeJitter()
component = Component(..., network=network, runtime_jitter=runtime_jitter, ...)
```

**教訓: モデル追加時はローダーの更新を忘れるな。**

## InfiniBand + GC-free の設定

| パラメータ | Ethernet (v10.5) | InfiniBand (v10.6) |
|-----------|-----------------|-------------------|
| パケットロス | 0.01% | **0.0001%** |
| RTT | 1ms | **0.05ms** (50μs) |
| ジッター | 0.5ms | **0.01ms** |
| GC パーズ | 2ms × 0.1/s | **0** (GC-free) |
| カーネルジッター | 0.1ms | **0.01ms** (RT kernel) |

## 結果

| シナリオ | Ethernet (4 nines) | InfiniBand (6 nines) |
|---------|-------------------|---------------------|
| 7日 baseline | 99.99% | **99.9999%** |
| 30日 stress | 99.99% | **99.9999%** |
| Nines | 4.00 | **5.91** |

## 6 nines を超えるには

残り 0.0001% のペナルティは `packet_loss_rate: 0.000001` (0.0001%)。これをさらに下げるには:

- **光ファイバー直結** (パケットロス 0.00001%) → 7 nines
- **FPGA ネットワークスタック** (ソフトウェアスタック除去) → 8 nines
- **量子通信** (理論上パケットロスゼロ) → ∞ nines

これは**物理学の領域**であり、InfraSim のシミュレーション精度の限界でもあります。
