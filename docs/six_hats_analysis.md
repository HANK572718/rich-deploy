# 六頂思考帽：硬體指紋識別碼設計決策分析

> 本文件記錄「移除 MAC 位址出核心指紋、保留 BIOS UUID + 系統 ID 雙層架構」
> 這個決策的六頂思考帽論證，以及支持該決策的外部文獻證據。

---

## 白帽（White Hat）— 客觀事實與數據

### MAC 位址的本質限制已被業界文獻明確記載

**10Duke 技術部落格**明確指出：
> "The MAC address can change when a user upgrades their network hardware or if MAC spoofing is used."

**NetLicensing Wiki** 的機器指紋生成指引：
> "The MAC address is a commonly used fingerprint, but please note that **it can change**."

**Broadcom/Symantec 企業知識庫**（KB264590）確認映像部署碰撞問題：
> "If a machine is imaged without stripping its existing GUID (e.g., failing to run sysprep), **all machines restored from that image will share the same ID**."

### BIOS UUID 與系統 ID 的穩定性被業界採用

**NetLicensing** 建議的識別碼優先順序：
> "Motherboard serial numbers and BIOS UUIDs change rarely, making them reliable for licensing software or asset tracking."

**Keygen.sh**（主流授權服務商）的做法：
> "Keys can be signed with a 2048-bit RSA private key... for offline scenarios the private key is stored securely, while clients use the public key to validate offline."

### Apple Secure Enclave 的硬體唯一性獲 Apple 官方確認

**Apple Platform Security Guide（2026 年版）**：
> "The Secure Enclave includes a unique ID (UID) root cryptographic key that is unique to each individual device...
> A randomly generated UID is **fused into the SoC at manufacturing time**...
> This process protects the UID from being visible outside the device during manufacturing and therefore **isn't available for access or storage by Apple or any of its suppliers**."

---

## 紅帽（Red Hat）— 直覺與感受

**MAC 位址用作授權識別碼，從直覺上就感覺不對。**

MAC 位址是 OSI 模型第二層（資料連結層）的封包定址機制，
它的設計目的是讓封包知道要送到哪個介面，而不是用來證明「這台機器是誰」。

把網路位址當成身份證，就像用一個人的電話號碼當作護照號碼，
號碼可以換、可以攜號轉移，用來綁定身份天然不穩定。

授權失效打電話來的甲方工程師，他第一個懷疑的不是「我們換了網卡」，
而是「你們的授權系統壞了」。這個使用者體驗的代價遠大於 MAC 帶來的安全邊際效益。

---

## 黑帽（Black Hat）— 風險與問題

### 風險一：MAC 位址仿冒工具唾手可得

**Technitium MAC Address Changer** 是一個免費的 Windows 工具，
任何人都可以下載並在 30 秒內更改 MAC 位址，不需要任何技術背景。

**Wikipedia MAC Spoofing 條目**確認：
> "MAC spoofing enables hackers to get around security measures like MAC filters,
> and in reality, **MAC whitelists offer very little protection**."

若攻擊者能拿到合法機器的 MAC 值（只需要 `ipconfig /all`），
加上 MachineGuid（`reg query`），即可在 5 分鐘內仿冒完整指紋。
MAC 在此情境中毫無貢獻，只是多了一個需要複製的值。

### 風險二：合法使用者的授權誤失效

現代作業系統的 MAC 隨機化導致合法授權意外失效：

- **Windows 10+**：Wi-Fi 隱私設定預設開啟 MAC 隨機化
- **企業環境**：更換防火牆、更換交換器有時會觸發網卡重置
- **虛擬機**：重建網路介面是常見維運操作

**對攻擊者**：需要多複製一個可以用免費工具 5 秒改掉的值（幾乎無代價）
**對合法用戶**：合理的維運操作導致授權斷線（直接代價）

這是一個嚴重不對稱的壞交易。

### 風險三：映像部署的 MachineGuid 碰撞已被企業 IT 廣泛回報

FOG Project 論壇、Experts Exchange、Broadcom KB 均有大量真實案例記載，
sysprep 被跳過在工廠出貨和工控部署中是常態而非例外。

---

## 黃帽（Yellow Hat）— 效益與優點

### 移除 MAC 後的直接效益

1. **合法用戶的授權穩定性大幅提升**
   - 換網卡不斷授權
   - VM 重建網路介面不斷授權
   - Wi-Fi MAC 隨機化不影響授權

