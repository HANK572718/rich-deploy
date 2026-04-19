# Q&A：工作流程與資料儲存常見問題

---

## 工作流程篇

### Q1：我走完一次完整流程是指哪些步驟？

```
① [k] 為專案產生金鑰對
      → 產生 RSA-2048 私鑰 + 公鑰
      → 私鑰存到 projects/{專案}/keys/private_key_v1.pem
      → 公鑰 PEM 內容 + 指紋（SHA-256）存進 DB

② 在甲方機器執行 get_fingerprint.py
      → 採集本機 OS ID + BIOS UUID
      → 輸出 64 字元 hex 指紋字串

③ [l] 簽發授權
      → 貼上指紋、填入客戶名稱與到期日
      → 產生 license.lic（RSA 簽章）
      → 授權記錄存進 DB
      → 實體 .lic 檔存到 projects/{專案}/licenses/{客戶}.lic

④ [e] 匯出客戶端 SDK
      → 複製 client_sdk/ 到 dist/{專案}/
      → 自動將該專案公鑰嵌入 dist/{專案}/verify_license.py

⑤ 甲方機器驗證
      python verify_license.py /path/to/xxx.lic
      → 三道關卡：指紋比對 → 到期日 → RSA 簽章
      → 全通過才回傳 True
```

---

### Q2：匯出的 SDK 裡公鑰是怎麼來的？

匯出時從 DB 讀取該專案的 **當前使用中金鑰（最新未退役版本）** 的公鑰 PEM，
直接寫死進 `dist/{專案}/verify_license.py` 的 `PUBLIC_KEY_PEM` 常數。

甲方拿到的腳本已經「認識」該專案的公鑰，不需要另外傳遞公鑰檔案。

---

### Q3：一個專案一定只有一組金鑰嗎？

不一定，但**同時生效的只有最新的未退役版本**。

DB 的 `keys` table 支援多版本（`version` 欄位），用於金鑰輪換：
- 發現私鑰外洩 → 產生 v2 金鑰，v1 標記 `retired_at`
- 重新對所有現有客戶用 v2 簽發授權
- 匯出新 SDK 時自動帶入 v2 公鑰

---

### Q4：一個客戶等於一份 .lic 授權檔嗎？

通常是。設計上一份 license.lic 對應：
- 一台機器的指紋
- 一個專案的公鑰
- 一段有效期

同一客戶有多台機器 → 每台各取指紋、各簽一份 .lic。
授權可以永久或有期限，到期後重新簽發。

---

## 資料儲存篇

### Q5：資料庫（registry.db）裡存了什麼？

#### `projects` 表
| 欄位 | 說明 |
|------|------|
| id | 專案唯一 ID（如 `GIT_SmartSOPGuardian`） |
| display_name | 顯示名稱 |
| env_prefix | 環境變數前綴（如 `SSOPG`） |
| version | 軟體版本號 |
| fp_version | 指紋演算法版本（目前固定為 1） |
| validity_days | 預設授權天數 |
| created_at | 建立時間 |

#### `keys` 表
| 欄位 | 說明 |
|------|------|
| project_id | 所屬專案 |
| version | 金鑰版本號（從 1 開始遞增） |
| algorithm | `rsa2048` |
| **public_key_pem** | **公鑰完整 PEM 內容（存 DB）** |
| public_key_fp | 公鑰的 SHA-256 雜湊（快速比對用） |
| **private_key_path** | **私鑰的檔案路徑（只存路徑，不存內容）** |
| created_at | 建立時間 |
| retired_at | 退役時間（NULL = 仍在使用） |

#### `licenses` 表
| 欄位 | 說明 |
|------|------|
| project_id | 所屬專案 |
| client_name | 客戶名稱（人工備注） |
| machine_fp | 機器指紋（64 字元 hex） |
| fp_version | 使用的指紋演算法版本 |
| key_version | 使用的金鑰版本 |
| mac_hint | MAC 位址（審計用，不參與驗證） |
| issued_at | 簽發時間 |
| expires_at | 到期時間（NULL = 永久） |
| **license_json** | **完整 license.lic 的 JSON 內容** |
| lic_file_path | 實體 .lic 檔的路徑（可為 NULL） |
| revoked | 是否已撤銷 |
| revoked_at | 撤銷時間 |

---

### Q6：資料庫不存哪些東西？

| 不存的東西 | 原因 | 實際位置 |
|-----------|------|---------|
| **私鑰內容** | 安全原則，私鑰絕不離開檔案系統 | `projects/{id}/keys/private_key_v*.pem` |
| 匯出的 SDK 內容 | 每次匯出都重新生成，屬於建置產物 | `dist/{id}/`（.gitignore 排除） |

---

### Q7：DB 和實體檔案的關係是什麼？

```
DB = 定義層（唯一來源）
  Project / Key 元資料、License 台帳
  公鑰 PEM 內容在 DB 裡，是可靠的

實體檔案 = 副產物（可從 DB 重建，除了私鑰）
  public_key_v1.pem  → 可從 DB keys.public_key_pem 重建
  local_test.lic     → 可從 DB licenses.license_json 重建
  private_key_v1.pem → ⚠ 唯一無法從 DB 重建，必須獨立備份
```

**結論：私鑰是整個系統的根，遺失就必須重新產生金鑰、重新對所有客戶簽發授權。**

---

### Q8：如果 .lic 檔案不小心刪掉了，怎麼辦？

不用擔心。DB 的 `licenses.license_json` 欄位存有完整的 JSON 內容，
可以直接重建：

```bash
# 從 DB 撈出並還原 .lic 檔案
poetry run python -c "
import sys, json
sys.path.insert(0, '.')
from tools.db.engine import get_session
from tools.db.models import License
from sqlalchemy import select

with get_session() as s:
    lic = s.get(License, 1)  # 換成對應的 license id
    print(lic.license_json)
" > restored.lic
```

---

### Q9：目前 DB 的實際內容是什麼（截至建立當下）？

```
Projects: 1 筆
  GIT_SmartSOPGuardian  [SSOPG]

Keys: 1 筆
  GIT_SmartSOPGuardian v1  公鑰指紋: 47b201bab9a92fa6...

Licenses: 1 筆
  client: local_test
  machine_fp: 3335b4a38bfd260d...（本機開發機）
  lic_file: projects/GIT_SmartSOPGuardian/licenses/local_test.lic
```
