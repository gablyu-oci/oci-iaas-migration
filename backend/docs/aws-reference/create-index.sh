#!/bin/bash

echo "# AWS IAM Documentation Index" > index.md
echo "" >> index.md
echo "Comprehensive reference documentation for AWS Identity and Access Management (IAM)" >> index.md
echo "" >> index.md
echo "**Last Updated:** $(date -u +"%Y-%m-%d %H:%M UTC")" >> index.md
echo "" >> index.md
echo "Total documents: $(find . -name '*.md' -not -name 'index.md' -not -name 'crawl-report.md' | wc -l)" >> index.md
echo "" >> index.md

for dir in user-guide api-reference cli-reference authorization-reference managed-policies; do
    echo "## $(echo $dir | tr '-' ' ' | sed 's/\b\(.\)/\u\1/g')" >> index.md
    echo "" >> index.md
    count=$(ls -1 $dir/*.md 2>/dev/null | grep -v index.md | wc -l)
    echo "**Documents: $count**" >> index.md
    echo "" >> index.md
    
    for file in $dir/*.md; do
        if [ -f "$file" ] && [ "$(basename $file)" != "index.md" ]; then
            title=$(grep -m1 '^title:' "$file" | sed 's/title: *"\(.*\)"/\1/')
            if [ -z "$title" ]; then
                title=$(grep -m1 '^# ' "$file" | sed 's/^# //')
            fi
            if [ -z "$title" ]; then
                title=$(basename "$file" .md)
            fi
            echo "- **$(basename $file)**: $title" >> index.md
        fi
    done
    echo "" >> index.md
done

echo "---" >> index.md
echo "" >> index.md
echo "## Focus Areas" >> index.md
echo "" >> index.md
echo "This documentation collection prioritizes:" >> index.md
echo "- IAM policy syntax and structure" >> index.md
echo "- Policy elements (Principal, Action, Resource, Condition, Effect)" >> index.md
echo "- Condition operators and context keys" >> index.md
echo "- IAM API operations for policy management" >> index.md
echo "- AWS managed policies" >> index.md
echo "- Resource identifiers and ARN formats" >> index.md
echo "- IAM quotas and limits" >> index.md