2. **安全性實質不降低**
   - 攻擊者仍需同時仿冒 BIOS UUID + 系統 ID 兩個來自不同層的值
   - SHA-256 的單向性確保從指紋字串無法反推原始值
   - 仿冒成本沒有實質降低，因為 MAC 從來就不是有效屏障

3. **符合業界演進方向**

   **Revenera（全球最大授權管理廠商之一）**的 2024 分析指出：
   > "The focus has shifted to user entitlements and centralized management...
   > A sophisticated licensing system detaches licenses from specific hardware."

   即使業界趨勢是往帳號制移動，在仍需硬體綁定的場景中，
   去除不穩定識別碼是正確的中間路線。

### BIOS UUID 作為補強識別碼的效益

- **獨立於 OS 映像**：sysprep 不清除 BIOS UUID
- **修改需要韌體工具**：比修改 MachineGuid 難一個數量級
- **跨廠商支援廣**：所有 x86 主機板（SMBIOS 規範）均有實作

---

## 綠帽（Green Hat）— 創意與替代方案

### 方案一（採用）：移除 MAC，保留 BIOS UUID + 系統 ID

核心指紋只用穩定識別碼，MAC 降格為 `mac_hint` 純記錄欄位。

```
指紋 = SHA-256( sorted([biosuuid, system_id]) )
```

### 方案二（備用）：寬限期機制

若日後需要容許部分識別碼改變（例如允許 1 個識別碼不符合），
可實作評分門檻驗證：

```
每個識別碼比對成功 → 累加分數
總分 >= 門檻 → 通過
```

**但目前不建議**：增加攻擊者的可利用路徑，且邏輯複雜難維護。

### 方案三（高安全場景）：加入 TPM EK 雜湊

若日後需要防護到 Level 3 攻擊（物理接觸後仿冒），
可加入 TPM 2.0 的 Endorsement Key 公鑰雜湊作為第三識別碼。
2016 年後的機器幾乎都有 TPM 2.0，但採集需要特殊權限。

---

## 藍帽（Blue Hat）— 結論與行動

### 決策結論

外部文獻、業界實踐、攻擊成本分析三者一致指向同一個結論：

**MAC 位址不應作為授權核心識別碼的組成部分。**

具體理由：
1. 業界文獻明確記載其不穩定性（10Duke、NetLicensing、Wikipedia）
2. 免費工具可在 30 秒內更改，安全屏障效果趨近於零
3. 企業環境中的合法操作會觸發誤失效，用戶體驗差
4. 移除後安全性實質不降低，因為替代識別碼（BIOS UUID）更難篡改

### 採用的架構

```
核心指紋（參與雜湊）：
  BIOS UUID    ← 韌體層，映像無關，修改需專業工具
  系統 ID      ← 安裝層，MachineGuid / machine-id / IOPlatformUUID

輔助記錄（不參與雜湊）：
  MAC 位址     ← 純記錄用，存入 license.lic 的 mac_hint 欄位
```

---

## 參考來源

- [How to Generate a Machine Fingerprint — NetLicensing Wiki](https://netlicensing.io/wiki/faq-how-to-generate-machine-fingerprint)
- [The Limitations of Using MAC Addresses for Software Licensing — 10Duke](https://www.10duke.com/blog/the-limitations-of-using-mac-addresses-for-software-licensing/)
- [Duplicate machines using same GUID after imaging — Broadcom KB264590](https://knowledge.broadcom.com/external/article/264590/duplicate-machines-using-same-guid-after.html)
- [The Secure Enclave — Apple Support](https://support.apple.com/guide/security/the-secure-enclave-sec59b0b31ff/web)
- [Apple Platform Security Guide 2026](https://help.apple.com/pdf/security/en_US/apple-platform-security-guide.pdf)
- [MAC Spoofing — Wikipedia](https://en.wikipedia.org/wiki/MAC_spoofing)
- [Offline Licensing Cryptography — Keygen.sh](https://keygen.sh/docs/api/cryptography/)
- [Disk duplication of Windows installations — Microsoft Learn](https://learn.microsoft.com/en-us/troubleshoot/windows-server/setup-upgrade-and-drivers/windows-installations-disk-duplication)
- [Technitium MAC Address Changer](https://technitium.com/tmac/)
- [Is Your Software Licensing Stuck In the Physical World? — Revenera](https://www.revenera.com/blog/software-monetization/is-your-software-licensing-stuck-in-the-physical-world/)
