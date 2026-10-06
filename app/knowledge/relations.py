"""Conservative polarity validation for curated structures, not free prose."""
import re


def negative_relation(source, target):
    # Exclude lexical absence of quantity and the word 'different'. Question
    # particles (是否) are not an asserted negative condition.
    negative=re.findall(r'不要|不得|禁止|不能|没有|未|无|不(?!同|足|推荐|良|正常)',source)
    rendered=re.findall(r'\bне\b|\bнет\b|\bбез\b|\bотсутств\w*|\bзапрещ\w*',target,re.I)
    lexical=bool(re.search(r'不良|不正常',source))
    lexical_rendered=bool(re.search(r'\b(?:неисправ\w*|неправил\w*|ненормал\w*|некоррект\w*|плох\w*)\b',target,re.I))
    return len(rendered)>=len(negative) and (not lexical or lexical_rendered or len(rendered)>len(negative))
