#!/usr/bin/env sh
# Build the Pages upload directory for the Blue Ridge booth.
#
# `wrangler pages deploy` uploads EVERY file in the directory it is given and
# does not read `.assetsignore` (that file is a Workers static-assets feature).
# The 2026-09-16 deploy served worker.js, test-worker.mjs, wrangler.toml and
# DEPLOY.md at 200 from the public site. No credentials in any of them, but
# there is no reason to publish the Worker's logic or the HubSpot owner ids.
#
# So the public site is built from an explicit allowlist, and both deploy
# paths (laptop and .github/workflows/booth-deploy.yml) upload THIS directory.
#
#   sh pages-dist.sh && npx wrangler pages deploy .pages-dist --project-name blue-ridge-booth
set -eu
cd "$(dirname "$0")"
rm -rf .pages-dist
mkdir .pages-dist
cp spin-back-to-school.html _redirects .pages-dist/
echo "pages dist:"; ls -1 .pages-dist
