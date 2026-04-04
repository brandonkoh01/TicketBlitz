import os
import pathlib
import sys
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

# Ensure shared/ can be imported by expiry_scheduler.py during test execution.
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import expiry_scheduler

SEED_EVENT_ID = "10000000-0000-0000-0000-000000000301"
SEED_HOLD_ID = "40000000-0000-0000-0000-000000000003"
SEED_SEAT_ID = "30000000-0000-0000-0000-000000000013"
SEED_USER_ID = "00000000-0000-0000-0000-000000000001"


class _FakeResponse:
    def __init__(self, status_code=200, json_payload=None, text="", json_error=None):
        self.status_code = status_code
        self._json_payload = json_payload
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_payload


class _FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.closed = False

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response

    def close(self):
        self.closed = True


class ExpirySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.original_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def _config(self):
        return expiry_scheduler.SchedulerConfig(
            service_name="expiry-scheduler-service",
            inventory_service_url="http://inventory-service:5000",
            maintenance_path="/inventory/maintenance/expire-holds",
            expiry_interval_seconds=60,
            error_retry_delay_seconds=2,
            error_retry_jitter_seconds=0.5,
            request_connect_timeout_seconds=1.0,
            request_read_timeout_seconds=2.0,
            retry_total=0,
            retry_backoff_factor=0.0,
            internal_auth_header="X-Internal-Token",
            internal_service_token="",
        )

    def test_validate_http_url_strips_trailing_slash(self):
        self.assertEqual(
            expiry_scheduler.validate_http_url("INVENTORY_SERVICE_URL", "http://example.com/"),
            "http://example.com",
        )

    def test_validate_http_url_rejects_non_http_scheme(self):
        with self.assertRaises(ValueError):
            expiry_scheduler.validate_http_url("INVENTORY_SERVICE_URL", "ftp://example.com")

    def test_from_env_applies_defaults_and_normalization(self):
        os.environ["INVENTORY_SERVICE_URL"] = "http://inventory-service:5000/"
        os.environ["INVENTORY_EXPIRE_HOLDS_PATH"] = "inventory/maintenance/expire-holds"
        os.environ["EXPIRY_INTERVAL_SECONDS"] = "0"
        os.environ["EXPIRY_ERROR_RETRY_DELAY_SECONDS"] = "bad"

        config = expiry_scheduler.SchedulerConfig.from_env()

        self.assertEqual(config.inventory_service_url, "http://inventory-service:5000")
        self.assertEqual(config.maintenance_path, "/inventory/maintenance/expire-holds")
        self.assertEqual(config.expiry_interval_seconds, 1)
        self.assertEqual(config.error_retry_delay_seconds, 5)

    def test_from_env_rejects_blank_auth_header_when_token_present(self):
        os.environ["INTERNAL_SERVICE_TOKEN"] = "secret"
        os.environ["INTERNAL_AUTH_HEADER"] = "   "

        with self.assertRaises(ValueError):
            expiry_scheduler.SchedulerConfig.from_env()

    def test_from_env_rejects_invalid_inventory_service_url(self):
        os.environ["INVENTORY_SERVICE_URL"] = "inventory-service:5000"

        with self.assertRaises(ValueError):
            expiry_scheduler.SchedulerConfig.from_env()

    def test_from_env_non_finite_timeout_uses_default(self):
        os.environ["EXPIRY_REQUEST_CONNECT_TIMEOUT_SECONDS"] = "nan"
        config = expiry_scheduler.SchedulerConfig.from_env()
        self.assertEqual(config.request_connect_timeout_seconds, 3.05)

    def test_from_env_blank_inventory_service_url_uses_default(self):
        os.environ["INVENTORY_SERVICE_URL"] = "   "

        config = expiry_scheduler.SchedulerConfig.from_env()

        self.assertEqual(config.inventory_service_url, "http://inventory-service:5000")

    def test_from_env_negative_jitter_is_clamped_to_zero(self):
        os.environ["EXPIRY_ERROR_RETRY_JITTER_SECONDS"] = "-2"

        config = expiry_scheduler.SchedulerConfig.from_env()

        self.assertEqual(config.error_retry_jitter_seconds, 0.0)

    def test_maintenance_url_uses_config_values(self):
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=_FakeSession())
        self.assertEqual(
            scheduler.maintenance_url,
            "http://inventory-service:5000/inventory/maintenance/expire-holds",
        )

    def test_run_once_success(self):
        session = _FakeSession(
            response=_FakeResponse(
                status_code=200,
                json_payload={
                    "count": 2,
                    "expiredHolds": [
                        {"holdID": "H-001"},
                        {"holdID": "H-002"},
                    ],
                },
            )
        )
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertTrue(success)
        self.assertIsNotNone(scheduler.last_success_at)
        self.assertEqual(len(session.calls), 1)

    def test_run_once_adds_internal_auth_header_when_token_present(self):
        cfg = replace(self._config(), internal_service_token="secret-token")
        session = _FakeSession(response=_FakeResponse(status_code=200, json_payload={"count": 0}))
        scheduler = expiry_scheduler.ExpiryScheduler(cfg, session=session)

        success = scheduler.run_once()

        self.assertTrue(success)
        _args, kwargs = session.calls[0]
        self.assertEqual(kwargs["headers"]["X-Internal-Token"], "secret-token")

    def test_run_once_sends_expected_payload_headers_and_timeouts(self):
        session = _FakeSession(response=_FakeResponse(status_code=200, json_payload={"count": 0}))
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertTrue(success)
        _args, kwargs = session.calls[0]
        self.assertEqual(kwargs["json"], {})
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["timeout"], (1.0, 2.0))

    def test_run_once_handles_seed_like_expired_hold_payload(self):
        session = _FakeSession(
            response=_FakeResponse(
                status_code=200,
                json_payload={
                    "count": 1,
                    "publishFailures": 0,
                    "expiredHolds": [
                        {
                            "holdID": SEED_HOLD_ID,
                            "seatID": SEED_SEAT_ID,
                            "eventID": SEED_EVENT_ID,
                            "seatCategory": "CAT1",
                            "userID": SEED_USER_ID,
                        }
                    ],
                },
            )
        )
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertTrue(success)

    def test_run_once_non_200(self):
        session = _FakeSession(response=_FakeResponse(status_code=503, text="service unavailable"))
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertFalse(success)

    def test_run_once_non_object_payload(self):
        session = _FakeSession(response=_FakeResponse(status_code=200, json_payload=[]))
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertFalse(success)

    def test_run_once_count_falls_back_to_expired_holds_length(self):
        session = _FakeSession(
            response=_FakeResponse(
                status_code=200,
                json_payload={
                    "count": "invalid",
                    "expiredHolds": [{"holdID": "H-001"}, {"holdID": "H-002"}],
                },
            )
        )
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertTrue(success)

    def test_run_once_non_list_expired_holds_defaults_count_to_zero(self):
        session = _FakeSession(
            response=_FakeResponse(
                status_code=200,
                json_payload={
                    "count": "invalid",
                    "expiredHolds": {"holdID": SEED_HOLD_ID},
                },
            )
        )
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertTrue(success)

    def test_run_once_invalid_publish_failures_treated_as_zero(self):
        session = _FakeSession(
            response=_FakeResponse(
                status_code=200,
                json_payload={
                    "count": 1,
                    "publishFailures": "invalid",
                    "expiredHolds": [{"holdID": SEED_HOLD_ID}],
                },
            )
        )
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertTrue(success)
        self.assertIsNotNone(scheduler.last_success_at)

    def test_run_once_returns_false_when_publish_failures_present(self):
        session = _FakeSession(
            response=_FakeResponse(
                status_code=200,
                json_payload={
                    "count": 1,
                    "expiredHolds": [{"holdID": "H-001"}],
                    "publishFailures": 1,
                    "publishFailureHoldIDs": ["H-001"],
                },
            )
        )
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertFalse(success)
        self.assertIsNone(scheduler.last_success_at)

    def test_run_once_returns_false_when_publish_failure_hold_ids_is_not_list(self):
        session = _FakeSession(
            response=_FakeResponse(
                status_code=200,
                json_payload={
                    "count": 1,
                    "publishFailures": 1,
                    "publishFailureHoldIDs": "not-a-list",
                    "expiredHolds": [{"holdID": SEED_HOLD_ID}],
                },
            )
        )
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertFalse(success)

    def test_run_once_invalid_json(self):
        session = _FakeSession(response=_FakeResponse(status_code=200, json_error=ValueError("bad json")))
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertFalse(success)

    def test_run_once_request_exception(self):
        session = _FakeSession(error=expiry_scheduler.RequestException("boom"))
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        success = scheduler.run_once()

        self.assertFalse(success)

    def test_run_forever_stops_when_shutdown_requested(self):
        sleep_calls = []

        def sleeper(seconds):
            sleep_calls.append(seconds)
            scheduler.request_shutdown()

        session = _FakeSession(response=_FakeResponse(status_code=200, json_payload={"count": 0}))
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session, sleeper=sleeper)

        scheduler.run_forever()

        self.assertGreaterEqual(len(session.calls), 1)
        self.assertGreaterEqual(len(sleep_calls), 1)

    def test_sleep_interruptibly_stops_when_shutdown_requested(self):
        sleep_calls = []

        def sleeper(seconds):
            sleep_calls.append(seconds)
            scheduler.request_shutdown()

        scheduler = expiry_scheduler.ExpiryScheduler(
            self._config(),
            session=_FakeSession(response=_FakeResponse(status_code=200, json_payload={"count": 0})),
            sleeper=sleeper,
        )

        scheduler._sleep_interruptibly(4.0)

        self.assertEqual(len(sleep_calls), 1)
        self.assertEqual(sleep_calls[0], 1.0)

    def test_run_forever_applies_failure_jitter(self):
        sleep_calls = []

        def sleeper(seconds):
            sleep_calls.append(seconds)
            if sum(sleep_calls) >= 2.3:
                scheduler.request_shutdown()

        def jitterer(_start, _end):
            return 0.4

        cfg = replace(self._config(), error_retry_delay_seconds=2, error_retry_jitter_seconds=0.4)
        session = _FakeSession(response=_FakeResponse(status_code=503, text="service unavailable"))
        scheduler = expiry_scheduler.ExpiryScheduler(
            cfg,
            session=session,
            sleeper=sleeper,
            jitterer=jitterer,
        )

        scheduler.run_forever()

        self.assertTrue(sleep_calls)
        self.assertGreaterEqual(sum(sleep_calls), 2.3)

    def test_run_forever_handles_unhandled_run_once_exception(self):
        sleep_calls = []

        def sleeper(seconds):
            sleep_calls.append(seconds)
            if sum(sleep_calls) >= 2.0:
                scheduler.request_shutdown()

        cfg = replace(self._config(), error_retry_delay_seconds=2, error_retry_jitter_seconds=0.0)
        scheduler = expiry_scheduler.ExpiryScheduler(
            cfg,
            session=_FakeSession(response=_FakeResponse(status_code=200, json_payload={"count": 0})),
            sleeper=sleeper,
        )

        def _raise_unhandled_error():
            raise RuntimeError("boom")

        scheduler.run_once = _raise_unhandled_error

        scheduler.run_forever()

        self.assertGreaterEqual(sum(sleep_calls), 2.0)

    def test_install_signal_handlers_registers_sigint_and_sigterm(self):
        scheduler = expiry_scheduler.ExpiryScheduler(
            self._config(),
            session=_FakeSession(response=_FakeResponse(status_code=200, json_payload={"count": 0})),
        )
        registered_handlers = {}

        def fake_signal(signal_number, handler):
            registered_handlers[signal_number] = handler

        with patch("expiry_scheduler.signal.signal", side_effect=fake_signal):
            expiry_scheduler.install_signal_handlers(scheduler)

        self.assertIn(expiry_scheduler.signal.SIGINT, registered_handlers)
        self.assertIn(expiry_scheduler.signal.SIGTERM, registered_handlers)

        registered_handlers[expiry_scheduler.signal.SIGTERM](expiry_scheduler.signal.SIGTERM, None)
        self.assertTrue(scheduler._shutdown_requested)

    def test_main_exits_with_status_one_for_invalid_config(self):
        with patch("expiry_scheduler.SchedulerConfig.from_env", side_effect=ValueError("bad config")):
            with self.assertRaises(SystemExit) as raised:
                expiry_scheduler.main()

        self.assertEqual(raised.exception.code, 1)

    def test_main_closes_scheduler_after_normal_run(self):
        fake_scheduler = MagicMock()

        with (
            patch("expiry_scheduler.SchedulerConfig.from_env", return_value=self._config()),
            patch("expiry_scheduler.ExpiryScheduler", return_value=fake_scheduler),
            patch("expiry_scheduler.install_signal_handlers"),
        ):
            expiry_scheduler.main()

        fake_scheduler.run_forever.assert_called_once()
        fake_scheduler.close.assert_called_once()

    def test_main_closes_scheduler_even_when_run_forever_raises(self):
        fake_scheduler = MagicMock()
        fake_scheduler.run_forever.side_effect = RuntimeError("scheduler failure")

        with (
            patch("expiry_scheduler.SchedulerConfig.from_env", return_value=self._config()),
            patch("expiry_scheduler.ExpiryScheduler", return_value=fake_scheduler),
            patch("expiry_scheduler.install_signal_handlers"),
        ):
            with self.assertRaises(RuntimeError):
                expiry_scheduler.main()

        fake_scheduler.close.assert_called_once()

    def test_build_http_session_configures_retry_for_post(self):
        cfg = replace(self._config(), retry_total=3, retry_backoff_factor=0.2)
        session = expiry_scheduler.build_http_session(cfg)

        try:
            retry = session.adapters["http://"].max_retries
            self.assertEqual(retry.total, 3)
            self.assertIn("POST", retry.allowed_methods)
            self.assertIn(503, retry.status_forcelist)
        finally:
            session.close()

    def test_close_closes_underlying_session(self):
        session = _FakeSession(response=_FakeResponse(status_code=200, json_payload={"count": 0}))
        scheduler = expiry_scheduler.ExpiryScheduler(self._config(), session=session)

        scheduler.close()

        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
