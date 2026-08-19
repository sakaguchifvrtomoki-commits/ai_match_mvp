# フェアリーズ

AIとの会話を通じてユーザーの性格・価値観・関心を分析し、相性の良い候補者を紹介するマッチングMVPです。

会話を重ねることで、ユーザーごとのパーソナルAI「Fairy」がプロフィールを蓄積・更新し、通常会話やマッチングに活用します。

## 現在のバージョン

**v0.2.1**

## 主な機能

- StreamlitによるチャットUI
- スマホ対応のLINE風UI
- AIとの会話を通じた性格・価値観分析
- 候補者データとのマッチング
- マッチング理由・注意点・最初のメッセージ提案
- マッチ後支援
- ユーザーごとの固定 `user_id`
- セッションごとの `session_id`
- Fairyプロフィールの生成・保存
- Fairyプロフィールの差分更新
- プロフィール更新履歴の保存
- 保存プロフィールを通常会話へ補助的に反映
- AIによる初回挨拶の生成
- ログ保存同意画面
- ローカルおよびGoogle Driveへのログ保存
- アンケートへの導線
- PC向けデバッグ表示
- エラー時のフォールバック処理

## v0.2.1の主な変更

- v0.2.0で発生した重大な不具合（旧バージョンのプロフィールJSON読み込み時に例外が起きると、元ファイルが
  `.bak`へ退避され、過去の人格情報を継承しない新規プロフィールが作られてしまう）を修正
- `profile_version` を見て段階的にプロフィール構造を補完する `migrate_profile()` を追加
  （`0.1.0 → 0.1.1 → 0.1.2 → 0.1.3 → 0.2.0 → 0.2.1` の順に1段階ずつ変換、未対応バージョンは
  明示的にエラーとし、新規プロフィールへは初期化しない）
- 候補管理（`canonical_key`）導入前の旧プロフィールが持つプレーンテキスト（`personality_traits`の各項目、
  `preferences.conversation_topics`）を、マイグレーション時に1件のcandidate/メタデータとして種付けし、
  その後のマージで消えないようにした
- `canonical_key`を持たない旧candidateには、`legacy_<sha256先頭16桁>`形式の決定的なキーを補完
  （何度マイグレーションしても同じキーになり、重複しない）
- プロフィール保存をアトミック化（一時ファイルへ書き込み→再読込・検証→元ファイルと置き換え）し、
  保存途中の失敗で元プロフィールが壊れないようにした
- マイグレーション前に旧ファイルを**コピー**でバックアップ（`.pre_migration.bak`）してから変換を実施
  （移動ではなくコピーのため、失敗時も元ファイルが残る）
- マイグレーション・検証の失敗時は例外を投げて処理を停止し、元ファイルの上書きや新規プロフィールの
  自動作成を行わない
- 実際に発生した2件のプロフィール（更新回数のリセット）を、旧バックアップと今回のセッション情報を
  マージして復旧（`profile_update_count` 9→10, 10→11）
- マイグレーションの自動テストを12件追加（実プロフィールをfixtureとして使用）

## v0.1.3の主な変更

- candidateを `canonical_key`（snake_case英語キー）単位で管理し、セッション横断で同一概念を正確に統合
- 1セッションから複数のcandidateを独立して抽出・管理可能
- `support_count` が2以上かつ同一 `canonical_key` が複数セッションで確認された場合のみ stable に昇格
- 明示的な訂正（`corrections`）を処理し、旧candidateをcorrected状態に移行、新candidateを生成
- `stable_good_match` も同様のcandidate管理と昇格ルールで更新
- `personality_trait_candidates` をフィールドごとにcandidate管理し、display文字列を自動生成（上限200文字）
- `conversation_topic_metadata` をセッション横断で蓄積し、重要度・support_countによる上限30件の自動eviction
- `reasoning_history_entries` に session_id を追加し、最新エントリを先頭に保持（上限20件、古いものを自動削除）
- プロフィール更新をsession_id単位で冪等化（同一セッションの再適用は変更なし）
- evidenceリストを最新10件で管理（古いものを自動削除）
- 既存candidateが別セッションで再確認された場合、AIは既存canonical_keyを `reinforced_candidate_keys` として返し、support_countとevidenceを更新する。同じ特徴が2つの異なるセッションで確認されると、candidateはstableへ昇格する
- 同様の仕組みを `matching_hypothesis`（`reinforced_stable_good_match_candidate_keys`）と `personality_traits`（`personality_trait_reinforced_keys`）にも適用
- 差分マージの回帰テストを52件追加（v0.1.3合計57件）、reinforcement系テストを23件追加（合計80件）

