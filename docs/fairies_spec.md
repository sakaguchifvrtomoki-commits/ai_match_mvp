# Fairies v0.2.2 Flutter / FastAPI 移行仕様

## 1. 文書の目的

本書は、Fairies `v0.2.1` のStreamlit版を維持しながら、Flutterクライアント向けFastAPIを追加するための仕様を定義する。

- 開発バージョン: `v0.2.2`
- 開発ブランチ: `feature/v0.2.2-fastapi`
- 実装方針: APIを1本ずつ実装し、各APIの実装ごとにテストする
- 将来構成: FastAPIをクラウドへデプロイし、Flutterから利用する

## 2. システムの責務分担

### 2.1 Flutter

Flutterは以下を担当する。

- UI表示
- 画面遷移と画面状態
- 会話履歴 `messages` を含む一時データの保持
- エラー発生後の状態維持と再試行操作
- セッション終了後のアンケート画面への遷移

一時データはFlutter側のユーザー端末で保持する。

### 2.2 Python / FastAPI

Python/FastAPIは以下を担当する。

- OpenAI APIとの通信
- Fairyの会話応答生成
- ユーザーの人物分析
- 候補者とのマッチング
- マッチ後支援の生成
- Fairyプロフィールの抽出、merge、migration、更新
- セッションログおよびプロフィールの永続保存

FastAPI側では `st.session_state` を使用しない。API処理に必要な `user_id`、`session_id`、`messages` などはリクエストから明示的に受け取る。

### 2.3 データ保存

- 永続データは最終的にGoogle Driveを正本とする。
- Flutterが保持する会話履歴や画面状態は一時データとして扱う。
- Google Driveから既存プロフィールを読み込めなかった場合、空プロフィールを新規作成して上書きしてはならない。
- 永続化に失敗した場合は既存データを保護し、再試行可能なエラーとして扱う。

## 3. 既存v0.2.1との互換性

- 既存Streamlit版を壊さない。
- 既存の人物分析、マッチング、Fairyプロフィールmerge/migrationロジックは可能な限り再利用する。
- Streamlit固有の状態操作と、再利用可能な業務ロジックを分離してFastAPIから利用する。
- `v0.2.2` ではFairyプロフィールのスキーマを変更しない。
- 新しいプロフィールmigrationは追加しない。
- v0.2.1までの既存migration機構を維持する。
- スマホ移植後に、既存プロフィールの読み込み、更新、継承が正しく動くことをテストする。

## 4. API一覧

実装対象は以下の4 APIとする。

1. `POST /sessions`
2. `POST /chat`
3. `POST /match`
4. `POST /sessions/{session_id}/end`

## 5. 共通仕様

### 5.1 メッセージ形式

会話メッセージは少なくとも次の形式を使用する。

```json
{
  "role": "assistant",
  "content": "メッセージ本文"
}
```

`role` は送信者、`content` は本文を表す。会話履歴はFlutterが保持し、必要なAPIへ配列として送る。

### 5.2 共通エラー形式

