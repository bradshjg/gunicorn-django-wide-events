# noqa INP001 intentionally not a package, part of pytest tests
import pytest

from gunicorn_django_canonical_logs.logfmt import LogFmt


class MockContext:
    def __init__(self, context: dict):
        self._context = context

    def raw_items(self):
        return self._context.items()


def test_logfmt_namespaceing():
    context = MockContext({"namespace_1": {"foo": "bar"}, "namespace_2": {"baz": "qux"}})
    assert LogFmt.format(context) == 'namespace_1_foo="bar" namespace_2_baz="qux"'


def test_logfmt_key_normalization():
    context = MockContext({"namespace with spaces": {"key with spaces": "value"}})
    assert LogFmt.format(context) == 'namespace_with_spaces_key_with_spaces="value"'


def test_context_value_coercion():
    class CustomStr:
        def __str__(self):
            return "custom_str"

    context = MockContext({"p": {"bool": True, "none": None, "custom_str": CustomStr()}})
    assert LogFmt.format(context) == 'p_bool="true" p_none="-" p_custom_str="custom_str"'


@pytest.mark.parametrize(
    ("val", "expected"),
    [
        ("howdy", 'p_k="howdy"'),
        ("howdy\nthere\r", 'p_k="howdy there"'),
        (" howdy     there\tpartner   ", 'p_k="howdy there partner"'),
        ('needs "escaping"', 'p_k="needs \\"escaping\\""'),
        ("", 'p_k="-"'),
    ],
)
def test_value_escaping(val, expected):
    context = MockContext({"p": {"k": val}})
    log = LogFmt.format(context)
    assert log == expected