## バージョン履歴

### v0.1.1

- Fairyプロフィールを通常会話へ反映
- 会話用の記憶コンテキストを短く整理
- プロフィール全文をプロンプトへ渡さない設計へ変更
- 現在のユーザー発言を保存プロフィールより優先
- 記憶の使用状況をデバッグログで確認可能にした

### v0.1.0

- ユーザーごとのFairyプロフィールを実装
- 会話から性格・価値観・関心・マッチング仮説を抽出
- プロフィールをJSONで保存
- `user_id` ごとに同じプロフィールを継続更新
- プロフィール履歴を保存
- プロフィール更新を全文再生成方式から差分更新方式へ変更
- Python側で重複排除、件数制限、更新回数、履歴管理を実施
- JSON生成失敗時の再試行と既存プロフィール保護を追加

### v0.0.4

- LINE風チャットUI
- スマホ対応
- 固定下部操作バー
- 分析後のカード表示
- アンケートへの導線
- Google Driveへのログ保存

### v0.0.3

- アプリ内バージョン表示
- ログ保存機能
- ログ保存同意画面
- セッション管理
- 「最初からやり直す」機能
- 「終わる」機能
- `session_id` によるログ追跡

## 処理の概要

```text
ユーザーが会話を開始
↓
AIが短い初回挨拶を生成
↓
ユーザーとFairyが会話
↓
性格・価値観を分析
↓
候補者から相性の良い相手を提示
↓
会話内容からFairyプロフィールの差分を抽出
↓
Python側で既存プロフィールへ統合
↓
プロフィールと履歴を保存
```

## Fairyプロフィール

プロフィールには、主に次の情報を保存します。

```text
summary
├─ stable
├─ recent
├─ growth
└─ tensions

personality_traits
values
preferences
matching_hypothesis
confidence
memory_notes
uncertainties
evidence
```

プロフィール更新では、AIは現在のセッションから新しい情報や変更点のみを抽出します。

既存プロフィールとの統合、重複排除、件数制限、更新回数、タイムスタンプ、履歴保存はPython側で管理します。

### プロフィールのバージョン管理

各プロフィールJSONは `profile_version` を持ち、アプリの現在の `CURRENT_PROFILE_VERSION` より古い場合は
読み込み時に自動でマイグレーションされます。方針は次の通りです。

- 保存されている人格情報（`summary`, `values`, `preferences`, `matching_hypothesis`, `evidence` など）は
  マイグレーションで消したり初期値で上書きしたりしない。不足している項目のみ安全な初期値で補う
- マイグレーションは1バージョンずつ段階的に実行し、未対応の`profile_version`を検出した場合は
  新規プロフィールへの初期化を行わず、明示的なエラーとして処理を停止する
- マイグレーション前に旧ファイルをコピー（移動ではない）してバックアップを作成し、保存は
  一時ファイル経由のアトミック書き込みで行う。失敗時は元ファイルがそのまま残る

## セットアップ

### 1. リポジトリを取得

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Python環境を用意

仮想環境の利用を推奨します。

```bash
python -m venv .venv
```

Windows:

