#!/usr/bin/env python3
"""
AWS IAM to OCI IAM Policy Translator
Automatically translates AWS IAM policies to OCI IAM policy statements.
"""

import json
import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set, Any, Optional
from dataclasses import dataclass, field


@dataclass
class TranslationResult:
    """Result of translating an AWS policy statement to OCI."""
    oci_statements: List[str]
    prerequisites: Dict[str, List[Dict[str, str]]] = field(default_factory=lambda: {
        'groups': [],
        'compartments': [],
        'network_sources': [],
        'dynamic_groups': []
    })
    gaps: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ServiceMapper:
    """Maps AWS services to OCI resource types."""
    
    # Service name mappings
    SERVICE_MAP = {
        'ec2': {
            'base': 'compute',
            'resources': {
                'instance': 'instances',
                'image': 'instance-images',
                'volume': 'volumes',
                'snapshot': 'volume-backups',
                '*': 'instances'
            }
        },
        's3': {
            'base': 'object-storage',
            'resources': {
                'bucket': 'buckets',
                'object': 'objects',
                '*': 'buckets'
            }
        },
        'rds': {
            'base': 'database',
            'resources': {
                'db': 'db-systems',
                'snapshot': 'db-backups',
                '*': 'database-family'
            }
        },
        'dynamodb': {
            'base': 'nosql',
            'resources': {
                'table': 'nosql-tables',
                'stream': 'nosql-rows',
                '*': 'nosql-family'
            }
        },
        'lambda': {
            'base': 'fn',
            'resources': {
                'function': 'fn-function',
                '*': 'fn-function'
            }
        },
        'iam': {
            'base': 'identity',
            'resources': {
                'user': 'users',
                'group': 'groups',
                'role': 'dynamic-groups',
                'policy': 'policies',
                '*': 'users'
            }
        },
        'kms': {
            'base': 'kms',
            'resources': {
                'key': 'keys',
                'alias': 'keys',
                '*': 'keys'
            }
        },
        'vpc': {
            'base': 'networking',
            'resources': {
                'vpc': 'vcns',
                'subnet': 'subnets',
                'security-group': 'security-lists',
                'route-table': 'route-tables',
                'internet-gateway': 'internet-gateways',
                '*': 'virtual-network-family'
            }
        },
        'logs': {
            'base': 'logging',
            'resources': {
                '*': 'log-groups'
            }
        }
    }
    
    @classmethod
    def get_oci_resource_type(cls, aws_service: str, resource_type: str = '*') -> str:
        """Get OCI resource type from AWS service and resource."""
        service_info = cls.SERVICE_MAP.get(aws_service.lower())
        if not service_info:
            return f"<UNKNOWN-SERVICE:{aws_service}>"
        
        return service_info['resources'].get(resource_type, service_info['resources']['*'])
    
    @classmethod
    def get_oci_service(cls, aws_service: str) -> str:
        """Get OCI service name from AWS service."""
        service_info = cls.SERVICE_MAP.get(aws_service.lower())
        return service_info['base'] if service_info else f"<UNKNOWN:{aws_service}>"


