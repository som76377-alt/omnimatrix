#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="som76377-alt/omnimatrix"
KEY_ALIAS="omnitrix-update-key"
KEY_DIR="$HOME/.config/omnitrix-signing"
KEYSTORE="$KEY_DIR/omnitrix-update.p12"
PASSWORD_FILE="$KEY_DIR/store-password"

# Install GitHub CLI into the user's home directory if the Codespace image lacks it.
# This avoids needing sudo or a preconfigured system package.
if ! command -v gh >/dev/null 2>&1; then
  for command_name in curl tar python3; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      echo "Required bootstrap command missing: $command_name"
      echo "Open the Omnitrix Codespace with its standard terminal image and rerun this script."
      exit 1
    fi
  done

  case "$(uname -m)" in
    x86_64|amd64) GH_ARCH="amd64" ;;
    aarch64|arm64) GH_ARCH="arm64" ;;
    *)
      echo "Unsupported Codespace CPU architecture: $(uname -m)"
      exit 1
      ;;
  esac

  echo "GitHub CLI is missing; downloading the official GitHub CLI release..."
  GH_RELEASE_JSON="$(curl -fsSL --retry 2 https://api.github.com/repos/cli/cli/releases/latest)"
  read -r GH_VERSION GH_URL GH_DIGEST < <(python3 -c '
import json, sys
data=json.load(sys.stdin)
version=data["tag_name"].lstrip("v")
arch=sys.argv[1]
name=f"gh_{version}_linux_{arch}.tar.gz"
asset=next((item for item in data.get("assets", []) if item.get("name")==name), None)
if not asset:
    raise SystemExit("Could not find the official GitHub CLI Linux archive.")
print(version, asset["browser_download_url"], asset.get("digest") or "-")
' "$GH_ARCH" <<< "$GH_RELEASE_JSON")

  GH_TMP="$(mktemp -d)"
  trap 'rm -rf "$GH_TMP"' EXIT
  curl -fL --retry 2 "$GH_URL" -o "$GH_TMP/gh.tar.gz"
  if [[ "$GH_DIGEST" == sha256:* ]]; then
    printf '%s  %s\n' "$(cut -d: -f2- <<< "$GH_DIGEST")" "$GH_TMP/gh.tar.gz" | sha256sum -c -
  fi
  tar -xzf "$GH_TMP/gh.tar.gz" -C "$GH_TMP"
  mkdir -p "$HOME/.local/bin"
  install -m 0755 "$GH_TMP/gh_"$GH_VERSION"_linux_"$GH_ARCH"/bin/gh" "$HOME/.local/bin/gh"
  export PATH="$HOME/.local/bin:$PATH"
  hash -r
  rm -rf "$GH_TMP"
  trap - EXIT
  echo "GitHub CLI installed in $HOME/.local/bin/gh"
fi

for command_name in openssl base64; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name"
    exit 1
  fi
done

# Start GitHub's device authorization if this Codespace has not authenticated gh yet.
if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  echo
  echo "ONE-TIME APPROVAL REQUIRED"
  echo "1. Open https://github.com/login/device on your phone."
  echo "2. GitHub CLI will print a one-time code below. Enter that code on the page."
  echo "3. Tap Authorize GitHub CLI. This terminal will continue automatically after approval."
  echo
  # Prevent a headless Codespace from trying to open a browser inside the container.
  export GH_BROWSER=echo
  gh auth login --hostname github.com --git-protocol https --web --scopes repo
fi


if ! command -v keytool >/dev/null 2>&1; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "Java 17 is required to generate the signing key. Install a JDK and run this again."
    exit 1
  fi
  sudo apt-get update
  sudo apt-get install -y openjdk-17-jdk-headless
fi

gh auth status --hostname github.com >/dev/null
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
