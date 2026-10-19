"""Upgrade only the known stock culture metadata snapshot, without paid retries."""
import hashlib
import json
from pathlib import Path

LEGACY_METADATA_SHA256 = '4b6911066f67a21dadc967e6e17532abbc4ca05dc455a5cdd523443de35a10ba'


def metadata_prompt(prompt, template, track, root):
    selected = template.get('id') == 'culture-knowledge' or (
        not template.get('id') and track == 'culture-knowledge')
    if not selected or not isinstance(prompt, str):
        return prompt
    normalized = prompt.replace('\r\n', '\n').strip()
    if hashlib.sha256(normalized.encode('utf8')).hexdigest() != LEGACY_METADATA_SHA256:
        # A user edit or a different template is an intentional snapshot.
        return prompt
    templates = json.loads((Path(root) / 'assets/prompt_templates.json').read_text('utf8'))
    current = next((t.get('step1MetadataSystemPrompt') for t in templates if t.get('id') == 'culture-knowledge'), None)
    if not isinstance(current, str) or not current.strip():
        raise ValueError('传统文化标题模板无法读取，请检查内置模板')
    return current
