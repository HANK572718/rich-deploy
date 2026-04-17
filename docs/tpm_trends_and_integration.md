# TPM 趨勢、與本系統的關係及未來整合方向

---

## 一、TPM 是什麼，為什麼現在這麼熱

### 基本概念

TPM（Trusted Platform Module）是一顆**獨立的安全晶片**，焊在主機板上或整合進 CPU 內部。
它有自己的處理器、記憶體、隨機數生成器，最關鍵的是：**有自己的金鑰儲存空間，且金鑰永遠無法被讀出晶片外**。

```
一般做法（本系統目前使用）：
  金鑰存在檔案系統 → 有 admin/root 就能讀走

TPM 的做法：
  金鑰存在晶片內部的保險箱 → 即使有 admin/root 也讀不出來
  只能叫 TPM「用這把金鑰做某件事」，然後拿回結果
  金鑰本身永不離開晶片
```

### 為什麼現在突然變得重要

**關鍵節點：Windows 11 強制要求 TPM 2.0（2021 年）**

Microsoft 官方說明（2025 年再次強調）：
> "TPM 2.0 is not just a recommendation — it's a necessity for maintaining
> a secure and future-proof IT environment with Windows 11."

這個決定把 TPM 從「進階安全功能」變成「普通電腦的標配」：

```
2016：TPM 2.0 成為 Windows 10 硬體認證的建議項目
2021：Windows 11 強制要求 TPM 2.0（買新電腦就有）
2025：Windows 10 停止支援，企業被推著升級到 Win11
2026：Microsoft 要求新 Windows Server 硬體也必須有 TPM 2.0
```

**結果**：2016 年後出廠的電腦幾乎全部有 TPM 2.0。
你的甲方機器，只要不是超過 8 年的老機器，大概率有 TPM。

---

## 二、TPM 的核心能力與授權相關的部分

TPM 提供很多功能，與本系統最相關的有三個：

### 能力一：Endorsement Key（EK）— 硬體唯一身份

```
每顆 TPM 在出廠時，製造商會：
  1. 在晶片內部生成一組 RSA/ECC 金鑰對（Endorsement Key）
  2. 用製造商的 CA 簽發一張憑證（EK Certificate），
     證明「這顆 TPM 是真實的，EK 公鑰是 XXXX」
  3. 把憑證燒進 TPM 的 NVRAM 裡

EK 的特性：
  - 私鑰永遠在晶片內，無法匯出
  - 公鑰可以讀出，用來識別這顆特定的 TPM
  - 製造商簽發的憑證可以驗證公鑰的真實性（非偽造）
```

**對授權系統的意義**：EK 公鑰雜湊可以作為機器識別碼，
且這個識別碼有製造商（Intel、AMD、Infineon 等）的背書，
無法用軟體偽造。

### 能力二：PCR（Platform Configuration Registers）— 啟動狀態測量

TPM 內有 24 個 PCR 暫存器，在每次開機時記錄啟動鏈的雜湊值：

```
PCR[0] = BIOS/UEFI 韌體的雜湊
PCR[4] = 開機管理程式（bootloader）的雜湊
PCR[7] = Secure Boot 狀態
PCR[11] = BitLocker 使用（Windows）
...
```

**對授權系統的潛在用途**：可以要求「只有在特定 Secure Boot 狀態下才解鎖授權」，
防止在被篡改的系統環境中使用。

### 能力三：Key Sealing — 把秘密鎖在特定環境

TPM 可以把任何資料（例如授權金鑰）「封存」，
讓它只在 PCR 值符合預期時才能「解封」：

```
封存時：
  TPM.Seal(data=授權金鑰, policy=PCR[0,7]的當前值)
  → 資料被加密，解密條件綁定在晶片裡

解封時：
  TPM.Unseal()
  → TPM 內部檢查當前 PCR 值是否符合封存時的條件
  → 符合：回傳資料
  → 不符合（系統被篡改）：拒絕
```

---

## 三、TPM vs 本系統目前的做法

### 直接對比

| 面向 | 本系統（目前） | 加入 TPM 後 |
|------|-------------|-----------|
| 識別碼來源 | 軟體層（MachineGuid、machine-id） | 硬體層（EK 公鑰，製造商背書） |
| 識別碼可否被偽造 | 可（需 admin/root） | 不可（金鑰在晶片內） |
| 需要在甲方機器安裝什麼 | 只需 Python | 需要 TPM 驅動 + tpm2-tools 或 tpm2-pytss |
| 實作複雜度 | 低 | 中到高 |
| 支援的機器 | 所有有 Python 的機器 | 2016 年後有 TPM 2.0 的機器 |
| 甲方機器需要 TPM | 否 | 是 |

