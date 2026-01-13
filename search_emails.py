#!/usr/bin/env python3
"""
Email Search & Analysis Script for Litigation Support
SRC Recruiting, LLC v. Cognitio Corp. (Florida) — Counsel Brief Support

Implements the query library and produces deliverables:
- Exhibit Index (CSV)
- Timeline Table
- Entity/Privity/Novation Packet
- Diligence Proof Matrix
- Confidentiality Flag List

Usage:
    python3 search_emails.py master.json -o ./analysis_output
"""

import json
import re
import csv
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
from collections import defaultdict


# =============================================================================
# SECTION F: CONTROLLED TAGS
# =============================================================================

CONTROLLED_TAGS = {
    # Motions / Procedure
    "PROCEDURAL_MOTION",
    "SEAL_CONFIDENTIALITY",
    "STRIKE_IMMATERIAL",
    "MORE_DEFINITE_STATEMENT",
    "DISMISS_QUASI_CONTRACT",
    "STRIKE_FEES_DEMAND",
    "JURISDICTION_VENUE",
    # Diligence / Candidate Pattern
    "DILIGENCE_PROCESS",
    "DILIGENCE_GAP_NO_RECORDS",
    "CANDIDATE_RED_FLAG",
    "CANDIDATE_DECLINED",
    "FAILED_HIRE_PERFORMANCE",
    # Dispute Evolution
    "FEE_DISPUTE_DEMAND",
    "NEGOTIATION_SETTLEMENT",
    "INTERNAL_STRATEGY",
    # Entity / Privity / Standing / Assignment
    "ENTITY_CHANGE_REPRESENTATION",
    "PRIVITY_STANDING",
    "ASSIGNMENT_NOVATION_REQUEST",
    "NDA_ASSIGNMENT_NOVATION",
    "INVOICING_ENTITY_MISMATCH",
}


# =============================================================================
# SECTION E: QUERY LIBRARY
# =============================================================================

# Each query pack is a dict with:
#   - "name": human-readable name
#   - "tags": list of tags to apply if matched
#   - "patterns": list of regex patterns (any match triggers)
#   - "required_all": list of patterns that ALL must match (optional)
#   - "priority": search order (lower = higher priority)
#   - "date_range": optional (start, end) ISO date strings to filter

