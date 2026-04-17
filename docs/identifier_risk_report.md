# 硬體識別碼唯一性與仿冒風險分析報告

---

## 摘要

本報告針對授權系統所使用的三種平台識別碼進行深入分析：

| 平台 | 識別碼 | 產生層級 | 仿冒難度 |
|------|--------|---------|---------|
| Windows | MachineGuid | 軟體層（安裝期） | 低（需 admin，但操作簡單） |
| Linux | machine-id | 軟體層（首次開機） | 低（需 root，一行指令） |
| macOS | IOPlatformUUID | 韌體層（出廠燒錄） | 高（需特殊工具，Apple Silicon 幾乎不可能） |

同時分析 MAC 位址作為輔助識別碼的實際風險，以及量產型主機重複碰撞的可能性。

---

## 一、各識別碼的唯一性來源

### 1.1 Windows — MachineGuid

**產生機制：**

Windows 在安裝過程中，`setup.exe` 呼叫 `UuidCreate()` API 產生一組 Version 4 UUID（隨機），
寫入登錄機碼：

```
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography\MachineGuid
```

**唯一性保證：**

UUID v4 由 122 bits 隨機數組成，碰撞機率為 $\frac{1}{2^{122}}$，約等於
$5.3 \times 10^{-37}$，在實際場景中視為絕對唯一。

**重要特性：**

- 這是一個**安裝時期的軟體 UUID**，與硬體本身無關
- 同一台硬體重裝 Windows 後會得到不同的 MachineGuid
- 反之，相同的 Ghost/映像檔部署到不同硬體，所有機器的 MachineGuid **完全相同**

---

### 1.2 Linux — machine-id

**產生機制：**

系統首次開機時，`systemd-machine-id-setup` 讀取以下來源（依優先順序）：

1. D-Bus 舊有 machine-id（`/var/lib/dbus/machine-id`）
2. `/proc/sys/kernel/random/boot_id`（開機時核心產生的隨機值）
3. 若皆不存在，使用 `getrandom()` 系統呼叫產生隨機 UUID

最終寫入 `/etc/machine-id`，格式為 32 位小寫 hex（128 bits）。

**唯一性保證：**

與 Windows MachineGuid 相同等級，128 bits 隨機數，碰撞機率極低。

**重要特性：**

- 同樣是**安裝時期的軟體識別碼**，與硬體無直接關聯
- Docker 容器若不特別處理，會繼承宿主機的 machine-id（所有容器相同）
- VM clone 後若不執行 `systemd-machine-id-setup`，所有 clone 的 machine-id 相同

---

### 1.3 macOS — IOPlatformUUID

**產生機制：**

IOPlatformUUID 的來源依機型而異：

```
Intel Mac：
  EFI 韌體中的 NVRAM 變數 (platform-uuid)
  由 Apple 在出廠時寫入，理論上與硬體序號連動

Apple Silicon (M1/M2/M3/M4)：
  Secure Enclave Processor (SEP) 內部產生並封存
  與晶片的唯一識別碼（ECID）綁定
  無法從作業系統層直接讀取或修改原始值，
  ioreg 回傳的是 SEP 導出的衍生值
```

**唯一性保證：**

- Intel Mac：出廠燒錄，Apple 負責確保不重複（類似序號管理）
- Apple Silicon：由 SEP 硬體保證，每顆晶片的 ECID 在製造時燒斷熔絲（eFuse），物理上不可改寫

**重要特性：**

- 這是三種識別碼中**唯一真正與硬體綁定**的識別碼
- macOS 系統升級、重裝系統（不換硬體）均不改變此值
- Intel Mac 的 NVRAM 理論上可被修改（見第三節）

---

## 二、MAC 位址：為何不應作為主要識別碼

### 2.1 MAC 位址的本質

MAC 位址（Media Access Control Address）是網路介面卡的**邏輯識別碼**，
由 48 bits 組成，前 24 bits 為廠商 OUI，後 24 bits 為裝置序號。

它**從未被設計為硬體唯一識別碼**，IEEE 標準允許軟體覆寫。

### 2.2 更改 MAC 位址有多容易

**Windows（不需要任何工具，5 秒完成）：**

```
裝置管理員 → 網路介面卡 → 內容 → 進階 → Network Address → 輸入任意值
```

或透過 PowerShell：

```powershell
Set-NetAdapter -Name "乙太網路" -MacAddress "AA-BB-CC-DD-EE-FF"
```

**Linux（一行指令）：**

```bash
ip link set eth0 address aa:bb:cc:dd:ee:ff
```

**macOS：**

```bash
sudo ifconfig en0 ether aa:bb:cc:dd:ee:ff
```

### 2.3 MAC 位址在現代環境的不穩定性

| 情境 | MAC 是否改變 |
|------|------------|
| 更換網卡 | 改變 |
| 重灌網卡驅動 | 可能改變 |
| Windows 隨機化 MAC（Wi-Fi 隱私保護） | 每次連線改變 |
| Linux NetworkManager 隨機化 | 每次開機改變（預設行為） |
| 虛擬機重建 | 通常改變 |
| 防火牆 / 網路設備更換 | 改變（若綁定的是閘道 MAC） |

