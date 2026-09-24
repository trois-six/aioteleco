# Security policy

## Supported versions

aioteleco is in alpha. Security fixes are made on the `main` branch and shipped in the
next release; older releases are not patched.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it privately
through GitHub's security advisories:
[Report a vulnerability](https://github.com/trois-six/aioteleco/security/advisories/new)
(the "Security" tab of the repository, then "Report a vulnerability").

Include what you found, how to reproduce it, and its impact. You should get a first
answer within a few days. Once a fix is released, the advisory is published with credit
to the reporter unless you prefer otherwise.

## Scope

aioteleco talks to a **third-party cloud** operated by Teleco Automation and to the
Teleco box on your local network. It is not affiliated with Teleco Automation:

* issues in aioteleco itself (credential handling, the local channel, the CLI, the
  diagnostics dump…) are in scope;
* weaknesses of the Teleco cloud, of the box firmware or of the official apps are not
  something this project can fix. Report them to Teleco Automation. Do not test them
  against accounts or installations that are not yours.

## Protect your credentials

* **Never post your email, password, session id, installation code or box address** in
  an issue, a discussion, a pull request or a log. Redact them from anything you share.
* To share the state of an installation, use `teleco diagnose`: its output is
  anonymised (credentials, session, installation code, location, IP addresses and Wi-Fi
  network name are removed). Review it before attaching it anyway.
* If you think your credentials leaked, change your password in the brand app.
