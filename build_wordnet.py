"""Convert the Princeton WordNet 3.1 data archive; retain the original licence."""
from pathlib import Path
import sqlite3
import sys
import tarfile


def build(archive,target):
    conn = sqlite3.connect(target)
    count = 0
    try:
        with conn,tarfile.open(archive) as package:
            conn.execute('CREATE TABLE IF NOT EXISTS dictionary(term TEXT,meaning TEXT)')
            conn.execute('DELETE FROM dictionary')
            license_header = []
            for member in package:
                name = Path(member.name).name
                if name=='LICENSE':
                    folder = Path(target).parent.parent/'licenses'/'WordNet'
                    folder.mkdir(parents=True,exist_ok=True)
                    (folder/'LICENSE').write_bytes(package.extractfile(member).read())
                if name not in ('data.noun','data.verb','data.adj','data.adv'):continue
                for raw in package.extractfile(member):
                    line = raw.decode('utf-8').rstrip()
                    if name=='data.noun' and line.startswith(' '):license_header.append(line)
                    if not line or not line[0].isdigit() or ' | ' not in line:continue
                    head,gloss = line.split(' | ',1)
                    values = head.split()
                    words = int(values[3],16)
                    part = {'n':'noun','v':'verb','a':'adjective','s':'adjective','r':'adverb'}[values[2]]
                    for i in range(words):
                        lemma = values[4+i*2].replace('_',' ').casefold()
                        conn.execute('INSERT INTO dictionary VALUES(?,?)',(lemma,part+' · '+gloss))
                        count += 1
            conn.execute('CREATE INDEX IF NOT EXISTS dictionary_term ON dictionary(term)')
            if license_header:
                folder = Path(target).parent.parent/'licenses'/'WordNet'
                folder.mkdir(parents=True,exist_ok=True)
                (folder/'LICENSE').write_text('\n'.join(license_header)+'\n',encoding='utf-8')
    finally:conn.close()
    return count


if __name__=='__main__':
    print(build(sys.argv[1],Path(__file__).parent/'data'/'wordnet.sqlite3'))