### 保護等級的跳躍

```
目前的系統：
  攻擊者有 admin → 可以修改 MachineGuid → 仿冒成功
  攻擊者有 admin → 可以修改 machine-id → 仿冒成功

加入 TPM EK 後：
  攻擊者有 admin → 讀得到 EK 公鑰（但無法偽造）
  攻擊者有 root  → 讀得到 EK 公鑰（但無法偽造）
  攻擊者拆開主機板 → 仍然無法取出私鑰（需要摧毀晶片）
```

---

## 四、現有工具生態

### tpm2-pytss（Python 原生）

```
專案：https://github.com/tpm2-software/tpm2-pytss
PyPI：tpm2-pytss
最新版：2024 年 6 月更新
```

這是 Linux TPM2 Software Stack 的官方 Python 綁定，
OpenSecurityTraining2 在 2025 年有專門的 TPM 程式設計課程使用它。

**基本使用概念（讀取 EK 公鑰做機器識別）：**

```python
from tpm2_pytss import ESAPI, types

with ESAPI() as ectx:
    # 讀取 EK 公鑰
    ek_pub, _, _ = ectx.read_public(
        types.ESYS_TR.RH_ENDORSEMENT
    )
    # 序列化公鑰後做雜湊，作為機器識別碼
    ek_bytes = ek_pub.marshal()
    import hashlib
    ek_fingerprint = hashlib.sha256(ek_bytes).hexdigest()
```

**平台支援：**
- Linux：完整支援（需要 `tpm2-tss` 函式庫）
- Windows：需要 Windows TPM Base Services API，Python 綁定較不成熟
- macOS：Apple Silicon 的 Secure Enclave 不走標準 TPM 介面，不適用

### tpm2-tools（命令列工具）

```
專案：https://github.com/tpm2-software/tpm2-tools
```

比 Python 綁定更容易使用，適合腳本呼叫：

```bash
# 讀取 EK 公鑰
tpm2_readpublic -c 0x81010001 -o ek_pub.pem

# 讀取 EK 憑證（製造商簽發的）
tpm2_nvread 0x01c00002 -o ek_cert.der

# 驗證 EK 憑證鏈（確認 TPM 是真實的）
openssl verify -CAfile tpm_ca_bundle.pem ek_cert.pem
```

### Windows 原生 API（PowerShell）

Windows 提供原生的 TPM 管理介面，不需要安裝任何工具：

```powershell
# 取得 TPM 資訊
Get-Tpm

# 取得 EK 憑證指紋（間接方式）
$tpm = Get-WmiObject -Namespace "root\CIMV2\Security\MicrosoftTpm" -Class Win32_Tpm
$tpm.GetEndorsementKeyInfo(0x00)
```

---

## 五、與本系統整合的路線圖

### 路線一：EK 公鑰雜湊作為第三識別碼（漸進式加強）

在現有的雙層架構上，**選擇性**加入 TPM 識別碼：

```python
# 未來版本的指紋組成概念

parts = []

# Layer 1（現有）
parts.append(system_id)       # MachineGuid / machine-id / IOPlatformUUID

# Layer 2（現有）
parts.append(bios_uuid)       # BIOS/EFI UUID

# Layer 3（新增，可選）
tpm_id = _collect_tpm_ek()    # EK 公鑰雜湊
if tpm_id:
    parts.append(tpm_id)      # 有 TPM 就加，沒有就跳過

fingerprint = sha256(sorted(parts))
```

**設計原則**：TPM 層是「加分題」而非「必要條件」。
有 TPM 的機器得到更強的保護，沒有 TPM 的舊機器仍能正常授權。

### 路線二：TPM Key Sealing（進階，完全離線）

用 TPM 的封存功能把授權驗證邏輯本身鎖起來，
不在檔案系統上存放任何可讀的授權資料：

```
開發機生成授權時：
  用甲方 TPM 的 EK 公鑰加密授權金鑰
  → 只有那顆特定的 TPM 才能解密

甲方機器驗證時：
  TPM 解密授權金鑰
  程式讀取解密後的金鑰進行驗證
  授權金鑰永遠不以明文形式出現在磁碟上
```

