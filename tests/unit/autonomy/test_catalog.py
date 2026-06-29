from datasentry.autonomy import BuiltInAutonomyPolicyCatalog


def test_builtin_policy_catalog_defaults_to_disabled_shadow_policies() -> None:
    catalog = BuiltInAutonomyPolicyCatalog()

    policies = catalog.list_policies()

    assert [policy.runbook_name for policy in policies] == [
        "mock.restart_preview",
        "mock.clear_cache_preview",
    ]
    assert all(policy.enabled is False for policy in policies)
    assert all(policy.shadow_mode is True for policy in policies)


def test_builtin_policy_catalog_returns_copy() -> None:
    catalog = BuiltInAutonomyPolicyCatalog()

    policy = catalog.get("mock.restart_preview")
    policy = policy.model_copy(update={"enabled": True})

    assert policy.enabled is True
    assert catalog.get("mock.restart_preview").enabled is False