QUERY_PACKS = [
    # -----------------------------------------------------------------
    # E1: Entity Change / Acquisition / Privity / Assignment / Novation
    # -----------------------------------------------------------------
    {
        "name": "Entity Change - Core",
        "tags": ["ENTITY_CHANGE_REPRESENTATION", "PRIVITY_STANDING"],
        "patterns": [
            r'Stanley\s+Reid',
            r'SRC\s+Recruiting',
            r'new\s+entity',
            r'entity\s+change',
            r'change\s+in\s+entity',
            r'different\s+entity',
        ],
        "priority": 1,
    },
    {
        "name": "Entity Change - Acquisition/Merger",
        "tags": ["ENTITY_CHANGE_REPRESENTATION"],
        "patterns": [
            r'acquired',
            r'acquisition',
            r'we\s+acquired',
            r'we\s+bought',
            r'rolled\s+up',
            r'merged',
            r'merger',
            r'rebrand',
            r'now\s+part\s+of',
            r'successor',
            r'successor[\-\s]in[\-\s]interest',
        ],
        "priority": 1,
    },
    {
        "name": "Entity Change - Tax/Onboarding",
        "tags": ["INVOICING_ENTITY_MISMATCH", "ENTITY_CHANGE_REPRESENTATION"],
        "patterns": [
            r'\bEIN\b',
            r'tax\s+ID',
            r'W[\-\s]?9',
            r'vendor\s+setup',
            r'vendor\s+onboarding',
            r'onboarding',
        ],
        "priority": 1,
    },
    {
        "name": "Assignment/Novation - Contract Transfer",
        "tags": ["ASSIGNMENT_NOVATION_REQUEST", "PRIVITY_STANDING"],
        "patterns": [
            r'\bassignment\b',
            r'\bassign\b',
            r'\bassumption\b',
            r'\bassume\b',
            r'\btransfer\b',
            r'novation',
            r'\bconsent\b',
            r'written\s+consent',
            r'counterparty\s+consent',
            r'amendment',
            r'addendum',
            r'restated',
            r'replacement\s+agreement',
        ],
        "priority": 1,
    },
    {
        "name": "NDA Assignment/Novation",
        "tags": ["NDA_ASSIGNMENT_NOVATION"],
        "patterns": [
            r'NDA',
            r'non[\-\s]?disclosure',
            r'confidentiality\s+agreement',
        ],
        "required_any": [
            r'assign',
            r'novation',
            r'new\s+NDA',
            r'supersede',
            r'replace',
        ],
        "priority": 1,
    },
    {
        "name": "Entity Change - Mollie Jan 2023",
        "tags": ["ENTITY_CHANGE_REPRESENTATION", "PRIVITY_STANDING"],
        "patterns": [
            r'mollie|mclaughlin',
        ],
        "required_any": [
            r'entity',
            r'Stanley\s+Reid',
            r'SRC',
            r'acquired',
            r'merger',
        ],
        "date_range": ("2022-10-01", "2023-04-30"),
        "priority": 0,  # Highest priority - known target
    },

    # -----------------------------------------------------------------
    # E2: Confidentiality / Customer Identity / Sensitive References
    # -----------------------------------------------------------------
    {
        "name": "Confidentiality - Agency/IC References",
        "tags": ["SEAL_CONFIDENTIALITY"],
        "patterns": [
            r'\bCIA\b',
            r'Langley',
            r'\bintelligence\b',
            r'\bIC\b',
            r'\bagency\b',
        ],
        "priority": 2,
    },
    {
        "name": "Confidentiality - Customer Identity",
        "tags": ["SEAL_CONFIDENTIALITY"],
        "patterns": [
            r'end\s+customer',
            r'government\s+customer',
            r'customer\s+identity',
            r'client\s+identity',
            r'do\s+not\s+disclose',
            r'confidential',
            r'\bNDA\b',
            r'protected',
            r'sensitive',
        ],
        "priority": 2,
    },
    {
        "name": "Confidentiality - Seal/Protective",
        "tags": ["SEAL_CONFIDENTIALITY", "PROCEDURAL_MOTION"],
        "patterns": [
            r'\bseal\b',
            r'motion\s+to\s+seal',
            r'protective\s+order',
            r'confidential\s+filing',
        ],
        "priority": 2,
    },

    # -----------------------------------------------------------------
    # E3: Diligence Process Evidence
    # -----------------------------------------------------------------
    {
        "name": "Diligence - Process Terms",
        "tags": ["DILIGENCE_PROCESS"],
        "patterns": [
            r'due\s+diligence',
            r'\bdiligence\b',
            r'screening',
            r'vetting',
        ],
        "priority": 3,
    },
    {
        "name": "Diligence - Background/Reference",
        "tags": ["DILIGENCE_PROCESS"],
        "patterns": [
            r'background\s+check',
            r'\bcriminal\b',
            r'\barrest\b',
            r'\bcharge\b',
            r'reference\s+check',
            r'\breferences\b',
            r'verification',
        ],
        "priority": 3,
    },
    {
        "name": "Diligence - Credentials",
        "tags": ["DILIGENCE_PROCESS"],
        "patterns": [
            r'credential',
            r'certification',
            r'\blicense\b',
            r'checklist',
            r'\bSOP\b',
            r'\bpolicy\b',
            r'standard\s+process',
        ],
        "priority": 3,
    },
    {
        "name": "Diligence - Contract Obligation Echo",
        "tags": ["DILIGENCE_PROCESS", "DILIGENCE_GAP_NO_RECORDS"],
        "patterns": [
            r'reviewed\s+profile',
            r'review\s+your\s+profile',
            r'reviewed\s+the\s+profile\s+with\s+the\s+candidate',
            r'within\s+90\s+days',
            r'90[\-\s]?day',
        ],
        "priority": 3,
    },
    {
        "name": "Diligence - Artifacts",
        "tags": ["DILIGENCE_PROCESS"],
        "patterns": [
            r'screening\s+notes',
            r'call\s+notes',
            r'diligence\s+packet',
            r'candidate\s+packet',
        ],
        "priority": 3,
    },

    # -----------------------------------------------------------------
    # E4: Candidate Red Flags / Declines / Failed Hires
    # -----------------------------------------------------------------
    {
        "name": "Candidate - Red Flags",
        "tags": ["CANDIDATE_RED_FLAG"],
        "patterns": [
            r'red\s+flag',
            r'\bconcern\b',
            r'not\s+comfortable',
            r'no[\-\s]?go',
            r'do\s+not\s+submit',
        ],
        "priority": 4,
    },
    {
        "name": "Candidate - Declined/Withdrawn",
        "tags": ["CANDIDATE_DECLINED"],
        "patterns": [
            r'\bdecline\b',
            r'\bpass\b',
            r'\bwithdraw\b',
            r'\bstop\b',
            r'disqualify',
        ],
        "priority": 4,
    },
    {
        "name": "Candidate - Failed Hires",
        "tags": ["FAILED_HIRE_PERFORMANCE"],
        "patterns": [
            r'terminated',
            r'performance\s+issue',
            r'\bcomplaint\b',
            r'investigation',
        ],
        "priority": 4,
    },
    {
        "name": "Candidate - Specific Incidents",
        "tags": ["CANDIDATE_RED_FLAG", "DILIGENCE_GAP_NO_RECORDS"],
        "patterns": [
            r'Taco\s+Bell',
            r'drive[\-\s]?through',
            r'abduction',
            r'kidnap',
            r'kidnapping',
            r'off\s+duty',
            r'state\s+cop',
            r'state\s+trooper',
            r'\bpolice\b',
        ],
        "priority": 4,
    },
    {
        "name": "Candidate - News/Public Records",
        "tags": ["CANDIDATE_RED_FLAG"],
        "patterns": [
            r'\bGoogle\b',
            r'\bnews\b',
            r'\barticle\b',
            r'mugshot',
        ],
        "priority": 4,
    },

    # -----------------------------------------------------------------
    # E5: Fee Dispute / Demand / Negotiation
    # -----------------------------------------------------------------
    {
        "name": "Fee Dispute - Invoice/Fee Terms",
        "tags": ["FEE_DISPUTE_DEMAND"],
        "patterns": [
            r'\binvoice\b',
            r'placement\s+fee',
            r'\bfee\b',
            r'installment',
            r'past\s+due',
            r'late\s+fee',
            r'\binterest\b',
            r'1\.5\s*%',
        ],
        "priority": 5,
    },
    {
        "name": "Fee Dispute - Demand/Settlement",
        "tags": ["FEE_DISPUTE_DEMAND", "NEGOTIATION_SETTLEMENT"],
        "patterns": [
            r'\bdemand\b',
            r'demand\s+letter',
            r'settlement',
            r'\bresolve\b',
        ],
        "priority": 5,
    },
    {
        "name": "Fee Dispute - Breach Claims",
        "tags": ["FEE_DISPUTE_DEMAND"],
        "patterns": [
            r'\bbreach\b',
            r'material\s+breach',
            r'Section\s+2',
        ],
        "priority": 5,
    },
    {
        "name": "Fee Dispute - FRE 408",
        "tags": ["NEGOTIATION_SETTLEMENT", "INTERNAL_STRATEGY"],
        "patterns": [
            r'FRE\s+408',
            r'without\s+prejudice',
        ],
        "priority": 5,
    },

    # -----------------------------------------------------------------
    # E6: Procedural Motion Support Terms
    # -----------------------------------------------------------------
    {
        "name": "Procedural - Quasi Contract",
        "tags": ["DISMISS_QUASI_CONTRACT", "PROCEDURAL_MOTION"],
        "patterns": [
            r'unjust\s+enrichment',
            r'quasi[\-\s]?contract',
        ],
        "priority": 6,
    },
    {
        "name": "Procedural - Attorneys Fees",
        "tags": ["STRIKE_FEES_DEMAND", "PROCEDURAL_MOTION"],
        "patterns": [
            r'attorney[s\']?\s+fees',
        ],
        "required_any": [
            r'\bbasis\b',
            r'entitled',
        ],
        "priority": 6,
    },
    {
        "name": "Procedural - Strike/MDS",
        "tags": ["STRIKE_IMMATERIAL", "MORE_DEFINITE_STATEMENT", "PROCEDURAL_MOTION"],
        "patterns": [
            r'more\s+definite\s+statement',
            r'\bstrike\b',
            r'scandalous',
            r'immaterial',
        ],
        "priority": 6,
    },
    {
        "name": "Procedural - Jurisdiction/Venue",
        "tags": ["JURISDICTION_VENUE", "PROCEDURAL_MOTION"],
        "patterns": [
            r'jurisdiction',
            r'\bvenue\b',
            r'Manatee',
            r'Florida\s+complaint',
            r'\bsummons\b',
        ],
        "priority": 6,
    },
]


