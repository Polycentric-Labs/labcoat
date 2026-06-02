# tests/test_redaction_gate.py
import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import redaction_gate as rg

@pytest.mark.parametrize("bad", [
    "sk-or-v1-abcdefabcdefabcdefabcdef",          # OpenRouter key shape
    "ghp_0123456789012345678901234567890123",     # GitHub PAT
    "AKIAIOSFODNN7EXAMPLE",                        # AWS key id
    "-----BEGIN PRIVATE KEY-----",                 # PEM
    "C:\\Users\\alice\\.secrets\\app.env",  # secret path
])
def test_scan_flags_secret_shapes(bad):
    findings = rg.scan_for_sensitive(f"context {bad} more")
    assert findings, f"should have flagged: {bad}"

def test_scan_flags_absolute_user_path():
    assert rg.scan_for_sensitive(r"see C:\Users\alice\Documents\private\x.md")

def test_scan_passes_benign_text():
    assert rg.scan_for_sensitive("Compare Hyper-V vs Firecracker for sandbox isolation.") == []

def test_assert_clean_raises_on_finding():
    with pytest.raises(rg.SensitiveDataError):
        rg.assert_clean("my key is sk-or-v1-abcdefabcdefabcdefabcdef")

def test_assert_clean_passes_benign():
    rg.assert_clean("a perfectly fine research question")  # no raise

def test_assert_clean_message_does_not_echo_secret():
    secret = "sk-or-v1-SUPERSECRETVALUE1234567890"
    with pytest.raises(rg.SensitiveDataError) as exc_info:
        rg.assert_clean(f"key is {secret}")
    assert secret not in str(exc_info.value)
    assert "SUPERSECRETVALUE" not in str(exc_info.value)

def test_findings_carry_no_secret_value():
    secret = "sk-or-v1-SUPERSECRETVALUE1234567890"
    findings = rg.scan_for_sensitive(f"key is {secret}")
    assert findings
    assert "SUPERSECRETVALUE" not in repr(findings)
    assert all({"label", "start", "end"} <= set(f.keys()) for f in findings)
    assert all("match" not in f for f in findings)

def test_non_str_input_fails_closed():
    for bad in (None, 123, ["x"], {"a": 1}):
        with pytest.raises(TypeError):
            rg.scan_for_sensitive(bad)
        with pytest.raises(TypeError):
            rg.assert_clean(bad)


def test_bytes_input_fails_closed():
    # bytes is non-str; a secret-shaped bytes value must NOT silently pass (SOUNDNESS probe).
    secret_bytes = b"sk-or-v1-" + b"a" * 40
    with pytest.raises(TypeError):
        rg.scan_for_sensitive(secret_bytes)
    with pytest.raises(TypeError):
        rg.assert_clean(secret_bytes)


def test_str_subclass_with_secret_still_blocked():
    # An str subclass passes isinstance but must still be scanned (no fail-open via subclassing).
    class EvilStr(str):
        pass
    with pytest.raises(rg.SensitiveDataError):
        rg.assert_clean(EvilStr("key sk-or-v1-" + "q" * 40))


def test_scan_message_and_findings_contain_no_window_of_secret():
    # No 6-char window of the secret value may appear in the raised message or findings repr.
    secret = "sk-or-v1-ZYXWVUT9876543210abcdefghij"
    findings = rg.scan_for_sensitive(f"use {secret} now")
    assert findings and all("match" not in f and "value" not in f for f in findings)
    with pytest.raises(rg.SensitiveDataError) as exc:
        rg.assert_clean(f"use {secret} now")
    msg = str(exc.value)
    body = secret.split("sk-or-v1-")[1]
    assert not any(body[i:i + 6] in msg for i in range(len(body) - 6))
    assert not any(body[i:i + 6] in repr(findings) for i in range(len(body) - 6))

def test_flags_bare_username_paths():
    assert rg.scan_for_sensitive(r"my dir is C:\Users\alice here")     # no trailing separator
    assert rg.scan_for_sensitive("on linux it is /home/alice there")

def test_flags_fine_grained_github_pat():
    assert rg.scan_for_sensitive("token github_pat_" + "A" * 40)

