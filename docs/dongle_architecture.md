# Dongle 架構預留設計

> 本文件為技術預留，目前不實作。記錄若未來需要硬體狗（Dongle）授權時的整合方向與擴充點。

---

## 一、Dongle 是什麼，適用場景

硬體狗（Dongle）是一種 USB 裝置，用於確認「授權綁定在實體裝置上，而非機器上」。
主要使用場景：

- 授權需要在多台機器間流動（帶著走）
- 對逆向工程有更高防護需求（金鑰在硬體裡）
- 高單價工業軟體（CAD、EDA、影像處理）的傳統授權方式

相較於本系統目前的硬體指紋方案：

| 面向 | 硬體指紋（目前） | Dongle |
|------|----------------|--------|
| 綁定對象 | 機器 | 裝置（可移動） |
| 授權轉移 | 需重新簽發 | 插拔即轉移 |
| 硬體成本 | 無 | 每個 Dongle 約 USD 10–50 |
| 逆向防護 | 中 | 高（金鑰在晶片內） |
| 部署複雜度 | 低 | 中（需發貨 Dongle） |

---

## 二、主流技術方案

### USB HID（Human Interface Device）

最簡單的做法：把一個 USB 隨身碟或微控制器（如 Arduino Pro Micro）偽裝成 HID 裝置，
程式讀取其中儲存的特定識別碼或挑戰回應。

**Python 函式庫**：
```
pip install hid        # 跨平台 USB HID 讀寫
# 或
pip install pyusb      # 較低階，需要 libusb
```

優點：無需簽名驅動，支援 Windows/Linux/macOS。
缺點：裝置本身金鑰可被讀出（需要加密保護）。

### PCSC / Smart Card

使用符合 ISO 7816 標準的智慧卡晶片（如 Yubico、ACS ACR 系列），
金鑰存在晶片安全區，只能做挑戰回應（類似 TPM）。

**Python 函式庫**：
```
pip install pyscard    # 跨平台 PC/SC 介面
```

優點：金鑰無法匯出，密碼學強度等同 TPM。
缺點：需要讀卡機（許多筆電有內建，桌機需外接）。

### 商用 Dongle SDK

市場上有成熟方案（Sentinel HASP、SafeNet）提供 Python SDK，
但有授權費用，適合商業規模產品，不適合本工具的定位。

---

## 三、在本系統的擴充點

### 指紋版本化的預留槽

`get_fingerprint.py` 的 dispatcher 已為 Dongle 預留：

```python
dispatchers = {
    1: _compute_v1,       # 現有：OS ID + BIOS UUID
    # 2: _compute_v2,     # 預留：TPM EK 雜湊
    # 3: _compute_v3,     # 預留：Dongle 序號
}
```

實作 `fp_version=3` 時，`_compute_v3` 的邏輯：
1. 呼叫 HID/PCSC 函式庫讀取 Dongle 識別碼（或挑戰回應結果）
2. 組合識別碼字串，計算 SHA-256
3. 回傳 64 字元 hex，介面與 v1 完全一致

### license.lic 的 `binding_type` 欄位設計

未來授權 JSON 可加入 `binding_type` 欄位指示驗證方式：

```json
{
  "fingerprint": "3335b4a3...",
  "fp_version":  3,
  "binding_type": "dongle",
  "signature":   "V40EhXDF...",
  "note":        "客戶名稱"
}
```

`verify_license.py` 的 Gate 1 可根據 `binding_type` 選擇對應的指紋採集路徑。

### DB Schema 預留

`License` table 已有 `fp_version` 欄位，可直接用版本號區分 Dongle 授權。
若需要記錄 Dongle 序號，可在未來 migration 加入 `dongle_id` 欄位：

```python
# 未來加入 License model
dongle_id: Mapped[str | None] = mapped_column(String, nullable=True)
```

### bootstrap.py 的 Dongle 偵測預留點

`_run_customer_wizard()` 中可加入 Dongle 偵測步驟：

```python
# 未來：在採集指紋前偵測 Dongle
if _detect_dongle():
    fp = get_fingerprint(version=3)   # Dongle 模式
else:
    fp = get_fingerprint(version=1)   # 機器指紋模式
```

---

## 四、推薦方案

若未來需要實作 Dongle 支援，建議路線：

1. **低成本試水**：USB HID + `hid` 套件，用現成 USB 隨身碟 + 自定義識別碼
2. **生產強度**：PCSC Smart Card（如 YubiKey 5）+ `pyscard`，金鑰不可匯出
3. **商業規模**：評估 Sentinel HASP / SafeNet 的 Python SDK

---

## 參考資源

| 資源 | 說明 |
|------|------|
| [hid PyPI](https://pypi.org/project/hid/) | USB HID Python 綁定 |
| [pyscard GitHub](https://github.com/LudovicRousseau/pyscard) | PCSC Smart Card Python 介面 |
| [YubiKey Python SDK](https://github.com/Yubico/yubikey-manager) | YubiKey 管理與挑戰回應 |
| [USB HID Spec](https://www.usb.org/hid) | USB HID 規格書 |
