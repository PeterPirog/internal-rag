# Release checklist

1. Set the correct version in `VERSION` and `CHANGELOG.md`.
2. Verify the date and sources in `docs/COMPATIBILITY.md`.
3. Run `python self_test.py` on Windows and Linux (GitHub Actions covers both).
4. Check that the package contains no private paths or real credentials.
5. Create a ZIP as a GitHub Release asset.
6. Do not commit the ZIP to the source repository — `.gitignore` ignores `*.zip`.
7. To push `.github/workflows/`, the git token needs the `workflow` scope.