# =============================================================================
# SEARCH ENGINE
# =============================================================================

def compile_patterns(patterns: list) -> list:
    """Compile regex patterns for efficiency."""
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def email_matches_query(email: dict, query: dict, compiled_patterns: dict) -> tuple[bool, list]:
    """
    Check if an email matches a query pack.
    Returns (matched, excerpts).
    """
    # Build searchable text
    searchable_parts = [
        email.get('subject', ''),
        email.get('body_plain', ''),
    ]

    # Add sender/recipient names and emails
    if email.get('from'):
        searchable_parts.append(email['from'].get('name', ''))
        searchable_parts.append(email['from'].get('email', ''))

    for field in ['to', 'cc', 'bcc']:
        for addr in email.get(field, []):
            searchable_parts.append(addr.get('name', ''))
            searchable_parts.append(addr.get('email', ''))

    searchable_text = ' '.join(searchable_parts)

    # Check date range if specified
    if 'date_range' in query:
        start, end = query['date_range']
        email_date = email.get('date', '')
        if email_date:
            if start and email_date < start:
                return False, []
            if end and email_date > end:
                return False, []

    # Get compiled patterns
    query_name = query['name']
    patterns = compiled_patterns.get(query_name, [])

    # Check main patterns (any match)
    main_matched = False
    excerpts = []

    for pattern in patterns:
        match = pattern.search(searchable_text)
        if match:
            main_matched = True
            # Extract excerpt with context
            start = max(0, match.start() - 50)
            end = min(len(searchable_text), match.end() + 50)
            excerpt = searchable_text[start:end].strip()
            if len(excerpt) > 150:
                excerpt = excerpt[:147] + "..."
            excerpts.append(excerpt)

    if not main_matched:
        return False, []

    # Check required_any patterns if specified
    if 'required_any' in query:
        req_patterns = compiled_patterns.get(f"{query_name}_required_any", [])
        if req_patterns:
            any_req_matched = False
            for pattern in req_patterns:
                if pattern.search(searchable_text):
                    any_req_matched = True
                    break
            if not any_req_matched:
                return False, []

    # Check required_all patterns if specified
    if 'required_all' in query:
        req_patterns = compiled_patterns.get(f"{query_name}_required_all", [])
        for pattern in req_patterns:
            if not pattern.search(searchable_text):
                return False, []

    return True, excerpts[:3]  # Limit to 3 excerpts


