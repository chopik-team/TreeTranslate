import re
from .models import ConstraintPlan
from .errors import ConstraintFailure


class PlaceholderCodec:
    def __init__(self,pattern='ZXQ{:04d}QXZ'):
        if pattern not in ('ZXQ{:04d}QXZ','TTTERM{:04d}','__TTTERM{:04d}__'):
            raise ConstraintFailure('unknown_placeholder_policy')
        self.pattern=pattern

    def encode(self,text,matches):
        values=[];replacements=[];forbidden=[];serial=1
        for match in matches:
            forbidden.extend(match.entry.forbidden_target_variants)
            if match.entry.mode=='FORBIDDEN':
                forbidden.append(match.entry.target_term);continue
            while True:
                token=self.pattern.format(serial);serial+=1
                if token.casefold() not in text.casefold():break
            value=text[match.start:match.end] if match.entry.mode=='KEEP' else match.entry.target_term
            values.append((token,value));replacements.append((match.start,match.end,token))
        masked=text
        for start,end,token in reversed(replacements):
            # Separate source ASCII codes from generated markers. Evaluate the
            # original neighbors: do not change adjacent Chinese term behavior.
            left=' ' if start and re.match(r'[A-Za-z0-9_]',text[start-1]) else ''
            right=' ' if end<len(text) and re.match(r'[A-Za-z0-9_]',text[end]) else ''
            masked=masked[:start]+left+token+right+masked[end:]
        return ConstraintPlan(masked,tuple(values),tuple(forbidden),tuple(matches))

    def restore(self,translated,plan):
        for token,_ in plan.mapping:
            # A valid token embedded in a corrupted longer token is not intact.
            matches=list(re.finditer(r'(?<![A-Za-z0-9_])'+re.escape(token)+r'(?![A-Za-z0-9_])',translated))
            if len(matches)!=1 or translated.count(token)!=1:raise ConstraintFailure('placeholder_integrity')
        tokens={token for token,_ in plan.mapping}
        for value in re.findall(r'ZXQ\d+QXZ|__TTTERM\d+__|TTTERM\d+',translated):
            if value not in tokens and value not in plan.text:raise ConstraintFailure('unexpected_placeholder')
        # Reordering is allowed: identity, not position, determines restoration.
        lookup=dict(plan.mapping)
        if not lookup:return translated
        return re.sub('|'.join(re.escape(t) for t in lookup),lambda m:lookup[m.group()],translated)
