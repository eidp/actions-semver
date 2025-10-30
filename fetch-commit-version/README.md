<!-- NOTE: This file's contents are automatically generated. Do not edit manually. -->
# Fetch commit Version (Action)

The fetch-commit-version component executes the [`commit_version`](../github_semver/commit_version.py) script which 
downloads the version artifact from the last successful workflow run for the current commit.

The corresponding version is stored as `COMMIT_VERSION` environment variable and set as output of this action.

This pipeline is supposed to be run for releases only.

This action requires a GitHub token with the following permissions:
```yaml
permissions:
  contents: read
  actions: read
```

## 🔧 Inputs

|Name            |Description                                                                                   |Required|Default                  |
|----------------|----------------------------------------------------------------------------------------------|--------|-------------------------|
|`github-token`  |GitHub token for API access                                                                   |No      |`${{ github.token }}`    |
|`artifact-name` |Name of the version artifact                                                                  |No      |`version`                |
|`workflow-name` |Name of the workflow to retrieve the version artifact from. Defaults to the current workflow. |No      |`${{ github.workflow }}` |

## 📤 Outputs

|Name      |Description                           |
|----------|--------------------------------------|
|`version` |Retrieved semantic version for commit |

## 🚀 Usage

```yaml
- name: Fetch commit Version
  uses: eidp/actions-semver/fetch-commit-version@v0
  with:
    # your inputs here
```
