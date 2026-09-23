import pytest

from nascommon.bridge.json_extract import extract_json, first_balanced_object


def test_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_fenced_with_commentary():
    text = 'Here you go:\n```json\n{"final": {"x": "a } b"}}\n```\nHope this helps.'
    assert extract_json(text) == {"final": {"x": "a } b"}}


def test_balanced_ignores_braces_in_strings():
    assert first_balanced_object('x {"s": "}{", "n": {"m": 1}} y') == '{"s": "}{", "n": {"m": 1}}'


def test_no_object():
    with pytest.raises(ValueError):
        extract_json("just prose")


def test_a_json_array_or_scalar_is_not_an_object():
    """The callers all want an object; a bare list is a different shape, not a near miss."""
    with pytest.raises(ValueError):
        extract_json("[1, 2, 3]")
    with pytest.raises(ValueError):
        extract_json('"just a string"')


def test_escapes_inside_strings_do_not_end_the_object_early():
    text = r'prefix {"quote": "he said \"hi\"", "brace": "}", "path": "a\\b"} suffix'
    assert extract_json(text) == {"quote": 'he said "hi"', "brace": "}", "path": "a\\b"}


def test_an_unclosed_object_yields_nothing():
    assert first_balanced_object('{"a": 1') is None
    assert first_balanced_object('{"a": "unterminated') is None
    with pytest.raises(ValueError):
        extract_json('{"a": 1')


def test_the_first_complete_object_wins():
    assert first_balanced_object('{"a": 1} {"b": 2}') == '{"a": 1}'
    assert extract_json('noise {"a": 1} more {"b": 2}') == {"a": 1}


def test_a_fence_containing_something_unparseable_falls_back_to_the_braces():
    text = 'talk ```json\nnot json at all\n``` but also {"a": 1}'
    assert extract_json(text) == {"a": 1}
