---
title: "コピペで使える「心地よい動き」のCSS 15選 ― JSなし・純CSSマイクロインタラクション集"
emoji: "✨"
type: "tech"
topics: ["css", "animation", "フロントエンド", "ui", "webデザイン"]
published: true
---

## はじめに

UIの「なんか心地いいな」という感覚、その正体は**マイクロインタラクション**です。ボタンを押したときの弾力、トグルが切り替わるときの滑らかさ、ローディングの有機的な動き。こうした細部の積み重ねがプロダクトの質感を決めます。

この記事では、**JavaScript不使用・純CSSだけ**で実現できるマイクロインタラクションを15個紹介します。すべてコピペで使えます。

**デモページ**: https://mattyopon.github.io/dawn-code/micro-interactions.html

![デモページのスクリーンショット](/images/css-micro-interactions/demo-preview.png)
*15個すべてのインタラクションをブラウザで体験できます*

---

## 詳細解説 ― 7選

特に使いどころの多い7つのパーツを、コード付きで詳しく解説します。

### 1. Jelly Button（ゼリーバウンス）

**どんな動き？** ホバーでふわっと膨らみ、クリックするとゼリーのように縦横に潰れて弾む。

```css
.jelly-btn {
  display: inline-block;
  padding: 0.9rem 2.4rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #ff6584, #ff8a5c);
  border: none;
  border-radius: 50px;
  cursor: pointer;
  transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1),
              box-shadow 0.4s ease;
  box-shadow: 0 4px 15px rgba(255, 101, 132, 0.3);
}

.jelly-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 6px 25px rgba(255, 101, 132, 0.45);
}

.jelly-btn:active {
  animation: jelly-squish 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes jelly-squish {
  0%   { transform: scale(1.05); }
  20%  { transform: scale(0.88, 1.12); }
  40%  { transform: scale(1.08, 0.92); }
  60%  { transform: scale(0.97, 1.03); }
  80%  { transform: scale(1.02, 0.98); }
  100% { transform: scale(1); }
}
```

**心地よさのポイント**: `cubic-bezier(0.34, 1.56, 0.64, 1)` は制御点が1.0を超えているため、目標値を一旦オーバーシュートしてから戻る「バウンス」が生まれます。20%刻みで縦横比を交互に変えることで、実際のゼリーのような物理的な振動を再現しています。

---

### 2. Toggle Switch（iOS風トグル）

**どんな動き？** チェックボックスを隠してカスタムトラック＋ノブを表示。ONで緑に変わり、ノブが右にスライド。

```css
.toggle-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-track {
  position: relative;
  width: 56px;
  height: 30px;
  background: #2a2a45;
  border-radius: 15px;
  cursor: pointer;
  transition: background 0.4s ease;
}

.toggle-track::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 24px;
  height: 24px;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
  transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.toggle-input:checked + .toggle-track {
  background: #43e97b;
}

.toggle-input:checked + .toggle-track::after {
  transform: translateX(26px);
}

.toggle-input:focus-visible + .toggle-track {
  outline: 2px solid #6c63ff;
  outline-offset: 2px;
}
```

**心地よさのポイント**: ノブの移動にバウンスイージングを使うことで、「パチン」と止まるのではなく「トン」と着地する感覚に。`focus-visible` でキーボードアクセシビリティも確保しています。

---

### 3. Draw Checkbox（チェック描画）

**どんな動き？** チェックを入れると、ボックス内にチェックマークが「描かれる」ように現れる。

```css
.draw-checkbox-input {
  position: absolute;
  opacity: 0;
}

.draw-checkbox-box {
  position: relative;
  width: 28px;
  height: 28px;
  border: 2px solid #6a6a80;
  border-radius: 8px;
  transition: border-color 0.3s ease, background 0.3s ease;
}

.draw-checkbox-box::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 8px;
  width: 8px;
  height: 14px;
  border: solid transparent;
  border-width: 0 2.5px 2.5px 0;
  transform: rotate(45deg) scale(0);
  transform-origin: bottom right;
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1),
              border-color 0.3s ease;
}

.draw-checkbox-input:checked + .draw-checkbox-box {
  border-color: #43e97b;
  background: rgba(67, 233, 123, 0.1);
}

.draw-checkbox-input:checked + .draw-checkbox-box::after {
  border-color: #43e97b;
  transform: rotate(45deg) scale(1);
}
```