class ActionAnalyzer:
    """Analyzes AWS actions to determine OCI verbs."""
    
    # Action pattern to verb mappings
    ACTION_PATTERNS = {
        # inspect - metadata only
        'inspect': [
            r'^Describe.*',
            r'^List.*',
            r'^Get.*Status$',
            r'^Get.*Attribute$',
        ],
        # read - view + download
        'read': [
            r'^Get.*',
            r'^Download.*',
            r'^Read.*',
        ],
        # use - limited modifications
        'use': [
            r'^Start.*',
            r'^Stop.*',
            r'^Reboot.*',
            r'^Restart.*',
            r'^.*Item$',  # DynamoDB PutItem, UpdateItem
            r'^Put.*',  # Some Put operations
            r'^Update.*Item$',
        ],
        # manage - full control
        'manage': [
            r'^Create.*',
            r'^Delete.*',
            r'^Update.*',
            r'^Modify.*',
            r'^.*\*$',  # Wildcard actions
        ]
    }
    
    # Special cases that override pattern matching
    SPECIAL_CASES = {
        # EC2
        'ec2:TerminateInstances': 'manage',
        'ec2:RunInstances': 'manage',
        'ec2:StartInstances': 'use',
        'ec2:StopInstances': 'use',
        'ec2:RebootInstances': 'use',
        
        # S3
        's3:PutObject': 'manage',
        's3:DeleteObject': 'manage',
        's3:GetObject': 'read',
        's3:ListBucket': 'inspect',
        
        # DynamoDB
        'dynamodb:PutItem': 'use',
        'dynamodb:UpdateItem': 'use',
        'dynamodb:DeleteItem': 'use',
        'dynamodb:GetItem': 'read',
        'dynamodb:Query': 'read',
        'dynamodb:Scan': 'read',
        
        # IAM
        'iam:PassRole': 'use',  # Requires dynamic group in OCI
        'iam:AddUserToGroup': 'use',
        'iam:RemoveUserFromGroup': 'use',
        
        # Lambda
        'lambda:InvokeFunction': 'use',
    }
    
    @classmethod
    def determine_verb(cls, actions: List[str]) -> Tuple[str, List[str]]:
        """
        Determine the OCI verb needed for a list of AWS actions.
        Returns (verb, warnings).
        """
        if not actions:
            return 'inspect', []
        
        warnings = []
        verb_scores = {'inspect': 0, 'read': 0, 'use': 0, 'manage': 0}
        verb_order = ['inspect', 'read', 'use', 'manage']
        
        for action in actions:
            # Check special cases first
            if action in cls.SPECIAL_CASES:
                verb = cls.SPECIAL_CASES[action]
                verb_index = verb_order.index(verb)
            else:
                # Pattern matching
                verb_index = 0
                for i, verb in enumerate(verb_order):
                    patterns = cls.ACTION_PATTERNS.get(verb, [])
                    action_name = action.split(':')[-1] if ':' in action else action
                    
                    for pattern in patterns:
                        if re.match(pattern, action_name):
                            verb_index = max(verb_index, i)
                            break
            
            verb_scores[verb_order[verb_index]] += 1
        
        # Return the highest privilege verb needed
        for verb in reversed(verb_order):
            if verb_scores[verb] > 0:
                if verb == 'manage' and verb_scores['manage'] < len(actions):
                    warnings.append(
                        f"Some actions require 'manage', which grants full control. "
                        f"Consider splitting policy for finer-grained access."
                    )
                return verb, warnings
        
        return 'inspect', warnings