這個方案的保護等級接近硬體狗（Dongle）。

### 路線三：遠端證明（Remote Attestation，需要網路）

讓甲方機器向你的伺服器「證明自己的硬體狀態」：

```
甲方機器                          你的授權伺服器
  │                                    │
  ├─ 向伺服器要求 nonce（隨機挑戰值）  │
  │  ←─────────────────────────────── │
  │                                    │
  ├─ TPM 用 EK 私鑰簽章 nonce         │
  ├─ 附上 PCR 值（啟動狀態測量）       │
  ├─ 傳給伺服器 ───────────────────→  │
  │                                    ├─ 驗證 EK 憑證（製造商背書）
  │                                    ├─ 驗證 PCR 值是否在白名單內
  │                                    ├─ 確認 nonce 正確（防重放攻擊）
  │  ←─────────────────────────────── ├─ 發放短期授權 token
  │                                    │
  ├─ 使用 token 解鎖功能               │
```

這是企業零信任架構（Zero Trust）的標準做法，
也是 Microsoft Intune + Azure Attestation 的實作方式。
但這需要網路連線，不符合本系統「純離線」的設計原則。

---

## 六、趨勢總結與對本系統的影響

### 不可逆的趨勢

```
1. TPM 普及化（已完成）
   2016 年後的電腦幾乎都有，Windows 11 強制要求確保了覆蓋率

2. 零信任（Zero Trust）成為企業標配
   TPM + 遠端證明 = 硬體層的身份驗證，不只靠帳號密碼

3. 遊戲防作弊整合（意外的推動力）
   Call of Duty 在 2025 年加入 TPM + Secure Boot 作為反作弊要求，
   加速了一般用戶對「為什麼我的電腦需要 TPM」的認知

4. 工業 / IoT 的 TPM 整合（Infineon OPTIGA TPM 2.0）
   工控場景開始採用帶開源軟體棧的 TPM 2.0 晶片
```

### 對本系統的實際建議

| 時間軸 | 行動 |
|--------|------|
| 現在（已完成） | BIOS UUID + 系統 ID 雙層架構，移除 MAC，已覆蓋 80% 場景 |
| 近期（可選） | 加入 TPM EK 雜湊作為選擇性第三層，僅在 Linux/Windows 上實作 |
| 未來（視需求） | 若甲方有高安全需求，評估 TPM Key Sealing 路線 |

### 不用急著整合 TPM 的理由

1. **現有設計已夠用**：對 99% 的攻擊場景有效防護
2. **TPM 整合有相容性代價**：舊機器沒有 TPM，會排除部分客戶
3. **`tpm2-pytss` 在 Windows 的支援仍不如 Linux 成熟**：跨平台複雜度增加
4. **甲方機器可能關閉 TPM 或未啟用**：企業管理政策不一，採集可能失敗

**結論**：TPM 是值得觀察的下一步，但在甲方環境普遍支援前不值得強制依賴。
維持「有 TPM 就加分、沒有 TPM 也能用」的選擇性整合是最務實的路線。

---

## 參考資源

| 資源 | 說明 |
|------|------|
| [tpm2-pytss GitHub](https://github.com/tpm2-software/tpm2-pytss) | Python TPM 2.0 綁定，官方維護 |
| [tpm2-pytss PyPI](https://pypi.org/project/tpm2-pytss/) | 安裝：`poetry add tpm2-pytss` |
| [OpenSecurityTraining2 TPM 課程](https://p.ost2.fyi/courses/course-v1:OpenSecurityTraining2+TC2202_tpm2-pytss+2025_v1/about) | 2025 年版 Python TPM 程式設計課程 |
| [smallstep: All About TPMs](https://smallstep.com/blog/trusted-platform-modules-tpms/) | 深入淺出的 TPM 技術說明 |
| [Microsoft TPM 基礎概念](https://learn.microsoft.com/en-us/windows/security/hardware-security/tpm/tpm-fundamentals) | Windows 官方 TPM 文件 |
| [Eric Chiang: TPM Key Hierarchy](https://ericchiang.github.io/post/tpm-keys/) | TPM 金鑰層級結構詳細說明 |
| [TCG TPM 2.0 Library Spec](https://trustedcomputinggroup.org/resource/tpm-library-specification/) | TPM 2.0 完整規格書 |
