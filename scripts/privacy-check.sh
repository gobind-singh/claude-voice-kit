#!/bin/sh
# Fails if the repository contains personal or machine-specific data (run before making it public; CI runs it too).
cd "$(dirname "$0")/.." || exit 1
fail=0
check() {  # $1 = description, $2 = extended regex
  hits=$(git ls-files -z 2>/dev/null | xargs -0 grep -nIE "$2" -- 2>/dev/null | grep -v "scripts/privacy-check.sh")
  if [ -n "$hits" ]; then printf '❌ %s\n%s\n\n' "$1" "$hits"; fail=1; fi
}
check "home-directory paths"          '/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/'
check "e-mail addresses"              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(com|net|org|io|dev|ai)'
check "API keys / tokens"             '(sk-ant-|ghp_|gho_|github_pat_|xox[bap]-|AKIA)[A-Za-z0-9_-]{10,}'
check "private keys"                  'BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY'
check "temp / scratch paths"          '/private/tmp/|/var/folders/'
for f in .env .env.local; do git ls-files --error-unmatch "$f" >/dev/null 2>&1 && { echo "❌ $f is tracked"; fail=1; }; done
[ $fail -eq 0 ] && echo "✅ privacy check passed: no personal or local data found."
exit $fail
