# PubMed → Discord 翻訳配信ツール

PubMedの新着論文を毎日2回（8:00 / 15:00 JST）、Claude APIで日本語に翻訳してDiscordへ自動投稿します。  
GitHub Actionsで完全無料で運用できます（外部サーバー不要）。

---

## セットアップ手順

### 1. リポジトリの準備

```bash
# GitHubで新しいリポジトリを作成し、このファイル群をpush
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/<あなたのID>/<リポジトリ名>.git
git push -u origin main
```

### 2. Secrets の登録

GitHub リポジトリの **Settings → Secrets and variables → Actions → Secrets** に追加：

| 名前 | 値 |
|------|----|
| `ANTHROPIC_API_KEY` | Anthropic Console で取得したAPIキー |
| `DISCORD_WEBHOOK_URL` | DiscordチャンネルのWebhook URL |
| `PUBMED_API_KEY` | （任意）NCBI My Account で取得。なくても動作します |

### 3. Variables の登録

同ページの **Variables** タブに追加：

| 名前 | 例 | 説明 |
|------|----|------|
| `PUBMED_KEYWORDS` | `menopause hormone therapy` | PubMed検索式。AND/OR/MeSH記法も可 |
| `MAX_RESULTS` | `5` | 1回あたりの最大取得件数（1〜10推奨） |

### 4. Discord Webhook URLの取得

1. Discordのチャンネル設定 → 連携サービス → ウェブフック
2. 「新しいウェブフック」を作成
3. URLをコピーして `DISCORD_WEBHOOK_URL` に貼り付け

---

## 配信スケジュール

| 配信 | JST | UTC（GitHub Actionsで設定）|
|------|-----|--------------------------|
| 朝   | 08:00 | 23:00（前日）|
| 午後 | 15:00 | 06:00 |

---

## 動作確認（手動実行）

GitHub の **Actions タブ** → **PubMed → Discord 翻訳配信** → **Run workflow** で即時実行できます。

---

## キーワード例

```
# 単純なキーワード
menopause hormone therapy

# MeSH + フリーワード
"Menopause"[MeSH] AND ("hormone replacement therapy" OR "HRT")

# 特定雑誌に絞る
menopause[tiab] AND Menopause[Journal]

# 著者で絞る
Manson JE[Author] AND menopause
```

---

## ファイル構成

```
.
├── fetch_and_post.py               # メインスクリプト（標準ライブラリのみ）
├── .github/
│   └── workflows/
│       └── pubmed_discord.yml      # GitHub Actions ワークフロー
└── README.md
```

---

## 注意事項

- NCBI E-utilities の利用規約に従い、APIキーなしの場合は1秒に3リクエスト以内です。
- Anthropic API は従量課金です。1回の実行あたり、論文5件で概ね **$0.01〜$0.03** 程度です。
- GitHub Actionsの無料枠は月2,000分。本ツールは1回あたり約1〜2分なので月60回（=1日2回×30日）でも余裕です。