def run_search(emails: list, queries: list) -> dict:
    """
    Run all queries against all emails.
    Returns dict mapping email index to (tags, excerpts, query_names).
    """
    # Pre-compile all patterns
    compiled_patterns = {}
    for query in queries:
        compiled_patterns[query['name']] = compile_patterns(query.get('patterns', []))
        if 'required_any' in query:
            compiled_patterns[f"{query['name']}_required_any"] = compile_patterns(query['required_any'])
        if 'required_all' in query:
            compiled_patterns[f"{query['name']}_required_all"] = compile_patterns(query['required_all'])

    # Sort queries by priority
    sorted_queries = sorted(queries, key=lambda q: q.get('priority', 99))

    results = {}

    for i, email in enumerate(emails):
        if i % 500 == 0:
            print(f"  Searching email {i}...")

        email_tags = set()
        email_excerpts = []
        matched_queries = []

        for query in sorted_queries:
            matched, excerpts = email_matches_query(email, query, compiled_patterns)
            if matched:
                email_tags.update(query.get('tags', []))
                email_excerpts.extend(excerpts)
                matched_queries.append(query['name'])

        if email_tags:
            results[i] = {
                'tags': list(email_tags),
                'excerpts': email_excerpts[:5],  # Limit total excerpts
                'matched_queries': matched_queries,
            }

    return results


