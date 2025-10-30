import os
import subprocess
from unittest import mock

import pytest

from github_semver.run_semver import main


@mock.patch.dict(os.environ, clear=True)
def test_when_no_environment_variables_then_throw_error():
    with pytest.raises(RuntimeError) as cm:
        main()
    assert "environment" in str(cm.value)


@mock.patch.dict(
    os.environ,
    {
        "GITHUB_SHA": "abababababababababababababababababababab",  # Full 40-char SHA
        "GITHUB_REF": "refs/heads/feature/abc-def",
        "GITHUB_REF_NAME": "feature/abc-def",
        "REPO_DEFAULT_BRANCH": "main",
        "GITHUB_RUN_ID": "1",
    },
    clear=True,
)
@mock.patch.object(subprocess, "check_output")
def test_when_environment_variables_are_set_build_version_is_bumped(
    mock_check_output, capsys
):
    mock_check_output.return_value = b"b2984df042ba025c1f46f74eaea18945fc504e7a\trefs/tags/1.0.0\nfcc84d34053e580507cb79583587b37812a21e10\trefs/tags/0.0.1\n"

    main()

    assert capsys.readouterr().out == "0.0.1-build.1+featureabcdef.abababa\n"


@mock.patch.dict(
    os.environ,
    {
        "GITHUB_SHA": "abababababababababababababababababababab",
        "GITHUB_REF": "refs/heads/feature/abc-def",
        "GITHUB_REF_NAME": "feature/abc-def",
        "REPO_DEFAULT_BRANCH": "main",
        "GITHUB_RUN_ID": "1",
    },
    clear=True,
)
@mock.patch.object(subprocess, "check_output")
def test_when_no_tag_is_found_default_to_first_patch(mock_check_output, capsys):
    mock_check_output.return_value = (
        b"b2984df042ba025c1f46f74eaea18945fc504e7a\trefs/tags/my-new-tag\n"
    )

    main()

    assert capsys.readouterr().out == "0.0.1-build.1+featureabcdef.abababa\n"


@mock.patch.dict(
    os.environ,
    {
        "GITHUB_SHA": "abababababababababababababababababababab",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_NAME": "main",
        "REPO_DEFAULT_BRANCH": "main",
        "GITHUB_RUN_ID": "1",
    },
    clear=True,
)
@mock.patch.object(subprocess, "check_output")
def test_when_run_on_default_branch_patch_bump_based_on_last_tag(
    mock_check_output, capsys
):
    mock_check_output.return_value = b"b2984df042ba025c1f46f74eaea18945fc504e7a\trefs/tags/1.0.0\nfcc84d34053e580507cb79583587b37812a21e10\trefs/tags/0.0.1\n"

    main()
    assert capsys.readouterr().out == "1.0.1-rc.1+abababa\n"


@mock.patch.dict(
    os.environ,
    {
        "GITHUB_SHA": "abababababababababababababababababababab",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_NAME": "main",
        "REPO_DEFAULT_BRANCH": "main",
        "GITHUB_RUN_ID": "1",
    },
    clear=True,
)
@mock.patch.object(subprocess, "check_output")
def test_when_run_on_default_branch_without_tag_bump_to_0_0_2_rc(
    mock_check_output, capsys
):
    mock_check_output.return_value = b""
    main()
    assert capsys.readouterr().out == "0.0.2-rc.1+abababa\n"


@mock.patch.dict(
    os.environ,
    {
        "GITHUB_SHA": "abababababababababababababababababababab",
        "GITHUB_REF": "refs/pull/123/merge",
        "GITHUB_HEAD_REF": "feature/my-feature",
        "REPO_DEFAULT_BRANCH": "main",
        "GITHUB_RUN_ID": "42",
    },
    clear=True,
)
@mock.patch.object(subprocess, "check_output")
def test_when_run_on_pull_request_patch_bump_build_version(mock_check_output, capsys):
    mock_check_output.return_value = b"b2984df042ba025c1f46f74eaea18945fc504e7a\trefs/tags/1.0.0\nfcc84d34053e580507cb79583587b37812a21e10\trefs/tags/0.0.1\n"

    main()

    assert capsys.readouterr().out == "0.0.1-build.42+featuremyfeature.abababa\n"


@mock.patch.dict(
    os.environ,
    {
        "GITHUB_SHA": "abababababababababababababababababababab",
        "GITHUB_REF": "refs/pull/123/merge",
        "GITHUB_HEAD_REF": "feature/my-feature",
        "REPO_DEFAULT_BRANCH": "main",
        "GITHUB_RUN_ID": "42",
    },
    clear=True,
)
@mock.patch.object(subprocess, "check_output")
def test_when_run_on_pull_request_without_tag_bump_to_first_patch(
    mock_check_output, capsys
):
    mock_check_output.return_value = b""

    main()

    assert capsys.readouterr().out == "0.0.1-build.42+featuremyfeature.abababa\n"


@mock.patch.dict(
    os.environ,
    {
        "GITHUB_SHA": "abababababababababababababababababababab",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_NAME": "main",
        "REPO_DEFAULT_BRANCH": "main",
        "GITHUB_RUN_ID": "1",
        "BUILD_RC_SEMVER": "False",  # Disable RC building
    },
    clear=True,
)
@mock.patch.object(subprocess, "check_output")
def test_when_run_on_default_branch_with_rc_disabled_no_rc_suffix(
    mock_check_output, capsys
):
    mock_check_output.return_value = b"b2984df042ba025c1f46f74eaea18945fc504e7a\trefs/tags/1.0.0\nfcc84d34053e580507cb79583587b37812a21e10\trefs/tags/0.0.1\n"

    main()
    assert capsys.readouterr().out == "1.0.1\n"