APIエラーは次のJSON形式で返す。

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "ユーザー向けメッセージ"
  }
}
```

代表的なエラーコードは以下とする。

| code | 意味 |
| --- | --- |
| `INVALID_REQUEST` | 必須項目の欠落、型不正、値不正など |
| `AI_RESPONSE_FAILED` | AIから有効な応答を取得できなかった |
| `AI_RESPONSE_TRUNCATED` | AI応答が途中で切れた |
| `AI_CONTEXT_TOO_LONG` | AIへ送るコンテキストが上限を超えた |
| `INSUFFICIENT_MESSAGES` | マッチングに必要なユーザー発言数が不足している |
| `ANALYSIS_FAILED` | 人物分析に失敗した |
| `MATCHING_FAILED` | マッチングに失敗した |
| `PROFILE_UPDATE_FAILED` | Fairyプロフィール更新に失敗した |
| `SESSION_END_FAILED` | セッション終了処理または最終ログ保存に失敗した |

HTTPステータスコードの詳細な割り当ては、各API実装時にテストと合わせて定義する。レスポンス本文は上記形式に統一する。

### 5.3 エラー処理方針

- エラー発生時もFlutter側の会話履歴、入力内容、画面状態を消さない。
- Flutterから同じ処理を再試行できるようにする。
- エラー内容をFairyの発言として `messages` に混ぜない。
- AIによるJSON生成失敗は、Python内部で既存の再試行ロジックを利用する。
- マッチ後支援だけ失敗した場合は、成功したマッチ結果を返す。
- プロフィール更新だけ失敗した場合は、マッチ結果を返し、`profile_updated` を `false` とする。
- Google Driveから既存プロフィールを読み込めなかった場合、空プロフィールで上書きしない。

## 6. `POST /sessions`

### 6.1 目的

ユーザーのログ保存同意を確認し、新しいセッションを開始する。呼び出すたびに新しい `session_id` を生成する。

Streamlit版の `get_or_create_session_id()` のような暗黙の状態管理は使用しない。

### 6.2 Request

```json
{
  "user_id": null,
  "log_consent": true
}
```

| フィールド | 必須 | 型 | 説明 |
| --- | --- | --- | --- |
| `user_id` | 必須 | string または null | 既存ユーザーは既存ID、新規ユーザーは `null` |
| `log_consent` | 必須 | boolean | ログ保存への同意 |

要件:

- `log_consent` は必須とする。
- `log_consent=false` の場合、セッションを開始しない。
- `user_id=null` の場合、Python側で新しい `user_id` を生成する。
- 既存ユーザーの場合は、受け取った `user_id` を検証して利用する。
- APIを呼ぶたびに新しい `session_id` を生成する。

### 6.3 処理順序

以下の順序で処理する。

1. `user_id` を確定する。
2. 新しい `session_id` を生成する。
3. セッション開始時刻を記録する。
4. `log_consent` と同意情報を記録する。
5. 初期セッションログを作成する。
6. 初回挨拶を生成する。
7. FlutterへJSONレスポンスを返す。

途中でセッション開始を継続できないエラーが発生した場合は、共通エラー形式を返す。AIによる初回挨拶生成だけが失敗した場合は、固定フォールバック文を使用して成功扱いとする。

### 6.4 Response

```json
{
  "user_id": "user_xxxxx",
  "session_id": "session_xxxxx",
  "message": {
    "role": "assistant",
    "content": "..."
  }
}
```

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `user_id` | string | 既存または新規生成されたユーザーID |
| `session_id` | string | 今回新規生成されたセッションID |
| `message.role` | string | 常に `assistant` |
| `message.content` | string | AI生成またはフォールバックの初回挨拶 |

### 6.5 初回挨拶

- v0.2.1の `generate_initial_greeting()` のAI生成ロジックを可能な限り再利用する。
- 過去のFairyプロフィールは初回挨拶に使用しない。
- OpenAI APIが失敗した場合は、現行v0.2.1の固定フォールバック文を使用する。
- フォールバックを使用した場合も、セッション開始自体は成功として扱う。
- 初回挨拶を `st.session_state` へ保存しない。
- 生成した挨拶はレスポンスの `message` としてFlutterへ返し、その後の会話履歴はFlutterが保持する。

## 7. `POST /chat`

### 7.1 目的

Flutterが保持する会話履歴と既存Fairyプロフィールを使用し、次のFairy応答を生成する。

### 7.2 Request

```json
{
  "user_id": "user_xxxxx",
  "session_id": "session_xxxxx",
  "messages": [
    {
      "role": "assistant",
      "content": "こんにちは。"
    },
    {
      "role": "user",
      "content": "最近は読書をしています。"
    }
  ]
}
```

### 7.3 処理方針

- Flutterから `user_id`、`session_id`、現在の `messages` を受け取る。
- Pythonは既存プロフィールを読み込む。
- 既存のFairy記憶コンテキスト生成ロジックを利用してAI応答を生成する。
- 現在のユーザー発言を保存プロフィールより優先する。
- FastAPI側で会話履歴を暗黙に保持しない。
- AIや内部処理のエラー文字列をFairyの発言として返したり、`messages` に追加したりしない。
- 失敗時は共通エラー形式を返し、Flutterが元の会話履歴を保持したまま再試行できるようにする。

### 7.4 Response

```json
{
  "message": {
    "role": "assistant",
    "content": "Fairyの返答"
  }
}
```

FastAPIは受け取った `messages` をレスポンスへ含めず、保存・変更もしない。Flutterは成功時に返された `message` を端末上の会話履歴へ追加する。

### 7.5 エラー

| 条件 | HTTP status | code |
| --- | --- | --- |
| リクエストまたはIDの形式が不正 | 400 | `INVALID_REQUEST` |
| コンテキスト上限超過を明確に判定できた | 413 | `AI_CONTEXT_TOO_LONG` |
| AI応答が出力上限により途中で切れた | 502 | `AI_RESPONSE_TRUNCATED` |
| API未設定、通信失敗、空応答、その他のAI失敗 | 502 | `AI_RESPONSE_FAILED` |

エラー本文を会話メッセージとして返さない。エラー時もリクエストの `messages` は保存・変更しない。

## 8. `POST /match`

### 8.1 目的

会話履歴からユーザーを分析し、候補者とのマッチング、マッチ後支援、Fairyプロフィール更新、セッションログ保存を行う。

### 8.2 Request

```json
{
  "user_id": "user_xxxxx",
  "session_id": "session_xxxxx",
  "messages": [
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."}
  ]
}
```

### 8.3 処理順序

1. `messages` 内の空でないユーザー発言が3件以上あることを確認する。
2. 既存の `analyze_user()` 相当の処理で人物分析を行う。
3. 既存の `generate_match()` 相当の処理で候補者選定とマッチ結果生成を行う。
4. 既存の `generate_after_match_support()` 相当の処理でマッチ後支援を生成する。
5. 既存の `update_fairy_profile()` 相当の処理でFairyプロフィールを更新する。
6. 現在の分析結果、マッチ結果、マッチ後支援、プロフィール更新結果を含むセッションログを保存する。
7. Flutterへ結果を返す。

### 8.4 部分失敗

- ユーザー発言が3件未満の場合は `INSUFFICIENT_MESSAGES` を返す。
- 人物分析に失敗した場合は `ANALYSIS_FAILED` を返し、マッチング以降を実行しない。
- マッチングに失敗した場合は `MATCHING_FAILED` を返す。
- マッチ後支援だけ失敗した場合は、マッチング成功結果を返す。
- プロフィール更新だけ失敗した場合も、マッチング成功結果を返す。
- プロフィール更新の成否はレスポンス内の `profile_updated` で表し、失敗時は `false` とする。
- プロフィール読み込みに失敗した場合は、空プロフィールで既存プロフィールを上書きしない。

### 8.5 Response

```json
{
  "analysis": {
    "personality": "...", "values": "...", "hidden_needs": "...",
    "communication_style": "...", "ideal_partner_type": "...", "summary": "..."
  },
  "match": {
    "matched_candidate": {
      "id": "c01", "name": "葵", "age": 29, "personality": "...", "values": "...",
      "hobbies": "...", "communication_style": "...", "relationship_style": "...", "description": "..."
    },
    "match_score": 85,
    "match_label": "安心感重視タイプ",
    "match_reason": "...",
    "possible_concern": "...",
    "recommended_first_message": "..."
  },
  "top_candidates": [
    {"candidate": {"id": "c01", "name": "葵", "age": 29, "personality": "...", "values": "...", "hobbies": "...", "communication_style": "...", "relationship_style": "...", "description": "..."}, "similarity": 0.85}
  ],
  "after_match_support": {
    "first_message_today": "...", "question_in_3days": "...",
    "avoid_phrase": "...", "slow_reply_action": "..."
  },
  "profile_updated": true
}
```

`top_candidates` は既存v0.2.1が保持する上位3件の `{candidate, similarity}` を返す。マッチ後支援に失敗した場合は `after_match_support=null`、プロフィール更新に失敗した場合は `profile_updated=false` とする。

## 9. `POST /sessions/{session_id}/end`

### 9.1 目的

指定されたセッションの最終ログを `completed` として保存し、セッションを終了する。

### 9.2 処理方針

- URLパスから `session_id` を受け取る。
- セッションの最終ログを `completed` として保存する。
- このAPIでは人物分析、マッチング、Fairyプロフィール更新を行わない。
- 終了成功後のアンケート画面への遷移はFlutterが担当する。
- 終了処理または最終ログ保存に失敗した場合は `SESSION_END_FAILED` を返す。
- 失敗時もFlutter側の画面状態と一時データを維持し、再試行可能にする。

### 9.3 Request

```json
{
  "user_id": "user_xxxxx",
  "messages": [],
  "analysis": null,
  "match": null,
  "top_candidates": [],
  "after_match_support": null
}
```

`user_id` と `messages` は必須。分析前に終了できるため、分析・マッチ・マッチ後支援は任意とする。存在する場合は `POST /match` のResponseと同じ構造を送る。開始時刻と同意情報は `POST /sessions` が保存したセッションメタデータを使用する。

### 9.4 Response

```json
{"status": "completed"}
```

成功時は `session_status=completed`、`end_reason=user_clicked_finish`、終了時刻を `ended_at` に記録する。FastAPIはFlutterの一時状態を削除しない。保存失敗時はHTTP 500と `SESSION_END_FAILED` を返す。

## 10. プロフィールmigration方針

- `v0.2.2` ではプロフィールスキーマ自体を変更しない。
- 新しいmigrationは作成しない。
- v0.2.1までの段階的migration、検証、バックアップ、アトミック保存の仕組みを維持する。
- 未対応バージョンや読み込みエラーを新規の空プロフィールへ置き換えない。
- Flutter/FastAPI移行後も、既存プロフィールが読み込めることを確認する。
- 同じユーザーの既存プロフィールへ更新を適用し、過去情報を継承できることを確認する。
- 既存のmerge処理が持つセッション単位の冪等性を維持する。

## 11. テスト方針

- APIを1本ずつ実装し、その都度正常系、入力不正、AI失敗、保存失敗をテストする。
- FastAPIテストではStreamlitの `st.session_state` に依存しないことを確認する。
- 既存v0.2.1のプロフィールmerge/migrationテストを維持する。
- 部分失敗時に成功済みの結果が失われないことを確認する。
- エラー時にFlutterが会話や画面状態を維持して再試行できるレスポンスであることを確認する。
- Google Driveの読み込み失敗時に既存プロフィールを空データで上書きしないことを確認する。

## 12. Google Drive認証設定

FastAPIの `GoogleDriveStorage` はStreamlitの状態やsecretに依存せず、`GOOGLE_DRIVE_AUTH_MODE` で認証方式を明示的に選択する。

- `user_oauth`: GoogleユーザーOAuth 2.0。通常ユーザーのMy Driveへ、そのユーザー本人として接続する。
- `service_account`: `GOOGLE_SERVICE_ACCOUNT_JSON` のサービスアカウントを使用する。
- `adc`: Application Default Credentialsを使用する。
- `auto` または未指定: 従来互換として、サービスアカウントJSONがあれば使用し、なければADCを使用する。ユーザーOAuthへは暗黙に切り替えない。

ユーザーOAuthでは `GOOGLE_OAUTH_CREDENTIALS_JSON` を優先し、未指定の場合は `GOOGLE_OAUTH_TOKEN_FILE` のファイルを読む。ファイルパスの既定値は `token.json` とする。期限切れまたは無効なアクセストークンはrefresh tokenで更新する。tokenの不存在、形式不正、refresh失敗は保存先の不存在ではなく `Unavailable` として扱う。未知の認証方式は設定エラーとし、別方式へfallbackしない。

Drive内の保存先ルートは `GOOGLE_DRIVE_ROOT_FOLDER_ID` で指定する。秘密情報やtokenをソースコードへ保存しない。クラウド環境ではOAuth credential JSONをSecret Manager等から環境設定へ注入できる構造を使用する。

### 12.1 開発用テストルートのbootstrap

`drive.file` scopeのまま実Drive接続を確認するため、`scripts/create_drive_test_root.py` を開発者が明示的に1回実行する。このスクリプトはユーザーOAuthだけを許可し、ユーザーが指定した `パーソナルAIマッチングMVP` フォルダ直下にアプリ所有の `Fairies_Test` フォルダを作成してfolder IDを出力する。

親フォルダは名前から推測せず、`GOOGLE_DRIVE_PARENT_FOLDER_ID` でfolder IDを必須指定する。未設定の場合は認証やDrive操作より前に設定エラーとする。`Fairies_Test` の検索と作成は必ずこのID直下へ限定し、My Drive直下には作成しない。

テストルートは、指定親ID、`Fairies_Test` という名前、folder MIME、`data_type=fairies_test_root`、`app_id=fairies_v0_2_2` のappPropertiesで識別する。同じ識別情報のフォルダが1件あれば、手動で親フォルダ直下へ移動済みの場合も再利用する。複数件あれば競合として作成を中止し、名前だけが同じ別フォルダには触れない。取得したIDは後続の実Driveテストで `GOOGLE_DRIVE_ROOT_FOLDER_ID` に設定する。本番データの移行や既存Driveファイルの操作は行わない。

### 12.2 開発用OAuth再認証

既存tokenが失効してrefreshできない場合は、開発者が `scripts/authorize_google_drive.py` を明示的に実行する。対話的認証はFastAPIおよび `GoogleDriveStorage` へ組み込まず、Desktop app用OAuth client JSONを使用して `InstalledAppFlow.run_local_server(port=0)` で行う。scopeは `https://www.googleapis.com/auth/drive.file` から拡張しない。

