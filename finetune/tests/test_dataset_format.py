import hashlib
import json

from finetune.scripts.generate_dataset import example_to_line


def _expected_id(meta):
    payload = {
        'input_prompt': meta['input_prompt'],
        'plan': meta['plan'],
        'pre_files': meta['pre_files'],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def test_example_to_line_fields():
    meta = {
        'input_prompt': 'Plan the update',
        'plan': {'steps': ['one', 'two']},
        'pre_files': {'a.txt': 'old'},
        'post_files': {'a.txt': 'new'},
        'exec_rc': 0,
        'exec_log': 'ok',
        'labels': {'task_type': 'planning'},
    }
    line = example_to_line(meta, 'reports/run_sample')

    required_keys = [
        'id', 'timestamp', 'source', 'input_prompt', 'plan', 'pre_files',
        'post_files', 'exec_rc', 'exec_log', 'labels',
    ]
    for key in required_keys:
        assert key in line

    assert isinstance(line['plan'], dict)
    assert isinstance(line['labels'], dict)
    assert isinstance(line['pre_files'], dict)
    assert isinstance(line['post_files'], dict)

    assert line['timestamp']
    assert line['source'] == 'reports/run_sample'
    assert line['input_prompt'] == meta['input_prompt']

    assert len(line['id']) == 64
    assert all(ch in '0123456789abcdef' for ch in line['id'])
    assert line['id'] == _expected_id(meta)

    assert line['exec_rc'] == 0
    assert line['pre_files']['a.txt'] == 'old'
    assert line['post_files']['a.txt'] == 'new'
