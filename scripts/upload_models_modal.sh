#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1
if ! source scripts/_modal_auth.sh; then
  exit 1
fi
VOL=cicero-models
STAGE=.cicero_model_stage
# Cache the remote listing once per run to decide skips (root + nonsense_ensemble).
have_root="$(modal volume ls "$VOL" / 2>/dev/null)"
have_ne="$(modal volume ls "$VOL" /nonsense_ensemble 2>/dev/null)"
ok=0; skip=0; fail=0
while IFS= read -r f; do
  rel="${f#"$STAGE"/}"                    # e.g. dialogue or nonsense_ensemble/location
  base="$(basename "$rel")"
  if [[ "$rel" == nonsense_ensemble/* ]]; then haystack="$have_ne"; else haystack="$have_root"; fi
  if grep -qF "$base" <<<"$haystack"; then echo "skip  $rel"; skip=$((skip+1)); continue; fi
  for attempt in 1 2 3 4 5; do
    if modal volume put "$VOL" "$f" "/$rel" >/dev/null 2>>/tmp/cicero_upload_err.log; then
      echo "ok    $rel"; ok=$((ok+1)); break
    else
      echo "retry $rel (attempt $attempt)"; sleep 5
      [[ $attempt -eq 5 ]] && { echo "FAIL  $rel"; fail=$((fail+1)); }
    fi
  done
done < <(find "$STAGE" -type f | sort)
echo "DONE ok=$ok skip=$skip fail=$fail"
