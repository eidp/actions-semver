import re
from typing import NamedTuple


class BuildInformation(NamedTuple):
    version: str
    build: str


def _split_build_tag(version_identifier: str) -> BuildInformation:
    parts = version_identifier.split("-", 1)

    return BuildInformation(parts[0], parts[1] if len(parts) > 1 else "")


def bump_major(current_ver: str) -> str:
    version, _ = _split_build_tag(current_ver)
    version_segments = version.split(".")

    bumped_ver = ".".join(
        [
            str(
                int(version_segments[0]) + 1,
            ),
            "0",
            "0",
        ]
    )
    return bumped_ver


def bump_minor(current_ver: str) -> str:
    version, _ = _split_build_tag(current_ver)
    version_segments = version.split(".")

    bumped_ver = ".".join(
        [
            version_segments[0],
            str(int(version_segments[1]) + 1),
            "0",
        ]
    )
    return bumped_ver


def bump_patch(current_ver: str) -> str:
    version, _ = _split_build_tag(current_ver)
    version_segments = version.split(".")

    bumped_ver = ".".join(
        [
            *version_segments[:-1],
            str(int(version_segments[-1]) + 1),
        ]
    )
    return bumped_ver


def bump_build(
    current_ver: str, branch_name: str, commit_sha1: str, build_number: int | str
) -> str:
    version, build = _split_build_tag(current_ver)

    if not build:
        # if a non-build version (such as 1.2.1), we will bump to
        # 1.2.2-build.<X>+<branch_name>.<commit_sha1>
        version = bump_patch(version)

    clean_branch = re.sub("[^A-Za-z0-9]+", "", branch_name)

    return "-".join(
        [version, "+".join([f"build.{build_number}", f"{clean_branch}.{commit_sha1}"])]
    )


def append_rc(current_ver: str, commit_sha1: str, build_number: int | str) -> str:
    version, _ = _split_build_tag(current_ver)

    return "-".join([version, "+".join([f"rc.{build_number}", f"{commit_sha1}"])])
