#!/usr/bin/env python3
"""
mhtml_to_html.py — Recursively converts all .mhtml files under input_dir
into standalone .html files under output_dir, preserving folder structure
AND extracting embedded resources (images, CSS, fonts, etc.) so the page
actually renders correctly instead of showing broken cid:/mhtml.blink links.

Usage:
    python mhtml_to_html.py <input_dir> [output_dir]

If output_dir is omitted, defaults to ~/hackthebox_academy_EXTRACTED/modules
"""

import email
from email import policy
import argparse
import os
import re
import mimetypes
import hashlib

# Fallback extension map for content types mimetypes doesn't always guess well
EXT_OVERRIDES = {
    'image/svg+xml': '.svg',
    'image/x-icon': '.ico',
    'image/vnd.microsoft.icon': '.ico',
    'font/woff': '.woff',
    'font/woff2': '.woff2',
    'application/font-woff': '.woff',
    'text/css': '.css',
    'application/javascript': '.js',
    'text/javascript': '.js',
}

MAX_FILENAME_LEN = 150  # stay well under the 255-byte filesystem limit


def guess_ext(content_type):
    if content_type in EXT_OVERRIDES:
        return EXT_OVERRIDES[content_type]
    ext = mimetypes.guess_extension(content_type)
    return ext if ext else '.bin'


def sanitize_filename(name, ext):
    # Strip query strings/fragments and unsafe characters so it's a valid filename
    name = name.split('?')[0].split('#')[0]
    name = os.path.basename(name) or 'resource'
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name)

    # If it's still too long (e.g. huge encoded/data-like names), or has no
    # recognizable extension, fall back to a short hash-based name instead.
    if len(name) > MAX_FILENAME_LEN or not os.path.splitext(name)[1]:
        digest = hashlib.sha1(name.encode('utf-8', errors='ignore')).hexdigest()[:16]
        name = f'resource_{digest}{ext}'

    return name


def convert_file(input_path, output_path):
    with open(input_path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    html_content = None
    resources = []  # list of dicts: content_id, content_location, filename, data

    for part in msg.walk():
        content_type = part.get_content_type()

        if content_type == 'text/html' and html_content is None:
            html_content = part.get_content()
            continue

        if content_type.startswith('multipart/'):
            continue

        # Anything else (images, css, js, fonts) is a resource to extract
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            payload = None
        if not payload:
            continue

        content_id = part.get('Content-ID', '')
        content_id = content_id.strip('<>') if content_id else ''
        content_location = part.get('Content-Location', '') or ''

        ext = guess_ext(content_type)
        if content_location:
            base = sanitize_filename(content_location, ext)
            if not os.path.splitext(base)[1]:
                base += ext
        else:
            base = f'resource_{len(resources):04d}{ext}'

        resources.append({
            'content_id': content_id,
            'content_location': content_location,
            'filename': base,
            'data': payload,
        })

    if not html_content:
        print(f'No HTML content found in: {input_path}')
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    resources_dir_name = f'{base_name}_files'
    resources_dir = os.path.join(os.path.dirname(output_path), resources_dir_name)

    # Deduplicate filenames within this page
    seen = {}
    for res in resources:
        fname = res['filename']
        if fname in seen:
            seen[fname] += 1
            root, ext = os.path.splitext(fname)
            fname = f'{root}_{seen[fname]}{ext}'
        else:
            seen[fname] = 0
        res['final_filename'] = fname

    # Write resources to disk (only create the folder if there's anything to put in it)
    if resources:
        os.makedirs(resources_dir, exist_ok=True)
        for res in resources:
            with open(os.path.join(resources_dir, res['final_filename']), 'wb') as rf:
                rf.write(res['data'])

    # Rewrite references in the HTML:
    #   cid:XXXX@mhtml.blink  -> resources_dir_name/filename
    #   original absolute URL (Content-Location) -> resources_dir_name/filename
    for res in resources:
        rel_path = f'{resources_dir_name}/{res["final_filename"]}'
        if res['content_id']:
            html_content = html_content.replace(f'cid:{res["content_id"]}', rel_path)
        if res['content_location']:
            html_content = html_content.replace(res['content_location'], rel_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f'Saved: {output_path}  ({len(resources)} resource(s) extracted)')
    return True


def main(input_dir, output_dir):
    input_dir = os.path.abspath(os.path.expanduser(input_dir))
    output_dir = os.path.abspath(os.path.expanduser(output_dir))
    os.makedirs(output_dir, exist_ok=True)

    converted = 0
    skipped = 0

    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            if not filename.lower().endswith('.mhtml'):
                continue

            input_path = os.path.join(root, filename)
            rel_path = os.path.relpath(input_path, input_dir)
            output_path = os.path.join(output_dir, os.path.splitext(rel_path)[0] + '.html')

            if convert_file(input_path, output_path):
                converted += 1
            else:
                skipped += 1

    print(f'\nDone. Converted: {converted}, Skipped (no HTML found): {skipped}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Recursively convert MHTML files to standalone HTML with extracted resources.')
    parser.add_argument('input_dir', type=str, help='Input directory (searches MHTML recursively)[.ex: hack-the-box-academy/modules]')
    parser.add_argument('output_dir', type=str, nargs='?',
                         default=os.path.join(os.path.expanduser('~'), 'hackthebox_academy_EXTRACTED', 'modules'),
                         help='Output directory (default: ~/hackthebox_academy_EXTRACTED/modules)')
    args = parser.parse_args()
    main(args.input_dir, args.output_dir)

