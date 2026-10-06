import pytest

from tools.aw081_nmt_batch_scheduler_5pdf import require_exact_replay, run, QA, read


def accepted():
    return dict(pass_=True,results={str(size):dict(exact_prepared_inputs=True,exact_outputs=True,mismatches=[])
                                    for size in (1,2,4,8)})


@pytest.mark.parametrize('size',[1,2,4,8])
def test_one_native_output_mismatch_blocks_final_even_if_summary_claims_pass(size):
    record=accepted();record['results'][str(size)]['mismatches']=[{'source':'中文','before':'a','after':'b'}]
    with pytest.raises(RuntimeError,match='mandatory exact native replay'):require_exact_replay(record)


def test_incomplete_or_inexact_inputs_block_final():
    record=accepted();del record['results']['4']
    with pytest.raises(RuntimeError):require_exact_replay(record)
    record=accepted();record['results']['8']['exact_prepared_inputs']=False
    with pytest.raises(RuntimeError):require_exact_replay(record)
    require_exact_replay(accepted())


def test_rejected_captured_replay_prevents_pdf_run_before_any_side_effect(monkeypatch,tmp_path):
    import tools.aw081_nmt_batch_scheduler_5pdf as harness
    # Real observed counterexamples are the regression, not a mocked model.
    replay=read(QA/'batch_replay.json')
    assert replay['results']['1']['exact_outputs']
    assert len(replay['results']['2']['mismatches'])==26
    monkeypatch.setattr(harness,'QA',tmp_path)
    monkeypatch.setattr(harness,'read',lambda path:replay)
    with pytest.raises(RuntimeError,match='Final fixed5 forbidden'):run('after')
    assert list(tmp_path.iterdir())==[]