OAuth clientファイルは `GOOGLE_OAUTH_CLIENT_FILE`、保存先は `GOOGLE_OAUTH_TOKEN_FILE` で指定する。既存tokenがある場合は通常実行を拒否し、`--force` を明示した場合だけ、タイムスタンプ付きバックアップを作成してからアトミックに置換する。保存前にrefresh tokenと `drive.file` scopeを検証する。token値は標準出力へ表示しない。この処理は認証tokenの取得だけを行い、Drive上のファイルやフォルダは作成しない。

### 12.3 GoogleDriveStorage実疎通テスト

`scripts/test_google_drive_storage_live.py` は、開発者が明示実行した場合だけ `GoogleDriveStorage.from_env()` で実Driveへ接続する。`FAIRIES_STORAGE_BACKEND=google_drive`、`GOOGLE_DRIVE_AUTH_MODE=user_oauth`、`GOOGLE_DRIVE_ROOT_FOLDER_ID` の明示設定を必須とし、rootにはbootstrapで取得した `Fairies_Test` のfolder IDを指定する。通常pytestではStorageをモックし、実Driveへ接続しない。

実行ごとにUUIDを含む `__fairies_drive_live_test_<uuid>__` と `__fairies_drive_live_session_<uuid>__` を生成し、プロフィールの不存在、作成、読込、更新、履歴、migration前バックアップ、およびセッションの作成、読込、更新を既存Storageインターフェースだけで確認する。秘密情報は表示せず、作成したtest user IDとtest session IDだけをcleanup・調査用に表示する。

