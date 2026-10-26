#!/usr/bin/env python3
"""Unit tests for the magpie-optimizer public release self-check scripts.

Covered modules
    * ``magpie_preflight.py``     -- ``parse_agent_lines``,
      ``detect_loopback_hosts``, ``summarize_checks``, ``extract_version``,
      ``has_proxy``, ``is_vendor_host``, ``safe_gateway_label``
    * ``magpie_inventory.py``     -- ``mask_account``,
      ``single_source_tiers``, ``account_order_unset``
    * ``public_release_check.py`` -- ``find_secret_matches``,
      ``find_personal_emails``, ``find_home_paths``, ``markdown_links``,
      ``check_markdown_links``, ``check_json_samples``,
      ``gitignore_covers``, ``latest_changelog_version``,
      ``skill_frontmatter_version``, ``check_version_consistency``

Environment independence
    The suite never calls the real ``magpie`` CLI, never opens a socket and
    never reads ``~/.config/magpie``.  Every fixture is synthetic: either
    built in memory or created inside a ``tempfile.TemporaryDirectory()``.
    The whole file therefore runs green on a machine without Magpie, without
    a local gateway and without network access, and it produces the same
    result on every run.

Self-scanning safety
    This file is itself scanned by ``public_release_check.py`` before the
    Skill is published.  Therefore no mail address, no credential-shaped
    assignment and no machine-local home path is stored here as a literal:
    the samples that must look like a credential or like a home directory
    are composed at runtime from fragments (see the ``_join``/``_address``
    helpers), so the scanner finds no match in the source text.  All of
    them are synthetic placeholders and describe no real account.

Read-only boundary
    The tests only read the sibling scripts and write inside a temporary
    directory.  They never modify the Skill tree, never touch the Magpie
    configuration, never change the gateway and never issue a model
    request, so no quota is consumed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load(name):
    """Import a sibling module.

    A module that cannot be imported is an error, not a reason to skip the
    whole group: a silently skipped suite would report "green" while the
    required behaviour is not covered at all.  The import failure is
    recorded and re-raised by :func:`test_required_modules_import`.
    """
    try:
        return __import__(name), None
    except Exception as error:  # pragma: no cover - only hit on a broken tree
        return None, error


inventory, INVENTORY_IMPORT_ERROR = _load("magpie_inventory")
preflight, PREFLIGHT_IMPORT_ERROR = _load("magpie_preflight")
release, RELEASE_IMPORT_ERROR = _load("public_release_check")

REQUIRED_MODULE_ERRORS = {
    "magpie_inventory": INVENTORY_IMPORT_ERROR,
    "magpie_preflight": PREFLIGHT_IMPORT_ERROR,
    "public_release_check": RELEASE_IMPORT_ERROR,
}


def _required_missing(module_name, module, *names):
    """Return the required names that the module does not provide.

    A missing name is a broken candidate, not an optional capability.
    """
    if module is None:
        return list(names)
    return [name for name in names if not callable(getattr(module, name, None))]


def _supports(module, *names):
    if module is None:
        return False
    return all(callable(getattr(module, name, None)) for name in names)


HAS_MASK = _supports(inventory, "mask_account")
HAS_SOURCES = _supports(inventory, "single_source_tiers")
HAS_ORDER = _supports(inventory, "account_order_unset")
HAS_AGENT_LINES = _supports(preflight, "parse_agent_lines")
HAS_LOOPBACK = _supports(preflight, "detect_loopback_hosts")
HAS_SUMMARY = _supports(preflight, "summarize_checks")
HAS_EXTRACT_VERSION = _supports(preflight, "extract_version")
HAS_HAS_PROXY = _supports(preflight, "has_proxy")
HAS_VENDOR_HOST = _supports(preflight, "is_vendor_host")
HAS_GATEWAY_LABEL = _supports(preflight, "safe_gateway_label")
HAS_SECRETS = _supports(release, "find_secret_matches")
HAS_EMAILS = _supports(release, "find_personal_emails")
HAS_HOME_PATHS = _supports(release, "find_home_paths")
HAS_LINKS = _supports(release, "markdown_links")
HAS_MD_LINK_CHECK = _supports(release, "check_markdown_links")
HAS_JSON_CHECK = _supports(release, "check_json_samples")
HAS_IGNORE = _supports(release, "gitignore_covers")
HAS_CHANGELOG = _supports(release, "latest_changelog_version")
HAS_FRONTMATTER = _supports(release, "skill_frontmatter_version")
HAS_VERSION_CHECK = _supports(release, "check_version_consistency")
HAS_RELEASE_SCRIPT = (SCRIPTS_DIR / "public_release_check.py").is_file()


# --------------------------------------------------------------------------
# Synthetic sample builders.
#
# Every value below is a placeholder.  The fragments are joined at runtime
# so that this test file never contains a literal credential shape, a
# complete mail address or a machine-local absolute path: the release gate
# scans the published tree and would otherwise flag the test file itself.
# --------------------------------------------------------------------------

def _join(parts):
    """Join fragments into one runtime-only sample string."""
    return "".join(parts)


def _address(local, domain):
    """Compose a mail address at runtime (never stored as a literal)."""
    return local + "@" + domain


def _home_path(name):
    """Compose a home-directory path at runtime (never stored literally)."""
    return "/Users" + "/" + name


# Credential-shaped samples: each one must be detected by the scanner.
SK_SAMPLE = _join(("sk-", "SYNTHETICPLACEHOLDER"))
API_KEY_SAMPLE = _join(("api", "_key", " = ", "SYNTHETIC-VALUE-9f3a"))
BEARER_SAMPLE = _join(("Author", "ization: Bear", "er ", "SYNTHETICTOKEN123456"))
PASSWORD_SAMPLE = _join(("pass", "word: ", "SYNTHETIC-PASS-7b2c"))
PRIVATE_KEY_SAMPLE = _join(("-----BEGIN ", "PRIVATE KEY-----"))
SHORT_SK_SAMPLE = _join(("sk-", "abc"))
# A harmless sentence that mentions the keywords but assigns nothing.
PLAIN_SAMPLE = "This line mentions an api key and a password in plain prose."

# Mail samples: one complete address that must be reported, plus the
# placeholder domains that must stay silent.
REPORTED_MAIL = _address("sampleuser", "notreal-company.test")
PLACEHOLDER_MAILS = (
    _address("someone", "example.com"),
    _address("someone", "example.invalid"),
    _address("someone", "example.org"),
    _address("someone", "service.localhost"),
)
MASKED_MAIL = _join(("sa", "****", "le", "@", "example.invalid"))

# Home path samples.
HOME_SAMPLE = _home_path("exampleuser")
SYSTEM_PATH_SAMPLE = "/usr/local/bin"

# Placeholder credential values must not be reported: the release gate
# treats a documented placeholder as harmless.
PLACEHOLDER_API_KEY_SAMPLE = _join(("api", "_key", " = ", "YOUR_KEY_HERE"))
PLACEHOLDER_BRACKET_SAMPLE = _join(("api", "_key", " = ", "<your-key>"))
# A documentation sentence that only names the field must not be reported.
FIELD_NAME_SAMPLE = "The api_key field stores the credential in the provider panel."

# A skill-relative path and a home-relative path are not machine-local
# absolute paths.
SKILL_DIR_SAMPLE = _join(("<skill", "-dir>", "/references/guide.md"))
TILDE_SAMPLE = _join(("~", "/Library/Application Support/example"))


class ProfileRiskTests(unittest.TestCase):
    def test_profile_expensive_models_reads_current_and_legacy_fields(self):
        current = {"constraints": {"expensive_models": ["example/strong", "other/strong"]}}
        legacy = {"expensive_models": ["legacy/strong"], "cost": {"premium": ["legacy/premium"]}}
        self.assertEqual(inventory.profile_expensive_models(current),
                         ["example/strong", "other/strong"])
        self.assertEqual(inventory.profile_expensive_models(legacy),
                         ["legacy/strong", "legacy/premium"])

class MaskAccountTests(unittest.TestCase):
    """Neither account aliases nor email fragments belong in the report."""

    def test_mail_local_part_is_masked(self):
        value = _address("sampleuser", "163.example")
        self.assertEqual(inventory.mask_account(value), inventory.REDACTED)

    def test_short_local_part_is_masked(self):
        for local in ("a", "ab"):
            self.assertEqual(inventory.mask_account(_address(local, "example.invalid")),
                             inventory.REDACTED)

    def test_already_masked_address_hides_domain(self):
        self.assertEqual(inventory.mask_account(MASKED_MAIL), inventory.REDACTED)

    def test_display_name_is_masked(self):
        self.assertEqual(inventory.mask_account("Synthetic Alias"), inventory.REDACTED)

    def test_non_ascii_display_name_is_masked(self):
        for alias in ("合成账号甲", "合成账号乙", "Team Account"):
            self.assertEqual(inventory.mask_account(alias), inventory.REDACTED)

    def test_api_key_label_is_masked(self):
        self.assertEqual(inventory.mask_account("API key"), inventory.REDACTED)

    def test_long_credential_blob_is_redacted(self):
        blob = "0123456789abcdef" * 5
        self.assertEqual(inventory.mask_account(blob), inventory.REDACTED)

    def test_empty_and_non_string_values_are_safe(self):
        for value in ("", "  ", None, [], {}):
            self.assertEqual(inventory.mask_account(value), "")

    def test_scan_local_labels_preserve_distinct_accounts(self):
        labels = {}
        first = inventory.mask_account("Synthetic Alias A", labels)
        second = inventory.mask_account("Synthetic Alias B", labels)
        self.assertEqual(first, inventory.mask_account("Synthetic Alias A", labels))
        self.assertNotEqual(first, second)
        self.assertEqual([first, second], ["account-1", "account-2"])
        self.assertEqual(inventory.mask_account("Another Alias", {}), "account-1")

    def test_provider_report_hides_identity_but_keeps_counts(self):
        alias = "SYNTHETIC_PRIVATE_ALIAS"
        email = _address("synthetic-user", "private.example")
        providers, _ = inventory.build_providers(
            None, {"providers": [{"id": "example", "models": ["model"],
                                   "key": "SYNTHETIC_CREDENTIAL"}]},
            [{"agent": "example", "user": alias}, {"agent": "example", "user": email}],
            [], {}, {}, [])
        encoded = json.dumps(providers)
        for private in (alias, email, "private.example", "SYNTHETIC_CREDENTIAL"):
            self.assertNotIn(private, encoded)
        self.assertEqual(providers[0]["accounts"], 2)
        self.assertTrue(providers[0]["multi_account"])
        self.assertEqual(providers[0]["account_labels"], ["account-1", "account-2"])

    def test_cli_account_fallback_is_labeled(self):
        providers, _ = inventory.build_providers(
            None, {"providers": [{"id": "example", "models": []}]}, None,
            [{"id": "example", "account": "SYNTHETIC_FALLBACK_ALIAS"}], {}, {}, [])
        self.assertEqual(providers[0]["account_labels"], ["account-1"])
        self.assertNotIn("SYNTHETIC_FALLBACK_ALIAS", json.dumps(providers))

    def test_account_order_set_is_three_state(self):
        def provider(order):
            return {"id": "example", "models": [], "accountOrder": order}
        for order, expected in ((None, None), ([], False), (["account-a"], True)):
            with self.subTest(order=order):
                providers, _ = inventory.build_providers(
                    None, {"providers": [provider(order)]}, [], [], {}, {}, [])
                self.assertEqual(providers[0]["account_order_set"], expected)


class SingleSourceTierTests(unittest.TestCase):
    """A tier with more than one servable source is not single-source."""

    def test_all_servable_members_are_not_single_source(self):
        members = ["provider/one", "provider/two", "provider/three"]
        servable = {name: True for name in members}
        self.assertEqual(inventory.single_source_tiers(members, servable, {}), [])

    def test_only_servable_member_is_reported(self):
        members = ["provider/one", "provider/two", "provider/three"]
        servable = {"provider/one": True, "provider/two": False,
                    "provider/three": False}
        self.assertEqual(inventory.single_source_tiers(members, servable, {}),
                         ["provider/one"])

    def test_nested_group_with_two_sources_is_not_single_source(self):
        members = ["group/nested"]
        servable = {"provider/one": True, "provider/two": True}
        group_index = {"group/nested": ["provider/one", "provider/two"]}
        self.assertEqual(inventory.single_source_tiers(members, servable, group_index), [])

    def test_nested_group_with_one_source_is_reported(self):
        members = ["group/nested"]
        servable = {"provider/one": True, "provider/two": False}
        group_index = {"group/nested": ["provider/one", "provider/two"]}
        self.assertEqual(inventory.single_source_tiers(members, servable, group_index),
                         ["group/nested"])

    def test_same_provider_two_accounts_is_not_single_source(self):
        # NOTE: 待第二小包（MP-013-SCRIPTS-B）。
        # This case only exercises two *member ids*.  Whether one provider
        # with two accounts counts as one source or two is a separate
        # question that the current API does not answer, so this test does
        # not derive "model == account" from the member text.
        members = ["provider/one", "provider/two"]
        servable = {"provider/one": True, "provider/two": True}
        self.assertEqual(inventory.single_source_tiers(members, servable, {}), [])

    def test_nested_group_and_direct_member_is_not_single_source(self):
        # A nested group contributes as many sources as it has servable
        # members, so one nested source plus one direct member is two.
        members = ["group/nested", "provider/direct"]
        servable = {"provider/one": True, "provider/direct": True}
        group_index = {"group/nested": ["provider/one"]}
        self.assertEqual(inventory.single_source_tiers(members, servable, group_index), [])

    def test_result_is_a_list_of_member_names(self):
        members = ["provider/one"]
        result = inventory.single_source_tiers(members, {"provider/one": True}, {})
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(item, str) for item in result))


class AccountOrderTests(unittest.TestCase):
    """Multi-account providers without an explicit order are reported."""

    def test_single_account_provider_is_not_reported(self):
        providers = [{"id": "solo", "accountConcurrency": {"account-a": 2}}]
        self.assertEqual(inventory.account_order_unset(providers), [])

    def test_multi_account_with_order_is_not_reported(self):
        providers = [{"id": "ordered",
                      "accountConcurrency": {"account-a": 2, "account-b": 2},
                      "accountOrder": ["account-a", "account-b"]}]
        self.assertEqual(inventory.account_order_unset(providers), [])

    def test_multi_account_without_order_is_reported(self):
        providers = [{"id": "unordered",
                      "accountConcurrency": {"account-a": 2, "account-b": 2}}]
        self.assertEqual(inventory.account_order_unset(providers), ["unordered"])

    def test_empty_account_order_is_reported(self):
        providers = [{"id": "blank-order",
                      "accountConcurrency": {"account-a": 2, "account-b": 2},
                      "accountOrder": []}]
        self.assertEqual(inventory.account_order_unset(providers), ["blank-order"])


class SecretDetectionTests(unittest.TestCase):
    """Credential shapes must be reported with their line number and rule."""

    def _codes(self, text):
        return [rule for _line, rule in release.find_secret_matches(text)]

    def test_sk_prefix_sample_is_detected(self):
        self.assertEqual(self._codes(SK_SAMPLE), ["sk_prefix"])

    def test_api_key_assignment_sample_is_detected(self):
        self.assertEqual(self._codes(API_KEY_SAMPLE), ["api_key_assignment"])

    def test_bearer_header_sample_is_detected(self):
        self.assertEqual(self._codes(BEARER_SAMPLE), ["bearer_token"])

    def test_password_assignment_sample_is_detected(self):
        self.assertEqual(self._codes(PASSWORD_SAMPLE), ["credential_assignment"])

    def test_private_key_block_is_detected(self):
        self.assertEqual(self._codes(PRIVATE_KEY_SAMPLE), ["private_key_block"])

    def test_plain_prose_is_not_reported(self):
        self.assertEqual(self._codes(PLAIN_SAMPLE), [])

    def test_short_sk_prefix_is_not_reported(self):
        self.assertEqual(self._codes(SHORT_SK_SAMPLE), [])

    def test_hit_carries_line_number_and_rule_code(self):
        text = "first line is harmless\n" + SK_SAMPLE + "\n"
        self.assertEqual(release.find_secret_matches(text), [(2, "sk_prefix")])

    def test_placeholder_value_is_not_reported(self):
        # A documented placeholder is harmless in any file.
        self.assertEqual(self._codes(PLACEHOLDER_API_KEY_SAMPLE), [])
        self.assertEqual(self._codes(PLACEHOLDER_BRACKET_SAMPLE), [])

    def test_field_name_without_value_is_not_reported(self):
        self.assertEqual(self._codes(FIELD_NAME_SAMPLE), [])

    def test_empty_text_is_not_reported(self):
        self.assertEqual(release.find_secret_matches(""), [])
        self.assertEqual(release.find_secret_matches("\n\n"), [])


class EmailDetectionTests(unittest.TestCase):
    """Complete addresses are reported; placeholders and masks are not."""

    def test_complete_address_is_reported(self):
        hits = release.find_personal_emails("owner is " + REPORTED_MAIL)
        self.assertEqual(hits, [(1, REPORTED_MAIL)])

    def test_placeholder_domains_are_not_reported(self):
        for address in PLACEHOLDER_MAILS:
            with self.subTest(address=address):
                self.assertEqual(release.find_personal_emails(address), [])

    def test_masked_address_is_not_reported(self):
        self.assertEqual(release.find_personal_emails(MASKED_MAIL), [])

    def test_domain_without_dot_is_not_reported(self):
        self.assertEqual(release.find_personal_emails("a@invalid"), [])
        self.assertEqual(release.find_personal_emails("a@example"), [])

    def test_localhost_domain_is_not_reported(self):
        self.assertEqual(release.find_personal_emails("host at " + _address("dev", "localhost")), [])


class HomePathTests(unittest.TestCase):
    """Machine-local absolute paths are reported, system paths are not."""

    def test_home_path_is_reported(self):
        text = "config lives in " + HOME_SAMPLE + "/config.toml"
        self.assertEqual(release.find_home_paths(text), [(1, HOME_SAMPLE)])

    def test_system_path_is_not_reported(self):
        self.assertEqual(release.find_home_paths(SYSTEM_PATH_SAMPLE), [])

    def test_skill_relative_and_home_relative_paths_are_not_reported(self):
        self.assertEqual(release.find_home_paths(SKILL_DIR_SAMPLE), [])
        self.assertEqual(release.find_home_paths(TILDE_SAMPLE), [])


class MarkdownLinkTests(unittest.TestCase):
    """Only relative link targets belong to the published tree."""

    def test_relative_links_are_collected(self):
        text = "[a](docs/guide.md) [b](references/notes.md) [c](docs/guide.md)"
        self.assertEqual(release.markdown_links(text),
                         ["docs/guide.md", "references/notes.md"])

    def test_external_and_anchor_links_are_skipped(self):
        text = "[a](https://example.com/page) [b](http://example.com/page) [c](#section)"
        self.assertEqual(release.markdown_links(text), [])

    def test_reachable_relative_link_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.md").write_text("# Notes\n", encoding="utf-8")
            self.assertEqual(release.check_markdown_links("doc.md", "[present](notes.md)", root), [])

    def test_broken_relative_link_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            findings = release.check_markdown_links("doc.md", "[absent](missing.md)", root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["code"], "MARKDOWN_LINKS")
            self.assertEqual(findings[0]["severity"], "fail")

    def test_external_and_anchor_links_are_not_broken_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = "[a](https://example.com/page) [b](#section)"
            self.assertEqual(release.check_markdown_links("doc.md", text, root), [])

    def test_non_markdown_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(release.check_markdown_links("data.json", "[a](missing.md)", root), [])


class JsonSampleTests(unittest.TestCase):
    """Sample and schema files must parse as JSON."""

    def test_valid_example_json_passes(self):
        self.assertEqual(release.check_json_samples("profile.example.json", '{"a": 1}\n'), [])

    def test_invalid_example_json_is_reported(self):
        findings = release.check_json_samples("profile.example.json", '{"a": ')
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "EXAMPLE_JSON_VALID")
        self.assertEqual(findings[0]["severity"], "fail")

    def test_invalid_schema_json_is_reported(self):
        findings = release.check_json_samples("profile.schema.json", "{")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "SCHEMA_JSON_VALID")

    def test_other_json_file_is_skipped(self):
        self.assertEqual(release.check_json_samples("data.json", "{"), [])


class GitignoreTests(unittest.TestCase):
    """The ignore list must cover local runtime artefacts."""

    def test_suffix_pattern_covers(self):
        self.assertTrue(release.gitignore_covers("state.local.json", ["*.local.*"]))
        self.assertFalse(release.gitignore_covers("state.json", ["*.local.*"]))

    def test_local_json_suffix_is_covered(self):
        self.assertTrue(release.gitignore_covers("profile.local.json", ["*.local.json"]))
        self.assertFalse(release.gitignore_covers("profile.json", ["*.local.json"]))

    def test_negated_pattern_re_enables_a_file(self):
        # A later '!' line cancels an earlier match.
        self.assertFalse(release.gitignore_covers(
            "profile.local.json", ["*.local.json", "!profile.local.json"]))

    def test_exact_name_covers(self):
        self.assertTrue(release.gitignore_covers("name.json", ["name.json"]))
        self.assertFalse(release.gitignore_covers("other.json", ["name.json"]))

    def test_directory_pattern_covers_children(self):
        self.assertTrue(release.gitignore_covers("state/", ["state/"]))
        self.assertTrue(release.gitignore_covers("state/session.json", ["state/"]))
        self.assertFalse(release.gitignore_covers("other/session.json", ["state/"]))


class VersionTests(unittest.TestCase):
    """The published version must be readable from CHANGELOG and SKILL.md."""

    CHANGELOG = (
        "# Changelog\n\n"
        "## [1.2.3] - 2026-01-05\n\n"
        "- first entry\n\n"
        "## [1.2.2] - 2026-01-01\n\n"
        "- older entry\n"
    )

    FRONTMATTER = (
        "---\n"
        "name: magpie-optimizer\n"
        "description: Read-only optimizer for the Magpie gateway.\n"
        "metadata:\n"
        "  version: 0.4.0\n"
        "---\n\n"
        "# Body\n"
    )

    def test_latest_changelog_version_is_found(self):
        self.assertEqual(release.latest_changelog_version(self.CHANGELOG), "1.2.3")

    def test_changelog_without_version_returns_none(self):
        self.assertIsNone(release.latest_changelog_version("# Changelog\n\nno version here\n"))

    def test_frontmatter_version_is_found(self):
        self.assertEqual(release.skill_frontmatter_version(self.FRONTMATTER), "0.4.0")

    def test_frontmatter_without_version_returns_none(self):
        self.assertIsNone(release.skill_frontmatter_version(
            "---\nname: magpie-optimizer\n---\n\n# Body\n"))

    def test_version_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "---\nname: synthetic-skill\nmetadata:\n  version: 1.0.0\n---\n\n# Body\n",
                encoding="utf-8")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [2.0.0] - 2026-01-05\n\n- entry\n", encoding="utf-8")
            findings = release.check_version_consistency(root, None)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["code"], "VERSION_CONSISTENT")
            self.assertEqual(findings[0]["severity"], "fail")

    def test_matching_versions_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "---\nname: synthetic-skill\nmetadata:\n  version: 1.0.0\n---\n\n# Body\n",
                encoding="utf-8")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [1.0.0] - 2026-01-05\n\n- entry\n", encoding="utf-8")
            self.assertEqual(release.check_version_consistency(root, None), [])


class PreflightPureTests(unittest.TestCase):
    """The preflight parsers must survive partial and malformed input."""

    LS_OUTPUT = (
        "  Codex   group/smart-split  ·  effort max  ·  subagents group/subagent-exec"
        "  ·  subagent model group/subagent-exec  ·  subagent effort high"
        "  ~/.codex/config.toml\n"
        "  Claude  group/claude  ·  effort high  ~/.claude/settings.json\n"
        "  Malformed line without any field\n"
    )

    HOSTS_TEXT = (
        "# synthetic hosts file\n"
        "127.0.0.1 localhost\n"
        "127.0.0.1 api.openai.com\n"
        "203.0.113.10 api.anthropic.com\n"
        "203.0.113.11 docs.example.org\n"
    )

    def test_agent_lines_are_parsed(self):
        rows = preflight.parse_agent_lines(self.LS_OUTPUT)
        self.assertEqual([row["name"] for row in rows], ["Codex", "Claude"])
        first = rows[0]
        self.assertEqual(first["model"], "group/smart-split")
        self.assertEqual(first["effort"], "max")
        self.assertEqual(first["subagent_model"], "group/subagent-exec")
        self.assertEqual(first["subagent_effort"], "high")
        self.assertEqual(rows[1]["effort"], "high")
        self.assertIsNone(rows[1]["subagent_model"])

    def test_malformed_agent_line_is_skipped(self):
        rows = preflight.parse_agent_lines(self.LS_OUTPUT)
        self.assertNotIn("Malformed", [row["name"] for row in rows])
        self.assertEqual(len(rows), 2)

    def test_only_loopback_vendor_hosts_are_detected(self):
        self.assertEqual(preflight.detect_loopback_hosts(self.HOSTS_TEXT),
                         ["api.openai.com"])

    def test_summary_counts_by_status(self):
        checks = [
            {"code": "MAGPIE_CLI", "status": "ok", "detail": "", "evidence": {}},
            {"code": "PROXY", "status": "warn", "detail": "", "evidence": {}},
            {"code": "GATEWAY", "status": "fail", "detail": "", "evidence": {}},
        ]
        self.assertEqual(preflight.summarize_checks(checks),
                         {"ok": 1, "warn": 1, "fail": 1})

    def test_summary_ignores_unknown_status(self):
        checks = [{"code": "OTHER", "status": "info", "detail": "", "evidence": {}}]
        self.assertEqual(preflight.summarize_checks(checks),
                         {"ok": 0, "warn": 0, "fail": 0})

    def test_summary_handles_empty_and_malformed_input(self):
        self.assertEqual(preflight.summarize_checks([]),
                         {"ok": 0, "warn": 0, "fail": 0})
        self.assertEqual(preflight.summarize_checks(None),
                         {"ok": 0, "warn": 0, "fail": 0})
        self.assertEqual(preflight.summarize_checks(["not-a-dict"]),
                         {"ok": 0, "warn": 0, "fail": 0})

    def test_extract_version_reads_the_version_number(self):
        self.assertEqual(preflight.extract_version("magpie 0.1.1330"), "0.1.1330")
        self.assertEqual(preflight.extract_version("magpie version 0.1.1307"), "0.1.1307")
        self.assertEqual(preflight.extract_version("1.2.3"), "1.2.3")

    def test_extract_version_returns_none_without_a_version(self):
        self.assertIsNone(preflight.extract_version("no version here"))
        self.assertIsNone(preflight.extract_version(""))
        self.assertIsNone(preflight.extract_version(None))

    def test_has_proxy_detects_a_configured_proxy(self):
        self.assertTrue(preflight.has_proxy("http://127.0.0.1:1082"))
        self.assertTrue(preflight.has_proxy("socks5://127.0.0.1:1080"))
        self.assertTrue(preflight.has_proxy("direct"))

    def test_has_proxy_treats_empty_values_as_no_proxy(self):
        for value in (None, False, "", "off", "none", "false", "0", "disabled"):
            with self.subTest(value=value):
                self.assertFalse(preflight.has_proxy(value))

    def test_is_vendor_host_separates_vendor_from_local_domains(self):
        for host in ("chatgpt.com", "openai.com", "api.openai.com"):
            with self.subTest(host=host):
                self.assertTrue(preflight.is_vendor_host(host))
        for host in ("localhost", "example.org", "myopenai.com", "openai.com.example.org"):
            with self.subTest(host=host):
                self.assertFalse(preflight.is_vendor_host(host))

    def test_safe_gateway_label_drops_credentials_and_path(self):
        label = preflight.safe_gateway_label(
            "http://user:password@gateway.example:3425/base?token=abc")
        self.assertNotIn("password", label)
        self.assertNotIn("user", label)
        self.assertNotIn("token", label)
        self.assertNotIn("base", label)
        self.assertEqual(label, "http://gateway.example:3425")

    def test_safe_gateway_label_keeps_a_plain_loopback_gateway(self):
        self.assertEqual(preflight.safe_gateway_label("http://127.0.0.1:3425"),
                         "http://127.0.0.1:3425")


class ReleaseCheckEndToEndTests(unittest.TestCase):
    """The published script must run on a tree and report real problems."""

    def _run_check(self, root):
        command = [sys.executable, str(SCRIPTS_DIR / "public_release_check.py"),
                   "check", "--root", str(root)]
        return subprocess.run(command, capture_output=True, text=True, timeout=120)

    def test_broken_sample_and_link_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.md").write_text(
                "# Synthetic doc\n\nSee [missing](docs/absent.md) for details.\n",
                encoding="utf-8")
            (root / "sample.example.json").write_text(
                '{"broken": \n', encoding="utf-8")
            result = self._run_check(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            codes = {finding["code"] for finding in report["findings"]}
            self.assertIn("EXAMPLE_JSON_VALID", codes)
            self.assertIn("MARKDOWN_LINKS", codes)

    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.md").write_text(
                "# Synthetic doc\n\nSee [present](notes.md).\n", encoding="utf-8")
            (root / "notes.md").write_text("# Notes\n", encoding="utf-8")
            (root / "sample.example.json").write_text(
                '{"ok": true}\n', encoding="utf-8")
            (root / "SKILL.md").write_text(
                "---\nname: synthetic-skill\nmetadata:\n  version: 1.2.3\n---\n\n# Body\n",
                encoding="utf-8")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [1.2.3] - 2026-01-05\n\n- first entry\n",
                encoding="utf-8")
            result = self._run_check(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _write_publishable_tree(self, root):
        """Build a minimal, valid tree shaped like the published Skill."""
        skill = root / "magpie-optimizer"
        (skill / "config").mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            "---\n"
            "name: magpie-optimizer\n"
            "description: Read-only optimizer for the Magpie gateway.\n"
            "metadata:\n"
            "  version: 1.0.0\n"
            "---\n\n"
            "# Body\n",
            encoding="utf-8")
        (skill / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [1.0.0] - 2026-01-05\n\n- first entry\n",
            encoding="utf-8")
        (skill / "config" / "profile.example.json").write_text(
            '{"schema": "magpie-profile.v1"}\n', encoding="utf-8")
        (skill / "config" / ".gitignore").write_text(
            "profile.local.json\nstate/\n", encoding="utf-8")
        return skill

    def test_minimal_publishable_tree_has_no_fail_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_publishable_tree(root)
            result = self._run_check(root)
            report = json.loads(result.stdout)
            fail_codes = {finding["code"] for finding in report["findings"]
                          if finding["severity"] == "fail"}
            self.assertEqual(fail_codes, set(),
                             "clean tree produced fail findings: "
                             + json.dumps(report["findings"], ensure_ascii=False))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_absolute_home_path_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self._write_publishable_tree(root)
            (skill / "doc.md").write_text(
                "The local config lives in " + HOME_SAMPLE + "/config.toml\n",
                encoding="utf-8")
            result = self._run_check(root)
            report = json.loads(result.stdout)
            codes = {finding["code"] for finding in report["findings"]}
            self.assertIn("ABSOLUTE_HOME_PATH", codes)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_scripts_expose_help_without_side_effects(self):
        scripts = ("magpie_preflight.py", "magpie_inventory.py",
                   "public_release_check.py")
        before = set(SCRIPTS_DIR.rglob("*.pyc"))
        for name in scripts:
            with self.subTest(script=name):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / name), "--help"],
                    capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
        # The release gate is the only script that scans a directory tree.
        gate = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "public_release_check.py"), "--help"],
            capture_output=True, text=True, timeout=60)
        self.assertIn("--root", gate.stdout)
        self.assertEqual(set(SCRIPTS_DIR.rglob("*.pyc")) - before, set())


class RequiredModuleTests(unittest.TestCase):
    """A broken candidate must fail loudly, never skip the whole group.

    Every module and every function listed here is part of the published
    contract.  If one of them cannot be imported or does not exist, the
    suite has to fail: a group of skipped tests would report a green run
    while the required behaviour is not covered at all.
    """

    REQUIRED = {
        "magpie_inventory": ("mask_account", "single_source_tiers",
                             "account_order_unset"),
        "magpie_preflight": ("parse_agent_lines", "detect_loopback_hosts",
                              "summarize_checks", "extract_version",
                              "has_proxy", "is_vendor_host",
                              "safe_gateway_label"),
        "public_release_check": ("find_secret_matches", "find_personal_emails",
                                 "find_home_paths", "markdown_links",
                                 "check_markdown_links", "check_json_samples",
                                 "gitignore_covers", "latest_changelog_version",
                                 "skill_frontmatter_version",
                                 "check_version_consistency",
                                 "check_private_maintenance"),
    }

    def test_every_required_module_imports(self):
        broken = {name: repr(error) for name, error in REQUIRED_MODULE_ERRORS.items()
                  if error is not None}
        self.assertEqual(broken, {},
                         "必需模块导入失败，测试不得整组 skip："
                         + json.dumps(broken, ensure_ascii=False))

    def test_every_required_function_exists(self):
        modules = {
            "magpie_inventory": inventory,
            "magpie_preflight": preflight,
            "public_release_check": release,
        }
        missing = {}
        for name, functions in self.REQUIRED.items():
            gaps = _required_missing(name, modules[name], *functions)
            if gaps:
                missing[name] = gaps
        self.assertEqual(missing, {},
                         "必需函数缺失，测试不得整组 skip："
                         + json.dumps(missing, ensure_ascii=False))

    def test_no_required_test_is_skipped(self):
        # The suite must not carry skip guards for the required behaviour:
        # a skipped test would let a broken candidate pass as green.
        skipped = []
        suite = unittest.defaultTestLoader.loadTestsFromModule(
            sys.modules[__name__])
        stack = list(suite)
        while stack:
            case = stack.pop()
            if isinstance(case, unittest.TestSuite):
                stack.extend(list(case))
                continue
            reason = getattr(case, "__unittest_skip__", None)
            if reason:
                skipped.append("{}.{}: {}".format(
                    type(case).__name__, case._testMethodName, reason))
        self.assertEqual(skipped, [],
                         "存在被 skip 的测试，候选不可用却会被当成通过："
                         + json.dumps(sorted(skipped), ensure_ascii=False))


class VersionExtractionTests(unittest.TestCase):
    """A leading "v" must not truncate the version number."""

    def test_version_with_v_prefix_is_read_in_full(self):
        self.assertEqual(preflight.extract_version("magpie v1.2.3"), "1.2.3")
        self.assertEqual(preflight.extract_version("v1.2.3"), "1.2.3")
        self.assertEqual(preflight.extract_version("version v0.1.1307"), "0.1.1307")

    def test_version_without_v_prefix_still_works(self):
        self.assertEqual(preflight.extract_version("magpie 0.1.1330"), "0.1.1330")
        self.assertEqual(preflight.extract_version("1.2.3"), "1.2.3")

    def test_version_inside_a_word_is_not_a_version(self):
        self.assertIsNone(preflight.extract_version("buildv1.2.3"))
        self.assertIsNone(preflight.extract_version("no version here"))
        self.assertIsNone(preflight.extract_version(""))
        self.assertIsNone(preflight.extract_version(None))


class IgnoreRuleTests(unittest.TestCase):
    """The local ignore rules must behave like Git's own rules."""

    def test_wildcard_local_pattern_covers_local_files_only(self):
        self.assertTrue(release.gitignore_covers("config/other.local.json", ["*.local.*"]))
        self.assertFalse(release.gitignore_covers("config/inventory.example.json", ["*.local.*"]))
        self.assertFalse(release.gitignore_covers("config/profile.schema.json", ["*.local.*"]))
        self.assertTrue(release.gitignore_covers("config/other.local.yaml", ["*.local.*"]))

    def test_directory_rule_covers_children(self):
        self.assertTrue(release.gitignore_covers("state/plan.json", ["state/"]))
        self.assertTrue(release.gitignore_covers("state/deep/nested.json", ["state/"]))
        self.assertFalse(release.gitignore_covers("other/plan.json", ["state/"]))

    def test_negation_after_a_directory_rule_cannot_re_include_the_file(self):
        # Git does not descend into an excluded directory: the file stays
        # ignored even though a later rule names it.
        self.assertTrue(release.gitignore_covers(
            "state/plan.json", ["state/", "!state/plan.json"]))

    def test_negated_directory_rule_re_opens_the_directory(self):
        self.assertFalse(release.gitignore_covers(
            "state/plan.json", ["state/", "!state/"]))

    def test_later_rule_wins_over_an_earlier_one(self):
        self.assertFalse(release.gitignore_covers(
            "config/other.local.json", ["*.local.*", "!config/other.local.json"]))
        self.assertTrue(release.gitignore_covers(
            "config/other.local.json", ["!config/other.local.json", "*.local.*"]))

    def test_anchored_pattern_only_matches_in_its_own_directory(self):
        self.assertTrue(release.gitignore_covers("config/local.conf", ["config/local.conf"]))
        self.assertFalse(release.gitignore_covers("other/local.conf", ["config/local.conf"]))

    def test_comments_and_blank_lines_are_ignored(self):
        self.assertTrue(release.gitignore_covers(
            "config/other.local.json", ["# comment", "", "*.local.*"]))


