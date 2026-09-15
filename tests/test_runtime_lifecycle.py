from threading import Event, Thread

from app.engine.runtime.runtime_manager import RuntimeManager
from app.engine.types import PairKind
from test_router import FakeBackend, FakeDevices, request
from app.engine.router.routing_policy import RoutingPolicy


def test_startup_first_request_reuse_idle_reload_shutdown():
    backend = FakeBackend("argos")
    clock = [0]
    runtime = RuntimeManager({"argos": backend}, idle_timeout_seconds=1000, clock=lambda: clock[0])
    options = FakeDevices().options("cpu", RoutingPolicy().profile(request().performance_profile))[0]
    assert backend.loads == 0
    runtime.run("argos", request(), PairKind.DIRECT, options, Event())
    assert backend.loads == 1
    runtime.run("argos", request(), PairKind.DIRECT, options, Event())
    assert backend.loads == 1
    clock[0] = 1001
    assert runtime.release_idle()
    assert not backend.loaded
    runtime.run("argos", request(), PairKind.DIRECT, options, Event())
    assert backend.loads == 2
    runtime.shutdown()
    assert not backend.loaded


def test_idle_cannot_unload_during_native_inference():
    entered, release, finished = Event(), Event(), Event()
    backend = FakeBackend("argos")
    original = backend.translate

    def slow(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)
    backend.translate = slow
    runtime = RuntimeManager({"argos": backend}, idle_timeout_seconds=1000)
    options = FakeDevices().options("cpu", RoutingPolicy().profile(request().performance_profile))[0]
    worker = Thread(target=lambda: runtime.run("argos", request(), PairKind.DIRECT, options, Event()))
    worker.start()
    assert entered.wait(2)
    idle = Thread(target=lambda: (runtime.release_idle(), finished.set()))
    idle.start()
    assert not finished.wait(0.03)
    release.set()
    worker.join(3)
    idle.join(3)
    assert backend.loaded
    runtime.shutdown()
