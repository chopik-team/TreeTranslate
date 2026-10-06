from . import wikidata, cedict, agrovoc, wiktionary

ADAPTERS = {'wikidata': wikidata.parse, 'cedict': cedict.parse, 'agrovoc': agrovoc.parse, 'wiktionary': wiktionary.parse}
