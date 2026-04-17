# rich-deploy — 離線授權工具

本工具實作一套**私鑰永不離開開發機**的軟體授權流程。
整個流程透過 CLI 的複製貼上完成，不需要網路連線，不需要在甲方機器上放置任何秘密。

支援平台：**Windows · Linux · macOS**

---

## 快速使用

> 日常發授權只需要這三個步驟，不需要讀完整份文件。

### 前置：初始化金鑰（只做一次）

在**你的開發機**執行，產生 RSA 金鑰對：

```bash
poetry run python tools/generate_keys.py
```

---

### 每次發授權的流程

**① 甲方機器：取得指紋**

在甲方機器上執行（只需要 Python，無需安裝任何套件）：

```bash
python client/get_fingerprint.py
```

複製印出的 64 字元指紋，透過訊息或 email 傳給你自己。

---

**② 你的開發機：簽章產生授權檔**

```bash
# 永久授權
poetry run python tools/sign_license.py <貼上指紋>

# 限期授權（建議）
poetry run python tools/sign_license.py <貼上指紋> --expires 2027-12-31
```

複製印出的 JSON 內容，傳回給甲方。

---

**③ 甲方機器：存檔並啟動**

將收到的 JSON 存成 `license.lic`，設定環境變數後啟動程式：

```bash
# Linux / macOS
export NHAD_LICENSE_FILE=/path/to/license.lic

# Windows PowerShell
$env:NHAD_LICENSE_FILE = "C:\path\to\license.lic"
```

---

### 工具一覽

| 腳本 | 在哪執行 | 用途 |
|------|---------|------|
| `tools/generate_keys.py` | 開發機（只做一次） | 產生 RSA 金鑰對 |
| `client/get_fingerprint.py` | **甲方機器** | 採集硬體指紋，無需任何套件 |
| `tools/sign_license.py` | **開發機** | 用私鑰簽章，產生 `license.lic` |

---

## 目錄

