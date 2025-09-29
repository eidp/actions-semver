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
# Waiting for workflows
WORKFLOW_POLL_INTERVAL = 10  # seconds between polls
MAX_WAIT_TIME = 1800  # 30 minutes maximum wait time

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


def _should_wait_for_success() -> bool:
    """
    Check if we should wait for workflows to complete successfully.
    If False, immediately return in-progress workflows if found.
    """
    # Default to True (wait for success) for backwards compatibility
    return os.getenv("DO_NOT_WAIT_FOR_SUCCESS", "False").lower() not in (
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


def _wait_for_workflow_completion(
    workflow_run: dict[str, Any],
    max_wait_time: int = MAX_WAIT_TIME,
) -> dict[str, Any] | None:
    """
    Wait for a specific workflow run to complete successfully.

    Args:
        workflow_run (dict): the specific workflow run to wait for.
        max_wait_time (int): maximum time to wait in seconds.

    Returns:
        dict | None: the workflow run if it completes successfully, or None if timeout/failed.
    """
    run_id = workflow_run["id"]
    logger.info(f"Waiting for workflow run {run_id} to complete (max {max_wait_time}s)")
    start_time = time.time()

    while time.time() - start_time < max_wait_time:
        # Check the current status of this specific workflow run
        url = f"{api_url}/repos/{repository}/actions/runs/{run_id}"
        response = _make_request_with_retry(url, headers)
        current_run = response.json()

        status = current_run.get("status")
        conclusion = current_run.get("conclusion")

        if status == "completed":
            if conclusion == "success":
                logger.info(f"Workflow run {run_id} completed successfully")
                return current_run
            logger.info(
                f"Workflow run {run_id} completed with conclusion: {conclusion}"
            )
            return None  # Workflow failed

        logger.info(
            f"Workflow run {run_id} still in progress, waiting {WORKFLOW_POLL_INTERVAL}s..."
        )
        time.sleep(WORKFLOW_POLL_INTERVAL)

    logger.info(f"Timeout waiting for workflow run {run_id}")
    return None


def get_last_successful_workflow_for_commit(
    commit_sha: str,
    workflow_name: str | None = None,
) -> dict[str, Any] | None:
    """
    Use GitHub API to retrieve the last successful workflow run for a specific commit.

    This function supports pagination to retrieve all workflow runs, not just the
    first page. It also includes retry logic with exponential backoff for rate limiting.

    Always fetches both successful and in-progress workflows. If DO_NOT_WAIT_FOR_SUCCESS
    is set, immediately returns in-progress workflow. Otherwise, waits for them to complete.

    Args:
        commit_sha (str): full sha to search workflow runs for.
        workflow_name (str, optional): name of the workflow to filter by.

    Returns:
        dict | None: workflow run found for this specific commit.
            (ex.: https://docs.github.com/en/rest/actions/workflow-runs)
    """
    logger.info(f"Searching for workflow runs for commit: {commit_sha}")

    wait_for_success = _should_wait_for_success()
    if not wait_for_success:
        logger.info("Will return immediately if in-progress workflows found")
    else:
        logger.info("Will wait for workflows to complete successfully")

    # Fetch all workflows and filter out failed ones
    all_workflow_runs = _fetch_all_workflow_runs(commit_sha)

    # Handle case when no workflows are found
    if not all_workflow_runs:
        return _handle_no_workflows_found(
            commit_sha,
            workflow_name,
            wait_for_success=wait_for_success,
        )

    # Filter by workflow name if specified
    if workflow_name:
        all_workflow_runs = _filter_workflows_by_name(all_workflow_runs, workflow_name)
        if not all_workflow_runs:
            return _handle_no_workflows_found(
                commit_sha,
                workflow_name,
                wait_for_success=wait_for_success,
            )

    # Sort workflow runs by ID (latest first)
    sorted_runs = sorted(all_workflow_runs, key=lambda x: x["id"], reverse=True)

    # Find the best workflow run based on configuration
    return _find_best_workflow_run(
        sorted_runs,
        wait_for_success=wait_for_success,
    )


def _fetch_all_workflow_runs(
    commit_sha: str,
) -> list[dict[str, Any]]:
    """Fetch all workflow runs for a commit and filter out only failed/cancelled ones."""
    base_url = f"{api_url}/repos/{repository}/actions/runs"
    params = f"?head_sha={commit_sha}&per_page={PER_PAGE}"
    url = base_url + params

    all_workflow_runs = []
    page_count = 0

    while url:
        page_count += 1
        logger.debug(f"Fetching workflows page {page_count} from: {url}")

        response = _make_request_with_retry(url, headers)
        data = response.json()
        page_runs = data.get("workflow_runs", [])

        # Filter out only failed/cancelled workflows
        # Keep successful, in-progress, and other states that might transition to success
        filtered_runs = [
            run
            for run in page_runs
            if not (
                run.get("status") == "completed"
                and run.get("conclusion") in ("failure", "cancelled", "skipped")
            )
        ]
        all_workflow_runs.extend(filtered_runs)

        logger.debug(
            f"Page {page_count}: fetched {len(page_runs)} runs, "
            f"kept {len(filtered_runs)} (excluding failed/cancelled)"
        )

        links = _parse_link_header(response.headers.get("Link"))
        url = links.get("next")
        if not url:
            logger.debug("No more pages to fetch")
            break

    logger.info(
        f"Found {len(all_workflow_runs)} workflow runs (excluding failed/cancelled) across {page_count} page(s)"
    )
    return all_workflow_runs


def _filter_workflows_by_name(
    workflow_runs: list[dict[str, Any]], workflow_name: str
) -> list[dict[str, Any]]:
    """Filter workflow runs by workflow name."""
    filtered = [run for run in workflow_runs if run.get("name") == workflow_name]
    logger.info(f"Filtered to {len(filtered)} runs for workflow '{workflow_name}'")
    return filtered


def _find_best_workflow_run(
    sorted_runs: list[dict[str, Any]],
    *,
    wait_for_success: bool,
) -> dict[str, Any] | None:
    """Find the best workflow run based on the current configuration."""
    if not sorted_runs:
        return None

    # The most recent workflow run (highest ID)
    latest_run = sorted_runs[0]
    status = latest_run.get("status")
    conclusion = latest_run.get("conclusion")

    # If the latest run is successful, return it
    if status == "completed" and conclusion == "success":
        logger.info(
            f"Returning most recent successful workflow run with ID: {latest_run['id']}"
        )
        return latest_run

    # If the latest run is in progress or other non-final state
    if status in [
        "in_progress",
        "action_required",
        "queued",
        "requested",
        "waiting",
        "pending",
    ]:
        if not wait_for_success:
            # Return immediately with the in-progress workflow
            logger.info(
                f"Returning most recent in-progress workflow run with ID: {latest_run['id']} (DO_NOT_WAIT_FOR_SUCCESS is set)"
            )
            return latest_run
        # Wait for THIS specific workflow to complete
        logger.info(
            f"Latest workflow run {latest_run['id']} has not finished yet, waiting for completion..."
        )
        return _wait_for_workflow_completion(latest_run)

    logger.info(
        f"No successful workflow runs found. Latest run {latest_run['id']} has status: {status}, conclusion: {conclusion}"
    )
    return None


def _handle_no_workflows_found(
    commit_sha: str,
    workflow_name: str | None,
) -> dict[str, Any] | None:
    """Handle the case when no workflows are found."""
    if workflow_name:
        logger.info(
            f"No successful or in-progress workflow runs found for workflow '{workflow_name}'"
        )
    else:
        logger.info(
            f"No successful or in-progress workflow runs found for commit '{commit_sha}'"
        )

    return None


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
            if "session" in locals() and session is not None:
                session.close()
        except (AttributeError, OSError) as e:
            # Log the exception but don't let it propagate since we're in cleanup
            # Only catch specific exceptions that might occur during session.close()
            logger.warning(f"Failed to close session during cleanup: {e}")


def main(commit_sha: str, artifact_name: str, workflow_name: str | None = None) -> int:
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
                return 0

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

    if not _should_wait_for_success():
        logger.error(
            "\033[1;31m Unable to retrieve any workflow run for this commit. No workflows found or none completed successfully. Exiting.\033[0m"
        )
    else:
        logger.error(
            "\033[1;31m Unable to retrieve finished workflow run for this commit after waiting. Consider setting DO_NOT_WAIT_FOR_SUCCESS=true to return in-progress builds immediately. Exiting.\033[0m"
        )
    return 1


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

    sys.exit(main(args.commit_sha, args.artifact_name, args.workflow_name))
