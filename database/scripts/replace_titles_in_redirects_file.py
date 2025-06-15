"""
Replaces page titles in the redirects file with their corresponding IDs.

Output is written to stdout.
"""

import sys
import gzip
from pathlib import Path
from typing import Dict, Set

def main() -> None:
    # Validate input arguments.
    if len(sys.argv) < 3:
        print('[ERROR] Not enough arguments provided!', file=sys.stderr)
        print(f'[INFO] Usage: {sys.argv[0]} <pages_file> <redirects_file>', file=sys.stderr)
        sys.exit(1)

    pages_file = Path(sys.argv[1])
    redirects_file = Path(sys.argv[2])

    if not pages_file.suffix == '.gz':
        print('[ERROR] Pages file must be gzipped.', file=sys.stderr)
        sys.exit(1)

    if not redirects_file.suffix == '.gz':
        print('[ERROR] Redirects file must be gzipped.', file=sys.stderr)
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

    # Create a dictionary of redirects, replace page titles in the redirects file with their
    # corresponding IDs and ignoring pages which do not exist.
    redirects: Dict[str, str] = {}
    
    with gzip.open(redirects_file, 'rt', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 3:
                print(f'[ERROR] Line {line_num} in redirects file has only {len(parts)} parts, expected 3', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            source_page_id, source_page_ns, target_page_title = parts[0], parts[1], parts[2]

            source_page_exists = source_page_id in all_page_ids
            target_page_id = page_titles_to_ids.get(target_page_title)

            if source_page_exists and target_page_id is not None:
                redirects[source_page_id] = target_page_id

    # Loop through the redirects dictionary and remove redirects which redirect to another redirect,
    # writing the remaining redirects to stdout.
    for source_page_id, target_page_id in redirects.items():
        start_target_page_id = target_page_id

        redirected_count = 0
        while target_page_id in redirects:
            target_page_id = redirects[target_page_id]
            redirected_count += 1

            # Break out if there is a circular path, meaning the redirects only point to other redirects,
            # not an actual page.
            if target_page_id == start_target_page_id or redirected_count > 100:
                target_page_id = None
                break

        if target_page_id is not None:
            print(f'{source_page_id}\t{target_page_id}')

if __name__ == '__main__':
    main()
