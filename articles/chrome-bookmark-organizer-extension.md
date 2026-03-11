---
title: "Chromeブックマーク自動整理の続編 ― ローカルJSON編集では同期に負ける問題をChrome拡張機能で解決した"
emoji: "🧩"
type: "tech"
topics: ["chrome", "javascript", "chromeextension", "automation", "python"]
published: true
---

## TL;DR

[前回の記事](https://zenn.dev/yutaro2076145/articles/chrome-bookmark-auto-organizer)でPythonスクリプトによるブックマーク自動整理を作りましたが、**Chrome Syncによってクラウド側のデータでローカルが上書きされ、整理が元に戻る**という致命的な問題がありました。

解決策として**Chrome拡張機能（chrome.bookmarks API）**で整理するように作り直しました。APIを通じた変更はChrome Syncに正しく認識されるため、クラウドにも反映されて元に戻りません。

## 前回のおさらい：Pythonスクリプト方式

前回は以下のアプローチでした：

```
WSL2 cron (毎日AM4:00)
  → Python スクリプト
    → Bookmarks JSON を直接読み書き
      → ドメインベースでフォルダ分類
      → 重複除去
      → トラッキングURL除去
```

Chrome停止中にJSONファイルを書き換えるので、処理自体は問題なく動きます。

## 発覚した問題：Chrome Syncとの戦い

### 症状

スクリプトを実行するとブックマークは綺麗に整理される。しかし**Chromeを起動すると数秒で元の散らかった状態に戻る**。

### 原因の特定

調査の過程で以下のことがわかりました：

1. **Pythonスクリプト実行後のBookmarksファイル**: 整理済み（フォルダ分類・重複除去完了）
2. **Chrome起動直後のBookmarksファイル**: 元に戻っている

Chrome Syncは起動時にクラウド側のブックマークデータをダウンロードし、ローカルの`Bookmarks`ファイルを上書きします。Pythonスクリプトはファイルを直接書き換えているだけなので、Chromeから見ると「外部からの不正な変更」となり、クラウド側のデータが優先されてしまいます。

### 試行錯誤した対策（全て失敗）

| 対策 | 結果 |
|------|------|
| Chrome停止中に整理 → 起動 | 同期でクラウド側に上書きされる |
| Preferences の `sync.bookmarks` を `false` に変更 | Chromeが起動時に設定をリセットする |
| 整理 → Chrome起動して同期待ち → 閉じて再整理 | 2回目の整理もChrome起動時に上書きされる |
| Chrome起動 → 同期完了待ち → 閉じて整理 → 起動 | 同上。クラウドが常に勝つ |

**結論：Bookmarks JSONを直接書き換えるアプローチでは、Chrome Syncが有効な環境では使えない。**

## 解決策：Chrome拡張機能で整理する

### なぜ拡張機能なら解決するのか

Chrome拡張機能が提供する `chrome.bookmarks` API を通じてブックマークを操作すると、Chromeはその変更を**正規の操作**として認識します。つまり：

- `chrome.bookmarks.move()` でフォルダに移動 → **クラウドにも同期される**
- `chrome.bookmarks.remove()` で重複を削除 → **クラウドからも削除される**
- `chrome.bookmarks.update()` でURL修正 → **クラウドにも反映される**

ローカルのJSONファイルを直接弄るのではなく、**Chromeの内部APIを使う**ことで同期問題を根本解決できます。

## 実装

### ディレクトリ構成

```
chrome-bookmark-organizer-ext/
├── manifest.json    # 拡張機能定義
├── popup.html       # ポップアップUI
├── organizer.js     # 整理ロジック
└── icon.png         # アイコン
```

### manifest.json

```json
{
  "manifest_version": 3,
  "name": "ブックマーク自動整理",
  "version": "1.0",
  "description": "ブックマークをカテゴリフォルダに自動分類・重複除去する",
  "permissions": ["bookmarks"],
  "action": {
    "default_popup": "popup.html",
    "default_icon": "icon.png"
  }
}
```

`permissions` に `"bookmarks"` を指定するだけで `chrome.bookmarks` API が使えます。Manifest V3対応。

### 分類ルール

Pythonスクリプトと同じドメインベースのルールをJavaScriptに移植：

```javascript
const CATEGORY_RULES = [
  ["転職・キャリア", [
    "pasonacareer", "freelance-hub", "doda-x.jp", "bizreach",
    "geekly", "levtech", "green-japan", "wantedly", "findy",
  ]],
  ["学習・資格", [
    "coursera", "udemy", "certmetrics", "credly",
    "academy.openai", "skills.google",
  ]],
  ["AI・ツール", [
    "claude.ai", "openai.com", "genspark", "notebooklm",
    "chatgpt", "gemini.google", "deepl.com", "perplexity",
  ]],
  ["開発・技術", [
    "github.com", "zenn.dev", "qiita.com", "stackoverflow",
    "aws.amazon.com", "cloud.google.com", "terraform", "docker",
  ]],
  ["動画・エンタメ", [
    "youtube.com", "bilibili", "netflix", "twitch.tv",
  ]],
  ["ショッピング", [
    "amazon.co.jp", "rakuten.co.jp", "mercari",
  ]],
  ["ユーティリティ", [
    "gigafile", "drive.google.com",
  ]],
];

function getCategory(url) {
  const lower = url.toLowerCase();
  for (const [category, patterns] of CATEGORY_RULES) {
    for (const pattern of patterns) {
      if (lower.includes(pattern)) return category;
    }
  }
  return null;
}
```

### 重複除去ロジック

```javascript
// URLを正規化して重複を検出
const seen = new Map();
const duplicateIds = [];

for (const bm of allBookmarks) {
  try {
    const u = new URL(bm.url);
    const key = `${u.protocol}//${u.host}${u.pathname.replace(/\/$/, "")}`;
    if (seen.has(key)) {
      duplicateIds.push(bm.id);
    } else {
      seen.set(key, bm);
    }
  } catch { /* invalid URL */ }
}

