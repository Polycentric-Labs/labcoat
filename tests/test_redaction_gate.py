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


# ---------------------------------------------------------------------------
# Task 1: Class A / Class B classification
# ---------------------------------------------------------------------------

def test_classify_separates_secrets_from_contextual():
    assert rg.classify("OpenRouter API key shape") == "A"
    assert rg.classify("PEM private key") == "A"
    assert rg.classify("secret-store reference") == "A"
    assert rg.classify("absolute Windows user path") == "B"
    assert rg.classify("email address") == "B"
    assert rg.classify("client term") == "B"

def test_class_a_labels_are_the_secret_shapes():
    a = rg.class_a_labels()
    assert "OpenRouter API key shape" in a and "AWS access key id" in a
    assert "absolute Windows user path" not in a and "email address" not in a


# ---------------------------------------------------------------------------
# Task 2: SSH-URL allowlist
# ---------------------------------------------------------------------------

def test_ssh_url_not_flagged_as_email():
    # git@github.com:owner/repo.git is an SSH URL, not PII
    findings = rg.scan_for_sensitive("clone git@github.com:Polycentric-Labs/labcoat.git please")
    assert not any(f["label"] == "email address" for f in findings)

def test_real_email_still_flagged():
    findings = rg.scan_for_sensitive("contact a.person@example.com")
    assert any(f["label"] == "email address" for f in findings)


# ---------------------------------------------------------------------------
# Task 3: Surgical redaction with typed placeholders
# ---------------------------------------------------------------------------

def test_apply_redactions_replaces_class_b_with_typed_placeholders():
    text = r"see C:\Users\alice\proj and mail a@b.com"
    findings = rg.scan_for_sensitive(text)
    clean, applied = rg.apply_redactions(text, findings)
    assert "C:\\Users\\alice" not in clean and "a@b.com" not in clean
    assert "<PATH_1>" in clean and "<EMAIL_1>" in clean   # typed, indexed
    assert {a["placeholder"] for a in applied} == {"<PATH_1>", "<EMAIL_1>"}

def test_apply_redactions_is_index_safe_with_multiple_spans():
    text = "a@b.com then c@d.com"
    clean, applied = rg.apply_redactions(text, rg.scan_for_sensitive(text))
    assert clean == "<EMAIL_1> then <EMAIL_2>"


# ---------------------------------------------------------------------------
# Task 4: Post-redaction signal check
# ---------------------------------------------------------------------------

def test_signal_recommends_stop_when_query_is_gutted():
    text = "a@b.com c@d.com e@f.com"               # 3 Class-B entities, mostly redacted
    findings = rg.scan_for_sensitive(text)
    clean, _ = rg.apply_redactions(text, findings)
    sig = rg.signal(text, clean, findings)
    assert sig["entity_count"] == 3 and sig["recommend_stop"] is True

def test_signal_allows_continue_for_light_redaction():
    text = "Compare Hyper-V vs Firecracker; ignore mail a@b.com in passing here ok"
    findings = rg.scan_for_sensitive(text)
    clean, _ = rg.apply_redactions(text, findings)
    sig = rg.signal(text, clean, findings)
    assert sig["entity_count"] == 1 and sig["recommend_stop"] is False


# ---------------------------------------------------------------------------
# Task 5: redact() orchestration + client_terms
# ---------------------------------------------------------------------------

def test_redact_hard_blocks_on_class_a_secret():
    r = rg.redact("my key is sk-or-v1-abcdefabcdefabcdefabcdef and path C:\\Users\\x\\y")
    assert r["hard_block"] is True
    assert r["clean_text"] is None       # do not emit a prompt that contained a secret
    assert any(f["cls"] == "A" for f in r["findings"])

def test_redact_surgically_continues_on_class_b_only():
    r = rg.redact(r"investigate path C:\Users\alice\proj for the build")
    assert r["hard_block"] is False
    assert "C:\\Users\\alice" not in r["clean_text"] and "<PATH_1>" in r["clean_text"]
    assert r["signal"]["recommend_stop"] is False

def test_redact_redacts_caller_client_terms():
    r = rg.redact("the Wexler matter needs review", client_terms=["Wexler"])
    assert "Wexler" not in r["clean_text"] and "<CLIENT_1>" in r["clean_text"]
    assert any(f["label"] == "client term" for f in r["findings"])


# ---------------------------------------------------------------------------
# Task 6: assert_clean -> Class-A-only wrapper
# ---------------------------------------------------------------------------

def test_assert_clean_raises_only_on_class_a_secret():
    with pytest.raises(rg.SensitiveDataError):
        rg.assert_clean("key sk-or-v1-abcdefabcdefabcdefabcdef")

def test_assert_clean_does_not_raise_on_class_b_path():
    # v2: a bare path is Class B (surgical), NOT a hard block — assert_clean is Class-A-only now
    rg.assert_clean(r"see C:\Users\alice\Documents\x.md")   # no raise

def test_assert_clean_error_lists_labels_not_values():
    try:
        rg.assert_clean("key sk-or-v1-abcdefabcdefabcdefabcdef")
    except rg.SensitiveDataError as e:
        assert "OpenRouter API key shape" in str(e)
        assert "sk-or-v1-abcdef" not in str(e)   # never echo the value


# ---------------------------------------------------------------------------
# Task 7: Optional Presidio NER enhancement (import-guarded, graceful degrade)
# ---------------------------------------------------------------------------

