from app.services.hardware_profile_service import HardwareProfile, HardwareProfileService


def test_recommends_gpu_turbo_for_powerful_hardware() -> None:
    recommendation = HardwareProfileService.recommend(
        HardwareProfile("Test CPU", logical_cores=24, ram_gb=32, gpu="Test GPU")
    )
    assert recommendation.device == "GPU"
    assert recommendation.profile == "Турбо"
    assert recommendation.cpu_threads == "12"
    assert recommendation.ram_limit == "24 GB"


def test_recommends_economy_cpu_when_gpu_is_unavailable() -> None:
    recommendation = HardwareProfileService.recommend(
        HardwareProfile("Test CPU", logical_cores=4, ram_gb=8, gpu="Не определена")
    )
    assert recommendation.device == "CPU"
    assert recommendation.profile == "Эконом"
    assert recommendation.gpu_usage == "Отключено"
    assert recommendation.ram_limit == "6 GB"


def test_hardware_profile_is_persisted_between_sessions(tmp_path) -> None:
    profile_path = tmp_path / "hardware_profile.json"
    hardware = HardwareProfile("Saved CPU", logical_cores=16, ram_gb=32, gpu="Saved GPU")
    HardwareProfileService(profile_path).save(hardware)

    restored = HardwareProfileService(profile_path).load()
    assert restored == hardware
    text = profile_path.read_text(encoding="utf-8")
    assert "Saved CPU" in text
    assert '"recommendation"' in text


def test_device_names_are_normalized_without_fake_values() -> None:
    assert HardwareProfileService._normalize_device_name(
        "AMD Ryzen 7 5700X 8-Core Processor", "Не определён"
    ) == "AMD Ryzen 7 5700X"
    assert HardwareProfileService._normalize_device_name(
        "Intel(R) Core(TM) i7-12700K CPU @ 3.60GHz", "Не определён"
    ) == "Intel Core i7-12700K"
    assert HardwareProfileService._normalize_device_name("", "Не определена") == "Не определена"


def test_legacy_hardware_profile_without_vram_still_loads(tmp_path) -> None:
    profile_path = tmp_path / "hardware_profile.json"
    profile_path.write_text(
        '{"hardware":{"cpu":"CPU","logical_cores":8,"ram_gb":16,"gpu":"GPU"}}',
        encoding="utf-8",
    )
    assert HardwareProfileService(profile_path).load().vram_gb == 0
