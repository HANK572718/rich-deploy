"""Generate an RSA key pair for license signing (run once on the developer's machine).

Outputs:
    tools/private_key.pem  — keep secret, never commit
    tools/public_key.pem   — safe to distribute with your application
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_HERE = Path(__file__).parent
_PRIVATE = _HERE / "private_key.pem"
_PUBLIC = _HERE / "public_key.pem"


def generate() -> None:
    """Generate and save a 2048-bit RSA key pair."""
    if _PRIVATE.exists():
        print(f"私鑰已存在：{_PRIVATE}，跳過（避免覆蓋）。")
        return

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    _PRIVATE.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    _PUBLIC.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    print(f"金鑰已生成：\n  私鑰 → {_PRIVATE}\n  公鑰 → {_PUBLIC}")
    print("警告：私鑰絕對不可提交至版本控制！")


if __name__ == "__main__":
    generate()
