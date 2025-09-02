import json
import os
from unittest.mock import MagicMock, patch

import requests

from github_semver.commit_version import (
    get_last_successful_workflow_for_commit,
    download_artifact,
    _get_artifact_metadata,
    _extract_zip_content,
)

# Test constants
EXPECTED_LATEST_WORKFLOW_ID = 124
EXPECTED_JOB_COUNT = 2


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
            {"id": 123, "name": "version", "expired": False},
            {"id": 124, "name": "other-artifact", "expired": False},
        ]
    }
    mock_response.json.return_value = artifact_data
    mock_get.return_value = mock_response

    result = _get_artifact_metadata("456", "version")

    assert result is not None
    assert result["id"] == 123
    assert result["name"] == "version"


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_download_artifact_with_redirect(mock_get):
    # Mock first response (artifact metadata)
    metadata_response = MagicMock()
    metadata_response.status_code = 200
    metadata_response.raise_for_status.return_value = None
    metadata_response.json.return_value = {
        "artifacts": [{"id": 123, "name": "version", "expired": False}]
    }

    # Mock second response (initial download request with redirect)
    redirect_response = MagicMock()
    redirect_response.status_code = 302
    redirect_response.headers = {"Location": "https://external-storage.com/artifact.zip"}

    # Mock third response (actual artifact download)
    download_response = MagicMock()
    download_response.status_code = 200
    download_response.raise_for_status.return_value = None
    # Mock zip content containing "1.2.3"
    import zipfile
    import io
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        zip_file.writestr("version", "1.2.3")
    download_response.content = zip_buffer.getvalue()

    # Configure mock to return different responses for different calls
    mock_get.side_effect = [metadata_response, redirect_response, download_response]

    result = download_artifact("456", "version")

    assert result == "1.2.3"
    assert mock_get.call_count == 3


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_download_artifact_without_redirect(mock_get):
    # Mock first response (artifact metadata)
    metadata_response = MagicMock()
    metadata_response.status_code = 200
    metadata_response.raise_for_status.return_value = None
    metadata_response.json.return_value = {
        "artifacts": [{"id": 123, "name": "version", "expired": False}]
    }

    # Mock second response (direct download without redirect)
    download_response = MagicMock()
    download_response.status_code = 200
    download_response.raise_for_status.return_value = None
    # Mock zip content containing "2.0.0"
    import zipfile
    import io
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        zip_file.writestr("version", "2.0.0")
    download_response.content = zip_buffer.getvalue()

    # Configure mock to return different responses for different calls
    mock_get.side_effect = [metadata_response, download_response]

    result = download_artifact("456", "version")

    assert result == "2.0.0"
    assert mock_get.call_count == 2


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
        "artifacts": [{"id": 123, "name": "version", "expired": True}]
    }
    mock_get.return_value = mock_response

    try:
        download_artifact("456", "version")
        assert False, "Expected ValueError for expired artifact"
    except ValueError as e:
        assert "expired" in str(e)


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.requests.get")
def test_download_artifact_403_error(mock_get):
    # Mock first response (artifact metadata)
    metadata_response = MagicMock()
    metadata_response.status_code = 200
    metadata_response.raise_for_status.return_value = None
    metadata_response.json.return_value = {
        "artifacts": [{"id": 123, "name": "version", "expired": False}]
    }

    # Mock second response (403 error)
    error_response = MagicMock()
    error_response.status_code = 403
    http_error = requests.exceptions.HTTPError()
    http_error.response = error_response
    error_response.raise_for_status.side_effect = http_error

    mock_get.side_effect = [metadata_response, error_response]

    try:
        download_artifact("456", "version")
        assert False, "Expected ValueError for 403 error"
    except ValueError as e:
        assert "403 Forbidden" in str(e)
        assert "actions:read" in str(e)
