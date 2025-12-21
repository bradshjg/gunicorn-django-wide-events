# noqa INP001 intentionally not a package, part of pytest tests
import shutil
import traceback

import pytest

from gunicorn_django_canonical_logs.stack_context import get_stack_loc_context


class CustomError(Exception):
    pass


def func_that_throws_directly():
    raise CustomError


def func_that_throws_from_library():
    shutil.copy("non-existent-source", "non-existent-destination")


def test_app_code_is_cause_if_app_code_throws_directly():
    with pytest.raises(CustomError) as e:
        func_that_throws_directly()
    context = get_stack_loc_context(traceback.extract_tb(e.tb))

    assert "test_app_code_is_cause_if_app_code_throws_directly" in context["loc"]
    assert "func_that_throws_directly" in context["cause_loc"]


def test_app_code_is_cause_if_app_code_throws_from_library():
    with pytest.raises(FileNotFoundError) as e:
        func_that_throws_from_library()
    context = get_stack_loc_context(traceback.extract_tb(e.tb))

    assert "test_app_code_is_cause_if_app_code_throws_from_library" in context["loc"]
    assert "func_that_throws_from_library" in context["cause_loc"]


def test_library_code_is_cause_if_no_app_code_in_stack():
    with pytest.raises(FileNotFoundError) as e:
        shutil.copy("non-existent-source", "non-existent-destination")
    context = get_stack_loc_context(traceback.extract_tb(e.tb))

    assert "test_library_code_is_cause_if_no_app_code_in_stack" in context["loc"]
    assert "shutil.py" in context["cause_loc"]
