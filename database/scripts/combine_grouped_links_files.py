"""
Combines the incoming and outgoing links (as well as their counts) for each page.

Output is written to stdout.
"""

import sys
import gzip
from pathlib import Path
from collections import defaultdict
from typing import Dict, DefaultDict

def main() -> None:
    # Validate input arguments.
    if len(sys.argv) < 3:
        print('[ERROR] Not enough arguments provided!', file=sys.stderr)
        print(f'[INFO] Usage: {sys.argv[0]} <outgoing_links_file> <incoming_links_file>', file=sys.stderr)
        sys.exit(1)

    outgoing_links_file = Path(sys.argv[1])
    incoming_links_file = Path(sys.argv[2])

    if not outgoing_links_file.suffix == '.gz':
        print('[ERROR] Outgoing links file must be gzipped.', file=sys.stderr)
        sys.exit(1)

    if not incoming_links_file.suffix == '.gz':
        print('[ERROR] Incoming links file must be gzipped.', file=sys.stderr)
        sys.exit(1)

    # Create a dictionary of page IDs to their incoming and outgoing links.
    links: DefaultDict[str, Dict[str, str]] = defaultdict(lambda: defaultdict(str))
    
    # Process outgoing links
    with gzip.open(outgoing_links_file, 'rt', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 2:
                print(f'[ERROR] Line {line_num} in outgoing links file has only {len(parts)} parts, expected 2', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            source_page_id, target_page_ids = parts[0], parts[1]
            links[source_page_id]['outgoing'] = target_page_ids

    # Process incoming links
    with gzip.open(incoming_links_file, 'rt', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip('\n')
            parts = line.split('\t')
            
            if len(parts) < 2:
                print(f'[ERROR] Line {line_num} in incoming links file has only {len(parts)} parts, expected 2', file=sys.stderr)
                print(f'[ERROR] Problematic line: {repr(line)}', file=sys.stderr)
                print(f'[ERROR] Parts: {parts}', file=sys.stderr)
                continue
            
            target_page_id, source_page_ids = parts[0], parts[1]
            links[target_page_id]['incoming'] = source_page_ids

    # For each page in the links dictionary, print out its incoming and outgoing links as well as their
    # counts.
    for page_id, page_links in links.items():
        outgoing_links = page_links.get('outgoing', '')
        outgoing_links_count = 0 if outgoing_links == '' else len(outgoing_links.split('|'))

        incoming_links = page_links.get('incoming', '')
        incoming_links_count = 0 if incoming_links == '' else len(incoming_links.split('|'))

        columns = [page_id, str(outgoing_links_count), str(incoming_links_count), outgoing_links, incoming_links]

        print('\t'.join(columns))

if __name__ == '__main__':
    main()
