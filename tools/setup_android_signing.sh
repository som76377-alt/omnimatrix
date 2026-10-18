#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="som76377-alt/omnimatrix"
KEY_ALIAS="omnitrix-update-key"
KEY_DIR="$HOME/.config/omnitrix-signing"
KEYSTORE="$KEY_DIR/omnitrix-update.p12"
PASSWORD_FILE="$KEY_DIR/store-password"

for command_name in gh keytool openssl base64; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name"
    echo "Run this from the Omnitrix GitHub Codespace with Java 17, GitHub CLI, and OpenSSL installed."
    exit 1
  fi
done

gh auth status >/dev/null
ADMIN="$(gh api "repos/$REPOSITORY" --jq '.permissions.admin // false')"
if [[ "$ADMIN" != "true" ]]; then
  echo "The currently signed-in GitHub account needs admin permission on $REPOSITORY to configure Actions secrets."
  exit 1
fi

existing="$(gh secret list --repo "$REPOSITORY" | awk 'NR > 1 { print $1 }')"
for required_secret in ANDROID_KEYSTORE_BASE64 ANDROID_KEYSTORE_PASSWORD ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD; do
  if printf '%s\n' "$existing" | grep -Fxq "$required_secret"; then
    echo "A signing secret ($required_secret) already exists."
    echo "Refusing to generate or upload a new key because replacing it would break future Android updates."
    exit 1
  fi
done

mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

if [[ -f "$KEYSTORE" || -f "$PASSWORD_FILE" ]]; then
  if [[ ! -f "$KEYSTORE" || ! -f "$PASSWORD_FILE" ]]; then
    echo "Found an incomplete local signing setup in $KEY_DIR; refusing to replace it."
    exit 1
  fi
  echo "Reusing the existing local Omnitrix signing key."
else
  store_password="$(openssl rand -hex 32)"
  (umask 077 && printf '%s' "$store_password" > "$PASSWORD_FILE")
  keytool -genkeypair -noprompt \
    -alias "$KEY_ALIAS" \
    -keyalg RSA -keysize 3072 -validity 10000 \
    -storetype PKCS12 \
    -keystore "$KEYSTORE" \
    -storepass "$store_password" \
    -keypass "$store_password" \
    -dname "CN=Omnitrix Android, O=Omnitrix, C=IN"
  chmod 600 "$KEYSTORE" "$PASSWORD_FILE"
fi

store_password="$(cat "$PASSWORD_FILE")"
base64 "$KEYSTORE" | tr -d '\n' | gh secret set ANDROID_KEYSTORE_BASE64 --repo "$REPOSITORY"
printf '%s' "$store_password" | gh secret set ANDROID_KEYSTORE_PASSWORD --repo "$REPOSITORY"
printf '%s' "$KEY_ALIAS" | gh secret set ANDROID_KEY_ALIAS --repo "$REPOSITORY"
printf '%s' "$store_password" | gh secret set ANDROID_KEY_PASSWORD --repo "$REPOSITORY"

# Start a new build now that the encrypted signing secrets are available.
gh workflow run android-apk.yml --repo "$REPOSITORY"

echo
echo "Persistent Omnitrix signing is configured in GitHub Actions."
echo "A new Android build was dispatched; follow it at https://github.com/$REPOSITORY/actions/workflows/android-apk.yml"
echo "The private key stays out of the public repository; keep $KEY_DIR private."
echo "After installing the first permanently signed release once, future updates can be installed in place."
