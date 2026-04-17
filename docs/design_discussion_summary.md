# 設計討論彙整：硬體指紋授權系統

> 記錄從初版設計到最終架構的完整討論脈絡、決策理由與演進過程。

---

## 一、起點：為什麼不把私鑰帶去甲方

最初的問題是「如何授權甲方機器」。傳統做法是把私鑰複製過去，在甲方機器上直接簽章。

這個做法的根本缺陷：私鑰一旦傳出就失去控制，甲方可用它為任意機器偽造授權。

**解法：職責分離。** 把流程拆成兩支腳本：

```
get_fingerprint.py  → 只在甲方機器跑，採集硬體資訊，不含任何秘密
sign_license.py     → 只在開發機跑，用私鑰簽章，產生 license.lic
```

傳輸過程中流動的只有指紋（公開安全）和授權 JSON（沒有私鑰無法偽造）。

---

## 二、密碼學設計

### 算法選擇

```
RSA-2048 + PKCS#1 v1.5 + SHA-256
```

- **RSA-2048**：非對稱加密，公鑰可驗證、私鑰才能簽章
- **PKCS#1 v1.5**：標準填充方案，廣泛支援
- **SHA-256**：對簽章資料做雜湊，確保完整性

### 簽章 payload 的設計

```python
# 永久授權
payload = fingerprint

# 限期授權（expires 進入 payload，改了就簽章失效）
payload = f"{fingerprint}|expires:{expires}"
```

`expires` 被包入 payload 是刻意設計：攻擊者若竄改到期日，簽章驗證必然失敗。

### 指紋為何用明文存放

`fingerprint` 欄位是明文，這是刻意的。指紋本身是 SHA-256 雜湊，無法反推原始硬體資訊。
真正的保護來自簽章，沒有私鑰就無法偽造一份通過驗證的授權。

---

## 三、識別碼的選擇與演進

### 第一版：MAC + 系統 ID

最初的設計包含 MAC 位址作為組合識別碼之一。

```python
# 第一版指紋組成
parts = [mac, system_id]
fingerprint = sha256("|".join(sorted(parts)))
```

### 問題浮現：MAC 為何不適合

討論中發現 MAC 位址存在根本性的問題：

**穩定性問題（對合法用戶的傷害）：**
- Windows 10+ 的 Wi-Fi 隱私保護預設開啟 MAC 隨機化
- 換網卡、VM 重建網路介面、部分防火牆更換都會改變 MAC
- 任何一個合理的維運操作都可能觸發授權失效

**安全性問題（對攻擊者毫無阻力）：**
- Technitium MAC Address Changer 等免費工具可在 30 秒內更改 MAC
- MAC 位址本來就被 IEEE 設計為可軟體覆寫
- 攻擊者多複製一個值的邊際成本幾乎為零

這是一個**嚴重不對稱的壞交易**：
對攻擊者幾乎無阻礙，對合法用戶卻造成實際傷害。

### 加入 BIOS UUID 層

映像部署碰撞問題的討論引出了 BIOS UUID 的需求：
MachineGuid 和 machine-id 都是安裝時產生的軟體識別碼，
映像複製不執行 sysprep 會讓同批機器指紋完全相同。

BIOS UUID 的關鍵特性：**與 OS 映像完全無關，sysprep 不清除它**。

```python
# 第二版：加入 BIOS UUID
parts = [mac, system_id, bios_uuid]
fingerprint = sha256("|".join(sorted(parts)))
```

### 最終版：移除 MAC，保留雙層穩定識別碼

在充分討論並查閱業界文獻後，決策明確：

**MAC 位址不應參與核心指紋的計算。**

```python
# 最終版：僅用穩定識別碼
parts = [system_id, bios_uuid]   # MAC 完全移出
fingerprint = sha256("|".join(sorted(parts)))

# MAC 另外採集，作為 license.lic 的審計記錄
mac_hint = get_mac_hint()        # 存入 license.lic，不影響驗證
```

---

## 四、三種平台識別碼的選擇理由

### 識別碼優先順序

```
IOPlatformUUID  >  BIOS UUID  >  MachineGuid / machine-id  >  MAC（已移出核心）
```

### 各識別碼特性對比

| 識別碼 | 產生層級 | 修改難度 | 映像部署是否安全 | 平台 |
|--------|---------|---------|---------------|------|
| IOPlatformUUID | 硬體（SEP/NVRAM） | 極高（Apple Silicon 幾乎不可能） | 安全 | macOS |
| BIOS UUID | 韌體 | 高（需刷韌體工具） | 安全 | 全平台 |
| MachineGuid | OS 安裝層 | 低（需 admin，一行指令） | 不安全（需 sysprep） | Windows |
| machine-id | OS 安裝層 | 低（需 root，一行指令） | 不安全（需重設） | Linux |
| MAC 位址 | 網路介面邏輯層 | 極低（任何人，30 秒） | — | 全平台 |

### 為何各平台選這個識別碼

