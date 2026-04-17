# 映像部署碰撞問題、仿冒防護與識別碼權重設計

---

## 一、映像部署為何會造成全批碰撞

### 1.1 問題的根本原因

MachineGuid 和 machine-id 都是**安裝時期一次性產生的隨機值**。
它們的唯一性前提是：**每台機器都經歷了一次獨立的安裝流程**。

當企業用映像部署（Ghost、Clonezilla、WDS、Ansible、PXE boot 等），
實際上是把同一份磁碟狀態複製到多台機器，這個前提就被打破了：

```
正常安裝流程（唯一）：

  機器 A  →  安裝 Windows  →  產生 MachineGuid = "1111-AAAA"
  機器 B  →  安裝 Windows  →  產生 MachineGuid = "2222-BBBB"
  機器 C  →  安裝 Windows  →  產生 MachineGuid = "3333-CCCC"


映像部署流程（碰撞）：

  原始機器  →  安裝 Windows  →  MachineGuid = "1111-AAAA"
                ↓
           製作映像檔（此時 MachineGuid 已固化在映像裡）
                ↓
  機器 A  →  套用映像  →  MachineGuid = "1111-AAAA"  ← 相同
  機器 B  →  套用映像  →  MachineGuid = "1111-AAAA"  ← 相同
  機器 C  →  套用映像  →  MachineGuid = "1111-AAAA"  ← 相同
```

### 1.2 實際影響有多嚴重

這不是邊緣案例，而是企業環境的常態：

| 部署場景 | 是否會碰撞 | 現實頻率 |
|---------|----------|---------|
| 工廠產線工控機（批次 Ghost） | 碰撞 | 極常見 |
| 企業 IT 部門 WDS/MDT 部署 | 碰撞（若無 sysprep） | 常見 |
| 雲端 VM 範本複製 | 碰撞（若無重設步驟） | 常見 |
| PXE 無人值守安裝（kickstart/preseed） | **不碰撞** | 每台獨立安裝 |
| 個人零售版 Windows 自行安裝 | **不碰撞** | 每台獨立安裝 |
| macOS（任何部署方式） | **不碰撞** | IOPlatformUUID 與映像無關 |

---

## 二、sysprep 的機制與為何常被忽略

### 2.1 sysprep 做了什麼

`sysprep /generalize` 會在封存映像前執行以下清除動作（與本系統相關的部分）：

```
清除項目：
  ✓  刪除 MachineGuid（下次開機重新產生）
  ✓  清除 SID（Security Identifier）
  ✓  清除啟動紀錄、事件日誌
  ✓  重設網路設定

不清除項目：
  ✗  磁碟序號（不受 sysprep 影響）
  ✗  BIOS/UEFI 序號
  ✗  TPM EK（Endorsement Key）
```

### 2.2 為何常被跳過

```
1. 流程繁瑣：sysprep 後機器無法直接使用，需要再走一次 OOBE（開箱體驗）
2. 工廠圖省事：部分 OEM 代工廠對軟體部署品質無要求
3. 工控/嵌入式場景：機器出廠後通常不對外連網，IT 人員認為無所謂
4. Linux 更少人知道：machine-id 重設不像 sysprep 是有名的 SOP，
   許多 Linux 管理員根本不知道這個問題
```

### 2.3 Linux 映像部署的 machine-id 問題

Linux 的情況比 Windows 更容易被忽略：

```bash
# 問題情境：用 dd 或 rsync 複製系統到多台機器
dd if=/dev/sda of=/dev/sdb        # 直接複製磁碟
# 結果：/etc/machine-id 的內容被完整複製，所有機器相同

# 正確做法：部署後立即執行
rm -f /etc/machine-id
systemd-machine-id-setup          # 重新產生唯一值
```

部分 cloud-init 工具（如 AWS、GCP 的 cloud-init）在 VM 首次啟動時會自動處理這個問題，
但裸機部署或自製映像通常不包含此步驟。

---

## 三、當前做法能克服仿冒嗎

### 3.1 兩種截然不同的攻擊模型

在回答「能不能克服仿冒」之前，必須先區分攻擊者的類型：

```
攻擊模型 A：被動仿冒（拿到 license.lic 後想在別的機器用）
攻擊模型 B：主動仿冒（攻擊者刻意研究後想偽造指紋）
```

這兩種的答案完全不同。

---

### 3.2 被動仿冒：當前做法的防護效果

**情境：甲方員工離職，把 license.lic 帶走，想在家裡電腦使用**

```
家裡電腦執行驗證：
  步驟一：計算本機指紋
    → 本機 MachineGuid = "9999-ZZZZ"（與授權機器不同）
    → 指紋 = sha256("mac:xxxx|wguid:9999-ZZZZ") = "ffff..."

  步驟二：比對 license.lic 的 fingerprint = "cd66..."
    → "ffff..." ≠ "cd66..."
    → 關卡一直接擋下，驗證失敗
```

**結論：對被動仿冒，防護完全有效。**

---

### 3.3 主動仿冒：當前做法的極限

