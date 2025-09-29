import os
from unittest.mock import MagicMock, patch

import pytest

from github_semver.commit_version import (
    download_artifact,
    get_last_successful_workflow_for_commit,
)

# Test constants
EXPECTED_LATEST_WORKFLOW_ID = 124
EXPECTED_JOB_COUNT = 2
EXPECTED_ARTIFACT_ID = 123
SUCCESSFUL_WORKFLOW_ID = 100
OLDER_SUCCESSFUL_WORKFLOW_ID = 101
LATEST_IN_PROGRESS_WORKFLOW_ID = 102
EXPECTED_API_CALL_COUNT = 2


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_get_last_successful_workflow_for_commit(mock_get):
    # Mock single response with all workflows
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}  # No pagination
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "workflow_runs": [
            {"id": 123, "status": "completed", "conclusion": "success"},
            {
                "id": EXPECTED_LATEST_WORKFLOW_ID,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 100,
                "status": "completed",
                "conclusion": "failure",
            },  # Should be filtered out
        ]
    }

    mock_get.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert result["id"] == EXPECTED_LATEST_WORKFLOW_ID  # Should return the latest one
    # Verify the request was made with per_page parameter
    call_args = mock_get.call_args[0][0]
    assert "per_page=100" in call_args


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_download_artifact_expired_error(mock_get):
    # Mock response with expired artifact
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "artifacts": [{"id": EXPECTED_ARTIFACT_ID, "name": "version", "expired": True}]
    }
    mock_get.return_value = mock_response

    with pytest.raises(ValueError, match="expired"):
        download_artifact("456", "version")


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_get_workflow_with_pagination(mock_get):
    # Create responses for multiple pages with mixed statuses
    page1_response = MagicMock()
    page1_response.status_code = 200
    page1_response.headers = {
        "Link": '<https://api.github.com/repos/owner/repo/actions/runs?page=2>; rel="next"'
    }
    page1_response.raise_for_status.return_value = None
    workflow_runs_page1 = []
    for i in range(100):
        if i % 3 == 0:  # Some failed workflows that should be filtered
            workflow_runs_page1.append(
                {"id": 100 + i, "status": "completed", "conclusion": "failure"}
            )
        else:
            workflow_runs_page1.append(
                {"id": 100 + i, "status": "completed", "conclusion": "success"}
            )
    page1_response.json.return_value = {"workflow_runs": workflow_runs_page1}

    page2_response = MagicMock()
    page2_response.status_code = 200
    page2_response.headers = {
        "Link": '<https://api.github.com/repos/owner/repo/actions/runs?page=3>; rel="next"'
    }
    page2_response.raise_for_status.return_value = None
    page2_response.json.return_value = {
        "workflow_runs": [
            {"id": 200 + i, "status": "completed", "conclusion": "success"}
            for i in range(100)
        ]
    }

    page3_response = MagicMock()
    page3_response.status_code = 200
    page3_response.headers = {"Link": None}  # Last page
    page3_response.raise_for_status.return_value = None
    page3_response.json.return_value = {
        "workflow_runs": [
            {"id": 300 + i, "status": "completed", "conclusion": "success"}
            for i in range(50)
        ]
    }

    mock_get.side_effect = [page1_response, page2_response, page3_response]

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert result["id"] == 349  # The highest ID from page 3  # noqa: PLR2004
    assert mock_get.call_count == 3  # Should have made 3 requests  # noqa: PLR2004


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_get_workflow_single_page(mock_get):
    # Test case where all results fit in a single page (no pagination needed)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}  # No next page
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "workflow_runs": [
            {"id": 100 + i, "status": "completed", "conclusion": "success"}
            for i in range(30)
        ]
    }

    mock_get.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert result["id"] == 129  # The highest ID from single page  # noqa: PLR2004
    assert mock_get.call_count == 1  # Should only make 1 request


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_get_workflow_with_name_filter(mock_get):
    # Mock response with multiple workflow types
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "workflow_runs": [
            {
                "id": 100,
                "name": "build",
                "status": "completed",
                "conclusion": "success",
            },
            {"id": 101, "name": "test", "status": "completed", "conclusion": "success"},
            {
                "id": 102,
                "name": "build",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 103,
                "name": "deploy",
                "status": "completed",
                "conclusion": "success",
            },
        ]
    }

    mock_get.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123", workflow_name="build")

    assert result is not None
    assert result["id"] == 102  # The latest "build" workflow  # noqa: PLR2004
    assert result["name"] == "build"


