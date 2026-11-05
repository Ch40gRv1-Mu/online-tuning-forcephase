"""Import only a SHA-bound completed development receipt bundle; never launches work."""
import argparse,csv,hashlib,io,json,tarfile
from pathlib import Path,PurePosixPath

def digest(data):return hashlib.sha256(data).hexdigest()

def import_archive(archive,expected_sha256,destination,expected_spec,expected_cohort):
    archive=Path(archive);destination=Path(destination)
    if destination.exists():raise ValueError('immutable import destination exists')
    if not expected_sha256 or digest(archive.read_bytes())!=expected_sha256:
        raise ValueError('archive checksum mismatch')
    payload={};total=0
    with tarfile.open(archive,'r:gz') as source:
        for member in source:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not member.isfile() or str(path)!=member.name:
                raise ValueError('unsafe archive member')
            if member.name!='RECEIPT_MANIFEST.json' and path.parts[0] not in ('metadata','results','logs'):
                raise ValueError('unexpected export namespace')
            if member.name in payload:raise ValueError('duplicate archive member')
            if member.size>100_000_000:raise ValueError('unexpected receipt member size')
            total+=member.size
            if total>256*1024**2:raise ValueError('receipt bundle exceeds total import bound')
            payload[member.name]=source.extractfile(member).read()
    manifest=json.loads(payload.get('RECEIPT_MANIFEST.json',b'{}'))
    if manifest.get('root_role')!='completed_development_stage':raise ValueError('wrong data role')
    files=manifest.get('files',[])
    paths=[r['path'] for r in files]
    if len(set(paths))!=len(paths) or set(paths)!=set(payload)-{'RECEIPT_MANIFEST.json'}:
        raise ValueError('manifest coverage mismatch')
    for row in files:
        if digest(payload[row['path']])!=row['sha256']:raise ValueError('member checksum mismatch')
    if payload.get('metadata/spec.json')!=Path(expected_spec).read_bytes():
        # Exported JSON may have formatting differences; canonical content must be identical.
        if json.loads(payload.get('metadata/spec.json',b'{}'))!=json.loads(Path(expected_spec).read_text()):
            raise ValueError('frozen specification mismatch')
    cohort=Path(expected_cohort).read_bytes()
    if payload.get('metadata/cohort.csv')!=cohort:raise ValueError('frozen cohort mismatch')
    rows=list(csv.DictReader(io.StringIO(cohort.decode())))
    if not rows or any(r['role'] not in ('development_fit','development_feedback') for r in rows):
        raise ValueError('protected input cannot enter development importer')
    completion=json.loads(payload.get('results/completion.json',b'{}'))
    if completion.get('status')!='COMPLETE':raise ValueError('stage is not complete')
    # Nothing is written until the full bundle, frozen plan and role boundary pass.
    destination.mkdir(parents=True)
    for name,data in payload.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    receipt={'status':'IMPORTED_HASH_VERIFIED_DEVELOPMENT_ONLY','archive_sha256':expected_sha256,
             'files':len(files),'parents':len(rows),'spec_sha256':digest(Path(expected_spec).read_bytes()),
             'cohort_sha256':digest(cohort),'scope':'Identity/transport check; strict matrix analysis is still required'}
    (destination/'LOCAL_IMPORT_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--expected-sha256',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--spec',type=Path,required=True);p.add_argument('--cohort',type=Path,required=True)
    a=p.parse_args();print(json.dumps(import_archive(a.archive,a.expected_sha256,a.out,a.spec,a.cohort)))

if __name__=='__main__':main()
