---
title: "Vrew代替のAI字幕ツールをゼロから作った話"
emoji: "🎬"
type: "tech"
topics: ["ai", "react", "python", "ffmpeg"]
published: true
---

## TL;DR

**Subtitle Studio** は、AI音声認識で動画の字幕を自動生成し、編集・翻訳・書き出しまでワンストップで行えるデスクトップツールです。Vrew の OSS 代替として開発しました。

## 背景

動画制作において字幕作成は最も時間のかかる工程の一つです。Vrew は便利ですが、有料プランの制限やカスタマイズ性の不足が課題でした。

「Whisper API + GPT-4o-mini + edge-tts を組み合わせれば、同等以上のものが作れるのでは？」と思い、開発を始めました。

## 機能

### AI文字起こし
- OpenAI Whisper API による高精度な音声認識
- **ワードレベルのタイムスタンプ** - 単語単位で正確な時間同期

### 字幕編集
- インラインエディタで直接テキスト修正
- **WaveSurfer.js による波形タイムライン** - 音声波形を見ながら編集
- 無音区間の自動検出

### 多言語翻訳
- GPT-4o-mini による18言語対応翻訳
- 文脈を考慮した自然な翻訳

### 音声合成 (TTS)
- edge-tts による無料のテキスト読み上げ
- 多数の音声・言語に対応

### 書き出し
- SRT / ASS / VTT 形式の字幕ファイルエクスポート
- **FFmpeg による字幕焼き込み** - 動画に直接字幕を合成

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| フロントエンド | React 18 + TypeScript + Vite + TailwindCSS |
| 状態管理 | Zustand |
| 波形表示 | WaveSurfer.js |
| バックエンド | Python + FastAPI |
| AI | OpenAI Whisper API + GPT-4o-mini |
| TTS | edge-tts (無料) |
| 動画処理 | FFmpeg |

## アーキテクチャ

```
React (Vite) ──> FastAPI Backend ──> Whisper API (STT)
     │                  │              GPT-4o-mini (翻訳)
     │                  │              edge-tts (TTS)
     │                  └──> FFmpeg (動画処理)
     └──> WaveSurfer.js (波形)
```

## 苦労した点

### ワードレベル同期
Whisper のレスポンスからワードレベルのタイムスタンプを抽出し、それを字幕セグメントとして構造化する処理が最も難しかったです。無音検出と組み合わせて自然な区切りを実現しました。

### FFmpeg 字幕焼き込み
ASS 形式のスタイリング（フォント、色、位置、アウトライン）を保持したまま動画に焼き込むパイプラインの構築に苦労しました。

## まとめ

AIの進化により、以前は専門ソフトが必要だった字幕制作が、OSSで実現できるようになりました。Whisper の精度は商用ツールに匹敵し、GPT-4o-mini の翻訳品質も実用レベルです。動画制作者の方はぜひ試してみてください。
