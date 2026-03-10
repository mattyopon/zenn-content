---
title: "Chromeブックマークを毎日自動整理するPythonスクリプトを作った（WSL2 + cron）"
emoji: "🔖"
type: "tech"
topics: ["python", "chrome", "wsl2", "automation", "cron"]
published: true
---

## TL;DR

Chromeのブックマークファイル（JSON）を直接読み書きして、**ドメインベースの自動フォルダ分類・重複除去・トラッキングURL除去**を行うPythonスクリプトを作りました。WSL2のcronで毎日自動実行し、全Chromeプロファイルに対応しています。

## なぜ作ったか

ブックマークが増えると「ブックマーク バー」や「その他のブックマーク」が散らかります。手動でフォルダ分けするのは面倒だし、続かない。

また、Google検索経由で保存したブックマークのURLには `utm_source` や `gclid` などのトラッキングパラメータが大量に付いていて汚い。

「毎日自動で整理してくれたらいいのに」を実現しました。

## 仕組み

### Chromeブックマークの正体

Chromeのブックマークは、実はただのJSONファイルです。

```
# Windows上のパス
%LOCALAPPDATA%\Google\Chrome\User Data\Default\Bookmarks

# WSL2からのパス
/mnt/c/Users/<ユーザー名>/AppData/Local/Google/Chrome/User Data/Default/Bookmarks
```

中身はこんな構造になっています。

```json
{
  "roots": {
    "bookmark_bar": {
      "children": [...],
      "name": "ブックマーク バー",
      "type": "folder"
    },
    "other": {
      "children": [...],
      "name": "その他のブックマーク",
      "type": "folder"
    },
    "synced": {
      "children": [],
      "name": "モバイルのブックマーク",
      "type": "folder"
    }
  }
}
```

各ブックマークは `type: "url"` で、フォルダは `type: "folder"` + `children` 配列。これを読み書きするだけでブックマークを操作できます。

### 処理フロー

```
Chrome Bookmarks (JSON)
  ↓ 読み込み
全ブックマークをフラットに収集
  ↓
URLクリーンアップ（トラッキングパラメータ除去）
  ↓
重複除去（URL正規化して比較）
  ↓
ドメインベースでカテゴリ分類
  ↓
フォルダ構造を再構築
  ↓
ID再割り当て
  ↓ 書き込み
Chrome Bookmarks (JSON)
```

## 主要機能

### 1. 全プロファイル自動検出

Chromeは複数プロファイルに対応しています（仕事用・プライベート用など）。`User Data` ディレクトリを走査して、`Bookmarks` ファイルを持つ全プロファイルを自動検出します。

```python
CHROME_USER_DATA_DIR = "/mnt/c/Users/user/AppData/Local/Google/Chrome/User Data"

def discover_profiles() -> list[dict]:
    profiles = []
    for entry in os.listdir(CHROME_USER_DATA_DIR):
        profile_dir = os.path.join(CHROME_USER_DATA_DIR, entry)
        bookmarks_path = os.path.join(profile_dir, "Bookmarks")
        if not os.path.isfile(bookmarks_path):
            continue

        # Preferencesからプロファイル表示名を取得
        display_name = entry
        prefs_path = os.path.join(profile_dir, "Preferences")
        if os.path.isfile(prefs_path):
            try:
                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
                display_name = prefs.get("profile", {}).get("name", entry)
            except Exception:
                pass

        profiles.append({
            "dir_name": entry,
            "display_name": display_name,
            "bookmarks_path": bookmarks_path,
        })
    return profiles
```

プロファイルが追加されても、設定変更なしで自動的に対象に含まれます。

### 2. ドメインベースのカテゴリ分類

URLに含まれるドメイン文字列でカテゴリを判定します。

```python
CATEGORY_RULES = [
    ("転職・キャリア", [
        "pasonacareer", "freelance-hub", "doda-x.jp", "doda.jp",
        "bizreach", "geekly", "levtech", ...
    ]),
    ("学習・資格", [
        "coursera", "udemy", "certmetrics", "credly", ...
    ]),
    ("AI・ツール", [
        "claude.ai", "openai.com", "genspark", "notebooklm", "deepl.com", ...
    ]),
    ("開発・技術", [
        "github.com", "zenn.dev", "qiita.com", "stackoverflow", ...
    ]),
    ("動画・エンタメ", [
        "youtube.com", "bilibili", "unext", "netflix", ...
    ]),
    # ...
]
```

ルールにマッチしなくても、既存のフォルダに入っていたブックマークはそのフォルダを維持します。どのルールにもマッチせず、フォルダにも入っていないものだけが「ブックマーク バー」に残ります。

### 3. トラッキングパラメータの除去

Google広告やアフィリエイト系のパラメータを自動除去します。

```python
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "gbraid", "gad_source", "gad_campaignid",
    "campaign_id", "adgroup_id", "ad_id", "keyword", "matchtype",
    "hvpone", "hvptwo", "hvadid", "hvpos", "hvnetw", "_gl",
    # ...
}

def clean_url(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in params.items() if k not in TRACKING_PARAMS}
    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
```

