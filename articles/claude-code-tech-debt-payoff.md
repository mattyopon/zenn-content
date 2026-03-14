---
title: '個人開発の"技術的負債"をClaude Codeに一括返済させた ― テスト壊れ・README無し・dead codeを4並行エージェントで修復'
emoji: "🏗️"
type: "tech"
topics: ["claudecode", "ai", "テスト", "個人開発", "技術的負債"]
published: true
---

## はじめに

前回の記事で、Claude Codeに18プロジェクトを自律巡回させてgit管理の闇を一掃した話を書きました。

https://zenn.dev/yutaro2076145/articles/claude-code-autonomous-project-patrol

あれで「きれいになった」と思っていたのですが、git管理レベルの整理だけでは見えない問題がまだ残っていました。もう一段深く掘ると、こんなものが出てきます。

- **テストが壊れている**（設定ファイル欠落で `npm test` が即死）
- **READMEが存在しない**（何のプロジェクトか本人すら思い出せない）
- **TODOコメントが放置されている**（「あとで直す」が永遠に来ない）
- **dead project**（最終更新が2〜3週間前、非git管理のまま放置）

Round 1が「表面の清掃」だとすれば、今回のRound 2は**「構造的な負債の返済」**です。

## 発見した問題の全体像

4つのプロジェクトで、合計12件の問題を発見しました。

| プロジェクト | 停止日数 | 主な問題 | 深刻度 |
|:--|:--|:--|:--|
| kakei-coin | - | jest設定ファイル欠落、テスト0件 | 高 |
| backpack-game | 8日 | README無し、LICENSE無し、非公開 | 中 |
| 3d-project | 18日 | 非git、ハードコードパス、エラーハンドリング無し | 高 |
| infrasim | - | DRY違反、BFS O(n)→O(1)未最適化、サイレント例外 | 中 |

## 修復内容の詳細

### 1. kakei-coin: テスト基盤が存在しなかった

ブロックチェーンで家計簿を管理するプロジェクトですが、`npm test` を実行すると即座にエラー終了していました。

**原因**: `jest.config.js` が存在しなかった。`package.json` に `"test": "jest"` と書いてあるのに、Jest自体の設定ファイルがないため、テストランナーが起動できない状態。

**修復内容**:

```js
// jest.config.js（新規作成）
/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/tests'],
  testMatch: ['**/*.test.ts'],
  moduleFileExtensions: ['ts', 'js', 'json'],
};
```

さらに、テストファイルが1件も存在しなかったため、コアロジック（ブロック生成、チェーン検証、トランザクション処理など）に対する14件のユニットテストを新規作成。

**結果**: 14テスト全パス。

### 2. backpack-game: 8日間放置、READMEなし

Electron + Phaserで作っていたバックパックゲームですが、8日間コミットがなく、READMEもLICENSEもない状態でした。

**修復内容**:
- バイリンガルREADME（EN/JP）を作成
- MITライセンスを追加
- GitHubにpublicリポジトリとして公開

READMEがないプロジェクトは、1週間後の自分にとっても「他人のコード」です。

### 3. 3d-project: 18日放置の非gitプロジェクト

画像から3Dモデルを生成するパイプラインですが、18日間放置されており、gitで管理すらされていませんでした。

**発見した問題**:
- スクリプト内のパスがハードコード（`/home/user/specific-path/` のような絶対パス）
- エラーハンドリングが一切なし（外部コマンド失敗時にサイレントに続行）

**修復内容**:
- パスをポータブル化（`$HOME` や相対パスに変更）
- 外部コマンド呼び出しにエラーチェックを追加
- git初期化 + GitHubに `image-to-3d-pipeline` として公開

### 4. infrasim: コード品質問題5件

仮想インフラの障害シミュレーターですが、コード品質の問題が5件見つかりました。ここが今回最もコード例を示しやすい部分なので、詳しく紹介します。

#### 4-1. DRY違反: 90行の重複コードを共通モジュール化