**心地よさのポイント**: `scale(0)` → `scale(1)` と `rotate(45deg)` を組み合わせることで、チェックマークが「描画される」錯覚を生み出します。`transform-origin: bottom right` がペン先の位置をシミュレートしています。

---

### 4. Gradient Shimmer（テキスト光沢）

**どんな動き？** テキストの上を光の帯がゆっくり横切る、高級感のあるシマー効果。

```css
.shimmer-text {
  font-size: 2.4rem;
  font-weight: 700;
  background: linear-gradient(
    90deg,
    #6a6a80 0%,
    #6a6a80 35%,
    #fff 50%,
    #6a6a80 65%,
    #6a6a80 100%
  );
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer-slide 2.5s ease-in-out infinite;
}

@keyframes shimmer-slide {
  0%   { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}
```

**心地よさのポイント**: `background-size: 300%` にすることで、光の帯（白い部分）がテキスト幅よりも広い範囲を移動します。2.5秒の `ease-in-out` で「ゆったりと光が通り過ぎる」自然な動きになります。ロゴやタイトルに最適です。

---

### 5. Hamburger → X（モーフ）

**どんな動き？** 三本線のハンバーガーメニューがクリックで X（閉じる）に滑らかに変形。

```css
.hamburger-input {
  position: absolute;
  opacity: 0;
}

.hamburger {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 52px;
  height: 52px;
  background: #1e1e38;
  border: 1px solid rgba(108, 99, 255, 0.15);
  border-radius: 14px;
  cursor: pointer;
  gap: 6px;
}

.hamburger-line {
  display: block;
  width: 24px;
  height: 2px;
  background: #e0e0e0;
  border-radius: 2px;
  transition:
    transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1),
    opacity 0.3s ease,
    width 0.3s ease;
  transform-origin: center center;
}

/* チェック時: 1本目 → 右下45度回転 */
.hamburger-input:checked + .hamburger .hamburger-line:nth-child(1) {
  transform: translateY(8px) rotate(45deg);
}

/* チェック時: 2本目 → フェードアウト */
.hamburger-input:checked + .hamburger .hamburger-line:nth-child(2) {
  opacity: 0;
  width: 0;
}

/* チェック時: 3本目 → 右上-45度回転 */
.hamburger-input:checked + .hamburger .hamburger-line:nth-child(3) {
  transform: translateY(-8px) rotate(-45deg);
}
```

**心地よさのポイント**: 中央の線は `opacity` と `width` の両方をアニメーションさせることで「溶けるように消える」印象に。上下の線は `translateY` で中央に集まってから `rotate` で交差するため、連続的なモーフ感が得られます。

---

### 6. Input Label Float（ラベル浮上）

**どんな動き？** 入力欄にフォーカスすると、プレースホルダーのように見えたラベルが上にふわっと浮き上がり、小さくなる。

```css
.float-input-group {
  position: relative;
  width: 220px;
}

.float-input {
  width: 100%;
  padding: 1rem 0 0.5rem;
  font-size: 0.95rem;
  color: #e0e0e0;
  background: transparent;
  border: none;
  border-bottom: 2px solid #6a6a80;
  outline: none;
  transition: border-color 0.3s ease;
}

.float-label {
  position: absolute;
  left: 0;
  top: 0.9rem;
  font-size: 0.95rem;
  color: #6a6a80;
  pointer-events: none;
  transition:
    top 0.35s cubic-bezier(0.18, 0.89, 0.32, 1.28),
    font-size 0.35s cubic-bezier(0.18, 0.89, 0.32, 1.28),
    color 0.35s ease;
}

.float-input:focus + .float-label,
.float-input:not(:placeholder-shown) + .float-label {
  top: -0.6rem;
  font-size: 0.72rem;
  color: #38f9d7;
  font-weight: 500;
}

.float-input-underline {
  position: absolute;
  bottom: 0;
  left: 50%;
  width: 0;
  height: 2px;
  background: #38f9d7;
  transition: width 0.4s cubic-bezier(0.18, 0.89, 0.32, 1.28),
              left 0.4s cubic-bezier(0.18, 0.89, 0.32, 1.28);
}

.float-input:focus ~ .float-input-underline {
  width: 100%;
  left: 0;
}
```

