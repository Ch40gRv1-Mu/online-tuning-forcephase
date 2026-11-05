"""End-to-end leakage test using synthetic identity metadata, no SAT outcomes."""
import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FreezeTests(unittest.TestCase):
    def test_equivalent_test_cases_cannot_enter_development_or_clean_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ids={i:f"{i:032x}" for i in range(1,10)}
            iso={1:"A",2:"P",3:"Q",4:"Q",5:"A",6:"D",7:"E",8:"P",9:"D"}
            meta=sqlite3.connect(root/"meta.db")
            meta.execute("create table features(hash text,isohash text,family text,result text)")
            meta.executemany("insert into features values(?,?,?,?)",[(ids[i],iso[i],"FORBIDDEN_FAMILY","FORBIDDEN_RESULT") for i in ids]);meta.commit();meta.close()
            base=sqlite3.connect(root/"base.db")
            base.execute("create table features(hash text,variables integer,clauses integer,bytes integer)")
            base.executemany("insert into features values(?,10,30,1000)",[(h,) for h in ids.values()]);base.commit();base.close()
            def write(name, numbers):
                with (root/name).open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=['hash']);w.writeheader();w.writerows({'hash':ids[i]} for i in numbers)
            write('test_candidates.csv',[1,2,3,4])
            write('development_candidates.csv',[5,6,7,9])
            write('exposed_identifiers.csv',[5,8])
            script=Path(__file__).with_name('freeze_cohorts.py')
            subprocess.run([sys.executable,str(script),'--out',str(root),'--meta',str(root/'meta.db'),'--base',str(root/'base.db')],check=True,capture_output=True)
            with (root/'development_frozen.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertEqual({r['isohash'] for r in rows},{'D','E'})
            self.assertEqual(len(rows),2)
            self.assertNotIn(ids[5],{r['hash'] for r in rows})
            with (root/'confirmation_sealed.csv').open() as f:test=list(csv.DictReader(f))
            self.assertEqual(len(test),1)
            self.assertEqual(test[0]['hash'],min(ids[3],ids[4]))
            self.assertNotIn('FORBIDDEN',(root/'cohort_freeze.json').read_text())


if __name__=='__main__':unittest.main()
