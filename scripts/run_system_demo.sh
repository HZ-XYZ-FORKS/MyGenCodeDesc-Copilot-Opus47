#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${1:-$(mktemp -d "${TMPDIR:-/tmp}/agcd-system-demo.XXXXXX")}" 

printf 'Demo workspace: %s\n' "$WORK"
mkdir -p "$WORK" "$WORK/repo" "$WORK/gcd_v2603" "$WORK/gcd_v2604" "$WORK/patches"

cd "$WORK/repo"
git init -q -b main
git config user.email demo@example.com
git config user.name demo

cat > src_app.tmp <<'EOF'
a1
a2
a3
a4
EOF
mkdir -p src
mv src_app.tmp src/app.py
git add src/app.py
GIT_AUTHOR_DATE='2026-02-01T10:00:00Z' GIT_COMMITTER_DATE='2026-02-01T10:00:00Z' git commit -q -m 'c1 add app'
C1="$(git rev-parse HEAD)"

cat > src/app.py <<'EOF'
a1
a2_human
a3
a4
EOF
git add src/app.py
GIT_AUTHOR_DATE='2026-02-02T10:00:00Z' GIT_COMMITTER_DATE='2026-02-02T10:00:00Z' git commit -q -m 'c2 modify line2'
C2="$(git rev-parse HEAD)"

cat > util.py <<'EOF'
u1
u2
u3
EOF
git add util.py
GIT_AUTHOR_DATE='2026-02-03T10:00:00Z' GIT_COMMITTER_DATE='2026-02-03T10:00:00Z' git commit -q -m 'c3 add util'
C3="$(git rev-parse HEAD)"

git mv src/app.py src/main.py
GIT_AUTHOR_DATE='2026-02-04T10:00:00Z' GIT_COMMITTER_DATE='2026-02-04T10:00:00Z' git commit -q -m 'c4 rename app'
C4="$(git rev-parse HEAD)"

cat > util.py <<'EOF'
u1
u3
EOF
git add util.py
GIT_AUTHOR_DATE='2026-02-05T10:00:00Z' GIT_COMMITTER_DATE='2026-02-05T10:00:00Z' git commit -q -m 'c5 delete one util line'
C5="$(git rev-parse HEAD)"

for C in "$C1" "$C2" "$C3" "$C4" "$C5"; do
  git show --format= --patch "$C" > "$WORK/patches/$C.patch"
done