**心地よさのポイント**: `cubic-bezier(0.18, 0.89, 0.32, 1.28)` は末尾が1.0を超える「out-back」イージングで、ラベルが浮き上がるときにわずかに行き過ぎてから定位置に戻ります。下線は中央から両端へ広がり、フォーカス位置を直感的に伝えます。

---

### 7. Breathing Glow Ring（呼吸リング）

**どんな動き？** リングが呼吸するようにゆっくり明滅し、グローが拡大・収縮する。ステータス表示やローディングに。

```css
.glow-ring {
  width: 90px;
  height: 90px;
  border-radius: 50%;
  border: 3px solid rgba(56, 249, 215, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: breathe 4s ease-in-out infinite;
  position: relative;
}

.glow-ring::before {
  content: '';
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 1px solid rgba(56, 249, 215, 0.1);
  animation: breathe-outer 4s ease-in-out infinite;
}

.glow-ring-inner {
  width: 12px;
  height: 12px;
  background: #38f9d7;
  border-radius: 50%;
  animation: breathe-dot 4s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% {
    box-shadow:
      0 0 15px rgba(56, 249, 215, 0.15),
      inset 0 0 15px rgba(56, 249, 215, 0.05);
    transform: scale(1);
    border-color: rgba(56, 249, 215, 0.3);
  }
  50% {
    box-shadow:
      0 0 40px rgba(56, 249, 215, 0.35),
      0 0 80px rgba(56, 249, 215, 0.1),
      inset 0 0 25px rgba(56, 249, 215, 0.1);
    transform: scale(1.08);
    border-color: rgba(56, 249, 215, 0.6);
  }
}

@keyframes breathe-outer {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50%      { transform: scale(1.15); opacity: 0.7; }
}

@keyframes breathe-dot {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50%      { opacity: 1; transform: scale(1.3); }
}
```

**心地よさのポイント**: 3層（外側リング・メインリング・中央ドット）が同じ4秒周期で連動しつつ、`scale` 値をずらすことで奥行き感のある「呼吸」を実現。`box-shadow` の多重指定でグローを滲ませ、有機的な光の広がりを表現しています。

---

## 簡易紹介 ― 残り8選

以下の8つもデモページで実際に触って確認できます。

### 8. Morphing Button（モーフィングボタン）

ホバーで背景色が左から右へスライドしてフィルする。`width: 0%` → `width: 100%` の `::before` 疑似要素で実装。

```css
.morphing-btn::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 0%;
  height: 100%;
  background: #6c63ff;
  transition: width 0.45s cubic-bezier(0.65, 0, 0.35, 1);
  z-index: -1;
}
.morphing-btn:hover::before { width: 100%; }
```

### 9. Magnetic Card（磁気カード）

ホバーで浮き上がり、わずかに3D回転する。`translateY(-8px) rotateX(4deg) rotateY(-2deg)` による微妙な傾きが高級感を演出。

### 10. Liquid Loading（液体ローディング）

3つのドットが波打つように上下するローディング。`animation-delay` を0.15秒ずつずらして「液体が跳ねる」連鎖を作ります。

```css
.liquid-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  animation: liquid-wave 1.4s ease infinite;
}
.liquid-dot:nth-child(1) { animation-delay: 0s; }
.liquid-dot:nth-child(2) { animation-delay: 0.15s; }
.liquid-dot:nth-child(3) { animation-delay: 0.3s; }
```

### 11. Ripple Effect（リップル効果）

クリック時に中央から広がる波紋。`:active` でサイズ0の円を瞬時に300pxに展開し、`opacity` でフェードアウト。

### 12. Stagger Fade-in Cards（時差フェードイン）

