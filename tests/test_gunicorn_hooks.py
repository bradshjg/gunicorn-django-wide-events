# noqa INP001 intentionally not a package, part of pytest tests
from gunicorn_django_canonical_logs.gunicorn_hooks.registry import Hook, HookRegistry, hook_registry, register_hook


def test_valid_hook_registration():
    local_hook_registry = HookRegistry()

    @register_hook(registry=local_hook_registry)
    def when_ready():
        pass

    assert local_hook_registry[Hook.WHEN_READY.value] == {when_ready.__wrapped__}


def test_global_registration():
    hook_registry.reset()

    @register_hook(registry=hook_registry)
    def when_ready():
        pass

    assert hook_registry[Hook.WHEN_READY.value] == {when_ready.__wrapped__}


def test_global_registration_reset():
    hook_registry.reset()

    @register_hook(registry=hook_registry)
    def when_ready():
        pass

    assert hook_registry[Hook.WHEN_READY.value] == {when_ready.__wrapped__}
    hook_registry.reset()
    assert hook_registry[Hook.WHEN_READY.value] == set()


def test_duplicate_registration_is_deduplicated():
    local_hook_registry = HookRegistry()

    def when_ready():
        pass

    register_hook(registry=local_hook_registry)(when_ready)
    register_hook(registry=local_hook_registry)(when_ready)

    assert local_hook_registry[Hook.WHEN_READY.value] == {when_ready}


def test_separate_registrations_result_in_multiple_callbacks():
    local_hook_registry = HookRegistry()

    def first_callback():
        pass

    def second_callback():
        pass

    local_hook_registry.register(hook=Hook.ON_EXIT.value, callback=first_callback)
    local_hook_registry.register(hook=Hook.ON_EXIT.value, callback=second_callback)

    assert local_hook_registry[Hook.ON_EXIT.value] == {first_callback, second_callback}
