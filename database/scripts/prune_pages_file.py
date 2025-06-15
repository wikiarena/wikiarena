"""
Prunes the pages file by removing pages which are marked as redirects but have no corresponding
redirect in the redirects file.

Output is written to stdout.
"""

import sys
import gzip
from pathlib import Path
from typing import Dict

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

    # Create a dictionary of redirects.
    redirects: Dict[str, bool] = {}
    
    with gzip.open(redirects_file, 'rt', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 2:
                print(f'[ERROR] Line {line_num} in redirects file has only {len(parts)} parts, expected 2', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            source_page_id = parts[0]
            redirects[source_page_id] = True

    # Loop through the pages file, ignoring pages which are marked as redirects but which do not have a
    # corresponding redirect in the redirects dictionary, printing the remaining pages to stdout.
    with gzip.open(pages_file, 'rt', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 4:
                print(f'[ERROR] Line {line_num} in pages file has only {len(parts)} parts, expected 4', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            page_id, page_namespace, page_title, is_redirect = parts[0], parts[1], parts[2], parts[3]

            if is_redirect == '0' or page_id in redirects:
                print(f'{page_id}\t{page_namespace}\t{page_title}\t{is_redirect}')

if __name__ == '__main__':
    main()
