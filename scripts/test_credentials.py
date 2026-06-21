"""
test_credentials.py — covers v1.0.3 credential store invariants.

What we lock down here (DO NOT REGRESS):

  P1  Empty store on a fresh machine — list returns []; suggest is_empty.
  P2  Add metadata round-trips through atomic_write + reload.
  P3  Default consent answer is NO. add_credential_noninteractive
      WITHOUT consented_plaintext refuses plaintext storage.
  P4  Plaintext password storage is base64-encoded and round-trips.
  P5  Same URL with two different usernames produces two distinct
      entries (no overwrite).
  P6  Score formula: 0 for fresh entry; > 0 after bump_usage; decays
      with simulated time gap.
  P7  Ranked() ordering: bigger uses + recent timestamps come first.
  P8  Remove cleans index AND backend (best-effort delete from
      plaintext fallback).
  P9  POSIX file permissions: dir 0o700, file 0o600.
  P10 No password ever appears in list_credentials() output.
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure we run from the right path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

# Use an isolated user data dir for ALL tests
os.environ["EVO_QA_HOME"] = tempfile.mkdtemp(prefix="pq-creds-test-")

from evo_qa.core.credentials import CredentialStore, NullBackend
from evo_qa.core.credentials.store import _make_entry_id
from evo_qa.core.credentials.interactive import (
    add_credential_noninteractive,
    list_credentials, select_for_url,
    get_password, remove_credential,
)


def _fresh_store() -> CredentialStore:
    """Return a store rooted in a brand-new temp dir."""
    d = tempfile.mkdtemp(prefix="pq-creds-")
    os.environ["EVO_QA_HOME"] = d
    # Reset module-level default so we don't reuse a stale instance.
    from evo_qa.core import credentials as cred_pkg
    cred_pkg.store._DEFAULT_STORE = None
    return CredentialStore(Path(d))


# ---------------------------------------------------------------------------

def test_p1_empty_store():
    s = _fresh_store()
    assert list_credentials(store=s) == []
    sel = select_for_url(store=s)
    assert sel["is_empty"] is True
    assert sel["default"] is None
    print("✓ P1 empty store")


def test_p2_metadata_roundtrip():
    s = _fresh_store()
    res = add_credential_noninteractive(
        url="https://x.test", username="alice", password="pw",
        prefer_backend="plaintext_file", consented_plaintext=True,
        store=s,
    )
    assert res["ok"], res
    eid = res["entry_id"]

    # reload from disk
    s2 = CredentialStore(s.root)
    e = s2.get(eid)
    assert e is not None and e.username == "alice" and e.url == "https://x.test"
    print("✓ P2 metadata round-trip")


def test_p3_consent_default_is_no():
    s = _fresh_store()
    # No consent flag → must refuse for plaintext
    res = add_credential_noninteractive(
        url="https://x", username="u", password="p",
        prefer_backend="plaintext_file",
        consented_plaintext=False, store=s,
    )
    assert res["ok"] is False
    assert "consent" in res["msg"].lower()
    assert list_credentials(store=s) == []  # nothing got created
    print("✓ P3 consent default = no")


def test_p4_plaintext_roundtrip():
    s = _fresh_store()
    add_credential_noninteractive(
        url="https://y", username="bob", password="hunter2",
        prefer_backend="plaintext_file", consented_plaintext=True,
        store=s,
    )
    eid = "y-bob"
    pw = get_password(eid, store=s)
    assert pw == "hunter2", pw

    # And the on-disk YAML must NOT contain "hunter2" in clear text
    text = s.path.read_text(encoding="utf-8")
    assert "hunter2" not in text, "plaintext password leaked unencoded!"
    # base64 of hunter2 == "aHVudGVyMg=="
    assert "aHVudGVyMg==" in text or "aHVudGVyMg" in text
    print("✓ P4 plaintext password roundtrip + base64-only on disk")


def test_p5_same_url_different_users():
    s = _fresh_store()
    r1 = add_credential_noninteractive(
        url="https://www.saucedemo.com", username="standard_user",
        password="x", prefer_backend="plaintext_file",
        consented_plaintext=True, store=s,
    )
    r2 = add_credential_noninteractive(
        url="https://www.saucedemo.com", username="locked_out_user",
        password="y", prefer_backend="plaintext_file",
        consented_plaintext=True, store=s,
    )
    assert r1["entry_id"] != r2["entry_id"]
    assert len(list_credentials(store=s)) == 2
    print("✓ P5 same URL, two users -> two entries")


def test_p6_score_formula():
    s = _fresh_store()
    res = add_credential_noninteractive(
        url="https://z", username="u", password="p",
        prefer_backend="plaintext_file", consented_plaintext=True,
        store=s,
    )
    eid = res["entry_id"]

    e = s.get(eid)
    assert e.score() == 0.0  # never used yet

    s.bump_usage(eid)
    e = s.get(eid)
    assert e.uses == 1 and e.last_used_at
    fresh = e.score()
    assert fresh > 0.99 and fresh <= 1.0   # essentially 1.0 today

    # Simulate 60 days later: score must drop to ~ uses * 0.25
    later = time.time() + 60 * 86400
    decayed = e.score(now=later)
    assert decayed < fresh * 0.5, (fresh, decayed)
    assert decayed > 0
    print(f"✓ P6 score formula  fresh={fresh:.3f} 60d={decayed:.3f}")


def test_p7_ranked_ordering():
    s = _fresh_store()
    # Three creds, varying usage
    ids = []
    for u, n_uses in [("a", 5), ("b", 1), ("c", 20)]:
        res = add_credential_noninteractive(
            url=f"https://{u}", username=u, password="p",
            prefer_backend="plaintext_file", consented_plaintext=True,
            store=s,
        )
        for _ in range(n_uses):
            s.bump_usage(res["entry_id"])
        ids.append(res["entry_id"])

    ranked = s.ranked()
    # All used "now", so order should be by uses desc: c, a, b
    assert ranked[0].username == "c", ranked[0].username
    assert ranked[1].username == "a"
    assert ranked[2].username == "b"
    print("✓ P7 ranked by usage")


def test_p8_remove_clears_secret():
    s = _fresh_store()
    res = add_credential_noninteractive(
        url="https://r", username="u", password="topsecret",
        prefer_backend="plaintext_file", consented_plaintext=True,
        store=s,
    )
    eid = res["entry_id"]
    assert get_password(eid, store=s) == "topsecret"

    r = remove_credential(eid, store=s)
    assert r["ok"]
    assert s.get(eid) is None
    assert get_password(eid, store=s) is None
    # And no string "topsecret" anywhere in the YAML
    text = s.path.read_text(encoding="utf-8") if s.path.exists() else ""
    assert "topsecret" not in text
    print("✓ P8 remove clears secret")


def test_p9_posix_permissions():
    if os.name != "posix":
        print("⊙ P9 skipped (non-POSIX)")
        return
    s = _fresh_store()
    add_credential_noninteractive(
        url="https://p", username="u", password="p",
        prefer_backend="plaintext_file", consented_plaintext=True,
        store=s,
    )
    dir_mode = stat.S_IMODE(s.root.stat().st_mode)
    file_mode = stat.S_IMODE(s.path.stat().st_mode)
    assert dir_mode == 0o700, oct(dir_mode)
    assert file_mode == 0o600, oct(file_mode)
    print(f"✓ P9 POSIX perms  dir={oct(dir_mode)} file={oct(file_mode)}")


def test_p10_list_never_leaks_password():
    s = _fresh_store()
    add_credential_noninteractive(
        url="https://leaky", username="u", password="VERYSECRETPW",
        prefer_backend="plaintext_file", consented_plaintext=True,
        store=s,
    )
    items = list_credentials(store=s)
    flat = repr(items)
    assert "VERYSECRETPW" not in flat
    # Even base64 form must not appear in list output (we don't expose it)
    import base64
    enc = base64.b64encode(b"VERYSECRETPW").decode()
    assert enc not in flat
    # and no password-shaped key
    assert "password" not in [k for it in items for k in it.keys()]
    print("✓ P10 list_credentials never leaks password")


# ---------------------------------------------------------------------------

def main():
    tests = [
        test_p1_empty_store,
        test_p2_metadata_roundtrip,
        test_p3_consent_default_is_no,
        test_p4_plaintext_roundtrip,
        test_p5_same_url_different_users,
        test_p6_score_formula,
        test_p7_ranked_ordering,
        test_p8_remove_clears_secret,
        test_p9_posix_permissions,
        test_p10_list_never_leaks_password,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"✗ {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 60)
    if failed == 0:
        print(f"All credential tests passed ({len(tests)}/{len(tests)}) ✅")
        return 0
    print(f"FAILED {failed}/{len(tests)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
