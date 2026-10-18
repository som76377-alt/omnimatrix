# Omnitrix Android automatic updates

## What the updater does

When a build is signed with the permanent Omnitrix key, the app checks the latest GitHub Release without blocking chat startup. If a newer build exists, it downloads the APK in the background, validates its SHA-256 digest, and opens Android's package installer when you choose **Install Update**.

Android does not allow an ordinary sideloaded app to silently replace itself. The updater avoids manual browser downloads and APK hunting, but the final install/upgrade confirmation remains an Android security prompt. Android may also ask you once to allow installs from Omnitrix.

## One-time signing setup (required)

The old CI workflow used a new signing certificate on every fresh runner, so Android could not upgrade those builds in place. Never solve this by committing a keystore to the public repository.

Open the Omnitrix repository in a GitHub Codespace, ensure its terminal is on the main branch, and run the following from the repository root:

~~~bash
bash tools/setup_android_signing.sh
~~~

The script creates a permanent PKCS#12 signing key in your Codespace home directory and stores it as four encrypted GitHub Actions repository secrets:

- ANDROID_KEYSTORE_BASE64
- ANDROID_KEYSTORE_PASSWORD
- ANDROID_KEY_ALIAS
- ANDROID_KEY_PASSWORD

It refuses to overwrite any existing signing secret, because rotating the key would break in-place updates. The generated private key never goes into Git.

## First install after setup

The app build that was already installed was signed by a different, temporary CI key. After configuring persistent signing, the first APK signed by the new permanent key cannot upgrade that older installation in place. Install the first persistent-signed release once as a clean install (Android may require uninstalling the older build first). **After that one-time transition, future releases built by this workflow use the same signing certificate and can update in place.**

This initial one-time reinstall may clear app-local settings and GitHub sign-in tokens. The hosted chat backend and GitHub repository data are not deleted.

## Verification

After the one-time setup, open the Android APK workflow. A successful new release should say that persistent signing is configured. Its build has auto-update checks enabled; builds created without the four secrets keep the updater disabled to avoid offering APKs that Android cannot reliably install as upgrades.