# =============================================================================
# DELIVERABLE GENERATORS
# =============================================================================

def generate_exhibit_index(emails: list, search_results: dict, output_path: Path):
    """Generate G1: Exhibit Index as CSV."""
    kept_emails = []

    for idx, result in search_results.items():
        email = emails[idx]
        kept_emails.append({
            'index': idx,
            'email': email,
            'tags': result['tags'],
            'excerpts': result['excerpts'],
            'matched_queries': result['matched_queries'],
        })

    # Sort by date
    kept_emails.sort(key=lambda x: x['email'].get('date', '') or '')

    # Assign exhibit IDs
    for i, item in enumerate(kept_emails):
        item['exhibit_id'] = f"E-{i+1:03d}"

    # Write CSV
    csv_path = output_path / "exhibit_index.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Exhibit_ID',
            'Message_ID',
            'Custodian',
            'Date',
            'From_Name',
            'From_Email',
            'To',
            'CC',
            'Subject',
            'Tags',
            'Matched_Queries',
            'Excerpt_1',
            'Excerpt_2',
            'Brief_Section',
        ])

        for item in kept_emails:
            email = item['email']

            # Determine brief section
            tags = set(item['tags'])
            if tags & {'SEAL_CONFIDENTIALITY', 'STRIKE_IMMATERIAL', 'MORE_DEFINITE_STATEMENT',
                       'DISMISS_QUASI_CONTRACT', 'STRIKE_FEES_DEMAND', 'PROCEDURAL_MOTION'}:
                brief_section = "1-Motion/Confidentiality"
            elif tags & {'ENTITY_CHANGE_REPRESENTATION', 'PRIVITY_STANDING',
                         'ASSIGNMENT_NOVATION_REQUEST', 'NDA_ASSIGNMENT_NOVATION', 'INVOICING_ENTITY_MISMATCH'}:
                brief_section = "2-Entity/Privity"
            elif tags & {'DILIGENCE_PROCESS', 'DILIGENCE_GAP_NO_RECORDS'}:
                brief_section = "3-Diligence"
            elif tags & {'CANDIDATE_RED_FLAG', 'CANDIDATE_DECLINED', 'FAILED_HIRE_PERFORMANCE'}:
                brief_section = "4-Candidate Pattern"
            elif tags & {'FEE_DISPUTE_DEMAND', 'NEGOTIATION_SETTLEMENT', 'INTERNAL_STRATEGY'}:
                brief_section = "5-Fee Dispute"
            else:
                brief_section = "Other"

            # Format recipients
            to_str = "; ".join([f"{a.get('name', '')} <{a.get('email', '')}>" for a in email.get('to', [])])
            cc_str = "; ".join([f"{a.get('name', '')} <{a.get('email', '')}>" for a in email.get('cc', [])])

            from_addr = email.get('from', {}) or {}

            excerpts = item['excerpts']

            writer.writerow([
                item['exhibit_id'],
                email.get('message_id', ''),
                email.get('custodian', ''),
                email.get('date', ''),
                from_addr.get('name', ''),
                from_addr.get('email', ''),
                to_str[:200],
                cc_str[:200],
                email.get('subject', '')[:200],
                "; ".join(item['tags']),
                "; ".join(item['matched_queries']),
                excerpts[0] if len(excerpts) > 0 else '',
                excerpts[1] if len(excerpts) > 1 else '',
                brief_section,
            ])

    print(f"  Exhibit Index: {csv_path}")
    return kept_emails


