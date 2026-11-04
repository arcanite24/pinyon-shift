"""Align and sign an APK without the JDK or the Android build tools (TP-5).

docs/TIME_TO_PLAY_BACKLOG.md: Android packaging needed a JDK for keytool and
apksigner and the SDK's build tools for zipalign. This module does the same
three jobs in plain Python, so a PC builds the Android package with only the
NDK, CMake and Ninja:

- the per-PC signing key: an RSA 3072 key and a self-signed certificate,
  made here, or read from the keytool keystore an earlier build made, so an
  update installs over an earlier build;
- zipalign: stored entries aligned to 4 bytes, stored native libraries to
  16 KiB (zipalign -P 16);
- APK Signature Scheme v2, which every Android version the game supports
  verifies (min SDK 33; v1 is for Android 6 and older, v3 adds key rotation).

    python tools/apk_sign.py sign --in unsigned.apk --out signed.apk --key-dir DIR
    python tools/apk_sign.py verify signed.apk
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- DER -------------------------------------------------------------------


def _length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def der(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _length(len(body)) + body


def der_int(value: int) -> bytes:
    body = value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big", signed=True)
    return der(0x02, body)


def der_seq(*items: bytes) -> bytes:
    return der(0x30, b"".join(items))


def der_oid(dotted: str) -> bytes:
    parts = [int(part) for part in dotted.split(".")]
    body = bytes([40 * parts[0] + parts[1]])
    for part in parts[2:]:
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.append(0x80 | (part & 0x7F))
            part >>= 7
        body += bytes(reversed(chunk))
    return der(0x06, body)


NULL = b"\x05\x00"
RSA_ENCRYPTION = der_seq(der_oid("1.2.840.113549.1.1.1"), NULL)
SHA256_WITH_RSA = der_seq(der_oid("1.2.840.113549.1.1.11"), NULL)
SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def der_read(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    """(tag, body, offset after the element)."""
    tag = data[offset]
    length = data[offset + 1]
    offset += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[offset:offset + count], "big")
        offset += count
    return tag, data[offset:offset + length], offset + length


def der_items(body: bytes) -> list[tuple[int, bytes]]:
    items, offset = [], 0
    while offset < len(body):
        tag, value, offset = der_read(body, offset)
        items.append((tag, value))
    return items


def oid_text(body: bytes) -> str:
    parts = [body[0] // 40, body[0] % 40]
    value = 0
    for byte in body[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(value)
            value = 0
    return ".".join(map(str, parts))


# --- RSA -------------------------------------------------------------------

SMALL_PRIMES = [p for p in range(3, 2000) if all(p % d for d in range(2, int(p ** 0.5) + 1))]


def _probable_prime(n: int) -> bool:
    if any(n % p == 0 for p in SMALL_PRIMES):
        return False
    d, s = n - 1, 0
    while d % 2 == 0:
        d, s = d // 2, s + 1
    for _ in range(40):
        x = pow(secrets.randbelow(n - 3) + 2, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (3 << (bits - 2)) | 1
        if _probable_prime(candidate):
            return candidate


class RsaKey:
    def __init__(self, n: int, e: int, d: int, p: int, q: int) -> None:
        self.n, self.e, self.d, self.p, self.q = n, e, d, p, q

    @classmethod
    def generate(cls, bits: int = 3072) -> "RsaKey":
        e = 65537
        while True:
            p, q = _prime(bits // 2), _prime(bits // 2)
            phi = (p - 1) * (q - 1)
            if p != q and (p * q).bit_length() == bits and phi % e:
                return cls(p * q, e, pow(e, -1, phi), p, q)

    def pkcs8(self) -> bytes:
        p, q, d = self.p, self.q, self.d
        private = der_seq(der_int(0), der_int(self.n), der_int(self.e), der_int(d), der_int(p),
                          der_int(q), der_int(d % (p - 1)), der_int(d % (q - 1)),
                          der_int(pow(q, -1, p)))
        return der_seq(der_int(0), RSA_ENCRYPTION, der(0x04, private))

    @classmethod
    def from_pkcs8(cls, data: bytes) -> "RsaKey":
        _, body, _ = der_read(data)
        private = der_items(body)[2][1]
        _, fields, _ = der_read(private)
        values = [int.from_bytes(value, "big") for _, value in der_items(fields)]
        return cls(values[1], values[2], values[3], values[4], values[5])

    def public_key_info(self) -> bytes:
        public = der_seq(der_int(self.n), der_int(self.e))
        return der_seq(RSA_ENCRYPTION, der(0x03, b"\x00" + public))

    def sign_sha256(self, message: bytes) -> bytes:
        size = (self.n.bit_length() + 7) // 8
        digest_info = SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
        padded = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
        return pow(int.from_bytes(padded, "big"), self.d, self.n).to_bytes(size, "big")


def verify_sha256(public_key_info: bytes, message: bytes, signature: bytes) -> bool:
    _, body, _ = der_read(public_key_info)
    bits = der_items(body)[1][1][1:]
    _, numbers, _ = der_read(bits)
    n, e = (int.from_bytes(value, "big") for _, value in der_items(numbers))
    size = (n.bit_length() + 7) // 8
    recovered = pow(int.from_bytes(signature, "big"), e, n).to_bytes(size, "big")
    expected = SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    return recovered == b"\x00\x01" + b"\xff" * (size - len(expected) - 3) + b"\x00" + expected


def _time(moment: datetime) -> bytes:
    if moment.year < 2050:
        return der(0x17, moment.strftime("%y%m%d%H%M%SZ").encode())
    return der(0x18, moment.strftime("%Y%m%d%H%M%SZ").encode())


def self_signed_certificate(key: RsaKey, common_name: str, days: int = 10000) -> bytes:
    """An X.509 v3 certificate as keytool -genkeypair makes one."""
    name = der_seq(der(0x31, der_seq(der_oid("2.5.4.3"), der(0x0C, common_name.encode()))))
    start = datetime.now(timezone.utc).replace(microsecond=0)
    tbs = der_seq(der(0xA0, der_int(2)), der_int(secrets.randbits(63) | 1), SHA256_WITH_RSA,
                  name, der_seq(_time(start), _time(start + timedelta(days=days))), name,
                  key.public_key_info())
    return der_seq(tbs, SHA256_WITH_RSA, der(0x03, b"\x00" + key.sign_sha256(tbs)))


# --- keytool's PKCS#12 keystore --------------------------------------------
# Only what keytool -genkeypair writes: a PBES2 (PBKDF2, AES-CBC) shrouded
# key bag and a certificate bag. Read once, to carry an earlier build's key
# over; the key is then kept as PKCS#8 beside it.

_SBOX = []


def _aes_tables() -> None:
    if _SBOX:
        return
    inverse = [0] * 256
    p = q = 1
    sbox = [0] * 256
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1 | q >> 7) & 0xFF) ^ ((q << 2 | q >> 6) & 0xFF) \
            ^ ((q << 3 | q >> 5) & 0xFF) ^ ((q << 4 | q >> 4) & 0xFF)
        sbox[p] = x ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    for i, value in enumerate(sbox):
        inverse[value] = i
    _SBOX.extend([sbox, inverse])


def _xtime(a: int) -> int:
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _mul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        a, b = _xtime(a), b >> 1
    return result


def _expand_key(key: bytes) -> list[list[int]]:
    sbox = _SBOX[0]
    nk = len(key) // 4
    rounds = nk + 6
    words = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (rounds + 1)):
        word = list(words[i - 1])
        if i % nk == 0:
            word = [sbox[b] for b in word[1:] + word[:1]]
            word[0] ^= rcon
            rcon = _xtime(rcon)
        elif nk > 6 and i % nk == 4:
            word = [sbox[b] for b in word]
        words.append([a ^ b for a, b in zip(words[i - nk], word)])
    return [sum(words[4 * r:4 * r + 4], []) for r in range(rounds + 1)]


def _decrypt_block(round_keys: list[list[int]], block: bytes) -> bytes:
    inverse = _SBOX[1]
    state = [b ^ k for b, k in zip(block, round_keys[-1])]
    for r in range(len(round_keys) - 2, -1, -1):
        # Inverse shift rows, inverse sub bytes, add round key.
        state = [state[((c - row) % 4) * 4 + row] for c in range(4) for row in range(4)]
        state = [inverse[b] ^ k for b, k in zip(state, round_keys[r])]
        if r:
            mixed = []
            for c in range(4):
                a = state[4 * c:4 * c + 4]
                mixed += [_mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9),
                          _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13),
                          _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11),
                          _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)]
            state = mixed
    return bytes(state)


def aes_cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    _aes_tables()
    round_keys = _expand_key(key)
    plain, previous = b"", iv
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        plain += bytes(a ^ b for a, b in zip(_decrypt_block(round_keys, block), previous))
        previous = block
    return plain[:-plain[-1]]


def _pbes2_decrypt(algorithm: bytes, data: bytes, password: str) -> bytes:
    items = der_items(algorithm)
    if oid_text(items[0][1]) != "1.2.840.113549.1.5.13":
        raise ValueError("the keystore uses an encryption this reader does not know "
                         f"({oid_text(items[0][1])})")
    kdf, cipher = (value for _, value in der_items(items[1][1]))
    kdf_items = der_items(kdf)
    params = der_items(kdf_items[1][1])
    salt, iterations = params[0][1], int.from_bytes(params[1][1], "big")
    prf = "sha1"
    for tag, value in params[2:]:
        if tag == 0x30:
            prf = {"1.2.840.113549.2.9": "sha256", "1.2.840.113549.2.7": "sha1"}[
                oid_text(der_items(value)[0][1])]
    cipher_items = der_items(cipher)
    sizes = {"2.16.840.1.101.3.4.1.2": 16, "2.16.840.1.101.3.4.1.42": 32}
    size = sizes[oid_text(cipher_items[0][1])]
    key = hashlib.pbkdf2_hmac(prf, password.encode("utf-8"), salt, iterations, size)
    return aes_cbc_decrypt(key, cipher_items[1][1], data)


def read_pkcs12(path: Path, password: str) -> tuple[bytes, bytes]:
    """(PKCS#8 private key, certificate) from keytool's keystore."""
    _, pfx, _ = der_read(path.read_bytes())
    content = der_items(pfx)[1][1]
    _, auth_safe, _ = der_read(der_items(der_items(content)[1][1])[0][1])  # [0] OCTET STRING
    key = certificate = None
    for _, info in der_items(auth_safe):
        info_items = der_items(info)
        kind = oid_text(info_items[0][1])
        explicit = der_items(info_items[1][1])[0]
        if kind == "1.2.840.113549.1.7.1":  # data
            bags = explicit[1]
        elif kind == "1.2.840.113549.1.7.6":  # encryptedData
            encrypted = der_items(explicit[1])[1][1]
            parts = der_items(encrypted)
            bags = _pbes2_decrypt(parts[1][1], parts[2][1], password)
            bags = der_read(bags)[1]
        else:
            continue
        _, sequence, _ = der_read(bags) if bags[:1] == b"\x30" and kind != "1.2.840.113549.1.7.6" \
            else (0, bags, 0)
        for _, bag in der_items(sequence):
            bag_items = der_items(bag)
            bag_kind = oid_text(bag_items[0][1])
            value = der_items(bag_items[1][1])[0][1]
            if bag_kind == "1.2.840.113549.1.12.10.1.2":  # pkcs8ShroudedKeyBag
                parts = der_items(value)
                key = _pbes2_decrypt(parts[0][1], parts[1][1], password)
            elif bag_kind == "1.2.840.113549.1.12.10.1.3":  # certBag
                certificate = der_read(der_items(value)[1][1])[1]
                _, certificate, _ = der_read(certificate) if certificate[:1] == b"\x04" \
                    else (0, certificate, 0)
    if key is None or certificate is None:
        raise ValueError(f"{path} holds no key and certificate this reader understands")
    return key, certificate


def signing_key(directory: Path, keystore: Path | None = None,
                password: str = "pinyon-local") -> tuple[RsaKey, bytes]:
    """The PC's signing key and certificate: kept as PKCS#8 and DER in
    directory, carried over from keytool's keystore when an earlier build
    made one, or made now."""
    key_path, certificate_path = directory / "pinyon-shift-local.pk8", \
        directory / "pinyon-shift-local.der"
    if not key_path.is_file() or not certificate_path.is_file():
        directory.mkdir(parents=True, exist_ok=True)
        if keystore is not None and keystore.is_file():
            pkcs8, certificate = read_pkcs12(keystore, password)
            key = RsaKey.from_pkcs8(pkcs8)
        else:
            key = RsaKey.generate()
            pkcs8, certificate = key.pkcs8(), self_signed_certificate(key,
                                                                      "Pinyon Shift local build")
        certificate_path.write_bytes(certificate)
        key_path.write_bytes(pkcs8)
    return RsaKey.from_pkcs8(key_path.read_bytes()), certificate_path.read_bytes()


# --- zipalign --------------------------------------------------------------

LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
CENTRAL_HEADER = struct.Struct("<IHHHHHHIIIHHHHHII")
END_RECORD = struct.Struct("<IHHHHIIH")


def _end_record(data: bytes) -> int:
    offset = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if offset < 0:
        raise ValueError("not a zip archive")
    return offset


def zipalign(data: bytes, page_kib: int = 16) -> bytes:
    """data's entries rewritten with stored ones aligned as zipalign -P does:
    4 bytes, native libraries to page_kib KiB."""
    end = _end_record(data)
    fields = END_RECORD.unpack_from(data, end)
    count, directory_offset = fields[4], fields[6]
    output, central = bytearray(), bytearray()
    offset = directory_offset
    for _ in range(count):
        header = list(CENTRAL_HEADER.unpack_from(data, offset))
        name_length, extra_length, comment_length = header[10], header[11], header[12]
        name = data[offset + 46:offset + 46 + name_length]
        rest = data[offset + 46 + name_length:offset + 46 + name_length + extra_length
                    + comment_length]
        local = header[16]
        local_header = LOCAL_HEADER.unpack_from(data, local)
        local_name_length, local_extra_length = local_header[9], local_header[10]
        start = local + 30 + local_name_length + local_extra_length
        payload = data[start:start + header[8]]
        stored = header[4] == 0
        alignment = (page_kib * 1024 if name.endswith(b".so") else 4) if stored else 1
        new_local = len(output)
        padding = (-(new_local + 30 + len(name))) % alignment
        new_header = list(local_header)
        new_header[10] = padding
        output += LOCAL_HEADER.pack(*new_header) + name + b"\x00" * padding + payload
        header[16] = new_local
        central += CENTRAL_HEADER.pack(*header) + name + rest
        offset += 46 + name_length + extra_length + comment_length
    directory = len(output)
    fields = list(fields)
    fields[5], fields[6] = len(central), directory
    return bytes(output + central + END_RECORD.pack(*fields)) + \
        data[end + 22:end + 22 + fields[7]]


# --- APK Signature Scheme v2 ------------------------------------------------

V2_BLOCK_ID = 0x7109871A
RSA_PKCS1_SHA256 = 0x0103
CHUNK = 1 << 20
MAGIC = b"APK Sig Block 42"


def _prefixed(data: bytes) -> bytes:
    return struct.pack("<I", len(data)) + data


def _content_digest(sections: list[bytes]) -> bytes:
    chunks = []
    for section in sections:
        for offset in range(0, len(section), CHUNK):
            chunk = section[offset:offset + CHUNK]
            chunks.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(chunk)) + chunk).digest())
    return hashlib.sha256(b"\x5a" + struct.pack("<I", len(chunks)) + b"".join(chunks)).digest()


