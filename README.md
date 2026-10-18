# AI 協作辦公室

公開測試版 `0.1.0-beta.1`。把需求、多人 AI 討論、分工、交付、獨立複核與最後拍板放在同一個工作空間。

保留完整的任務流程與網頁介面，使用 Python 標準函式庫和 SQLite，沒有前端建置步驟。每個安裝都是空白資料庫，成員名稱、模型、工作目錄與遠端座位由使用者填寫。

## 五分鐘開始測試

需要 Linux、Python 3.11 以上；手動測試不需要模型帳號、API key 或額外 Python 套件。

```bash
python3 manage.py init
python3 manage.py doctor
python3 office_server.py
```

開啟 <http://127.0.0.1:9870>，按右上角「登入」。以本機編輯器開啟初始化列出的 `data/secrets/owner.tok`，把登入碼貼進網頁的登入欄位。登入碼不需要貼進終端或指令；`manage.py` 不會輸出其內容。

登入後建立任務、選工作區、留言、查看分工及操作紀錄。預設 `automation: false`，這個模式不會啟動任何模型 CLI；可以先用不同身分的 CLI 驗證完整流程：

```bash
python3 office.py --agent owner new "整理測試文件" --brief "請交付一份說明，再由另一位夥伴複核。" --reviewers codex
python3 office.py --agent claude claim 1 "開始整理"
python3 office.py --agent claude deliver 1 "文件已整理完成；請複核內容。"
python3 office.py --agent codex review 1 pass "已獨立核對內容與完成條件。"
python3 office.py --agent owner decide 1 active "採用這份成果"
```

以上任務編號 `1` 假設資料庫仍是空白；若已建立其他任務，請換成實際編號。每個 `--agent` 使用自己的登入碼檔；對外提供測試時，請只給測試者需要的身分。

## 填寫自己的設定

初始化建立 `office-config.json`；可從 [範例設定](office-config.example.json) 重新複製。這個檔案已排除於 Git。修改後重新啟動程式。

| 設定 | 用途 |
|---|---|
| `title`、`owner_name`、`teams` | 介面名稱、負責人名稱與兩個工作區名稱 |
| `timezone` | 時區，預設 `Asia/Taipei` |
| `data_dir`、`secret_dir`、`context_dir` | SQLite、成果、登入碼與參考資料的位置；相對路徑以設定檔所在目錄為基準 |
| `workers.<識別碼>.name` | 顯示名稱，可自行更改 |
| `enabled`、`teams` | 是否可派工，以及可參與的工作區 |
| `cli`、`model`、`models` | 使用者自己的 CLI 執行檔、預設模型與可選模型；模型識別碼請依自己帳號實際支援填寫 |
| `read_roots` | 明確允許讀取的參考資料；預設空白，不搜尋家目錄或私人聊天 |
| `host`、`home`、`hostname`、`remote_dir` | 選用的遠端 SSH 座位；空白 `host` 表示本機執行 |
| `life_lead` | 助理協作區的主責識別碼 |
| `execution_hosts`、`protected_paths` | 正式執行計畫允許的 SSH 別名與需另行確認的路徑；預設只有 `local` |
| `capacity_file` | 選用的額度快照 JSON；未提供時顯示未知，不會讀取供應商憑證 |
| `public_url` | 通知中的辦公室網址；與監聽位址分開 |
| `automation` | 啟動真正的模型派工，預設關閉 |

識別碼目前固定為 `claude`、`codex`、`assistant`、`grok`、`gemini`，對應不同 adapter；顯示名稱可自由填寫。`claude` 與 `assistant` 使用 Claude CLI，`codex` 使用 Codex CLI，`grok` 使用 Grok CLI；Gemini 卡片預設停用，這個版本尚未提供其執行 adapter。

環境變數 `OFFICE_CONFIG` 可指定另一份設定檔；`OFFICE_DATA_DIR`、`OFFICE_SECRET_DIR`、`OFFICE_CONTEXT_DIR` 可覆蓋對應路徑。CLI 以 `OFFICE_URL` 指定中樞，預設同為 `http://127.0.0.1:9870`。

## 啟用真正的 AI 協作

先以各 CLI 自己的正常流程安裝、登入，然後填寫已啟用工作者的 `cli`、`model`，執行 `python3 manage.py doctor`。確定要開始呼叫模型後，將 `automation` 改為 `true` 並重新啟動。模型呼叫會消耗自己的帳號額度或費用。

