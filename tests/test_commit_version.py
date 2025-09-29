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


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_get_last_successful_workflow_for_commit(mock_get):
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": None}  # No pagination
    mock_response.raise_for_status.return_value = None

    workflow_data = {
        "workflow_runs": [
            {"id": 123, "status": "completed", "conclusion": "success"},
            {
                "id": EXPECTED_LATEST_WORKFLOW_ID,
                "status": "completed",
                "conclusion": "success",
            },
        ]
    }
    mock_response.json.return_value = workflow_data
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
    # Create responses for multiple pages
    page1_response = MagicMock()
    page1_response.status_code = 200
    page1_response.headers = {
        "Link": '<https://api.github.com/repos/owner/repo/actions/runs?page=2>; rel="next"'
    }
    page1_response.raise_for_status.return_value = None
    page1_response.json.return_value = {
        "workflow_runs": [
            {"id": 100 + i, "status": "completed", "conclusion": "success"}
            for i in range(100)
        ]
    }

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