1. [核心設計理念](#1-核心設計理念)
2. [密碼學原理](#2-密碼學原理)
3. [機器指紋：產生方式與依賴來源](#3-機器指紋產生方式與依賴來源)
4. [跨平台支援分析](#4-跨平台支援分析)
5. [虛擬機與容器環境的適用性](#5-虛擬機與容器環境的適用性)
6. [專案結構](#6-專案結構)
7. [環境需求與安裝](#7-環境需求與安裝)
8. [操作流程](#8-操作流程)
9. [授權驗證實作範例](#9-授權驗證實作範例)
10. [安全性總覽](#10-安全性總覽)
11. [常見問題](#11-常見問題)
12. [本機模擬練習](#12-本機模擬練習)

---

## 1. 核心設計理念

### 傳統做法的問題

傳統「帶私鑰到甲方」的做法有以下風險：

```
傳統做法（有問題）
─────────────────────────────────────────
開發機                      甲方機器
  │                            │
  ├─ private_key.pem ────────→ ├─ private_key.pem  ← 私鑰洩漏風險
  │                            ├─ get_fingerprint()
  │                            ├─ sign_license()
  │                            └─ license.lic
```

私鑰一旦傳出，就失去控制：甲方可以用它為任意機器偽造授權。

### 本工具的解法：職責分離

將「採集指紋」和「產生授權」拆成兩支獨立腳本，私鑰的計算全程留在開發機：

```
本工具做法（安全）
──────────────────────────────────────────────────────────────
甲方機器（無私鑰）                  你的開發機（私鑰永遠在這）
─────────────────────               ─────────────────────────
① 執行 get_fingerprint.py
  → 印出機器指紋字串

② 複製指紋
  傳給你（訊息/email）  ──────────→ ③ 執行 sign_license.py <指紋>
                                       → 印出 license.lic 的內容

                        ←────────── ④ 你複製 license.lic 內容
                                       傳回給甲方

⑤ 甲方存成 license.lic
   設定環境變數，啟動程式 ✓
```

傳輸過程中流動的只有**指紋**（公開安全）和 **JSON 授權檔**（偽造需要私鑰），兩者都不是秘密本身。

---

## 2. 密碼學原理

### 使用的算法

```
RSA-2048  +  PKCS#1 v1.5 padding  +  SHA-256 hash
```

| 元件 | 用途 |
|------|------|
| RSA-2048 | 非對稱加密，公鑰可驗證、私鑰才能簽章 |
| PKCS#1 v1.5 | 簽章填充方案，為 RSA 簽章的標準格式 |
| SHA-256 | 對簽章資料做雜湊，確保完整性 |

### 簽章流程（開發機端）

```
                    ┌─────────────────────────────────┐
                    │  payload = fingerprint           │
                    │  （若有到期日：                  │
                    │    payload = fp|expires:date）   │
                    └────────────┬────────────────────┘
                                 │
                          SHA-256 雜湊
                                 │
                          RSA 私鑰簽章
                                 │
                         Base64 編碼輸出
                                 │
                    ┌────────────▼────────────────────┐
                    │  license.lic（JSON）             │
                    │  {                               │
                    │    "fingerprint": "cd668...",    │
                    │    "signature":   "RcJz7...",    │
                    │    "expires":     "2027-12-31"   │
                    │  }                               │
                    └─────────────────────────────────┘
```

### 驗證流程（甲方機器端）

```
  讀取 license.lic
         │
         ├─→ 重新計算本機指紋 ──→ 比對 fingerprint 欄位是否吻合
         │
         └─→ Base64 解碼 signature
                   │
             RSA 公鑰驗簽（verify）
                   │
             ✓ 通過：fingerprint 確實由私鑰簽章，授權合法
             ✗ 失敗：簽章不符，授權無效或被竄改
```

### 為什麼指紋用明文存放？

`fingerprint` 欄位是明文，這是刻意的設計：

- 指紋本身是 SHA-256 雜湊，無法反推原始硬體資訊
- 驗證時需要比對「現場計算的指紋」與「授權檔的指紋」是否相同
- 真正的保護來自**簽章**，沒有私鑰就無法偽造一份通過驗證的授權

---

## 3. 機器指紋：產生方式與依賴來源

### 指紋產生流程

```python
# 虛擬碼，完整實作見 client/get_fingerprint.py

parts = []
parts.append(f"mac:{MAC 位址}")           # 所有平台
parts.append(f"wguid:{MachineGuid}")      # 僅 Windows
parts.append(f"mid:{machine-id}")         # 僅 Linux
parts.append(f"ioplatform:{PlatformUUID}")# 僅 macOS

raw = "|".join(sorted(parts))             # 排序後拼接，確保順序一致
fingerprint = sha256(raw).hexdigest()     # 64 個 hex 字元
```

`sorted()` 是關鍵：確保不論收集順序，相同的硬體資訊永遠產生相同的指紋。

### 各識別碼詳細說明

#### MAC 位址（`uuid.getnode()`）

- **來源**：網路介面卡的硬體位址
- **格式**：`mac:aabbccddeeff`（12 位 hex）
- **穩定性**：★★★☆☆
- **注意**：
  - 更換網卡、停用網卡、更改 MAC 位址（MAC spoofing）都會改變
  - 部分筆電每次開機會隨機化 Wi-Fi MAC（需確認 BIOS 設定）
  - 若 `uuid.getnode()` 回傳 `0` 或 `2^48-1`（無效值），腳本會忽略此項

#### Windows MachineGuid（`winreg`）

- **來源**：登錄機碼 `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography\MachineGuid`
- **格式**：`wguid:{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}`（UUID 格式）
- **穩定性**：★★★★☆
- **何時改變**：
  - 重新安裝 Windows（包含重設這台電腦）
  - 使用 `sysprep /generalize` 準備系統映像
  - 部分系統備份還原工具
- **何時不變**：一般 Windows Update、驅動程式更新、BIOS 更新

#### Linux machine-id（`/etc/machine-id`）

- **來源**：`/etc/machine-id` 或 `/var/lib/dbus/machine-id`
- **格式**：`mid:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`（32 位 hex）
- **穩定性**：★★★★☆
- **何時改變**：
  - 重新安裝 Linux
  - 手動執行 `systemd-machine-id-setup --commit`
  - 複製虛擬機映像（clone）後執行 `systemd-machine-id-setup`
- **何時不變**：一般 OS 升級、套件更新、核心更新

#### macOS IOPlatformUUID（`ioreg`）

- **來源**：`ioreg -rd1 -c IOPlatformExpertDevice` 輸出的 `IOPlatformUUID` 欄位
- **格式**：`ioplatform:XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`（UUID 格式）
- **穩定性**：★★★★★
- **何時改變**：
  - 更換主機板（邏輯板）
  - 全新安裝 macOS（erase install）
  - 少數機型在 Apple Silicon 重新啟用時
- **何時不變**：macOS 系統升級（Ventura → Sonoma 等）、重新啟動、軟體更新、Time Machine 還原

> IOPlatformUUID 是 macOS 上等同 Windows MachineGuid 的硬體識別碼，穩定性最高，是三個平台中唯一達到五星的識別碼。

### 指紋穩定性總結

| 操作 | MAC | MachineGuid（Win） | machine-id（Linux） | IOPlatformUUID（macOS） |
|------|-----|--------------------|---------------------|------------------------|
| 一般軟體 / OS 更新 | 不變 | 不變 | 不變 | 不變 |
| 重裝作業系統 | 不變 | **改變** | **改變** | **改變** |
| 更換網卡 | **改變** | 不變 | 不變 | 不變 |
| 修改 MAC 位址 | **改變** | 不變 | 不變 | 不變 |
| 重新啟動 | 不變 | 不變 | 不變 | 不變 |
| BIOS / 韌體更新 | 不變 | 不變 | 不變 | 不變 |
| 磁碟擴充 / 分割 | 不變 | 不變 | 不變 | 不變 |
| 更換主機板 | 可能改變 | **改變** | 不變 | **改變** |

---

## 4. 跨平台支援分析

### 支援矩陣

| 平台 | 可取得指紋 | 使用的識別碼 | 穩定性評估 |
|------|-----------|-------------|-----------|
| Windows 10/11 | ✅ | MAC + MachineGuid | 高 |
| Windows Server 2016+ | ✅ | MAC + MachineGuid | 高 |
| Ubuntu / Debian | ✅ | MAC + machine-id | 高 |
| CentOS / RHEL | ✅ | MAC + machine-id | 高 |
| Arch Linux | ✅ | MAC + machine-id | 高 |
| macOS 12 Monterey+ | ✅ | MAC + IOPlatformUUID | 高 |
| macOS 11 Big Sur | ✅ | MAC + IOPlatformUUID | 高 |
| WSL2 (Windows 內) | ⚠️ 部分 | MAC（虛擬）+ machine-id | 低（每次可能不同） |
| Alpine Linux | ✅ | MAC + machine-id | 高（需安裝 `util-linux`） |

### Python 版本相容性

| Python 版本 | 支援 | 備註 |
|-------------|------|------|
| 3.10 | ✅ | 最低支援版本 |
| 3.11 | ✅ | |
| 3.12 | ✅ | |
| 3.13 | ✅ | |
| 3.9 以下 | ❌ | `str \| None` 型別語法不支援 |

`get_fingerprint.py`（給甲方的版本）**只使用標準函式庫**，不需要安裝任何第三方套件。

---

## 5. 虛擬機與容器環境的適用性

### VMware / VirtualBox / Hyper-V 虛擬機

```
適用程度：⚠️ 有條件適用
```

虛擬機可以產生指紋，但需要注意以下行為：

| 情境 | 指紋是否穩定 |
|------|-------------|
| 正常開關機 | **穩定** |
| 快照還原（Snapshot Revert） | **改變**（machine-id 可能被還原至舊值） |
| 複製 VM（Clone） | **改變**（machine-id 相同，但 clone 後應重新生成） |
| 即時遷移（Live Migration） | **視設定而定**（MAC 若固定則不變） |
| 重新部署（Re-provision） | **改變** |

**建議做法：**
- 在 VMware / VirtualBox 設定中**固定 MAC 位址**（不要使用隨機產生）
- 避免對已授權的 VM 執行複製，若需複製應重新申請授權

### Docker 容器

```
適用程度：❌ 不建議用於容器本身
```

Docker 容器的識別碼極不穩定：

| 識別碼 | 容器內行為 |
|--------|-----------|
| MAC 位址 | 每次 `docker run` 預設隨機產生 |
| machine-id | 繼承自宿主機，或每次重建後不同 |
| 容器 ID | 每次重啟後改變 |

**結論：** 若你的程式跑在容器裡，授權應綁定**宿主機**而非容器：

```
正確做法：
  宿主機執行 get_fingerprint.py  →  取得宿主機指紋
  授權檔掛載進容器（volume mount）
  容器內程式讀取授權檔時，
    比對的是「宿主機指紋」而非容器自身的網路介面
```

若必須在容器內驗證，可改用固定 MAC 的方式啟動：

```bash
docker run --mac-address 02:42:ac:11:00:02 your-image
```

但這等同於由部署者自行設定指紋來源，安全性需另行評估。

### Kubernetes Pod

```
適用程度：❌ 不適用（Pod 是無狀態的）
```

Kubernetes Pod 本質上是可替換的無狀態單元，MAC 位址和 machine-id 每次調度都可能不同。
若需要在 K8s 環境授權，建議改用**節點（Node）層級的識別碼**或整合 K8s 的 Secret 機制。

### WSL2

```
適用程度：⚠️ 僅限開發測試
```

WSL2 是一個在 Hyper-V 虛擬機上跑的 Linux，其識別碼行為：

- `machine-id`：每次 WSL2 執行個體重建後可能改變
- MAC 位址：虛擬網路介面，重啟 WSL2 服務後可能改變

不建議將 WSL2 環境作為需要穩定授權的部署目標。

---

## 6. 專案結構

```
rich_deploy/
├── client/
│   └── get_fingerprint.py   ← 給甲方執行，不含任何秘密，可自由散布
├── tools/
│   ├── generate_keys.py     ← 一次性產生 RSA 金鑰對（只在開發機執行）
│   ├── sign_license.py      ← 簽章腳本（只在開發機執行）
│   ├── private_key.pem      ← 私鑰，已加入 .gitignore，絕不提交
│   └── public_key.pem       ← 公鑰，可隨程式一起發布
├── .gitignore
├── pyproject.toml
└── README.md
```

### 各腳本的依賴關係

```
get_fingerprint.py          sign_license.py         generate_keys.py
────────────────────        ──────────────────────  ────────────────────
標準函式庫只：              cryptography 套件：     cryptography 套件：
  hashlib                     asymmetric.padding      asymmetric.rsa
  platform                    hashes                  primitives.serialization
  uuid                        serialization
  winreg（Windows）
  pathlib
```

---

## 7. 環境需求與安裝

| 項目 | 版本 |
|------|------|
| Python | 3.10 以上 |
| Poetry | 最新版 |

### 安裝 Poetry（若尚未安裝）

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

### 安裝專案依賴

```bash
# 確認虛擬環境建在專案目錄內
poetry config virtualenvs.in-project true

# 安裝所有依賴
poetry install
```

---

## 8. 操作流程

### 第零步：初始化金鑰（只做一次）

> 僅在**你的開發機**上執行，甲方機器跳過此步驟。

```bash
poetry run python tools/generate_keys.py
```

輸出：

```
金鑰已生成：
  私鑰 → .../tools/private_key.pem
  公鑰 → .../tools/public_key.pem
警告：私鑰絕對不可提交至版本控制！
```

- `private_key.pem`：絕對保密，已加入 `.gitignore`
- `public_key.pem`：可隨你的應用程式一起發布，用於驗證授權

若私鑰已存在，腳本會自動跳過，不會覆蓋。

---

### 第一步：在甲方機器取得指紋

在**甲方機器**上執行（只需要 Python，不需要安裝 Poetry 或任何套件）：

```bash
python client/get_fingerprint.py
```

輸出範例：

```
============================================================
請複製以下指紋字串，傳給授權方：
============================================================
cd668926847b3b7f31545a26284a66c117ccbfb7080a1882779765a0e8761a9a
============================================================
```

將這串 64 個字元的指紋複製起來，透過任何方式（訊息、email）傳給你自己。

---

### 第二步：在開發機簽章，產生授權檔

在**你的開發機**上執行：

```bash
# 基本用法（永久授權）
poetry run python tools/sign_license.py <貼上指紋>

# 加上到期日
poetry run python tools/sign_license.py <貼上指紋> --expires 2027-12-31
```

實際範例：

```bash
poetry run python tools/sign_license.py cd668926847b3b7f31545a26284a66c117ccbfb7080a1882779765a0e8761a9a --expires 2027-12-31
```

輸出範例：

```
============================================================
請複製以下內容，在甲方機器上存成 license.lic：
============================================================
{
  "fingerprint": "cd668926847b3b7f31545a26284a66c117ccbfb7080a1882779765a0e8761a9a",
  "signature": "RcJz7VX8YbW/WQqAKGvk...(base64)...",
  "note": "此授權僅限本機使用",
  "expires": "2027-12-31"
}
============================================================
```

將 `{...}` 整段 JSON 複製起來，傳回給甲方。

---

### 第三步：甲方存檔並啟動

1. 新增純文字檔，命名為 `license.lic`，貼入 JSON 內容並儲存
2. 設定環境變數，告訴程式授權檔的位置：

   **Windows（PowerShell）**
   ```powershell
   $env:NHAD_LICENSE_FILE = "C:\path\to\license.lic"
   ```

   **Windows（命令提示字元）**
   ```cmd
   set NHAD_LICENSE_FILE=C:\path\to\license.lic
   ```

   **Linux / macOS**
   ```bash
   export NHAD_LICENSE_FILE=/path/to/license.lic
   ```

3. 啟動程式，驗證通過後即可正常使用。

---

## 9. 授權驗證實作範例

以下是你的應用程式端（甲方機器上執行）需要自行實作的驗證邏輯範例：

```python
# verify_license.py — 整合進你的應用程式
import base64
import json
import os
import sys
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# 公鑰直接嵌入程式碼，或從檔案讀取
_PUBLIC_KEY_PEM = (Path(__file__).parent / "public_key.pem").read_bytes()


def _current_fingerprint() -> str:
    """重新計算本機指紋（邏輯必須與 get_fingerprint.py 完全一致）。"""
    # ... 與 get_fingerprint.py 相同的邏輯 ...


def verify_license(license_path: str) -> bool:
    """Return True if the license is valid for this machine, False otherwise."""
    try:
        data = json.loads(Path(license_path).read_text())
        fingerprint = data["fingerprint"]
        signature   = base64.b64decode(data["signature"])
        expires     = data.get("expires")

        # ① 確認指紋符合本機
        if fingerprint != _current_fingerprint():
            return False

        # ② 確認尚未到期
        if expires and date.fromisoformat(expires) < date.today():
            return False

        # ③ 驗證簽章
        payload = fingerprint
        if expires:
            payload = f"{fingerprint}|expires:{expires}"

        public_key = load_pem_public_key(_PUBLIC_KEY_PEM)
        public_key.verify(signature, payload.encode(), PKCS1v15(), SHA256())

        return True

    except (InvalidSignature, KeyError, ValueError, FileNotFoundError):
        return False


if __name__ == "__main__":
    lic = os.environ.get("NHAD_LICENSE_FILE", "license.lic")
    if verify_license(lic):
        print("授權驗證通過 ✓")
    else:
        print("授權無效或已過期 ✗")
        sys.exit(1)
```

### 驗證三道關卡說明

```
關卡一：指紋比對
  現場計算 == license.lic 的 fingerprint？
  → 不符：此授權不屬於這台機器

關卡二：到期日
  今天 <= expires？（若有 expires 欄位）
  → 不符：授權已過期

關卡三：簽章驗證
  用公鑰驗證 signature 是否由私鑰簽出？
  → 不符：授權檔被竄改，或是偽造的
```

三關全過才算授權合法。攻擊者若修改 `fingerprint` 欄位，簽章驗證必然失敗；若修改 `expires`，簽章驗證同樣失敗（因為 payload 包含 expires）。

---

## 10. 安全性總覽

| 資產 | 位置 | 保護方式 |
|------|------|----------|
| `private_key.pem` | 開發機 `tools/` | `.gitignore` 排除，永不傳輸 |
| `public_key.pem` | 可公開散布 | 只能驗證，無法偽造簽章 |
| `license.lic` | 甲方機器 | 綁定硬體指紋，換機即失效 |
| 指紋字串 | 傳輸過程 | 單向雜湊，無法還原原始硬體資訊 |

### 攻擊向量分析

| 攻擊方式 | 是否有效 | 原因 |
|---------|---------|------|
| 複製 license.lic 到其他機器 | ❌ | 指紋不符，關卡一失敗 |
| 修改 license.lic 的 fingerprint | ❌ | 簽章驗證失敗，關卡三失敗 |
| 修改 license.lic 的 expires | ❌ | expires 包含在簽章 payload 中，關卡三失敗 |
| 偽造 license.lic（無私鑰） | ❌ | RSA-2048 無法在沒有私鑰的情況下偽造簽章 |
| 取得私鑰後偽造 | ✅ | 私鑰安全是整個系統的根本，需妥善保管 |
| MAC 位址偽造（MAC Spoofing） | ⚠️ | 可使指紋符合，但需同時知道 MachineGuid / machine-id / IOPlatformUUID |

### 已知限制

1. **無撤銷機制**：目前沒有 CRL（憑證撤銷列表）。若需要提前終止授權，只能更換金鑰對並要求甲方重新安裝。
2. **單向依賴標準函式庫**：指紋腳本設計為零依賴，但這也表示各作業系統採集到的欄位數量不同，穩定性略有差異。
3. **時鐘竄改**：到期日依賴系統時鐘，有心人可撥回時間繞過。若要強化，可在驗證時要求連線對時，但這會喪失離線特性。

---

## 11. 常見問題

### Q：指紋腳本在甲方機器上需要安裝什麼？

只需要 Python 3.10 以上，不需要安裝任何第三方套件。
`get_fingerprint.py` 只使用 Python 標準函式庫。

### Q：指紋會不會因重裝 Windows 而改變？

會。重灌系統後 MachineGuid 會重新產生，需要重新走一次授權流程。
一般的軟體更新、驅動程式安裝、BIOS 更新則不會改變。

### Q：私鑰不小心提交了怎麼辦？

立刻視為洩漏：
1. 執行 `generate_keys.py` 重新生成一組全新的金鑰對
2. 以 git 歷史清理工具（如 `git filter-repo`）移除含私鑰的 commit
3. 通知所有持有舊授權的甲方，重新走一次授權流程

### Q：可以同時授權多台機器嗎？

每台機器分別走一次完整流程，各自產生一份 `license.lic`，互不干擾。

### Q：`--expires` 日期格式？

ISO 8601 格式：`YYYY-MM-DD`，例如 `2027-12-31`。
驗證邏輯由你的應用程式讀取 `expires` 欄位實作（參考第 9 節的範例）。

### Q：Docker 容器裡可以用嗎？

不建議直接在容器內驗證，原因見第 5 節。
建議的做法是在宿主機取得指紋，將授權檔以 volume mount 的方式掛入容器。

### Q：macOS 支援嗎？

支援。`get_fingerprint.py` 會自動偵測 macOS（`platform.system() == "Darwin"`），
並透過 `ioreg` 指令取得 `IOPlatformUUID`，這是 macOS 上最穩定的硬體識別碼，
穩定性等同 Windows 的 MachineGuid，macOS 系統升級後不會改變。

```
指紋組成：mac:<位址> + ioplatform:<UUID>
採集方式：subprocess 執行 ioreg -rd1 -c IOPlatformExpertDevice
```

`ioreg` 是 macOS 內建指令，無需安裝任何額外軟體。

---

## 12. 本機模擬練習

> 在真正發授權給甲方前，先在自己的電腦上把整個流程走一遍。
> 你同時扮演「甲方機器」和「開發機」兩個角色，所有操作都在同一台機器完成。

### 情境說明

```
本機同時模擬兩個角色：

  [甲方機器角色]                    [開發機角色]
  client/get_fingerprint.py  ──→  tools/sign_license.py
        ↓ 複製指紋                       ↓ 複製 JSON
                          ←── license.lic 存在本機任意路徑
```

---

### 步驟一：確認金鑰存在

```bash
ls tools/private_key.pem tools/public_key.pem
```

若顯示「找不到檔案」，先執行一次金鑰初始化：

```bash
poetry run python tools/generate_keys.py
```

預期輸出：

```
金鑰已生成：
  私鑰 → ...\tools\private_key.pem
  公鑰 → ...\tools\public_key.pem
```

---

### 步驟二：扮演甲方，取得本機指紋

```bash
poetry run python client/get_fingerprint.py
```

預期輸出（你的指紋值會不同）：

```
============================================================
請複製以下指紋字串，傳給授權方：
============================================================
cd668926847b3b7f31545a26284a66c117ccbfb7080a1882779765a0e8761a9a
============================================================
```

把這串指紋複製起來，留在剪貼簿備用。

---

### 步驟三：扮演開發機，簽章產生授權檔

將剛才的指紋貼入下列指令（加上一個月後的到期日做測試）：

```bash
# Windows
poetry run python tools/sign_license.py <貼上你的指紋> --expires 2026-05-17

# 實際範例（請換成你自己的指紋）
poetry run python tools/sign_license.py cd668926847b3b7f31545a26284a66c117ccbfb7080a1882779765a0e8761a9a --expires 2026-05-17
```

預期輸出：

```
============================================================
請複製以下內容，在甲方機器上存成 license.lic：
============================================================
{
  "fingerprint": "cd668926847b3b7f31545a26284a66c117ccbfb7080a1882779765a0e8761a9a",
  "signature": "RcJz7VX8...(base64)...",
  "note": "此授權僅限本機使用",
  "expires": "2026-05-17"
}
============================================================
```

將 `{` 到 `}` 的整段 JSON 複製起來。

---

### 步驟四：扮演甲方，存成 license.lic

將 JSON 貼入新檔案並存檔：

```bash
# 在專案根目錄建立測試用的授權檔
# 直接把複製的 JSON 貼入你的編輯器，存成 license.lic
```

或用指令快速建立（Windows PowerShell）：

```powershell
@"
{
  "fingerprint": "貼上你的指紋",
  "signature": "貼上 signature 值",
  "note": "此授權僅限本機使用",
  "expires": "2026-05-17"
}
"@ | Out-File -Encoding utf8 license.lic
```

---

### 步驟五：執行驗證，確認授權合法

使用第 9 節的 `verify_license.py` 範例（需先建立該檔案），或直接用 Python 快速驗證：

```bash
# 設定環境變數指向剛才建立的授權檔
# Windows PowerShell
$env:NHAD_LICENSE_FILE = "license.lic"
poetry run python verify_license.py

# Linux / macOS
NHAD_LICENSE_FILE=license.lic poetry run python verify_license.py
```

預期輸出：

```
授權驗證通過 ✓
```

---

### 步驟六：測試錯誤情境（選做）

確認防護機制真的有效：

**情境 A：竄改指紋**

用文字編輯器打開 `license.lic`，把 `fingerprint` 最後幾個字元改掉，再執行驗證：

```
預期輸出：授權無效或已過期 ✗
原因：指紋不符本機（關卡一失敗）
```

**情境 B：竄改到期日**

把 `expires` 改成昨天的日期（例如 `"2026-04-16"`），再執行驗證：

```
預期輸出：授權無效或已過期 ✗
原因：到期日已過（關卡二失敗）
```

**情境 C：竄改 signature**

把 `signature` 的值改成任意字串，再執行驗證：

```
預期輸出：授權無效或已過期 ✗
原因：簽章不符（關卡三失敗）
```

---

### 練習完成後的清理

```bash
# 刪除測試用的授權檔
rm license.lic

# 取消環境變數（Windows PowerShell）
Remove-Item Env:NHAD_LICENSE_FILE

# 取消環境變數（Linux / macOS）
unset NHAD_LICENSE_FILE
```

---

### 練習流程速查

```
① poetry run python tools/generate_keys.py      ← 只做一次
② poetry run python client/get_fingerprint.py   ← 取得指紋
③ poetry run python tools/sign_license.py <指紋> --expires YYYY-MM-DD
                                                 ← 產生授權 JSON
④ 將 JSON 存成 license.lic
⑤ NHAD_LICENSE_FILE=license.lic poetry run python verify_license.py
                                                 ← 驗證通過即完成
```
