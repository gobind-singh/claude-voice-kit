"""Fast unit tests (no audio, no models, no network). Run: python3 -m unittest discover tests"""
import importlib.machinery, importlib.util, json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "packages", "listen-voice"), os.path.join(ROOT, "packages", "kokoro-voice"),
                os.path.join(ROOT, "claude"), os.path.join(ROOT, "claude", "hooks")]
os.environ["VOICEKIT_STATE_DIR"] = tempfile.mkdtemp()
os.environ["VOICEKIT_CONFIG_DIR"] = tempfile.mkdtemp()


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Polish(unittest.TestCase):
    def test_punctuation_and_case(self):
        from polish import polish
        self.assertEqual(polish("do everything plan for all "), "Do everything plan for all.")
        self.assertEqual(polish("  is it done"), "Is it done?")
        self.assertEqual(polish("what's happening"), "What's happening?")
        self.assertEqual(polish("do you know"), "Do you know?")
        self.assertEqual(polish("i think it works , right"), "I think it works, right?")

    def test_vocabulary(self):
        from polish import polish
        self.assertEqual(polish("tell harder to run the tests", ["herdr"], {"harder": "herdr"}),
                         "Tell herdr to run the tests.")


class MarkdownToSpeech(unittest.TestCase):
    def test_blocks(self):
        voiced = load("voiced", "packages/kokoro-voice/voiced.py")
        md = "## Plan\n- step **one**\n```\ncode\n```\n| Key | Does |\n|---|---|\n| ⌃⌥F | full read |\nSee /opt/project/src/a/file.md"
        blocks = voiced.to_blocks(md)
        texts = [t for t, _ in blocks]
        self.assertEqual(blocks[0], ("Plan.", True))
        self.assertIn("step one", texts)
        self.assertIn("Code block skipped.", texts)
        self.assertIn("Key: Control Option F, Does: full read.", texts)
        self.assertIn("See file.md", texts)


try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed (run with packages/listen-voice/.venv/bin/python)")
class WakePhrase(unittest.TestCase):
    def test_handle_phrase(self):
        listend = load("listend", "packages/listen-voice/listend.py")
        base = listend.config
        listend.config = lambda: {**base(), "wake": {**base()["wake"], "command": [], "barge_in_command": [],
                                                     "chime": ""}}
        self.assertEqual(listend.handle_phrase("Hey Claude, what's happening?"), ("command", "What's happening?"))
        self.assertEqual(listend.handle_phrase("Stop."), ("barge_in", "stop"))
        self.assertEqual(listend.handle_phrase("The build finished and Claude needs you.")[0], "ignored")
        self.assertEqual(listend.handle_phrase("Hey Claude."), ("wake", ""))
        self.assertEqual(listend.handle_phrase("Tell api to run the tests.")[0], "command")


class Approval(unittest.TestCase):
    def test_describe_and_risk(self):
        va = load("voice_approval", "claude/hooks/voice_approval.py")
        self.assertEqual(va.short_paths(va.describe("Bash", {"command": "rm /a/b/c/x.txt"})), "run rm x.txt")
        self.assertEqual(va.describe("ExitPlanMode", {"plan": "x"}), "approve the plan")
        pats = json.loads(json.dumps(load("vkc", "claude/voicekit_common.py").DEFAULTS["control"]["risky_patterns"]))
        self.assertTrue(va.is_risky("git push --force", pats))
        self.assertFalse(va.is_risky("npm test", pats))


class Router(unittest.TestCase):
    def test_resolve_names(self):
        vc = load("voicectl", "claude/voicectl")
        sess = [{"session_id": "s1", "name": "api", "state": "idle", "updated": 1},
                {"session_id": "s2", "name": "docs", "state": "waiting", "updated": 2},
                {"session_id": "s3", "name": "api 2", "state": "idle", "updated": 3}]
        self.assertEqual(vc.resolve("docs", sess)["session_id"], "s2")
        self.assertEqual(vc.resolve("s3", sess)["session_id"], "s3")          # exact id (notification buttons)
        self.assertEqual(vc.resolve("agent 2", sess)["session_id"], "s2")
        self.assertIsNone(vc.resolve("nonexistent thing", sess))