@patch.dict(
    os.environ,
    {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_TOKEN": "test_token",
        "DO_NOT_WAIT_FOR_SUCCESS": "true",
    },
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_do_not_wait_for_success_returns_in_progress(mock_get):
    # Test that when DO_NOT_WAIT_FOR_SUCCESS=true, in-progress workflows are returned immediately
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "workflow_runs": [
            {"id": SUCCESSFUL_WORKFLOW_ID, "status": "in_progress", "conclusion": None},
            {
                "id": 99,
                "status": "completed",
                "conclusion": "failure",
            },  # Should be filtered out
        ]
    }

    mock_get.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert result["id"] == 100  # noqa: PLR2004
    assert result["status"] == "in_progress"
    # Should return immediately without waiting


@patch.dict(
    os.environ,
    {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_TOKEN": "test_token",
        "DO_NOT_WAIT_FOR_SUCCESS": "true",
    },
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_do_not_wait_returns_latest_failed_with_older_successful(mock_get):
    # Test that DO_NOT_WAIT_FOR_SUCCESS=true returns latest even if it failed (with older successful available)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "workflow_runs": [
            {
                "id": 102,
                "status": "completed",
                "conclusion": "failure",
            },  # Latest, failed
            {
                "id": 101,
                "status": "completed",
                "conclusion": "success",
            },  # Older, successful
        ]
    }

    mock_get.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert (
        result["id"] == OLDER_SUCCESSFUL_WORKFLOW_ID
    )  # Should still use the older successful one, not the failed latest


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_standard_behavior_fetches_all_workflows(mock_get):
    # Test that standard behavior fetches all workflows and filters failed ones
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "workflow_runs": [
            {
                "id": SUCCESSFUL_WORKFLOW_ID,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 99,
                "status": "completed",
                "conclusion": "failure",
            },  # Should be filtered out
            {
                "id": 98,
                "status": "completed",
                "conclusion": "cancelled",
            },  # Should be filtered out
        ]
    }

    mock_get.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert result["id"] == SUCCESSFUL_WORKFLOW_ID  # Should get the successful one
    # Should have made only one request for all workflows
    assert mock_get.call_count == 1
    # Call should not have status filter (gets all workflows)
    call_args = mock_get.call_args[0][0]
    assert "status=success" not in call_args
    assert "status=in_progress" not in call_args


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_latest_failed_uses_older_successful(mock_get):
    # Test when latest workflow failed but older successful exists
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "workflow_runs": [
            {
                "id": 102,
                "status": "completed",
                "conclusion": "failure",
            },  # Latest, failed
            {
                "id": 101,
                "status": "completed",
                "conclusion": "success",
            },  # Older, successful
            {
                "id": SUCCESSFUL_WORKFLOW_ID,
                "status": "completed",
                "conclusion": "success",
            },
        ]
    }

    mock_get.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert (
        result["id"] == OLDER_SUCCESSFUL_WORKFLOW_ID
    )  # Should use the older successful one, not the latest failed


@patch.dict(
    os.environ,
    {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_TOKEN": "test_token",
    },
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
@patch("github_semver.commit_version.time.sleep")
def test_waits_for_latest_workflow_only(mock_sleep, mock_get):  # noqa: ARG001
    # Test that when waiting, only waits for the latest (most recent) workflow
    # First call returns in-progress workflow
    initial_response = MagicMock()
    initial_response.status_code = 200
    initial_response.headers = {"Link": None}
    initial_response.raise_for_status.return_value = None
    initial_response.json.return_value = {
        "workflow_runs": [
            {
                "id": 102,
                "status": "in_progress",
                "conclusion": None,
            },  # Latest, in-progress
            {
                "id": 101,
                "status": "completed",
                "conclusion": "success",
            },  # Older, successful
        ]
    }

    # Second call (polling the specific workflow) returns completed
    polling_response = MagicMock()
    polling_response.status_code = 200
    polling_response.raise_for_status.return_value = None
    polling_response.json.return_value = {
        "id": 102,
        "status": "completed",
        "conclusion": "success",
    }

    mock_get.side_effect = [initial_response, polling_response]

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert (
        result["id"] == LATEST_IN_PROGRESS_WORKFLOW_ID
    )  # Should return the latest workflow after it completes
    assert (
        mock_get.call_count == EXPECTED_API_CALL_COUNT
    )  # One for listing, one for polling specific workflow
    # Second call should be to the specific workflow run endpoint
    second_call_url = mock_get.call_args_list[1][0][0]
    assert f"/actions/runs/{LATEST_IN_PROGRESS_WORKFLOW_ID}" in second_call_url