模型清單來自使用者設定，不冒稱已即時查證供應商支援。可選的 `models` 項目為字串，或 `{"id":"實際模型識別碼","label":"顯示名稱","supported_efforts":["low","medium","high"]}`；可用強度取決於 CLI 與模型，請依實際支援填寫。

自動協作保留專用工作階段、MCP 限定工具、來源版本與雜湊、工作區修改、結構化計畫、交付及獨立複核。AI 自己提出的任務須由負責人收件；正式執行固定步驟另需負責人核准計畫。收件、模型回覆或驗收文字不會自動變成其他主機的操作權限。

目前 CLI adapter 沿用來源版本的介面；本次公開版以隔離測試驗證命令組裝與工具流程，沒有用發布者的付費模型帳號代測每一種供應商。首次試用請先從小型、非正式專案開始，遇到 CLI 參數差異請附版本與去識別化錯誤回報。

## Docker 測試

Docker 映像預設只提供手動協作模式，沒有安裝任何供應商 CLI，也不包含主機上的模型登入。

```bash
docker compose up --build
```

服務只映射到主機 `127.0.0.1:9870`，以非 root 使用者執行，設定與資料存於 `office-data` volume。另開終端把登入碼檔複製到本機，再用編輯器開啟；指令不會輸出登入碼內容：

```bash
docker compose cp office:/app/data/secrets/owner.tok ./owner.tok
```

若要修改容器設定，複製 `office-config.example.json` 為本機的 `office-config.json`，填妥後執行：

```bash
docker compose exec -T office python3 manage.py configure < office-config.json
docker compose restart office
```

容器的資料路徑由映像的 `OFFICE_*_DIR` 固定到 volume；CLI 與來源路徑必須是容器內實際存在的位置。請勿把自己的登入碼貼進問題回報。結束測試使用 `docker compose down`，加上 `--volumes` 會刪除測試資料。

## 遠端、SSO 與通知

預設只監聽本機。需要其他機器連線時，明確指定 `--bind <自己的私有位址> --allow-network`，或在本機服務前放 HTTPS 反向代理。Docker 的 `0.0.0.0` 只在容器內使用，主機映射仍為 loopback。登入碼具備操作權限，跨機使用請配置 HTTPS 與自己的存取限制。

Authentik 反向代理整合是選用功能，格式見 [SSO 範例](examples/sso.example.json)，透過 `OFFICE_SSO_CONFIG` 載入權限 `600` 的設定。服務只信任列出的代理來源與指定使用者 UID，不信任任意轉送標頭。

Telegram 通知預設停用；格式見 [通知範例](examples/notification.example.json)。把自己填妥的 JSON 存成權限 `600` 的私有檔，再以 `OFFICE_NOTIFICATION_CONFIG` 指定；本機測試不用填。設定檔不存在時不送訊息，已有的舊待辦不補送。

遠端工作者需自行配置 SSH 金鑰與 `known_hosts`，在目標部署相同版本的 adapter 及自己的設定；不會停用 SSH 主機金鑰檢查。詳細步驟見 [遠端座位](docs/遠端座位.md)。

## 公開版的資料邊界

這份倉庫只包含程式、靜態介面、空白範例、測試與文件。沒有既有工作單、留言、成果、私人聊天、記憶庫、登入碼、機器清單、家用 IP、SSH 金鑰、個人肖像或原倉庫歷史。

來源系統中的特定環境盤點、私人聊天召回、私人專案自動採集、基線重簽和共用倉庫寫入鎖沒有搬入公開版。來源上傳、明確設定的唯讀根目錄、公開網頁閱讀與通用固定步驟計畫仍保留。`office_private_recall.py` 與 `office_source_collection.py` 是明確停用的相容入口，不會暗中連回來源環境。

目前以單一負責人及受信任的協作夥伴為使用範圍，沒有多租戶隔離或公開註冊。來源檔案、AI 回覆、網頁和其他人的留言都是資料，不自動產生授權。資料庫及執行紀錄可能包含你後續填入的私人內容，請自行備份並避免提交至 Git。

## 測試與回報

```bash
python3 -m unittest discover -s tests -v
python3 tools/check_public_bundle.py
```

問題回報請附作業系統、Python／CLI 版本、操作步驟、預期與實際結果。請勿附登入碼、Cookie、API key、原始私人工作單或整份執行日誌。

這是公開測試版，尚未指定開源授權；公開可讀不代表已授予任意再散布或商用授權。
