from urllib.parse import urlparse

import requests.adapters


def _get_hostname(url: str) -> str:
    """Extract hostname from URL, normalizing GitHub hostnames."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Normalize GitHub hostnames (similar to ghauth.NormalizeHostname in Go)
    if hostname in ("github.com", "www.github.com"):
        return "github.com"
    if hostname.endswith(".github.com"):
        return hostname

    return hostname


def _should_include_auth_header(original_url: str, redirect_url: str) -> bool:
    """
    Determine if auth header should be included based on hostname comparison.
    Only include auth header if redirect is to the same host as original request.
    """
    original_host = _get_hostname(original_url)
    redirect_host = _get_hostname(redirect_url)

    # Only include auth header if hostname hasn't changed
    return original_host == redirect_host


class GitHubAuthRedirectAdapter(requests.adapters.HTTPAdapter):
    """
    A custom HTTPAdapter to handle redirects while preserving auth headers
    for same-host redirects and removing them for cross-host redirects.
    """

    def __init__(self, original_url: str, auth_headers: dict) -> None:
        super().__init__()
        self.original_url = original_url
        self.auth_headers = auth_headers

    def send(
        self, request: requests.PreparedRequest, **kwargs: object
    ) -> requests.Response:
        # Only add auth headers if we're on the same host as original request
        # or if this is the initial request
        if not hasattr(request, "url") or _should_include_auth_header(
            self.original_url, request.url
        ):
            # Add auth headers if not already present
            if "Authorization" not in request.headers and self.auth_headers:
                request.headers.update(self.auth_headers)
        else:
            # Remove auth headers for cross-host redirects
            request.headers.pop("Authorization", None)

        # Always include User-Agent
        if "User-Agent" not in request.headers:
            request.headers["User-Agent"] = "actions-semver/1.0"

        return super().send(request, **kwargs)
