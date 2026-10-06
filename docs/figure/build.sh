#!/usr/bin/env bash
# Compile method.tex -> docs/method.pdf and docs/method.png (used by the README). macOS / Linux.
# Needs a TeX distribution with pdflatex (MacTeX or TeX Live) and pdftoppm (poppler: brew install poppler).
#   bash docs/figure/build.sh
set -euo pipefail
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error method.tex > /dev/null
cp method.pdf ../method.pdf
pdftoppm -png -r 220 -singlefile method.pdf ../method
rm -f method.aux method.log
echo "ok: docs/method.pdf, docs/method.png"
