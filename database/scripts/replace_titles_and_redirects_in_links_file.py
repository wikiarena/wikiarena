"""
Replaces page names in the links file with their corresponding IDs, eliminates links containing
non-existing pages, and replaces redirects with the pages to which they redirect.

Output is written to stdout.
"""

import sys
import gzip
from pathlib import Path
from typing import Dict, Set

def main() -> None:
    # Validate inputs
    if len(sys.argv) < 4:
        print('[ERROR] Not enough arguments provided!', file=sys.stderr)
        print(f'[INFO] Usage: {sys.argv[0]} <pages_file> <redirects_file> <links_file>', file=sys.stderr)
        sys.exit(1)

    pages_file = Path(sys.argv[1])
    redirects_file = Path(sys.argv[2])
    links_file = Path(sys.argv[3])

    if not pages_file.suffix == '.gz':
        print('[ERROR] Pages file must be gzipped.', file=sys.stderr)
        sys.exit(1)

    if not redirects_file.suffix == '.gz':
        print('[ERROR] Redirects file must be gzipped.', file=sys.stderr)
        sys.exit(1)

    if not links_file.suffix == '.gz':
        print('[ERROR] Links file must be gzipped.', file=sys.stderr)
        sys.exit(1)

    # Create a set of all page IDs and a dictionary of page titles to their corresponding IDs.
    all_page_ids: Set[str] = set()
    page_titles_to_ids: Dict[str, str] = {}
    
    with gzip.open(pages_file, 'rt', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 4:
                print(f'[ERROR] Line {line_num} in pages file has only {len(parts)} parts, expected 4', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            page_id, page_ns, page_title, page_is_redirect = parts[0], parts[1], parts[2], parts[3]
            # Ignore the ns and redirect we don't need them
            all_page_ids.add(page_id)
            page_titles_to_ids[page_title] = page_id

    print(f'[INFO] {len(all_page_ids)} pages loaded', file=sys.stderr)
    print(f'[INFO] {len(page_titles_to_ids)} page titles loaded', file=sys.stderr)

    # Create a dictionary of page IDs to the target page ID to which they redirect.
    redirects: Dict[str, str] = {}
    
    with gzip.open(redirects_file, 'rt', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 2:
                print(f'[ERROR] Line {line_num} in redirects file has only {len(parts)} parts, expected 2', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            source_page_id, target_page_id = parts[0], parts[1]
            redirects[source_page_id] = target_page_id

    print(f'[INFO] {len(redirects)} redirects loaded', file=sys.stderr)

    # Loop through each line in the links file, replacing titles with IDs, applying redirects, and
    # removing nonexistent pages, writing the result to stdout.
    with gzip.open(links_file, 'rt', encoding='utf-8') as f:
        written_lines = 0
        source_page_exists_count = 0
        target_page_exists_count = 0

        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 2:
                print(f'[ERROR] Line {line_num} in links file has only {len(parts)} parts, expected 2', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            source_page_id, target_page_id = parts[0], parts[1]

            # resolve redirects
            source_page_id = redirects.get(source_page_id, source_page_id)
            target_page_id = redirects.get(target_page_id, target_page_id)

            # check if pages exist
            source_page_exists = source_page_id in all_page_ids
            target_page_exists = target_page_id in all_page_ids

            # if both pages exist, write the link
            if source_page_exists and target_page_exists and source_page_id != target_page_id:
                print(f'{source_page_id}\t{target_page_id}')
                written_lines += 1

            if source_page_exists:
                source_page_exists_count += 1

            if target_page_exists:
                target_page_exists_count += 1

            if line_num % 1_000_000 == 0:
                print(f"  Processed {line_num:,} lines, {source_page_exists_count:,} source pages exist, {target_page_exists_count:,} target pages exist, {written_lines:,} lines written...", file=sys.stderr, end='\r')
    
    print(f'[INFO] Processed {line_num:,} lines, {source_page_exists_count:,} source pages exist, {written_lines:,} lines written', file=sys.stderr)

if __name__ == '__main__':
    main()
