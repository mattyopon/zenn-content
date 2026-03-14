---
title: "InfraSim v5.4: Pydanticバリデーターで入力境界を防御する"
emoji: "🔒"
type: "tech"
topics: ["python", "pydantic", "validation", "infrastructure", "chaosengineering"]
published: false
---

## はじめに

InfraSim v5.4 では、モデル層とシナリオ層に **Pydantic `field_validator`** を追加し、不正な入力値による予期しない動作を防止しました。

## 追加したバリデーション

### 1. Component.replicas >= 1

```python
class Component(BaseModel):
    replicas: int = 1

    @field_validator('replicas')
    @classmethod
    def validate_replicas(cls, v):
        if v < 1:
            raise ValueError(f"replicas must be >= 1, got {v}")
        return v
```

レプリカ数が 0 以下のコンポーネントは物理的に意味がないため、モデル構築時に拒否します。loader.py での手動チェックに加え、**Pydantic レベルでも二重防御**します。

### 2. Scenario.traffic_multiplier >= 0

```python
class Scenario(BaseModel):
    traffic_multiplier: float = 1.0

    @field_validator('traffic_multiplier')
    @classmethod
    def validate_multiplier(cls, v):
        if v < 0:
            raise ValueError(f"traffic_multiplier must be >= 0, got {v}")
        return v
```

負のトラフィック倍率は数学的に無意味です。

### 3. DynamicScenario.duration_seconds / time_step_seconds > 0

```python
@field_validator('duration_seconds', 'time_step_seconds')
@classmethod
def validate_positive(cls, v):
    if v <= 0:
        raise ValueError(f"Duration/step must be > 0, got {v}")
    return v
```

`duration=0` はシミュレーションが即座に終了し、`step=0` は無限ループを引き起こします。

## なぜメトリクスをクランプしないのか

`cpu_percent` や `memory_percent` を 0-100% にクランプすることも検討しましたが、**意図的に見送りました**。ops_engine は利用率が 95% を超えると OVERLOADED、110% を超えると DOWN に遷移する設計で、100% 超の値はシミュレーション上有効なシグナルです。

## テスト結果

```
71 passed in 0.86s
```

既存テストに影響なし。バリデーターは正常値を通し、不正値のみ拒否します。

## v4.9-v5.4 シリーズ総括

| バージョン | 修正数 | 主な成果 |
|-----------|--------|---------|
| v4.9 | 15 | バリデーション・パフォーマンス・テスト基盤構築 |
| v5.0 | 7 | README全面改訂・グラフアルゴリズム修正 |
| v5.1 | 5 | エンジン間一貫性・What-If正確性 |
| v5.2 | 3 | SVG XSS修正・シナリオ上限・フィード堅牢化 |
| v5.3 | 1 | dynamic CLIランタイムクラッシュ修正 |
| v5.4 | 3 | Pydanticバリデーター追加 |
| **合計** | **34** | **71テスト、6記事** |

全監査項目が対処済みまたは安全確認済みとなりました。
