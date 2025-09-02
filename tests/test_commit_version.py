import json
import os
from unittest.mock import MagicMock, patch

from github_semver.commit_version import (
    get_jobs_for_workflow_run,
    get_last_successful_workflow_for_commit,
)

# Test constants
EXPECTED_LATEST_WORKFLOW_ID = 124
EXPECTED_JOB_COUNT = 2


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.urllib.request.urlopen")
def test_get_last_successful_workflow_for_commit(mock_urlopen):
    # Mock response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__.return_value = mock_response

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
    mock_response.read.return_value = json.dumps(workflow_data).encode()
    mock_urlopen.return_value = mock_response

    result = get_last_successful_workflow_for_commit("abc123")

    assert result is not None
    assert result["id"] == EXPECTED_LATEST_WORKFLOW_ID  # Should return the latest one


@patch.dict(
    os.environ,
    {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"},
    clear=True,
)
@patch("github_semver.commit_version.urllib.request.urlopen")
def test_get_jobs_for_workflow_run(mock_urlopen):
    # Mock response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__.return_value = mock_response

    jobs_data = {
        "jobs": [{"name": "generate-version", "id": 1}, {"name": "build", "id": 2}]
    }
    mock_response.read.return_value = json.dumps(jobs_data).encode()
    mock_urlopen.return_value = mock_response

    result = get_jobs_for_workflow_run("123")

    assert result is not None
    assert len(result) == EXPECTED_JOB_COUNT
    assert result[0]["name"] == "generate-version"
