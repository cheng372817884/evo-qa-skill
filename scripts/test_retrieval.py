"""Test the hybrid retriever (substring + BM25)."""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from evo_qa.core.retrieval import HybridRetriever, IndexEntry
from evo_qa.core.retrieval.hybrid import BM25_THRESHOLD


def section(name): print(f"\n--- {name} ---")


def R1_substring_only_below_threshold():
    section("R1 substring-only when corpus < threshold")
    r = HybridRetriever()
    r.index_entries([
        IndexEntry(id="e1", path="/a", text="Login button practices",
                   title="Login button", tags=["login"]),
        IndexEntry(id="e2", path="/b", text="Checkout flow",
                   title="Checkout", tags=["checkout"]),
    ])
    assert r.stats["bm25_active"] is False
    hits = r.search("login button")
    assert hits and hits[0]["entry"].id == "e1"
    assert hits[0]["signals"]["bm25"] == 0.0
    print(f"  ✓ R1  bm25 inactive ({r.stats['indexed']} < {BM25_THRESHOLD})")


def R2_bm25_kicks_in_at_threshold():
    section("R2 bm25 activates above threshold")
    r = HybridRetriever()
    # Synthesize 250 entries; only one mentions the target keyword
    entries = []
    for i in range(BM25_THRESHOLD + 50):
        if i == 0:
            entries.append(IndexEntry(
                id=f"e{i}", path=f"/p{i}",
                text="Enterprise quote workflow",
                title=f"PC quote {i}",
                tags=["enterprise"]))
        else:
            # Generic noise documents
            entries.append(IndexEntry(
                id=f"e{i}", path=f"/p{i}",
                text=f"Generic doc number {i} about web testing forms",
                title=f"Doc {i}",
                tags=["misc"]))
    r.index_entries(entries)
    assert r.stats["bm25_active"] is True
    hits = r.search("enterprise quote workflow", top_k=3)
    assert hits, "expected at least one hit"
    assert hits[0]["entry"].id == "e0", \
        f"expected e0 first; got {hits[0]['entry'].id}"
    assert hits[0]["signals"]["bm25"] > 0
    print(f"  ✓ R2  bm25 active ({r.stats['indexed']} >= {BM25_THRESHOLD}); top hit e0")


def R3_substring_beats_unrelated_bm25():
    section("R3 substring rare-keyword hit ranks high in hybrid")
    r = HybridRetriever()
    entries = []
    # 250 docs about login
    for i in range(BM25_THRESHOLD + 50):
        entries.append(IndexEntry(
            id=f"e{i}", path=f"/p{i}",
            text="login form authentication test",
            title=f"login {i}", tags=["login"]))
    # ONE rare doc that uniquely contains "ZQX_TOKEN"
    entries[42] = IndexEntry(
        id="rare", path="/r",
        text="login with ZQX_TOKEN special handling",
        title="login rare", tags=["login"])
    r.index_entries(entries)
    hits = r.search("ZQX_TOKEN", top_k=3)
    assert hits and hits[0]["entry"].id == "rare", \
        f"expected 'rare' first, got: {[h['entry'].id for h in hits]}"
    print("  ✓ R3  rare-keyword hit ranks first")


def R4_scope_filter():
    section("R4 scope filter narrows results")
    r = HybridRetriever()
    r.index_entries([
        IndexEntry(id="g1", path="/a", text="Login basic", title="login",
                   scope="global"),
        IndexEntry(id="p1", path="/b", text="Login project specific",
                   title="login", scope="project"),
        IndexEntry(id="i1", path="/c", text="Login industry specific",
                   title="login", scope="industry"),
    ])
    hits = r.search("login", scope=["project"])
    ids = [h["entry"].id for h in hits]
    assert ids == ["p1"], f"got: {ids}"
    print("  ✓ R4  scope filter")


def R5_tag_filter():
    section("R5 tag filter narrows results")
    r = HybridRetriever()
    r.index_entries([
        IndexEntry(id="a", path="/a", text="login", title="x", tags=["red"]),
        IndexEntry(id="b", path="/b", text="login", title="x", tags=["blue"]),
        IndexEntry(id="c", path="/c", text="login", title="x", tags=["red", "extra"]),
    ])
    hits = r.search("login", tags=["red"])
    ids = sorted(h["entry"].id for h in hits)
    assert ids == ["a", "c"], f"got: {ids}"
    print("  ✓ R5  tag filter")


def R6_index_dirs():
    section("R6 index_dirs reads markdown files")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        kdir = td / "knowledge"
        kdir.mkdir()
        (kdir / "page.md").write_text("# Login Page\n\nThe login flow.")
        (kdir / "_private.md").write_text("# Skip\n")  # underscore = skipped
        (kdir / "irrelevant.md").write_text("# Checkout\n\nCart and coupons.")
        r = HybridRetriever()
        r.index_dirs([kdir])
        ids = sorted(e.id for e in r.entries)
        assert "page.md" in ids
        assert "irrelevant.md" in ids
        assert "_private.md" not in ids
        hits = r.search("login")
        assert hits and "page.md" in hits[0]["entry"].id
        print(f"  ✓ R6  loaded {len(r.entries)} files; private skipped")


def R7_empty_query_returns_empty():
    section("R7 empty query → []")
    r = HybridRetriever()
    r.index_entries([IndexEntry(id="a", path="/a", text="x", title="x")])
    assert r.search("") == []
    assert r.search("   ") == []
    print("  ✓ R7")


if __name__ == "__main__":
    tests = [R1_substring_only_below_threshold,
             R2_bm25_kicks_in_at_threshold,
             R3_substring_beats_unrelated_bm25,
             R4_scope_filter, R5_tag_filter,
             R6_index_dirs, R7_empty_query_returns_empty]
    print("=" * 60)
    print("Hybrid retrieval test suite")
    print("=" * 60)
    for t in tests:
        t()
    print()
    print("=" * 60)
    print(f"All retrieval tests passed ({len(tests)}/{len(tests)}) ✅")
    print("=" * 60)
