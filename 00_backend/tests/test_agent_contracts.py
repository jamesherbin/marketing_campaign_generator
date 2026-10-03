"""004-R3: recursive contracts and JSON interoperability, without model calls."""
import json
from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from campaign import models
from campaign.runner_factory import build_phase_runners
from campaign.config import RunnerMode

# The factory establishes the repository import path without invoking models.
RUNNERS = build_phase_runners(RunnerMode.ADK)
PAIRS = [(phase.value, runner.runner.agent.sub_agents[-1].output_schema, runner.output_model)
         for phase, runner in RUNNERS.items()]

PAYLOADS = {
    'planning': dict(goals=['Awareness'], measurable_objectives=['Reach 100 people'],
        audience_segments=['Builders'], positioning_statement='Built for builders',
        value_proposition='Save time', key_messages=['Build faster'],
        recommended_channels=['email'], budget_by_channel={'email': 1000.5}),
    'development': dict(creative_direction='Simple', assets=[dict(
        asset_id='12345678-1234-4234-8234-123456789abc', channel='email', format='text',
        headline='Hello', body='Try it', call_to_action='Learn more', status='draft')],
        media_plan={'email': {'weeks': [1, 2], 'enabled': True, 'optional': None}}),
    'execution': dict(activities=[dict(channel='email', action='Prepare',
        scheduled_for='2026-10-02T12:30:00Z', status='prepared')], publication_summary='Prepared only'),
    'monitoring': dict(kpis={'missing': None, 'count': 3, 'ratio': 0.5, 'label': 'unavailable'},
        analysis=['No live source'], recommendations=['Connect analytics'], stakeholder_summary='Review'),
}


def normalize_schema(schema):
    """Ignore titles only on schema nodes; preserve property names and defaults."""
    if not isinstance(schema, dict):
        return schema
    normalized = {}
    for key, value in schema.items():
        if key == 'title':
            continue
        if key in {'properties', '$defs', 'patternProperties', 'dependentSchemas'}:
            normalized[key] = {name: normalize_schema(child) for name, child in value.items()}
        elif key in {'items', 'additionalProperties', 'contains', 'not', 'if', 'then', 'else', 'propertyNames'}:
            normalized[key] = normalize_schema(value)
        elif key in {'anyOf', 'allOf', 'oneOf', 'prefixItems'}:
            normalized[key] = [normalize_schema(child) for child in value]
        else:
            normalized[key] = value
    return normalized


@pytest.mark.parametrize('phase,agent,backend', PAIRS, ids=[p[0] for p in PAIRS])
@pytest.mark.parametrize('mode', ['validation', 'serialization'])
def test_synthesizer_schema_matches_backend_recursively(phase, agent, backend, mode):
    assert backend is getattr(models, f'{phase.title()}Output')
    assert normalize_schema(agent.model_json_schema(mode=mode)) == normalize_schema(backend.model_json_schema(mode=mode))


@pytest.mark.parametrize('phase,agent,backend', PAIRS, ids=[p[0] for p in PAIRS])
@pytest.mark.parametrize('reverse', [False, True])
def test_representative_outputs_round_trip_in_both_directions(phase, agent, backend, reverse):
    source, target = (backend, agent) if reverse else (agent, backend)
    value = source.model_validate_json(json.dumps(PAYLOADS[phase]))
    transferred = target.model_validate_json(value.model_dump_json())
    assert transferred.model_dump(mode='json') == value.model_dump(mode='json')
    assert source.model_validate_json(transferred.model_dump_json()) == value


@pytest.mark.parametrize('phase,agent,backend', PAIRS, ids=[p[0] for p in PAIRS])
def test_both_models_reject_missing_required_fields(phase, agent, backend):
    for field in backend.model_fields:
        payload = deepcopy(PAYLOADS[phase])
        del payload[field]
        for model in (agent, backend):
            with pytest.raises(ValidationError):
                model.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize('phase,change', [
    ('planning', {'budget_by_channel': {'email': {'invalid': 1}}}),
    ('development', {'assets': [PAYLOADS['development']['assets'][0] | {'asset_id': 'bad-uuid'}]}),
    ('development', {'assets': [PAYLOADS['development']['assets'][0] | {'body': None}]}),
    ('execution', {'activities': [PAYLOADS['execution']['activities'][0] | {'scheduled_for': 'bad-date'}]}),
    ('execution', {'activities': [{'channel': 'email'}]}),
    ('monitoring', {'kpis': {'clicks': [1, 2]}}),
])
def test_nested_invalid_values_fail_on_both_sides(phase, change):
    _, agent, backend = next(pair for pair in PAIRS if pair[0] == phase)
    for model in (agent, backend):
        with pytest.raises(ValidationError):
            model.model_validate_json(json.dumps(PAYLOADS[phase] | change))


@pytest.mark.parametrize('side', [1, 2], ids=['agent', 'backend'])
def test_omitted_nested_defaults_and_generated_ids(side):
    development = next(pair for pair in PAIRS if pair[0] == 'development')[side]
    payload = deepcopy(PAYLOADS['development'])
    for key in ('asset_id', 'status', 'call_to_action'):
        del payload['assets'][0][key]
    first, second = [development.model_validate(payload) for _ in range(2)]
    assert isinstance(first.assets[0].asset_id, UUID)
    assert first.assets[0].asset_id.version == 4
    assert first.assets[0].asset_id != second.assets[0].asset_id
    assert first.assets[0].status == 'draft'
    assert first.assets[0].call_to_action is None
    other = next(pair for pair in PAIRS if pair[0] == 'development')[3-side]
    assert other.model_validate_json(first.model_dump_json()).model_dump(mode='json') == first.model_dump(mode='json')

    execution = next(pair for pair in PAIRS if pair[0] == 'execution')[side]
    result = execution.model_validate(dict(activities=[dict(channel='email', action='Prepare')], publication_summary='Prepared'))
    assert result.activities[0].scheduled_for is None
    assert result.activities[0].status == 'prepared'
    other = next(pair for pair in PAIRS if pair[0] == 'execution')[3-side]
    assert other.model_validate_json(result.model_dump_json()).model_dump(mode='json') == result.model_dump(mode='json')