class ConditionTranslator:
    """Translates AWS IAM conditions to OCI conditions."""
    
    # AWS condition operators to OCI
    OPERATOR_MAP = {
        'StringEquals': '=',
        'StringNotEquals': '!=',
        'StringLike': '=',  # Limited wildcard support
        'NumericEquals': '=',
        'NumericNotEquals': '!=',
        'Bool': '=',
        'IpAddress': 'network-source',
        'NotIpAddress': 'network-source',  # Will invert in translation
        'DateEquals': 'time-based',
    }
    
    # AWS context keys to OCI variables
    CONTEXT_KEY_MAP = {
        'aws:username': 'request.user.name',
        'aws:userid': 'request.user.id',
        'aws:ResourceTag/': 'target.resource.tag.',
        'aws:RequestedRegion': 'request.region',
        'aws:CurrentTime': 'request.utc-timestamp',
        'aws:SourceIp': 'request.networkSource.name',
        'ec2:ResourceTag/': 'target.resource.tag.',
        's3:ResourceTag/': 'target.resource.tag.',
    }
    
    # Unsupported conditions
    UNSUPPORTED = {
        'aws:MultiFactorAuthPresent': 'MFA enforcement - handle via IdP and group segregation',
        'aws:MultiFactorAuthAge': 'MFA age checking - not supported in OCI',
        'aws:SourceVpc': 'VPC source restriction - use service gateway routing',
        'aws:SourceVpce': 'VPC endpoint restriction - not supported',
        'aws:SecureTransport': 'HTTPS enforcement - always enabled in OCI',
        's3:x-amz-server-side-encryption': 'S3 encryption headers - set at bucket level',
        'ec2:InstanceType': 'Instance type restriction - not supported',
    }
    
    @classmethod
    def translate_conditions(cls, conditions: Dict[str, Any], 
                           result: TranslationResult) -> List[str]:
        """
        Translate AWS conditions to OCI where clauses.
        Returns list of OCI condition strings.
        """
        oci_conditions = []
        
        for operator, condition_block in conditions.items():
            for key, value in condition_block.items():
                # Check if unsupported
                if key in cls.UNSUPPORTED:
                    result.gaps.append({
                        'feature': f"Condition: {key}",
                        'severity': 'HIGH' if 'MFA' in key else 'MEDIUM',
                        'impact': cls.UNSUPPORTED[key],
                        'workaround': cls._get_workaround(key)
                    })
                    continue
                
                # Handle IP address conditions
                if operator in ['IpAddress', 'NotIpAddress']:
                    network_source_name = cls._handle_ip_condition(value, result)
                    if operator == 'NotIpAddress':
                        result.gaps.append({
                            'feature': 'NotIpAddress condition',
                            'severity': 'MEDIUM',
                            'impact': 'OCI cannot negate network sources',
                            'workaround': 'Define allowed IPs as network source (inverted logic)'
                        })
                        # Note: In OCI, we can't negate, so this becomes allow from these IPs
                        oci_conditions.append(
                            f"request.networkSource.name = '{network_source_name}'"
                        )
                    else:
                        oci_conditions.append(
                            f"request.networkSource.name = '{network_source_name}'"
                        )
                    continue
                
                # Handle tag-based conditions
                if 'ResourceTag/' in key:
                    tag_key = key.split('ResourceTag/')[-1]
                    oci_key = f"target.resource.tag.{tag_key}"
                    
                    # Handle ${aws:username} variable substitution
                    if isinstance(value, str) and '${aws:username}' in value:
                        oci_value = 'request.user.name'
                        oci_conditions.append(f"{oci_key} = {oci_value}")
                    else:
                        oci_conditions.append(f"{oci_key} = '{value}'")
                    continue
                
                # Handle other mapped conditions
                for aws_prefix, oci_prefix in cls.CONTEXT_KEY_MAP.items():
                    if key.startswith(aws_prefix):
                        if '/' in aws_prefix:
                            # Handle tag keys
                            tag_key = key.replace(aws_prefix, '')
                            oci_key = f"{oci_prefix}{tag_key}"
                        else:
                            oci_key = oci_prefix
                        
                        oci_op = cls.OPERATOR_MAP.get(operator, '=')
                        if isinstance(value, list):
                            # Multiple values - use 'any' clause
                            value_clause = ', '.join([f"{oci_key} = '{v}'" for v in value])
                            oci_conditions.append(f"any {{{value_clause}}}")
                        else:
                            oci_conditions.append(f"{oci_key} {oci_op} '{value}'")
                        break
        
        return oci_conditions
    
    @classmethod
    def _handle_ip_condition(cls, ip_values: Any, result: TranslationResult) -> str:
        """Handle IP address conditions by creating network source."""
        if isinstance(ip_values, str):
            ip_values = [ip_values]
        
        # Generate network source name
        network_source_name = 'allowed-ips-' + '-'.join(
            v.replace('/', '-').replace('.', '-')[:20] for v in ip_values[:2]
        )
        
        result.prerequisites['network_sources'].append({
            'name': network_source_name,
            'cidr_blocks': ip_values,
            'command': f"oci network-firewall network-source create --name {network_source_name} "
                      f"--public-source-list '{json.dumps(ip_values)}'"
        })
        
        return network_source_name
    
    @classmethod
    def _get_workaround(cls, unsupported_key: str) -> str:
        """Get workaround suggestion for unsupported condition."""
        workarounds = {
            'aws:MultiFactorAuthPresent': 'Create separate group for MFA-verified users and enforce MFA at IdP level',
            'aws:MultiFactorAuthAge': 'Configure session timeout at IdP level',
            'aws:SourceVpc': 'Use service gateway and route table restrictions',
            'aws:SourceVpce': 'Use service gateway configuration',
            's3:x-amz-server-side-encryption': 'Set encryption policy at bucket level during bucket creation',
            'ec2:InstanceType': 'Use compartments to segregate workloads by type',
        }
        return workarounds.get(unsupported_key, 'Manual review required')