def generate_timeline_table(kept_emails: list, output_path: Path):
    """Generate G2: Timeline Table as CSV."""
    csv_path = output_path / "timeline_table.csv"

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Event', 'Exhibit_ID', 'Message_ID', 'Tags', 'Relevance_Note'])

        for item in kept_emails:
            email = item['email']

            # Generate event description
            from_addr = email.get('from', {}) or {}
            sender = from_addr.get('name') or from_addr.get('email', 'Unknown')
            subject = email.get('subject', 'No subject')[:80]

            event = f"{sender}: {subject}"

            writer.writerow([
                email.get('date', ''),
                event,
                item['exhibit_id'],
                email.get('message_id', ''),
                "; ".join(item['tags']),
                item['excerpts'][0] if item['excerpts'] else '',
            ])

    print(f"  Timeline Table: {csv_path}")


def generate_entity_privity_packet(kept_emails: list, output_path: Path):
    """Generate G3: Entity/Privity/Novation Packet."""
    entity_tags = {
        'ENTITY_CHANGE_REPRESENTATION',
        'PRIVITY_STANDING',
        'ASSIGNMENT_NOVATION_REQUEST',
        'NDA_ASSIGNMENT_NOVATION',
        'INVOICING_ENTITY_MISMATCH',
    }

    # Filter to entity-related emails
    entity_emails = [e for e in kept_emails if set(e['tags']) & entity_tags]

    md_path = output_path / "entity_privity_packet.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# Entity/Privity/Novation Packet\n\n")
        f.write("## SRC Recruiting, LLC v. Cognitio Corp.\n\n")
        f.write("---\n\n")

        f.write("## Timeline of Entity-Related Communications\n\n")
        f.write("| Date | From | Subject | Tags | Exhibit |\n")
        f.write("|------|------|---------|------|--------|\n")

        for item in entity_emails[:20]:  # Top 20
            email = item['email']
            from_addr = email.get('from', {}) or {}
            sender = from_addr.get('name') or from_addr.get('email', '')
            f.write(f"| {email.get('date', '')[:10]} | {sender[:30]} | {email.get('subject', '')[:50]} | {', '.join(item['tags'][:3])} | {item['exhibit_id']} |\n")

        f.write("\n---\n\n")
        f.write("## Key Threads\n\n")

        for i, item in enumerate(entity_emails[:15]):
            email = item['email']
            from_addr = email.get('from', {}) or {}

            f.write(f"### {item['exhibit_id']}: {email.get('subject', 'No subject')[:60]}\n\n")
            f.write(f"**Date:** {email.get('date', '')}\n\n")
            f.write(f"**From:** {from_addr.get('name', '')} <{from_addr.get('email', '')}>\n\n")
            f.write(f"**Tags:** {', '.join(item['tags'])}\n\n")

            if item['excerpts']:
                f.write("**Key Excerpts:**\n\n")
                for excerpt in item['excerpts'][:2]:
                    f.write(f"> {excerpt}\n\n")

            f.write("---\n\n")

        # Gap statement
        f.write("## Gap Analysis\n\n")

        novation_found = any('ASSIGNMENT_NOVATION_REQUEST' in e['tags'] for e in entity_emails)
        nda_novation_found = any('NDA_ASSIGNMENT_NOVATION' in e['tags'] for e in entity_emails)

        if not novation_found:
            f.write("- **No explicit novation/assignment request found** in searched records.\n")
        if not nda_novation_found:
            f.write("- **No NDA assignment/novation request found** in searched records.\n")

        f.write(f"\n*Total entity-related emails found: {len(entity_emails)}*\n")

    print(f"  Entity/Privity Packet: {md_path}")


