from authorization_in_the_middle.logging_context import (
    authz_outcome_log_extra,
    set_authz_outcome_log_extra,
)


def test_authz_outcome_log_extra_round_trip():
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context("/"):
        assert authz_outcome_log_extra() == {}
        set_authz_outcome_log_extra(
            rate_limit="60 per minute",
            tenant_uuid="tenant-1",
            tenant_type=None,
        )
        assert authz_outcome_log_extra() == {
            "rate_limit": "60 per minute",
            "tenant_uuid": "tenant-1",
        }