**Before:**
```
https://www.amazon.co.jp/?&tag=hydraamazonav-22&ref=pd_sl_7ibq2d37on_e
  &adgrpid=157529192841&hvpone=&hvptwo=&hvadid=675114138690&hvpos=
  &hvnetw=g&hvrand=337846274775201308&hvqmt=e&hvdev=c...
```

**After:**
```
https://www.amazon.co.jp/
```

### 4. 重複除去

URLを正規化（末尾スラッシュ・フラグメント除去）して比較し、同じURLのブックマークは最初のものだけ残します。

```python
normalized = urlparse(bm["url"])
norm_key = f"{normalized.scheme}://{normalized.netloc}{normalized.path.rstrip('/')}"
```

### 5. プロファイルごとのバックアップ

整理前に必ずバックアップを取ります。プロファイルごとに30世代保持。

```
bookmark_backups/
  Default/
    Bookmarks_20260310_040000.json
    Bookmarks_20260309_040000.json
    ...
  Profile 1/
    ...
  Profile 2/
    ...
```

## Chrome epoch について

ChromeのブックマークJSONには `date_added` や `date_modified` というタイムスタンプがありますが、Unix epochではなく **Chrome独自のepoch**（1601年1月1日からのマイクロ秒）です。

```python
def chrome_epoch():
    # Chrome epoch = Unix epoch + 11644473600 seconds
    return str(int((time.time() + 11644473600) * 1_000_000))
```

新しいフォルダを作るときに正しいタイムスタンプを設定しないと、Chromeが混乱する可能性があります。

## cron設定

WSL2のcronで毎日AM 4:00に自動実行しています。

```bash
# ラッパースクリプト: run_bookmark_organizer.sh
#!/bin/bash
LOG_DIR="/home/user/scripts/bookmark_logs"
LOG_FILE="${LOG_DIR}/organizer_$(date +%Y%m%d).log"
mkdir -p "$LOG_DIR"

echo "=== 実行開始: $(date) ===" >> "$LOG_FILE"
/usr/bin/python3 /home/user/scripts/chrome_bookmark_organizer.py >> "$LOG_FILE" 2>&1
echo "=== 実行完了: $(date) ===" >> "$LOG_FILE"

# 30日以上前のログを削除
find "$LOG_DIR" -name "organizer_*.log" -mtime +30 -delete 2>/dev/null
```

```bash
# crontab -e
0 4 * * * /usr/bin/flock -n /tmp/bookmark-organizer.lock /home/user/scripts/run_bookmark_organizer.sh
```

`flock` で排他ロックをかけて、多重実行を防止しています。

## 実行結果

```
============================================================
Chrome ブックマーク自動整理（全プロファイル対応）
実行日時: 2026-03-10 12:15:52
============================================================

検出プロファイル数: 3
  - Chrome (Default)
  - Chrome (Profile 1)
  - Chrome (Profile 2)

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
プロファイル: Chrome (Default)
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  整理結果: 43件→43件 (重複除去:0, URL修正:0, 移動:0)
    📁 その他のブックマーク (0件)
      📂 転職・キャリア (7件)
      📂 学習・資格 (10件)
      📂 AI・ツール (6件)
      📂 開発・技術 (9件)
      📂 動画・エンタメ (5件)
      📂 ショッピング (2件)
      📂 ユーティリティ (3件)

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
プロファイル: Chrome (Profile 2)
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  整理結果: 103件→101件 (重複除去:2, URL修正:3, 移動:12)
    📁 その他のブックマーク (0件)
      📂 AI・ツール (1件)
      📂 開発・技術 (1件)
      📂 動画・エンタメ (10件)
      📂 配信管理 (22件)
      📂 配信 (32件)

============================================================
全体サマリー:
  処理プロファイル数: 3/3
  総ブックマーク数: 149→147
  総重複除去: 2件
  総URLクリーンアップ: 4件
  総フォルダ移動: 12件
============================================================
```

## 注意点

### Chrome起動中の書き込み

Chromeは `Bookmarks` ファイルの変更を検知して自動リロードしますが、**Chrome起動中に書き込むと変更が上書きされる可能性**があります。cronをAM 4:00に設定しているのは、PCがスリープ状態でChromeが停止している時間帯を狙っているためです。

スクリプト内でChrome起動チェックもしています。

```python
def is_chrome_running() -> bool:
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command",
             "Get-Process chrome -ErrorAction SilentlyContinue | Select-Object -First 1"],
            capture_output=True, text=True, timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False
```

### カテゴリルールの拡張

新しいサイトをブックマークしたときに自動分類されるよう、`CATEGORY_RULES` にドメインパターンを追加するだけでOKです。

```python
# 例: SNSカテゴリを追加
("SNS", [
    "twitter.com", "x.com", "instagram.com",
    "facebook.com", "threads.net",
]),
```

## 技術スタック

- **Python 3.12** - 標準ライブラリのみ（外部依存なし）
- **WSL2** - Windows上のChromeファイルに `/mnt/c/` 経由でアクセス
- **cron + flock** - 日次自動実行 + 排他制御

## まとめ

ChromeのブックマークはただのJSONファイルなので、読み書きするだけで自由に操作できます。外部依存ゼロのPythonスクリプトとcronだけで、ブックマークの自動整理が実現できました。

同じようにブックマークの散らかりが気になっている人は、カテゴリルールを自分好みにカスタマイズして使ってみてください。
