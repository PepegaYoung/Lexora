"""Convert original FreeDict TEI to a searchable SQLite dictionary.

Usage: python build_dictionary.py input.tei
Data: Karl Bartel / WikDict / FreeDict / Wiktionary / DBnary, CC BY-SA 3.0.
Conversion preserves the headwords, pronunciations, parts of speech and senses;
this converted dataset is distributed under the same CC BY-SA 3.0 license.
"""
from pathlib import Path
import sqlite3
import sys
import xml.etree.ElementTree as ET


def build(source, target):
    ns = {'t':'http://www.tei-c.org/ns/1.0'}
    conn = sqlite3.connect(target)
    conn.execute('CREATE TABLE IF NOT EXISTS dictionary (term TEXT, meaning TEXT)')
    conn.execute('DELETE FROM dictionary')
    count = 0
    for event,element in ET.iterparse(source,events=['end']):
        if element.tag != '{'+ns['t']+'}entry':
            continue
        orth = element.find('t:form/t:orth',ns)
        if orth is None:
            continue
        word = ''.join(orth.itertext()).strip().casefold()
        pronunciations = [''.join(e.itertext()).strip() for e in element.findall('t:form/t:pron',ns)][:2]
        pos = element.find('t:gramGrp/t:pos',ns)
        senses = []
        for sense in element.findall('t:sense',ns):
            definitions = [''.join(e.itertext()).strip() for e in sense.findall('t:def',ns)]
            translations = [''.join(e.itertext()).strip() for e in sense.findall('.//t:quote',ns)]
            value = ' — '.join(dict.fromkeys(definitions + translations))
            if value:
                senses.append(value)
        if not senses:
            senses = [''.join(e.itertext()).strip() for e in element.findall('.//t:quote',ns)]
        header = ' · '.join(pronunciations+([pos.text] if pos is not None and pos.text else []))
        meaning = '\n'.join(([header] if header else [])+[f'{i+1}. {s}' for i,s in enumerate(senses)])
        if word and senses:
            conn.execute('INSERT INTO dictionary VALUES(?,?)',(word,meaning))
            count += 1
        element.clear()
    conn.execute('CREATE INDEX IF NOT EXISTS dictionary_term ON dictionary(term)')
    conn.commit()
    conn.close()
    return count


if __name__=='__main__':
    print(build(sys.argv[1],Path(__file__).parent/'data'/'dictionary.sqlite3'))