class PrivateLayerLeakTests(unittest.TestCase):
    """Tracked private files must fail the gate; ignore rules never help.

    A file that is already tracked stays in the published history no matter
    what the .gitignore says, so "it is ignored" is not an excuse.
    """

    def _git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=60)

    def _write_tree(self, root, private_files):
        skill = root / "magpie-optimizer"
        (skill / "config").mkdir(parents=True, exist_ok=True)
        (skill / "state").mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            "---\nname: magpie-optimizer\nmetadata:\n  version: 1.0.0\n---\n\n# Body\n",
            encoding="utf-8")
        (skill / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [1.0.0] - 2026-01-05\n\n- entry\n", encoding="utf-8")
        (skill / "config" / ".gitignore").write_text(
            "*.local.*\nstate/\n", encoding="utf-8")
        (skill / "config" / "inventory.example.json").write_text(
            '{"schema": "magpie-profile.v1"}\n', encoding="utf-8")
        for name in private_files:
            path = skill / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"private": "value"}\n', encoding="utf-8")
        self._git(root, "init", "-q")
        self._git(root, "add", "-A")
        for name in private_files:
            self._git(root, "add", "-f", "--", "magpie-optimizer/" + name)
        self._git(root, "-c", "user.email=t@example.invalid",
                  "-c", "user.name=Synthetic", "commit", "-qm", "synthetic")

    def _run_check(self, root):
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "public_release_check.py"),
             "check", "--root", str(root)],
            capture_output=True, text=True, timeout=120)

    def test_tracked_private_config_file_fails_even_when_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_tree(root, ["config/other.local.json"])
            result = self._run_check(root)
            report = json.loads(result.stdout)
            codes = {(finding["code"], finding["severity"])
                     for finding in report["findings"]}
            self.assertIn(("LOCAL_CONFIG_PUBLISHED", "fail"), codes)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_tracked_state_evidence_fails_even_when_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_tree(root, ["state/plan.json"])
            result = self._run_check(root)
            report = json.loads(result.stdout)
            codes = {(finding["code"], finding["severity"])
                     for finding in report["findings"]}
            self.assertIn(("PRIVATE_STATE_PUBLISHED", "fail"), codes)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_empty_state_with_only_the_rule_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_tree(root, ["state/.gitignore"])
            result = self._run_check(root)
            report = json.loads(result.stdout)
            fail_codes = {finding["code"] for finding in report["findings"]
                          if finding["severity"] == "fail"}
            self.assertEqual(fail_codes, set(),
                             "clean tree produced fail findings: "
                             + json.dumps(report["findings"], ensure_ascii=False))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_standalone_tree_without_git_also_rejects_private_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "magpie-optimizer"
            (skill / "config").mkdir(parents=True)
            (skill / "state").mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: magpie-optimizer\nmetadata:\n  version: 1.0.0\n---\n\n# Body\n",
                encoding="utf-8")
            (skill / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [1.0.0] - 2026-01-05\n\n- entry\n", encoding="utf-8")
            (skill / "config" / ".gitignore").write_text("*.local.*\nstate/\n",
                                                         encoding="utf-8")
            (skill / "config" / "other.local.json").write_text('{"private": "value"}\n',
                                                               encoding="utf-8")
            (skill / "state" / "plan.json").write_text('{"private": "value"}\n',
                                                        encoding="utf-8")
            result = self._run_check(root)
            report = json.loads(result.stdout)
            codes = {finding["code"] for finding in report["findings"]
                     if finding["severity"] == "fail"}
            self.assertIn("LOCAL_CONFIG_PUBLISHED", codes)
            self.assertIn("PRIVATE_STATE_PUBLISHED", codes)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


class TaskDocumentPrivacyTests(unittest.TestCase):
    """A machine-local path in TASKS/DECISIONS is a leak, not a note."""

    def test_task_and_decision_documents_fail_on_absolute_paths(self):
        for name in ("TASKS.md", "DECISIONS.md"):
            with self.subTest(document=name):
                findings = release.check_text_content(
                    name, "worktree: " + HOME_SAMPLE + "/private-skills\n")
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0]["code"], "TASKS_PRIVATE_PATH")
                self.assertEqual(findings[0]["severity"], "fail")

    def test_other_documents_still_report_the_absolute_path(self):
        findings = release.check_text_content("references/notes.md",
                                              "config lives in " + HOME_SAMPLE + "\n")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "ABSOLUTE_HOME_PATH")
        self.assertEqual(findings[0]["severity"], "fail")

    def test_tracked_maintenance_records_fail_the_manifest_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: magpie-optimizer\nmetadata:\n  version: 1.0.0\n---\n",
                encoding="utf-8")
            paths = ["TASKS.md", "DECISIONS.md", "references/notes.md"]
            findings = release.check_private_maintenance(paths, root)
            self.assertEqual(
                {item["code"] for item in findings},
                {"PRIVATE_MAINTENANCE_PUBLISHED"},
            )
            self.assertEqual(
                {item["file"] for item in findings},
                {"TASKS.md", "DECISIONS.md"},
            )

    def test_private_state_rule_passes_in_repo_root_mode(self):
        self.assertFalse(release._is_private_state_path(
            "skills/magpie-optimizer/state/.gitignore"))
        self.assertTrue(release._is_private_state_path(
            "skills/magpie-optimizer/state/plan.json"))

    def test_untracked_maintenance_records_do_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "---\nname: magpie-optimizer\nmetadata:\n  version: 1.0.0\n---\n",
                encoding="utf-8")
            self.assertEqual(release.check_private_maintenance([], root), [])