**情境：攻擊者知道 MachineGuid 可以被改，刻意模仿授權機器的識別碼**

攻擊者需要的資訊：
1. 目標機器的 MachineGuid（從 `license.lic` 的 fingerprint 反查不了，因為是 SHA-256 單向雜湊）
2. 目標機器的 MAC 位址（同樣無法從指紋反查）

這裡有個關鍵的**資訊屏障**：

```
license.lic 只包含：
  "fingerprint": "cd668926847b3b7f31545a26284a66c117ccbfb7080a1882779765a0e8761a9a"

這是 sha256("mac:aabbccddeeff|wguid:XXXX-...") 的結果。

攻擊者拿到 fingerprint 字串，無法反推出：
  - 實際的 MAC 位址是什麼
  - 實際的 MachineGuid 是什麼

因為 SHA-256 是單向函數，暴力破解 2^128 種組合不可行。
```

**攻擊者唯一可行的方法：直接存取目標授權機器**，用眼睛看或用指令查出原始值，再複製到攻擊機器。

```
# 攻擊者在授權機器上執行
reg query "HKLM\SOFTWARE\Microsoft\Cryptography" /v MachineGuid
ipconfig /all | findstr "Physical Address"

# 然後在攻擊機器上執行
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name "MachineGuid" -Value "查到的值"
Set-NetAdapter -Name "乙太網路" -MacAddress "查到的值"
```

**這意味著：若攻擊者已經能物理存取授權機器，授權本身的意義已大幅削弱。**

---

### 3.4 仿冒攻擊成本分析

```
攻擊成本（由低到高）

Level 1：複製 license.lic 換機使用
  成本：幾乎零（複製貼上）
  當前防護：完全有效 ✓

Level 2：知道識別碼可以改，但不知道目標值
  成本：需要接觸授權機器 + 具備基礎 IT 知識
  當前防護：SHA-256 屏障，無法從指紋反推原始值 ✓

Level 3：已接觸授權機器，查出原始識別碼，手動複製
  成本：需要實體接觸 + admin/root 權限 + 10 分鐘
  當前防護：Windows/Linux 無法阻擋，macOS Apple Silicon 可阻擋 ✗/△

Level 4：逆向工程驗證邏輯，修改程式碼繞過驗證
  成本：需要逆向能力 + 原始碼或反組譯分析
  當前防護：授權系統本身無法防止，需搭配程式碼混淆 ✗
```

**Level 1 和 Level 2 是本系統完全覆蓋的範圍，也是 99% 的實際攻擊場景。**
Level 3 以上需要攻擊者具備特定技術能力且有明確動機，一般商業軟體授權不需要防到這個程度。

---

## 四、識別碼的參考排序與權重設計

### 4.1 為何需要明確的優先順序

當多個識別碼同時存在時，任何一個改變都會改變指紋，導致授權失效。
因此需要定義：**哪些識別碼是必要的、哪些是輔助的、哪些應該排除。**

### 4.2 各識別碼的穩定性與仿冒難度評分

```
評估維度：
  穩定性  = 日常使用中不會意外改變的程度（高分 = 越穩定）
  仿冒難度 = 攻擊者複製此值的難度（高分 = 越難仿冒）
  唯一性  = 在量產/映像部署情境下保持唯一的能力（高分 = 越可靠）

                    穩定性   仿冒難度   唯一性（含量產）
  IOPlatformUUID     ★★★★★    ★★★★☆      ★★★★★
  MachineGuid        ★★★★☆    ★★☆☆☆      ★★★☆☆  ← 映像部署風險
  machine-id         ★★★★☆    ★★☆☆☆      ★★★☆☆  ← 映像部署風險
  MAC 位址           ★★☆☆☆    ★☆☆☆☆      ★★★★☆
  BIOS/UEFI 序號     ★★★★★    ★★★☆☆      ★★★★★  （目前未採集）
  磁碟序號           ★★★★☆    ★★★☆☆      ★★★★☆  （目前未採集）
  CPU ID             ★★★★★    ★★★☆☆      ★★★★★  （目前未採集）
```

### 4.3 建議的識別碼採用順序

```
第一優先（主識別碼）：平台專屬的系統級 ID
───────────────────────────────────────────
  Windows：MachineGuid
    理由：是 Windows 上除 TPM 外最標準的唯一識別碼，
          普遍存在，修改需要 admin 且需知道目標值

  Linux：machine-id
    理由：systemd 生態系的標準識別碼，所有現代 Linux 均有，
          單一穩定的真實來源

  macOS：IOPlatformUUID
    理由：出廠燒錄，韌體層保證，是三者中最強的識別碼


第二優先（強化識別碼）：補充主識別碼的獨立來源
───────────────────────────────────────────────
  BIOS/UEFI 序號（所有平台）
    來源：dmidecode（Linux）/ WMI（Windows）/ system_profiler（macOS）
    理由：與作業系統映像無關，即使 sysprep 也不影響，
          比 MachineGuid 更接近硬體層

    # Windows
    Get-WmiObject Win32_BIOS | Select-Object SerialNumber

    # Linux（需 root）
    dmidecode -s system-uuid

    # macOS
    system_profiler SPHardwareDataType | grep "Hardware UUID"


第三優先（輔助識別碼）：增加攻擊者需同時偽造的欄位數
───────────────────────────────────────────────────────
  MAC 位址
    理由：雖然容易改，但攻擊者仍需要知道正確值才能仿冒，
          搭配主識別碼使用可提高攻擊成本，
          但絕對不能單獨使用


不建議採用：
───────────
  CPU ID（CPUID 指令）
    原因：現代 CPU 的 CPUID 不包含唯一序號（Intel 在 Pentium III 後
          移除了序號欄位，因隱私爭議），回傳的是型號資訊而非唯一ID

  硬碟序號
    原因：換硬碟（包含 SSD 損壞更換）即失效，對企業用戶不友善
```

