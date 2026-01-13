#!/usr/bin/env python3
"""
MBOX to JSON Parser for Litigation Support
Extracts emails with full metadata, plain text bodies, and attachments.
Optimized for AI assessment of content for timelines and actions.
"""

import mailbox
import email
import email.utils
import email.header
import json
import os
import re
import hashlib
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from email.utils import parseaddr, getaddresses


def decode_header_value(value: str) -> str:
    """Decode encoded email header values (handles UTF-8, ISO-8859-1, etc.)"""
    if not value:
        return ""

    decoded_parts = []
    try:
        parts = email.header.decode_header(value)
        for content, charset in parts:
            if isinstance(content, bytes):
                charset = charset or 'utf-8'
                try:
                    decoded_parts.append(content.decode(charset, errors='replace'))
                except (LookupError, UnicodeDecodeError):
                    decoded_parts.append(content.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(content)
    except Exception:
        return value

    return ''.join(decoded_parts)


def parse_email_address(addr_string: str) -> dict:
    """Parse an email address into name and email components."""
    if not addr_string:
        return None

    decoded = decode_header_value(addr_string)
    name, email_addr = parseaddr(decoded)

    if not email_addr and not name:
        return None

    return {
        "name": name.strip() if name else "",
        "email": email_addr.strip().lower() if email_addr else ""
    }


def parse_email_addresses(addr_string: str) -> list:
    """Parse multiple email addresses from a header field."""
    if not addr_string:
        return []

    decoded = decode_header_value(addr_string)
    addresses = getaddresses([decoded])

    result = []
    for name, email_addr in addresses:
        if email_addr or name:
            result.append({
                "name": name.strip() if name else "",
                "email": email_addr.strip().lower() if email_addr else ""
            })

    return result


def parse_date(date_string: str) -> tuple[Optional[str], str]:
    """
    Parse email date to ISO 8601 format.
    Returns (iso_date, original_date_string)
    """
    if not date_string:
        return None, ""

    original = date_string.strip()

    try:
        parsed = email.utils.parsedate_to_datetime(date_string)
        # Convert to UTC for consistent sorting
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        iso_date = parsed.isoformat()
        return iso_date, original
    except Exception:
        return None, original


def get_plain_text_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message."""
    body_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            # Skip attachments
            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_parts.append(payload.decode(charset, errors='replace'))
                except Exception as e:
                    body_parts.append(f"[Decoding error: {e}]")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload:
                    body_parts.append(payload.decode(charset, errors='replace'))
            except Exception as e:
                body_parts.append(f"[Decoding error: {e}]")

    return "\n".join(body_parts).strip()


def extract_attachments(msg: email.message.Message, output_dir: Path, msg_index: int) -> list:
    """Extract attachments from email and save to disk."""
    attachments = []

    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))

        if "attachment" not in content_disposition and "inline" not in content_disposition:
            # Check if it's a non-text part that should be treated as attachment
            content_type = part.get_content_type()
            if content_type in ["text/plain", "text/html", "multipart/alternative",
                               "multipart/mixed", "multipart/related"]:
                continue
            # If it has no filename, skip
            filename = part.get_filename()
            if not filename:
                continue

        filename = part.get_filename()
        if not filename:
            continue

        # Decode filename if encoded
        filename = decode_header_value(filename)
        # Sanitize filename
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip()

        if not filename:
            continue

        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue

            # Create message-specific attachment directory
            msg_attach_dir = output_dir / f"msg_{msg_index:06d}"
            msg_attach_dir.mkdir(parents=True, exist_ok=True)

            # Handle duplicate filenames
            file_path = msg_attach_dir / filename
            counter = 1
            base_name = file_path.stem
            suffix = file_path.suffix
            while file_path.exists():
                file_path = msg_attach_dir / f"{base_name}_{counter}{suffix}"
                counter += 1

            # Write attachment
            with open(file_path, 'wb') as f:
                f.write(payload)

            # Calculate hash for integrity verification
            file_hash = hashlib.sha256(payload).hexdigest()

            attachments.append({
                "filename": filename,
                "content_type": part.get_content_type(),
                "size_bytes": len(payload),
                "extracted_path": str(file_path.relative_to(output_dir.parent)),
                "sha256": file_hash
            })

        except Exception as e:
            attachments.append({
                "filename": filename,
                "content_type": part.get_content_type(),
                "error": str(e)
            })

    return attachments


def parse_references(msg: email.message.Message) -> list:
    """Extract message references for threading."""
    refs_header = msg.get("References", "")
    if not refs_header:
        return []

    # References are space or newline separated message-ids
    refs = re.findall(r'<[^>]+>', refs_header)
    return refs


def parse_mbox_file(mbox_path: Path, output_dir: Path) -> dict:
    """Parse a single MBOX file and return structured data."""

    print(f"Parsing: {mbox_path}")

    attachments_dir = output_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    emails = []
    earliest_date = None
    latest_date = None
    total_attachments = 0

    try:
        mbox = mailbox.mbox(str(mbox_path))
    except Exception as e:
        return {"error": f"Failed to open MBOX file: {e}"}

    for i, msg in enumerate(mbox):
        if i % 100 == 0:
            print(f"  Processing message {i}...")

        # Extract message ID
        message_id = msg.get("Message-ID", "")
        if message_id:
            message_id = message_id.strip()
        else:
            # Generate a fallback ID based on content hash
            fallback_content = f"{msg.get('From', '')}{msg.get('Date', '')}{msg.get('Subject', '')}"
            message_id = f"<generated-{hashlib.md5(fallback_content.encode()).hexdigest()}@mbox-parser>"

        # Parse date
        iso_date, original_date = parse_date(msg.get("Date", ""))

        # Track date range
        if iso_date:
            if earliest_date is None or iso_date < earliest_date:
                earliest_date = iso_date
            if latest_date is None or iso_date > latest_date:
                latest_date = iso_date

        # Extract attachments
        attachments = extract_attachments(msg, attachments_dir, i)
        total_attachments += len(attachments)

        # Build email record
        email_record = {
            "index": i,
            "message_id": message_id,
            "date": iso_date,
            "date_original": original_date,
            "from": parse_email_address(msg.get("From", "")),
            "to": parse_email_addresses(msg.get("To", "")),
            "cc": parse_email_addresses(msg.get("Cc", "")),
            "bcc": parse_email_addresses(msg.get("Bcc", "")),
            "subject": decode_header_value(msg.get("Subject", "")),
            "body_plain": get_plain_text_body(msg),
            "attachments": attachments,
            "in_reply_to": msg.get("In-Reply-To", "").strip() if msg.get("In-Reply-To") else None,
            "references": parse_references(msg),
        }

        emails.append(email_record)

    mbox.close()

    print(f"  Completed: {len(emails)} emails, {total_attachments} attachments")

    return {
        "source_file": mbox_path.name,
        "source_path": str(mbox_path.absolute()),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "total_emails": len(emails),
        "total_attachments": total_attachments,
        "date_range": {
            "earliest": earliest_date,
            "latest": latest_date
        },
        "emails": emails
    }


def parse_multiple_mbox_files(mbox_paths: list[Path], output_dir: Path) -> dict:
    """Parse multiple MBOX files into a single master JSON."""

    all_emails = []
    file_summaries = []
    total_attachments = 0
    earliest_date = None
    latest_date = None

    for mbox_path in mbox_paths:
        result = parse_mbox_file(mbox_path, output_dir)

        if "error" in result:
            file_summaries.append({
                "file": mbox_path.name,
                "error": result["error"]
            })
            continue

        # Add source file reference to each email
        for email_rec in result["emails"]:
            email_rec["source_file"] = mbox_path.name

        all_emails.extend(result["emails"])
        total_attachments += result["total_attachments"]

        # Track overall date range
        file_earliest = result["date_range"]["earliest"]
        file_latest = result["date_range"]["latest"]

        if file_earliest:
            if earliest_date is None or file_earliest < earliest_date:
                earliest_date = file_earliest
        if file_latest:
            if latest_date is None or file_latest > latest_date:
                latest_date = file_latest

        file_summaries.append({
            "file": mbox_path.name,
            "email_count": result["total_emails"],
            "attachment_count": result["total_attachments"],
            "date_range": result["date_range"]
        })

    # Sort all emails by date for timeline analysis
    all_emails.sort(key=lambda x: x["date"] or "")

    # Re-index after sorting
    for i, email_rec in enumerate(all_emails):
        email_rec["index"] = i

    return {
        "metadata": {
            "parser_version": "1.0.0",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "total_emails": len(all_emails),
            "total_attachments": total_attachments,
            "date_range": {
                "earliest": earliest_date,
                "latest": latest_date
            },
            "source_files": file_summaries
        },
        "emails": all_emails
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parse MBOX files to JSON for litigation support and AI analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s inbox.mbox
  %(prog)s inbox.mbox sent.mbox archive.mbox -o ./parsed_emails
  %(prog)s *.mbox --output-dir ./litigation_data

Output Structure:
  output_dir/
  ├── master.json          # All emails with metadata
  ├── attachments/
  │   ├── msg_000001/      # Attachments from first email
  │   │   └── document.pdf
  │   └── msg_000042/
  │       └── image.png
        """
    )

    parser.add_argument(
        "mbox_files",
        nargs="+",
        type=Path,
        help="One or more MBOX files to parse"
    )

    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("./mbox_output"),
        help="Output directory for JSON and attachments (default: ./mbox_output)"
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: True)"
    )

    parser.add_argument(
        "--no-pretty",
        action="store_false",
        dest="pretty",
        help="Compact JSON output"
    )

    args = parser.parse_args()

    # Validate input files
    for mbox_file in args.mbox_files:
        if not mbox_file.exists():
            print(f"Error: File not found: {mbox_file}")
            return 1

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("MBOX to JSON Parser - Litigation Support Edition")
    print(f"{'='*60}\n")
    print(f"Input files: {len(args.mbox_files)}")
    print(f"Output directory: {args.output_dir.absolute()}\n")

    # Parse files
    if len(args.mbox_files) == 1:
        result = parse_mbox_file(args.mbox_files[0], args.output_dir)
        result = {
            "metadata": {
                "parser_version": "1.0.0",
                "parsed_at": result.get("parsed_at", datetime.now(timezone.utc).isoformat()),
                "total_emails": result.get("total_emails", 0),
                "total_attachments": result.get("total_attachments", 0),
                "date_range": result.get("date_range", {}),
                "source_files": [{
                    "file": result.get("source_file", ""),
                    "email_count": result.get("total_emails", 0),
                    "attachment_count": result.get("total_attachments", 0),
                    "date_range": result.get("date_range", {})
                }]
            },
            "emails": result.get("emails", [])
        }
    else:
        result = parse_multiple_mbox_files(args.mbox_files, args.output_dir)

    # Write output
    output_file = args.output_dir / "master.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        if args.pretty:
            json.dump(result, f, indent=2, ensure_ascii=False)
        else:
            json.dump(result, f, ensure_ascii=False)

    print(f"\n{'='*60}")
    print("PARSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total emails:      {result['metadata']['total_emails']}")
    print(f"Total attachments: {result['metadata']['total_attachments']}")
    print(f"Date range:        {result['metadata']['date_range']['earliest'] or 'N/A'}")
    print(f"               to  {result['metadata']['date_range']['latest'] or 'N/A'}")
    print(f"\nOutput file: {output_file.absolute()}")
    print(f"Attachments: {args.output_dir.absolute()}/attachments/")
    print()

    return 0


if __name__ == "__main__":
    exit(main())