class ResourceParser:
    """Parses AWS resource ARNs to extract compartment info."""
    
    @classmethod
    def parse_arn(cls, arn: str) -> Dict[str, str]:
        """
        Parse AWS ARN to extract useful information.
        ARN format: arn:aws:service:region:account:resource
        """
        if arn == '*':
            return {'compartment': '<COMPARTMENT_NAME>', 'resource_filter': None}
        
        try:
            parts = arn.split(':')
            if len(parts) < 6:
                return {'compartment': '<COMPARTMENT_NAME>', 'resource_filter': None}
            
            service = parts[2]
            region = parts[3] or 'all-regions'
            account = parts[4]
            resource = ':'.join(parts[5:])
            
            # Extract resource name/pattern if available
            resource_filter = None
            if '/' in resource:
                resource_parts = resource.split('/')
                if len(resource_parts) > 1 and resource_parts[-1] not in ['*', '']:
                    resource_filter = resource_parts[-1]
            
            # Use region as compartment hint
            compartment = region if region and region != '*' else '<COMPARTMENT_NAME>'
            
            return {
                'compartment': compartment,
                'resource_filter': resource_filter,
                'service': service
            }
        except Exception:
            return {'compartment': '<COMPARTMENT_NAME>', 'resource_filter': None}
    
    @classmethod
    def extract_bucket_name(cls, arn: str) -> Optional[str]:
        """Extract bucket name from S3 ARN."""
        if 'arn:aws:s3:::' in arn:
            # arn:aws:s3:::bucket-name or arn:aws:s3:::bucket-name/*
            bucket_part = arn.replace('arn:aws:s3:::', '')
            return bucket_part.split('/')[0] if '/' in bucket_part else bucket_part
        return None
    
    @classmethod
    def extract_table_name(cls, arn: str) -> Optional[str]:
        """Extract table name from DynamoDB ARN."""
        if 'table/' in arn:
            parts = arn.split('table/')
            if len(parts) > 1:
                return parts[1].split('/')[0]
        return None