失敗時の調査データを保持するため、自動cleanupは行わない。cleanupする場合は、成功時に表示された専用IDだけを使い、`Fairies_Test/profiles/current` のprofile、`profiles/history/<test user ID>`、`profiles/migration_backups/<test user ID>`、`sessions/<test session ID>` をGoogle Drive UIから手動削除する。共有の親フォルダや他のIDは削除しない。

### 12.4 FastAPI・Google Drive実統合テスト

`scripts/test_fastapi_google_drive_live.py` は、開発者が明示実行した場合だけFastAPIの `TestClient` から4 endpointを呼び、各service、Storage abstraction、`GoogleDriveStorage`、実Driveまでの経路を確認する。Driveは実接続するが、初回挨拶、チャット応答、人物分析、候補、マッチ結果、マッチ後支援、プロフィール抽出AIは固定stubとし、OpenAI APIへ接続しない。プロフィールmerge、履歴保存、sessionログ更新は既存業務コードを通す。

`FAIRIES_STORAGE_BACKEND=google_drive`、`GOOGLE_DRIVE_AUTH_MODE=user_oauth`、`GOOGLE_DRIVE_ROOT_FOLDER_ID=<Fairies_Testのfolder ID>` を必須とする。実行ごとにUUIDを含む `__fairies_api_drive_live_test_<uuid>__` を使用し、session IDは `POST /sessions` が新規生成した値だけを後続APIへ渡す。

