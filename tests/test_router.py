from dataclasses import replace
from threading import Event

import pytest

from app.engine.backends.base_backend import BaseBackend
from app.engine.errors import DeviceUnavailableError, ModelMissingError, TranslationCancelledError, TranslationError
from app.engine.router.translation_router import TranslationRouter
from app.engine.runtime.device_manager import DeviceManager
from app.engine.types import (BackendCapabilities, BackendOutput, DevicePreference, InferenceOptions,
                              PairKind, PerformanceProfile, TranslationRequest)


class FakeBackend(BaseBackend):
    def __init__(self, name, pairs=(), pivots=(), languages=()):
        self.name = name
        self.caps = BackendCapabilities(frozenset(pairs), frozenset(pivots), frozenset(languages))
        self.calls = []
        self.fail = set()
        self.loaded = False
        self.loads = 0
        self.unloads = 0

    def capabilities(self):
        return self.caps

    def translate(self, request, kind, options, cancelled):
        self.calls.append((request, kind, options))
        if options.device in self.fail:
            raise TranslationError("synthetic failure")
        if not self.loaded:
            self.loads += 1
            self.loaded = True
        return BackendOutput("Переведено", (f"{self.name}-test",))

    def shutdown(self):
        self.unloads += self.loaded
        self.loaded = False


class FakeDevices(DeviceManager):
    def __init__(self, gpu=True):
        self.gpu = gpu
        self.gpu_checks = 0

    def gpu_available(self):
        self.gpu_checks += 1
        return self.gpu

    def options(self, device, policy):
        return (InferenceOptions(device, "int8", policy.threads, policy.beam_size,
                                 policy.batch_tokens, policy.max_input_tokens, policy.max_decoding_length),)


@pytest.fixture
def router():
    argos = FakeBackend("argos", [("en", "ru"), ("ru", "en")], [("zh", "ru"), ("ru", "zh")])
    m2m = FakeBackend("m2m100", languages=["en", "ru", "zh"])
    engine = TranslationRouter({"argos": argos, "m2m100": m2m}, devices=FakeDevices())
    yield engine
    engine.shutdown()


def request(source="en", target="ru", profile=PerformanceProfile.BALANCED, device=DevicePreference.CPU):
    return TranslationRequest("Technical sample.", source, target, device, profile)


@pytest.mark.parametrize("source,target,profile,backend", [
    ("en", "ru", PerformanceProfile.BALANCED, "argos"),
    ("ru", "en", PerformanceProfile.AUTOMATIC, "argos"),
    ("zh", "ru", PerformanceProfile.BALANCED, "m2m100"),
    ("zh", "ru", PerformanceProfile.MAXIMUM, "m2m100"),
    ("ru", "zh", PerformanceProfile.AUTOMATIC, "m2m100"),
    ("zh", "ru", PerformanceProfile.FAST, "m2m100"),
    ("en", "ru", PerformanceProfile.MAXIMUM, "argos"),
    ("ru", "en", PerformanceProfile.MAXIMUM, "argos"),
    ("zh", "ru", PerformanceProfile.ECONOMY, "argos"),
])
def test_routes(router, source, target, profile, backend):
    decision = router.decide(request(source, target, profile))
    assert decision.backend == backend
    result = router.translate(request(source, target, profile))
    assert result.backend == backend


def test_quality_precedes_pivot_even_when_direct_argos_exists(router):
    router.backends["argos"].caps = BackendCapabilities(direct_pairs=frozenset({("zh", "ru")}),
                                                       pivot_pairs=frozenset({("zh", "ru")}))
    decision = router.decide(request("zh", "ru"))
    assert decision.backend == "m2m100"
    assert [item.kind for item in decision.fallback_chain] == [PairKind.DIRECT, PairKind.PIVOT]


def test_missing_quality_backend_uses_pivot(router):
    router.backends["m2m100"].caps = BackendCapabilities()
    result = router.translate(request("zh", "ru"))
    assert result.backend == "argos"
    assert router.backends["argos"].calls[-1][1] == PairKind.PIVOT


def test_backend_failure_uses_next_backend_without_changing_explicit_device(router):
    router.backends["argos"].fail.add("cpu")
    result = router.translate(request())
    assert result.backend == "m2m100"
    assert result.fallback_used and result.device == "cpu"
    assert router.devices.gpu_checks == 0


def test_explicit_gpu_is_never_cpu(router):
    router.devices.gpu = False
    with pytest.raises(DeviceUnavailableError):
        router.translate(request(device=DevicePreference.GPU))
    assert not any(b.calls for b in router.backends.values())


def test_explicit_gpu_failure_never_switches_to_cpu(router):
    for backend in router.backends.values():
        backend.fail.add("cuda")
    with pytest.raises(TranslationError):
        router.translate(request(device=DevicePreference.GPU))
    assert all(call[2].device == "cuda" for backend in router.backends.values() for call in backend.calls)


def test_auto_gpu_failure_uses_cpu(router):
    router.backends["argos"].fail.add("cuda")
    result = router.translate(request(device=DevicePreference.AUTO))
    assert result.backend == "argos" and result.device == "cpu" and result.fallback_used


def test_economy_auto_cpu_but_explicit_gpu_takes_precedence(router):
    assert router.translate(request(profile=PerformanceProfile.ECONOMY, device=DevicePreference.AUTO)).device == "cpu"
    assert router.translate(request(profile=PerformanceProfile.ECONOMY, device=DevicePreference.GPU)).device == "cuda"


def test_passthrough_needs_no_capabilities_or_device(router, monkeypatch):
    monkeypatch.setattr(router, "_capabilities", lambda: pytest.fail("passthrough initialized a backend"))
    result = router.translate(request("ru", "ru", device=DevicePreference.GPU))
    assert result.translated_text == "Technical sample."
    assert result.backend == "passthrough"


def test_cancel_never_falls_back(router):
    event = Event()
    event.set()
    with pytest.raises(TranslationCancelledError):
        router.translate(request(), event)
    assert not any(b.calls for b in router.backends.values())


def test_metrics_and_logs_do_not_contain_user_content(router, caplog):
    text = "PRIVATE_SECRET_123"
    router.backends["argos"].fail.add("cpu")
    router.translate(replace(request(), text=text))
    assert text not in caplog.text
    assert text not in repr(router.metrics)
    assert [metric.success for metric in router.metrics] == [False, True]


def test_backend_only_benchmark_does_not_measure_fallback_backend(router):
    router.backends["argos"].fail.add("cpu")
    with pytest.raises(TranslationError):
        router.translate(request(), backend_only="argos")
    assert not router.backends["m2m100"].calls