### 2.4 結論：MAC 在本系統中的定位

本工具將 MAC 位址作為**輔助識別碼**，而非主要識別碼。
真正決定指紋穩定性的是 MachineGuid / machine-id / IOPlatformUUID。

MAC 的作用是增加攻擊者需要同時偽造的欄位數，稍微提高仿冒成本，
但不依賴 MAC 單獨提供安全保證。

---

## 三、仿冒攻擊的實際難度分析

### 3.1 攻擊場景：試圖在未授權機器上使用有效的 license.lic

攻擊者拿到一份合法的 `license.lic`，想在另一台機器上使用。
需要讓未授權機器的指紋 == 授權機器的指紋。

**需要同時偽造：**

```
Windows：mac:<值>  +  wguid:<值>
Linux：  mac:<值>  +  mid:<值>
macOS：  mac:<值>  +  ioplatform:<值>
```

---

### 3.2 Windows — MachineGuid 的仿冒難度

**難度：低**

MachineGuid 只是登錄機碼中的一個字串值，任何具有管理員權限的使用者都可以直接修改：

```powershell
# 以管理員身分執行 PowerShell
Set-ItemProperty `
  -Path "HKLM:\SOFTWARE\Microsoft\Cryptography" `
  -Name "MachineGuid" `
  -Value "目標機器的 GUID 值"
```

**門檻：**

- 需要管理員權限（一般企業用戶不一定有）
- 需要知道目標機器的 MachineGuid 值
- 修改後需要重新採集指紋確認

**實際評估：**

對於有動機、有技術的攻擊者而言，Windows MachineGuid 幾乎沒有防護力。
它的保護對象是「不懂技術、沒有動機深入鑽研的一般用戶」。

---

### 3.3 Linux — machine-id 的仿冒難度

**難度：低**

machine-id 是純文字檔，root 可以直接覆寫：

```bash
# 需要 root 權限
echo "目標機器的 machine-id 值" > /etc/machine-id
```

修改後立即生效，不需要重啟。

**門檻：**

- 需要 root 權限
- 需要知道目標機器的 machine-id 值

**實際評估：**

與 Windows 相同，Linux machine-id 對有 root 權限的攻擊者無法提供技術防護。

---

### 3.4 macOS — IOPlatformUUID 的仿冒難度

**難度：Intel Mac 中等、Apple Silicon 極高**

#### Intel Mac

IOPlatformUUID 儲存在 NVRAM 中，理論上可透過 EFI shell 修改：

```bash
# 需要關閉 SIP（系統完整性保護）
# 進入 Recovery Mode 後執行
nvram platform-uuid=<目標UUID>
```

但這個操作有顯著障礙：
1. 必須關閉 SIP（Secure Boot 的子功能），這本身需要進入 Recovery Mode
2. 關閉 SIP 會觸發系統警告，部分企業 MDM 政策會偵測並上報
3. 某些 Intel Mac 型號的 `platform-uuid` 由 SMC 控制，NVRAM 修改無效

#### Apple Silicon (M1/M2/M3/M4)

**幾乎不可能在不破壞硬體的情況下偽造。**

原因：

```
IOPlatformUUID 的產生鏈（Apple Silicon）：

  晶片製造時 → eFuse 燒斷寫入 ECID（唯一晶片 ID）
                      ↓
              Secure Enclave 在首次啟動時
              使用 ECID 衍生 IOPlatformUUID
                      ↓
              衍生結果封存於 SEP 內部
              作業系統只能透過 ioreg 讀取結果，
              無法從外部寫入或修改
```

eFuse 是物理上的一次性燒斷結構，無法電子反寫。
即使取得完整 root 權限，也無法修改 SEP 內部的封存值。

**唯一的「偽造」方式**：直接盜用目標機器（物理層面的攻擊）。

---

## 四、量產型主機的碰撞風險

### 4.1 使用相同映像檔部署的企業環境

這是**最常見的真實碰撞情境**，與演算法唯一性無關，而是部署流程的問題。

**情境：Ghost / Clonezilla / WDS 批次部署**

```
原始機器（Master）安裝 Windows，產生 MachineGuid = "AAAA-..."
↓
製作映像檔
↓
部署到 100 台機器

