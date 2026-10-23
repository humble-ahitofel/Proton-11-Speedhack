#!/bin/sh
# Proton SpeedHack installer.
#
# One command, on the machine that runs Steam (desktop mode on a Steam Deck):
#
#   curl -fsSL https://raw.githubusercontent.com/humble-ahitofel/Proton-11-Speedhack/proton_11.0/install-speedhack.sh | sh
#
# It downloads the newest release tarball from GitHub, verifies its sha256 and
# installs it into Steam's compatibilitytools.d.  Restart Steam afterwards.
#
# The script can also install a tarball you already have (e.g. copied over on
# a USB stick): put it next to the script and run "sh install-speedhack.sh",
# or pass its path.
#
#   sh install-speedhack.sh [-y] [--dest DIR] [--repo OWNER/NAME] [TARBALL]
#     -y            replace an existing installation of the same name without asking
#                   (when piping into sh:  curl ... | sh -s -- -y)
#     --dest DIR    install into DIR instead of the detected <Steam>/compatibilitytools.d
#     --repo R      GitHub repository to download from
#     TARBALL       install this proton-*.tar.xz instead of downloading

set -eu

repo=${SPEEDHACK_REPO:-humble-ahitofel/Proton-11-Speedhack}
yes=0
dest=""
tarball=""
dl=""
tmp=""

die() { echo "error: $*" >&2; exit 1; }
usage() { sed -n '2,20p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; }
cleanup() { [ -n "$tmp" ] && rm -rf "$tmp"; [ -n "$dl" ] && rm -rf "$dl"; return 0; }
trap cleanup EXIT INT TERM

while [ $# -gt 0 ]; do
    case $1 in
        -y|--yes) yes=1; shift ;;
        --dest) [ $# -ge 2 ] || die "--dest needs a directory"; dest=$2; shift 2 ;;
        --repo) [ $# -ge 2 ] || die "--repo needs OWNER/NAME"; repo=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        -*) die "unknown option: $1 (try --help)" ;;
        *) tarball=$1; shift ;;
    esac
done

for tool in tar xz sha256sum; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is required but not installed"
done