class ReviewFixes(unittest.TestCase):
    """Regressions for the code review: approvals must never reach the wrong or an expired request."""

    def setUp(self):
        self.vc = load("voicectl", "claude/voicectl")
        self.vk = load("vkc2", "claude/voicekit_common.py")
        os.makedirs(self.vk.PENDING_DIR, exist_ok=True)

    def _pending(self, rid, age=0, risky=False):
        p = {"id": rid, "session_id": "s1", "name": "api", "desc": "run rm x", "risky": risky,
             "created": __import__("time").time() - age}
        p["expires"] = p["created"] + 20
        with open(os.path.join(self.vk.PENDING_DIR, rid + ".json"), "w") as f:
            json.dump(p, f)

    def test_button_answers_only_its_own_live_request(self):
        vc = self.vc
        self._pending("live-1")
        with self.assertRaises(vc.Reply) as r:
            vc.answer_request("live-1", "deny")
        self.assertEqual(r.exception.text, "Denied.")
        self.assertTrue(os.path.exists(os.path.join(self.vk.PENDING_DIR, "live-1.decision")))
        with self.assertRaises(vc.Reply) as r:
            vc.answer_request("gone-2", "allow")
        self.assertFalse(r.exception.ok)                      # unknown request: nothing is approved

    def test_expired_requests_are_ignored_and_removed(self):
        self._pending("old-3", age=120)
        self.assertNotIn("old-3", [p["id"] for p in self.vc.pending_approvals()])
        self.assertFalse(os.path.exists(os.path.join(self.vk.PENDING_DIR, "old-3.json")))

    def test_bare_always_does_not_skip_the_risky_check(self):
        vc = self.vc
        self._pending("risky-4", risky=True)
        with self.assertRaises(vc.Reply) as r:
            vc.do_approve("always", None, [], said_yes=False)
        self.assertIn("risky", r.exception.text)
        os.remove(os.path.join(self.vk.PENDING_DIR, "risky-4.json"))

    def test_window_route_needs_a_verified_tab(self):
        ad = load("adapters2", "claude/adapters.py")
        self.assertFalse(ad.front_tab_is({"terminal": {"app_bundle": "com.mitchellh.ghostty", "tty": "/dev/ttys001"}}))
        self.assertFalse(ad.front_tab_is({"terminal": {"app_bundle": "com.apple.Terminal"}}))   # no tty known


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class EchoGuard(unittest.TestCase):
    def test_own_speech_is_ignored_but_stop_still_works(self):
        listend = load("listend2", "packages/listen-voice/listend.py")
        base = listend.config
        listend.config = lambda: {**base(), "wake": {**base()["wake"], "command": [], "barge_in_command": [],
                                                     "chime": "", "busy_command": ["true"]}}   # "speakers busy"
        self.assertEqual(listend.handle_phrase("Hey Claude, approve.")[0], "ignored")
        self.assertEqual(listend.handle_phrase("Stop.")[0], "barge_in")


class Installer(unittest.TestCase):
    """Regression: hooks from a copy in another folder must be recognised, replaced and removed, and a
    missing hook script must never block Claude Code (exit code 2 = block)."""

    def setUp(self):
        self.vk = load("voicekit_bin", "bin/voicekit")

    def test_recognises_hooks_in_any_folder(self):
        vk = self.vk
        self.assertTrue(vk.is_ours(vk.hook_cmd("/any/folder/name/claude/hooks/session_event.py")))
        self.assertTrue(vk.is_ours('python3 "/tmp/fresh/claude/hooks/speak_alert.py"'))      # older format
        self.assertFalse(vk.is_ours("node /opt/other-tool/hooks/claude-hook.js"))
        self.assertFalse(vk.is_ours("sh ~/.other/agent-hooks/claude-hook.sh"))

    def test_hook_never_blocks(self):
        import subprocess
        cmd = self.vk.hook_cmd("/no/such/folder/claude/hooks/session_event.py")
        self.assertEqual(subprocess.run(["sh", "-c", cmd], capture_output=True).returncode, 0)

    def test_detects_missing_scripts(self):
        vk = self.vk
        d = {"hooks": {"Stop": [{"hooks": [{"command": vk.hook_cmd("/no/such/x/claude/hooks/speak_summary.py")},
                                            {"command": "echo ok"}]}]}}
        self.assertEqual(len(vk.missing_hook_scripts(d)), 1)

    def test_strip_replaces_only_ours(self):
        vk = self.vk
        d = {"hooks": {"Stop": [{"matcher": "", "hooks": [{"command": vk.hook_cmd("/a/claude/hooks/speak_summary.py")}]},
                                {"matcher": "", "hooks": [{"command": "node other.js"}]}]}}
        out = vk.strip_our_hooks(d)
        self.assertEqual([h["command"] for e in out["hooks"]["Stop"] for h in e["hooks"]], ["node other.js"])


if __name__ == "__main__":
    unittest.main()