4枚のカードが下からスタガー表示。`animation-delay` を0.12秒ずつずらし、ホバーで再生。

```css
@keyframes stagger-fade-in {
  0%   { opacity: 0; transform: translateY(30px) scale(0.85); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
```

### 13. Elastic Notification Badge（弾性バッジ）

通知ベルにホバーすると揺れ、バッジがポップイン。`bell-ring` keyframeで左右に減衰振動、バッジは `scale(0)` → `scale(1.25)` → `scale(1)` で弾む登場。

### 14. Tooltip Bubble（ツールチップ）

ホバーで上方にツールチップが浮上。`scale(0.8) translateY(8px)` → `scale(1) translateY(0)` のバウンス付き出現。

### 15. Pulse Ring Button（パルスリングボタン）

ボタンの外側にリングが繰り返し拡大・フェードアウトする波紋。3つのリングを `animation-delay` でずらして常時パルス。CTAボタンに最適。

```css
@keyframes pulse-expand {
  0%   { transform: scale(1); opacity: 0.6; }
  100% { transform: scale(1.35); opacity: 0; }
}
.pulse-ring { animation: pulse-expand 2s ease infinite; }
.pulse-ring:nth-child(2) { animation-delay: 0.6s; }
.pulse-ring:nth-child(3) { animation-delay: 1.2s; }
```

> すべてのコードは[デモページ](https://mattyopon.github.io/dawn-code/micro-interactions.html)のソースから取得できます。

---

## 心地よさの設計原則

15個のパーツを通じて見えてくる「心地よいアニメーション」の共通原則をまとめます。

### Duration: 0.3s〜0.5s が黄金ゾーン

- **0.3秒未満**: 速すぎて変化に気づきにくい
- **0.3〜0.5秒**: 「あ、動いた」と認識できつつ待たされない
- **0.5秒超**: ループアニメーション（呼吸リングの4秒など）や装飾的用途に限定

### イージング: `cubic-bezier` でバウンス感を出す

```css
/* 定番のバウンスイージング */
--ease-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);

/* 柔らかい戻り */
--ease-out-back: cubic-bezier(0.18, 0.89, 0.32, 1.28);
```

制御点のY値が **1.0を超える** と、目標値を一旦超えてから戻る動きになります。これが物理世界の「慣性」を再現し、心地よさの源になります。

### transform 中心で 60fps を維持

`transform` と `opacity` だけをアニメーションさせるのが鉄則です。

| プロパティ | コスト | 60fps |
|-----------|--------|-------|
| `transform`, `opacity` | Composite のみ | 維持しやすい |
| `background`, `box-shadow` | Paint | やや注意 |
| `width`, `height`, `top` | Layout + Paint | 避ける |

今回の15パーツはすべて `transform` ベースで構築し、`box-shadow` を使う部分（Glow Ring等）も GPU 合成が効くよう `will-change` を意識しています。

### 「戻り」のアニメーションも丁寧に

ホバー解除やトグルOFF時のアニメーションを雑にすると、途端にチープに感じます。`transition` プロパティを要素本体に書くことで、行きも帰りも同じイージングが適用されます。

```css
/* 行きも帰りも同じバウンス */
.toggle-track::after {
  transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

---

## アクセシビリティへの配慮

すべてのパーツに `prefers-reduced-motion` 対応を入れています。

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

「アニメーションを減らす」設定のユーザーにはすべての動きが無効化されます。心地よさを追求しつつ、**使う人を選ばない**のが本当の設計です。

---

## まとめ

- 全15パーツ、JavaScript不使用の純CSS実装
- **デモページ**: https://mattyopon.github.io/dawn-code/micro-interactions.html
- **GitHub**: https://github.com/mattyopon/dawn-code

気に入ったパーツがあれば、デモページのソースからコピペして使ってください。カスタムプロパティ（CSS変数）の色やイージングを差し替えるだけで、自分のプロジェクトに馴染むマイクロインタラクションになります。

UI設計において「動き」は装飾ではなく**フィードバック**です。ユーザーの操作に対して「ちゃんと反応している」と伝える、最も簡潔な手段がマイクロインタラクションです。
