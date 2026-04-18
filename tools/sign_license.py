"""Sign a machine fingerprint with the developer's private key.

This script must only exist on the developer's machine.
Usage:
    python sign_license.py <fingerprint>
    python sign_license.py <fingerprint> --expires 2027-12-31
    python sign_license.py <fingerprint> --expires 2027-12-31 --mac aa:bb:cc:dd:ee:ff --note "客戶名稱"
    python sign_license.py <fingerprint> --fp-version 1 --expires 2027-12-31
"""

import argparse
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key

_PRIVATE_KEY_PATH = Path(__file__).parent / "private_key.pem"
_FP_LEN = 64
_HEX_CHARS = frozenset("0123456789abcdef")


def _load_private_key(path: Path):
    """Load and return the RSA private key from *path*."""
    if not path.exists():
        print(f"ERROR: 找不到私鑰 {path}", file=sys.stderr)
        sys.exit(1)
    return load_pem_private_key(path.read_bytes(), password=None)


def _validate_fingerprint(fp: str) -> str:
    """Return *fp* unchanged, or exit with an error if the format is invalid."""
    if len(fp) != _FP_LEN or not all(c in _HEX_CHARS for c in fp):
        print(
            "ERROR: 指紋格式不正確，應為 64 個小寫 hex 字元",
            file=sys.stderr,
        )
        sys.exit(1)
    return fp


def sign(
    fingerprint: str,
    expires: str | None = None,
    mac_hint: str | None = None,
    note: str | None = None,
    fp_version: int = 1,
) -> dict:
    """Sign *fingerprint* and return the license dict ready for serialisation.

    MAC address is stored as an informational hint only — it is NOT part of
    the signed payload and does NOT affect license validation. This allows
    NIC replacement, VM network rebuilds, and Wi-Fi MAC randomisation to
    occur without invalidating the license.

    fp_version is included in the signed payload to prevent downgrade attacks.
    """
    fingerprint = _validate_fingerprint(fingerprint.strip())
    private_key = _load_private_key(_PRIVATE_KEY_PATH)

    # Signed payload includes fp_version to prevent downgrade attacks.
    # MAC is intentionally excluded so hardware changes don't break licenses.
    payload = f"{fingerprint}|fp_version:{fp_version}"
    if expires:
        payload += f"|expires:{expires}"

    signature = private_key.sign(payload.encode(), PKCS1v15(), SHA256())
    sig_b64 = base64.b64encode(signature).decode()

    license_data: dict = {
        "fingerprint": fingerprint,
        "fp_version": fp_version,
        "signature": sig_b64,
        "note": note or "此授權僅限本機使用",
    }
    if expires:
        license_data["expires"] = expires

    # mac_hint is outside the signed payload — for auditing only.
    if mac_hint:
        license_data["mac_hint"] = mac_hint

    return license_data


def main() -> None:
    """Entry point: parse args, sign, and print the license JSON."""
    parser = argparse.ArgumentParser(
        description="Sign a machine fingerprint to produce a license.",
    )
    parser.add_argument(
        "fingerprint",
        help="64-char hex string from get_fingerprint.py",
    )
    parser.add_argument(
        "--expires",
        metavar="YYYY-MM-DD",
        default=None,
        help="Optional expiry date (ISO 8601)",
    )
    parser.add_argument(
        "--mac",
        metavar="XX:XX:XX:XX:XX:XX",
        default=None,
        dest="mac_hint",
        help="MAC address for audit record only (not used in validation)",
    )
    parser.add_argument(
        "--note",
        metavar="TEXT",
        default=None,
        help="Human-readable note to embed in the license (e.g. customer name)",
    )
    parser.add_argument(
        "--fp-version",
        metavar="N",
        type=int,
        default=1,
        dest="fp_version",
        help="Fingerprint algorithm version (default: 1)",
    )
    args = parser.parse_args()

    license_data = sign(
        args.fingerprint,
        expires=args.expires,
        mac_hint=args.mac_hint,
        note=args.note,
        fp_version=args.fp_version,
    )
    output = json.dumps(license_data, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("請複製以下內容，在甲方機器上存成 license.lic：")
    print("=" * 60)
    print(output)
    print("=" * 60)


if __name__ == "__main__":
    main()
