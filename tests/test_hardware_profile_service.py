from app.services.hardware_profile_service import HardwareProfile, HardwareProfileService


def test_recommends_gpu_turbo_for_powerful_hardware() -> None:
    recommendation = HardwareProfileService.recommend(
        HardwareProfile("Test CPU", logical_cores=24, ram_gb=32, gpu="Test GPU")
    )
    assert recommendation.device == "GPU"
    assert recommendation.profile == "Турбо"
    assert recommendation.cpu_threads == "12"
    assert recommendation.ram_limit == "32 GB"


def test_recommends_economy_cpu_when_gpu_is_unavailable() -> None:
    recommendation = HardwareProfileService.recommend(
        HardwareProfile("Test CPU", logical_cores=4, ram_gb=8, gpu="Не определена")
    )
    assert recommendation.device == "CPU"
    assert recommendation.profile == "Эконом"
    assert recommendation.gpu_usage == "Отключено"
    assert recommendation.ram_limit == "8 GB"


def test_hardware_profile_is_persisted_between_sessions(tmp_path) -> None:
    profile_path = tmp_path / "hardware_profile.json"
    hardware = HardwareProfile("Saved CPU", logical_cores=16, ram_gb=32, gpu="Saved GPU")
    HardwareProfileService(profile_path).save(hardware)

    restored = HardwareProfileService(profile_path).load()
    assert restored == hardware
    text = profile_path.read_text(encoding="utf-8")
    assert "Saved CPU" in text
    assert '"recommendation"' in text
