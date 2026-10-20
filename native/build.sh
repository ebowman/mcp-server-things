#!/bin/sh
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir=${THINGS_MCP_SCOPED_BUILD_DIR:-"$repo/build"}
app="$output_dir/ThingsReadHelper.app"
staging=$(mktemp -d "${TMPDIR:-/tmp}/things-read-helper.XXXXXX")
install_dir=
backup=
cleanup() {
  if [ -n "$backup" ] && [ -d "$backup" ] && [ ! -e "$app" ]; then
    if ! mv -f "$backup" "$app"; then
      printf 'Failed to restore previous helper from %s\n' "$backup" >&2
      rm -rf "$staging"
      return
    fi
  fi
  rm -rf "$staging"
  if [ -n "$install_dir" ]; then rm -rf "$install_dir"; fi
}
trap cleanup EXIT
staged_app="$staging/ThingsReadHelper.app"
mkdir -p "$staged_app/Contents/MacOS"
cp -f "$repo/native/Info.plist" "$staged_app/Contents/Info.plist"
clang -fobjc-arc -Wall -Wextra -framework AppKit -lsqlite3 \
  "$repo/native/ThingsReadHelper.m" -o "$staged_app/Contents/MacOS/ThingsReadHelper"
codesign --force --sign - --entitlements "$repo/native/entitlements.plist" "$staged_app"
codesign --verify --strict "$staged_app"
mkdir -p "$output_dir"
install_dir=$(mktemp -d "$output_dir/.things-read-helper.XXXXXX")
candidate="$install_dir/ThingsReadHelper.app"
backup="$install_dir/previous.app"
ditto "$staged_app" "$candidate"
xattr -cr "$candidate"
codesign --verify --strict "$candidate"
if [ -d "$app" ]; then mv -f "$app" "$backup"; fi
mv -f "$candidate" "$app"
printf '%s\n' "$app"
