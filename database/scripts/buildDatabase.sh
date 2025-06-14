#!/usr/bin/env bash
set -euo pipefail

# ========================================================
# 0.  Language edition
# ========================================================
WIKI="${WIKI:-enwiki}"            # simplewiki, frwiki, …

# ========================================================
# 1.  GNU ↔︎ BSD helpers
# ========================================================
GREP=$(command -v ggrep || echo grep)
SORT=$(command -v gsort || echo sort)
SHA1SUM=$(command -v gsha1sum || command -v sha1sum || echo shasum)

sha1_check() {                    # read “hash  file” lines from stdin
  if [[ $SHA1SUM == *sha1sum ]]; then $SHA1SUM -c -
  else awk '{print $1"\t"$2}' | $SHA1SUM -a 1 -c -; fi
}

sort_maybe_mem() {                # $1 mem %, rest = sort args
  local mem=$1; shift
  if $SORT --version 2>/dev/null | grep -q GNU; then
      $SORT -S "$mem" -t$'\t' "$@"
  else
      $SORT      -t$'\t' "$@"
  fi
}

# ========================================================
# 2.  Dump date
# ========================================================
if [[ $# -eq 0 || $1 == latest ]]; then
  DOWNLOAD_DATE=$(wget -q -O- "https://dumps.wikimedia.org/$WIKI/" \
                 | $GREP -Eo '[0-9]{8}' | $SORT | tail -n1)
else
  [[ ${#1} -eq 8 ]] || { echo "[ERROR] invalid date $1"; exit 1; }
  DOWNLOAD_DATE=$1
fi

# ========================================================
# 3.  Paths & filenames
# ========================================================
ROOT_DIR=$(pwd);  OUT_DIR=dumps
DOWNLOAD_URL="https://dumps.wikimedia.org/$WIKI/$DOWNLOAD_DATE"
TORRENT_URL="https://tools.wmflabs.org/dump-torrents/$WIKI/$DOWNLOAD_DATE"

SHA1SUM_FILE="$WIKI-$DOWNLOAD_DATE-sha1sums.txt"
REDIRECTS_FILE="$WIKI-$DOWNLOAD_DATE-redirect.sql.gz"
PAGES_FILE="$WIKI-$DOWNLOAD_DATE-page.sql.gz"
LINKS_FILE="$WIKI-$DOWNLOAD_DATE-pagelinks.sql.gz"
LINKTARGET_FILE="$WIKI-$DOWNLOAD_DATE-linktarget.sql.gz"

mkdir -p "$OUT_DIR";  pushd "$OUT_DIR" >/dev/null
echo "[INFO] wiki=$WIKI   date=$DOWNLOAD_DATE   dir=$OUT_DIR"; echo

# ========================================================
# 4.  Download & verify
# ========================================================
download_file() {
  local tag=$1 file=$2
  [[ -f $file ]] && { echo "[WARN] $file already present"; return; }
  echo
  if [[ $tag != sha1sums && -x $(command -v aria2c) ]]; then
      echo "[INFO] torrent $tag"
      time aria2c --summary-interval=0 --console-log-level=warn --seed-time=0 \
           "$TORRENT_URL/$file.torrent"
  else
      echo "[INFO] wget $tag"
      time wget --progress=dot:giga "$DOWNLOAD_URL/$file"
  fi
  [[ $tag == sha1sums ]] && return
  echo; echo "[INFO] verify SHA-1 $file"
  time $GREP "$file" "$SHA1SUM_FILE" | sha1_check
}

download_file sha1sums   "$SHA1SUM_FILE"
download_file redirects  "$REDIRECTS_FILE"
download_file pages      "$PAGES_FILE"
download_file links      "$LINKS_FILE"
download_file linktarget "$LINKTARGET_FILE"

# ========================================================
# 5.  Trim SQL → TSV (gzip-compressed)
# ========================================================
trim_step() {                        # $1 tag  $2 in  $3 out
  [[ -f $3 ]] && { echo "[WARN] $3 exists"; return; }
  echo; echo "[INFO] trim $1"
  time python "$ROOT_DIR/trim_wikipedia_dump.py" "$1" "$2" "$3"
}

trim_step redirects   "$REDIRECTS_FILE"   redirects.txt.gz
trim_step pages       "$PAGES_FILE"       pages.txt.gz
trim_step links       "$LINKS_FILE"       links.txt.gz
trim_step targets     "$LINKTARGET_FILE"  linktarget.txt.gz

# ========================================================
# 6.  ID normalisation & pruning
# ========================================================

if [[ ! -f redirects.with_ids.txt.gz ]]; then
  echo; echo "[INFO] titles→ids in redirects"
  time python "$ROOT_DIR/replace_titles_in_redirects_file.py" \
       pages.txt.gz redirects.txt.gz |
       sort_maybe_mem 100% -k1,1n | pigz --fast \
       > redirects.with_ids.txt.gz.tmp
  mv redirects.with_ids.txt.gz.tmp redirects.with_ids.txt.gz
fi

if [[ ! -f edges.ids_only.txt.gz ]]; then
  echo; echo "[INFO] merge pages+links+targets → IDs-only edge list"
  time python "$ROOT_DIR/merge_links.py" \
       pages.txt.gz linktarget.txt.gz links.txt.gz |
       pigz --fast > edges.ids_only.txt.gz.tmp
  mv edges.ids_only.txt.gz.tmp edges.ids_only.txt.gz
fi

if [[ ! -f links.with_ids.txt.gz ]]; then
  echo; echo "[INFO] apply redirects to edge list"
  time python "$ROOT_DIR/replace_titles_and_redirects_in_links_file.py" \
       pages.txt.gz redirects.with_ids.txt.gz edges.ids_only.txt.gz |
       pigz --fast > links.with_ids.txt.gz.tmp
  mv links.with_ids.txt.gz.tmp links.with_ids.txt.gz
fi

if [[ ! -f pages.pruned.txt.gz ]]; then
  echo; echo "[INFO] prune orphan redirects in pages"
  time python "$ROOT_DIR/prune_pages_file.py" \
       pages.txt.gz redirects.with_ids.txt.gz |
       pigz --fast > pages.pruned.txt.gz
fi

#########################################################
#  7. Sort links two ways                               #
#########################################################
sort_links() {                           # $1 = field (1|2)  $2 = outfile
  [[ -f $2 ]] && { echo "[WARN] $2 exists"; return; }
  echo; echo "[INFO] Sorting links by $1"
  time pigz -dc links.with_ids.txt.gz |
       sort_maybe_mem 80% -k"$1","$1"n |
       uniq |
       pigz --fast > "$2.tmp"
  mv "$2.tmp" "$2"
}
sort_links 1 links.sorted_by_source_id.txt.gz
sort_links 2 links.sorted_by_target_id.txt.gz

#########################################################
#  8. Group links per page                              #
#########################################################
group_links() {                         # $1 in  $2 col  $3 out
  [[ -f $3 ]] && { echo "[WARN] $3 exists"; return; }
  echo; echo "[INFO] Grouping $1"
  time pigz -dc "$1" | awk -F'\t' -v col="$2" '
    $col==last {printf "|%s", (col==1?$2:$1); next}
    NR>1       {print ""}
                {last=$col; printf "%s\t%s", $col, (col==1?$2:$1)}
    END        {print ""}' |
    pigz --fast > "$3.tmp"
  mv "$3.tmp" "$3"
}
group_links links.sorted_by_source_id.txt.gz 1 links.grouped_by_source_id.txt.gz
group_links links.sorted_by_target_id.txt.gz 2 links.grouped_by_target_id.txt.gz

#########################################################
#  9. Combine incoming + outgoing + counts              #
#########################################################
if [[ ! -f links.with_counts.txt.gz ]]; then
  echo; echo "[INFO] Combining grouped links"
  time python "$ROOT_DIR/combine_grouped_links_files.py" \
       links.grouped_by_source_id.txt.gz links.grouped_by_target_id.txt.gz |
       pigz --fast > links.with_counts.txt.gz.tmp
  mv links.with_counts.txt.gz.tmp links.with_counts.txt.gz
fi

#########################################################
# 10. Build SQLite graph DB                             #
#########################################################
if [[ ! -f wiki_graph.sqlite ]]; then
  echo; echo "[INFO] Creating SQLite DB"
  time pigz -dc redirects.with_ids.txt.gz | \
       sqlite3 wiki_graph.sqlite ".read $ROOT_DIR/../schema/createRedirectsTable.sql"

  echo; echo "[INFO] Inserting pages"
  time pigz -dc pages.pruned.txt.gz | \
       sqlite3 wiki_graph.sqlite ".read $ROOT_DIR/../schema/createPagesTable.sql"

  echo; echo "[INFO] Inserting links"
  time pigz -dc links.with_counts.txt.gz | \
       sqlite3 wiki_graph.sqlite ".read $ROOT_DIR/../schema/createLinksTable.sql"

  echo; echo "[INFO] Compressing DB"
  time pigz --best --keep wiki_graph.sqlite
else
  echo "[WARN] wiki_graph.sqlite already present"
fi

echo; echo "[INFO] All done!"