`POST /sessions` は既存API仕様のHTTP 201、他3 APIはHTTP 200を確認する。chat後に空プロフィールが保存されていないこと、match後にプロフィールが空でなくsessionが `matched` であること、end後にsessionが `completed`、`end_reason=user_clicked_finish` であること、およびend処理がプロフィールを再更新していないことをDriveから再読込して確認する。

自動cleanupは行わない。実行後は表示されたtest user IDとtest session IDだけを使用し、`profiles/current/<test user ID>.json`、`profiles/history/<test user ID>/`、`sessions/<test session ID>/` をDrive UIから手動削除する。共有フォルダや他ユーザーのデータには触れない。

## 13. Flutterプロジェクト

Flutter clientはリポジトリ直下の `flutter_app/` に配置する。Dart package名は `fairies_app`、アプリ表示名は「フェアリーズ」とし、Androidを主要な開発ターゲットとする。

初期構成では `lib/main.dart` がアプリ起動とテーマ、`lib/screens/` が画面を担当する。API接続工程では必要になった時点で `config/`、`models/`、`services/`、状態管理、共通widgetを小さく追加し、WidgetへHTTP処理を直接集中させない。

### 13.1 Flutterからのセッション開始

Flutterの最初のAPI接続は `POST /sessions` だけを対象とする。`lib/config/api_config.dart` が `FAIRIES_API_BASE_URL` のdart-defineを読み、`lib/services/fairies_api_client.dart` がHTTP 201と共通エラーJSONを処理する。API URLやHTTP処理をWidgetへ直接記述しない。