def generate_diligence_matrix(kept_emails: list, output_path: Path):
    """Generate G4: Diligence Proof Matrix."""
    diligence_tags = {
        'DILIGENCE_PROCESS',
        'DILIGENCE_GAP_NO_RECORDS',
        'CANDIDATE_RED_FLAG',
        'CANDIDATE_DECLINED',
        'FAILED_HIRE_PERFORMANCE',
    }

    diligence_emails = [e for e in kept_emails if set(e['tags']) & diligence_tags]

    csv_path = output_path / "diligence_matrix.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Exhibit_ID',
            'Date',
            'Subject',
            'Diligence_Tags',
            'Candidate_Tags',
            'Key_Excerpt',
            'Artifacts_Referenced',
        ])

        for item in diligence_emails:
            email = item['email']
            tags = set(item['tags'])

            diligence_t = tags & {'DILIGENCE_PROCESS', 'DILIGENCE_GAP_NO_RECORDS'}
            candidate_t = tags & {'CANDIDATE_RED_FLAG', 'CANDIDATE_DECLINED', 'FAILED_HIRE_PERFORMANCE'}

            # Check for artifact references in attachments
            artifacts = []
            for att in email.get('attachments', []):
                doc_types = att.get('doc_types', [])
                if any(t in doc_types for t in ['resume', 'background_check', 'reference']):
                    artifacts.append(f"{att.get('filename', '')} ({', '.join(doc_types)})")

            writer.writerow([
                item['exhibit_id'],
                email.get('date', ''),
                email.get('subject', '')[:100],
                "; ".join(diligence_t),
                "; ".join(candidate_t),
                item['excerpts'][0] if item['excerpts'] else '',
                "; ".join(artifacts) if artifacts else 'None found',
            ])

    print(f"  Diligence Matrix: {csv_path}")


def generate_confidentiality_flags(kept_emails: list, output_path: Path):
    """Generate G5: Confidentiality Flag List."""
    conf_tags = {'SEAL_CONFIDENTIALITY'}

    conf_emails = [e for e in kept_emails if set(e['tags']) & conf_tags]

    csv_path = output_path / "confidentiality_flags.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Exhibit_ID',
            'Date',
            'Subject',
            'Sensitive_Excerpt',
            'Review_Action',
        ])

        for item in conf_emails:
            email = item['email']

            writer.writerow([
                item['exhibit_id'],
                email.get('date', ''),
                email.get('subject', '')[:100],
                item['excerpts'][0] if item['excerpts'] else '',
                'REVIEW FOR SEAL/PROTECTIVE ORDER',
            ])

    print(f"  Confidentiality Flags: {csv_path}")


