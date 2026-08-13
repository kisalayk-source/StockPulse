# Contributing to Kronos

Thank you for helping improve Kronos. By participating, you agree to follow the
[Code of Conduct](./CODE_OF_CONDUCT.md).

## Before opening a change

1. Search existing issues and open one for substantial behavior or API changes.
2. Keep pull requests focused; do not include credentials, market data you cannot
   redistribute, model checkpoints, generated predictions, or runtime logs.
3. Base work on a supported Python (3.10–3.12) and Node.js 22 environment.
4. Follow the setup and verification steps in [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md).

## Pull requests

- Explain the motivation, user-visible effects, and testing performed.
- Add or update tests for behavior changes.
- Preserve backward compatibility where practical and call out breaking changes.
- Update documentation and `CHANGELOG.md` for noteworthy changes.
- Keep downloaded models out of Git. Model regression tests download pinned
  revisions and are intentionally run manually or on the nightly schedule.

Maintainers may request changes before merge. Contributions are submitted under
the repository's [MIT License](./LICENSE); see [licensing guidance](./docs/LICENSING.md).

## Reporting problems

Use the issue templates for reproducible bugs and feature proposals. Report
security vulnerabilities privately as described in [SECURITY.md](./SECURITY.md).
Do not use security reports for trading losses or general model-quality questions.