def _sections(data: bytes) -> tuple[bytes, bytes, bytes]:
    end = _end_record(data)
    directory = struct.unpack_from("<I", data, end + 16)[0]
    return data[:directory], data[directory:end], data[end:]


def _eocd_with_offset(eocd: bytes, offset: int) -> bytes:
    return eocd[:16] + struct.pack("<I", offset) + eocd[20:]


def sign_v2(data: bytes, key: RsaKey, certificate: bytes) -> bytes:
    entries, directory, eocd = _sections(data)
    digest = _content_digest([entries, directory, _eocd_with_offset(eocd, len(entries))])
    digests = _prefixed(_prefixed(struct.pack("<I", RSA_PKCS1_SHA256) + _prefixed(digest)))
    signed_data = digests + _prefixed(_prefixed(certificate)) + _prefixed(b"")
    signature = _prefixed(_prefixed(struct.pack("<I", RSA_PKCS1_SHA256)
                                    + _prefixed(key.sign_sha256(signed_data))))
    signer = _prefixed(signed_data) + signature + _prefixed(key.public_key_info())
    value = _prefixed(_prefixed(signer))
    pair = struct.pack("<QI", 4 + len(value), V2_BLOCK_ID) + value
    size = len(pair) + 8 + 16
    block = struct.pack("<Q", size) + pair + struct.pack("<Q", size) + MAGIC
    return entries + block + directory + _eocd_with_offset(eocd, len(entries) + len(block))