def test_presidio_available_flag_is_bool_and_safe():
    assert isinstance(rg.presidio_available(), bool)

def test_redact_uses_presidio_when_present(monkeypatch):
    # simulate presidio surfacing a PERSON entity span; redact() must fold it in as Class B
    monkeypatch.setattr(rg, "presidio_available", lambda: True)
    monkeypatch.setattr(rg, "_presidio_classB", lambda text: [
        {"label": "person name", "start": text.index("Ada"), "end": text.index("Ada") + 3, "cls": "B"}])
    r = rg.redact("Ada wrote the spec")
    assert "Ada" not in r["clean_text"] and "<PERSON" in r["clean_text"]


# ---------------------------------------------------------------------------
# FIX 1: overlapping-span corruption in apply_redactions
# ---------------------------------------------------------------------------

def test_overlapping_spans_no_garbled_output():
    # "alice" is a substring of both "C:\\Users\\alice\\docs" (PATH) and "alice@corp.com" (EMAIL).
    # Applying spans naively produces garbled fragments like "<PATH_1>NT_1>".
    # After merging overlapping spans, output must contain ONLY well-formed placeholders.
    text = r"C:\Users\alice\docs and alice@corp.com"
    r = rg.redact(text, client_terms=["alice"])
    clean = r["clean_text"]
    assert r["hard_block"] is False
    # No raw sensitive fragments
    assert "alice" not in clean
    assert r"C:\Users\alice" not in clean
    assert "alice@corp.com" not in clean
    # No garbled placeholder fragments (e.g. ">NT_1>" or "<PATH_1>NT_1>")
    import re as _re
    # Every <...> token must be a well-formed placeholder
    tokens = _re.findall(r"<[^>]+>", clean)
    for tok in tokens:
        assert _re.fullmatch(r"<[A-Z]+_\d+>", tok), f"Garbled placeholder: {tok!r}"
    # The overall string must not contain a bare '>' that belongs to a broken span
    # (i.e., no '>' not preceded by a valid placeholder close)
    assert ">NT_" not in clean and ">IL_" not in clean

def test_overlapping_client_term_in_path():
    # client_term "alice" overlaps "C:\\Users\\alice\\proj" — path span should win.
    r = rg.redact(r"check C:\Users\alice\proj please", client_terms=["alice"])
    clean = r["clean_text"]
    assert "alice" not in clean
    import re as _re
    tokens = _re.findall(r"<[^>]+>", clean)
    for tok in tokens:
        assert _re.fullmatch(r"<[A-Z]+_\d+>", tok), f"Garbled placeholder: {tok!r}"


# ---------------------------------------------------------------------------
# FIX 2: client_terms=None must not crash
# ---------------------------------------------------------------------------

def test_redact_client_terms_none_behaves_as_default():
    # Must not raise TypeError; should behave identically to client_terms=()
    r = rg.redact("hello world", client_terms=None)
    assert r["hard_block"] is False
    assert r["clean_text"] == "hello world"

def test_redact_client_terms_none_with_path():
    # Regression: None + text that has Class-B findings must still redact normally
    r = rg.redact(r"see C:\Users\alice\docs please", client_terms=None)
    assert r["hard_block"] is False
    assert "alice" not in r["clean_text"]
    assert "<PATH_1>" in r["clean_text"]


# ---------------------------------------------------------------------------
# FIX 3: residual-substance floor in signal()
# ---------------------------------------------------------------------------

def test_signal_gutted_single_email_recommends_stop():
    # 1 email, 100% redacted — residual text < 10 chars → should stop.
    r = rg.redact("a@b.com")
    assert r["signal"]["recommend_stop"] is True, (
        "A fully-gutted prompt (single email, nothing else) must trigger recommend_stop"
    )

def test_signal_single_path_with_context_does_not_stop():
    # 1 path but lots of surrounding words — residual substance > threshold → must NOT stop.
    r = rg.redact(r"investigate the path C:\Users\alice\proj carefully for the build please")
    assert r["signal"]["recommend_stop"] is False, (
        "A prompt with one path but plenty of surrounding text must not recommend_stop"
    )

def test_signal_two_entities_high_pct_does_not_stop():
    # 2 emails in a string, entity_count==2 — must NOT satisfy the AND clause (needs >=3).
    # Pick a string with enough residual chars that the floor doesn't trip either.
    r = rg.redact("contact a@b.com or c@d.com for detailed scheduling information here")
    sig = r["signal"]
    assert sig["entity_count"] == 2
    assert sig["recommend_stop"] is False, (
        "entity_count==2 should not satisfy AND clause (requires >=3)"
    )

def test_signal_returns_residual_chars():
    # signal() must now include residual_chars in the returned dict.
    r = rg.redact(r"see C:\Users\alice\proj for build")
    assert "residual_chars" in r["signal"]
    assert isinstance(r["signal"]["residual_chars"], int)


# ---------------------------------------------------------------------------
# Fix 1 (campaign): client_terms are case-insensitive
# ---------------------------------------------------------------------------

def test_client_terms_are_case_insensitive():
    r = rg.redact("investigating the wexler matter and WEXLER docs", client_terms=["Wexler"])
    assert "wexler" not in r["clean_text"].lower()
    assert any(f["label"] == "client term" for f in r["findings"])

