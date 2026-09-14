from app.engine.interfaces import EngineCapabilities, EngineStatus, TranslationEngine


def test_engine_boundary_exposes_backend_neutral_capabilities_and_status() -> None:
    capabilities = EngineCapabilities()
    assert capabilities.supports_cpu
    assert not capabilities.supports_gpu
    assert not capabilities.supports_parallel_jobs
    assert not capabilities.supports_streaming_text
    assert not capabilities.supports_ocr
    assert EngineStatus.READY.name == "READY"
    assert {"initialize", "shutdown", "translate_text", "translate_file", "pause", "resume", "cancel", "capabilities", "get_status"} <= TranslationEngine.__abstractmethods__
