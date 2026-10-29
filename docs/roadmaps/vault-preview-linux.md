# Linux Vault-to-Preview Distribution Roadmap

## Status

**Parked — planning only.** Lead Manager pending work remains the active priority. Do not begin implementation, packaging, deployment, or installation until Bob explicitly resumes this roadmap.

This document records an approved direction, not a delivery commitment.

## Objective

Provide secure saved-login autofill in the Hermes Desktop embedded Browser on Linux without depending on acceptance into the official Hermes repository.

The design separates:

1. a minimal trusted Hermes core capability that performs vault-to-preview filling; and
2. a private Desktop plugin that contributes the title-bar key button and invokes the trusted action.

## Repositories

- Upstream: `NousResearch/hermes-agent`
- Linux distribution fork: `BobB7037/hermes-agent`
- Button plugin: `BobB7037/hermes-save-login-button`

The fork is public because it is a GitHub fork of the public MIT-licensed upstream repository. Credentials, environment files, signing material, deployment configuration, and private infrastructure details must never be committed.

## Scope

### Included

- Linux-only Hermes Desktop builds.
- A matching Linux Hermes Agent/gateway build.
- Hermes local vault support.
- Existing Bitwarden and 1Password CLI-backed vault sources.
- Exact-origin login matching: scheme, hostname, and port.
- A built-in trusted action such as `vault.fillPreview`.
- A private plugin button that invokes the trusted action without receiving credentials.
- Account selection when more than one saved login matches.
- Existing masked unlock prompts for external password managers.
- Identifier and password filling into the visible login form without automatic submission.
- A private update pipeline that rebases the small core patch onto validated upstream releases.
- Compatibility checks between Desktop and gateway versions.
- Automated security, unit, integration, type-check, lint, and build gates.

### Excluded

- Windows and macOS packaging or testing.
- Automatic form submission.
- Card, address, or TOTP filling in the first release.
- Wildcard domains, parent-domain inference, or cross-origin credential use.
- Giving Desktop plugins direct access to vault handles, passwords, generated fill scripts, or secret-bearing transport frames.
- Replacing the official Hermes updater with an unverified automatic update path.
- An upstream pull request unless separately approved later.

## Security invariants

1. A plugin may request the core action but never receives the selected credential or secret-bearing response.
2. The trusted core determines the active preview target and origin; plugins cannot provide or override them.
3. The gateway validates the saved item's exact origin before resolving a password.
4. Desktop validates the live origin again immediately before injection and aborts after navigation or target replacement.
5. The operation fills fields but never submits the form.
6. Secrets never enter chat, logs, notifications, telemetry, persistent UI state, plugin APIs, generic gateway events, reconnect replay, or ordinary RPC responses.
7. A destination login page can necessarily read values after they are filled, as with a conventional password-manager extension; no broader secrecy claim is made.
8. Locked-manager cancellation, malformed payloads, unavailable preview targets, stale tabs, origin mismatch, and navigation races fail closed.
9. No release is produced when patch application, compatibility checks, or required tests fail.

## Target architecture

### Core action

Hermes core owns an action conceptually equivalent to:

```text
vault.fillPreview
```

The action:

1. identifies the active embedded Browser tab;
2. obtains its current HTTP(S) origin internally;
3. finds exact-origin login metadata through existing vault abstractions;
4. presents trusted account-selection or manager-unlock UI when needed;
5. resolves the selected login in the gateway;
6. transfers the credential through a dedicated, non-replayable core-only request path;
7. rechecks the active tab and origin immediately before filling; and
8. fills identifier and password controls without submitting.

Only non-secret status is returned to the invoker.

### Plugin

`hermes-save-login-button` owns only the title-bar control and calls the supported core action, similar to `hermes-browser-toggle` invoking `view.showBrowser`.

The plugin must feature-detect the action and show an unavailable state when connected to an incompatible official or older custom build.

### Distribution

Desktop and gateway are released together using a version suffix such as:

```text
<upstream-version>-vaultpreview.<revision>
```

Official automatic updates must not overwrite the custom Desktop or gateway. Updates come from the validated fork release process.

