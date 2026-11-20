#!/usr/bin/env bash
# Turn the text on stdin into one GitHub Actions error annotation (shown on the run page even to
# people who aren't signed in, unlike logs and step summaries). CI only.
#   some-command | bash tests/ci_annotate.sh "Title"
title=${1:-failure}
text=$(head -c 12000)
text=${text//'%'/'%25'}
text=${text//$'\r'/'%0D'}
text=${text//$'\n'/'%0A'}
echo "::error title=${title}::${text}"
