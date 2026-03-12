---
title: "JavaScriptゼロ行。1,778行のCSSだけで「プログラマーの夜明け」を描いた"
emoji: "🌅"
type: "tech"
topics: ["css", "animation", "フロントエンド", "デザイン", "webデザイン"]
published: true
---

## はじめに

[yui540](https://twitter.com/yui540)さんの純CSSアニメーション作品群をご存知でしょうか。JavaScriptを一切使わず、CSSだけで映像的な表現を実現するアプローチに衝撃を受けました。

「CSSだけでどこまで映像を作れるのか」を自分でも試してみたくなり、**1,778行のHTML + CSS**で6シーン構成のアニメーション作品を制作しました。JavaScriptは**文字通りゼロ行**です。

作品名は**「夜明けのコード — Dawn Code」**。深夜にコードを書くプログラマーの窓辺から、やがて朝が訪れるまでを18秒で描きます。

**デモ**: https://mattyopon.github.io/dawn-code/
**ソースコード**: https://github.com/mattyopon/dawn-code

## 作品の概要

ページを開くとアニメーションが自動再生されます。6つのシーンが`animation-delay`で順次切り替わる構成です。

| 時間 | シーン | 内容 |
|------|--------|------|
| 0-3秒 | 星空 | 45個の星がbox-shadowで瞬き、流れ星が横切る |
| 3-6秒 | 都市 | 13棟のビルシルエットが下からせり上がる |
| 6-10秒 | コーディング | プログラマーの窓が光り、コード粒子が浮遊する |
| 10-14秒 | 夜明け | 空のグラデーションが変化し、太陽が昇る |
| 14-18秒 | 桜 | 25枚の花びらが舞い降り、タイトルが1文字ずつ表示 |
| 18秒〜 | 静止 | 最終フレームを保持 |

すべてのアニメーションは`animation`プロパティと`@keyframes`だけで実現しています。タイマーもイベントリスナーもありません。

## 技術解説

ここからが本題です。純CSSでアニメーション作品を作る上で使った主要なテクニックを解説します。

### 1. box-shadowで星空を描く

最初のシーンでは、45個以上の星が瞬く夜空を表現しています。星1つずつに`<div>`を用意するのは非効率なので、**1つの要素のbox-shadowに複数の値を列挙する**手法を使いました。

```css
.stars__layer--1 {
  position: absolute;
  width: 1px;
  height: 1px;
  box-shadow:
    10vw 5vh 0 1px #fff,
    25vw 12vh 0 0.5px #fff,
    40vw 8vh 0 1.5px #fff,
    55vw 15vh 0 0.5px #fff,
    70vw 3vh 0 1px #fff,
    85vw 18vh 0 0.8px #fff,
    15vw 25vh 0 1.2px #fff,
    35vw 22vh 0 0.6px #fff,
    60vw 28vh 0 1px #fff,
    80vw 20vh 0 1.5px #fff,
    5vw 35vh 0 0.5px #fff,
    92vw 10vh 0 1px #fff,
    48vw 32vh 0 0.8px #fff,
    73vw 38vh 0 0.5px #fff,
    20vw 40vh 0 1px #fff;
  animation: twinkle1 3s ease-in-out infinite,
             starsAppear 2s ease-out forwards;
  opacity: 0;
}
```

`box-shadow`の構文は `offsetX offsetY blurRadius spreadRadius color` です。`blur`を0にして`spread`を0.5px〜1.5pxに設定すると、小さな光点になります。位置は`vw`/`vh`単位で指定しているので、どの画面サイズでもバランスが崩れません。

このレイヤーを3枚重ね、それぞれ異なるタイミングの`twinkle`アニメーションを適用することで、自然な瞬きを実現しています。

```css
@keyframes twinkle1 {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.3; }
}

@keyframes twinkle2 {
  0%, 100% { opacity: 0.8; }
  30%      { opacity: 0.2; }
  70%      { opacity: 1; }
}

@keyframes twinkle3 {
  0%, 100% { opacity: 0.6; }
  40%      { opacity: 1; }
  80%      { opacity: 0.3; }
}
```

3層のbox-shadowレイヤー × 15個ずつ = **45個の星**を3つの`<div>`だけで描画しています。さらに8個の`star-bright`要素を加え、`::before`/`::after`で`filter: blur()`をかけたグロー効果も付与しました。

### 2. animation-delayでシーンを制御する

JavaScriptのタイマーが使えないので、**すべてのシーン切り替えは`animation-delay`の値をずらすことで実現**しています。これが純CSSアニメーション制作の最も重要な技術です。

```css
/* シーン1: 星が出現（0秒〜） */
.stars__layer--1 { animation: starsAppear 2s ease-out forwards; }
.stars__layer--2 { animation: starsAppear 2.5s ease-out 0.3s forwards; }
.stars__layer--3 { animation: starsAppear 3s ease-out 0.6s forwards; }

/* シーン2: 都市がせり上がる（3秒〜） */
.city { animation: cityRise 3s cubic-bezier(0.25, 0.46, 0.45, 0.94) 3s forwards; }

/* シーン3: プログラマーの窓が光る（4秒〜）→ コード粒子（6秒〜） */
.programmer-window { animation: windowLightOn 1s ease-out 4s forwards; }
.code-particles { animation: particlesAppear 1s ease-out 6s forwards; }

/* シーン4: 地平線の光（9秒〜）→ 太陽（10.5秒〜） */
.horizon-glow { animation: horizonGlow 6s ease-in 9s forwards; }
.sun { animation: sunRise 6s cubic-bezier(...) 10.5s forwards; }

/* シーン5: 桜（14秒〜）→ タイトル（15秒〜） */
.sakura-container { animation: sakuraContainerAppear 2s ease-out 14s forwards; }
.title-char--1 { animation: charAppear 0.6s ease-out 15s forwards; }
.title-char--2 { animation: charAppear 0.6s ease-out 15.1s forwards; }
/* ... 0.1秒ずつずらして1文字ずつ表示 ... */
```

ポイントは`animation-fill-mode: forwards`の活用です。これにより、アニメーション終了後も最終フレームの状態を維持できます。`opacity: 0`で初期化しておき、`animation-delay`で指定した時刻に`opacity: 1`へ遷移させることで、「ある時刻になったら要素が出現する」という制御を実現しています。

空の色変化は18秒間かけた1つのkeyframesで5段階のグラデーション遷移を行います。

```css
@keyframes skyTransition {
  0%   { background: linear-gradient(180deg, #050516 0%, #0a0a2e 40%, #0f0f3d 100%); }
  30%  { background: linear-gradient(180deg, #050516 0%, #0a0a2e 40%, #0f0f3d 100%); }
  55%  { background: linear-gradient(180deg, #0a0a2e 0%, #1a1a4e 20%, #2d1b69 50%, #4a1942 80%, #6b2040 100%); }
  70%  { background: linear-gradient(180deg, #1a1a4e 0%, #4a2060 15%, ... #ffcc88 100%); }
  85%  { background: linear-gradient(180deg, #3a5f8a 0%, ... #ffe8d6 100%); }
  100% { background: linear-gradient(180deg, #5b9bd5 0%, #87ceeb 20%, ... #fff5ee 100%); }
}
```

0%〜30%は夜の色を維持（都市シーンまで空は暗いまま）、55%以降で紫→橙→青へと遷移します。

### 3. CSS変数で色管理する

作品全体で使う色は`:root`にCSS変数として定義しました。夜・夜明け・朝の3パレットに分類することで、一貫したカラースキームを維持しています。

```css
:root {
  /* Night colors */
  --night-deep: #050516;
  --night-mid: #0a0a2e;
  --night-light: #1a1a4e;
  --night-purple: #2d1b69;
  /* Dawn colors */
  --dawn-red: #ff6b6b;
  --dawn-orange: #ffa07a;
  --dawn-pink: #ff8fa3;
  --dawn-peach: #ffcdb2;
  /* Morning colors */
  --morning-blue: #87ceeb;
  --morning-light: #e0f0ff;
  --morning-warm: #fff0f0;
  /* Code syntax colors */
  --code-green: #66ffaa;
  --code-blue: #66ccff;
  --code-purple: #cc99ff;
  --code-orange: #ffaa66;
  --code-pink: #ff99cc;
  /* Sakura */
  --sakura-1: #ffb7c5;
  --sakura-2: #ffc1cc;
  --sakura-3: #ffd1dc;
  --sakura-4: #ffe0e6;
  --sakura-5: #ff9eb5;
}
```

コード粒子の色は`--code-green`〜`--code-pink`の5色をローテーションで割り当てています。桜の花びらも5段階のピンクを使い分けることで、単調さを避けています。

### 4. コード粒子の浮遊表現

プログラマーの窓から浮かび上がるコード粒子は、`content`属性ではなく**HTMLの`<span>`にテキストを直接記述**し、CSSで浮遊アニメーションを付けています。

```html
<div class="code-particles">
  <span class="code-particle code-particle--1">{</span>
  <span class="code-particle code-particle--2">}</span>
  <span class="code-particle code-particle--3">&lt;/&gt;</span>
  <span class="code-particle code-particle--4">;</span>
  <span class="code-particle code-particle--5">const</span>
  <span class="code-particle code-particle--6">=&gt;</span>
  <!-- ... 18個の粒子 ... -->
</div>
```

```css
.code-particle {
  position: absolute;
  font-family: var(--font-code);
  font-size: clamp(6px, 1.2vmin, 12px);
  font-weight: 700;
  white-space: nowrap;
  opacity: 0;
  will-change: transform, opacity;
}

.code-particle--1 {
  color: var(--code-green);
  animation: floatParticle1 4s ease-out 6.5s infinite;
}
```

各粒子ごとに異なる`@keyframes`を用意し、移動方向・回転角度・到達距離を変えています。

```css
@keyframes floatParticle1 {
  0%   { opacity: 0; transform: translate(0, 0) scale(0.5); }
  10%  { opacity: 0.9; }
  100% { opacity: 0; transform: translate(-3vw, -30vh) scale(0.3) rotate(45deg); }
}

@keyframes floatParticle2 {
  0%   { opacity: 0; transform: translate(0, 0) scale(0.5); }
  10%  { opacity: 0.8; }
  100% { opacity: 0; transform: translate(4vw, -35vh) scale(0.2) rotate(-30deg); }
}
```

7パターンのkeyframesを18個の粒子に割り当て、さらに`animation-duration`と`animation-delay`をそれぞれ微妙にずらすことで、ランダムに浮遊しているような印象を作り出しています。`{ } </> ; const => fn () [] :: let # @ async if <> import` といったプログラミングのシンボルが夜空に舞い上がる様子は、深夜のコーディングセッションを象徴しています。

### 5. パフォーマンス：GPUレンダリングに限定する

CSSアニメーションでは、**何をアニメーションさせるか**がパフォーマンスに直結します。本作品では以下のルールを徹底しました。

**使うプロパティ:**
- `transform`（translate, scale, rotate）
- `opacity`
- `filter`（一部のblur効果のみ）

**使わないプロパティ:**
- `width`, `height`（レイアウト再計算が発生）
- `top`, `left`（レイアウトトリガー）
- `margin`, `padding`

`transform`と`opacity`はブラウザがGPUで処理できる（=コンポジターレイヤーで完結する）ため、メインスレッドをブロックしません。都市がせり上がるシーンも、`top`を変えるのではなく`translateY`で制御しています。

```css
.city {
  transform: translateY(100%);
  animation: cityRise 3s cubic-bezier(0.25, 0.46, 0.45, 0.94) 3s forwards;
  will-change: transform;
}

@keyframes cityRise {
  0%   { transform: translateY(100%); }
  100% { transform: translateY(0); }
}
```

`will-change`プロパティも要所に付けて、ブラウザにレイヤー昇格のヒントを与えています。ただし乱用するとVRAMを圧迫するので、アニメーションする要素にだけ限定的に適用しました。

### 6. prefers-reduced-motion対応

アニメーション作品でもアクセシビリティは重要です。OSの「視差効果を減らす」設定をオンにしているユーザーには、すべてのアニメーションを事実上無効化しています。

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01s !important;
    animation-delay: 0.01s !important;
    transition-duration: 0.01s !important;
  }
}
```

`0s`ではなく`0.01s`にしているのは、`animation-fill-mode: forwards`を正しく動作させるためです。0秒にするとアニメーション自体がスキップされて最終フレームが適用されないブラウザがあるため、ほぼ瞬時に完了する微小な値を設定しています。

## 苦労した点

### animation-delayの精密な調整

最も時間を費やしたのは、シーン間の接続です。たとえば「都市が完全にせり上がる前にプログラマーの窓が光り始める」「太陽が昇り始める前に地平線のグローが先に見える」といった、**前のシーンの末尾と次のシーンの冒頭がオーバーラップする**タイミングの調整は、0.1秒単位で何度も繰り返しました。

特に難しかったのがタイトルの1文字ずつの表示です。「夜明けのコード — Dawn Code」の16文字に対して、0.1秒間隔で`animation-delay`を設定しつつ、ダッシュ（—）の前後は少し間を空けるといった**テンポ**の調整が必要でした。

```css
.title-char--5  { animation: charAppear 0.6s ease-out 15.4s forwards; }
/* ↑「コ」と「ー」の間は0.15秒空ける */
.title-char--6  { animation: charAppear 0.6s ease-out 15.55s forwards; }
```

### 背景グラデーションのアニメーション

CSSの`background`プロパティ（`linear-gradient`）はアニメーション補間されません。keyframesの各ステップ間はステップ的に切り替わるだけです。そのため`skyTransition`のkeyframesでは、中間ステップを多く設定してなめらかに見えるように工夫しました。5段階の色設定（0%, 30%, 55%, 70%, 85%, 100%）は、最適な見た目になるまで調整を繰り返した結果です。

### 桜の花びらの自然な動き

25枚の花びらそれぞれに異なるアニメーション設定（6パターンのkeyframes、7〜10.5秒のduration、14〜16秒のdelay）を割り当てています。同じ動きをする花びらが2枚並ぶと不自然さが目立つため、duration・delay・keyframesの組み合わせが隣接要素で重複しないよう手作業で配置しました。

## まとめ

**CSSは描画ツールとして想像以上に使えます。**

box-shadowで星空を描き、animation-delayでシーンを制御し、transformでGPUレンダリングを活用する。これらの基本的なプロパティの組み合わせだけで、6シーン18秒の映像作品が成立します。

1,778行のCSSを書き上げて気づいたのは、CSSアニメーション制作は「コーディング」と「映像演出」の中間にある独特の創作体験だということです。keyframesの%を調整する作業は、動画編集ソフトのタイムラインを操作する感覚に近い。けれど、すべてがテキストで完結するからこそ、バージョン管理もできるし、他のツールへの依存もない。

興味を持った方は、ぜひデモを見てからソースコードを読んでみてください。1ファイル完結なので、全体構造を追いやすいはずです。

**デモ**: https://mattyopon.github.io/dawn-code/
**GitHub**: https://github.com/mattyopon/dawn-code

yui540さんをはじめとするCSS作家の方々の作品にも、ぜひ触れてみてください。CSSの表現力に対する認識が変わると思います。