class PolicyTranslator:
    """Main translator class."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.service_mapper = ServiceMapper()
        self.action_analyzer = ActionAnalyzer()
        self.condition_translator = ConditionTranslator()
        self.resource_parser = ResourceParser()
    
    def translate_policy(self, policy: Dict[str, Any]) -> TranslationResult:
        """Translate an AWS IAM policy to OCI policy statements."""
        result = TranslationResult(oci_statements=[], prerequisites={
            'groups': [],
            'compartments': [],
            'network_sources': [],
            'dynamic_groups': []
        }, gaps=[], warnings=[])
        
        statements = policy.get('Statement', [])
        if not isinstance(statements, list):
            statements = [statements]
        
        for stmt in statements:
            self._translate_statement(stmt, result)
        
        return result
    
    def _translate_statement(self, statement: Dict[str, Any], result: TranslationResult):
        """Translate a single AWS IAM statement."""
        effect = statement.get('Effect', 'Allow')
        actions = statement.get('Action', [])
        resources = statement.get('Resource', '*')
        conditions = statement.get('Condition', {})
        
        # Normalize to lists
        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]
        
        # Handle Deny statements
        if effect == 'Deny':
            result.gaps.append({
                'feature': 'Deny statement',
                'severity': 'HIGH',
                'impact': 'OCI has limited Deny support',
                'workaround': 'Use group segregation or inverted Allow statements'
            })
            result.warnings.append(
                "Deny statement detected. OCI handles Deny differently - review output carefully."
            )
        
        # Group actions by service
        service_actions = self._group_actions_by_service(actions)
        
        # Translate each service's actions
        for service, svc_actions in service_actions.items():
            self._translate_service_actions(
                service, svc_actions, resources, conditions, result
            )
    
    def _group_actions_by_service(self, actions: List[str]) -> Dict[str, List[str]]:
        """Group actions by AWS service."""
        service_actions = {}
        
        for action in actions:
            # Handle wildcard action "*" 
            if action == '*':
                service = '*'
                action_name = '*'
            elif ':' in action:
                service, action_name = action.split(':', 1)
            else:
                service = 'unknown'
                action_name = action
            
            if service not in service_actions:
                service_actions[service] = []
            service_actions[service].append(action)
        
        return service_actions
    
    def _translate_service_actions(self, service: str, actions: List[str],
                                   resources: List[str], conditions: Dict[str, Any],
                                   result: TranslationResult):
        """Translate actions for a specific service."""
        # Handle wildcard service/action
        if service == '*' or actions == ['*']:
            oci_resource_type = 'all-resources'
            verb = 'manage'
            result.warnings.append(
                "Wildcard action '*' detected - translating to 'manage all-resources'. "
                "Consider using more specific permissions."
            )
        else:
            # Determine OCI verb
            verb, warnings = self.action_analyzer.determine_verb(actions)
            result.warnings.extend(warnings)
            
            # Get OCI resource type
            oci_resource_type = self.service_mapper.get_oci_resource_type(service)
        
        # Parse resources for compartment info
        compartments = set()
        resource_filters = []
        
        for resource in resources:
            parsed = self.resource_parser.parse_arn(resource)
            compartments.add(parsed['compartment'])
            
            # Handle service-specific resource filters
            if service == 's3':
                bucket_name = self.resource_parser.extract_bucket_name(resource)
                if bucket_name and bucket_name != '*':
                    resource_filters.append(f"target.bucket.name = '{bucket_name}'")
            elif service == 'dynamodb':
                table_name = self.resource_parser.extract_table_name(resource)
                if table_name:
                    resource_filters.append(f"target.nosql-table.name = '{table_name}'")
        
        # Translate conditions
        oci_conditions = self.condition_translator.translate_conditions(conditions, result)
        
        # Combine resource filters and conditions
        all_conditions = resource_filters + oci_conditions
        
        # Handle special cases
        if service == 's3':
            self._handle_s3_special_case(actions, compartments, all_conditions, result)
        elif service == 'iam' and 'iam:PassRole' in actions:
            self._handle_passrole(result)
        else:
            # Generate standard OCI policy statement
            self._generate_oci_statement(
                verb, oci_resource_type, compartments, all_conditions, result
            )
    
    def _handle_s3_special_case(self, actions: List[str], compartments: Set[str],
                                conditions: List[str], result: TranslationResult):
        """Handle S3 special case - separate bucket and object statements."""
        bucket_actions = [a for a in actions if 'Bucket' in a or a == 's3:*']
        object_actions = [a for a in actions if 'Object' in a or a == 's3:*']
        
        if bucket_actions:
            verb, _ = self.action_analyzer.determine_verb(bucket_actions)
            self._generate_oci_statement(
                verb, 'buckets', compartments, conditions, result
            )
        
        if object_actions:
            verb, _ = self.action_analyzer.determine_verb(object_actions)
            self._generate_oci_statement(
                verb, 'objects', compartments, conditions, result
            )
    
    def _handle_passrole(self, result: TranslationResult):
        """Handle IAM PassRole - requires dynamic group in OCI."""
        result.gaps.append({
            'feature': 'iam:PassRole',
            'severity': 'MEDIUM',
            'impact': 'PassRole requires dynamic groups in OCI',
            'workaround': 'Create dynamic group matching the service resources'
        })
        result.warnings.append(
            "iam:PassRole detected. In OCI, create a dynamic group for the service "
            "and grant permissions to that dynamic group instead."
        )
    
    def _generate_oci_statement(self, verb: str, resource_type: str,
                               compartments: Set[str], conditions: List[str],
                               result: TranslationResult):
        """Generate OCI policy statement."""
        group_name = '<GROUP_NAME>'
        
        # Add group to prerequisites
        if not any(g['name'] == group_name for g in result.prerequisites['groups']):
            result.prerequisites['groups'].append({
                'name': group_name,
                'description': 'Group for this policy - update with actual group name'
            })
        
        for compartment in compartments:
            # Add compartment to prerequisites
            if compartment != '<COMPARTMENT_NAME>':
                if not any(c['name'] == compartment for c in result.prerequisites['compartments']):
                    result.prerequisites['compartments'].append({
                        'name': compartment,
                        'description': 'Compartment inferred from AWS resource ARN'
                    })
            
            # Build statement
            statement = f"Allow group {group_name} to {verb} {resource_type} in compartment {compartment}"
            
            if conditions:
                conditions_str = ' AND '.join(conditions)
                statement += f" where {conditions_str}"
            
            result.oci_statements.append(statement)


def main():
    parser = argparse.ArgumentParser(
        description='Translate AWS IAM policies to OCI IAM policy statements',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic translation
  python translator.py sample-policies/01-ec2-full-access-with-mfa.json
  
  # Verbose mode with translation reasoning
  python translator.py -v sample-policies/05-ec2-tag-based-access.json
  
  # Save output to file
  python translator.py sample-policies/01-ec2-full-access-with-mfa.json -o output.txt
"""
    )
    
    parser.add_argument('policy_file', help='Path to AWS IAM policy JSON file')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Show translation reasoning')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    
    args = parser.parse_args()
    
    # Load AWS policy
    try:
        with open(args.policy_file, 'r') as f:
            aws_policy = json.load(f)
    except FileNotFoundError:
        print(f"Error: Policy file not found: {args.policy_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in policy file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Translate
    translator = PolicyTranslator(verbose=args.verbose)
    result = translator.translate_policy(aws_policy)
    
    # Format output
    if args.json:
        output = json.dumps({
            'oci_statements': result.oci_statements,
            'prerequisites': result.prerequisites,
            'gaps': result.gaps,
            'warnings': result.warnings
        }, indent=2)
    else:
        output = format_output(result, args.verbose, Path(args.policy_file).name)
    
    # Write output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Translation written to: {args.output}")
    else:
        print(output)


def format_output(result: TranslationResult, verbose: bool, policy_name: str) -> str:
    """Format translation result as human-readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"OCI IAM Policy Translation")
    lines.append(f"Source: {policy_name}")
    lines.append("=" * 80)
    lines.append("")
    
    # OCI Policy Statements
    lines.append("OCI POLICY STATEMENTS:")
    lines.append("-" * 80)
    for i, stmt in enumerate(result.oci_statements, 1):
        lines.append(f"{i}. {stmt}")
    lines.append("")
    
    # Prerequisites
    if any(result.prerequisites.values()):
        lines.append("PREREQUISITES:")
        lines.append("-" * 80)
        
        if result.prerequisites['groups']:
            lines.append("Groups to create:")
            for group in result.prerequisites['groups']:
                lines.append(f"  - {group['name']}: {group['description']}")
            lines.append("")
        
        if result.prerequisites['compartments']:
            lines.append("Compartments (update with actual OCID or name):")
            for comp in result.prerequisites['compartments']:
                lines.append(f"  - {comp['name']}: {comp['description']}")
            lines.append("")
        
        if result.prerequisites['network_sources']:
            lines.append("Network sources to create:")
            for ns in result.prerequisites['network_sources']:
                lines.append(f"  - {ns['name']}")
                lines.append(f"    CIDR blocks: {', '.join(ns['cidr_blocks'])}")
                lines.append(f"    Command: {ns['command']}")
            lines.append("")
    
    # Gaps
    if result.gaps:
        lines.append("TRANSLATION GAPS:")
        lines.append("-" * 80)
        for gap in result.gaps:
            lines.append(f"[{gap['severity']}] {gap['feature']}")
            lines.append(f"  Impact: {gap['impact']}")
            lines.append(f"  Workaround: {gap['workaround']}")
            lines.append("")
    
    # Warnings
    if result.warnings:
        lines.append("WARNINGS:")
        lines.append("-" * 80)
        for warning in result.warnings:
            lines.append(f"⚠ {warning}")
        lines.append("")
    
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