`lib/models/` はAPIのsnake_case JSONとDartのcamelCaseプロパティを変換する。`lib/state/session_state.dart` は外部状態管理packageを使わず `ChangeNotifier` で `userId`、`sessionId`、Flutterが保持する `messages`、loading、API errorを管理する。成功時だけ初回assistant messageを会話履歴へ設定し、エラーは会話へ混ぜない。画面は開始、loading、初回挨拶、エラー、再試行を表示する。

AndroidエミュレータからローカルFastAPIへ接続する開発既定値は `http://10.0.2.2:8000` とする。クラウド接続時はコード変更を行わず、`--dart-define=FAIRIES_API_BASE_URL=<URL>` で切り替える。

### 13.2 Flutterからのチャット送信

Flutterの次のAPI接続は `POST /chat` だけを対象とする。Flutterが初回挨拶を含む `messages` 全体を保持し、送信時に `userId`、`sessionId` とともに送る。成功時はresponseのassistant messageだけを末尾へ追加する。

空白だけの入力、session開始前、通信中は送信しない。新しいuser messageは通信開始前に1回だけ追加し、通信失敗時も削除しない。APIエラーは `errorCode` と `errorMessage` で別管理し、会話履歴へ混ぜない。失敗後のretryはuser messageを追加せず、既存のmessages全体を再送する。retry完了までは新規送信を抑止し、成功時だけassistant messageを追加する。

画面は初回挨拶を含む会話履歴、roleで区別した簡易message表示、入力欄、送信、loading、APIエラー、retryを提供する。本格的なチャットデザイン、`POST /match`、session終了APIとの接続は後工程とする。

### 13.3 Flutterからのマッチング

Flutterは空でないuser messageが3件以上ある場合だけ `POST /match` を実行し、保持中の `userId`、`sessionId`、`messages` 全体を送る。分析、マッチ結果、上位候補、マッチ後支援、プロフィール更新結果は型付きの `MatchResponse` として会話履歴とは別に保持する。成功または失敗によってmessagesを変更せず、matching中の二重実行も抑止する。

画面は分析summary、候補者名・年齢、score・label・理由・懸念・推奨初回文、プロフィール更新結果を表示する。マッチ後支援がnullでも成功として扱い、`profile_updated=false` の場合もマッチ結果を破棄しない。APIエラーは会話へ混ぜず、再実行可能な状態で別表示する。session終了APIとの接続は後工程とする。

## 14. v0.2.2 完了条件

FlutterとFastAPIを使用して、以下の一連の流れを動作確認できることを完了条件とする。

```text
起動
  ↓
ログ保存への同意
  ↓
セッション開始
  ↓
Fairyとの会話
  ↓
人物分析
  ↓
マッチング
  ↓
Fairyプロフィール更新
  ↓
結果表示
  ↓
セッション終了
  ↓
アンケート
```

加えて、既存のStreamlit版が引き続き動作し、既存プロフィールを破損・消失させないことを確認する。
