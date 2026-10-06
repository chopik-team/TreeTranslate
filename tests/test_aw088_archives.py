from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile, ZipInfo, ZIP_STORED
import pytest
from app.documents.control import JobControl
from app.documents.errors import DocumentError
from app.documents.zip_archive import ArchiveLimits, validate_members, inventory, disk_budget, check_disk
from app.engine.errors import TranslationCancelledError


def info(size, name='file.bin', compressed=None):
    value=ZipInfo(name);value.file_size=size;value.compress_size=size if compressed is None else compressed
    return value


@pytest.mark.parametrize('size',[256*1024**2+1,1_600_000_000,2*1024**3])
def test_large_metadata_accepted(size):
    assert validate_members([info(size)])[0].size==size


@pytest.mark.parametrize('size',[2*1024**3+1,16*1024**3+1])
def test_member_or_total_over_budget(size):
    with pytest.raises(DocumentError):validate_members([info(size)])


def test_total_and_count_boundaries():
    assert len(validate_members([info(2*1024**3,str(n)) for n in range(8)]))==8
    with pytest.raises(DocumentError):validate_members([info(2*1024**3,str(n)) for n in range(9)])
    assert len(validate_members([info(0,str(n)) for n in range(100000)]))==100000
    with pytest.raises(DocumentError):validate_members([info(0)]*100001)


def test_bomb_unchanged_for_large_metadata():
    with pytest.raises(DocumentError):validate_members([info(1_600_000_000,compressed=1000)])


def test_cancel_inside_metadata_iteration():
    control=JobControl();calls=[0]
    original=control.checkpoint
    def check():
        calls[0]+=1
        if calls[0]==3:control.cancel()
        original()
    control.checkpoint=check
    with pytest.raises(TranslationCancelledError):validate_members([info(1,str(n)) for n in range(20)],control=control)
    assert calls[0]==3


def test_real_zip64_headers_central_directory_and_crc(tmp_path,monkeypatch):
    import zipfile
    monkeypatch.setattr(zipfile,'ZIP64_LIMIT',32)
    path=tmp_path/'zip64.zip'
    with ZipFile(path,'w',compression=ZIP_STORED,allowZip64=True) as archive:
        with archive.open('payload.bin','w',force_zip64=True) as stream:stream.write(b'payload'*20)
    raw=path.read_bytes()
    assert b'PK\x06\x06' in raw and b'PK\x06\x07' in raw
    members=inventory(path,JobControl())
    assert members[0].size==140
    with ZipFile(path) as archive:assert archive.testzip() is None and archive.read('payload.bin')==b'payload'*20


@pytest.mark.parametrize('size,accepted',[(4*1024**3,True),(4*1024**3+1,False)])
def test_compressed_container_boundary(tmp_path,monkeypatch,size,accepted):
    path=tmp_path/'input.zip'
    with ZipFile(path,'w') as archive:archive.writestr('file.bin',b'abc')
    original=Path.stat
    def simulated(p,*a,**kw):
        return SimpleNamespace(st_size=size) if p==path else original(p,*a,**kw)
    monkeypatch.setattr(Path,'stat',simulated)
    if accepted:assert inventory(path,JobControl())[0].size==3
    else:
        with pytest.raises(DocumentError):inventory(path,JobControl())


def test_disk_budget_depends_on_compression_and_one_working_member(tmp_path,monkeypatch):
    import shutil
    members=validate_members([info(2*1024**3,str(n)) for n in range(8)])
    budget=disk_budget(members,archive_bytes=1024**3)
    assert budget['required']<sum(m.size for m in members)
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(free=budget['required']-1))
    with pytest.raises(DocumentError,match='свободного места'):check_disk(members,tmp_path,tmp_path,1024**3)
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(free=budget['required']))
    assert check_disk(members,tmp_path,tmp_path,1024**3)==budget


def test_scanning_reports_entries_and_can_cancel(tmp_path):
    path=tmp_path/'scan.zip'
    with ZipFile(path,'w') as archive:
        for n in range(4):archive.writestr(str(n),b'abc')
    control=JobControl();values=[]
    def progress(i,t):
        values.append((i,t))
        if i==2:control.cancel()
    with pytest.raises(TranslationCancelledError):inventory(path,control,progress=progress)
    assert values==[(1,4),(2,4)]


def test_previous_payloads_removed_before_next_translation(tmp_path,monkeypatch):
    from test_zip_output import archive,docx_bytes,run
    import app.documents.archive_job as jobs
    source=archive(tmp_path,[(f'folder/{n}.docx',docx_bytes()) for n in range(5)])
    extract=jobs.extract;observed=[]
    def checked(path,root,members,control,**kwargs):
        assert not list(root.rglob('*.docx'))
        assert not list((root.parent/'output').rglob('*.docx'))
        result=extract(path,root,members,control,**kwargs)
        observed.append(len(list(root.rglob('*.docx'))))
        return result
    monkeypatch.setattr(jobs,'extract',checked)
    output,=run(source)
    assert observed==[1]*5
    with ZipFile(output) as archive:assert len([n for n in archive.namelist() if n.endswith('.docx')])==5
