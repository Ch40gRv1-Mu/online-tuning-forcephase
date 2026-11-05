"""Scientific cache identity: changed input, budget, verifier or receipt blocks reuse."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from run_matrix import hydrate_cached


class ReuseIdentity(unittest.TestCase):
    def test_only_unchanged_physical_measurements_can_be_reused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'original.json';cache=root/'cache.json';dest=root/'r1.json'
            identity={'mode':'static','checker':'binary-checked'}
            row={'hash':'a'*32,'sha256':'input-A'}
            record={'run_id':'r1','identity':identity,'input_sha256':'input-A','hash':row['hash'],
                    'seed':0,'action':'D','cutoff_s':600,'status':'UNSAT','verify':'VERIFIED_LRAT','contended':False}
            source.write_text(json.dumps(record));original=source.read_bytes()
            cache.write_text(json.dumps({'record_path':str(source),'record_sha256':hashlib.sha256(original).hexdigest()}))
            for badrow,badidentity,budget in [({**row,'sha256':'input-B'},identity,600),
                                            (row,{**identity,'checker':'other'},600),(row,identity,120)]:
                with self.assertRaises(ValueError):hydrate_cached(cache,dest,badidentity,badrow,0,'D',budget)
                self.assertFalse(dest.exists())
            self.assertEqual(hydrate_cached(cache,dest,identity,row,0,'D',600),'r1')
            self.assertEqual(source.read_bytes(),original);self.assertEqual(dest.read_bytes(),original)
            dest.unlink();source.write_text(json.dumps({**record,'status':'ERROR'}))
            with self.assertRaises(ValueError):hydrate_cached(cache,dest,identity,row,0,'D',600)


if __name__=='__main__':unittest.main()
