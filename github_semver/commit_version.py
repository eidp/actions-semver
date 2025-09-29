import argparse
import io
import logging
import os
import re
import sys
import time
import zipfile
from typing import Any

import requests

from .github_auth_redirect_adapter import GitHubAuthRedirectAdapter

logger = logging.getLogger(__name__)

# Constants
HTTP_FORBIDDEN = 403
HTTP_RATE_LIMITED = 429
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 32.0  # seconds
PER_PAGE = 100  # Maximum allowed by GitHub API

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


def _parse_link_header(link_header: str | None) -> dict[str, str]:
    """Parse GitHub's Link header to extract pagination URLs.

    Args:
        link_header: The Link header value from the response

    Returns:
        Dictionary mapping rel values to URLs
    """
    if not link_header:
        return {}

    links = {}
    # Parse links like: <https://api.github.com/...?page=2>; rel="next"
    for link in link_header.split(","):
        match = re.match(r'<([^>]+)>;\s*rel="([^"]+)"', link.strip())
        if match:
            url, rel = match.groups()
            links[rel] = url

    return links


def _make_request_with_retry(
    url: str,
    headers: dict[str, str],
    max_retries: int = MAX_RETRIES,
) -> requests.Response:
    """Make an HTTP request with exponential backoff retry for rate limiting.

    Args:
        url: The URL to request
        headers: Headers to include in the request
        max_retries: Maximum number of retry attempts

    Returns:
        The response object

    Raises:
        requests.exceptions.HTTPError: If the request fails after all retries
    """
    backoff = INITIAL_BACKOFF

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == HTTP_RATE_LIMITED:
                # Check if we have rate limit reset time
                reset_time = response.headers.get("X-RateLimit-Reset")
                if reset_time:
                    # Wait until the rate limit resets
                    wait_time = max(0, int(reset_time) - int(time.time()))
                    if wait_time > 0:
                        logger.info(
                            f"Rate limited. Waiting {wait_time} seconds until reset."
                        )
                        time.sleep(wait_time + 1)  # Add 1 second buffer
                        continue

                # Otherwise use exponential backoff
                if attempt < max_retries - 1:
                    wait_time = min(backoff, MAX_BACKOFF)
                    logger.info(
                        f"Rate limited. Retrying in {wait_time} seconds (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    backoff *= 2
                    continue

            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == HTTP_RATE_LIMITED:
                if attempt == max_retries - 1:
                    logger.exception(
                        f"Max retries ({max_retries}) exceeded for rate limiting"
                    )
                    raise
            else:
                # For non-rate-limit errors, raise immediately
                raise
        else:
            return response

    raise requests.exceptions.HTTPError(f"Failed after {max_retries} retries")


def get_last_successful_workflow_for_commit(
    commit_sha: str,
    workflow_name: str | None = None,
) -> dict[str, Any] | None:
    """
    Use GitHub API to retrieve the last successful workflow run for a specific commit.

    This function supports pagination to retrieve all workflow runs, not just the
    first page. It also includes retry logic with exponential backoff for rate limiting.

    Args:
        commit_sha (str): full sha to search workflow runs for.
        workflow_name (str, optional): name of the workflow to filter by.

    Returns:
        dict | None: workflow run found for this specific commit.
            (ex.: https://docs.github.com/en/rest/actions/workflow-runs)
    """
    logger.info(f"Searching for workflow runs for commit: {commit_sha}")

    # Build initial URL with per_page parameter
    base_url = f"{api_url}/repos/{repository}/actions/runs"
    params = f"?head_sha={commit_sha}&per_page={PER_PAGE}"

    if not list_all_workflows:
        params += "&status=success"

    url = base_url + params

    if list_all_workflows:
        logger.info("Checking for in_progress workflows")

    all_workflow_runs = []
    page_count = 0
    total_fetched = 0

    # Paginate through all results
    while url:
        page_count += 1
        logger.debug(f"Fetching page {page_count} from: {url}")

        # Use retry logic for the request
        response = _make_request_with_retry(url, headers)

        data = response.json()
        page_runs = data.get("workflow_runs", [])
        all_workflow_runs.extend(page_runs)
        total_fetched += len(page_runs)

        logger.debug(
            f"Page {page_count}: fetched {len(page_runs)} runs (total: {total_fetched})"
        )

        # Check for next page
        links = _parse_link_header(response.headers.get("Link"))
        url = links.get("next")
        if not url:
            logger.debug("No more pages to fetch")
            break

    logger.info(
        f"Found {len(all_workflow_runs)} total workflow runs for commit {commit_sha} across {page_count} page(s)"
    )

    if not all_workflow_runs:
        logger.info(
            f"No {'in progress' if list_all_workflows else 'successful'} workflow runs found for commit '{commit_sha}'"
        )
        return None

    # Filter by workflow name if specified
    if workflow_name:
        filtered_runs = [
            run for run in all_workflow_runs if run.get("name") == workflow_name
        ]

        if not filtered_runs:
            logger.info(
                f"No {'in progress' if list_all_workflows else 'successful'} workflow runs found for workflow '{workflow_name}'"
            )
            return None
        all_workflow_runs = filtered_runs
        logger.info(
            f"Filtered to {len(all_workflow_runs)} runs for workflow '{workflow_name}'"
        )

    # Sort workflow runs by ID (latest first) and return the most recent
    sorted_runs = sorted(all_workflow_runs, key=lambda x: x["id"], reverse=True)
    latest_run = sorted_runs[0]
    logger.info(f"Returning most recent workflow run with ID: {latest_run['id']}")
    return latest_run


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
        if e.response and e.response.status_code == HTTP_FORBIDDEN:
            error_msg = (
                f"403 Forbidden when downloading artifact '{artifact_name}'. "
                f"This could be due to: Insufficient permissions (ensure GITHUB_TOKEN has 'actions:read' scope), "
                f"Original error: {e}"
            )
            logger.exception(error_msg)
        else:
            logger.exception(
                f"HTTP error occurred: {e.response.status_code if e.response else 'Unknown'}"
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
