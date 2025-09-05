import pytest

from github_semver.bumps import (
    BuildInformation,
    _split_build_tag,
    append_rc,
    bump_build,
    bump_major,
    bump_minor,
    bump_patch,
)

# Test constants
BASIC_VERSION = "1.2.3"
VERSION_WITH_BUILD = "1.2.3-build.123+feature.abc123"
VERSION_WITH_RC = "2.0.0-rc.1+def456"
BRANCH_NAME = "feature/my-awesome-feature"
COMMIT_SHA = "abc123def456"
BUILD_NUMBER = 42
LONG_BUILD_STRING_LENGTH = 1000


class TestSplitBuildTag:
    """Test the internal _split_build_tag function."""

    def test_split_version_without_build_info(self):
        """Test splitting a version without build information."""
        result = _split_build_tag(BASIC_VERSION)

        assert result.version == "1.2.3"
        assert result.build == ""
        assert isinstance(result, BuildInformation)

    def test_split_version_with_build_info(self):
        """Test splitting a version with build information."""
        result = _split_build_tag(VERSION_WITH_BUILD)

        assert result.version == "1.2.3"
        assert result.build == "build.123+feature.abc123"

    def test_split_version_with_rc_info(self):
        """Test splitting a version with release candidate information."""
        result = _split_build_tag(VERSION_WITH_RC)

        assert result.version == "2.0.0"
        assert result.build == "rc.1+def456"

    def test_split_empty_version(self):
        """Test splitting an empty version string."""
        result = _split_build_tag("")

        assert result.version == ""
        assert result.build == ""

    def test_split_version_with_multiple_dashes(self):
        """Test splitting a version with multiple dashes in build info."""
        version = "1.0.0-alpha-beta-gamma"
        result = _split_build_tag(version)

        assert result.version == "1.0.0"
        assert result.build == "alpha-beta-gamma"


class TestBumpMajor:
    """Test the bump_major function."""

    def test_bump_major_basic_version(self):
        """Test bumping major version of a basic version string."""
        result = bump_major(BASIC_VERSION)

        assert result == "2.0.0"

    def test_bump_major_version_with_build(self):
        """Test bumping major version ignoring build information."""
        result = bump_major(VERSION_WITH_BUILD)

        assert result == "2.0.0"

    def test_bump_major_from_zero(self):
        """Test bumping major version from 0."""
        result = bump_major("0.1.5")

        assert result == "1.0.0"

    def test_bump_major_large_number(self):
        """Test bumping major version with large numbers."""
        result = bump_major("99.88.77")

        assert result == "100.0.0"

    def test_bump_major_single_digit(self):
        """Test bumping major version with single digit version."""
        # The actual behavior: it works but produces unexpected results
        result = bump_major("5")
        # When there's no "." in the version, split(".") returns ["5"]
        # So version_segments[0] is "5", and it becomes "6.0.0"
        assert result == "6.0.0"

    def test_bump_major_invalid_version_format(self):
        """Test bumping major with invalid version format."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_major("invalid.version.format")

    def test_bump_major_non_numeric_major(self):
        """Test bumping major with non-numeric major version."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_major("v1.2.3")


