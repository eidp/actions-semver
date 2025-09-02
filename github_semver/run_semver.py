import logging
import os
import re
import subprocess

from .bumps import append_rc, bump_build, bump_patch

logger = logging.getLogger(__name__)


def _retrieve_latest_tag_from_git() -> str | None:
    # raw tag is a line which is 'tab' separated, with hash on the left
    # tag on the right. tag is in a refs/tags/0.0.x format.
    raw_output = subprocess.check_output(
        "git ls-remote --refs --tags --sort='-v:refname'",
        shell=True,
    ).decode()
    logger.debug(f"shell output is: {raw_output}")
    tag_lines = raw_output.splitlines()
    for tag in tag_lines:
        if semver_match := re.search(r"refs/tags/([0-9]+\..*)", tag):
            return semver_match.group(1)

    return None


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    try:
        # GitHub Actions environment variables
        sha1 = os.environ["GITHUB_SHA"][:7]  # Short SHA equivalent

        # Determine branch name from different GitHub contexts
        github_ref = os.environ["GITHUB_REF"]
        github_ref_name = os.environ.get("GITHUB_REF_NAME", "")
        github_head_ref = os.environ.get("GITHUB_HEAD_REF", "")  # For pull requests

        # Extract branch name based on context
        if github_head_ref:
            # This is a pull request
            branch = github_head_ref
        elif github_ref.startswith("refs/heads/"):
            # This is a push to a branch
            branch = github_ref_name
        else:
            # Fallback to ref name
            branch = github_ref_name

        # Default branch name, defaulting to 'main' if not set
        default_branch = os.environ.get("REPO_DEFAULT_BRANCH", "main")

        # GitHub Actions run number as build number
        build_number = os.environ["GITHUB_RUN_NUMBER"]

        # if 'RC' building is enabled, 'rc' suffix will be added
        # on generate semver.
        build_rc_semver = os.getenv("BUILD_RC_SEMVER", "True").lower() in (
            "true",
            "1",
            "yes",
        )
    except KeyError as e:
        raise RuntimeError("expected environment values are not set.") from e

    if default_branch == branch:
        try:
            if not (latest_tag := _retrieve_latest_tag_from_git()):
                latest_tag = "0.0.1"
            logger.info(f"latest tag is {latest_tag}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"command '{e.cmd}' return with error (code {e.returncode}): {e.output}"
            ) from e

        logger.info("building on default branch, triggering a patch bump on latest tag")
        new_version = bump_patch(latest_tag)
        if build_rc_semver:
            new_version = append_rc(new_version, sha1, build_number)
    else:
        logger.info("building on a feature branch, bump build number")
        new_version = bump_build("0.0.0", branch, sha1, build_number)

    logger.info(f"new version is {new_version}")
    print(new_version)


if __name__ == "__main__":
    main()
