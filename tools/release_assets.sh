#!/bin/bash
# =====================================================================
# release_assets.sh - the files a GitHub release carries, from a bundle.
#
# 17 November 2026 (BACKLOG 506). Until 1.64.2 John attached the QGIS,
# Pro and Stata zips to each release by hand, from a bundle he built
# on his own PC. John: "this should be automatic (also because we risk
# missing to attach a file at some point if left manual)". The release
# workflow now runs this after make_bundle.sh and uploads what it
# writes; the tests workflow runs it on every pull request, so a
# release cannot be the first time it breaks.
#
# Usage: tools/release_assets.sh <version> <bundle dir> <dist dir> <out dir>
#   <dist dir> holds the wheel and source archive to attach - in a
#   release, the very files PyPI receives.
#
# Writes into <out dir>:
#   equipop-<v>-py3-none-any.whl, equipop-<v>.tar.gz   the engine
#   equipop_qgis-<v>.zip            QGIS: Plugins > Install from ZIP
#   equipop_arcgis-<v>.zip          Pro: the toolbox, its help, the guide
#   equipop_stata_netinstall-<v>.zip  Stata: unzip, then net install
#   equipop_ssc_submission-<v>.zip  for the SSC archive
#   gridby-<v>.gpkg                 the teaching town for QGIS and Pro
#   SHA256SUMS.txt                  a checksum for each of the above
# =====================================================================
set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "usage: tools/release_assets.sh <version> <bundle dir> <dist dir> <out dir>" >&2
    exit 2
fi
V="$1"; B="$2"; D="$3"; A="$4"
mkdir -p "$A"

need() { test -f "$1" || { echo "FATAL: $1 is missing" >&2; exit 1; }; }

need "$D/equipop-$V-py3-none-any.whl"
need "$D/equipop-$V.tar.gz"
cp "$D/equipop-$V-py3-none-any.whl" "$D/equipop-$V.tar.gz" "$A/"

for f in equipop_qgis-$V.zip equipop_stata_netinstall-$V.zip \
         equipop_ssc_submission-$V.zip; do
    need "$B/$f"; cp "$B/$f" "$A/"
done

# Pro: the toolbox with its help sidecars beside it, as Pro needs them,
# and the guide. The bundle verified the sidecars, one per tool.
need "$B/EquiPop.pyt"; need "$B/ARCGIS_GUIDE.md"
ls "$B"/EquiPop.*.pyt.xml > /dev/null
rm -f "$A/equipop_arcgis-$V.zip"
( cd "$B" && zip -q "$A/equipop_arcgis-$V.zip" EquiPop.pyt EquiPop.*.pyt.xml ARCGIS_GUIDE.md )

# the teaching town, in ETRS89 / UTM 33N (BACKLOG 504); needs geopandas
python -c "import sys; from equipop.gridby import write_gridby; write_gridby(sys.argv[1])" "$A/gridby-$V.gpkg"

# every zip opens, and every member is whole
python - "$A" <<'PY'
import sys, zipfile, pathlib
for z in sorted(pathlib.Path(sys.argv[1]).glob("*.zip")):
    with zipfile.ZipFile(z) as f:
        bad = f.testzip()
        assert bad is None, f"{z.name}: {bad} is damaged"
        print(f"  {z.name}: {len(f.namelist())} files, all whole")
PY

( cd "$A" && rm -f SHA256SUMS.txt && sha256sum -- * > SHA256SUMS.txt )
echo "---- $(wc -l < "$A/SHA256SUMS.txt") files for the release, in $A ----"
cat "$A/SHA256SUMS.txt"
