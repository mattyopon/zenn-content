---
title: "Electron + CSS box-shadowだけでデスクトップ常駐型放置RPGを作った"
emoji: "⚔️"
type: "tech"
topics: ["electron", "gamedev", "javascript", "css", "pixelart"]
published: true
---

## TL;DR

**卓上冒険物語：放置ほっこりタイム** は、デスクトップ上に常駐する放置型RPGです。画像ファイルゼロ、CSS `box-shadow` だけでピクセルアートを描画し、Vanilla JS + Electron でフルスクラッチ開発しました。

![GitHub](https://github.com/mattyopon/tabletop-idle-game)

## 技術スタック

| 用途 | 技術 |
|------|------|
| デスクトップ | Electron 41 |
| ゲームロジック | Vanilla JavaScript (IIFE) |
| ピクセルアート | CSS box-shadow（16x16スプライト） |
| UI | HTML + CSS (glassmorphism) |
| パッケージング | electron-builder |
| 画像ファイル | **0個**（全てCSSで描画） |

## デモ

380x580pxの小さなウィンドウがデスクトップの隅に常駐し、自動でバトルが進行します。

- フレームレス＆透過ウィンドウ
- 常に最前面表示（always-on-top）
- システムトレイ格納
- タスクバー非表示

## なぜ画像を一切使わなかったのか

デスクトップ常駐アプリにとって、**バンドルサイズ**は重要です。画像アセットを使うと、たかだか放置ゲームなのにファイルサイズが膨らみます。

CSS `box-shadow` を使えば、16x16のピクセルアートを **1つの `<div>` 要素** で表現できます。キャラクター全18種＋キャンプファイヤーで、わずか **5KB** です。

## box-shadow ピクセルアートの仕組み

### 基本原理

1ピクセル = 1つの `box-shadow` として、座標と色を指定します。

```css
/* 3x3の赤い四角 */
.pixel-art {
  width: 3px;
  height: 3px;
  box-shadow:
    0px 0px 0 #ff0000,   /* (0,0) */
    3px 0px 0 #ff0000,   /* (1,0) */
    6px 0px 0 #ff0000,   /* (2,0) */
    0px 3px 0 #ff0000,   /* (0,1) */
    3px 3px 0 #ff0000,   /* (1,1) */
    6px 3px 0 #ff0000,   /* (2,1) */
    0px 6px 0 #ff0000,   /* (0,2) */
    3px 6px 0 #ff0000,   /* (1,2) */
    6px 6px 0 #ff0000;   /* (2,2) */
}
```

### 16x16 スプライトの実装

```javascript
const PX = 3; // 1ピクセル = 3x3px → 16x16 = 48x48px表示

function createSprite(grid, palette) {
  const shadows = [];
  for (let y = 0; y < grid.length; y++) {
    for (let x = 0; x < grid[y].length; x++) {
      const colorKey = grid[y][x];
      if (colorKey === '.') continue; // 透明
      shadows.push(`${x * PX}px ${y * PX}px 0 ${palette[colorKey]}`);
    }
  }
  return shadows.join(',');
}
```

### 戦士のスプライト例

```javascript
const warrior = {
  palette: {
    'h': '#ffd700', // 金の兜
    's': '#c0c0c0', // 銀の鎧
    'b': '#8B4513', // 茶色の肌
    'w': '#ff4444', // 赤いマント
    // ...
  },
  grid: [
    '....hhhh....',
    '...hhhhhh...',
    '..hhbbbbhh..',
    // ... 16行
  ]
};
```

この方法のメリット：

- **ゼロアセット** — PNGもSVGもWebPも不要
- **CSSアニメーション対応** — `transform: translate()` でそのまま動かせる
- **スケーリング自由** — `PX` 定数を変えるだけで全スプライトがリサイズ
- **超軽量** — 全キャラクター合計 5KB

## ゲーム設計

### ジョブシステム（6職業）

前衛・後衛の配置概念があり、ジョブごとに異なるステータスとスキルを持ちます。

| ジョブ | 配置 | HP | ATK | DEF | スキル |
|--------|------|-----|-----|-----|--------|
| 戦士 | 前衛 | 100 | 12 | 10 | シールドバッシュ（スタン付与） |
| 騎士 | 前衛 | 120 | 10 | 15 | パリィ（DEFアップ） |
| 魔法使い | 後衛 | 55 | 25 | 5 | AOE魔法（全体攻撃） |
| 僧侶 | 後衛 | 80 | 8 | 8 | ヒール（味方回復） |
| 暗殺者 | 前衛 | 65 | 22 | 6 | マルチストライク（複数回攻撃） |
| 召喚師 | 後衛 | 70 | 18 | 7 | 精霊召喚（追加ダメージ） |

### エリア＆ステージ進行

5エリア × 5ステージ ＋ ボス戦の全25ステージ構成です。

```
草原 → 洞窟 → 森 → 火山 → 魔王城
 │       │      │      │       │
 ↓       ↓      ↓      ↓       ↓
ゴブリン  骸骨   妖精   炎竜    魔王
 キング   ゴーレム  エルフ王 ヘルハウンド リッチ
(HP150) (HP250) (HP350) (HP500) (HP800)
```

### 装備システム（5段階レアリティ）

ドロップ時にレアリティとランダムアフィックスが付与されます。

| レアリティ | ドロップ率 | アフィックス数 | 色 |
|-----------|----------|-------------|-----|
| Common | 50% | 0 | 白 |
| Uncommon | 30% | 1 | 緑 |
| Rare | 14% | 1-2 | 青 |
| Epic | 5% | 2 | 紫 |
| Legendary | 1% | 2-3 | 金（虹エフェクト付き） |

アフィックスの例：
- ATK+5%, DEF+3, HP+50
- クリティカル率+3%, 経験値+10%, ゴールド+15%

Legendaryドロップ時は**画面全体が虹色に光る**演出が入ります。

## Electron のデスクトップ常駐設計

### フレームレス透過ウィンドウ

```javascript
new BrowserWindow({
  width: 380, height: 580,
  transparent: true,
  frame: false,
  alwaysOnTop: true,
  resizable: false,
  skipTaskbar: true,
  hasShadow: false,
  webPreferences: {
    contextIsolation: true,
    nodeIntegration: false,
    preload: path.join(__dirname, 'preload.js')
  }
});
```

OS標準のウィンドウ枠を消し、背景を透過させることで、キャラクターがデスクトップに直接居る感覚を実現しています。

### プログラマティックなシステムトレイアイコン

アイコンも画像ファイル不要。`nativeImage` でピクセル単位に描画しています。

```javascript
const icon = nativeImage.createFromBuffer(
  createSwordIcon(), // 16x16 金の剣アイコン
  { width: 16, height: 16 }
);
tray = new Tray(icon);
```

### オフライン進行

アプリを閉じている間もゴールドが蓄積される仕組みです。

```javascript
// 復帰時にオフライン報酬を計算
const offlineMs = Date.now() - state.lastSaveTime;
const offlineHours = Math.min(offlineMs / 3600000, 24); // 最大24時間
const offlineGold = Math.floor(offlineHours * goldPerHour);
```

## ビジュアルデザイン

### グラスモーフィズムUI

```css
.container {
  background: rgba(20, 10, 30, 0.85);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 215, 0, 0.3);
  border-radius: 12px;
}
```

### エリア別背景演出

各エリアでCSS背景が変化します。

- **草原**: 空色→草色のグラデーション
- **洞窟**: ダークグレー＋松明のフリッカーアニメーション
- **森**: 複数レイヤーのグリーングラデーション
- **火山**: 赤茶色＋溶岩グローアニメーション
- **魔王城**: ダークパープル＋魔法オーラエフェクト

### HPバーの段階的カラー変化

```css
/* 66%以上: 緑 */
.hp-fill { background: linear-gradient(90deg, #27ae60, #2ecc71); }

/* 33-66%: オレンジ */
.hp-fill.caution { background: linear-gradient(90deg, #f39c12, #e67e22); }

/* 33%以下: 赤 + パルスアニメーション */
.hp-fill.critical {
  background: linear-gradient(90deg, #e74c3c, #c0392b);
  animation: hpPulse 0.5s ease-in-out infinite;
}
```

## アニメーション一覧

放置ゲームは「見ているだけで楽しい」ことが重要なので、14種類のCSSアニメーションを実装しています。

| アニメーション | 用途 | 時間 |
|-------------|------|------|
| charFloat | 味方の浮遊アイドル | 2.5s |
| attackRush | 攻撃時の突進 | 0.4s |
| monsterBounce | 敵の跳ね | 1.2s |
| monsterAppear | 敵出現（回転＋スケール） | 0.5s |
| monsterDefeat | 敵撃破（膨張→消滅） | 0.5s |
| damageFloat | ダメージ数値の浮遊 | 1.2s |
| levelUpAnim | レベルアップ演出 | 2.0s |
| skillFlash | スキル発動エフェクト | 0.6s |
| critFlash | クリティカルヒット画面フラッシュ | 0.15s |
| rainbowShift | Legendaryドロップ演出 | 1.5s |
| fireFlicker | キャンプファイヤー揺らぎ | 0.5s |
| torchFlicker | 洞窟の松明明滅 | 3.0s |
| hpPulse | 瀕死時HPバー点滅 | 0.5s |
| lavaGlow | 火山の溶岩発光 | 2.0s |

## 状態管理

ゲーム全体の状態を1つのオブジェクトで管理し、`localStorage` に30秒ごとに自動保存します。

```javascript
const state = {
  gold: 0,
  party: [
    { job: 'warrior', level: 1, exp: 0, hp: 100, maxHp: 100,
      equipment: { weapon: null, armor: null, accessory: null } }
  ],
  inventory: [],
  currentArea: 0,
  currentStage: 0,
  totalKills: 0,
  lastSaveTime: Date.now()
};

// 保存キー（バージョン管理）
localStorage.setItem('tabletop_idle_save_v2', JSON.stringify(state));
```

## まとめ

| こだわり | 実現方法 |
|---------|---------|
| 画像ファイルゼロ | CSS box-shadow ピクセルアート |
| デスクトップ常駐 | Electron frameless + alwaysOnTop |
| 見てるだけで楽しい | 14種のCSSアニメーション |
| 放置で進む | オフライン進行 + 自動バトル |
| 戦略性 | 6職業 × 前衛後衛 × 装備アフィックス |

Web技術だけでここまでのゲーム体験が作れるのは、Electron + CSS の表現力のおかげです。

ゲームエンジン不要、画像ファイル不要、ライブラリ不要。**Vanilla JS + CSS + Electron** だけで、デスクトップに住む小さなRPGが完成しました。

## リポジトリ

https://github.com/mattyopon/tabletop-idle-game