def generate_summary_report(emails: list, search_results: dict, kept_emails: list, output_path: Path):
    """Generate summary statistics report."""
    md_path = output_path / "search_summary.md"

    # Count tags
    tag_counts = defaultdict(int)
    for result in search_results.values():
        for tag in result['tags']:
            tag_counts[tag] += 1

    # Count by brief section
    section_counts = defaultdict(int)
    for item in kept_emails:
        tags = set(item['tags'])
        if tags & {'SEAL_CONFIDENTIALITY', 'STRIKE_IMMATERIAL', 'MORE_DEFINITE_STATEMENT',
                   'DISMISS_QUASI_CONTRACT', 'STRIKE_FEES_DEMAND', 'PROCEDURAL_MOTION'}:
            section_counts['1-Motion/Confidentiality'] += 1
        if tags & {'ENTITY_CHANGE_REPRESENTATION', 'PRIVITY_STANDING',
                   'ASSIGNMENT_NOVATION_REQUEST', 'NDA_ASSIGNMENT_NOVATION', 'INVOICING_ENTITY_MISMATCH'}:
            section_counts['2-Entity/Privity'] += 1
        if tags & {'DILIGENCE_PROCESS', 'DILIGENCE_GAP_NO_RECORDS'}:
            section_counts['3-Diligence'] += 1
        if tags & {'CANDIDATE_RED_FLAG', 'CANDIDATE_DECLINED', 'FAILED_HIRE_PERFORMANCE'}:
            section_counts['4-Candidate Pattern'] += 1
        if tags & {'FEE_DISPUTE_DEMAND', 'NEGOTIATION_SETTLEMENT', 'INTERNAL_STRATEGY'}:
            section_counts['5-Fee Dispute'] += 1

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# Search Analysis Summary\n\n")
        f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")
        f.write("---\n\n")

        f.write("## Overview\n\n")
        f.write(f"- **Total emails searched:** {len(emails)}\n")
        f.write(f"- **Emails matched (kept):** {len(search_results)}\n")
        f.write(f"- **Match rate:** {len(search_results)/len(emails)*100:.1f}%\n\n")

        f.write("## Results by Brief Section\n\n")
        f.write("| Section | Count |\n")
        f.write("|---------|-------|\n")
        for section in sorted(section_counts.keys()):
            f.write(f"| {section} | {section_counts[section]} |\n")

        f.write("\n## Results by Tag\n\n")
        f.write("| Tag | Count |\n")
        f.write("|-----|-------|\n")
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
            f.write(f"| {tag} | {count} |\n")

        f.write("\n---\n\n")
        f.write("## Validation Checklist\n\n")

        # Check for key items
        mollie_entity = any(
            'mollie' in ' '.join(r.get('matched_queries', [])).lower()
            and 'ENTITY_CHANGE_REPRESENTATION' in r['tags']
            for r in search_results.values()
        )
        f.write(f"- [{'x' if mollie_entity else ' '}] Mollie entity-change email found\n")

        w9_found = any('INVOICING_ENTITY_MISMATCH' in r['tags'] for r in search_results.values())
        f.write(f"- [{'x' if w9_found else ' '}] W-9/vendor onboarding/invoice mismatch found\n")

        novation_found = any('ASSIGNMENT_NOVATION_REQUEST' in r['tags'] for r in search_results.values())
        f.write(f"- [{'x' if novation_found else ' '}] Novation/assignment request found\n")

        nda_found = any('NDA_ASSIGNMENT_NOVATION' in r['tags'] for r in search_results.values())
        f.write(f"- [{'x' if nda_found else ' '}] NDA assignment/novation found\n")

        diligence_gaps = sum(1 for r in search_results.values() if 'DILIGENCE_GAP_NO_RECORDS' in r['tags'])
        f.write(f"- [{'x' if diligence_gaps >= 3 else ' '}] 3+ diligence gap threads found ({diligence_gaps} found)\n")

    print(f"  Summary Report: {md_path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Search parsed emails for litigation support evidence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Outputs:
  exhibit_index.csv        - All matched emails with tags and excerpts
  timeline_table.csv       - Chronological event list
  entity_privity_packet.md - Entity/novation analysis
  diligence_matrix.csv     - Diligence evidence matrix
  confidentiality_flags.csv - Items needing seal/protective review
  search_summary.md        - Statistics and validation checklist
        """
    )

    parser.add_argument(
        "master_json",
        type=Path,
        help="Path to master.json from mbox_parser.py"
    )

    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("./search_output"),
        help="Output directory for analysis files (default: ./search_output)"
    )

    args = parser.parse_args()

    if not args.master_json.exists():
        print(f"Error: File not found: {args.master_json}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("Email Search & Analysis - Litigation Support")
    print("SRC Recruiting, LLC v. Cognitio Corp.")
    print(f"{'='*60}\n")

    # Load data
    print("Loading parsed emails...")
    with open(args.master_json, 'r', encoding='utf-8') as f:
        data = json.load(f)

    emails = data.get('emails', [])
    print(f"  Loaded {len(emails)} emails\n")

    # Run search
    print("Running search queries...")
    search_results = run_search(emails, QUERY_PACKS)
    print(f"  Found {len(search_results)} matching emails\n")

    # Generate deliverables
    print("Generating deliverables...")
    kept_emails = generate_exhibit_index(emails, search_results, args.output_dir)
    generate_timeline_table(kept_emails, args.output_dir)
    generate_entity_privity_packet(kept_emails, args.output_dir)
    generate_diligence_matrix(kept_emails, args.output_dir)
    generate_confidentiality_flags(kept_emails, args.output_dir)
    generate_summary_report(emails, search_results, kept_emails, args.output_dir)

    print(f"\n{'='*60}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"Output directory: {args.output_dir.absolute()}")
    print()

    return 0


if __name__ == "__main__":
    exit(main())
