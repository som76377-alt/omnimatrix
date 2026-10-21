# Cline coding specialist in Omnitrix

## What is integrated

Omnitrix has an optional cline.coding tool. When enabled in the Python CLI or private Codespaces Studio, the lead specialist can delegate a specific implementation task to the real Cline CLI. The handoff supports the shared objective/context, findings from other specialists, acceptance criteria, and target paths. On complex hybrid tasks, Omnitrix now runs bounded no-tools calls for supporting specialists first and injects their findings into the lead specialist's context. The lead model can then pass the relevant findings to Cline, which inspects the workspace, implements, runs relevant tests, and reports results. Omnitrix receives structured metadata about changed files and whether changes were applied.

This is an adapter, not model training. Cline uses the provider/model configured in its own CLI profile; adding Cline does not automatically grant a free model or improve every response.

## One-time setup in a trusted private development workspace

1. Install Node.js/npm in the environment where Omnitrix will run.
2. Install Cline CLI with: npm install -g cline
3. Authenticate/configure Cline once with: cline auth. Confirm cline --version works.
4. In the Omnitrix repository, start the CLI with an explicit workspace and opt in:

   python -m interfaces.cli.main --config config/mobile.models.json --workspace-root . --enable-cline-coding

   Use the actual model config path available in your checkout. The coding.execute capability is granted only when --enable-cline-coding is explicitly present, and an explicit workspace root is required.

5. Ask Omnitrix to implement a concrete software task with acceptance criteria. The coding specialist is instructed to use cline.coding when it is available and permitted.

Cline can also run in plan mode (read-only) before implement mode. Implementation runs with Cline's tool actions auto-approved because it is non-interactive; Omnitrix first copies eligible workspace files to a temporary task copy, and only applies bounded changes after Cline exits successfully. Secret-like files, hidden credential/config directories, symlinks, oversized files and build/dependency directories are excluded from the copy. The Codespaces workspace allowlist is applied before files are copied into Cline's task workspace and again before changes are applied. Changes are checked for path traversal and protected names before they are applied.

## Security boundary and deployment status

**This is not an OS-level sandbox.** A coding agent can execute commands; a disposable copy limits what gets copied back but does not guarantee the child process cannot access other files or the network. Enable this only in a trusted, private development environment where you are comfortable with the permissions of the account running Omnitrix. Do not enable it on a public multi-user Render service or expose it to anonymous chat.

The hosted Render service does not install or enable Cline automatically. It needs the CLI installed and authenticated in the process environment, and an explicit private-runtime integration before it can be safely enabled there. The normal public chat deployment remains unchanged by this feature.

## Truthful reporting

- If the cline executable is missing, the tool reports that it is unavailable instead of pretending to run it.
- Plan mode never applies changes.
- A non-zero exit or timeout applies no changes.
- A successful exit is not proof the code is correct. The lead coding specialist must compare changed-file/test metadata against acceptance criteria; the critic and CI/independent review remain the verification gate.
- Supporting specialist calls run only on complex hybrid tasks; their findings are explicitly marked untrusted and must be checked against the user's request. This is coordinated specialist context, not a claim that every role runs on every chat.
- This adapter invokes the actual Cline CLI when available; it does not train or fine-tune the model.