def verify_v2(data: bytes) -> dict:
    """The v2 signature's checks, as apksigner verify makes them for one
    RSA signer: the block, the signature over the signed data, and the
    content digest. Raises ValueError on a mismatch."""
    entries, directory, eocd = _sections(data)
    if entries[-16:] != MAGIC:
        raise ValueError("no APK signing block")
    size = struct.unpack_from("<Q", entries, len(entries) - 24)[0]
    block_start = len(entries) - size - 8
    pairs, offset = entries[block_start + 8:len(entries) - 24], 0
    value = None
    while offset < len(pairs):
        length, identifier = struct.unpack_from("<QI", pairs, offset)
        if identifier == V2_BLOCK_ID:
            value = pairs[offset + 12:offset + 8 + length]
        offset += 8 + length
    if value is None:
        raise ValueError("no v2 signature")

    def take(buffer: bytes, at: int) -> tuple[bytes, int]:
        length = struct.unpack_from("<I", buffer, at)[0]
        return buffer[at + 4:at + 4 + length], at + 4 + length

    signers, _ = take(value, 0)
    signer, _ = take(signers, 0)
    signed_data, at = take(signer, 0)
    signatures, at = take(signer, at)
    public_key, _ = take(signer, at)
    signature, _ = take(signatures, 0)
    algorithm = struct.unpack_from("<I", signature)[0]
    signature_bytes, _ = take(signature, 4)
    if algorithm != RSA_PKCS1_SHA256 or not verify_sha256(public_key, signed_data,
                                                          signature_bytes):
        raise ValueError("the v2 signature does not verify")
    digests, at = take(signed_data, 0)
    certificates, _ = take(signed_data, at)
    first_digest, _ = take(digests, 0)
    recorded, _ = take(first_digest, 4)
    actual = _content_digest([entries[:block_start], directory,
                              _eocd_with_offset(eocd, block_start)])
    if recorded != actual:
        raise ValueError("the v2 content digest does not match the APK")
    certificate, _ = take(certificates, 0)
    return {"scheme": "v2", "certificate_sha256": hashlib.sha256(certificate).hexdigest()}


def sign(source: bytes, key: RsaKey, certificate: bytes, page_kib: int = 16) -> bytes:
    return sign_v2(zipalign(source, page_kib), key, certificate)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    signing = commands.add_parser("sign")
    signing.add_argument("--in", dest="source", required=True, type=Path)
    signing.add_argument("--out", required=True, type=Path)
    signing.add_argument("--key-dir", required=True, type=Path)
    signing.add_argument("--keystore", type=Path,
                         help="keytool's keystore from an earlier build, to keep its key")
    checking = commands.add_parser("verify")
    checking.add_argument("apk", type=Path)
    args = parser.parse_args(argv)
    if args.command == "sign":
        key, certificate = signing_key(args.key_dir, args.keystore)
        args.out.write_bytes(sign(args.source.read_bytes(), key, certificate))
        print(json.dumps(verify_v2(args.out.read_bytes())))
    else:
        print(json.dumps(verify_v2(args.apk.read_bytes())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