class TestBumpMinor:
    """Test the bump_minor function."""

    def test_bump_minor_basic_version(self):
        """Test bumping minor version of a basic version string."""
        result = bump_minor(BASIC_VERSION)

        assert result == "1.3.0"

    def test_bump_minor_version_with_build(self):
        """Test bumping minor version ignoring build information."""
        result = bump_minor(VERSION_WITH_BUILD)

        assert result == "1.3.0"

    def test_bump_minor_from_zero(self):
        """Test bumping minor version from 0."""
        result = bump_minor("1.0.5")

        assert result == "1.1.0"

    def test_bump_minor_large_number(self):
        """Test bumping minor version with large numbers."""
        result = bump_minor("1.99.77")

        assert result == "1.100.0"

    def test_bump_minor_invalid_version_format(self):
        """Test bumping minor with invalid version format."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_minor("invalid.version.format")

    def test_bump_minor_insufficient_parts(self):
        """Test bumping minor with insufficient version parts."""
        with pytest.raises(IndexError):
            bump_minor("1")


class TestBumpPatch:
    """Test the bump_patch function."""

    def test_bump_patch_basic_version(self):
        """Test bumping patch version of a basic version string."""
        result = bump_patch(BASIC_VERSION)

        assert result == "1.2.4"

    def test_bump_patch_version_with_build(self):
        """Test bumping patch version ignoring build information."""
        result = bump_patch(VERSION_WITH_BUILD)

        assert result == "1.2.4"

    def test_bump_patch_from_zero(self):
        """Test bumping patch version from 0."""
        result = bump_patch("1.2.0")

        assert result == "1.2.1"

    def test_bump_patch_large_number(self):
        """Test bumping patch version with large numbers."""
        result = bump_patch("1.2.999")

        assert result == "1.2.1000"

    def test_bump_patch_four_part_version(self):
        """Test bumping patch with four-part version (should bump the last part)."""
        result = bump_patch("1.2.3.4")

        assert result == "1.2.3.5"

    def test_bump_patch_invalid_version_format(self):
        """Test bumping patch with invalid version format."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_patch("invalid.version.format")

    def test_bump_patch_empty_version(self):
        """Test bumping patch with empty version."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            # This raises ValueError because int("") fails
            bump_patch("")


class TestBumpBuild:
    """Test the bump_build function."""

    def test_bump_build_basic_version(self):
        """Test creating build version from basic version."""
        result = bump_build(BASIC_VERSION, BRANCH_NAME, COMMIT_SHA, BUILD_NUMBER)

        expected = "1.2.4-build.42+featuremyawesomefeature.abc123def456"
        assert result == expected

    def test_bump_build_version_with_existing_build(self):
        """Test creating build version when build info already exists."""
        result = bump_build(VERSION_WITH_BUILD, BRANCH_NAME, COMMIT_SHA, BUILD_NUMBER)

        expected = "1.2.3-build.42+featuremyawesomefeature.abc123def456"
        assert result == expected

    def test_bump_build_clean_branch_name(self):
        """Test that branch names are cleaned (special characters removed)."""
        dirty_branch = "feature/fix-issue#123@special-chars!"
        result = bump_build(BASIC_VERSION, dirty_branch, COMMIT_SHA, BUILD_NUMBER)

        expected = "1.2.4-build.42+featurefixissue123specialchars.abc123def456"
        assert result == expected

    def test_bump_build_with_string_build_number(self):
        """Test bump_build with string build number."""
        result = bump_build(BASIC_VERSION, BRANCH_NAME, COMMIT_SHA, "123")

        expected = "1.2.4-build.123+featuremyawesomefeature.abc123def456"
        assert result == expected

    def test_bump_build_empty_branch_name(self):
        """Test bump_build with empty branch name."""
        result = bump_build(BASIC_VERSION, "", COMMIT_SHA, BUILD_NUMBER)

        expected = "1.2.4-build.42+.abc123def456"
        assert result == expected

    def test_bump_build_empty_commit_sha(self):
        """Test bump_build with empty commit SHA."""
        result = bump_build(BASIC_VERSION, BRANCH_NAME, "", BUILD_NUMBER)

        expected = "1.2.4-build.42+featuremyawesomefeature."
        assert result == expected

    def test_bump_build_numeric_only_branch(self):
        """Test bump_build with numeric-only branch name."""
        result = bump_build(BASIC_VERSION, "123456", COMMIT_SHA, BUILD_NUMBER)

        expected = "1.2.4-build.42+123456.abc123def456"
        assert result == expected


class TestAppendRc:
    """Test the append_rc function."""

    def test_append_rc_basic_version(self):
        """Test appending RC suffix to basic version."""
        result = append_rc(BASIC_VERSION, COMMIT_SHA, BUILD_NUMBER)

        expected = "1.2.3-rc.42+abc123def456"
        assert result == expected

    def test_append_rc_version_with_build(self):
        """Test appending RC suffix ignoring existing build info."""
        result = append_rc(VERSION_WITH_BUILD, COMMIT_SHA, BUILD_NUMBER)

        expected = "1.2.3-rc.42+abc123def456"
        assert result == expected

    def test_append_rc_with_string_build_number(self):
        """Test append_rc with string build number."""
        result = append_rc(BASIC_VERSION, COMMIT_SHA, "123")

        expected = "1.2.3-rc.123+abc123def456"
        assert result == expected

    def test_append_rc_empty_commit_sha(self):
        """Test append_rc with empty commit SHA."""
        result = append_rc(BASIC_VERSION, "", BUILD_NUMBER)

        expected = "1.2.3-rc.42+"
        assert result == expected

    def test_append_rc_zero_build_number(self):
        """Test append_rc with zero build number."""
        result = append_rc(BASIC_VERSION, COMMIT_SHA, 0)

        expected = "1.2.3-rc.0+abc123def456"
        assert result == expected

    def test_append_rc_large_build_number(self):
        """Test append_rc with large build number."""
        result = append_rc(BASIC_VERSION, COMMIT_SHA, 999999)

        expected = "1.2.3-rc.999999+abc123def456"
        assert result == expected


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_version_with_only_major(self):
        """Test functions with version containing only major number."""
        # bump_minor fails with IndexError when there's no minor version part
        with pytest.raises(IndexError):
            bump_minor("1")

        # bump_patch works because it uses the last segment
        result_patch = bump_patch("1")
        assert result_patch == "2"  # Works because it bumps the last segment

    def test_version_with_letters(self):
        """Test functions with version containing letters."""
        # bump_major fails when the major part contains letters
        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_major("v1.2.3")

        # These will also fail when trying to convert letters to int
        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_minor("1.a.3")

        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_patch("1.2.beta")

    def test_very_long_version_string(self):
        """Test with very long version strings."""
        long_version = "1.2.3-" + "a" * LONG_BUILD_STRING_LENGTH
        result = _split_build_tag(long_version)

        assert result.version == "1.2.3"
        assert len(result.build) == LONG_BUILD_STRING_LENGTH

    def test_version_with_leading_zeros(self):
        """Test with version containing leading zeros."""
        result = bump_patch("01.02.03")

        # Should work but might produce unexpected results
        assert result == "01.02.4"  # Leading zeros preserved in major.minor

    def test_negative_version_numbers(self):
        """Test with negative version numbers."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            bump_major("-1.2.3")
