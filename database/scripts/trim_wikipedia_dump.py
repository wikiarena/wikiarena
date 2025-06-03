#!/usr/bin/env python
"""
Memory-efficient trimming of Wikipedia SQL dumps
"""
import gzip
import re
import sys
import os

def trim_file(input_file, output_file, file_type):
    """
    Trim a Wikipedia SQL dump file
    
    file_type: 'pages', 'links', or 'redirects'
    """
    if file_type == 'pages':
        insert_pattern = re.compile(r"^INSERT INTO `page` VALUES (.+);$")
        # Match pattern for: (page_id,namespace=0,'title',is_redirect, ... we don't care about the rest)
        record_pattern = re.compile(r"(\d+),0,'((?:[^'\\]|\\.)*)',([01]),")
    elif file_type == 'links':
        insert_pattern = re.compile(r"^INSERT INTO `pagelinks` VALUES (.+);$")
        record_pattern = re.compile(r"(\d+),0,(\d+)")
    elif file_type == 'redirects':
        insert_pattern = re.compile(r"^INSERT INTO `redirect` VALUES (.+);$")
        record_pattern = re.compile(r"(\d+),0,'((?:[^'\\]|\\.)*)',")
    
    processed_lines = 0
    written_records = 0
    
    with gzip.open(input_file, 'rt', encoding='utf-8', errors='replace') as infile:
        with gzip.open(output_file, 'wt', encoding='utf-8') as outfile:
            for line in infile:
                processed_lines += 1
                if processed_lines % 1000 == 0:
                    print(f"  Processed {processed_lines:,} lines, written {written_records:,} records...", 
                          file=sys.stderr, end='\r')
                
                match = insert_pattern.match(line.strip())
                if not match:
                    continue
                
                # Extract all records from the INSERT statement
                values_str = match.group(1)
                
                # Split by ),( but handle escaped parentheses
                records = re.split(r'\),\(', values_str)
                
                for record in records:
                    # record = record.strip('()')
                    
                    if file_type == 'pages':
                        match = record_pattern.search(record)
                        if match:
                            page_id = match.group(1)
                            title = match.group(2)
                            is_redirect = match.group(3)
                            outfile.write(f"{page_id}\t{title}\t{is_redirect}\n")
                            written_records += 1
                    
                    elif file_type == 'links':
                        match = record_pattern.search(record)
                        if match:
                            source_id = match.group(1)
                            target_id = match.group(2)
                            outfile.write(f"{source_id}\t{target_id}\n")
                            written_records += 1
                    
                    elif file_type == 'redirects':
                        match = record_pattern.search(record)
                        if match:
                            source_id = match.group(1)
                            target_title = match.group(2)
                            outfile.write(f"{source_id}\t{target_title}\n")
                            written_records += 1
    
    print(f"\n  Finished! Processed {processed_lines:,} lines, written {written_records:,} records.")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: trim_wikipedia_dump.py <file_type> <input_file> <output_file>")
        print("  file_type: pages, links, or redirects")
        sys.exit(1)
    
    file_type = sys.argv[1]
    input_file = sys.argv[2]
    output_file = sys.argv[3]
    
    if file_type not in ['pages', 'links', 'redirects']:
        print(f"Error: Invalid file type '{file_type}'")
        sys.exit(1)
    
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found")
        sys.exit(1)
    
    print(f"Trimming {file_type} file: {input_file} -> {output_file}")
    trim_file(input_file, output_file, file_type)