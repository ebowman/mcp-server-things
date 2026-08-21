"""hq-nb1: Unit tests for ThingsMCPConfig's tag_creation_policy /
ai_can_create_tags reconciliation.

Prior to the fix, config.py's `validate_tag_creation_policy` /
`set_ai_can_create_tags_from_policy` field_validator pair coupled the two
fields via pydantic's field-declaration order: `ai_can_create_tags` (declared
first) was always validated before `tag_creation_policy`, so
`tag_creation_policy`'s validator always saw `ai_can_create_tags` already
present in `info.data` and unconditionally derived the policy from it alone -
making `THINGS_MCP_TAG_CREATION_POLICY` (env or env_file) dead, and
FILTER_SILENT/FAIL_ON_UNKNOWN unreachable via env or via passing
`tag_creation_policy=` directly to the constructor alongside the
`ai_can_create_tags` default.

The fix replaces both field_validators with a single
`model_validator(mode='after')` that reconciles the two fields using
`model_fields_set` to detect which were *explicitly* provided (env var,
env_file, or constructor kwarg) vs left at their declared defaults, with
explicit `tag_creation_policy` taking precedence over a value derived from
`ai_can_create_tags`.

These tests construct ThingsMCPConfig directly (env via monkeypatch, and
constructor kwargs) - no mocking of AppleScript/Things needed.
"""
import pytest

from things_mcp.config import ThingsMCPConfig, TagCreationPolicy


ALL_POLICIES = list(TagCreationPolicy)


# ---------------------------------------------------------------------------
# Defaults (neither field explicitly set)
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_defaults_are_mutually_consistent(self, monkeypatch):
        """The declared default is FILTER_WARN, not FAIL_ON_UNKNOWN - see
        config.py's comment on the tag_creation_policy Field for history:
        prior to the hq-nb1 fix, the buggy validators silently rewrote an
        unconfigured policy from its then-declared FAIL_ON_UNKNOWN default
        to FILTER_WARN, so FAIL_ON_UNKNOWN was never actually reachable as
        the effective default - every unconfigured deployment has always
        behaved as FILTER_WARN. The declared default was corrected to
        FILTER_WARN so fixing the reconciliation bug does not also
        silently change behavior for unconfigured users."""
        monkeypatch.delenv("THINGS_MCP_TAG_CREATION_POLICY", raising=False)
        monkeypatch.delenv("THINGS_MCP_AI_CAN_CREATE_TAGS", raising=False)
        config = ThingsMCPConfig()
        assert config.tag_creation_policy == TagCreationPolicy.FILTER_WARN
        assert config.ai_can_create_tags is False


# ---------------------------------------------------------------------------
# Env var: THINGS_MCP_TAG_CREATION_POLICY reaches all 4 policies
# ---------------------------------------------------------------------------


class TestEnvVarPolicy:
    @pytest.mark.parametrize("policy", ALL_POLICIES)
    def test_policy_env_var_reaches_policy_and_derives_bool(self, monkeypatch, policy):
        monkeypatch.delenv("THINGS_MCP_AI_CAN_CREATE_TAGS", raising=False)
        monkeypatch.setenv("THINGS_MCP_TAG_CREATION_POLICY", policy.value)
        config = ThingsMCPConfig()
        assert config.tag_creation_policy == policy
        assert config.ai_can_create_tags == (policy == TagCreationPolicy.ALLOW_ALL)

    def test_ai_can_create_tags_env_true_derives_allow_all(self, monkeypatch):
        monkeypatch.delenv("THINGS_MCP_TAG_CREATION_POLICY", raising=False)
        monkeypatch.setenv("THINGS_MCP_AI_CAN_CREATE_TAGS", "true")
        config = ThingsMCPConfig()
        assert config.ai_can_create_tags is True
        assert config.tag_creation_policy == TagCreationPolicy.ALLOW_ALL

    def test_ai_can_create_tags_env_false_derives_filter_warn(self, monkeypatch):
        monkeypatch.delenv("THINGS_MCP_TAG_CREATION_POLICY", raising=False)
        monkeypatch.setenv("THINGS_MCP_AI_CAN_CREATE_TAGS", "false")
        config = ThingsMCPConfig()
        assert config.ai_can_create_tags is False
        assert config.tag_creation_policy == TagCreationPolicy.FILTER_WARN

    def test_both_env_vars_set_policy_wins(self, monkeypatch):
        """Explicit policy wins over explicit (conflicting) bool; the bool
        is recomputed for consistency rather than left as the caller's
        conflicting value."""
        monkeypatch.setenv("THINGS_MCP_TAG_CREATION_POLICY", "fail_on_unknown")
        monkeypatch.setenv("THINGS_MCP_AI_CAN_CREATE_TAGS", "true")
        config = ThingsMCPConfig()
        assert config.tag_creation_policy == TagCreationPolicy.FAIL_ON_UNKNOWN
        assert config.ai_can_create_tags is False

    def test_both_env_vars_set_agreeing(self, monkeypatch):
        monkeypatch.setenv("THINGS_MCP_TAG_CREATION_POLICY", "allow_all")
        monkeypatch.setenv("THINGS_MCP_AI_CAN_CREATE_TAGS", "true")
        config = ThingsMCPConfig()
        assert config.tag_creation_policy == TagCreationPolicy.ALLOW_ALL
        assert config.ai_can_create_tags is True