CLIの `demo` コマンドとWebダッシュボードの `/demo` エンドポイントに、**ほぼ同一の約90行のデモインフラ構築コード**がコピペされていました。

```python
# Before: cli.py と api/server.py の両方に同じコードが存在（約90行 x 2）

# cli.py
def demo_command():
    graph = InfraGraph()
    graph.add_component(Component(id="nginx", name="nginx (LB)", ...))
    graph.add_component(Component(id="app-1", name="api-server-1", ...))
    graph.add_component(Component(id="postgres", name="PostgreSQL", ...))
    # ... 90行のコンポーネント定義とDependency追加 ...

# api/server.py
@app.post("/demo")
def create_demo():
    graph = InfraGraph()
    graph.add_component(Component(id="nginx", name="nginx (LB)", ...))  # 同じ
    graph.add_component(Component(id="app-1", name="api-server-1", ...))  # 同じ
    # ... ほぼ同一の90行 ...
```

```python
# After: model/demo.py に共通化

# model/demo.py（新規作成）
def create_demo_graph() -> InfraGraph:
    """Build a realistic web application stack for demonstration."""
    graph = InfraGraph()
    components = [
        Component(id="nginx", name="nginx (LB)",
                  type=ComponentType.LOAD_BALANCER, ...),
        Component(id="app-1", name="api-server-1",
                  type=ComponentType.APP_SERVER, ...),
        # ... 6コンポーネントを一箇所で定義 ...
    ]
    for comp in components:
        graph.add_component(comp)
    # ... dependency定義 ...
    return graph

# cli.py（修正後）
def demo_command():
    graph = create_demo_graph()  # 1行で済む

# api/server.py（修正後）
@app.post("/demo")
def create_demo():
    graph = create_demo_graph()  # 1行で済む
```

**効果**: 213行削除、154行追加。正味59行の削減と、デモ構成の一元管理を実現。

#### 4-2. BFS探索: list.pop(0) → deque.popleft() で O(n) → O(1)

障害の影響範囲を探索するBFS（幅優先探索）で、Pythonの `list.pop(0)` を使っていました。これはリストの先頭要素を削除するたびに全要素をシフトするため **O(n)** の操作です。

```python
# Before: list.pop(0) は O(n)
def get_all_affected(self, component_id: str) -> set[str]:
    affected = set()
    queue = [component_id]
    while queue:
        current = queue.pop(0)  # O(n) — 全要素シフト
        for dep in self.get_dependents(current):
            if dep.id not in affected:
                affected.add(dep.id)
                queue.append(dep.id)
    return affected
```

```python
# After: deque.popleft() は O(1)
from collections import deque

def get_all_affected(self, component_id: str) -> set[str]:
    affected: set[str] = set()
    bfs_queue: deque[str] = deque([component_id])
    while bfs_queue:
        current = bfs_queue.popleft()  # O(1) — 定数時間
        for dep in self.get_dependents(current):
            if dep.id not in affected:
                affected.add(dep.id)
                bfs_queue.append(dep.id)
    return affected
```

小規模なグラフでは差が出ませんが、インフラコンポーネントが数百〜数千ノードになると顕著に効いてきます。Pythonのデータ構造選択として基本ですが、AIが生成したコードではこの手の「動くけど非効率」なパターンが見落とされがちです。

#### 4-3. サイレント例外にログ追加

セキュリティフィード取得時に `except Exception: pass` でエラーを握りつぶしていた箇所に、`logger.warning()` を追加しました。

```python
# Before
try:
    feed_data = fetch_security_feed(url)
except Exception:
    pass  # サイレント — 障害時に原因が追えない

# After
try:
    feed_data = fetch_security_feed(url)
except Exception as exc:
    logger.warning("Failed to fetch security feed %s: %s", url, exc)
```

**結果**: 全27テストパス。既存テストが壊れていないことを確認した上でマージ。

## Before / After 比較