結果：所有 100 台的 MachineGuid = "AAAA-..."（完全相同）
```

**正確的企業部署流程應包含：**

```bash
# Windows：映像部署後執行 sysprep
sysprep /generalize /oobe /shutdown
# /generalize 會清除 MachineGuid，下次開機時重新產生
```

```bash
# Linux：映像部署後重新生成 machine-id
rm /etc/machine-id
systemd-machine-id-setup
# 或
dbus-uuidgen --ensure=/etc/machine-id
```

若甲方使用的是沒有執行 sysprep 的批次部署映像，
**同一批機器的指紋會完全相同**，授權一台等於授權全部。

---

### 4.2 相同硬體、正常個別安裝

若每台機器都是**獨立安裝**作業系統（即使硬體完全相同），
MachineGuid 和 machine-id 由亂數產生，碰撞機率為 $\frac{1}{2^{128}}$，
在宇宙尺度上可視為不可能。

---

### 4.3 OEM 出廠預裝的風險

部分 OEM 廠商（尤其是低成本大量出貨的製造商）有時會：

1. 使用同一套 Windows 映像部署後**未執行 sysprep**
2. 同批次機器的 MachineGuid 相同

這在廉價 Windows 平板、工業電腦領域有實際案例被回報。
若授權對象是此類設備，建議在拿到指紋後主動詢問甲方部署方式。

---

### 4.4 各平台量產碰撞風險摘要

| 平台 | 正常個別安裝 | 映像部署（未 sysprep） | OEM 批次出貨 |
|------|------------|----------------------|------------|
| Windows MachineGuid | 唯一 | **全部相同** | 可能相同 |
| Linux machine-id | 唯一 | **全部相同** | 取決於 OEM 流程 |
| macOS IOPlatformUUID | 唯一（出廠燒錄） | 唯一（與映像無關） | 唯一（Apple 控管） |

macOS 在這個面向表現最好：因為 IOPlatformUUID 是出廠時由 Apple 寫入韌體，
與作業系統映像完全無關，批次部署不影響其唯一性。

---

## 五、綜合風險評估

### 5.1 各識別碼防護強度總覽

```
防護強度（對有技術能力的攻擊者）

Windows MachineGuid  ████░░░░░░  40%
  └─ 修改門檻：需管理員 + 知道目標值 + 一行 PowerShell

Linux machine-id     ████░░░░░░  40%
  └─ 修改門檻：需 root + 知道目標值 + 一行指令

macOS (Intel)        ██████░░░░  60%
  └─ 修改門檻：需關閉 SIP + EFI shell 操作 + 部分型號無效

macOS (Apple Silicon)████████░░  90%
  └─ 修改門檻：eFuse 物理結構 + SEP 封存，無軟體途徑

MAC 位址             ██░░░░░░░░  20%
  └─ 修改門檻：一行指令，不需要特殊權限
```

### 5.2 本系統的真實保護對象

本授權系統對以下族群提供有效防護：

| 族群 | 防護效果 | 說明 |
|------|---------|------|
| 一般使用者（複製授權檔） | 有效 | 指紋不符，直接失敗 |
| 有基礎 IT 知識的使用者 | 有效 | 需要同時偽造多個識別碼 |
| 專業技術人員（有意繞過） | 有限 | Windows/Linux 識別碼可被修改 |
| 競爭對手逆向工程 | 無效 | 若他們有完整的逆向能力，識別碼保護不是主要障礙 |

### 5.3 與其他授權方案的比較

| 方案 | 仿冒難度 | 穩定性 | 離線支援 | 實作複雜度 |
|------|---------|-------|---------|----------|
| 本系統（MAC + 軟體ID） | 中 | 高 | 是 | 低 |
| TPM 晶片綁定 | 極高 | 極高 | 是 | 高 |
| 線上啟動碼（如 Office） | 高（需破解伺服器） | 中 | 否 | 中 |
| 純 MAC 位址綁定 | 極低 | 低 | 是 | 極低 |
| 僅序號（無硬體綁定） | 極低 | 高 | 是 | 極低 |
| USB 硬體狗（Dongle） | 極高 | 高 | 是 | 高 |

---

## 六、建議與結論

### 6.1 核心結論

1. **識別碼演算法層面的唯一性是夠的**：正常安裝情況下碰撞機率趨近於零。

2. **真正的風險不是演算法，而是部署流程**：映像複製不執行 sysprep/machine-id 重設，是量產環境唯一值得擔心的碰撞來源。

3. **Windows 和 Linux 的識別碼可被有技術能力的人修改**：這是設計上的本質限制，不是 bug。若業務場景需要更高防護，應考慮 TPM 或硬體狗。

4. **MAC 位址應降格為輔助角色**：不應作為授權穩定性的依賴，容易因網路變更導致誤失效。

5. **macOS Apple Silicon 是三平台中最難仿冒的**：IOPlatformUUID 由硬體層保證，是本系統最強的識別碼。

### 6.2 針對高風險場景的加固建議

**若甲方是使用映像部署的企業環境：**
- 授權前請甲方確認已執行 sysprep 或 machine-id 重設
- 或要求提供機器序號作為人工輔助核對

**若需要更高的防仿冒強度：**
- 將 `sign_license.py` 在簽章 payload 中加入額外的人工核對欄位（如合約編號）
- 考慮整合 TPM 2.0 的 `tpm2-tools` 讀取 EK（Endorsement Key）公鑰雜湊作為識別碼

**若甲方環境是純 macOS Apple Silicon：**
- IOPlatformUUID 已提供接近硬體狗等級的保護，目前方案已足夠