class ReturnForFixRegressionTests(unittest.TestCase):
    """Regressions for the review round that returned the candidate."""

    def _git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=60)

    def _commit(self, root):
        self._git(root, "-c", "user.email=t@example.invalid",
                  "-c", "user.name=Synthetic", "commit", "-qm", "synthetic")

    def _skill_root(self, tmp, extra_files=(), tracked=()):
        root = Path(tmp)
        skill = root / "magpie-optimizer"
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            "---\nname: magpie-optimizer\nmetadata:\n  version: 1.0.0\n---\n\n# Body\n",
            encoding="utf-8")
        (skill / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [1.0.0] - 2026-01-05\n\n- entry\n", encoding="utf-8")
        for name, content in extra_files:
            path = skill / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self._git(root, "init", "-q")
        self._git(root, "add", "-f", "-f", "--",
                  *["magpie-optimizer/" + name for name in tracked])
        self._commit(root)
        return root, skill

    def _run_check(self, root):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "public_release_check.py"),
             "check", "--root", str(root)],
            capture_output=True, text=True, timeout=120)
        report = json.loads(result.stdout)
        return result.returncode, report

    def _codes(self, report):
        return {(finding["code"], finding["severity"]) for finding in report["findings"]}

    def test_message_does_not_tell_the_user_to_delete_private_files(self):
        findings = release.check_local_config(
            ["magpie-optimizer/config/other.local.json"], Path("/nonexistent"))
        self.assertEqual(len(findings), 1)
        detail = findings[0]["detail"]
        self.assertIn("保留本机原件", detail)
        self.assertNotIn("删除本机内容", detail)

    def test_state_message_does_not_tell_the_user_to_delete_private_files(self):
        findings = release.check_private_state(
            ["magpie-optimizer/state/plan.json"], Path("/nonexistent"))
        self.assertEqual(len(findings), 1)
        detail = findings[0]["detail"]
        self.assertIn("保留本机原件", detail)
        self.assertNotIn("删除本机内容", detail)

    def test_nested_state_rule_file_does_not_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _skill = self._skill_root(
                tmp,
                extra_files=[("state/.gitignore", b"*\n"),
                             ("state/nested/.gitignore", b"*\n")],
                tracked=["SKILL.md", "CHANGELOG.md",
                         "state/.gitignore", "state/nested/.gitignore"])
            code, report = self._run_check(root)
            self.assertIn(("PRIVATE_STATE_PUBLISHED", "fail"), self._codes(report))
            files = {finding["file"] for finding in report["findings"]
                     if finding["code"] == "PRIVATE_STATE_PUBLISHED"}
            self.assertIn("magpie-optimizer/state/nested/.gitignore", files)
            self.assertEqual(code, 1, report)

    def test_state_rule_file_itself_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _skill = self._skill_root(
                tmp, extra_files=[("state/.gitignore", b"*\n")],
                tracked=["SKILL.md", "CHANGELOG.md", "state/.gitignore"])
            code, report = self._run_check(root)
            self.assertNotIn(("PRIVATE_STATE_PUBLISHED", "fail"), self._codes(report))
            self.assertEqual(code, 0, report)

    def test_directory_symlink_is_not_followed_in_git_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tempfile.mkdtemp())
            (outside / "secret.txt").write_text("outside secret\n", encoding="utf-8")
            root = Path(tmp)
            skill = root / "magpie-optimizer"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: magpie-optimizer\nmetadata:\n  version: 1.0.0\n---\n\n# Body\n",
                encoding="utf-8")
            (skill / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [1.0.0] - 2026-01-05\n\n- entry\n", encoding="utf-8")
            (skill / "a").mkdir()
            (skill / "a" / "file.txt").write_text("x\n", encoding="utf-8")
            self._git(root, "init", "-q")
            self._git(root, "add", "-A")
            self._commit(root)
            import shutil
            shutil.rmtree(skill / "a")
            os.symlink(str(outside), str(skill / "a"))
            code, report = self._run_check(root)
            self.assertIn(("FILE_UNREADABLE", "fail"), self._codes(report))
            files = {finding["file"] for finding in report["findings"]
                     if finding["code"] == "FILE_UNREADABLE"}
            self.assertIn("magpie-optimizer/a/file.txt", files)
            self.assertEqual(code, 1, report)

    def test_binary_and_invalid_utf8_files_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _skill = self._skill_root(
                tmp,
                extra_files=[("blob.bin", b"\x00\x01binary"),
                             ("bad.md", b"\xff\xfe not utf8 \xff")],
                tracked=["SKILL.md", "CHANGELOG.md", "blob.bin", "bad.md"])
            code, report = self._run_check(root)
            self.assertIn(("FILE_UNREADABLE", "fail"), self._codes(report))
            files = {finding["file"] for finding in report["findings"]
                     if finding["code"] == "FILE_UNREADABLE"}
            self.assertIn("magpie-optimizer/blob.bin", files)
            self.assertIn("magpie-optimizer/bad.md", files)
            self.assertEqual(code, 1, report)

    def test_tracked_but_missing_file_fails_in_a_single_skill_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, skill = self._skill_root(tmp, tracked=["SKILL.md", "CHANGELOG.md"])
            (skill / "gone.md").write_text("x\n", encoding="utf-8")
            self._git(root, "add", "-f", "--", "magpie-optimizer/gone.md")
            self._commit(root)
            (skill / "gone.md").unlink()
            code, report = self._run_check(root)
            self.assertIn(("FILE_MISSING", "fail"), self._codes(report))
            self.assertEqual(code, 1, report)

    def test_missing_file_stays_info_in_a_multi_skill_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("skill-a", "skill-b"):
                directory = root / name
                directory.mkdir(parents=True)
                (directory / "SKILL.md").write_text(
                    "---\nname: " + name + "\nmetadata:\n  version: 1.0.0\n---\n\n# Body\n",
                    encoding="utf-8")
                (directory / "CHANGELOG.md").write_text(
                    "# Changelog\n\n## [1.0.0] - 2026-01-05\n\n- entry\n", encoding="utf-8")
            (root / "skill-a" / "gone.md").write_text("x\n", encoding="utf-8")
            self._git(root, "init", "-q")
            self._git(root, "add", "-A")
            self._commit(root)
            (root / "skill-a" / "gone.md").unlink()
            code, report = self._run_check(root)
            self.assertIn(("FILE_MISSING", "info"), self._codes(report))
            self.assertNotIn(("FILE_MISSING", "fail"), self._codes(report))

    def test_ignore_ancestors_are_path_prefixes(self):
        # "a/*.local.json" covers a/c.local.json but not a/b/c.local.json.
        self.assertTrue(release.gitignore_covers("a/c.local.json", ["a/*.local.json"]))
        self.assertFalse(release.gitignore_covers("a/b/c.local.json", ["a/*.local.json"]))

    def test_leading_slash_anchors_the_pattern(self):
        self.assertTrue(release.gitignore_covers("a/b/c.txt", ["/a/b/c.txt"]))
        self.assertFalse(release.gitignore_covers("x/a/b/c.txt", ["/a/b/c.txt"]))
        # A pattern with a slash is relative to the .gitignore directory,
        # so it matches there but not below another directory.
        self.assertTrue(release.gitignore_covers("a/b/c.txt", ["a/b/c.txt"]))
        self.assertFalse(release.gitignore_covers("x/a/b/c.txt", ["a/b/c.txt"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