// chrome.bookmarks API で削除 → クラウドにも反映される
for (const id of duplicateIds) {
  await chrome.bookmarks.remove(id);
}
```

ポイントは `chrome.bookmarks.remove()` を使っていること。JSONを直接消すのではなく、APIを通じて削除するため、Chrome Syncが正しくクラウド側にも変更を伝播します。

### フォルダ移動

```javascript
// 「その他のブックマーク」配下にカテゴリフォルダを作成（or既存を取得）
async function getOrCreateFolder(parentId, title) {
  const children = await chrome.bookmarks.getChildren(parentId);
  const existing = children.find(c => !c.url && c.title === title);
  if (existing) return existing;
  return chrome.bookmarks.create({ parentId, title });
}

// ブックマークを適切なフォルダに移動
const category = getCategory(bm.url);
if (category) {
  const targetFolder = categoryFolders[category];
  if (bm.parentId !== targetFolder.id) {
    await chrome.bookmarks.move(bm.id, { parentId: targetFolder.id });
  }
}
```

### トラッキングURL除去

```javascript
const TRACKING_PARAMS = new Set([
  "utm_source", "utm_medium", "utm_campaign", "utm_term",
  "utm_content", "gclid", "gbraid", "gad_source", "ref", "tag", "_gl",
]);

function cleanUrl(url) {
  try {
    const u = new URL(url);
    for (const param of TRACKING_PARAMS) {
      u.searchParams.delete(param);
    }
    return u.toString();
  } catch { return url; }
}

// API経由でURL更新
const cleaned = cleanUrl(bm.url);
if (cleaned !== bm.url) {
  await chrome.bookmarks.update(bm.id, { url: cleaned });
}
```

## Python版との比較

| 項目 | Python（前回） | Chrome拡張機能（今回） |
|------|---------------|---------------------|
| **仕組み** | Bookmarks JSONを直接読み書き | chrome.bookmarks API |
| **同期対応** | ❌ クラウドに上書きされる | ✅ クラウドにも反映される |
| **実行方法** | cron自動実行（WSL2） | 拡張機能のボタンをクリック |
| **Chrome状態** | 停止中のみ | 起動中に実行 |
| **対応プロファイル** | 全プロファイル一括 | 現在のプロファイルのみ |
| **依存** | Python3, WSL2 | Chrome のみ |

## ハマったポイント

### 1. Bookmarks JSONの直接編集はChrome Syncに無視される

これが今回の最大の学び。Chrome Syncは独自の変更追跡メカニズムを持っており、外部からのファイル書き換えは「不正な変更」として扱われます。次回Chrome起動時にクラウド側のデータで上書きされます。

### 2. Preferences での同期制御も効かない

`Preferences` ファイルの `sync.bookmarks` を `false` に書き換えても、Chrome起動時にこの設定自体がリセットされることがあります。Sync設定はChrome UIから変更しないと確実ではありません。

### 3. Google Sync APIは公開されていない

「クラウド側のブックマークを直接編集できないか？」も調査しましたが、Google Chrome Sync APIは非公開です。旧Google Bookmarks APIも廃止済み。結局、Chrome拡張機能が唯一の正規ルートです。

## インストール方法

1. [GitHub](https://github.com/mattyopon) からリポジトリをクローン（またはZIPダウンロード）
2. Chromeで `chrome://extensions` を開く
3. 「デベロッパーモード」をON
4. 「パッケージ化されていない拡張機能を読み込む」をクリック
5. ダウンロードしたフォルダを選択
6. ツールバーのアイコンをクリック → 「整理を実行」

## 今後の展望

- **自動実行**: `chrome.alarms` APIを使って定期実行（1日1回など）
- **ルールのカスタマイズUI**: ポップアップ画面でドメイン→フォルダのマッピングを編集可能に
- **Chrome Web Store公開**: 他のユーザーも使えるように公開
- **Python版との棲み分け**: Chrome Sync無効環境（オフライン環境など）ではPython版が引き続き有効

## まとめ

- Chromeブックマークの自動整理で、**Bookmarks JSONの直接編集はChrome Syncと共存できない**
- **chrome.bookmarks API（Chrome拡張機能）を使えば、変更がクラウドにも正しく同期される**
- Manifest V3 + `bookmarks` permission だけで実装可能
- Python版の分類ルールをそのままJavaScriptに移植でき、ロジックの互換性も保てた

**関連記事:**
- [Chromeブックマークを毎日自動整理するPythonスクリプトを作った（WSL2 + cron）](https://zenn.dev/yutaro2076145/articles/chrome-bookmark-auto-organizer)
