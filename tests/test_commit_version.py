import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from github_semver.commit_version import (
    _get_artifact_metadata,
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


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_get_artifact_metadata(mock_get):
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None

    artifact_data = {
        "artifacts": [
            {"id": EXPECTED_ARTIFACT_ID, "name": "version", "expired": False},
            {"id": 124, "name": "other-artifact", "expired": False},
        ]
    }
    mock_response.json.return_value = artifact_data
    mock_get.return_value = mock_response

    result = _get_artifact_metadata("456", "version")

    assert result is not None
    assert result["id"] == EXPECTED_ARTIFACT_ID
    assert result["name"] == "version"


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
@patch("github_semver.commit_version.requests.Session")
@patch("github_semver.commit_version.requests.get")
def test_download_artifact_403_error(mock_get, mock_session_class):
    # Mock artifact metadata request
    metadata_response = MagicMock()
    metadata_response.status_code = 200
    metadata_response.raise_for_status.return_value = None
    metadata_response.json.return_value = {
        "artifacts": [{"id": EXPECTED_ARTIFACT_ID, "name": "version", "expired": False}]
    }
    mock_get.return_value = metadata_response

    # Mock session
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session

    # Mock 403 error response
    error_response = MagicMock()
    error_response.status_code = 403
    http_error = requests.exceptions.HTTPError()
    http_error.response = error_response
    mock_session.get.side_effect = http_error

    with pytest.raises(ValueError, match="403 Forbidden.*actions:read"):
        download_artifact("456", "version")

    # Verify session was still closed despite the error
    mock_session.close.assert_called_once()
