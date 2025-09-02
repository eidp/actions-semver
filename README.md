# Actions Semver

This repository contains GitHub Actions for managing semantic versioning (semver) in your projects.

<!-- BEGIN ACTIONS -->

## 🛠️ GitHub Actions

The following GitHub Actions are available in this repository:

- [fetch-commit-version](fetch-commit-version/README.md)
- [generate-version](generate-version/README.md)

<!-- END ACTIONS -->

## How to use

### Run 'Commit Version'

This script can be used to retrieve the content of version artifacts from previous workflow runs for the current commit.

This script is used in release workflows, to retrieve the version identifier of already built Docker images / Helm
charts for this specific commit (based on the SHA1 for this commit).

#### Arguments

| Argument        | Description                                                                     | Default          |
|-----------------|---------------------------------------------------------------------------------|------------------|
| --commit-sha1   | The full SHA of the commit for which you want to retrieve the version artifact. | $GITHUB_SHA      |
| --job-name      | The name of the GitHub Actions job in which the version artifact is generated.  | generate-version |
| --artifact-name | The name of the version artifact.                                               | version          |

#### Example

```bash
python3 ./github_semver/commit_version.py --commit-sha1 b8e97c025c633005e1f89a5de886dcf4b87dcddd --job-name generate-version --artifact-name version
```

### Run 'SemVer'

You can use `python3 ./github_semver/run_semver.py` to invoke this script.

When invoking this script, the following environment variables are expected to be set (these variables will be set when running in a GitHub CI environment):

- `GITHUB_SHA`: Full commit SHA
- `GITHUB_REF`: Git reference (branch/tag)
- `GITHUB_REF_NAME`: Branch or tag name
- `GITHUB_HEAD_REF`: Head reference for pull requests

- CI_COMMIT_SHORT_SHA
- CI_PIPELINE_IID
- CI_DEFAULT_BRANCH
- CI_COMMIT_BRANCH

Optionally you can set:

- BUILD_RC_SEMVER to enable `release candidate` postfixing on new semver bumps on the default branch.

Depending on the branch, the following logic will be executed:

### Run on default branch

When running this script on the default branch a new SemVer version will be generated. 
This for now will always be a patch bump on the latest Git tag, or patch bump from 
`0.0.1` if tag is not set.

To perform this bump, this script will look for the latest "tag" set on the remote of the repository, and be set to the next build.

- `1.2.9 -> 1.2.10`

If `BUILD_RC_SEMVER` is enabled, a suffix with:
`-rc.<CI_PIPELINE_IID>+<CI_COMMIT_SHORT_SHA>` will be added

### Run on non-default branch

On a non-default branch commit, we will create a SemVer identifier
for a build version. For this we treat 0.0.1-0-0 as a reserved version identifier, (which is the lowest possible semver release).

An example of such a SemVer would be:

`0.0.1-build.234+mybranchababab`

## Notes

- If no tag is set on the repository, the build will default to version **'0.0.1'**
- It is a good practice to keep your branch name short and descriptive.
  Technically a **semver** tag is allowed to have up to 255 characters, this will leave you with approx. 200 characters for a branch name.

<!-- BEGIN ACTIONS -->

## 🛠️ GitHub Actions

The following GitHub Actions are available in this repository:

- [fetch-commit-version](fetch-commit-version/README.md)
- [generate-version](generate-version/README.md)

<!-- END ACTIONS -->


### GitHub Actions

This repository provides two GitHub Actions:

#### Generate Version Action

Generates semantic versions based on git tags and branch logic.

```yaml
- name: Generate Version
  uses: ./generate-version
  with:
    python-version: '3.13'  # optional
    build-rc-semver: 'true'  # optional
```

#### Promote Version Action

Retrieves version artifacts from previous successful workflow runs for the same commit.

```yaml
- name: Promote Version
  uses: ./promote-version
  with:
    python-version: '3.13'  # optional
    generate-version-job-name: 'generate-version'  # optional
    github-token: ${{ secrets.GITHUB_TOKEN }}  # optional
    artifact-name: 'version'  # optional
```

### Environment Variables

The GitHub version uses these environment variables:

- `GITHUB_SHA`: Full commit SHA
- `GITHUB_REF`: Git reference (branch/tag)
- `GITHUB_REF_NAME`: Branch or tag name
- `GITHUB_HEAD_REF`: Head reference for pull requests
- `GITHUB_RUN_NUMBER`: Workflow run number (used as build number)
- `GITHUB_REPOSITORY`: Repository in format owner/repo
- `GITHUB_TOKEN`: GitHub API token for authentication
- `BUILD_RC_SEMVER`: Whether to build RC semver (default: true)

### Example Workflow

```yaml
name: Version Management
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  generate-version:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0  # Required for git tag operations

    - name: Generate Version
      id: version
      uses: ./generate-version

    - name: Use generated version
      run:
        echo "Generated version: ${{ steps.version.outputs.version }}"

  promote-version:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
    - uses: actions/checkout@v4

    - name: Promote Version
      id: promote
      uses: ./promote-version
      with:
        github-token: ${{ secrets.GITHUB_TOKEN }}

    - name: Use promoted version
      run:
        echo "Promoted version: ${{ steps.promote.outputs.version }}"
```

## Development

This project uses [UV](https://docs.astral.sh/uv/) for Python package management, with [ruff](https://docs.astral.sh/ruff/) for linting and [pytest](https://docs.pytest.org/) for testing.

### Prerequisites

- Python 3.12 or higher
- [UV](https://docs.astral.sh/uv/getting-started/installation/) package manager

### Pre-commit hooks

To ensure code quality and consistency, this repository uses [pre-commit](https://pre-commit.com/) hooks. Make sure to
install the pre-commit hooks by running:

```bash
pre-commit install
```

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd actions-semver
   ```

2. Install dependencies:
   ```bash
   uv sync --dev
   ```

### Development Commands

```bash
# Run tests
uv run pytest

# Run linting
uv run ruff check

# Format code
uv run ruff format

# Run the semver script
uv run python -m github_semver.run_semver

# Run the commit version script
uv run python -m github_semver.commit_version

# Install new dependencies
uv add package-name

# Install dev dependencies
uv add --dev package-name
```