# 1. The tarball: given on the command line, next to this script, or downloaded.
if [ -z "$tarball" ] && [ -f "$0" ]; then
    here=$(cd "$(dirname "$0")" && pwd)
    set -- "$here"/proton-*speedhack*.tar.xz
    if [ $# -eq 1 ] && [ -f "$1" ]; then
        tarball=$1
    elif [ $# -gt 1 ]; then
        die "several proton-*speedhack*.tar.xz next to this script, pass the one to install"
    fi
fi
if [ -z "$tarball" ]; then
    command -v curl >/dev/null 2>&1 || die "curl is required to download the release"
    api=${SPEEDHACK_RELEASE_API:-"https://api.github.com/repos/$repo/releases?per_page=10"}
    json=$(curl -fsSL -H "Accept: application/vnd.github+json" "$api") \
        || die "cannot fetch the release list from $api"
    # newest release (pre-releases included) that has a .tar.xz asset
    tar_url=$(printf '%s\n' "$json" | grep -o '"browser_download_url": *"[^"]*\.tar\.xz"' \
              | head -n 1 | sed 's/.*"\(http[^"]*\)".*/\1/')
    [ -n "$tar_url" ] || die "no release with a .tar.xz asset found in $repo"
    dl=$(mktemp -d "${TMPDIR:-/tmp}/speedhack-download.XXXXXX")
    tarball="$dl/$(basename "$tar_url")"
    echo "Download: $tar_url"
    curl -fL --progress-bar -o "$tarball" "$tar_url" || die "download failed"
    curl -fsSL -o "$tarball.sha256" "$tar_url.sha256" \
        || { rm -f "$tarball.sha256"; echo "Checksum: no .sha256 asset in the release, skipping"; }
fi
[ -f "$tarball" ] || die "$tarball: no such file"
echo "Tarball:  $tarball"

# 2. Checksum, when the .sha256 file from the build is present.
if [ -f "$tarball.sha256" ]; then
    expected=$(cut -d' ' -f1 "$tarball.sha256")
    actual=$(sha256sum "$tarball" | cut -d' ' -f1)
    [ "$expected" = "$actual" ] || die "checksum mismatch: the tarball is corrupt or incomplete"
    echo "Checksum: OK"
fi

# 3. The tool name is the top-level directory inside the tarball.
name=$(tar -tJf "$tarball" 2>/dev/null | head -n 1 | cut -d/ -f1)
[ -n "$name" ] || die "cannot read the tarball"
echo "Tool:     $name"

# 4. Where Steam keeps compatibility tools.
if [ -z "$dest" ]; then
    for d in "$HOME/.steam/root" "$HOME/.local/share/Steam" "$HOME/.steam/steam" \
             "$HOME/.var/app/com.valvesoftware.Steam/data/Steam"; do
        if [ -d "$d/steamapps" ] || [ -d "$d/compatibilitytools.d" ]; then
            dest="$d/compatibilitytools.d"
            break
        fi
    done
    [ -n "$dest" ] || die "no Steam installation found under $HOME; pass --dest <Steam dir>/compatibilitytools.d"
fi
mkdir -p "$dest"
echo "Install:  $dest/$name"

# Unpacked Proton is about 1.5 GB.
avail_kb=$(df -Pk "$dest" | awk 'NR == 2 { print $4 }')
[ "$avail_kb" -ge 2500000 ] || die "only $((avail_kb / 1024)) MiB free on $dest, need about 2.5 GiB"

# 5. Replace an existing installation of the same name?
if [ -e "$dest/$name" ]; then
    [ -f "$dest/$name/version" ] && echo "Existing: $(cat "$dest/$name/version")"
    if [ $yes != 1 ]; then
        # ask on the terminal even when the script itself comes from a pipe
        if printf 'Replace the existing %s? [y/N] ' "$name" 2>/dev/null > /dev/tty \
           && read -r answer 2>/dev/null < /dev/tty; then :
        else
            die "an installation exists and there is no terminal to ask on; rerun with -y to replace it"
        fi
        case $answer in
            y|Y|yes|YES) ;;
            *) echo "Aborted, nothing changed."; exit 1 ;;
        esac
    fi
fi

# 6. Unpack next to the final location first, so that a broken extraction
#    never leaves a half-installed tool behind.
tmp=$(mktemp -d "$dest/.$name.install.XXXXXX")
echo "Unpacking (this takes a minute)..."
tar -xJf "$tarball" -C "$tmp"
for f in proton compatibilitytool.vdf toolmanifest.vdf version files/bin/wine files/bin/wineserver \
         proton_speedhack.py speedhack.json; do
    [ -e "$tmp/$name/$f" ] || die "the tarball does not contain $name/$f, not a Proton SpeedHack build?"
done
chmod +x "$tmp/$name/proton"

rm -rf "$dest/$name"
mv "$tmp/$name" "$dest/$name"

echo
echo "Installed $name ($(cat "$dest/$name/version"))"
echo
if pgrep -x steam >/dev/null 2>&1; then
    echo "Steam is running: restart it so that it picks up the new tool."
else
    echo "Start Steam."
fi
echo "Then, for a game: Properties > Compatibility > Force the use of a specific Steam Play"
echo "compatibility tool > $name."
echo
echo "By default holding Page Up runs the game at 2.5x.  To change this, create"
echo "  ~/.speedhack/speedhack.json          (all games)   or"
echo "  ~/.speedhack/<SteamGameId>.json      (one game)"
echo "with for example: {\"speed\": 3, \"toggle\": 1, \"keys\": \"ctrl,f12\"}"
echo "See $dest/$name/speedhack.json for the shipped defaults, and"
echo "https://github.com/$repo/blob/proton_11.0/SPEEDHACK.md for everything else."
