import argparse
import io
import json
import logging
import os
import sys
import urllib.error
import urllib.request
import zipfile
from http import HTTPStatus
from typing import Any

logger = logging.getLogger(__name__)

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
list_running_workflows = os.getenv("LIST_RUNNING_WORKFLOWS", "False").lower() in (
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
        commit_sha (str): full sha1 to search workflow runs for.
        workflow_name (str, optional): name of the workflow to filter by.

    Returns:
        dict | None: workflow run found for this specific commit.
            (ex.: https://docs.github.com/en/rest/actions/workflow-runs)
    """
    print(f"Searching for workflow runs for commit: {commit_sha}")
    url = f"{api_url}/repos/{repository}/actions/runs?head_sha={commit_sha}&status=success"
    if list_running_workflows:
        print("Checking for in_progress workflows")
        url = f"{api_url}/repos/{repository}/actions/runs?head_sha={commit_sha}&status=in_progress"

    req = urllib.request.Request(url, headers=headers)
    workflow_runs = None

    with urllib.request.urlopen(req) as response:
        # Check the status code
        if response.status != HTTPStatus.OK:
            raise ValueError(
                url, response.status, response.reason, response.headers, None
            )
        data = json.load(response)
        workflow_runs = data.get("workflow_runs", [])

    if not workflow_runs:
        logger.info(
            f"No {'in progress' if list_running_workflows else 'successful'} workflow runs found for workflow '{workflow_name}'"
        )
        return None

    # Filter by workflow name if specified
    if workflow_name:
        workflow_runs = [
            run for run in workflow_runs if run.get("name") == workflow_name
        ]

        if not workflow_runs:
            logger.info(
                f"No {'in progress' if list_running_workflows else 'successful'} workflow runs found for workflow '{workflow_name}'"
            )
            return None

    # Sort workflow runs by ID or created_at date (latest first)
    return sorted(workflow_runs, key=lambda x: x["id"], reverse=True)[0]


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
    # First, get the list of artifacts for the workflow run
    url = f"{api_url}/repos/{repository}/actions/runs/{run_id}/artifacts"
    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req) as response:
        if response.status != HTTPStatus.OK:
            raise ValueError(
                url, response.status, response.reason, response.headers, None
            )
        data = json.load(response)
        artifacts = data.get("artifacts", [])

    # Find the artifact by name
    target_artifact = None
    for artifact in artifacts:
        if artifact["name"] == artifact_name:
            target_artifact = artifact
            break

    if not target_artifact:
        raise ValueError(
            f"Artifact '{artifact_name}' not found in workflow run {run_id}"
        )

    # Check if artifact has expired
    if target_artifact.get("expired", False):
        raise ValueError(
            f"Artifact '{artifact_name}' has expired and is no longer available for download"
        )

    logger.info(f"Found artifact '{artifact_name}' with ID: {target_artifact['id']}")

    # Download the artifact
    download_url = (
        f"{api_url}/repos/{repository}/actions/artifacts/{target_artifact['id']}/zip"
    )
    req = urllib.request.Request(download_url, headers=headers)

    with urllib.request.urlopen(req) as response:
        if response.status != HTTPStatus.OK:
            raise ValueError(
                download_url, response.status, response.reason, response.headers, None
            )

        # GitHub artifacts are zip files, we need to extract the content
        zip_content = response.read()
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
            # Assume the artifact contains a single file with the version
            for file_name in zip_file.namelist():
                if file_name == artifact_name or file_name.endswith(
                    f"/{artifact_name}"
                ):
                    return zip_file.read(file_name).decode("utf-8").rstrip()

            # If exact match not found, try the first file
            if zip_file.namelist():
                return zip_file.read(zip_file.namelist()[0]).decode("utf-8").rstrip()

        raise ValueError(f"No content found in artifact '{artifact_name}'")


def main(
    commit_sha1: str, artifact_name: str, workflow_name: str | None = None
) -> None:
    """Entrypoint for script that prints content of artifact
    generated in a workflow run that has previously run for commit with
    given sha1.

    This is useful in scenario's such as tagging existing commits, to allow reuse
    of previously generated artifacts.

    Args:
        commit_sha1 (str): sha1 of commit for which a workflow run has run before.
        artifact_name (str, optional): name of artifact to download from the given workflow run.
            Defaults to "version".
        workflow_name (str, optional): name of the workflow to filter by.

    Returns:
        Returns none, outputs content to stdout.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        last_workflow_run = get_last_successful_workflow_for_commit(
            commit_sha1, workflow_name
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
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as e:
                logger.warning(f"Could not download artifact: {e}")
            else:
                logger.info(f"found version from artifact: {version}")
                print(version)  # print result to stdout
                return

    except urllib.error.HTTPError as e:
        print(f"HTTP error occurred: {e.code} - {e.reason}")
        pass

    logger.error(
        "\033[1;31m Unable to retrieve finished workflow run for this commit, wait for a previous build to finish before tagging. Exiting.\033[0m"
    )
    sys.exit(1)


if __name__ == "__main__":
    sha1 = os.getenv("GITHUB_SHA")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit-sha1",
        help=(
            "The full SHA of the commit for which you "
            "want to retrieve the version artifact."
        ),
        default=sha1,
    )
    parser.add_argument(
        "--artifact-name", help="The name of the version artifact.", default="version"
    )
    parser.add_argument(
        "--workflow-name",
        help="The name of the workflow to filter by. If not specified, uses the most recent workflow run.",
        default=None,
    )
    args = parser.parse_args()

    main(args.commit_sha1, args.artifact_name, args.workflow_name)
