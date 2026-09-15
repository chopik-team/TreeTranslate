from app.engine.errors import BackendUnavailableError, DeviceUnavailableError
from app.engine.router.routing_policy import ProfilePolicy
from app.engine.types import BackendCapabilities, DevicePreference, InferenceOptions


class DeviceManager:
    """Query CT2 itself, lazily. nvidia-smi availability is not inference support."""

    def gpu_available(self) -> bool:
        try:
            import ctranslate2
            return ctranslate2.get_cuda_device_count() > 0
        except (ImportError, RuntimeError, OSError):
            return False

    def devices(self, preference: DevicePreference, policy: ProfilePolicy,
                capabilities: BackendCapabilities) -> tuple[str, ...]:
        if preference == DevicePreference.CPU:
            if "cpu" not in capabilities.devices:
                raise DeviceUnavailableError("Этот компонент не поддерживает CPU.")
            return ("cpu",)
        if preference == DevicePreference.GPU:
            if "cuda" not in capabilities.devices or not self.gpu_available():
                raise DeviceUnavailableError()
            return ("cuda",)
        candidates = []
        if policy.auto_gpu and "cuda" in capabilities.devices and self.gpu_available():
            candidates.append("cuda")
        if "cpu" in capabilities.devices:
            candidates.append("cpu")
        if not candidates:
            raise DeviceUnavailableError()
        return tuple(candidates)

    def options(self, device: str, policy: ProfilePolicy) -> tuple[InferenceOptions, ...]:
        try:
            if device == "cuda":
                from app.engine.runtime.cuda_libraries import load_cuda_libraries
                load_cuda_libraries()
            import ctranslate2
            supported = ctranslate2.get_supported_compute_types(device)
        except (ImportError, RuntimeError, OSError):
            if device == "cuda":
                raise DeviceUnavailableError() from None
            raise BackendUnavailableError() from None
        order = ("int8_float16", "int8_float32", "float32") if device == "cuda" else ("int8", "int8_float32", "float32")
        options = tuple(InferenceOptions(device, compute, policy.threads, policy.beam_size,
                                          policy.batch_tokens, policy.max_input_tokens, policy.max_decoding_length)
                        for compute in order if compute in supported)
        if not options:
            raise DeviceUnavailableError()
        return options