| 項目 | Before | After |
|:--|:--|:--|
| kakei-coin テスト | 0件（設定欠落で起動不可） | 14件全パス |
| backpack-game README | なし | バイリンガルREADME + LICENSE |
| backpack-game 公開状態 | ローカルのみ | GitHub public |
| 3d-project git管理 | 非git（18日放置） | GitHub public (image-to-3d-pipeline) |
| 3d-project パス | ハードコード | ポータブル化 |
| infrasim DRY違反 | 90行x2の重複 | 共通モジュール化（-59行） |
| infrasim BFS計算量 | O(n) per dequeue | O(1) per dequeue |
| infrasim 例外処理 | サイレント例外 | ログ付き例外処理 |
| infrasim テスト | 27件パス | 27件パス（回帰なし） |

## 並行エージェント構成

今回は4プロジェクトを**4つのエージェントで同時修復**しました。

```
┌──────────────────────────────────────────────────┐
│  Claude Code Agent Team — Round 2                │
│                                                  │
│  Agent 1 ──→ kakei-coin                          │
│    jest.config.js作成 → 14テスト新規作成         │
│                                                  │
│  Agent 2 ──→ backpack-game                       │
│    README/LICENSE作成 → GitHub公開                │
│                                                  │
│  Agent 3 ──→ 3d-project                          │
│    パス修正 → エラーハンドリング → GitHub公開     │
│                                                  │
│  Agent 4 ──→ infrasim                            │
│    DRY修正 → BFS最適化 → 例外処理 → テスト確認   │
│                                                  │
│  ───────── 全エージェント並行実行 ─────────       │
└──────────────────────────────────────────────────┘
```

各エージェントは独立したプロジェクトを担当するため、コンフリクトなしで並行実行できます。人間が4プロジェクトを順番に直していたら半日仕事ですが、並行実行なら数分で完了します。

## 学び: 技術的負債は「溜まる前に返す」のが最安

今回の経験から得た教訓をまとめます。

### 1. テストが壊れている状態は、放置するほど直すのが怖くなる

kakei-coinの場合、「jest.config.jsを作る」というたった1ファイルの追加で解決する問題でした。しかし、テストが0件の状態が続くと、「今さらテストを書いても既存コードが壊れるかもしれない」という心理的障壁が生まれ、どんどん手が付けられなくなります。

AIに定期巡回させれば、この「恐怖の蓄積」が起きる前に修復できます。

### 2. READMEのないプロジェクトは存在しないのと同じ

backpack-gameは機能的には動く状態でしたが、READMEがないために「何をするプロジェクトなのか」が外部から判断できませんでした。OSS的には存在しないも同然です。

### 3. 「動くけど非効率」は人間のレビューで見落とされやすい

infrasimの `list.pop(0)` は典型例です。テストは通る、機能は正しい、でもパフォーマンス特性が悪い。こういう問題はコードレビューでも見落とされがちですが、AIによる定期スキャンで検出できます。

### 4. 定期巡回の仕組みが重要

手動で「そろそろ負債を返すか」と思い立つ頃には、すでに負債が山積みです。cron + Claude Codeで定期的に巡回させることで、負債が小さいうちに返済できます。

## まとめ

| 指標 | 数値 |
|:--|:--|
| 修復プロジェクト数 | 4 |
| 並行エージェント数 | 4 |
| 新規テスト数 | 14（kakei-coin） |
| テスト回帰 | 0件（infrasim 27テスト全パス維持） |
| 削減コード行数 | 59行（infrasim DRY修正） |
| 新規GitHub公開 | 2リポジトリ（backpack-game, image-to-3d-pipeline） |

個人開発の技術的負債は、「いつか直す」と思っている限り永遠に直りません。AIに定期巡回させて、負債が溜まる前に自動返済する仕組みを作ることが、個人開発を持続可能にする鍵だと実感しました。

Round 1（git整理）→ Round 2（テスト・README・コード品質）と来たので、次はRound 3として「依存パッケージの脆弱性スキャン」「非推奨APIの検出」あたりに踏み込む予定です。
