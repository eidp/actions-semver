from unittest.mock import MagicMock, patch

from github_semver.github_auth_redirect_adapter import GitHubAuthRedirectAdapter


class TestGitHubAuthRedirectAdapter:
    """Test cases for GitHubAuthRedirectAdapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.original_url = (
            "https://api.github.com/repos/owner/repo/actions/artifacts/123/zip"
        )
        self.auth_headers = {
            "Authorization": "Bearer test_token",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.adapter = GitHubAuthRedirectAdapter(self.original_url, self.auth_headers)

    def test_adapter_initialization(self):
        """Test that adapter initializes correctly."""
        assert self.adapter.original_url == self.original_url
        assert self.adapter.auth_headers == self.auth_headers

    @patch("github_semver.github_auth_redirect_adapter._should_include_auth_header")
    def test_send_includes_auth_headers_same_host(self, mock_should_include):
        """Test that auth headers are included when redirecting to same host."""
        mock_should_include.return_value = True

        # Create a mock request
        request = MagicMock()
        request.url = "https://api.github.com/redirected/path"
        request.headers = {}

        # Mock the parent send method
        with patch("requests.adapters.HTTPAdapter.send") as mock_parent_send:
            mock_response = MagicMock()
            mock_parent_send.return_value = mock_response

            result = self.adapter.send(request)

            # Verify auth headers were added
            assert "Authorization" in request.headers
            assert request.headers["Authorization"] == "Bearer test_token"
            assert request.headers["Accept"] == "application/vnd.github+json"
            assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"

            # Verify User-Agent was added
            assert request.headers["User-Agent"] == "actions-semver/1.0"

            # Verify parent send was called
            mock_parent_send.assert_called_once_with(request)
            assert result == mock_response

    # ...existing code...