# ---------------------------------------------------------------------------
# Constructor kwargs: all 4 policies reachable directly
# ---------------------------------------------------------------------------


class TestConstructorKwargs:
    @pytest.mark.parametrize("policy", ALL_POLICIES)
    def test_policy_kwarg_reaches_policy_and_derives_bool(self, policy):
        config = ThingsMCPConfig(tag_creation_policy=policy)
        assert config.tag_creation_policy == policy
        assert config.ai_can_create_tags == (policy == TagCreationPolicy.ALLOW_ALL)

    def test_ai_can_create_tags_kwarg_true_derives_allow_all(self):
        config = ThingsMCPConfig(ai_can_create_tags=True)
        assert config.ai_can_create_tags is True
        assert config.tag_creation_policy == TagCreationPolicy.ALLOW_ALL

    def test_ai_can_create_tags_kwarg_false_derives_filter_warn(self):
        config = ThingsMCPConfig(ai_can_create_tags=False)
        assert config.ai_can_create_tags is False
        assert config.tag_creation_policy == TagCreationPolicy.FILTER_WARN

    def test_both_kwargs_set_policy_wins_on_conflict(self, caplog):
        config = ThingsMCPConfig(
            tag_creation_policy=TagCreationPolicy.FILTER_SILENT,
            ai_can_create_tags=True,
        )
        assert config.tag_creation_policy == TagCreationPolicy.FILTER_SILENT
        assert config.ai_can_create_tags is False

    def test_both_kwargs_set_agreeing_no_conflict(self):
        config = ThingsMCPConfig(
            tag_creation_policy=TagCreationPolicy.ALLOW_ALL,
            ai_can_create_tags=True,
        )
        assert config.tag_creation_policy == TagCreationPolicy.ALLOW_ALL
        assert config.ai_can_create_tags is True

    def test_neither_kwarg_set_uses_defaults(self):
        config = ThingsMCPConfig()
        assert config.tag_creation_policy == TagCreationPolicy.FILTER_WARN
        assert config.ai_can_create_tags is False


# ---------------------------------------------------------------------------
# Backward-compat string aliases for tag_creation_policy still parse
# ---------------------------------------------------------------------------


class TestBackwardCompatAliases:
    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("filter_unknown", TagCreationPolicy.FILTER_WARN),
            ("reject_unknown", TagCreationPolicy.FAIL_ON_UNKNOWN),
            ("warn_unknown", TagCreationPolicy.ALLOW_ALL),
        ],
    )
    def test_legacy_alias_env_var(self, monkeypatch, alias, expected):
        monkeypatch.delenv("THINGS_MCP_AI_CAN_CREATE_TAGS", raising=False)
        monkeypatch.setenv("THINGS_MCP_TAG_CREATION_POLICY", alias)
        config = ThingsMCPConfig()
        assert config.tag_creation_policy == expected
        assert config.ai_can_create_tags == (expected == TagCreationPolicy.ALLOW_ALL)