```bash
.venv\\Scripts\\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

### 3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数を設定

ローカル実行では、ルートディレクトリに `.env` を作成します。

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=your_model_name
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Streamlit Community Cloudでは、Secretsへ必要な値を設定します。

Google Drive保存を使用する場合は、Google OAuthまたはサービスアカウント関連の設定と保存先フォルダIDも必要です。

## 実行方法

```bash
python -m streamlit run app.py
```

起動後、ターミナルに表示されるURLをブラウザで開きます。

## user_id

ユーザーとFairyプロフィールを紐づけるため、URLパラメータから `user_id` を指定できます。

例：

```text
?user_id=test_user
```

同じ `user_id` を使用すると、過去に保存されたプロフィールを継続して更新します。

現段階ではアカウント機能は未実装です。将来、テストユーザーへアカウント作成を依頼する段階で、アカウントとニックネームをFairyへ紐づける予定です。

## 初回挨拶

v0.1.2では、新しいセッション開始時にAIが短い挨拶を生成します。

- 誰にでも通用する内容
- Fairyプロフィールは使用しない
- 名前での呼びかけは任意
- 呼びかける場合は「マスターさん」
- 同一セッション中は再生成しない
- API失敗時は固定文を表示

将来は「マスターさん」を、アカウントに登録されたニックネームへ置き換える予定です。

## ログ保存

本アプリでは、品質改善・動作確認のため、ユーザーの同意後にログを保存します。

保存対象：

- チャット履歴
- 分析結果
- マッチング結果
- マッチ後支援
- デバッグ情報
- エラー情報
- プロフィール更新結果

### 主な保存先

```text
logs/
├─ sessions/
├─ debug/
└─ errors/

user_profiles/
└─ history/
```

環境やバージョンによって、ログ配下にバージョン別フォルダが作成される場合があります。

### sessions

人間確認用のMarkdownログです。

保存内容：

- アプリバージョン
- `session_id`
- `user_id`
- 開始・終了時刻
- チャット履歴
- 分析結果
- マッチング結果
- マッチ後支援

### debug

JSON Lines形式のデバッグログです。

主なイベント：

- セッション開始・終了
- AI応答生成
- 初回挨拶生成
- 分析開始・完了
- マッチング開始・完了
- プロフィール差分抽出
- プロフィール更新
- Google Driveアップロード

### errors

JSON Lines形式のエラーログです。

保存内容：

- APIエラー
- 認証エラー
- JSON解析エラー
- ログ保存エラー
- Google Driveアップロードエラー
- その他の例外

## Google Drive保存

ローカル保存に加えて、セッションログをGoogle Driveへアップロードできます。

アップロード成功時には、ファイルID、ファイル名、閲覧URLなどをデバッグ情報で確認できます。

Google Drive保存に失敗しても、可能な限りアプリ本体とローカルログ保存は継続します。

## テスト

テストコードは `tests/` に配置します。

```bash
pytest
```

特定のテストだけ実行する場合：

```bash
pytest tests/<test_file>.py
```

## GitHubへアップロードしないファイル

以下のファイルやフォルダはGitHubへアップロードしません。

```text
.env
.streamlit/secrets.toml
.claude/settings.local.json
logs/
user_profiles/
```

APIキー、Google認証情報、ユーザープロフィール、会話ログをコミットしないでください。

## プロジェクト構成

主なファイル・フォルダ：

```text
app.py
fairy_memory.py
requirements.txt
README.md
prompts/
tests/
assets/
logs/
user_profiles/
```

## 現在確認している課題

- `summary.stable` が直近セッションの内容で置き換わりやすい
- 安定した特徴と直近の特徴の更新規則を分離する必要がある
- `matching_hypothesis.stable_good_match` も直近情報へ寄りやすい
- リスト上限により、新しい会話トピックが保存されない場合がある
- フィールドごとに「上書き・統合・追加・保留」の規則を定義する必要がある

## 今後の改善候補

- Fairyプロフィールの長期記憶統合ロジック改善
- ユーザーがプロフィールを確認・訂正できるUI
- 記憶の削除・忘却機能
- 記憶の重要度と有効期限
- アカウント機能
- ニックネームによる呼びかけ
- 複数端末間でのFairyプロフィール共有
- クラウドデータベース
- 候補者データとマッチングロジックの改善
- Fairy同士の相互作用
- Play to Match機能
- Neural Planetへ向けたパーソナルAI同士の実験
