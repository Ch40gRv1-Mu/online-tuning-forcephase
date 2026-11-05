"""Meaningful boundary tests for the new transport/import path, not performance trials."""
import hashlib,io,json,tarfile,tempfile,unittest
from pathlib import Path
from import_receipts import import_archive

class ImportBoundary(unittest.TestCase):
    def fixture(self,root,role='development_fit',extra=None,tamper=False):
        spec=root/'spec.json';cohort=root/'cohort.csv'
        spec.write_text('{"stage":"long600_fit16","cutoff_s":600}\n')
        cohort.write_text('hash,role\n'+'a'*32+','+role+'\n')
        files={'metadata/spec.json':spec.read_bytes(),'metadata/cohort.csv':cohort.read_bytes(),
               'results/completion.json':b'{"status":"COMPLETE"}'}
        if extra:files.update(extra)
        manifest={'root_role':'completed_development_stage','files':[{'path':k,'sha256':hashlib.sha256(v).hexdigest()} for k,v in files.items()]}
        if tamper:files['metadata/spec.json']=b'{}'
        files['RECEIPT_MANIFEST.json']=json.dumps(manifest).encode()
        archive=root/'receipt.tar.gz'
        with tarfile.open(archive,'w:gz') as t:
            for name,data in files.items():
                item=tarfile.TarInfo(name);item.size=len(data);t.addfile(item,io.BytesIO(data))
        return archive,hashlib.sha256(archive.read_bytes()).hexdigest(),spec,cohort

    def check(self,root,values):
        a,h,s,c=values;return import_archive(a,h,root/'imported',s,c)

    def test_valid_complete_development_bundle_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);values=self.fixture(root);receipt=self.check(root,values)
            self.assertEqual(receipt['parents'],1)
            with self.assertRaises(ValueError):self.check(root,values)

    def test_failed_checksum_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,h,s,c=self.fixture(root)
            with self.assertRaises(ValueError):import_archive(a,'0'*64,root/'imported',s,c)
            self.assertFalse((root/'imported').exists())

    def test_member_tampering_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):self.check(root,self.fixture(root,tamper=True))
            self.assertFalse((root/'imported').exists())

    def test_path_traversal_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):self.check(root,self.fixture(root,extra={'../outside':b'bad'}))
            self.assertFalse((root/'imported').exists())

    def test_gate_and_test_roles_cannot_enter_development_importer(self):
        for role in ('development_gate','test','protected_candidate'):
            with self.subTest(role=role),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                with self.assertRaises(ValueError):self.check(root,self.fixture(root,role=role))
                self.assertFalse((root/'imported').exists())

if __name__=='__main__':unittest.main()
