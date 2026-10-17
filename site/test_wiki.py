"""python3 -m unittest site.test_wiki  (or run it directly): the wiki page rules and renderer."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def page(author="ai"):
    d = {
        "tagline": "Steer a lantern through a sleeping town.",
        "overview": "A calm puzzle game. " * 12,
        "story": "The town forgot how to wake up. " * 6,
        "goal": "Light every window before dawn; you lose if the lantern goes out.",
        "rules": ["Windows light when the lantern is near.", "Wind blows the flame out.", "Shelter behind walls to refill."],
        "controls": [{"input": "Arrow keys", "action": "Move"}],
        "characters": [{"name": "Lantern", "role": "You", "description": "A small flame in a jar.", "image": "c1.png"}],
        "gallery": [{"image": f"g{i}.png", "caption": f"Moment {i}"} for i in range(3)],
    }
    d.update({"why_made": "I wanted a game about gentle pressure instead of danger, because most scheduled games were frantic. " * 2} if author == "ai" else {"prompt": "Make a calm puzzle game."})
    return d


class Wiki(unittest.TestCase):
    def folder(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        for n in ("c1", "g0", "g1", "g2"):
            Path(t.name, n + ".png").write_bytes(PNG)
        return Path(t.name)

    def test_a_complete_page_passes_for_both_kinds_of_author(self):
        f = self.folder()
        self.assertEqual(wiki.problems(page("ai"), "ai", f), [])
        self.assertEqual(wiki.problems(page("human"), "human", f), [])

    def test_the_author_specific_field_is_required(self):
        f = self.folder()
        self.assertTrue(any("why_made" in p for p in wiki.problems(page("human"), "ai", f)))
        self.assertTrue(any("prompt" in p for p in wiki.problems(page("ai"), "human", f)))

    def test_missing_or_thin_content_and_pictures_are_reported(self):
        f = self.folder(); d = page()
        d["overview"] = "short"; d["rules"] = ["one"]; d["gallery"] = d["gallery"][:2]; d["characters"][0]["image"] = "nope.png"
        got = " | ".join(wiki.problems(d, "ai", f))
        for must in ("overview", "rules", "gallery", "character `Lantern`"):
            self.assertIn(must, got)
        d = page(); d["gallery"][1]["image"] = "g0.png"
        self.assertTrue(any("repeats" in p for p in wiki.problems(d, "ai", f)))
        (f / "g1.png").write_bytes(b"not a png")
        self.assertTrue(any("gallery picture 2" in p for p in wiki.problems(page(), "ai", f)))

    def test_the_page_renders_every_section_and_escapes_text(self):
        d = page(); d["story"] = "<script>x</script> " * 20
        h = wiki.render(d, "ai")
        for must in ("Overview", "Story", "How to play", "Characters", "Gallery", "Why this game exists", 'href="#gallery"', 'src="c1.png"'):
            self.assertIn(must, h)
        self.assertNotIn("<script>", h)
        self.assertIn("The prompt", wiki.render(page("human"), "human"))


if __name__ == "__main__":
    unittest.main()