## Delivery phases

### Phase 0 — Hold point

- Finish the outstanding Lead Manager work.
- Reconfirm that this roadmap should resume.
- Review upstream changes since this roadmap was parked.
- Decide whether the initial fork releases will be published publicly or distributed privately as build artifacts.

**Exit:** explicit approval from Bob to begin.

### Phase 1 — Core security primitive

- Implement the trusted action and dedicated secret transport.
- Enforce exact-origin validation in gateway and Desktop.
- Add navigation-race and stale-target refusal.
- Fill identifier and password without submission.
- Add tests proving secrets are absent from plugin surfaces, ordinary responses, events, replay, logs, and persisted state.

**Estimate:** 12–20 hours.

### Phase 2 — Plugin integration

- Update the private key-button plugin to call the core action.
- Add capability detection and clear unavailable-state messaging.
- Verify the plugin receives status only.

**Estimate:** included in Phase 1 or up to 4 additional hours if SDK action exposure requires compatibility work.

### Phase 3 — Linux update pipeline

- Add an upstream remote and documented synchronization process.
- Create a workflow that applies the maintained patch series to a selected upstream tag.
- Run Python and Desktop test, type-check, lint, and build gates.
- Build matching Linux Desktop and gateway artifacts.
- Refuse publication on conflict or failed verification.

**Estimate:** 8–16 hours.

### Phase 4 — Packaging and compatibility

- Add Desktop/gateway protocol compatibility detection.
- Define Linux installation, update, rollback, and backup procedures.
- Ensure official updates cannot silently replace only one side.

**Estimate:** 8–16 hours.

### Phase 5 — First upgrade rehearsal

- Install a matched custom release in a non-production test environment.
- Verify local-vault and, if available, Vaultwarden/Bitwarden CLI flows.
- Rebase onto a newer upstream release in a rehearsal.
- Confirm rollback restores the previous matched pair.
- Record results and residual risks.

**Estimate:** 4–8 hours.

## Estimated level of effort

Linux-only initial delivery: **32–60 engineering hours**, approximately **4–7.5 engineering days**. A practical calendar allowance is one to two weeks for review and build iterations.

Typical ongoing maintenance:

- clean upstream release: 15–30 minutes to review and approve a successful automated build;
- release with conflicts: approximately 1–3 hours to rebase, repair, and retest;
- major upstream Desktop/gateway redesign: separately estimated, with publication blocked until resolved.

## Verification gates

A release is not complete until all applicable gates pass:

- exact-origin positive and scheme/host/port mismatch tests;
- multiple-account chooser tests;
- locked-manager unlock and cancellation tests;
- navigation-race and stale-target tests;
- no-match and malformed-payload tests;
- no automatic submission test;
- plugin isolation and core-only action tests;
- secret non-retention and non-replay tests;
- relevant Python suites;
- Desktop unit tests;
- TypeScript type checking;
- lint and internationalization-key validation;
- Linux Desktop production build;
- matched Desktop/gateway smoke test;
- independent security-focused code review.

## Update and rollback policy

- Keep fork `main` synchronized with upstream and maintain custom work on a narrow release branch or patch series.
- Never force a conflicting upstream update into production.
- Publish Desktop and gateway as one compatibility set.
- Retain the previous known-good release and installation artifacts.
- Back up Hermes configuration and vault material using existing supported procedures before changing versions.
- Roll back both Desktop and gateway when a compatibility or vault-fill regression occurs.

## Definition of done

- The key button appears in the Linux Desktop title bar through the private plugin.
- Clicking it invokes the trusted core action.
- A matching saved login fills the active embedded login form without submission.
- Multiple matches are selected in trusted Hermes UI.
- Local vault and configured external-manager paths pass their tests.
- Exact-origin and navigation-race controls fail closed.
- No credential reaches chat or plugin-accessible interfaces.
- Desktop and gateway version incompatibility disables the feature safely.
- A reproducible Linux release and rollback procedure is documented and rehearsed.
- The update workflow successfully carries the patch across at least one upstream-version rehearsal.