### 4.4 指紋組合的實際建議

```
最低保障（當前實作）：
  主識別碼 + MAC
  → 覆蓋 Level 1、Level 2 攻擊
  → 適合一般商業軟體授權

加強版（建議加入）：
  主識別碼 + BIOS 序號 + MAC
  → 額外克服映像部署碰撞問題
    （BIOS 序號不受 sysprep 影響）
  → 攻擊者需同時查出並複製三個值

高安全版（若需要）：
  主識別碼 + BIOS 序號 + TPM EK 公鑰雜湊
  → Level 3 攻擊成本大幅提升
  → 需要甲方機器有 TPM 2.0 晶片（2016 年後的機器幾乎都有）
```

---

## 五、針對映像部署碰撞的具體克服方案

### 5.1 方案一：授權前確認步驟（低成本）

在發授權前，要求甲方提供額外資訊作為人工核對：

```
發授權前確認清單：
  □ 機器的作業系統是獨立安裝還是映像部署？
  □ 若映像部署，是否有執行 sysprep / machine-id 重設？
  □ 提供機器型號與序號（肉眼比對，確認不是同一台機器的複本）
```

### 5.2 方案二：在指紋中加入 BIOS 序號（中成本）

BIOS/UEFI 序號是目前最容易採集且與映像完全無關的硬體識別碼，
可以直接在 `get_fingerprint.py` 中加入：

```python
# Windows 版本
import subprocess
result = subprocess.run(
    ["powershell", "-Command",
     "(Get-WmiObject Win32_BIOS).SerialNumber"],
    capture_output=True, text=True
)
bios_sn = result.stdout.strip()
if bios_sn and bios_sn not in ("", "To Be Filled By O.E.M.", "Default string"):
    parts.append(f"bios:{bios_sn}")

# Linux 版本（需要 root 權限執行 dmidecode）
result = subprocess.run(
    ["dmidecode", "-s", "system-uuid"],
    capture_output=True, text=True
)
system_uuid = result.stdout.strip()
if system_uuid:
    parts.append(f"sysuuid:{system_uuid}")
```

**注意：** 部分廉價主機板的 BIOS 序號是 `"To Be Filled By O.E.M."` 或空白，
採集前需過濾這些無效值（程式碼中已示範）。

### 5.3 方案三：指紋採集後人工備查欄位

在 `sign_license.py` 中加入一個非驗證用的備查欄位，
讓你自己記錄是哪台機器、哪個客戶：

```json
{
  "fingerprint": "cd668...",
  "signature": "RcJz7...",
  "note": "此授權僅限本機使用",
  "expires": "2027-12-31",
  "meta": "客戶：台灣某某公司 / 機器：辦公室主機 / 日期：2026-04-17"
}
```

`meta` 欄位不參與簽章 payload，僅供人工核對，
但也因此攻擊者可以任意修改此欄位（不影響安全性）。

---

## 六、結論

### 映像部署碰撞問題

| 問題 | 能否克服 | 方式 |
|------|---------|------|
| 同批映像 MachineGuid 相同 | 部分克服 | 加入 BIOS 序號作為第二主識別碼 |
| Linux clone 未重設 machine-id | 部分克服 | 同上，加入 dmidecode system-uuid |
| macOS 映像部署碰撞 | 天然免疫 | IOPlatformUUID 與映像無關 |
| OEM 廠商未做 sysprep | 人工克服 | 授權前確認部署方式 |

### 主動仿冒問題

| 攻擊等級 | 當前做法 | 加強版（含 BIOS 序號） |
|---------|---------|----------------------|
| 複製授權檔換機 | 完全防護 | 完全防護 |
| 知道可改但不知目標值 | SHA-256 屏障有效 | SHA-256 屏障有效 |
| 物理接觸授權機器後仿冒 | Windows/Linux 無法防 | 難度提升（多一個值要複製）|
| 逆向程式碼繞過 | 授權系統本身無法防 | 授權系統本身無法防 |

### 識別碼排序建議

```
優先順序：IOPlatformUUID > BIOS序號 > MachineGuid/machine-id > MAC位址

當前實作已正確使用主識別碼，建議下一步是加入 BIOS 序號
作為對映像部署碰撞的補強，成本低且效果直接。
```
