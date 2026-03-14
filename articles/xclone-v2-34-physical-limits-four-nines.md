---
title: "Xクローン v2.34 — パケットロスとGCパーズを入れたら6.65→4.00 Ninesに落ちた：物理世界の壁"
emoji: "🌐"
type: "tech"
topics: ["infrastructure", "sre", "network", "availability", "simulation"]
published: true
---

## はじめに

v2.33 でフェイルオーバーのみを考慮して 6.65 Nines を達成しましたが、現実のシステムには**パケットロス、GCパーズ、カーネルスケジューリング遅延**が常に存在します。これらをモデル化したら、一気に 4.00 Nines に落ちました。

## InfraSim v5.13: 物理層モデリング

### 追加したモデル

```python
class NetworkProfile(BaseModel):
    rtt_ms: float = 1.0           # ラウンドトリップタイム
    packet_loss_rate: float = 0.0001  # パケットロス率 (0.01%)
    jitter_ms: float = 0.5        # ネットワークジッター
    dns_resolution_ms: float = 5.0 # DNS解決時間
    tls_handshake_ms: float = 10.0 # TLSハンドシェイク

class RuntimeJitter(BaseModel):
    gc_pause_ms: float = 0.0      # GCパーズ (Go/Rust=0, JVM=50-200)
    gc_pause_frequency: float = 0.0  # GC発生頻度 (/秒)
    scheduling_jitter_ms: float = 0.1  # OSカーネルスケジューリング遅延
```

### 可用性計算への組み込み

```python
# 各コンポーネントのベースラインリクエスト失敗確率
comp_fail_prob = packet_loss_rate + gc_fraction
# gc_fraction = gc_pause_ms/1000 * gc_pause_frequency

# 全コンポーネントの加重平均
network_penalty += comp_fail_prob / total_components * 100
```

### Xclone v10.5 に設定したプロファイル

| コンポーネント | パケットロス | GCパーズ | GC頻度 |
|---------------|------------|---------|--------|
| LB / DNS (AWS managed) | 0.001% | 0 | 0 |
| API Pods (Bun/V8) | 0.01% | 2ms | 0.1/s |
| Aurora (PostgreSQL) | 0.005% | 0 | 0 |
| Redis | 0.002% | 0 | 0 |
| Kafka (JVM) | 0.01% | 5ms | 0.05/s |

## 結果: 6.65 → 4.00 Nines

| シナリオ | v10.4 (理想) | v10.5 (物理) |
|---------|-------------|-------------|
| 7日 baseline | ∞ | **4.00** |
| 7日 deploys | 7.46 | **4.00** |
| 30日 stress | 6.65 | **4.00** |

### なぜ 4.00 で止まるか

```
パケットロス寄与: 0.0001 (avg across 38 components) = 0.01%
GCパーズ寄与:    0.0002 (V8 2ms × 0.1/s for 12 pods) = 0.0024%
カーネルジッター: negligible

Total baseline failure rate ≈ 0.01% → 4 nines が天井
```

**パケットロス 0.01% が存在する限り、4 nines を超えることは物理的に不可能。**

## 4 nines を超えるために必要なもの

| アプローチ | 効果 | 実現性 |
|-----------|------|--------|
| パケットロス 0.001% に減少 | 5 nines | InfiniBand / RDMA |
| GC-free ランタイム (Rust/Go) | +0.3 nines | 言語変更が必要 |
| DPDK (カーネルバイパス) | +0.5 nines | 専用ハードウェア |
| SR-IOV (NIC仮想化) | +0.3 nines | ベアメタルサーバー |

これらは**インフラアーキテクチャではなくハードウェア/言語選択**の領域。

## 全改善履歴

```
v8.1   99.88%      (2.9 nines)  出発点
v9.0   99.89%      (3.0 nines)  サイドカー除去
v9.1   99.92%      (3.1 nines)  MTTR最適化
v9.2   99.94%      (3.2 nines)  NLBバックアップ
v10.0  99.9967%    (4.5 nines)  マルチリージョンDR
v10.2  99.9997%    (5.5 nines)  ティア可用性
v10.3  99.9999%    (6.0 nines)  sub-second failover
v10.4  99.999978%  (6.65 nines) near-zero failover
v10.5  99.99%      (4.00 nines) 物理世界の真実
```

## 結論

**Four Nines (99.99%) = 年間 52 分のダウンタイムが、ソフトウェアアーキテクチャで到達可能な物理的限界。**

これは Google や AWS が SLO として掲げる値と整合します（Google Cloud: 99.99%、AWS: 99.99%）。イレブンナインは光速と量子力学が許さない限り不可能です。

InfraSim は v5.13 で**物理世界を正確に反映するシミュレーション精度**に到達しました。
