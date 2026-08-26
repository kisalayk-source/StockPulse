# Security Policy

## Supported versions

Security fixes are applied to the latest revision of the default branch. This
project does not currently maintain older release branches.

## Reporting a vulnerability

Do not open a public issue for suspected vulnerabilities. Use GitHub's
**Security** tab to submit a private vulnerability report. If private reporting
is unavailable, contact a maintainer through their public GitHub profile and ask
for a private reporting channel; do not include exploit details in the first
message.

Include affected components, reproduction steps, impact, and any suggested
mitigation. Maintainers will aim to acknowledge a complete report within seven
days and will coordinate disclosure after a fix is available.

Never include broker credentials, API keys, access tokens, account identifiers,
or proprietary market data. Revoke exposed credentials with the provider
immediately.

## Trading application scope

The StockPulse application can connect to external broker and market-data
services. Keep live trading disabled while developing, use paper credentials,
and review provider-side permissions. Financial loss, forecast accuracy, and
ordinary provider outages are not software security vulnerabilities.
