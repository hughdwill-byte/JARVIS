#!/bin/bash
# ============================================================================
#  JARVIS — bundle your key/secret files for the move to a new computer.
#  Double-click this on your MAC. It makes an ENCRYPTED zip on your Desktop
#  containing whatever secrets exist (.env, mcp_servers.json) and, if you
#  want, your notes/tasks/memory database. Nothing leaves your machine — it
#  just creates the zip; you send it however you like.
# ============================================================================

set -u

# Work from the repo root (this script lives in JARVIS/launchers/).
cd "$(dirname "$0")/.." || { echo "Could not find the JARVIS folder."; read -r; exit 1; }

OUT="$HOME/Desktop/jarvis-secrets.zip"
rm -f "$OUT"

echo "JARVIS — secrets bundler"
echo "Repo: $(pwd)"
echo

# Collect the key-bearing files that actually exist.
FILES=()
for f in .env mcp_servers.json; do
  if [ -f "$f" ]; then FILES+=("$f"); echo "  found: $f"; fi
done

# Google Calendar OAuth file, if referenced in mcp_servers.json.
if [ -f mcp_servers.json ]; then
  GOAUTH=$(grep -oE '"[^"]*gcp-oauth[^"]*\.json"' mcp_servers.json 2>/dev/null | tr -d '"' | head -1)
  if [ -n "${GOAUTH:-}" ] && [ -f "$GOAUTH" ]; then
    FILES+=("$GOAUTH"); echo "  found: $GOAUTH (Google OAuth)"
  fi
fi

if [ ${#FILES[@]} -eq 0 ]; then
  echo
  echo "No .env or mcp_servers.json found here — nothing to bundle."
  echo "(That means your keys were only ever entered in the app's Settings,"
  echo " or this isn't the folder you run JARVIS from.)"
  echo
  read -r -p "Press Enter to close."
  exit 0
fi

# Offer to include the history database (not a key, but you'll want it moved).
INCLUDE_DB=""
if [ -f data/jarvis.db ]; then
  echo
  read -r -p "Also include your notes/tasks/memory database (data/jarvis.db)? [Y/n] " a
  case "${a:-y}" in [Nn]*) : ;; *) INCLUDE_DB="data/jarvis.db"; echo "  will include: data/jarvis.db";; esac
fi

echo
echo "You'll now set a PASSWORD for the zip (needed to open it on the new PC)."
echo "Pick something you'll remember — the zip holds your live keys."
echo

# -e = encrypt (prompts for password). Store db with path; secrets flat (-j not
# used so paths are kept, which the Windows side expects at the repo root).
if [ -n "$INCLUDE_DB" ]; then
  zip -e "$OUT" "${FILES[@]}" "$INCLUDE_DB"
else
  zip -e "$OUT" "${FILES[@]}"
fi

echo
if [ -f "$OUT" ]; then
  echo "Done -> $OUT"
  echo
  echo "On the new Windows PC (after the installer has cloned JARVIS):"
  echo "  unzip it INTO the JARVIS folder, so .env and mcp_servers.json land"
  echo "  in the repo root and jarvis.db lands in data\\ — replacing what's there."
  echo
  echo "Security tip: delete the zip (and any copy you sent) once it's in place."
  open -R "$OUT" 2>/dev/null || true
else
  echo "Something went wrong — no zip was created."
fi

echo
read -r -p "Press Enter to close."