cat > "$WORK/gcd_v2603/01-c1.json" <<EOF
{"protocolName":"generatedTextDesc","protocolVersion":"26.03","SUMMARY":{},"DETAIL":[{"fileName":"src/app.py","codeLines":[{"lineRange":{"from":1,"to":4},"genRatio":100,"genMethod":"vibeCoding"}]}],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C1","revisionTimestamp":"2026-02-01T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2603/02-c2.json" <<EOF
{"protocolName":"generatedTextDesc","protocolVersion":"26.03","SUMMARY":{},"DETAIL":[{"fileName":"src/app.py","codeLines":[{"lineLocation":2,"genRatio":0,"genMethod":"Manual"}]}],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C2","revisionTimestamp":"2026-02-02T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2603/03-c3.json" <<EOF
{"protocolName":"generatedTextDesc","protocolVersion":"26.03","SUMMARY":{},"DETAIL":[{"fileName":"util.py","codeLines":[{"lineRange":{"from":1,"to":3},"genRatio":80,"genMethod":"vibeCoding"}]}],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C3","revisionTimestamp":"2026-02-03T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2603/04-c4.json" <<EOF
{"protocolName":"generatedTextDesc","protocolVersion":"26.03","SUMMARY":{},"DETAIL":[],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C4","revisionTimestamp":"2026-02-04T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2603/05-c5.json" <<EOF
{"protocolName":"generatedTextDesc","protocolVersion":"26.03","SUMMARY":{},"DETAIL":[],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C5","revisionTimestamp":"2026-02-05T10:00:00Z"}}
EOF

cat > "$WORK/gcd_v2604/01-c1.json" <<EOF
{"protocolVersion":"26.04","SUMMARY":{"lineCount":4},"DETAIL":[{"fileName":"src/app.py","codeLines":[{"changeType":"add","lineLocation":1,"genRatio":100,"genMethod":"vibeCoding","blame":{"revisionId":"$C1","originalFilePath":"src/app.py","originalLine":1,"timestamp":"2026-02-01T10:00:00Z"}},{"changeType":"add","lineLocation":2,"genRatio":100,"genMethod":"vibeCoding","blame":{"revisionId":"$C1","originalFilePath":"src/app.py","originalLine":2,"timestamp":"2026-02-01T10:00:00Z"}},{"changeType":"add","lineLocation":3,"genRatio":100,"genMethod":"vibeCoding","blame":{"revisionId":"$C1","originalFilePath":"src/app.py","originalLine":3,"timestamp":"2026-02-01T10:00:00Z"}},{"changeType":"add","lineLocation":4,"genRatio":100,"genMethod":"vibeCoding","blame":{"revisionId":"$C1","originalFilePath":"src/app.py","originalLine":4,"timestamp":"2026-02-01T10:00:00Z"}}]}],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C1","revisionTimestamp":"2026-02-01T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2604/02-c2.json" <<EOF
{"protocolVersion":"26.04","SUMMARY":{"lineCount":1},"DETAIL":[{"fileName":"src/app.py","codeLines":[{"changeType":"delete","blame":{"revisionId":"$C1","originalFilePath":"src/app.py","originalLine":2}},{"changeType":"add","lineLocation":2,"genRatio":0,"genMethod":"Manual","blame":{"revisionId":"$C2","originalFilePath":"src/app.py","originalLine":2,"timestamp":"2026-02-02T10:00:00Z"}}]}],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C2","revisionTimestamp":"2026-02-02T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2604/03-c3.json" <<EOF
{"protocolVersion":"26.04","SUMMARY":{"lineCount":3},"DETAIL":[{"fileName":"util.py","codeLines":[{"changeType":"add","lineLocation":1,"genRatio":80,"genMethod":"vibeCoding","blame":{"revisionId":"$C3","originalFilePath":"util.py","originalLine":1,"timestamp":"2026-02-03T10:00:00Z"}},{"changeType":"add","lineLocation":2,"genRatio":80,"genMethod":"vibeCoding","blame":{"revisionId":"$C3","originalFilePath":"util.py","originalLine":2,"timestamp":"2026-02-03T10:00:00Z"}},{"changeType":"add","lineLocation":3,"genRatio":80,"genMethod":"vibeCoding","blame":{"revisionId":"$C3","originalFilePath":"util.py","originalLine":3,"timestamp":"2026-02-03T10:00:00Z"}}]}],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C3","revisionTimestamp":"2026-02-03T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2604/04-c4.json" <<EOF
{"protocolVersion":"26.04","SUMMARY":{"lineCount":0},"DETAIL":[],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C4","revisionTimestamp":"2026-02-04T10:00:00Z"}}
EOF
cat > "$WORK/gcd_v2604/05-c5.json" <<EOF
{"protocolVersion":"26.04","SUMMARY":{"lineCount":0},"DETAIL":[{"fileName":"util.py","codeLines":[{"changeType":"delete","blame":{"revisionId":"$C3","originalFilePath":"util.py","originalLine":2}}]}],"REPOSITORY":{"vcsType":"git","repoURL":"https://demo/r","repoBranch":"main","revisionId":"$C5","revisionTimestamp":"2026-02-05T10:00:00Z"}}
EOF

cd "$ROOT"
START='2026-01-01T00:00:00Z'
END='2026-12-31T00:00:00Z'
THRESH='60'

run_case() {
  local name="$1"; shift
  local out="$WORK/out_${name}"
  python3 -m aggregateGenCodeDesc "$@" \
    --start-time "$START" --end-time "$END" --threshold "$THRESH" --scope A \
    --output-dir "$out"
  python3 - <<'PY' "$out/genCodeDescV26.03.json" "$name"
import json,sys
p=sys.argv[1]; n=sys.argv[2]
d=json.load(open(p, encoding='utf-8'))
m=d['AGGREGATE']['metrics']
print(f"{n}: total={d['SUMMARY']['totalCodeLines']} weighted={m['weighted']['value']:.6f} fullyAI={m['fullyAI']['value']:.6f} mostlyAI={m['mostlyAI']['value']:.6f}")
PY
}

run_case A --repo-url https://demo/r --repo-branch main --algorithm A --gen-code-desc-dir "$WORK/gcd_v2603" --repo-path "$WORK/repo"
run_case B --repo-url https://demo/r --repo-branch main --algorithm B --gen-code-desc-dir "$WORK/gcd_v2603" --commit-patch-dir "$WORK/patches"
run_case C --repo-url https://demo/r --repo-branch main --algorithm C --gen-code-desc-dir "$WORK/gcd_v2604"

python3 - <<'PY' "$WORK/out_A/genCodeDescV26.03.json" "$WORK/out_B/genCodeDescV26.03.json" "$WORK/out_C/genCodeDescV26.03.json"
import json,sys
vals=[]
for p in sys.argv[1:]:
    d=json.load(open(p, encoding='utf-8'))
    m=d['AGGREGATE']['metrics']
    vals.append((d['SUMMARY']['totalCodeLines'], m['weighted']['value'], m['fullyAI']['value'], m['mostlyAI']['value']))
if not (vals[0]==vals[1]==vals[2]):
    raise SystemExit(f"metric mismatch across A/B/C: {vals}")
print('A/B/C metrics consistent.')
PY

printf 'Demo finished successfully. Artifacts under: %s\n' "$WORK"
