import hashlib,json,tempfile,unittest
from pathlib import Path
from matrix_reuse import validate_record

class ReuseContract(unittest.TestCase):
    def fixture(self,root):
        identity={'proof_file_limit_bytes':4*1024**3,'solver_sha256':'fixed'}
        r={'run_id':'one','hash':'parent','action':'D','seed':0,'role':'development_fit',
           'input_sha256':'input','identity':identity,'cutoff_s':600,'status':'UNKNOWN',
           'verify':'NOT_ANSWERED','proof_bytes':123,'contended':False}
        path=root/'one.json';path.write_text(json.dumps(r))
        bound={k:r[k] for k in ('run_id','hash','action','seed','role','input_sha256')}
        bound['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        return r,path,{'allowed_source_identities':[identity],'reused_records':[bound]}

    def test_exact_source_bytes_are_required(self):
        with tempfile.TemporaryDirectory() as d:
            r,p,plan=self.fixture(Path(d));validate_record(r,p,plan)
            p.write_text(p.read_text()+' ')
            with self.assertRaises(ValueError):validate_record(r,p,plan)

    def test_other_cutoff_or_role_is_not_the_same_physical_measurement(self):
        with tempfile.TemporaryDirectory() as d:
            r,p,plan=self.fixture(Path(d))
            for change in ({'cutoff_s':120},{'role':'development_feedback'}):
                v={**r,**change};p.write_text(json.dumps(v));plan['reused_records'][0]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):validate_record(v,p,plan)

    def test_resource_failure_is_never_cached_as_ordinary_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            r,p,plan=self.fixture(Path(d));r['status']='ERROR';p.write_text(json.dumps(r))
            plan['reused_records'][0]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):validate_record(r,p,plan)

if __name__=='__main__':unittest.main()
