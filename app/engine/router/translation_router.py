from __future__ import annotations

from collections import deque
from dataclasses import replace
import logging
from threading import Event
from time import perf_counter

from app.engine.backends.base_backend import BaseBackend, check_cancelled
from app.engine.errors import (BackendUnavailableError, DeviceUnavailableError, InputTooLongError,
                               ModelMissingError, TranslationCancelledError, TranslationError,
                               UnsupportedLanguageError)
from app.engine.languages import LanguageResolver
from app.engine.router.route_decision import RouteCandidate, RouteDecision
from app.engine.router.routing_policy import RoutingPolicy
from app.engine.runtime.device_manager import DeviceManager
from app.engine.runtime.offline import offline_scope
from app.engine.runtime.runtime_manager import RuntimeManager
from app.engine.types import (BackendCapabilities, PairKind, PerformanceProfile,
                              TranslationMetric, TranslationRequest, TranslationResult)

logger = logging.getLogger("treetranslate.engine")


class TranslationRouter:
    def __init__(self, backends: dict[str, BaseBackend], *, policy: RoutingPolicy | None = None,
                 devices: DeviceManager | None = None, runtime: RuntimeManager | None = None) -> None:
        self.backends = backends
        self.policy = policy or RoutingPolicy()
        self.devices = devices or DeviceManager()
        self.runtime = runtime or RuntimeManager(backends, self.policy.idle_timeout_seconds)
        self.languages = LanguageResolver()
        self.metrics = deque(maxlen=1000)  # Memory only, bounded, never user text.

    def _capabilities(self):
        capabilities = {}
        failures = []
        for name, backend in self.backends.items():
            try:
                capabilities[name] = backend.capabilities()
            except TranslationError as error:
                failures.append(error)
                capabilities[name] = BackendCapabilities(devices=frozenset())
        return capabilities, failures

    def decide(self, request: TranslationRequest, capabilities=None) -> RouteDecision:
        if request.source_language == request.target_language:
            return RouteDecision("passthrough", "source equals target", (), "none", request.performance_profile)
        if capabilities is None:
            with offline_scope():
                capabilities, _failures = self._capabilities()
        policy = self.policy.profile(request.performance_profile, request.cpu_threads)
        source, target = request.source_language, request.target_language
        pair = (source, target)
        balanced = request.performance_profile in {PerformanceProfile.BALANCED, PerformanceProfile.AUTOMATIC, PerformanceProfile.TURBO}
        # Measured EN/RU quality is stronger with the dedicated Argos models,
        # including Maximum. Larger multilingual models are not universally better.
        quality_first = (policy.prefer_quality and pair not in self.policy.argos_preferred_pairs) or (balanced and (pair in self.policy.quality_pairs or pair not in self.policy.argos_preferred_pairs))
        order = ["m2m100", "argos"] if quality_first else ["argos", "m2m100"]
        candidates = []
        for name in order:
            caps = capabilities.get(name)
            if name == "m2m100" and not policy.allow_quality:
                continue
            if caps and caps.supports_pair(source, target):
                candidates.append(RouteCandidate(name, PairKind.DIRECT))
        argos = capabilities.get("argos")
        if argos and argos.supports_pair(source, target, PairKind.PIVOT):
            candidates.append(RouteCandidate("argos", PairKind.PIVOT))
        if not candidates:
            if not any(caps.languages or caps.direct_pairs for caps in capabilities.values()):
                raise ModelMissingError()
            raise UnsupportedLanguageError()
        first, *fallbacks = candidates
        reason = f"{first.kind.value} {'quality' if first.backend == 'm2m100' else 'primary'} route for {source}-{target}"
        return RouteDecision(first.backend, reason, tuple(fallbacks), request.device_preference.value,
                             request.performance_profile, first.kind)

    def translate(self, request: TranslationRequest, cancelled: Event | None = None,
                  *, backend_only: str | None = None) -> TranslationResult:
        cancelled = cancelled or Event()
        started = perf_counter()
        with offline_scope():
            check_cancelled(cancelled)
            if len(request.text) > self.policy.max_text_chars:
                raise InputTooLongError()
            if not request.text.strip():
                return TranslationResult(request.text, request.source_language, request.target_language,
                                         "passthrough", "none", 0, "empty text", False, request.request_id)
            source, target = self.languages.resolve(request.text, request.source_language, request.target_language)
            request = replace(request, source_language=source, target_language=target)
            if source == target:
                return TranslationResult(request.text, source, target, "passthrough", "none",
                                         (perf_counter() - started) * 1000, "source equals target", False, request.request_id)
            capabilities, failures = self._capabilities()
            if backend_only:
                # Benchmark backend-only mode has no cross-backend fallback.
                caps = capabilities.get(backend_only)
                if not caps or not (caps.direct_pairs or caps.languages):
                    raise ModelMissingError()
                if caps.supports_pair(source, target):
                    kind = PairKind.DIRECT
                elif caps.supports_pair(source, target, PairKind.PIVOT):
                    kind = PairKind.PIVOT
                else:
                    raise UnsupportedLanguageError()
                decision = RouteDecision(backend_only, f"benchmark {kind.value} route", (), request.device_preference.value,
                                         request.performance_profile, kind)
            else:
                decision = self.decide(request, capabilities)
            candidates = (RouteCandidate(decision.backend, decision.kind), *decision.fallback_chain)
            policy = self.policy.profile(request.performance_profile, request.cpu_threads)
            last_error = failures[-1] if failures else BackendUnavailableError()
            attempted = 0
            for candidate in candidates:
                try:
                    devices = self.devices.devices(request.device_preference, policy, capabilities[candidate.backend])
                except TranslationError as error:
                    last_error = error
                    attempted += 1
                    continue
                for device in devices:
                    try:
                        options_list = self.devices.options(device, policy)
                    except TranslationError as error:
                        last_error = error
                        attempted += 1
                        continue
                    for options in options_list:
                        check_cancelled(cancelled)
                        tick = perf_counter()
                        fallback = attempted > 0
                        attempted += 1
                        try:
                            output = self.runtime.run(candidate.backend, request, candidate.kind, options, cancelled)
                            check_cancelled(cancelled)
                            if request.text.strip() and not output.text.strip():
                                raise TranslationError()
                        except TranslationCancelledError:
                            raise
                        except Exception as error:
                            # Native exception messages can contain user tokens: never log them.
                            last_error = error if isinstance(error, TranslationError) else (
                                DeviceUnavailableError() if device == "cuda" else TranslationError())
                            self._metric(candidate.backend, request, device, tick, False, fallback, type(error).__name__)
                            # A different compute type is useful only for device initialization failures.
                            if isinstance(last_error, DeviceUnavailableError):
                                continue
                            break
                        self._metric(candidate.backend, request, device, tick, True, fallback)
                        duration = (perf_counter() - started) * 1000
                        reason = decision.reason if candidate == candidates[0] else f"fallback {candidate.kind.value} route for {source}-{target}"
                        logger.info("translation completed backend=%s route=%s device=%s model_ids=%s chars=%d duration_ms=%.2f fallback=%s",
                                    candidate.backend, reason, device, ",".join(output.model_ids), len(request.text), duration, fallback)
                        return TranslationResult(output.text, source, target, candidate.backend, device, duration,
                                                 reason, fallback, request.request_id, output.model_ids, options.compute_type)
            raise last_error from None

    def _metric(self, backend, request, device, started, success, fallback, error_type=None):
        duration = (perf_counter() - started) * 1000
        self.metrics.append(TranslationMetric(backend, f"{request.source_language}-{request.target_language}",
                                              len(request.text), duration, device, success, fallback, error_type))
        if not success:
            logger.warning("translation failed backend=%s device=%s chars=%d duration_ms=%.2f fallback=%s error_type=%s",
                           backend, device, len(request.text), duration, fallback, error_type)

    def shutdown(self):
        self.runtime.shutdown()
        self.languages.shutdown()
