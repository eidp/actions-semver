<!-- NOTE: This file's contents are automatically generated. Do not edit manually. -->
# Promote Version (Action)

The promote-version component executes the [`commit_version`](../github_semver/commit_version.py) script which  downloads the version artifact from the last successful workflow run for the current commit. The corresponding version is stored as `SEMVER_VERSION` environment variable and set as output of this action. This pipeline is supposed to be run for releases only.
The GitHub token needs to have `actions: read` permission to be able to access the workflow runs.

## 🔧 Inputs

|      Name      |         Description        |Required|       Default       |
|----------------|----------------------------|--------|---------------------|
|`python-version`|    Python version to use   |   No   |        `3.13`       |
| `github-token` | GitHub token for API access|   No   |`${{ github.token }}`|
| `artifact-name`|Name of the version artifact|   No   |      `version`      |

## 📤 Outputs

|   Name  |        Description       |
|---------|--------------------------|
|`version`|Retrieved semantic version|

## 🚀 Usage

```yaml
- name: Promote Version
  uses: eidp/actions-semver/promote-version@v0
  with:
    # your inputs here
```
