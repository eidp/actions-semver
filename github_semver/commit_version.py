import argparse
import io
import logging
import os
import sys
import zipfile
from typing import Any

import requests

from .github_auth_redirect_adapter import GitHubAuthRedirectAdapter

logger = logging.getLogger(__name__)

# Constants
HTTP_FORBIDDEN = 403

api_url = os.getenv("GITHUB_API_URL", "https://api.github.com")
repository = os.getenv("GITHUB_REPOSITORY")  # format: owner/repo
github_token = os.getenv("GITHUB_TOKEN")
headers = (
    {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_token
    else {}
)
list_all_workflows = os.getenv("LIST_ALL_WORKFLOWS", "False").lower() in (
    "true",
    "1",
    "yes",
)


def get_last_successful_workflow_for_commit(
    commit_sha: str,
    workflow_name: str | None = None,
) -> dict[str, Any] | None:
    """
    Use GitHub API to retrieve the last successful workflow run for a specific commit.

    Args:
        commit_sha (str): full sha to search workflow runs for.
        workflow_name (str, optional): name of the workflow to filter by.

    Returns:
        dict | None: workflow run found for this specific commit.
            (ex.: https://docs.github.com/en/rest/actions/workflow-runs)
    """
    logger.info(f"Searching for workflow runs for commit: {commit_sha}")
    url = f"{api_url}/repos/{repository}/actions/runs?head_sha={commit_sha}&status=success"
    if list_all_workflows:
        logger.info("Checking for in_progress workflows")
        url = f"{api_url}/repos/{repository}/actions/runs?head_sha={commit_sha}"

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    workflow_runs = data.get("workflow_runs", [])

    logger.info(f"Found {len(workflow_runs)} workflow runs for commit {commit_sha}")

    if not workflow_runs:
        logger.info(
            f"No {'in progress' if list_all_workflows else 'successful'} workflow runs found for workflow '{workflow_name}'"
        )
        return None

    # Filter by workflow name if specified
    if workflow_name:
        workflow_runs = [
            run for run in workflow_runs if run.get("name") == workflow_name
        ]

        if not workflow_runs:
            logger.info(
                f"No {'in progress' if list_all_workflows else 'successful'} workflow runs found for workflow '{workflow_name}'"
            )
            return None

    # Sort workflow runs by ID or created_at date (latest first)
    return sorted(workflow_runs, key=lambda x: x["id"], reverse=True)[0]


def _get_artifact_metadata(run_id: str, artifact_name: str) -> dict[str, Any]:
    """Get artifact metadata from workflow run."""
    url = f"{api_url}/repos/{repository}/actions/runs/{run_id}/artifacts"
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    artifacts = data.get("artifacts", [])

    # Find the artifact by name
    for artifact in artifacts:
        if artifact["name"] == artifact_name:
            # Check if artifact has expired
            if artifact.get("expired", False):
                raise ValueError(
                    f"Artifact '{artifact_name}' has expired and is no longer available for download"
                )
            return artifact

    raise ValueError(f"Artifact '{artifact_name}' not found in workflow run {run_id}")


def _extract_zip_content(zip_content: bytes, artifact_name: str) -> str:
    """Extract content from zip file."""
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
        # Assume the artifact contains a single file with the version
        for file_name in zip_file.namelist():
            if file_name == artifact_name or file_name.endswith(f"/{artifact_name}"):
                return zip_file.read(file_name).decode("utf-8").rstrip()

        # If exact match not found, try the first file
        if zip_file.namelist():
            return zip_file.read(zip_file.namelist()[0]).decode("utf-8").rstrip()

    raise ValueError(f"No content found in artifact '{artifact_name}'")


def download_artifact(run_id: str, artifact_name: str) -> str:
    """
    Use GitHub API to retrieve an artifact for a specific workflow run.

    Args:
        run_id (str): Workflow run ID on which to search for the artifact.
        artifact_name (str): name of artifact to download.

    Returns:
        str: content of the downloaded artifact.
            (ex.: https://docs.github.com/en/rest/actions/artifacts)
    """
    try:
        session = None
        # Get artifact metadata
        target_artifact = _get_artifact_metadata(run_id, artifact_name)
        logger.info(
            f"Found artifact '{artifact_name}' with ID: {target_artifact['id']}"
        )

        download_url = f"{api_url}/repos/{repository}/actions/artifacts/{target_artifact['id']}/zip"

        # Use requests session to handle redirects with proper auth header logic
        session = requests.Session()

        # Mount the custom adapter
        session.mount("http://", GitHubAuthRedirectAdapter(download_url, headers))
        session.mount("https://", GitHubAuthRedirectAdapter(download_url, headers))

        # Make the request with the session (will handle redirects automatically)
        response = session.get(download_url, timeout=30)
        response.raise_for_status()

        # Extract and return content
        return _extract_zip_content(response.content, artifact_name)

    except requests.exceptions.HTTPError as e:
        if e.response and e.response.status_code == HTTP_FORBIDDEN:
            error_msg = (
                f"403 Forbidden when downloading artifact '{artifact_name}'. "
                f"This could be due to: Insufficient permissions (ensure GITHUB_TOKEN has 'actions:read' scope), "
                f"Original error: {e}"
            )
            raise ValueError(error_msg) from e
        raise
    finally:
        # Clean up session
        try:
            if session is not None:
                session.close()
        except (AttributeError, OSError) as e:
            # Log the exception but don't let it propagate since we're in cleanup
            # Only catch specific exceptions that might occur during session.close()
            logger.warning(f"Failed to close session during cleanup: {e}")


def main(commit_sha: str, artifact_name: str, workflow_name: str | None = None) -> None:
    """Entrypoint for script that prints content of artifact
    generated in a workflow run that has previously run for commit with
    given sha.

    This is useful in scenario's such as tagging existing commits, to allow reuse
    of previously generated artifacts.

    Args:
        commit_sha (str): sha of commit for which a workflow run has run before.
        artifact_name (str, optional): name of artifact to download from the given workflow run.
            Defaults to "version".
        workflow_name (str, optional): name of the workflow to filter by.

    Returns:
        Returns none, outputs content to stdout.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        last_workflow_run = get_last_successful_workflow_for_commit(
            commit_sha, workflow_name
        )
        if last_workflow_run:
            logger.info(
                f"Last successful workflow run has ID: {last_workflow_run['id']}"
            )
            if workflow_name:
                logger.info(f"Found workflow run for workflow '{workflow_name}'")

            # Download artifact directly from the workflow run
            try:
                version = download_artifact(last_workflow_run["id"], artifact_name)
            except (requests.exceptions.RequestException, ValueError) as e:
                logger.warning(f"Could not download artifact: {e}")
            else:
                logger.info(f"found version from artifact: {version}")
                print(version)  # print result to stdout
                return

    except requests.exceptions.HTTPError as e:
        print(
            f"HTTP error occurred: {e.response.status_code if e.response else 'Unknown'} - {e}"
        )

    logger.error(
        "\033[1;31m Unable to retrieve finished workflow run for this commit, wait for a previous build to finish before tagging. Exiting.\033[0m"
    )
    sys.exit(1)


if __name__ == "__main__":
    github_sha = os.getenv("GITHUB_SHA")
    workflow = os.getenv("GITHUB_WORKFLOW")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit-sha",
        help=(
            "The full hash of the commit for which you "
            "want to retrieve the version artifact."
        ),
        default=github_sha,
    )
    parser.add_argument(
        "--artifact-name", help="The name of the version artifact.", default="version"
    )
    parser.add_argument(
        "--workflow-name",
        help="The name of the workflow to filter by. If not specified, uses the most recent workflow run.",
        default=workflow,
    )
    args = parser.parse_args()

    main(args.commit_sha, args.artifact_name, args.workflow_name)
