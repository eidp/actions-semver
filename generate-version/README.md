<!-- NOTE: This file's contents are automatically generated. Do not edit manually. -->
# Generate Version (Action)

The generate-version action executes the [`run_semver.py`](../github_semver/run_semver.py) script. The generated version is then stored as `SEMVER_VERSION` environment variable, set as output of this action and finally stored as an artifact.

## 🔧 Inputs

|       Name      |                Description                |Required|Default|
|-----------------|-------------------------------------------|--------|-------|
| `python-version`|           Python version to use           |   No   | `3.13`|
|`build-rc-semver`|Whether to build RC semver (adds rc suffix)|   No   | `true`|

## 📤 Outputs

|   Name  |        Description       |
|---------|--------------------------|
|`version`|Generated semantic version|

## 🚀 Usage

```yaml
- name: Generate Version
  uses: eidp/actions-semver/generate-version@v0
  with:
    # your inputs here
```