**Windows — MachineGuid**：
OS 安裝時由 `UuidCreate()` 產生的 Version 4 UUID（128 bits 隨機），
修改需要管理員權限，且需要知道目標值才能仿冒（SHA-256 屏障阻擋了反查）。

**Linux — machine-id**：
systemd 生態的標準機器識別碼，所有現代 Linux 均有，
存於 `/etc/machine-id`，需要 root 才能修改。

**macOS — IOPlatformUUID**：
Apple Silicon 的值由 Secure Enclave 的 UID 衍生，
UID 在 SoC 製造時燒斷 eFuse 寫入，軟體層完全無法修改。
是三個平台中唯一達到硬體層保護的識別碼。

---

## 五、平台兼容性分析

### 支援矩陣

| 平台 | 系統 ID | BIOS UUID | 指紋穩定性 |
|------|--------|-----------|-----------|
| Windows 10/11 | MachineGuid ✅ | WMI UUID ✅ | 高 |
| Linux (systemd) | machine-id ✅ | dmidecode ✅（需 root） | 高 |
| macOS Apple Silicon | IOPlatformUUID ✅ | Hardware UUID ✅ | 極高 |
| macOS Intel | IOPlatformUUID ✅ | Hardware UUID ✅ | 高 |

### 不建議的部署環境

| 環境 | 原因 |
|------|------|
| Docker 容器 | machine-id 繼承宿主機，BIOS UUID 無法讀取 |
| Kubernetes Pod | 無狀態設計，識別碼每次調度可能不同 |
| WSL2 | 每次重建執行個體識別碼可能不同 |

**容器環境的建議做法**：在宿主機取得指紋，授權檔以 volume mount 掛入容器。

---

## 六、映像部署碰撞問題

### 問題根本原因

MachineGuid 和 machine-id 是「安裝時一次性產生的隨機值」，
映像複製等於把同一份隨機值貼給所有機器。

Broadcom 企業 KB（KB264590）確認這是真實的生產問題：
> "If a machine is imaged without stripping its existing GUID, all machines
> restored from that image will share the same ID."

### 加入 BIOS UUID 後的改善

BIOS UUID 與 OS 映像完全無關，即使 sysprep 被省略，
每台機器的 BIOS UUID 也因主機板不同而不同（實體機）。

**仍需注意的場景**：VM clone 時，Hypervisor 也會複製虛擬 BIOS UUID，
VMware/VirtualBox 需手動重設，Hyper-V 會自動產生新的 GUID。

---

## 七、最終架構總覽

### 指紋計算

```
核心指紋（參與 SHA-256 計算）：
  Layer 1 — 系統 ID：MachineGuid / machine-id / IOPlatformUUID
  Layer 2 — BIOS UUID：WMI UUID / dmidecode system-uuid / Hardware UUID

  fingerprint = sha256(sorted([layer1, layer2]).join("|"))

輔助記錄（不參與計算）：
  MAC 位址 → 存入 license.lic 的 mac_hint 欄位，供人工審計
```

### 授權檔結構

```json
{
  "fingerprint": "3335b4a3...",        ← SHA-256(系統ID + BIOS UUID)
  "signature":   "V40EhXDF...",        ← RSA 私鑰簽章
  "note":        "客戶名稱",           ← 人工備注
  "expires":     "2027-12-31",         ← 到期日（進入簽章 payload）
  "mac_hint":    "dc:45:46:be:46:c4"  ← 審計記錄，不影響驗證
}
```

### 驗證三道關卡

```
關卡一：重新計算本機指紋 == license.lic 的 fingerprint？
  → 不符：此授權不屬於這台機器

關卡二：今天 <= expires？（若有到期日）
  → 不符：授權已過期

關卡三：用公鑰驗簽 signature 是否有效？
  → 不符：授權被竄改或偽造
```

---

## 八、安全性邊界說明

本系統的保護對象與保護極限：

| 攻擊類型 | 是否防護 | 說明 |
|---------|---------|------|
| 複製授權檔換機使用 | ✅ 有效 | 指紋不符直接失敗 |
| 從授權檔反推原始識別碼 | ✅ 有效 | SHA-256 單向，無法反推 |
| 修改授權檔竄改到期日 | ✅ 有效 | expires 在簽章 payload 中 |
| 偽造授權（無私鑰） | ✅ 有效 | RSA-2048 無法在無私鑰下偽造 |
| 物理接觸機器後複製識別碼 | ⚠️ 有限 | Windows/Linux 識別碼可被改寫 |
| 逆向程式碼繞過驗證邏輯 | ❌ 不防護 | 需搭配程式碼混淆或 TPM |
| 私鑰外洩後大量偽造 | ❌ 不防護 | 私鑰安全是整個系統的根本 |

**結論**：本系統覆蓋了 99% 的實際攻擊場景（被動仿冒與低技術主動仿冒）。
Level 3 以上的攻擊需要明確動機加技術能力，超出一般商業軟體授權的防護需求。
若需更高保護，應考慮 TPM 2.0 整合或硬體狗（Dongle）方案。
